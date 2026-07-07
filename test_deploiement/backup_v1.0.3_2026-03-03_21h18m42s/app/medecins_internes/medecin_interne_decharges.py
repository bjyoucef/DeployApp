# app/medecin_interne_decharges.py
"""
Module de gestion des paiements et décharges pour médecins internes
Système identique aux gynécos internes
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

def to_decimal(value, default=0) -> Decimal:
    """Convertit une valeur en Decimal de manière sécurisée"""
    if value is None or value == '':
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except (Exception,):
        return Decimal(str(default))


def generer_numero_decharge_medecin() -> str:
    """Génère un numéro unique de décharge"""
    now = datetime.now()
    prefix = f"DMI-{now.year}{now.month:02d}"

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM medecin_interne_decharges
            WHERE numero_decharge LIKE %s
        """, (f"{prefix}%",))
        count = cursor.fetchone()['count']
        return f"{prefix}-{count + 1:04d}"
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# LISTE DES ACTES NON PAYÉS
# ==============================================================================

@app.route('/medecin-interne/paiements')
@login_required
@handle_errors()

def medecin_interne_paiements_list():
    """Liste des actes non payés par médecin interne"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres
        id_doctor = request.args.get('id_doctor', 'all')
        date_debut = request.args.get('date_debut', '')
        date_fin = request.args.get('date_fin', '')

        # Liste des médecins internes
        cursor.execute("""
            SELECT d.id,
                   CONCAT(d.first_name, ' ', d.last_name) as nom_complet
            FROM doctors d
            JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.est_interne = 1
              AND s.name_specialty IN ('ORTHOPÉDIE', 'CHIRURGIE GÉNÉRALE')
            ORDER BY d.last_name, d.first_name
        """)
        medecins = cursor.fetchall()

        # Construction de la requête
        where_clauses = [
            "medecin_paye = 0",
            "id_decharge_medecin IS NULL",
            "est_annule = FALSE"
        ]
        params = {}

        if id_doctor != 'all':
            where_clauses.append("id_doctor = %(id_doctor)s")
            params['id_doctor'] = id_doctor

        if date_debut:
            where_clauses.append("date_acte >= %(date_debut)s")
            params['date_debut'] = date_debut

        if date_fin:
            where_clauses.append("date_acte <= %(date_fin)s")
            params['date_fin'] = date_fin

        where_sql = " AND ".join(where_clauses)

        # Actes non payés groupés par médecin
        cursor.execute(f"""
            SELECT 
                a.id_doctor,
                CONCAT(d.first_name, ' ', d.last_name) as medecin_name,
                COUNT(a.id_acte) as nb_actes,
                COALESCE(SUM(a.part_medecin), 0) as total_honoraires,
                MIN(a.date_acte) as date_min,
                MAX(a.date_acte) as date_max
            FROM medecin_interne_actes a
            JOIN doctors d ON a.id_doctor = d.id
            WHERE {where_sql}
            GROUP BY a.id_doctor
            ORDER BY medecin_name
        """, params)
        medecins_stats = cursor.fetchall()

        # Détail des actes si un médecin est sélectionné
        actes = []
        if id_doctor != 'all':
            cursor.execute(f"""
                SELECT 
                    a.id_acte,
                    a.patient,
                    a.date_acte,
                    a.nom_acte,
                    a.part_medecin,
                    a.prix_acte_base
                FROM medecin_interne_actes a
                WHERE {where_sql}
                ORDER BY a.date_acte DESC
            """, params)
            actes = cursor.fetchall()

        return render_template(
            'medecin_interne/paiements_interne/liste_impayes.html',
            medecins=medecins,
            medecins_stats=medecins_stats,
            actes=actes,
            id_doctor_selected=id_doctor,
            date_debut=date_debut,
            date_fin=date_fin,
            title="Paiements Médecins Internes"
        )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# CRÉER UNE DÉCHARGE
# ==============================================================================

@app.route('/medecin-interne/decharge/creer', methods=['GET', 'POST'])
@login_required
@handle_errors()

def medecin_interne_decharge_create():
    """Création d'une décharge de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if request.method == 'GET':
            id_doctor = request.args.get('id_doctor')
            date_debut = request.args.get('date_debut', '')
            date_fin = request.args.get('date_fin', '')

            if not id_doctor:
                flash('Médecin non spécifié', 'danger')
                return redirect(url_for('medecin_interne_paiements_list'))

            # Info médecin
            cursor.execute("""
                SELECT id, CONCAT(first_name, ' ', last_name) as nom_complet
                FROM doctors
                WHERE id = %s
                  AND est_interne = 1
            """, (id_doctor,))
            medecin = cursor.fetchone()

            if not medecin:
                flash('Médecin non trouvé', 'danger')
                return redirect(url_for('medecin_interne_paiements_list'))

            # Actes non payés ET non dans une décharge ET non annulés
            where_clauses = [
                "id_doctor = %(id_doctor)s",
                "medecin_paye = 0",
                "id_decharge_medecin IS NULL",
                "est_annule = FALSE"
            ]
            params = {'id_doctor': id_doctor}

            if date_debut:
                where_clauses.append("date_acte >= %(date_debut)s")
                params['date_debut'] = date_debut

            if date_fin:
                where_clauses.append("date_acte <= %(date_fin)s")
                params['date_fin'] = date_fin

            where_sql = " AND ".join(where_clauses)

            cursor.execute(f"""
                SELECT 
                    id_acte,
                    patient,
                    date_acte,
                    nom_acte,
                    part_medecin,
                    prix_acte_base
                FROM medecin_interne_actes
                WHERE {where_sql}
                AND (est_annule IS NULL OR est_annule = 0)
                ORDER BY date_acte
            """, params)
            actes = cursor.fetchall()

            return render_template(
                'medecin_interne/paiements_interne/creer_decharge.html',
                medecin=medecin,
                actes=actes,
                date_debut=date_debut,
                date_fin=date_fin,
                title="Nouvelle Décharge"
            )

        # POST - Création de la décharge
        id_doctor = request.form.get('id_doctor')
        date_decharge = request.form.get('date_decharge')
        periode_debut = request.form.get('periode_debut')
        periode_fin = request.form.get('periode_fin')
        mode_paiement = request.form.get('mode_paiement', 'ESPECES')
        reference_paiement = request.form.get('reference_paiement', '').strip()
        observations = request.form.get('observations', '').strip()
        actes_ids = request.form.getlist('actes[]')

        if not actes_ids:
            flash('Veuillez sélectionner au moins un acte', 'danger')
            return redirect(request.referrer)

        # Vérification actes déjà déchargés
        placeholders = ','.join(['%s'] * len(actes_ids))
        cursor.execute(f"""
            SELECT id_acte, numero_decharge
            FROM medecin_interne_actes a
            LEFT JOIN medecin_interne_decharges dech ON a.id_decharge_medecin = dech.id_decharge
            WHERE a.id_acte IN ({placeholders})
              AND a.id_decharge_medecin IS NOT NULL
              AND dech.statut NOT IN ('ANNULE')
        """, actes_ids)

        actes_deja_decharges = cursor.fetchall()

        if actes_deja_decharges:
            actes_list = ', '.join([
                f"#{a['id_acte']} (décharge {a['numero_decharge']})"
                for a in actes_deja_decharges
            ])
            flash(f'❌ Les actes suivants sont déjà dans une décharge active: {actes_list}', 'danger')
            return redirect(request.referrer)

        # Récupérer les actes valides (non annulés)
        cursor.execute(f"""
            SELECT 
                id_acte,
                part_medecin
            FROM medecin_interne_actes
            WHERE id_acte IN ({placeholders})
              AND id_doctor = %s
              AND medecin_paye = 0
              AND id_decharge_medecin IS NULL
              AND (est_annule IS NULL OR est_annule = 0)
        """, (*actes_ids, id_doctor))
        actes = cursor.fetchall()

        if not actes:
            flash('Aucun acte valide sélectionné', 'danger')
            return redirect(request.referrer)

        if len(actes) < len(actes_ids):
            flash(
                f'⚠️ Attention: {len(actes_ids) - len(actes)} acte(s) '
                'ignoré(s) car déjà dans une décharge ou déjà payé(s)',
                'warning'
            )

        montant_total = sum(to_decimal(a['part_medecin']) for a in actes)
        nb_actes = len(actes)

        # Générer numéro
        numero_decharge = generer_numero_decharge_medecin()

        # Créer la décharge
        cursor.execute("""
            INSERT INTO medecin_interne_decharges
            (numero_decharge, id_doctor, date_decharge, periode_debut, periode_fin,
             montant_total, nb_actes, mode_paiement, reference_paiement,
             observations, statut, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'BROUILLON', %s)
        """, (
            numero_decharge, id_doctor, date_decharge, periode_debut, periode_fin,
            montant_total, nb_actes, mode_paiement, reference_paiement,
            observations, g.user['id_personnel']
        ))

        id_decharge = cursor.lastrowid

        # Lier les actes
        for acte in actes:
            cursor.execute("""
                INSERT INTO medecin_interne_decharge_actes
                (id_decharge, id_acte, montant_honoraires)
                VALUES (%s, %s, %s)
            """, (id_decharge, acte['id_acte'], acte['part_medecin']))

        # Marquer les actes
        actes_ids_valides = [a['id_acte'] for a in actes]
        placeholders = ','.join(['%s'] * len(actes_ids_valides))
        cursor.execute(f"""
            UPDATE medecin_interne_actes
            SET id_decharge_medecin = %s
            WHERE id_acte IN ({placeholders})
        """, (id_decharge, *actes_ids_valides))

        conn.commit()

        flash(f'✅ Décharge {numero_decharge} créée avec succès ({nb_actes} actes)', 'success')
        return redirect(url_for('medecin_interne_decharge_detail', id_decharge=id_decharge))

    except Exception as e:
        conn.rollback()
        app.logger.error(f'Erreur création décharge: {e}')
        flash(f'❌ Erreur: {str(e)}', 'danger')
        return redirect(url_for('medecin_interne_paiements_list'))

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# DÉTAIL D'UNE DÉCHARGE
# ==============================================================================

