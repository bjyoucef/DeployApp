-- =========================================================
-- MIGRATION: Système d'Hospitalisation
-- Base: dbsmart2026
-- Date: 2026-02-26
-- NOTE: Ordre de création adapté pour éviter les FK circulaires
-- =========================================================

USE `dbsmart2026`;

-- 1. ALTER TABLE services: ajouter les colonnes hospitalisation
ALTER TABLE `services`
    ADD COLUMN IF NOT EXISTS `est_hospitalier` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Service avec lits d hospitalisation',
    ADD COLUMN IF NOT EXISTS `tarif_fixe_sejour_court` DECIMAL(10,2) DEFAULT 0.00 COMMENT 'Tarif fixe pour sejour court (<24h)',
    ADD COLUMN IF NOT EXISTS `seuil_sejour_court_heures` INT(11) DEFAULT 24 COMMENT 'Seuil en heures pour considerer un sejour comme court';


-- 2. Table hosp_chambres
CREATE TABLE IF NOT EXISTS `hosp_chambres` (
    `id_chambre` INT(11) NOT NULL AUTO_INCREMENT,
    `id_service` INT(11) NOT NULL,
    `id_type_chambre` INT(11) NOT NULL,
    `numero_chambre` VARCHAR(20) NOT NULL,
    `prix_nuit` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Prix par nuit (override du type_chambre si necessaire)',
    `est_active` TINYINT(1) NOT NULL DEFAULT 1,
    `etage` VARCHAR(10) DEFAULT NULL COMMENT 'Etage (ex: 2, 3, RDC)',
    `position_css` VARCHAR(50) DEFAULT NULL COMMENT 'Classe CSS pour positionnement dans le plan',
    `notes` TEXT DEFAULT NULL,
    `created_by` INT(11) DEFAULT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP(),
    `updated_by` INT(11) DEFAULT NULL,
    `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
    PRIMARY KEY (`id_chambre`),
    UNIQUE KEY `uq_chambre_service` (`id_service`, `numero_chambre`),
    CONSTRAINT `FK_hosp_chambres_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`),
    CONSTRAINT `FK_hosp_chambres_type` FOREIGN KEY (`id_type_chambre`) REFERENCES `type_chambre` (`id_type_chambre`),
    CONSTRAINT `FK_hosp_chambres_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- 3. Table hosp_lits
CREATE TABLE IF NOT EXISTS `hosp_lits` (
    `id_lit` INT(11) NOT NULL AUTO_INCREMENT,
    `id_chambre` INT(11) NOT NULL,
    `numero_lit` VARCHAR(10) NOT NULL COMMENT 'Numero du lit dans la chambre (ex: A, B, 1, 2)',
    `est_occupe` TINYINT(1) NOT NULL DEFAULT 0,
    `est_actif` TINYINT(1) NOT NULL DEFAULT 1,
    `notes` TEXT DEFAULT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP(),
    `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
    PRIMARY KEY (`id_lit`),
    UNIQUE KEY `uq_lit_chambre` (`id_chambre`, `numero_lit`),
    CONSTRAINT `FK_hosp_lits_chambre` FOREIGN KEY (`id_chambre`) REFERENCES `hosp_chambres` (`id_chambre`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- 4. Table hosp_admissions (créée AVANT hosp_demandes_admission pour résoudre le FK circulaire)
CREATE TABLE IF NOT EXISTS `hosp_admissions` (
    `id_admission` INT(11) NOT NULL AUTO_INCREMENT,
    `id_demande` INT(11) DEFAULT NULL COMMENT 'FK ajoutee apres creation de hosp_demandes_admission',
    `patient_oid` VARCHAR(50) NOT NULL,
    `patient_nom` VARCHAR(255) NOT NULL,
    `statut` ENUM('en_cours','sorti','annule') NOT NULL DEFAULT 'en_cours',
    `date_admission` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    `date_sortie` DATETIME DEFAULT NULL,
    `motif_sortie` TEXT DEFAULT NULL,
    `destination_sortie` VARCHAR(100) DEFAULT NULL COMMENT 'domicile, transfert, deces, etc.',
    `cout_total` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    `notes` TEXT DEFAULT NULL,
    `created_by` INT(11) DEFAULT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP(),
    `updated_by` INT(11) DEFAULT NULL,
    `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
    PRIMARY KEY (`id_admission`),
    KEY `idx_admission_statut` (`statut`),
    KEY `idx_admission_patient` (`patient_oid`),
    KEY `idx_admission_dates` (`date_admission`, `date_sortie`),
    CONSTRAINT `FK_hosp_admission_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- 5. Table hosp_demandes_admission
CREATE TABLE IF NOT EXISTS `hosp_demandes_admission` (
    `id_demande` INT(11) NOT NULL AUTO_INCREMENT,
    `patient_oid` VARCHAR(50) NOT NULL COMMENT 'OID patient depuis le HIS PostgreSQL',
    `patient_nom` VARCHAR(255) NOT NULL COMMENT 'Nom complet du patient (cache)',
    `id_service` INT(11) NOT NULL,
    `id_medecin` INT(11) DEFAULT NULL COMMENT 'Medecin referent',
    `statut` ENUM('en_attente','admis','annule','transfere') NOT NULL DEFAULT 'en_attente',
    `motif` TEXT DEFAULT NULL,
    `priorite` ENUM('basse','normale','haute','urgente') NOT NULL DEFAULT 'normale',
    `id_admission_source` INT(11) DEFAULT NULL COMMENT 'Pour les transferts inter-services: admission d origine',
    `notes` TEXT DEFAULT NULL,
    `created_by` INT(11) DEFAULT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP(),
    `updated_by` INT(11) DEFAULT NULL,
    `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
    PRIMARY KEY (`id_demande`),
    KEY `idx_demande_statut` (`statut`),
    KEY `idx_demande_patient` (`patient_oid`),
    KEY `idx_demande_service` (`id_service`),
    CONSTRAINT `FK_hosp_demande_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`),
    CONSTRAINT `FK_hosp_demande_medecin` FOREIGN KEY (`id_medecin`) REFERENCES `doctors` (`id`) ON DELETE SET NULL,
    CONSTRAINT `FK_hosp_demande_source` FOREIGN KEY (`id_admission_source`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE SET NULL,
    CONSTRAINT `FK_hosp_demande_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- 6. Ajouter la FK croisée: hosp_admissions.id_demande -> hosp_demandes_admission.id_demande
ALTER TABLE `hosp_admissions`
    ADD CONSTRAINT `FK_hosp_admission_demande` FOREIGN KEY (`id_demande`) REFERENCES `hosp_demandes_admission` (`id_demande`);


-- 7. Table hosp_attributions_lits
CREATE TABLE IF NOT EXISTS `hosp_attributions_lits` (
    `id_attribution` INT(11) NOT NULL AUTO_INCREMENT,
    `id_admission` INT(11) NOT NULL,
    `id_lit` INT(11) NOT NULL,
    `id_service` INT(11) NOT NULL COMMENT 'Service au moment de l attribution',
    `date_debut` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    `date_fin` DATETIME DEFAULT NULL,
    `prix_nuit_applique` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Prix fixe au moment de l attribution',
    `est_sejour_court` TINYINT(1) NOT NULL DEFAULT 0,
    `cout_calcule` DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    `tarif_fixe_applique` DECIMAL(10,2) DEFAULT 0.00 COMMENT 'Tarif fixe pour sejour court',
    `notes` TEXT DEFAULT NULL,
    `created_by` INT(11) DEFAULT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP(),
    `updated_by` INT(11) DEFAULT NULL,
    `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP() ON UPDATE CURRENT_TIMESTAMP(),
    PRIMARY KEY (`id_attribution`),
    KEY `idx_attribution_admission` (`id_admission`),
    KEY `idx_attribution_lit` (`id_lit`),
    KEY `idx_attribution_dates` (`date_debut`, `date_fin`),
    CONSTRAINT `FK_hosp_attr_admission` FOREIGN KEY (`id_admission`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE CASCADE,
    CONSTRAINT `FK_hosp_attr_lit` FOREIGN KEY (`id_lit`) REFERENCES `hosp_lits` (`id_lit`),
    CONSTRAINT `FK_hosp_attr_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- 8. Table hosp_transferts
CREATE TABLE IF NOT EXISTS `hosp_transferts` (
    `id_transfert` INT(11) NOT NULL AUTO_INCREMENT,
    `id_admission` INT(11) NOT NULL,
    `id_attribution_source` INT(11) DEFAULT NULL,
    `id_attribution_dest` INT(11) DEFAULT NULL,
    `id_service_source` INT(11) NOT NULL,
    `id_service_dest` INT(11) NOT NULL,
    `type_transfert` ENUM('intra_service','inter_service') NOT NULL DEFAULT 'intra_service',
    `date_transfert` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    `motif` TEXT DEFAULT NULL,
    `notes` TEXT DEFAULT NULL,
    `created_by` INT(11) DEFAULT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (`id_transfert`),
    KEY `idx_transfert_admission` (`id_admission`),
    CONSTRAINT `FK_hosp_transfert_admission` FOREIGN KEY (`id_admission`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE CASCADE,
    CONSTRAINT `FK_hosp_transfert_src_service` FOREIGN KEY (`id_service_source`) REFERENCES `services` (`id_service`),
    CONSTRAINT `FK_hosp_transfert_dst_service` FOREIGN KEY (`id_service_dest`) REFERENCES `services` (`id_service`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- 9. Table hosp_historique_sejours
CREATE TABLE IF NOT EXISTS `hosp_historique_sejours` (
    `id_historique` INT(11) NOT NULL AUTO_INCREMENT,
    `id_admission` INT(11) NOT NULL,
    `patient_oid` VARCHAR(50) NOT NULL,
    `patient_nom` VARCHAR(255) NOT NULL,
    `id_lit` INT(11) DEFAULT NULL,
    `id_chambre` INT(11) DEFAULT NULL,
    `id_service` INT(11) DEFAULT NULL,
    `numero_lit` VARCHAR(10) DEFAULT NULL,
    `numero_chambre` VARCHAR(20) DEFAULT NULL,
    `nom_service` VARCHAR(255) DEFAULT NULL,
    `date_debut` DATETIME DEFAULT NULL,
    `date_fin` DATETIME DEFAULT NULL,
    `duree_heures` DECIMAL(10,2) DEFAULT 0.00,
    `prix_nuit_applique` DECIMAL(10,2) DEFAULT 0.00,
    `cout_periode` DECIMAL(12,2) DEFAULT 0.00,
    `est_sejour_court` TINYINT(1) DEFAULT 0,
    `notes` TEXT DEFAULT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (`id_historique`),
    KEY `idx_historique_admission` (`id_admission`),
    KEY `idx_historique_patient` (`patient_oid`),
    CONSTRAINT `FK_hosp_hist_admission` FOREIGN KEY (`id_admission`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- =========================================================
-- FIN DE MIGRATION
-- =========================================================
