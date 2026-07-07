-- --------------------------------------------------------
-- Hôte:                         127.0.0.1
-- Version du serveur:           11.5.2-MariaDB - mariadb.org binary distribution
-- SE du serveur:                Win64
-- HeidiSQL Version:             12.15.0.7171
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- Listage de la structure de la base pour dbsmart2026
CREATE DATABASE IF NOT EXISTS `dbsmart2026` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;
USE `dbsmart2026`;



-- Listage de la structure de table dbsmart2026. accouchement_dossiers
CREATE TABLE IF NOT EXISTS `accouchement_dossiers` (
  `id_dossier` int(11) NOT NULL AUTO_INCREMENT,
  `id_gyneco` int(11) NOT NULL,
  `patient_oid` varchar(50) DEFAULT NULL,
  `patiente` varchar(255) NOT NULL,
  `age_patiente` int(11) DEFAULT NULL,
  `date_accouchement` date NOT NULL,
  `heure_accouchement` time DEFAULT NULL,
  `type_accouchement` enum('VOIE_BASSE','CESARIENNE') NOT NULL,
  `type_cesarienne` enum('URGENCE','PROPHYLACTIQUE') DEFAULT NULL COMMENT 'Type de césarienne (urgence ou prophylactique)',
  `sexe_bebe` enum('MASCULIN','FEMININ') DEFAULT NULL,
  `poids_naissance` decimal(5,3) DEFAULT NULL COMMENT 'poids en kg (ex: 3.150)',
  `prenom_bebe` varchar(100) DEFAULT NULL,
  `ddr` date DEFAULT NULL COMMENT 'Date précise des dernières règles (copie/alias de ddr)',
  `age_gestationnel` varchar(50) DEFAULT NULL,
  `parite` varchar(20) DEFAULT NULL,
  `groupage_sanguin` varchar(5) DEFAULT NULL,
  `rhesus` varchar(10) DEFAULT NULL,
  `apgar_score` varchar(20) DEFAULT NULL COMMENT 'Score APGAR',
  `mode_accouchement_detail` text DEFAULT NULL COMMENT 'JSON ou détails textuels',
  `complications_medicales` text DEFAULT NULL,
  `pathologie_grossesse` text DEFAULT NULL,
  `indication_cesarienne` text DEFAULT NULL,
  `type_anesthesie` varchar(100) DEFAULT NULL,
  `gestes_chirurgicaux` text DEFAULT NULL,
  `instrumentation` text DEFAULT NULL COMMENT 'Instrumentation utilisée (forceps, ventouse, etc.)',
  `fermeture` text DEFAULT NULL,
  `pathologies_maternelles` text DEFAULT NULL COMMENT 'HTA, diabète, etc.',
  `type_tarification` enum('CONVENTION','PAYANT') NOT NULL,
  `est_gyneco_interne` tinyint(1) DEFAULT 0,
  `prix_base` decimal(12,2) NOT NULL DEFAULT 0.00,
  `supplement_gyneco` decimal(12,2) DEFAULT 0.00 COMMENT 'Supplément demandé par gynéco externe',
  `part_gyneco` decimal(12,2) DEFAULT 0.00,
  `part_clinique` decimal(12,2) DEFAULT 0.00,
  `nuitees_incluses` int(11) DEFAULT 1 COMMENT '1 pour voie basse, 2 pour césarienne',
  `prix_produits` decimal(12,2) DEFAULT 0.00,
  `prix_actes` decimal(12,2) DEFAULT 0.00,
  `prix_anesthesie` decimal(12,2) DEFAULT 0.00,
  `prix_explorations` decimal(12,2) DEFAULT 0.00,
  `prix_nuitees` decimal(12,2) DEFAULT 0.00 COMMENT 'Suppléments nuitées uniquement',
  `prix_total` decimal(12,2) DEFAULT 0.00,
  `montant_paye` decimal(12,2) DEFAULT 0.00,
  `mode_paiement` varchar(20) DEFAULT 'DIRECT',
  `statut_paiement` enum('SOLDE','COMPLEMENT_PATIENT','SURPLUS_CLINIQUE','EN_ATTENTE','GYNECO_DOIT_PAYER','CLINIQUE_DOIT_PAYER') DEFAULT 'EN_ATTENTE',
  `statut_medical` enum('NON_VALIDE','VALIDE','EN_ATTENTE') DEFAULT 'NON_VALIDE',
  `statut_financier` enum('NON_VALIDE','VALIDE','EN_ATTENTE') DEFAULT 'NON_VALIDE',
  `observations` text DEFAULT NULL,
  `notes_cliniques` text DEFAULT NULL COMMENT 'Notes cliniques diverses',
  `observations_medicales` text DEFAULT NULL COMMENT 'Observations médicales (complications, suivi, etc.)',
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `balance_patient` decimal(10,2) DEFAULT 0.00 COMMENT 'Balance avec le patient',
  `balance_medecin` decimal(10,2) DEFAULT 0.00 COMMENT 'Balance avec le gynécologue',
  `gyneco_paye` tinyint(1) DEFAULT 0,
  `id_decharge_gyneco` int(11) DEFAULT NULL,
  `valide_medical_par` int(11) DEFAULT NULL COMMENT 'id_personnel qui a validé médicalement',
  `valide_medical_le` datetime DEFAULT NULL,
  `documents_generes` tinyint(4) DEFAULT 0 COMMENT 'Flag : documents générés (0/1)',
  `date_generation_documents` timestamp NULL DEFAULT NULL COMMENT 'Date/heure de génération des documents',
  `date_validation_medical` datetime DEFAULT NULL,
  `validateur_medical_id` int(11) DEFAULT NULL,
  `date_validation_finance` datetime DEFAULT NULL,
  `validateur_finance_id` int(11) DEFAULT NULL,
  `nom_epoux` varchar(255) DEFAULT NULL COMMENT 'Nom du mari/époux de la patiente',
  `ta_postop` varchar(50) DEFAULT NULL COMMENT 'Tension Artérielle post-opératoire (ex: 12/8)',
  `diurese_postop` varchar(100) DEFAULT NULL COMMENT 'Diurèse post-opératoire',
  `reveil_postop` text DEFAULT NULL COMMENT 'État au réveil post-opératoire',
  `compte_compresses` text DEFAULT NULL COMMENT 'Compte des compresses chirurgicales',
  `hemostases` text DEFAULT NULL COMMENT 'Hémostases effectuées',
  `est_annule` tinyint(1) DEFAULT 0,
  `motif_annulation` text DEFAULT NULL,
  `annule_par` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  `qr_uuid` char(36) DEFAULT uuid() COMMENT 'UUID permanent pour QR Code dossier',
  PRIMARY KEY (`id_dossier`),
  UNIQUE KEY `qr_uuid` (`qr_uuid`),
  KEY `fk_accouchement_created_by` (`created_by`),
  KEY `idx_accouchement_date` (`date_accouchement`),
  KEY `idx_accouchement_gyneco` (`id_gyneco`),
  KEY `idx_accouchement_type` (`type_accouchement`),
  KEY `idx_accouchement_tarif` (`type_tarification`),
  KEY `idx_accouchement_statut` (`statut_paiement`),
  KEY `idx_dossier_decharge_gyneco` (`id_decharge_gyneco`),
  KEY `idx_dossier_gyneco_paye` (`gyneco_paye`,`id_decharge_gyneco`),
  KEY `idx_patient_oid` (`patient_oid`),
  KEY `idx_statut_paiement` (`statut_paiement`),
  KEY `idx_statut_medical` (`statut_medical`),
  KEY `idx_statut_financier` (`statut_financier`),
  KEY `fk_valide_medical_par` (`valide_medical_par`),
  KEY `idx_documents_generes` (`documents_generes`),
  CONSTRAINT `accouchement_dossiers_ibfk_1` FOREIGN KEY (`id_decharge_gyneco`) REFERENCES `gyneco_interne_decharges` (`id_decharge`),
  CONSTRAINT `fk_accouchement_created_by` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `fk_accouchement_gyneco` FOREIGN KEY (`id_gyneco`) REFERENCES `doctors` (`id`),
  CONSTRAINT `fk_dossier_decharge_gyneco` FOREIGN KEY (`id_decharge_gyneco`) REFERENCES `gyneco_interne_decharges` (`id_decharge`),
  CONSTRAINT `fk_valide_medical_par` FOREIGN KEY (`valide_medical_par`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `chk_gyneco_paye_coherence` CHECK (`gyneco_paye` = 0 and `id_decharge_gyneco` is null or `gyneco_paye` = 1 and `id_decharge_gyneco` is not null or `gyneco_paye` = 0 and `id_decharge_gyneco` is not null)
) ENGINE=InnoDB AUTO_INCREMENT=191 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;





-- Listage de la structure de table dbsmart2026. doctors
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
) ENGINE=InnoDB AUTO_INCREMENT=101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;