@app.route('/medecin-interne/decharge/<int:id_decharge>')
@login_required
@handle_errors()

def medecin_interne_decharge_detail(id_decharge):
    """Détail d'une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Info décharge
        cursor.execute("""
            SELECT dech.*,
                   CONCAT(doc.first_name, ' ', doc.last_name) as medecin_name,
                   CONCAT(p_created.nom, ' ', p_created.prenom) as created_by_name,
                   CONCAT(p_validated.nom, ' ', p_validated.prenom) as validated_by_name,
                   CONCAT(p_paid.nom, ' ', p_paid.prenom) as paid_by_name
            FROM medecin_interne_decharges dech
            JOIN doctors doc ON dech.id_doctor = doc.id
            LEFT JOIN personnel p_created ON dech.created_by = p_created.id_personnel
            LEFT JOIN personnel p_validated ON dech.validated_by = p_validated.id_personnel
            LEFT JOIN personnel p_paid ON dech.paid_by = p_paid.id_personnel
            WHERE dech.id_decharge = %s
        """, (id_decharge,))
        decharge = cursor.fetchone()

        if not decharge:
            flash('Décharge non trouvée', 'danger')
            return redirect(url_for('medecin_interne_decharges_list'))

        # Actes liés
        cursor.execute("""
            SELECT da.montant_honoraires,
                   a.id_acte,
                   a.patient,
                   a.date_acte,
                   a.nom_acte
            FROM medecin_interne_decharge_actes da
            JOIN medecin_interne_actes a ON da.id_acte = a.id_acte
            WHERE da.id_decharge = %s
            ORDER BY a.date_acte
        """, (id_decharge,))
        actes = cursor.fetchall()

        # Tranches de paiement
        cursor.execute("""
            SELECT t.*,
                   CONCAT(p.nom, ' ', p.prenom) as created_by_name
            FROM medecin_interne_decharge_tranches t
            LEFT JOIN personnel p ON t.created_by = p.id_personnel
            WHERE t.id_decharge = %s
            ORDER BY t.date_paiement, t.created_at
        """, (id_decharge,))
        tranches = cursor.fetchall()

        return render_template(
            'medecin_interne/paiements_interne/detail_decharge.html',
            decharge=decharge,
            actes=actes,
            tranches=tranches,
            title=f"Décharge {decharge['numero_decharge']}"
        )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# LISTE DES DÉCHARGES
# ==============================================================================

@app.route('/medecin-interne/decharges')
@login_required
@handle_errors()

def medecin_interne_decharges_list():
    """Liste de toutes les décharges"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres
        id_doctor = request.args.get('id_doctor', 'all')
        statut = request.args.get('statut', 'all')
        date_debut = request.args.get('date_debut', '')
        date_fin = request.args.get('date_fin', '')

        # Médecins internes
        cursor.execute("""
            SELECT d.id, CONCAT(d.first_name, ' ', d.last_name) as nom_complet
            FROM doctors d
            JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.est_interne = 1
              AND s.name_specialty IN ('ORTHOPÉDIE', 'CHIRURGIE GÉNÉRALE')
            ORDER BY d.last_name
        """)
        medecins = cursor.fetchall()

        # Construction requête
        where_clauses = ["1=1"]
        params = {}

        if id_doctor != 'all':
            where_clauses.append("dech.id_doctor = %(id_doctor)s")
            params['id_doctor'] = id_doctor

        if statut != 'all':
            where_clauses.append("dech.statut = %(statut)s")
            params['statut'] = statut

        if date_debut:
            where_clauses.append("dech.date_decharge >= %(date_debut)s")
            params['date_debut'] = date_debut

        if date_fin:
            where_clauses.append("dech.date_decharge <= %(date_fin)s")
            params['date_fin'] = date_fin

        where_sql = " AND ".join(where_clauses)

        # Liste des décharges
        cursor.execute(f"""
            SELECT 
                dech.*,
                CONCAT(doc.first_name, ' ', doc.last_name) as medecin_name
            FROM medecin_interne_decharges dech
            JOIN doctors doc ON dech.id_doctor = doc.id
            WHERE {where_sql}
            ORDER BY dech.date_decharge DESC, dech.id_decharge DESC
        """, params)
        decharges = cursor.fetchall()

        # Stats
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total_decharges,
                COALESCE(SUM(montant_total), 0) as total_montant,
                COALESCE(SUM(CASE WHEN statut = 'PAYE' THEN montant_total ELSE 0 END), 0) as montant_paye
            FROM medecin_interne_decharges dech
            WHERE {where_sql}
        """, params)
        stats = cursor.fetchone()

        return render_template(
            'medecin_interne/paiements_interne/liste_decharges.html',
            decharges=decharges,
            medecins=medecins,
            stats=stats,
            id_doctor_selected=id_doctor,
            statut_selected=statut,
            date_debut=date_debut,
            date_fin=date_fin,
            title="Décharges de Paiement"
        )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# VALIDER UNE DÉCHARGE
# ==============================================================================

@app.route('/medecin-interne/decharge/<int:id_decharge>/valider', methods=['POST'])
@login_required
@handle_errors()

def medecin_interne_decharge_valider(id_decharge):
    """Valider une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT statut FROM medecin_interne_decharges WHERE id_decharge = %s",
            (id_decharge,)
        )
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404

        if decharge['statut'] != 'BROUILLON':
            return jsonify(
                {'success': False, 'error': 'Seules les décharges en brouillon peuvent être validées'}
            ), 400

        cursor.execute("""
            UPDATE medecin_interne_decharges
            SET statut = 'VALIDE',
                validated_at = NOW(),
                validated_by = %s
            WHERE id_decharge = %s
        """, (g.user['id_personnel'], id_decharge))

        conn.commit()

        return jsonify({
            'success': True,
            'message': 'Décharge validée avec succès'
        })

    except Exception as e:
        conn.rollback()
        app.logger.error(f'Erreur validation décharge: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# GESTION DES TRANCHES DE PAIEMENT
# ==============================================================================

def calculer_solde_decharge_medecin(cursor, id_decharge: int) -> Tuple[Decimal, Decimal, int]:
    """
    Calcule le solde d'une décharge
    Returns: (montant_total, montant_paye_total, nb_tranches)
    """
    cursor.execute(
        "SELECT montant_total FROM medecin_interne_decharges WHERE id_decharge = %s",
        (id_decharge,)
    )
    result = cursor.fetchone()
    if not result:
        return Decimal('0'), Decimal('0'), 0

    montant_total = to_decimal(result['montant_total'])

    # Calculer le total payé via les tranches
    cursor.execute("""
        SELECT COALESCE(SUM(montant_paye), 0) as total_paye,
               COUNT(*) as nb_tranches
        FROM medecin_interne_decharge_tranches
        WHERE id_decharge = %s
    """, (id_decharge,))
    result = cursor.fetchone()
    montant_paye_total = to_decimal(result['total_paye'])
    nb_tranches = int(result['nb_tranches'])

    return montant_total, montant_paye_total, nb_tranches


def mettre_a_jour_statut_decharge_medecin(cursor, id_decharge: int):
    """Met à jour le statut de la décharge selon le solde"""
    montant_total, montant_paye_total, nb_tranches = calculer_solde_decharge_medecin(cursor, id_decharge)
    solde_restant = montant_total - montant_paye_total

    # Déterminer le statut
    if solde_restant <= Decimal('0.01'):  # Totalement payé
        nouveau_statut = 'PAYE'
        # Marquer les actes comme payés
        cursor.execute("""
            UPDATE medecin_interne_actes a
            JOIN medecin_interne_decharge_actes da ON a.id_acte = da.id_acte
            SET a.medecin_paye = 1,
                a.id_decharge_medecin = %s
            WHERE da.id_decharge = %s
        """, (id_decharge, id_decharge))
        paid_at = 'NOW()'
        paid_by = g.user['id_personnel']
    elif montant_paye_total > 0:  # Paiement partiel
        nouveau_statut = 'PAIEMENT_PARTIEL'
        paid_at = 'NULL'
        paid_by = 'NULL'
    else:  # Pas encore de paiement
        cursor.execute("""
            UPDATE medecin_interne_decharges
            SET montant_paye_total = %s,
                solde_restant = %s,
                nb_tranches = %s
            WHERE id_decharge = %s
        """, (montant_paye_total, solde_restant, nb_tranches, id_decharge))
        return

    # Mettre à jour la décharge
    cursor.execute(f"""
        UPDATE medecin_interne_decharges
        SET statut = %s,
            montant_paye_total = %s,
            solde_restant = %s,
            nb_tranches = %s,
            paid_at = {paid_at},
            paid_by = {'%s' if paid_by != 'NULL' else 'NULL'}
        WHERE id_decharge = %s
    """,
        (nouveau_statut, montant_paye_total, solde_restant, nb_tranches,
         paid_by if paid_by != 'NULL' else None, id_decharge) if paid_by != 'NULL'
        else (nouveau_statut, montant_paye_total, solde_restant, nb_tranches, id_decharge)
    )


def generer_numero_tranche_medecin(cursor, id_decharge: int) -> str:
    """Génère un numéro unique de tranche"""
    cursor.execute(
        "SELECT numero_decharge FROM medecin_interne_decharges WHERE id_decharge = %s",
        (id_decharge,)
    )
    result = cursor.fetchone()
    if not result:
        return ""

    numero_decharge = result['numero_decharge']

    cursor.execute(
        "SELECT COUNT(*) as count FROM medecin_interne_decharge_tranches WHERE id_decharge = %s",
        (id_decharge,)
    )
    count = cursor.fetchone()['count']

    return f"{numero_decharge}-T{count + 1:02d}"


@app.route('/medecin-interne/decharge/<int:id_decharge>/ajouter-tranche', methods=['POST'])
@login_required
@handle_errors()

def medecin_interne_decharge_ajouter_tranche(id_decharge):
    """Ajouter une tranche de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Vérifier la décharge
        cursor.execute("""
            SELECT statut, montant_total, montant_paye_total, solde_restant
            FROM medecin_interne_decharges
            WHERE id_decharge = %s
        """, (id_decharge,))
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404

        if decharge['statut'] in ['ANNULE', 'PAYE']:
            return jsonify({
                'success': False,
                'error': 'Impossible d\'ajouter une tranche à une décharge annulée ou déjà payée'
            }), 400

        # Récupérer les données
        data = request.get_json()
        date_paiement = data.get('date_paiement')
        montant_paye = to_decimal(data.get('montant_paye', 0))
        mode_paiement = data.get('mode_paiement', 'ESPECES')
        reference_paiement = data.get('reference_paiement', '').strip()
        observations = data.get('observations', '').strip()

        if montant_paye <= 0:
            return jsonify({'success': False, 'error': 'Le montant doit être supérieur à 0'}), 400

        # Vérifier qu'on ne dépasse pas le solde
        solde_actuel = to_decimal(decharge['montant_total']) - to_decimal(decharge['montant_paye_total'] or 0)
        if montant_paye > solde_actuel + Decimal('0.01'):
            return jsonify({
                'success': False,
                'error': f'Le montant dépasse le solde restant ({float(solde_actuel):.2f} DA)'
            }), 400

        # Générer numéro de tranche
        numero_tranche = generer_numero_tranche_medecin(cursor, id_decharge)

        # Insérer la tranche
        cursor.execute("""
            INSERT INTO medecin_interne_decharge_tranches
            (id_decharge, numero_tranche, date_paiement, montant_paye,
             mode_paiement, reference_paiement, observations, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            id_decharge, numero_tranche, date_paiement, montant_paye,
            mode_paiement, reference_paiement, observations, g.user['id_personnel']
        ))

        # Mettre à jour le statut de la décharge
        mettre_a_jour_statut_decharge_medecin(cursor, id_decharge)

        conn.commit()

        # Récupérer les nouvelles valeurs
        montant_total, montant_paye_total, nb_tranches = calculer_solde_decharge_medecin(cursor, id_decharge)
        solde_restant = montant_total - montant_paye_total

        return jsonify({
            'success': True,
            'message': f'Tranche de {float(montant_paye):.2f} DA enregistrée',
            'montant_paye_total': float(montant_paye_total),
            'solde_restant': float(solde_restant),
            'nb_tranches': nb_tranches
        })

    except Exception as e:
        conn.rollback()
        app.logger.error(f'Erreur ajout tranche: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


@app.route('/medecin-interne/decharge/<int:id_decharge>/tranches')
@login_required
@handle_errors()

def medecin_interne_decharge_tranches(id_decharge):
    """Liste des tranches d'une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT t.*,
                   CONCAT(p.nom, ' ', p.prenom) as created_by_name
            FROM medecin_interne_decharge_tranches t
            LEFT JOIN personnel p ON t.created_by = p.id_personnel
            WHERE t.id_decharge = %s
            ORDER BY t.date_paiement, t.created_at
        """, (id_decharge,))
        tranches = cursor.fetchall()

        return jsonify({
            'success': True,
            'tranches': [dict(t) for t in tranches]
        })

    finally:
        cursor.close()
        conn.close()


