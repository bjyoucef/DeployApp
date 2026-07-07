from flask import request, render_template, g

from app import app, get_db_connection
from app.utiles import login_required, permission_required, redirect_with_message
from app.error import handle_errors


@app.route('/manage_employees', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AU_PERSONNEL')
def manage_employees():
    user = g.user
    connection = get_db_connection()
    cursor = connection.cursor()
    if request.method == 'POST':
        if 'add_employee' in request.form:
            return handle_employee_addition(cursor)
        elif 'edit_employee' in request.form:
            return handle_employee_edit(cursor)
        elif 'change_status' in request.form:
            return handle_employee_status_change(cursor)

    # Récupérer la liste des employés
    cursor.execute("""
                    SELECT p.*, s.service_name
                    FROM personnel p
                    LEFT JOIN services s ON p.id_service = s.id_service
                    ORDER BY statut_activite ASC
                """)
    employes = cursor.fetchall()

    # Récupérer la liste des services
    cursor.execute("SELECT * FROM services")
    services = cursor.fetchall()
    connection.close()
    return render_template('manage_employees.html', title='personnel',services=services, employes=employes, user=user)

def handle_employee_addition(cursor):
    """Handle the addition of a new employee."""
    # Récupération des données avec gestion des erreurs potentielles
    try:
        nom = (request.form['nom']).upper()
        prenom = (request.form['prenom']).upper()
        role = (request.form['role']).upper()
        service = (request.form['service']).upper()
        telephone = request.form.get('telephone', None)  # Optionnel
        use_in_planning = 1 if request.form.get('use_in_planning') == 'on' else 0
        username = request.form['usernameI'].strip()
        password = request.form['passwordI'].strip()
        confirm_password = request.form['confirm_passwordI'].strip()
        user = g.user
        id_personne_add = user['id_personnel']

        if not all([nom, prenom,role,service, telephone, username, password, confirm_password]):
            return redirect_with_message('manage_employees',"Tous les champs doivent être remplis.", 'danger')

        if password != confirm_password:
            return redirect_with_message('manage_employees',"Les mots de passe ne correspondent pas.", 'danger')

    except KeyError as e:
        return redirect_with_message(
            'manage_employees',
            f"Le champ {str(e)} est manquant.",
            "danger"
        )

    # Insertion dans la base de données
    try:
        cursor.execute('SELECT id_personnel FROM personnel WHERE username = %s', (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            return redirect_with_message('manage_employees',
                                         "Cet nom d'utilisateur est déjà utilisé. Veuillez en choisir un autre.",
                                         'danger')


        # Récupérer l'ID du service
        cursor.execute("SELECT id_service FROM services WHERE service_name = %s", (service,))
        result = cursor.fetchone()
        if result is None:
            return redirect_with_message(
                'manage_employees',
                "Service introuvable.",
                "danger"
            )
        id_service = result['id_service']

        full_name = f"{nom} {prenom}"

        # Insertion de téléphone et récupération de l'ID généré
        cursor.execute("""
            INSERT INTO contacts 
            (nom, Poste, numero, id_personne_add)
            VALUES (%s, %s, %s, %s)
        """, (full_name, role, telephone, id_personne_add))

        # Récupération de l'ID généré
        id_contact = cursor.lastrowid
        cursor.connection.commit()  # Commit transaction

        # Insertion de l'employé
        cursor.execute("""
            INSERT INTO personnel 
            (nom, prenom, role, id_service, id_phone,username, password, use_in_planning, created_at, updated_at, statut_activite)
            VALUES (%s, %s, %s, %s, %s,%s, %s, %s, NOW(), NOW(),1)
        """, (nom, prenom, role, id_service, id_contact,username, password, use_in_planning))
        cursor.connection.commit()  # Commit transaction
        return redirect_with_message(
            'manage_employees',
            "L'employé a été ajouté avec succès.",
            "success"
        )
    except Exception as e:
        return redirect_with_message(
            'manage_employees',
            f"Erreur lors de l'ajout de l'employé : {str(e)}",
            "danger"
        )


def handle_employee_edit(cursor):
    """Handle the editing of an existing employee."""
    try:
        # Récupération des données du formulaire
        id_personnel = request.form['id_personnel']
        nom = (request.form.get('nom', None)).upper()
        prenom = (request.form.get('prenom', None)).upper()
        role = (request.form.get('role', None)).upper()
        service = (request.form.get('service', None)).upper()
        use_in_planning = 1 if request.form.get('use_in_planning') == 'on' else 0
        username = request.form.get('usernameM', None)
        password = request.form.get('passwordM', None)
        confirm_password = request.form.get('confirm_passwordM', None)

        # Récupérer l'ID du service correspondant (si service est fourni)
        if service:
            cursor.execute("SELECT id_service FROM services WHERE service_name = %s", (service,))
            result = cursor.fetchone()
            if result is None:
                return redirect_with_message(
                    'manage_employees',
                    "Service introuvable.",
                    "danger"
                )
            id_service = result['id_service']
        else:
            id_service = None  # Si aucun service n'est fourni, garder l'ancien service

        # Préparer la mise à jour dynamique
        update_fields = []
        update_values = []

        # Ajouter les champs qui ont été modifiés
        if nom:
            update_fields.append("nom = %s")
            update_values.append(nom)
        if prenom:
            update_fields.append("prenom = %s")
            update_values.append(prenom)
        if role:
            update_fields.append("role = %s")
            update_values.append(role)
        if id_service:
            update_fields.append("id_service = %s")
            update_values.append(id_service)
        if use_in_planning is not None:
            update_fields.append("use_in_planning = %s")
            update_values.append(use_in_planning)
        if username:
            update_fields.append("username = %s")
            update_values.append(username)
        if password and password == confirm_password:  # Assurez-vous que le mot de passe et sa confirmation sont égaux
            update_fields.append("password = %s")
            update_values.append(password)

        # Vérification s'il y a des modifications à appliquer
        if not update_fields:
            return redirect_with_message(
                'manage_employees',
                "Aucune information n'a été modifiée.",
                "warning"
            )

        # Exécuter la mise à jour
        update_fields.append("updated_at = NOW()")  # Ajouter la mise à jour de l'horodatage
        update_values.append(id_personnel)

        # Effectuer l'UPDATE
        cursor.execute(f"""
        UPDATE personnel 
        SET {', '.join(update_fields)} 
        WHERE id_personnel = %s
        """, tuple(update_values))

        # Validation de la transaction
        cursor.connection.commit()
        return redirect_with_message(
            'manage_employees',
            "Les informations de l'employé ont été mises à jour.",
            "success"
        )
    except Exception as e:
        return redirect_with_message(
            'manage_employees',
            f"Erreur lors de la modification de l'employé : {str(e)}",
            "danger"
        )


def handle_employee_status_change(cursor):
    try:
        id_personnel = request.form['id_personnel']
        nouveau_statut = request.form['change_status']

        # Récupération de l'ID du téléphone associé
        cursor.execute("""
            SELECT id_phone FROM personnel WHERE id_personnel = %s
        """, (id_personnel,))
        id_phone = cursor.fetchone()

        if id_phone:
            # Mise à jour du statut du téléphone
            cursor.execute("""
            UPDATE contacts
            SET status_phone = FALSE
            WHERE id = %s
                """, (id_phone['id_phone'],))

        # Mise à jour du statut de l'employé
        cursor.execute("""
        UPDATE personnel
        SET statut_activite = %s, updated_at = NOW()
        WHERE id_personnel = %s
    """, (nouveau_statut, id_personnel))

        # Validation des modifications
        cursor.connection.commit()

        return redirect_with_message('manage_employees', "Le statut de l'employé a été mis à jour.", "success")

    except Exception as e:
        cursor.connection.rollback()  # Annuler les modifications en cas d'erreur
        return redirect_with_message('manage_employees', f"Erreur lors de la mise à jour : {e}", "danger")