-- Listage de la structure de table dbsmart2026. hosp_chambres
CREATE TABLE IF NOT EXISTS `hosp_chambres` (
  `id_chambre` int(11) NOT NULL AUTO_INCREMENT,
  `id_service` int(11) NOT NULL,
  `id_type_chambre` int(11) NOT NULL,
  `numero_chambre` varchar(20) NOT NULL,
  `prix_nuit` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Prix par nuit (override du type_chambre si necessaire)',
  `est_active` tinyint(1) NOT NULL DEFAULT 1,
  `etage` varchar(10) DEFAULT NULL COMMENT 'Etage (ex: 2, 3, RDC)',
  `position_css` varchar(50) DEFAULT NULL COMMENT 'Classe CSS pour positionnement dans le plan (ex: room-201)',
  `notes` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_chambre`),
  UNIQUE KEY `uq_chambre_service` (`id_service`,`numero_chambre`),
  KEY `FK_hosp_chambres_service` (`id_service`),
  KEY `FK_hosp_chambres_type` (`id_type_chambre`),
  KEY `FK_hosp_chambres_created` (`created_by`),
  CONSTRAINT `FK_hosp_chambres_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL ON UPDATE NO ACTION,
  CONSTRAINT `FK_hosp_chambres_service` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_hosp_chambres_type` FOREIGN KEY (`id_type_chambre`) REFERENCES `type_chambre` (`id_type_chambre`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=28 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;





-- Listage de la structure de table dbsmart2026. hosp_lits
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
  KEY `FK_hosp_lits_chambre` (`id_chambre`),
  CONSTRAINT `FK_hosp_lits_chambre` FOREIGN KEY (`id_chambre`) REFERENCES `hosp_chambres` (`id_chambre`) ON DELETE CASCADE ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=58 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;





-- Listage de la structure de table dbsmart2026. kt_doctor_situations
CREATE TABLE IF NOT EXISTS `kt_doctor_situations` (
  `id_doctor_situations` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) DEFAULT NULL,
  `id_dossier` int(11) DEFAULT NULL,
  `part_operateur` decimal(10,2) DEFAULT 0.00,
  `payment` decimal(10,2) DEFAULT 0.00,
  `payment_date` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_doctor_situations`) USING BTREE,
  KEY `id_doctor` (`id_doctor`) USING BTREE,
  KEY `FK_doctor_situations_dossier_patient_kt` (`id_dossier`) USING BTREE,
  KEY `idx_kt_situations_doctor` (`id_doctor`),
  KEY `idx_kt_situations_dossier` (`id_dossier`),
  CONSTRAINT `FK_kt_doctor_situations_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_kt_doctor_situations_kt_dossier_patient` FOREIGN KEY (`id_dossier`) REFERENCES `kt_dossier_patient` (`id_dossier`)
) ENGINE=InnoDB AUTO_INCREMENT=2342 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;






