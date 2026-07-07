from flask import request, redirect, url_for, render_template, g, flash
from app import app, get_db_connection
from flask import jsonify

from app.utils.utiles import login_required
from app.error import handle_errors


# Gestion des rôles
@app.route('/roles', methods=['GET', 'POST'])
@login_required
@handle_errors()

def roles():
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        nom_role = request.form.get('nom_role', '').strip().upper()

        if not nom_role:
            flash('Le nom du rôle est requis.', 'danger')
            return redirect(url_for('roles'))

        # Vérifier si le rôle existe déjà
        cursor.execute("SELECT id_role FROM roles WHERE nom_role = %s", (nom_role,))
        if cursor.fetchone():
            flash(f'Le rôle "{nom_role}" existe déjà.', 'danger')
            return redirect(url_for('roles'))

        try:
            query = "INSERT INTO roles (nom_role) VALUES (%s)"
            cursor.execute(query, (nom_role,))
            connection.commit()
            flash('Rôle ajouté avec succès !', 'success')
        except Exception as e:
            connection.rollback()
            flash(f'Erreur lors de l\'ajout du rôle : {str(e)}', 'danger')
        finally:
            connection.close()

        return redirect(url_for('roles'))

    # Récupérer tous les rôles avec le nombre de privilèges associés
    cursor.execute("""
        SELECT r.*, 
               COUNT(rp.id_privilege) as privilege_count
        FROM roles r
        LEFT JOIN roles_privileges rp ON r.id_role = rp.id_role
        GROUP BY r.id_role
        ORDER BY r.nom_role
    """)
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
        'admin/privileges/gestion_roles.html',
        title="Gestion des Rôles",
        roles=roles,
        privileges_grouped=privileges_grouped,
        user=g.user
    )


@app.route('/roles/modifier/<int:id_role>', methods=['GET', 'POST'])
@login_required
@handle_errors()

def modifier_role(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        nom_role = request.form.get('nom_role', '').strip().upper()

        if not nom_role:
            flash('Le nom du rôle est requis.', 'danger')
            return redirect(url_for('roles'))

        # Vérifier si le nouveau nom existe déjà (sauf pour ce rôle)
        cursor.execute(
            "SELECT id_role FROM roles WHERE nom_role = %s AND id_role != %s",
            (nom_role, id_role)
        )
        if cursor.fetchone():
            flash(f'Le rôle "{nom_role}" existe déjà.', 'danger')
            return redirect(url_for('roles'))

        try:
            query = "UPDATE roles SET nom_role = %s WHERE id_role = %s"
            cursor.execute(query, (nom_role, id_role))
            connection.commit()
            flash('Rôle modifié avec succès !', 'success')
        except Exception as e:
            connection.rollback()
            flash(f'Erreur lors de la modification : {str(e)}', 'danger')
        finally:
            connection.close()

        return redirect(url_for('roles'))

    connection.close()
    return redirect(url_for('roles'))


@app.route('/roles/supprimer/<int:id_role>', methods=['GET'])
@login_required
@handle_errors()

def supprimer_role(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Vérifier si le rôle est utilisé par des utilisateurs
        cursor.execute(
            "SELECT COUNT(*) as count FROM personnel_roles WHERE id_role = %s",
            (id_role,)
        )
        result = cursor.fetchone()

        if result and result['count'] > 0:
            flash(
                f'Impossible de supprimer ce rôle car {result["count"]} utilisateur(s) l\'utilise(nt).',
                'danger'
            )
            return redirect(url_for('roles'))

        # Supprimer d'abord les associations de privilèges
        cursor.execute("DELETE FROM roles_privileges WHERE id_role = %s", (id_role,))

        # Puis supprimer le rôle
        cursor.execute("DELETE FROM roles WHERE id_role = %s", (id_role,))
        connection.commit()
        flash('Rôle supprimé avec succès !', 'success')
    except Exception as e:
        connection.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'danger')
    finally:
        connection.close()

    return redirect(url_for('roles'))


@app.route('/roles/<int:id_role>/privileges/data', methods=['GET'])
@login_required
@handle_errors()

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
            ORDER BY p.type_privilege, p.nom_privilege
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
            ORDER BY p.type_privilege, p.nom_privilege
        """
        cursor.execute(query_non_associes, (id_role,))
        non_associes = cursor.fetchall()

        result = {
            "associes": [
                {
                    "id_privilege": p["id_privilege"],
                    "nom_privilege": p["nom_privilege"],
                    "type_privilege": p["type_privilege"]
                }
                for p in associes
            ],
            "non_associes": [
                {
                    "id_privilege": p["id_privilege"],
                    "nom_privilege": p["nom_privilege"],
                    "type_privilege": p["type_privilege"]
                }
                for p in non_associes
            ]
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        connection.close()


@app.route('/roles/<int:id_role>/privileges/grouped', methods=['GET'])
@login_required
@handle_errors()

def get_privileges_grouped(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer tous les privilèges avec indication d'association
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

        return jsonify(privileges_grouped)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        connection.close()


@app.route('/roles/<int:id_role>/privileges', methods=['POST'])
@login_required
@handle_errors()

def associer_privilege(id_role):
    id_privilege = request.json.get('id_privilege')
    if not id_privilege:
        return jsonify({"success": False, "error": "ID de privilège manquant"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT IGNORE INTO roles_privileges (id_role, id_privilege) 
            VALUES (%s, %s)
        """, (id_role, id_privilege))
        connection.commit()
        return jsonify({"success": True, "message": "Privilège associé avec succès"}), 200
    except Exception as e:
        connection.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        connection.close()


