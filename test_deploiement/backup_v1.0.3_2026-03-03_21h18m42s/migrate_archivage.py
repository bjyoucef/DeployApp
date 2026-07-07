from app import get_db_connection, app

def migrate():
    with app.app_context():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # Check if columns exist
            cursor.execute("SHOW COLUMNS FROM archivage_dossiers LIKE 'source_module'")
            if not cursor.fetchone():
                print("Adding source_module column...")
                cursor.execute("ALTER TABLE archivage_dossiers ADD COLUMN source_module VARCHAR(50) DEFAULT NULL")
                
            cursor.execute("SHOW COLUMNS FROM archivage_dossiers LIKE 'id_source'")
            if not cursor.fetchone():
                print("Adding id_source column...")
                cursor.execute("ALTER TABLE archivage_dossiers ADD COLUMN id_source INT DEFAULT NULL")

            conn.commit()
            print("Migration successful.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
