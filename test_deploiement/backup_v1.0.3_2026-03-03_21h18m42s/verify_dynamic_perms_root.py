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

def check():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM actes_routes_config WHERE endpoint = 'decharges'")
            res = cursor.fetchone()
            if res:
                print(f"Rule found for 'decharges': {res}")
            else:
                print("No rule found for 'decharges'.")
    finally:
        conn.close()

if __name__ == "__main__":
    check()
