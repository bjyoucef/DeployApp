from flask import request, render_template, g, jsonify
from werkzeug.security import generate_password_hash
from app import app, get_db_connection
from app.utils.utiles import login_required, redirect_with_message
from app.error import handle_errors


# ============================================================================
# CONSTANTES
# ============================================================================
class Messages:
    """Messages de l'application"""
    EMPLOYEE_ADDED = "L'employé a été ajouté avec succès."
    EMPLOYEE_UPDATED = "Les informations de l'employé ont été mises à jour."
    EMPLOYEE_STATUS_CHANGED = "Le statut de l'employé a été mis à jour."
    USER_UPDATED = "Les informations utilisateur ont été mises à jour."
    ROLE_ASSOCIATED = "Rôle associé avec succès."
    ROLE_DISSOCIATED = "Rôle dissocié avec succès."
    ROLE_ALREADY_ASSOCIATED = "Ce rôle est déjà associé à cet employé."

    EMPLOYEE_NOT_FOUND = "Employé introuvable."
    SERVICE_NOT_FOUND = "Service introuvable."
    MISSING_FIELDS = "Tous les champs doivent être remplis."
    PASSWORD_MISMATCH = "Les mots de passe ne correspondent pas."
    USERNAME_EXISTS = "Ce nom d'utilisateur est déjà utilisé."
    NO_MODIFICATIONS = "Aucune information n'a été modifiée."
    SELECT_ROLE = "Veuillez sélectionner un rôle."


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================
def validate_required_fields(fields_dict):
    """Valide que tous les champs requis sont présents et non vides"""
    missing = [key for key, value in fields_dict.items() if not value]
    if missing:
        raise ValueError(f"Champs manquants: {', '.join(missing)}")
    return True


def get_service_id(cursor, service_name):
    """Récupère l'ID d'un service par son nom"""
    cursor.execute("SELECT id_service FROM services WHERE service_name = %s", (service_name,))
    result = cursor.fetchone()
    if not result:
        raise ValueError(Messages.SERVICE_NOT_FOUND)
    return result['id_service']


def check_username_exists(cursor, username, exclude_id=None):
    """Vérifie si un nom d'utilisateur existe déjà"""
    if exclude_id:
        cursor.execute(
            'SELECT id_personnel FROM personnel WHERE username = %s AND id_personnel != %s',
            (username, exclude_id)
        )
    else:
        cursor.execute('SELECT id_personnel FROM personnel WHERE username = %s', (username,))
    return cursor.fetchone() is not None


def create_contact(connection, cursor, nom, prenom, role, telephone, id_personne_add):
    """Crée un contact et retourne son ID"""
    full_name = f"{nom} {prenom}"
    cursor.execute("""
        INSERT INTO contacts (nom, Poste, numero, id_personne_add)
        VALUES (%s, %s, %s, %s)
    """, (full_name, role, telephone, id_personne_add))
    connection.commit()
    return cursor.lastrowid


# ============================================================================
# ROUTES PRINCIPALES
# ============================================================================
@app.route('/manage_employees', methods=['GET', 'POST'])
@login_required
@handle_errors()

