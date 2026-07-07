from collections import defaultdict

from flask import request, redirect, url_for, render_template, g, flash, jsonify
from decimal import Decimal
from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, permission_required
from datetime import date

# Route pour gérer l'ajout de dossier
@app.route('/kt_dossier_patient', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_DOSSIERS_PATIENTS_KT')
def kt_dossier_patient():
    # Récupérer les paramètres de requête
    doctor_filter = request.args.get('doctor', 'all')
    start_date = request.args.get('start_date',date.today())
    end_date = request.args.get('end_date',date.today())
    print(start_date,end_date)

    user = g.user
    user_id = user['id_personnel']
    connection = get_db_connection()
    cursor = connection.cursor()

    # Gestion des dates de configuration
    cursor.execute("""
                    SELECT start_date, end_date 
                    FROM config_date 
                    WHERE user_id = %s AND page = 'dossier_kt' 
                    """
                   , (user_id,))
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

    # … après fetchone() …
    current_start_date = result['start_date'] or date.today()
    current_end_date = result['end_date'] or date.today()

    # Mise à jour des dates de configuration
    if start_date == start_date or str(current_start_date):
        cursor.execute("""
                        UPDATE config_date
                            SET start_date = %s
                            WHERE user_id = %s AND page = 'dossier_kt'
            """, (start_date, user_id))

    if end_date == end_date or str(current_end_date):
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
    print(start_date,end_date)
    base_query = """
            SELECT
                d.id_dossier,
                CONCAT(doc.first_name, ' ', doc.last_name) AS doctor_name, 
                d.patient AS patient_name, 
                d.acte_date, 
                d.urgence, 

                ak.code_cnas, 
                ak.name_acte_kt, 

                d.nbr_nuite, 
                d.vip, 
                d.nbr_nuite_conjoint, 
                d.prix_hospitalisation, 
                d.prix_conjoint, 
                d.extras, 
                d.prix_dossier_convention, 
                d.prix_dossier_esp, 
                d.part_operateur_extrat, 
                dak.convention,  
                dak.part_operateur AS part_operateur_acte 
            FROM kt_dossier_patient d
            LEFT JOIN kt_dossier_actes dak ON d.id_dossier = dak.id_dossier
            LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
            LEFT JOIN kt_doctors doc ON d.id_doctor = doc.id
            WHERE 1 = 1
        """

    print(base_query)

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
    cursor.execute("SELECT id, CONCAT(first_name, ' ', last_name) AS name FROM kt_doctors")
    kt_doctors = cursor.fetchall()

    cursor.execute("SELECT * FROM kt_actes")
    acts_kt = cursor.fetchall()

    cursor.execute(query, query_params)
    dossiers = cursor.fetchall()
    return render_template(
        'kt_dossier_patient.html',
        kt_doctors=kt_doctors or [],
        acts_kt=acts_kt or [],
        dossiers=dossiers or [],
        start_date=start_date or '',
        end_date=end_date or '',
        title="Gestion des Dossiers",
        user=g.user
    )

@app.route('/ajouter_dossier_kt', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ADD_DOSSIERS_PATIENTS_KT')
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
        'extra_percentage': get_form_value('extraPercentage', 20, int),
        'extras': get_form_value('extras', 0, int),
    }

    # if None in form_data.values():  # Vérifie si un champ est invalide
    #     return redirect(url_for('kt_dossier_patient'))

    acte_keys = [key for key in request.form.keys() if key.startswith('id_acte_')]

    # Définir des constantes pour les valeurs utilisées
    prix_nuit_extra_standard = 15000
    prix_nuit_extra_vip = 30000
    prix_nuit_vip = 18000
    prix_hospitalisation = 0
    kt_nights = 0

    total_part_operateur = 0
    total_part_clinique = 0
    prix_dossier_convention = 0
    prix_dossier_esp = 0
    part_operateur = 0
    part_clinique_convention = 0
    part_clinique_esp = 0

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Calcul des coûts pour le conjoint
        prix_conjoint = form_data['nbr_nuite_conjoint'] * 8000

        prix_extras = form_data['extras']
        part_operateur_extrat = form_data['extras'] * (form_data['extra_percentage']/100)


        # Insertion du dossier dans la base de données
        query = """INSERT INTO kt_dossier_patient ( 
                    id_doctor, patient, acte_date, nbr_nuite, vip,
                    nbr_nuite_conjoint, prix_conjoint,extras,part_operateur_extrat) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        values = (
            form_data['id_doctor'],
            form_data['patient'],
            form_data['acte_date'],
            form_data['nbr_nuite'],
            form_data['vip'],
            form_data['nbr_nuite_conjoint'],
            prix_conjoint,
            prix_extras,
            part_operateur_extrat
        )
        cursor.execute(query, values)
        connection.commit()
        id_dossier = cursor.lastrowid

        if acte_keys:
            grouped_actes = []

            for key in acte_keys:
                acte_id = request.form[key]
                convention = request.form.get(f"convention_acte_kt_{key.split('_')[-1]}")
                if not convention:
                    flash("Type de convention obligatoire pour chaque acte.", 'danger')
                    return redirect(url_for('kt_dossier_patient'))

                # Récupérer les détails de l'acte
                cursor.execute(""" 
                    SELECT id_acte, 
                    nbr_nuit, 
                    prix_cnas_casnos, 
                    prix_autre_convention, 
                    prix_public, 
                    urgence, 
                    part_operateur_cnas_casnos, 
                    part_operateur_payante, 
                    part_operateur_urgence 
                    FROM kt_actes 
                    WHERE id_acte = %s
                """, (acte_id,))
                kt_data = cursor.fetchone()

                if not kt_data:
                    flash(f"L'acte ID {acte_id} n'existe pas.", 'danger')
                    return redirect(url_for('kt_dossier_patient'))

                if form_data['urgenceCheck']:
                    part_clinique_esp = kt_data['urgence']
                    total_part_clinique += kt_data['urgence']

                    total_part_operateur += kt_data['part_operateur_urgence']
                    part_operateur = kt_data['part_operateur_urgence']

                elif convention == 'payante':
                    part_clinique_esp = kt_data['prix_public']
                    total_part_clinique += kt_data['prix_public']

                    total_part_operateur += kt_data['part_operateur_payante']
                    part_operateur = kt_data['part_operateur_payante']
                else:
                    part_clinique_convention = kt_data['prix_cnas_casnos']
                    total_part_clinique += kt_data['prix_cnas_casnos']
                    total_part_operateur += kt_data['part_operateur_cnas_casnos']
                    part_operateur = kt_data['part_operateur_cnas_casnos']

                # Insérer les actes dans la table associée
                cursor.execute("""
                    INSERT INTO kt_dossier_actes (
                    id_dossier, 
                    id_acte, 
                    convention, 
                    part_operateur, 
                    part_clinique_convention, 
                    part_clinique_esp
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (id_dossier,
                          acte_id,
                          convention,
                          part_operateur,
                          part_clinique_convention,
                          part_clinique_esp))
                connection.commit()

                prix_dossier_convention += part_clinique_convention
                prix_dossier_esp += part_clinique_esp

                part_clinique_convention = 0
                part_clinique_esp = 0

                kt_nights += kt_data['nbr_nuit']
                grouped_actes.append(acte_id)

            prix_dossier_esp += prix_extras

            # Calcul des nuits supplémentaires et des frais d'hospitalisation
            extra_nights = form_data['nbr_nuite'] - kt_nights
            prix_hospitalisation += max(0, extra_nights) * (
                prix_nuit_extra_vip if form_data['vip'] else prix_nuit_extra_standard)
            prix_hospitalisation += kt_nights * (prix_nuit_vip if form_data['vip'] else 0)

            total_part_operateur += Decimal(part_operateur_extrat)

            # Mise à jour finale des informations du dossier
            cursor.execute("""
                UPDATE kt_dossier_patient SET 
                urgence = %s, 
                prix_hospitalisation = %s, 
                part_operateur = %s, 
                prix_dossier_convention = %s,  
                prix_dossier_esp = %s 
                WHERE id_dossier = %s
            """, (form_data['urgenceCheck'],
                  prix_hospitalisation,
                  total_part_operateur,
                  prix_dossier_convention,
                  prix_dossier_esp,
                  id_dossier,))
            connection.commit()

            # Insertion dans la table kt_doctor_situations
            cursor.execute("""
                            INSERT INTO kt_doctor_situations 
                            (id_doctor, 
                            id_dossier, 
                            part_operateur)
                VALUES (%s, %s, %s)
            """, (form_data['id_doctor'], id_dossier, total_part_operateur))
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


@app.route('/supprimer_dossier_kt', methods=['POST'])
@login_required
@handle_errors()
@permission_required('DELETE_DOSSIERS_PATIENTS_KT')
def supprimer_dossier_kt():
    """Supprime un dossier KT et ses données associées."""
    id_dossier = request.form.get('id_dossier')

    if not id_dossier:
        flash("ID dossier manquant.", 'danger')
        return redirect(url_for('kt_dossier_patient'))

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Suppression des données liées dans les tables associées
        cursor.execute("DELETE FROM kt_dossier_actes WHERE id_dossier = %s", (id_dossier,))
        cursor.execute("DELETE FROM kt_doctor_situations WHERE id_dossier = %s", (id_dossier,))

        # Suppression du dossier principal
        cursor.execute("DELETE FROM kt_dossier_patient WHERE id_dossier = %s", (id_dossier,))

        connection.commit()
        flash("Dossier supprimé avec succès.", 'success')

    except Exception as e:
        connection.rollback()
        flash(f"Erreur lors de la suppression : {str(e)}", 'danger')

    finally:
        connection.close()

    return redirect(url_for('kt_dossier_patient'))