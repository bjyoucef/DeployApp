# app/situations_medecin_interne.py
"""
Module de gestion des situations financières des médecins internes
Similaire aux gynécos internes mais pour orthopédie/chirurgie générale
"""
from datetime import datetime
from decimal import Decimal

from flask import redirect, url_for, flash, render_template, request, jsonify, make_response

from app import app, get_db_connection
from app.error import handle_errors
from app.medecins_internes.situations_internes_helpers import (
    get_periode_defaut, get_situation_paiements_medecin,
    to_decimal
    )
from app.utils.utiles import login_required


# ==============================================================================
# LISTE DES MÉDECINS INTERNES
# ==============================================================================

@app.route( '/situations/medecins-internes' )
@login_required
@handle_errors()

def situations_medecins_internes_list():
    """Liste des médecins internes avec leurs situations"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres de période
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Récupérer tous les médecins internes
        cursor.execute(
            """
            SELECT d.id,
                   CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                   s.name_specialty                       as specialite
            FROM doctors d
                     JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.est_interne = 1
              AND s.name_specialty IN ('ORTHOPÉDIE', 'CHIRURGIE GÉNÉRALE')
            ORDER BY d.last_name, d.first_name
                       """
            )
        medecins = cursor.fetchall()

        # Pour chaque médecin, calculer ses stats
        medecins_stats = [ ]
        total_general_honoraires = Decimal( '0' )
        total_general_actes = 0

        for medecin in medecins:
            # Compter les actes
            cursor.execute(
                """
                SELECT COUNT(*)                         as nb_actes,
                       COALESCE(SUM(part_medecin), 0)   as total_honoraires,
                       COALESCE(SUM(prix_acte_base), 0) as ca_genere
                FROM medecin_interne_actes
                WHERE id_doctor = %s
                  AND date_acte BETWEEN %s AND %s
                           """, (medecin[ 'id' ], date_debut, date_fin)
                )
            stats = cursor.fetchone()

            # Pourcentage selon spécialité
            pourcentage = 45 if 'ORTHO' in medecin['specialite'].upper() else 50

            # Répartition
            cursor.execute(
                """
                SELECT nom_acte,
                       COUNT(*)                       as nb,
                       COALESCE(SUM(part_medecin), 0) as honoraires
                FROM medecin_interne_actes
                WHERE id_doctor = %s
                  AND date_acte BETWEEN %s AND %s
                GROUP BY nom_acte
                           """, (medecin[ 'id' ], date_debut, date_fin)
                )
            repartition = cursor.fetchall()

            # Situation paiements
            situation = get_situation_paiements_medecin(
                cursor, medecin['id'], date_debut, date_fin
            )

            # Badge selon spécialité
            if 'ORTHO' in medecin['specialite'].upper():
                specialite_badge = {'class': 'badge-ortho'}
            else:
                specialite_badge = {'class': 'badge-chirurgie'}

            medecins_stats.append(
                    {
                            'id': medecin[ 'id' ],
                            'nom_complet': medecin[ 'nom_complet' ],
                            'specialite': medecin[ 'specialite' ],
                'nb_items': stats['nb_actes'],
                'total_honoraires': to_decimal(stats['total_honoraires']),
                'ca_genere': to_decimal(stats['ca_genere']),
                            'repartition': repartition,
                'montant_paye': situation['montant_paye'],
                'solde_restant': situation['solde_restant'],
                'nb_decharges': situation['nb_decharges'],
                'nb_items_non_payes': situation['nb_items_non_payes'],
                'pourcentage_paye': situation['pourcentage_paye'],
                'pourcentage_medecin': pourcentage,
                'specialite_badge': specialite_badge
            })

            total_general_honoraires += to_decimal(stats['total_honoraires'])
            total_general_actes += stats['nb_actes']

        # Configuration pour le template unifié
        config = {
            'type': 'medecin',
            'primary_color': '#3b82f6',
            'primary_dark': '#2563eb',
            'primary_light': '#dbeafe',
            'bg_light': '#eff6ff',
            'bg_medium': '#dbeafe',
            'subtitle': 'Gestion des situations financières des médecins internes',
            'medecin_label': 'médecin interne',
            'medecin_label_plural': 'Médecins internes',
            'item_label': 'acte',
            'item_label_plural': 'Actes totaux',
            'item_icon': 'fas fa-procedures',
            'show_items_link': False,
            'items_icon': 'fas fa-file-medical',
            'items_label': 'Actes',
            'decharges_route': 'medecin_interne_decharges_list',  # ✅ Juste le nom
            'stats_route': 'situations_medecins_internes_stats',  # ✅ Juste le nom
            'list_route': 'situations_medecins_internes_list',  # ✅ Juste le nom
            'detail_route': 'situation_medecin_interne_detail',
            'create_decharge_route': 'medecin_interne_decharge_create',
            'api_chart_data_route': 'api_situations_chart_data',
            'back_route': 'medecin_interne_actes_list',
            'doctor_param': 'id_doctor',
            'repartition_headers': [
                {'label': 'Type d\'acte', 'class': ''},
                {'label': 'Nombre', 'class': 'text-center'},
                {'label': 'Honoraires', 'class': 'text-end'}
            ]
        }

        return render_template(
            'situations_internes/medecins_internes_list_unified.html',
                medecins = medecins_stats,
                date_debut = date_debut,
                date_fin = date_fin,
                total_general_honoraires = float( total_general_honoraires ),
            total_general_items=total_general_actes,
                title = "Situations Médecins Internes",
                config = config
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# DÉTAIL SITUATION MÉDECIN
# ==============================================================================

@app.route( '/situations/medecin-interne/<int:id_doctor>' )
@login_required
@handle_errors()

def situation_medecin_interne_detail( id_doctor ):
    """Détail de la situation d'un médecin interne"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres de période
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Infos médecin
        cursor.execute(
            """
            SELECT d.id,
                   CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                   s.name_specialty                       as specialite,
                   d.est_interne
            FROM doctors d
                     JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
        """, (id_doctor,))
        medecin_data = cursor.fetchone()

        if not medecin_data or not medecin_data['est_interne']:
            flash('Médecin non trouvé ou non interne', 'danger')
            return redirect( url_for( 'situations_medecins_internes_list' ) )

        # Pourcentage selon spécialité
        pourcentage = 45 if 'ORTHO' in medecin_data['specialite'].upper() else 50

        # Situation paiements
        situation_paiements = get_situation_paiements_medecin( cursor, id_doctor, date_debut, date_fin )

        # Décharges
        cursor.execute("""
            SELECT id_decharge, numero_decharge, date_decharge,
                   montant_total, montant_paye_total, solde_restant,
                   nb_actes as nb_items, nb_tranches, statut
            FROM medecin_interne_decharges
            WHERE id_doctor = %s
              AND periode_debut >= %s
              AND periode_fin <= %s
              AND statut != 'ANNULE'
            ORDER BY date_decharge DESC
                       """, (id_doctor, date_debut, date_fin)
            )
        decharges = cursor.fetchall()

        # Actes (items)
        cursor.execute("""
            SELECT id_acte, patient, date_acte, nom_acte,
                   prix_acte_base, part_medecin, part_clinique,
                   COALESCE(medecin_paye, 0) as medecin_paye
            FROM medecin_interne_actes
            WHERE annule_at IS NULL
              AND id_doctor = %s
              AND date_acte BETWEEN %s AND %s
            ORDER BY date_acte DESC
                       """, (id_doctor, date_debut, date_fin)
            )
        actes = cursor.fetchall()

        # Statistiques
        cursor.execute(
            """
            SELECT COUNT(*)                         as total_actes,
                   COALESCE(SUM(part_medecin), 0)   as total_honoraires,
                   COALESCE(SUM(prix_acte_base), 0) as ca_genere,
                   COALESCE(SUM(part_clinique), 0)  as part_clinique_totale
            FROM medecin_interne_actes
            WHERE annule_at IS NULL
              AND id_doctor = %s
              AND date_acte BETWEEN %s AND %s
        """, (id_doctor, date_debut, date_fin))
        stats_data = cursor.fetchone()

        # Répartition
        cursor.execute(
            """
            SELECT nom_acte,
                   COUNT(*)                       as nombre,
                   COALESCE(SUM(part_medecin), 0) as honoraires_totaux,
                   COALESCE(AVG(part_medecin), 0) as honoraires_moyens
            FROM medecin_interne_actes
            WHERE annule_at IS NULL
              AND id_doctor = %s
              AND date_acte BETWEEN %s AND %s
            GROUP BY nom_acte
            ORDER BY honoraires_totaux DESC
                       """, (id_doctor, date_debut, date_fin)
            )
        repartition = cursor.fetchall()

        # Configuration
        config = {
            'type': 'medecin',
            'primary_color': '#3b82f6',
            'primary_dark': '#2563eb',
            'primary_light': '#dbeafe',
            'bg_light': '#eff6ff',
            'bg_medium': '#dbeafe',
            'medecin_type': 'Médecin Interne',
            'item_label': 'acte',
            'item_label_plural': 'actes',
            'item_icon': 'fas fa-procedures',
            'list_route': 'situations_medecins_internes_list',
            'create_decharge_route': 'medecin_interne_decharge_create',
            'pdf_route': 'generer_situation_medecin_pdf',
            'decharge_detail_route': 'medecin_interne_decharge_detail',
            'doctor_param': 'id_doctor','api_chart_data_route': 'api_situations_chart_data',
            'repartition_table_template': 'situations_internes/_repartition_medecin.html',
            'items_table_template': 'situations_internes/_items_medecin.html',
            'extra_stats': None,
            'info_note': f'Les honoraires affichés sont calculés selon le pourcentage du médecin interne ({pourcentage}% pour {medecin_data["specialite"]}).'
        }

        # Préparer les stats
        stats = {
            'total_items': stats_data['total_actes'],
            'total_honoraires': to_decimal(stats_data['total_honoraires']),
            'ca_genere': to_decimal(stats_data['ca_genere']),
            'part_clinique_totale': to_decimal(stats_data['part_clinique_totale']),
            'pourcentage_medecin': pourcentage
        }

        # Préparer medecin
        medecin = {
            'id': medecin_data['id'],
            'nom_complet': medecin_data['nom_complet'],
            'specialite': medecin_data['specialite'],
            'pourcentage': pourcentage
        }

        return render_template(
            'situations_internes/medecin_interne_detail_unified.html',
                medecin = medecin,
            items=actes,
                stats = stats,
                repartition = repartition,
                situation_paiements = situation_paiements,
                decharges = decharges,
                date_debut = date_debut,
                date_fin = date_fin,
                title = f"Situation - {medecin_data[ 'nom_complet' ]}",
                config = config
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# GÉNÉRATION DE SITUATION (PDF)
# ==============================================================================

@app.route( '/situations/medecin-interne/<int:id_doctor>/generer-pdf' )
@login_required
@handle_errors()

def generer_situation_medecin_pdf( id_doctor ):
    """Génère un PDF de la situation du médecin"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Infos médecin
        cursor.execute(
            """
            SELECT CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                   s.name_specialty                       as specialite
            FROM doctors d
                     JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
        """, (id_doctor,))
        medecin_data = cursor.fetchone()

        # Pourcentage selon spécialité
        pourcentage = 45 if 'ORTHO' in medecin_data['specialite'].upper() else 50

        # Actes
        cursor.execute(
            """
            SELECT id_acte,
                   patient,
                   date_acte,
                   nom_acte,
                   part_medecin
            FROM medecin_interne_actes
            WHERE id_doctor = %s
              AND date_acte BETWEEN %s AND %s
            ORDER BY date_acte
                       """, (id_doctor, date_debut, date_fin)
            )
        actes = cursor.fetchall()

        # Stats
        cursor.execute(
            """
            SELECT COUNT(*)                       as total,
                   COALESCE(SUM(part_medecin), 0) as total_honoraires
            FROM medecin_interne_actes
            WHERE id_doctor = %s
              AND date_acte BETWEEN %s AND %s
                       """, (id_doctor, date_debut, date_fin)
            )
        stats = cursor.fetchone()

        # Fonction helper pour afficher le nom de l'acte
        def get_acte_value(item):
            return item['nom_acte'] or 'Acte médical'

        # Configuration
        config = {
            'type': 'medecin',
            'primary_color': '#3b82f6',
            'primary_dark': '#2563eb',
            'primary_light': '#dbeafe',
            'bg_light': '#eff6ff',
            'clinique_name': 'CLINIQUE INAYA',
            'clinique_info': 'Adresse de la clinique • Téléphone • Email',
            'medecin_label_singular': 'Médecin',
            'medecin_type': 'Médecin Interne',
            'item_label': 'acte médical',
            'item_label_plural': 'actes médicaux',
            'patient_label': 'Patient',
            'id_field': 'id_acte','api_chart_data_route': 'api_situations_chart_data',
            'date_field': 'date_acte',
            'patient_field': 'patient',
            'honoraires_field': 'part_medecin',
            'pdf_columns': [
                {
                    'label': 'Acte',
                    'class': '',
                    'type': 'text',
                    'value': get_acte_value
                }
            ],
            'pdf_note': f'Ce document constitue un relevé des honoraires pour la période indiquée. Les honoraires sont calculés selon le pourcentage applicable aux médecins internes ({pourcentage}% pour {medecin_data["specialite"]}).'
        }

        # Préparer medecin
        medecin = {
            'nom_complet': medecin_data['nom_complet'],
            'specialite': medecin_data['specialite'],
            'pourcentage': pourcentage
        }

        html = render_template(
            'situations_internes/situation_pdf_unified.html',
            medecin=medecin,
            items=actes,
            stats=stats,
            date_debut=date_debut,
            date_fin=date_fin,
            date_generation=datetime.now().strftime('%d/%m/%Y %H:%M'),
            config=config
        )

        response = make_response(html)
        response.headers['Content-Type'] = 'text/html'
        return response

    finally:
        cursor.close()
        conn.close()

# ==============================================================================
# STATISTIQUES COMPARATIVES
# ==============================================================================

@app.route( '/situations/medecins-internes/statistiques' )
@login_required
@handle_errors()

def situations_medecins_internes_stats():
    """Statistiques comparatives entre médecins internes"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Stats par médecin
        cursor.execute(
            """
            SELECT d.id,
                   CONCAT(d.first_name, ' ', d.last_name) as medecin,
                   s.name_specialty                       as specialite,
                   COUNT(a.id_acte) as nb_items,
                   COALESCE(SUM(a.part_medecin), 0)       as total_honoraires,
                   COALESCE(AVG(a.part_medecin), 0)       as honoraires_moyens
            FROM doctors d
                     JOIN specialty s ON d.id_specialty = s.id_specialty
                     LEFT JOIN medecin_interne_actes a ON d.id = a.id_doctor
                AND a.date_acte BETWEEN %s AND %s
            WHERE d.est_interne = 1
              AND s.name_specialty IN ('ORTHOPÉDIE', 'CHIRURGIE GÉNÉRALE')
            GROUP BY d.id
            ORDER BY total_honoraires DESC
        """, (date_debut, date_fin))
        stats_medecins_data = cursor.fetchall()

        # Ajouter les badges de spécialité
        stats_medecins = []
        for stat in stats_medecins_data:
            stat_dict = dict(stat)
            if 'ORTHO' in stat['specialite'].upper():
                stat_dict['specialite_badge'] = {'class': 'badge-ortho'}
            else:
                stat_dict['specialite_badge'] = {'class': 'badge-chirurgie'}
            stats_medecins.append(stat_dict)

        # Évolution mensuelle globale
        cursor.execute(
            """
            SELECT DATE_FORMAT(date_acte, '%%Y-%%m') as mois,
                   COUNT(*) as nb_items,
                   COALESCE(SUM(part_medecin), 0)    as honoraires
            FROM medecin_interne_actes
            WHERE date_acte BETWEEN %s AND %s
            GROUP BY DATE_FORMAT(date_acte, '%%Y-%%m')
            ORDER BY mois
                       """, (date_debut, date_fin)
            )
        evolution = cursor.fetchall()

        # Totaux globaux
        cursor.execute(
            """
            SELECT COUNT(*) as total_items,
                   COALESCE(SUM(part_medecin), 0)   as total_honoraires,
                   COALESCE(SUM(prix_acte_base), 0) as ca_total
            FROM medecin_interne_actes
            WHERE date_acte BETWEEN %s AND %s
                       """, (date_debut, date_fin)
            )
        totaux = cursor.fetchone()

        # Données pour le graphique de répartition par spécialité
        specialites = {}
        for m in stats_medecins:
            spec = m['specialite']
            if spec not in specialites:
                specialites[spec] = {'actes': 0, 'honoraires': 0}
            specialites[spec]['actes'] += m['nb_items']
            specialites[spec]['honoraires'] += m['total_honoraires']

        labels = list(specialites.keys())
        data = [specialites[s]['honoraires'] for s in labels]
        colors = [
            'rgba(99, 102, 241, 0.8)' if 'ORTHO' in l else 'rgba(236, 72, 153, 0.8)'
            for l in labels
        ]

        chart_repartition_data = {
            'labels': labels,
            'datasets': [{
                'data': data,
                'backgroundColor': colors,
                'borderColor': [c.replace('0.8', '1') for c in colors],
                'borderWidth': 2
            }]
        }

        # Configuration
        config = {
            'type': 'medecin',
            'primary_color': '#3b82f6',
            'primary_dark': '#2563eb',
            'primary_light': '#dbeafe',
            'bg_light': '#eff6ff',
            'bg_medium': '#dbeafe',
            'primary_color_alpha': 'rgba(59, 130, 246, 0.8)',
            'primary_shadow': 'rgba(59, 130, 246, 0.4)',
            'item_label': 'acte',
            'item_label_plural': 'Actes',
            'item_icon': 'fas fa-procedures',
            'medecin_label_singular': 'Médecin','api_chart_data_route': 'api_situations_chart_data',
            'show_specialite': True,  # Différentes spécialités
            'extra_columns': None,  # Pas de colonnes supplémentaires
            'list_route': 'situations_medecins_internes_list',
            'chart_repartition_type': 'doughnut',
            'chart_repartition_title': 'Répartition par Spécialité',
            'chart_repartition_data': chart_repartition_data
        }

        return render_template(
            'situations_internes/medecins_internes_stats_unified.html',
                stats_medecins = stats_medecins,
                evolution = evolution,
                totaux = totaux,
                date_debut = date_debut,
                date_fin = date_fin,
                title = "Statistiques Médecins Internes",
                config = config
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# API - DONNÉES POUR GRAPHIQUES
# ==============================================================================

@app.route( '/api/situations/medecins-internes/chart-data' )
@login_required
def api_situations_medecins_chart_data():
    """API pour récupérer les données des graphiques"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )
        id_doctor = request.args.get( 'id_doctor' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        where_doctor = ""
        params = [ date_debut, date_fin ]

        if id_doctor:
            where_doctor = "AND a.id_doctor = %s"
            params.append( id_doctor )

        # Évolution par jour (détaillée)
        cursor.execute(
            f"""
            SELECT DATE_FORMAT(date_acte, '%%Y-%%m-%%d') as periode,
                   COUNT(*) as nb,
                   COALESCE(SUM(part_medecin), 0) as honoraires
            FROM medecin_interne_actes a
            WHERE date_acte BETWEEN %s AND %s
              {where_doctor}
            GROUP BY DATE(date_acte)
            ORDER BY date_acte
        """, params
        )
        evolution_journaliere = cursor.fetchall()

        # Évolution mensuelle (pour le tableau)
        cursor.execute(
            f"""
            SELECT DATE_FORMAT(date_acte, '%%Y-%%m') as mois,
                   COUNT(*) as nb_items,
                   COALESCE(SUM(part_medecin), 0) as honoraires
            FROM medecin_interne_actes a
            WHERE date_acte BETWEEN %s AND %s
              {where_doctor}
            GROUP BY DATE_FORMAT(date_acte, '%%Y-%%m')
            ORDER BY mois
        """, params
            )
        evolution_mensuelle = cursor.fetchall()

        # Répartition par type
        cursor.execute(
            f"""
            SELECT nom_acte,
                   COUNT(*) as nb,
                   COALESCE(SUM(part_medecin), 0) as honoraires
            FROM medecin_interne_actes a
            WHERE date_acte BETWEEN %s AND %s
              {where_doctor}
            GROUP BY nom_acte
        """, params
            )
        repartition = cursor.fetchall()

        # Statistiques supplémentaires
        cursor.execute(
            f"""
            SELECT 
                DAYOFWEEK(date_acte) as jour_semaine,
                COUNT(*) as nb_actes,
                COALESCE(SUM(part_medecin), 0) as honoraires
            FROM medecin_interne_actes a
            WHERE date_acte BETWEEN %s AND %s
              {where_doctor}
            GROUP BY DAYOFWEEK(date_acte)
            ORDER BY jour_semaine
        """, params
        )
        stats_semaine = cursor.fetchall()

        return jsonify(
                {
                'evolution': [ dict( row ) for row in evolution_journaliere ],
                'evolution_mensuelle': [ dict( row ) for row in evolution_mensuelle ],
                'repartition': [ dict( row ) for row in repartition ],
                'stats_semaine': [ dict( row ) for row in stats_semaine ]
                        }
                )

    finally:
        cursor.close()
        conn.close()