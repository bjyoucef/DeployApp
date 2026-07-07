# app/anesthesie_honoraires/anesthesie_decharges.py
"""
Module de gestion des décharges et paiements par tranche
pour les anesthésistes et réanimateurs.
"""
import io
from datetime import datetime
from decimal import Decimal

from flask import (
    render_template, request, jsonify, redirect, url_for,
    flash, g, make_response
)
from num2words import num2words
from xhtml2pdf import pisa

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


# ==============================================================================
# HELPERS
# ==============================================================================

def _to_decimal(value, default=0):
    if value is None or value == '':
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(str(default))


def _generer_numero_decharge():
    now = datetime.now()
    prefix = f"DAN-{now.year}{now.month:02d}"
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM anesthesie_decharges WHERE numero_decharge LIKE %s",
            (f"{prefix}%",)
        )
        cnt = cursor.fetchone()['cnt']
        return f"{prefix}-{cnt + 1:04d}"
    finally:
        cursor.close()
        conn.close()


def _generer_numero_tranche(cursor, id_decharge):
    cursor.execute(
        "SELECT numero_decharge FROM anesthesie_decharges WHERE id_decharge = %s",
        (id_decharge,)
    )
    r = cursor.fetchone()
    if not r:
        return ""
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM anesthesie_decharge_tranches WHERE id_decharge = %s",
        (id_decharge,)
    )
    cnt = cursor.fetchone()['cnt']
    return f"{r['numero_decharge']}-T{cnt + 1:02d}"


SOURCE_TABLE_MAP = {
    'BLOC': {
        'table': 'location_bloc_dossier_anesthesie',
        'pk': 'id_dossier_anesthesie',
        'date_join': 'location_bloc_dossier_patient',
        'date_fk': 'id_dossier',
        'date_col': 'location_date',
        'patient_col': 'patient',
        'paid_col': 'honoraires_payes',
    },
    'ACCOUCHEMENT': {
        'table': 'accouchement_dossier_anesthesie',
        'pk': 'id_dossier_anesthesie',
        'date_join': 'accouchement_dossiers',
        'date_fk': 'id_dossier',
        'date_col': 'date_accouchement',
        'patient_col': 'patiente',
        'paid_col': 'honoraires_payes',
    },
    'KT': {
        'table': 'kt_dossier_anesthesie',
        'pk': 'id_dossier_anesthesie',
        'date_join': 'kt_dossier_patient',
        'date_fk': 'id_dossier',
        'date_col': 'acte_date',
        'patient_col': 'patient',
        'paid_col': 'honoraires_payes',
    },
    'MEDECIN_INTERNE': {
        'table': 'medecin_interne_anesthesie',
        'pk': 'id_anesthesie',
        'date_join': 'medecin_interne_actes',
        'date_fk': 'id_acte',
        'date_col': 'date_acte',
        'patient_col': 'patient',
        'paid_col': 'anesthesiste_paye',
    },
}


def _calculer_solde(cursor, id_decharge):
    cursor.execute(
        "SELECT montant_total FROM anesthesie_decharges WHERE id_decharge = %s",
        (id_decharge,)
    )
    r = cursor.fetchone()
    if not r:
        return Decimal('0'), Decimal('0'), 0
    montant_total = _to_decimal(r['montant_total'])

    cursor.execute("""
        SELECT COALESCE(SUM(montant_paye), 0) as total_paye,
               COUNT(*) as nb
        FROM anesthesie_decharge_tranches
        WHERE id_decharge = %s AND est_annule = 0
    """, (id_decharge,))
    r2 = cursor.fetchone()
    return montant_total, _to_decimal(r2['total_paye']), int(r2['nb'])


