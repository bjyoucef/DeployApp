import pymysql
from flask import request, redirect, url_for, render_template, g, flash

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


@app.route('/actes_kt', methods=['GET', 'POST'])
@login_required
@handle_errors()

def actes_kt():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Charger les actes avec spécialité
        cursor.execute("""
            SELECT a.*, s.name_specialty
            FROM kt_actes a
            LEFT JOIN specialty s ON a.id_specialty = s.id_specialty
            ORDER BY a.name_acte_kt
        """)
        actes_kt = cursor.fetchall()

        # Pour chaque acte, charger ses conventions associées
        for acte in actes_kt:
            cursor.execute("""
                SELECT ac.id, ac.id_convention, c.code_convention, c.nom_convention,
                       ac.prix, ac.part_operateur
                FROM kt_actes_conventions ac
                JOIN kt_conventions c ON ac.id_convention = c.id_convention
                WHERE ac.id_acte = %s AND ac.est_actif = 1
                ORDER BY c.nom_convention
            """, (acte['id_acte'],))
            acte['conventions'] = cursor.fetchall()

        # Charger toutes les conventions actives (pour le formulaire)
        cursor.execute("""
            SELECT * FROM kt_conventions WHERE est_active = 1 ORDER BY nom_convention
        """)
        conventions = cursor.fetchall()

        cursor.execute("SELECT * FROM specialty")
        specialtys = cursor.fetchall()

    except pymysql.MySQLError as e:
        flash(f"Erreur : {e}", "danger")
        actes_kt, specialtys, conventions = [], [], []

    return render_template(
        'admin/kt_actes.html',
        title="Gestion des Actes",
        actes_kt=actes_kt,
        specialtys=specialtys,
        conventions=conventions
    )


@app.route('/add_acte_kt', methods=['POST'])
@login_required
@handle_errors()

def add_acte_kt():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        def get_form_value(field, default=0, value_type=float):
            return value_type(request.form.get(field, default) or default)

        # Insérer l'acte avec les prix standard (payante + urgence)
        form_data = {
            "code_cnas": request.form['code_cnas'],
            "name_acte_kt": request.form['name_acte_kt'],
            "id_specialty": int(request.form['id_specialty']),
            "nbr_nuit": int(request.form.get('nbr_nuit', 0)),
            "prix_payant": get_form_value('prix_payant'),
            "honoraires_payant": get_form_value('honoraires_payant'),
            "prix_urgence": get_form_value('prix_urgence'),
            "honoraires_urgence": get_form_value('honoraires_urgence'),
        }

        sql = """
        INSERT INTO kt_actes (
            code_cnas, name_acte_kt, id_specialty, nbr_nuit,
            prix_payant, honoraires_payant, prix_urgence, honoraires_urgence
        )
        VALUES (%(code_cnas)s, %(name_acte_kt)s, %(id_specialty)s, %(nbr_nuit)s,
                %(prix_payant)s, %(honoraires_payant)s, %(prix_urgence)s, %(honoraires_urgence)s)
        """
        cursor.execute(sql, form_data)
        conn.commit()
        id_acte = cursor.lastrowid

        # Insérer les associations convention/prix
        conv_ids = request.form.getlist('conv_id[]')
        conv_prix = request.form.getlist('conv_prix[]')
        conv_honoraires = request.form.getlist('conv_honoraires[]')

        for i, cid in enumerate(conv_ids):
            if cid:
                prix = float(conv_prix[i]) if i < len(conv_prix) and conv_prix[i] else 0
                honoraires = float(conv_honoraires[i]) if i < len(conv_honoraires) and conv_honoraires[i] else 0
                if prix > 0 or honoraires > 0:
                    cursor.execute("""
                        INSERT INTO kt_actes_conventions (id_acte, id_convention, prix, part_operateur, created_by)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (id_acte, cid, prix, honoraires, g.user['id_personnel']))

        conn.commit()
        flash('Acte ajouté avec succès', 'success')

    except pymysql.MySQLError as e:
        conn.rollback()
        flash(f"Erreur lors de l'ajout : {e}", 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('actes_kt'))


@app.route('/update_acte_kt', methods=['POST'])
@login_required
@handle_errors()

def update_acte_kt():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        def get_form_value(field, default=0, value_type=float):
            return value_type(request.form.get(field, default) or default)

        id_acte = int(request.form['id_acte'])

        form_data = {
            "id_acte": id_acte,
            "code_cnas": request.form['code_cnas'],
            "name_acte_kt": request.form['name_acte_kt'],
            "id_specialty": int(request.form['specialty_acte_kt']),
            "nbr_nuit": int(request.form.get('nbr_nuit', 0)),
            "prix_payant": get_form_value('prix_payant'),
            "honoraires_payant": get_form_value('honoraires_payant'),
            "prix_urgence": get_form_value('prix_urgence'),
            "honoraires_urgence": get_form_value('honoraires_urgence'),
        }

        sql = """
        UPDATE kt_actes
        SET code_cnas = %(code_cnas)s, name_acte_kt = %(name_acte_kt)s, id_specialty = %(id_specialty)s,
            nbr_nuit = %(nbr_nuit)s, prix_payant = %(prix_payant)s, honoraires_payant = %(honoraires_payant)s,
            prix_urgence = %(prix_urgence)s, honoraires_urgence = %(honoraires_urgence)s
        WHERE id_acte = %(id_acte)s
        """
        cursor.execute(sql, form_data)

        # Mettre à jour les associations convention/prix
        # Supprimer les anciennes puis réinsérer
        cursor.execute("DELETE FROM kt_actes_conventions WHERE id_acte = %s", (id_acte,))

        conv_ids = request.form.getlist('conv_id[]')
        conv_prix = request.form.getlist('conv_prix[]')
        conv_honoraires = request.form.getlist('conv_honoraires[]')

        for i, cid in enumerate(conv_ids):
            if cid:
                prix = float(conv_prix[i]) if i < len(conv_prix) and conv_prix[i] else 0
                honoraires = float(conv_honoraires[i]) if i < len(conv_honoraires) and conv_honoraires[i] else 0
                if prix > 0 or honoraires > 0:
                    cursor.execute("""
                        INSERT INTO kt_actes_conventions (id_acte, id_convention, prix, part_operateur, created_by)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (id_acte, cid, prix, honoraires, g.user['id_personnel']))

        conn.commit()
        flash('Acte mis à jour avec succès', 'success')

    except pymysql.MySQLError as e:
        conn.rollback()
        flash(f"Erreur lors de la mise à jour : {e}", 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('actes_kt'))