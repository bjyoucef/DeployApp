
import pymysql
from app import get_db_connection

def migrate():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        print("Checking if column 'patient_oid_his' exists in 'kt_dossier_patient'...")
        cursor.execute("DESCRIBE kt_dossier_patient")
        columns = [row['Field'] for row in cursor.fetchall()]
        
        if 'patient_oid_his' not in columns:
            print("Adding 'patient_oid_his' column...")
            cursor.execute("ALTER TABLE kt_dossier_patient ADD COLUMN patient_oid_his INT NULL")
            cursor.execute("CREATE INDEX idx_kt_dossier_patient_oid_his ON kt_dossier_patient(patient_oid_his)")
            conn.commit()
            print("Column added successfully.")
        else:
            print("Column 'patient_oid_his' already exists.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
