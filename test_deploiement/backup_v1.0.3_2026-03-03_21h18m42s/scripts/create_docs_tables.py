import sys
import os

# Ensure app is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import get_db_connection

def create_docs_tables():
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database.")
        sys.exit(1)

    cursor = conn.cursor()
    try:
        # Create documentation table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documentation (
                id_doc INT(11) NOT NULL AUTO_INCREMENT,
                titre VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
                content LONGTEXT NOT NULL COLLATE 'utf8mb4_general_ci',
                created_at DATETIME NULL DEFAULT current_timestamp(),
                updated_at DATETIME NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
                created_by INT(11) NULL DEFAULT NULL,
                updated_by INT(11) NULL DEFAULT NULL,
                PRIMARY KEY (id_doc) USING BTREE,
                INDEX created_by (created_by) USING BTREE,
                INDEX updated_by (updated_by) USING BTREE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')

        # Create documentation_routes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documentation_routes (
                id_doc INT(11) NOT NULL,
                page_route VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
                PRIMARY KEY (id_doc, page_route) USING BTREE,
                INDEX page_route (page_route) USING BTREE,
                CONSTRAINT fk_doc_routes_doc FOREIGN KEY (id_doc) REFERENCES documentation (id_doc) ON UPDATE CASCADE ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')

        conn.commit()
        print("Documentation tables created successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error creating tables: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    create_docs_tables()
