-- =====================================================
-- MIGRATION: QR Code Dossiers — Phase 1
-- Date: 2026-02-24
-- =====================================================

-- ① Ajout colonne qr_uuid dans les 4 tables source
ALTER TABLE accouchement_dossiers
ADD COLUMN qr_uuid CHAR(36) UNIQUE DEFAULT (UUID())
COMMENT 'UUID permanent pour QR Code dossier';

ALTER TABLE location_bloc_dossier_patient
ADD COLUMN qr_uuid CHAR(36) UNIQUE DEFAULT (UUID())
COMMENT 'UUID permanent pour QR Code dossier';

ALTER TABLE kt_dossier_patient
ADD COLUMN qr_uuid CHAR(36) UNIQUE DEFAULT (UUID())
COMMENT 'UUID permanent pour QR Code dossier';

ALTER TABLE medecin_interne_actes
ADD COLUMN qr_uuid CHAR(36) UNIQUE DEFAULT (UUID())
COMMENT 'UUID permanent pour QR Code dossier';

-- ② Rétro-population UUID pour les enregistrements existants
UPDATE accouchement_dossiers SET qr_uuid = UUID() WHERE qr_uuid IS NULL;
UPDATE location_bloc_dossier_patient SET qr_uuid = UUID() WHERE qr_uuid IS NULL;
UPDATE kt_dossier_patient SET qr_uuid = UUID() WHERE qr_uuid IS NULL;
UPDATE medecin_interne_actes SET qr_uuid = UUID() WHERE qr_uuid IS NULL;

-- ③ Ajout statut dans archivage_dossiers
ALTER TABLE archivage_dossiers
ADD COLUMN statut ENUM('ARCHIVE', 'SORTI', 'DESARCHIVE')
    NOT NULL DEFAULT 'ARCHIVE';

-- ④ Table historique des mouvements
CREATE TABLE IF NOT EXISTS archivage_dossiers_historique (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    id_dossier      INT NOT NULL,
    action          ENUM('CREATION','DEPLACEMENT_BOITE','DEPLACEMENT_ZONE',
                         'SORTIE_TEMPORAIRE','RETOUR','DESARCHIVE') NOT NULL,
    id_boite_avant  INT DEFAULT NULL,
    id_boite_apres  INT DEFAULT NULL,
    zone_avant      VARCHAR(100) DEFAULT NULL,
    zone_apres      VARCHAR(100) DEFAULT NULL,
    commentaire     TEXT DEFAULT NULL,
    effectue_par    INT NOT NULL,
    date_action     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_dossier) REFERENCES archivage_dossiers(id) ON DELETE CASCADE,
    INDEX idx_hist_dossier (id_dossier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ⑤ Table sorties temporaires
CREATE TABLE IF NOT EXISTS archivage_dossiers_sorties (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    id_dossier      INT NOT NULL UNIQUE,
    motif           VARCHAR(255) NOT NULL,
    sorti_par       INT NOT NULL,
    date_sortie     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_retour_prevue DATETIME DEFAULT NULL,
    date_retour     DATETIME DEFAULT NULL,
    retourne_par    INT DEFAULT NULL,
    FOREIGN KEY (id_dossier) REFERENCES archivage_dossiers(id),
    INDEX idx_sorties_actives (date_retour)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
