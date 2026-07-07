from app import app
from flask import render_template, g, request, jsonify, session
from functools import wraps
import traceback
import logging
import os
from logging.handlers import RotatingFileHandler

# ================================
# CONFIGURATION DES LOGGERS
# ================================

def setup_logger(name, log_file, level=logging.ERROR):
    """Fonction pour configurer un logger spécifique."""
    
    # Créer le répertoire logs s'il n'existe pas
    log_dir = os.path.join(app.root_path, '..', 'logs') # Logs à la racine du projet
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_path = os.path.join(log_dir, log_file)
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )

    # Rotation des logs : 10 fichiers de 1MB max
    handler = RotatingFileHandler(log_path, maxBytes=1000000, backupCount=10, encoding='utf-8')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Éviter d'ajouter plusieurs handlers si le logger existe déjà
    if not logger.handlers:
        logger.addHandler(handler)

    return logger

# Création des loggers spécifiques
db_logger = setup_logger('db_logger', 'db_errors.log')
http_logger = setup_logger('http_logger', 'http_errors.log')
generic_logger = setup_logger('generic_logger', 'generic_errors.log')


from datetime import datetime

def log_error(e, error_type, details):
    """Log l'erreur dans le fichier approprié."""
    
    # Récupération des infos utilisateur
    user_info = "Anonyme"
    if g.get('user'):
        # On suppose que g.user est un dictionnaire (DictCursor)
        nom = g.user.get('nom', 'Nom Inconnu')
        uid = g.user.get('id_personnel', 'ID Inconnu')
        user_info = f"{nom} (ID: {uid})"
    
    # Récupération des infos requête
    user_agent = request.user_agent.string
    ip_address = request.remote_addr
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    log_message = (
        f"\nTimestamp: {timestamp}\n"
        f"User: {user_info}\n"
        f"IP Address: {ip_address}\n"
        f"Browser/OS: {user_agent}\n"
        f"Path: {request.path}\n"
        f"Method: {request.method}\n"
        f"Error Message: {str(e)}\n"
        f"Traceback:\n{details}\n"
        f"{'-'*80}"
    )
    
    if error_type == 'db':
        db_logger.error(log_message)
    elif error_type == 'http':
        http_logger.error(log_message)
    else:
        generic_logger.error(log_message)


def render_error(e):
    """Fonction centrale pour traiter, logger et rendre les erreurs."""
    from werkzeug.exceptions import HTTPException
    
    # Determine if it is a 404 to avoid noisy tracebacks
    is_404 = False
    if isinstance(e, HTTPException) and e.code == 404:
        is_404 = True

    if is_404:
        print(f"⚠️ 404 Not Found: {request.path}")
        error_details = "404 Not Found"
    else:
        error_details = traceback.format_exc()
        print(f"Erreur : {str(e)}\n{error_details}")

    # Déterminer le type d'erreur
    is_db_error = False
    status_code = 500
    template = 'errors/general_error.html'
    error_title = "Erreur Inattendue"
    log_type = 'generic' # Par défaut
    
    # Vérifier si c'est une erreur de base de données
    try:
        import pymysql
        import psycopg2
        if isinstance(e, (pymysql.MySQLError, psycopg2.Error)):
            is_db_error = True
            template = 'errors/db_error.html'
            error_title = "Erreur Base de Données"
            log_type = 'db'
    except ImportError:
        pass

    # Vérifier si c'est une erreur HTTP (ex: 404 venant d'un abort)
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        status_code = e.code
        error_title = e.name
        log_type = 'http'
        if status_code == 404:
            template = 'errors/404.html'
        else:
            template = 'errors/general_error.html'
    
    # === ENREGISTRER L'ERREUR DANS LES LOGS ===
    log_error(e, log_type, error_details)

    # Préparer le contexte pour le template
    context = {
        'error_message': str(e),
        'error_details': error_details,
        'error_code': status_code,
        'error_title': error_title,
        'path': request.path,
        'user': g.get('user'),
        'is_db_error': is_db_error
    }

    # Renvoi d'une page HTML personnalisée
    if request.accept_mimetypes['text/html']:
        return render_template(template, **context), status_code

    # Renvoi d'une réponse JSON en cas de requête API
    return jsonify({
        "error": error_title, 
        "message": str(e),
        "code": status_code,
        "path": request.path
    }), status_code


def handle_errors():
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                return render_error(e)
        return wrapped
    return decorator

# ================================
# GESTIONNAIRES D'ERREURS GLOBAUX
# ================================
@app.errorhandler(404)
def page_not_found(e):
    return render_error(e)

@app.errorhandler(500)
def internal_server_error(e):
    return render_error(e)

@app.errorhandler(Exception)
def unhandled_exception(e):
    return render_error(e)



def log_activity(action):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user_id = session.get('user_id', 'anonymous')
            # Logique pour enregistrer l'activité
            print(f"User {user_id} performed {action}")
            return f(*args, **kwargs)
        return wrapped
    return decorator
