from datetime import datetime, timedelta
from io import BytesIO

from flask import render_template, g, request, redirect, url_for, Response, jsonify
from xhtml2pdf import pisa

from app import app, get_db_connection
from app.auth import chargement
from app.error import handle_errors
from app.utils.utiles import redirect_with_message, nettoyer_texte, login_required, has_permission



@app.route('/planning', methods=['GET'])
@login_required
@handle_errors()

def planning():
    # Récupération des paramètres de la requête
    selected_service = request.args.get('service', '')
    selected_employee = request.args.get('employee', 'all')
    selected_shift = request.args.get('shift', 'all')
    selected_start_date = request.args.get('start_date', '')
    selected_end_date = request.args.get('end_date', '')

    user = g.user
    user_id = user['id_personnel']

    # Valeurs par défaut pour les dates si aucune configuration n'existe
    DEFAULT_START = "2025-01-01"
    DEFAULT_END = "2025-01-01"

    # Utilisation d'un context manager pour la connexion à la base de données
    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        # --- 1. Gestion de la configuration des dates ---

        # Récupération de la configuration de dates pour la page "planning"
        cursor.execute("""
            SELECT start_date, end_date 
            FROM config_date
            WHERE user_id = %s AND page = 'planning'
        """, (user_id,))
        config = cursor.fetchone()

        # Insertion initiale si aucune configuration n'existe
        if not config:
            cursor.execute("""
                INSERT INTO config_date (user_id, page)
                VALUES (%s, 'planning')
            """, (user_id,))
            connection.commit()
            cursor.execute("""
                SELECT start_date, end_date 
                FROM config_date
                WHERE user_id = %s AND page = 'planning'
            """, (user_id,))
            config = cursor.fetchone()

        # Définition des dates actuelles en tenant compte des valeurs par défaut
        current_start_date = config['start_date'] or DEFAULT_START
        current_end_date = config['end_date'] or DEFAULT_END

        # Mise à jour des dates si elles diffèrent
        if selected_start_date and selected_start_date != str(current_start_date):
            cursor.execute("""
                UPDATE config_date
                SET start_date = %s
                WHERE user_id = %s AND page = 'planning'
            """, (selected_start_date, user_id))
        if selected_end_date and selected_end_date != str(current_end_date):
            cursor.execute("""
                UPDATE config_date
                SET end_date = %s
                WHERE user_id = %s AND page = 'planning'
            """, (selected_end_date, user_id))
        connection.commit()

        # Utilisation des dates filtrées ou des dates par défaut
        selected_start_date = selected_start_date or str(current_start_date)
        selected_end_date = selected_end_date or str(current_end_date)

        # --- 2. Récupération et filtrage des services ---

        cursor.execute("SELECT id_service, service_name, color FROM services")
        services_all = cursor.fetchall()

        # Conserver uniquement les services pour lesquels l'utilisateur a la permission
        services = [
            s for s in services_all
            if has_permission(nettoyer_texte(s["service_name"]))
        ]

        # Récupération de l'id du service sélectionné, s'il a été choisi (différent de "all")
        selected_service_id = None
        if selected_service and selected_service != 'all':
            cursor.execute("""
                SELECT id_service FROM services WHERE service_name = %s
            """, (selected_service,))
            res = cursor.fetchone()
            if res:
                selected_service_id = res['id_service']

        # --- 3. Récupération des employés associés au service concerné ---
        # Si un service spécifique est sélectionné, ne récupérer que les employés de ce service,
        # sinon, récupérer les employés de tous les services filtrés.
        if selected_service and selected_service != 'all' and selected_service_id:
            cursor.execute("""
                SELECT id_personnel, CONCAT(nom, ' ', prenom) AS full_name, telephone, id_service
                FROM personnel
                WHERE statut_activite = 1 AND use_in_planning = 1 AND id_service = %s
                ORDER BY CAST(prenom AS CHAR) DESC
            """, (selected_service_id,))
            employees = cursor.fetchall()
        else:
            service_ids = [s["id_service"] for s in services]
            employees = []
            if service_ids:
                format_strings = ','.join(['%s'] * len(service_ids))
                cursor.execute(f"""
                    SELECT id_personnel, CONCAT(nom, ' ', prenom) AS full_name, telephone, id_service
                    FROM personnel
                    WHERE statut_activite = 1 AND use_in_planning = 1 AND id_service IN ({format_strings})
                    ORDER BY CAST(prenom AS CHAR) DESC
                """, service_ids)
                employees = cursor.fetchall()

        # --- 4. Construction et exécution de la requête des plannings ---

        base_query = """
            SELECT pl.id, pl.employee_id, pl.id_service, pl.shift_date, pl.shift_type, 
                   CONCAT(p.nom, ' ', p.prenom) AS full_name, s.service_name
            FROM planning pl
            INNER JOIN personnel p ON pl.employee_id = p.id_personnel
            INNER JOIN services s ON pl.id_service = s.id_service
            WHERE pl.shift_date BETWEEN %s AND %s
        """
        query_params = [selected_start_date, selected_end_date]

        # Filtrage par service
        if selected_service != 'all':
            if selected_service_id:
                base_query += " AND pl.id_service = %s"
                query_params.append(selected_service_id)
        else:
            if services:
                service_ids = [s["id_service"] for s in services]
                placeholders = ','.join(['%s'] * len(service_ids))
                base_query += f" AND pl.id_service IN ({placeholders})"
                query_params.extend(service_ids)

        # Filtrage par employé
        if selected_employee != 'all':
            base_query += " AND CONCAT(p.nom, ' ', p.prenom) = %s"
            query_params.append(selected_employee)

        # Filtrage par type de shift
        if selected_shift != 'all':
            base_query += " AND pl.shift_type = %s"
            query_params.append(selected_shift)

        cursor.execute(base_query, query_params)
        plannings = cursor.fetchall()


    finally:
        connection.close()

    # --- 5. Préparation des événements pour FullCalendar ---

    # Dictionnaire associant le nom de service à sa couleur
    service_colors = {s['service_name']: s['color'] for s in services}

    events = []
    for planning in plannings:
        # Conversion de la date si nécessaire
        shift_date = planning['shift_date']
        if isinstance(shift_date, str):
            shift_date = datetime.strptime(shift_date, "%Y-%m-%d").date()

        # Détermination des horaires en fonction du type de poste
        if planning['shift_type'] == 'day':
            start_time = f"{shift_date}T08:00:00"
            end_time = f"{shift_date}T18:00:00"
        elif planning['shift_type'] == 'night':
            start_time = f"{shift_date}T18:00:00"
            end_time = f"{(shift_date + timedelta(days=1)).strftime('%Y-%m-%d')}T08:00:00"
        elif planning['shift_type'] == '24H':
            start_time = f"{shift_date}T08:00:00"
            end_time = f"{(shift_date + timedelta(days=1)).strftime('%Y-%m-%d')}T08:00:00"
        else:
            start_time = end_time = None

        events.append({
            "id": planning['id'],
            "title": f"{planning['full_name']} - {planning['shift_type']} - {planning['service_name']}",
            "start": start_time,
            "end": end_time,
            "backgroundColor": service_colors.get(planning['service_name'], 'gray'),
            "borderColor": service_colors.get(planning['service_name'], 'gray'),
        })
    chargement()
    # --- 6. Rendu du template ---
    return render_template(
            'personnel/planning.html',
        employees=employees,
        services=services,
        events=events,
        selected_service=selected_service,
        selected_shift=selected_shift,
        selected_employee=selected_employee,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        title="Plannings",
        user=g.user
    )



