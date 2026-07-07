from app import get_db_connection
from flask import g
import pymysql

# Constantes de configuration
EPAISSEUR_DOSSIER_SIMPLE = 2
EPAISSEUR_DOSSIER_CONVENTION = 4


def log_historique(id_dossier, action, effectue_par, cursor,
                   id_boite_avant=None, id_boite_apres=None,
                   zone_avant=None, zone_apres=None,
                   commentaire=None):
    """
    Enregistre un mouvement dans archivage_dossiers_historique.
    Actions possibles: CREATION, DEPLACEMENT_BOITE, DEPLACEMENT_ZONE,
                       SORTIE_TEMPORAIRE, RETOUR, DESARCHIVE
    """
    cursor.execute("""
        INSERT INTO archivage_dossiers_historique
        (id_dossier, action, id_boite_avant, id_boite_apres,
         zone_avant, zone_apres, commentaire, effectue_par, date_action)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
    """, (id_dossier, action, id_boite_avant, id_boite_apres,
          zone_avant, zone_apres, commentaire, effectue_par))

def get_config_types_boites():
    """Charge la configuration des types de boîtes en mémoire."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM archivage_types_boites")
        types = {row['nom']: row for row in cursor.fetchall()}
        return types
    finally:
        conn.close()

def calculer_remplissage_boite(id_boite, cursor=None):
    """
    Recalcule l'épaisseur actuelle d'une boîte en fonction de son contenu.
    Retourne (epaisseur_actuelle, est_pleine).
    """
    should_close = False
    conn = None
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        should_close = True

    try:
        # 1. Somme des épaisseurs des dossiers
        cursor.execute("""
            SELECT SUM(epaisseur_mm) as total 
            FROM archivage_dossiers 
            WHERE id_boite = %s
        """, (id_boite,))
        result = cursor.fetchone()
        epaisseur_totale = int(result['total']) if result and result['total'] else 0
        
        # 2. Récupérer les infos de la boîte pour vérifier le max
        cursor.execute("""
            SELECT b.id, t.epaisseur_max_mm 
            FROM archivage_boites b
            JOIN archivage_types_boites t ON b.id_type_boite = t.id
            WHERE b.id = %s
        """, (id_boite,))
        boite_info = cursor.fetchone()
        
        if not boite_info:
            return 0, False
            
        est_pleine = epaisseur_totale >= boite_info['epaisseur_max_mm']
        
        # Mise à jour du cache dans la table boite
        cursor.execute("""
            UPDATE archivage_boites 
            SET epaisseur_actuelle_mm = %s, est_pleine = %s 
            WHERE id = %s
        """, (epaisseur_totale, 1 if est_pleine else 0, id_boite))
        
        if should_close:
            conn.commit()
            
        return epaisseur_totale, est_pleine
        
    finally:
        if should_close and conn:
            conn.close()

def trouver_emplacement_libre(epaisseur_requise_mm, id_medecin, nom_zone=None, cursor=None):
    """
    Trouve le premier emplacement capable d'accueillir une nouvelle boîte de l'épaisseur donnée et vérifie qu'elle est compatible avec le médecin et le spécialité et le statut interne/externe.
    Prend en compte la largeur totale du rayonnage, l'occupation actuelle, et le zonage strict (Spécialité/Statut).
    Accepte un `nom_zone` optionnel pour forcer la recherche dans une zone précise.
    Retourne l'ID de l'emplacement ou lève une exception précise.
    """
    should_close = False
    conn = None
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        should_close = True

    try:
        
        # 1. Récupérer infos Médecin
        cursor.execute("""
            SELECT d.est_interne, s.name_specialty, d.id_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
        """, (id_medecin,))
        medecin = cursor.fetchone()
        
        if not medecin:
            raise Exception("Médecin introuvable pour l'attribution de zone.")

        est_interne = medecin['est_interne']
        id_specialty = medecin['id_specialty']
        specialite_nom = medecin['name_specialty'] or "Sans Spécialité"
        statut_nom = "INTERNE" if est_interne else "EXTERNE"
        
        # Filtre sur la zone
        zone_condition_count = "1=1"
        zone_condition_main = "1=1"
        if nom_zone:
            zone_condition_count = "nom_zone = %s"
            zone_condition_main = "r.nom_zone = %s"
        
        # 2. Vérifier si des rayonnages sont configurés pour cette cible
        # Note: On gère le cas où id_specialty est NULL (ex: généraliste sans spé affichée, ou erreur data)
        # Mais la contrainte métier est stricte : id_specialty DOIT matcher.
        
        if id_specialty is not None:
             specialty_condition_count = """
                 (
                     EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = id AND ars.id_specialty = %s)
                     OR NOT EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = id)
                 )
             """
             specialty_condition_main = """
                 (
                     EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = r.id AND ars.id_specialty = %s)
                     OR NOT EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = r.id)
                 )
             """
             specialty_match_col = "(SELECT COUNT(*) FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = r.id AND ars.id_specialty = %s)"
             
             params_config = [id_specialty, est_interne]
             if nom_zone: params_config.append(nom_zone)
        else:
             specialty_condition_count = "NOT EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = id)"
             specialty_condition_main = "NOT EXISTS (SELECT 1 FROM archivage_rayonnage_specialites ars WHERE ars.id_rayonnage = r.id)"
             specialty_match_col = "0"
             
             params_config = [est_interne]
             if nom_zone: params_config.append(nom_zone)

        cursor.execute(f"""
            SELECT COUNT(*) as nb 
            FROM archivage_rayonnages 
            WHERE {specialty_condition_count} AND est_interne = %s AND {zone_condition_count}
        """, tuple(params_config))
        
        if cursor.fetchone()['nb'] == 0:
             zone_msg = f" dans la zone '{nom_zone}'" if nom_zone else ""
             raise Exception(f"Aucune zone de rayonnage configurée pour {specialite_nom} ({statut_nom}){zone_msg}")

        # 3. Chercher emplacement libre avec TRI CHRONOLOGIQUE
        # On cherche un emplacement libre
        # ET qui respecte partageabilité
        # ET qui respecte les RÉSERVATIONS (M2M)
        
        # Logique Réservation:
        # Si la cellule a des entrées dans archivage_emplacements_medecins, alors le médecin DOIT être dedans.
        # Si aucune entrée, pas de restriction spécifique (sauf celle du rayonnage global).

        query = f"""
            SELECT 
                e.id, 
                (r.largeur_cm * 10) as capacite_mm, 
                COALESCE(SUM(t.epaisseur_max_mm), 0) as occupe_mm,
                COALESCE(e.est_partageable, r.est_partageable) as est_partageable_effective,
                COUNT(CASE WHEN b.id_medecin != %s AND b.id_medecin IS NOT NULL THEN 1 END) as nb_autres_medecins,
                (SELECT COUNT(*) FROM archivage_emplacements_medecins WHERE id_emplacement = e.id) as nb_reservations,
                (SELECT COUNT(*) FROM archivage_emplacements_medecins WHERE id_emplacement = e.id AND id_medecin = %s) as est_reserve_pour_ce_medecin,
                {specialty_match_col} as match_specialty
            FROM archivage_emplacements e
            JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            LEFT JOIN archivage_boites b ON b.id_emplacement = e.id
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            WHERE {specialty_condition_main} 
              AND r.est_interne = %s
              AND {zone_condition_main}
            GROUP BY e.id, r.largeur_cm, r.code_etagere, e.ligne_y, e.colonne_x, r.est_partageable, e.est_partageable
            HAVING (capacite_mm - occupe_mm) >= %s 
               AND (est_partageable_effective = 1 OR nb_autres_medecins = 0)
               AND (nb_reservations = 0 OR est_reserve_pour_ce_medecin > 0)
            ORDER BY 
                est_reserve_pour_ce_medecin DESC,
                match_specialty DESC,
                r.code_etagere ASC, e.ligne_y ASC, e.colonne_x ASC
            LIMIT 1
        """
        
        # Paramètres pour la recherche : 
        
        params_search = [id_medecin, id_medecin] # 1: Count autres, 2: Check reservation
        if id_specialty is not None:
            params_search.append(id_specialty) # 3: Select match_specialty
            params_search.append(id_specialty) # 4: WHERE specialty_condition_main
            
        params_search.append(est_interne)
        if nom_zone: params_search.append(nom_zone)
        
        params_search.append(epaisseur_requise_mm)
            
        cursor.execute(query, tuple(params_search))
        result = cursor.fetchone()
        
        if not result:
             raise Exception(f"Zone {specialite_nom} ({statut_nom}) saturée, veuillez attribuer une nouvelle zone")
             
        return result['id']
    finally:
        if should_close and conn:
            conn.close()

def allouer_et_decaler_boites(id_medecin, epaisseur_box, id_type_boite, nom_zone=None, cursor=None):
    """
    Alloue une nouvelle boîte et décale les suivantes pour garder les boîtes du médecin groupées.
    """
    should_close = False
    conn = None
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        should_close = True

    try:
        # 1. Obtenir les contraintes du médecin
        cursor.execute("""
            SELECT d.est_interne, d.id_specialty
            FROM doctors d WHERE d.id = %s
        """, (id_medecin,))
        medecin = cursor.fetchone()
        
        if not medecin:
            raise Exception("Médecin introuvable.")

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
            raise Exception("Aucun emplacement compatible trouvé pour ce médecin (vérifiez la zone et les spécialités).")
            
        emplacement_ids = [e['id'] for e in emplacements]
        
        # 3. Récupérer toutes les boîtes existantes
        placeholders = ', '.join(['%s'] * len(emplacement_ids))
        cursor.execute(f"""
            SELECT b.id, b.id_medecin, b.id_emplacement, t.epaisseur_max_mm
            FROM archivage_boites b
            JOIN archivage_types_boites t ON b.id_type_boite = t.id
            WHERE b.id_emplacement IN ({placeholders})
        """, tuple(emplacement_ids))
        
        raw_boxes = cursor.fetchall()
        
        # 4. Trier les boîtes existantes 
        emp_order_map = {e_id: idx for idx, e_id in enumerate(emplacement_ids)}
        sorted_boxes = sorted(raw_boxes, key=lambda b: (emp_order_map[b['id_emplacement']], b['id_medecin'], b['id']))
        
        # 5. Déterminer le point d'insertion
        insertion_index = -1
        for i in range(len(sorted_boxes)-1, -1, -1):
            if sorted_boxes[i]['id_medecin'] == id_medecin:
                insertion_index = i
                break
                
        # Simuler la nouvelle boîte (ID temporaire)
        new_box = {
            'id': 'NEW',
            'id_medecin': id_medecin,
            'id_emplacement': None,
            'epaisseur_max_mm': epaisseur_box
        }
        
        if insertion_index != -1:
            sorted_boxes.insert(insertion_index + 1, new_box)
            start_emp_id = sorted_boxes[insertion_index]['id_emplacement']
            start_emp_idx = emp_order_map[start_emp_id]
            repack_start_box_idx = insertion_index + 1
        else:
            if len(sorted_boxes) > 0:
                last_box = sorted_boxes[-1]
                start_emp_idx = emp_order_map[last_box['id_emplacement']]
            else:
                start_emp_idx = 0
            sorted_boxes.append(new_box)
            repack_start_box_idx = len(sorted_boxes) - 1

        boxes_to_repack = sorted_boxes[repack_start_box_idx:]
        
        # Calculer l'état de l'occupation jusqu'à start_emp_idx
        emp_state = {}
        for emp in emplacements:
            emp_state[emp['id']] = {
                'occupe': 0,
                'doctors': set()
            }
            
        for i in range(repack_start_box_idx):
            b = sorted_boxes[i]
            emp_state[b['id_emplacement']]['occupe'] += b['epaisseur_max_mm']
            emp_state[b['id_emplacement']]['doctors'].add(b['id_medecin'])
            
        # 6. Repacking / Décalage
        current_emp_idx = start_emp_idx
        
        moved_boxes = []
        new_box_emp_id = None
        
        for b in boxes_to_repack:
            placed = False
            while current_emp_idx < len(emplacements):
                emp = emplacements[current_emp_idx]
                state = emp_state[emp['id']]
                
                # Vérifier la capacité
                if state['occupe'] + b['epaisseur_max_mm'] > emp['capacite_mm']:
                    current_emp_idx += 1
                    continue
                    
                # Vérifier les réservations éventuelles
                if emp['nb_reservations'] > 0 and emp['is_reserved_for_doc'] == 0:
                    current_emp_idx += 1
                    continue
                    
                # Vérifier le partage (si non partageable et déjà occupé par un autre)
                if not emp['est_partageable']:
                    if len(state['doctors']) > 0 and b['id_medecin'] not in state['doctors']:
                        current_emp_idx += 1
                        continue
                        
                # On le place ici
                state['occupe'] += b['epaisseur_max_mm']
                state['doctors'].add(b['id_medecin'])
                
                if b['id'] == 'NEW':
                    new_box_emp_id = emp['id']
                elif b['id_emplacement'] != emp['id']:
                    moved_boxes.append({
                        'id': b['id'],
                        'old_emp': b['id_emplacement'],
                        'new_emp': emp['id']
                    })
                    
                b['id_emplacement'] = emp['id']
                placed = True
                break
                
            if not placed:
                raise Exception("L'étagère/zone est pleine. Impossible de placer ou décaler les boîtes (Espace insuffisant).")

        # 7. Exécuter les changements en BDD
        # A. Créer la nouvelle boîte
        import uuid
        temp_ref = str(uuid.uuid4())[:8].upper()
        cursor.execute("""
            INSERT INTO archivage_boites (id_medecin, id_type_boite, numero_archive, id_emplacement, date_creation)
            VALUES (%s, %s, %s, %s, NOW())
        """, (id_medecin, id_type_boite, f"PENDING-{temp_ref}", new_box_emp_id))
        
        new_boite_id = cursor.lastrowid
        final_ref = f"MED{id_medecin}-B{new_boite_id}"
        cursor.execute("UPDATE archivage_boites SET numero_archive = %s WHERE id = %s", (final_ref, new_boite_id))
        
        # B. Appliquer les décalages (Update id_emplacement des boîtes existantes)
        for mb in moved_boxes:
            cursor.execute("""
                UPDATE archivage_boites
                SET id_emplacement = %s
                WHERE id = %s
            """, (mb['new_emp'], mb['id']))
            
        # C. Re-calculer les attributs est_occupe et id_boite_actuelle pour tous les emplacements affectés
        # On va remettre à zéro et recalculer pour sécuriser.
        # Tous les emplacements touchés sont entre start_emp_idx et current_emp_idx
        affected_emps = [e['id'] for e in emplacements[start_emp_idx:current_emp_idx+1]]
        
        if affected_emps:
            placeholders_aff = ', '.join(['%s'] * len(affected_emps))
            # Obtenir la dernière boîte insérée par emplacement pour id_boite_actuelle
            # On utilise MAX(id) par simplicité, même si l'ordre logique est important, id_boite_actuelle sert surtout 
            # de raccourci. Le COUNT(*) == 0 -> est_occupe = 0
            
            # Reset
            cursor.execute(f"""
                UPDATE archivage_emplacements
                SET est_occupe = 0, id_boite_actuelle = NULL
                WHERE id IN ({placeholders_aff})
            """, tuple(affected_emps))
            
            # Recalculate
            cursor.execute(f"""
                SELECT id_emplacement, COUNT(*) as nb, MAX(id) as last_box_id
                FROM archivage_boites
                WHERE id_emplacement IN ({placeholders_aff})
                GROUP BY id_emplacement
            """, tuple(affected_emps))
            
            for row in cursor.fetchall():
                cursor.execute("""
                    UPDATE archivage_emplacements
                    SET est_occupe = 1, id_boite_actuelle = %s
                    WHERE id = %s
                """, (row['last_box_id'], row['id_emplacement']))

        if should_close:
            conn.commit()
            
        return new_boite_id

    except Exception as e:
        if should_close and conn:
            conn.rollback()
        raise e
    finally:
        if should_close and conn:
            conn.close()

def creer_nouvelle_boite(id_medecin, id_type_boite_preferee=None, cursor=None):
    """
    Crée une nouvelle boîte pour un médecin et lui assigne un emplacement en décalant les autres au besoin.
    Lève une exception si aucun emplacement n'est disponible ou si aucun type n'est fourni.
    """
    if not id_type_boite_preferee:
        raise Exception("Un type de boîte doit être spécifié pour créer une nouvelle boîte.")

    conn = get_db_connection() if cursor is None else None
    exec_cursor = cursor if cursor else conn.cursor()

    try:
        # Récupérer l'épaisseur de la boîte
        exec_cursor.execute("SELECT id, epaisseur_max_mm FROM archivage_types_boites WHERE id = %s", (id_type_boite_preferee,))
        type_boite = exec_cursor.fetchone()
        if not type_boite:
            raise Exception("Le type de boîte spécifié est introuvable.")
            
        epaisseur_box = type_boite['epaisseur_max_mm']
        
        # Appel de la nouvelle logique continue
        new_boite_id = allouer_et_decaler_boites(id_medecin, epaisseur_box, type_boite['id'], cursor=exec_cursor)
        
        if conn:
            conn.commit()
            
        return new_boite_id
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

def attribuer_boite_pour_dossier(id_medecin, epaisseur_dossier, id_type_boite_preferee=None):
    """
    Algorithme principal d'allocation :
    1. Cherche une boîte existante du médecin avec assez de place.
    2. Sinon, crée une nouvelle boîte.
    Retourne l'ID de la boîte.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Chercher les boîtes du médecin qui ne sont pas pleines
        cursor.execute("""
            SELECT b.id, b.epaisseur_actuelle_mm, t.epaisseur_max_mm
            FROM archivage_boites b
            JOIN archivage_types_boites t ON b.id_type_boite = t.id
            WHERE b.id_medecin = %s AND b.est_pleine = 0
            ORDER BY b.date_creation DESC
        """, (id_medecin,))
        
        candidats = cursor.fetchall()
        
        for boite in candidats:
            espace_disponible = boite['epaisseur_max_mm'] - boite['epaisseur_actuelle_mm']
            if espace_disponible >= epaisseur_dossier:
                return boite['id']
        
        # Aucune boîte compatible trouvée -> Création
        return creer_nouvelle_boite(id_medecin, id_type_boite_preferee)
        
    finally:
        conn.close()

