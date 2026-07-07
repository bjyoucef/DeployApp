# app/situation_accouchement_externe.py - Gestion des accouchements EXTERNES uniquement

from datetime import datetime, date
from decimal import Decimal

from flask import request, redirect, url_for, render_template, g, flash, jsonify

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


def to_decimal(value, default=0):
    """Convertit une valeur en Decimal de manière sécurisée"""
    if value is None or value == '':
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except:
        return Decimal(str(default))


def calculer_statut_paiement(reste):
    """
    Détermine le statut selon la balance

    ✅ Pour VIA_GYNECO :
    reste > 0  : Gynéco doit payer la clinique → GYNECO_DOIT_PAYER
    reste < 0  : Clinique doit payer le gynéco → CLINIQUE_DOIT_PAYER
    reste == 0 : Équilibré

    ✅ Pour DIRECT/DIFFERE :
    reste > 0  : Clinique a surplus → EQUILIBRE (ou SURPLUS_CLINIQUE)
    reste < 0  : Clinique doit payer le gynéco → CLINIQUE_DOIT_PAYER
    reste == 0 : Équilibré
    """
    if abs( reste ) < Decimal( '0.01' ):
        return 'EQUILIBRE'
    return 'GYNECO_DOIT_PAYER' if reste > 0 else 'CLINIQUE_DOIT_PAYER'


# ========================================================================
# FONCTIONS UTILITAIRES
# ========================================================================

def get_dossiers_accouchement_externe(cursor, id_gyneco, include_decharge_status=False, start_date=None, end_date=None):
    """
    Récupère les dossiers ACCOUCHEMENT d'un gynécologue EXTERNE
    """
    where_clause = "WHERE a.id_gyneco = %s AND a.est_gyneco_interne = 0"
    params = [id_gyneco]
    
    if start_date:
        where_clause += " AND a.date_accouchement >= %s"
        params.append(start_date)
    if end_date:
        where_clause += " AND a.date_accouchement <= %s"
        params.append(end_date)
    
    # ✅ Exclure les dossiers annulés
    where_clause += " AND (a.est_annule IS NULL OR a.est_annule = 0)"   
        
    cursor.execute(
        f"""
        SELECT a.id_dossier,
               a.patiente as patient,
               a.date_accouchement,
               a.part_gyneco,
               a.part_clinique,
               a.prix_total as prix_total_dossier,
               a.montant_paye,
               a.balance_medecin,
               a.type_accouchement,
               a.type_tarification,
               IFNULL(a.mode_paiement, 'DIRECT') as mode_paiement,
               COALESCE(SUM(ags.encaissement_patient), 0) as enc_patient,
               COALESCE(SUM(ags.encaissement_gyneco), 0) as enc_gyneco,
               COALESCE(SUM(ags.decaissement_clinique), 0) as decaissement,
               COALESCE(SUM(ags.compensation), 0) as compensation
        FROM accouchement_dossiers a
        INNER JOIN accouchement_gyneco_situations ags ON a.id_dossier = ags.id_dossier
        {where_clause}
        GROUP BY a.id_dossier
        ORDER BY a.date_accouchement DESC
        """, tuple(params)
    )

    dossiers = []
    for d in cursor.fetchall():
        part_gyneco = to_decimal(d['part_gyneco'])
        part_clinique = to_decimal(d['part_clinique'])
        mode_paiement = d['mode_paiement']

        # ✅ Balance de base depuis accouchement_dossiers.balance_medecin
        # Calculée différemment selon le mode de paiement
        balance_base = to_decimal(d['balance_medecin'])

        # ✅ Calcul de la balance finale
        # Les transactions (enc_gyneco, decaissement) s'appliquent différemment selon le mode

        if mode_paiement == 'VIA_GYNECO':
            # Patient a payé le gynéco
            # balance_base = part_clinique - montant_paye (ce que gynéco doit à la clinique)
            # enc_gyneco = paiements du gynéco vers la clinique (diminue sa dette)
            # decaissement = paiements clinique vers gynéco (augmente sa dette, déjà négatif)
            balance_finale = (
                balance_base
                - to_decimal(d['enc_gyneco'])      # Paiement gynéco → réduit sa dette
                + to_decimal(d['decaissement'])    # Déjà négatif dans la DB
                + to_decimal(d['compensation'])
            )

            # Pour VIA_GYNECO, la "part médecin" affichée est la part gynéco
            part_medecin_affichee = part_gyneco

        else:
            # DIRECT ou DIFFERE : Patient paie (ou paiera) la clinique
            # balance_base = montant_paye - part_gyneco (ce que clinique doit au gynéco)
            # decaissement = paiements clinique vers gynéco (diminue sa dette, déjà négatif)
            # enc_patient = encaissements supplémentaires du patient
            balance_finale = (
                balance_base
                + to_decimal(d['decaissement'])     # Paiement clinique → réduit sa dette (déjà négatif)
                + to_decimal(d['enc_patient'])      # Encaissements patient
                + to_decimal(d['compensation'])
            )

            # Pour DIRECT/DIFFERE, la "part médecin" affichée est la part gynéco
            part_medecin_affichee = part_gyneco

        dossier = {
            'id': d['id_dossier'],
            'id_dossier': d['id_dossier'],
            'type_dossier': 'ACCOUCHEMENT',
            'patient': d['patient'],
            'date_accouchement': d['date_accouchement'],
            'part_gyneco': part_gyneco,
            'part_clinique': part_clinique,
            'part_medecin': part_medecin_affichee,  # Pour compatibilité avec le template
            'prix_total': part_gyneco,              # Pour compatibilité
            'prix_total_dossier': to_decimal(d['prix_total_dossier']),
            'balance': balance_finale,
            'reste': balance_finale,
            'statut_paiement': calculer_statut_paiement(balance_finale),
            'type_accouchement': d.get('type_accouchement'),
            'type_tarification': d.get('type_tarification'),
            'mode_paiement': mode_paiement,
            'enc_patient': to_decimal(d['enc_patient']),
            'enc_gyneco': to_decimal(d['enc_gyneco']),
            'decaissement': to_decimal(d['decaissement']),
            'compensation': to_decimal(d['compensation'])
        }

        if include_decharge_status:
            dossier['deja_decharge'] = est_dossier_deja_decharge(
                cursor, d['id_dossier'], 'ACCOUCHEMENT'
            )

        dossiers.append(dossier)

    return dossiers


