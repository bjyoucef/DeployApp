
import pymysql
from app import get_db_connection

def inspect_content():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = ['medecin_interne_actes', 'location_bloc_dossier_patient']
    
    for table in tables:
        print(f"\n--- {table} (First 3 rows) ---")
        try:
            cursor.execute(f"SELECT * FROM {table} LIMIT 3")
            rows = cursor.fetchall()
            for row in rows:
                # Print only relevant columns to avoid clutter
                relevant = {k: v for k, v in row.items() if 'patient' in k or 'oid' in k or 'id' in k}
                print(relevant)
        except Exception as e:
            print(f"Error: {e}")
            
    conn.close()

if __name__ == "__main__":
    inspect_content()
