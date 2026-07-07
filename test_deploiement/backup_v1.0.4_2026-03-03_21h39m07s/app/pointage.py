from datetime import date

from flask import g, url_for
from flask import request, redirect, flash, render_template
from flask import jsonify
from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import redirect_with_message, nettoyer_texte, login_required, permission_required, has_permission


@app.route('/pointage', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_POINTAGES')
def pointage():
    # Récupération des filtres depuis le formulaire (ou valeurs par défaut)
    service_filter   = request.form.get('service', '')
    employee_filter  = request.form.get('employee', 'all')
    shift_filter     = request.form.get('shift', 'all')
    selected_date_start = request.form.get('shift_date_start', '')
    selected_date_end   = request.form.get('shift_date_end', '')
    today_date = date.today().strftime('%Y-%m-%d')
    user_id = g.user['id_personnel']

    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        #############################
        # Configuration des dates   #
        #############################
        cursor.execute("""
                        SELECT start_date, end_date 
                        FROM config_date
                        WHERE user_id = %s AND page = 'pointage'
                        """, (user_id,))
        config = cursor.fetchone()

        if not config:
            # Insertion initiale si aucune configuration n'existe
            cursor.execute("""
                            INSERT INTO config_date (user_id, page)
                            VALUES (%s, 'pointage')
                            """, (user_id,))
            connection.commit()
            cursor.execute("""
                            SELECT start_date, end_date 
                            FROM config_date
                            WHERE user_id = %s AND page = 'pointage'
            """, (user_id,))
            config = cursor.fetchone()

        current_start_date = config['start_date'] or "2025-01-01"
        current_end_date   = config['end_date'] or "2025-01-01"

        # Mise à jour des dates si le formulaire en fournit de nouvelles
        if selected_date_start and selected_date_start != str(current_start_date):
            cursor.execute("""
                            UPDATE config_date
                            SET start_date = %s
                            WHERE user_id = %s AND page = 'pointage'
            """, (selected_date_start, user_id))
        if selected_date_end and selected_date_end != str(current_end_date):
            cursor.execute("""
                            UPDATE config_date
                            SET end_date = %s
                            WHERE user_id = %s AND page = 'pointage'
            """, (selected_date_end, user_id))
        connection.commit()

        # Si aucune date n'est sélectionnée, on utilise la configuration existante
        selected_date_start = selected_date_start or str(current_start_date)
        selected_date_end   = selected_date_end or str(current_end_date)

        #############################
        # Récupération des données  #
        #############################

        # 1. Récupérer les actes
        cursor.execute("""
        SELECT ha.id_acte, ha.name_acte, ha.prix_acte, ha.id_service
        FROM honoraires_acte ha
        JOIN services s ON ha.id_service = s.id_service
        """)
        actes = cursor.fetchall()

        # 2. Récupérer l'ensemble des services
        cursor.execute("SELECT id_service, service_name, color FROM services")
        all_services = cursor.fetchall()
        services = [
            {
                "id_service": service["id_service"],
                "service_name": service["service_name"],
                "color": service["color"]
            }
            for service in all_services
            if has_permission(nettoyer_texte(service["service_name"]))
        ]

        # 3. Récupérer les employés par service
        employes = []
        for service in services:
            try:
                cursor.execute("""
                                SELECT id_personnel, CONCAT(nom, ' ', prenom) AS full_name, telephone, id_service
                                FROM personnel 
                                WHERE statut_activite = 1 AND use_in_planning = 1 AND id_service = %s
                                """, (service["id_service"],))
                employes.extend(cursor.fetchall())
            except Exception as e:
                print(f"Erreur lors de la récupération des employés pour le service {service['id_service']}: {e}")

        ##################################
        # Récupération du planning       #
        ##################################
        planning_query = """
                    SELECT p.id, p.id_service, p.shift_date, s.service_name, s.color, p.employee_id, 
                    p.shift_type, e.nom, e.prenom, p.id_created_par, p.created_at
                    FROM planning p 
                    LEFT JOIN personnel e ON p.employee_id = e.id_personnel 
                    LEFT JOIN services s ON p.id_service = s.id_service 
                    WHERE id_pointage = 0 AND p.shift_date BETWEEN %s AND %s 
                    """
        planning_conditions = [selected_date_start, selected_date_end]

        # Filtre sur le service
        if service_filter :
            cursor.execute("SELECT id_service FROM services WHERE service_name = %s", (service_filter,))
            service_row = cursor.fetchone()
            if service_row:
                planning_query += " AND p.id_service = %s"
                planning_conditions.append(service_row['id_service'])
            else:
                planning_query += " AND 1=0"

        # Filtre sur l'employé
        if employee_filter != 'all':
            planning_query += " AND CONCAT(e.nom, ' ', e.prenom) = %s"
            planning_conditions.append(employee_filter)

        # Filtre sur le shift
        if shift_filter != 'all':
            planning_query += " AND p.shift_type = %s"
            planning_conditions.append(shift_filter)

        planning_query += " ORDER BY p.shift_date, p.id_service, e.nom"
        cursor.execute(planning_query, tuple(planning_conditions))
        planning = cursor.fetchall()

        ##################################
        # Récupération des pointages     #
        ##################################
        pointages_query = """
            SELECT p.*, CONCAT(e.nom, ' ', e.prenom) AS full_name, p.id_service, s.service_name, s.color,
                   CONCAT(criator.nom, ' ', criator.prenom) AS created_par
                FROM pointages p 
                LEFT JOIN personnel e ON p.id_employe = e.id_personnel 
                LEFT JOIN personnel criator ON p.id_created_par = criator.id_personnel 
                LEFT JOIN services s ON p.id_service = s.id_service 
                WHERE p.date_pointage BETWEEN %s AND %s 
                """
        pointages_conditions = [selected_date_start, selected_date_end]

        # Filtre sur le service
        if service_filter == 'all':
            if services:
                service_conditions = []
                for service in services:
                    service_conditions.append("s.service_name = %s")
                    pointages_conditions.append(service["service_name"])
                pointages_query += " AND (" + " OR ".join(service_conditions) + ")"
            else:
                pointages_query += " AND 1=0"
        else:
            pointages_query += " AND s.service_name = %s"
            pointages_conditions.append(service_filter)

        # Filtre sur l'employé
        if employee_filter != 'all':
            pointages_query += " AND CONCAT(e.nom, ' ', e.prenom) = %s"
            pointages_conditions.append(employee_filter)

        # Filtre sur le shift
        if shift_filter != 'all':
            pointages_query += " AND p.shift_type = %s"
            pointages_conditions.append(shift_filter)

        pointages_query += " ORDER BY p.date_pointage"
        cursor.execute(pointages_query, tuple(pointages_conditions))
        pointages = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        'pointages.html',
        today_date=today_date,
        employes=employes,
        services=services,
        actes=actes,
        pointages=pointages,
        planning=planning,
        selected_date_start=selected_date_start,
        selected_date_end=selected_date_end,
        service_filter=service_filter,
        employee_filter=employee_filter,
        shift_filter=shift_filter,
        title="Pointage",
        user=g.user
    )