def _maj_statut_decharge(cursor, id_decharge):
    montant_total, paye, nb = _calculer_solde(cursor, id_decharge)
    solde = montant_total - paye

    if solde <= Decimal('0.01'):
        statut = 'PAYE'
        # Mark acts as paid
        cursor.execute("""
            SELECT source_acte, id_acte_source
            FROM anesthesie_decharge_actes WHERE id_decharge = %s
        """, (id_decharge,))
        for row in cursor.fetchall():
            info = SOURCE_TABLE_MAP[row['source_acte']]
            cursor.execute(
                f"UPDATE {info['table']} SET {info['paid_col']} = 1 WHERE {info['pk']} = %s",
                (row['id_acte_source'],)
            )
        cursor.execute("""
            UPDATE anesthesie_decharges
            SET statut = %s, montant_paye_total = %s, solde_restant = %s,
                nb_tranches = %s, paid_at = NOW(), paid_by = %s
            WHERE id_decharge = %s
        """, (statut, paye, solde, nb, g.user['id_personnel'], id_decharge))
    elif paye > 0:
        statut = 'PAIEMENT_PARTIEL'
        cursor.execute("""
            UPDATE anesthesie_decharges
            SET statut = %s, montant_paye_total = %s, solde_restant = %s,
                nb_tranches = %s, paid_at = NULL, paid_by = NULL
            WHERE id_decharge = %s
        """, (statut, paye, solde, nb, id_decharge))
    else:
        cursor.execute("""
            UPDATE anesthesie_decharges
            SET montant_paye_total = %s, solde_restant = %s, nb_tranches = %s
            WHERE id_decharge = %s
        """, (paye, solde, nb, id_decharge))




# ==============================================================================
# CRÉER UNE DÉCHARGE
# ==============================================================================

