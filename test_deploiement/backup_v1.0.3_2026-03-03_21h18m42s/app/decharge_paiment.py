import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import render_template, request, make_response, g, redirect, url_for, flash, jsonify
from num2words import num2words
from xhtml2pdf import pisa
from app import get_db_connection, app
from app.error import handle_errors
from app.utils.utiles import login_required


# ========================================================================
# ROUTE PRINCIPALE AVEC PAGINATION
# ========================================================================

@app.route('/decharges_r/decharges', methods=['GET'])
@login_required
@handle_errors()

def decharges():
    """Affiche la liste des décharges avec pagination et filtres"""
    # Paramètres de pagination
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))  # 20 par page par défaut

    # Filtres
    filter_paid = request.args.get('payDoctorFilter', 'false').lower() == 'true'
    search_query = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    # Récupération des décharges paginées
    result = fetch_decharges_paginated(
        page=page,
        per_page=per_page,
        filter_paid=filter_paid,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to
    )

    current_date = datetime.utcnow().strftime('%Y-%m-%d')

    return render_template(
        'decharges/decharge_paiment.html',
        title="Gestion des Décharges",
        decharges=result['decharges'],
        pagination=result['pagination'],
        current_date=current_date,
        user=g.user,
        filter_paid=filter_paid,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to
    )


def fetch_decharges_paginated(page=1, per_page=20, filter_paid=False,
                              search_query='', date_from='', date_to=''):
    """
    Récupère les décharges avec pagination et filtres
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Construction de la requête de base
        base_query = """
            SELECT 
                d.id, 
                d.doctor_name, 
                d.id_doctor_kt, 
                d.id_employe, 
                d.amount, 
                d.payment, 
                d.reste_calc as reste, 
                d.date, 
                d.dossiers,
                CONCAT(criator.nom, ' ', criator.prenom) AS created_par,
                d.time_export_decharge_pdf, 
                CONCAT(exporter.nom, ' ', exporter.prenom) AS exporter_par, 
                d.time_payment, 
                CONCAT(pa.nom, ' ', pa.prenom) AS payment_par
            FROM decharges d
            LEFT JOIN personnel criator ON d.id_created_par = criator.id_personnel
            LEFT JOIN personnel exporter ON d.id_export_par = exporter.id_personnel
            LEFT JOIN personnel pa ON d.id_payment_par = pa.id_personnel
        """

        # Construction des conditions WHERE
        conditions = []
        params = []

        # Filtre payé/non payé (utilise reste_calc pour MariaDB)
        if filter_paid:
            conditions.append("d.reste_calc = 0")
        else:
            conditions.append("d.reste_calc != 0")

        # Filtre de recherche
        if search_query:
            conditions.append("""
                (d.doctor_name LIKE %s 
                OR d.dossiers LIKE %s 
                OR CONCAT(criator.nom, ' ', criator.prenom) LIKE %s)
            """)
            search_param = f'%{search_query}%'
            params.extend([search_param, search_param, search_param])

        # Filtre par date
        if date_from:
            conditions.append("d.date >= %s")
            params.append(date_from)

        if date_to:
            conditions.append("d.date <= %s")
            params.append(date_to)

        # Assemblage de la requête WHERE
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # Compter le total pour la pagination
        count_query = f"""
            SELECT COUNT(*) as total
            FROM decharges d
            LEFT JOIN personnel criator ON d.id_created_par = criator.id_personnel
            {where_clause}
        """
        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone()['total']

        # Requête principale avec LIMIT et OFFSET
        offset = (page - 1) * per_page
        main_query = f"""
            {base_query}
            {where_clause}
            ORDER BY d.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])

        cursor.execute(main_query, tuple(params))
        decharges = cursor.fetchall()

        # Calcul de la pagination
        total_pages = (total_count + per_page - 1) // per_page

        return {
            'decharges': decharges,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'total_pages': total_pages,
                'has_prev': page > 1,
                'has_next': page < total_pages
            }
        }

    finally:
        cursor.close()
        connection.close()


# ========================================================================
# API POUR CHARGER UNE DÉCHARGE (LAZY LOADING DES MODALES)
# ========================================================================

