import math
from decimal import Decimal

from flask import render_template, request, jsonify

from app import app, get_db_connection
from app.error import handle_errors
from app.prestation_location_bloc.location_bloc import (
    to_decimal, convert_decimals_to_float
)
from app.utils.utiles import login_required


# ========================================================================
# FONCTIONS DE CALCUL - DISTINCTION CLAIRE
# ========================================================================

def get_tarif_forfaitaire_anesthesie(cursor, id_acte_anesthesie):
    """
    Récupère le TARIF FORFAITAIRE (prix fixe facturé au patient)
    Ce montant NE VARIE PAS avec la durée et est lié à l'ACTE, pas à l'intervenant

    ⚠️ IMPORTANT : Le tarif forfaitaire est maintenant dans anesthesie_type_acte

    Args:
        cursor: Curseur de base de données
        id_acte_anesthesie: ID du type d'acte d'anesthésie

    Returns:
        Decimal: Tarif forfaitaire (prix fixe)
    """
    cursor.execute(
        """
        SELECT tarif_forfaitaire
        FROM anesthesie_type_acte
        WHERE id_acte_anesthesie = %s
          AND est_actif = 1
        """, (id_acte_anesthesie,)
    )

    tarif = cursor.fetchone()
    if not tarif or not tarif['tarif_forfaitaire']:
        return Decimal('0')

    return to_decimal(tarif['tarif_forfaitaire'])


def calculer_honoraires_anesthesie(cursor, id_acte_anesthesie, id_type_intervenant, duree_reelle):
    """
    Calcule les HONORAIRES (rémunération de l'intervenant)
    Ce montant VARIE avec la durée de l'opération

    Args:
        cursor: Curseur de base de données
        id_acte_anesthesie: ID du type d'acte d'anesthésie
        id_type_intervenant: ID du type d'intervenant
        duree_reelle: Durée réelle en minutes

    Returns:
        Decimal: Montant des honoraires calculés (rémunération)
    """
    # Récupération des tarifs
    cursor.execute(
        """
        SELECT honoraires_base, supplement_30min, duree_avant_supplement
        FROM anesthesie_tarifs
        WHERE id_acte_anesthesie = %s
          AND id_type_intervenant = %s
          AND est_actif = 1
        """, (id_acte_anesthesie, id_type_intervenant)
    )

    tarif = cursor.fetchone()
    if not tarif:
        return Decimal('0')

    honoraires_base = to_decimal(tarif['honoraires_base'])
    supplement_30min = to_decimal(tarif.get('supplement_30min'))
    duree_avant_supplement = tarif.get('duree_avant_supplement') or 0

    # Calcul : honoraires de base + suppléments de durée
    total = honoraires_base

    if supplement_30min and supplement_30min > 0 and duree_reelle > duree_avant_supplement:
        minutes_supplementaires = duree_reelle - duree_avant_supplement
        tranches_30min = math.ceil(minutes_supplementaires / 30)
        total += tranches_30min * supplement_30min

    return total


def calculer_total_honoraires_anesthesie(cursor, id_dossier):
    """
    Calcule le total des honoraires d'anesthésie pour un dossier
    (pour la comptabilité interne - ce que les intervenants reçoivent)
    """
    cursor.execute(
        """
        SELECT SUM(honoraires_calcules) as total
        FROM location_bloc_dossier_anesthesie
        WHERE id_dossier = %s
        """, (id_dossier,)
    )

    result = cursor.fetchone()
    return to_decimal(result['total']) if result and result['total'] else Decimal('0')


# ========================================================================
# ROUTES API
# ========================================================================

@app.route('/api/anesthesie/calculer_tarif', methods=['POST'])
@login_required
def api_calculer_tarif_anesthesie():
    """Calcule le tarif forfaitaire pour un acte (indépendant de l'intervenant)"""
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        id_acte = data.get('id_acte_anesthesie')

        # Récupérer le tarif forfaitaire (lié à l'acte)
        tarif = get_tarif_forfaitaire_anesthesie(cursor, id_acte)

        return jsonify({
            'tarif_forfaitaire': float(tarif)
        })
    finally:
        cursor.close()
        connection.close()