def manage_employees():
    """Page principale de gestion des employés"""
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        action = request.form.get('action')

        handlers = {
            'add_employee': handle_employee_addition,
            'edit_employee': handle_employee_edit,
            'edit_user': handle_user_credentials_edit,
            'change_status': handle_employee_status_change,
        }

        handler = handlers.get(action)
        if handler:
            result = handler(cursor)
            connection.close()
            return result

    # --- Gestion de la recherche et pagination ---
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search_query = request.args.get('search', '', type=str).strip()
    
    offset = (page - 1) * per_page

    # --- Gestion de la recherche et pagination ---
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search_query = request.args.get('search', '', type=str).strip()
    filter_status = request.args.get('filter_status', '', type=str).strip()
    filter_online = request.args.get('filter_online', '', type=str).strip()
    
    offset = (page - 1) * per_page

    # Clauses séparées pour éviter l'erreur de colonnes dupliquées (1060) dans le COUNT
    query_select = """
        SELECT p.*, s.service_name, c.numero as telephone,
               CASE 
                   WHEN p.last_activity >= (NOW() - INTERVAL 5 MINUTE) THEN 1 
                   ELSE 0 
               END as is_online,
               CASE
                   WHEN p.role IN ('admin', 'ADMIN', 'ADMINISTRATION') THEN 1
                   ELSE 0
               END as is_admin
    """
    
    query_from = """
        FROM personnel p
        LEFT JOIN services s ON p.id_service = s.id_service
        LEFT JOIN contacts c ON p.id_phone = c.id
        WHERE 1=1
    """
    
    params = []

    if search_query:
        query_from += """ AND (
            p.nom LIKE %s OR 
            p.prenom LIKE %s OR 
            p.role LIKE %s OR 
            p.username LIKE %s
        )"""
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term, search_term, search_term])

    if filter_status:
        query_from += " AND p.statut_activite = %s"
        params.append(filter_status)

    if filter_online == '1':
        query_from += " AND p.last_activity >= (NOW() - INTERVAL 5 MINUTE)"
    elif filter_online == '0':
        query_from += " AND (p.last_activity < (NOW() - INTERVAL 5 MINUTE) OR p.last_activity IS NULL)"

    # 1. Récupérer le total pour la pagination (COUNT classique sans subquery sélectionnant des colonnes)
    count_query = f"SELECT COUNT(*) as total {query_from}"
    cursor.execute(count_query, tuple(params))
    total_items = cursor.fetchone()['total']
    total_pages = (total_items + per_page - 1) // per_page

    # 2. Récupérer les données paginées
    final_query = f"{query_select} {query_from} ORDER BY is_online DESC, statut_activite DESC, nom, prenom LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    cursor.execute(final_query, tuple(params))
    employes = cursor.fetchall()
    
    # --- Statistiques Globales (Indépendantes de la recherche/pagination) ---
    cursor.execute("SELECT COUNT(*) as total FROM personnel")
    total_employes = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM personnel WHERE last_activity >= (NOW() - INTERVAL 5 MINUTE)")
    total_online = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM personnel WHERE password IS NOT NULL") # Approximation pour user
    total_users = cursor.fetchone()['total']

    # --- Réponse AJAX ---
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_template(
                'personnel/manage_employees_rows.html',
            employes=employes, 
            current_page=page,
            per_page=per_page
        )
        # Note: session object is global, render_template sees it.
        # But 'session' variable in template usually comes from context processors.
        # We assume standard Flask context.
        
        connection.close()
        return jsonify({
            'html': html,
            'current_page': page,
            'total_pages': total_pages,
            'total_items': total_items
        })

    # Récupérer la liste des services (pour le modal d'ajout qui est statique)
    cursor.execute("SELECT * FROM services ORDER BY service_name")
    services = cursor.fetchall()
    
    # Pour le chargement initial, on charge la page 1 (déjà dans 'employes')
    # On a besoin de TOUS les employés pour les Modals d'édition s'ils sont pré-générés ?
    # NON, le changement vers AJAX implique que les modals doivent être dynamiques ou on doit inclure les modals des employés affichés.
    # Dans 'manage_employees_rows.html', on a inclus un script employeeData.
    # On devra adapter le JS pour remplir le modal Edit depuis ce JSON.

    connection.close()
    return render_template(
            'personnel/manage_employees.html',
        title='Personnel',
        services=services,
        employes=employes, # Page 1 seulement
        current_page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_items=total_items,
        search_query=search_query,
        stats={
            'total': total_employes,
            'online': total_online,
            'users': total_users
        }
    )


