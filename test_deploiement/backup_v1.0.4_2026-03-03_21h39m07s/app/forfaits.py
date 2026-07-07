import pymysql
from flask import request, redirect, url_for, render_template, g, flash

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, permission_required


@app.route('/forfait', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_FORFAITS')
def forfait():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT f.*, s.name_specialty
        FROM forfait_actes f
        LEFT JOIN specialty s ON f.id_specialty = s.id_specialty
    """)
    forfaits = cursor.fetchall()

    for forfait in forfaits:
        cursor.execute("""
            SELECT p.id_produit, p.description, fp.qte
            FROM forfait_actes_produits fp
            INNER JOIN produits p ON fp.id_produit = p.id_produit
            WHERE fp.id_forfait = %s
        """, (forfait['id_forfait'],))
        produits = cursor.fetchall()
        forfait['produits_inclus'] = produits

    cursor.execute("SELECT * FROM specialty")
    specialtys = cursor.fetchall()

    cursor.execute("SELECT * FROM produits")
    produits = cursor.fetchall()


    return render_template('forfait.html', title="Gestion des Forfaits", forfaits=forfaits, specialtys=specialtys, produits=produits, user=g.user)


@app.route('/add_forfait', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_FORFAITS')
def add_forfait():
    name_forfait = request.form['name_forfait']
    id_specialty = request.form['specialty_forfait']
    duree_forfait = request.form.get('duree_forfait') or None
    nbr_nuit = request.form.get('nbr_nuit') or None
    prix_forfait = request.form['prix_forfait']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Insertion du forfait
        sql_forfait = """
        INSERT INTO forfait_actes (name_forfait, id_specialty, duree_forfait, nbr_nuit, prix_forfait)
        VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(sql_forfait, (name_forfait, id_specialty, duree_forfait, nbr_nuit, prix_forfait))
        id_forfait = cursor.lastrowid  # Récupérer l'ID du forfait inséré

        connection.commit()
        flash('Forfait ajouté avec succès ', 'success')
    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur lors de l\'ajout du forfait : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('forfait'))


@app.route('/update_forfait', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_FORFAITS')
def update_forfait():
    id_forfait = request.form['id_forfait']
    name_forfait = request.form['name_forfait']
    id_specialty = request.form['specialty_forfait']
    duree_forfait = request.form.get('duree_forfait') or None
    nbr_nuit = request.form.get('nbr_nuit') or None
    prix_forfait = request.form['prix_forfait']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Mise à jour des informations du forfait
        sql_update = """
        UPDATE forfait_actes
        SET name_forfait = %s, id_specialty = %s, duree_forfait = %s, nbr_nuit = %s, prix_forfait = %s
        WHERE id_forfait = %s
        """
        cursor.execute(sql_update, (name_forfait, id_specialty, duree_forfait, nbr_nuit, prix_forfait, id_forfait))

        connection.commit()
        flash('Forfait mis à jour avec succès ', 'success')
    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('forfait'))



@app.route('/delete_forfait/<int:id_forfait>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_FORFAITS')
def delete_forfait(id_forfait):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        sql = "DELETE FROM forfait_actes WHERE id_forfait = %s"
        cursor.execute(sql, (id_forfait,))
        connection.commit()
        flash('Forfait supprimé avec succès', 'success')
    except pymysql.MySQLError as e:
        flash(f'Erreur : {e}', 'danger')
    return redirect(url_for('forfait'))



@app.route('/add_produit_to_forfait/<int:id_forfait>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_FORFAITS')
def add_produit_to_forfait(id_forfait):
    id_produit = request.form['id_produit']
    qte = request.form['qte']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifie si le produit est déjà inclus
        sql_check = """
        SELECT id FROM forfait_actes_produits WHERE id_forfait = %s AND id_produit = %s
        """
        cursor.execute(sql_check, (id_forfait, id_produit))
        if cursor.fetchone():
            flash('Le produit est déjà inclus dans ce forfait.', 'warning')
        else:
            # Ajoute le produit
            sql_insert = """
            INSERT INTO forfait_actes_produits (id_forfait, id_produit, qte)
            VALUES (%s, %s, %s)
            """
            cursor.execute(sql_insert, (id_forfait, id_produit, qte))
            connection.commit()
            flash('Produit ajouté au forfait avec succès.', 'success')
    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('forfait'))


@app.route('/remove_produit_from_forfait/<int:id_forfait>/<int:id_produit>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_FORFAITS')
def remove_produit_from_forfait(id_forfait, id_produit):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Supprime le produit du forfait
        sql_delete = """
        DELETE FROM forfait_actes_produits WHERE id_forfait = %s AND id_produit = %s
        """
        cursor.execute(sql_delete, (id_forfait, id_produit))
        connection.commit()
        flash('Produit supprimé du forfait avec succès.', 'success')
    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('forfait'))



