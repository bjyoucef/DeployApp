"""
Routes QR Code pour les dossiers.
- Scan public (smartphone)
- Impression étiquette individuelle
- Impression étiquettes en masse
- Sortie temporaire / Retour / Désarchivage
- Historique des mouvements
"""

import os
import base64
from io import BytesIO
from flask import render_template, redirect, url_for, flash, request, make_response, jsonify, g, current_app, session
from xhtml2pdf import pisa

from app import app, get_db_connection
from app.auth import login_required
from app.error import handle_errors
from app.utils.qr_utils import (
    generer_qr_base64,
    MODULE_TABLE_MAP,
    URL_TO_SOURCE_MODULE,
    SOURCE_MODULE_TO_URL,
    MODULE_LABELS,
)
from app.archivage.utils import log_historique


# =====================================================================
# ROUTE PUBLIQUE — Scan QR Code Dossier (smartphone)
# =====================================================================

@app.route('/dossier/scan/<string:module_url>/<string:qr_uuid>')
def dossier_scan(module_url, qr_uuid):
    """
    Page publique affichée lors du scan d'un QR Code dossier.
    Affiche les infos du dossier, le statut de paiement, et la localisation si archivé.
    """
    if module_url not in MODULE_TABLE_MAP:
        return render_template('archivage/scan_dossier.html', error="Module invalide"), 404

    table, pk, patient_col, date_col, doctor_col = MODULE_TABLE_MAP[module_url]
    # Récupérer le vrai source_module pour la DB
    source_module_db = URL_TO_SOURCE_MODULE.get(module_url, module_url)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Récupérer le dossier source avec infos paiement
        cursor.execute(f"""
            SELECT d.{pk} as id, d.{patient_col} as patient, d.{date_col} as date_acte,
                   d.qr_uuid,
                   CONCAT(COALESCE(doc.first_name, ''), ' ', COALESCE(doc.last_name, '')) as medecin,
                   s.name_specialty as specialite
            FROM {table} d
            LEFT JOIN doctors doc ON d.{doctor_col} = doc.id
            LEFT JOIN specialty s ON doc.id_specialty = s.id_specialty
            WHERE d.qr_uuid = %s
        """, (qr_uuid,))
        dossier = cursor.fetchone()

        if not dossier:
            return render_template('archivage/scan_dossier.html', error="Dossier introuvable"), 404

        # 2. Récupérer les infos de paiement spécifiques au module
        paiement_info = _get_paiement_info(cursor, module_url, dossier['id'])

        # 3. Vérifier si archivé
        emplacement = None
        statut_archivage = 'NON_ARCHIVE'
        sortie_info = None

        cursor.execute("""
            SELECT ad.id, ad.statut, b.numero_archive,
                   r.nom_zone, r.code_etagere, e.ligne_y, e.colonne_x
            FROM archivage_dossiers ad
            JOIN archivage_boites b ON ad.id_boite = b.id
            LEFT JOIN archivage_emplacements e ON b.id_emplacement = e.id
            LEFT JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE ad.source_module = %s AND ad.id_source = %s
        """, (source_module_db, dossier['id']))
        archive = cursor.fetchone()

        if archive:
            statut_archivage = archive.get('statut', 'ARCHIVE')
            emplacement = {
                'zone': archive.get('nom_zone'),
                'etagere': archive.get('code_etagere'),
                'ligne': archive.get('ligne_y'),
                'colonne': archive.get('colonne_x'),
                'boite': archive.get('numero_archive'),
            }

            # 4. Si SORTI, récupérer info sortie
            if statut_archivage == 'SORTI':
                cursor.execute("""
                    SELECT s.motif, s.date_sortie, s.date_retour_prevue,
                           CONCAT(COALESCE(p.prenom, ''), ' ', COALESCE(p.nom, '')) as sorti_par_nom
                    FROM archivage_dossiers_sorties s
                    LEFT JOIN personnel p ON s.sorti_par = p.id_personnel
                    WHERE s.id_dossier = %s AND s.date_retour IS NULL
                    ORDER BY s.date_sortie DESC LIMIT 1
                """, (archive['id'],))
                sortie_info = cursor.fetchone()

        return render_template(
            'archivage/scan_dossier.html',
            dossier=dossier,
            module=module_url,
            module_label=MODULE_LABELS.get(module_url, module_url),
            statut_archivage=statut_archivage,
            emplacement=emplacement,
            paiement_info=paiement_info,
            sortie_info=sortie_info,
            id_archive=archive['id'] if archive else None,
            is_logged_in=bool(session.get('user_id')),
        )
    finally:
        conn.close()


