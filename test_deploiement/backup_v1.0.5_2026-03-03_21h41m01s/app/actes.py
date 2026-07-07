import pymysql
from flask import request, redirect, url_for, render_template, g, flash

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, permission_required


@app.route('/actes', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ACTES')
def actes():
    connection= get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM services")
    services = cursor.fetchall()

    cursor.execute("""
        SELECT ha.id_acte, ha.name_acte, ha.prix_acte, ha.id_service, s.service_name
        FROM honoraires_acte ha
        LEFT JOIN services s ON ha.id_service = s.id_service
    """)
    actes = cursor.fetchall()

    return render_template('actes.html', title="Gestion des actes", actes=actes, services=services, user=g.user)


@app.route('/add_acte', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ADD_ACTES')
def add_acte():
    name_acte = request.form['name_acte']
    prix_acte = request.form['prix_acte']
    id_service = request.form['id_service']  # Ajout du service

    try:
        connection= get_db_connection()
        cursor = connection.cursor()
        sql = """
        INSERT INTO honoraires_acte (name_acte, prix_acte, id_service)
        VALUES (%s, %s, %s)
        """
        cursor.execute(sql, (name_acte, prix_acte, id_service))
        connection.commit()
        flash('Acte ajouté avec succès', 'success')
    except pymysql.MySQLError as e:
        flash(f'Erreur : {e}', 'danger')
    return redirect(url_for('actes'))


@app.route('/update_acte', methods=['POST'])
@login_required
@handle_errors()
@permission_required('UPDATE_ACTES')
def update_acte():
    id_acte = request.form['id_acte']
    name_acte = request.form['name_acte']
    prix_acte = request.form['prix_acte']
    id_service = request.form['id_service']  # Ajout du service

    try:
        connection= get_db_connection()
        cursor = connection.cursor()
        sql = """
        UPDATE honoraires_acte
        SET name_acte = %s, prix_acte = %s, id_service = %s
        WHERE id_acte = %s
        """
        cursor.execute(sql, (name_acte, prix_acte, id_service, id_acte))
        connection.commit()
        flash('Acte mis à jour avec succès', 'success')
    except pymysql.MySQLError as e:
        flash(f'Erreur : {e}', 'danger')
    return redirect(url_for('actes'))


@app.route('/delete_acte/<int:id_acte>', methods=['POST'])
@login_required
@handle_errors()
@permission_required('DELETE_ACTES')
def delete_acte(id_acte):
    try:
        connection= get_db_connection()
        cursor = connection.cursor()
        sql = "DELETE FROM honoraires_acte WHERE id_acte = %s"
        cursor.execute(sql, (id_acte,))
        connection.commit()
        flash('Acte supprimé avec succès', 'success')
    except pymysql.MySQLError as e:
        flash(f'Erreur : {e}', 'danger')
    return redirect(url_for('actes'))