-- Listage de la structure de table dbsmart2026. kt_dossier_patient
CREATE TABLE IF NOT EXISTS `kt_dossier_patient` (
  `id_dossier` int(11) NOT NULL AUTO_INCREMENT,
  `n_admission` int(200) DEFAULT 0,
  `id_doctor` int(11) NOT NULL,
  `patient` varchar(100) NOT NULL DEFAULT '',
  `patient_oid_his` int(11) DEFAULT NULL,
  `urgence` tinyint(1) DEFAULT 0,
  `acte_date` date DEFAULT NULL,
  `nbr_nuite` int(11) DEFAULT 0,
  `vip` tinyint(1) DEFAULT 0,
  `nbr_nuite_conjoint` int(11) DEFAULT 0,
  `prix_hospitalisation` decimal(10,2) DEFAULT 0.00,
  `prix_conjoint` decimal(10,2) DEFAULT 0.00,
  `extras` decimal(10,2) DEFAULT 0.00,
  `up_medecin` decimal(10,2) DEFAULT 0.00,
  `up_clinique` decimal(10,2) DEFAULT 0.00,
  `part_operateur_up_medecin` decimal(10,2) DEFAULT 0.00,
  `part_operateur_up_clinique` decimal(10,2) DEFAULT 0.00,
  `id_anesthesiste` int(11) DEFAULT NULL,
  `id_reanimateur` int(11) DEFAULT NULL,
  `duree_operation` int(11) DEFAULT NULL COMMENT 'Durée en minutes',
  `compte_rendu_path` varchar(500) DEFAULT NULL,
  `compte_rendu_nom_original` varchar(255) DEFAULT NULL,
  `compte_rendu_date_upload` datetime DEFAULT NULL,
  `part_operateur_extrat` decimal(10,2) DEFAULT 0.00,
  `part_operateur` decimal(10,2) DEFAULT 0.00,
  `prix_dossier_convention` decimal(10,2) DEFAULT 0.00,
  `prix_dossier_esp` decimal(10,2) DEFAULT 0.00,
  `payment` decimal(10,2) DEFAULT 0.00,
  `total_calculé` decimal(10,2) GENERATED ALWAYS AS (coalesce(`prix_dossier_esp`,0) + coalesce(`prix_hospitalisation`,0) + coalesce(`prix_conjoint`,0)) STORED,
  `qr_uuid` char(36) DEFAULT uuid() COMMENT 'UUID permanent pour QR Code dossier',
  PRIMARY KEY (`id_dossier`) USING BTREE,
  UNIQUE KEY `qr_uuid` (`qr_uuid`),
  KEY `doctor_id` (`id_doctor`) USING BTREE,
  KEY `Index_patient` (`patient`) USING BTREE,
  KEY `idx_acte_date` (`acte_date`) USING BTREE,
  KEY `idx_kt_dossier_doctor` (`id_doctor`),
  KEY `idx_kt_dossier_date` (`acte_date`),
  KEY `idx_kt_dossier_patient` (`patient`),
  KEY `idx_kt_dossier_doctor_date` (`id_doctor`,`acte_date`),
  KEY `idx_kt_dossier_urgence` (`urgence`),
  KEY `idx_kt_dossier_vip` (`vip`),
  KEY `idx_kt_dossier_total` (`total_calculé`),
  KEY `id_anesthesiste` (`id_anesthesiste`),
  KEY `id_reanimateur` (`id_reanimateur`),
  KEY `idx_kt_dossier_patient_oid_his` (`patient_oid_his`),
  CONSTRAINT `FK_kt_dossier_patient_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`),
  CONSTRAINT `kt_dossier_patient_ibfk_1` FOREIGN KEY (`id_anesthesiste`) REFERENCES `anesthesie_personnel` (`id_personnel_anesthesie`),
  CONSTRAINT `kt_dossier_patient_ibfk_2` FOREIGN KEY (`id_reanimateur`) REFERENCES `anesthesie_personnel` (`id_personnel_anesthesie`)
) ENGINE=InnoDB AUTO_INCREMENT=2108 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;