@app.route('/api/anesthesie/types_actes')
@login_required
def api_anesthesie_types_actes():
    """Retourne la liste des types d'actes d'anesthésie avec tarifs forfaitaires"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT id_acte_anesthesie, nom_acte, description, tarif_forfaitaire
            FROM anesthesie_type_acte
            WHERE est_actif = 1
            ORDER BY nom_acte
            """
        )

        actes = cursor.fetchall()
        return jsonify(convert_decimals_to_float(actes))
    except Exception as e:
        app.logger.error(f'Erreur API types actes: {str(e)}')
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/anesthesie/personnel')
@login_required
def api_anesthesie_personnel():
    """Retourne la liste du personnel d'anesthésie"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT p.id_personnel_anesthesie,
               p.nom,
               p.prenom,
               CONCAT(p.prenom, ' ', p.nom) as nom_complet,
               p.id_type_intervenant,
               t.nom_type,
               t.description                as type_description
        FROM anesthesie_personnel p
                 JOIN anesthesie_intervenant_type t ON p.id_type_intervenant = t.id_type_intervenant
        WHERE p.est_actif = 1
        ORDER BY t.nom_type, p.nom, p.prenom
        """
    )

    personnel = cursor.fetchall()
    return jsonify(convert_decimals_to_float(personnel))


@app.route('/api/anesthesie/types_intervenants')
@login_required
def api_anesthesie_types_intervenants():
    """Retourne la liste des types d'intervenants"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id_type_intervenant, nom_type, description
        FROM anesthesie_intervenant_type
        WHERE est_actif = 1
        ORDER BY nom_type
        """
    )

    types = cursor.fetchall()
    return jsonify(convert_decimals_to_float(types))