# ============================================================================
# GESTION DES EMPLOYÉS
# ============================================================================
def handle_employee_addition(cursor):
    """Gère l'ajout d'un nouvel employé"""
    connection = cursor.connection

    try:
        # Récupération et validation des données employé
        nom = request.form.get('nom', '').strip().upper()
        prenom = request.form.get('prenom', '').strip().upper()
        role = request.form.get('role', '').strip().upper()
        service = request.form.get('service', '').strip().upper()
        telephone = request.form.get('telephone', '').strip()
        use_in_planning = 1 if request.form.get('use_in_planning') == 'on' else 0

        # Validation des champs employé
        validate_required_fields({
            'nom': nom,
            'prenom': prenom,
            'role': role,
            'service': service,
            'telephone': telephone
        })

        # Récupération et validation des données utilisateur (si présentes)
        username = request.form.get('usernameI', '').strip()
        password = request.form.get('passwordI', '').strip()
        confirm_password = request.form.get('confirm_passwordI', '').strip()

        hashed_password = None
        # Si des credentials sont fournis, les valider
        if username or password or confirm_password:
            validate_required_fields({
                'username': username,
                'password': password,
                'confirm_password': confirm_password
            })

            if password != confirm_password:
                return redirect_with_message(
                    'manage_employees',
                    Messages.PASSWORD_MISMATCH,
                    'danger'
                )

            if check_username_exists(cursor, username):
                return redirect_with_message(
                    'manage_employees',
                    Messages.USERNAME_EXISTS,
                    'danger'
                )
            
            hashed_password = generate_password_hash(password)

        # Récupérer l'ID du service
        id_service = get_service_id(cursor, service)

        # Créer le contact
        id_contact = create_contact(
            connection, cursor, nom, prenom, role, telephone, g.user['id_personnel']
        )

        # Insertion de l'employé
        cursor.execute("""
            INSERT INTO personnel 
            (nom, prenom, role, id_service, id_phone, username, password, 
             use_in_planning, created_at, updated_at, statut_activite)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), 1)
        """, (nom, prenom, role, id_service, id_contact,
              username or None, hashed_password, use_in_planning))

        connection.commit()

        return redirect_with_message(
            'manage_employees',
            Messages.EMPLOYEE_ADDED,
            'success'
        )

    except ValueError as e:
        return redirect_with_message('manage_employees', str(e), 'danger')
    except Exception as e:
        connection.rollback()
        return redirect_with_message(
            'manage_employees',
            f"Erreur lors de l'ajout : {str(e)}",
            'danger'
        )


def handle_employee_edit(cursor):
    """Gère la modification des informations d'un employé (sans credentials)"""
    connection = cursor.connection

    try:
        id_personnel = request.form.get('id_personnel')
        if not id_personnel:
            raise ValueError("ID personnel manquant")

        # Récupération des données
        nom = request.form.get('nom', '').strip().upper()
        prenom = request.form.get('prenom', '').strip().upper()
        role = request.form.get('role', '').strip().upper()
        service = request.form.get('service', '').strip().upper()
        telephone = request.form.get('telephone', '').strip()
        use_in_planning = 1 if request.form.get('use_in_planning') == 'on' else 0

        # Préparer la mise à jour dynamique
        update_fields = []
        update_values = []

        if nom:
            update_fields.append("nom = %s")
            update_values.append(nom)

        if prenom:
            update_fields.append("prenom = %s")
            update_values.append(prenom)

        if role:
            update_fields.append("role = %s")
            update_values.append(role)

        if service:
            id_service = get_service_id(cursor, service)
            update_fields.append("id_service = %s")
            update_values.append(id_service)

        update_fields.append("use_in_planning = %s")
        update_values.append(use_in_planning)
        
        # Gestion du téléphone
        if telephone:
            # Récupérer l'id_phone actuel
            cursor.execute("SELECT id_phone FROM personnel WHERE id_personnel = %s", (id_personnel,))
            result = cursor.fetchone()
            
            if result and result['id_phone']:
                # Mise à jour contact existant
                cursor.execute("UPDATE contacts SET numero = %s WHERE id = %s", (telephone, result['id_phone']))
            else:
                # Création nouveau contact
                # Note: On a besoin du nom/prenom actuel si pas fournis, mais ici on a soit les nouveaux soit vides
                # Pour simplifier on utilise ce qu'on a ou on récupère l'existant si nécessaire, mais
                # create_contact demande nom/prenom.
                # Si nom/prenom manquent dans le form (edit partiel?), on devrait les fetch.
                # Mais le form d'edit envoie généralement tout.
                # Allons chercher les valeurs actuelles si manquantes
                if not (nom and prenom):
                    cursor.execute("SELECT nom, prenom FROM personnel WHERE id_personnel = %s", (id_personnel,))
                    current_p = cursor.fetchone()
                    nom_contact = nom or current_p['nom']
                    prenom_contact = prenom or current_p['prenom']
                else:
                    nom_contact = nom
                    prenom_contact = prenom
                
                id_contact = create_contact(connection, cursor, nom_contact, prenom_contact, 
                                          role, telephone, g.user['id_personnel'])
                
                update_fields.append("id_phone = %s")
                update_values.append(id_contact)


        if not update_fields and not telephone: # telephone traité à part mais peut être la seule modif
             # Si telephone a été traité (via update contacts), update_fields peut être vide
             # mais on doit quand même dire success.
             # Cependant, update_fields sert pour UPDATE personnel.
             pass

        # Ajouter l'horodatage et l'ID si on update personnel
        if update_fields:
            update_fields.append("updated_at = NOW()")
            update_values.append(id_personnel)

            # Exécuter la mise à jour
            cursor.execute(
                f"UPDATE personnel SET {', '.join(update_fields)} WHERE id_personnel = %s",
                tuple(update_values)
            )

        connection.commit()

        return redirect_with_message(
            'manage_employees',
            Messages.EMPLOYEE_UPDATED,
            'success'
        )

    except ValueError as e:
        return redirect_with_message('manage_employees', str(e), 'danger')
    except Exception as e:
        connection.rollback()
        return redirect_with_message(
            'manage_employees',
            f"Erreur lors de la modification : {str(e)}",
            'danger'
        )