def get_stats_gyneco_externe(cursor, id_gyneco, start_date=None, end_date=None):
    """
    Calcule les statistiques pour un gynécologue externe
    """
    
    date_filter_dossier = ""
    params_dossier = [id_gyneco]
    
    date_filter_trans = ""
    
    if start_date:
        date_filter_dossier += " AND date_accouchement >= %s"
        params_dossier.append(start_date)
        date_filter_trans += " AND d.date_accouchement >= %s"
        
    if end_date:
        date_filter_dossier += " AND date_accouchement <= %s"
        params_dossier.append(end_date)
        date_filter_trans += " AND d.date_accouchement <= %s"

    # Stats ACCOUCHEMENT
    cursor.execute(
        f"""
        SELECT COUNT(d.id_dossier) as total_dossiers,
               COALESCE(SUM(d.part_gyneco), 0) as chiffre_affaire,
               COALESCE(SUM(d.balance_medecin), 0) as balance_totale
        FROM accouchement_dossiers d
        INNER JOIN accouchement_gyneco_situations ags ON d.id_dossier = ags.id_dossier
        WHERE d.id_gyneco = %s
          AND d.est_gyneco_interne = 0
          AND (d.est_annule IS NULL OR d.est_annule = 0)
          {date_filter_trans}
        """, tuple(params_dossier)
    )
    acc_base = cursor.fetchone()

    # Params for transactions query
    # We need to reuse params if filtering by date, but we also select from situations so we need a join
    params_trans = [id_gyneco]
    if start_date:
        params_trans.append(start_date)
    if end_date:
        params_trans.append(end_date)

    cursor.execute(
        f"""
        SELECT COALESCE(SUM(s.encaissement_patient), 0) as enc_patient,
               COALESCE(SUM(s.encaissement_gyneco), 0) as enc_gyneco,
               COALESCE(SUM(s.decaissement_clinique), 0) as decaissement,
               COALESCE(SUM(s.compensation), 0) as compensation
        FROM accouchement_gyneco_situations s
        JOIN accouchement_dossiers d ON s.id_dossier = d.id_dossier
        WHERE s.id_gyneco = %s
        AND (d.est_annule IS NULL OR d.est_annule = 0)
        {date_filter_trans}
        """, tuple(params_trans)
    )
    acc_trans = cursor.fetchone()

    ca_acc = to_decimal(acc_base['chiffre_affaire'])           # Total honoraires (part_gyneco)
    balance_acc_base = to_decimal(acc_base['balance_totale'])  # SUM(part_clinique - montant_paye)
    enc_gyneco = to_decimal(acc_trans['enc_gyneco'])           # Paiements du gynéco
    dec_acc = to_decimal(acc_trans['decaissement'])            # Paiements de la clinique (négatif)
    comp_acc = to_decimal(acc_trans['compensation'])           # Compensations

    # ✅ Balance finale = balance_base - enc_gyneco + decaissement + compensation
    # Quand le gynéco paie, sa dette diminue
    balance_acc = balance_acc_base - enc_gyneco + dec_acc + comp_acc

    return {
        'total_dossiers': acc_base['total_dossiers'] or 0,
        'chiffre_affaire': ca_acc,                    # Honoraires du gynéco
        'total_decaissement': dec_acc,                # Paiements clinique → gynéco
        'total_encaissement': enc_gyneco,             # Paiements gynéco → clinique
        'total_compensation': comp_acc,
        'balance_globale': balance_acc,               # Ce que le gynéco doit (ou clinique doit si négatif)
        'reste_a_regler_global': balance_acc
    }


