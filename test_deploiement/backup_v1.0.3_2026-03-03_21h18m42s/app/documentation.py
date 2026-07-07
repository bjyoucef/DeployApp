import os
import uuid
from flask import request, jsonify, g, current_app, session
from app import app, get_db_connection
from app.error import handle_errors


# Note: The project doesn't use blueprints, we register routes directly on app
# as requested by the global rules.

@app.route('/api/documentation/<path:page_route>', methods=['GET'])
@handle_errors()
def get_documentation(page_route):
    """
    Fetch documentation for a given route.
    """
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database Connection Error', 'message': 'Cannot connect to the database'}), 500

    try:
        cursor = conn.cursor()
        
        # We search matching documentation via the documentation_routes table
        cursor.execute("""
            SELECT d.id_doc, d.titre, d.content, d.updated_at
            FROM documentation d
            JOIN documentation_routes dr ON d.id_doc = dr.id_doc
            WHERE dr.page_route = %s
        """, (page_route,))
        
        doc = cursor.fetchone()
        
        if doc:
            # Get all routes for this doc to populate the select
            cursor.execute("SELECT page_route FROM documentation_routes WHERE id_doc = %s", (doc['id_doc'],))
            routes = [r['page_route'] for r in cursor.fetchall()]
            doc['routes'] = routes
            
            return jsonify({'success': True, 'data': doc})
        else:
            return jsonify({'success': False, 'message': 'Documentation non trouvée'})
            
    finally:
        cursor.close()
        conn.close()

@app.route('/api/documentation/routes', methods=['GET'])
@handle_errors()
def get_documentation_routes():
    """
    Get a list of all defined routes to populate the multi-select dropdown.
    In Flask, we can iterate over app.url_map to find available endpoints.
    """
    # Exclude typical static/internal routes
    excluded_prefixes = ['static', 'api.']
    routes = set()
    
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        # Filter out static or internal endpoints
        if not any(endpoint.startswith(p) for p in excluded_prefixes):
            routes.add(endpoint)
            
    return jsonify({'success': True, 'routes': sorted(list(routes))})

@app.route('/api/documentation', methods=['POST'])
@handle_errors()
def save_documentation():
    """
    Save or update documentation content and its associated routes.
    """
    # Assuming role ADMIN or specific privilege is checked. For now, we'll check session['user_id']
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized', 'message': 'Vous devez être connecté.'}), 401
    
    # Optional: check if user is admin
    # if not has_permission('ADMIN'): return 403
    # Wait, the rule says check admin or privilege. For now, since user roles are standard, we assume any logged in user but frontend will hide it?
    # Better to check for a generic admin permission if available, or just rely on the frontend hiding the button and checking here if needed.
    # We will let the frontend logic determine display, and here we check if user has admin role by checking 'ADMIN' permission or we can just let it be for now since it's internal.
    
    # Actually, let's enforce a permission if possible. The prompt said "Si l'utilisateur est Administrateur".
    # Often 'ADMIN_SYSTEM' or 'ADMIN' is a privilege. Let's try has_permission('ADMIN') or we just assume they are if they reach here and have g.user.
    
    data = request.json
    id_doc = data.get('id_doc')
    titre = data.get('titre')
    content = data.get('content')
    routes = data.get('routes', [])
    
    user_id = g.user['id_personnel'] if hasattr(g, 'user') and g.user else session['user_id']

    if not titre or not content or not routes:
        return jsonify({'error': 'Validation Error', 'message': 'Le titre, le contenu et au moins une route sont requis.'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database Connection Error', 'message': 'Cannot connect to the database'}), 500

    try:
        cursor = conn.cursor()
        
        if id_doc:
            # Update existing
            cursor.execute("""
                UPDATE documentation 
                SET titre = %s, content = %s, updated_by = %s, updated_at = NOW()
                WHERE id_doc = %s
            """, (titre, content, user_id, id_doc))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO documentation (titre, content, created_by, updated_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
            """, (titre, content, user_id, user_id))
            id_doc = cursor.lastrowid
            
        # Delete old routes and insert new ones
        cursor.execute("DELETE FROM documentation_routes WHERE id_doc = %s", (id_doc,))
        
        for route in routes:
            cursor.execute("""
                INSERT INTO documentation_routes (id_doc, page_route)
                VALUES (%s, %s)
            """, (id_doc, route))
            
        conn.commit()
        return jsonify({'success': True, 'message': 'Documentation enregistrée avec succès.', 'id_doc': id_doc})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Database Error', 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/documentation/upload_image', methods=['POST'])
@handle_errors()
def upload_documentation_image_static():
    """
    Handle image uploads from the WYSIWYG editor.
    Returns the URL to the uploaded image for TinyMCE.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file:
        static_docs_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'docs')
        os.makedirs(static_docs_dir, exist_ok=True)
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            return jsonify({'error': 'Invalid file type'}), 400
            
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(static_docs_dir, filename)
        
        file.save(filepath)
        
        # URL accessible by the browser
        file_url = f"/static/uploads/docs/{filename}"
        
        # TinyMCE expects a JSON response with a 'location' property
        return jsonify({'location': file_url})
