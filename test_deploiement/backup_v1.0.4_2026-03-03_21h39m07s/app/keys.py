from flask import request, redirect, url_for, render_template, g

from app import app, get_db_connection
from app.utiles import login_required, permission_required
from app.error import handle_errors


@app.route('/cles_')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def cles_():
    connection = get_db_connection()
    cursor = connection.cursor()
    # Récupérer les clés disponibles
    cursor.execute("""
        SELECT id, numero_cle, description, quantite, 
               quantite_emprunts, quantite_manquante, 
               (quantite - quantite_emprunts - quantite_manquante) as qte 
        FROM cles
    """)
    cles = cursor.fetchall()

    cursor.execute('SELECT * FROM personnel WHERE statut_activite = TRUE')
    personnes = cursor.fetchall()

    # Récupérer le mouvement des clés avec plus de détails
    mouvements = {}
    for cle in cles:
        cursor.execute("""
            SELECT 'Emprunt' as description, date_emprunt as date, 
                   p1.nom as emprunteur, p2.nom as donneur
            FROM cles_mouvement  
            LEFT JOIN personnel p1 ON cles_mouvement .personne_id_prend = p1.id_personnel
            LEFT JOIN personnel p2 ON cles_mouvement .personne_id_donne = p2.id_personnel
            WHERE cle_id = %s
            UNION
            SELECT 'Retour' as description, date_retour as date, 
                   p3.nom as retourneur, p4.nom as receveur
            FROM cles_mouvement  
            LEFT JOIN personnel p3 ON cles_mouvement .personne_id_retourne = p3.id_personnel
            LEFT JOIN personnel p4 ON cles_mouvement .personne_id_recoit = p4.id_personnel
            WHERE cle_id = %s AND date_retour IS NOT NULL
            UNION
            SELECT 'Manquante' as description, date_marquer_manquante as date, 
                   p5.nom as marqueur_manque, p6.nom as personne_perte
            FROM cles_mouvement 
            LEFT JOIN personnel p5 ON cles_mouvement.personne_id_marquee_manque = p5.id_personnel
            LEFT JOIN personnel p6 ON cles_mouvement.personne_id_perte = p6.id_personnel
            WHERE cle_id = %s
            UNION
            SELECT 'Retrouvée' as description, date_retrouvie as date, 
                   p7.nom as marqueur_retrouve, p8.nom as personne_retrouve
            FROM cles_mouvement 
            LEFT JOIN personnel p7 ON cles_mouvement.personne_id_marquee_retrevie = p7.id_personnel
            LEFT JOIN personnel p8 ON cles_mouvement.personne_id_retrevie = p8.id_personnel
            WHERE cle_id = %s AND date_retrouvie IS NOT NULL
            ORDER BY date ASC
        """, (cle['id'], cle['id'], cle['id'], cle['id']))
        mouvements[cle['id']] = cursor.fetchall()

    connection.close()
    return render_template('cles_.html', title='Cles', personnes=personnes, cles=cles, mouvements=mouvements,
                           user=g.user)


