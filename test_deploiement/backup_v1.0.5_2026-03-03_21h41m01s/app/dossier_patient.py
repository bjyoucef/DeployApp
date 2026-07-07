import math
from collections import defaultdict

from flask import request, redirect, url_for, render_template, g, flash, jsonify

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, permission_required


# Route pour gérer l'ajout de dossier
@app.route('/dossier_patient', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def dossier_patient():
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
                        WHERE user_id = %s AND page = 'dossier'
                        """, (user_id,))
    result = cursor.fetchone()

    if not result:
        # Insertion initiale si aucune configuration n'existe
        cursor.execute("""
                            INSERT INTO config_date (user_id, page)
                            VALUES (%s, 'dossier')
                            """, (user_id,))
        connection.commit()

        # Récupérer les données insérées
        cursor.execute("""
                            SELECT start_date, end_date 
                            FROM config_date
                            WHERE user_id = %s AND page = 'dossier'
            """, (user_id,))
        result = cursor.fetchone()

    current_start_date = result['start_date']
    current_end_date = result['end_date']

    # Mise à jour des dates de configuration
    if start_date and start_date != str(current_start_date):
        cursor.execute("""
                        UPDATE config_date
                            SET start_date = %s
                            WHERE user_id = %s AND page = 'dossier'
            """, (start_date, user_id))

    if end_date and end_date != str(current_end_date):
        cursor.execute("""
                        UPDATE config_date
                            SET end_date = %s
                WHERE user_id = %s AND page = 'dossier'
            """, (end_date, user_id))

    # Valider les changements
    connection.commit()

    # Utiliser les dates filtrées ou par défaut
    start_date = start_date or str(current_start_date)
    end_date = end_date or str(current_end_date)

    base_query = """
        SELECT
            d.*, 
            IFNULL(a.name_forfait, d.custom_acte) AS act_name,
            doc.id AS id_doctor, 
            CONCAT(doc.first_name, ' ', doc.last_name) AS doctor_name, 
            d.patient AS patient_name, 
            b.name_bloc
        FROM dossier_patient d
        LEFT JOIN doctors doc ON d.id_doctor = doc.id
        LEFT JOIN forfait_actes a ON d.forfait_id = a.id_forfait
        LEFT JOIN bloc b ON d.id_bloc = b.id_bloc
        WHERE 1 = 1 
    """

    query_filters = ""
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

    cursor.execute("SELECT * FROM bloc")
    blocs = cursor.fetchall()

    cursor.execute(query, query_params)
    dossiers = cursor.fetchall()

    # Récupérer les produits depuis la base
    cursor.execute("SELECT * FROM produits")
    produits = cursor.fetchall()

    # Regrouper les dossiers par ID si besoin (optionnel)
    grouped_dossiers = defaultdict(list)
    for dossier in dossiers:
        grouped_dossiers[dossier['id_dossier']].append(dossier)

    return render_template(
        'dossier_patient.html',
        doctors=doctors or [],
        acts=acts or [],
        blocs=blocs or [],
        dossiers=dossiers or [],
        produits=produits or [],
        start_date=start_date or '',
        end_date=end_date or '',
        grouped_dossiers=grouped_dossiers,
        title="Gestion des Dossiers",
        user=g.user
    )


# Ajouter cette route pour récupérer les produits du forfait
@app.route('/get_forfait_products')
@login_required
def get_forfait_products():
    forfait_id = request.args.get('forfait_id')
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT p.id_produit, p.description, p.prix, fp.qte as qte_incluse
        FROM forfait_actes_produits fp
        JOIN produits p ON fp.id_produit = p.id_produit
        WHERE fp.id_forfait = %s
    """, (forfait_id,))

    products = cursor.fetchall()
    return jsonify(products)