@app.route('/anesthesie/honoraires/decharge/creer', methods=['GET', 'POST'])
@login_required
@handle_errors()
def anesthesie_decharge_creer():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if request.method == 'GET':
            id_personnel = request.args.get('id_personnel')
            date_debut = request.args.get('date_debut', '')
            date_fin = request.args.get('date_fin', '')

            if not id_personnel:
                flash('Personnel non spécifié', 'danger')
                return redirect(url_for('anesthesie_honoraires_global'))

            cursor.execute("""
                SELECT p.id_personnel_anesthesie,
                       CONCAT(p.prenom, ' ', p.nom) as nom_complet,
                       t.nom_type
                FROM anesthesie_personnel p
                JOIN anesthesie_intervenant_type t ON p.id_type_intervenant = t.id_type_intervenant
                WHERE p.id_personnel_anesthesie = %s
            """, (id_personnel,))
            personnel = cursor.fetchone()
            if not personnel:
                flash('Personnel non trouvé', 'danger')
                return redirect(url_for('anesthesie_honoraires_global'))

            # Fetch unpaid acts
            actes = []
            for source_key, info in SOURCE_TABLE_MAP.items():
                query = f"""
                    SELECT a.{info['pk']} as id_source,
                           '{source_key}' as source,
                           d.{info['patient_col']} as patient,
                           d.{info['date_col']} as date_intervention,
                           aa.nom_acte,
                           a.honoraires_calcules
                    FROM {info['table']} a
                    JOIN {info['date_join']} d ON a.{info['date_fk']} = d.{info['date_fk']}
                    JOIN anesthesie_type_acte aa ON a.id_acte_anesthesie = aa.id_acte_anesthesie
                    WHERE a.id_personnel_anesthesie = %(id_personnel)s
                      AND a.{info['paid_col']} = 0
                      AND a.id_decharge_anesthesie IS NULL
                """
                params = {'id_personnel': id_personnel}
                if date_debut:
                    query += f" AND d.{info['date_col']} >= %(date_debut)s"
                    params['date_debut'] = date_debut
                if date_fin:
                    query += f" AND d.{info['date_col']} <= %(date_fin)s"
                    params['date_fin'] = date_fin

                if source_key == 'MEDECIN_INTERNE':
                    query += " AND (a.est_annule IS NULL OR a.est_annule = 0)"

                query += f" ORDER BY d.{info['date_col']}"
                try:
                    cursor.execute(query, params)
                    actes.extend(cursor.fetchall())
                except Exception as e:
                    app.logger.warning(f"Erreur récup actes {source_key}: {e}")

            return render_template(
                'anesthesie_honoraires/decharges/creer_decharge.html',
                personnel=personnel,
                actes=actes,
                date_debut=date_debut,
                date_fin=date_fin,
                title="Nouvelle Décharge Anesthésie"
            )

        # POST
        id_personnel = request.form.get('id_personnel')
        date_decharge = request.form.get('date_decharge')
        mode_paiement = request.form.get('mode_paiement', 'ESPECES')
        reference_paiement = request.form.get('reference_paiement', '').strip()
        observations = request.form.get('observations', '').strip()
        actes_raw = request.form.getlist('actes[]')

        if not actes_raw:
            flash('Veuillez sélectionner au moins un acte', 'danger')
            return redirect(request.referrer)

        # Parse composite keys "SOURCE:ID"
        selected = []
        for item in actes_raw:
            parts = item.split(':')
            if len(parts) == 2:
                selected.append({'source': parts[0], 'id': int(parts[1])})

        # Verify none already in a decharge
        for sel in selected:
            info = SOURCE_TABLE_MAP.get(sel['source'])
            if not info:
                continue
            cursor.execute(
                f"SELECT id_decharge_anesthesie FROM {info['table']} WHERE {info['pk']} = %s",
                (sel['id'],)
            )
            row = cursor.fetchone()
            if row and row['id_decharge_anesthesie']:
                flash(f"❌ L'acte {sel['source']} #{sel['id']} est déjà dans une décharge", 'danger')
                return redirect(request.referrer)

        # Calculate total
        montant_total = Decimal('0')
        valid_actes = []
        for sel in selected:
            info = SOURCE_TABLE_MAP.get(sel['source'])
            if not info:
                continue
            cursor.execute(
                f"SELECT honoraires_calcules FROM {info['table']} WHERE {info['pk']} = %s AND {info['paid_col']} = 0",
                (sel['id'],)
            )
            row = cursor.fetchone()
            if row:
                montant = _to_decimal(row['honoraires_calcules'])
                montant_total += montant
                valid_actes.append({**sel, 'montant': montant})

        if not valid_actes:
            flash('Aucun acte valide sélectionné', 'danger')
            return redirect(request.referrer)

        numero = _generer_numero_decharge()

        cursor.execute("""
            INSERT INTO anesthesie_decharges
            (numero_decharge, id_personnel_anesthesie, date_decharge,  montant_total, solde_restant, nb_actes, mode_paiement,
             reference_paiement, observations, statut, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BROUILLON', %s)
        """, (
            numero, id_personnel, date_decharge, montant_total, montant_total, len(valid_actes), mode_paiement,
            reference_paiement, observations, g.user['id_personnel']
        ))
        id_decharge = cursor.lastrowid

        for acte in valid_actes:
            cursor.execute("""
                INSERT INTO anesthesie_decharge_actes
                (id_decharge, source_acte, id_acte_source, montant_honoraires)
                VALUES (%s, %s, %s, %s)
            """, (id_decharge, acte['source'], acte['id'], acte['montant']))

            info = SOURCE_TABLE_MAP[acte['source']]
            cursor.execute(
                f"UPDATE {info['table']} SET id_decharge_anesthesie = %s WHERE {info['pk']} = %s",
                (id_decharge, acte['id'])
            )

        conn.commit()
        flash(f'✅ Décharge {numero} créée ({len(valid_actes)} actes, {montant_total:.2f} DA)', 'success')
        return redirect(url_for('anesthesie_decharge_detail', id_decharge=id_decharge))

    except Exception as e:
        conn.rollback()
        app.logger.error(f'Erreur création décharge anesthésie: {e}')
        flash(f'❌ Erreur: {str(e)}', 'danger')
        return redirect(url_for('anesthesie_honoraires_global'))
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# DETAIL D'UNE DÉCHARGE
# ==============================================================================