def get_transactions_dossier_accouchement(cursor, id_dossier):
    """Récupère les transactions d'un dossier ACCOUCHEMENT"""
    cursor.execute(
        """
        SELECT payment_date,
               encaissement_patient,
               encaissement_gyneco,
               decaissement_clinique,
               compensation,
               notes
        FROM accouchement_gyneco_situations
        WHERE id_dossier = %s
        ORDER BY payment_date DESC
        """, (id_dossier,)
    )
    return cursor.fetchall()


def est_dossier_deja_decharge(cursor, id_dossier, type_dossier):
    """Vérifie si un dossier est déjà inclus dans une opération de décharge non soldée"""
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM accouchement_operation_dossiers od
        INNER JOIN accouchement_operations_financieres_gyneco o
            ON od.id_operation = o.id
        WHERE od.id_dossier = %s
          AND o.type_operation = 'DECHARGE'
          AND o.reste > 0
        """, (id_dossier,)
    )
    result = cursor.fetchone()
    return result['count'] > 0


def est_dossier_deja_encaisse(cursor, id_dossier, type_dossier):
    """Vérifie si un dossier est déjà inclus dans une opération d'encaissement non soldée"""
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM accouchement_operation_dossiers od
        INNER JOIN accouchement_operations_financieres_gyneco o
            ON od.id_operation = o.id
        WHERE od.id_dossier = %s
          AND o.type_operation = 'ENCAISSEMENT'
          AND o.reste > 0
        """, (id_dossier,)
    )
    result = cursor.fetchone()
    return result['count'] > 0


# ========================================================================
# ROUTES PRINCIPALES
# ========================================================================

@app.route('/situation_accouchement_externe')
@login_required
@handle_errors()

def situation_accouchement_externe():
    """Liste des gynécologues EXTERNES avec leur situation financière ACCOUCHEMENT"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT d.id as id_gyneco,
                   CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                   s.name_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE (d.est_interne = 0 OR d.est_interne IS NULL)
              AND s.name_specialty LIKE '%gyn%'
            ORDER BY d.last_name, d.first_name
            """
        )
        gynecos = cursor.fetchall()

        gynecos_with_balance = []
        total_balance_all = Decimal('0')

        for gyneco in gynecos:
            stats = get_stats_gyneco_externe(cursor, gyneco['id_gyneco'])

            if stats['total_dossiers'] == 0:
                continue

            total_balance_all += stats['balance_globale']
            gynecos_with_balance.append({**gyneco, **stats})

        return render_template(
            'situation_medecin/situation_medecin_externe.html',  # ✅ Template unifié
            doctors=gynecos_with_balance,  # ✅ Nom unifié (au lieu de gynecos)
            total_balance_all=total_balance_all,
            type_situation='ACCOUCHEMENT',  # ✅ Paramètre de type
            type_display='Accouchements',
            route_prefix='operations_accouchement_externe',
            route_detail='situation_accouchement_externe_detail',
            id_param='id_gyneco',
            title="Situation Accouchement - Gynécos Externes",
        )
    finally:
        cursor.close()
        conn.close()


@app.route('/situation_accouchement_externe/<int:id_gyneco>')
@login_required
@handle_errors()

def situation_accouchement_externe_detail(id_gyneco):
    """Détail de la situation ACCOUCHEMENT d'un gynécologue externe"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Info gynéco
        cursor.execute(
            """
            SELECT d.id as id_gyneco,
                   CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                   s.name_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
            """, (id_gyneco,)
        )
        gyneco = cursor.fetchone()

        if not gyneco:
            flash('Gynécologue non trouvé', 'danger')
            return redirect(url_for('situation_accouchement_externe'))

        # Filtres dates
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Dossiers ACCOUCHEMENT externes
        dossiers = get_dossiers_accouchement_externe(cursor, id_gyneco, start_date=start_date, end_date=end_date)

        # Enrichir avec transactions
        for doss in dossiers:
            doss['transactions'] = get_transactions_dossier_accouchement(cursor, doss['id'])

        # Stats
        stats = get_stats_gyneco_externe(cursor, id_gyneco, start_date=start_date, end_date=end_date)
        gyneco_enriched = {**gyneco, **stats}

        return render_template(
            'situation_medecin/situation_accouchement_externe_detail.html',
            gyneco=gyneco_enriched,
            dossiers=dossiers,
            current_date=date.today().isoformat(),
            start_date=start_date,
            end_date=end_date,
            title=f"Dr. {gyneco['nom_complet']} - Accouchements",
        )
    finally:
        cursor.close()
        conn.close()


# ========================================================================
# CRÉATION DES BONS (ENCAISSEMENT / DÉCHARGE)
# ========================================================================

@app.route('/creer_operation_accouchement_externe', methods=['POST'])
@login_required
@handle_errors()