@app.route('/api/anesthesie/calculer_prix_et_honoraires', methods=['POST'])
@login_required
def api_calculer_prix_et_honoraires():
    """
    Calcule à la fois :
    1. Le prix de l'anesthésie pour le dossier (tarif forfaitaire)
    2. Les honoraires des intervenants (rémunération avec durée)
    """
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        id_acte = data.get('id_acte_anesthesie')
        id_anesthesiste = data.get('id_anesthesiste')
        id_reanimateur = data.get('id_reanimateur')
        duree_reelle = int(data.get('duree_reelle', 90))

        # ✅ Prix pour le dossier (tarif forfaitaire de l'acte)
        tarif_forfaitaire = get_tarif_forfaitaire_anesthesie(cursor, id_acte)

        intervenants = []
        honoraires_details = []

        # Traiter l'anesthésiste
        if id_anesthesiste:
            cursor.execute(
                """
                SELECT id_type_intervenant
                FROM anesthesie_personnel
                WHERE id_personnel_anesthesie = %s
                """, (id_anesthesiste,)
            )
            anes = cursor.fetchone()
            if anes:
                id_type = anes['id_type_intervenant']

                # Honoraires pour l'intervenant (variable avec durée)
                honoraires = calculer_honoraires_anesthesie(cursor, id_acte, id_type, duree_reelle)

                honoraires_details.append({
                    'id_personnel': id_anesthesiste,
                    'type': 'Anesthésiste',
                    'tarif_forfaitaire': float(tarif_forfaitaire),
                    'honoraires': float(honoraires)
                })

        # Traiter le réanimateur
        if id_reanimateur:
            cursor.execute(
                """
                SELECT id_type_intervenant
                FROM anesthesie_personnel
                WHERE id_personnel_anesthesie = %s
                """, (id_reanimateur,)
            )
            rea = cursor.fetchone()
            if rea:
                id_type = rea['id_type_intervenant']

                # Honoraires pour l'intervenant (variable avec durée)
                honoraires = calculer_honoraires_anesthesie(cursor, id_acte, id_type, duree_reelle)

                honoraires_details.append({
                    'id_personnel': id_reanimateur,
                    'type': 'Réanimateur',
                    'tarif_forfaitaire': float(tarif_forfaitaire),
                    'honoraires': float(honoraires)
                })

        # Prix total = tarif forfaitaire × nombre d'intervenants
        prix_total_dossier = tarif_forfaitaire

        return jsonify({
            'prix_anesthesie_dossier': float(prix_total_dossier),  # Ce qui est facturé
            'honoraires_total': float(sum(h['honoraires'] for h in honoraires_details)),  # Ce qui est payé
            'details': honoraires_details
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/anesthesie/tarifs/<int:id_acte>')
@login_required
def api_anesthesie_tarifs(id_acte):
    """Retourne les tarifs pour un acte d'anesthésie par type d'intervenant"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer le tarif forfaitaire (depuis anesthesie_type_acte)
    cursor.execute(
        """
        SELECT tarif_forfaitaire
        FROM anesthesie_type_acte
        WHERE id_acte_anesthesie = %s
          AND est_actif = 1
        """, (id_acte,)
    )

    acte_info = cursor.fetchone()
    tarif_forfaitaire = to_decimal(acte_info['tarif_forfaitaire']) if acte_info else Decimal('0')

    # Récupérer les honoraires par type d'intervenant
    cursor.execute(
        """
        SELECT t.id_tarif,
               t.id_acte_anesthesie,
               t.id_type_intervenant,
               ti.nom_type,
               ti.description as type_description,
               t.honoraires_base,
               t.supplement_30min,
               t.duree_avant_supplement
        FROM anesthesie_tarifs t
                 JOIN anesthesie_intervenant_type ti ON t.id_type_intervenant = ti.id_type_intervenant
        WHERE t.id_acte_anesthesie = %s
          AND t.est_actif = 1
        ORDER BY ti.nom_type
        """, (id_acte,)
    )

    tarifs = cursor.fetchall()
    return jsonify(convert_decimals_to_float(tarifs))


# ========================================================================
# PAGE GLOBALE DES HONORAIRES (INCHANGÉE)
# ========================================================================

@app.route('/anesthesie/honoraires/global')
@login_required
@handle_errors()

def anesthesie_honoraires_global():
    """Page globale des honoraires d'anesthésie (BLOC + ACCOUCHEMENTS + KT)"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Filtres
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    personnel_filter = request.args.get('personnel', 'all')
    type_intervenant_filter = request.args.get('type_intervenant', 'all')
    type_intervention = request.args.get('type_intervention', 'all')
    statut_paiement = request.args.get('statut_paiement', 'all')  # 'all', 'impayes', 'payes'
    patient_search = request.args.get('patient', '').strip()

    # Nouveaux paramètres de tri
    order_by = request.args.get('order_by', 'date')  # 'date', 'patient', 'personnel', 'type', 'honoraires'
    order_direction = request.args.get('order_direction', 'desc')  # 'asc' ou 'desc'

    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 25

    params = { }

    # =============================================
    # ACTES BLOC OPÉRATOIRE
    # =============================================
    query_bloc = """
                 SELECT da.id_dossier_anesthesie     as id_acte,
                        'BLOC'                       as source,
                        da.id_dossier,
                        d.patient,
                        d.location_date              as date_intervention,
                        aa.nom_acte,
                        CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                        p.id_personnel_anesthesie,
                        ti.nom_type                  as type_intervenant,
                        ti.id_type_intervenant,
                        da.duree_reelle,
                        da.honoraires_calcules,
                        da.observations,
                        da.date_creation
                 FROM location_bloc_dossier_anesthesie da
                          JOIN location_bloc_dossier_patient d ON da.id_dossier = d.id_dossier
                          JOIN anesthesie_type_acte aa ON da.id_acte_anesthesie = aa.id_acte_anesthesie
                          JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
                          JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
                 WHERE 1 = 1 \
                 """

    if date_debut:
        query_bloc += " AND d.location_date >= %(date_debut)s"
        params[ 'date_debut' ] = date_debut
    if date_fin:
        query_bloc += " AND d.location_date <= %(date_fin)s"
        params[ 'date_fin' ] = date_fin
    if personnel_filter != 'all':
        query_bloc += " AND p.id_personnel_anesthesie = %(personnel)s"
        params[ 'personnel' ] = personnel_filter
    if type_intervenant_filter != 'all':
        query_bloc += " AND ti.id_type_intervenant = %(type_intervenant)s"
        params[ 'type_intervenant' ] = type_intervenant_filter
    if statut_paiement == 'impayes':
        query_bloc += " AND da.honoraires_payes = 0 AND da.id_decharge_anesthesie IS NULL"
    elif statut_paiement == 'payes':
        query_bloc += " AND da.honoraires_payes = 1"
    if patient_search:
        query_bloc += " AND d.patient LIKE %(patient_search)s"
        params['patient_search'] = f'%{patient_search}%'

    # =============================================
    # ACTES ACCOUCHEMENTS
    # =============================================
    query_accouchement = """
                         SELECT aa.id_acte_anesthesie        as id_acte,
                                'ACCOUCHEMENT'               as source,
                                aa.id_dossier,
                                ad.patiente                  as patient,
                                ad.date_accouchement         as date_intervention,
                                ata.nom_acte,
                                CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                                p.id_personnel_anesthesie,
                                ti.nom_type                  as type_intervenant,
                                ti.id_type_intervenant,
                                NULL                         as duree_reelle,
                                aa.honoraires_calcules,
                                NULL                         as observations,
                                aa.date_creation
                         FROM accouchement_dossier_anesthesie aa
                                  JOIN accouchement_dossiers ad ON aa.id_dossier = ad.id_dossier
                                  JOIN anesthesie_type_acte ata ON aa.id_acte_anesthesie = ata.id_acte_anesthesie
                                  JOIN anesthesie_personnel p ON aa.id_personnel_anesthesie = p.id_personnel_anesthesie
                                  JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
                         WHERE 1 = 1 \
                         """

    if date_debut:
        query_accouchement += " AND ad.date_accouchement >= %(date_debut)s"
    if date_fin:
        query_accouchement += " AND ad.date_accouchement <= %(date_fin)s"
    if personnel_filter != 'all':
        query_accouchement += " AND p.id_personnel_anesthesie = %(personnel)s"
    if type_intervenant_filter != 'all':
        query_accouchement += " AND ti.id_type_intervenant = %(type_intervenant)s"
    if statut_paiement == 'impayes':
        query_accouchement += " AND aa.honoraires_payes = 0 AND aa.id_decharge_anesthesie IS NULL"
    elif statut_paiement == 'payes':
        query_accouchement += " AND aa.honoraires_payes = 1"
    if patient_search:
        query_accouchement += " AND ad.patiente LIKE %(patient_search)s"
    # Exclure les accouchements annulés
    query_accouchement += " AND (ad.est_annule IS NULL OR ad.est_annule = 0)"

    # =============================================
    # NOUVEAU : ACTES KT
    # =============================================
    query_kt = """
               SELECT ka.id_dossier_anesthesie     as id_acte,
                      'KT'                         as source,
                      ka.id_dossier,
                      kd.patient,
                      kd.acte_date                 as date_intervention,
                      ata.nom_acte,
                      CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                      p.id_personnel_anesthesie,
                      ti.nom_type                  as type_intervenant,
                      ti.id_type_intervenant,
                      ka.duree_reelle,
                      ka.honoraires_calcules,
                      ka.observations,
                      ka.date_creation
               FROM kt_dossier_anesthesie ka
                        JOIN kt_dossier_patient kd ON ka.id_dossier = kd.id_dossier
                        JOIN anesthesie_type_acte ata ON ka.id_acte_anesthesie = ata.id_acte_anesthesie
                        JOIN anesthesie_personnel p ON ka.id_personnel_anesthesie = p.id_personnel_anesthesie
                        JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
               WHERE 1 = 1 \
               """

    if date_debut:
        query_kt += " AND kd.acte_date >= %(date_debut)s"
    if date_fin:
        query_kt += " AND kd.acte_date <= %(date_fin)s"
    if personnel_filter != 'all':
        query_kt += " AND p.id_personnel_anesthesie = %(personnel)s"
    if type_intervenant_filter != 'all':
        query_kt += " AND ti.id_type_intervenant = %(type_intervenant)s"
    if statut_paiement == 'impayes':
        query_kt += " AND ka.honoraires_payes = 0 AND ka.id_decharge_anesthesie IS NULL"
    elif statut_paiement == 'payes':
        query_kt += " AND ka.honoraires_payes = 1"
    if patient_search:
        query_kt += " AND kd.patient LIKE %(patient_search)s"
    # =============================================
    # NOUVEAU : ACTES MÉDECINS INTERNES
    # =============================================
    query_mi = """
               SELECT ma.id_anesthesie             as id_acte,
                      'MEDECIN_INTERNE'            as source,
                      ma.id_acte                   as id_dossier,
                      mi.patient,
                      mi.date_acte                 as date_intervention,
                      ata.nom_acte,
                      CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                      p.id_personnel_anesthesie,
                      ti.nom_type                  as type_intervenant,
                      ti.id_type_intervenant,
                      ma.duree_reelle,
                      ma.honoraires_calcules,
                      ma.observations,
                      ma.date_creation
               FROM medecin_interne_anesthesie ma
                        JOIN medecin_interne_actes mi ON ma.id_acte = mi.id_acte
                        JOIN anesthesie_type_acte ata ON ma.id_acte_anesthesie = ata.id_acte_anesthesie
                        JOIN anesthesie_personnel p ON ma.id_personnel_anesthesie = p.id_personnel_anesthesie
                        JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
               WHERE 1 = 1 \
               """

    if date_debut:
        query_mi += " AND mi.date_acte >= %(date_debut)s"
    if date_fin:
        query_mi += " AND mi.date_acte <= %(date_fin)s"
    if personnel_filter != 'all':
        query_mi += " AND p.id_personnel_anesthesie = %(personnel)s"
    if type_intervenant_filter != 'all':
        query_mi += " AND ti.id_type_intervenant = %(type_intervenant)s"
    if statut_paiement == 'impayes':
        query_mi += " AND ma.anesthesiste_paye = 0 AND ma.id_decharge_anesthesie IS NULL"
    elif statut_paiement == 'payes':
        query_mi += " AND ma.anesthesiste_paye = 1"
    if patient_search:
        query_mi += " AND mi.patient LIKE %(patient_search)s"
    # Exclure les actes MI annulés
    query_mi += " AND (mi.est_annule IS NULL OR mi.est_annule = 0)"

    # =============================================
    # FUSION DES DONNÉES
    # =============================================
    actes = [ ]

    if type_intervention in [ 'all', 'bloc' ]:
        cursor.execute( query_bloc, params )
        actes.extend( cursor.fetchall() )

    if type_intervention in [ 'all', 'accouchement' ]:
        cursor.execute( query_accouchement, params )
        actes.extend( cursor.fetchall() )

    if type_intervention in [ 'all', 'kt' ]:
        cursor.execute( query_kt, params )
        actes.extend( cursor.fetchall() )

    # Ajouter les actes des médecins internes (toujours)
    try:
        cursor.execute( query_mi, params )
        actes.extend( cursor.fetchall() )
    except Exception as e:
        app.logger.warning(f"Erreur récupération actes MI: {str(e)}")
    # =============================================
    # TRI DYNAMIQUE
    # =============================================
    reverse_order = (order_direction == 'desc')

    # Définir la clé de tri selon le critère choisi
    if order_by == 'patient':
        actes.sort(key=lambda x: (x['patient'] or '').lower(), reverse=reverse_order)
    elif order_by == 'personnel':
        actes.sort(key=lambda x: (x['nom_personnel'] or '').lower(), reverse=reverse_order)
    elif order_by == 'type':
        actes.sort(key=lambda x: (x['type_intervenant'] or '').lower(), reverse=reverse_order)
    elif order_by == 'honoraires':
        actes.sort(key=lambda x: to_decimal(x['honoraires_calcules']), reverse=reverse_order)
    else:  # 'date' par défaut
        actes.sort(key=lambda x: x['date_intervention'], reverse=reverse_order)

    # =============================================
    # TOTAUX PAR INTERVENANT (COMBINÉS)
    # =============================================
    query_totaux_bloc = """
        SELECT 
            CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
            p.id_personnel_anesthesie,
            ti.nom_type as type_intervenant,
            COUNT(da.id_dossier_anesthesie) as nombre_actes,
            SUM(da.honoraires_calcules) as total_honoraires,
            'BLOC' as source
        FROM location_bloc_dossier_anesthesie da
        JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
        JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
        JOIN location_bloc_dossier_patient d ON da.id_dossier = d.id_dossier
        WHERE 1=1
    """ + (f" AND d.location_date >= %(date_debut)s" if date_debut else "") + \
                        (f" AND d.location_date <= %(date_fin)s" if date_fin else "") + """
        GROUP BY p.id_personnel_anesthesie, nom_personnel, type_intervenant
    """

    query_totaux_accouchement = """
        SELECT 
            CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
            p.id_personnel_anesthesie,
            ti.nom_type as type_intervenant,
            COUNT(aa.id_acte_anesthesie) as nombre_actes,
            SUM(aa.honoraires_calcules) as total_honoraires,
            'ACCOUCHEMENT' as source
        FROM accouchement_dossier_anesthesie aa
        JOIN anesthesie_personnel p ON aa.id_personnel_anesthesie = p.id_personnel_anesthesie
        JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
        JOIN accouchement_dossiers ad ON aa.id_dossier = ad.id_dossier
        WHERE 1=1
    """ + (f" AND ad.date_accouchement >= %(date_debut)s" if date_debut else "") + \
                                (f" AND ad.date_accouchement <= %(date_fin)s" if date_fin else "") + """
        GROUP BY p.id_personnel_anesthesie, nom_personnel, type_intervenant
    """
    query_totaux_kt = """
        SELECT 
            CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
            p.id_personnel_anesthesie,
            ti.nom_type as type_intervenant,
            COUNT(ka.id_dossier_anesthesie) as nombre_actes,
            SUM(ka.honoraires_calcules) as total_honoraires,
            'KT' as source
        FROM kt_dossier_anesthesie ka
        JOIN anesthesie_personnel p ON ka.id_personnel_anesthesie = p.id_personnel_anesthesie
        JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
        JOIN kt_dossier_patient kd ON ka.id_dossier = kd.id_dossier
        WHERE 1=1
    """ + (f" AND kd.acte_date >= %(date_debut)s" if date_debut else "") + \
                      (f" AND kd.acte_date <= %(date_fin)s" if date_fin else "") + """
        GROUP BY p.id_personnel_anesthesie, nom_personnel, type_intervenant
    """
    totaux_personnel_raw = [ ]

    if type_intervention in [ 'all', 'bloc' ]:
        cursor.execute( query_totaux_bloc, params )
        totaux_personnel_raw.extend( cursor.fetchall() )

    if type_intervention in [ 'all', 'accouchement' ]:
        cursor.execute( query_totaux_accouchement, params )
        totaux_personnel_raw.extend( cursor.fetchall() )

    if type_intervention in [ 'all', 'kt' ]:
        cursor.execute( query_totaux_kt, params )
        totaux_personnel_raw.extend( cursor.fetchall() )

    # Agréger les totaux par personnel
    totaux_dict = { }
    for total in totaux_personnel_raw:
        key = total[ 'id_personnel_anesthesie' ]
        if key not in totaux_dict:
            totaux_dict[ key ] = {
                    'nom_personnel': total[ 'nom_personnel' ],
                    'type_intervenant': total[ 'type_intervenant' ],
                    'nombre_actes': 0,
                    'total_honoraires': Decimal( '0' ),
                    'nombre_actes_bloc': 0,
                    'total_honoraires_bloc': Decimal( '0' ),
                    'nombre_actes_accouchement': 0,
                    'total_honoraires_accouchement': Decimal( '0' ),
                    'nombre_actes_kt': 0,
                    'total_honoraires_kt': Decimal( '0' ),
                    'nombre_actes_mi': 0,
                    'total_honoraires_mi': Decimal( '0' )
                    }

        totaux_dict[ key ][ 'nombre_actes' ] += total[ 'nombre_actes' ]
        totaux_dict[ key ][ 'total_honoraires' ] += to_decimal( total[ 'total_honoraires' ] )

        if total[ 'source' ] == 'BLOC':
            totaux_dict[ key ][ 'nombre_actes_bloc' ] = total[ 'nombre_actes' ]
            totaux_dict[ key ][ 'total_honoraires_bloc' ] = to_decimal( total[ 'total_honoraires' ] )
        elif total[ 'source' ] == 'ACCOUCHEMENT':
            totaux_dict[ key ][ 'nombre_actes_accouchement' ] = total[ 'nombre_actes' ]
            totaux_dict[ key ][ 'total_honoraires_accouchement' ] = to_decimal( total[ 'total_honoraires' ] )
        elif total[ 'source' ] == 'KT':
            totaux_dict[ key ][ 'nombre_actes_kt' ] = total[ 'nombre_actes' ]
            totaux_dict[ key ][ 'total_honoraires_kt' ] = to_decimal( total[ 'total_honoraires' ] )
        elif total[ 'source' ] == 'MEDECIN_INTERNE':
            totaux_dict[ key ][ 'nombre_actes_mi' ] = total[ 'nombre_actes' ]
            totaux_dict[ key ][ 'total_honoraires_mi' ] = to_decimal( total[ 'total_honoraires' ] )

    totaux_personnel = sorted(
        totaux_dict.values(),
        key = lambda x: x[ 'total_honoraires' ],
        reverse = True
        )

    # =============================================
    # PERSONNEL ET TYPES
    # =============================================
    cursor.execute(
        """
        SELECT p.id_personnel_anesthesie,
               CONCAT(p.prenom, ' ', p.nom) as nom_complet,
               ti.nom_type
        FROM anesthesie_personnel p
                 JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
        WHERE p.est_actif = 1
        ORDER BY ti.nom_type, p.nom, p.prenom
        """
        )
    personnel_list = cursor.fetchall()

    cursor.execute(
        """
        SELECT id_type_intervenant, nom_type, description
        FROM anesthesie_intervenant_type
        WHERE est_actif = 1
        ORDER BY nom_type
        """
        )
    types_intervenants = cursor.fetchall()

    # Totaux généraux
    total_general = sum( to_decimal( a[ 'honoraires_calcules' ] ) for a in actes )
    total_general_bloc = sum( to_decimal( a[ 'honoraires_calcules' ] ) for a in actes if a[ 'source' ] == 'BLOC' )
    total_general_accouchement = sum(
            to_decimal( a[ 'honoraires_calcules' ] ) for a in actes if a[ 'source' ] == 'ACCOUCHEMENT'
            )
    total_general_kt = sum( to_decimal( a[ 'honoraires_calcules' ] ) for a in actes if a[ 'source' ] == 'KT' )
    total_general_mi = sum( to_decimal( a[ 'honoraires_calcules' ] ) for a in actes if a[ 'source' ] == 'MEDECIN_INTERNE' )

    # Pagination des actes
    total_count = len(actes)
    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
    page = max(1, min(page, total_pages))
    actes_paginated = actes[(page - 1) * per_page : page * per_page]

    # =============================================
    # IMPAYÉS PAR PERSONNEL (pour section inline)
    # =============================================
    impayes_dict = {}
    source_configs = [
        ('BLOC', 'location_bloc_dossier_anesthesie', 'honoraires_payes'),
        ('ACCOUCHEMENT', 'accouchement_dossier_anesthesie', 'honoraires_payes'),
        ('KT', 'kt_dossier_anesthesie', 'honoraires_payes'),
        ('MEDECIN_INTERNE', 'medecin_interne_anesthesie', 'anesthesiste_paye'),
    ]
    for src_label, src_table, paid_col in source_configs:
        try:
            extra = ""
            if src_table == 'medecin_interne_anesthesie':
                extra = " AND a.est_annule = 0"
            cursor.execute(f"""
                SELECT a.id_personnel_anesthesie,
                       CONCAT(p.prenom, ' ', p.nom) as nom_complet,
                       ti.nom_type as type_intervenant,
                       COUNT(*) as nb_actes,
                       COALESCE(SUM(a.honoraires_calcules), 0) as total_impaye
                FROM {src_table} a
                JOIN anesthesie_personnel p ON a.id_personnel_anesthesie = p.id_personnel_anesthesie
                JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
                WHERE a.{paid_col} = 0 AND a.id_decharge_anesthesie IS NULL {extra}
                GROUP BY a.id_personnel_anesthesie, nom_complet, type_intervenant
            """)
            for row in cursor.fetchall():
                pid = row['id_personnel_anesthesie']
                if pid not in impayes_dict:
                    impayes_dict[pid] = {
                        'id_personnel_anesthesie': pid,
                        'nom_complet': row['nom_complet'],
                        'type_intervenant': row['type_intervenant'],
                        'nb_actes': 0,
                        'total_impaye': Decimal('0'),
                    }
                impayes_dict[pid]['nb_actes'] += row['nb_actes']
                impayes_dict[pid]['total_impaye'] += to_decimal(row['total_impaye'])
        except Exception as e:
            app.logger.warning(f"Erreur récup impayés {src_label}: {e}")

    impayes_personnel = sorted(impayes_dict.values(), key=lambda x: x['total_impaye'], reverse=True)

    return render_template(
            'anesthesie_honoraires/honoraires_rea_anes.html',
            actes = actes_paginated,
            totaux_personnel = totaux_personnel,
            personnel_list = personnel_list,
            types_intervenants = types_intervenants,
            total_general = total_general,
            total_general_bloc = total_general_bloc,
            total_general_accouchement = total_general_accouchement,
            total_general_kt = total_general_kt,
            total_general_mi = total_general_mi,
            impayes_personnel = impayes_personnel,
            page = page,
            per_page = per_page,
            total_pages = total_pages,
            total_count = total_count,
            filters = {
                    'date_debut': date_debut or '',
                    'date_fin': date_fin or '',
                    'personnel': personnel_filter,
                    'type_intervenant': type_intervenant_filter,
                    'type_intervention': type_intervention,
                    'statut_paiement': statut_paiement,
                    'patient': patient_search,
                    'order_by': order_by,
                    'order_direction': order_direction
                    },
            title = "Honoraires d'Anesthésie - Global",
            )


@app.route( '/anesthesie/honoraires/global/export_excel' )
@login_required

def anesthesie_honoraires_global_export():
    """Export Excel des honoraires d'anesthésie globaux"""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from flask import send_file

    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer les mêmes filtres
    date_debut = request.args.get( 'date_debut' )
    date_fin = request.args.get( 'date_fin' )
    personnel_filter = request.args.get( 'personnel', 'all' )
    type_intervention = request.args.get( 'type_intervention', 'all' )

    params = { }

    # Même logique que la route principale
    query_bloc = """
                 SELECT d.location_date              as date_intervention,
                        d.patient,
                        aa.nom_acte,
                        CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                        ti.nom_type                  as type_intervenant,
                        da.duree_reelle,
                        da.honoraires_calcules,
                        da.observations,
                        'BLOC'                       as source
                 FROM location_bloc_dossier_anesthesie da
                          JOIN location_bloc_dossier_patient d ON da.id_dossier = d.id_dossier
                          JOIN anesthesie_type_acte aa ON da.id_acte_anesthesie = aa.id_acte_anesthesie
                          JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
                          JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
                 WHERE 1 = 1 \
                 """

    if date_debut:
        query_bloc += " AND d.location_date >= %(date_debut)s"
        params[ 'date_debut' ] = date_debut
    if date_fin:
        query_bloc += " AND d.location_date <= %(date_fin)s"
        params[ 'date_fin' ] = date_fin
    if personnel_filter != 'all':
        query_bloc += " AND p.id_personnel_anesthesie = %(personnel)s"
        params[ 'personnel' ] = personnel_filter

    query_accouchement = """
                         SELECT ad.date_accouchement         as date_intervention,
                                ad.patiente                  as patient,
                                ata.nom_acte,
                                CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                                ti.nom_type                  as type_intervenant,
                                NULL                         as duree_reelle,
                                aa.honoraires_calcules,
                                NULL                         as observations,
                                'ACCOUCHEMENT'               as source
                         FROM accouchement_dossier_anesthesie aa
                                  JOIN accouchement_dossiers ad ON aa.id_dossier = ad.id_dossier
                                  JOIN anesthesie_type_acte ata ON aa.id_acte_anesthesie = ata.id_acte_anesthesie
                                  JOIN anesthesie_personnel p ON aa.id_personnel_anesthesie = p.id_personnel_anesthesie
                                  JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
                         WHERE 1 = 1 \
                         """

    if date_debut:
        query_accouchement += " AND ad.date_accouchement >= %(date_debut)s"
    if date_fin:
        query_accouchement += " AND ad.date_accouchement <= %(date_fin)s"
    if personnel_filter != 'all':
        query_accouchement += " AND p.id_personnel_anesthesie = %(personnel)s"

    actes = [ ]
    if type_intervention in [ 'all', 'bloc' ]:
        cursor.execute( query_bloc, params )
        actes.extend( cursor.fetchall() )
    if type_intervention in [ 'all', 'accouchement' ]:
        cursor.execute( query_accouchement, params )
        actes.extend( cursor.fetchall() )

    actes.sort( key = lambda x: x[ 'date_intervention' ], reverse = True )

    # Créer le workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Honoraires Global"

    # Styles
    header_fill = PatternFill( start_color = "4F81BD", end_color = "4F81BD", fill_type = "solid" )
    header_font = Font( bold = True, color = "FFFFFF", size = 11 )
    border = Border(
            left = Side( style = 'thin' ),
            right = Side( style = 'thin' ),
            top = Side( style = 'thin' ),
            bottom = Side( style = 'thin' )
            )

    # En-têtes
    headers = [
            'Date', 'Patient', 'Acte', 'Intervenant', 'Type', 'Source', 'Durée (min)', 'Honoraires (DA)',
            'Observations'
            ]
    for col, header in enumerate( headers, 1 ):
        cell = ws.cell( row = 1, column = col, value = header )
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment( horizontal = 'center' )
        cell.border = border

    # Données
    for row_idx, acte in enumerate( actes, 2 ):
        ws.cell(
            row = row_idx, column = 1, value = acte[ 'date_intervention' ].strftime( '%d/%m/%Y' ) if acte[
                'date_intervention' ] else ''
            ).border = border
        ws.cell( row = row_idx, column = 2, value = acte[ 'patient' ] ).border = border
        ws.cell( row = row_idx, column = 3, value = acte[ 'nom_acte' ] ).border = border
        ws.cell( row = row_idx, column = 4, value = acte[ 'nom_personnel' ] ).border = border
        ws.cell( row = row_idx, column = 5, value = acte[ 'type_intervenant' ] ).border = border

        source_cell = ws.cell( row = row_idx, column = 6, value = acte[ 'source' ] )
        source_cell.border = border
        if acte[ 'source' ] == 'BLOC':
            source_cell.font = Font( color = "0070C0", bold = True )
        else:
            source_cell.font = Font( color = "C00000", bold = True )

        ws.cell( row = row_idx, column = 7, value = acte[ 'duree_reelle' ] or '-' ).border = border
        ws.cell( row = row_idx, column = 8, value = float( acte[ 'honoraires_calcules' ] ) ).border = border
        ws.cell( row = row_idx, column = 9, value = acte[ 'observations' ] or '' ).border = border

    # Ajuster largeurs
    ws.column_dimensions[ 'A' ].width = 12
    ws.column_dimensions[ 'B' ].width = 25
    ws.column_dimensions[ 'C' ].width = 30
    ws.column_dimensions[ 'D' ].width = 25
    ws.column_dimensions[ 'E' ].width = 20
    ws.column_dimensions[ 'F' ].width = 15
    ws.column_dimensions[ 'G' ].width = 12
    ws.column_dimensions[ 'H' ].width = 15
    ws.column_dimensions[ 'I' ].width = 30

    # Total
    total_row = len( actes ) + 2
    ws.cell( row = total_row, column = 7, value = "TOTAL:" ).font = Font( bold = True )
    total_cell = ws.cell(
        row = total_row, column = 8, value = sum( float( a[ 'honoraires_calcules' ] ) for a in actes )
        )
    total_cell.font = Font( bold = True, color = "C00000" )
    total_cell.border = border

    # Sauvegarder
    output = io.BytesIO()
    wb.save( output )
    output.seek( 0 )

    filename = f"honoraires_anesthesie_global_{date_debut or 'all'}_{date_fin or 'all'}.xlsx"

    return send_file(
            output,
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment = True,
            download_name = filename
            )