@app.route('/api/decharge/<int:id>')
@login_required
@handle_errors()
def get_decharge_details(id):
    """Récupère les détails d'une décharge pour édition"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT 
                id, doctor_name, amount, date, dossiers, (amount - payment) as reste
            FROM decharges
            WHERE id = %s
        """, (id,))

        decharge = cursor.fetchone()

        if not decharge:
            return jsonify({'success': False, 'error': 'Décharge non trouvée'}), 404

        return jsonify({
            'success': True,
            'decharge': {
                'id': decharge['id'],
                'doctor_name': decharge['doctor_name'],
                'amount': float(decharge['amount']),
                'date': decharge['date'].strftime('%Y-%m-%d') if decharge['date'] else '',
                'dossiers': decharge['dossiers'],
                'reste': float(decharge['reste']) if decharge['reste'] else 0
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


# ========================================================================
# API POUR RECHERCHE AJAX
# ========================================================================

@app.route('/api/decharges/search')
@login_required
@handle_errors()
def search_decharges_ajax():
    """Recherche AJAX pour les décharges"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    filter_paid = request.args.get('filter_paid', 'false').lower() == 'true'
    search_query = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    result = fetch_decharges_paginated(
        page=page,
        per_page=per_page,
        filter_paid=filter_paid,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to
    )

    # Formater les décharges pour JSON
    decharges_json = []
    for d in result['decharges']:
        decharges_json.append({
            'id': d['id'],
            'date': d['date'].strftime('%Y-%m-%d') if d['date'] else '',
            'doctor_name': d['doctor_name'],
            'amount': float(d['amount']),
            'reste': float(d['reste']) if d['reste'] else 0,
            'payment': float(d['payment']) if d['payment'] else 0,
            'created_par': d['created_par'],
            'dossiers': d['dossiers'].splitlines() if d['dossiers'] else [],
            'time_export_decharge_pdf': d['time_export_decharge_pdf'].strftime('%Y-%m-%d %H:%M') if d['time_export_decharge_pdf'] else None,
            'time_payment': d['time_payment'].strftime('%Y-%m-%d %H:%M') if d['time_payment'] else None,
            'payment_par': d['payment_par']
        })

    return jsonify({
        'success': True,
        'decharges': decharges_json,
        'pagination': result['pagination']
    })


# ========================================================================
# ANCIENNES FONCTIONS (MODIFIÉES)
# ========================================================================

def fetch_decharges(id=None, filter_paid=False):
    """
    Récupère une décharge spécifique par ID
    (Pour compatibilité avec l'ancien code)
    """
    query = """
        SELECT 
            d.id, 
            d.doctor_name, 
            d.id_doctor_kt, 
            d.id_employe, 
            d.amount, 
            d.payment, 
            (d.amount - d.payment) AS reste, 
            d.date, 
            d.dossiers,
            CONCAT(criator.nom, ' ', criator.prenom) AS created_par,
            d.time_export_decharge_pdf, 
            CONCAT(exporter.nom, ' ', exporter.prenom) AS exporter_par, 
            d.time_payment, 
            CONCAT(pa.nom, ' ', pa.prenom) AS payment_par
        FROM decharges d
        LEFT JOIN personnel criator ON d.id_created_par = criator.id_personnel
        LEFT JOIN personnel exporter ON d.id_export_par = exporter.id_personnel
        LEFT JOIN personnel pa ON d.id_payment_par = pa.id_personnel
        WHERE d.id = %s
    """

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(query, (id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


# ========================================================================
# RESTE DU CODE INCHANGÉ
# ========================================================================

@app.route('/add_decharge_paiment', methods=['POST'])
@login_required
@handle_errors()
def add_decharge_paiment():
    """Ajoute une nouvelle décharge de paiement."""
    doctor_name = request.form.get('doctor_name', '').strip()
    amount = request.form.get('amount', '').strip()
    date = request.form.get('date', '').strip()
    dossiers = request.form.get('dossiers', '').strip()
    dossiers_list = [line.strip() for line in dossiers.splitlines() if line.strip()]
    id_doctor_kt = None
    id_employe = None

    if not doctor_name or not amount or not date or not dossiers_list:
        flash("Tous les champs sont requis.", "danger")
        return redirect(url_for('decharges'))

    try:
        amount = Decimal(amount)
        if amount <= 0:
            flash("Erreur : Le montant doit être supérieur à zéro.", "danger")
            return redirect(url_for('decharges'))
    except (InvalidOperation, ValueError):
        flash("Erreur : Montant invalide.", "danger")
        return redirect(url_for('decharges'))

    error = insert_decharge(doctor_name, id_doctor_kt, id_employe, amount, date, dossiers_list, g.user['id_personnel'])
    if error:
        flash(error, "danger")
    else:
        flash("Décharge ajoutée avec succès.", "success")

    return redirect(url_for('decharges'))


def insert_decharge(doctor_name, id_doctor_kt, id_employe, amount, date, dossiers, user_id):
    """Insère une décharge dans la base de données."""
    query = """
        INSERT INTO decharges (doctor_name, id_doctor_kt, id_employe, amount, date, dossiers, id_created_par)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (doctor_name, id_doctor_kt, id_employe, amount, date, '\n'.join(dossiers), user_id)

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(query, params)
        connection.commit()
    except Exception as e:
        connection.rollback()
        return f"Erreur lors de l'insertion : {str(e)}"
    finally:
        cursor.close()
        connection.close()
    return None


@app.route('/decharges_r/decharge/<int:id>/export_pdf', methods=['GET'])
@login_required
@handle_errors()
def export_decharge_pdf(id):
    """Exporte une décharge au format PDF."""
    decharge = fetch_decharges(id)
    if not decharge:
        flash("Erreur : Décharge non trouvée.", "danger")
        return redirect(url_for('decharges'))

    try:
        amount_in_words = num2words(float(decharge['amount']), lang='fr').upper()
        html = render_template('pdf/decharge_template.html',
                             doctor_name=decharge['doctor_name'],
                             amount=decharge['amount'],
                             amount_in_words=amount_in_words,
                             id=id,
                             date=decharge['date'],
                             dossiers=decharge['dossiers'].splitlines())

        response, error = generate_pdf(html, f"decharge_{id}.pdf", is_attachment=True)
        if error:
            flash(error, "danger")
            return redirect(url_for('decharges'))

        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        query = """
            UPDATE decharges
            SET id_export_par = %s, time_export_decharge_pdf = %s
            WHERE id = %s
        """
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(query, (g.user['id_personnel'], date, id))
            connection.commit()
        finally:
            cursor.close()
            connection.close()

        return response
    except Exception as e:
        flash(f"Erreur : {str(e)}", "danger")
        return redirect(url_for('decharges'))


def generate_pdf(html_content, filename, is_attachment=False):
    """Génère un fichier PDF à partir de HTML."""
    try:
        pdf_output = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_output)
        if pisa_status.err:
            return None, "Erreur lors de la génération du PDF."

        pdf_output.seek(0)
        response = make_response(pdf_output.read())
        response.headers['Content-Type'] = 'application/pdf'
        disposition = 'attachment' if is_attachment else 'inline'
        response.headers['Content-Disposition'] = f'{disposition}; filename={filename}'
        return response, None
    except Exception as e:
        return None, f"Erreur : {str(e)}"


@app.route('/add_payment_decharges/<int:id>', methods=['POST'])
@login_required
@handle_errors()
def add_payment_decharges(id):
    """Ajoute un paiement à une décharge existante."""
    try:
        payment_amount = request.form.get('payment_amount', '').strip()
        if not payment_amount or not payment_amount.replace('.', '').replace(',', '').isdigit() or Decimal(payment_amount) <= 0:
            flash("Erreur : Veuillez entrer un montant de paiement valide.", "danger")
            return redirect(url_for('decharges'))

        payment_amount = Decimal(payment_amount)

        decharge = fetch_decharges(id)
        if not decharge:
            flash("Erreur : Décharge introuvable.", "danger")
            return redirect(url_for('decharges'))

        remaining_amount = Decimal(decharge['amount']) - Decimal(decharge['payment'])
        if remaining_amount <= 0:
            flash("Cette décharge est déjà payée.", "info")
            return redirect(url_for('decharges'))

        if payment_amount > remaining_amount:
            flash(f"Erreur : Le montant dépasse le solde restant ({remaining_amount:.2f}).", "danger")
            return redirect(url_for('decharges'))

        query = """
            UPDATE decharges 
            SET payment = payment + %s, time_payment = CURRENT_TIMESTAMP, id_payment_par = %s
            WHERE id = %s
        """
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(query, (payment_amount, g.user['id_personnel'], id))
            connection.commit()
        finally:
            cursor.close()
            connection.close()

        if decharge['id_employe']:
            total_decaissement = process_employe_payment(decharge['id_employe'], payment_amount)
            if total_decaissement > 0:
                flash(f"Décaissement de {total_decaissement:.2f} effectué avec succès.", "success")

        if decharge['id_doctor_kt']:
            total_decaissement = process_doctor_payment(decharge['id_doctor_kt'], payment_amount)
            if total_decaissement > 0:
                flash(f"Décaissement de {total_decaissement:.2f} effectué avec succès.", "success")

        flash(f"Paiement enregistré avec succès. Nouveau solde : {remaining_amount - payment_amount:.2f}.", "success")

    except Exception as e:
        flash(f"Erreur inattendue : {str(e)}", "danger")

    return redirect(url_for('decharges'))


def process_doctor_payment(id_doctor_kt, payment_amount):
    """Traite le paiement pour les dossiers associés à un médecin."""
    connection = get_db_connection()
    cursor = connection.cursor()
    total_decaissement = Decimal(0)

    try:
        cursor.execute("""
            SELECT id_dossier, part_operateur, payment
            FROM kt_dossier_patient
            WHERE id_doctor = %s AND payment < part_operateur
        """, (id_doctor_kt,))
        dossiers_nd = cursor.fetchall()

        if not dossiers_nd:
            return total_decaissement

        for dossier in dossiers_nd:
            montant_restant = Decimal(dossier['part_operateur']) - Decimal(dossier['payment'])

            if payment_amount >= montant_restant:
                total_decaissement += montant_restant
                payment_amount -= montant_restant
                update_dossier_payment(cursor, dossier['id_dossier'], montant_restant, id_doctor_kt)
            else:
                total_decaissement += payment_amount
                update_dossier_payment(cursor, dossier['id_dossier'], payment_amount, id_doctor_kt)
                payment_amount = Decimal(0)
                break

        connection.commit()
    finally:
        cursor.close()
        connection.close()

    return total_decaissement


def update_dossier_payment(cursor, id_dossier, amount, id_doctor_kt):
    """Met à jour le paiement d'un dossier et enregistre la situation du médecin."""
    cursor.execute("""
        UPDATE kt_dossier_patient
        SET payment = payment + %s
        WHERE id_dossier = %s
    """, (amount, id_dossier))

    cursor.execute("""
        UPDATE kt_doctor_situations 
        SET payment = payment + %s 
        WHERE id_dossier = %s
    """, (amount, id_dossier))


def process_employe_payment(employee_id, payment_amount):
    """Traite le paiement pour les dossiers associés à un employé."""
    connection = get_db_connection()
    cursor = connection.cursor()
    total_decaissement = Decimal(0)

    try:
        cursor.execute("""
            SELECT id_pointage, prix, prix_acte, paiement 
            FROM pointages
            WHERE id_employe = %s AND (prix + prix_acte - paiement) > 0
        """, (employee_id,))
        pointages_np = cursor.fetchall()

        if not pointages_np:
            return total_decaissement

        for pointage in pointages_np:
            montant_restant = Decimal(pointage['prix']) + Decimal(pointage['prix_acte']) - Decimal(pointage['paiement'])

            if payment_amount >= montant_restant:
                cursor.execute("""
                    UPDATE pointages
                    SET paiement = paiement + %s
                    WHERE id_pointage = %s
                """, (montant_restant, pointage['id_pointage']))
                total_decaissement += montant_restant
                payment_amount -= montant_restant
            else:
                cursor.execute("""
                    UPDATE pointages
                    SET paiement = paiement + %s
                    WHERE id_pointage = %s
                """, (payment_amount, pointage['id_pointage']))
                total_decaissement += payment_amount
                payment_amount = Decimal(0)
                break

        connection.commit()
    finally:
        cursor.close()
        connection.close()

    return total_decaissement


@app.route('/decharge/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@handle_errors()
def edit_decharge(id):
    """Modifie une décharge existante."""
    decharge = fetch_decharges(id)
    if not decharge:
        flash("Erreur : Décharge non trouvée.", "danger")
        return redirect(url_for('decharges'))

    if request.method == 'POST':
        doctor_name = request.form['doctor_name']
        amount = request.form['amount']
        date = request.form['date']
        dossiers = [line.strip() for line in request.form['dossiers'].splitlines() if line.strip()]

        error = update_decharge(id, doctor_name, amount, date, dossiers)
        if error:
            flash(error, "danger")
        else:
            flash("Décharge mise à jour avec succès.", "success")

    return redirect(url_for('decharges'))


def update_decharge(id, doctor_name, amount, date, dossiers):
    """Met à jour une décharge dans la base de données."""
    query = """
        UPDATE decharges
        SET doctor_name = %s, amount = %s, date = %s, dossiers = %s
        WHERE id = %s
    """
    params = (doctor_name, amount, date, '\n'.join(dossiers), id)

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(query, params)
        connection.commit()
    except Exception as e:
        connection.rollback()
        return f"Erreur lors de la mise à jour : {str(e)}"
    finally:
        cursor.close()
        connection.close()
    return None


@app.route('/decharge/<int:id>/delete', methods=['POST'])
@login_required
@handle_errors()

def delete_decharge(id):
    """Supprime une décharge."""
    decharge = fetch_decharges(id)
    if not decharge:
        flash("Erreur : Décharge non trouvée.", "danger")
        return redirect(url_for('decharges'))

    try:
        query = "DELETE FROM decharges WHERE id = %s"
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(query, (id,))
            connection.commit()
            flash("Décharge supprimée avec succès.", "success")
        finally:
            cursor.close()
            connection.close()
    except Exception as e:
        flash(f"Erreur lors de la suppression : {str(e)}", "danger")

    return redirect(url_for('decharges'))