def creer_operation_accouchement_externe():
    """
    Créer un bon d'encaissement ou de décharge pour ACCOUCHEMENTS EXTERNES

    ✅ LOGIQUE SELON MODE PAIEMENT :

    ENCAISSEMENT : Gynéco paie la clinique
    - Utilisé pour VIA_GYNECO quand balance > 0

    DÉCHARGE : Clinique paie le gynéco
    - Utilisé pour DIRECT/DIFFERE quand balance < 0
    - Utilisé pour VIA_GYNECO quand balance < 0 (rare)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        id_gyneco = int( request.form.get( 'id_gyneco' ) )
        type_operation = request.form.get( 'type_operation' )
        date_operation = request.form.get( 'date_operation' )
        dossiers_ids = request.form.getlist( 'dossiers[]' )

        if not all( [ id_gyneco, type_operation, date_operation, dossiers_ids ] ):
            flash( 'Données incomplètes', 'danger' )
            return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )

        if type_operation not in [ 'ENCAISSEMENT', 'DECHARGE' ]:
            flash( 'Type d\'opération invalide', 'danger' )
            return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )

        # Récupérer tous les dossiers
        dossiers_acc = get_dossiers_accouchement_externe( cursor, id_gyneco, include_decharge_status = True )
        all_dossiers = { str( d[ 'id' ] ): d for d in dossiers_acc }

        # Vérifier les dossiers déjà utilisés
        dossiers_deja_utilises = [ ]

        for doss_id in dossiers_ids:
            if doss_id not in all_dossiers:
                continue

            doss = all_dossiers[ doss_id ]

            if type_operation == 'DECHARGE':
                if doss.get( 'deja_decharge', False ):
                    dossiers_deja_utilises.append( doss[ 'patient' ] )
            elif type_operation == 'ENCAISSEMENT':
                if est_dossier_deja_encaisse( cursor, int( doss_id ), 'ACCOUCHEMENT' ):
                    dossiers_deja_utilises.append( doss[ 'patient' ] )

        if dossiers_deja_utilises:
            operation_nom = 'décharge' if type_operation == 'DECHARGE' else 'encaissement'
            flash(
                    f'⚠️ Certains dossiers sont déjà inclus dans un {operation_nom} en cours: {", ".join( dossiers_deja_utilises )}',
                    'warning'
                    )
            return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )

        # Calculer le montant total
        montant_total = Decimal( '0' )
        dossiers_data = [ ]

        for doss_id in dossiers_ids:
            if doss_id not in all_dossiers:
                continue

            doss = all_dossiers[ doss_id ]
            reste = doss[ 'reste' ]
            mode = doss.get( 'mode_paiement', 'DIRECT' )

            # ✅ LOGIQUE CORRIGÉE SELON MODE PAIEMENT
            if type_operation == 'ENCAISSEMENT':
                # Gynéco paie la clinique
                # Seulement pour VIA_GYNECO avec balance > 0
                if mode == 'VIA_GYNECO' and reste > Decimal( '0.01' ):
                    montant_du = reste
                    montant_total += montant_du
                    dossiers_data.append( { 'id': int( doss_id ), 'montant': montant_du } )

            elif type_operation == 'DECHARGE':
                # Clinique paie le gynéco
                # Pour DIRECT/DIFFERE avec balance < 0
                # OU pour VIA_GYNECO avec balance < 0 (rare)
                if reste < Decimal( '-0.01' ):
                    montant_du = abs( reste )
                    montant_total += montant_du
                    dossiers_data.append( { 'id': int( doss_id ), 'montant': montant_du } )

        if montant_total == 0:
            flash( 'Aucun dossier éligible sélectionné', 'warning' )
            return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )

        # Création du bon
        cursor.execute(
                """
                INSERT INTO accouchement_operations_financieres_gyneco
                    (id_gyneco, type_operation, date, montant, reste, id_created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                        id_gyneco, type_operation, date_operation, montant_total,
                        montant_total, g.user[ 'id_personnel' ]
                        )
                )

        id_operation = cursor.lastrowid

        # Liaison avec les dossiers
        for doss_data in dossiers_data:
            cursor.execute(
                    """
                    INSERT INTO accouchement_operation_dossiers
                        (id_operation, id_dossier, montant)
                    VALUES (%s, %s, %s)
                    """, (id_operation, doss_data[ 'id' ], doss_data[ 'montant' ])
                    )

        conn.commit()

        flash( f'✅ Bon de {type_operation.lower()} créé. Montant: {float( montant_total ):.2f} DA', 'success' )
        return redirect( url_for( 'operations_accouchement_externe_list', type_operation = type_operation ) )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur création opération: {e}' )
        flash( f'Erreur: {str( e )}', 'danger' )
        return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )
    finally:
        cursor.close()
        conn.close()


# ========================================================================
# COMPENSATION
# ========================================================================

@app.route( '/creer_compensation_accouchement_externe', methods = [ 'POST' ] )
@login_required
@handle_errors()