@app.route('/roles/<int:id_role>/privileges/sauvegarder', methods=['POST'])
@login_required
@handle_errors()

def sauvegarder_privileges(id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        data = request.get_json()
        changes = data.get("changes", [])

        if not changes:
            return jsonify({"success": False, "error": "Aucun changement à sauvegarder"}), 400

        # Traiter les changements
        for change in changes:
            id_privilege = change.get("id_privilege")
            associe = change.get("associe", False)

            if not id_privilege:
                continue

            if associe:
                cursor.execute("""
                    INSERT IGNORE INTO roles_privileges (id_role, id_privilege)
                    VALUES (%s, %s)
                """, (id_role, id_privilege))
            else:
                cursor.execute("""
                    DELETE FROM roles_privileges
                    WHERE id_role = %s AND id_privilege = %s
                """, (id_role, id_privilege))

        connection.commit()
        return jsonify({"success": True, "message": "Modifications sauvegardées avec succès !"})
    except Exception as e:
        connection.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        connection.close()


@app.route('/roles/<int:id_role>/privileges/supprimer/<int:id_privilege>', methods=['DELETE'])
@login_required
@handle_errors()

def supprimer_privilege(id_role, id_privilege):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM roles_privileges 
            WHERE id_role = %s AND id_privilege = %s
        """, (id_role, id_privilege))
        connection.commit()
        return jsonify({"success": True, "message": "Privilège dissocié avec succès"}), 200
    except Exception as e:
        connection.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        connection.close()

@app.route('/personnel/<int:id_personnel>/roles', methods=['GET', 'POST'])
@login_required
@handle_errors()

def gestion_personnel_roles(id_personnel):
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        data = request.get_json()
        id_role = data.get('id_role')

        if not id_role:
            return jsonify({"error": "ID du rôle manquant"}), 400

        try:
            query = "INSERT IGNORE INTO personnel_roles (id_personnel, id_role) VALUES (%s, %s)"
            cursor.execute(query, (id_personnel, id_role))
            connection.commit()
            return jsonify({'message': 'Rôle associé avec succès !'}), 200
        except Exception as e:
            connection.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            connection.close()

    connection.close()
    return jsonify({"error": "Méthode non autorisée"}), 405


@app.route('/personnel/<int:id_personnel>/roles/supprimer/<int:id_role>', methods=['GET'])
@login_required
@handle_errors()

def supprimer_personnel_role(id_personnel, id_role):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        query = "DELETE FROM personnel_roles WHERE id_personnel = %s AND id_role = %s"
        cursor.execute(query, (id_personnel, id_role))
        connection.commit()
        flash('Rôle dissocié avec succès !', 'success')
        return jsonify({"message": "Rôle dissocié avec succès !"})
    except Exception as e:
        connection.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        connection.close()


@app.route('/personnel/<int:id_personnel>/roles/data', methods=['GET'])
@login_required
@handle_errors()

def get_personnel_roles_data(id_personnel):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer les rôles associés
        query_associes = """
            SELECT r.id_role, r.nom_role 
            FROM roles r
            INNER JOIN personnel_roles pr ON r.id_role = pr.id_role
            WHERE pr.id_personnel = %s
            ORDER BY r.nom_role
        """
        cursor.execute(query_associes, (id_personnel,))
        associes = cursor.fetchall()

        # Récupérer les rôles non associés
        query_non_associes = """
            SELECT id_role, nom_role 
            FROM roles
            WHERE id_role NOT IN (
                SELECT id_role FROM personnel_roles WHERE id_personnel = %s
            )
            ORDER BY nom_role
        """
        cursor.execute(query_non_associes, (id_personnel,))
        non_associes = cursor.fetchall()

        return jsonify({
            "associes": associes,
            "non_associes": non_associes
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        connection.close()




@app.route( '/roles/<int:id_role>/privileges', methods = [ 'GET' ] )
@login_required
@handle_errors()

def gestion_privileges_role( id_role ):
    """Page dédiée pour gérer les privilèges d'un rôle"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer les informations du rôle
        cursor.execute( "SELECT * FROM roles WHERE id_role = %s", (id_role,) )
        role = cursor.fetchone()

        if not role:
            flash( "Rôle introuvable", "danger" )
            return redirect( url_for( 'roles' ) )

        # Récupérer tous les privilèges avec indication d'association
        cursor.execute(
            """
            SELECT p.id_privilege,
                   p.nom_privilege,
                   p.type_privilege,
                   CASE WHEN rp.id_privilege IS NOT NULL THEN 1 ELSE 0 END AS associe
            FROM privileges p
                     LEFT JOIN roles_privileges rp ON p.id_privilege = rp.id_privilege AND rp.id_role = %s
            ORDER BY p.type_privilege, p.nom_privilege
                       """, (id_role,)
            )
        privileges = cursor.fetchall()

        # Regrouper par type
        privileges_grouped = { }
        for privilege in privileges:
            type_privilege = privilege[ "type_privilege" ]
            if type_privilege not in privileges_grouped:
                privileges_grouped[ type_privilege ] = [ ]
            privileges_grouped[ type_privilege ].append(
                    {
                            "id_privilege": privilege[ "id_privilege" ],
                            "nom_privilege": privilege[ "nom_privilege" ],
                            "associe": bool( privilege[ "associe" ] )
                            }
                    )

        return render_template(
                'admin/privileges/gestion_privileges_role.html',
                title = f"Privilèges - {role[ 'nom_role' ]}",
                role = role,
                privileges_grouped = privileges_grouped,
                
                )

    except Exception as e:
        flash( f"Erreur : {str( e )}", "danger" )
        return redirect( url_for( 'roles' ) )
    finally:
        connection.close()