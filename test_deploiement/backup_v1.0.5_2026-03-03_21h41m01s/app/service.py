from flask import render_template, request, g
from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import redirect_with_message, nettoyer_texte, login_required, permission_required


# Route pour afficher la liste des services
@app.route('/service')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def service():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM services ORDER BY service_name")
    services = cursor.fetchall()
    connection.close()
    return render_template('service.html',title="Liste des services", services=services, user=g.user)


# Route pour ajouter un service
@app.route('/add', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def add_service():
    service_name = (request.form['service_name']).upper()
    prix_joure = request.form['prix_joure']
    prix_nuit = request.form['prix_nuit']
    prix_24h = request.form['prix_24h']
    salaire = request.form['salaire']
    color = request.form['color']  # Ajout du champ color

    # Ensure numeric fields are not empty, set to 0.00 if empty
    prix_joure = float(prix_joure) if prix_joure else 0.00
    prix_nuit = float(prix_nuit) if prix_nuit else 0.00
    prix_24h = float(prix_24h) if prix_24h else 0.00
    salaire = float(salaire) if salaire else 0.00

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO services (service_name, prix_joure, prix_nuit, prix_24h, salaire, color)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (service_name, prix_joure, prix_nuit, prix_24h, salaire, color))

    cleaned_privilege = nettoyer_texte(
        service_name)  # Nettoyer le privilège (espaces -> underscores, accents -> sans accents)
    query = "INSERT INTO `privileges` (`nom_privilege`,'type_privilege') VALUES (%s,'SERVICES')"
    cursor.execute(query, (cleaned_privilege,))

    connection.commit()
    connection.close()
    return redirect_with_message('service',"Le service a été ajouté avec succès.", 'success')



# Route pour modifier un service
@app.route('/edit-service/<int:id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SERVICES')
def edit_service(id):
    service_name = (request.form['service_name']).upper()
    prix_joure = request.form['prix_joure']
    prix_nuit = request.form['prix_nuit']
    prix_24h = request.form['prix_24h']
    salaire = request.form['salaire']
    color = request.form['color']

    # Ensure numeric fields are not empty, set to 0.00 if empty
    prix_joure = float(prix_joure) if prix_joure else 0.00
    prix_nuit = float(prix_nuit) if prix_nuit else 0.00
    prix_24h = float(prix_24h) if prix_24h else 0.00
    salaire = float(salaire) if salaire else 0.00

    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
            UPDATE services
        SET service_name = %s, prix_joure = %s, prix_nuit = %s, prix_24h = %s, salaire = %s, color = %s
        WHERE id_service = %s
    """, (service_name, prix_joure, prix_nuit, prix_24h, salaire, color, id))
    connection.commit()
    connection.close()
    return redirect_with_message('service',"Le service a été modifié avec succès.", 'success')