def creer_compensation_accouchement_externe():
    """Créer une compensation FIFO entre dossiers ACCOUCHEMENT EXTERNES"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        id_gyneco = int( request.form.get( 'id_gyneco' ) )
        date_operation = request.form.get( 'date_operation' )
        dossiers_ids = [ int( x ) for x in request.form.getlist( 'dossiers[]' ) ]

        if not all( [ id_gyneco, date_operation, dossiers_ids ] ):
            flash( 'Données incomplètes', 'danger' )
            return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )

        # Récupérer tous les dossiers
        dossiers_acc = get_dossiers_accouchement_externe( cursor, id_gyneco )
        all_dossiers = { d[ 'id' ]: d for d in dossiers_acc }

        # Séparer positifs/négatifs
        dossiers_positifs = [ ]
        dossiers_negatifs = [ ]

        for doss_id in dossiers_ids:
            if doss_id not in all_dossiers:
                continue

            doss = all_dossiers[ doss_id ]
            reste = doss[ 'reste' ]

            if reste > Decimal( '0.01' ):
                dossiers_positifs.append( doss )
            elif reste < Decimal( '-0.01' ):
                dossiers_negatifs.append( doss )

        # Tri FIFO
        dossiers_positifs.sort( key = lambda x: x[ 'date_accouchement' ] )
        dossiers_negatifs.sort( key = lambda x: x[ 'date_accouchement' ] )

        if not dossiers_positifs or not dossiers_negatifs:
            flash( 'Vous devez sélectionner au moins un dossier de chaque type', 'warning' )
            return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )

        total_surplus = sum( d[ 'reste' ] for d in dossiers_positifs )
        total_deficit = sum( abs( d[ 'reste' ] ) for d in dossiers_negatifs )
        montant_compensation = min( total_surplus, total_deficit )

        # Création du bon
        cursor.execute(
                """
                INSERT INTO accouchement_operations_financieres_gyneco
                    (id_gyneco, type_operation, date, montant, reste, id_created_by)
                VALUES (%s, 'COMPENSATION', %s, %s, 0, %s)
                """, (id_gyneco, date_operation, montant_compensation, g.user[ 'id_personnel' ])
                )

        id_operation = cursor.lastrowid

        # Application FIFO sur négatifs
        surplus_restant = montant_compensation

        for doss in dossiers_negatifs:
            if surplus_restant <= 0:
                break

            deficit = abs( doss[ 'reste' ] )
            montant = min( surplus_restant, deficit )

            cursor.execute(
                    """
                    INSERT INTO accouchement_operation_dossiers
                        (id_operation, id_dossier, montant)
                    VALUES (%s, %s, %s)
                    """, (id_operation, doss[ 'id' ], montant)
                    )

            cursor.execute(
                    """
                    INSERT INTO accouchement_gyneco_situations
                        (id_gyneco, id_dossier, compensation, notes)
                    VALUES (%s, %s, %s, %s)
                    """, (id_gyneco, doss[ 'id' ], montant, f'Compensation #{id_operation}')
                    )

            surplus_restant -= montant

        # Application FIFO sur positifs
        deficit_restant = montant_compensation

        for doss in dossiers_positifs:
            if deficit_restant <= 0:
                break

            surplus = doss[ 'reste' ]
            montant = min( deficit_restant, surplus )

            cursor.execute(
                    """
                    INSERT INTO accouchement_operation_dossiers
                        (id_operation, id_dossier, montant)
                    VALUES (%s, %s, %s)
                    """, (id_operation, doss[ 'id' ], montant)
                    )

            cursor.execute(
                    """
                    INSERT INTO accouchement_gyneco_situations
                        (id_gyneco, id_dossier, compensation, notes)
                    VALUES (%s, %s, %s, %s)
                    """, (id_gyneco, doss[ 'id' ], -montant, f'Compensation #{id_operation}')
                    )

            deficit_restant -= montant

        conn.commit()

        flash( f'Compensation créée. Montant: {float( montant_compensation ):.2f} DA', 'success' )
        return redirect( url_for( 'operations_accouchement_externe_list', type_operation = 'COMPENSATION' ) )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur compensation: {e}' )
        flash( f'Erreur: {str( e )}', 'danger' )
        return redirect( url_for( 'situation_accouchement_externe_detail', id_gyneco = id_gyneco ) )
    finally:
        cursor.close()
        conn.close()


# ========================================================================
# PAIEMENT D'UNE OPÉRATION
# ========================================================================

@app.route( '/payer_operation_accouchement/<int:id_operation>', methods = [ 'POST' ] )
@login_required
@handle_errors()

def payer_operation_accouchement( id_operation ):
    """
    Enregistrer un paiement pour une opération ACCOUCHEMENT

    ✅ ENCAISSEMENT : Gynéco paie la clinique → enc_gyneco
    ✅ DÉCHARGE : Clinique paie le gynéco → decaissement
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        payment_amount = to_decimal( request.form.get( 'payment_amount', 0 ) )
        type_operation = request.form.get( 'type_operation' )

        if payment_amount <= 0:
            flash( 'Montant invalide', 'danger' )
            return redirect( url_for( 'operations_accouchement_externe_list', type_operation = type_operation ) )

        # Récupérer l'opération
        cursor.execute(
                """
                SELECT *
                FROM accouchement_operations_financieres_gyneco
                WHERE id = %s
                """, (id_operation,)
                )
        operation = cursor.fetchone()

        if not operation:
            flash( 'Opération non trouvée', 'danger' )
            return redirect( url_for( 'operations_accouchement_externe_list', type_operation = type_operation ) )

        reste_actuel = to_decimal( operation[ 'reste' ] )

        if payment_amount > reste_actuel:
            flash( 'Le montant dépasse le reste à payer', 'danger' )
            return redirect( url_for( 'operations_accouchement_externe_list', type_operation = type_operation ) )

        # Mise à jour de l'opération
        nouveau_paye = to_decimal( operation[ 'montant_paye' ] ) + payment_amount
        nouveau_reste = reste_actuel - payment_amount

        cursor.execute(
                """
                UPDATE accouchement_operations_financieres_gyneco
                SET montant_paye  = %s,
                    reste         = %s,
                    id_payment_by = %s,
                    payment_at    = %s
                WHERE id = %s
                """, (nouveau_paye, nouveau_reste, g.user[ 'id_personnel' ], datetime.now(), id_operation)
                )

        # Récupérer les dossiers liés
        cursor.execute(
                """
                SELECT id_dossier, montant
                FROM accouchement_operation_dossiers
                WHERE id_operation = %s
                """, (id_operation,)
                )
        dossiers_lies = cursor.fetchall()

        montant_total = to_decimal( operation[ 'montant' ] )

        # Répartition proportionnelle sur les dossiers
        for doss in dossiers_lies:
            montant_dossier = to_decimal( doss[ 'montant' ] )
            proportion = montant_dossier / montant_total
            montant_transaction = payment_amount * proportion

            if type_operation == 'ENCAISSEMENT':
                # ✅ Gynéco paie la clinique
                cursor.execute(
                        """
                        INSERT INTO accouchement_gyneco_situations
                            (id_gyneco, id_dossier, encaissement_gyneco, notes)
                        VALUES (%s, %s, %s, %s)
                        """, (
                                operation[ 'id_gyneco' ], doss[ 'id_dossier' ], montant_transaction,
                                f'Paiement bon #{id_operation}'
                                )
                        )
            elif type_operation == 'DECHARGE':
                # ✅ Clinique paie le gynéco (montant négatif)
                cursor.execute(
                        """
                        INSERT INTO accouchement_gyneco_situations
                            (id_gyneco, id_dossier, decaissement_clinique, notes)
                        VALUES (%s, %s, %s, %s)
                        """, (
                                operation[ 'id_gyneco' ], doss[ 'id_dossier' ], -montant_transaction,
                                f'Paiement bon #{id_operation}'
                                )
                        )

        conn.commit()

        flash( f'Paiement de {float( payment_amount ):.2f} DA enregistré', 'success' )
        return redirect( url_for( 'operations_accouchement_externe_list', type_operation = type_operation ) )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur paiement: {e}' )
        flash( f'Erreur: {str( e )}', 'danger' )
        return redirect( url_for( 'operations_accouchement_externe_list', type_operation = type_operation ) )
    finally:
        cursor.close()
        conn.close()