@app.route('/medecin-interne/decharge/tranche/<int:id_tranche>/supprimer', methods=['POST'])
@login_required
@handle_errors()

def medecin_interne_tranche_supprimer(id_tranche):
    """Supprimer une tranche de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Récupérer l'id_decharge
        cursor.execute(
            "SELECT id_decharge FROM medecin_interne_decharge_tranches WHERE id_tranche = %s",
            (id_tranche,)
        )
        result = cursor.fetchone()

        if not result:
            return jsonify({'success': False, 'error': 'Tranche non trouvée'}), 404

        id_decharge = result['id_decharge']

        # Vérifier le statut de la décharge
        cursor.execute(
            "SELECT statut FROM medecin_interne_decharges WHERE id_decharge = %s",
            (id_decharge,)
        )
        decharge = cursor.fetchone()

        if decharge['statut'] == 'PAYE':
            return jsonify({
                'success': False,
                'error': 'Impossible de supprimer une tranche d\'une décharge totalement payée'
            }), 400

        # Supprimer la tranche
        cursor.execute(
            "DELETE FROM medecin_interne_decharge_tranches WHERE id_tranche = %s",
            (id_tranche,)
        )

        # Mettre à jour le statut
        mettre_a_jour_statut_decharge_medecin(cursor, id_decharge)

        conn.commit()

        return jsonify({
            'success': True,
            'message': 'Tranche supprimée avec succès'
        })

    except Exception as e:
        conn.rollback()
        app.logger.error(f'Erreur suppression tranche: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# PAYER LE SOLDE TOTAL
# ==============================================================================

@app.route('/medecin-interne/decharge/<int:id_decharge>/payer-total', methods=['POST'])
@login_required
@handle_errors()
@handle_errors()
def medecin_interne_decharge_payer_total(id_decharge):
    """Payer le solde total en une fois"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT statut, montant_total, montant_paye_total, solde_restant
            FROM medecin_interne_decharges
            WHERE id_decharge = %s
        """, (id_decharge,))
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404

        if decharge['statut'] == 'PAYE':
            return jsonify({'success': False, 'error': 'Décharge déjà payée'}), 400

        # Récupérer les données
        data = request.get_json()
        mode_paiement = data.get('mode_paiement', 'ESPECES')
        reference_paiement = data.get('reference_paiement', '').strip()
        observations = data.get('observations', '').strip()

        # Calculer le solde restant
        solde = to_decimal(decharge['montant_total']) - to_decimal(decharge['montant_paye_total'] or 0)

        if solde <= 0:
            return jsonify({'success': False, 'error': 'Aucun solde à payer'}), 400

        # Générer numéro de tranche
        numero_tranche = generer_numero_tranche_medecin(cursor, id_decharge)

        # Ajouter une tranche pour le solde total
        cursor.execute("""
            INSERT INTO medecin_interne_decharge_tranches
            (id_decharge, numero_tranche, date_paiement, montant_paye,
             mode_paiement, reference_paiement, observations, created_by)
            VALUES (%s, %s, CURDATE(), %s, %s, %s, %s, %s)
        """, (
            id_decharge, numero_tranche, solde,
            mode_paiement, reference_paiement,
            f"Paiement du solde total. {observations}".strip(),
            g.user['id_personnel']
        ))

        # Mettre à jour le statut
        mettre_a_jour_statut_decharge_medecin(cursor, id_decharge)

        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Paiement total de {float(solde):.2f} DA enregistré'
        })

    except Exception as e:
        conn.rollback()
        app.logger.error(f'Erreur paiement total: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# GÉNÉRER PDF
# ==============================================================================

@app.route('/medecin-interne/decharge/<int:id_decharge>/pdf')
@login_required
@handle_errors()
@handle_errors()
def medecin_interne_decharge_pdf(id_decharge):
    """Générer le PDF de la décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Info décharge
        cursor.execute("""
            SELECT dech.*,
                   CONCAT(doc.first_name, ' ', doc.last_name) as medecin_name
            FROM medecin_interne_decharges dech
            JOIN doctors doc ON dech.id_doctor = doc.id
            WHERE dech.id_decharge = %s
        """, (id_decharge,))
        decharge = cursor.fetchone()

        if not decharge:
            flash('Décharge non trouvée', 'danger')
            return redirect(url_for('medecin_interne_decharges_list'))

        # Actes liés
        cursor.execute("""
            SELECT da.montant_honoraires,
                   a.id_acte,
                   a.patient,
                   a.date_acte,
                   a.nom_acte
            FROM medecin_interne_decharge_actes da
            JOIN medecin_interne_actes a ON da.id_acte = a.id_acte
            WHERE da.id_decharge = %s
            ORDER BY a.date_acte
        """, (id_decharge,))
        actes = cursor.fetchall()

        # Tranches de paiement
        cursor.execute("""
            SELECT t.*,
                   CONCAT(p.nom, ' ', p.prenom) as created_by_name
            FROM medecin_interne_decharge_tranches t
            LEFT JOIN personnel p ON t.created_by = p.id_personnel
            WHERE t.id_decharge = %s
            ORDER BY t.date_paiement, t.created_at
        """, (id_decharge,))
        tranches = cursor.fetchall()

        html = render_template(
            'medecin_interne/paiements_interne/decharge_pdf.html',
            decharge=decharge,
            actes=actes,
            tranches=tranches,
            date_generation=datetime.now().strftime('%d/%m/%Y %H:%M')
        )

        response = make_response(html)
        response.headers['Content-Type'] = 'text/html'

        return response

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# ANNULER UNE DÉCHARGE
# ==============================================================================

