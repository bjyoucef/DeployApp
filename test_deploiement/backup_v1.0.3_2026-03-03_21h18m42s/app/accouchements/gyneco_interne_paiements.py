# app/gyneco_interne_paiements.py
"""
Module de gestion des paiements et décharges pour gynécologues internes
"""
from datetime import datetime
from decimal import Decimal
from typing import Tuple

from flask import redirect, url_for, g, flash, render_template, request, jsonify, make_response

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


# ==============================================================================
# HELPERS
# ==============================================================================

def to_decimal( value, default = 0 ) -> Decimal:
    """Convertit une valeur en Decimal de manière sécurisée"""
    if value is None or value == '':
        return Decimal( str( default ) )
    try:
        return Decimal( str( value ) )
    except (Exception,):
        return Decimal( str( default ) )


def generer_numero_decharge() -> str:
    """Génère un numéro unique de décharge"""
    now = datetime.now()
    prefix = f"DGI-{now.year}{now.month:02d}"

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM gyneco_interne_decharges
                WHERE numero_decharge LIKE %s
                """, (f"{prefix}%",)
                )
        count = cursor.fetchone()[ 'count' ]
        return f"{prefix}-{count + 1:04d}"
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# LISTE DES DOSSIERS NON PAYÉS
# ==============================================================================

@app.route( '/gyneco-interne/paiements' )
@login_required
@handle_errors()

def gyneco_interne_paiements_list():
    """Liste des dossiers non payés par gynéco interne"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres
        id_gyneco = request.args.get( 'id_gyneco', 'all' )
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        # Liste des gynécos internes
        cursor.execute(
                """
                SELECT d.id,
                       CONCAT(d.first_name, ' ', d.last_name) as nom_complet
                FROM doctors d
                         JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.est_interne = 1
                  AND s.name_specialty LIKE '%gyn%'
                ORDER BY d.last_name, d.first_name
                """
                )
        gynecos = cursor.fetchall()

        # Construction de la requête
        where_clauses = [
            "est_gyneco_interne = 1",
            "gyneco_paye = 0",
            "id_decharge_gyneco IS NULL",  # ✅ AJOUT: Exclure les dossiers déjà dans une décharge
            "(est_annule IS NULL OR est_annule = 0)"  # ✅ AJOUT: Exclure les dossiers annulés
        ]
        params = { }

        if id_gyneco != 'all':
            where_clauses.append( "id_gyneco = %(id_gyneco)s" )
            params[ 'id_gyneco' ] = id_gyneco

        if date_debut:
            where_clauses.append( "date_accouchement >= %(date_debut)s" )
            params[ 'date_debut' ] = date_debut

        if date_fin:
            where_clauses.append( "date_accouchement <= %(date_fin)s" )
            params[ 'date_fin' ] = date_fin

        where_sql = " AND ".join( where_clauses )

        # Dossiers non payés groupés par gynéco
        cursor.execute(
                f"""
            SELECT 
                d.id_gyneco,
                CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name,
                COUNT(d.id_dossier) as nb_dossiers,
                COALESCE(SUM(d.part_gyneco), 0) as total_honoraires,
                MIN(d.date_accouchement) as date_min,
                MAX(d.date_accouchement) as date_max
            FROM accouchement_dossiers d
            JOIN doctors doc ON d.id_gyneco = doc.id
            WHERE {where_sql}
            GROUP BY d.id_gyneco
            ORDER BY gyneco_name
            """, params
                )
        gynecos_stats = cursor.fetchall()

        # Détail des dossiers si un gynéco est sélectionné
        dossiers = [ ]
        if id_gyneco != 'all':
            cursor.execute(
                    f"""
                SELECT 
                    d.id_dossier,
                    d.patiente,
                    d.date_accouchement,
                    d.type_accouchement,
                    d.type_tarification,
                    d.part_gyneco,
                    d.prix_total
                FROM accouchement_dossiers d
                WHERE {where_sql}
                ORDER BY d.date_accouchement DESC
                """, params
                    )
            dossiers = cursor.fetchall()

        return render_template(
                'accouchement/paiements_interne/liste_impayés.html',
                gynecos = gynecos,
                gynecos_stats = gynecos_stats,
                dossiers = dossiers,
                id_gyneco_selected = id_gyneco,
                date_debut = date_debut,
                date_fin = date_fin,
                title = "Paiements Gynécos Internes"
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# CRÉER UNE DÉCHARGE
# ==============================================================================

@app.route( '/gyneco-interne/decharge/creer', methods = [ 'GET', 'POST' ] )
@login_required
@handle_errors()

def gyneco_interne_decharge_create():
    """Création d'une décharge de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if request.method == 'GET':
            id_gyneco = request.args.get( 'id_gyneco' )
            date_debut = request.args.get( 'date_debut', '' )
            date_fin = request.args.get( 'date_fin', '' )

            if not id_gyneco:
                flash( 'Gynécologue non spécifié', 'danger' )
                return redirect( url_for( 'gyneco_interne_paiements_list' ) )

            # Info gynéco
            cursor.execute(
                    """
                    SELECT id, CONCAT(first_name, ' ', last_name) as nom_complet
                    FROM doctors
                    WHERE id = %s
                      AND est_interne = 1
                    """, (id_gyneco,)
                    )
            gyneco = cursor.fetchone()

            if not gyneco:
                flash( 'Gynécologue non trouvé', 'danger' )
                return redirect( url_for( 'gyneco_interne_paiements_list' ) )

            # Dossiers non payés ET non dans une décharge
            where_clauses = [
                    "id_gyneco = %(id_gyneco)s",
                    "est_gyneco_interne = 1",
                "gyneco_paye = 0",
                "id_decharge_gyneco IS NULL",  # ✅ AJOUT
                "(est_annule IS NULL OR est_annule = 0)"  # ✅ AJOUT: Exclure les dossiers annulés
                    ]
            params = { 'id_gyneco': id_gyneco }

            if date_debut:
                where_clauses.append( "date_accouchement >= %(date_debut)s" )
                params[ 'date_debut' ] = date_debut

            if date_fin:
                where_clauses.append( "date_accouchement <= %(date_fin)s" )
                params[ 'date_fin' ] = date_fin

            where_sql = " AND ".join( where_clauses )

            cursor.execute(
                    f"""
                SELECT 
                    id_dossier,
                    patiente,
                    date_accouchement,
                    type_accouchement,
                    type_tarification,
                    part_gyneco,
                    prix_total
                FROM accouchement_dossiers
                WHERE {where_sql}
                ORDER BY date_accouchement
                """, params
                    )
            dossiers = cursor.fetchall()

            return render_template(
                    'accouchement/paiements_interne/creer_decharge.html',
                    gyneco = gyneco,
                    dossiers = dossiers,
                    date_debut = date_debut,
                    date_fin = date_fin,
                    title = "Nouvelle Décharge"
                    )

        # POST - Création de la décharge
        id_gyneco = request.form.get( 'id_gyneco' )
        date_decharge = request.form.get( 'date_decharge' )
        periode_debut = request.form.get( 'periode_debut' )
        periode_fin = request.form.get( 'periode_fin' )
        mode_paiement = request.form.get( 'mode_paiement', 'ESPECES' )
        reference_paiement = request.form.get( 'reference_paiement', '' ).strip()
        observations = request.form.get( 'observations', '' ).strip()
        dossiers_ids = request.form.getlist( 'dossiers[]' )

        if not dossiers_ids:
            flash( 'Veuillez sélectionner au moins un dossier', 'danger' )
            return redirect( request.referrer )

        # ✅ VÉRIFICATION: S'assurer qu'aucun dossier n'est déjà dans une décharge active
        placeholders = ','.join( [ '%s' ] * len( dossiers_ids ) )
        cursor.execute(f"""
            SELECT id_dossier, numero_decharge
            FROM accouchement_dossiers d
            LEFT JOIN gyneco_interne_decharges dech ON d.id_decharge_gyneco = dech.id_decharge
            WHERE d.id_dossier IN ({placeholders})
              AND d.id_decharge_gyneco IS NOT NULL
              AND dech.statut NOT IN ('ANNULE')
        """, dossiers_ids)

        dossiers_deja_decharges = cursor.fetchall()

        if dossiers_deja_decharges:
            dossiers_list = ', '.join([
                f"#{d['id_dossier']} (décharge {d['numero_decharge']})"
                for d in dossiers_deja_decharges
            ])
            flash(
                f'❌ Les dossiers suivants sont déjà dans une décharge active: {dossiers_list}',
                'danger'
            )
            return redirect(request.referrer)

        # Récupérer les dossiers valides
        cursor.execute(f"""
            SELECT 
                id_dossier,
                part_gyneco
            FROM accouchement_dossiers
            WHERE id_dossier IN ({placeholders})
              AND id_gyneco = %s
              AND est_gyneco_interne = 1
              AND gyneco_paye = 0
              AND id_decharge_gyneco IS NULL
              AND (est_annule IS NULL OR est_annule = 0)
            """, (*dossiers_ids, id_gyneco)
                )
        dossiers = cursor.fetchall()

        if not dossiers:
            flash( 'Aucun dossier valide sélectionné', 'danger' )
            return redirect( request.referrer )

        # Si le nombre de dossiers récupérés est différent, informer l'utilisateur
        if len(dossiers) < len(dossiers_ids):
            flash(
                f'⚠️ Attention: {len(dossiers_ids) - len(dossiers)} dossier(s) '
                'ignoré(s) car déjà dans une décharge ou déjà payé(s)',
                'warning'
            )

        montant_total = sum( to_decimal( d[ 'part_gyneco' ] ) for d in dossiers )
        nb_dossiers = len( dossiers )

        # Générer numéro
        numero_decharge = generer_numero_decharge()

        # Créer la décharge
        cursor.execute(
                """
                INSERT INTO gyneco_interne_decharges
                (numero_decharge, id_gyneco, date_decharge, periode_debut, periode_fin,
                 montant_total, nb_dossiers, mode_paiement, reference_paiement,
                 observations, statut, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'BROUILLON', %s)
                """, (
                        numero_decharge, id_gyneco, date_decharge, periode_debut, periode_fin,
                        montant_total, nb_dossiers, mode_paiement, reference_paiement,
                        observations, g.user[ 'id_personnel' ]
                        )
                )

        id_decharge = cursor.lastrowid

        # Lier les dossiers
        for dossier in dossiers:
            cursor.execute(
                    """
                    INSERT INTO gyneco_interne_decharge_dossiers
                        (id_decharge, id_dossier, montant_honoraires)
                    VALUES (%s, %s, %s)
                    """, (id_decharge, dossier[ 'id_dossier' ], dossier[ 'part_gyneco' ])
                    )
        # ✅ IMPORTANT: Marquer immédiatement les dossiers avec l'id_decharge
        dossiers_ids_valides = [d['id_dossier'] for d in dossiers]
        placeholders = ','.join(['%s'] * len(dossiers_ids_valides))
        cursor.execute(f"""
            UPDATE accouchement_dossiers
            SET id_decharge_gyneco = %s
            WHERE id_dossier IN ({placeholders})
        """, (id_decharge, *dossiers_ids_valides))

        conn.commit()

        flash(f'✅ Décharge {numero_decharge} créée avec succès ({nb_dossiers} dossiers)', 'success')
        return redirect( url_for( 'gyneco_interne_decharge_detail', id_decharge = id_decharge ) )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur création décharge: {e}' )
        flash( f'❌ Erreur: {str( e )}', 'danger' )
        return redirect( url_for( 'gyneco_interne_paiements_list' ) )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# DÉTAIL D'UNE DÉCHARGE
# ==============================================================================

@app.route( '/gyneco-interne/decharge/<int:id_decharge>' )
@login_required
@handle_errors()

def gyneco_interne_decharge_detail( id_decharge ):
    """Détail d'une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Info décharge
        cursor.execute(
                """
                SELECT dech.*,
                       CONCAT(doc.first_name, ' ', doc.last_name)       as gyneco_name,
                       CONCAT(p_created.nom, ' ', p_created.prenom)     as created_by_name,
                       CONCAT(p_validated.nom, ' ', p_validated.prenom) as validated_by_name,
                       CONCAT(p_paid.nom, ' ', p_paid.prenom)           as paid_by_name
                FROM gyneco_interne_decharges dech
                         JOIN doctors doc ON dech.id_gyneco = doc.id
                         LEFT JOIN personnel p_created ON dech.created_by = p_created.id_personnel
                         LEFT JOIN personnel p_validated ON dech.validated_by = p_validated.id_personnel
                         LEFT JOIN personnel p_paid ON dech.paid_by = p_paid.id_personnel
                WHERE dech.id_decharge = %s
                """, (id_decharge,)
                )
        decharge = cursor.fetchone()

        if not decharge:
            flash( 'Décharge non trouvée', 'danger' )
            return redirect( url_for( 'gyneco_interne_decharges_list' ) )

        # Dossiers liés
        cursor.execute(
                """
                SELECT dd.montant_honoraires,
                       d.id_dossier,
                       d.patiente,
                       d.date_accouchement,
                       d.type_accouchement,
                       d.type_tarification
                FROM gyneco_interne_decharge_dossiers dd
                         JOIN accouchement_dossiers d ON dd.id_dossier = d.id_dossier
                WHERE dd.id_decharge = %s
                ORDER BY d.date_accouchement
                """, (id_decharge,)
                )
        dossiers = cursor.fetchall()

        return render_template(
                'accouchement/paiements_interne/detail_decharge.html',
                decharge = decharge,
                dossiers = dossiers,
                title = f"Décharge {decharge[ 'numero_decharge' ]}"
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# LISTE DES DÉCHARGES
# ==============================================================================

@app.route( '/gyneco-interne/decharges' )
@login_required
@handle_errors()

def gyneco_interne_decharges_list():
    """Liste de toutes les décharges"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres
        id_gyneco = request.args.get( 'id_gyneco', 'all' )
        statut = request.args.get( 'statut', 'all' )
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )

        # Gynécos
        cursor.execute(
                """
                SELECT d.id, CONCAT(d.first_name, ' ', d.last_name) as nom_complet
                FROM doctors d
                         JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.est_interne = 1
                  AND s.name_specialty LIKE '%gyn%'
                ORDER BY d.last_name
                """
                )
        gynecos = cursor.fetchall()

        # Construction requête
        where_clauses = [ "1=1" ]
        params = { }

        if id_gyneco != 'all':
            where_clauses.append( "dech.id_gyneco = %(id_gyneco)s" )
            params[ 'id_gyneco' ] = id_gyneco

        if statut != 'all':
            where_clauses.append( "dech.statut = %(statut)s" )
            params[ 'statut' ] = statut

        if date_debut:
            where_clauses.append( "dech.date_decharge >= %(date_debut)s" )
            params[ 'date_debut' ] = date_debut

        if date_fin:
            where_clauses.append( "dech.date_decharge <= %(date_fin)s" )
            params[ 'date_fin' ] = date_fin

        where_sql = " AND ".join( where_clauses )

        # Liste des décharges
        cursor.execute(
                f"""
            SELECT 
                dech.*,
                CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name
            FROM gyneco_interne_decharges dech
            JOIN doctors doc ON dech.id_gyneco = doc.id
            WHERE {where_sql}
            ORDER BY dech.date_decharge DESC, dech.id_decharge DESC
            """, params
                )
        decharges = cursor.fetchall()

        # Stats
        cursor.execute(
                f"""
            SELECT 
                COUNT(*) as total_decharges,
                COALESCE(SUM(montant_total), 0) as total_montant,
                COALESCE(SUM(CASE WHEN statut = 'PAYE' THEN montant_total ELSE 0 END), 0) as montant_paye
            FROM gyneco_interne_decharges dech
            WHERE {where_sql}
            """, params
                )
        stats = cursor.fetchone()

        return render_template(
                'accouchement/paiements_interne/liste_decharges.html',
                decharges = decharges,
                gynecos = gynecos,
                stats = stats,
                id_gyneco_selected = id_gyneco,
                statut_selected = statut,
                date_debut = date_debut,
                date_fin = date_fin,
                title = "Décharges de Paiement"
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# VALIDER UNE DÉCHARGE
# ==============================================================================

@app.route( '/gyneco-interne/decharge/<int:id_decharge>/valider', methods = [ 'POST' ] )
@login_required
@handle_errors()

def gyneco_interne_decharge_valider( id_decharge ):
    """Valider une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                "SELECT statut FROM gyneco_interne_decharges WHERE id_decharge = %s",
                (id_decharge,)
                )
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify( { 'success': False, 'error': 'Décharge non trouvée' } ), 404

        if decharge[ 'statut' ] != 'BROUILLON':
            return jsonify(
                    { 'success': False, 'error': 'Seules les décharges en brouillon peuvent être validées' }
                    ), 400

        cursor.execute(
                """
                UPDATE gyneco_interne_decharges
                SET statut       = 'VALIDE',
                    validated_at = NOW(),
                    validated_by = %s
                WHERE id_decharge = %s
                """, (g.user[ 'id_personnel' ], id_decharge)
                )

        conn.commit()

        return jsonify(
                {
                        'success': True,
                        'message': 'Décharge validée avec succès'
                        }
                )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur validation décharge: {e}' )
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# MARQUER COMME PAYÉ
# ==============================================================================

@app.route( '/gyneco-interne/decharge/<int:id_decharge>/payer', methods = [ 'POST' ] )
@login_required
@handle_errors()

def gyneco_interne_decharge_payer( id_decharge ):
    """Marquer une décharge comme payée"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                "SELECT statut FROM gyneco_interne_decharges WHERE id_decharge = %s",
                (id_decharge,)
                )
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify( { 'success': False, 'error': 'Décharge non trouvée' } ), 404

        if decharge[ 'statut' ] not in [ 'VALIDE', 'BROUILLON' ]:
            return jsonify( { 'success': False, 'error': 'La décharge doit être validée' } ), 400

        # Marquer la décharge comme payée
        cursor.execute(
                """
                UPDATE gyneco_interne_decharges
                SET statut  = 'PAYE',
                    paid_at = NOW(),
                    paid_by = %s
                WHERE id_decharge = %s
                """, (g.user[ 'id_personnel' ], id_decharge)
                )

        # Marquer les dossiers comme payés
        cursor.execute(
                """
                UPDATE accouchement_dossiers d
                    JOIN gyneco_interne_decharge_dossiers dd ON d.id_dossier = dd.id_dossier
                SET d.gyneco_paye        = 1,
                    d.id_decharge_gyneco = %s
                WHERE dd.id_decharge = %s
                """, (id_decharge, id_decharge)
                )

        conn.commit()

        return jsonify(
                {
                        'success': True,
                        'message': 'Paiement enregistré avec succès'
                        }
                )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur enregistrement paiement: {e}' )
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# GESTION DES TRANCHES DE PAIEMENT
# ==============================================================================

def calculer_solde_decharge( cursor, id_decharge: int ) -> Tuple[ Decimal, Decimal, int ]:
    """
    Calcule le solde d'une décharge
    Returns: (montant_total, montant_paye_total, nb_tranches)
    """
    cursor.execute(
            "SELECT montant_total FROM gyneco_interne_decharges WHERE id_decharge = %s",
            (id_decharge,)
            )
    result = cursor.fetchone()
    if not result:
        return Decimal( '0' ), Decimal( '0' ), 0

    montant_total = to_decimal( result[ 'montant_total' ] )

    # Calculer le total payé via les tranches
    cursor.execute(
            """
            SELECT COALESCE(SUM(montant_paye), 0) as total_paye,
                   COUNT(*)                       as nb_tranches
            FROM gyneco_interne_decharge_tranches
            WHERE id_decharge = %s
            """, (id_decharge,)
            )
    result = cursor.fetchone()
    montant_paye_total = to_decimal( result[ 'total_paye' ] )
    nb_tranches = int( result[ 'nb_tranches' ] )

    return montant_total, montant_paye_total, nb_tranches


def mettre_a_jour_statut_decharge( cursor, id_decharge: int ):
    """Met à jour le statut de la décharge selon le solde"""
    montant_total, montant_paye_total, nb_tranches = calculer_solde_decharge( cursor, id_decharge )
    solde_restant = montant_total - montant_paye_total

    # Déterminer le statut
    if solde_restant <= Decimal( '0.01' ):  # Totalement payé
        nouveau_statut = 'PAYE'
        # Marquer les dossiers comme payés
        cursor.execute(
                """
                UPDATE accouchement_dossiers d
                    JOIN gyneco_interne_decharge_dossiers dd ON d.id_dossier = dd.id_dossier
                SET d.gyneco_paye        = 1,
                    d.id_decharge_gyneco = %s
                WHERE dd.id_decharge = %s
                """, (id_decharge, id_decharge)
                )
        paid_at = 'NOW()'
        paid_by = g.user[ 'id_personnel' ]
    elif montant_paye_total > 0:  # Paiement partiel
        nouveau_statut = 'PAIEMENT_PARTIEL'
        paid_at = 'NULL'
        paid_by = 'NULL'
    else:  # Pas encore de paiement
        # Ne pas changer le statut si c'est BROUILLON ou VALIDE
        cursor.execute(
                """
                UPDATE gyneco_interne_decharges
                SET montant_paye_total = %s,
                    solde_restant      = %s,
                    nb_tranches        = %s
                WHERE id_decharge = %s
                """, (montant_paye_total, solde_restant, nb_tranches, id_decharge)
                )
        return

    # Mettre à jour la décharge
    cursor.execute(
            f"""
        UPDATE gyneco_interne_decharges
        SET statut = %s,
            montant_paye_total = %s,
            solde_restant = %s,
            nb_tranches = %s,
            paid_at = {paid_at},
            paid_by = {'%s' if paid_by != 'NULL' else 'NULL'}
        WHERE id_decharge = %s
        """,
            (
                    nouveau_statut, montant_paye_total, solde_restant, nb_tranches,
                    paid_by if paid_by != 'NULL' else None, id_decharge
                    ) if paid_by != 'NULL'
            else (nouveau_statut, montant_paye_total, solde_restant, nb_tranches, id_decharge)
            )


def generer_numero_tranche( cursor, id_decharge: int ) -> str:
    """Génère un numéro unique de tranche"""
    cursor.execute(
            "SELECT numero_decharge FROM gyneco_interne_decharges WHERE id_decharge = %s",
            (id_decharge,)
            )
    result = cursor.fetchone()
    if not result:
        return ""

    numero_decharge = result[ 'numero_decharge' ]

    cursor.execute(
            "SELECT COUNT(*) as count FROM gyneco_interne_decharge_tranches WHERE id_decharge = %s",
            (id_decharge,)
            )
    count = cursor.fetchone()[ 'count' ]

    return f"{numero_decharge}-T{count + 1:02d}"


@app.route( '/gyneco-interne/decharge/<int:id_decharge>/ajouter-tranche', methods = [ 'POST' ] )
@login_required
@handle_errors()

def gyneco_interne_decharge_ajouter_tranche( id_decharge ):
    """Ajouter une tranche de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Vérifier la décharge
        cursor.execute(
                """
                SELECT statut, montant_total, montant_paye_total, solde_restant
                FROM gyneco_interne_decharges
                WHERE id_decharge = %s
                """, (id_decharge,)
                )
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify( { 'success': False, 'error': 'Décharge non trouvée' } ), 404

        if decharge[ 'statut' ] in [ 'ANNULE', 'PAYE' ]:
            return jsonify(
                    {
                            'success': False,
                            'error': 'Impossible d\'ajouter une tranche à une décharge annulée ou déjà payée'
                            }
                    ), 400

        # Récupérer les données
        data = request.get_json()
        date_paiement = data.get( 'date_paiement' )
        montant_paye = to_decimal( data.get( 'montant_paye', 0 ) )
        mode_paiement = data.get( 'mode_paiement', 'ESPECES' )
        reference_paiement = data.get( 'reference_paiement', '' ).strip()
        observations = data.get( 'observations', '' ).strip()

        if montant_paye <= 0:
            return jsonify( { 'success': False, 'error': 'Le montant doit être supérieur à 0' } ), 400

        # Vérifier qu'on ne dépasse pas le solde
        solde_actuel = to_decimal( decharge[ 'montant_total' ] ) - to_decimal( decharge[ 'montant_paye_total' ] or 0 )
        if montant_paye > solde_actuel + Decimal( '0.01' ):
            return jsonify(
                    {
                            'success': False,
                            'error': f'Le montant dépasse le solde restant ({float( solde_actuel ):.2f} DA)'
                            }
                    ), 400

        # Générer numéro de tranche
        numero_tranche = generer_numero_tranche( cursor, id_decharge )

        # Insérer la tranche
        cursor.execute(
                """
                INSERT INTO gyneco_interne_decharge_tranches
                (id_decharge, numero_tranche, date_paiement, montant_paye,
                 mode_paiement, reference_paiement, observations, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                        id_decharge, numero_tranche, date_paiement, montant_paye,
                        mode_paiement, reference_paiement, observations, g.user[ 'id_personnel' ]
                        )
                )

        # Mettre à jour le statut de la décharge
        mettre_a_jour_statut_decharge( cursor, id_decharge )

        conn.commit()

        # Récupérer les nouvelles valeurs
        montant_total, montant_paye_total, nb_tranches = calculer_solde_decharge( cursor, id_decharge )
        solde_restant = montant_total - montant_paye_total

        return jsonify(
                {
                        'success': True,
                        'message': f'Tranche de {float( montant_paye ):.2f} DA enregistrée',
                        'montant_paye_total': float( montant_paye_total ),
                        'solde_restant': float( solde_restant ),
                        'nb_tranches': nb_tranches
                        }
                )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur ajout tranche: {e}' )
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        cursor.close()
        conn.close()


@app.route( '/gyneco-interne/decharge/<int:id_decharge>/tranches' )
@login_required
@handle_errors()

def gyneco_interne_decharge_tranches( id_decharge ):
    """Liste des tranches d'une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                """
                SELECT t.*,
                       CONCAT(p.nom, ' ', p.prenom) as created_by_name
                FROM gyneco_interne_decharge_tranches t
                         LEFT JOIN personnel p ON t.created_by = p.id_personnel
                WHERE t.id_decharge = %s
                ORDER BY t.date_paiement, t.created_at
                """, (id_decharge,)
                )
        tranches = cursor.fetchall()

        return jsonify(
                {
                        'success': True,
                        'tranches': [ dict( t ) for t in tranches ]
                        }
                )

    finally:
        cursor.close()
        conn.close()


@app.route( '/gyneco-interne/decharge/tranche/<int:id_tranche>/supprimer', methods = [ 'POST' ] )
@login_required
@handle_errors()

def gyneco_interne_tranche_supprimer( id_tranche ):
    """Supprimer une tranche de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Récupérer l'id_decharge
        cursor.execute(
                "SELECT id_decharge FROM gyneco_interne_decharge_tranches WHERE id_tranche = %s",
                (id_tranche,)
                )
        result = cursor.fetchone()

        if not result:
            return jsonify( { 'success': False, 'error': 'Tranche non trouvée' } ), 404

        id_decharge = result[ 'id_decharge' ]

        # Vérifier le statut de la décharge
        cursor.execute(
                "SELECT statut FROM gyneco_interne_decharges WHERE id_decharge = %s",
                (id_decharge,)
                )
        decharge = cursor.fetchone()

        if decharge[ 'statut' ] == 'PAYE':
            return jsonify(
                    {
                            'success': False,
                            'error': 'Impossible de supprimer une tranche d\'une décharge totalement payée'
                            }
                    ), 400

        # Supprimer la tranche
        cursor.execute(
                "DELETE FROM gyneco_interne_decharge_tranches WHERE id_tranche = %s",
                (id_tranche,)
                )

        # Mettre à jour le statut
        mettre_a_jour_statut_decharge( cursor, id_decharge )

        conn.commit()

        return jsonify(
                {
                        'success': True,
                        'message': 'Tranche supprimée avec succès'
                        }
                )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur suppression tranche: {e}' )
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# MARQUER COMME PAYÉ (VERSION SIMPLIFIÉE - PAIEMENT TOTAL)
# ==============================================================================

@app.route( '/gyneco-interne/decharge/<int:id_decharge>/payer-total', methods = [ 'POST' ] )
@login_required
@handle_errors()

def gyneco_interne_decharge_payer_total( id_decharge ):
    """Payer le solde total en une fois"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                """
                SELECT statut, montant_total, montant_paye_total, solde_restant
                FROM gyneco_interne_decharges
                WHERE id_decharge = %s
                """, (id_decharge,)
                )
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify( { 'success': False, 'error': 'Décharge non trouvée' } ), 404

        if decharge[ 'statut' ] == 'PAYE':
            return jsonify( { 'success': False, 'error': 'Décharge déjà payée' } ), 400

        # Récupérer les données
        data = request.get_json()
        mode_paiement = data.get( 'mode_paiement', 'ESPECES' )
        reference_paiement = data.get( 'reference_paiement', '' ).strip()
        observations = data.get( 'observations', '' ).strip()

        # Calculer le solde restant
        solde = to_decimal( decharge[ 'montant_total' ] ) - to_decimal( decharge[ 'montant_paye_total' ] or 0 )

        if solde <= 0:
            return jsonify( { 'success': False, 'error': 'Aucun solde à payer' } ), 400

        # Générer numéro de tranche
        numero_tranche = generer_numero_tranche( cursor, id_decharge )

        # Ajouter une tranche pour le solde total
        cursor.execute(
                """
                INSERT INTO gyneco_interne_decharge_tranches
                (id_decharge, numero_tranche, date_paiement, montant_paye,
                 mode_paiement, reference_paiement, observations, created_by)
                VALUES (%s, %s, CURDATE(), %s, %s, %s, %s, %s)
                """, (
                        id_decharge, numero_tranche, solde,
                        mode_paiement, reference_paiement,
                        f"Paiement du solde total. {observations}".strip(),
                        g.user[ 'id_personnel' ]
                        )
                )

        # Mettre à jour le statut
        mettre_a_jour_statut_decharge( cursor, id_decharge )

        conn.commit()

        return jsonify(
                {
                        'success': True,
                        'message': f'Paiement total de {float( solde ):.2f} DA enregistré'
                        }
                )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur paiement total: {e}' )
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        cursor.close()
        conn.close()

# ==============================================================================
# GÉNÉRER PDF
# ==============================================================================

@app.route( '/gyneco-interne/decharge/<int:id_decharge>/pdf' )
@login_required
@handle_errors()

def gyneco_interne_decharge_pdf( id_decharge ):
    """Générer le PDF de la décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Info décharge
        cursor.execute(
                """
                SELECT dech.*,
                       CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name
                FROM gyneco_interne_decharges dech
                         JOIN doctors doc ON dech.id_gyneco = doc.id
                WHERE dech.id_decharge = %s
                """, (id_decharge,)
                )
        decharge = cursor.fetchone()

        if not decharge:
            flash( 'Décharge non trouvée', 'danger' )
            return redirect( url_for( 'gyneco_interne_decharges_list' ) )

        # Dossiers
        cursor.execute(
                """
                SELECT dd.montant_honoraires,
                       d.id_dossier,
                       d.patiente,
                       d.date_accouchement,
                       d.type_accouchement,
                       d.type_tarification
                FROM gyneco_interne_decharge_dossiers dd
                         JOIN accouchement_dossiers d ON dd.id_dossier = d.id_dossier
                WHERE dd.id_decharge = %s
                ORDER BY d.date_accouchement
                """, (id_decharge,)
                )
        dossiers = cursor.fetchall()

        html = render_template(
                'accouchement/paiements_interne/decharge_pdf.html',
                decharge = decharge,
                dossiers = dossiers,
                date_generation = datetime.now().strftime( '%d/%m/%Y %H:%M' )
                )

        response = make_response( html )
        response.headers[ 'Content-Type' ] = 'text/html'

        # Si weasyprint est installé:
        # from weasyprint import HTML
        # pdf = HTML(string=html).write_pdf()
        # response = make_response(pdf)
        # response.headers['Content-Type'] = 'application/pdf'
        # response.headers['Content-Disposition'] = f'attachment; filename=decharge_{decharge["numero_decharge"]}.pdf'
        return response

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# ANNULER UNE DÉCHARGE
# ==============================================================================

@app.route( '/gyneco-interne/decharge/<int:id_decharge>/annuler', methods = [ 'POST' ] )
@login_required
@handle_errors()

def gyneco_interne_decharge_annuler( id_decharge ):
    """Annuler une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                "SELECT statut FROM gyneco_interne_decharges WHERE id_decharge = %s",
                (id_decharge,)
                )
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify( { 'success': False, 'error': 'Décharge non trouvée' } ), 404

        if decharge[ 'statut' ] == 'PAYE':
            return jsonify( { 'success': False, 'error': 'Impossible d\'annuler une décharge payée' } ), 400

        # Annuler la décharge
        cursor.execute(
                """
                UPDATE gyneco_interne_decharges
            SET statut = 'ANNULE',
                cancelled_at = NOW(),
                cancelled_by = %s
                WHERE id_decharge = %s
        """, (g.user['id_personnel'], id_decharge))

        # ✅ Libérer les dossiers (remettre à zéro gyneco_paye ET id_decharge_gyneco)
        cursor.execute(
                """
                UPDATE accouchement_dossiers d
                    JOIN gyneco_interne_decharge_dossiers dd ON d.id_dossier = dd.id_dossier
                SET d.gyneco_paye        = 0,
                    d.id_decharge_gyneco = NULL
                WHERE dd.id_decharge = %s
                """, (id_decharge,)
                )

        conn.commit()

        return jsonify(
                {
                        'success': True,
            'message': 'Décharge annulée avec succès. Les dossiers sont à nouveau disponibles.'
        })

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur annulation décharge: {e}' )
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        cursor.close()
        conn.close()

# Ajouter cette route dans gyneco_interne_paiements.py

# ==============================================================================
# API - VÉRIFICATION DES DOSSIERS DISPONIBLES
# ==============================================================================

@app.route('/api/gyneco-interne/verifier-dossiers-disponibles', methods=['POST'])
@login_required
def api_verifier_dossiers_disponibles():
    """
    Vérifie quels dossiers sont déjà dans une décharge active
    Retourne la liste des IDs de dossiers indisponibles
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        data = request.get_json()
        dossier_ids = data.get('dossier_ids', [])

        if not dossier_ids:
            return jsonify({
                'success': True,
                'dossiers_indisponibles': [],
                'details': []
            })

        # Vérifier quels dossiers sont déjà dans une décharge
        placeholders = ','.join(['%s'] * len(dossier_ids))
        cursor.execute(f"""
            SELECT 
                d.id_dossier,
                d.id_decharge_gyneco,
                dech.numero_decharge,
                dech.statut,
                dech.date_decharge,
                CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name
            FROM accouchement_dossiers d
            LEFT JOIN gyneco_interne_decharges dech ON d.id_decharge_gyneco = dech.id_decharge
            LEFT JOIN doctors doc ON d.id_gyneco = doc.id
            WHERE d.id_dossier IN ({placeholders})
              AND d.id_decharge_gyneco IS NOT NULL
              AND dech.statut NOT IN ('ANNULE')
        """, dossier_ids)

        dossiers_indisponibles = cursor.fetchall()

        return jsonify({
            'success': True,
            'dossiers_indisponibles': [d['id_dossier'] for d in dossiers_indisponibles],
            'details': [
                {
                    'id_dossier': d['id_dossier'],
                    'numero_decharge': d['numero_decharge'],
                    'statut': d['statut'],
                    'date_decharge': d['date_decharge'].strftime('%d/%m/%Y') if d['date_decharge'] else None,
                    'gyneco': d['gyneco_name']
                }
                for d in dossiers_indisponibles
            ]
        })

    except Exception as e:
        app.logger.error(f'Erreur vérification dossiers: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# API - STATISTIQUES DES DÉCHARGES PAR GYNÉCO
# ==============================================================================

@app.route('/api/gyneco-interne/stats-decharges/<int:id_gyneco>')
@login_required
def api_stats_decharges_gyneco(id_gyneco):
    """
    Retourne les statistiques de décharges pour un gynécologue
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get('date_debut', '')
        date_fin = request.args.get('date_fin', '')

        where_clauses = ['id_gyneco = %s']
        params = [id_gyneco]

        if date_debut:
            where_clauses.append('periode_debut >= %s')
            params.append(date_debut)

        if date_fin:
            where_clauses.append('periode_fin <= %s')
            params.append(date_fin)

        where_sql = ' AND '.join(where_clauses)

        # Stats globales
        cursor.execute(f"""
            SELECT 
                COUNT(*) as nb_decharges,
                COALESCE(SUM(montant_total), 0) as montant_total,
                COALESCE(SUM(montant_paye_total), 0) as montant_paye,
                COALESCE(SUM(solde_restant), 0) as solde_restant,
                SUM(nb_dossiers) as total_dossiers,
                SUM(CASE WHEN statut = 'BROUILLON' THEN 1 ELSE 0 END) as nb_brouillon,
                SUM(CASE WHEN statut = 'VALIDE' THEN 1 ELSE 0 END) as nb_valide,
                SUM(CASE WHEN statut = 'PAIEMENT_PARTIEL' THEN 1 ELSE 0 END) as nb_partiel,
                SUM(CASE WHEN statut = 'PAYE' THEN 1 ELSE 0 END) as nb_paye,
                SUM(CASE WHEN statut = 'ANNULE' THEN 1 ELSE 0 END) as nb_annule
            FROM gyneco_interne_decharges
            WHERE {where_sql}
        """, params)

        stats = cursor.fetchone()

        # Dossiers disponibles pour nouvelle décharge
        cursor.execute("""
            SELECT COUNT(*) as nb_disponibles,
                   COALESCE(SUM(part_gyneco), 0) as montant_disponible
            FROM accouchement_dossiers
            WHERE id_gyneco = %s
              AND est_gyneco_interne = 1
              AND gyneco_paye = 0
              AND id_decharge_gyneco IS NULL
        """, (id_gyneco,))

        disponibles = cursor.fetchone()

        return jsonify({
            'success': True,
            'stats': {
                'decharges': {
                    'total': int(stats['nb_decharges'] or 0),
                    'brouillon': int(stats['nb_brouillon'] or 0),
                    'valide': int(stats['nb_valide'] or 0),
                    'paiement_partiel': int(stats['nb_partiel'] or 0),
                    'paye': int(stats['nb_paye'] or 0),
                    'annule': int(stats['nb_annule'] or 0)
                },
                'montants': {
                    'total': float(stats['montant_total'] or 0),
                    'paye': float(stats['montant_paye'] or 0),
                    'solde_restant': float(stats['solde_restant'] or 0),
                    'pourcentage_paye': round(
                        (float(stats['montant_paye'] or 0) / float(stats['montant_total'] or 1)) * 100,
                        2
                    )
                },
                'dossiers': {
                    'total_decharges': int(stats['total_dossiers'] or 0),
                    'disponibles': int(disponibles['nb_disponibles'] or 0),
                    'montant_disponible': float(disponibles['montant_disponible'] or 0)
                }
            }
        })

    except Exception as e:
        app.logger.error(f'Erreur stats décharges: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# API - HISTORIQUE DES DÉCHARGES D'UN DOSSIER
# ==============================================================================

@app.route('/api/gyneco-interne/dossier/<int:id_dossier>/historique-decharges')
@login_required
def api_dossier_historique_decharges(id_dossier):
    """
    Retourne l'historique des décharges d'un dossier
    (utile pour débogage ou audit)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Décharge actuelle
        cursor.execute("""
            SELECT 
                d.id_decharge_gyneco,
                d.gyneco_paye,
                dech.numero_decharge,
                dech.statut,
                dech.date_decharge,
                dech.montant_total,
                dd.montant_honoraires
            FROM accouchement_dossiers d
            LEFT JOIN gyneco_interne_decharges dech ON d.id_decharge_gyneco = dech.id_decharge
            LEFT JOIN gyneco_interne_decharge_dossiers dd ON d.id_dossier = dd.id_dossier 
                AND dd.id_decharge = dech.id_decharge
            WHERE d.id_dossier = %s
        """, (id_dossier,))

        decharge_actuelle = cursor.fetchone()

        # Historique (si le dossier a été dans plusieurs décharges)
        cursor.execute("""
            SELECT 
                dech.id_decharge,
                dech.numero_decharge,
                dech.statut,
                dech.date_decharge,
                dd.montant_honoraires,
                dech.created_at,
                CONCAT(p.nom, ' ', p.prenom) as created_by_name
            FROM gyneco_interne_decharge_dossiers dd
            JOIN gyneco_interne_decharges dech ON dd.id_decharge = dech.id_decharge
            LEFT JOIN personnel p ON dech.created_by = p.id_personnel
            WHERE dd.id_dossier = %s
            ORDER BY dech.created_at DESC
        """, (id_dossier,))

        historique = cursor.fetchall()

        return jsonify({
            'success': True,
            'decharge_actuelle': dict(decharge_actuelle) if decharge_actuelle else None,
            'historique': [dict(h) for h in historique]
        })

    except Exception as e:
        app.logger.error(f'Erreur historique décharges dossier: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        conn.close()