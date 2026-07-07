import os
from decimal import Decimal  # 👈 Ajouter cet import
from flask import g, session
import pymysql
from flask import Flask
from datetime import timedelta, datetime, date
from config.config import Config
import psycopg2


# Initialize the app
app = Flask( __name__ )
app.config.from_object( Config )
# Définir une limite pour la taille des fichiers (par exemple, 50 Mo)
app.config[ 'MAX_CONTENT_LENGTH' ] = 50 * 1024 * 1024  # 50 MB
app.config['BASE_URL'] = os.getenv('IP_ADDRESS')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
# logging.basicConfig( filename = 'log.log', level = logging.DEBUG )
# ✅ VALIDER LES VARIABLES D'ENVIRONNEMENT
try:
    Config.validate()
except ValueError as e:
    print(f"\n{'='*60}")
    print(e)
    print(f"{'='*60}\n")
    exit(1)
@app.template_filter( 'format_time' )
def format_time_filter( value ):
    """Convertit un timedelta ou time en format HH:MM"""
    if value is None:
        return ''

    # Si c'est déjà une string
    if isinstance( value, str ):
        return value

    # Si c'est un timedelta (retourné par MySQL pour les champs TIME)
    if isinstance( value, timedelta ):
        total_seconds = int( value.total_seconds() )
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"

    # Si c'est un objet time
    if hasattr( value, 'strftime' ):
        return value.strftime( '%H:%M' )

    return str( value )


@app.template_filter( 'format_date' )
def format_date_filter( value ):
    """Convertit une date en format YYYY-MM-DD pour input type="date" """
    if value is None:
        return ''

    # Si c'est déjà une string
    if isinstance( value, str ):
        return value

    # Si c'est un objet date ou datetime
    if hasattr( value, 'strftime' ):
        return value.strftime( '%Y-%m-%d' )

    return str( value )


def get_user_by_id(user_id):
    cursor = get_db_connection().cursor()
    cursor.execute(
        "SELECT * FROM personnel WHERE id_personnel = %s",
        (user_id,)
    )
    user = cursor.fetchone()
    cursor.close()
    return user

# ==============================
# Charger l'utilisateur
# ==============================
@app.before_request
def load_user():
    if 'user_id' in session:
        g.user = get_user_by_id( session[ 'user_id' ] )
    else:
        g.user = None


# ==============================
# Injecter user dans tous les templates
# ==============================
@app.context_processor
def inject_user():
    return {'user': g.user}

# Database connection
def get_db_connection():
    try:
        connection = pymysql.connect(
                host = app.config[ 'DB_HOST' ],
                user = app.config[ 'DB_USER' ],
                password = app.config[ 'DB_PASSWORD' ],
                database = app.config[ 'DB_NAME' ],
                charset = 'utf8mb4',
                cursorclass = pymysql.cursors.DictCursor
                # Utiliser DictCursor pour retourner les résultats sous forme de dictionnaire
                )
        return connection

    except pymysql.MySQLError as e:
        print( f"Error connecting to the database: {e}" )  # Afficher une erreur si la connexion échoue
        return None



def get_pg_connection():
    conn = psycopg2.connect(
        host=app.config['PG_HOST'],
        port=app.config['PG_PORT'],
        database=app.config['PG_DB'],
        user=app.config['PG_USER'],
        password=app.config['PG_PASSWORD'],
        options=app.config['PG_OPTIONS']
    )

    # Sécurité supplémentaire
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;")
    cur.close()

    return conn



def safe_pg_execute(cursor, query, params=None):
    """
    Exécute une requête PostgreSQL en mode lecture seule.
    Autorise uniquement SELECT, WITH (pour les CTE), et SHOW.
    """
    import re

    # Nettoyer la requête
    clean_query = query.strip()

    # Enlever les commentaires
    # Enlever les commentaires de ligne --
    clean_query = re.sub( r'--[^\n]*', '', clean_query )
    # Enlever les commentaires de bloc /* */
    clean_query = re.sub( r'/\*.*?\*/', '', clean_query, flags = re.DOTALL )

    # Nettoyer les espaces
    clean_query = clean_query.strip().lower()

    # Récupérer le premier mot-clé SQL
    first_word = clean_query.split()[ 0 ] if clean_query else ""

    # Liste blanche : opérations de lecture autorisées
    read_operations = { 'select', 'with', 'show', 'explain', 'describe', 'desc' }

    # Si ce n'est pas une opération de lecture, bloquer
    if first_word not in read_operations:
        raise PermissionError(
                f"⛔ PostgreSQL HIS en lecture seule - '{first_word.upper()}' non autorisé"
                )

    # Exécuter la requête
    cursor.execute(query, params)

