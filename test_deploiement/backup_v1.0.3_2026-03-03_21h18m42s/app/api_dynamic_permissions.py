from flask import request, jsonify

from app import app, get_db_connection
from app.utils.utiles import login_required, has_permission
from app.dynamic_permissions import permission_service


@app.route('/api/config/dynamic_permissions/ui', methods=['POST'])
@login_required
def save_ui_permission():
    # Only Admin (or specific config role)
    if not has_permission('MODE_CONFIGURATION'):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    page_route = data.get('page_route')
    element_selector = data.get('element_selector')
    privilege_name = data.get('privilege_name') 
    
    # On reçoit le NOM du privilège, faut trouver l'ID
    if not all([page_route, element_selector, privilege_name]):
        return jsonify({'error': 'Missing fields'}), 400

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. Get ID
            cursor.execute("SELECT id_privilege FROM privileges WHERE nom_privilege = %s", (privilege_name,))
            res = cursor.fetchone()
            if not res:
                return jsonify({'error': 'Privilege not found'}), 404
            id_privilege = res['id_privilege']

            # 2. Upsert
            # MySQL 'ON DUPLICATE KEY UPDATE'
            sql = """
                INSERT INTO actes_ui_config (page_route, element_selector, id_privilege)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE id_privilege = %s
            """
            cursor.execute(sql, (page_route, element_selector, id_privilege, id_privilege))

            # 3. Sync Routes (IF it's a Module Card OR we have a target_url)
            target_route = None

            # Case A: Explicit Module Card ID
            if element_selector and element_selector.startswith('#module-card-'):
                target_route = element_selector.replace('#module-card-', '')
            
            # Case B: Target URL provided (from Link)
            if not target_route and data.get('target_url'):
                try:
                    # Resolve URL to Endpoint
                    # Need to bind adapter to a dummy server name if not in request context context, 
                    # but here we are in a request context.
                    # match() returns (endpoint, args)
                    adapter = app.url_map.bind('', '/')
                    # We might need to handle the leading slash or full url.
                    # config_mode sends pathname "/patients"
                    path = data.get('target_url')
                    if path.startswith('/'):
                        # adapter.match matches path info
                        endpoint, args = adapter.match(path, method='GET')
                        target_route = endpoint
                except Exception as e:
                    print(f"Could not resolve URL {data.get('target_url')}: {e}")

            if target_route:
                # Insert/Update actes_routes_config
                sql_route = """
                    INSERT INTO actes_routes_config (endpoint, id_privilege)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE id_privilege = %s
                """
                cursor.execute(sql_route, (target_route, id_privilege, id_privilege))
        connection.commit()
        
        # Reload cache
        permission_service.load_configurations()
        
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500
    finally:
        connection.close()

@app.route('/api/config/dynamic_permissions/ui', methods=['DELETE'])
@login_required
def delete_ui_permission():
    if not has_permission('MODE_CONFIGURATION'):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    page_route = data.get('page_route')
    element_selector = data.get('element_selector')
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "DELETE FROM actes_ui_config WHERE page_route=%s AND element_selector=%s"
            cursor.execute(sql, (page_route, element_selector))

            # Sync Routes Delete
            if element_selector and element_selector.startswith('#module-card-'):
                target_route = element_selector.replace('#module-card-', '')
                if target_route:
                    sql_route = "DELETE FROM actes_routes_config WHERE endpoint=%s"
                    cursor.execute(sql_route, (target_route,))
        connection.commit()
        permission_service.load_configurations()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        connection.close()

@app.route('/api/privileges/list', methods=['GET'])
@login_required
def list_privileges():
    # Public endpoint for logged users? No, mainly for config autocomplete
    if not has_permission('MODE_CONFIGURATION'):
        return jsonify([])

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id_privilege, nom_privilege FROM privileges ORDER BY nom_privilege")
            # Return list of strings
            rows = cursor.fetchall()
            privs = [r['nom_privilege'] for r in rows]
        return jsonify(privs)
    finally:
        connection.close()