def handle_user_credentials_edit(cursor):
    """Gère la modification des credentials utilisateur (username/password)"""
    connection = cursor.connection

    try:
        id_personnel = request.form.get('id_personnel')
        if not id_personnel:
            raise ValueError("ID personnel manquant")

        username = request.form.get('usernameM', '').strip()
        password = request.form.get('passwordM', '').strip()
        confirm_password = request.form.get('confirm_passwordM', '').strip()

        update_fields = []
        update_values = []

        # Modification du username
        if username:
            if check_username_exists(cursor, username, exclude_id=id_personnel):
                return redirect_with_message(
                    'manage_employees',
                    Messages.USERNAME_EXISTS,
                    'danger'
                )
            update_fields.append("username = %s")
            update_values.append(username)

        # Modification du password
        if password or confirm_password:
            if password != confirm_password:
                return redirect_with_message(
                    'manage_employees',
                    Messages.PASSWORD_MISMATCH,
                    'danger'
                )
            if password:  # Si les mots de passe correspondent et ne sont pas vides
                update_fields.append("password = %s")
                update_values.append(generate_password_hash(password))

        if not update_fields:
            return redirect_with_message(
                'manage_employees',
                Messages.NO_MODIFICATIONS,
                'warning'
            )

        # Ajouter l'horodatage et l'ID
        update_fields.append("updated_at = NOW()")
        update_values.append(id_personnel)

        # Exécuter la mise à jour
        cursor.execute(
            f"UPDATE personnel SET {', '.join(update_fields)} WHERE id_personnel = %s",
            tuple(update_values)
        )

        connection.commit()

        return redirect_with_message(
            'manage_employees',
            Messages.USER_UPDATED,
            'success'
        )

    except ValueError as e:
        return redirect_with_message('manage_employees', str(e), 'danger')
    except Exception as e:
        connection.rollback()
        return redirect_with_message(
            'manage_employees',
            f"Erreur lors de la modification : {str(e)}",
            'danger'
        )


def handle_employee_status_change(cursor):
    """Gère le changement de statut d'un employé"""
    connection = cursor.connection

    try:
        id_personnel = request.form.get('id_personnel')
        nouveau_statut = request.form.get('change_status')

        if not id_personnel or nouveau_statut is None:
            raise ValueError("Paramètres manquants")

        # Récupération de l'ID du téléphone associé
        cursor.execute(
            "SELECT id_phone FROM personnel WHERE id_personnel = %s",
            (id_personnel,)
        )
        result = cursor.fetchone()

        if result and result['id_phone']:
            # Mise à jour du statut du téléphone
            cursor.execute(
                "UPDATE contacts SET status_phone = FALSE WHERE id = %s",
                (result['id_phone'],)
            )

        # Mise à jour du statut de l'employé
        cursor.execute("""
            UPDATE personnel
            SET statut_activite = %s, updated_at = NOW()
            WHERE id_personnel = %s
        """, (nouveau_statut, id_personnel))

        connection.commit()

        return redirect_with_message(
            'manage_employees',
            Messages.EMPLOYEE_STATUS_CHANGED,
            'success'
        )

    except ValueError as e:
        return redirect_with_message('manage_employees', str(e), 'danger')
    except Exception as e:
        connection.rollback()
        return redirect_with_message(
            'manage_employees',
            f"Erreur lors de la mise à jour : {str(e)}",
            'danger'
        )


