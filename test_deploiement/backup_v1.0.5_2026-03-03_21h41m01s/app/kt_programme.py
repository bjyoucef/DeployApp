from datetime import datetime
from io import BytesIO

from flask import render_template, g, request, redirect, url_for, Response, jsonify
from xhtml2pdf import pisa

from app import app, get_db_connection
from app.auth import chargement
from app.error import handle_errors
from app.utiles import redirect_with_message, login_required, permission_required


@app.route('/kt_programme', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_IT_KT_PROGRAMME')
def kt_programme():
    # Récupération des paramètres GET
    selected_doctor = request.args.get('doctor', '')
    selected_convention = request.args.get('convention', 'all')
    selected_start_date = request.args.get('start_date', '')
    selected_end_date = request.args.get('end_date', '')

    user = g.user
    user_id = user['id_personnel']

    # Valeurs par défaut
    DEFAULT_START = "2025-01-01"
    DEFAULT_END = "2025-02-01"

    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        # --- 1. Gestion des dates ---
        cursor.execute("""
            SELECT start_date, end_date 
            FROM config_date
            WHERE user_id = %s AND page = 'kt_programme'
        """, (user_id,))
        config = cursor.fetchone()

        # Si aucune configuration n'existe, on insère les valeurs par défaut
        if not config:
            cursor.execute("""
                INSERT INTO config_date (user_id, page, start_date, end_date)
                VALUES (%s, 'kt_programme', %s, %s)
            """, (user_id, DEFAULT_START, DEFAULT_END))
            connection.commit()
            current_start_date, current_end_date = DEFAULT_START, DEFAULT_END
        else:
            current_start_date = str(config['start_date'])
            current_end_date = str(config['end_date'])

        # Mise à jour si les dates ont changé
        update_needed = False

        if selected_start_date and selected_start_date != current_start_date:
            cursor.execute("""
                UPDATE config_date SET start_date = %s
                WHERE user_id = %s AND page = 'kt_programme'
            """, (selected_start_date, user_id))
            update_needed = True

        if selected_end_date and selected_end_date != current_end_date:
            cursor.execute("""
                UPDATE config_date SET end_date = %s
                WHERE user_id = %s AND page = 'kt_programme'
            """, (selected_end_date, user_id))
            update_needed = True

        if update_needed:
            connection.commit()

        # Utilisation des valeurs de la base si non définies
        selected_start_date = selected_start_date or current_start_date
        selected_end_date = selected_end_date or current_end_date

        # --- 2. Requête principale ---
        query = """
            SELECT pl.id, pl.patient_name, pl.id_doctor, pl.date, 
                   kd.first_name AS doctor_nom, kd.last_name AS doctor_prenom,
                   pl.convention
            FROM kt_programme pl
            INNER JOIN kt_doctors kd ON pl.id_doctor = kd.id
            WHERE pl.date BETWEEN %s AND %s
        """
        query_params = [selected_start_date, selected_end_date]

        # Filtrage par médecin
        if selected_doctor:
            query += " AND pl.id_doctor = %s"
            query_params.append(selected_doctor)

        # Filtrage par convention
        if selected_convention != 'all':
            query += " AND pl.convention = %s"
            query_params.append(selected_convention)

        cursor.execute(query, query_params)
        kt_programmes = cursor.fetchall()

        # --- 3. Préparation des événements pour FullCalendar ---
        events = []
        for programme in kt_programmes:
            shift_date = programme['date']
            if isinstance(shift_date, str):
                shift_date = datetime.strptime(shift_date, "%Y-%m-%d").date()

            events.append({
                "id": programme['id'],
                "title": f"{programme['patient_name']} - Dr. {programme['doctor_nom']} {programme['doctor_prenom']} - {programme['convention']}",
                "start": shift_date.strftime("%Y-%m-%d"),
            })
        cursor.execute("SELECT id, first_name, last_name FROM kt_doctors")
        doctors = cursor.fetchall()

    finally:
        connection.close()

    # --- 4. Rendu du template ---
    return render_template(
        'kt_programme.html',
        events=events,
        doctors=doctors,
        selected_doctor=selected_doctor,
        selected_convention=selected_convention,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        title="Plannings",
        user=g.user
    )


@app.route('/save-kt-programme', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_IT_KT_PROGRAMME')
def save_planning_kt():
    # Récupération des filtres existants depuis la query string
    selected_doctor = request.args.get('doctor', 'all')
    selected_convention = request.args.get('convention', 'all')
    selected_start_date = request.args.get('start_date', '')
    selected_end_date = request.args.get('end_date', '')

    # Récupération des données du formulaire POST
    form_doctor = request.form.get('doctor')
    patient_full_name = request.form.get('patient')
    convention_type = request.form.get('convention')
    date = request.form.get('date')
    event_id = request.form.get('event_id')  # Ce champ peut être utilisé pour la modification

    if not all([form_doctor, patient_full_name, convention_type, date]):
        # Redirection si des champs sont manquants
        return redirect(url_for('kt_programme',
                                doctor=selected_doctor,
                                convention=selected_convention,
                                start_date=selected_start_date,
                                end_date=selected_end_date))

    # Validation de la date
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        # Redirection en cas d'erreur de validation
        return redirect(url_for('kt_programme',
                                doctor=selected_doctor,
                                convention=selected_convention,
                                start_date=selected_start_date,
                                end_date=selected_end_date))

    # Connexion et gestion de la base de données
    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        # Récupération du doctor via son identifiant (celui transmis par le formulaire)
        cursor.execute("""
            SELECT id FROM kt_doctors WHERE id = %s
        """, (form_doctor,))
        selected_doctor_row = cursor.fetchone()

        if not selected_doctor_row:
            return redirect(url_for('kt_programme',
                                    doctor=selected_doctor,
                                    convention=selected_convention,
                                    start_date=selected_start_date,
                                    end_date=selected_end_date))

        id_doctor = selected_doctor_row['id']

        if event_id:
            # Modification de l'événement existant
            cursor.execute("""
                UPDATE kt_programme
                SET id_doctor = %s, date = %s, convention = %s
                WHERE id = %s
            """, (id_doctor, date, convention_type, event_id))
        else:
            # Ajout d'un nouvel événement
            cursor.execute("""
                INSERT INTO kt_programme (id_doctor, date, patient_name, convention)
                VALUES (%s, %s, %s, %s)
            """, (id_doctor, date, patient_full_name, convention_type))

            connection.commit()
    except Exception as e:
        connection.rollback()
        print("Erreur lors de la modification/ajout de l'événement :", e)
        return redirect(url_for('kt_programme',
                                doctor=selected_doctor,
                                convention=selected_convention,
                                start_date=selected_start_date,
                                end_date=selected_end_date))
    finally:
        connection.close()

    chargement()  # Si cette fonction est nécessaire pour recharger les événements

    # Redirection avec les filtres conservés
    return redirect(url_for('kt_programme',
                            doctor=selected_doctor,
                            convention=selected_convention,
                            start_date=selected_start_date,
                            end_date=selected_end_date))



@app.route('/update-event-kt', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_IT_KT_PROGRAMME')
def update_event_planning_kt():
    # Récupération des données POST pour la mise à jour
    event_id = request.form.get('event_id')
    new_date = request.form.get('start')

    # Récupération des filtres existants (ils peuvent être transmis via POST ou GET selon votre implémentation)
    selected_doctor = request.form.get('doctor', 'all')
    selected_patient = request.form.get('patient', 'all')
    selected_convention = request.form.get('convention', 'all')
    selected_start_date = request.form.get('start_date', '')
    selected_end_date = request.form.get('end_date', '')

    # Validation des données obligatoires
    if not event_id or not new_date:
        return redirect(url_for('kt_programme',
                                doctor=selected_doctor,
                                patient=selected_patient,
                                convention=selected_convention,
                                start_date=selected_start_date,
                                end_date=selected_end_date,
                                message="Données invalides.",
                                category='danger'))

    # Mise à jour dans la base de données
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
                "UPDATE kt_programme SET date = %s WHERE id = %s",
                (new_date, event_id))
        connection.commit()
        chargement()
        return redirect(url_for('kt_programme',
                                doctor=selected_doctor,
                                patient=selected_patient,
                                convention=selected_convention,
                                start_date=selected_start_date,
                                end_date=selected_end_date,
                                message="Le kt_programme a été modifié avec succès.",
                                category='success'))
    except Exception as e:
        connection.rollback()
        return redirect(url_for('kt_programme',
                                doctor=selected_doctor,
                                patient=selected_patient,
                                convention=selected_convention,
                                start_date=selected_start_date,
                                end_date=selected_end_date,
                                message=f"Erreur lors de la mise à jour : {str(e)}",
                                category='danger'))
    finally:
        connection.close()


@app.route('/delete-event-kt/<int:event_id>', methods=['DELETE'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_IT_KT_PROGRAMME')
def delete_event_planning_kt(event_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM kt_programme WHERE id = %s", (event_id,))
        connection.commit()
        chargement()

        # Retourner un message de succès après suppression
        return jsonify({"success": True, "message": "Événement supprimé avec succès"}), 200

    except Exception as e:
        connection.rollback()
        return jsonify({"success": False, "message": f"Erreur : {str(e)}"}), 500
    finally:
        connection.close()
