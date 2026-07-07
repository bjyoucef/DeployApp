from flask import Response

from app import app, get_db_connection
from app.utils.utiles import login_required
from app.error import handle_errors


@app.route('/generate_rdp/<ip_address>')
@login_required
@handle_errors()
def generate_rdp(ip_address):
    # Retrieve the user information associated with the IP address
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM personnel WHERE ip_adresse = %s', (ip_address,))
    user_windows = cursor.fetchone()
    conn.close()
    
    if user_windows:
        # If user is found, retrieve the username
        username = user_windows['username']

        # RDP file content with username
        rdp_content = f"""full address:s:{ip_address}
        username:s:inaya.ehp\\{username}
        prompt for credentials:i:1
        administrative session:i:1
        """
    else:
        # If no user is found, provide default RDP file content
        rdp_content = f"""full address:s:{ip_address}
        prompt for credentials:i:1
        administrative session:i:1
        """
    
    # Create a response with the RDP file content
    response = Response(rdp_content, mimetype='application/x-rdp')
    response.headers['Content-Disposition'] = 'attachment; filename=remote_connection.rdp'
    return response
