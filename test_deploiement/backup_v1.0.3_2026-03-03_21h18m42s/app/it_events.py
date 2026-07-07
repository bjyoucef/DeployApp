from datetime import datetime
from flask import render_template, flash, redirect, request, g, url_for
from app import app, get_db_connection
from app.utils.utiles import login_required
from app.error import handle_errors

@app.route('/it_event')
@login_required
@handle_errors()

def it_event():
    """Affiche la liste des événements IT."""
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT i.*, 
       CONCAT(criator.nom, ' ', criator.prenom) AS created_par 
FROM it_events i
LEFT JOIN personnel criator ON i.id_created_par = criator.id_personnel
ORDER BY i.pinned DESC, i.created_at DESC
                """
            )
            events = cursor.fetchall()
        return render_template('admin/it_event.html', events=events, user=g.user)
    except Exception as e:
        flash(f"Erreur de base de données : {str(e)}", "danger")
        return render_template('admin/it_event.html', events=[], user=g.user)
    finally:
        if connection:
            connection.close()

@app.route('/add', methods=['POST'])
@login_required
@handle_errors()

def add_it_event():
    """Permet d'ajouter un nouvel événement IT."""
    title = request.form.get('title')
    description = request.form.get('description')
    event_type = request.form.get('event_type')
    status = request.form.get('status')
    created_at = datetime.now()
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO it_events (id_created_par, title, description, event_type, created_at, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (g.user['id_personnel'], title, description, event_type, created_at, status))
        connection.commit()
        flash('Événement ajouté avec succès!', "success")
    except Exception as e:
        connection.rollback()
        flash(f"Erreur lors de l'ajout : {str(e)}", "danger")
    finally:
        if connection:
            connection.close()
    return redirect(url_for('it_event'))

@app.route('/it_event/edit/<int:id>', methods=['POST'])
@login_required
@handle_errors()

def edit_it_event(id):
    """Modifie un événement IT."""
    title = request.form.get('title')
    description = request.form.get('description')
    event_type = request.form.get('event_type')
    status = request.form.get('status')
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = """
                UPDATE it_events SET
                     title = %s,
                     description = %s,
                     event_type = %s,
        status = %s,
        updated_at = NOW()
                WHERE id = %s
            """
            cursor.execute(sql, (title, description, event_type, status, id))
        connection.commit()
        flash('Événement mis à jour avec succès!', "success")
    except Exception as e:
        connection.rollback()
        flash(f"Erreur de mise à jour : {str(e)}", "danger")
    finally:
        if connection:
            connection.close()
    return redirect(url_for('it_event'))

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
@handle_errors()

def delete_it_event(id):
    """Supprime un événement IT."""
    connection = get_db_connection()

    if not connection:
        flash("Impossible de se connecter à la base de données.", "danger")
        return redirect(url_for('it_event'))

    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM it_events WHERE id = %s", (id,))
        connection.commit()
        flash('Événement supprimé avec succès!', "success")
    except Exception as e:
        connection.rollback()
        flash(f"Erreur de suppression : {str(e)}", "danger")
    finally:
        connection.close()

    return redirect(url_for('it_event'))



@app.route('/pin_event', methods=['POST'])
@login_required
@handle_errors()

def pin_event():
    """Épingle ou désépingle un événement IT via soumission de formulaire."""
    event_id = request.form.get("id")
    if not event_id:
        flash("ID de l'événement manquant.", "danger")
        return redirect(url_for('it_event'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT pinned FROM it_events WHERE id = %s", (event_id,))
        result = cursor.fetchone()
        if not result:
            flash("Événement introuvable.", "danger")
            return redirect(url_for('it_event'))
        current_pinned = result['pinned']

        new_pinned = 0 if current_pinned == 1 else 1
        cursor.execute("UPDATE it_events SET pinned = %s WHERE id = %s", (new_pinned, event_id))
        connection.commit()
        flash("Événement mis à jour avec succès !", "success")
    except Exception as e:
        connection.rollback()
        flash(f"Erreur lors de la mise à jour : {str(e)}", "danger")
    finally:
        if connection:
            connection.close()
    return redirect(url_for('it_event'))