@app.route('/anesthesie/honoraires/decharge/<int:id_decharge>')
@login_required
@handle_errors()
def anesthesie_decharge_detail(id_decharge):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT dech.*,
                   CONCAT(p.prenom, ' ', p.nom) as personnel_name,
                   ti.nom_type as type_intervenant,
                   CONCAT(pc.nom, ' ', pc.prenom) as created_by_name,
                   CONCAT(pv.nom, ' ', pv.prenom) as validated_by_name,
                   CONCAT(pp.nom, ' ', pp.prenom) as paid_by_name,
                   CONCAT(pa.nom, ' ', pa.prenom) as annule_by_name
            FROM anesthesie_decharges dech
            JOIN anesthesie_personnel p ON dech.id_personnel_anesthesie = p.id_personnel_anesthesie
            JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
            LEFT JOIN personnel pc ON dech.created_by = pc.id_personnel
            LEFT JOIN personnel pv ON dech.validated_by = pv.id_personnel
            LEFT JOIN personnel pp ON dech.paid_by = pp.id_personnel
            LEFT JOIN personnel pa ON dech.annule_par = pa.id_personnel
            WHERE dech.id_decharge = %s
        """, (id_decharge,))
        decharge = cursor.fetchone()
        if not decharge:
            flash('Décharge non trouvée', 'danger')
            return redirect(url_for('anesthesie_decharges_list'))

        # Actes liés
        cursor.execute("""
            SELECT da.source_acte, da.id_acte_source, da.montant_honoraires
            FROM anesthesie_decharge_actes da
            WHERE da.id_decharge = %s
        """, (id_decharge,))
        actes_raw = cursor.fetchall()

        actes = []
        for a in actes_raw:
            info = SOURCE_TABLE_MAP.get(a['source_acte'])
            if not info:
                continue
            try:
                cursor.execute(f"""
                    SELECT d.{info['patient_col']} as patient,
                           d.{info['date_col']} as date_intervention,
                           aa.nom_acte
                    FROM {info['table']} act
                    JOIN {info['date_join']} d ON act.{info['date_fk']} = d.{info['date_fk']}
                    JOIN anesthesie_type_acte aa ON act.id_acte_anesthesie = aa.id_acte_anesthesie
                    WHERE act.{info['pk']} = %s
                """, (a['id_acte_source'],))
                detail = cursor.fetchone()
                actes.append({
                    'source_acte': a['source_acte'],
                    'id_acte_source': a['id_acte_source'],
                    'montant_honoraires': a['montant_honoraires'],
                    'patient': detail['patient'] if detail else 'N/A',
                    'date_intervention': detail['date_intervention'] if detail else None,
                    'nom_acte': detail['nom_acte'] if detail else 'N/A',
                })
            except Exception:
                actes.append({
                    'source_acte': a['source_acte'],
                    'id_acte_source': a['id_acte_source'],
                    'montant_honoraires': a['montant_honoraires'],
                    'patient': 'N/A', 'date_intervention': None, 'nom_acte': 'N/A',
                })

        # Tranches
        cursor.execute("""
            SELECT t.*,
                   CONCAT(p.nom, ' ', p.prenom) as created_by_name,
                   CONCAT(pa.nom, ' ', pa.prenom) as annule_by_name
            FROM anesthesie_decharge_tranches t
            LEFT JOIN personnel p ON t.created_by = p.id_personnel
            LEFT JOIN personnel pa ON t.annule_par = pa.id_personnel
            WHERE t.id_decharge = %s
            ORDER BY t.date_paiement, t.created_at
        """, (id_decharge,))
        tranches = cursor.fetchall()

        return render_template(
            'anesthesie_honoraires/decharges/detail_decharge.html',
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

@app.route('/anesthesie/honoraires/decharges')
@login_required
@handle_errors()
def anesthesie_decharges_list():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        id_personnel = request.args.get('id_personnel', 'all')
        statut = request.args.get('statut', 'all')
        date_debut = request.args.get('date_debut', '')
        date_fin = request.args.get('date_fin', '')
        page = int(request.args.get('page', 1))
        per_page = 20

        cursor.execute("""
            SELECT p.id_personnel_anesthesie,
                   CONCAT(p.prenom, ' ', p.nom) as nom_complet,
                   t.nom_type
            FROM anesthesie_personnel p
            JOIN anesthesie_intervenant_type t ON p.id_type_intervenant = t.id_type_intervenant
            WHERE p.est_actif = 1
            ORDER BY t.nom_type, p.nom
        """)
        personnel_list = cursor.fetchall()

        where = ["1=1"]
        params = {}
        if id_personnel != 'all':
            where.append("dech.id_personnel_anesthesie = %(id_personnel)s")
            params['id_personnel'] = id_personnel
        if statut != 'all':
            where.append("dech.statut = %(statut)s")
            params['statut'] = statut
        if date_debut:
            where.append("dech.date_decharge >= %(date_debut)s")
            params['date_debut'] = date_debut
        if date_fin:
            where.append("dech.date_decharge <= %(date_fin)s")
            params['date_fin'] = date_fin

        where_sql = " AND ".join(where)

        # Count for pagination
        cursor.execute(f"""
            SELECT COUNT(*) as cnt
            FROM anesthesie_decharges dech
            WHERE {where_sql}
        """, params)
        total_count = cursor.fetchone()['cnt']
        import math
        total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page

        cursor.execute(f"""
            SELECT dech.*,
                   CONCAT(p.prenom, ' ', p.nom) as personnel_name,
                   ti.nom_type as type_intervenant
            FROM anesthesie_decharges dech
            JOIN anesthesie_personnel p ON dech.id_personnel_anesthesie = p.id_personnel_anesthesie
            JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
            WHERE {where_sql}
            ORDER BY dech.date_decharge DESC, dech.id_decharge DESC
            LIMIT {per_page} OFFSET {offset}
        """, params)
        decharges = cursor.fetchall()

        cursor.execute(f"""
            SELECT COUNT(*) as total,
                   COALESCE(SUM(montant_total), 0) as montant_total,
                   COALESCE(SUM(montant_paye_total), 0) as montant_paye,
                   COALESCE(SUM(solde_restant), 0) as solde
            FROM anesthesie_decharges dech
            WHERE {where_sql}
        """, params)
        stats = cursor.fetchone()

        return render_template(
            'anesthesie_honoraires/decharges/liste_decharges.html',
            decharges=decharges,
            personnel_list=personnel_list,
            stats=stats,
            id_personnel_selected=id_personnel,
            statut_selected=statut,
            date_debut=date_debut,
            date_fin=date_fin,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_count=total_count,
            title="Décharges Anesthésie"
        )
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# VALIDER UNE DÉCHARGE
# ==============================================================================

@app.route('/anesthesie/honoraires/decharge/<int:id_decharge>/valider', methods=['POST'])
@login_required
@handle_errors()
def anesthesie_decharge_valider(id_decharge):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT statut FROM anesthesie_decharges WHERE id_decharge = %s",
            (id_decharge,)
        )
        dech = cursor.fetchone()
        if not dech:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404
        if dech['statut'] != 'BROUILLON':
            return jsonify({'success': False, 'error': 'Seules les décharges en brouillon peuvent être validées'}), 400

        cursor.execute("""
            UPDATE anesthesie_decharges
            SET statut = 'VALIDE', validated_at = NOW(), validated_by = %s
            WHERE id_decharge = %s
        """, (g.user['id_personnel'], id_decharge))
        conn.commit()
        return jsonify({'success': True, 'message': 'Décharge validée'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# AJOUTER UNE TRANCHE DE PAIEMENT
# ==============================================================================

@app.route('/anesthesie/honoraires/decharge/<int:id_decharge>/tranche', methods=['POST'])
@login_required
@handle_errors()
def anesthesie_decharge_ajouter_tranche(id_decharge):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT statut, montant_total, montant_paye_total
            FROM anesthesie_decharges WHERE id_decharge = %s
        """, (id_decharge,))
        dech = cursor.fetchone()
        if not dech:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404
        if dech['statut'] in ['ANNULE', 'PAYE']:
            return jsonify({'success': False, 'error': 'Impossible d\'ajouter à cette décharge'}), 400

        data = request.get_json()
        date_paiement = data.get('date_paiement')
        montant = _to_decimal(data.get('montant_paye', 0))
        mode = data.get('mode_paiement', 'ESPECES')
        ref = data.get('reference_paiement', '').strip()
        obs = data.get('observations', '').strip()

        if montant <= 0:
            return jsonify({'success': False, 'error': 'Montant invalide'}), 400

        solde = _to_decimal(dech['montant_total']) - _to_decimal(dech['montant_paye_total'] or 0)
        if montant > solde + Decimal('0.01'):
            return jsonify({
                'success': False,
                'error': f'Montant dépasse le solde ({float(solde):.2f} DA)'
            }), 400

        numero = _generer_numero_tranche(cursor, id_decharge)

        cursor.execute("""
            INSERT INTO anesthesie_decharge_tranches
            (id_decharge, numero_tranche, date_paiement, montant_paye,
             mode_paiement, reference_paiement, observations, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (id_decharge, numero, date_paiement, montant, mode, ref, obs,
              g.user['id_personnel']))

        _maj_statut_decharge(cursor, id_decharge)
        conn.commit()

        mt, mp, nb = _calculer_solde(cursor, id_decharge)
        return jsonify({
            'success': True,
            'message': f'Tranche de {float(montant):.2f} DA enregistrée',
            'montant_paye_total': float(mp),
            'solde_restant': float(mt - mp),
            'nb_tranches': nb
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# ANNULER UNE DÉCHARGE
# ==============================================================================

@app.route('/anesthesie/honoraires/decharge/<int:id_decharge>/annuler', methods=['POST'])
@login_required
@handle_errors()
def anesthesie_decharge_annuler(id_decharge):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        data = request.get_json()
        motif = data.get('motif', '').strip()
        if not motif:
            return jsonify({'success': False, 'error': 'Motif obligatoire'}), 400

        cursor.execute(
            "SELECT statut FROM anesthesie_decharges WHERE id_decharge = %s",
            (id_decharge,)
        )
        dech = cursor.fetchone()
        if not dech:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404
        if dech['statut'] == 'ANNULE':
            return jsonify({'success': False, 'error': 'Décharge déjà annulée'}), 400

        # Release all acts
        cursor.execute(
            "SELECT source_acte, id_acte_source FROM anesthesie_decharge_actes WHERE id_decharge = %s",
            (id_decharge,)
        )
        for row in cursor.fetchall():
            info = SOURCE_TABLE_MAP.get(row['source_acte'])
            if info:
                cursor.execute(
                    f"UPDATE {info['table']} SET {info['paid_col']} = 0, id_decharge_anesthesie = NULL WHERE {info['pk']} = %s",
                    (row['id_acte_source'],)
                )

        cursor.execute("""
            UPDATE anesthesie_decharges
            SET statut = 'ANNULE', est_annule = 1, annule_par = %s,
                annule_le = NOW(), motif_annulation = %s
            WHERE id_decharge = %s
        """, (g.user['id_personnel'], motif, id_decharge))

        conn.commit()
        return jsonify({'success': True, 'message': 'Décharge annulée'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# ANNULER UNE TRANCHE
# ==============================================================================

@app.route('/anesthesie/honoraires/decharge/tranche/<int:id_tranche>/annuler', methods=['POST'])
@login_required
@handle_errors()
def anesthesie_tranche_annuler(id_tranche):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        data = request.get_json()
        motif = data.get('motif', '').strip()
        if not motif:
            return jsonify({'success': False, 'error': 'Motif obligatoire'}), 400

        cursor.execute(
            "SELECT id_decharge, est_annule FROM anesthesie_decharge_tranches WHERE id_tranche = %s",
            (id_tranche,)
        )
        tranche = cursor.fetchone()
        if not tranche:
            return jsonify({'success': False, 'error': 'Tranche non trouvée'}), 404
        if tranche['est_annule']:
            return jsonify({'success': False, 'error': 'Tranche déjà annulée'}), 400

        cursor.execute("""
            UPDATE anesthesie_decharge_tranches
            SET est_annule = 1, annule_par = %s, annule_le = NOW(), motif_annulation = %s
            WHERE id_tranche = %s
        """, (g.user['id_personnel'], motif, id_tranche))

        # Recalculate decharge status
        id_decharge = tranche['id_decharge']

        # If decharge was PAYE, revert acts paid status
        cursor.execute(
            "SELECT statut FROM anesthesie_decharges WHERE id_decharge = %s",
            (id_decharge,)
        )
        dech = cursor.fetchone()
        if dech and dech['statut'] == 'PAYE':
            cursor.execute(
                "SELECT source_acte, id_acte_source FROM anesthesie_decharge_actes WHERE id_decharge = %s",
                (id_decharge,)
            )
            for row in cursor.fetchall():
                info = SOURCE_TABLE_MAP.get(row['source_acte'])
                if info:
                    cursor.execute(
                        f"UPDATE {info['table']} SET {info['paid_col']} = 0 WHERE {info['pk']} = %s",
                        (row['id_acte_source'],)
                    )

        _maj_statut_decharge(cursor, id_decharge)
        conn.commit()

        mt, mp, nb = _calculer_solde(cursor, id_decharge)
        return jsonify({
            'success': True,
            'message': 'Tranche annulée',
            'montant_paye_total': float(mp),
            'solde_restant': float(mt - mp),
            'nb_tranches': nb
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# EXPORT PDF D'UNE DÉCHARGE
# ==============================================================================

@app.route('/anesthesie/honoraires/decharge/<int:id_decharge>/pdf')
@login_required
@handle_errors()
def anesthesie_decharge_pdf(id_decharge):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT dech.*,
                   CONCAT(p.prenom, ' ', p.nom) as personnel_name,
                   ti.nom_type as type_intervenant,
                   CONCAT(pc.nom, ' ', pc.prenom) as created_by_name
            FROM anesthesie_decharges dech
            JOIN anesthesie_personnel p ON dech.id_personnel_anesthesie = p.id_personnel_anesthesie
            JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
            LEFT JOIN personnel pc ON dech.created_by = pc.id_personnel
            WHERE dech.id_decharge = %s
        """, (id_decharge,))
        decharge = cursor.fetchone()
        if not decharge:
            flash('Décharge non trouvée', 'danger')
            return redirect(url_for('anesthesie_decharges_list'))

        # Actes
        cursor.execute(
            "SELECT source_acte, id_acte_source, montant_honoraires FROM anesthesie_decharge_actes WHERE id_decharge = %s",
            (id_decharge,)
        )
        actes_raw = cursor.fetchall()
        actes = []
        for a in actes_raw:
            info = SOURCE_TABLE_MAP.get(a['source_acte'])
            if not info:
                continue
            try:
                cursor.execute(f"""
                    SELECT d.{info['patient_col']} as patient,
                           d.{info['date_col']} as date_intervention,
                           aa.nom_acte
                    FROM {info['table']} act
                    JOIN {info['date_join']} d ON act.{info['date_fk']} = d.{info['date_fk']}
                    JOIN anesthesie_type_acte aa ON act.id_acte_anesthesie = aa.id_acte_anesthesie
                    WHERE act.{info['pk']} = %s
                """, (a['id_acte_source'],))
                detail = cursor.fetchone()
                actes.append({
                    'source_acte': a['source_acte'],
                    'montant_honoraires': a['montant_honoraires'],
                    'patient': detail['patient'] if detail else 'N/A',
                    'date_intervention': detail['date_intervention'] if detail else None,
                    'nom_acte': detail['nom_acte'] if detail else 'N/A',
                })
            except Exception:
                actes.append({
                    'source_acte': a['source_acte'],
                    'montant_honoraires': a['montant_honoraires'],
                    'patient': 'N/A', 'date_intervention': None, 'nom_acte': 'N/A',
                })

        # Tranches
        cursor.execute("""
            SELECT t.*, CONCAT(p.nom, ' ', p.prenom) as created_by_name
            FROM anesthesie_decharge_tranches t
            LEFT JOIN personnel p ON t.created_by = p.id_personnel
            WHERE t.id_decharge = %s AND t.est_annule = 0
            ORDER BY t.date_paiement
        """, (id_decharge,))
        tranches = cursor.fetchall()

        # Amount in words
        try:
            amount_words = num2words(float(decharge['montant_total']), lang='fr').upper()
        except Exception:
            amount_words = ''

        html = render_template(
            'anesthesie_honoraires/decharges/decharge_pdf.html',
            decharge=decharge,
            actes=actes,
            tranches=tranches,
            amount_words=amount_words
        )

        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
        if pisa_status.err:
            flash('Erreur génération PDF', 'danger')
            return redirect(url_for('anesthesie_decharge_detail', id_decharge=id_decharge))

        pdf_buffer.seek(0)
        response = make_response(pdf_buffer.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=decharge_{decharge["numero_decharge"]}.pdf'
        return response
    finally:
        cursor.close()
        conn.close()