# Ajouter une clé
@app.route('/add_key', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def add_key():
    user = g.user
    mes = ('', '')
    connection = get_db_connection()
    numero_cle = request.form['numero_cle']
    description = request.form['description']
    quantite = request.form['quantite']

    try:
        cursor = connection.cursor()
        # Insérer la nouvelle clé dans la base de données
        cursor.execute("""
            INSERT INTO cles (numero_cle, description, quantite) 
            VALUES (%s, %s, %s)
        """, (numero_cle, description, quantite))
        connection.commit()
        mes = ('Clé ajoutée avec succès!', 'success')
    except Exception as e:
        connection.rollback()
        mes = (f'Erreur lors de l\'ajout de la clé: {e}', 'danger')
    finally:
        connection.close()

    return redirect(url_for('cles_', message=mes[0], category=mes[1]))


@app.route('/modifier_key/<int:id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def modifier_key(id):
    connection = get_db_connection()
    if request.method == 'POST':
        numero_cle = request.form.get('numero_cle', None)  # Récupère le numéro de clé ou None si vide
        description = request.form.get('description', None)  # Récupère la description ou None si vide
        quantite = request.form.get('quantite', None)  # Récupère la quantité ou None si vide

        cursor= connection.cursor()
        updates = []
        params = []

        if numero_cle is not None and numero_cle != "":
            updates.append("numero_cle = %s")
            params.append(numero_cle)

        if description is not None and description != "":
            updates.append("description = %s")
            params.append(description)

        if quantite is not None and quantite != "":
            updates.append("quantite = %s")
            params.append(quantite)

        # Ajoutez l'ID de la clé à la liste des paramètres
        params.append(id)

        if updates:  # Vérifiez si nous avons des mises à jour à faire
            sql = f"UPDATE cles SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(sql, params)

        connection.commit()
        connection.close()

        return redirect(url_for('cles_', message="Clé modifiée avec succès!", category="success"))

    return redirect(url_for('cles_'))


@app.route('/mvm_cles')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def mvm_cles():
    user = g.user
    filter_option = request.args.get('filter', 'all')  # Par défaut, 'all' est sélectionné
    message = ('', '')

    connection= get_db_connection()
    try:
        cursor =connection.cursor()
        # Récupérer les clés disponibles
        cursor.execute("""
            SELECT id, numero_cle, description, quantite, 
                   quantite_emprunts, quantite_manquante, 
                   (quantite - quantite_emprunts - quantite_manquante) AS qte 
            FROM cles
        """)
        cles = cursor.fetchall()

        # Base de la requête pour les emprunts
        base_query = """
                    SELECT cm.*,
                    p_donne.nom AS nom_personne_donne, 
                    p_donne.prenom AS prenom_personne_donne, 
                    p_donne.role AS role_personne_donne, 

                    p_prend.nom AS nom_personne_prend, 
                    p_prend.prenom AS prenom_personne_prend, 
                    p_prend.role AS role_personne_prend, 

                    p_retourne.nom AS nom_personne_retourne, 
                    p_retourne.prenom AS prenom_personne_retourne, 
                    p_retourne.role AS role_personne_retourne, 

                    p_recoit.nom AS nom_personne_recoit, 
                    p_recoit.prenom AS prenom_personne_recoit, 
                    p_recoit.role AS role_personne_recoit, 

                    p_marquee_manque.nom AS nom_marquee_manque,
                    p_marquee_manque.prenom AS prenom_marquee_manque,
                    p_marquee_manque.role AS role_marquee_manque,

                    p_perte.nom AS nom_perte, 
                    p_perte.prenom AS prenom_perte, 
                    p_perte.role AS role_perte, 

                    p_marquee_retrevie.nom AS nom_marquee_retrevie,
                    p_marquee_retrevie.prenom AS prenom_marquee_retrevie,
                    p_marquee_retrevie.role AS role_marquee_retrevie,

                    p_retrevie.nom AS nom_retrevie, 
                    p_retrevie.prenom AS prenom_retrevie, 
                    p_retrevie.role AS role_retrevie, 

                    c.numero_cle, 
                    c.description
                    FROM cles_mouvement cm
                    LEFT JOIN personnel p_prend ON cm.personne_id_prend = p_prend.id_personnel
                    LEFT JOIN personnel p_donne ON cm.personne_id_donne = p_donne.id_personnel
                    LEFT JOIN personnel p_recoit ON cm.personne_id_recoit = p_recoit.id_personnel
                    LEFT JOIN personnel p_retourne ON cm.personne_id_retourne = p_retourne.id_personnel
                    LEFT JOIN personnel p_marquee_manque ON cm.personne_id_marquee_manque = p_marquee_manque.id_personnel
                    LEFT JOIN personnel p_perte ON cm.personne_id_perte = p_perte.id_personnel
                    LEFT JOIN personnel p_marquee_retrevie ON cm.personne_id_marquee_retrevie = p_marquee_retrevie.id_personnel
                    LEFT JOIN personnel p_retrevie ON cm.personne_id_retrevie = p_retrevie.id_personnel
                    LEFT JOIN cles c ON cm.cle_id = c.id
        """

        if filter_option == 'en_cours':
            base_query += " WHERE cm.date_retour IS NULL AND cm.personne_id_perte IS NULL"
        elif filter_option == 'retournees':
            base_query += " WHERE cm.date_retour IS NOT NULL"
        base_query += " ORDER BY cm.id DESC"

        cursor.execute(base_query)
        emprunts = cursor.fetchall()

        # Marquer les clés empruntées
        empruntes_ids = {emprunt['cle_id'] for emprunt in emprunts}
        for cle in cles:
            cle['empruntee'] = cle['id'] in empruntes_ids

        cursor.execute('SELECT * FROM personnel WHERE statut_activite = TRUE')
        personnes = cursor.fetchall()

    except Exception as e:
        message = (f'Erreur lors de la récupération des données : {str(e)}', 'danger')
        return render_template('mouvements_cles.html', title='Cles', cles=[], emprunts=[], personnes=[],
                               filter=filter_option, user=user, message=message[0], category=message[1])

    return render_template('mouvements_cles.html', title='Cles', cles=cles, emprunts=emprunts, personnes=personnes,
                           filter=filter_option, user=user)


@app.route('/emprunt_key/<int:id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def emprunt_key(id):
    personne_id_prend = request.form.get('personne_id_prend')
    if not personne_id_prend:
        return redirect(url_for('cles_', message='Identifiant de la personne empruntant manquant.', category='error'))

    personne_id_donne = g.user['id_personnel']
    mes = ('', '')

    try:
        connection= get_db_connection()
        cursor= connection.cursor()
        # Vérifier la disponibilité de la clé
        cursor.execute("""
            SELECT (quantite - quantite_emprunts - quantite_manquante) AS qte
            FROM cles
            WHERE id = %s
        """, (id,))
        cle = cursor.fetchone()

        if cle and cle['qte'] > 0:
            # Insérer l'emprunt dans la table
            cursor.execute("""
                INSERT INTO cles_mouvement (cle_id, personne_id_donne, personne_id_prend, date_emprunt)
                VALUES (%s, %s, %s, NOW())
            """, (id, personne_id_donne, personne_id_prend))

            # Mettre à jour la quantité empruntée
            cursor.execute("""
                UPDATE cles
                SET quantite_emprunts = quantite_emprunts + 1
                WHERE id = %s
            """, (id,))
            connection.commit()

            mes = ('Clé empruntée avec succès!', 'success')
        else:
            mes = ('La clé n\'est pas disponible!', 'error')
    except Exception as e:
        mes = (f'Erreur lors de l\'emprunt de la clé: {str(e)}', 'error')

    return redirect(url_for('cles_', message=mes[0], category=mes[1]))


# Retourner une clé
@app.route('/retourner_key/<int:id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def retourner_key(id):
    personne_id_recoit = g.user['id_personnel']
    personne_id_retourne = request.form.get('personne_id_retourne')
    mes = ('', '')
    connection = get_db_connection()
    try:
        cursor= connection.cursor()
        # Récupérer l'ID de la clé de l'emprunt
        cursor.execute("SELECT cle_id FROM cles_mouvement  WHERE id = %s", (id,))
        cle_info = cursor.fetchone()
        if cle_info:
            cle_id = cle_info['cle_id']

            # Mettre à jour la quantité empruntée
            cursor.execute("""
                UPDATE cles SET quantite_emprunts = quantite_emprunts - 1 WHERE id = %s
            """, (cle_id,))

            # Mettre à jour la date de retour, personne_id_recoit et personne_id_retourne
            cursor.execute("""
                UPDATE cles_mouvement
                SET date_retour = NOW(), personne_id_recoit = %s, personne_id_retourne = %s
                WHERE id = %s
            """, (personne_id_recoit, personne_id_retourne, id))

            connection.commit()
            # Erreur lors du retour de la clé: not all arguments converted during string formatting

            mes = ('Clé retournée avec succès et quantité mise à jour!', 'success')
        else:
            mes = ('Aucun emprunt trouvé pour cet ID.', 'error')
    except Exception as e:
        connection.rollback()
        mes = (f'Erreur lors du retour de la clé: {str(e)}', 'error')
    finally:
        connection.close()

    return redirect(url_for('emprunt_key', message=mes[0], category=mes[1]))


@app.route('/marquer_key_manquant/<int:id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def marquer_key_manquant(id):
    personne_id_perte = request.form.get('personne_id_perte')
    personne_id_marquee_manque = g.user['id_personnel']
    message = ('', '')

    connection =get_db_connection()
    try:
        cursor= connection.cursor()
        cursor.execute("SELECT cle_id FROM cles_mouvement WHERE id = %s", (id,))
        cle_id = cursor.fetchone()

        if cle_id:
            cursor.execute("""
                SELECT (quantite - (quantite_emprunts - 1) - quantite_manquante) AS qte
                FROM cles
                WHERE id = %s
            """, (cle_id['cle_id'],))
            cle = cursor.fetchone()

            if cle and cle['qte'] > 0:
                cursor.execute("""
                    UPDATE cles
                    SET quantite_manquante = quantite_manquante + 1, quantite_emprunts = quantite_emprunts + 1
                    WHERE id = %s
                """, (cle_id['cle_id'],))

                cursor.execute("""
                    UPDATE cles_mouvement
                    SET personne_id_marquee_manque = %s, personne_id_perte = %s, date_marquer_manquante = NOW()
                    WHERE id = %s
                """, (personne_id_marquee_manque, personne_id_perte, id))

                connection.commit()
                message = ('Clé marquée comme manquante avec succès !', 'success')
            else:
                message = ('Clé déjà manquante ou quantité insuffisante.', 'danger')
        else:
            message = ('Clé introuvable.', 'danger')

    except Exception as e:
        connection.rollback()
        message = (f'Erreur lors de la mise à jour de la clé : {str(e)}', 'danger')

    return redirect(url_for('emprunt_key', message=message[0], category=message[1]))


@app.route('/marquer_retrouvee/<int:id>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_CLES')
def marquer_retrouvee(id):
    id_personne_trouvee = request.form.get('id_personne_trouvee')
    mes = ('', '')

    connection = get_db_connection()
    try:
        cursor= connection.cursor()
        # Vérifier si l'ID existe dans la table cles_mouvement
        cursor.execute("SELECT cle_id FROM cles_mouvement WHERE id = %s", (id,))
        cle_manquante = cursor.fetchone()

        if cle_manquante:
            cle_id = cle_manquante['cle_id']

            # Vérifier la quantité manquante pour cette clé
            cursor.execute("SELECT quantite_manquante FROM cles WHERE id = %s", (cle_id,))
            cle = cursor.fetchone()

            if cle and cle['quantite_manquante'] > 0:
                # Mettre à jour la table `cles` en réduisant la quantité manquante
                cursor.execute("""
                    UPDATE cles
                    SET quantite_manquante = quantite_manquante - 1
                    WHERE id = %s
                """, (cle_id,))

                # Mettre à jour la table `cles_mouvement` en indiquant la clé comme retrouvée
                cursor.execute("""
                    UPDATE cles_mouvement
                    SET date_retrouvie = NOW(),
                        personne_id_retrevie = %s,
                        personne_id_marquee_retrevie = %s
                    WHERE id = %s
                """, (id_personne_trouvee, g.user['id_personnel'], id))

                # Commit des modifications dans la base de données
                connection.commit()
                mes = ('Clé marquée comme retrouvée avec succès !', 'success')
            else:
                mes = ('Aucune clé manquante à retrouver ou quantité déjà retrouvée.', 'danger')
        else:
            mes = ('Aucune clé manquante trouvée avec cet ID.', 'danger')

    except Exception as e:
        connection.rollback()
        mes = (f'Erreur lors de la mise à jour de la clé retrouvée : {str(e)}', 'danger')

    finally:
        connection.close()

    return redirect(url_for('emprunt_key', message=mes[0], category=mes[1]))
