from decimal import Decimal

from flask import request, redirect, url_for, render_template, g, flash

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, permission_required, redirect_with_message


# /doctors (GET, POST) : Ajouter, mettre à jour ou consulter les informations des médecins
@app.route('/manage_doctors', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ADD_DOCTORS')
def manage_doctors():
    if request.method == 'POST':
        # Récupérer les données du formulaire
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        id_specialty = request.form['specialty']

        # Ajouter un nouveau médecin
        connection= get_db_connection()


        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO doctors (first_name, last_name, id_specialty)
            VALUES (%s, %s, %s)
        """, (first_name, last_name, id_specialty))
        connection.commit()

    return redirect(url_for('situation_medecin'))

@app.route('/edit_doctor/<int:id_doctor>', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('MODIFIER_DOCTORS')
def edit_doctor(id_doctor):
    # Fetch the doctor from the database by ID
    connection = get_db_connection()


    cursor = connection.cursor()
    cursor.execute("SELECT * FROM doctors WHERE id = %s", (id_doctor,))
    doctor = cursor.fetchone()

    if not doctor:
        flash('Médecin non trouvé', 'danger')
        return redirect(url_for('situation_medecin'))

    if request.method == 'POST':
        # Retrieve the form data
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        id_specialty = request.form['specialty']

        # Update the doctor details
        connection= get_db_connection()


        cursor = connection.cursor()
        cursor.execute("""
                UPDATE doctors
                SET first_name = %s, last_name = %s, id_specialty = %s
                WHERE id = %s
            """, (first_name, last_name, id_specialty, id_doctor))
        connection.commit()

        flash('Détails du médecin mis à jour avec succès!', 'success')
        return redirect(url_for('situation_medecin'))

# Endpoint pour traiter le paiement
@app.route('/paiement_doctor', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def paiement_doctor():
    try:
        # Récupérer les données du formulaire
        id_doctor = request.form['id_doctor']
        amount = Decimal(request.form['amount'])  # Convertir en Decimal
        # Connexion à la base de données
        connection = get_db_connection()


        cursor = connection.cursor()
        # Vérifier s'il y a des pointages non payés pour cet employé
        cursor.execute("""
            SELECT id_dossier, part_clinique, balance
            FROM dossier_patient
            WHERE id_doctor = %s AND (balance) < 0
        """, (id_doctor,))
        dossiers_np = cursor.fetchall()

        # Vérifier que des pointages non payés existent
        if len(dossiers_np) == 0:
            return redirect_with_message('situation_medecin', "Aucun dossier non payé trouvé pour ce médecin.",
                                         'danger')

        # Le médecin doit payer la clinique
        total_paiement = Decimal(0)
        for dossier in dossiers_np:
            montant_restant_p = (Decimal(dossier['balance'])) * (-1)  # Convertir explicitement en Decimal
            montant_restant_n = (Decimal(dossier['balance']))  # Convertir explicitement en Decimal

            if amount >= montant_restant_p:
                total_paiement += montant_restant_p
                amount -= montant_restant_p
                # Mettre à jour le dossier avec un paiement total
                cursor.execute("""
                    UPDATE dossier_patient
                    SET balance = balance - %s
                    WHERE id_dossier = %s
                """, (montant_restant_n, dossier['id_dossier']))

                sql = """
                INSERT INTO doctor_situations (encaissement_doctor, id_doctor, id_dossier)
                VALUES (%s, %s, %s)
                """
                cursor.execute(sql, (montant_restant_p, id_doctor, dossier['id_dossier']))
                connection.commit()  # Appliquer les changements à la base de données

            else:
                total_paiement += amount
                amount_n = amount * -1
                # Mettre à jour le dossier avec un paiement partiel
                cursor.execute("""
                    UPDATE dossier_patient
                    SET balance = balance - %s
                    WHERE id_dossier = %s
                """, (amount_n, dossier['id_dossier']))

                sql = """
                INSERT INTO doctor_situations (encaissement_doctor, id_doctor, id_dossier)
                VALUES (%s, %s, %s)
                """
                cursor.execute(sql, (amount, id_doctor, dossier['id_dossier']))

                connection.commit()  # Appliquer les changements à la base de données
                amount = Decimal(0)
                break

        # Flash pour indiquer si le paiement a été effectué
        if total_paiement > 0:
            return redirect_with_message('situation_medecin', f'Paiement de {total_paiement} effectué avec succès !',
                                         'success')
        else:
            return redirect_with_message('situation_medecin', "Montant insuffisant pour payer les dossiers.", 'danger')

    except Exception as e:
        print("*****")
        return redirect_with_message('situation_medecin', f'Erreur lors du paiement : {e}', 'danger')

# Endpoint pour traiter le decaissement
@app.route('/decaissement_doctor', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def decaissement_doctor():
    try:
        # Récupérer les données du formulaire
        id_doctor = request.form['id_doctor']
        amount = Decimal(request.form['amount'])  # Convertir en Decimal
        # Connexion à la base de données
        connection = get_db_connection()


        cursor= connection.cursor()
        # Vérifier s'il y a des  non payés pour cet
        cursor.execute("""
            SELECT id_dossier, part_clinique, balance
            FROM dossier_patient
            WHERE id_doctor = %s AND (balance) > 0
        """, (id_doctor,))
        dossiers_nd = cursor.fetchall()

        # Vérifier que des non payés existent
        if len(dossiers_nd) == 0:
            return redirect_with_message('situation_medecin', "Aucun dossier a decaisser trouvé pour ce médecin.",
                                         'danger')

        # La clinique doit payer le médecin
        total_decaissement = Decimal(0)
        for dossier in dossiers_nd:
            montant_restant = (Decimal(dossier['balance']))

            if amount >= montant_restant:
                total_decaissement += montant_restant
                amount -= montant_restant

                # Mettre à jour le dossier avec un paiement total
                cursor.execute("""
                    UPDATE dossier_patient
                    SET balance = balance - %s
                    WHERE id_dossier = %s
                """, (montant_restant, dossier['id_dossier']))

                sql = """
                INSERT INTO doctor_situations (decaissement_clinique, id_doctor, id_dossier)
                VALUES (%s, %s, %s)
                """
                cursor.execute(sql, (montant_restant, id_doctor, dossier['id_dossier']))
                connection.commit()  # Appliquer les changements à la base de données

            else:
                total_decaissement += amount
                # Mettre à jour le dossier avec un paiement partiel
                cursor.execute("""
                    UPDATE dossier_patient
                    SET balance = balance - %s
                    WHERE id_dossier = %s
                """, (amount, dossier['id_dossier']))

                sql = """
                INSERT INTO doctor_situations (decaissement_clinique, id_doctor, id_dossier)
                VALUES (%s, %s, %s)
                """
                cursor.execute(sql, (amount, id_doctor, dossier['id_dossier']))

                connection.commit()  # Appliquer les changements à la base de données
                amount = Decimal(0)
                break

        # Flash pour indiquer si le paiement a été effectué
        if total_decaissement > 0:
            return redirect_with_message('situation_medecin', f'decaissement de {total_decaissement} effectué avec succès !',
                                         'success')
        else:
            return redirect_with_message('situation_medecin', "Montant insuffisant pour decaissement les dossiers.", 'danger')

    except Exception as e:
        print("*****")
        return redirect_with_message('situation_medecin', f'Erreur lors du decaissement : {e}', 'danger')

@app.route('/compensation_doctor', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def compensation_doctor():
    try:
        # Récupérer les données du formulaire
        id_doctor = request.form.get('id_doctor')
        if not id_doctor:
            return redirect_with_message('situation_medecin', "Médecin non spécifié.", 'danger')

        # Connexion à la base de données
        connection = get_db_connection()


        cursor= connection.cursor()
        # Récupérer les dossiers non payés et ceux à compenser
        cursor.execute("""
            SELECT id_dossier, part_clinique, balance
            FROM dossier_patient
            WHERE id_doctor = %s AND balance < 0
        """, (id_doctor,))
        dossiers_non_paye = list(cursor.fetchall())  # Convertir en liste pour modification

        # Récupérer les dossiers_non_paye avec balance > 0 (montant à compenser)
        cursor.execute("""
            SELECT id_dossier, part_clinique, balance
            FROM dossier_patient
            WHERE id_doctor = %s AND balance > 0
        """, (id_doctor,))
        dossiers_compensation = list(cursor.fetchall())

        if not dossiers_compensation:
            return redirect_with_message('situation_medecin', "Aucun montant disponible pour la compensation.", 'danger')

        if not dossiers_non_paye:
            return redirect_with_message('situation_medecin', "Aucun dossier non payé trouvé pour ce médecin.", 'danger')

        total_paiement = Decimal(0)

        # Parcourir les dossiers avec balance positive
        for dossier in dossiers_compensation:
            amount = Decimal(dossier['balance'])

            # Parcourir les dossiers non payés jusqu'à ce qu'ils soient réglés ou que le montant soit épuisé
            for dossier_n_p in dossiers_non_paye[:]:  # Itérer sur une copie pour modification
                if amount <= 0:
                    break

                montant_restant = Decimal(dossier_n_p['balance']) * (-1)

                if amount >= montant_restant:
                    # Régler complètement ce dossier
                    total_paiement += montant_restant
                    amount -= montant_restant

                    # Mettre à jour les balances et enregistrer les transactions
                    cursor.execute("""
                        UPDATE dossier_patient
                        SET balance = 0
                        WHERE id_dossier = %s
                    """, (dossier_n_p['id_dossier'],))

                    cursor.execute("""
                        INSERT INTO doctor_situations (compensation, id_doctor, id_dossier)
                        VALUES (%s, %s, %s)
                    """, (montant_restant, id_doctor, dossier_n_p['id_dossier']))

                    cursor.execute("""
                        UPDATE dossier_patient
                        SET balance = balance - %s 
                        WHERE id_dossier = %s
                    """, (montant_restant, dossier['id_dossier']))

                    cursor.execute("""
                        INSERT INTO doctor_situations (compensation, id_doctor, id_dossier) 
                        VALUES (%s, %s, %s)
                    """, (-montant_restant, id_doctor, dossier['id_dossier']))

                    connection.commit()
                    dossiers_non_paye.remove(dossier_n_p)  # Retirer le dossier réglé
                else:
                    # Paiement partiel
                    total_paiement += amount

                    cursor.execute("""
                        UPDATE dossier_patient
                        SET balance = balance - %s
                        WHERE id_dossier = %s
                    """, (amount, dossier_n_p['id_dossier']))

                    # Enregistrement de la transaction dans doctor_situations
                    cursor.execute("""
                        INSERT INTO doctor_situations (compensation, id_doctor, id_dossier)
                        VALUES (%s, %s, %s)
                    """, (amount, id_doctor, dossier_n_p['id_dossier']))

                    # Mise à jour du dossier positif après compensation
                    cursor.execute("""
                          UPDATE dossier_patient
                          SET balance = balance - %s
                          WHERE id_dossier = %s
                      """, (amount, dossier['id_dossier']))

                    cursor.execute("""
                          INSERT INTO doctor_situations (compensation, id_doctor, id_dossier)
                          VALUES (%s, %s, %s)
                    """, (-amount, id_doctor, dossier['id_dossier']))

                    connection.commit()
                    amount = Decimal(0)  # Montant épuisé
                    break

            if not dossiers_non_paye or amount <= 0:
                break

            if total_paiement > 0:
                return redirect_with_message('situation_medecin', f'Compensation de {total_paiement} DA effectuée avec succès !', 'success')
            else:
                return redirect_with_message('situation_medecin', "Montant insuffisant pour payer les dossiers non payés.", 'danger')

    except Exception as e:
        return redirect_with_message('situation_medecin', f'Erreur lors de la compensation : {e}', 'danger')

@app.route('/situation_medecin')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def situation_medecin():
    try:
        connection = get_db_connection()


        cursor= connection.cursor()
        # Récupérer la liste des médecins et leurs spécialités
        cursor.execute("""
            SELECT d.*, s.name_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
        """)
        doctors = cursor.fetchall()


        cursor.execute("SELECT * FROM specialty")  # Assuming there's a specialties table
        specialties = cursor.fetchall()

        total_balance_all_doctors = 0  # Variable pour stocker le total des balances de tous les médecins

        # Ajouter les détails des dossiers et transactions pour chaque médecin
        for doctor in doctors:
            # Récupérer les dossiers pour chaque médecin
            cursor.execute("""
                SELECT d.id_dossier, d.balance, d.part_clinique, 
                       d.patient AS patient_name
                FROM dossier_patient d
                WHERE d.id_doctor = %s
            """, (doctor['id'],))
            dossiers = cursor.fetchall()

            # Calculer la balance totale de ce médecin
            doctor_total_balance = 0
            for dossier in dossiers:
                doctor_total_balance += dossier['balance']
                cursor.execute("""
                    SELECT ds.id_doctor_situations, ds.encaissement_patient, 
                           ds.encaissement_doctor, ds.decaissement_clinique, ds.compensation, 
                           ds.payment_date
                    FROM doctor_situations ds
                    WHERE ds.id_dossier = %s
                """, (dossier['id_dossier'],))
                dossier['transactions'] = cursor.fetchall()

            # Associer la balance totale au médecin
            doctor['total_balance'] = doctor_total_balance

            # Ajouter la balance de ce médecin au total global
            total_balance_all_doctors += doctor_total_balance

            # Associer les dossiers au médecin
            doctor['dossiers'] = dossiers

    except Exception as e:
        print(f"Erreur : {e}")
        doctors = []  # Renvoie une liste vide en cas d'erreur
        total_balance_all_doctors = 0

    finally:
        connection.close()

    # Renvoyer les données au template
    return render_template('situation_medecin.html',title="Situation medecin", doctors=doctors, specialties=specialties, total_balance_all_doctors=total_balance_all_doctors, user=g.user)


