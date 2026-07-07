from flask import render_template, request, redirect, g, url_for

from app import app, get_db_connection
from app.error import handle_errors
from app.utiles import save_audio, save_files, login_required, has_permission


@app.route('/demande_assistance')
def demande_assistance():
    return render_template('demande_assistance.html', title="Assistance", user=g.user)

def traiter_demande(demande_type):
    """Traite une demande d'assistance avec ou sans fichiers/audio."""
    ip_address = request.remote_addr

    # Récupération des données de la demande
    name = request.form.get('name')
    demande_details = request.form.get('demande_details')
    audio_data = request.form.get('audioData')  # Données audio
    files = request.files.getlist('file_upload')  # Liste des fichiers

    # Vérification des champs obligatoires
    if not name or not demande_details:
        return redirect(
            url_for('demande_assistance', message="Tous les champs obligatoires doivent être remplis.",
                    category="danger")
        )

    # Sauvegarde des fichiers (si présents)
    file_paths_str = None
    if files and any(f.filename for f in files):  # Vérifie si des fichiers sont réellement téléchargés
        file_paths_str = save_files(files, f'files/{demande_type}')
        if not file_paths_str:
            return redirect(
                url_for('demande_assistance', message="Erreur lors de la sauvegarde des fichiers.", category="danger")
            )

    # Sauvegarde des données audio (si présentes)
    audio_path = None
    if audio_data:
        audio_path = save_audio(audio_data, f'audios/demande/{demande_type}')
        if not audio_path:
            return redirect(
                url_for('demande_assistance', message="Erreur lors de la sauvegarde de l'enregistrement audio.",
                        category="danger")
            )

    # Insertion des données dans la base de données
    try:
        connection =get_db_connection() # Utiliser un context manager pour gérer la connexion à la base de données
        cursor = connection.cursor()
        cursor.execute('''INSERT INTO demandes
                          (ip_address, name, type, details, file_path, audio_path)
                          VALUES (%s, %s, %s, %s, %s, %s)''', (
            ip_address,
            name,
            demande_type,
            demande_details,
            file_paths_str,
            audio_path
        ))
        connection.commit()  # Sauvegarder les changements dans la base de données
    except Exception as e:
        # Gestion des erreurs d'insertion en base de données
        return redirect(
            url_for('demande_assistance', message=f"Erreur lors de l'enregistrement de la demande : {e}",
                    category="danger")
        )

    # Retourner une confirmation en cas de succès
    return redirect(
        url_for('demande_assistance', message="Demande envoyée avec succès!", category="success")
    )


# Routes spécifiques utilisant la fonction générique
@app.route('/envoyer_demandeIt', methods=['POST'])
def envoyer_demandeIt():
    return traiter_demande('it')


@app.route('/envoyer_demandeTech', methods=['POST'])
def envoyer_demandeTech():
    return traiter_demande('tech')


@app.route('/envoyer_demandeAppro', methods=['POST'])
def envoyer_demandeAppro():
    return traiter_demande('appro')


@app.route('/dashboard')
@login_required
@handle_errors()
def dashboard():
    user = g.user
    id_personnel = user['id_personnel']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Requête de base pour récupérer les demandes
    query_base = """
        SELECT * FROM demandes
    """

    query_conditions = []
    query_params = []

    # Conditions basées sur les permissions utilisateur
    if has_permission('ACCES_AU_DEPARTEMENT_IT'):
        query_conditions.append("type = %s")
        query_params.append("it")

    if has_permission('ACCES_AU_DEPARTEMENT_TECHNIQUE'):
        query_conditions.append("type = %s")
        query_params.append("tech")

    if has_permission('ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'):
        query_conditions.append("type = %s")
        query_params.append("appro")

    # Si aucune permission n'est définie, filtrer par nom d'utilisateur

    query_conditions.append("name = %s")
    query_params.append(id_personnel)

    # Générer le WHERE clause
    query_where_clause = f"WHERE {' OR '.join(query_conditions)}"

    # Construire la requête complète
    final_query = f"""
        {query_base}
        {query_where_clause}
        ORDER BY time_send DESC
    """

    try:
        cursor.execute(final_query, query_params)
        demandesDb = cursor.fetchall()
    except Exception as e:
        print(f"Erreur lors de l'exécution de la requête : {e}")
        demandesDb = []
    finally:
        conn.close()

    return render_template(
        'dashboard.html',
        demandes=demandesDb,
        title="Liste des demandes",
        user=user
    )


@app.route('/mark_terminee/<int:demande_id>', methods=['POST'])
@login_required
@handle_errors()
def mark_terminee(demande_id):
    user = g.user
    user_name = user['username']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE Demandes SET
        time_terminee = CURRENT_TIMESTAMP,
        terminee_par = %s
        WHERE id = %s
    ''', (user_name, demande_id))
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard', message="La demande a été conclue avec succès.!", category="success"))
