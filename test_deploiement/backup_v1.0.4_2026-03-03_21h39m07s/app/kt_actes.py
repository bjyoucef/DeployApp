import pymysql
from flask import request, redirect, url_for, render_template, g, flash

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import login_required, permission_required


@app.route('/actes_kt', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_ACTES_KT')
def actes_kt():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT a.*, s.name_specialty
            FROM kt_actes a
            LEFT JOIN specialty s ON a.id_specialty = s.id_specialty
        """)
        actes_kt = cursor.fetchall()

        cursor.execute("SELECT * FROM specialty")
        specialtys = cursor.fetchall()
    except pymysql.MySQLError as e:
        flash(f"Erreur : {e}", "danger")
        actes_kt, specialtys = [], []

    return render_template('kt_actes.html', title="Gestion des Actes", actes_kt=actes_kt, specialtys=specialtys,
                           user=g.user)


@app.route('/add_acte_kt', methods=['POST'])
@login_required
@handle_errors()
@permission_required('ADD_ACTES_KT')
def add_acte_kt():
    try:
        # Récupération des données du formulaire avec des valeurs par défaut
        def get_form_value(field, default=0, value_type=float):
            return value_type(request.form.get(field, default) or default)

        form_data = {
            "code_cnas": request.form['code_cnas'],
            "name_acte_kt": request.form['name_acte_kt'],
            "id_specialty": int(request.form['id_specialty']),
            "nbr_nuit": int(request.form.get('nbr_nuit', 0)),
            "prix_cnas_casnos": get_form_value('prix_cnas_casnos'),
            "prix_autre_convention": get_form_value('prix_autre_convention'),
            "prix_public": get_form_value('prix_public'),
            "urgence": get_form_value('prix_urgence'),
            "part_operateur_cnas_casnos": get_form_value('part_operateur_cnas_casnos'),
            "part_operateur_payante": get_form_value('part_operateur_payante'),
            "part_operateur_urgence": get_form_value('part_operateur_urgence'),
        }

        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
        INSERT INTO kt_actes (
            code_cnas, name_acte_kt, id_specialty, nbr_nuit, prix_cnas_casnos, 
            prix_autre_convention, prix_public, urgence, 
            part_operateur_cnas_casnos, part_operateur_payante, part_operateur_urgence
        )
        VALUES (%(code_cnas)s, %(name_acte_kt)s, %(id_specialty)s, %(nbr_nuit)s, %(prix_cnas_casnos)s,
                %(prix_autre_convention)s, %(prix_public)s, %(urgence)s, 
                %(part_operateur_cnas_casnos)s, %(part_operateur_payante)s, %(part_operateur_urgence)s)
        """
        cursor.execute(sql, form_data)
        connection.commit()
        flash('Acte ajouté avec succès', 'success')
    except pymysql.MySQLError as e:
        flash(f'Erreur lors de l\'ajout : {e}', 'danger')

    return redirect(url_for('actes_kt'))


@app.route('/update_acte_kt', methods=['POST'])
@login_required
@handle_errors()
@permission_required('MODIFIER_ACTES_KT')
def update_acte_kt():
    try:
        # Récupération des données du formulaire avec des valeurs par défaut
        def get_form_value(field, default=0, value_type=float):
            return value_type(request.form.get(field, default) or default)

        form_data = {
            "id_acte": int(request.form['id_acte']),
            "code_cnas": request.form['code_cnas'],
            "name_acte_kt": request.form['name_acte_kt'],
            "id_specialty": int(request.form['specialty_acte_kt']),
            "nbr_nuit": int(request.form.get('nbr_nuit', 0)),
            "prix_cnas_casnos": get_form_value('prix_cnas_casnos'),
            "prix_autre_convention": get_form_value('prix_autre_convention'),
            "prix_public": get_form_value('prix_public'),
            "urgence": get_form_value('prix_urgence'),
            "part_operateur_cnas_casnos": get_form_value('part_operateur_cnas_casnos'),
            "part_operateur_payante": get_form_value('part_operateur_payante'),
            "part_operateur_urgence": get_form_value('part_operateur_urgence'),
        }


        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
        UPDATE kt_actes
        SET code_cnas = %(code_cnas)s, name_acte_kt = %(name_acte_kt)s, id_specialty = %(id_specialty)s, 
            nbr_nuit = %(nbr_nuit)s, prix_cnas_casnos = %(prix_cnas_casnos)s, 
            prix_autre_convention = %(prix_autre_convention)s, prix_public = %(prix_public)s, 
            urgence = %(urgence)s, part_operateur_cnas_casnos = %(part_operateur_cnas_casnos)s, 
            part_operateur_payante = %(part_operateur_payante)s, 
            part_operateur_urgence = %(part_operateur_urgence)s
        WHERE id_acte = %(id_acte)s
        """
        cursor.execute(sql, form_data)
        connection.commit()
        flash('Acte mis à jour avec succès', 'success')
    except pymysql.MySQLError as e:
        flash(f'Erreur lors de la mise à jour : {e}', 'danger')

    return redirect(url_for('actes_kt'))