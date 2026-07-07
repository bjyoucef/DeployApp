import base64
import locale
import os
import uuid
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

import unicodedata
from flask import send_from_directory, flash, redirect, url_for, session
from werkzeug.utils import secure_filename

from app import app
from app.error import handle_errors

def has_permission(privilege_name):
    return privilege_name in session.get('privileges', [])

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(
                url_for('index', message="Vous devez être connecté pour accéder à cette page", category="danger"))
        return f(*args, **kwargs)

    return decorated_function


def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not has_permission(permission):
                return redirect_with_message('index', 'Accès refusé : privilège insuffisant.', 'danger')
            return f(*args, **kwargs)

        return wrapped

    return decorator

# Extensions de fichiers autorisées
ALLOWED_EXTENSIONS = {
    # Images
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'svg', 'webp',
    # Documents
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'csv', 'rtf', 'odt', 'ods', 'odp', 'md',
    # Vidéos
    'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'mpeg', 'mpg', '3gp',
    # Audio
    'mp3', 'wav', 'aac', 'flac', 'ogg', 'wma', 'm4a',
    # Archives
    'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'iso',
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_unique_filename(filename):
    # Générer un identifiant unique
    unique_id = str(uuid.uuid4()).replace("-", "")  # Retirer les tirets pour raccourcir l'ID
    unique_id = unique_id[:10]  # Limiter à 10 caractères
    # Obtenir l'extension
    _, extension = os.path.splitext(filename)
    return f"{unique_id}{extension}"

@app.route('/uploads/<path:filename>')
@login_required
@handle_errors()
def download_file(filename):
    uploads_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    try:
        return send_from_directory(uploads_path, filename)
    except FileNotFoundError:
        # Ajout d'un message d'erreur pour le débogage
        return f"Le fichier {filename} n'a pas été trouvé.", 404

def save_files(files, save_path):
    """ Save the uploaded files and return their paths as a comma-separated string. """
    saved_file_paths = []
    file_folder = os.path.join(app.config['UPLOAD_FOLDER'], save_path)

    # Create the directory if it doesn't exist
    os.makedirs(file_folder, exist_ok=True)

    for file in files:
        if file and allowed_file(file.filename):  # Check if the file is valid
            try:
                unique_filename = get_unique_filename(secure_filename(file.filename))
                file_path_full = os.path.join(file_folder, unique_filename)

                file.save(file_path_full)  # Save the file
                saved_file_paths.append(f"{save_path}/{unique_filename}")  # Store relative path
            except Exception as e:
                flash(f"Erreur lors de la sauvegarde du fichier {file.filename}: {str(e)}", "danger")

    return ','.join(saved_file_paths)  # Return file paths as a comma-separated string

def save_audio(audio_data, save_path):
    """ Save audio data and return its file path, or None on failure. """
    if not audio_data:
        return None
    """ Save the audio data and return its relative path. """
    unique_audio_filename = get_unique_filename("_audio.wav")
    audio_folder = os.path.join(app.config['UPLOAD_FOLDER'], save_path)
    os.makedirs(audio_folder, exist_ok=True)

    # Store the relative path using forward slashes
    audio_path = f'{save_path}/{unique_audio_filename}'  # Use forward slashes
    audio_path_full = os.path.join(app.config['UPLOAD_FOLDER'], audio_path)

    audio_data = audio_data.split(',')[1]
    decoded_audio = base64.b64decode(audio_data)

    with open(audio_path_full, 'wb') as audio_file:
        audio_file.write(decoded_audio)

    return audio_path  # Return relative path

def redirect_with_message(endpoint, message, category, **kwargs):
    """Redirige avec un message de retour."""
    query_params = urlencode({'message': message, 'category': category})
    return redirect(url_for(endpoint, **kwargs) + '?' + query_params)

# Fonction pour nettoyer le texte : remplacer les espaces par des underscores et les accents par des lettres sans accent
def nettoyer_texte(texte):
    # Normaliser le texte pour supprimer les accents
    texte_sans_accents = unicodedata.normalize('NFKD', texte).encode('ASCII', 'ignore').decode('ASCII')
    # Remplacer les espaces par des underscores
    texte_clean = texte_sans_accents.replace(' ', '_')
    return texte_clean

def format_price(price):
    try:
        # Set to the user's default locale
        locale.setlocale(locale.LC_ALL, '')  # Automatically uses the default locale
    except locale.Error:
        # If there's an error setting the locale, use 'en_US.UTF-8' as fallback
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

    # Si le prix est un nombre (int, float, Decimal), le convertir en chaîne
    if isinstance(price, (int, float, Decimal)):
        price = str(price)  # Convertir en chaîne de caractères

    # Normaliser le prix pour s'assurer que l'on enlève les espaces et remplace les virgules par un point
    normalized_price = price.replace(' ', '').replace(',', '.')

    try:
        price_float = float(normalized_price)  # Convertir en float
        # Formater le prix selon la locale de l'utilisateur (avec 2 décimales et séparation des milliers)
        return locale.format_string("%.2f", price_float, grouping=True)
    except ValueError:
        return "Invalid price format"

# Ajouter le filtre à Jinja2
app.jinja_env.filters['format_price'] = format_price