# ========================================================================
# LISTE DES OPÉRATIONS
# ========================================================================

@app.route( '/operations_accouchement_externe/<type_operation>' )
@login_required
@handle_errors()

def operations_accouchement_externe_list( type_operation ):
    """Liste des bons d'opérations ACCOUCHEMENT EXTERNES"""
    if type_operation not in [ 'ENCAISSEMENT', 'DECHARGE', 'COMPENSATION' ]:
        flash( 'Type d\'opération invalide', 'danger' )
        return redirect( url_for( 'situation_accouchement_externe' ) )

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        filter_paid = request.args.get( 'filter_paid', 'false' ) == 'true'
        where_reste = "AND o.reste = 0" if filter_paid else "AND o.reste > 0"

        cursor.execute(
                f"""
            SELECT o.*, CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   CONCAT(pc.nom, ' ', pc.prenom) as created_by_name,
                   CONCAT(pp.nom, ' ', pp.prenom) as payment_by_name
            FROM accouchement_operations_financieres_gyneco o
            LEFT JOIN doctors d ON o.id_gyneco = d.id
            LEFT JOIN personnel pc ON o.id_created_by = pc.id_personnel
            LEFT JOIN personnel pp ON o.id_payment_by = pp.id_personnel
            WHERE o.type_operation = %s {where_reste}
            ORDER BY o.date DESC, o.id DESC
        """, (type_operation,)
                )

        operations = cursor.fetchall()

        return render_template(
            'situation_medecin/operations_externe_list.html',  # ✅ Template unifié
                operations = operations,
                type_operation = type_operation,
                filter_paid = filter_paid,
            type_situation='ACCOUCHEMENT',  # ✅ Paramètre de type
            type_display='Accouchements',
            route_back='situation_accouchement_externe',
            api_dossiers_endpoint='/api/get_dossiers_operation_accouchement',
            route_payer='payer_operation_accouchement',
            route_supprimer='supprimer_operation_accouchement',
                title = f"Bons de {type_operation.lower()} - Accouchements",
                )
    finally:
        cursor.close()
        conn.close()