@app.route('/ajouter_dossier', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def ajouter_dossier():
    def get_form_value(field, default=None):
        """Récupère la valeur d'un champ du formulaire avec une valeur par défaut."""
        return request.form.get(field, default) or default

    def validate_required_fields(fields):
        """Vérifie que tous les champs obligatoires sont présents."""
        missing_fields = [field for field in fields if not request.form.get(field)]
        if missing_fields:
            for field in missing_fields:
                flash(f"Le champ '{field}' est obligatoire.", 'danger')
            return False
        return True

    # Vérification des champs obligatoires
    required_fields = ['id_doctor', 'patient', 'acte_date']
    if not validate_required_fields(required_fields):
        return redirect(url_for('dossier_patient'))

    try:
        form_data = {
            'id_doctor': request.form['id_doctor'],
            'patient': request.form['patient'],
            'acte_date': request.form['acte_date'],
            'encaissement_patient': float(request.form['encaissement_patient']),
            'nbr_nuite': int(get_form_value('nbr_nuite', 0)),
            'vip': request.form.get('vip'),
            'nbr_nuite_conjoint': int(get_form_value('nbr_nuite_conjoint', 0)),
            'extras': float(get_form_value('extras', 0)),
            'convention': request.form.get('conventionCheckbox'),
            'forfait': request.form.get('forfait'),
            'forfait_id': get_form_value('forfait_id'),
            'custom_acte': request.form.get('custom_acte'),
            'duree_acte': float(get_form_value('duree_acte', 0)),
            'id_bloc': request.form.get('id_bloc'),
        }
    except ValueError:
        flash("Erreur lors de la conversion des données.", 'danger')
        return redirect(url_for('dossier_patient'))

    prix_hospitalisation = 0
    connection = get_db_connection()
    cursor = connection.cursor()

    # Calcul du coût conjoint
    prix_conjoint = form_data['nbr_nuite_conjoint'] * 8000

    # Insertion initiale dans dossier_patient (informations de base)
    query = """
        INSERT INTO dossier_patient ( 
                id_doctor, patient, acte_date, nbr_nuite, vip,
            nbr_nuite_conjoint, extras, prix_conjoint
        ) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        form_data['id_doctor'], form_data['patient'],
        form_data['acte_date'], form_data['nbr_nuite'], form_data['vip'],
        form_data['nbr_nuite_conjoint'], form_data['extras'], prix_conjoint
    )
    cursor.execute(query, values)
    connection.commit()
    id_dossier = cursor.lastrowid

    if form_data['forfait']:
        # -------------------- Gestion du forfait --------------------
        cursor.execute(
            "SELECT id_forfait, duree_forfait, nbr_nuit, prix_forfait FROM forfait_actes WHERE id_forfait = %s",
            (form_data['forfait_id'],)
        )
        forfait_data = cursor.fetchone()
        if not forfait_data:
            flash("Forfait non trouvé.", "danger")
            return redirect(url_for('dossier_patient'))

        extra_nights = form_data['nbr_nuite'] - forfait_data['nbr_nuit']
        prix_hospitalisation += max(0, extra_nights) * (30000 if form_data['vip'] else 15000)
        # Coût forfaitaire pour les nuits incluses (si applicable)
        prix_hospitalisation += forfait_data['nbr_nuit'] * (18000 if form_data['vip'] else 0)
        extra_duration = form_data['duree_acte'] - forfait_data['duree_forfait']
        prix_bloc = max(0, math.ceil(extra_duration / 30)) * 5000

        part_clinique = prix_hospitalisation + prix_conjoint + prix_bloc + forfait_data['prix_forfait'] + form_data['extras']
        balance = form_data['encaissement_patient'] - part_clinique

        update_query = """
            UPDATE dossier_patient SET 
                forfait_id = %s, duree_acte = %s, prix_forfait = %s, prix_bloc = %s,
                prix_hospitalisation = %s, part_clinique = %s, balance = %s
            WHERE id_dossier = %s
        """
        update_values = (
            forfait_data['id_forfait'], form_data['duree_acte'], forfait_data['prix_forfait'], prix_bloc,
            prix_hospitalisation, part_clinique, balance, id_dossier
        )
        cursor.execute(update_query, update_values)
        connection.commit()

        # -------------------- Insertion des produits consommés du forfait --------------------
        extra_products_cost = 0
        cursor.execute(
            "SELECT id_produit, qte FROM forfait_actes_produits WHERE id_forfait = %s",
            (form_data['forfait_id'],)
        )
        forfait_products = cursor.fetchall()
        for fp in forfait_products:
            id_produit = fp['id_produit']
            qte_incluse = fp['qte']
            # Récupérer la quantité saisie pour ce produit
            qty_str = request.form.get(f'produit_{id_produit}', '0')
            try:
                qty_used = int(qty_str)
            except ValueError:
                qty_used = 0

            # Insertion dans dossier_produits
            cursor.execute(
                "INSERT INTO dossier_produits (id_dossier, id_produit, qte_utilisee) VALUES (%s, %s, %s)",
                (id_dossier, id_produit, qty_used)
            )
            # Calcul du supplément si la quantité utilisée dépasse la quantité incluse
            if qty_used > qte_incluse:
                surplus = qty_used - qte_incluse
                cursor.execute("SELECT prix FROM produits WHERE id_produit = %s", (id_produit,))
                product = cursor.fetchone()
                product_price = float(product['prix']) if product and product.get('prix') else 0
                extra_products_cost += surplus * product_price
        connection.commit()

        new_extras = form_data['extras'] + extra_products_cost
        new_part_clinique = prix_hospitalisation + prix_conjoint + prix_bloc + forfait_data['prix_forfait'] + new_extras
        new_balance = form_data['encaissement_patient'] - new_part_clinique

        cursor.execute(
            "UPDATE dossier_patient SET extras = %s, part_clinique = %s, balance = %s WHERE id_dossier = %s",
            (new_extras, new_part_clinique, new_balance, id_dossier)
        )
        connection.commit()

        cursor.execute(
            "INSERT INTO doctor_situations (encaissement_patient, id_doctor, id_dossier) VALUES (%s, %s, %s)",
            (form_data['encaissement_patient'], form_data['id_doctor'], id_dossier)
        )
        connection.commit()

    else:
        # -------------------- Gestion sans forfait --------------------
        cursor.execute("SELECT prix_bloc FROM bloc WHERE id_bloc = %s", (form_data['id_bloc'],))
        bloc_data = cursor.fetchone()
        prix_bloc = bloc_data['prix_bloc'] + max(0, math.ceil((form_data['duree_acte'] - 90) / 30)) * 5000
        prix_hospitalisation += max(0, form_data['nbr_nuite']) * (30000 if form_data['vip'] else 12000)
        part_clinique = prix_hospitalisation + prix_conjoint + prix_bloc + form_data['extras']
        balance = form_data['encaissement_patient'] - part_clinique

        cursor.execute(
            """
            UPDATE dossier_patient SET 
                custom_acte = %s, duree_acte = %s, id_bloc = %s, prix_bloc = %s,
                prix_hospitalisation = %s, part_clinique = %s, balance = %s
            WHERE id_dossier = %s
            """,
            (form_data['custom_acte'], form_data['duree_acte'], form_data['id_bloc'],
             prix_bloc, prix_hospitalisation, part_clinique, balance, id_dossier)
        )
        connection.commit()

        cursor.execute(
            "INSERT INTO doctor_situations (encaissement_patient, id_doctor, id_dossier) VALUES (%s, %s, %s)",
            (form_data['encaissement_patient'], form_data['id_doctor'], id_dossier)
        )
        connection.commit()

    # -------------------- Insertion des produits consommés ajoutés manuellement --------------------
    # Parcourir les clés du formulaire qui commencent par "manual_product_"
    for key, value in request.form.items():
        if key.startswith("manual_product_"):
            try:
                product_id = key.split("_")[-1]  # extrait l'ID du produit
                qty = int(value)
            except ValueError:
                qty = 0
            if qty > 0:
                cursor.execute(
                    "INSERT INTO dossier_produits (id_dossier, id_produit, qte_utilisee) VALUES (%s, %s, %s)",
                    (id_dossier, product_id, qty)
                )
    connection.commit()

    flash("Dossier et actes ajoutés avec succès.", 'success')
    return redirect(url_for('dossier_patient'))



@app.route('/autocomplete', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def autocomplete():
    query = request.args.get('query', '')
    type = request.args.get('type', '')

    if not query or type not in ['patient', 'acte']:
        return jsonify([])

    connection = get_db_connection()
    cursor = connection.cursor()

    if type == 'patient':
        cursor.execute("""
            SELECT DISTINCT patient
            FROM dossier_patient
            WHERE patient LIKE %s
            LIMIT 10
        """, (f"%{query}%",))
    elif type == 'acte':
        cursor.execute("""
            SELECT DISTINCT custom_acte
            FROM dossier_patient
            WHERE custom_acte LIKE %s
            LIMIT 10
        """, (f"%{query}%",))
    else:
        return jsonify([])

    results = cursor.fetchall()
    suggestions = [{type: row[type]} for row in results]

    return jsonify(suggestions)
