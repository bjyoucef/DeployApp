# app/situations_gyneco_interne.py
"""
Module de gestion des situations financières des gynécologues internes
"""
from datetime import datetime
from decimal import Decimal

from flask import redirect, url_for, flash, render_template, request, jsonify, make_response

from app import app, get_db_connection
from app.error import handle_errors
from app.medecins_internes.situations_internes_helpers import (
    get_periode_defaut, get_situation_paiements_gyneco,
    to_decimal
    )
from app.utils.utiles import login_required


# ==============================================================================
# LISTE DES GYNÉCOLOGUES INTERNES
# ==============================================================================

@app.route( '/situations/gyneco-internes' )
@login_required
@handle_errors()

def situations_gyneco_internes_list():
    """Liste des gynécologues internes avec leurs situations"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres de période
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Récupérer tous les gynécologues internes
        cursor.execute(
                """
                SELECT d.id,
                       CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                       s.name_specialty                       as specialite
                FROM doctors d
                         JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.est_interne = 1
                  AND s.name_specialty LIKE '%gyn%'
                ORDER BY d.last_name, d.first_name
                """
                )
        gynecos = cursor.fetchall()

        # Pour chaque gynéco, calculer ses stats sur la période
        gynecos_stats = [ ]
        total_general_honoraires = Decimal( '0' )
        total_general_dossiers = 0

        for gyneco in gynecos:
            # Compter les accouchements
            cursor.execute(
                    """
                    SELECT COUNT(*)                      as nb_accouchements,
                           COALESCE(SUM(part_gyneco), 0) as total_honoraires,
                           COALESCE(SUM(prix_total), 0)  as ca_genere
                    FROM accouchement_dossiers
                    WHERE id_gyneco = %s
                      AND est_gyneco_interne = 1
                      AND date_accouchement BETWEEN %s AND %s
                      AND (est_annule IS NULL OR est_annule = 0)
                    """, (gyneco[ 'id' ], date_debut, date_fin)
                    )
            stats = cursor.fetchone()

            # Répartition
            cursor.execute(
                    """
                    SELECT type_accouchement,
                           type_tarification,
                           COUNT(*)                      as nb,
                           COALESCE(SUM(part_gyneco), 0) as honoraires
                    FROM accouchement_dossiers
                    WHERE id_gyneco = %s
                      AND est_gyneco_interne = 1
                      AND date_accouchement BETWEEN %s AND %s
                      AND (est_annule IS NULL OR est_annule = 0)
                    GROUP BY type_accouchement, type_tarification
                    """, (gyneco[ 'id' ], date_debut, date_fin)
                    )
            repartition = cursor.fetchall()

            # Situation paiements
            situation = get_situation_paiements_gyneco(
                cursor, gyneco['id'], date_debut, date_fin
            )

            gynecos_stats.append(
                    {
                            'id': gyneco[ 'id' ],
                            'nom_complet': gyneco[ 'nom_complet' ],
                            'specialite': gyneco[ 'specialite' ],
                'nb_items': stats['nb_accouchements'],
                'total_honoraires': to_decimal(stats['total_honoraires']),
                'ca_genere': to_decimal(stats['ca_genere']),
                'repartition': repartition,
                'montant_paye': situation['montant_paye'],
                'solde_restant': situation['solde_restant'],
                'nb_decharges': situation['nb_decharges'],
                'nb_items_non_payes': situation['nb_items_non_payes'],
                'pourcentage_paye': situation['pourcentage_paye'],
                'specialite_badge': None  # Pas de badge spécial pour gynéco
            })

            total_general_honoraires += to_decimal(stats['total_honoraires'])
            total_general_dossiers += stats['nb_accouchements']

        # Configuration pour le template unifié
        config = {
            'type': 'gyneco',
            'primary_color': '#10b981',
            'primary_dark': '#059669',
            'primary_light': '#d1fae5',
            'bg_light': '#ecfdf5',
            'bg_medium': '#d1fae5',
            'subtitle': 'Gestion des situations financières des gynécologues internes',
            'medecin_label': 'gynécologue interne',
            'medecin_label_plural': 'Gynécologues internes',
            'item_label': 'accouchement',
            'item_label_plural': 'Accouchements totaux',
            'item_icon': 'fas fa-folder',
            'show_items_link': False,
            'decharges_route':'gyneco_interne_decharges_list',
            'stats_route': 'situations_gyneco_internes_stats',
            'list_route': 'situations_gyneco_internes_list',
            'detail_route': 'situation_gyneco_interne_detail',
            'create_decharge_route': 'gyneco_interne_decharge_create',
            'api_chart_data_route': 'api_situations_medecins_chart_data',
            'back_route': 'accouchement_list',
            'doctor_param': 'id_gyneco',
            'repartition_headers': [
                {'label': 'Type accouchement', 'class': ''},
                {'label': 'Tarification', 'class': ''},
                {'label': 'Nombre', 'class': 'text-center'},
                {'label': 'Honoraires', 'class': 'text-end'}
            ]
        }

        return render_template(
            'situations_internes/medecins_internes_list_unified.html',
            medecins=gynecos_stats,
                date_debut = date_debut,
                date_fin = date_fin,
                total_general_honoraires = float( total_general_honoraires ),
            total_general_items=total_general_dossiers,
                title = "Situations Gynécologues Internes",
                config = config
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# DÉTAIL SITUATION GYNÉCOLOGUE
# ==============================================================================

@app.route( '/situations/gyneco-interne/<int:id_gyneco>' )
@login_required
@handle_errors()

def situation_gyneco_interne_detail( id_gyneco ):
    """Détail de la situation d'un gynécologue interne"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Infos gynécologue
        cursor.execute(
                """
                SELECT d.id,
                       CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                       s.name_specialty                       as specialite,
                       d.est_interne
                FROM doctors d
                         JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.id = %s
                """, (id_gyneco,)
                )
        gyneco = cursor.fetchone()

        if not gyneco or not gyneco['est_interne']:
            flash('Gynécologue non trouvé ou non interne', 'danger')
            return redirect( url_for( 'situations_gyneco_internes_list' ) )

        # Situation paiements
        situation_paiements = get_situation_paiements_gyneco(
            cursor, id_gyneco, date_debut, date_fin
        )

        # Décharges
        cursor.execute("""
            SELECT id_decharge, numero_decharge, date_decharge,
                   montant_total, montant_paye_total, solde_restant,
                   nb_dossiers as nb_items, nb_tranches, statut
            FROM gyneco_interne_decharges
            WHERE id_gyneco = %s
              AND periode_debut >= %s
              AND periode_fin <= %s
              AND statut != 'ANNULE'
            ORDER BY date_decharge DESC
        """, (id_gyneco, date_debut, date_fin))
        decharges = cursor.fetchall()

        # Dossiers (items)
        cursor.execute("""
            SELECT id_dossier, patiente, date_accouchement,
                   type_accouchement, type_tarification,
                   prix_total, part_gyneco, part_clinique,
                   COALESCE(gyneco_paye, 0) as gyneco_paye
                FROM accouchement_dossiers
                WHERE id_gyneco = %s
                  AND est_gyneco_interne = 1
                  AND date_accouchement BETWEEN %s AND %s
                  AND (est_annule IS NULL OR est_annule = 0)
                ORDER BY date_accouchement DESC
                """, (id_gyneco, date_debut, date_fin)
                )
        dossiers = cursor.fetchall()

        # Statistiques
        cursor.execute(
                """
                SELECT COUNT(*)                                                          as total_dossiers,
                       COALESCE(SUM(part_gyneco), 0)                                     as total_honoraires,
                       COALESCE(SUM(prix_total), 0)                                      as ca_genere,
                       COALESCE(SUM(part_clinique), 0)                                   as part_clinique_totale,
                       SUM(CASE WHEN type_accouchement = 'VOIE_BASSE' THEN 1 ELSE 0 END) as nb_voie_basse,
                   SUM(CASE WHEN type_accouchement = 'CESARIENNE' THEN 1 ELSE 0 END) as nb_cesarienne
                FROM accouchement_dossiers
                WHERE id_gyneco = %s
                  AND est_gyneco_interne = 1
                  AND date_accouchement BETWEEN %s AND %s
                  AND (est_annule IS NULL OR est_annule = 0)
        """, (id_gyneco, date_debut, date_fin))
        stats_data = cursor.fetchone()

        # Répartition
        cursor.execute(
                """
                SELECT type_accouchement,
                       type_tarification,
                       COUNT(*)                      as nombre,
                       COALESCE(SUM(part_gyneco), 0) as honoraires_totaux,
                       COALESCE(AVG(part_gyneco), 0) as honoraires_moyens
                FROM accouchement_dossiers
                WHERE id_gyneco = %s
                  AND est_gyneco_interne = 1
                  AND date_accouchement BETWEEN %s AND %s
                  AND (est_annule IS NULL OR est_annule = 0)
                GROUP BY type_accouchement, type_tarification
                ORDER BY type_tarification, type_accouchement
                """, (id_gyneco, date_debut, date_fin)
                )
        repartition = cursor.fetchall()

        # Configuration
        config = {
            'type': 'gyneco',
            'primary_color': '#aa49b9',
            'primary_dark': '#aa49b9',
            'primary_light': '#f1eafa',
            'bg_light': '#ecfdf5',
            'bg_medium': '#f1eafa',
            'medecin_type': 'Gynécologue Interne',
            'item_label': 'accouchement',
            'item_label_plural': 'accouchements',
            'item_icon': 'fas fa-folder',
            'list_route': 'situations_gyneco_internes_list',
            'create_decharge_route': 'gyneco_interne_decharge_create',
            'pdf_route': 'generer_situation_pdf',
            'decharge_detail_route': 'gyneco_interne_decharge_detail',
            'doctor_param': 'id_gyneco',
            'repartition_table_template': 'situations_internes/_repartition_gyneco.html',
            'items_table_template': 'situations_internes/_items_gyneco.html',
            'api_chart_data_route': 'api_situations_medecins_chart_data',
            'extra_stats': [
                {'value': stats_data['nb_voie_basse'], 'icon': 'fas fa-baby', 'label': 'Voie Basse'},
                {'value': stats_data['nb_cesarienne'], 'icon': 'fas fa-procedures', 'label': 'Césariennes'}
            ],
            'info_note': 'Les honoraires affichés sont les honoraires fixes du gynécologue interne selon les tarifs en vigueur (8k/15k pour Convention, 12k/20k pour Payant).'
        }
        # Préparer les stats
        stats = {
            'total_items': stats_data['total_dossiers'],
            'total_honoraires': to_decimal(stats_data['total_honoraires']),
            'ca_genere': to_decimal(stats_data['ca_genere']),
            'part_clinique_totale': to_decimal(stats_data['part_clinique_totale'])
        }

        # Préparer medecin avec pourcentage (pas applicable pour gynéco)
        medecin = {
            'id': gyneco['id'],
            'nom_complet': gyneco['nom_complet'],
            'specialite': gyneco['specialite'],
            'pourcentage': None
        }

        return render_template(
            'situations_internes/medecin_interne_detail_unified.html',
            medecin=medecin,
            items=dossiers,
                stats = stats,
                repartition = repartition,
            situation_paiements=situation_paiements,
            decharges=decharges,
                date_debut = date_debut,
                date_fin = date_fin,
                title = f"Situation - {gyneco[ 'nom_complet' ]}",
                config = config,


                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# GÉNÉRATION DE SITUATION (PDF)
# ==============================================================================

@app.route( '/situations/gyneco-interne/<int:id_gyneco>/generer-pdf' )
@login_required
@handle_errors()

def generer_situation_pdf( id_gyneco ):
    """Génère un PDF de la situation du gynécologue"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Infos gynécologue
        cursor.execute(
            """
            SELECT CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                   s.name_specialty                       as specialite
            FROM doctors d
                     JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
                       """, (id_gyneco,)
            )
        gyneco = cursor.fetchone()

        # Dossiers
        cursor.execute(
            """
            SELECT id_dossier,
                   patiente,
                   date_accouchement,
                   type_accouchement,
                   type_tarification,
                   part_gyneco
            FROM accouchement_dossiers
            WHERE id_gyneco = %s
              AND est_gyneco_interne = 1
              AND date_accouchement BETWEEN %s AND %s
              AND (est_annule IS NULL OR est_annule = 0)
            ORDER BY date_accouchement
                       """, (id_gyneco, date_debut, date_fin)
            )
        dossiers = cursor.fetchall()

        # Stats
        cursor.execute(
            """
            SELECT COUNT(*)                      as total,
                   COALESCE(SUM(part_gyneco), 0) as total_honoraires
            FROM accouchement_dossiers
            WHERE id_gyneco = %s
              AND est_gyneco_interne = 1
              AND date_accouchement BETWEEN %s AND %s
              AND (est_annule IS NULL OR est_annule = 0)
                       """, (id_gyneco, date_debut, date_fin)
            )
        stats = cursor.fetchone()


        # Fonctions helper pour les badges
        def get_type_badge_class( item ):
            if item[ 'type_accouchement' ] == 'VOIE_BASSE':
                return 'badge-voie-basse'
            return 'badge-cesarienne'


        def get_type_value( item ):
            if item[ 'type_accouchement' ] == 'VOIE_BASSE':
                return 'Voie Basse'
            return 'Césarienne'


        def get_tarif_badge_class( item ):
            if item[ 'type_tarification' ] == 'CONVENTION':
                return 'badge-convention'
            return 'badge-payant'


        def get_tarif_value( item ):
            if item[ 'type_tarification' ] == 'CONVENTION':
                return 'Convention'
            return 'Payant'


        # Configuration
        config = {
                'type': 'gyneco',
                'primary_color': '#10b981',
                'primary_dark': '#059669',
                'primary_light': '#d1fae5',
                'bg_light': '#ecfdf5',
                'clinique_name': 'CLINIQUE INAYA',
                'clinique_info': 'Adresse de la clinique • Téléphone • Email',
                'medecin_label_singular': 'Gynécologue',
                'medecin_type': 'Gynécologue Interne',
                'item_label': 'accouchement',
                'item_label_plural': 'accouchements',
                'patient_label': 'Patiente',
                'id_field': 'id_dossier',
                'date_field': 'date_accouchement',
                'patient_field': 'patiente',
                'honoraires_field': 'part_gyneco',
                'api_chart_data_route': 'api_situations_medecins_chart_data',
                'pdf_columns': [
                        {
                                'label': 'Type',
                                'class': '',
                                'type': 'badge',
                                'badge_class': get_type_badge_class,
                                'value': get_type_value
                                },
                        {
                                'label': 'Tarif',
                                'class': '',
                                'type': 'badge',
                                'badge_class': get_tarif_badge_class,
                                'value': get_tarif_value
                                }
                        ],
                'pdf_note': 'Ce document constitue un relevé des honoraires pour la période indiquée. Les honoraires sont calculés selon les tarifs en vigueur pour les gynécologues internes.'
                }

        # Préparer medecin
        medecin = {
                'nom_complet': gyneco[ 'nom_complet' ],
                'specialite': gyneco[ 'specialite' ],
                'pourcentage': None
                }

        html = render_template(
                'situations_internes/situation_pdf_unified.html',
                medecin = medecin,
                items = dossiers,
                stats = stats,
                date_debut = date_debut,
                date_fin = date_fin,
                date_generation = datetime.now().strftime( '%d/%m/%Y %H:%M' ),
                config = config
                )

        response = make_response( html )
        response.headers[ 'Content-Type' ] = 'text/html'
        return response

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# STATISTIQUES COMPARATIVES
# ==============================================================================

@app.route( '/situations/gyneco-internes/statistiques' )
@login_required
@handle_errors()

def situations_gyneco_internes_stats():
    """Statistiques comparatives entre gynécologues internes"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        # Stats par gynécologue
        cursor.execute(
                """
                SELECT d.id,
                   CONCAT(d.first_name, ' ', d.last_name) as medecin,
                   s.name_specialty as specialite,
                   COUNT(acc.id_dossier) as nb_items,
                       COALESCE(SUM(acc.part_gyneco), 0)                                     as total_honoraires,
                       COALESCE(AVG(acc.part_gyneco), 0)                                     as honoraires_moyens,
                       SUM(CASE WHEN acc.type_accouchement = 'VOIE_BASSE' THEN 1 ELSE 0 END) as nb_voie_basse,
                       SUM(CASE WHEN acc.type_accouchement = 'CESARIENNE' THEN 1 ELSE 0 END) as nb_cesarienne
                FROM doctors d
                         JOIN specialty s ON d.id_specialty = s.id_specialty
                         LEFT JOIN accouchement_dossiers acc ON d.id = acc.id_gyneco
                    AND acc.est_gyneco_interne = 1
                    AND acc.date_accouchement BETWEEN %s AND %s
                    AND (acc.est_annule IS NULL OR acc.est_annule = 0)
                WHERE d.est_interne = 1
                  AND s.name_specialty LIKE '%%gyn%%'
                GROUP BY d.id
                ORDER BY total_honoraires DESC
                """, (date_debut, date_fin)
                )
        stats_gynecos = cursor.fetchall()

        # Ajouter specialite_badge à None pour chaque gynéco
        stats_gynecos = [
            {**dict(stat), 'specialite_badge': None}
            for stat in stats_gynecos
        ]

        # Évolution mensuelle globale
        cursor.execute(
                """
                SELECT DATE_FORMAT(date_accouchement, '%%Y-%%m') as mois,
                   COUNT(*) as nb_items,
                       COALESCE(SUM(part_gyneco), 0)             as honoraires
                FROM accouchement_dossiers
                WHERE est_gyneco_interne = 1
                  AND date_accouchement BETWEEN %s AND %s
                  AND (est_annule IS NULL OR est_annule = 0)
                GROUP BY DATE_FORMAT(date_accouchement, '%%Y-%%m')
                ORDER BY mois
                """, (date_debut, date_fin)
                )
        evolution = cursor.fetchall()

        # Totaux globaux
        cursor.execute(
                """
            SELECT COUNT(*) as total_items,
                       COALESCE(SUM(part_gyneco), 0) as total_honoraires,
                       COALESCE(SUM(prix_total), 0)  as ca_total
                FROM accouchement_dossiers
                WHERE est_gyneco_interne = 1
                  AND date_accouchement BETWEEN %s AND %s
                  AND (est_annule IS NULL OR est_annule = 0)
                """, (date_debut, date_fin)
                )
        totaux = cursor.fetchone()

        # Données pour le graphique de répartition (Voie Basse vs Césarienne)
        total_vb = sum(s['nb_voie_basse'] for s in stats_gynecos)
        total_cs = sum(s['nb_cesarienne'] for s in stats_gynecos)

        chart_repartition_data = {
            'labels': ['Voie Basse', 'Césarienne'],
            'datasets': [{
                'data': [total_vb, total_cs],
                'backgroundColor': [
                    'rgba(236, 72, 153, 0.8)',
                    'rgba(59, 130, 246, 0.8)'
                ],
                'borderColor': [
                    'rgba(219, 39, 119, 1)',
                    'rgba(29, 78, 216, 1)'
                ],
                'borderWidth': 2
            }]
        }

        # Configuration
        config = {
            'type': 'gyneco',
            'primary_color': '#10b981',
            'primary_dark': '#059669',
            'primary_light': '#d1fae5',
            'bg_light': '#ecfdf5',
            'bg_medium': '#d1fae5',
            'primary_color_alpha': 'rgba(16, 185, 129, 0.8)',
            'primary_shadow': 'rgba(16, 185, 129, 0.4)',
            'item_label': 'accouchement',
            'item_label_plural': 'Accouchements',
            'item_icon': 'fas fa-folder',
            'medecin_label_singular': 'Gynécologue',
            'show_specialite': False,  # Tous sont gynécos
            'extra_columns': [
                {'label': 'VB', 'class': 'text-center', 'field': 'nb_voie_basse'},
                {'label': 'CS', 'class': 'text-center', 'field': 'nb_cesarienne'}
            ],
            'list_route': 'situations_gyneco_internes_list',
            'chart_repartition_type': 'doughnut',
            'chart_repartition_title': 'Répartition Types d\'Accouchements',
            'chart_repartition_data': chart_repartition_data,
                'api_chart_data_route': 'api_situations_medecins_chart_data',
        }

        return render_template(
            'situations_internes/medecins_internes_stats_unified.html',
            stats_medecins=stats_gynecos,
                evolution = evolution,
                totaux = totaux,
                date_debut = date_debut,
                date_fin = date_fin,
                title = "Statistiques Gynécologues Internes",
            config=config
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# API - DONNÉES POUR GRAPHIQUES
# ==============================================================================

@app.route( '/api/situations/gyneco-internes/chart-data' )
@login_required
def api_situations_chart_data():
    """API pour récupérer les données des graphiques"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )
        id_gyneco = request.args.get( 'id_gyneco' )

        if not date_debut or not date_fin:
            date_debut, date_fin = get_periode_defaut()

        where_gyneco = ""
        params = [ date_debut, date_fin ]

        if id_gyneco:
            where_gyneco = "AND acc.id_gyneco = %s"
            params.append( id_gyneco )

        # Évolution journalière
        cursor.execute(
            f"""
            SELECT DATE_FORMAT(date_accouchement, '%%Y-%%m-%%d') as periode,
                   COUNT(*) as nb,
                   COALESCE(SUM(part_gyneco), 0) as honoraires
            FROM accouchement_dossiers acc
            WHERE est_gyneco_interne = 1
              AND date_accouchement BETWEEN %s AND %s
              AND (acc.est_annule IS NULL OR acc.est_annule = 0)
              {where_gyneco}
            GROUP BY DATE(date_accouchement)
            ORDER BY date_accouchement
            """, params
        )
        evolution_journaliere = cursor.fetchall()

        # Évolution mensuelle
        cursor.execute(
                f"""
            SELECT DATE_FORMAT(date_accouchement, '%%Y-%%m') as mois,
                   COUNT(*) as nb,
                   COALESCE(SUM(part_gyneco), 0) as honoraires
            FROM accouchement_dossiers acc
            WHERE est_gyneco_interne = 1
              AND date_accouchement BETWEEN %s AND %s
              AND (acc.est_annule IS NULL OR acc.est_annule = 0)
              {where_gyneco}
            GROUP BY DATE_FORMAT(date_accouchement, '%%Y-%%m')
            ORDER BY mois
            """, params
                )
        evolution_mensuelle = cursor.fetchall()

        # Répartition par type
        cursor.execute(
                f"""
            SELECT type_accouchement,
                   type_tarification,
                   COUNT(*) as nb,
                   COALESCE(SUM(part_gyneco), 0) as honoraires
            FROM accouchement_dossiers acc
            WHERE est_gyneco_interne = 1
              AND date_accouchement BETWEEN %s AND %s
              AND (acc.est_annule IS NULL OR acc.est_annule = 0)
              {where_gyneco}
            GROUP BY type_accouchement, type_tarification
            """, params
                )
        repartition = cursor.fetchall()

        return jsonify(
                {
                'evolution': [ dict( row ) for row in evolution_journaliere ],
                'evolution_mensuelle': [ dict( row ) for row in evolution_mensuelle ],
                        'repartition': [ dict( row ) for row in repartition ]
                        }
                )

    finally:
        cursor.close()
        conn.close()
