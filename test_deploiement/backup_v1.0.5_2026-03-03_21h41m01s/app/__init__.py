import logging

import pymysql
from flask import Flask
from pymysql import cursors

from config.config import Config

# Initialize the app
app = Flask(__name__)
app.config.from_object(Config)
# Définir une limite pour la taille des fichiers (par exemple, 50 Mo)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

logging.basicConfig(filename='log.log', level=logging.DEBUG)


# Database connection
def get_db_connection():
    try:
        connection = pymysql.connect(
            host=app.config['DB_HOST'],
            user=app.config['DB_USER'],
            password=app.config['DB_PASSWORD'],
            database=app.config['DB_NAME'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
            # Utiliser DictCursor pour retourner les résultats sous forme de dictionnaire
        )
        return connection

    except pymysql.MySQLError as e:
        print(f"Error connecting to the database: {e}")  # Afficher une erreur si la connexion échoue
        return None


def get_menu_items():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM menu_items")
    menu_items = cursor.fetchall()

    return menu_items


@app.context_processor
def inject_menu_items():
    menu_items = get_menu_items()
    return {'menu_items': menu_items}


@app.context_processor
def inject_permissions():
    from app.utiles import has_permission
    return {'has_permission': has_permission}


from app import (auth,
                 routes,
                 report,
                 phone,
                 demande,
                 personnel,
                 keys,
                 bloc,
                 stock,
                 it_events,
                 equipment,
                 utiles,
                 pointage,
                 planning,
                 service,
                 salaire,
                 gestion_roles_privileges,
                 decharge_paiment,
                 situation_medecin,
                 dossier_patient,
                 kt_dossier_patient,
                 kt_situation_medecin,
                 kt_actes,
                 kt_programme,
                 forfaits,
                 actes,
                 produits,
                 kt_stat,
                 kt_facturation)