@app.route( '/supprimer_operation_accouchement/<int:id_operation>', methods = [ 'POST' ] )
@login_required
@handle_errors()

def supprimer_operation_accouchement( id_operation ):
    """Supprimer une opération non payée"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                """
                SELECT *
                FROM accouchement_operations_financieres_gyneco
                WHERE id = %s
                """, (id_operation,)
                )
        operation = cursor.fetchone()

        if not operation:
            flash( 'Opération non trouvée', 'danger' )
            return redirect( url_for( 'situation_accouchement_externe' ) )

        if to_decimal( operation[ 'montant_paye' ] ) > 0:
            flash( 'Impossible de supprimer une opération déjà payée', 'danger' )
            return redirect(
                url_for( 'operations_accouchement_externe_list', type_operation = operation[ 'type_operation' ] )
                )

        cursor.execute( "DELETE FROM accouchement_operations_financieres_gyneco WHERE id = %s", (id_operation,) )
        conn.commit()

        flash( 'Opération supprimée', 'success' )
        return redirect(
            url_for( 'operations_accouchement_externe_list', type_operation = operation[ 'type_operation' ] )
            )

    except Exception as e:
        conn.rollback()
        flash( f'Erreur: {str( e )}', 'danger' )
        return redirect( url_for( 'situation_accouchement_externe' ) )
    finally:
        cursor.close()
        conn.close()


# ========================================================================
# APIs
# ========================================================================

@app.route( '/api/get_dossiers_accouchement_externe/<int:id_gyneco>' )
@login_required
def api_get_dossiers_accouchement_externe( id_gyneco ):
    """API: Récupère les dossiers d'un gynécologue externe paginés"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        page = int( request.args.get( 'page', 1 ) )
        per_page = int( request.args.get( 'per_page', 20 ) )
        offset = (page - 1) * per_page

        dossiers = get_dossiers_accouchement_externe( cursor, id_gyneco )

        total = len( dossiers )
        paginated = dossiers[ offset:offset + per_page ]

        # Formatter
        for d in paginated:
            if isinstance( d[ 'date_accouchement' ], date ):
                d[ 'date_accouchement' ] = d[ 'date_accouchement' ].strftime( '%d/%m/%Y' )

            d[ 'prix_total' ] = float( d[ 'prix_total' ] )
            d[ 'part_clinique' ] = float( d[ 'part_clinique' ] )
            d[ 'part_gyneco' ] = float( d[ 'part_gyneco' ] )
            d[ 'prix_total_dossier' ] = float( d[ 'prix_total_dossier' ] )
            d[ 'balance' ] = float( d[ 'balance' ] )
            d[ 'reste' ] = float( d[ 'reste' ] )

        return jsonify(
                {
                        'success': True,
                        'dossiers': paginated,
                        'pagination': {
                                'page': page,
                                'per_page': per_page,
                                'total': total,
                                'total_pages': (total + per_page - 1) // per_page
                                }
                        }
                )
    except Exception as e:
        return jsonify( { 'success': False, 'error': str( e ) } ), 500
    finally:
        cursor.close()
        conn.close()


@app.route( '/api/get_transactions_accouchement/<int:id_dossier>' )
@login_required
def api_get_transactions_accouchement( id_dossier ):
    """API: Récupère les transactions d'un dossier accouchement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        transactions = get_transactions_dossier_accouchement( cursor, id_dossier )

        return jsonify(
                {
                        'success': True,
                        'transactions': [ {
                                'payment_date': t[ 'payment_date' ].strftime( '%d/%m/%Y %H:%M' ) if t[
                                    'payment_date' ] else 'N/A',
                                'encaissement_patient': float( t[ 'encaissement_patient' ] or 0 ),
                                'encaissement_gyneco': float( t[ 'encaissement_gyneco' ] or 0 ),
                                'decaissement_clinique': float( t[ 'decaissement_clinique' ] or 0 ),
                                'compensation': float( t[ 'compensation' ] or 0 ),
                                'notes': t[ 'notes' ] or ''
                                } for t in transactions ]
                        }
                )
    except Exception as e:
        return jsonify( { 'success': False, 'error': str( e ) } ), 500
    finally:
        cursor.close()
        conn.close()


@app.route( '/api/get_gynecos_a_encaisser' )
@login_required
def api_get_gynecos_a_encaisser():
    """API: Gynécos avec dossiers à encaisser (balance > 0)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                """
                SELECT DISTINCT d.id as id_gyneco, CONCAT(d.first_name, ' ', d.last_name) as nom
                FROM doctors d
                         JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE (d.est_interne = 0 OR d.est_interne IS NULL)
                  AND s.name_specialty LIKE '%gyn%'
                """
                )
        gynecos = cursor.fetchall()

        result = [ ]
        for gyneco in gynecos:
            dossiers = get_dossiers_accouchement_externe( cursor, gyneco[ 'id_gyneco' ] )

            dossiers_eligibles = [ ]
            for d in dossiers:
                # ✅ ENCAISSEMENT : balance > 0 (gynéco doit payer)
                if d['reste'] > Decimal('0.01') and not est_dossier_deja_encaisse(
                        cursor, d[ 'id' ], 'ACCOUCHEMENT'
                        ):
                    dossiers_eligibles.append(
                            {
                                    'id_dossier': d[ 'id' ],
                                    'patient': d[ 'patient' ],
                                    'date': d[ 'date_accouchement' ].strftime( '%d/%m/%Y' ),
                                    'prix_total': float( d[ 'prix_total' ] ),
                            'montant_du': float(d['reste'])
                                    }
                            )

            if dossiers_eligibles:
                result.append(
                        {
                                'id': gyneco[ 'id_gyneco' ],
                                'nom': gyneco[ 'nom' ],
                                'dossiers': dossiers_eligibles
                                }
                        )

        return jsonify( result )
    finally:
        cursor.close()
        conn.close()