def _get_paiement_info(cursor, module_url, dossier_id):
    """Récupère les infos de paiement spécifiques à chaque module."""
    info = {}

    if module_url == 'MATERNITE':
        cursor.execute("""
            SELECT montant_paye, prix_total, statut_paiement, balance_medecin,
                   mode_paiement, part_clinique, part_gyneco
            FROM accouchement_dossiers
            WHERE id_dossier = %s
        """, (dossier_id,))
        row = cursor.fetchone()
        if row:
            info = {
                'montant_paye_caisse': float(row.get('montant_paye', 0) or 0),
                'prix_total': float(row.get('prix_total', 0) or 0),
                'statut_paiement': row.get('statut_paiement', ''),
                'balance_medecin': float(row.get('balance_medecin', 0) or 0),
            }

    elif module_url == 'BLOC_EXTERNE':
        cursor.execute("""
            SELECT montant_paye_caisse, prix_total, statut_paiement, difference_paiement
            FROM location_bloc_dossier_patient
            WHERE id_dossier = %s
        """, (dossier_id,))
        row = cursor.fetchone()
        if row:
            info = {
                'montant_paye_caisse': float(row.get('montant_paye_caisse', 0) or 0),
                'prix_total': float(row.get('prix_total', 0) or 0),
                'statut_paiement': row.get('statut_paiement', ''),
                'balance_medecin': float(row.get('difference_paiement', 0) or 0),
            }

    elif module_url == 'PRESTATION_KT':
        cursor.execute("""
            SELECT prix_dossier_esp, prix_dossier_convention, part_operateur
            FROM kt_dossier_patient
            WHERE id_dossier = %s
        """, (dossier_id,))
        row = cursor.fetchone()
        if row:
            esp = float(row.get('prix_dossier_esp', 0) or 0)
            conv = float(row.get('prix_dossier_convention', 0) or 0)
            info = {
                'montant_paye_caisse': esp,
                'prix_total': esp + conv,
                'statut_paiement': 'Convention' if conv > 0 else 'Espèces',
                'balance_medecin': float(row.get('part_operateur', 0) or 0),
            }

    elif module_url == 'BLOC_INTERNE':
        cursor.execute("""
            SELECT montant_paye_caisse, part_medecin, part_clinique,
                   statut_paiement, difference_paiement, prix_acte_base
            FROM medecin_interne_actes
            WHERE id_acte = %s
        """, (dossier_id,))
        row = cursor.fetchone()
        if row:
            info = {
                'montant_paye_caisse': float(row.get('montant_paye_caisse', 0) or 0),
                'prix_total': float(row.get('prix_acte_base', 0) or 0),
                'statut_paiement': row.get('statut_paiement', ''),
                'balance_medecin': float(row.get('part_medecin', 0) or 0),
            }

    return info


# =====================================================================
# IMPRESSION ÉTIQUETTE QR — Individuelle
# =====================================================================

