from app import app, get_db_connection
from flask import render_template, request, jsonify
from datetime import datetime, timedelta
from app.utils.utiles import login_required
import pymysql

@app.route('/stats-personnel')
@login_required
def stats_personnel():
    """Page principale des statistiques du personnel"""
    return render_template( 'personnel/stats_utilisateur.html' )


@app.route('/api/stats-personnel/data')
@login_required
def stats_personnel_data():
    """API pour récupérer les données de statistiques"""

    # Récupérer les paramètres de filtrage
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    id_personnel = request.args.get('id_personnel')

    # Dates par défaut: dernier mois
    if not date_debut:
        date_debut = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not date_fin:
        date_fin = datetime.now().strftime('%Y-%m-%d')

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Construire la clause WHERE pour le filtre de personnel
        personnel_filter = ""
        if id_personnel:
            personnel_filter = f"AND p.id_personnel = {id_personnel}"

        # Requête SQL principale
        query = f"""
        SELECT 
            p.id_personnel,
            p.nom,
            p.prenom,
            p.role,
            s. service_name,
            
            -- === ACCOUCHEMENTS ===
            COUNT(DISTINCT acc.id_dossier) as nb_accouchements_crees,
            COALESCE(SUM(CASE WHEN acc.created_by = p.id_personnel THEN acc.prix_total ELSE 0 END), 0) as montant_accouchements,
            
            -- === DÉCHARGES GYNÉCO INTERNES ===
            COUNT(DISTINCT gd.id_decharge) as nb_decharges_gyneco_creees,
            COUNT(DISTINCT CASE WHEN gd.statut = 'VALIDE' AND gd.validated_by = p.id_personnel THEN gd.id_decharge END) as nb_decharges_gyneco_validees,
            COUNT(DISTINCT CASE WHEN gd.statut IN ('PAYE', 'PAIEMENT_PARTIEL') AND gd.paid_by = p.id_personnel THEN gd.id_decharge END) as nb_decharges_gyneco_payees,
            COALESCE(SUM(CASE WHEN gd.created_by = p.id_personnel THEN gd.montant_total ELSE 0 END), 0) as montant_decharges_gyneco,
            
            -- === DÉCHARGES KT ===
            COUNT(DISTINCT ktd.id_decharge) as nb_decharges_kt_creees,
            COUNT(DISTINCT CASE WHEN ktd.statut = 'SOLDE' THEN ktd.id_decharge END) as nb_decharges_kt_soldees,
            COUNT(DISTINCT CASE WHEN ktd.statut = 'PARTIEL' THEN ktd.id_decharge END) as nb_decharges_kt_partielles,
            COALESCE(SUM(CASE WHEN ktd.id_createur = p.id_personnel THEN ktd.montant_total ELSE 0 END), 0) as montant_decharges_kt,
            
            -- === DÉCHARGES MÉDECIN INTERNE ===
            COUNT(DISTINCT mid.id_decharge) as nb_decharges_medint_creees,
            COUNT(DISTINCT CASE WHEN mid.statut = 'VALIDE' AND mid.validated_by = p.id_personnel THEN mid.id_decharge END) as nb_decharges_medint_validees,
            COUNT(DISTINCT CASE WHEN mid.statut IN ('PAYE', 'PAIEMENT_PARTIEL') AND mid.paid_by = p.id_personnel THEN mid.id_decharge END) as nb_decharges_medint_payees,
            COALESCE(SUM(CASE WHEN mid.created_by = p.id_personnel THEN mid.montant_total ELSE 0 END), 0) as montant_decharges_medint,
            
            -- === LOCATION BLOC ===
            COUNT(DISTINCT lb.id_dossier) as nb_dossiers_location_bloc,
            COALESCE(SUM(CASE WHEN lb.created_by = p.id_personnel THEN lb.prix_total ELSE 0 END), 0) as montant_location_bloc,
            
            -- === ACTES MÉDECIN INTERNE ===
            COUNT(DISTINCT mia.id_acte) as nb_actes_medint_crees,
            COALESCE(SUM(CASE WHEN mia.created_by = p.id_personnel THEN mia.prix_acte_base ELSE 0 END), 0) as montant_actes_medint,
            COALESCE(SUM(CASE WHEN mia.created_by = p.id_personnel THEN mia.part_medecin ELSE 0 END), 0) as part_medecin_actes,
            
            -- === PAIEMENTS ACCOUCHEMENTS ===
            COUNT(DISTINCT apb.id_paiement) as nb_paiements_accouchement,
            COALESCE(SUM(CASE WHEN apb.encaisse_par = p.id_personnel THEN apb.montant ELSE 0 END), 0) as montant_paiements_accouchement,
            
            -- === PAIEMENTS MÉDECIN INTERNE ===
            COUNT(DISTINCT mip.id_paiement) as nb_paiements_medint,
            COALESCE(SUM(CASE WHEN mip.created_by = p.id_personnel THEN mip.montant_paye ELSE 0 END), 0) as montant_paiements_medint,
            
            -- === TRANCHES KT ===
            COUNT(DISTINCT ktt.id_tranche) as nb_tranches_kt,
            COALESCE(SUM(CASE WHEN ktt.id_createur = p.id_personnel THEN ktt.montant_tranche ELSE 0 END), 0) as montant_tranches_kt,
            
            -- === TRANCHES GYNÉCO ===
            COUNT(DISTINCT gdt.id_tranche) as nb_tranches_gyneco,
            COALESCE(SUM(CASE WHEN gdt.created_by = p.id_personnel THEN gdt.montant_paye ELSE 0 END), 0) as montant_tranches_gyneco,
            
            -- === TRANCHES MÉDECIN INTERNE ===
            COUNT(DISTINCT mdt.id_tranche) as nb_tranches_medint,
            COALESCE(SUM(CASE WHEN mdt.created_by = p.id_personnel THEN mdt.montant_paye ELSE 0 END), 0) as montant_tranches_medint,
            
            -- === FACTURES ===
            COUNT(DISTINCT CASE WHEN f.created_by = p.id_personnel THEN f.id END) as nb_factures_creees,
            COUNT(DISTINCT CASE WHEN f.valide_par = p.id_personnel THEN f.id END) as nb_factures_validees,
            COUNT(DISTINCT CASE WHEN f.type_facture = 'facture' AND f.created_by = p.id_personnel THEN f.id END) as nb_factures_definitives,
            COUNT(DISTINCT CASE WHEN f.type_facture = 'proforma' AND f.created_by = p.id_personnel THEN f.id END) as nb_proformas,
            COALESCE(SUM(CASE WHEN f.created_by = p.id_personnel THEN f.total_ttc ELSE 0 END), 0) as montant_factures_creees,
            COALESCE(SUM(CASE WHEN f.created_by = p.id_personnel AND f.statut = 'valide' THEN f.total_ttc ELSE 0 END), 0) as montant_factures_validees
            
        FROM personnel p
        LEFT JOIN services s ON p.id_service = s.id_service
        
        -- Accouchements
        LEFT JOIN accouchement_dossiers acc ON acc.created_by = p.id_personnel 
            AND DATE(acc.created_at) BETWEEN %s AND %s
        
        -- Décharges gynéco
        LEFT JOIN gyneco_interne_decharges gd ON (
            gd.created_by = p.id_personnel OR 
            gd.validated_by = p.id_personnel OR 
            gd.paid_by = p.id_personnel
        ) AND DATE(gd.created_at) BETWEEN %s AND %s
        
        -- Décharges KT
        LEFT JOIN kt_decharges_paiement ktd ON ktd.id_createur = p.id_personnel 
            AND DATE(ktd.date_creation) BETWEEN %s AND %s
        
        -- Décharges médecin interne
        LEFT JOIN medecin_interne_decharges mid ON (
            mid.created_by = p.id_personnel OR 
            mid.validated_by = p.id_personnel OR 
            mid.paid_by = p.id_personnel
        ) AND DATE(mid.created_at) BETWEEN %s AND %s
        
        -- Location bloc
        LEFT JOIN location_bloc_dossier_patient lb ON lb.created_by = p.id_personnel 
            AND DATE(lb.date_creation) BETWEEN %s AND %s
        
        -- Actes médecin interne
        LEFT JOIN medecin_interne_actes mia ON mia.created_by = p.id_personnel 
            AND DATE(mia.date_creation) BETWEEN %s AND %s
        
        -- Paiements accouchement
        LEFT JOIN accouchement_paiements_bons apb ON apb.encaisse_par = p.id_personnel 
            AND DATE(apb.created_at) BETWEEN %s AND %s
        
        -- Paiements médecin interne
        LEFT JOIN medecin_interne_paiements mip ON mip.created_by = p.id_personnel 
            AND DATE(mip.created_at) BETWEEN %s AND %s
        
        -- Tranches KT
        LEFT JOIN kt_decharges_tranches ktt ON ktt.id_createur = p.id_personnel 
            AND DATE(ktt.date_creation) BETWEEN %s AND %s
        
        -- Tranches gynéco
        LEFT JOIN gyneco_interne_decharge_tranches gdt ON gdt.created_by = p.id_personnel 
            AND DATE(gdt.created_at) BETWEEN %s AND %s
        
        -- Tranches médecin interne
        LEFT JOIN medecin_interne_decharge_tranches mdt ON mdt.created_by = p.id_personnel 
            AND DATE(mdt.created_at) BETWEEN %s AND %s
        
        -- Factures
        LEFT JOIN factures f ON (f.created_by = p.id_personnel OR f.valide_par = p.id_personnel)
            AND DATE(f.created_at) BETWEEN %s AND %s
        
        WHERE p.statut_activite = 1 {personnel_filter}
        
        GROUP BY p.id_personnel, p.nom, p.prenom, p.role, s. service_name
        
        HAVING (
            nb_accouchements_crees > 0 OR
            nb_decharges_gyneco_creees > 0 OR
            nb_decharges_kt_creees > 0 OR
            nb_decharges_medint_creees > 0 OR
            nb_dossiers_location_bloc > 0 OR
            nb_actes_medint_crees > 0 OR
            nb_paiements_accouchement > 0 OR
            nb_paiements_medint > 0 OR
            nb_tranches_kt > 0 OR
            nb_tranches_gyneco > 0 OR
            nb_tranches_medint > 0 OR
            nb_factures_creees > 0
        )
        
        ORDER BY p.nom, p.prenom
        """

        # Exécuter avec les dates répétées pour chaque JOIN
        params = [date_debut, date_fin] * 12

        cursor.execute(query, params)
        stats = cursor.fetchall()

        # Récupérer la liste de tout le personnel actif
        cursor.execute("""
            SELECT id_personnel, nom, prenom, role
            FROM personnel 
            WHERE statut_activite = 1
            ORDER BY nom, prenom
        """)
        personnel_list = cursor.fetchall()

        return jsonify({
            'success': True,
            'stats': stats,
            'personnel_list': personnel_list,
            'periode': {
                'debut': date_debut,
                'fin': date_fin
            }
        })

    except pymysql.MySQLError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route('/api/stats-personnel/detail/<int:id_personnel>')