@app.route('/validate-presence', methods=['POST'])
@login_required
@handle_errors()
@permission_required('VALIDER_POINTAGES')
def validate_presence():
    data = request.form
    user = g.user
    user_id = user['id_personnel']

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        # Calculer le prix en fonction du service et du type de shift
        # Remplacez 'prix_joure' par 'prix_jour' si c'était une faute de frappe.
        prix_query = """
                    SELECT 
                    CASE 
                    WHEN %s = 'day' THEN s.prix_joure
                    WHEN %s = 'night' THEN s.prix_nuit
                    WHEN %s = '24H' THEN s.prix_24h
                    ELSE NULL
                    END AS prix
                    FROM services s
                    WHERE s.id_service = %s
                    """
        cursor.execute(prix_query, (
            data['shift_type'],
            data['shift_type'],
            data['shift_type'],
            data['service']
        ))
        result = cursor.fetchone()
        prix = result['prix'] if result and result['prix'] is not None else 0.0

        # Insertion du pointage validé avec le prix calculé
        insert_query = """
            INSERT INTO pointages (id_employe, date_pointage, id_service, shift_type, prix, id_created_par)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            data['employee_id'],
            data['shift_date'],
            data['service'],
            data['shift_type'],
            prix,
            user_id
        ))

        # Récupération de l'id du pointage inséré
        id_pointage = cursor.lastrowid

        # Mise à jour du planning pour indiquer que la présence est validée
        update_query = "UPDATE planning SET id_pointage = %s WHERE id = %s"
        cursor.execute(update_query, (id_pointage, data['id']))

        connection.commit()

        flash("Présence validée avec succès.", "success")
        return jsonify({"success": True, "message": "Présence validée avec succès."})

    except Exception as e:
        flash(f"Erreur : {str(e)}", "danger")
        return jsonify({"success": False, "message": str(e)}), 500




@app.route('/add-pointage', methods=['POST'])
@login_required
@handle_errors()
@permission_required('AJOUTER_POINTAGES')
def add_pointage():
    data = request.form
    service = data['service']
    employee_name = data['id_employe']  # Cela contient le nom au lieu de l'ID

    user = g.user
    user_id = user['id_personnel']
    connection = get_db_connection()
    try:
        cursor= connection.cursor()
        # Rechercher l'ID de l'employé à partir de son nom
        cursor.execute("""
            SELECT id_personnel FROM personnel
            WHERE CONCAT(nom, ' ', prenom) = %s
        """, (employee_name,))

        # Récupérer le résultat
        result_personnel = cursor.fetchone()

        if not result_personnel:
            return redirect_with_message('pointage', "Employé introuvable.", 'danger')

        # Récupérer l'ID de l'employé
        id_employe = result_personnel['id_personnel']

        # Rechercher l'ID de service à partir de son nom
        cursor.execute("""
            SELECT id_service FROM services
            WHERE service_name = %s
        """, (service,))

        # Récupérer le résultat
        result_service = cursor.fetchone()

        if not result_service:
            return redirect_with_message('pointage', "Service introuvable.", 'danger')

        # Récupérer l'ID de l'employé
        id_service = result_service['id_service']

        # Récupérer le prix en fonction du shift_type et du service
        prix_query = """
                    SELECT 
                    CASE 
                    WHEN %s = 'day' THEN s.prix_joure
                    WHEN %s = 'night' THEN s.prix_nuit
                    WHEN %s = '24H' THEN s.prix_24h
                    ELSE NULL
                    END AS prix
                    FROM services s
                    WHERE s.service_name = %s
                    """
        cursor.execute(prix_query, (
            data['shift_type'],
            data['shift_type'],
            data['shift_type'],
            data['service']
        ))
        result = cursor.fetchone()
        prix = result['prix'] if result else 0.0  # Défaut à 0.0 si aucun prix trouvé

        # Insertion des données du pointage avec le prix calculé
        insert_query = """
            INSERT INTO pointages (id_employe, date_pointage, shift_type, id_service, prix,id_created_par)
            VALUES (%s, %s, %s, %s, %s, %s,%s)
        """
        cursor.execute(insert_query, (
            id_employe,
            data['date_pointage'],
            data['shift_type'],
            id_service,
            prix,
            user_id
        ))

        connection.commit()

    finally:
        connection.close()

    return redirect_with_message('pointage', "Le pointage a été enregistré avec succès.", 'success')

@app.route('/edit-pointage/<int:pointage_id>', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('MODIFIER_POINTAGES')
def edit_pointage(pointage_id):
    connection = get_db_connection()
    if request.method == 'POST':
        # Récupérer les données du formulaire
        data = request.form
        try:
            cursor = connection.cursor()

            # Recalculer le prix en fonction des nouvelles données
            prix_query = """
                        SELECT 
                        CASE 
                        WHEN %s = 'day' THEN s.prix_joure
                        WHEN %s = 'night' THEN s.prix_nuit
                        WHEN %s = '24H' THEN s.prix_24h
                        ELSE NULL
                        END AS prix
                        FROM services s
                        WHERE id_service = %s
                        """
            cursor.execute(prix_query, (
                data['shift_type'],
                data['shift_type'],
                data['shift_type'],
                data['id_service']
            ))
            result = cursor.fetchone()
            prix = result['prix'] if result else 0.0  # Défaut à 0.0 si aucun prix trouvé

            # Mettre à jour les données du pointage, y compris le prix recalculé
            query = """
                UPDATE pointages
                SET id_employe = %s, date_pointage = %s, shift_type = %s, id_service = %s, prix = %s
                WHERE id_pointage = %s
            """
            cursor.execute(query, (
                data['id_employe'],
                data['date_pointage'],
                data['shift_type'],
                data['id_service'],
                prix,
                pointage_id
            ))
            connection.commit()
        finally:
            connection.close()
        return redirect_with_message('pointage', "Le pointage a été modifié avec succès.", 'success')
    else:
        # Charger les données du pointage à modifier
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM pointages WHERE id_pointage = %s", (pointage_id,))
            pointage = cursor.fetchone()

            # Charger également les services et employés pour afficher les options dans le formulaire
            cursor.execute("SELECT id_service, service_name FROM services")
            services = cursor.fetchall()

            cursor.execute("SELECT id_personnel, CONCAT(nom, ' ', prenom) AS nom_complet FROM personnel")
            employees = cursor.fetchall()
        finally:
            connection.close()

        return render_template('edit_pointage.html', pointage=pointage, services=services, employees=employees)

@app.route('/delete-pointage/<int:pointage_id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('SUPPRIMER_POINTAGES')
def delete_pointage(pointage_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        # Supprimer le pointage dans la table pointages

        # 1. Mettre à jour le planning avant la suppression
        update_query = """
            UPDATE planning 
            SET id_pointage = NULL 
            WHERE id_pointage = %s
        """
        cursor.execute(update_query, (pointage_id,))

        # 2. Suppression du pointage
        delete_query = """
            DELETE FROM pointages 
            WHERE id_pointage = %s
        """
        cursor.execute(delete_query, (pointage_id,))

        connection.commit()

        flash("Pointage supprimé avec succès.", "success")

    except Exception as e:
        connection.rollback()
        flash("Erreur lors de la suppression du pointage", "danger")
        return redirect(url_for('pointage'))

    return redirect(url_for('pointage'))
@app.route('/add_actes/<int:pointage_id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('AJOUTER_ACTES_POINTAGES')
def add_actes(pointage_id):
    id_actes = request.form.getlist('id_acte[]')
    nbr_actes = request.form.getlist('nbr_actes[]')

    # Validation initiale
    if not id_actes or not nbr_actes:
        return redirect_with_message('pointage', "Tous les champs doivent être remplis.", 'danger')

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        prix_total = 0  # Variable pour le total des actes

        for id_acte, nbr in zip(id_actes, nbr_actes):
            # Validation des entrées pour chaque acte
            if not id_acte or not nbr:
                continue  # Ignorer les entrées incomplètes

            try:
                nbr = int(nbr)  # Convertir en entier
                if nbr <= 0:
                    flash('Le nombre d\'actes doit être supérieur à 0.', 'danger')
                    continue
            except ValueError:
                flash('Le nombre d\'actes doit être un entier valide.', 'danger')
                continue

            # Insérer l'acte dans la table `pointages_actes`
            query_insert_acte = """
                INSERT INTO pointages_actes (id_acte, id_pointage, nbr_actes) 
                VALUES (%s, %s, %s)
            """
            cursor.execute(query_insert_acte, (id_acte, pointage_id, nbr))

            # Récupérer le prix de l'acte
            query_get_prix = "SELECT prix_acte FROM honoraires_acte WHERE id_acte = %s"
            cursor.execute(query_get_prix, (id_acte,))
            result = cursor.fetchone()

            if result:
                prix_acte = result['prix_acte']
                prix_total += prix_acte * nbr

        # Mettre à jour le total des prix dans la table `pointages`
        query_update_pointage = """
            UPDATE pointages
            SET prix_acte = %s
            WHERE id_pointage = %s
        """
        cursor.execute(query_update_pointage, (prix_total, pointage_id))

        # Valider les modifications
        connection.commit()

        flash('Les actes ont été ajoutés et le total mis à jour avec succès.', 'success')
    except Exception as e:
        flash(f"Erreur : {str(e)}", 'danger')
    finally:
        connection.close()

    return redirect(url_for('pointage'))