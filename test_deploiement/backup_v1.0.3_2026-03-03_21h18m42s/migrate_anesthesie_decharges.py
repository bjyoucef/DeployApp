"""
Migration: Create anesthesie discharge tables and alter existing act tables.
"""
from app import app, get_db_connection

SQL_STATEMENTS = [
    # 1. Main decharges table
    """
    CREATE TABLE IF NOT EXISTS anesthesie_decharges (
        id_decharge INT AUTO_INCREMENT PRIMARY KEY,
        numero_decharge VARCHAR(30) NOT NULL UNIQUE,
        id_personnel_anesthesie INT NOT NULL,
        date_decharge DATE NOT NULL,
        periode_debut DATE NULL,
        periode_fin DATE NULL,
        montant_total DECIMAL(12,2) NOT NULL DEFAULT 0,
        montant_paye_total DECIMAL(12,2) NOT NULL DEFAULT 0,
        solde_restant DECIMAL(12,2) NOT NULL DEFAULT 0,
        nb_actes INT NOT NULL DEFAULT 0,
        nb_tranches INT NOT NULL DEFAULT 0,
        mode_paiement VARCHAR(30) DEFAULT 'ESPECES',
        reference_paiement VARCHAR(100) NULL,
        observations TEXT NULL,
        statut ENUM('BROUILLON','VALIDE','PAIEMENT_PARTIEL','PAYE','ANNULE') DEFAULT 'BROUILLON',
        created_by INT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        validated_at DATETIME NULL,
        validated_by INT NULL,
        paid_at DATETIME NULL,
        paid_by INT NULL,
        est_annule TINYINT(1) DEFAULT 0,
        annule_par INT NULL,
        annule_le DATETIME NULL,
        motif_annulation TEXT NULL,
        FOREIGN KEY (id_personnel_anesthesie) REFERENCES anesthesie_personnel(id_personnel_anesthesie),
        FOREIGN KEY (created_by) REFERENCES personnel(id_personnel),
        FOREIGN KEY (validated_by) REFERENCES personnel(id_personnel),
        FOREIGN KEY (paid_by) REFERENCES personnel(id_personnel),
        FOREIGN KEY (annule_par) REFERENCES personnel(id_personnel)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 2. Junction table: decharge <-> actes from multiple sources
    """
    CREATE TABLE IF NOT EXISTS anesthesie_decharge_actes (
        id_decharge INT NOT NULL,
        source_acte ENUM('BLOC','ACCOUCHEMENT','KT','MEDECIN_INTERNE') NOT NULL,
        id_acte_source INT NOT NULL,
        montant_honoraires DECIMAL(12,2) NOT NULL DEFAULT 0,
        PRIMARY KEY (id_decharge, source_acte, id_acte_source),
        FOREIGN KEY (id_decharge) REFERENCES anesthesie_decharges(id_decharge)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 3. Tranches (installments) table
    """
    CREATE TABLE IF NOT EXISTS anesthesie_decharge_tranches (
        id_tranche INT AUTO_INCREMENT PRIMARY KEY,
        id_decharge INT NOT NULL,
        numero_tranche VARCHAR(40) NOT NULL,
        date_paiement DATE NOT NULL,
        montant_paye DECIMAL(12,2) NOT NULL DEFAULT 0,
        mode_paiement VARCHAR(30) DEFAULT 'ESPECES',
        reference_paiement VARCHAR(100) NULL,
        observations TEXT NULL,
        created_by INT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        est_annule TINYINT(1) DEFAULT 0,
        annule_par INT NULL,
        annule_le DATETIME NULL,
        motif_annulation TEXT NULL,
        FOREIGN KEY (id_decharge) REFERENCES anesthesie_decharges(id_decharge),
        FOREIGN KEY (created_by) REFERENCES personnel(id_personnel),
        FOREIGN KEY (annule_par) REFERENCES personnel(id_personnel)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,

    # 4. Alter existing act tables
    "ALTER TABLE location_bloc_dossier_anesthesie ADD COLUMN IF NOT EXISTS honoraires_payes TINYINT(1) DEFAULT 0;",
    "ALTER TABLE location_bloc_dossier_anesthesie ADD COLUMN IF NOT EXISTS id_decharge_anesthesie INT NULL;",

    "ALTER TABLE accouchement_dossier_anesthesie ADD COLUMN IF NOT EXISTS honoraires_payes TINYINT(1) DEFAULT 0;",
    "ALTER TABLE accouchement_dossier_anesthesie ADD COLUMN IF NOT EXISTS id_decharge_anesthesie INT NULL;",

    "ALTER TABLE kt_dossier_anesthesie ADD COLUMN IF NOT EXISTS honoraires_payes TINYINT(1) DEFAULT 0;",
    "ALTER TABLE kt_dossier_anesthesie ADD COLUMN IF NOT EXISTS id_decharge_anesthesie INT NULL;",

    "ALTER TABLE medecin_interne_anesthesie ADD COLUMN IF NOT EXISTS anesthesiste_paye TINYINT(1) DEFAULT 0;",
    "ALTER TABLE medecin_interne_anesthesie ADD COLUMN IF NOT EXISTS id_decharge_anesthesie INT NULL;",
]

def run_migration():
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            for i, sql in enumerate(SQL_STATEMENTS):
                print(f"Executing statement {i+1}/{len(SQL_STATEMENTS)}...")
                cursor.execute(sql)
                conn.commit()
                print(f"  OK")
            print("\n=== Migration completed successfully! ===")
        except Exception as e:
            conn.rollback()
            print(f"\nERROR at statement {i+1}: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

if __name__ == '__main__':
    run_migration()