@app.route('/save-planning', methods=['GET', 'POST'])
@login_required
@handle_errors()

def save_planning():

    # Récupération des filtres existants
    selected_service = request.args.get('service', 'all')
    selected_employee = request.args.get('employee', 'all')
    selected_shift = request.args.get('shift', 'all')
    selected_start_date = request.args.get('start_date', '')
    selected_end_date = request.args.get('end_date', '')

    # Récupération des données du formulaire
    service = request.form.get('service')
    employee_full_name = request.form.get('employee')
    shift_type = request.form.get('shift')
    shift_date = request.form.get('date')
    event_id = request.form.get('event_id')  # ID pour modification (si fourni)

    if not all([service, employee_full_name, shift_type, shift_date]):
        # Redirection si des champs sont manquants
        return redirect(url_for('planning',
                                service=selected_service,
                                shift=selected_shift,
                                employee=selected_employee,
                                start_date=selected_start_date,
                                end_date=selected_end_date))

    # Validation de la date
    try:
        datetime.strptime(shift_date, '%Y-%m-%d')
    except ValueError:
        # Redirection en cas d'erreur de validation
        return redirect(url_for('planning',
                                service=selected_service,
                                shift=selected_shift,
                                employee=selected_employee,
                                start_date=selected_start_date,
                                end_date=selected_end_date))

    # Connexion et gestion de la base de données
    connection = get_db_connection()
    try:
        cursor = connection.cursor()            # Récupération des services
        cursor.execute("""
            SELECT id_service FROM services WHERE service_name = %s
        """, (selected_service,))
        selected_service_id = cursor.fetchone()

        if not selected_service_id:
            return redirect(url_for('planning',
                                    service=selected_service,
                                    shift=selected_shift,
                                    employee=selected_employee,
                                    start_date=selected_start_date,
                                    end_date=selected_end_date))

        # Récupération de l'ID de l'employé
        cursor.execute("""
            SELECT id_personnel FROM personnel
            WHERE CONCAT(nom, ' ', prenom) = %s
        """, (employee_full_name,))
        result = cursor.fetchone()

        if not result:
            return redirect(url_for('planning',
                                    service=selected_service,
                                    shift=selected_shift,
                                    employee=selected_employee,
                                    start_date=selected_start_date,
                                    end_date=selected_end_date))

        employee_id = result['id_personnel']
        id_service = selected_service_id['id_service']

        if event_id:
            # Modification de l'événement existant
            cursor.execute("""
                UPDATE planning
                SET id_service = %s, shift_date = %s, shift_type = %s
                WHERE id = %s
            """, (id_service, shift_date, shift_type, event_id))
        else:
            # Ajout d'un nouvel événement
            cursor.execute("""
                INSERT INTO planning (id_service, shift_date, employee_id, shift_type)
                VALUES (%s, %s, %s, %s)
            """, (id_service, shift_date, employee_id, shift_type))

            connection.commit()
    except Exception:
        connection.rollback()
        return redirect(url_for('planning',
                                service=selected_service,
                                shift=selected_shift,
                                employee=selected_employee,
                                start_date=selected_start_date,
                                end_date=selected_end_date))

    finally:
        connection.close()
    chargement()
    # Redirection avec les filtres conservés
    return redirect(url_for('planning',
                            service=selected_service,
                            shift=selected_shift,
                            employee=selected_employee,
                            start_date=selected_start_date,
                            end_date=selected_end_date))