def verifier_espace_boite_medecin(id_medecin, epaisseur_dossier):
    """
    Vérifie si le médecin a déjà une boîte avec suffisamment d'espace
    pour un dossier de l'épaisseur donnée.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.epaisseur_actuelle_mm, t.epaisseur_max_mm, b.numero_archive
            FROM archivage_boites b
            JOIN archivage_types_boites t ON b.id_type_boite = t.id
            WHERE b.id_medecin = %s AND b.est_pleine = 0
            ORDER BY b.date_creation DESC
        """, (id_medecin,))
        candidats = cursor.fetchall()
        for boite in candidats:
            if boite['epaisseur_max_mm'] - boite['epaisseur_actuelle_mm'] >= epaisseur_dossier:
                return boite['numero_archive']
        return None
    finally:
        conn.close()

def archiver_dossier(id_patient_his, nom_patient, type_dossier, id_medecin, user_id, source_module=None, id_source=None, id_type_boite_preferee=None):
    """
    Orchestre l'archivage complet d'un dossier.
    """
    epaisseur = EPAISSEUR_DOSSIER_CONVENTION if type_dossier == 'CONVENTION' else EPAISSEUR_DOSSIER_SIMPLE
    
    # 1. Trouver ou créer la boîte adéquate
    id_boite = attribuer_boite_pour_dossier(id_medecin, epaisseur, id_type_boite_preferee)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 2. Insérer le dossier
        cursor.execute("""
            INSERT INTO archivage_dossiers (id_boite, id_patient_his, nom_patient, type_dossier, epaisseur_mm, archive_par, source_module, id_source, date_archivage)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (id_boite, id_patient_his, nom_patient, type_dossier, epaisseur, user_id, source_module, id_source))
        
        dossier_id = cursor.lastrowid
        
        # 3. Logger l'historique CREATION
        log_historique(dossier_id, 'CREATION', user_id, cursor,
                       id_boite_apres=id_boite,
                       commentaire=f'Archivage initial dans boîte #{id_boite}')
        
        conn.commit()
        
        # 4. Mettre à jour les métadonnées de la boîte (épaisseur, statut plein)
        calculer_remplissage_boite(id_boite)
        
        return dossier_id, id_boite
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def archiver_dossiers_masse(dossiers, box_preferences, user_id):
    """
    Archive plusieurs dossiers en respectant l'ordre chronologique (shifting).
    Si un ancien dossier est inséré "dans le passé", il décale les suivants vers les
    boîtes ultérieures.
    """
    total_archived = 0
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Préparer les données
        # On va traiter ça médecin par médecin.
        dossiers_par_medecin = {}
        for d in dossiers:
            id_medecin = d.get('id_doctor')
            if not id_medecin: continue
            
            # Déterminer date_acte (nécessaire pour le tri)
            date_acte = d.get('date_acte')
            if not date_acte:
                # Fallback, on requiert une date. 
                import datetime
                date_acte = datetime.datetime.now().strftime('%Y-%m-%d')
                
            # Déterminer l'épaisseur
            type_dossier = 'SIMPLE'
            source_module = d.get('source_module')
            id_source = d.get('id_source')
            
            if source_module == 'MATERNITE':
                cursor.execute("SELECT type_tarification FROM accouchement_dossiers WHERE id_dossier = %s", (id_source,))
                maternite = cursor.fetchone()
                if maternite and maternite['type_tarification'] == 'CONVENTION':
                    type_dossier = 'CONVENTION'
            elif source_module == 'PRESTATION KT':
                cursor.execute("SELECT COUNT(*) as has_conv FROM kt_dossier_actes WHERE id_dossier = %s AND id_convention IS NOT NULL", (id_source,))
                kt = cursor.fetchone()
                if kt and kt['has_conv'] > 0:
                    type_dossier = 'CONVENTION'
                    
            epaisseur = EPAISSEUR_DOSSIER_CONVENTION if type_dossier == 'CONVENTION' else EPAISSEUR_DOSSIER_SIMPLE
            d['epaisseur'] = epaisseur
            d['type_dossier'] = type_dossier
            d['date_acte'] = date_acte
            
            if id_medecin not in dossiers_par_medecin:
                dossiers_par_medecin[id_medecin] = []
            dossiers_par_medecin[id_medecin].append(d)
        
        # 2. Traitement par médecin
        for id_medecin, nouveaux_dossiers in dossiers_par_medecin.items():
            
            # A. Récupérer TOUS les dossiers existants de ce médecin (déjà archivés)
            cursor.execute("""
                SELECT ad.id, ad.id_boite, ad.epaisseur_mm, 
                       COALESCE(
                           IF(ad.source_module='MATERNITE', 
                           (SELECT date_accouchement FROM accouchement_dossiers WHERE accouchement_dossiers.id_dossier=ad.id_source),
                           IF(ad.source_module='BLOC_EXTERNE', 
                           (SELECT str_to_date(location_date, '%%d/%%m/%%Y') FROM location_bloc_dossier_patient WHERE location_bloc_dossier_patient.id_dossier=ad.id_source),
                           IF(ad.source_module='PRESTATION KT', (SELECT acte_date FROM kt_dossier_patient WHERE kt_dossier_patient.id_dossier=ad.id_source LIMIT 1),
                           IF(ad.source_module='BLOC_INTERNE', (SELECT date_creation FROM medecin_interne_actes WHERE medecin_interne_actes.id_acte=ad.id_source), 
                           ad.date_archivage))))
                       ) as exact_date,
                       ad.nom_patient, ad.id_patient_his, ad.source_module, ad.id_source, ad.type_dossier
                FROM archivage_dossiers ad
                JOIN archivage_boites ab ON ad.id_boite = ab.id
                WHERE ab.id_medecin = %s
            """, (id_medecin,))
            
            existants = cursor.fetchall()
            
            # Formatter les existants pour la fusion
            tous_les_dossiers = []
            for ex in existants:
                tous_les_dossiers.append({
                    'is_new': False,
                    'id': ex['id'],
                    'epaisseur': ex['epaisseur_mm'],
                    'date_sort': ex['exact_date'],
                    'original_boite': ex['id_boite']
                })
                
            # Ajouter les nouveaux
            for nd in nouveaux_dossiers:
                tous_les_dossiers.append({
                    'is_new': True,
                    'data': nd,
                    'epaisseur': nd['epaisseur'],
                    'date_sort': nd['date_acte']
                })
                
            # B. Trier le tout chronologiquement pur
            # Note: Si des dossiers ont exactement la même date, l'ordre de Python (stable) gardera l'existant avant le nouveau.
            tous_les_dossiers.sort(key=lambda x: str(x['date_sort']))
            
            # C. Récupérer les boîtes de ce médecin triées chronologiquement
            cursor.execute("""
                SELECT b.id, t.epaisseur_max_mm
                FROM archivage_boites b
                JOIN archivage_types_boites t ON b.id_type_boite = t.id
                WHERE b.id_medecin = %s
                ORDER BY b.id ASC -- L'ID croissant correspond à l'ordre chronologique de création
            """, (id_medecin,))
            boites_existantes = cursor.fetchall()
            
            # Variables de simulation d'allocation
            boites_simulees = []
            for b in boites_existantes:
                boites_simulees.append({
                    'id': b['id'],
                    'max': b['epaisseur_max_mm'],
                    'current': 0,
                    'is_new': False
                })
            
            current_box_idx = 0
            
            # D. Allouer les dossiers virtuellement
            for dossier in tous_les_dossiers:
                epaisseur = dossier['epaisseur']
                placed = False
                
                # Chercher la première boîte (à partir de la courante) qui peut l'accueillir
                # En "shifting", on remplit boite 1, puis 2, etc. On ne retourne pas en arrière.
                while current_box_idx < len(boites_simulees):
                    b = boites_simulees[current_box_idx]
                    if b['current'] + epaisseur <= b['max']:
                        # On a la place !
                        b['current'] += epaisseur
                        dossier['assigned_boite'] = b['id']
                        placed = True
                        break
                    else:
                        # Boîte pleine, on passe à la suivante
                        current_box_idx += 1
                        
                if not placed:
                    # Plus de boîtes existantes, on doit virtuellement en créer une
                    # Pour ça, on va la créer réellement en BDD maintenant pour avoir son ID
                    pref = box_preferences.get(str(id_medecin))
                    if not pref:
                        # Fallback sur petite si la préférence n'a pas été fournie (sécurité)
                        cursor.execute("SELECT id FROM archivage_types_boites WHERE nom = 'Petite' LIMIT 1")
                        t = cursor.fetchone()
                        pref = t['id'] if t else 1
                        
                    new_b_id = creer_nouvelle_boite(id_medecin, pref, cursor=cursor)
                    
                    # Récupérer l'épaisseur max de cette nouvelle boîte
                    cursor.execute("SELECT epaisseur_max_mm FROM archivage_types_boites WHERE id = %s", (pref,))
                    n_max = cursor.fetchone()['epaisseur_max_mm']
                    
                    # L'ajouter à notre liste de simulation
                    new_box_sim = {
                        'id': new_b_id,
                        'max': n_max,
                        'current': epaisseur,
                        'is_new': True
                    }
                    boites_simulees.append(new_box_sim)
                    dossier['assigned_boite'] = new_b_id
                    
            # E. Appliquer les changements réels en BDD
            
            # E1. Insérer les nouveaux dossiers
            for dossier in tous_les_dossiers:
                if dossier['is_new']:
                    nd = dossier['data']
                    cursor.execute("""
                        INSERT INTO archivage_dossiers (id_boite, id_patient_his, nom_patient, type_dossier, epaisseur_mm, archive_par, source_module, id_source, date_archivage)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """, (dossier['assigned_boite'], nd.get('patient_oid_his'), nd.get('nom_patient'), nd['type_dossier'], nd['epaisseur'], user_id, nd.get('source_module'), nd.get('id_source')))
                    new_id = cursor.lastrowid
                    # Logger CREATION
                    log_historique(new_id, 'CREATION', user_id, cursor,
                                  id_boite_apres=dossier['assigned_boite'],
                                  commentaire='Archivage en masse')
                    total_archived += 1
                else:
                    # E2. Mettre à jour les dossiers existants qui ont changé de boîte (shifting effect)
                    if dossier['original_boite'] != dossier['assigned_boite']:
                        cursor.execute("""
                            UPDATE archivage_dossiers 
                            SET id_boite = %s 
                            WHERE id = %s
                        """, (dossier['assigned_boite'], dossier['id']))
                        # Logger DEPLACEMENT_BOITE (shifting)
                        log_historique(dossier['id'], 'DEPLACEMENT_BOITE', user_id, cursor,
                                      id_boite_avant=dossier['original_boite'],
                                      id_boite_apres=dossier['assigned_boite'],
                                      commentaire='Décalage chronologique (archivage masse)')
                        
            # E3. Recalculer l'épaisseur réelle de TOUTES les boîtes de ce médecin
            for b_sim in boites_simulees:
                calculer_remplissage_boite(b_sim['id'], cursor=cursor)

        conn.commit()
        return {'total_archived': total_archived}
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def generer_emplacements_pour_rayonnage(rayonnage_id, nb_lignes, cursor=None):
    """
    Génère les emplacements vides pour un rayonnage spécifié.
    Utilisé lors de la création d'un nouveau rayonnage.
    Accepte un curseur optionnel pour l'exécution dans une transaction existante.
    """
    conn = None
    should_close = False
    
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        should_close = True

    try:
        count = 0
        for y in range(1, int(nb_lignes) + 1):
            for x in range(1, int(1) + 1):
                # Vérifier si l'emplacement existe déjà pour éviter les doublons
                cursor.execute("""
                    SELECT id FROM archivage_emplacements 
                    WHERE id_rayonnage = %s AND colonne_x = %s AND ligne_y = %s
                """, (rayonnage_id, x, y))
                
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO archivage_emplacements (id_rayonnage, colonne_x, ligne_y, est_occupe)
                        VALUES (%s, %s, %s, 0)
                    """, (rayonnage_id, x, y))
                    count += 1
        
        if should_close:
            conn.commit()
            
        return count
    except Exception as e:
        if should_close and conn:
            conn.rollback()
        raise e
    finally:
        if should_close and conn:
            conn.close()
