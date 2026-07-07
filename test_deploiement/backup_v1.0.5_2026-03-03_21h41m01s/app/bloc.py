import os

from flask import render_template, g, flash
from flask import request, jsonify

from app import app, get_db_connection
from app.auth import login_required, get_user_accessible_blocs
from app.error import handle_errors
from app.utiles import allowed_file, permission_required


@app.route('/bloc')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_BLOCS_OPERATOIRES')
def bloc():
    user = g.user
    blocs_access = get_user_accessible_blocs(user)

    # Si aucun accès n'est défini, renvoyer un message d'erreur ou une page vide
    if not blocs_access:
        return render_template('bloc.html', title='Bloc', actes=[], user=g.user, message="Aucun accès aux blocs")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Construire la requête SQL pour inclure plusieurs blocs
    format_strings = ','.join(['%s'] * len(blocs_access))
    query = f"SELECT * FROM acte WHERE Bloc IN ({format_strings}) ORDER BY DateStart DESC"

    cursor.execute(query, tuple(blocs_access))
    actes = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('bloc.html', title='Bloc', actes=actes, user=g.user)


# Route pour gérer les vidéos par bloc
@app.route('/videos')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_BLOCS_OPERATOIRES')
def videos():
    user = g.user
    blocs_access = get_user_accessible_blocs(user)

    # Si aucun accès n'est défini, renvoyer un message d'erreur ou une page vide
    if not blocs_access:
        return render_template('videos.html', title='Videos', videos=[], user=g.user, message="Aucun accès aux blocs")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Construire la requête SQL pour inclure plusieurs blocs
    format_strings = ','.join(['%s'] * len(blocs_access))
    query = f"SELECT * FROM videos WHERE bloc IN ({format_strings}) ORDER BY date DESC"

    cursor.execute(query, tuple(blocs_access))
    videos = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('videos.html', title='Videos', videos=videos, user=g.user)


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        print('error: No file part')
        return jsonify({'error': 'No file part'}), 400

    # Récupérer le fichier depuis la requête
    file = request.files['file']

    if file.filename == '':
        print('error: No selected file')

        return jsonify({'error': 'No selected file'}), 400

    try:
        # Sauvegarde du fichier avec la fonction fournie
        saved_path = save_videos([file], 'videos')  # "videos" est le dossier cible
        if saved_path:
            print('message: File successfully uploaded')

            return jsonify({'message': 'File successfully uploaded', 'file_path': saved_path}), 200
        else:
            print('error: Failed to save file')

            return jsonify({'error': 'Failed to save file'}), 500
    except Exception as e:
        print(f'error: Failed to save file: {str(e)}')

        return jsonify({'error': f'Failed to save file: {str(e)}'}), 500

def save_videos(files, save_path):
    """ Save the uploaded files and return their paths as a comma-separated string. """
    saved_file_paths = []
    file_folder = os.path.join(app.config['UPLOAD_FOLDER'], save_path)

    # Create the directory if it doesn't exist
    os.makedirs(file_folder, exist_ok=True)

    for file in files:
        if file and allowed_file(file.filename):  # Check if the file is valid
            try:
                filename = file.filename
                file_path_full = os.path.join(file_folder, filename)

                file.save(file_path_full)  # Save the file
                saved_file_paths.append(f"{save_path}/{filename}")  # Store relative path
            except Exception as e:
                flash(f"Erreur lors de la sauvegarde du fichier {file.filename}: {str(e)}", "danger")

    return ','.join(saved_file_paths)  # Return file paths as a comma-separated string


@app.route('/live')
@login_required
@handle_errors()
@permission_required('ACCES_AUX_BLOCS_OPERATOIRES')
def live():
    user = g.user
    blocs_access = get_user_accessible_blocs(user)
    # Si aucun accès n'est défini, renvoyer un message d'erreur ou une page vide
    if not blocs_access:
        return render_template('live.html', title='Live', videos=[], user=g.user, message="Aucun accès aux blocs")
    conn = get_db_connection()
    cursor = conn.cursor()
    # Construire la requête SQL pour inclure plusieurs blocs
    format_strings = ','.join(['%s'] * len(blocs_access))
    query = f"SELECT * FROM equipements WHERE salle IN ({format_strings}) AND streaming_bloc IS TRUE"
    cursor.execute(query, tuple(blocs_access))
    lives = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('live.html', title='Live', lives=lives, user=g.user)