@app.route('/dossier/<string:module_url>/<int:id_dossier>/print-qr')
@login_required
@handle_errors()
def dossier_print_qr(module_url, id_dossier):
    """Imprime une étiquette QR 40mm×40mm pour un dossier existant."""
    if module_url not in MODULE_TABLE_MAP:
        flash("Module invalide.", "error")
        return redirect(request.referrer or url_for('archivage_index'))

    table, pk, patient_col, date_col, doctor_col = MODULE_TABLE_MAP[module_url]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT d.{pk} as id, d.{patient_col} as patient,
                   d.{date_col} as date_acte, d.qr_uuid,
                   CONCAT(COALESCE(doc.first_name, ''), ' ', COALESCE(doc.last_name, '')) as medecin,
                   s.name_specialty as specialite,
                   doc.id as doctor_id
            FROM {table} d
            LEFT JOIN doctors doc ON d.{doctor_col} = doc.id
            LEFT JOIN specialty s ON doc.id_specialty = s.id_specialty
            WHERE d.{pk} = %s
        """, (id_dossier,))
        dossier = cursor.fetchone()

        if not dossier or not dossier.get('qr_uuid'):
            flash("Dossier non trouvé ou sans QR UUID.", "error")
            return redirect(request.referrer or url_for('archivage_index'))

        qr_b64 = generer_qr_base64(module_url, dossier['qr_uuid'])

        # Logo
        logo_path = os.path.join(current_app.static_folder, 'images', 'entet_inaya.png')
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode('utf-8')

        html = render_template(
            'archivage/print_qr_dossier.html',
            dossier=dossier,
            module_label=MODULE_LABELS.get(module_url, module_url),
            qr_b64=qr_b64,
            logo_b64=logo_b64,
        )

        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

        if pisa_status.err:
            flash("Erreur lors de la génération du PDF.", "error")
            return redirect(request.referrer or url_for('archivage_index'))

        pdf_buffer.seek(0)
        response = make_response(pdf_buffer.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = (
            f'inline; filename=qr_dossier_{id_dossier}.pdf'
        )
        return response
    finally:
        conn.close()


# =====================================================================
# IMPRESSION ÉTIQUETTES QR — En Masse
# =====================================================================

@app.route('/dossier/<string:module_url>/print-qr-mass-setup', methods=['POST'])
@login_required
@handle_errors()
def dossier_print_qr_mass_setup(module_url):
    """
    Affiche la page de configuration de la planche d'étiquettes QR
    avant l'impression en masse.
    """
    if module_url not in MODULE_TABLE_MAP:
        flash("Module invalide.", "error")
        return redirect(request.referrer or url_for('archivage_index'))

    # Mémorisé comme champ JSON (liste d'IDs)
    ids_json = request.form.get('ids', '[]')
    try:
        import json
        ids_list = json.loads(ids_json)
        num_ids = len(ids_list)
    except:
        num_ids = 0

    if num_ids == 0:
        flash("Aucun dossier sélectionné.", "warning")
        return redirect(request.referrer or url_for('archivage_index'))

    return render_template(
        'archivage/print_qr_mass_setup.html',
        module_url=module_url,
        ids_json=ids_json,
        num_ids=num_ids
    )

@app.route('/dossier/<string:module_url>/print-qr-mass', methods=['POST'])
@login_required
@handle_errors()
def dossier_print_qr_mass(module_url):
    """
    Affiche une vue HTML formattée pour impression en masse (CSS Grid).
    Accepte les paramètres de mise en page depuis le formulaire de configuration.
    """
    if module_url not in MODULE_TABLE_MAP:
        return jsonify({'error': 'Module invalide'}), 400

    # On accepte soit le fetch (json) soit un form post normal depuis sheet_setup
    if request.is_json:
        data = request.get_json()
        ids = data.get('ids', [])
    else:
        # Form submit from setup page
        try:
            import json
            ids = json.loads(request.form.get('ids', '[]'))
        except:
            ids = []

    if not ids:
        flash("Liste d'IDs requise.", "warning")
        return redirect(request.referrer or url_for('archivage_index'))

    # Config params
    rows = int(request.form.get('rows', 6))
    cols = int(request.form.get('cols', 4))
    width = float(request.form.get('width', 40))
    height = float(request.form.get('height', 40))
    gap_x = float(request.form.get('gap_x', 5))
    gap_y = float(request.form.get('gap_y', 5))
    margin_top = float(request.form.get('margin_top', 10))
    margin_bottom = float(request.form.get('margin_bottom', 10))
    margin_left = float(request.form.get('margin_left', 10))
    margin_right = float(request.form.get('margin_right', 10))

    table, pk, patient_col, date_col, doctor_col = MODULE_TABLE_MAP[module_url]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Récupérer tous les dossiers
        placeholders = ', '.join(['%s'] * len(ids))
        cursor.execute(f"""
            SELECT d.{pk} as id, d.{patient_col} as patient,
                   d.{date_col} as date_acte, d.qr_uuid,
                   CONCAT(COALESCE(doc.first_name, ''), ' ', COALESCE(doc.last_name, '')) as medecin,
                   s.name_specialty as specialite,
                   doc.id as doctor_id
            FROM {table} d
            LEFT JOIN doctors doc ON d.{doctor_col} = doc.id
            LEFT JOIN specialty s ON doc.id_specialty = s.id_specialty
            WHERE d.{pk} IN ({placeholders})
            ORDER BY d.{pk}
        """, tuple(ids))
        dossiers = cursor.fetchall()

        if not dossiers:
            flash("Aucun dossier trouvé.", "error")
            return redirect(request.referrer or url_for('archivage_index'))

        # Générer les QR pour chaque dossier
        for d in dossiers:
            if d.get('qr_uuid'):
                d['qr_b64'] = generer_qr_base64(module_url, d['qr_uuid'])
            else:
                d['qr_b64'] = None

        # Logo
        logo_path = os.path.join(current_app.static_folder, 'images', 'entet_inaya.png')
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode('utf-8')

        return render_template(
            'archivage/print_qr_dossiers_a4.html',
            dossiers=dossiers,
            module_label=MODULE_LABELS.get(module_url, module_url),
            logo_b64=logo_b64,
            rows=rows,
            cols=cols,
            width=width,
            height=height,
            gap_x=gap_x,
            gap_y=gap_y,
            margin_top=margin_top,
            margin_bottom=margin_bottom,
            margin_left=margin_left,
            margin_right=margin_right
        )

    finally:
        conn.close()


# =====================================================================
# SORTIE TEMPORAIRE
# =====================================================================

@app.route('/archivage/api/dossier/<int:id_dossier_archive>/sortie', methods=['POST'])
@login_required
@handle_errors()
def archivage_dossier_sortie(id_dossier_archive):
    """Enregistre une sortie temporaire pour un dossier archivé."""
    data = request.get_json()
    motif = data.get('motif', '').strip()
    date_retour_prevue = data.get('date_retour_prevue')  # format YYYY-MM-DD ou null

    if not motif:
        return jsonify({'success': False, 'message': 'Le motif est obligatoire.'}), 400

    user_id = g.user['id_personnel']

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier que le dossier existe et est ARCHIVE
        cursor.execute("""
            SELECT id, statut, id_boite FROM archivage_dossiers WHERE id = %s
        """, (id_dossier_archive,))
        dossier = cursor.fetchone()

        if not dossier:
            return jsonify({'success': False, 'message': 'Dossier archivé introuvable.'}), 404

        if dossier['statut'] != 'ARCHIVE':
            return jsonify({'success': False, 'message': f'Le dossier est déjà en statut "{dossier["statut"]}".'}), 400

        # 1. Mettre à jour le statut
        cursor.execute("UPDATE archivage_dossiers SET statut = 'SORTI' WHERE id = %s", (id_dossier_archive,))

        # 2. Insérer la sortie
        cursor.execute("""
            INSERT INTO archivage_dossiers_sorties
            (id_dossier, motif, sorti_par, date_sortie, date_retour_prevue)
            VALUES (%s, %s, %s, NOW(), %s)
            ON DUPLICATE KEY UPDATE
                motif = VALUES(motif),
                sorti_par = VALUES(sorti_par),
                date_sortie = NOW(),
                date_retour_prevue = VALUES(date_retour_prevue),
                date_retour = NULL,
                retourne_par = NULL
        """, (id_dossier_archive, motif, user_id, date_retour_prevue))

        # 3. Logger l'historique
        log_historique(id_dossier_archive, 'SORTIE_TEMPORAIRE', user_id, cursor,
                       id_boite_avant=dossier['id_boite'],
                       commentaire=f'Motif: {motif}')

        conn.commit()
        return jsonify({'success': True, 'message': 'Sortie temporaire enregistrée.'})

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# =====================================================================
# RETOUR DE SORTIE
# =====================================================================

@app.route('/archivage/api/dossier/<int:id_dossier_archive>/retour', methods=['POST'])
@login_required
@handle_errors()
def archivage_dossier_retour(id_dossier_archive):
    """Enregistre le retour d'un dossier sorti temporairement."""
    user_id = g.user['id_personnel']

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier que le dossier est SORTI
        cursor.execute("""
            SELECT id, statut, id_boite FROM archivage_dossiers WHERE id = %s
        """, (id_dossier_archive,))
        dossier = cursor.fetchone()

        if not dossier:
            return jsonify({'success': False, 'message': 'Dossier archivé introuvable.'}), 404

        if dossier['statut'] != 'SORTI':
            return jsonify({'success': False, 'message': 'Ce dossier n\'est pas en sortie.'}), 400

        # 1. Mettre à jour le statut
        cursor.execute("UPDATE archivage_dossiers SET statut = 'ARCHIVE' WHERE id = %s", (id_dossier_archive,))

        # 2. Mettre à jour le record de sortie
        cursor.execute("""
            UPDATE archivage_dossiers_sorties
            SET date_retour = NOW(), retourne_par = %s
            WHERE id_dossier = %s AND date_retour IS NULL
        """, (user_id, id_dossier_archive))

        # 3. Logger l'historique
        log_historique(id_dossier_archive, 'RETOUR', user_id, cursor,
                       id_boite_apres=dossier['id_boite'],
                       commentaire='Retour de sortie temporaire')

        conn.commit()
        return jsonify({'success': True, 'message': 'Retour enregistré avec succès.'})

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# =====================================================================
# DÉSARCHIVAGE
# =====================================================================

