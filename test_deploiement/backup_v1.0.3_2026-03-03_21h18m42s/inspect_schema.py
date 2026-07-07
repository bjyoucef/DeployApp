
from app import app, get_db_connection
from pprint import pprint

with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Use standard SQL for MariaDB/MySQL
    cursor.execute("SHOW COLUMNS FROM personnel")
    columns = cursor.fetchall()
    print(f"Total columns: {len(columns)}")
    for col in columns:
        print(f"Field: {col['Field']}, Type: {col['Type']}")
    conn.close()
