
from app import app, get_db_connection
import pymysql

def add_columns():
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if columns exist
            cursor.execute("SHOW COLUMNS FROM personnel LIKE 'last_login'")
            if not cursor.fetchone():
                print("Adding last_login column...")
                cursor.execute("ALTER TABLE personnel ADD COLUMN last_login DATETIME NULL DEFAULT NULL")
            else:
                print("last_login column already exists.")

            cursor.execute("SHOW COLUMNS FROM personnel LIKE 'last_activity'")
            if not cursor.fetchone():
                print("Adding last_activity column...")
                cursor.execute("ALTER TABLE personnel ADD COLUMN last_activity DATETIME NULL DEFAULT NULL")
            else:
                print("last_activity column already exists.")
                
            conn.commit()
            print("Database migration completed successfully.")
            
        except Exception as e:
            print(f"Error during migration: {e}")
            conn.rollback()
        finally:
            conn.close()

if __name__ == "__main__":
    add_columns()