@login_required
def stats_personnel_detail(id_personnel):
    """Détail de l'activité d'un personnel spécifique"""

    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')

    if not date_debut:
        date_debut = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not date_fin:
        date_fin = datetime.now().strftime('%Y-%m-%d')

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Informations du personnel
        cursor.execute("""
            SELECT p.*, s. service_name
            FROM personnel p
            LEFT JOIN services s ON p.id_service = s.id_service
            WHERE p.id_personnel = %s
        """, (id_personnel,))
        personnel_info = cursor.fetchone()

        # Détails par catégorie
        details = {}

        # Accouchements créés
        cursor.execute("""
            SELECT 
                id_dossier,
                patiente,
                DATE(date_accouchement) as date_acte,
                type_accouchement,
                type_tarification,
                prix_total,
                statut_paiement
            FROM accouchement_dossiers
            WHERE created_by = %s 
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (id_personnel, date_debut, date_fin))
        details['accouchements'] = cursor.fetchall()

        # Décharges gynéco
        cursor.execute("""
            SELECT 
                id_decharge,
                numero_decharge,
                DATE(date_decharge) as date_acte,
                montant_total,
                montant_paye_total,
                statut,
                CASE 
                    WHEN created_by = %s THEN 'Créée'
                    WHEN validated_by = %s THEN 'Validée'
                    WHEN paid_by = %s THEN 'Payée'
                END as action_type
            FROM gyneco_interne_decharges
            WHERE (created_by = %s OR validated_by = %s OR paid_by = %s)
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (id_personnel, id_personnel, id_personnel, id_personnel, id_personnel, id_personnel, date_debut, date_fin))
        details['decharges_gyneco'] = cursor.fetchall()

        # Décharges KT
        cursor.execute("""
            SELECT 
                id_decharge,
                numero_decharge,
                DATE(date_decharge) as date_acte,
                montant_total,
                montant_paye,
                statut,
                nb_dossiers
            FROM kt_decharges_paiement
            WHERE id_createur = %s
            AND DATE(date_creation) BETWEEN %s AND %s
            ORDER BY date_creation DESC
            LIMIT 20
        """, (id_personnel, date_debut, date_fin))
        details['decharges_kt'] = cursor.fetchall()

        # Décharges médecin interne
        cursor.execute("""
            SELECT 
                id_decharge,
                numero_decharge,
                DATE(date_decharge) as date_acte,
                montant_total,
                montant_paye_total,
                statut,
                nb_actes,
                CASE 
                    WHEN created_by = %s THEN 'Créée'
                    WHEN validated_by = %s THEN 'Validée'
                    WHEN paid_by = %s THEN 'Payée'
                END as action_type
            FROM medecin_interne_decharges
            WHERE (created_by = %s OR validated_by = %s OR paid_by = %s)
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (id_personnel, id_personnel, id_personnel, id_personnel, id_personnel, id_personnel, date_debut, date_fin))
        details['decharges_medint'] = cursor.fetchall()

        # Dossiers location bloc
        cursor.execute("""
            SELECT 
                id_dossier,
                patient,
                DATE(location_date) as date_acte,
                nom_acte,
                prix_total,
                statut_paiement
            FROM location_bloc_dossier_patient
            WHERE created_by = %s
            AND DATE(date_creation) BETWEEN %s AND %s
            ORDER BY date_creation DESC
            LIMIT 20
        """, (id_personnel, date_debut, date_fin))
        details['location_bloc'] = cursor.fetchall()

        # Actes médecin interne
        cursor.execute("""
            SELECT 
                id_acte,
                patient,
                DATE(date_acte) as date_acte,
                nom_acte,
                prix_acte_base,
                part_medecin,
                statut_paiement
            FROM medecin_interne_actes
            WHERE created_by = %s
            AND DATE(date_creation) BETWEEN %s AND %s
            ORDER BY date_creation DESC
            LIMIT 20
        """, (id_personnel, date_debut, date_fin))
        details['actes_medint'] = cursor.fetchall()

        # Factures
        cursor.execute("""
            SELECT 
                id,
                numero_facture,
                DATE(date_facture) as date_acte,
                type_facture,
                patient_nom,
                patient_prenom,
                total_ttc,
                statut,
                CASE 
                    WHEN created_by = %s THEN 'Créée'
                    WHEN valide_par = %s THEN 'Validée'
                END as action_type
            FROM factures
            WHERE (created_by = %s OR valide_par = %s)
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (id_personnel, id_personnel, id_personnel, id_personnel, date_debut, date_fin))
        details['factures'] = cursor.fetchall()

        # Paiements
        cursor.execute("""
            SELECT 
                'Accouchement' as type,
                DATE(date_paiement) as date_acte,
                montant,
                mode_paiement
            FROM accouchement_paiements_bons
            WHERE encaisse_par = %s
            AND DATE(created_at) BETWEEN %s AND %s
            
            UNION ALL
            
            SELECT 
                'Médecin Interne' as type,
                DATE(date_paiement) as date_acte,
                montant_paye as montant,
                mode_paiement
            FROM medecin_interne_paiements
            WHERE created_by = %s
            AND DATE(created_at) BETWEEN %s AND %s
            
            ORDER BY date_acte DESC
            LIMIT 20
        """, (id_personnel, date_debut, date_fin, id_personnel, date_debut, date_fin))
        details['paiements'] = cursor.fetchall()

        # Activité journalière
        cursor.execute("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as nb_actions,
                'accouchement' as type
            FROM accouchement_dossiers 
            WHERE created_by = %s AND DATE(created_at) BETWEEN %s AND %s
            GROUP BY DATE(created_at)
            
            UNION ALL
            
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as nb_actions,
                'decharge_gyneco' as type
            FROM gyneco_interne_decharges 
            WHERE created_by = %s AND DATE(created_at) BETWEEN %s AND %s
            GROUP BY DATE(created_at)
            
            UNION ALL
            
            SELECT 
                DATE(date_creation) as date,
                COUNT(*) as nb_actions,
                'decharge_kt' as type
            FROM kt_decharges_paiement 
            WHERE id_createur = %s AND DATE(date_creation) BETWEEN %s AND %s
            GROUP BY DATE(date_creation)
            
            UNION ALL
            
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as nb_actions,
                'decharge_medint' as type
            FROM medecin_interne_decharges 
            WHERE created_by = %s AND DATE(created_at) BETWEEN %s AND %s
            GROUP BY DATE(created_at)
            
            UNION ALL
            
            SELECT 
                DATE(date_creation) as date,
                COUNT(*) as nb_actions,
                'location_bloc' as type
            FROM location_bloc_dossier_patient 
            WHERE created_by = %s AND DATE(date_creation) BETWEEN %s AND %s
            GROUP BY DATE(date_creation)
            
            UNION ALL
            
            SELECT 
                DATE(date_creation) as date,
                COUNT(*) as nb_actions,
                'acte_medint' as type
            FROM medecin_interne_actes 
            WHERE created_by = %s AND DATE(date_creation) BETWEEN %s AND %s
            GROUP BY DATE(date_creation)
            
            UNION ALL
            
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as nb_actions,
                'facture' as type
            FROM factures 
            WHERE created_by = %s AND DATE(created_at) BETWEEN %s AND %s
            GROUP BY DATE(created_at)
            
            ORDER BY date DESC
        """, (
            id_personnel, date_debut, date_fin,
            id_personnel, date_debut, date_fin,
            id_personnel, date_debut, date_fin,
            id_personnel, date_debut, date_fin,
            id_personnel, date_debut, date_fin,
            id_personnel, date_debut, date_fin,
            id_personnel, date_debut, date_fin
        ))
        activite_journaliere = cursor.fetchall()

        return jsonify({
            'success': True,
            'personnel': personnel_info,
            'details': details,
            'activite_journaliere': activite_journaliere
        })

    except pymysql.MySQLError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route('/api/stats-personnel/export')
@login_required
def stats_personnel_export():
    """Export Excel des statistiques"""
    from io import BytesIO
    from flask import send_file
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')

    if not date_debut:
        date_debut = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not date_fin:
        date_fin = datetime.now().strftime('%Y-%m-%d')

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Même requête que l'API data (version simplifiée)
        query = """
        SELECT 
            p.nom,
            p.prenom,
            p.role,
            s. service_name,
            COUNT(DISTINCT acc.id_dossier) as nb_accouchements,
            COUNT(DISTINCT gd.id_decharge) as nb_decharges_gyneco,
            COUNT(DISTINCT ktd.id_decharge) as nb_decharges_kt,
            COUNT(DISTINCT mid.id_decharge) as nb_decharges_medint,
            COUNT(DISTINCT lb.id_dossier) as nb_location_bloc,
            COUNT(DISTINCT mia.id_acte) as nb_actes_medint,
            COUNT(DISTINCT apb.id_paiement) as nb_paiements_acc,
            COUNT(DISTINCT mip.id_paiement) as nb_paiements_medint,
            COUNT(DISTINCT f.id) as nb_factures,
            COALESCE(SUM(CASE WHEN acc.created_by = p.id_personnel THEN acc.prix_total ELSE 0 END), 0) as montant_accouchements,
            COALESCE(SUM(CASE WHEN gd.created_by = p.id_personnel THEN gd.montant_total ELSE 0 END), 0) as montant_gyneco,
            COALESCE(SUM(CASE WHEN ktd.id_createur = p.id_personnel THEN ktd.montant_total ELSE 0 END), 0) as montant_kt,
            COALESCE(SUM(CASE WHEN mid.created_by = p.id_personnel THEN mid.montant_total ELSE 0 END), 0) as montant_medint,
            COALESCE(SUM(CASE WHEN lb.created_by = p.id_personnel THEN lb.prix_total ELSE 0 END), 0) as montant_location,
            COALESCE(SUM(CASE WHEN f.created_by = p.id_personnel THEN f.total_ttc ELSE 0 END), 0) as montant_factures
        FROM personnel p
        LEFT JOIN services s ON p.id_service = s.id_service
        LEFT JOIN accouchement_dossiers acc ON acc.created_by = p.id_personnel 
            AND DATE(acc.created_at) BETWEEN %s AND %s
        LEFT JOIN gyneco_interne_decharges gd ON gd.created_by = p.id_personnel 
            AND DATE(gd.created_at) BETWEEN %s AND %s
        LEFT JOIN kt_decharges_paiement ktd ON ktd.id_createur = p.id_personnel 
            AND DATE(ktd.date_creation) BETWEEN %s AND %s
        LEFT JOIN medecin_interne_decharges mid ON mid.created_by = p.id_personnel 
            AND DATE(mid.created_at) BETWEEN %s AND %s
        LEFT JOIN location_bloc_dossier_patient lb ON lb.created_by = p.id_personnel 
            AND DATE(lb.date_creation) BETWEEN %s AND %s
        LEFT JOIN medecin_interne_actes mia ON mia.created_by = p.id_personnel 
            AND DATE(mia.date_creation) BETWEEN %s AND %s
        LEFT JOIN accouchement_paiements_bons apb ON apb.encaisse_par = p.id_personnel 
            AND DATE(apb.created_at) BETWEEN %s AND %s
        LEFT JOIN medecin_interne_paiements mip ON mip.created_by = p.id_personnel 
            AND DATE(mip.created_at) BETWEEN %s AND %s
        LEFT JOIN factures f ON f.created_by = p.id_personnel
            AND DATE(f.created_at) BETWEEN %s AND %s
        WHERE p.statut_activite = 1
        GROUP BY p.id_personnel, p.nom, p.prenom, p.role, s. service_name
        HAVING (nb_accouchements > 0 OR nb_decharges_gyneco > 0 OR nb_decharges_kt > 0 
                OR nb_decharges_medint > 0 OR nb_location_bloc > 0 OR nb_actes_medint > 0 OR nb_factures > 0)
        ORDER BY p.nom, p.prenom
        """

        params = [date_debut, date_fin] * 9
        cursor.execute(query, params)
        stats = cursor.fetchall()

        # Créer le fichier Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Statistiques Personnel"

        # Styles
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        center_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        right_alignment = Alignment(horizontal="right", vertical="center")
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # Titre
        ws.merge_cells('A1:Q1')
        title_cell = ws['A1']
        title_cell.value = f"Statistiques d'Activité du Personnel - Période: {date_debut} au {date_fin}"
        title_cell.font = Font(bold=True, size=14, color="366092")
        title_cell.alignment = center_alignment

        # En-têtes
        headers = [
            "Nom", "Prénom", "Rôle", "Service",
            "Accouchements", "Déch. Gynéco", "Déch. KT", "Déch. Méd.Int",
            "Location Bloc", "Actes Méd.Int", "Paiements Acc", "Paiements Méd",
            "Factures",
            "Mt Accouchements", "Mt Gynéco", "Mt KT", "Mt Méd.Int",
            "Mt Location", "Mt Factures"
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_alignment
            cell.border = thin_border

        # Données
        for row_num, stat in enumerate(stats, 4):
            ws.cell(row=row_num, column=1, value=stat['nom']).border = thin_border
            ws.cell(row=row_num, column=2, value=stat['prenom']).border = thin_border
            ws.cell(row=row_num, column=3, value=stat['role']).border = thin_border
            ws.cell(row=row_num, column=4, value=stat[' service_name']).border = thin_border

            # Nombres
            ws.cell(row=row_num, column=5, value=stat['nb_accouchements']).alignment = center_alignment
            ws.cell(row=row_num, column=5).border = thin_border
            ws.cell(row=row_num, column=6, value=stat['nb_decharges_gyneco']).alignment = center_alignment
            ws.cell(row=row_num, column=6).border = thin_border
            ws.cell(row=row_num, column=7, value=stat['nb_decharges_kt']).alignment = center_alignment
            ws.cell(row=row_num, column=7).border = thin_border
            ws.cell(row=row_num, column=8, value=stat['nb_decharges_medint']).alignment = center_alignment
            ws.cell(row=row_num, column=8).border = thin_border
            ws.cell(row=row_num, column=9, value=stat['nb_location_bloc']).alignment = center_alignment
            ws.cell(row=row_num, column=9).border = thin_border
            ws.cell(row=row_num, column=10, value=stat['nb_actes_medint']).alignment = center_alignment
            ws.cell(row=row_num, column=10).border = thin_border
            ws.cell(row=row_num, column=11, value=stat['nb_paiements_acc']).alignment = center_alignment
            ws.cell(row=row_num, column=11).border = thin_border
            ws.cell(row=row_num, column=12, value=stat['nb_paiements_medint']).alignment = center_alignment
            ws.cell(row=row_num, column=12).border = thin_border
            ws.cell(row=row_num, column=13, value=stat['nb_factures']).alignment = center_alignment
            ws.cell(row=row_num, column=13).border = thin_border

            # Montants
            ws.cell(row=row_num, column=14, value=float(stat['montant_accouchements'])).alignment = right_alignment
            ws.cell(row=row_num, column=14).number_format = '#,##0.00'
            ws.cell(row=row_num, column=14).border = thin_border
            ws.cell(row=row_num, column=15, value=float(stat['montant_gyneco'])).alignment = right_alignment
            ws.cell(row=row_num, column=15).number_format = '#,##0.00'
            ws.cell(row=row_num, column=15).border = thin_border
            ws.cell(row=row_num, column=16, value=float(stat['montant_kt'])).alignment = right_alignment
            ws.cell(row=row_num, column=16).number_format = '#,##0.00'
            ws.cell(row=row_num, column=16).border = thin_border
            ws.cell(row=row_num, column=17, value=float(stat['montant_medint'])).alignment = right_alignment
            ws.cell(row=row_num, column=17).number_format = '#,##0.00'
            ws.cell(row=row_num, column=17).border = thin_border
            ws.cell(row=row_num, column=18, value=float(stat['montant_location'])).alignment = right_alignment
            ws.cell(row=row_num, column=18).number_format = '#,##0.00'
            ws.cell(row=row_num, column=18).border = thin_border
            ws.cell(row=row_num, column=19, value=float(stat['montant_factures'])).alignment = right_alignment
            ws.cell(row=row_num, column=19).number_format = '#,##0.00'
            ws.cell(row=row_num, column=19).border = thin_border

        # Ajuster les largeurs
        column_widths = {
            'A': 15, 'B': 15, 'C': 12, 'D': 20,
            'E': 12, 'F': 12, 'G': 10, 'H': 12,
            'I': 12, 'J': 12, 'K': 12, 'L': 12, 'M': 10,
            'N': 15, 'O': 15, 'P': 15, 'Q': 15, 'R': 15, 'S': 15
        }

        for col, width in column_widths.items():
            ws.column_dimensions[col].width = width

        # Figer les volets
        ws.freeze_panes = 'A4'

        # Sauvegarder
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"stats_personnel_{date_debut}_{date_fin}.xlsx"

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        connection.close()