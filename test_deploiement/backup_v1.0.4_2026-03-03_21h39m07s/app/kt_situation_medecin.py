from decimal import Decimal, InvalidOperation

from flask import request, redirect, url_for, render_template, g, flash
from num2words import num2words

from app import app, get_db_connection
from app.decharge_paiment import insert_decharge
from app.error import handle_errors
from app.utiles import login_required, permission_required


@app.route('/add_doctors_kt', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ADD_DOCTORS_KT')
def add_doctors_kt():
    if request.method == 'POST':
        # Récupérer les données du formulaire
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        id_specialty = request.form['specialty']

        # Ajouter un nouveau médecin
        connection= get_db_connection()


        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO kt_doctors (first_name, last_name, id_specialty)
            VALUES (%s, %s, %s)
        """, (first_name, last_name, id_specialty))
        connection.commit()

    return redirect(url_for('kt_situation_medecin'))

@app.route('/edit_doctor_kt/<int:id_doctor>', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('MODIFIER_DOCTORS_KT')
def edit_doctor_kt(id_doctor):
    # Fetch the doctor from the database by ID
    connection = get_db_connection()


    cursor = connection.cursor()
    cursor.execute("SELECT * FROM kt_doctors WHERE id = %s", (id_doctor,))
    doctor = cursor.fetchone()

    if not doctor:
        flash('Médecin non trouvé', 'danger')
        return redirect(url_for('kt_situation_medecin'))

    if request.method == 'POST':
        # Retrieve the form data
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        id_specialty = request.form['specialty']

        # Update the doctor details
        connection= get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
                UPDATE kt_doctors
                SET first_name = %s, last_name = %s, id_specialty = %s
                WHERE id = %s
            """, (first_name, last_name, id_specialty, id_doctor))
        connection.commit()

        flash('Détails du médecin mis à jour avec succès!', 'success')
        return redirect(url_for('kt_situation_medecin'))

@app.route('/kt_situation_medecin')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SITUATION_MEDECIN_KT')
def kt_situation_medecin():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Récupérer la liste des médecins et leurs spécialités
        cursor.execute("""
            SELECT d.*, s.name_specialty
            FROM kt_doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
        """)
        kt_doctors = cursor.fetchall()

        cursor.execute("SELECT * FROM specialty")  # Récupérer les spécialités
        specialties = cursor.fetchall()

        # Calcul global des soldes
        total_solde_all_doctors = 0

        # Préparer les données pour chaque médecin
        for doctor in kt_doctors:
            cursor.execute("""
                SELECT 
                    id_dossier, 
                    payment, 
                    part_operateur, 
                    patient AS patient_name
                FROM kt_dossier_patient
                WHERE id_doctor = %s
            """, (doctor['id'],))
            dossiers = cursor.fetchall()

            # Calcul du solde total du médecin
            doctor_total_solde = sum(
                dossier['part_operateur'] - dossier['payment'] for dossier in dossiers
            )
            doctor['total_solde'] = doctor_total_solde
            doctor['dossiers'] = dossiers

            # Ajouter les transactions de chaque dossier
            for dossier in dossiers:
                cursor.execute("""
                    SELECT
                    d.id_dossier,
                    d.acte_date, 
                    ak.code_cnas, 
                    ak.name_acte_kt, 
                    d.urgence, 
                    dak.convention,  
                    dak.part_operateur AS part_operateur_acte 
                    FROM kt_dossier_patient d
                    LEFT JOIN kt_dossier_actes dak ON d.id_dossier = dak.id_dossier
                    LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
                    LEFT JOIN kt_doctors doc ON d.id_doctor = doc.id
                    WHERE d.id_dossier = %s
                """, (dossier['id_dossier'],))
                dossier['transactions'] = cursor.fetchall()

            total_solde_all_doctors += doctor_total_solde

    except Exception as e:
        print(f"Erreur : {e}")
        return render_template(
            'kt_situation_medecin.html',
            title="Situation medecin",
            kt_doctors=[],
            specialties=[],
            total_solde_all_doctors=0,
            user=g.user
        )

    # Renvoyer les données au template
    return render_template(
        'kt_situation_medecin.html',
        title="Situation medecin",
        kt_doctors=kt_doctors,
        specialties=specialties,
        total_solde_all_doctors=total_solde_all_doctors,
        user=g.user
    )


@app.route('/add_decharge_paiment_kt', methods=['POST'])
@login_required
@handle_errors()
@permission_required('CREER_DECHARGE_KT')
def add_decharge_paiment_kt():
    """Ajoute une nouvelle décharge de paiement pour un médecin KT."""
    doctor_name = request.form.get('doctor_name', '').strip()
    amount = request.form.get('amount', '').strip()
    date = request.form.get('date', '').strip()
    id_doctor_kt = request.form.get('id_doctor_kt', '').strip()
    dossiers = request.form.get('dossiers', '').strip()
    dossiers_list = [line.strip() for line in dossiers.splitlines() if line.strip()]

    # Validation des champs obligatoires
    if not doctor_name or not amount or not date or not id_doctor_kt:
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
    error = insert_decharge(doctor_name, id_doctor_kt,None, amount, date, dossiers_list, g.user['id_personnel'])
    if error:
        flash(error, "danger")
    else:
        flash("Décharge ajoutée avec succès.", "success")

    return redirect(url_for('decharges'))
