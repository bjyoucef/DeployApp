from app import get_db_connection, app

def migrate():
    with app.app_context():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Create the new table
            print("Creating archivage_rayonnage_specialites table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS archivage_rayonnage_specialites (
                    id_rayonnage INT NOT NULL,
                    id_specialty INT NOT NULL,
                    PRIMARY KEY (id_rayonnage, id_specialty),
                    FOREIGN KEY (id_rayonnage) REFERENCES archivage_rayonnages(id) ON DELETE CASCADE,
                    FOREIGN KEY (id_specialty) REFERENCES specialty(id_specialty) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
            """)
            
            # 2. Migrate existing data from archivage_rayonnages
            print("Migrating existing specialties...")
            # Use REPLACE INTO or IGNORE to avoid duplicate key errors on rerun
            cursor.execute("""
                INSERT IGNORE INTO archivage_rayonnage_specialites (id_rayonnage, id_specialty)
                SELECT id, id_specialty 
                FROM archivage_rayonnages 
                WHERE id_specialty IS NOT NULL
            """)
            
            conn.commit()
            print("Migration successful.")
        except Exception as e:
            conn.rollback()
            print(f"Error during migration: {e}")
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
