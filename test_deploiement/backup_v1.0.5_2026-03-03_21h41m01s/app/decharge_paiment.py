import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import render_template, request, make_response, g, redirect, url_for, flash
from num2words import num2words
from xhtml2pdf import pisa
from app import get_db_connection, app
from app.error import handle_errors
from app.utiles import login_required, permission_required, has_permission, redirect_with_message


# Helper: Gestion des connexions à la base de données
def execute_query(query, params=(), fetchone=False, commit=False):
    """Exécute une requête SQL avec gestion contextuelle."""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if commit:
                conn.commit()
            return cursor.fetchone() if fetchone else cursor.fetchall()

# Routes
@app.route('/decharges', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_DECHARGE')
def decharges():
    """Affiche la liste des décharges avec un filtre sur les décharges réglées."""
    filter_paid = request.args.get('payDoctorFilter', 'false').lower() == 'true'

    # Passez le filtre `filter_paid` à la fonction `fetch_decharges`
    decharges = fetch_decharges(filter_paid=filter_paid)
    current_date = datetime.utcnow().strftime('%Y-%m-%d')

    return render_template(
        'decharge_paiment.html',
        title="Gestion des Décharges",
        decharges=decharges,
        current_date=current_date,
        user=g.user,
        filter_paid=filter_paid
    )

def fetch_decharges(id=None, filter_paid=False):
    """
    Récupère toutes les décharges ou applique un filtre pour les décharges réglées.
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
    """

    params = []

    if id:  # Si un ID spécifique est fourni, filtrez par ID
        query += " WHERE d.id = %s"
        params.append(id)
    elif filter_paid:  # Si `filter_paid` est True, appliquez un filtre pour les décharges réglées
        query += " WHERE d.amount - d.payment = 0"
    else:  # Par défaut, triez par date de création
        query += " WHERE d.amount - d.payment != 0"
        query += " ORDER BY d.created_at DESC"

    return execute_query(query, tuple(params), fetchone=True if id else False)

@app.route('/add_decharge_paiment', methods=['POST'])
@login_required
@handle_errors()
@permission_required('CREER_DECHARGE')
def add_decharge_paiment():
    """Ajoute une nouvelle décharge de paiement."""
    # Récupération des données du formulaire
    doctor_name = request.form.get('doctor_name', '').strip()
    amount = request.form.get('amount', '').strip()
    date = request.form.get('date', '').strip()
    dossiers = request.form.get('dossiers', '').strip()
    dossiers_list = [line.strip() for line in dossiers.splitlines() if line.strip()]
    id_doctor_kt = None
    id_employe = None

    # Validation des champs obligatoires
    if not doctor_name or not amount or not date or not dossiers_list:
        flash("Tous les champs sont requis.", "danger")
        return redirect(url_for('decharges'))

    # Validation du montant
    try:
        amount = Decimal(amount)
        if amount <= 0:
            flash("Erreur : Le montant doit être supérieur à zéro.", "danger")
            return redirect(url_for('decharges'))
        amount_in_words = num2words(float(amount), lang='fr').upper()
    except (InvalidOperation, ValueError):
        flash("Erreur : Montant invalide.", "danger")
        return redirect(url_for('decharges'))

    # Insertion de la décharge
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
    try:
        execute_query(query, params, commit=True)
    except Exception as e:
        return f"Erreur lors de l'insertion : {str(e)}"
    return None

@app.route('/decharge/<int:id>/export_pdf', methods=['GET'])
@login_required
@handle_errors()
@permission_required('EXPORTER_DECHARGE_PDF')
def export_decharge_pdf(id):
    """Exporte une décharge au format PDF."""
    decharge = fetch_decharges(id)
    if not decharge:
        flash("Erreur : Décharge non trouvée.", "danger")
        return redirect(url_for('decharges'))

    try:
        # Génération du PDF
        amount_in_words = num2words(float(decharge['amount']), lang='fr').upper()
        html = render_template('pdf/decharge_template.html', doctor_name=decharge['doctor_name'],
                               amount=decharge['amount'], amount_in_words=amount_in_words, id=id,
                               date=decharge['date'], dossiers=decharge['dossiers'].splitlines())
        response, error = generate_pdf(html, f"decharge_{id}.pdf", is_attachment=True)
        if error:
            flash(error, "danger")
            return redirect(url_for('decharges'))

        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Format SQL (YYYY-MM-DD HH:MM:SS)

        # Mise à jour de la base de données
        query = """
            UPDATE decharges
            SET id_export_par = %s, time_export_decharge_pdf = %s
            WHERE id = %s
        """
        execute_query(query, (g.user['id_personnel'], date, id), commit=True)

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
@permission_required('AJOUTER_PAYMENT_DECHARGE')
def add_payment_decharges(id):
    """Ajoute un paiement à une décharge existante."""
    try:
        # Récupération et validation du montant du paiement
        payment_amount = request.form.get('payment_amount', '').strip()
        if not payment_amount or not payment_amount.replace('.', '').isdigit() or Decimal(payment_amount) <= 0:
            flash("Erreur : Veuillez entrer un montant de paiement valide.", "danger")
            return redirect(url_for('decharges'))

        payment_amount = Decimal(payment_amount)

        # Récupération de la décharge
        decharge = fetch_decharges(id)
        if not decharge:
            flash("Erreur : Décharge introuvable.", "danger")
            return redirect(url_for('decharges'))

        # Vérification du solde restant
        remaining_amount = Decimal(decharge['amount']) - Decimal(decharge['payment'])
        if remaining_amount <= 0:
            flash("Cette décharge est déjà payée.", "info")
            return redirect(url_for('decharges'))

        # Vérifier si le montant dépasse le solde restant
        if payment_amount > remaining_amount:
            flash(f"Erreur : Le montant dépasse le solde restant ({remaining_amount:.2f}).", "danger")
            return redirect(url_for('decharges'))

        # Mise à jour du paiement
        query = """
            UPDATE decharges 
            SET payment = payment + %s, time_payment = CURRENT_TIMESTAMP, id_payment_par = %s
            WHERE id = %s
        """
        execute_query(query, (payment_amount, g.user['id_personnel'], id), commit=True)
        # Gestion des décaissements pour les dossiers associés
        # Gestion des décaissements pour les dossiers associés
        if decharge['id_employe']:
            total_decaissement = process_employe_payment(decharge['id_employe'], payment_amount)
            if total_decaissement > 0:
                flash(f"Décaissement de {total_decaissement:.2f} effectué avec succès.", "success")
            else:
                flash("Montant insuffisant pour décaisser les dossiers.", "danger")

        if decharge['id_doctor_kt']:
            total_decaissement = process_doctor_payment(decharge['id_doctor_kt'], payment_amount)
            if total_decaissement > 0:
                flash(f"Décaissement de {total_decaissement:.2f} effectué avec succès.", "success")
            else:
                flash("Montant insuffisant pour décaisser les dossiers.", "danger")

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
        # Récupérer les dossiers non payés
        cursor.execute("""
            SELECT id_dossier, part_operateur, payment
            FROM kt_dossier_patient
            WHERE id_doctor = %s AND payment < part_operateur
        """, (id_doctor_kt,))
        dossiers_nd = cursor.fetchall()
        print(dossiers_nd)
        if not dossiers_nd:
            return total_decaissement

        # Traiter chaque dossier
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
                UPDATE kt_doctor_situations SET payment = payment + %s WHERE id_dossier = %s
    """, (amount, id_dossier))


def process_employe_payment(employee_id, payment_amount):
    """Traite le paiement pour les dossiers associés à un employé."""
    connection = get_db_connection()
    cursor = connection.cursor()
    total_decaissement = Decimal(0)

    try:
        # Vérifier s'il y a des pointages non payés pour cet employé
        cursor.execute("""
            SELECT id_pointage, prix, prix_acte, paiement 
            FROM pointages
            WHERE id_employe = %s AND (prix + prix_acte - paiement) > 0
        """, (employee_id,))
        pointages_np = cursor.fetchall()

        if not pointages_np:
            return total_decaissement

        # Traiter chaque dossier
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
                break  # Plus de fonds à répartir

        connection.commit()
    finally:
        cursor.close()
        connection.close()

    return total_decaissement


@app.route('/decharge/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('MODIFIER_DECHARGE')
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

        # Mise à jour des informations dans la base de données
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
    try:
        execute_query(query, params, commit=True)
    except Exception as e:
        return f"Erreur lors de la mise à jour : {str(e)}"
    return None

@app.route('/decharge/<int:id>/delete', methods=['POST'])
@login_required
@handle_errors()
@permission_required('SUPPRIMER_DECHARGE')
def delete_decharge(id):
    """Supprime une décharge."""
    decharge = fetch_decharges(id)
    if not decharge:
        flash("Erreur : Décharge non trouvée.", "danger")
        return redirect(url_for('decharges'))

    try:
        # Suppression de la décharge de la base de données
        query = "DELETE FROM decharges WHERE id = %s"
        execute_query(query, (id,), commit=True)
        flash("Décharge supprimée avec succès.", "success")
    except Exception as e:
        flash(f"Erreur lors de la suppression : {str(e)}", "danger")

    return redirect(url_for('decharges'))