@app.route('/update-event', methods=['POST'])
@login_required
@handle_errors()

def update_event():
    # Récupération des données POST pour la mise à jour
    event_id = request.form.get('event_id')
    new_date = request.form.get('start')

    # Récupération des filtres existants via GET
    selected_service = request.form.get('service', 'all')
    selected_employee = request.form.get('employee', 'all')
    selected_shift = request.form.get('shift', 'all')
    selected_start_date = request.form.get('start_date', '')
    selected_end_date = request.form.get('end_date', '')

    # Validation des données obligatoires
    if not event_id or not new_date:
        return redirect(url_for('planning',
                                service=selected_service,
                                employee=selected_employee,
                                shift=selected_shift,
                                start_date=selected_start_date,
                                end_date=selected_end_date,
                                message="Données invalides.",
                                category='danger'))

    # Connexion à la base de données pour mettre à jour l'événement
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
                "UPDATE planning SET shift_date = %s WHERE id = %s",
                (new_date, event_id)
            )
        connection.commit()
        chargement()
        return redirect(url_for('planning',
                                service=selected_service,
                                employee=selected_employee,
                                shift=selected_shift,
                                start_date=selected_start_date,
                                end_date=selected_end_date,
                                message="Le planning a été modifié avec succès.",
                                category='success'))
    except Exception as e:
        connection.rollback()
        return redirect(url_for('planning',
                                service=selected_service,
                                employee=selected_employee,
                                shift=selected_shift,
                                start_date=selected_start_date,
                                end_date=selected_end_date,
                                message=f"Erreur lors de la mise à jour : {str(e)}",
                                category='danger'))
    finally:
        connection.close()