def get_index_menu_items():
    """Récupère les items de menu à afficher sur la page d'accueil depuis les deux tables"""
    connection = get_db_connection()
    if connection is None:
        return []

    cursor = connection.cursor()

    try:
        # Récupérer depuis menu_items
        cursor.execute("""
            SELECT route, label, icon, privilege, tooltip, 'menu_items' as source
            FROM menu_items 
            WHERE dans_index = 1
            ORDER BY privilege
        """)
        items_from_menu = cursor.fetchall()

        # Récupérer depuis menu_items_admin
        cursor.execute("""
            SELECT route, label, icon, privilege, tooltip, 'menu_items_admin' as source
            FROM menu_items_admin 
            WHERE dans_index = 1
            ORDER BY privilege
        """)
        items_from_admin = cursor.fetchall()

        # Combiner les deux listes
        all_items = items_from_menu + items_from_admin

    except pymysql.MySQLError as e:
        print(f"Erreur lors de la récupération des items d'index: {e}")
        all_items = []
    finally:
        cursor.close()
        connection.close()

    return all_items


@app.context_processor
def inject_index_menu_items():
    """Injecte les items de menu pour la page d'accueil dans tous les templates"""
    if 'user_id' in session:
        index_items = get_index_menu_items()
        return { 'index_menu_items': index_items }
    return { 'index_menu_items': [ ] }

def get_menu_items():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Charger tous les éléments du menu ordonnés par parent_id (NULL en premier) puis par order
    cursor.execute("""
        SELECT * FROM menu_items 
        ORDER BY 
            CASE WHEN parent_id IS NULL THEN 0 ELSE 1 END,
            parent_id,
            `order`,
            id
    """)
    menu_items = cursor.fetchall()

    cursor.close()
    connection.close()

    return menu_items


@app.context_processor
def inject_menu_items():
    # Ne charger le menu que si l'utilisateur est connecté
    if 'user_id' in session:
        menu_items = get_menu_items()
        return { 'menu_items': menu_items }
    return {'menu_items': []}

def get_menu_items_admin():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute( "SELECT * FROM menu_items_admin" )
    menu_items_admin = cursor.fetchall()

    cursor.close()
    connection.close()

    return menu_items_admin


@app.context_processor
def inject_menu_items_admin():
    menu_items_admin = get_menu_items_admin()
    return { 'menu_items_admin': menu_items_admin }


@app.context_processor
def inject_permissions():
    from app.utils.utiles import has_permission
    from app.dynamic_permissions import permission_service
    from flask import request

    # Récupérer la route courante (sans le slash initial parfois)
    current_endpoint = request.endpoint 
    # Ou utiliser request.path, mais route est mieux pour mapping
    # Le service attend 'page_route' qui est souvent le endpoint name ou path relative
    # Pour simplifier, on passe le endpoint name (ex: 'manage_employees')
    
    ui_perms = []
    if current_endpoint:
        ui_perms = permission_service.get_ui_permissions(current_endpoint)
        # Fallback: essayer avec request.path strip '/'
        if not ui_perms:
             path_key = request.path.strip('/')
             ui_perms = permission_service.get_ui_permissions(path_key)

    # Récupérer la map des routes protégées (URL -> Privilege)
    protected_urls = permission_service.get_protected_routes_url_map()

    return { 
        'has_permission': has_permission,
        'dynamic_ui_permissions': ui_perms,
        'protected_routes_map': protected_urls
    }


@app.template_filter( 'safe_tojson' )
def safe_tojson_filter( value ):
    """Convertit en JSON en remplaçant les None par des valeurs par défaut et les Decimal en float"""
    import json

    def clean_value( obj ):
        if obj is None:
            return ''
        elif isinstance( obj, Decimal ):  # 👈 AJOUT : Gérer les Decimal
            return float( obj )
        elif isinstance( obj, (datetime, date) ):
            return obj.isoformat()
        elif isinstance( obj, timedelta ):
            return str( obj )
        elif isinstance( obj, dict ):
            return { k: clean_value( v ) for k, v in obj.items() }
        elif isinstance( obj, list ):
            return [ clean_value( item ) for item in obj ]
        else:
            return obj


    cleaned_value = clean_value( value )
    return json.dumps(
            cleaned_value, ensure_ascii = False
            )  # 👈 Ajouter ensure_ascii=False pour les caractères français


