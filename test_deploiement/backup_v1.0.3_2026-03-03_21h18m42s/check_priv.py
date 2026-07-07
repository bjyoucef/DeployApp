import pymysql
import os
from dotenv import load_dotenv
import json

load_dotenv()

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        cursorclass=pymysql.cursors.DictCursor
    )

def check():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            print("--- UI Config ---")
            cursor.execute("SELECT auc.*, p.nom_privilege FROM actes_ui_config auc JOIN privileges p ON auc.id_privilege = p.id_privilege")
            for row in cursor.fetchall():
                print(row)
                
            print("\n--- Route Config ---")
            cursor.execute("SELECT arc.*, p.nom_privilege FROM actes_routes_config arc JOIN privileges p ON arc.id_privilege = p.id_privilege")
            for row in cursor.fetchall():
                print(row)
    finally:
        conn.close()

if __name__ == "__main__":
    check()
