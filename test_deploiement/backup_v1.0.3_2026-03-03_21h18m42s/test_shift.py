import sys
import os

# Ensure the app context is available
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app import app, get_db_connection
from app.archivage.utils import get_config_types_boites

def test_shifting_logic(id_medecin, id_type_boite_preferee, nom_zone=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Obtenir les contraintes du médecin
        cursor.execute("""
            SELECT d.est_interne, d.id_specialty
            FROM doctors d WHERE d.id = %s
        """, (id_medecin,))
        medecin = cursor.fetchone()
        
        if not medecin:
            print("Médecin introuvable.")
            return

        est_interne = medecin['est_interne']
        id_specialty = medecin['id_specialty']
        
        # 2. Chercher les emplacements compatibles dans la zone (ou toutes les zones)
        zone_condition_main = "1=1"
        params_config = []
        if nom_zone:
            zone_condition_main = "r.nom_zone = %s"
            params_config.append(nom_zone)
            
        params_config.append(est_interne)
            
        if id_specialty is not None:
             specialty_condition_main = """
                 (
                     EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = r.id AND ars.id_specialty = %s)
                     OR NOT EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = r.id)
                 )
             """
             params_config.insert(0, id_specialty)
        else:
             specialty_condition_main = "NOT EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = r.id)"
             
        cursor.execute(f"""
            SELECT e.id, (r.largeur_cm * 10) as capacite_mm,
                   COALESCE(e.est_partageable, r.est_partageable) as est_partageable,
                   (SELECT COUNT(*) FROM archivage_emplacements_medecins WHERE id_emplacement = e.id) as nb_reservations,
                   (SELECT COUNT(*) FROM archivage_emplacements_medecins WHERE id_emplacement = e.id AND id_medecin = %s) as is_reserved_for_doc
            FROM archivage_emplacements e
            JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE {specialty_condition_main} AND r.est_interne = %s AND {zone_condition_main}
            ORDER BY r.code_etagere ASC, e.ligne_y ASC, e.colonne_x ASC
        """, tuple([id_medecin] + params_config))

        emplacements = cursor.fetchall()
        
        if not emplacements:
            print("Aucun emplacement compatible trouvé.")
            return
            
        emplacement_ids = [e['id'] for e in emplacements]
        
        # Get all boxes in these emplacements to determine global sequence
        if not emplacement_ids:
            return
            
        placeholders = ', '.join(['%s'] * len(emplacement_ids))
        cursor.execute(f"""
            SELECT b.id, b.id_medecin, b.id_emplacement, t.epaisseur_max_mm
            FROM archivage_boites b
            JOIN archivage_types_boites t ON b.id_type_boite = t.id
            WHERE b.id_emplacement IN ({placeholders})
        """, tuple(emplacement_ids))
        
        raw_boxes = cursor.fetchall()
        
        # Sort boxes by physical emplacement order, then by id_medecin (to keep them grouped logically), then by id (creation order)
        # Note: If they are already grouped, id_medecin sort is just to stabilize. 
        # Actually, let's look at how they are currently arranged:
        # A box just has id_emplacement. Inside an emplacement, we don't know the order.
        # But we assume boxes of the same doctor are contiguous inside the emplacement.
        
        emp_order_map = {e_id: idx for idx, e_id in enumerate(emplacement_ids)}
        
        sorted_boxes = sorted(raw_boxes, key=lambda b: (emp_order_map[b['id_emplacement']], b['id_medecin'], b['id']))
        
        print(f"--- ETAT ACTUEL (Total boites: {len(sorted_boxes)}) ---")
        for b in sorted_boxes:
            print(f"Boite {b['id']} (Med {b['id_medecin']}) dans Emp {b['id_emplacement']} (Epaisseur: {b['epaisseur_max_mm']})")
            
        # Determine insertion point
        insertion_index = -1
        for i in range(len(sorted_boxes)-1, -1, -1):
            if sorted_boxes[i]['id_medecin'] == id_medecin:
                insertion_index = i
                break
                
        # Mock new box
        cursor.execute("SELECT epaisseur_max_mm FROM archivage_types_boites WHERE id = %s", (id_type_boite_preferee,))
        t_box = cursor.fetchone()
        ep_new = t_box['epaisseur_max_mm']
        
        new_box = {
            'id': 'NEW',
            'id_medecin': id_medecin,
            'id_emplacement': None,
            'epaisseur_max_mm': ep_new
        }
        
        if insertion_index != -1:
            sorted_boxes.insert(insertion_index + 1, new_box)
            # The repacking should start from the emplacement of the box that was AT insertion_index
            start_emp_id = sorted_boxes[insertion_index]['id_emplacement']
            start_emp_idx = emp_order_map[start_emp_id]
            repack_start_box_idx = insertion_index + 1 # Repack new box and all after
        else:
            # We must find the first empty space or append at the end of Doctor X
            # Find the first emplacement that is completely empty or has space.
            # For simplicity of simulation, just append at the physical end of all current boxes.
            if len(sorted_boxes) > 0:
                last_box = sorted_boxes[-1]
                start_emp_idx = emp_order_map[last_box['id_emplacement']]
            else:
                start_emp_idx = 0
            sorted_boxes.append(new_box)
            repack_start_box_idx = len(sorted_boxes) - 1

        print(f"\n--- REPACKING A PARTIR DE L'EMP IDX {start_emp_idx} (Box idx {repack_start_box_idx}) ---")
        
        # We need to repack all boxes from `repack_start_box_idx` onwards.
        # Wait, if we start repacking from `start_emp_idx`, we need to take into account the boxes that are STILL in `start_emp_idx` (from 0 to repack_start_box_idx-1) to calculate its remaining capacity and sharing constraints!
        
        boxes_to_repack = sorted_boxes[repack_start_box_idx:]
        
        # Calculate current state of emplacements up to start_emp_idx
        emp_state = {}
        for emp in emplacements:
            emp_state[emp['id']] = {
                'occupe': 0,
                'medecins': set()
            }
            
        for i in range(repack_start_box_idx):
            b = sorted_boxes[i]
            emp_state[b['id_emplacement']]['occupe'] += b['epaisseur_max_mm']
            emp_state[b['id_emplacement']]['medecins'].add(b['id_medecin'])
            
        # Perform repacking
        current_emp_idx = start_emp_idx
        
        moved_boxes = []
        
        for b in boxes_to_repack:
            placed = False
            while current_emp_idx < len(emplacements):
                emp = emplacements[current_emp_idx]
                state = emp_state[emp['id']]
                
                # Check constraints
                # 1. Capacity
                if state['occupe'] + b['epaisseur_max_mm'] > emp['capacite_mm']:
                    current_emp_idx += 1
                    continue
                    
                # 2. Reservation
                if emp['nb_reservations'] > 0 and emp['is_reserved_for_doc'] == 0:
                    current_emp_idx += 1
                    continue
                    
                # 3. Sharing
                if not emp['est_partageable']:
                    if len(state['medecins']) > 0 and b['id_medecin'] not in state['medecins']:
                        current_emp_idx += 1
                        continue
                        
                # It fits!
                state['occupe'] += b['epaisseur_max_mm']
                state['medecins'].add(b['id_medecin'])
                
                if b['id_emplacement'] != emp['id']:
                    moved_boxes.append({
                        'id': b['id'],
                        'old_emp': b['id_emplacement'],
                        'new_emp': emp['id']
                    })
                    
                b['id_emplacement'] = emp['id']
                placed = True
                break
                
            if not placed:
                print(f"ERREUR: Impossible de placer la boite {b['id']} (Espace insuffisant dans la zone)")
                return
                
        print("\n--- RESULTAT DECALAGE ---")
        print(f"Boites deplacées: {len(moved_boxes)}")
        for mb in moved_boxes:
            print(f"Boite {mb['id']} : Emp {mb['old_emp']} -> Emp {mb['new_emp']}")
            
    finally:
        conn.close()

if __name__ == "__main__":
    # Test avec un id_medecin (1 = Dr. Test ou autre), et id_type_boite = 1 (Petite)
    test_shifting_logic(1, 1)