import json


def escapejs_fallback( s ):
    return json.dumps( str( s ) )

from datetime import datetime
app.jinja_env.globals['datetime'] = datetime

app.jinja_env.filters[ 'escapejs' ] = escapejs_fallback

# Enregistrer le filtre
app.jinja_env.filters[ 'safe_tojson' ] = safe_tojson_filter
app.jinja_env.globals.update(
        {
                'abs': abs, 'min': min, 'max': max, 'round': round, 'len': len,
                }
        )
from app import (
    auth, routes, report, phone, demande, personnel, keys, bloc, stock, it_events, equipment, pointage,
    planning, service, salaire, decharge_paiment, actes, stats_utilisateur, bot_logs, bot_whitelist,
    user_settings
    )
from app.utils import utiles
from app.facturation import facturation,config_clinique_tva
from app.his import his_direct
from app.prestation_location_bloc import location_bloc, situation_medecin, export_location
from app.admin import (
    bloc_admin,
    forfaits,
    actes_admin,
    gestion_roles_privileges,
    produits,
    manage_type_chambre)
from app.gestion_medecins import admin_custom_pricing, manage_doctors
from app.prestation_kt import kt_programme, kt_dossier_patient, kt_actes, kt_situation_medecin, kt_facturation, kt_stat, kt_decharges, kt_conventions
from app.anesthesie_honoraires import anesthesie_honoraires, anesthesie_decharges, config_anesthesie
from app.accouchements import accouchements, situations_gyneco_interne, situation_accouchement_externe, bons_paiement, gyneco_interne_paiements
from app.medecins_internes import situations_internes_helpers, medecins_internes, medecin_interne_paiements_patient, situation_medecin_interne, medecin_interne_decharges
from app.barcode_label import routes
from app.archivage import routes, qr_routes
from app import documentation
from app.hospitalisation import routes as hospitalisation_routes

# Enregistrement des routes Dynamic Permissions (Direct via import)
from app.api_dynamic_permissions import *

# Chargement de la configuration initiale des permissions
from app.dynamic_permissions import permission_service
with app.app_context():
    try:
        permission_service.load_configurations()
        print("Dynamic Permissions loaded.")
    except Exception as e:
        print(f"Warning: Failed to load dynamic permissions: {e}")

# ==========================================
# GESTION DES PERMISSIONS DYNAMIQUES (BACKEND)
# ==========================================
@app.before_request
def check_dynamic_permissions():
    """
    Intercepte chaque requête pour vérifier si l'endpoint est protégé dynamiquement via actes_routes_config.
    """
    # 1. Ignorer les routes statiques et publiques
    if not request.endpoint or request.endpoint == 'static' or 'login' in request.endpoint:
        return

    # 2. Récupérer la permission requise pour (endpoint, method)
    # L'endpoint est le nom de la fonction Flask (ex: 'operations_medecin_bloc_list')
    try:
        privilege = permission_service.get_route_privilege(request.endpoint, request.method)
        
        if privilege:
            # 3. Vérifier si l'utilisateur a cette permission
            from app.utils.utiles import has_permission
            from flask import abort, jsonify, session, redirect, url_for, flash
            
            if not has_permission(privilege):
                # Vérifier si l'utilisateur est connecté
                if 'user_id' not in session:
                    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({
                            'error': 'Unauthorized', 
                            'message': 'Vous devez être connecté pour accéder à cette ressource',
                            'redirect': url_for('index')
                        }), 401
                    flash("Votre session a expiré ou vous n'êtes pas connecté.", "warning")
                    return redirect(url_for('index'))

                # Réponse JSON pour AJAX (connecté mais sans privilège)
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'error': 'Forbidden', 
                        'message': f'Permission manquante : {privilege}'
                    }), 403
                
                # Réponse HTML standard (connecté mais sans privilège)
                abort(403, description=f"Accès refusé. Vous n'avez pas le privilège requis : {privilege}")

    except Exception as e:
        print(f"Erreur check_dynamic_permissions: {e}")

print("************************************************")
print( 'PG:', 'OK' if get_pg_connection() else 'ERREUR' , 'Santymed' if app.config[ 'PG_HOST' ] == "192.168.10.152" else 'Local')
print( 'Maria:', 'OK' if get_db_connection() else 'ERREUR', 'SIC' if app.config[ 'DB_HOST' ] == "192.168.10.9" else 'Local' )
print("************************************************")