# ============================================================================
# GESTION DES RÔLES
# ============================================================================
@app.route('/personnel/<int:id_personnel>/roles', methods=['GET'])
@login_required
@handle_errors()

def manage_employee_roles(id_personnel):
    """Page de gestion des rôles d'un employé spécifique"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer les informations de l'employé
    cursor.execute("""
        SELECT p.*, s.service_name
        FROM personnel p
        LEFT JOIN services s ON p.id_service = s.id_service
        WHERE p.id_personnel = %s
    """, (id_personnel,))

    employe = cursor.fetchone()

    if not employe:
        connection.close()
        return redirect_with_message(
            'manage_employees',
            Messages.EMPLOYEE_NOT_FOUND,
            'danger'
        )

    # Récupérer les rôles associés
    cursor.execute("""
        SELECT r.id_role, r.nom_role
        FROM roles r
        INNER JOIN personnel_roles pr ON r.id_role = pr.id_role
        WHERE pr.id_personnel = %s
        ORDER BY r.nom_role
    """, (id_personnel,))
    roles_associes = cursor.fetchall()

    # Récupérer les rôles disponibles
    cursor.execute("""
        SELECT r.id_role, r.nom_role
        FROM roles r
        WHERE r.id_role NOT IN (
            SELECT id_role FROM personnel_roles WHERE id_personnel = %s
        )
        ORDER BY r.nom_role
    """, (id_personnel,))
    roles_disponibles = cursor.fetchall()

    connection.close()

    return render_template(
            'personnel/manage_employee_roles.html',
        title='Gestion des rôles',
        employe=employe,
        roles_associes=roles_associes,
        roles_disponibles=roles_disponibles
    )


@app.route('/personnel/<int:id_personnel>/roles/associer', methods=['POST'])
@login_required
@handle_errors()

def associer_role(id_personnel):
    """Associer un rôle à un employé"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        id_role = request.form.get('id_role')

        if not id_role:
            return redirect_with_message(
                'manage_employee_roles',
                Messages.SELECT_ROLE,
                'warning',
                id_personnel=id_personnel
            )

        # Vérifier si l'association existe déjà
        cursor.execute("""
            SELECT * FROM personnel_roles
            WHERE id_personnel = %s AND id_role = %s
        """, (id_personnel, id_role))

        if cursor.fetchone():
            return redirect_with_message(
                'manage_employee_roles',
                Messages.ROLE_ALREADY_ASSOCIATED,
                'warning',
                id_personnel=id_personnel
            )

        # Ajouter l'association
        cursor.execute("""
            INSERT INTO personnel_roles (id_personnel, id_role)
            VALUES (%s, %s)
        """, (id_personnel, id_role))

        connection.commit()

        return redirect_with_message(
            'manage_employee_roles',
            Messages.ROLE_ASSOCIATED,
            'success',
            id_personnel=id_personnel
        )

    except Exception as e:
        connection.rollback()
        return redirect_with_message(
            'manage_employee_roles',
            f"Erreur lors de l'association : {str(e)}",
            'danger',
            id_personnel=id_personnel
        )
    finally:
        connection.close()


@app.route('/personnel/<int:id_personnel>/roles/dissocier/<int:id_role>', methods=['POST'])
@login_required
@handle_errors()

def dissocier_role(id_personnel, id_role):
    """Dissocier un rôle d'un employé"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM personnel_roles
            WHERE id_personnel = %s AND id_role = %s
        """, (id_personnel, id_role))

        connection.commit()

        return redirect_with_message(
            'manage_employee_roles',
            Messages.ROLE_DISSOCIATED,
            'success',
            id_personnel=id_personnel
        )

    except Exception as e:
        connection.rollback()
        return redirect_with_message(
            'manage_employee_roles',
            f"Erreur lors de la dissociation : {str(e)}",
            'danger',
            id_personnel=id_personnel
        )
    finally:
        connection.close()