@app.route('/medecin-interne/decharge/<int:id_decharge>/annuler', methods=['POST'])
@login_required
@handle_errors()
@handle_errors()
def medecin_interne_decharge_annuler(id_decharge):
    """Annuler une décharge"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT statut FROM medecin_interne_decharges WHERE id_decharge = %s",
            (id_decharge,)
        )
        decharge = cursor.fetchone()

        if not decharge:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404

        if decharge['statut'] == 'PAYE':
            return jsonify({'success': False, 'error': 'Impossible d\'annuler une décharge payée'}), 400

        # Annuler la décharge
        cursor.execute("""
            UPDATE medecin_interne_decharges
            SET statut = 'ANNULE',
                cancelled_at = NOW(),
                cancelled_by = %s
            WHERE id_decharge = %s
        """, (g.user['id_personnel'], id_decharge))

        # Libérer les actes
        cursor.execute("""
            UPDATE medecin_interne_actes a
            JOIN medecin_interne_decharge_actes da ON a.id_acte = da.id_acte
            SET a.medecin_paye = 0,
                a.id_decharge_medecin = NULL
            WHERE da.id_decharge = %s
        """, (id_decharge,))

        conn.commit()

        return jsonify({
            'success': True,
            'message': 'Décharge annulée avec succès. Les actes sont à nouveau disponibles.'
        })

    except Exception as e:
        conn.rollback()
        app.logger.error(f'Erreur annulation décharge: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# API - VÉRIFICATION DES ACTES DISPONIBLES
# ==============================================================================

@app.route('/api/medecin-interne/verifier-actes-disponibles', methods=['POST'])
@login_required
def api_verifier_actes_disponibles():
    """
    Vérifie quels actes sont déjà dans une décharge active
    Retourne la liste des IDs d'actes indisponibles
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        data = request.get_json()
        acte_ids = data.get('acte_ids', [])

        if not acte_ids:
            return jsonify({
                'success': True,
                'actes_indisponibles': [],
                'details': []
            })

        # Vérifier quels actes sont déjà dans une décharge
        placeholders = ','.join(['%s'] * len(acte_ids))
        cursor.execute(f"""
            SELECT 
                a.id_acte,
                a.id_decharge_medecin,
                dech.numero_decharge,
                dech.statut,
                dech.date_decharge,
                CONCAT(doc.first_name, ' ', doc.last_name) as medecin_name
            FROM medecin_interne_actes a
            LEFT JOIN medecin_interne_decharges dech ON a.id_decharge_medecin = dech.id_decharge
            LEFT JOIN doctors doc ON a.id_doctor = doc.id
            WHERE a.id_acte IN ({placeholders})
              AND a.id_decharge_medecin IS NOT NULL
              AND dech.statut NOT IN ('ANNULE')
        """, acte_ids)

        actes_indisponibles = cursor.fetchall()

        return jsonify({
            'success': True,
            'actes_indisponibles': [a['id_acte'] for a in actes_indisponibles],
            'details': [
                {
                    'id_acte': a['id_acte'],
                    'numero_decharge': a['numero_decharge'],
                    'statut': a['statut'],
                    'date_decharge': a['date_decharge'].strftime('%d/%m/%Y') if a['date_decharge'] else None,
                    'medecin': a['medecin_name']
                }
                for a in actes_indisponibles
            ]
        })

    except Exception as e:
        app.logger.error(f'Erreur vérification actes: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# API - STATISTIQUES DES DÉCHARGES PAR MÉDECIN
# ==============================================================================

@app.route('/api/medecin-interne/stats-decharges/<int:id_doctor>')
@login_required
def api_stats_decharges_medecin(id_doctor):
    """Retourne les statistiques de décharges pour un médecin"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        date_debut = request.args.get('date_debut', '')
        date_fin = request.args.get('date_fin', '')

        where_clauses = ['id_doctor = %s']
        params = [id_doctor]

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
                SUM(nb_actes) as total_actes,
                SUM(CASE WHEN statut = 'BROUILLON' THEN 1 ELSE 0 END) as nb_brouillon,
                SUM(CASE WHEN statut = 'VALIDE' THEN 1 ELSE 0 END) as nb_valide,
                SUM(CASE WHEN statut = 'PAIEMENT_PARTIEL' THEN 1 ELSE 0 END) as nb_partiel,
                SUM(CASE WHEN statut = 'PAYE' THEN 1 ELSE 0 END) as nb_paye,
                SUM(CASE WHEN statut = 'ANNULE' THEN 1 ELSE 0 END) as nb_annule
            FROM medecin_interne_decharges
            WHERE {where_sql}
        """, params)

        stats = cursor.fetchone()

        # Actes disponibles pour nouvelle décharge
        cursor.execute("""
            SELECT COUNT(*) as nb_disponibles,
                   COALESCE(SUM(part_medecin), 0) as montant_disponible
            FROM medecin_interne_actes
            WHERE id_doctor = %s
              AND medecin_paye = 0
              AND id_decharge_medecin IS NULL
        """, (id_doctor,))

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
                'actes': {
                    'total_decharges': int(stats['total_actes'] or 0),
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
# API - HISTORIQUE DES DÉCHARGES D'UN ACTE
# ==============================================================================

@app.route('/api/medecin-interne/acte/<int:id_acte>/historique-decharges')
@login_required
def api_acte_historique_decharges(id_acte):
    """Retourne l'historique des décharges d'un acte"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Décharge actuelle
        cursor.execute("""
            SELECT 
                a.id_decharge_medecin,
                a.medecin_paye,
                dech.numero_decharge,
                dech.statut,
                dech.date_decharge,
                dech.montant_total,
                da.montant_honoraires
            FROM medecin_interne_actes a
            LEFT JOIN medecin_interne_decharges dech ON a.id_decharge_medecin = dech.id_decharge
            LEFT JOIN medecin_interne_decharge_actes da ON a.id_acte = da.id_acte 
                AND da.id_decharge = dech.id_decharge
            WHERE a.id_acte = %s
        """, (id_acte,))

        decharge_actuelle = cursor.fetchone()

        # Historique
        cursor.execute("""
            SELECT 
                dech.id_decharge,
                dech.numero_decharge,
                dech.statut,
                dech.date_decharge,
                da.montant_honoraires,
                dech.created_at,
                CONCAT(p.nom, ' ', p.prenom) as created_by_name
            FROM medecin_interne_decharge_actes da
            JOIN medecin_interne_decharges dech ON da.id_decharge = dech.id_decharge
            LEFT JOIN personnel p ON dech.created_by = p.id_personnel
            WHERE da.id_acte = %s
            ORDER BY dech.created_at DESC
        """, (id_acte,))

        historique = cursor.fetchall()

        return jsonify({
            'success': True,
            'decharge_actuelle': dict(decharge_actuelle) if decharge_actuelle else None,
            'historique': [dict(h) for h in historique]
        })

    except Exception as e:
        app.logger.error(f'Erreur historique décharges acte: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

    finally:
        cursor.close()
        conn.close()