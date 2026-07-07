from flask import g, render_template, request, redirect, url_for

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, has_permission


@app.route('/phone')
def phone():
    user = g.get('user', None)

    # Construction des requêtes SQL en fonction de la connexion utilisateur
    if not user:
        # Utilisateur non connecté, afficher uniquement les contacts et personnel avec status_phone = TRUE
        sql_contacts = "SELECT * FROM contacts WHERE status_phone = TRUE"
    else:
        # Si l'utilisateur a accès aux téléphones, afficher tout, sinon filtrer par status_phone
        if has_permission('DESACTIVER_TELEPHONE'):
            sql_contacts = "SELECT c.*, CONCAT(p.nom, ' ', p.prenom) AS nom_personne_add FROM contacts c LEFT JOIN personnel p ON c.id_personne_add = p.id_personnel;"
        else:
            sql_contacts = "SELECT c.*, CONCAT(p.nom, ' ', p.prenom) AS nom_personne_add FROM contacts c LEFT JOIN personnel p ON c.id_personne_add = p.id_personnel WHERE c.status_phone = TRUE OR p.statut_activite = TRUE;"

    # Gestion sécurisée de la connexion
    connection = get_db_connection()  # Obtenez la connexion à la base de données
    if connection:
        try:
            cursor = connection.cursor()  # Utilisez directement cursor() pour obtenir un curseur
            cursor.execute(sql_contacts)
            contacts = cursor.fetchall()

        finally:
            connection.close()  # Assurez-vous de fermer la connexion après usage

    # Rendu du template avec les contacts et le titre
    return render_template('phone.html',
                           contacts=contacts,
                           title='Contacts',
                           user=user)


# Route pour gérer l'ajout ou la modification d'un contact existant
@app.route('/add_or_edit_phone', methods=['GET', 'POST'])
@login_required
@handle_errors()
def add_or_edit_phone():
    user = g.user
    id_personne_add = user['id_personnel']

    if request.method == 'POST':

        phone_id = request.form.get('id')
        name = request.form.get('name')
        department = request.form.get('department')
        phone = request.form.get('phone')
        if not name or not department or not phone:
            return redirect(url_for('phone', message="Tous les champs doivent être remplis!", category="success"))

        try:
            # Connexion à la base de données
            conn = get_db_connection()
            cursor = conn.cursor()

            if phone_id:  # Si l'ID est présent, modification d'un contact
                cursor.execute("""
                    UPDATE contacts
                    SET nom = %s, Poste = %s, numero = %s
                    WHERE id = %s
                """, (name, department, phone, phone_id))
            else:  # Sinon, ajout d'un nouveau contact
                cursor.execute("""
                    INSERT INTO contacts (nom, Poste, numero, id_personne_add)
                    VALUES (%s, %s, %s, %s)
                """, (name, department, phone, id_personne_add))

            # Commit des modifications sur la connexion, pas sur le curseur
            conn.commit()
        except Exception as e:
            return redirect(url_for('phone', message=f"Une erreur est survenue : {e}", category="danger"))
        finally:
            cursor.close()  # Fermeture du curseur
            conn.close()  # Fermeture de la connexion

        return redirect(url_for('phone', message="Contact mis à jour avec succès!", category="success"))

    # Si c'est une modification, récupérer les informations du contact
    contact = None
    if 'phone_id' in request.args:
        phone_id = request.args.get('phone_id')
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            if conn:
                cursor.execute("SELECT * FROM contacts WHERE id = %s", (phone_id,))
                contact = cursor.fetchone()
        except Exception as e:
            return redirect(url_for('phone',
                                    message=f"Contact récupéré pour modification: {contact} et Une erreur est survenue : {e}",
                                    category="danger"))
        finally:
            cursor.close()
            conn.close()

    # Afficher la liste des contacts pour l'ajout ou modification
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM contacts")
        contacts = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('phone', contacts=contacts, contact=contact, title='Contacts',
                            user=g.user))


# Route pour supprimer un contact
@app.route('/change_status_phone', methods=['POST'])
@login_required
@handle_errors()
def change_status_phone():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        id_contact = request.form['id']
        nouveau_statut_phone_contact = int(request.form['change_status_phone_contact'])
        # Met à jour le statut du téléphone pour le contact
        cursor.execute("""
                UPDATE contacts
            SET status_phone = %s
            WHERE id = %s
        """, (nouveau_statut_phone_contact, id_contact))
        conn.commit()
        return redirect(url_for('phone', message="Le statut a été modifié avec succès!", category="success"))

    except Exception as e:
        # Afficher l'erreur dans la console pour le débogage
        print(f"Erreur lors du changement de statut : {str(e)}")
        return redirect(url_for('phone', message="Erreur lors de la modification du statut!", category="danger")), 500
