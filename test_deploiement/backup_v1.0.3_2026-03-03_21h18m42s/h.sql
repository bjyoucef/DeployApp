-- --------------------------------------------------------
-- Hôte:                         127.0.0.1
-- Version du serveur:           11.5.2-MariaDB - mariadb.org binary distribution
-- SE du serveur:                Win64
-- HeidiSQL Version:             12.15.0.7214
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- Listage de la structure de la base pour dbsmartv6
CREATE DATABASE IF NOT EXISTS `dbsmartv6` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;
USE `dbsmartv6`;

-- Listage de la structure de table dbsmartv6. actes_supplement
CREATE TABLE IF NOT EXISTS `actes_supplement` (
  `id_acte` int(11) NOT NULL AUTO_INCREMENT,
  `nom_acte` varchar(255) NOT NULL COMMENT 'Nom de l''intervention',
  `prix` decimal(10,2) DEFAULT 0.00 COMMENT 'Prix de base de l''acte',
  `est_actif` tinyint(1) NOT NULL DEFAULT 1,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_acte`),
  KEY `idx_nom_acte` (`nom_acte`)
) ENGINE=InnoDB AUTO_INCREMENT=1045 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. doctors
CREATE TABLE IF NOT EXISTS `doctors` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `first_name` varchar(255) NOT NULL,
  `last_name` varchar(255) DEFAULT NULL,
  `telephone` varchar(255) DEFAULT NULL,
  `id_specialty` int(11) DEFAULT NULL,
  `est_interne` tinyint(1) DEFAULT NULL,
  `_migration_old_kt_id` int(11) DEFAULT NULL,
  `pourcentage_medecin_interne` decimal(5,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK_doctors_specialty` (`id_specialty`),
  CONSTRAINT `FK_doctors_specialty` FOREIGN KEY (`id_specialty`) REFERENCES `specialty` (`id_specialty`)
) ENGINE=InnoDB AUTO_INCREMENT=145 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_admissions
CREATE TABLE IF NOT EXISTS `hosp_admissions` (
  `id_admission` int(11) NOT NULL AUTO_INCREMENT,
  `id_demande` int(11) DEFAULT NULL COMMENT 'FK ajoutee apres creation de hosp_demandes_admission',
  `patient_oid` varchar(50) NOT NULL,
  `patient_nom` varchar(255) NOT NULL,
  `statut` enum('en_cours','sorti','annule') NOT NULL DEFAULT 'en_cours',
  `date_admission` datetime NOT NULL DEFAULT current_timestamp(),
  `date_sortie` datetime DEFAULT NULL,
  `motif_sortie` text DEFAULT NULL,
  `destination_sortie` varchar(100) DEFAULT NULL COMMENT 'domicile, transfert, deces, etc.',
  `cout_total` decimal(12,2) NOT NULL DEFAULT 0.00,
  `notes` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_admission`),
  KEY `idx_admission_statut` (`statut`),
  KEY `idx_admission_patient` (`patient_oid`),
  KEY `idx_admission_dates` (`date_admission`,`date_sortie`),
  KEY `FK_hosp_admission_created` (`created_by`),
  KEY `FK_hosp_admission_demande` (`id_demande`),
  CONSTRAINT `FK_hosp_admission_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `FK_hosp_admission_demande` FOREIGN KEY (`id_demande`) REFERENCES `hosp_demandes_admission` (`id_demande`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_attributions_lits
CREATE TABLE IF NOT EXISTS `hosp_attributions_lits` (
  `id_attribution` int(11) NOT NULL AUTO_INCREMENT,
  `id_admission` int(11) NOT NULL,
  `id_lit` int(11) NOT NULL,
  `id_service` int(11) NOT NULL COMMENT 'Service au moment de l attribution',
  `date_debut` datetime NOT NULL DEFAULT current_timestamp(),
  `date_fin` datetime DEFAULT NULL,
  `prix_nuit_applique` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Prix fixe au moment de l attribution',
  `est_sejour_court` tinyint(1) NOT NULL DEFAULT 0,
  `cout_calcule` decimal(12,2) NOT NULL DEFAULT 0.00,
  `tarif_fixe_applique` decimal(10,2) DEFAULT 0.00 COMMENT 'Tarif fixe pour sejour court',
  `notes` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_attribution`),
  KEY `idx_attribution_admission` (`id_admission`),
  KEY `idx_attribution_lit` (`id_lit`),
  KEY `idx_attribution_dates` (`date_debut`,`date_fin`),
  KEY `FK_hosp_attr_service` (`id_service`),
  CONSTRAINT `FK_hosp_attr_admission` FOREIGN KEY (`id_admission`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE CASCADE,
  CONSTRAINT `FK_hosp_attr_lit` FOREIGN KEY (`id_lit`) REFERENCES `hosp_lits` (`id_lit`),
  CONSTRAINT `FK_hosp_attr_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_chambres
CREATE TABLE IF NOT EXISTS `hosp_chambres` (
  `id_chambre` int(11) NOT NULL AUTO_INCREMENT,
  `id_service` int(11) NOT NULL,
  `id_type_chambre` int(11) NOT NULL,
  `numero_chambre` varchar(20) NOT NULL,
  `prix_nuit` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Prix par nuit (override du type_chambre si necessaire)',
  `est_active` tinyint(1) NOT NULL DEFAULT 1,
  `etage` varchar(10) DEFAULT NULL COMMENT 'Etage (ex: 2, 3, RDC)',
  `position_css` varchar(50) DEFAULT NULL COMMENT 'Classe CSS pour positionnement dans le plan',
  `notes` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_chambre`),
  UNIQUE KEY `uq_chambre_service` (`id_service`,`numero_chambre`),
  KEY `FK_hosp_chambres_type` (`id_type_chambre`),
  KEY `FK_hosp_chambres_created` (`created_by`),
  CONSTRAINT `FK_hosp_chambres_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `FK_hosp_chambres_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`),
  CONSTRAINT `FK_hosp_chambres_type` FOREIGN KEY (`id_type_chambre`) REFERENCES `type_chambre` (`id_type_chambre`)
) ENGINE=InnoDB AUTO_INCREMENT=28 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_consommations
CREATE TABLE IF NOT EXISTS `hosp_consommations` (
  `id_consommation` int(11) NOT NULL AUTO_INCREMENT,
  `id_admission` int(11) NOT NULL,
  `type_element` enum('produit','acte','radio','labo') NOT NULL,
  `id_element` int(11) DEFAULT NULL,
  `libelle` varchar(255) NOT NULL,
  `quantite` int(11) NOT NULL DEFAULT 1,
  `prix_unitaire` decimal(10,2) NOT NULL DEFAULT 0.00,
  `date_consommation` datetime NOT NULL DEFAULT current_timestamp(),
  `created_by` int(11) NOT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `est_annule` tinyint(1) NOT NULL DEFAULT 0,
  `annule_by` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_consommation`),
  KEY `idx_consommation_admission` (`id_admission`),
  KEY `idx_consommation_type` (`type_element`),
  KEY `FK_consommation_created_by` (`created_by`),
  CONSTRAINT `FK_consommation_admission` FOREIGN KEY (`id_admission`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE CASCADE,
  CONSTRAINT `FK_consommation_created_by` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_demandes_admission
CREATE TABLE IF NOT EXISTS `hosp_demandes_admission` (
  `id_demande` int(11) NOT NULL AUTO_INCREMENT,
  `patient_oid` varchar(50) NOT NULL COMMENT 'OID patient depuis le HIS PostgreSQL',
  `patient_nom` varchar(255) NOT NULL COMMENT 'Nom complet du patient (cache)',
  `id_service` int(11) NOT NULL,
  `id_medecin` int(11) DEFAULT NULL COMMENT 'Medecin referent',
  `statut` enum('en_attente','admis','annule','transfere') NOT NULL DEFAULT 'en_attente',
  `motif` text DEFAULT NULL,
  `priorite` enum('basse','normale','haute','urgente') NOT NULL DEFAULT 'normale',
  `id_admission_source` int(11) DEFAULT NULL COMMENT 'Pour les transferts inter-services: admission d origine',
  `notes` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_demande`),
  KEY `idx_demande_statut` (`statut`),
  KEY `idx_demande_patient` (`patient_oid`),
  KEY `idx_demande_service` (`id_service`),
  KEY `FK_hosp_demande_medecin` (`id_medecin`),
  KEY `FK_hosp_demande_source` (`id_admission_source`),
  KEY `FK_hosp_demande_created` (`created_by`),
  CONSTRAINT `FK_hosp_demande_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `FK_hosp_demande_medecin` FOREIGN KEY (`id_medecin`) REFERENCES `doctors` (`id`) ON DELETE SET NULL,
  CONSTRAINT `FK_hosp_demande_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`),
  CONSTRAINT `FK_hosp_demande_source` FOREIGN KEY (`id_admission_source`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_historique_sejours
CREATE TABLE IF NOT EXISTS `hosp_historique_sejours` (
  `id_historique` int(11) NOT NULL AUTO_INCREMENT,
  `id_admission` int(11) NOT NULL,
  `patient_oid` varchar(50) NOT NULL,
  `patient_nom` varchar(255) NOT NULL,
  `id_lit` int(11) DEFAULT NULL,
  `id_chambre` int(11) DEFAULT NULL,
  `id_service` int(11) DEFAULT NULL,
  `numero_lit` varchar(10) DEFAULT NULL,
  `numero_chambre` varchar(20) DEFAULT NULL,
  `nom_service` varchar(255) DEFAULT NULL,
  `date_debut` datetime DEFAULT NULL,
  `date_fin` datetime DEFAULT NULL,
  `duree_heures` decimal(10,2) DEFAULT 0.00,
  `prix_nuit_applique` decimal(10,2) DEFAULT 0.00,
  `cout_periode` decimal(12,2) DEFAULT 0.00,
  `est_sejour_court` tinyint(1) DEFAULT 0,
  `notes` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_historique`),
  KEY `idx_historique_admission` (`id_admission`),
  KEY `idx_historique_patient` (`patient_oid`),
  CONSTRAINT `FK_hosp_hist_admission` FOREIGN KEY (`id_admission`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_lits
CREATE TABLE IF NOT EXISTS `hosp_lits` (
  `id_lit` int(11) NOT NULL AUTO_INCREMENT,
  `id_chambre` int(11) NOT NULL,
  `numero_lit` varchar(10) NOT NULL COMMENT 'Numero du lit dans la chambre (ex: A, B, 1, 2)',
  `est_occupe` tinyint(1) NOT NULL DEFAULT 0,
  `est_actif` tinyint(1) NOT NULL DEFAULT 1,
  `notes` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_lit`),
  UNIQUE KEY `uq_lit_chambre` (`id_chambre`,`numero_lit`),
  CONSTRAINT `FK_hosp_lits_chambre` FOREIGN KEY (`id_chambre`) REFERENCES `hosp_chambres` (`id_chambre`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=94 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_produits_inclus
CREATE TABLE IF NOT EXISTS `hosp_produits_inclus` (
  `id_inclusion` int(11) NOT NULL AUTO_INCREMENT,
  `id_service` int(11) DEFAULT NULL,
  `id_chambre` int(11) DEFAULT NULL,
  `id_produit` int(11) NOT NULL,
  `quantite_par_nuit` int(11) NOT NULL DEFAULT 1,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_inclusion`),
  KEY `idx_inclus_service` (`id_service`),
  KEY `idx_inclus_chambre` (`id_chambre`),
  KEY `FK_inclus_produit` (`id_produit`),
  CONSTRAINT `FK_inclus_chambre` FOREIGN KEY (`id_chambre`) REFERENCES `hosp_chambres` (`id_chambre`) ON DELETE CASCADE,
  CONSTRAINT `FK_inclus_produit` FOREIGN KEY (`id_produit`) REFERENCES `produits` (`id_produit`),
  CONSTRAINT `FK_inclus_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. hosp_transferts
CREATE TABLE IF NOT EXISTS `hosp_transferts` (
  `id_transfert` int(11) NOT NULL AUTO_INCREMENT,
  `id_admission` int(11) NOT NULL,
  `id_attribution_source` int(11) DEFAULT NULL,
  `id_attribution_dest` int(11) DEFAULT NULL,
  `id_service_source` int(11) NOT NULL,
  `id_service_dest` int(11) NOT NULL,
  `type_transfert` enum('intra_service','inter_service') NOT NULL DEFAULT 'intra_service',
  `date_transfert` datetime NOT NULL DEFAULT current_timestamp(),
  `motif` text DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_transfert`),
  KEY `idx_transfert_admission` (`id_admission`),
  KEY `FK_hosp_transfert_src_service` (`id_service_source`),
  KEY `FK_hosp_transfert_dst_service` (`id_service_dest`),
  CONSTRAINT `FK_hosp_transfert_admission` FOREIGN KEY (`id_admission`) REFERENCES `hosp_admissions` (`id_admission`) ON DELETE CASCADE,
  CONSTRAINT `FK_hosp_transfert_dst_service` FOREIGN KEY (`id_service_dest`) REFERENCES `services` (`id_service`),
  CONSTRAINT `FK_hosp_transfert_src_service` FOREIGN KEY (`id_service_source`) REFERENCES `services` (`id_service`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. personnel
CREATE TABLE IF NOT EXISTS `personnel` (
  `id_personnel` int(11) NOT NULL AUTO_INCREMENT,
  `nom` varchar(100) DEFAULT NULL,
  `prenom` varchar(100) DEFAULT NULL,
  `role` varchar(50) DEFAULT NULL,
  `id_service` int(11) DEFAULT NULL,
  `telephone` varchar(15) DEFAULT NULL,
  `id_phone` int(11) DEFAULT NULL,
  `username` varchar(50) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `statut_activite` tinyint(1) DEFAULT 0,
  `use_in_planning` tinyint(1) DEFAULT 0,
  `last_login` datetime DEFAULT NULL,
  `last_activity` datetime DEFAULT NULL,
  PRIMARY KEY (`id_personnel`),
  UNIQUE KEY `identifiant_acces` (`username`) USING BTREE,
  KEY `idx_id_personnel` (`id_personnel`),
  KEY `FK_personnel_r_services` (`id_service`),
  KEY `FK_personnel_r_contacts` (`id_phone`),
  KEY `idx_personnel_nom` (`nom`,`prenom`),
  CONSTRAINT `FK_personnel_r_contacts` FOREIGN KEY (`id_phone`) REFERENCES `contacts` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_personnel_r_services` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=632 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. services
CREATE TABLE IF NOT EXISTS `services` (
  `id_service` int(11) NOT NULL AUTO_INCREMENT,
  `service_name` varchar(255) NOT NULL,
  `prix_joure` decimal(10,2) DEFAULT 0.00,
  `prix_nuit` decimal(10,2) DEFAULT 0.00,
  `prix_24h` decimal(10,2) DEFAULT 0.00,
  `salaire` decimal(10,2) DEFAULT 0.00,
  `color` varchar(7) DEFAULT '#FFFFFF',
  `est_hospitalier` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Service avec lits d hospitalisation',
  `tarif_sejour_court` decimal(10,2) DEFAULT 0.00 COMMENT 'Tarif fixe pour sejour court (<24h)',
  `seuil_sejour_court_heures` int(11) DEFAULT 24 COMMENT 'Seuil en heures pour considerer un sejour comme court',
  PRIMARY KEY (`id_service`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. type_chambre
CREATE TABLE IF NOT EXISTS `type_chambre` (
  `id_type_chambre` int(11) NOT NULL AUTO_INCREMENT,
  `nom_type` varchar(100) NOT NULL,
  `prix_unitaire` decimal(10,2) NOT NULL,
  `est_standard` tinyint(1) NOT NULL DEFAULT 0,
  `description` text DEFAULT NULL,
  `capacite` int(11) DEFAULT 1,
  `est_actif` tinyint(1) DEFAULT 1,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_type_chambre`)
) ENGINE=InnoDB AUTO_INCREMENT=1006 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
