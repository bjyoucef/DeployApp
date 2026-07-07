import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        cursorclass=pymysql.cursors.DictCursor
    )

def add_rule():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            endpoint = 'operations_medecin_bloc_list'
            priv_id = 2  # ACCES_AUX_CLES (From UI config)
            
            # Check existance
            cursor.execute("SELECT id FROM actes_routes_config WHERE endpoint = %s", (endpoint,))
            if cursor.fetchone():
                print(f"Rule for {endpoint} already exists.")
            else:
                print(f"Adding route protection for {endpoint} -> Privilege ID {priv_id}...")
                cursor.execute(
                    "INSERT INTO actes_routes_config (endpoint, method, id_privilege) VALUES (%s, %s, %s)",
                    (endpoint, 'ANY', priv_id)
                )
                conn.commit()
                print("Rule added successfully.")
            
            # Verify
            cursor.execute("SELECT * FROM actes_routes_config WHERE endpoint = %s", (endpoint,))
            print("Current config:", cursor.fetchone())
            
    finally:
        conn.close()

if __name__ == "__main__":
    add_rule()