@app.route( '/api/get_gynecos_a_decaisser' )
@login_required
def api_get_gynecos_a_decaisser():
    """API: Gynécos avec dossiers à décaisser (balance < 0)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                """
                SELECT DISTINCT d.id as id_gyneco, CONCAT(d.first_name, ' ', d.last_name) as nom
                FROM doctors d
                         JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE (d.est_interne = 0 OR d.est_interne IS NULL)
                  AND s.name_specialty LIKE '%gyn%'
                """
                )
        gynecos = cursor.fetchall()

        result = [ ]
        for gyneco in gynecos:
            dossiers = get_dossiers_accouchement_externe(
                cursor, gyneco[ 'id_gyneco' ], include_decharge_status = True
                )

            dossiers_eligibles = [ ]
            for d in dossiers:
                # ✅ DÉCHARGE : balance < 0 (clinique doit payer)
                if d['reste'] < Decimal('-0.01') and not d.get('deja_decharge', False):
                    dossiers_eligibles.append(
                            {
                                    'id_dossier': d[ 'id' ],
                                    'patient': d[ 'patient' ],
                                    'date': d[ 'date_accouchement' ].strftime( '%d/%m/%Y' ),
                                    'prix_total': float( d[ 'prix_total' ] ),
                            'montant_du': float(abs(d['reste']))
                                    }
                            )

            if dossiers_eligibles:
                result.append(
                        {
                                'id': gyneco[ 'id_gyneco' ],
                                'nom': gyneco[ 'nom' ],
                                'dossiers': dossiers_eligibles
                                }
                        )

        return jsonify( result )
    finally:
        cursor.close()
        conn.close()


@app.route( '/api/get_dossiers_compensation_accouchement/<int:id_gyneco>' )
@login_required
def api_get_dossiers_compensation_accouchement( id_gyneco ):
    """API: Dossiers éligibles pour compensation"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        dossiers = get_dossiers_accouchement_externe( cursor, id_gyneco, include_decharge_status = True )

        dossiers_positifs = [ ]
        dossiers_negatifs = [ ]

        for d in dossiers:
            if abs( d[ 'reste' ] ) < Decimal( '0.01' ):
                continue

            deja_decharge = d.get( 'deja_decharge', False )
            deja_encaisse = est_dossier_deja_encaisse( cursor, d[ 'id' ], 'ACCOUCHEMENT' )

            doss_data = {
                    'id_dossier': d[ 'id' ],
                    'patient': d[ 'patient' ],
                    'date': d[ 'date_accouchement' ].strftime( '%d/%m/%Y' ),
                    'statut': d[ 'statut_paiement' ],
                    'reste': float( d[ 'reste' ] ),
                    'deja_decharge': deja_decharge,
                    'deja_encaisse': deja_encaisse
                    }

            if d[ 'reste' ] > 0:
                dossiers_positifs.append( doss_data )
            else:
                dossiers_negatifs.append( doss_data )

        return jsonify(
                {
                        'dossiers_positifs': dossiers_positifs,
                        'dossiers_negatifs': dossiers_negatifs
                        }
                )
    finally:
        cursor.close()
        conn.close()


@app.route( '/api/get_dossiers_operation_accouchement/<int:id_operation>' )
@login_required
def api_get_dossiers_operation_accouchement( id_operation ):
    """API: Dossiers liés à une opération"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
                """
                SELECT od.montant,
                       ad.patiente    as patient,
                       ad.date_accouchement,
                       ad.part_gyneco as prix_total
                FROM accouchement_operation_dossiers od
                         JOIN accouchement_dossiers ad ON od.id_dossier = ad.id_dossier
                WHERE od.id_operation = %s
                ORDER BY ad.date_accouchement
                """, (id_operation,)
                )
        dossiers = cursor.fetchall()

        return jsonify(
                [ {
                        'patient': d[ 'patient' ],
                        'date': d[ 'date_accouchement' ].strftime( '%d/%m/%Y' ) if d[ 'date_accouchement' ] else '',
                        'prix_total': float( d[ 'prix_total' ] or 0 ),
                        'montant': float( d[ 'montant' ] )
                        } for d in dossiers ]
                )
    finally:
        cursor.close()
        conn.close()