@app.route('/delete-event/<int:event_id>', methods=['DELETE'])
@login_required
@handle_errors()

def delete_event(event_id):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM planning WHERE id = %s", (event_id,))
        connection.commit()
        chargement()

        # Retourner un message de succès après suppression
        return jsonify({"success": True, "message": "Événement supprimé avec succès"}), 200

    except Exception as e:
        connection.rollback()
        return jsonify({"success": False, "message": f"Erreur : {str(e)}"}), 500
    finally:
        connection.close()


@app.route('/planning/print', methods=['GET'])
@login_required
@handle_errors()

def print_planning():
    # Récupérer les paramètres pour filtrer les événements
    selected_service = request.args.get('service', 'all')
    selected_shift = request.args.get('shift', 'all')
    selected_employee = request.args.get('employee', 'all')
    selected_start_date = request.args.get('start_date', '')
    selected_end_date = request.args.get('end_date', '')

    # Récupérer l'ID de l'employé si un nom complet est donné
    employee_id = None
    if selected_employee != 'all':  # Si un employé est sélectionné
        employee_full_name = selected_employee
        # Récupérer l'ID de l'employé dans la base de données
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
                SELECT id_personnel FROM personnel
                WHERE CONCAT(nom, ' ', prenom) = %s
            """, (employee_full_name,))
        result = cursor.fetchone()

        if result is None:
            # Si l'employé n'est pas trouvé, retourner une erreur
            return redirect_with_message('planning', "Employé introuvable.", 'danger')

        employee_id = result['id_personnel']
        connection.close()

    id_service = 0

    # Connexion à la base de données
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
            SELECT id_service FROM services WHERE service_name = %s
        """, (selected_service,))
    selected_service_id = cursor.fetchone()
    if selected_service_id:
        id_service = selected_service_id["id_service"]

    # Construire la requête SQL dynamiquement
    query = """
        SELECT pl.id, pl.id_service, pl.shift_date, pl.shift_type, CONCAT(p.nom, ' ', p.prenom) AS full_name, p.telephone
        FROM planning pl
        INNER JOIN personnel p ON pl.employee_id = p.id_personnel
        WHERE ( pl.id_service = %s)
        AND (%s = 'all' OR pl.shift_type = %s)
        AND (%s IS NULL OR pl.employee_id = %s)
          AND (%s = '' OR pl.shift_date >= %s)
          AND (%s = '' OR pl.shift_date <= %s)
          ORDER BY pl.shift_date
    """
    params = (id_service, selected_shift, selected_shift,
              employee_id, employee_id, selected_start_date, selected_start_date,
              selected_end_date, selected_end_date)

    cursor.execute(query, params)
    plannings = cursor.fetchall()

    connection.close()

    # Rendu du template HTML pour générer le PDF
    rendered_html = render_template(
        'pdf/planning_pdf.html',
        selected_service=selected_service,
        selected_shift=selected_shift,
        selected_employee=selected_employee,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        plannings=plannings
    )

    # Générer le PDF avec xhtml2pdf
    pdf_stream = BytesIO()
    pisa.CreatePDF(rendered_html, dest=pdf_stream)
    pdf_stream.seek(0)

    # Retourner le PDF comme réponse
    return Response(
        pdf_stream,
        mimetype='application/pdf',
        headers={"Content-Disposition": "attachment; filename=planning.pdf"}
    )