-- Listage de la structure de table dbsmart2026. kt_programme
CREATE TABLE IF NOT EXISTS `kt_programme` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `date` date NOT NULL,
  `patient_name` varchar(50) NOT NULL DEFAULT '',
  `convention` varchar(50) NOT NULL DEFAULT '',
  `id_created_par` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`) USING BTREE,
  KEY `FK_planning_personnel` (`patient_name`) USING BTREE,
  KEY `FK_kt_programme_kt_doctors` (`id_doctor`),
  CONSTRAINT `FK_kt_programme_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;







-- Listage de la structure de table dbsmart2026. medecin_interne_actes
CREATE TABLE IF NOT EXISTS `medecin_interne_actes` (
  `id_acte` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `patient` varchar(255) NOT NULL,
  `patient_oid_his` int(11) DEFAULT NULL,
  `date_acte` date NOT NULL,
  `heure_acte` time DEFAULT NULL,
  `nom_acte` varchar(255) DEFAULT NULL,
  `id_specialite` int(11) DEFAULT NULL,
  `nom_specialite` varchar(100) DEFAULT NULL,
  `pourcentage_medecin` decimal(5,2) NOT NULL,
  `prix_acte_base` decimal(10,2) NOT NULL DEFAULT 0.00,
  `prix_consommables_specifiques` decimal(10,2) DEFAULT 0.00,
  `prix_hospitalisation_hors_forfait` decimal(10,2) DEFAULT 0.00,
  `prix_reanimation` decimal(10,2) DEFAULT 0.00,
  `prix_supplements` decimal(10,2) DEFAULT 0.00,
  `total_deductions` decimal(10,2) DEFAULT NULL COMMENT 'Somme: consommables + hospitalisation + supplements + actes_supp + anesthesie',
  `base_calcul` decimal(10,2) DEFAULT 0.00,
  `part_medecin` decimal(10,2) DEFAULT 0.00,
  `part_clinique` decimal(10,2) DEFAULT 0.00,
  `montant_paye_caisse` decimal(10,2) DEFAULT 0.00,
  `difference_paiement` decimal(10,2) DEFAULT 0.00,
  `statut_paiement` enum('EQUILIBRE','COMPLEMENT_MEDECIN','SURPLUS_CLINIQUE','AUCUN_PAIEMENT') DEFAULT 'AUCUN_PAIEMENT',
  `mode_calcul` varchar(20) DEFAULT 'PRIX_TOTAL',
  `observations` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `prix_actes_supplementaires` decimal(10,2) DEFAULT 0.00,
  `prix_anesthesie` decimal(10,2) DEFAULT 0.00,
  `medecin_paye` tinyint(1) DEFAULT 0 COMMENT 'Indique si le médecin a été payé',
  `id_decharge_medecin` int(11) DEFAULT NULL COMMENT 'Référence vers la décharge de paiement',
  `nuitees_incluses_tarif` int(11) DEFAULT 0 COMMENT 'Nombre de nuitées incluses dans le tarif de base',
  `updated_by` int(11) DEFAULT NULL,
  `prix_consommables_medecin` decimal(10,2) DEFAULT 0.00 COMMENT 'Consommables du médecin ajoutés à sa part',
  `est_annule` tinyint(1) DEFAULT 0 COMMENT 'Indique si l''acte est annulé',
  `motif_annulation` text DEFAULT NULL COMMENT 'Motif de l''annulation',
  `annule_par` int(11) DEFAULT NULL COMMENT 'Personnel ayant annulé',
  `annule_at` datetime DEFAULT NULL COMMENT 'Date et heure d''annulation',
  `duree_bloc` int(11) DEFAULT 90,
  `qr_uuid` char(36) DEFAULT uuid() COMMENT 'UUID permanent pour QR Code dossier',
  PRIMARY KEY (`id_acte`),
  UNIQUE KEY `qr_uuid` (`qr_uuid`),
  KEY `id_specialite` (`id_specialite`),
  KEY `created_by` (`created_by`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_date` (`date_acte`),
  KEY `idx_statut` (`statut_paiement`),
  KEY `idx_mode_calcul` (`mode_calcul`),
  KEY `idx_medecin_paye` (`medecin_paye`),
  KEY `idx_decharge` (`id_decharge_medecin`),
  KEY `idx_acte_non_paye` (`id_doctor`,`medecin_paye`,`date_acte`),
  KEY `updated_by` (`updated_by`),
  KEY `idx_est_annule` (`est_annule`),
  KEY `idx_annule_par` (`annule_par`),
  CONSTRAINT `fk_acte_annule_par` FOREIGN KEY (`annule_par`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_acte_decharge` FOREIGN KEY (`id_decharge_medecin`) REFERENCES `medecin_interne_decharges` (`id_decharge`) ON DELETE SET NULL,
  CONSTRAINT `medecin_interne_actes_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`),
  CONSTRAINT `medecin_interne_actes_ibfk_2` FOREIGN KEY (`id_specialite`) REFERENCES `specialty` (`id_specialty`),
  CONSTRAINT `medecin_interne_actes_ibfk_3` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `medecin_interne_actes_ibfk_4` FOREIGN KEY (`updated_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=155 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- Listage de la structure de table dbsmart2026. medecin_interne_actes_supplementaires
CREATE TABLE IF NOT EXISTS `medecin_interne_actes_supplementaires` (
  `id_acte_supp` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte_principal` int(11) NOT NULL,
  `id_type_acte` int(11) DEFAULT NULL,
  `nom_acte` varchar(255) DEFAULT NULL,
  `quantite` decimal(10,2) DEFAULT 1.00,
  `prix_unitaire` decimal(10,2) DEFAULT 0.00,
  `prix_total` decimal(10,2) DEFAULT 0.00,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_acte_supp`),
  KEY `id_acte_principal` (`id_acte_principal`),
  KEY `id_type_acte` (`id_type_acte`),
  CONSTRAINT `FK_medecin_interne_actes_supplementaires_location_bloc_acte` FOREIGN KEY (`id_type_acte`) REFERENCES `location_bloc_acte` (`id_acte`),
  CONSTRAINT `medecin_interne_actes_supplementaires_ibfk_1` FOREIGN KEY (`id_acte_principal`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;



-- Listage de la structure de table dbsmart2026. medecin_interne_anesthesie
CREATE TABLE IF NOT EXISTS `medecin_interne_anesthesie` (
  `id_anesthesie` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) NOT NULL,
  `id_acte_anesthesie` int(11) NOT NULL,
  `id_personnel_anesthesie` int(11) NOT NULL,
  `duree_reelle` int(11) DEFAULT 90,
  `honoraires_calcules` decimal(10,2) DEFAULT 0.00,
  `observations` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `est_annule` tinyint(1) DEFAULT 0,
  `annule_par` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  `anesthesiste_paye` tinyint(1) DEFAULT 0,
  `id_decharge_anesthesie` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_anesthesie`),
  KEY `id_acte` (`id_acte`),
  KEY `id_acte_anesthesie` (`id_acte_anesthesie`),
  KEY `id_personnel_anesthesie` (`id_personnel_anesthesie`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `medecin_interne_anesthesie_ibfk_1` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `medecin_interne_anesthesie_ibfk_2` FOREIGN KEY (`id_acte_anesthesie`) REFERENCES `anesthesie_type_acte` (`id_acte_anesthesie`),
  CONSTRAINT `medecin_interne_anesthesie_ibfk_3` FOREIGN KEY (`id_personnel_anesthesie`) REFERENCES `anesthesie_personnel` (`id_personnel_anesthesie`),
  CONSTRAINT `medecin_interne_anesthesie_ibfk_4` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=307 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;



-- Listage de la structure de table dbsmart2026. medecin_interne_consommables
CREATE TABLE IF NOT EXISTS `medecin_interne_consommables` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) NOT NULL,
  `id_produit` int(11) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `quantite` decimal(10,2) NOT NULL DEFAULT 1.00,
  `prix_unitaire` decimal(10,2) NOT NULL,
  `prix_total` decimal(10,2) NOT NULL,
  `est_annule` tinyint(1) DEFAULT 0,
  `annule_par` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `id_produit` (`id_produit`),
  KEY `idx_acte` (`id_acte`),
  CONSTRAINT `medecin_interne_consommables_ibfk_1` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `medecin_interne_consommables_ibfk_2` FOREIGN KEY (`id_produit`) REFERENCES `produits` (`id_produit`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;




-- Listage de la structure de table dbsmart2026. medecin_interne_hospitalisation
CREATE TABLE IF NOT EXISTS `medecin_interne_hospitalisation` (
  `id_hospitalisation` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) NOT NULL,
  `id_type_chambre` int(11) NOT NULL,
  `date_entree` date NOT NULL,
  `date_sortie` date NOT NULL,
  `nombre_nuitees` int(11) NOT NULL,
  `prix_unitaire` decimal(10,2) NOT NULL,
  `prix_total` decimal(10,2) NOT NULL,
  `est_hors_forfait` tinyint(1) DEFAULT 1,
  `type_hospitalisation` enum('STANDARD','REANIMATION') DEFAULT 'STANDARD',
  `observations` text DEFAULT NULL,
  `nombre_nuitees_facturees` int(11) DEFAULT 0 COMMENT 'Nombre de nuitées facturées (après déduction des nuitées incluses)',
  `est_annule` tinyint(1) DEFAULT 0,
  `annule_par` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_hospitalisation`),
  KEY `id_type_chambre` (`id_type_chambre`),
  KEY `idx_acte` (`id_acte`),
  CONSTRAINT `medecin_interne_hospitalisation_ibfk_1` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `medecin_interne_hospitalisation_ibfk_2` FOREIGN KEY (`id_type_chambre`) REFERENCES `type_chambre` (`id_type_chambre`)
) ENGINE=InnoDB AUTO_INCREMENT=57 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;







-- Listage de la structure de table dbsmart2026. medecin_interne_situations
CREATE TABLE IF NOT EXISTS `medecin_interne_situations` (
  `id_situation` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `id_acte` int(11) NOT NULL,
  `payment_date` timestamp NULL DEFAULT current_timestamp(),
  `encaissement_patient` decimal(10,2) DEFAULT 0.00,
  `encaissement_doctor` decimal(10,2) DEFAULT 0.00,
  `decaissement_clinique` decimal(10,2) DEFAULT 0.00,
  `compensation` decimal(10,2) DEFAULT 0.00,
  `notes` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `est_annule` tinyint(1) DEFAULT 0,
  `annule_par` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_situation`),
  KEY `created_by` (`created_by`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_acte` (`id_acte`),
  KEY `idx_date` (`payment_date`),
  CONSTRAINT `medecin_interne_situations_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`),
  CONSTRAINT `medecin_interne_situations_ibfk_2` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `medecin_interne_situations_ibfk_3` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=151 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- Listage de la structure de table dbsmart2026. medecin_interne_supplements
CREATE TABLE IF NOT EXISTS `medecin_interne_supplements` (
  `id_supplement` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) NOT NULL,
  `type_supplement` varchar(100) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `prix` decimal(10,2) NOT NULL,
  `date_supplement` date DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `est_annule` tinyint(1) DEFAULT 0,
  `annule_par` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_supplement`),
  KEY `idx_acte` (`id_acte`),
  CONSTRAINT `medecin_interne_supplements_ibfk_1` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- Listage de la structure de table dbsmart2026. menu_items
CREATE TABLE IF NOT EXISTS `menu_items` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `route` varchar(255) NOT NULL,
  `label` varchar(255) NOT NULL,
  `icon` varchar(255) NOT NULL,
  `privilege` varchar(255) DEFAULT NULL,
  `badge` int(11) DEFAULT NULL,
  `parent_id` int(11) DEFAULT NULL,
  `order` int(11) NOT NULL DEFAULT 0,
  `dans_index` tinyint(1) DEFAULT NULL,
  `tooltip` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_menu_parent` (`parent_id`),
  CONSTRAINT `fk_menu_parent` FOREIGN KEY (`parent_id`) REFERENCES `menu_items` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=109 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;



-- Listage de la structure de table dbsmart2026. menu_items_admin
CREATE TABLE IF NOT EXISTS `menu_items_admin` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `route` varchar(255) NOT NULL,
  `label` varchar(255) NOT NULL,
  `icon` varchar(255) NOT NULL,
  `privilege` varchar(255) DEFAULT NULL,
  `badge` int(11) DEFAULT NULL,
  `dans_index` tinyint(1) DEFAULT NULL,
  `tooltip` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=59 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;





-- Listage de la structure de table dbsmart2026. services
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





-- Listage de la structure de vue dbsmart2026. v_accouchements_sans_documents
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_accouchements_sans_documents` (
	`id_dossier` INT(11) NOT NULL,
	`patiente` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_accouchement` DATE NOT NULL,
	`gyneco_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`prix_total` DECIMAL(12,2) NULL,
	`montant_paye` DECIMAL(12,2) NULL,
	`statut_financier` ENUM('NON_VALIDE','VALIDE','EN_ATTENTE') NULL COLLATE 'utf8mb4_unicode_ci',
	`documents_generes` TINYINT(4) NULL COMMENT 'Flag : documents générés (0/1)',
	`status_documents` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci'
);
