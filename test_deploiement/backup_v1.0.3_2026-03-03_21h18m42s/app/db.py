import csv
import os

import pymysql

from app import get_db_connection


def create_tables():
    conn = get_db_connection()
    if conn is None:
        return

    cursor = conn.cursor()

    try:
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Demandes (
        `id` INT(11) NOT NULL AUTO_INCREMENT,
        `ip_address` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        `name` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        `type` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        `details` TEXT NOT NULL COLLATE 'utf8mb4_general_ci',
        `time_send` DATETIME NULL DEFAULT current_timestamp(),
        `terminee` TINYINT(1) NULL DEFAULT '0',
        `time_terminee` DATETIME NULL DEFAULT NULL,
        `terminee_par` VARCHAR(255) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        `file_path` VARCHAR(255) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        PRIMARY KEY (`id`) USING BTREE,
        UNIQUE INDEX `id` (`id`) USING BTREE
    )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
        `id` INT(11) NOT NULL AUTO_INCREMENT,
        `nom` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        `etage` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        `numero` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        PRIMARY KEY (`id`) USING BTREE,
        UNIQUE INDEX `id` (`id`) USING BTREE,
        UNIQUE INDEX `numero` (`numero`) USING BTREE
    )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock (
        `id` INT(11) NOT NULL AUTO_INCREMENT,
        `user_id` INT(11) NOT NULL,
        `item` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        `category` VARCHAR(255) NOT NULL COLLATE 'utf8mb4_general_ci',
        `quantity` INT(11) NOT NULL,
        `description` TEXT NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        `type` VARCHAR(255) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        PRIMARY KEY (`id`) USING BTREE,
        UNIQUE INDEX `id` (`id`) USING BTREE,
        INDEX `users_fk` (`user_id`) USING BTREE
    )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movements_stock (
        `id` INT(11) NOT NULL AUTO_INCREMENT,
        `product_id` INT(11) NULL DEFAULT NULL,
        `user_id` INT(11) NULL DEFAULT NULL,
        `movement_type` VARCHAR(255) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        `quantity` INT(11) NULL DEFAULT NULL,
        `supplier` VARCHAR(255) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        `person` VARCHAR(255) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        `service` VARCHAR(255) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        `date` DATE NOT NULL,
        `stock_type` VARCHAR(50) NULL DEFAULT NULL COLLATE 'utf8mb4_general_ci',
        PRIMARY KEY (`id`) USING BTREE,
        UNIQUE INDEX `id` (`id`) USING BTREE,
        INDEX `product_id` (`product_id`) USING BTREE,
        INDEX `users_ibfk` (`user_id`) USING BTREE,
        CONSTRAINT `movements_stock_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `stock` (`id`) ON UPDATE RESTRICT ON DELETE RESTRICT
    )
        ''')
        
        # Insert default admin user if none exists
        cursor.execute('''
            INSERT INTO personnel (username, password)
            SELECT 'admin', %s, TRUE
            WHERE NOT EXISTS (SELECT 1 FROM personnel WHERE username = 'admin')
        ''', ('admin',))

        conn.commit()
        # Importation des données CSV après la création des tables
        import_csv(cursor)

        conn.commit()  # Valider l'importation
    except pymysql.MySQLError as e:
        conn.rollback()  # Annuler les modifications en cas d'erreur
    finally:
        conn.close()


def import_csv(cursor):
    csv_file = 'DB/contacts.csv'

    # Vérifier si le fichier CSV existe
    if os.path.exists(csv_file):
        try:
            with open(csv_file, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file, delimiter=';')

                for row in reader:
                    # Vérifier si le numéro existe déjà pour éviter les doublons
                    cursor.execute("SELECT * FROM contacts WHERE numero = %s", (row['numero'],))
                    existing_contact = cursor.fetchone()

                    if not existing_contact:
                        # Insérer les nouvelles données dans la table contacts
                        cursor.execute('''
                            INSERT INTO contacts (nom, numero)
                            VALUES (%s, %s, %s)
                        ''', (row['nom'], row['etage'], row['numero']))
        except Exception as e:
            print(f"Erreur lors de l'importation du fichier CSV : {e}")
    else:
        print(f"Le fichier CSV '{csv_file}' n'existe pas.")
