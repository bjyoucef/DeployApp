import math

from flask import request, redirect, url_for, render_template, g, flash, jsonify
from collections import defaultdict

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, permission_required, has_permission


# Route pour gérer l'ajout de dossier
@app.route('/kt_dossier_patient', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def kt_dossier_patient():
    # Récupérer les paramètres de requête
    doctor_filter = request.args.get('doctor', 'all')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    user = g.user
    user_id = user['id_personnel']
    connection = get_db_connection()
    cursor = connection.cursor()
    # Gestion des dates de configuration
    cursor.execute("""
                        SELECT start_date, end_date 
                        FROM config_date 
                        WHERE user_id = %s AND page = 'dossier_kt'
                        """, (user_id,))
    result = cursor.fetchone()

    if not result:
        # Insertion initiale si aucune configuration n'existe
        cursor.execute("""
                            INSERT INTO config_date (user_id, page)
                            VALUES (%s, 'dossier_kt')
                            """, (user_id,))
        connection.commit()

        # Récupérer les données insérées
        cursor.execute("""
                            SELECT start_date, end_date 
                            FROM config_date
                            WHERE user_id = %s AND page = 'dossier_kt'
            """, (user_id,))
        result = cursor.fetchone()

    current_start_date = result['start_date']
    current_end_date = result['end_date']

    # Mise à jour des dates de configuration
    if start_date and start_date != str(current_start_date):
        cursor.execute("""
                        UPDATE config_date
                            SET start_date = %s
                            WHERE user_id = %s AND page = 'dossier_kt'
            """, (start_date, user_id))

    if end_date and end_date != str(current_end_date):
        cursor.execute("""
                        UPDATE config_date
                            SET end_date = %s
                WHERE user_id = %s AND page = 'dossier_kt'
            """, (end_date, user_id))

    # Valider les changements
    connection.commit()

    # Utiliser les dates filtrées ou par défaut
    start_date = start_date or str(current_start_date)
    end_date = end_date or str(current_end_date)
    base_query = ''

    base_query = """
            SELECT
                d.id_dossier,
                CONCAT(doc.first_name, ' ', doc.last_name) AS doctor_name, 
                d.patient AS patient_name, 
                d.acte_date, 
                d.urgence, 

                ak.code_cnas, 
                ak.name_acte_kt, 
                ak.part_operateur_cnas_casnos, 
                ak.part_operateur_payante, 
                ak.part_operateur_urgence, 
                d.nbr_nuite, 
                d.vip, 
                d.nbr_nuite_conjoint, 
                d.prix_hospitalisation, 
                d.prix_conjoint, 
                d.extras, 
                d.part_operateur, 
                dak.convention 
            FROM kt_dossier_patient d
            LEFT JOIN kt_dossier_actes dak ON d.id_dossier = dak.id_dossier
            LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
            LEFT JOIN doctors doc ON d.id_doctor = doc.id
            WHERE 1 = 1
        """

    query_filters = " "
    query_params = {}

    if doctor_filter != 'all':
        query_filters += " AND d.id_doctor = %(doctor_id)s"
        query_params['doctor_id'] = doctor_filter

    if start_date:
        query_filters += " AND d.acte_date >= %(start_date)s"
        query_params['start_date'] = start_date

    if end_date:
        query_filters += " AND d.acte_date <= %(end_date)s"
        query_params['end_date'] = end_date

    query = base_query + query_filters + " ORDER BY d.id_dossier DESC"

    # Récupérer les données nécessaires pour le formulaire
    cursor = connection.cursor()
    cursor.execute("SELECT id, CONCAT(first_name, ' ', last_name) AS name FROM doctors")
    doctors = cursor.fetchall()

    cursor.execute("SELECT * FROM forfait_actes")
    acts = cursor.fetchall()

    cursor.execute("SELECT * FROM kt_actes")
    acts_kt = cursor.fetchall()

    cursor.execute("SELECT * FROM bloc")
    blocs = cursor.fetchall()

    cursor.execute(query, query_params)
    dossiers = cursor.fetchall()

    # Regrouper les dossiers par ID
    grouped_dossiers = defaultdict(list)
    for dossier in dossiers:
        grouped_dossiers[dossier['id_dossier']].append(dossier)

    return render_template(
        'kt_dossier_patient.html',
        doctors=doctors or [],
        acts=acts or [],
        acts_kt=acts_kt or [],
        blocs=blocs or [],
        dossiers=dossiers or [],
        start_date=start_date or '',
        end_date=end_date or '',
        grouped_dossiers=grouped_dossiers,
        title="Gestion des Dossiers",
        user=g.user
    )


@app.route('/ajouter_dossier_kt', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def ajouter_dossier_kt():
    """Ajoute un dossier KT et ses actes associés avec calculs et validations."""

    def get_form_value(field, default=None, cast_func=None):
        """Retrieve a form value with optional casting and default fallback."""
        value = request.form.get(field, default)
        if cast_func:
            try:
                return cast_func(value)
            except ValueError:
                flash(f"Le champ '{field}' est invalide.", 'danger')
                return None
        return value

    def validate_required_fields(fields):
        """Ensure all required fields are present and valid."""
        missing_fields = [field for field in fields if not request.form.get(field)]
        if missing_fields:
            for field in missing_fields:
                flash(f"Le champ '{field}' est obligatoire.", 'danger')
                return False
        return True

    # Champs obligatoires pour l'ajout de dossier
    required_fields = ['id_doctor', 'patient', 'acte_date']
    if not validate_required_fields(required_fields):
        return redirect(url_for('kt_dossier_patient'))

    # Récupérer les données du formulaire
    form_data = {
        'id_doctor': request.form['id_doctor'],
        'patient': request.form['patient'],
        'acte_date': request.form['acte_date'],
        'nbr_nuite': get_form_value('nbr_nuite', 0, int),
        'vip': request.form.get('vip'),
        'nbr_nuite_conjoint': get_form_value('nbr_nuite_conjoint', 0, int),
        'urgenceCheck': request.form.get('urgenceCheck'),
    }

    # if None in form_data.values():  # Vérifie si un champ est invalide
    #     return redirect(url_for('kt_dossier_patient'))

    acte_keys = [key for key in request.form.keys() if key.startswith('id_acte_')]

    print(acte_keys)

    prix_hospitalisation = 0
    kt_nights = 0
    part_operateur = 0

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Calcul des coûts pour le conjoint
        prix_conjoint = form_data['nbr_nuite_conjoint'] * 8000

        # Insertion du dossier dans la base de données
        query = """INSERT INTO kt_dossier_patient ( 
                    id_doctor, patient, acte_date, nbr_nuite, vip,
                    nbr_nuite_conjoint, prix_conjoint) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        values = (
            form_data['id_doctor'], form_data['patient'], form_data['acte_date'],
            form_data['nbr_nuite'], form_data['vip'], form_data['nbr_nuite_conjoint'],
            prix_conjoint
        )
        cursor.execute(query, values)
        connection.commit()
        id_dossier = cursor.lastrowid

        if acte_keys:
            # Définir des constantes pour les valeurs utilisées
            prix_nuit_extra_standard = 15000
            prix_nuit_extra_vip = 30000
            prix_nuit_vip = 18000

            grouped_actes = []

            for key in acte_keys:
                acte_id = request.form[key]
                convention = request.form.get(f"convention_acte_kt_{key.split('_')[-1]}")
                if not convention:
                    flash("Type de convention obligatoire pour chaque acte.", 'danger')
                    return redirect(url_for('kt_dossier_patient'))

                # Insérer les actes dans la table associée
                cursor.execute("""
                    INSERT INTO kt_dossier_actes (id_dossier, id_acte, convention)
                    VALUES (%s, %s, %s)
                    """, (id_dossier, acte_id, convention))
                connection.commit()

                # Récupérer les détails de l'acte
                cursor.execute("""
                    SELECT id_acte, nbr_nuit, part_operateur_cnas_casnos, 
                           part_operateur_payante, part_operateur_urgence 
                    FROM kt_actes 
                    WHERE id_acte = %s
                """, (acte_id,))
                kt_data = cursor.fetchone()

                if not kt_data:
                    flash(f"L'acte ID {acte_id} n'existe pas.", 'danger')
                    return redirect(url_for('kt_dossier_patient'))

                kt_nights += kt_data['nbr_nuit']
                grouped_actes.append(acte_id)

                if form_data['urgenceCheck'] == 1:
                    part_operateur += kt_data['part_operateur_urgence']
                elif convention == 'payante':
                    part_operateur += kt_data['part_operateur_payante']
                else:
                    part_operateur += kt_data['part_operateur_cnas_casnos']

            # Vérifier les conditions spécifiques pour grouped_actes
            if len(grouped_actes) > 1 and '1' in grouped_actes and any(
                    acte in grouped_actes for acte in {'3', '4', '5', '6'}):
                # Réduction opérateur pour le cas spécifique
                part_operateur -= 22000 if form_data['urgenceCheck'] == 1 else 17000
                c1 = 0
            elif '1' in grouped_actes:
                # Acte C1 présent
                c1 = 1
            else:
                # Aucun acte C1
                c1 = 0

            # Vérifier si le patient a déjà effectué un acte C1
            cursor.execute("""
                SELECT d.id_dossier, d.c1 
                FROM kt_dossier_patient d
    JOIN kt_dossier_actes dak ON d.id_dossier = dak.id_dossier
    JOIN kt_actes ak ON dak.id_acte = ak.id_acte
                WHERE d.patient = %s AND ak.code_cnas = 'C1' AND d.c1 = 1
            """, (form_data['patient'],))
            dossier = cursor.fetchone()

            if dossier:
                # Appliquer la déduction si un dossier C1 existe
                part_operateur -= 22000 if form_data['urgenceCheck'] == 1 else 17000

                # Mettre à jour le dossier précédent (désactiver c1)
                cursor.execute("""
                    UPDATE kt_dossier_patient
                    SET c1 = 0
                    WHERE id_dossier = %s
                """, (dossier['id_dossier'],))
                connection.commit()

            # Calcul des nuits supplémentaires et des frais d'hospitalisation
            extra_nights = form_data['nbr_nuite'] - kt_nights
            prix_hospitalisation += max(0, extra_nights) * (
                prix_nuit_extra_vip if form_data['vip'] else prix_nuit_extra_standard)
            prix_hospitalisation += kt_nights * (prix_nuit_vip if form_data['vip'] else 0)

            # Mise à jour finale des informations du dossier
            cursor.execute("""
                UPDATE kt_dossier_patient 
                SET c1 = %s, urgence = %s, prix_hospitalisation = %s, part_operateur = %s 
                WHERE id_dossier = %s
            """, (c1, form_data['urgenceCheck'], prix_hospitalisation, part_operateur, id_dossier,))
            connection.commit()


            # Insertion dans la table kt_doctor_situations
            cursor.execute("""
                            INSERT INTO kt_doctor_situations (id_doctor, id_dossier, part_operateur)
                VALUES (%s, %s, %s)
            """, (form_data['id_doctor'], id_dossier, part_operateur))
            connection.commit()

        flash("Dossier et actes ajoutés avec succès.", 'success')
        return redirect(url_for('kt_dossier_patient'))

    except Exception as e:
        flash(f"Une erreur est survenue : {str(e)}", 'danger')
        return redirect(url_for('kt_dossier_patient'))



@app.route('/autocompletekt', methods=['GET'])
@login_required
def autocompletekt():
    query = request.args.get('query', '')
    if not query:
        return jsonify([])

    connection = get_db_connection()
    cursor = connection.cursor()

    # Fetch distinct patients matching the query
    cursor.execute("""
        SELECT DISTINCT patient
        FROM kt_dossier_patient
        WHERE patient LIKE %s
        LIMIT 10
    """, (f"%{query}%",))
    patients = [{'patient': row['patient']} for row in cursor.fetchall()]

    cursor.close()
    connection.close()

    return jsonify(patients)


