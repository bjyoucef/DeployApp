from flask import request, redirect, url_for, render_template, g

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


@app.route('/equipements', methods=['GET', 'POST'])
@login_required
@handle_errors()

def equipements():
    user = g.user
    connection = get_db_connection()

    cursor= connection.cursor()
    if request.method == 'POST':
        # Ajouter un nouvel équipement
        if 'add_equipment' in request.form:
            nom_equipement = request.form['nom_equipement']
            type_equipement = request.form['type_equipement']
            reference = request.form['reference']
            ip_adresse = request.form['ip_adresse']
            mac_adresse = request.form['mac_adresse']
            login = request.form['login']
            pass_equipement = request.form['pass']  # Attention à la variable 'pass' qui est un mot-clé

            cursor.execute("""
                INSERT INTO equipements 
                (nom_equipement, type_equipement, reference, ip_adresse, mac_adresse, login, pass, date_acquisition, etat)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), 'fonctionnel')
            """, (
                nom_equipement, type_equipement, reference, ip_adresse, mac_adresse, login, pass_equipement))
            connection.commit()
            return redirect(
                url_for('equipements', message="L'équipement a été ajouté avec succès.", category="success"))

        # Modifier un équipement existant
        elif 'edit_equipment' in request.form:
            id_equipement = request.form['id_equipement']
            nom_equipement = request.form['nom_equipement']
            type_equipement = request.form['type_equipement']
            reference = request.form['reference']
            ip_adresse = request.form['ip_adresse']
            mac_adresse = request.form['mac_adresse']
            login = request.form['login']
            pass_equipement = request.form['pass']

            # Préparation des parties dynamiques de la requête SQL
            update_fields = [
                'nom_equipement = %s',
                'type_equipement = %s',
                'reference = %s',
                'ip_adresse = %s',
                'mac_adresse = %s',
                'login = %s',
                'pass = %s'
            ]
            params = [nom_equipement, type_equipement, reference, ip_adresse, mac_adresse, login, pass_equipement]

            # Ajoutez l'ID de l'équipement à la liste des paramètres pour la requête SQL
            params.append(id_equipement)

            # Construction de la requête SQL dynamique
            sql_query = f"""
                UPDATE equipements 
                SET {', '.join(update_fields)}
                WHERE id_equipement = %s
            """

            # Exécution de la requête SQL
            cursor.execute(sql_query, params)
            connection.commit()

            return redirect(url_for('equipements', message="Les informations de l'équipement ont été mises à jour.",
                                    category="success"))

        # Désactiver ou activer un équipement
        elif 'change_status' in request.form:
            id_equipement = request.form['id_equipement']
            nouveau_statut = request.form['change_status']

            # Exécuter la requête SQL pour mettre à jour le statut
            cursor.execute("""
                UPDATE equipements
                SET etat = %s, updated_at = NOW()
                WHERE id_equipement = %s
            """, (nouveau_statut, id_equipement))

            connection.commit()
            return redirect(
                url_for('equipements', message="Le statut de l'équipement a été mis à jour.", category="success"))

    # Récupérer la liste des équipements
    cursor.execute("SELECT * FROM equipements ORDER BY date_acquisition DESC")
    equipements = cursor.fetchall()

    connection.close()
    return render_template('equipements.html', title='Equipements', equipements=equipements, user=user)