@app.route('/archivage/api/dossier/<int:id_dossier_archive>/desarchiver', methods=['POST'])
@login_required
@handle_errors()
def archivage_dossier_desarchiver(id_dossier_archive):
    """Désarchive un dossier (le retire définitivement de l'archivage)."""
    user_id = g.user['id_personnel']
    data = request.get_json() or {}
    commentaire = data.get('commentaire', 'Désarchivage demandé')

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, statut, id_boite FROM archivage_dossiers WHERE id = %s
        """, (id_dossier_archive,))
        dossier = cursor.fetchone()

        if not dossier:
            return jsonify({'success': False, 'message': 'Dossier archivé introuvable.'}), 404

        if dossier['statut'] == 'DESARCHIVE':
            return jsonify({'success': False, 'message': 'Ce dossier est déjà désarchivé.'}), 400

        # 1. Mettre à jour le statut
        cursor.execute("UPDATE archivage_dossiers SET statut = 'DESARCHIVE' WHERE id = %s", (id_dossier_archive,))

        # 2. Clore toute sortie en cours
        cursor.execute("""
            UPDATE archivage_dossiers_sorties
            SET date_retour = NOW(), retourne_par = %s
            WHERE id_dossier = %s AND date_retour IS NULL
        """, (user_id, id_dossier_archive))

        # 3. Logger l'historique
        log_historique(id_dossier_archive, 'DESARCHIVE', user_id, cursor,
                       id_boite_avant=dossier['id_boite'],
                       commentaire=commentaire)

        # 4. Recalculer le remplissage de la boîte
        from app.archivage.utils import calculer_remplissage_boite
        calculer_remplissage_boite(dossier['id_boite'], cursor=cursor)

        conn.commit()
        return jsonify({'success': True, 'message': 'Dossier désarchivé avec succès.'})

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# =====================================================================
# HISTORIQUE DES MOUVEMENTS
# =====================================================================

@app.route('/archivage/api/dossier/<int:id_dossier_archive>/historique')
@login_required
@handle_errors()
def archivage_dossier_historique(id_dossier_archive):
    """Retourne l'historique des mouvements d'un dossier archivé."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT h.action, h.date_action, h.commentaire,
                   h.id_boite_avant, h.id_boite_apres,
                   h.zone_avant, h.zone_apres,
                   CONCAT(COALESCE(p.prenom, ''), ' ', COALESCE(p.nom, '')) as effectue_par_nom,
                   ba.numero_archive as boite_avant_nom,
                   bb.numero_archive as boite_apres_nom
            FROM archivage_dossiers_historique h
            LEFT JOIN personnel p ON h.effectue_par = p.id_personnel
            LEFT JOIN archivage_boites ba ON h.id_boite_avant = ba.id
            LEFT JOIN archivage_boites bb ON h.id_boite_apres = bb.id
            WHERE h.id_dossier = %s
            ORDER BY h.date_action DESC
        """, (id_dossier_archive,))
        historique = cursor.fetchall()

        # Sérialiser les dates
        result = []
        for h in historique:
            result.append({
                'action': h['action'],
                'date_action': h['date_action'].strftime('%d/%m/%Y %H:%M') if h['date_action'] else None,
                'commentaire': h['commentaire'],
                'effectue_par_nom': h['effectue_par_nom'],
                'boite_avant': h['boite_avant_nom'],
                'boite_apres': h['boite_apres_nom'],
                'zone_avant': h['zone_avant'],
                'zone_apres': h['zone_apres'],
            })

        return jsonify({'success': True, 'historique': result})
    finally:
        conn.close()


@app.route( '/archivage/boite/print', methods = [ 'GET', 'POST' ] )
@login_required
@handle_errors()
def archivage_boites_print():
    """Imprime une ou plusieurs étiquettes sur une page A4 (jusqu'à 4 par page)"""
    from io import BytesIO
    from flask import make_response, render_template, request, current_app
    from xhtml2pdf import pisa
    import qrcode
    import base64
    import hashlib
    import json
    from datetime import datetime
    from qrcode.main import QRCode

    if request.method == 'POST':
        numeros = request.form.getlist( 'numeros_archives[]' )
    else:
        numero = request.args.get( 'numero_archive' )
        numeros = [ numero ] if numero else [ ]

    if not numeros:
        flash( "Aucune boîte sélectionnée.", "warning" )
        return redirect( url_for( 'archivage_boites_list' ) )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Build query for single or multiple boxes
        placeholders = ', '.join( [ '%s' ] * len( numeros ) )
        query = f"""
            SELECT b.*, CONCAT(m.first_name, ' ', COALESCE(m.last_name, '')) as doctor_name, s.name_specialty as specialite_nom,
                   r.nom_zone, r.code_etagere, e.colonne_x, e.ligne_y,
                   t.epaisseur_max_mm, t.nom as type_nom,
                   ROUND((b.epaisseur_actuelle_mm / NULLIF(t.epaisseur_max_mm, 0)) * 100) as remplissage_pct
            FROM archivage_boites b
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            LEFT JOIN doctors m ON b.id_medecin = m.id
            LEFT JOIN specialty s ON m.id_specialty = s.id_specialty
            LEFT JOIN archivage_emplacements e ON b.id_emplacement = e.id
            LEFT JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE b.numero_archive IN ({placeholders})
            ORDER BY b.numero_archive ASC
        """
        cursor.execute( query, tuple( numeros ) )
        boites = cursor.fetchall()

        if not boites:
            flash( "Boîte(s) non trouvée(s).", "error" )
            return redirect( url_for( 'archivage_boites_list' ) )

    finally:
        conn.close()

    # Process each box to generate its QR code
    secret_key = current_app.config.get( 'SECRET_KEY', 'default_secret_key' )
    base_url = current_app.config.get( 'BASE_URL' )

    boites_data = [ ]

    for boite in boites:
        verification_data = {
                'id': boite[ 'numero_archive' ],
                'ts': datetime.now().strftime( '%Y%m%d%H%M%S' )
                }

        json_data = json.dumps( verification_data, ensure_ascii = False, separators = (',', ':') )
        encoded_data = base64.urlsafe_b64encode( json_data.encode( 'utf-8' ) ).decode( 'utf-8' )
        security_hash = hashlib.sha256( f"{json_data}{secret_key}".encode( 'utf-8' ) ).hexdigest()[ :16 ]
        verification_url = f"{base_url}/verifier_boite?data={encoded_data}&hash={security_hash}"

        qr = QRCode(
                version = None,
                error_correction = qrcode.constants.ERROR_CORRECT_L,
                box_size = 4,
                border = 2,
                )
        qr.add_data( verification_url )
        qr.make( fit = True )

        img_qr = qr.make_image( fill_color = "#000000", back_color = "white" )
        qr_buf = BytesIO()
        img_qr.save( qr_buf, format = 'PNG' )
        qr_b64 = base64.b64encode( qr_buf.getvalue() ).decode( 'utf-8' )

        boites_data.append(
                {
                        'boite': boite,
                        'qr_b64': qr_b64
                        }
                )

    # Encode logo as base64 for xhtml2pdf compatibility
    import os

    logo_path = os.path.join( current_app.static_folder, 'images', 'entet_inaya.png' )
    with open( logo_path, 'rb' ) as f:
        logo_b64 = base64.b64encode( f.read() ).decode( 'utf-8' )

    html = render_template( 'archivage/print_labels_a4.html', boites = boites_data, logo_b64 = logo_b64 )

    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF( html, dest = pdf_buffer )

    if pisa_status.err:
        return "Erreur lors de la génération du PDF", 500

    response = make_response( pdf_buffer.getvalue() )
    response.headers[ 'Content-Type' ] = 'application/pdf'

    filename = f"Boite_{numeros[ 0 ]}" if len( numeros ) == 1 else "Boites_Batch_A4"
    response.headers[ 'Content-Disposition' ] = f'inline; filename="{filename}.pdf"'
    return response


@app.route( '/verifier_boite' )
def page_verification_boite():
    """
    Page publique de vérification de boîte d'Archive via QR Code
    Accessible sans authentification pour permettre la vérification externe (ex: smartphone)
    """
    return render_template( 'archivage/verifier_boite.html' )


@app.route( '/api/verifier_boite', methods = [ 'POST' ] )
@handle_errors()
def api_verifier_boite():
    """
    API de vérification de l'authenticité d'une boîte via données QR Code
    """
    conn = None
    cursor = None

    try:
        from flask import jsonify, request, current_app
        import hashlib
        import json
        import base64

        qr_data = request.get_json()

        # Validation des données reçues
        if not qr_data:
            return jsonify( { 'success': False, 'error': 'Aucune donnée reçue' } ), 400

        if qr_data.get( 'type' ) != 'BOITE_ARCHIVE':
            return jsonify( { 'success': False, 'error': 'Type de QR Code invalide' } ), 400

        numero_archive = qr_data.get( 'numero' )
        received_hash = qr_data.get( 'hash' )
        timestamp = qr_data.get( 'timestamp' )

        # Recréer le payload attendu pour vérifier le hash
        verification_data = {
                'id': numero_archive,
                'ts': timestamp
                }

        json_data = json.dumps( verification_data, ensure_ascii = False, separators = (',', ':') )
        secret_key = current_app.config.get( 'SECRET_KEY', 'default_secret_key' )

        expected_hash = hashlib.sha256( f"{json_data}{secret_key}".encode( 'utf-8' ) ).hexdigest()[ :16 ]

        if expected_hash != received_hash:
            return jsonify( { 'success': True, 'valid': False, 'error': 'Signature numérique invalide' } )

        # Vérification en base de données
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT b.*,
                   CONCAT(m.first_name, ' ', COALESCE(m.last_name, ''))            as doctor_name,
                   s.name_specialty                                                as specialite_nom,
                   r.nom_zone,
                   r.code_etagere,
                   e.colonne_x,
                   e.ligne_y,
                   (SELECT COUNT(*) FROM archivage_dossiers WHERE id_boite = b.id) as nb_dossiers
            FROM archivage_boites b
                     LEFT JOIN doctors m ON b.id_medecin = m.id
                     LEFT JOIN specialty s ON m.id_specialty = s.id_specialty
                     LEFT JOIN archivage_emplacements e ON b.id_emplacement = e.id
                     LEFT JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE b.numero_archive = %s
                       """, (numero_archive,)
            )

        boite = cursor.fetchone()

        if not boite:
            return jsonify( { 'success': True, 'valid': False, 'error': 'Boîte introuvable dans la base de données' } )

        # Fetch dossiers with statut and sortie info
        cursor.execute(
            """
            SELECT d.id                                                     as id_archive,
                   d.source_module,
                   d.nom_patient,
                   d.statut,
                   d.date_archivage                                         as date_acte,
                   s.motif                                                  as sortie_motif,
                   s.date_sortie,
                   CONCAT(COALESCE(p.prenom, ''), ' ', COALESCE(p.nom, '')) as sorti_par_nom
            FROM archivage_dossiers d
                     LEFT JOIN archivage_dossiers_sorties s ON d.id = s.id_dossier AND s.date_retour IS NULL
                     LEFT JOIN personnel p ON s.sorti_par = p.id_personnel
            WHERE d.id_boite = %s
            ORDER BY d.date_archivage DESC
                       """, (boite[ 'id' ],)
            )
        dossiers_raw = cursor.fetchall()

        dossiers = [ ]
        for d in dossiers_raw:
            dossiers.append(
                    {
                            'id_archive': d[ 'id_archive' ],
                            'nom_patient': d[ 'nom_patient' ],
                            'source_module': d[ 'source_module' ],
                            'statut': d.get( 'statut', 'ARCHIVE' ),
                            'sortie_motif': d.get( 'sortie_motif' ),
                            'sorti_par_nom': d.get( 'sorti_par_nom' ),
                            'date_sortie': d[ 'date_sortie' ].strftime( '%d/%m/%Y %H:%M' ) if d.get(
                                'date_sortie'
                                ) else None,
                            'day': d[ 'date_acte' ].strftime( '%d' ) if d.get( 'date_acte' ) else '--',
                            'month_year': d[ 'date_acte' ].strftime( '%b %Y' ) if d.get( 'date_acte' ) else '----'
                            }
                    )

        # Si tout est OK, renvoyer les données formatées
        emplacement = ""
        if boite.get( 'id_emplacement' ):
            emplacement = f"{boite.get( 'nom_zone', '' )} > Étagère {boite.get( 'code_etagere', '' )} > L{boite.get( 'ligne_y', '' )}-C{boite.get( 'colonne_x', '' )}"

        # Check if user is authenticated
        is_authenticated = bool( session.get( 'user_id' ) )

        return jsonify(
                {
                        'success': True,
                        'valid': True,
                        'is_authenticated': is_authenticated,
                        'boite': {
                                'numero_archive': boite[ 'numero_archive' ],
                                'emplacement': emplacement,
                                'doctor_name': boite[ 'doctor_name' ],
                                'specialite_nom': boite[ 'specialite_nom' ],
                                'date_creation': boite[ 'date_creation' ].strftime( '%d/%m/%Y %H:%M' ) if boite.get(
                                    'date_creation'
                                    ) else '',
                                'nb_dossiers': boite[ 'nb_dossiers' ]
                                },
                        'dossiers': dossiers
                        }
                )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
