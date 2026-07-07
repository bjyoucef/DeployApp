from flask import request, redirect, url_for, render_template, g, flash
from app import app, get_db_connection
from flask import jsonify

from app.utiles import permission_required, login_required
from app.error import handle_errors


# Gestion des rôles
@app.route('/roles', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def roles():
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        # Ajouter un rôle
        nom_role = (request.form['nom_role']).upper()
        query = "INSERT INTO roles (nom_role) VALUES (%s)"
        cursor.execute(query, (nom_role,))
        connection.commit()
        flash('Rôle ajouté avec succès !', 'success')
        return redirect(url_for('roles', user=g.user))

    # Récupérer tous les rôles
    cursor.execute("SELECT * FROM roles")
    roles = cursor.fetchall()

    # Récupérer les privilèges regroupés par type
    cursor.execute("""
        SELECT p.id_privilege, p.nom_privilege, p.type_privilege 
        FROM privileges p
        ORDER BY p.type_privilege, p.nom_privilege
    """)
    privileges = cursor.fetchall()

    # Regrouper par type
    privileges_grouped = {}
    for privilege in privileges:
        type_privilege = privilege["type_privilege"]
        if type_privilege not in privileges_grouped:
            privileges_grouped[type_privilege] = []
        privileges_grouped[type_privilege].append({
            "id_privilege": privilege["id_privilege"],
            "nom_privilege": privilege["nom_privilege"]
        })

    connection.close()

    return render_template(
        'privileges/gestion_roles.html',
        title="Gestion des Rôles",
        roles=roles,
        privileges_grouped=privileges_grouped,
        user=g.user
    )


@app.route('/roles/modifier/<int:id_role>', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def modifier_role(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        # Modifier un rôle
        nom_role = (request.form['nom_role']).upper()

        query = "UPDATE roles SET nom_role=%s WHERE id_role=%s"
        cursor.execute(query, (nom_role, id_role))
        connection.commit()
        flash('Rôle modifié avec succès !', 'success')
        return redirect(url_for('roles', user=g.user))

    # Récupérer le rôle pour modification
    cursor.execute("SELECT * FROM roles WHERE id_role=%s", (id_role,))
    role = cursor.fetchone()

    connection.close()
    return redirect(url_for('roles', role=role,user=g.user))

@app.route('/roles/supprimer/<int:id_role>', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def supprimer_role(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    # Vérification pour éviter de supprimer un rôle critique ou important si nécessaire
    cursor.execute("DELETE FROM roles WHERE id_role=%s", (id_role,))
    connection.commit()
    flash('Rôle supprimé avec succès !', 'success')

    connection.close()

    return redirect(url_for('roles', user=g.user))

@app.route('/roles/<int:id_role>/privileges/data', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def get_privileges_data(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer les privilèges associés
        query_associes = """
        SELECT p.id_privilege, p.nom_privilege, p.type_privilege 
        FROM privileges p
        INNER JOIN roles_privileges rp ON p.id_privilege = rp.id_privilege
        WHERE rp.id_role = %s
        """
        cursor.execute(query_associes, (id_role,))
        associes = cursor.fetchall()

        # Récupérer les privilèges non associés
        query_non_associes = """
            SELECT p.id_privilege, p.nom_privilege, p.type_privilege
            FROM privileges p
            WHERE p.id_privilege NOT IN (
                SELECT rp.id_privilege FROM roles_privileges rp WHERE rp.id_role = %s
            )
            """
        cursor.execute(query_non_associes, (id_role,))
        non_associes = cursor.fetchall()

        # Résultat structuré
        result = {
            "associes": [
                {"id_privilege": p["id_privilege"], "nom_privilege": p["nom_privilege"], "type_privilege": p["type_privilege"]}
                for p in associes
            ],
            "non_associes": [
                {"id_privilege": p["id_privilege"], "nom_privilege": p["nom_privilege"], "type_privilege": p["type_privilege"]}
                for p in non_associes
            ]
        }

    except Exception as e:
        # Gérer les erreurs au niveau de la base de données
        connection.close()
        raise e

    finally:
        # S'assurer que la connexion est fermée
        connection.close()

    # Retourner les données au format JSON
    return jsonify(result)



@app.route('/roles/<int:id_role>/privileges/grouped', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def get_privileges_grouped(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer les privilèges associés
    cursor.execute("""
        SELECT p.id_privilege, p.nom_privilege, p.type_privilege, 
               CASE WHEN rp.id_privilege IS NOT NULL THEN 1 ELSE 0 END AS associe
        FROM privileges p
        LEFT JOIN roles_privileges rp ON p.id_privilege = rp.id_privilege AND rp.id_role = %s
        ORDER BY p.type_privilege, p.nom_privilege
    """, (id_role,))
    privileges = cursor.fetchall()

    # Regrouper par type
    privileges_grouped = {}
    for privilege in privileges:
        type_privilege = privilege["type_privilege"]
        if type_privilege not in privileges_grouped:
            privileges_grouped[type_privilege] = []
        privileges_grouped[type_privilege].append({
            "id_privilege": privilege["id_privilege"],
            "nom_privilege": privilege["nom_privilege"],
            "associe": privilege["associe"]
        })

    connection.close()
    return jsonify(privileges_grouped)


@app.route('/roles/<int:id_role>/privileges', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def associer_privilege(id_role):
    id_privilege = request.json.get('id_privilege')
    if not id_privilege:
        flash('ID de privilège manquant', 'danger')

        return jsonify({"error": "ID de privilège manquant"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT IGNORE INTO roles_privileges (id_role, id_privilege) 
        VALUES (%s, %s)
    """, (id_role, id_privilege))
    connection.commit()
    connection.close()
    flash('Privilège associé avec succès !', 'success')

    return jsonify({"message": "Privilège associé avec succès"}), 200

@app.route('/roles/<int:id_role>/privileges/sauvegarder', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def sauvegarder_privileges(id_role):
    data = request.get_json()
    changes = data.get("changes", [])
    connection = get_db_connection()
    cursor = connection.cursor()

    for change in changes:
        id_privilege = change["id_privilege"]
        associe = change["associe"]

        if associe:
            # Ajouter l'association si elle n'existe pas
            cursor.execute("""
                INSERT IGNORE INTO roles_privileges (id_role, id_privilege)
                VALUES (%s, %s)
            """, (id_role, id_privilege))

        else:
            # Supprimer l'association
            cursor.execute("""
                DELETE FROM roles_privileges
                WHERE id_role = %s AND id_privilege = %s
            """, (id_role, id_privilege))

    connection.commit()
    connection.close()
    return jsonify({"message": "Modifications sauvegardées avec succès !"})


@app.route('/roles/<int:id_role>/privileges/supprimer/<int:id_privilege>', methods=['DELETE'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def supprimer_privilege(id_role, id_privilege):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        DELETE FROM roles_privileges 
        WHERE id_role = %s AND id_privilege = %s
    """, (id_role, id_privilege))
    connection.commit()
    connection.close()
    flash('Privilège dissocié avec succès !', 'success')

    return jsonify({"message": "Privilège dissocié avec succès"}), 200

@app.route('/personnel/<int:id_personnel>/roles', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def gestion_personnel_roles(id_personnel):
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        # Associer un rôle à un personnel
        data = request.get_json()  # Utilisation de get_json pour recevoir des données JSON
        id_role = data.get('id_role')

        if not id_role:
            return jsonify({"error": "ID du rôle manquant"}), 400

        query = "INSERT IGNORE INTO personnel_roles (id_personnel, id_role) VALUES (%s, %s)"
        cursor.execute(query, (id_personnel, id_role))
        connection.commit()
        connection.close()

        return jsonify({'message': 'Rôle associé avec succès !'}), 200

    # Récupérer les rôles associes
    query = """
        SELECT r.id_role, r.nom_role 
        FROM roles r
        INNER JOIN personnel_roles pr ON r.id_role = pr.id_role
        WHERE pr.id_personnel = %s
    """
    cursor.execute(query, (id_personnel,))
    associes = cursor.fetchall()

    # Récupérer les rôles non associes
    query = """
        SELECT * FROM roles
        WHERE id_role NOT IN (SELECT id_role FROM personnel_roles WHERE id_personnel = %s)
    """
    cursor.execute(query, (id_personnel,))
    non_associes = cursor.fetchall()
    connection.close()
    return render_template('gestion_personnel_roles.html', id_personnel=id_personnel, associes=associes, non_associes=non_associes, user=g.user)

@app.route('/personnel/<int:id_personnel>/roles/supprimer/<int:id_role>', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def supprimer_personnel_role(id_personnel, id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    # Exécution de la suppression du rôle
    query = "DELETE FROM personnel_roles WHERE id_personnel=%s AND id_role=%s"
    cursor.execute(query, (id_personnel, id_role))
    connection.commit()

    connection.close()
    flash('Rôle dissocié avec succès !', 'success')

    # Retourner une réponse JSON avec un message de succès
    return jsonify({"message": "Rôle dissocié avec succès !"})

@app.route('/personnel/<int:id_personnel>/roles/data', methods=['GET'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def get_personnel_roles_data(id_personnel):
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer les rôles associés
    query_associes = """
        SELECT r.id_role, r.nom_role 
        FROM roles r
        INNER JOIN personnel_roles pr ON r.id_role = pr.id_role
        WHERE pr.id_personnel = %s
    """
    cursor.execute(query_associes, (id_personnel,))
    associes = cursor.fetchall()
    print(associes)

    # Récupérer les rôles non associés
    query_non_associes = """
        SELECT id_role, nom_role 
        FROM roles
        WHERE id_role NOT IN (SELECT id_role FROM personnel_roles WHERE id_personnel = %s)
    """
    cursor.execute(query_non_associes, (id_personnel,))
    non_associes = cursor.fetchall()
    connection.close()

    # Retourner les deux listes en JSON
    return jsonify({"associes": associes, "non_associes": non_associes})

# Gestion des privilèges
@app.route('/privileges', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ROLES_ET_PRIVILEGES')
def privileges():
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        # Ajouter un privilège
        nom_privilege = (request.form['nom_privilege']).upper()
        type_privilege = request.form['type_privilege']
        query = """
        INSERT INTO privileges (nom_privilege, type_privilege) 
        VALUES (%s, %s)
        """
        cursor.execute(query, (nom_privilege, type_privilege))
        connection.commit()
        flash('Privilège ajouté avec succès !', 'success')
        return redirect(url_for('privileges', user=g.user))

    # Afficher tous les privilèges avec leurs types
    cursor.execute("SELECT id_privilege, nom_privilege, type_privilege FROM privileges")
    privileges = cursor.fetchall()

    connection.close()
    return render_template(
        'privileges/gestion_privileges.html',
        title="Gestion des Privilèges",
        privileges=privileges,
        user=g.user
    )
