from flask import render_template, request, g, redirect, url_for

from app import app, get_db_connection
from app.utils.utiles import login_required, save_audio, save_files
from app.error import handle_errors


@app.route('/rapports')
@login_required
@handle_errors()

def rapports():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, titre, details, auteur, date, file_path, audio_path FROM rapports ORDER BY date DESC")
        rapports = cursor.fetchall()
    except:
        rapports = []
    finally:
        cursor.close()
        conn.close()

    return render_template('rapports.html', user=g.user, rapports=rapports)


@app.route('/submit_report', methods=['POST'])
@login_required
@handle_errors()

def submit_report():
    titre = request.form.get('title')
    details = request.form.get('details')
    auteur = g.user['id_personnel']
    files = request.files.getlist('file')  # Récupérer tous les fichiers uploadés
    audio_data = request.form.get('audioData')

    max_files = 10  # Limite de fichiers

    if len(files) > max_files:
        return redirect(url_for('rapports', error='Vous ne pouvez pas télécharger plus de {} fichiers.'.format(max_files)))

    if not titre or not details or not auteur:
        return redirect(url_for('rapports'))

    try:
        connection= get_db_connection()
        cursor = connection.cursor()

        file_paths = save_files(files,f'files/rapports') if files else None
        audio_path = save_audio(audio_data,'audios/rapports') if audio_data else None

        # Insert report information into the database
        cursor.execute("""
            INSERT INTO rapports (titre, details, auteur, date, file_path, audio_path)
            VALUES (%s, %s, %s, NOW(), %s, %s)
        """, (titre, details, auteur, file_paths, audio_path))

        connection.commit()
        # flash('Rapport soumis avec succès.', 'success')  # Optionally flash success message

    except Exception as e:
        # Handle logging and errors here, return redirect for errors
        print(f'Error submitting report: {e}')  # Replace with proper logging
        return redirect(url_for('rapports'))  # Redirect on error

    return redirect(url_for('rapports'))  # Redirect on success
