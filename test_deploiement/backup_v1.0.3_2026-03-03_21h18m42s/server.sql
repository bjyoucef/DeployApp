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

-- Listage de la structure de table dbsmartv6. accouchement_bons_paiement
CREATE TABLE IF NOT EXISTS `accouchement_bons_paiement` (
  `id_bon` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `numero_bon` varchar(50) NOT NULL,
  `type_bon` enum('INITIAL','COMPLEMENT','REMBOURSEMENT') DEFAULT 'INITIAL',
  `montant_total` decimal(12,2) NOT NULL,
  `montant_a_payer` decimal(12,2) NOT NULL,
  `montant_paye` decimal(12,2) DEFAULT 0.00,
  `montant_restant` decimal(12,2) NOT NULL,
  `description` text DEFAULT NULL,
  `details_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`details_json`)),
  `statut` enum('EN_ATTENTE','PAYE_PARTIEL','PAYE_COMPLET','ANNULE') DEFAULT 'EN_ATTENTE',
  `date_emission` datetime NOT NULL,
  `date_echeance` date DEFAULT NULL,
  `date_paiement_complet` datetime DEFAULT NULL,
  `emis_par` int(11) DEFAULT NULL,
  `encaisse_par` int(11) DEFAULT NULL,
  `caisse_id` int(11) DEFAULT NULL,
  `qr_code_data` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_bon`),
  UNIQUE KEY `numero_bon` (`numero_bon`),
  KEY `emis_par` (`emis_par`),
  KEY `encaisse_par` (`encaisse_par`),
  KEY `idx_numero` (`numero_bon`),
  KEY `idx_statut` (`statut`),
  KEY `idx_dossier` (`id_dossier`),
  CONSTRAINT `accouchement_bons_paiement_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `accouchement_bons_paiement_ibfk_2` FOREIGN KEY (`emis_par`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `accouchement_bons_paiement_ibfk_3` FOREIGN KEY (`encaisse_par`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_documents_generes
CREATE TABLE IF NOT EXISTS `accouchement_documents_generes` (
  `id_document` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `type_document` enum('CERTIFICAT_ACCOUCHEMENT','CONGE_MATERNITE','COMPTE_RENDU_POST_PARTUM','COMPTE_RENDU_OPERATOIRE') NOT NULL,
  `date_generation` datetime DEFAULT current_timestamp(),
  `genere_par` int(11) NOT NULL COMMENT 'id_personnel',
  `contenu_json` text DEFAULT NULL COMMENT 'Données du document en JSON pour régénération',
  `fichier_path` varchar(500) DEFAULT NULL COMMENT 'Chemin du fichier PDF stocké',
  PRIMARY KEY (`id_document`),
  KEY `idx_dossier` (`id_dossier`),
  KEY `idx_type` (`type_document`),
  KEY `genere_par` (`genere_par`),
  CONSTRAINT `accouchement_documents_generes_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `accouchement_documents_generes_ibfk_2` FOREIGN KEY (`genere_par`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_dossier_actes
CREATE TABLE IF NOT EXISTS `accouchement_dossier_actes` (
  `id_dossier_acte` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_acte` int(11) NOT NULL,
  `qte_utilisee` decimal(10,2) NOT NULL DEFAULT 1.00,
  `prix_unitaire` decimal(12,2) NOT NULL DEFAULT 0.00,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_dossier_acte`),
  KEY `fk_acc_acte_acte` (`id_acte`),
  KEY `idx_acc_acte_dossier` (`id_dossier`),
  CONSTRAINT `fk_acc_acte_acte` FOREIGN KEY (`id_acte`) REFERENCES `location_bloc_acte` (`id_acte`),
  CONSTRAINT `fk_acc_acte_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_dossier_anesthesie
CREATE TABLE IF NOT EXISTS `accouchement_dossier_anesthesie` (
  `id_dossier_anesthesie` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_acte_anesthesie` int(11) NOT NULL,
  `id_personnel_anesthesie` int(11) NOT NULL,
  `honoraires_calcules` decimal(12,2) NOT NULL DEFAULT 0.00,
  `observations` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `honoraires_payes` tinyint(1) DEFAULT 0,
  `id_decharge_anesthesie` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_dossier_anesthesie`),
  KEY `fk_acc_anesth_acte` (`id_acte_anesthesie`),
  KEY `fk_acc_anesth_personnel` (`id_personnel_anesthesie`),
  KEY `fk_acc_anesth_created` (`created_by`),
  KEY `idx_acc_anesth_dossier` (`id_dossier`),
  CONSTRAINT `fk_acc_anesth_acte` FOREIGN KEY (`id_acte_anesthesie`) REFERENCES `anesthesie_type_acte` (`id_acte_anesthesie`),
  CONSTRAINT `fk_acc_anesth_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `fk_acc_anesth_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `fk_acc_anesth_personnel` FOREIGN KEY (`id_personnel_anesthesie`) REFERENCES `anesthesie_personnel` (`id_personnel_anesthesie`)
) ENGINE=InnoDB AUTO_INCREMENT=486 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_dossier_explorations
CREATE TABLE IF NOT EXISTS `accouchement_dossier_explorations` (
  `id_exploration` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `type_exploration` enum('ECHOGRAPHIE','LABORATOIRE','IMAGERIE','AUTRE') DEFAULT 'AUTRE',
  `nom_exploration` varchar(255) DEFAULT NULL,
  `date_exploration` date DEFAULT NULL,
  `prix` decimal(12,2) NOT NULL DEFAULT 0.00,
  `observations` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_exploration`),
  KEY `idx_acc_exploration_dossier` (`id_dossier`),
  KEY `idx_acc_exploration_type` (`type_exploration`),
  CONSTRAINT `fk_acc_exploration_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_dossier_nuitees
CREATE TABLE IF NOT EXISTS `accouchement_dossier_nuitees` (
  `id_nuitee` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_type_chambre` int(11) NOT NULL,
  `date_entree` date NOT NULL,
  `date_sortie` date NOT NULL,
  `nombre_nuitees` int(11) NOT NULL DEFAULT 0,
  `prix_unitaire` decimal(12,2) NOT NULL DEFAULT 0.00,
  `prix_total` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT 'Prix calculé après déduction des nuitées incluses',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_nuitee`),
  KEY `fk_acc_nuitee_chambre` (`id_type_chambre`),
  KEY `idx_acc_nuitee_dossier` (`id_dossier`),
  KEY `idx_acc_nuitee_dates` (`date_entree`,`date_sortie`),
  CONSTRAINT `fk_acc_nuitee_chambre` FOREIGN KEY (`id_type_chambre`) REFERENCES `type_chambre` (`id_type_chambre`),
  CONSTRAINT `fk_acc_nuitee_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=162 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_dossier_produits
CREATE TABLE IF NOT EXISTS `accouchement_dossier_produits` (
  `id_dossier_produit` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_produit` int(11) NOT NULL,
  `qte_utilisee` decimal(10,2) NOT NULL DEFAULT 1.00,
  `prix_unitaire` decimal(12,2) NOT NULL DEFAULT 0.00,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_dossier_produit`),
  KEY `fk_acc_produit_produit` (`id_produit`),
  KEY `idx_acc_produit_dossier` (`id_dossier`),
  CONSTRAINT `fk_acc_produit_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `fk_acc_produit_produit` FOREIGN KEY (`id_produit`) REFERENCES `produits` (`id_produit`)
) ENGINE=InnoDB AUTO_INCREMENT=44 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_dossiers
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
  `ddr` date DEFAULT NULL,
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
  `date_validation_finance` datetime DEFAULT NULL,
  `documents_generes` tinyint(4) DEFAULT 0 COMMENT 'Flag : documents générés (0/1)',
  `date_generation_documents` timestamp NULL DEFAULT NULL COMMENT 'Date/heure de génération des documents',
  `date_validation_medical` datetime DEFAULT NULL,
  `validateur_medical_id` int(11) DEFAULT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=251 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_gyneco_situations
CREATE TABLE IF NOT EXISTS `accouchement_gyneco_situations` (
  `id_situation` int(11) NOT NULL AUTO_INCREMENT,
  `id_gyneco` int(11) NOT NULL,
  `id_dossier` int(11) NOT NULL,
  `encaissement_patient` decimal(12,2) DEFAULT 0.00 COMMENT 'Montant encaissé du patient',
  `encaissement_gyneco` decimal(12,2) DEFAULT 0.00 COMMENT 'Encaissement du gynéco vers la clinique',
  `decaissement_clinique` decimal(12,2) DEFAULT 0.00 COMMENT 'Décaissement de la clinique vers le gynéco (négatif)',
  `compensation` decimal(12,2) DEFAULT 0.00 COMMENT 'Compensation inter-dossiers',
  `notes` text DEFAULT NULL,
  `payment_date` timestamp NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_situation`),
  KEY `fk_acc_situation_created` (`created_by`),
  KEY `idx_acc_situation_gyneco` (`id_gyneco`),
  KEY `idx_acc_situation_dossier` (`id_dossier`),
  KEY `idx_acc_situation_date` (`payment_date`),
  CONSTRAINT `fk_acc_situation_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `fk_acc_situation_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `fk_acc_situation_gyneco` FOREIGN KEY (`id_gyneco`) REFERENCES `doctors` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=252 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_operation_dossiers
CREATE TABLE IF NOT EXISTS `accouchement_operation_dossiers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_operation` int(11) NOT NULL,
  `id_dossier` int(11) NOT NULL,
  `montant` decimal(12,2) NOT NULL DEFAULT 0.00,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_acc_op_dossier` (`id_operation`,`id_dossier`),
  KEY `idx_acc_op_dossier_op` (`id_operation`),
  KEY `idx_acc_op_dossier_dossier` (`id_dossier`),
  CONSTRAINT `fk_acc_op_dossier_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `fk_acc_op_dossier_op` FOREIGN KEY (`id_operation`) REFERENCES `accouchement_operations_financieres_gyneco` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_operations_financieres_gyneco
CREATE TABLE IF NOT EXISTS `accouchement_operations_financieres_gyneco` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_gyneco` int(11) NOT NULL,
  `type_operation` enum('ENCAISSEMENT','DECHARGE','COMPENSATION') NOT NULL,
  `date` date NOT NULL,
  `montant` decimal(12,2) NOT NULL DEFAULT 0.00,
  `montant_paye` decimal(12,2) DEFAULT 0.00,
  `reste` decimal(12,2) DEFAULT 0.00,
  `id_created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `id_payment_by` int(11) DEFAULT NULL,
  `payment_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_acc_op_created` (`id_created_by`),
  KEY `fk_acc_op_payment` (`id_payment_by`),
  KEY `idx_acc_op_gyneco` (`id_gyneco`),
  KEY `idx_acc_op_type` (`type_operation`),
  KEY `idx_acc_op_date` (`date`),
  KEY `idx_acc_op_reste` (`reste`),
  CONSTRAINT `fk_acc_op_created` FOREIGN KEY (`id_created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `fk_acc_op_gyneco` FOREIGN KEY (`id_gyneco`) REFERENCES `doctors` (`id`),
  CONSTRAINT `fk_acc_op_payment` FOREIGN KEY (`id_payment_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_paiements_bons
CREATE TABLE IF NOT EXISTS `accouchement_paiements_bons` (
  `id_paiement` int(11) NOT NULL AUTO_INCREMENT,
  `id_bon` int(11) NOT NULL,
  `montant` decimal(12,2) NOT NULL,
  `mode_paiement` enum('ESPECES','CARTE','CHEQUE','VIREMENT') NOT NULL,
  `reference_transaction` varchar(100) DEFAULT NULL,
  `numero_cheque` varchar(50) DEFAULT NULL,
  `banque` varchar(100) DEFAULT NULL,
  `date_paiement` datetime NOT NULL,
  `encaisse_par` int(11) NOT NULL,
  `caisse_id` int(11) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_paiement`),
  KEY `encaisse_par` (`encaisse_par`),
  KEY `idx_bon` (`id_bon`),
  KEY `idx_date` (`date_paiement`),
  CONSTRAINT `accouchement_paiements_bons_ibfk_1` FOREIGN KEY (`id_bon`) REFERENCES `accouchement_bons_paiement` (`id_bon`) ON DELETE CASCADE,
  CONSTRAINT `accouchement_paiements_bons_ibfk_2` FOREIGN KEY (`encaisse_par`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. accouchement_tarifs_config
CREATE TABLE IF NOT EXISTS `accouchement_tarifs_config` (
  `id_tarif` int(11) NOT NULL AUTO_INCREMENT,
  `type_tarification` enum('CONVENTION','PAYANT') NOT NULL,
  `type_accouchement` enum('VOIE_BASSE','CESARIENNE') NOT NULL,
  `forfait_supplement` decimal(12,2) DEFAULT 0.00 COMMENT 'Forfait supplément accouchement (CONVENTION)',
  `part_gyneco_externe` decimal(12,2) DEFAULT 0.00 COMMENT 'Part gynéco externe (CONVENTION)',
  `prix_base` decimal(12,2) DEFAULT 0.00 COMMENT 'Prix de base (PAYANT)',
  `part_clinique_base` decimal(12,2) DEFAULT 0.00 COMMENT 'Part clinique de base (PAYANT)',
  `honoraires_gyneco_interne` decimal(12,2) DEFAULT 0.00,
  `nuitees_incluses` int(11) DEFAULT 1,
  `est_actif` tinyint(1) DEFAULT 1,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_tarif`),
  UNIQUE KEY `uk_tarif_config` (`type_tarification`,`type_accouchement`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. acte
CREATE TABLE IF NOT EXISTS `acte` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `Bloc` varchar(255) DEFAULT NULL,
  `Medcin` varchar(255) DEFAULT NULL,
  `Patient` varchar(255) DEFAULT NULL,
  `DateStart` datetime DEFAULT NULL,
  `DateEnd` datetime DEFAULT NULL,
  `Duree` time DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=165 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. actes_routes_config
CREATE TABLE IF NOT EXISTS `actes_routes_config` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `endpoint` varchar(255) NOT NULL COMMENT 'Nom de la fonction endpoint Flask',
  `method` varchar(10) DEFAULT 'ANY' COMMENT 'GET, POST, ANY',
  `id_privilege` int(11) NOT NULL,
  `description` varchar(255) DEFAULT NULL COMMENT 'Description of the route access',
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_route` (`endpoint`,`method`),
  KEY `fk_route_privilege` (`id_privilege`),
  CONSTRAINT `fk_route_privilege` FOREIGN KEY (`id_privilege`) REFERENCES `privileges` (`id_privilege`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=371 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. actes_ui_config
CREATE TABLE IF NOT EXISTS `actes_ui_config` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `page_route` varchar(255) NOT NULL COMMENT 'Endpoint de la page (ex: manage_employees)',
  `element_selector` varchar(255) NOT NULL COMMENT 'Sélecteur CSS unique (ID ou classe)',
  `id_privilege` int(11) NOT NULL,
  `description` varchar(255) DEFAULT NULL COMMENT 'Description of the UI element',
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_ui_element` (`page_route`,`element_selector`),
  KEY `fk_ui_privilege` (`id_privilege`),
  CONSTRAINT `fk_ui_privilege` FOREIGN KEY (`id_privilege`) REFERENCES `privileges` (`id_privilege`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. anesthesie_decharge_actes
CREATE TABLE IF NOT EXISTS `anesthesie_decharge_actes` (
  `id_decharge` int(11) NOT NULL,
  `source_acte` enum('BLOC','ACCOUCHEMENT','KT','MEDECIN_INTERNE') NOT NULL,
  `id_acte_source` int(11) NOT NULL,
  `montant_honoraires` decimal(12,2) NOT NULL DEFAULT 0.00,
  PRIMARY KEY (`id_decharge`,`source_acte`,`id_acte_source`),
  CONSTRAINT `anesthesie_decharge_actes_ibfk_1` FOREIGN KEY (`id_decharge`) REFERENCES `anesthesie_decharges` (`id_decharge`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. anesthesie_decharge_tranches
CREATE TABLE IF NOT EXISTS `anesthesie_decharge_tranches` (
  `id_tranche` int(11) NOT NULL AUTO_INCREMENT,
  `id_decharge` int(11) NOT NULL,
  `numero_tranche` varchar(40) NOT NULL,
  `date_paiement` date NOT NULL,
  `montant_paye` decimal(12,2) NOT NULL DEFAULT 0.00,
  `mode_paiement` varchar(30) DEFAULT 'ESPECES',
  `reference_paiement` varchar(100) DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `est_annule` tinyint(1) DEFAULT 0,
  `annule_par` int(11) DEFAULT NULL,
  `annule_le` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_tranche`),
  KEY `id_decharge` (`id_decharge`),
  KEY `created_by` (`created_by`),
  KEY `annule_par` (`annule_par`),
  CONSTRAINT `anesthesie_decharge_tranches_ibfk_1` FOREIGN KEY (`id_decharge`) REFERENCES `anesthesie_decharges` (`id_decharge`),
  CONSTRAINT `anesthesie_decharge_tranches_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `anesthesie_decharge_tranches_ibfk_3` FOREIGN KEY (`annule_par`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. anesthesie_decharges
CREATE TABLE IF NOT EXISTS `anesthesie_decharges` (
  `id_decharge` int(11) NOT NULL AUTO_INCREMENT,
  `numero_decharge` varchar(30) NOT NULL,
  `id_personnel_anesthesie` int(11) NOT NULL,
  `date_decharge` date NOT NULL,
  `periode_debut` date DEFAULT NULL,
  `periode_fin` date DEFAULT NULL,
  `montant_total` decimal(12,2) NOT NULL DEFAULT 0.00,
  `montant_paye_total` decimal(12,2) NOT NULL DEFAULT 0.00,
  `solde_restant` decimal(12,2) NOT NULL DEFAULT 0.00,
  `nb_actes` int(11) NOT NULL DEFAULT 0,
  `nb_tranches` int(11) NOT NULL DEFAULT 0,
  `mode_paiement` varchar(30) DEFAULT 'ESPECES',
  `reference_paiement` varchar(100) DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `statut` enum('BROUILLON','VALIDE','PAIEMENT_PARTIEL','PAYE','ANNULE') DEFAULT 'BROUILLON',
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `validated_at` datetime DEFAULT NULL,
  `validated_by` int(11) DEFAULT NULL,
  `paid_at` datetime DEFAULT NULL,
  `paid_by` int(11) DEFAULT NULL,
  `est_annule` tinyint(1) DEFAULT 0,
  `annule_par` int(11) DEFAULT NULL,
  `annule_le` datetime DEFAULT NULL,
  `motif_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_decharge`),
  UNIQUE KEY `numero_decharge` (`numero_decharge`),
  KEY `id_personnel_anesthesie` (`id_personnel_anesthesie`),
  KEY `created_by` (`created_by`),
  KEY `validated_by` (`validated_by`),
  KEY `paid_by` (`paid_by`),
  KEY `annule_par` (`annule_par`),
  CONSTRAINT `anesthesie_decharges_ibfk_1` FOREIGN KEY (`id_personnel_anesthesie`) REFERENCES `anesthesie_personnel` (`id_personnel_anesthesie`),
  CONSTRAINT `anesthesie_decharges_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `anesthesie_decharges_ibfk_3` FOREIGN KEY (`validated_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `anesthesie_decharges_ibfk_4` FOREIGN KEY (`paid_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `anesthesie_decharges_ibfk_5` FOREIGN KEY (`annule_par`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. anesthesie_intervenant_type
CREATE TABLE IF NOT EXISTS `anesthesie_intervenant_type` (
  `id_type_intervenant` int(11) NOT NULL AUTO_INCREMENT,
  `nom_type` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `est_actif` tinyint(1) DEFAULT 1,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_type_intervenant`),
  UNIQUE KEY `nom_type` (`nom_type`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. anesthesie_personnel
CREATE TABLE IF NOT EXISTS `anesthesie_personnel` (
  `id_personnel_anesthesie` int(11) NOT NULL AUTO_INCREMENT,
  `nom` varchar(100) NOT NULL,
  `prenom` varchar(100) NOT NULL,
  `id_type_intervenant` int(11) NOT NULL,
  `est_actif` tinyint(1) DEFAULT 1,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `date_modification` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_personnel_anesthesie`),
  KEY `idx_personnel_type` (`id_type_intervenant`),
  CONSTRAINT `anesthesie_personnel_ibfk_1` FOREIGN KEY (`id_type_intervenant`) REFERENCES `anesthesie_intervenant_type` (`id_type_intervenant`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. anesthesie_tarifs
CREATE TABLE IF NOT EXISTS `anesthesie_tarifs` (
  `id_tarif` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte_anesthesie` int(11) NOT NULL,
  `id_type_intervenant` int(11) NOT NULL,
  `honoraires_base` decimal(10,2) NOT NULL COMMENT 'Honoraires de base',
  `supplement_30min` decimal(10,2) DEFAULT NULL COMMENT 'Supplément d''Honoraires par 30 minutes',
  `duree_avant_supplement` int(11) DEFAULT NULL COMMENT 'Durée avant suppléments Honoraires en minutes',
  `est_actif` tinyint(1) DEFAULT 1,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `date_modification` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_tarif`),
  UNIQUE KEY `unique_tarif` (`id_acte_anesthesie`,`id_type_intervenant`),
  KEY `id_type_intervenant` (`id_type_intervenant`),
  KEY `idx_tarif_acte` (`id_acte_anesthesie`),
  CONSTRAINT `anesthesie_tarifs_ibfk_1` FOREIGN KEY (`id_acte_anesthesie`) REFERENCES `anesthesie_type_acte` (`id_acte_anesthesie`),
  CONSTRAINT `anesthesie_tarifs_ibfk_2` FOREIGN KEY (`id_type_intervenant`) REFERENCES `anesthesie_intervenant_type` (`id_type_intervenant`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. anesthesie_type_acte
CREATE TABLE IF NOT EXISTS `anesthesie_type_acte` (
  `id_acte_anesthesie` int(11) NOT NULL AUTO_INCREMENT,
  `nom_acte` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `est_actif` tinyint(1) DEFAULT 1,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `date_modification` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `tarif_forfaitaire` decimal(10,2) DEFAULT NULL COMMENT 'Prix forfaitaire de l''acte d''anesthésie',
  PRIMARY KEY (`id_acte_anesthesie`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_boites
CREATE TABLE IF NOT EXISTS `archivage_boites` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_medecin` int(11) NOT NULL,
  `id_type_boite` int(11) NOT NULL,
  `numero_archive` varchar(50) DEFAULT NULL,
  `epaisseur_actuelle_mm` int(11) DEFAULT 0,
  `est_pleine` tinyint(1) DEFAULT 0,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `id_emplacement` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `numero_archive` (`numero_archive`),
  KEY `id_type_boite` (`id_type_boite`),
  KEY `id_emplacement` (`id_emplacement`),
  KEY `FK_archivage_boites_doctors` (`id_medecin`),
  CONSTRAINT `FK_archivage_boites_doctors` FOREIGN KEY (`id_medecin`) REFERENCES `doctors` (`id`),
  CONSTRAINT `archivage_boites_ibfk_2` FOREIGN KEY (`id_type_boite`) REFERENCES `archivage_types_boites` (`id`),
  CONSTRAINT `archivage_boites_ibfk_3` FOREIGN KEY (`id_emplacement`) REFERENCES `archivage_emplacements` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=34 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_dossiers
CREATE TABLE IF NOT EXISTS `archivage_dossiers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_boite` int(11) NOT NULL,
  `id_patient_his` varchar(50) DEFAULT NULL,
  `nom_patient` varchar(255) DEFAULT NULL,
  `type_dossier` enum('SIMPLE','CONVENTION') NOT NULL,
  `epaisseur_mm` int(11) NOT NULL,
  `date_archivage` timestamp NULL DEFAULT current_timestamp(),
  `archive_par` int(11) DEFAULT NULL,
  `source_module` varchar(50) DEFAULT NULL,
  `id_source` int(11) DEFAULT NULL,
  `statut` enum('ARCHIVE','SORTI','DESARCHIVE') NOT NULL DEFAULT 'ARCHIVE',
  PRIMARY KEY (`id`),
  KEY `id_boite` (`id_boite`),
  CONSTRAINT `archivage_dossiers_ibfk_1` FOREIGN KEY (`id_boite`) REFERENCES `archivage_boites` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=645 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_dossiers_historique
CREATE TABLE IF NOT EXISTS `archivage_dossiers_historique` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `action` enum('CREATION','DEPLACEMENT_BOITE','DEPLACEMENT_ZONE','SORTIE_TEMPORAIRE','RETOUR','DESARCHIVE') NOT NULL,
  `id_boite_avant` int(11) DEFAULT NULL,
  `id_boite_apres` int(11) DEFAULT NULL,
  `zone_avant` varchar(100) DEFAULT NULL,
  `zone_apres` varchar(100) DEFAULT NULL,
  `commentaire` text DEFAULT NULL,
  `effectue_par` int(11) NOT NULL,
  `date_action` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_hist_dossier` (`id_dossier`),
  CONSTRAINT `archivage_dossiers_historique_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `archivage_dossiers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_dossiers_sorties
CREATE TABLE IF NOT EXISTS `archivage_dossiers_sorties` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `motif` varchar(255) NOT NULL,
  `sorti_par` int(11) NOT NULL,
  `date_sortie` datetime NOT NULL DEFAULT current_timestamp(),
  `date_retour_prevue` datetime DEFAULT NULL,
  `date_retour` datetime DEFAULT NULL,
  `retourne_par` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id_dossier` (`id_dossier`),
  KEY `idx_sorties_actives` (`date_retour`),
  CONSTRAINT `archivage_dossiers_sorties_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `archivage_dossiers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_emplacements
CREATE TABLE IF NOT EXISTS `archivage_emplacements` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_rayonnage` int(11) NOT NULL,
  `colonne_x` int(11) NOT NULL,
  `ligne_y` int(11) NOT NULL,
  `est_occupe` tinyint(1) DEFAULT 0,
  `id_boite_actuelle` int(11) DEFAULT NULL,
  `id_medecin` int(11) DEFAULT NULL,
  `est_partageable` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_position` (`id_rayonnage`,`colonne_x`,`ligne_y`),
  KEY `fk_emplacement_medecin` (`id_medecin`),
  CONSTRAINT `archivage_emplacements_ibfk_1` FOREIGN KEY (`id_rayonnage`) REFERENCES `archivage_rayonnages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_emplacement_medecin` FOREIGN KEY (`id_medecin`) REFERENCES `doctors` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=176 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_emplacements_medecins
CREATE TABLE IF NOT EXISTS `archivage_emplacements_medecins` (
  `id_emplacement` int(11) NOT NULL,
  `id_medecin` int(11) NOT NULL,
  PRIMARY KEY (`id_emplacement`,`id_medecin`),
  KEY `fk_aem_medecin` (`id_medecin`),
  CONSTRAINT `fk_aem_emplacement` FOREIGN KEY (`id_emplacement`) REFERENCES `archivage_emplacements` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_aem_medecin` FOREIGN KEY (`id_medecin`) REFERENCES `doctors` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_rayonnage_specialites
CREATE TABLE IF NOT EXISTS `archivage_rayonnage_specialites` (
  `id_rayonnage` int(11) NOT NULL,
  `id_specialty` int(11) NOT NULL,
  PRIMARY KEY (`id_rayonnage`,`id_specialty`),
  KEY `id_specialty` (`id_specialty`),
  CONSTRAINT `archivage_rayonnage_specialites_ibfk_1` FOREIGN KEY (`id_rayonnage`) REFERENCES `archivage_rayonnages` (`id`) ON DELETE CASCADE,
  CONSTRAINT `archivage_rayonnage_specialites_ibfk_2` FOREIGN KEY (`id_specialty`) REFERENCES `specialty` (`id_specialty`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_rayonnages
CREATE TABLE IF NOT EXISTS `archivage_rayonnages` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nom_zone` varchar(100) NOT NULL,
  `code_etagere` varchar(50) NOT NULL,
  `nb_lignes` int(11) NOT NULL DEFAULT 7,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `largeur_cm` int(11) DEFAULT 100,
  `id_specialty` int(11) DEFAULT NULL,
  `est_interne` tinyint(1) DEFAULT 0,
  `est_partageable` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_etagere` (`nom_zone`,`code_etagere`),
  KEY `fk_rayonnage_specialty` (`id_specialty`),
  CONSTRAINT `fk_rayonnage_specialty` FOREIGN KEY (`id_specialty`) REFERENCES `specialty` (`id_specialty`)
) ENGINE=InnoDB AUTO_INCREMENT=26 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. archivage_types_boites
CREATE TABLE IF NOT EXISTS `archivage_types_boites` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nom` varchar(50) NOT NULL,
  `hauteur_cm` decimal(5,2) NOT NULL,
  `epaisseur_max_mm` int(11) NOT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `nom` (`nom`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. audit_doctor_situations
CREATE TABLE IF NOT EXISTS `audit_doctor_situations` (
  `id_audit` int(11) NOT NULL AUTO_INCREMENT,
  `action` varchar(10) NOT NULL,
  `id_doctor_situations` int(11) DEFAULT NULL,
  `id_doctor` int(11) DEFAULT NULL,
  `id_dossier` int(11) DEFAULT NULL,
  `encaissement_doctor` decimal(10,2) DEFAULT NULL,
  `decaissement_clinique` decimal(10,2) DEFAULT NULL,
  `compensation` decimal(10,2) DEFAULT NULL,
  `user_id` int(11) DEFAULT NULL,
  `action_date` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_audit`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. barcode_history
CREATE TABLE IF NOT EXISTS `barcode_history` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `product_name` varchar(255) NOT NULL,
  `gtin` varchar(20) DEFAULT NULL,
  `lot` varchar(100) DEFAULT NULL,
  `sn` varchar(100) DEFAULT NULL,
  `exp_date` date DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `barcode_history_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. bloc
CREATE TABLE IF NOT EXISTS `bloc` (
  `id_bloc` int(11) NOT NULL AUTO_INCREMENT,
  `name_bloc` varchar(255) NOT NULL,
  `ipserver` varchar(255) DEFAULT NULL,
  `port` varchar(255) DEFAULT NULL,
  `prix` decimal(10,2) NOT NULL DEFAULT 0.00,
  `duree_base` int(11) NOT NULL DEFAULT 90,
  `prix_supplement_30min` decimal(10,2) NOT NULL DEFAULT 5000.00,
  `est_actif` tinyint(1) DEFAULT 1,
  `description` text DEFAULT NULL,
  PRIMARY KEY (`id_bloc`) USING BTREE,
  UNIQUE KEY `id` (`id_bloc`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. bloc_produits_inclus
CREATE TABLE IF NOT EXISTS `bloc_produits_inclus` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_bloc` int(11) NOT NULL,
  `id_produit` int(11) NOT NULL,
  `qte` decimal(10,2) NOT NULL DEFAULT 1.00,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_bloc_produit` (`id_bloc`,`id_produit`),
  KEY `id_produit` (`id_produit`),
  CONSTRAINT `bloc_produits_inclus_ibfk_1` FOREIGN KEY (`id_bloc`) REFERENCES `bloc` (`id_bloc`) ON DELETE CASCADE,
  CONSTRAINT `bloc_produits_inclus_ibfk_2` FOREIGN KEY (`id_produit`) REFERENCES `produits` (`id_produit`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=93 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. bot_telegram_logs
CREATE TABLE IF NOT EXISTS `bot_telegram_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL COMMENT 'ID Telegram de l''utilisateur',
  `username` varchar(255) DEFAULT NULL COMMENT 'Username Telegram',
  `first_name` varchar(255) DEFAULT NULL COMMENT 'Prénom de l''utilisateur',
  `last_name` varchar(255) DEFAULT NULL COMMENT 'Nom de l''utilisateur',
  `action_type` enum('command','button','query','error','login') NOT NULL COMMENT 'Type d''action',
  `action_name` varchar(255) NOT NULL COMMENT 'Nom de la commande ou du bouton',
  `action_data` text DEFAULT NULL COMMENT 'Données supplémentaires (JSON)',
  `message_text` text DEFAULT NULL COMMENT 'Texte du message original',
  `success` tinyint(1) DEFAULT 1 COMMENT 'Action réussie ou échouée',
  `error_message` text DEFAULT NULL COMMENT 'Message d''erreur si échec',
  `created_at` timestamp NULL DEFAULT current_timestamp() COMMENT 'Date et heure de l''action',
  `session_id` varchar(100) DEFAULT NULL COMMENT 'Identifiant de session',
  `ip_address` varchar(45) DEFAULT NULL COMMENT 'Adresse IP (si disponible)',
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_action_type` (`action_type`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_user_action` (`user_id`,`action_type`,`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=48 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Logs des actions du bot Telegram Finance INAYA';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. bot_telegram_sessions
CREATE TABLE IF NOT EXISTS `bot_telegram_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `username` varchar(255) DEFAULT NULL,
  `first_name` varchar(255) DEFAULT NULL,
  `last_name` varchar(255) DEFAULT NULL,
  `first_login` timestamp NULL DEFAULT current_timestamp(),
  `last_login` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `total_commands` int(11) DEFAULT 0,
  `total_buttons` int(11) DEFAULT 0,
  `is_active` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_last_login` (`last_login`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Sessions utilisateur du bot Telegram';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. bot_telegram_stats
CREATE TABLE IF NOT EXISTS `bot_telegram_stats` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `stat_date` date NOT NULL,
  `user_id` bigint(20) NOT NULL,
  `total_actions` int(11) DEFAULT 0,
  `total_commands` int(11) DEFAULT 0,
  `total_buttons` int(11) DEFAULT 0,
  `total_errors` int(11) DEFAULT 0,
  `most_used_action` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_user_date` (`user_id`,`stat_date`),
  KEY `idx_stat_date` (`stat_date`),
  KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Statistiques quotidiennes du bot Telegram';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. bot_telegram_whitelist
CREATE TABLE IF NOT EXISTS `bot_telegram_whitelist` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL COMMENT 'ID Telegram de l''utilisateur',
  `username` varchar(255) DEFAULT NULL COMMENT 'Username Telegram (si disponible)',
  `first_name` varchar(255) DEFAULT NULL COMMENT 'Prénom',
  `last_name` varchar(255) DEFAULT NULL COMMENT 'Nom',
  `added_by` int(11) DEFAULT NULL COMMENT 'ID du personnel qui a ajouté',
  `added_at` timestamp NULL DEFAULT current_timestamp() COMMENT 'Date d''ajout',
  `is_active` tinyint(1) DEFAULT 1 COMMENT 'Utilisateur actif',
  `notes` text DEFAULT NULL COMMENT 'Notes/raison de l''ajout',
  `last_login` timestamp NULL DEFAULT NULL COMMENT 'Dernière connexion au bot',
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_is_active` (`is_active`),
  KEY `added_by` (`added_by`),
  CONSTRAINT `bot_telegram_whitelist_ibfk_1` FOREIGN KEY (`added_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Liste blanche des utilisateurs autorisés du bot Telegram';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. cles
CREATE TABLE IF NOT EXISTS `cles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `numero_cle` varchar(50) NOT NULL,
  `description` text DEFAULT NULL,
  `quantite` int(11) DEFAULT 0,
  `quantite_emprunts` int(11) DEFAULT 0,
  `quantite_manquante` int(11) DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=36 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. cles_mouvement
CREATE TABLE IF NOT EXISTS `cles_mouvement` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `cle_id` int(11) DEFAULT NULL,
  `personne_id_donne` int(11) DEFAULT NULL,
  `personne_id_prend` int(11) DEFAULT NULL,
  `date_emprunt` datetime DEFAULT NULL,
  `personne_id_retourne` int(11) DEFAULT NULL,
  `personne_id_recoit` int(11) DEFAULT NULL,
  `date_retour` datetime DEFAULT NULL,
  `personne_id_marquee_manque` int(11) DEFAULT NULL,
  `personne_id_perte` int(11) DEFAULT NULL,
  `date_marquer_manquante` datetime DEFAULT NULL,
  `personne_id_marquee_retrevie` int(11) DEFAULT NULL,
  `personne_id_retrevie` int(11) DEFAULT NULL,
  `date_retrouvie` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `FK_cles_mouvement_cles` (`cle_id`) USING BTREE,
  KEY `FK_cles_mouvement_personne_prend` (`personne_id_prend`) USING BTREE,
  KEY `FK_cles_mouvement_personne_retourne` (`personne_id_retourne`) USING BTREE,
  KEY `FK_cles_mouvement_personne_donne` (`personne_id_donne`) USING BTREE,
  KEY `FK_cles_mouvement_personne_recoit` (`personne_id_recoit`) USING BTREE,
  KEY `FK_cles_mouvement_personne_marquee` (`personne_id_marquee_manque`) USING BTREE,
  KEY `FK_cles_mouvement_personne_perte` (`personne_id_perte`) USING BTREE,
  KEY `FK_cles_mouvement_personne_retrevie` (`personne_id_retrevie`) USING BTREE,
  CONSTRAINT `FK_cles_mouvement_cles` FOREIGN KEY (`cle_id`) REFERENCES `cles` (`id`),
  CONSTRAINT `FK_cles_mouvement_personne_donne` FOREIGN KEY (`personne_id_donne`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_cles_mouvement_personne_marquee` FOREIGN KEY (`personne_id_marquee_manque`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_cles_mouvement_personne_perte` FOREIGN KEY (`personne_id_perte`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_cles_mouvement_personne_prend` FOREIGN KEY (`personne_id_prend`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_cles_mouvement_personne_recoit` FOREIGN KEY (`personne_id_recoit`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_cles_mouvement_personne_retourne` FOREIGN KEY (`personne_id_retourne`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_cles_mouvement_personne_retrevie` FOREIGN KEY (`personne_id_retrevie`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=39 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. config_clinique
CREATE TABLE IF NOT EXISTS `config_clinique` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `cle` varchar(100) NOT NULL COMMENT 'Clé de configuration (ex: NOM_CLINIQUE, NIF, etc.)',
  `valeur` text NOT NULL COMMENT 'Valeur de la configuration',
  `categorie` enum('identite','coordonnees','fiscal','bancaire','juridique','autre') DEFAULT 'autre',
  `libelle` varchar(200) NOT NULL COMMENT 'Libellé descriptif',
  `type_donnee` enum('texte','nombre','email','telephone','url') DEFAULT 'texte',
  `est_modifiable` tinyint(1) DEFAULT 1 COMMENT 'Peut être modifié via l''interface',
  `est_affiche_facture` tinyint(1) DEFAULT 0 COMMENT 'Affiché sur les factures',
  `ordre` int(11) DEFAULT 0,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `est_actif` tinyint(1) DEFAULT 1 COMMENT 'Configuration active ou archivée',
  PRIMARY KEY (`id`),
  UNIQUE KEY `cle` (`cle`),
  KEY `idx_categorie` (`categorie`),
  KEY `idx_cle` (`cle`),
  KEY `idx_actif_ordre` (`est_actif`,`ordre`),
  KEY `idx_categorie_actif` (`categorie`,`est_actif`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Configuration générale de la clinique';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. config_date
CREATE TABLE IF NOT EXISTS `config_date` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `start_date` date NOT NULL DEFAULT '2024-11-01',
  `end_date` date NOT NULL DEFAULT '2090-01-01',
  `page` varchar(50) NOT NULL DEFAULT '2090-01-01',
  PRIMARY KEY (`id`),
  KEY `FK_planning_config_personnel` (`user_id`),
  CONSTRAINT `FK_planning_config_personnel` FOREIGN KEY (`user_id`) REFERENCES `personnel` (`id_personnel`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=39 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. config_ligne_tva
CREATE TABLE IF NOT EXISTS `config_ligne_tva` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `type_ligne` varchar(50) NOT NULL COMMENT 'Type de ligne (acte, hospitalisation, etc.)',
  `config_tva_id` int(11) NOT NULL,
  `est_defaut` tinyint(1) DEFAULT 1 COMMENT 'TVA par défaut pour ce type',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_type_defaut` (`type_ligne`,`est_defaut`),
  KEY `config_tva_id` (`config_tva_id`),
  KEY `idx_type_ligne` (`type_ligne`),
  CONSTRAINT `config_ligne_tva_ibfk_1` FOREIGN KEY (`config_tva_id`) REFERENCES `config_tva` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Association types de lignes et TVA par défaut';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. config_tva
CREATE TABLE IF NOT EXISTS `config_tva` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL COMMENT 'Code unique (ex: ACTE_MEDICAL, HOSPITALISATION, DEBOURS)',
  `libelle` varchar(200) NOT NULL COMMENT 'Libellé descriptif',
  `taux_tva` decimal(5,2) NOT NULL DEFAULT 0.00 COMMENT 'Taux de TVA en %',
  `est_actif` tinyint(1) DEFAULT 1,
  `ordre` int(11) DEFAULT 0 COMMENT 'Ordre d''affichage',
  `description` text DEFAULT NULL COMMENT 'Description détaillée',
  `template_description` text DEFAULT NULL COMMENT 'Template de description à remplir par l''utilisateur',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `idx_code` (`code`),
  KEY `idx_actif` (`est_actif`),
  KEY `idx_actif_ordre` (`est_actif`,`ordre`),
  CONSTRAINT `chk_taux_valide` CHECK (`taux_tva` >= 0 and `taux_tva` <= 100)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Configuration des taux de TVA par type de prestation';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. contacts
CREATE TABLE IF NOT EXISTS `contacts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nom` varchar(255) NOT NULL,
  `Poste` varchar(255) NOT NULL,
  `numero` varchar(255) DEFAULT NULL,
  `status_phone` tinyint(1) DEFAULT 0,
  `id_personne_add` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  KEY `FKi_d_personne_add` (`id_personne_add`),
  CONSTRAINT `FKi_d_personne_add` FOREIGN KEY (`id_personne_add`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=218 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='    `telephone` VARCHAR(15) NULL DEFAULT NULL COLLATE ''utf8mb4_general_ci'',\r\n    `status_phone` TINYINT(1) NULL DEFAULT ''0'',';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. data
CREATE TABLE IF NOT EXISTS `data` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `date` varchar(255) NOT NULL,
  `time` varchar(255) NOT NULL,
  `temperature` float DEFAULT NULL,
  `humidity` float DEFAULT NULL,
  `pressure` float DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. decharges
CREATE TABLE IF NOT EXISTS `decharges` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `doctor_name` varchar(255) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `date` date DEFAULT NULL,
  `dossiers` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `id_created_par` int(11) DEFAULT NULL,
  `time_export_decharge_pdf` timestamp NULL DEFAULT NULL,
  `id_export_par` int(11) DEFAULT NULL,
  `payment` decimal(10,2) NOT NULL DEFAULT 0.00,
  `time_payment` timestamp NULL DEFAULT NULL,
  `id_payment_par` int(11) DEFAULT NULL,
  `id_doctor_kt` int(11) DEFAULT NULL,
  `id_doctor_location` int(11) DEFAULT NULL,
  `id_employe` int(11) DEFAULT NULL,
  `reste_calc` decimal(10,2) GENERATED ALWAYS AS (`amount` - `payment`) STORED,
  PRIMARY KEY (`id`),
  KEY `FK_decharges_personnel` (`id_created_par`),
  KEY `FK_decharges_personnel_2` (`id_export_par`),
  KEY `FK_decharges_personnel_3` (`id_payment_par`) USING BTREE,
  KEY `idx_decharges_doctor_location` (`id_doctor_location`),
  KEY `idx_decharges_date` (`date`),
  KEY `idx_decharges_created_at` (`created_at` DESC),
  KEY `idx_decharges_doctor_name` (`doctor_name`),
  KEY `idx_decharges_id_created_par` (`id_created_par`),
  KEY `idx_decharges_id_export_par` (`id_export_par`),
  KEY `idx_decharges_id_payment_par` (`id_payment_par`),
  KEY `idx_decharges_doctor_date` (`doctor_name`,`date` DESC),
  KEY `idx_decharges_id_doctor_kt` (`id_doctor_kt`),
  KEY `idx_decharges_id_employe` (`id_employe`),
  KEY `idx_decharges_reste_date` (`reste_calc`,`date` DESC),
  KEY `idx_decharges_reste_created` (`reste_calc`,`created_at` DESC),
  KEY `idx_decharges_reste` (`reste_calc`),
  FULLTEXT KEY `idx_decharges_fulltext` (`doctor_name`,`dossiers`),
  CONSTRAINT `FK_decharges_personnel` FOREIGN KEY (`id_created_par`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_decharges_personnel_2` FOREIGN KEY (`id_export_par`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_decharges_personnel_3` FOREIGN KEY (`id_payment_par`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=2200 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. demandes
CREATE TABLE IF NOT EXISTS `demandes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `ip_address` varchar(255) DEFAULT NULL,
  `name` varchar(255) NOT NULL,
  `type` varchar(255) NOT NULL,
  `details` text NOT NULL,
  `file_path` varchar(1000) DEFAULT NULL,
  `audio_path` varchar(255) DEFAULT NULL,
  `time_send` datetime DEFAULT current_timestamp(),
  `time_terminee` date DEFAULT NULL,
  `terminee_par` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=72 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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

-- Listage de la structure de table dbsmartv6. documentation
CREATE TABLE IF NOT EXISTS `documentation` (
  `id_doc` int(11) NOT NULL AUTO_INCREMENT,
  `titre` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `content` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  `updated_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_doc`) USING BTREE,
  KEY `created_by` (`created_by`) USING BTREE,
  KEY `updated_by` (`updated_by`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. documentation_routes
CREATE TABLE IF NOT EXISTS `documentation_routes` (
  `id_doc` int(11) NOT NULL,
  `page_route` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`id_doc`,`page_route`) USING BTREE,
  KEY `page_route` (`page_route`) USING BTREE,
  CONSTRAINT `fk_doc_routes_doc` FOREIGN KEY (`id_doc`) REFERENCES `documentation` (`id_doc`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. equipements
CREATE TABLE IF NOT EXISTS `equipements` (
  `id_equipement` int(11) NOT NULL AUTO_INCREMENT,
  `nom_equipement` varchar(100) DEFAULT NULL,
  `type_equipement` varchar(100) DEFAULT NULL,
  `reference` varchar(100) DEFAULT NULL,
  `marque` varchar(100) DEFAULT NULL,
  `serial_number` varchar(100) DEFAULT NULL,
  `ip_adresse` varchar(100) DEFAULT NULL,
  `mac_adresse` varchar(100) DEFAULT NULL,
  `login` varchar(100) DEFAULT NULL,
  `pass` varchar(100) DEFAULT NULL,
  `date_acquisition` datetime DEFAULT current_timestamp(),
  `etat` varchar(50) DEFAULT 'fonctionnel',
  `streaming_bloc` tinyint(1) DEFAULT 0,
  `salle` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id_equipement`),
  KEY `idx_ip_adresse` (`ip_adresse`)
) ENGINE=InnoDB AUTO_INCREMENT=58 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. equipements_mouvement
CREATE TABLE IF NOT EXISTS `equipements_mouvement` (
  `id` int(11) NOT NULL DEFAULT 0,
  `id_personnel` int(11) NOT NULL,
  `id_equipement` int(11) NOT NULL,
  `date_attribution` datetime DEFAULT current_timestamp(),
  `date_retour` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `FK1idpersonnel` (`id_personnel`),
  KEY `idx_id_equipement` (`id_equipement`),
  CONSTRAINT `FK1idpersonnel` FOREIGN KEY (`id_personnel`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK2idequipement` FOREIGN KEY (`id_equipement`) REFERENCES `equipements` (`id_equipement`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. facture_lignes
CREATE TABLE IF NOT EXISTS `facture_lignes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `facture_id` int(11) NOT NULL,
  `type_ligne` varchar(100) NOT NULL DEFAULT '',
  `est_debours` tinyint(1) DEFAULT 0,
  `designation` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `reference_justificatif` varchar(100) DEFAULT NULL,
  `quantite` decimal(10,2) DEFAULT 1.00,
  `prix_unitaire` decimal(10,2) NOT NULL,
  `montant_ht` decimal(10,2) NOT NULL,
  `taux_tva` decimal(5,2) DEFAULT 0.00,
  `montant_tva` decimal(10,2) DEFAULT 0.00,
  `montant_ttc` decimal(10,2) NOT NULL,
  `remise_pourcentage` decimal(5,2) DEFAULT 0.00,
  `remise_montant` decimal(10,2) DEFAULT 0.00,
  `ordre` int(11) DEFAULT 0,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_facture` (`facture_id`),
  KEY `idx_est_debours` (`est_debours`),
  KEY `idx_lignes_facture_id` (`facture_id`),
  KEY `idx_lignes_debours` (`est_debours`),
  KEY `idx_lignes_facture_ordre` (`facture_id`,`ordre`),
  KEY `idx_lignes_designation` (`designation`),
  KEY `idx_type` (`type_ligne`) USING BTREE,
  KEY `idx_lignes_type` (`type_ligne`) USING BTREE,
  FULLTEXT KEY `idx_ft_lignes_designation` (`designation`,`description`),
  CONSTRAINT `facture_lignes_ibfk_1` FOREIGN KEY (`facture_id`) REFERENCES `factures` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=270 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. factures
CREATE TABLE IF NOT EXISTS `factures` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `numero_facture` varchar(50) NOT NULL,
  `type_facture` enum('facture','proforma') DEFAULT 'facture',
  `date_facture` date NOT NULL,
  `date_echeance` date DEFAULT NULL,
  `patient_nom` varchar(100) NOT NULL,
  `patient_prenom` varchar(100) NOT NULL,
  `patient_adresse` text DEFAULT NULL,
  `patient_telephone` varchar(20) DEFAULT NULL,
  `total_ht` decimal(10,2) DEFAULT 0.00,
  `total_tva_9` decimal(10,2) DEFAULT 0.00,
  `total_tva_19` decimal(10,2) DEFAULT 0.00,
  `total_tva` decimal(10,2) DEFAULT 0.00,
  `total_ttc` decimal(10,2) DEFAULT 0.00,
  `total_debours` decimal(10,2) DEFAULT 0.00,
  `mode_paiement` enum('especes','cheque','carte','virement','autre') DEFAULT 'especes',
  `droit_timbre` decimal(10,2) DEFAULT 0.00,
  `total_net` decimal(10,2) DEFAULT 0.00,
  `remise_pourcentage` decimal(5,2) DEFAULT 0.00,
  `remise_montant` decimal(10,2) DEFAULT 0.00,
  `notes` text DEFAULT NULL,
  `conditions_paiement` text DEFAULT NULL,
  `statut` enum('brouillon','valide','annule') DEFAULT 'brouillon',
  `date_validation` datetime DEFAULT NULL,
  `valide_par` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  `patient_nif` varchar(50) DEFAULT NULL COMMENT 'Numéro d''identification fiscale du patient',
  `patient_rc` varchar(50) DEFAULT NULL COMMENT 'Registre de commerce du patient',
  `patient_article` varchar(50) DEFAULT NULL COMMENT 'Numéro d''article du patient',
  `patient_raison_sociale` varchar(255) DEFAULT NULL COMMENT 'Raison sociale si entreprise',
  `numero_cheque` varchar(100) DEFAULT NULL COMMENT 'Numéro de chèque si paiement par chèque',
  `date_annulation` datetime DEFAULT NULL,
  `annule_par` int(11) DEFAULT NULL,
  `montant_paye_caisse` decimal(10,2) DEFAULT NULL COMMENT 'Montant total payé en caisse (TTC avec timbre)',
  `proforma_origine_id` int(11) DEFAULT NULL,
  `proforma_origine_numero` varchar(50) DEFAULT NULL,
  `est_transforme` tinyint(1) DEFAULT 0,
  `patient_oid_his` varchar(50) DEFAULT NULL COMMENT 'OID du patient dans HIS',
  `patient_code_his` varchar(50) DEFAULT NULL COMMENT 'Code du patient dans HIS',
  `donnee_au_patient` tinyint(1) DEFAULT 0 COMMENT 'Indique si la facture a été remise au patient',
  `date_remise_patient` datetime DEFAULT NULL COMMENT 'Date de remise au patient',
  `remise_par` int(11) DEFAULT NULL COMMENT 'Personnel qui a remis la facture',
  PRIMARY KEY (`id`),
  UNIQUE KEY `numero_facture` (`numero_facture`),
  KEY `created_by` (`created_by`),
  KEY `valide_par` (`valide_par`),
  KEY `idx_numero` (`numero_facture`),
  KEY `idx_date` (`date_facture`),
  KEY `idx_type` (`type_facture`),
  KEY `idx_factures_patient_nif` (`patient_nif`),
  KEY `idx_factures_numero_cheque` (`numero_cheque`),
  KEY `idx_proforma_origine` (`proforma_origine_id`),
  KEY `idx_est_transforme` (`est_transforme`),
  KEY `idx_factures_type_statut` (`type_facture`,`statut`),
  KEY `idx_factures_date` (`date_facture`),
  KEY `idx_factures_patient` (`patient_nom`,`patient_prenom`),
  KEY `idx_factures_numero` (`numero_facture`),
  KEY `idx_factures_created_by` (`created_by`),
  KEY `idx_factures_type_date` (`type_facture`,`date_facture`),
  KEY `idx_factures_statut_date` (`statut`,`date_facture`),
  KEY `idx_factures_valide_par` (`valide_par`),
  KEY `idx_factures_raison_sociale` (`patient_raison_sociale`),
  KEY `idx_factures_type_statut_date` (`type_facture`,`statut`,`date_facture`),
  KEY `idx_factures_mode_paiement` (`mode_paiement`),
  KEY `idx_factures_totaux` (`total_ht`,`total_tva`,`total_ttc`),
  KEY `idx_factures_debours` (`total_debours`),
  KEY `idx_patient_oid_his` (`patient_oid_his`),
  KEY `idx_patient_code_his` (`patient_code_his`),
  KEY `fk_factures_remise_par` (`remise_par`),
  FULLTEXT KEY `idx_ft_factures_patient` (`patient_nom`,`patient_prenom`,`patient_raison_sociale`),
  CONSTRAINT `factures_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `factures_ibfk_2` FOREIGN KEY (`valide_par`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_factures_remise_par` FOREIGN KEY (`remise_par`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_proforma_origine` FOREIGN KEY (`proforma_origine_id`) REFERENCES `factures` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=87 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de fonction dbsmartv6. generate_numero_bon
DELIMITER //
CREATE FUNCTION `generate_numero_bon`() RETURNS varchar(50) CHARSET utf8mb4 COLLATE utf8mb4_general_ci
    DETERMINISTIC
BEGIN
    DECLARE nouveau_numero VARCHAR(50);
    DECLARE compteur INT;
    DECLARE annee VARCHAR(4);
    DECLARE mois VARCHAR(2);
    
    SET annee = YEAR(NOW());
    SET mois = LPAD(MONTH(NOW()), 2, '0');
    
    -- Compter les bons du mois
    SELECT COUNT(*) + 1 INTO compteur
    FROM medecin_interne_paiements
    WHERE YEAR(date_paiement) = YEAR(NOW())
    AND MONTH(date_paiement) = MONTH(NOW());
    
    SET nouveau_numero = CONCAT('BON-', annee, mois, '-', LPAD(compteur, 5, '0'));
    
    RETURN nouveau_numero;
END//
DELIMITER ;

-- Listage de la structure de fonction dbsmartv6. generate_numero_decharge_medecin
DELIMITER //
CREATE FUNCTION `generate_numero_decharge_medecin`() RETURNS varchar(50) CHARSET utf8mb4 COLLATE utf8mb4_general_ci
    DETERMINISTIC
BEGIN
    DECLARE nouveau_numero VARCHAR(50);
    DECLARE compteur INT;
    DECLARE annee VARCHAR(4);
    DECLARE mois VARCHAR(2);
    DECLARE prefix VARCHAR(20);
    
    SET annee = YEAR(NOW());
    SET mois = LPAD(MONTH(NOW()), 2, '0');
    SET prefix = CONCAT('DMI-', annee, mois);
    
    -- Compter les décharges du mois
    SELECT COUNT(*) + 1 INTO compteur
    FROM medecin_interne_decharges
    WHERE numero_decharge LIKE CONCAT(prefix, '%');
    
    SET nouveau_numero = CONCAT(prefix, '-', LPAD(compteur, 4, '0'));
    
    RETURN nouveau_numero;
END//
DELIMITER ;

-- Listage de la structure de table dbsmartv6. gyneco_interne_decharge_dossiers
CREATE TABLE IF NOT EXISTS `gyneco_interne_decharge_dossiers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_decharge` int(11) NOT NULL,
  `id_dossier` int(11) NOT NULL,
  `montant_honoraires` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_dossier_decharge` (`id_decharge`,`id_dossier`),
  KEY `idx_decharge` (`id_decharge`),
  KEY `idx_dossier` (`id_dossier`),
  CONSTRAINT `gyneco_interne_decharge_dossiers_ibfk_1` FOREIGN KEY (`id_decharge`) REFERENCES `gyneco_interne_decharges` (`id_decharge`) ON DELETE CASCADE,
  CONSTRAINT `gyneco_interne_decharge_dossiers_ibfk_2` FOREIGN KEY (`id_dossier`) REFERENCES `accouchement_dossiers` (`id_dossier`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. gyneco_interne_decharge_tranches
CREATE TABLE IF NOT EXISTS `gyneco_interne_decharge_tranches` (
  `id_tranche` int(11) NOT NULL AUTO_INCREMENT,
  `id_decharge` int(11) NOT NULL,
  `numero_tranche` varchar(50) NOT NULL,
  `date_paiement` date NOT NULL,
  `montant_paye` decimal(10,2) NOT NULL,
  `mode_paiement` enum('ESPECES','CHEQUE','VIREMENT','AUTRE') DEFAULT 'ESPECES',
  `reference_paiement` varchar(100) DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_tranche`),
  KEY `created_by` (`created_by`),
  KEY `idx_decharge` (`id_decharge`),
  KEY `idx_date` (`date_paiement`),
  CONSTRAINT `gyneco_interne_decharge_tranches_ibfk_1` FOREIGN KEY (`id_decharge`) REFERENCES `gyneco_interne_decharges` (`id_decharge`) ON DELETE CASCADE,
  CONSTRAINT `gyneco_interne_decharge_tranches_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. gyneco_interne_decharges
CREATE TABLE IF NOT EXISTS `gyneco_interne_decharges` (
  `id_decharge` int(11) NOT NULL AUTO_INCREMENT,
  `numero_decharge` varchar(50) NOT NULL,
  `id_gyneco` int(11) NOT NULL,
  `date_decharge` date NOT NULL,
  `periode_debut` date NOT NULL,
  `periode_fin` date NOT NULL,
  `montant_total` decimal(10,2) NOT NULL DEFAULT 0.00,
  `montant_paye_total` decimal(10,2) DEFAULT 0.00,
  `solde_restant` decimal(10,2) DEFAULT 0.00,
  `nb_tranches` int(11) DEFAULT 0,
  `nb_dossiers` int(11) NOT NULL DEFAULT 0,
  `mode_paiement` enum('ESPECES','CHEQUE','VIREMENT','AUTRE') DEFAULT 'ESPECES',
  `reference_paiement` varchar(100) DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `statut` enum('BROUILLON','VALIDE','PAIEMENT_PARTIEL','PAYE','ANNULE') DEFAULT 'BROUILLON',
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `validated_at` timestamp NULL DEFAULT NULL,
  `validated_by` int(11) DEFAULT NULL,
  `paid_at` timestamp NULL DEFAULT NULL,
  `paid_by` int(11) DEFAULT NULL,
  `cancelled_at` datetime DEFAULT NULL,
  `cancelled_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_decharge`),
  UNIQUE KEY `numero_decharge` (`numero_decharge`),
  KEY `created_by` (`created_by`),
  KEY `validated_by` (`validated_by`),
  KEY `paid_by` (`paid_by`),
  KEY `idx_gyneco` (`id_gyneco`),
  KEY `idx_date` (`date_decharge`),
  KEY `idx_statut` (`statut`),
  KEY `fk_decharge_cancelled_by` (`cancelled_by`),
  CONSTRAINT `fk_decharge_cancelled_by` FOREIGN KEY (`cancelled_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `gyneco_interne_decharges_ibfk_1` FOREIGN KEY (`id_gyneco`) REFERENCES `doctors` (`id`),
  CONSTRAINT `gyneco_interne_decharges_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `gyneco_interne_decharges_ibfk_3` FOREIGN KEY (`validated_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `gyneco_interne_decharges_ibfk_4` FOREIGN KEY (`paid_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. honoraires_acte
CREATE TABLE IF NOT EXISTS `honoraires_acte` (
  `id_acte` int(11) NOT NULL AUTO_INCREMENT,
  `name_acte` varchar(50) DEFAULT NULL,
  `prix_acte` decimal(10,0) DEFAULT NULL,
  `id_service` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id_acte`) USING BTREE,
  KEY `FK_honoraires_acte_services` (`id_service`),
  CONSTRAINT `FK_honoraires_acte_services` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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
) ENGINE=InnoDB AUTO_INCREMENT=58 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. it_events
CREATE TABLE IF NOT EXISTS `it_events` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `event_type` enum('server','reseau','maintenance','incident') NOT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp(),
  `status` enum('ouvert','en_cours','resolu') DEFAULT 'ouvert',
  `id_created_par` int(11) DEFAULT NULL,
  `pinned` tinyint(1) DEFAULT 0,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_actes
CREATE TABLE IF NOT EXISTS `kt_actes` (
  `id_acte` int(11) NOT NULL AUTO_INCREMENT,
  `code_cnas` varchar(100) NOT NULL DEFAULT '',
  `name_acte_kt` varchar(100) NOT NULL DEFAULT '',
  `id_specialty` int(11) NOT NULL DEFAULT 0,
  `nbr_nuit` int(11) DEFAULT 0,
  `prix_payant` decimal(10,2) DEFAULT 0.00 COMMENT 'Prix standard payante (hors convention)',
  `prix_urgence` decimal(10,2) DEFAULT 0.00 COMMENT 'Prix urgence',
  `honoraires_payant` decimal(10,2) DEFAULT 0.00 COMMENT 'Honoraires standard payante',
  `honoraires_urgence` decimal(10,2) DEFAULT 0.00 COMMENT 'Honoraires urgence',
  PRIMARY KEY (`id_acte`) USING BTREE,
  KEY `FK_forfait_actes_specialty` (`id_specialty`) USING BTREE,
  KEY `idx_code_cnass` (`code_cnas`) USING BTREE,
  KEY `idx_kt_actes_code` (`code_cnas`),
  KEY `idx_kt_actes_name` (`name_acte_kt`),
  CONSTRAINT `kt_actes_ibfk_1` FOREIGN KEY (`id_specialty`) REFERENCES `specialty` (`id_specialty`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=153 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_actes_conventions
CREATE TABLE IF NOT EXISTS `kt_actes_conventions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) NOT NULL,
  `id_convention` int(11) NOT NULL,
  `prix` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Prix clinique pour cette convention',
  `part_operateur` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Honoraires médecin pour cette convention',
  `est_actif` tinyint(1) DEFAULT 1,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_acte_convention` (`id_acte`,`id_convention`),
  KEY `idx_acte` (`id_acte`),
  KEY `idx_convention` (`id_convention`),
  CONSTRAINT `fk_ac_acte` FOREIGN KEY (`id_acte`) REFERENCES `kt_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `fk_ac_convention` FOREIGN KEY (`id_convention`) REFERENCES `kt_conventions` (`id_convention`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=191 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_conventions
CREATE TABLE IF NOT EXISTS `kt_conventions` (
  `id_convention` int(11) NOT NULL AUTO_INCREMENT,
  `code_convention` varchar(50) NOT NULL,
  `nom_convention` varchar(150) NOT NULL,
  `est_active` tinyint(1) DEFAULT 1,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_convention`),
  UNIQUE KEY `uk_code_convention` (`code_convention`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_decharges_dossiers
CREATE TABLE IF NOT EXISTS `kt_decharges_dossiers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_decharge` int(11) NOT NULL,
  `id_dossier` int(11) NOT NULL,
  `montant_dossier` decimal(10,2) NOT NULL,
  `date_ajout` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_dossier` (`id_dossier`),
  KEY `id_decharge` (`id_decharge`),
  KEY `idx_dossier_decharge` (`id_dossier`),
  CONSTRAINT `kt_decharges_dossiers_ibfk_1` FOREIGN KEY (`id_decharge`) REFERENCES `kt_decharges_paiement` (`id_decharge`) ON DELETE CASCADE,
  CONSTRAINT `kt_decharges_dossiers_ibfk_2` FOREIGN KEY (`id_dossier`) REFERENCES `kt_dossier_patient` (`id_dossier`)
) ENGINE=InnoDB AUTO_INCREMENT=387 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_decharges_paiement
CREATE TABLE IF NOT EXISTS `kt_decharges_paiement` (
  `id_decharge` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `numero_decharge` varchar(50) NOT NULL,
  `date_decharge` date NOT NULL,
  `montant_total` decimal(10,2) NOT NULL,
  `montant_paye` decimal(10,2) DEFAULT 0.00,
  `montant_restant` decimal(10,2) NOT NULL,
  `statut` enum('EN_COURS','PARTIEL','SOLDE','ANNULEE') DEFAULT 'EN_COURS',
  `observations` text DEFAULT NULL,
  `nb_dossiers` int(11) DEFAULT 0 COMMENT 'Nombre de dossiers dans la décharge',
  `id_createur` int(11) NOT NULL,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `date_modification` datetime DEFAULT NULL ON UPDATE current_timestamp(),
  `id_modificateur` int(11) DEFAULT NULL,
  `date_annulation` datetime DEFAULT NULL,
  `id_annulateur` int(11) DEFAULT NULL,
  `raison_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_decharge`),
  UNIQUE KEY `numero_decharge` (`numero_decharge`),
  KEY `id_createur` (`id_createur`),
  KEY `idx_decharge_doctor` (`id_doctor`),
  KEY `idx_decharge_statut` (`statut`),
  KEY `fk_modificateur` (`id_modificateur`),
  KEY `fk_annulateur_decharge` (`id_annulateur`),
  CONSTRAINT `fk_annulateur_decharge` FOREIGN KEY (`id_annulateur`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_modificateur` FOREIGN KEY (`id_modificateur`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `kt_decharges_paiement_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `kt_doctors` (`id`),
  CONSTRAINT `kt_decharges_paiement_ibfk_2` FOREIGN KEY (`id_createur`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=113 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_decharges_tranches
CREATE TABLE IF NOT EXISTS `kt_decharges_tranches` (
  `id_tranche` int(11) NOT NULL AUTO_INCREMENT,
  `id_decharge` int(11) NOT NULL,
  `numero_tranche` int(11) NOT NULL,
  `montant_tranche` decimal(10,2) NOT NULL,
  `date_paiement` date NOT NULL,
  `mode_paiement` enum('ESPECE','CHEQUE','VIREMENT','AUTRE') DEFAULT 'ESPECE',
  `reference_paiement` varchar(100) DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `id_createur` int(11) NOT NULL,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `statut` enum('ACTIVE','ANNULEE') DEFAULT 'ACTIVE',
  `date_annulation` datetime DEFAULT NULL,
  `id_annulateur` int(11) DEFAULT NULL,
  `raison_annulation` text DEFAULT NULL,
  PRIMARY KEY (`id_tranche`),
  KEY `id_createur` (`id_createur`),
  KEY `idx_tranche_decharge` (`id_decharge`),
  KEY `fk_annulateur_tranche` (`id_annulateur`),
  KEY `idx_tranche_statut` (`statut`),
  CONSTRAINT `fk_annulateur_tranche` FOREIGN KEY (`id_annulateur`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `kt_decharges_tranches_ibfk_1` FOREIGN KEY (`id_decharge`) REFERENCES `kt_decharges_paiement` (`id_decharge`) ON DELETE CASCADE,
  CONSTRAINT `kt_decharges_tranches_ibfk_2` FOREIGN KEY (`id_createur`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=121 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_doctor_situations
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
  CONSTRAINT `FK_kt_doctor_situations_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`),
  CONSTRAINT `FK_kt_doctor_situations_kt_dossier_patient` FOREIGN KEY (`id_dossier`) REFERENCES `kt_dossier_patient` (`id_dossier`)
) ENGINE=InnoDB AUTO_INCREMENT=2413 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_dossier_actes
CREATE TABLE IF NOT EXISTS `kt_dossier_actes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_acte` int(11) NOT NULL,
  `id_convention` int(11) DEFAULT NULL,
  `convention` varchar(50) DEFAULT '',
  `part_operateur` decimal(10,0) DEFAULT 0,
  `part_clinique_convention` decimal(10,0) DEFAULT 0,
  `part_clinique_esp` decimal(10,0) DEFAULT 0,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `FK_dossier_actes_dossier` (`id_dossier`) USING BTREE,
  KEY `FK_dossier_actes_actes` (`id_acte`) USING BTREE,
  KEY `idx_kt_dossier_actes_dossier` (`id_dossier`),
  KEY `idx_kt_dossier_actes_acte` (`id_acte`),
  KEY `idx_kt_dossier_actes_convention` (`convention`),
  KEY `idx_kt_dossier_actes_combined` (`id_dossier`,`id_acte`),
  KEY `idx_dossier_actes_convention` (`id_convention`),
  CONSTRAINT `FK_dossier_actes_actes` FOREIGN KEY (`id_acte`) REFERENCES `kt_actes` (`id_acte`) ON UPDATE CASCADE,
  CONSTRAINT `FK_kt_dossier_actes_kt_dossier_patient` FOREIGN KEY (`id_dossier`) REFERENCES `kt_dossier_patient` (`id_dossier`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dossier_actes_convention` FOREIGN KEY (`id_convention`) REFERENCES `kt_conventions` (`id_convention`)
) ENGINE=InnoDB AUTO_INCREMENT=2776 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_dossier_anesthesie
CREATE TABLE IF NOT EXISTS `kt_dossier_anesthesie` (
  `id_dossier_anesthesie` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_acte_anesthesie` int(11) NOT NULL,
  `id_personnel_anesthesie` int(11) NOT NULL,
  `duree_reelle` int(11) DEFAULT NULL COMMENT 'Durée réelle en minutes',
  `honoraires_calcules` decimal(10,2) DEFAULT 0.00,
  `observations` text DEFAULT NULL,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `honoraires_payes` tinyint(1) DEFAULT 0,
  `id_decharge_anesthesie` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_dossier_anesthesie`),
  KEY `id_acte_anesthesie` (`id_acte_anesthesie`),
  KEY `idx_dossier` (`id_dossier`),
  KEY `idx_personnel` (`id_personnel_anesthesie`),
  KEY `idx_date` (`date_creation`),
  CONSTRAINT `kt_dossier_anesthesie_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `kt_dossier_patient` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `kt_dossier_anesthesie_ibfk_2` FOREIGN KEY (`id_acte_anesthesie`) REFERENCES `anesthesie_type_acte` (`id_acte_anesthesie`),
  CONSTRAINT `kt_dossier_anesthesie_ibfk_3` FOREIGN KEY (`id_personnel_anesthesie`) REFERENCES `anesthesie_personnel` (`id_personnel_anesthesie`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_dossier_patient
CREATE TABLE IF NOT EXISTS `kt_dossier_patient` (
  `id_dossier` int(11) NOT NULL AUTO_INCREMENT,
  `n_admission` int(200) DEFAULT 0,
  `id_doctor` int(11) NOT NULL,
  `patient` varchar(100) NOT NULL DEFAULT '',
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
  `patient_oid_his` int(11) DEFAULT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=2178 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_dossier_patient_backup
CREATE TABLE IF NOT EXISTS `kt_dossier_patient_backup` (
  `id_dossier` int(11) NOT NULL DEFAULT 0,
  `n_admission` int(200) DEFAULT 0,
  `id_doctor` int(11) NOT NULL,
  `patient` varchar(100) NOT NULL DEFAULT '',
  `urgence` tinyint(1) DEFAULT 0,
  `acte_date` date DEFAULT NULL,
  `nbr_nuite` int(11) DEFAULT 0,
  `vip` tinyint(1) DEFAULT 0,
  `nbr_nuite_conjoint` int(11) DEFAULT 0,
  `prix_hospitalisation` decimal(10,2) DEFAULT 0.00,
  `prix_conjoint` decimal(10,2) DEFAULT 0.00,
  `extras` decimal(10,2) DEFAULT 0.00,
  `part_operateur_extrat` decimal(10,2) DEFAULT 0.00,
  `part_operateur` decimal(10,2) DEFAULT 0.00,
  `prix_dossier_convention` decimal(10,2) DEFAULT 0.00,
  `prix_dossier_esp` decimal(10,2) DEFAULT 0.00,
  `payment` decimal(10,2) DEFAULT 0.00,
  `total_calculé` decimal(10,2) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_dossier_produits
CREATE TABLE IF NOT EXISTS `kt_dossier_produits` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_produit` int(11) NOT NULL,
  `qte` int(11) NOT NULL DEFAULT 1,
  `prix_unitaire` decimal(10,2) NOT NULL,
  `date_ajout` datetime DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `id_dossier` (`id_dossier`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_medecin_tarifs
CREATE TABLE IF NOT EXISTS `kt_medecin_tarifs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `id_acte` int(11) NOT NULL,
  `id_convention` int(11) DEFAULT NULL COMMENT 'NULL = tarif payante hors convention',
  `est_urgence` tinyint(1) DEFAULT 0 COMMENT '1 = tarif pour cas urgence',
  `prix` decimal(10,2) NOT NULL DEFAULT 0.00,
  `part_operateur` decimal(10,2) NOT NULL DEFAULT 0.00,
  `est_actif` tinyint(1) DEFAULT 1,
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_medecin_acte_conv` (`id_doctor`,`id_acte`,`id_convention`,`est_urgence`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_acte` (`id_acte`),
  KEY `idx_convention` (`id_convention`),
  CONSTRAINT `fk_mt_acte` FOREIGN KEY (`id_acte`) REFERENCES `kt_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `fk_mt_convention` FOREIGN KEY (`id_convention`) REFERENCES `kt_conventions` (`id_convention`) ON DELETE SET NULL,
  CONSTRAINT `fk_mt_doctor` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_programme
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
  CONSTRAINT `FK_kt_programme_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. kt_verifications_log
CREATE TABLE IF NOT EXISTS `kt_verifications_log` (
  `id_verification` int(11) NOT NULL AUTO_INCREMENT,
  `numero_decharge` varchar(50) NOT NULL,
  `date_verification` datetime NOT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `user_agent` text DEFAULT NULL,
  `is_valid` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id_verification`),
  KEY `idx_numero` (`numero_decharge`),
  KEY `idx_date` (`date_verification`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_acte
CREATE TABLE IF NOT EXISTS `location_bloc_acte` (
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

-- Listage de la structure de table dbsmartv6. location_bloc_doctor_situations
CREATE TABLE IF NOT EXISTS `location_bloc_doctor_situations` (
  `id_doctor_situations` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) DEFAULT NULL,
  `id_dossier` int(11) DEFAULT NULL,
  `encaissement_doctor` decimal(10,2) DEFAULT 0.00,
  `encaissement_patient` decimal(10,2) DEFAULT 0.00,
  `decaissement_clinique` decimal(10,2) DEFAULT 0.00,
  `compensation` decimal(10,2) DEFAULT 0.00,
  `payment_date` timestamp NULL DEFAULT current_timestamp(),
  `notes` text DEFAULT NULL COMMENT 'Notes pour traçabilité (compensation, décharge, etc.)',
  PRIMARY KEY (`id_doctor_situations`) USING BTREE,
  KEY `id_doctor` (`id_doctor`) USING BTREE,
  KEY `FK_doctor_payments_dossier_patient` (`id_dossier`),
  KEY `idx_doctor_situations_dossier` (`id_dossier`),
  KEY `idx_doctor_situations_doctor` (`id_doctor`),
  KEY `idx_doctor_situations_date` (`payment_date`),
  KEY `idx_composite_doctor_date` (`id_doctor`,`payment_date`),
  KEY `idx_amounts` (`encaissement_doctor`,`decaissement_clinique`,`compensation`),
  KEY `idx_situations_composite` (`id_doctor`,`id_dossier`),
  KEY `idx_situations_dossier` (`id_dossier`),
  KEY `idx_situations_dossier_date` (`id_dossier`,`payment_date` DESC),
  CONSTRAINT `FK_doctor_payments_dossier_patient` FOREIGN KEY (`id_dossier`) REFERENCES `location_bloc_dossier_patient` (`id_dossier`),
  CONSTRAINT `location_bloc_doctor_situations_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=531 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_dossier_anesthesie
CREATE TABLE IF NOT EXISTS `location_bloc_dossier_anesthesie` (
  `id_dossier_anesthesie` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_acte_anesthesie` int(11) NOT NULL,
  `id_personnel_anesthesie` int(11) NOT NULL,
  `duree_reelle` int(11) DEFAULT NULL COMMENT 'Durée réelle en minutes',
  `honoraires_calcules` decimal(10,2) NOT NULL,
  `observations` text DEFAULT NULL,
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  `honoraires_payes` tinyint(1) DEFAULT 0,
  `id_decharge_anesthesie` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_dossier_anesthesie`),
  KEY `id_acte_anesthesie` (`id_acte_anesthesie`),
  KEY `created_by` (`created_by`),
  KEY `idx_anesthesie_dossier` (`id_dossier`),
  KEY `idx_anesthesie_personnel` (`id_personnel_anesthesie`),
  CONSTRAINT `location_bloc_dossier_anesthesie_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `location_bloc_dossier_patient` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `location_bloc_dossier_anesthesie_ibfk_2` FOREIGN KEY (`id_acte_anesthesie`) REFERENCES `anesthesie_type_acte` (`id_acte_anesthesie`),
  CONSTRAINT `location_bloc_dossier_anesthesie_ibfk_3` FOREIGN KEY (`id_personnel_anesthesie`) REFERENCES `anesthesie_personnel` (`id_personnel_anesthesie`),
  CONSTRAINT `location_bloc_dossier_anesthesie_ibfk_4` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=731 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_dossier_explorations
CREATE TABLE IF NOT EXISTS `location_bloc_dossier_explorations` (
  `id_exploration` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `type_exploration` enum('IMAGERIE','LABORATOIRE','AUTRE') NOT NULL,
  `nom_exploration` varchar(200) DEFAULT NULL,
  `date_exploration` date DEFAULT NULL,
  `prix` decimal(10,2) NOT NULL,
  `observations` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_exploration`),
  KEY `id_dossier` (`id_dossier`),
  CONSTRAINT `location_bloc_dossier_explorations_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `location_bloc_dossier_patient` (`id_dossier`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=187 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_dossier_nuitees
CREATE TABLE IF NOT EXISTS `location_bloc_dossier_nuitees` (
  `id_nuitee` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_type_chambre` int(11) NOT NULL,
  `date_entree` date NOT NULL,
  `date_sortie` date NOT NULL,
  `nombre_nuitees` int(11) NOT NULL,
  `nuit_pre_op_gratuite` tinyint(1) DEFAULT 0,
  `prix_unitaire` decimal(10,2) NOT NULL,
  `prix_total` decimal(10,2) NOT NULL,
  `observations` text DEFAULT NULL,
  PRIMARY KEY (`id_nuitee`),
  KEY `id_dossier` (`id_dossier`),
  KEY `id_type_chambre` (`id_type_chambre`),
  CONSTRAINT `location_bloc_dossier_nuitees_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `location_bloc_dossier_patient` (`id_dossier`) ON DELETE CASCADE,
  CONSTRAINT `location_bloc_dossier_nuitees_ibfk_2` FOREIGN KEY (`id_type_chambre`) REFERENCES `type_chambre` (`id_type_chambre`)
) ENGINE=InnoDB AUTO_INCREMENT=400 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_dossier_patient
CREATE TABLE IF NOT EXISTS `location_bloc_dossier_patient` (
  `id_dossier` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `patient` varchar(100) NOT NULL DEFAULT '',
  `patient_oid_his` int(11) DEFAULT NULL,
  `forfait_id` int(11) DEFAULT NULL,
  `location_date` date DEFAULT NULL,
  `heure_operation` time DEFAULT NULL,
  `nom_acte` varchar(255) DEFAULT NULL,
  `type_tarification` enum('DUREE','FORFAIT') NOT NULL DEFAULT 'DUREE',
  `duree_reelle` int(11) DEFAULT NULL COMMENT 'Durée réelle en minutes',
  `id_bloc` int(11) NOT NULL,
  `prix_bloc` decimal(10,2) DEFAULT 0.00,
  `prix_supplement_duree` decimal(10,2) DEFAULT 0.00 COMMENT 'Supplément si dépassement',
  `prix_produits_supplementaires` decimal(10,2) DEFAULT 0.00 COMMENT 'Produits hors forfait',
  `prix_nuitees` decimal(10,2) DEFAULT 0.00,
  `prix_explorations` decimal(10,2) DEFAULT 0.00,
  `prix_anesthesie` decimal(10,2) DEFAULT 0.00,
  `prix_total` decimal(10,2) DEFAULT 0.00 COMMENT 'Prix total facturé',
  `montant_paye_caisse` decimal(10,2) DEFAULT 0.00,
  `difference_paiement` decimal(10,2) DEFAULT 0.00,
  `statut_paiement` enum('EQUILIBRE','SURPLUS_CLINIQUE','COMPLEMENT_MEDECIN','AUCUN_PAIEMENT') DEFAULT 'AUCUN_PAIEMENT',
  `date_creation` timestamp NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `qr_uuid` char(36) DEFAULT uuid() COMMENT 'UUID permanent pour QR Code dossier',
  PRIMARY KEY (`id_dossier`) USING BTREE,
  UNIQUE KEY `qr_uuid` (`qr_uuid`),
  KEY `doctor_id` (`id_doctor`) USING BTREE,
  KEY `Index_patient` (`patient`) USING BTREE,
  KEY `idx_acte_date` (`location_date`) USING BTREE,
  KEY `idx_dossier_doctor` (`id_doctor`),
  KEY `idx_dossier_date` (`location_date`),
  KEY `idx_dossier_statut` (`statut_paiement`),
  KEY `idx_dossier_doctor_date` (`id_doctor`,`location_date`),
  KEY `idx_patient_oid_his` (`patient_oid_his`),
  CONSTRAINT `FK_dossier_fusion_doctor` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=444 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_dossier_patient_actes
CREATE TABLE IF NOT EXISTS `location_bloc_dossier_patient_actes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_acte` int(11) NOT NULL,
  `qte_incluse` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT 'Quantité incluse dans forfait',
  `qte_utilisee` decimal(10,2) NOT NULL DEFAULT 1.00 COMMENT 'Quantité réellement utilisée',
  `prix_unitaire` decimal(10,2) NOT NULL DEFAULT 0.00,
  `source_inclusion` enum('FORFAIT','SUPPLEMENTAIRE') NOT NULL DEFAULT 'SUPPLEMENTAIRE',
  PRIMARY KEY (`id`),
  KEY `idx_id_dossier` (`id_dossier`),
  KEY `idx_id_acte` (`id_acte`),
  CONSTRAINT `FK_dossier_actes_acte` FOREIGN KEY (`id_acte`) REFERENCES `location_bloc_acte` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `FK_dossier_actes_dossier` FOREIGN KEY (`id_dossier`) REFERENCES `location_bloc_dossier_patient` (`id_dossier`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=153 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_dossier_produits
CREATE TABLE IF NOT EXISTS `location_bloc_dossier_produits` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_dossier` int(11) NOT NULL,
  `id_produit` int(11) NOT NULL,
  `qte_incluse` decimal(10,2) DEFAULT 0.00 COMMENT 'Quantité incluse dans forfait/bloc',
  `qte_utilisee` decimal(10,2) NOT NULL COMMENT 'Quantité réellement utilisée',
  `prix_unitaire` decimal(10,2) NOT NULL,
  `source_inclusion` enum('BLOC','FORFAIT','SUPPLEMENTAIRE') NOT NULL,
  PRIMARY KEY (`id`),
  KEY `dossier_produits_ibfk_1` (`id_dossier`),
  KEY `dossier_produits_ibfk_2` (`id_produit`),
  CONSTRAINT `location_bloc_dossier_produits_ibfk_1` FOREIGN KEY (`id_dossier`) REFERENCES `location_bloc_dossier_patient` (`id_dossier`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `location_bloc_dossier_produits_ibfk_2` FOREIGN KEY (`id_produit`) REFERENCES `produits` (`id_produit`) ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=6834 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_forfait_actes
CREATE TABLE IF NOT EXISTS `location_bloc_forfait_actes` (
  `id_forfait` int(11) NOT NULL AUTO_INCREMENT,
  `name_forfait` varchar(255) NOT NULL,
  `id_specialty` int(11) DEFAULT NULL,
  `duree_forfait` int(11) NOT NULL COMMENT 'Durée incluse en minutes',
  `nbr_nuit` int(11) DEFAULT 0,
  `prix_forfait` decimal(10,2) NOT NULL,
  `est_actif` tinyint(1) DEFAULT 1,
  `description` text DEFAULT NULL,
  PRIMARY KEY (`id_forfait`),
  KEY `FK_forfait_actes_specialty` (`id_specialty`),
  CONSTRAINT `FK_forfait_actes_specialty` FOREIGN KEY (`id_specialty`) REFERENCES `specialty` (`id_specialty`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=43 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_forfait_actes_inclus
CREATE TABLE IF NOT EXISTS `location_bloc_forfait_actes_inclus` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_forfait` int(11) NOT NULL,
  `id_acte` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `forfait_acte_unique` (`id_forfait`,`id_acte`),
  KEY `idx_id_forfait` (`id_forfait`),
  KEY `idx_id_acte` (`id_acte`),
  CONSTRAINT `FK_forfait_actes_acte` FOREIGN KEY (`id_acte`) REFERENCES `location_bloc_acte` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `FK_forfait_actes_forfait` FOREIGN KEY (`id_forfait`) REFERENCES `location_bloc_forfait_actes` (`id_forfait`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_forfait_actes_produits
CREATE TABLE IF NOT EXISTS `location_bloc_forfait_actes_produits` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_forfait` int(11) NOT NULL,
  `id_produit` int(11) NOT NULL,
  `qte` decimal(10,2) NOT NULL DEFAULT 1.00,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_forfait_produit` (`id_forfait`,`id_produit`),
  KEY `FK_forfait_actes_produits_forfait_actes` (`id_forfait`),
  KEY `FK_forfait_actes_produits_produits` (`id_produit`),
  CONSTRAINT `FK_forfait_actes_produits_forfait_actes` FOREIGN KEY (`id_forfait`) REFERENCES `location_bloc_forfait_actes` (`id_forfait`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `FK_forfait_actes_produits_produits` FOREIGN KEY (`id_produit`) REFERENCES `produits` (`id_produit`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=247 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_forfait_medecin
CREATE TABLE IF NOT EXISTS `location_bloc_forfait_medecin` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL COMMENT 'Médecin concerné',
  `id_forfait` int(11) NOT NULL COMMENT 'Forfait personnalisé',
  `prix_personnalise` decimal(10,2) DEFAULT NULL COMMENT 'Prix personnalisé (NULL = prix normal du forfait)',
  `est_actif` tinyint(1) NOT NULL DEFAULT 1,
  `date_debut` date DEFAULT NULL COMMENT 'Date de début de validité',
  `date_fin` date DEFAULT NULL COMMENT 'Date de fin de validité',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_doctor_forfait` (`id_doctor`,`id_forfait`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_forfait` (`id_forfait`),
  KEY `idx_actif` (`est_actif`),
  KEY `FK_forfait_medecin_created_by` (`created_by`),
  KEY `idx_forfait_medecin_dates` (`date_debut`,`date_fin`),
  CONSTRAINT `FK_forfait_medecin_created_by` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_forfait_medecin_doctor` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`) ON DELETE CASCADE,
  CONSTRAINT `FK_forfait_medecin_forfait` FOREIGN KEY (`id_forfait`) REFERENCES `location_bloc_forfait_actes` (`id_forfait`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Forfaits personnalisés par médecin';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_medecin_config
CREATE TABLE IF NOT EXISTS `location_bloc_medecin_config` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `nuitees_preop_gratuites_max` int(11) DEFAULT 0 COMMENT 'Nombre max de nuitées pré-op gratuites (0 ou 1)',
  `est_actif` tinyint(1) DEFAULT 1,
  `date_debut` date DEFAULT NULL COMMENT 'Date de début de validité',
  `date_fin` date DEFAULT NULL COMMENT 'Date de fin de validité',
  `created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_doctor_config` (`id_doctor`),
  KEY `created_by` (`created_by`),
  KEY `idx_doctor_actif` (`id_doctor`,`est_actif`),
  KEY `idx_dates` (`date_debut`,`date_fin`),
  CONSTRAINT `location_bloc_medecin_config_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`) ON DELETE CASCADE,
  CONSTRAINT `location_bloc_medecin_config_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL,
  CONSTRAINT `chk_nuitees_max` CHECK (`nuitees_preop_gratuites_max` >= 0 and `nuitees_preop_gratuites_max` <= 1)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Configuration des nuitées pré-opératoires gratuites par médecin';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_operation_dossiers
CREATE TABLE IF NOT EXISTS `location_bloc_operation_dossiers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_operation` int(11) NOT NULL,
  `id_dossier` int(11) NOT NULL,
  `montant` decimal(10,2) NOT NULL,
  `type_dossier` enum('BLOC','ACCOUCHEMENT') NOT NULL DEFAULT 'BLOC',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_dossier_operation` (`id_dossier`,`id_operation`),
  KEY `idx_operation` (`id_operation`),
  KEY `idx_dossier` (`id_dossier`),
  KEY `idx_operation_dossiers_operation` (`id_operation`),
  KEY `idx_operation_dossiers` (`id_dossier`),
  KEY `idx_op_dossiers_type` (`type_dossier`),
  KEY `idx_type_id_dossier` (`type_dossier`,`id_dossier`),
  CONSTRAINT `location_bloc_operation_dossiers_ibfk_1` FOREIGN KEY (`id_operation`) REFERENCES `location_bloc_operations_financieres_medecin` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=89 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Liaison entre les bons d''opérations et les dossiers concernés';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_operations_financieres_medecin
CREATE TABLE IF NOT EXISTS `location_bloc_operations_financieres_medecin` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `type_operation` enum('ENCAISSEMENT','DECHARGE','COMPENSATION') NOT NULL,
  `date` date NOT NULL,
  `montant` decimal(10,2) NOT NULL DEFAULT 0.00,
  `montant_paye` decimal(10,2) NOT NULL DEFAULT 0.00,
  `reste` decimal(10,2) NOT NULL DEFAULT 0.00,
  `id_created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `id_payment_by` int(11) DEFAULT NULL,
  `payment_at` timestamp NULL DEFAULT NULL,
  `id_exported_by` int(11) DEFAULT NULL,
  `exported_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_type` (`type_operation`),
  KEY `idx_date` (`date`),
  KEY `idx_reste` (`reste`),
  KEY `id_created_by` (`id_created_by`),
  KEY `id_payment_by` (`id_payment_by`),
  KEY `id_exported_by` (`id_exported_by`),
  KEY `idx_type_operation` (`type_operation`),
  KEY `idx_operations_doctor_type` (`id_doctor`,`type_operation`,`reste`),
  KEY `idx_operations_composite` (`id_doctor`,`type_operation`,`reste`),
  KEY `idx_operations_type_reste` (`type_operation`,`reste`),
  CONSTRAINT `location_bloc_operations_financieres_medecin_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`) ON DELETE CASCADE,
  CONSTRAINT `location_bloc_operations_financieres_medecin_ibfk_2` FOREIGN KEY (`id_created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `location_bloc_operations_financieres_medecin_ibfk_3` FOREIGN KEY (`id_payment_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `location_bloc_operations_financieres_medecin_ibfk_4` FOREIGN KEY (`id_exported_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=44 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Bons d''opérations financières (encaissement, décharge, compensation)';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. location_bloc_prix_chambre_medecin
CREATE TABLE IF NOT EXISTS `location_bloc_prix_chambre_medecin` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL COMMENT 'Médecin concerné',
  `id_type_chambre` int(11) NOT NULL COMMENT 'Type de chambre',
  `prix_personnalise` decimal(10,2) NOT NULL COMMENT 'Prix personnalisé pour ce médecin',
  `est_actif` tinyint(1) NOT NULL DEFAULT 1,
  `date_debut` date DEFAULT NULL,
  `date_fin` date DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_doctor_chambre` (`id_doctor`,`id_type_chambre`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_type_chambre` (`id_type_chambre`),
  KEY `idx_actif` (`est_actif`),
  KEY `FK_prix_chambre_medecin_created_by` (`created_by`),
  KEY `idx_prix_chambre_medecin_dates` (`date_debut`,`date_fin`),
  CONSTRAINT `FK_prix_chambre_medecin_created_by` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `FK_prix_chambre_medecin_doctor` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`) ON DELETE CASCADE,
  CONSTRAINT `FK_prix_chambre_medecin_type` FOREIGN KEY (`id_type_chambre`) REFERENCES `type_chambre` (`id_type_chambre`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Prix de chambres personnalisés par médecin';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_actes
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
) ENGINE=InnoDB AUTO_INCREMENT=198 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_actes_supplementaires
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

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_actes_types
CREATE TABLE IF NOT EXISTS `medecin_interne_actes_types` (
  `id_acte` int(11) NOT NULL AUTO_INCREMENT,
  `nom_acte` varchar(255) NOT NULL,
  `prix` decimal(10,2) NOT NULL DEFAULT 0.00,
  `description` text DEFAULT NULL,
  `est_actif` tinyint(1) DEFAULT 1,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_acte`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_anesthesie
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
) ENGINE=InnoDB AUTO_INCREMENT=375 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_consommables
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
) ENGINE=InnoDB AUTO_INCREMENT=74 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_consommables_medecin
CREATE TABLE IF NOT EXISTS `medecin_interne_consommables_medecin` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) NOT NULL,
  `description` varchar(255) NOT NULL,
  `prix` decimal(10,2) NOT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_acte` (`id_acte`),
  CONSTRAINT `fk_consommables_medecin_acte` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_decharge_actes
CREATE TABLE IF NOT EXISTS `medecin_interne_decharge_actes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_decharge` int(11) NOT NULL COMMENT 'Référence vers la décharge',
  `id_acte` int(11) NOT NULL COMMENT 'Référence vers l''acte médical',
  `montant_honoraires` decimal(12,2) NOT NULL COMMENT 'Montant des honoraires pour cet acte',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_decharge_acte` (`id_decharge`,`id_acte`),
  KEY `idx_decharge` (`id_decharge`),
  KEY `idx_acte` (`id_acte`),
  CONSTRAINT `fk_decharge_acte_acte` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `fk_decharge_acte_decharge` FOREIGN KEY (`id_decharge`) REFERENCES `medecin_interne_decharges` (`id_decharge`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Liaison décharges-actes pour médecins internes';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_decharge_tranches
CREATE TABLE IF NOT EXISTS `medecin_interne_decharge_tranches` (
  `id_tranche` int(11) NOT NULL AUTO_INCREMENT,
  `id_decharge` int(11) NOT NULL COMMENT 'Référence vers la décharge',
  `numero_tranche` varchar(50) NOT NULL COMMENT 'Numéro de la tranche (ex: DMI-202501-0001-T01)',
  `date_paiement` date NOT NULL COMMENT 'Date du paiement',
  `montant_paye` decimal(12,2) NOT NULL COMMENT 'Montant de cette tranche',
  `mode_paiement` enum('ESPECES','CHEQUE','CARTE','VIREMENT','TPE') NOT NULL DEFAULT 'ESPECES',
  `reference_paiement` varchar(100) DEFAULT NULL COMMENT 'Référence du paiement',
  `observations` text DEFAULT NULL,
  `created_by` int(11) DEFAULT NULL COMMENT 'Enregistré par',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_tranche`),
  UNIQUE KEY `unique_numero_tranche` (`numero_tranche`),
  KEY `idx_decharge` (`id_decharge`),
  KEY `idx_date_paiement` (`date_paiement`),
  KEY `idx_created_by` (`created_by`),
  CONSTRAINT `fk_tranche_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_tranche_decharge` FOREIGN KEY (`id_decharge`) REFERENCES `medecin_interne_decharges` (`id_decharge`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tranches de paiement pour décharges médecins internes';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_decharges
CREATE TABLE IF NOT EXISTS `medecin_interne_decharges` (
  `id_decharge` int(11) NOT NULL AUTO_INCREMENT,
  `numero_decharge` varchar(50) NOT NULL COMMENT 'Numéro unique généré automatiquement',
  `id_doctor` int(11) NOT NULL COMMENT 'Médecin interne concerné',
  `date_decharge` date NOT NULL COMMENT 'Date de création de la décharge',
  `periode_debut` date NOT NULL COMMENT 'Début de la période couverte',
  `periode_fin` date NOT NULL COMMENT 'Fin de la période couverte',
  `montant_total` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT 'Montant total des honoraires',
  `montant_paye_total` decimal(12,2) DEFAULT 0.00 COMMENT 'Montant total payé (somme des tranches)',
  `solde_restant` decimal(12,2) DEFAULT 0.00 COMMENT 'Solde restant à payer',
  `nb_actes` int(11) DEFAULT 0 COMMENT 'Nombre d''actes dans la décharge',
  `nb_tranches` int(11) DEFAULT 0 COMMENT 'Nombre de tranches de paiement',
  `mode_paiement` enum('ESPECES','CHEQUE','CARTE','VIREMENT','TPE') DEFAULT 'ESPECES',
  `reference_paiement` varchar(100) DEFAULT NULL COMMENT 'Référence du paiement (n° chèque, virement...)',
  `observations` text DEFAULT NULL,
  `statut` enum('BROUILLON','VALIDE','PAIEMENT_PARTIEL','PAYE','ANNULE') NOT NULL DEFAULT 'BROUILLON',
  `created_by` int(11) DEFAULT NULL COMMENT 'Créé par',
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `validated_by` int(11) DEFAULT NULL COMMENT 'Validé par',
  `validated_at` timestamp NULL DEFAULT NULL,
  `paid_by` int(11) DEFAULT NULL COMMENT 'Marqué comme payé par',
  `paid_at` timestamp NULL DEFAULT NULL,
  `cancelled_by` int(11) DEFAULT NULL COMMENT 'Annulé par',
  `cancelled_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id_decharge`),
  UNIQUE KEY `numero_decharge` (`numero_decharge`),
  UNIQUE KEY `unique_numero` (`numero_decharge`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_date` (`date_decharge`),
  KEY `idx_periode` (`periode_debut`,`periode_fin`),
  KEY `idx_statut` (`statut`),
  KEY `idx_created_by` (`created_by`),
  KEY `idx_validated_by` (`validated_by`),
  KEY `idx_paid_by` (`paid_by`),
  KEY `idx_cancelled_by` (`cancelled_by`),
  KEY `idx_decharge_statut_date` (`statut`,`date_decharge`),
  CONSTRAINT `fk_decharge_cancelled` FOREIGN KEY (`cancelled_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_decharge_created` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_decharge_doctor` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`),
  CONSTRAINT `fk_decharge_paid` FOREIGN KEY (`paid_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `fk_decharge_validated` FOREIGN KEY (`validated_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Décharges de paiement pour médecins internes';

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_hospitalisation
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
) ENGINE=InnoDB AUTO_INCREMENT=80 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_operation_actes
CREATE TABLE IF NOT EXISTS `medecin_interne_operation_actes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_operation` int(11) NOT NULL,
  `id_acte` int(11) NOT NULL,
  `montant` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_operation_acte` (`id_operation`,`id_acte`),
  KEY `idx_operation` (`id_operation`),
  KEY `idx_acte` (`id_acte`),
  CONSTRAINT `medecin_interne_operation_actes_ibfk_1` FOREIGN KEY (`id_operation`) REFERENCES `medecin_interne_operations_financieres` (`id_operation`) ON DELETE CASCADE,
  CONSTRAINT `medecin_interne_operation_actes_ibfk_2` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_operations_financieres
CREATE TABLE IF NOT EXISTS `medecin_interne_operations_financieres` (
  `id_operation` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `type_operation` enum('ENCAISSEMENT','DECHARGE','COMPENSATION') NOT NULL,
  `date_operation` date NOT NULL,
  `montant` decimal(10,2) NOT NULL,
  `montant_paye` decimal(10,2) DEFAULT 0.00,
  `reste` decimal(10,2) NOT NULL,
  `id_created_by` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `id_payment_by` int(11) DEFAULT NULL,
  `payment_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id_operation`),
  KEY `id_created_by` (`id_created_by`),
  KEY `id_payment_by` (`id_payment_by`),
  KEY `idx_doctor` (`id_doctor`),
  KEY `idx_type` (`type_operation`),
  KEY `idx_date` (`date_operation`),
  CONSTRAINT `medecin_interne_operations_financieres_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`),
  CONSTRAINT `medecin_interne_operations_financieres_ibfk_2` FOREIGN KEY (`id_created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `medecin_interne_operations_financieres_ibfk_3` FOREIGN KEY (`id_payment_by`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_paiements
CREATE TABLE IF NOT EXISTS `medecin_interne_paiements` (
  `id_paiement` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) NOT NULL,
  `montant_paye` decimal(12,2) NOT NULL,
  `mode_paiement` enum('ESPECES','CHEQUE','CARTE','VIREMENT','TPE') NOT NULL DEFAULT 'ESPECES',
  `numero_bon` varchar(50) DEFAULT NULL,
  `reference_paiement` varchar(100) DEFAULT NULL,
  `nom_banque` varchar(100) DEFAULT NULL,
  `date_echeance` date DEFAULT NULL,
  `observations` text DEFAULT NULL,
  `date_paiement` datetime NOT NULL DEFAULT current_timestamp(),
  `created_by` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `est_annule` tinyint(1) DEFAULT 0,
  `motif_annulation` text DEFAULT NULL,
  `annule_par` int(11) DEFAULT NULL,
  `annule_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id_paiement`),
  UNIQUE KEY `numero_bon` (`numero_bon`),
  KEY `created_by` (`created_by`),
  KEY `annule_par` (`annule_par`),
  KEY `idx_acte` (`id_acte`),
  KEY `idx_date` (`date_paiement`),
  KEY `idx_numero_bon` (`numero_bon`),
  KEY `idx_paiement_search` (`id_acte`,`est_annule`,`date_paiement`),
  CONSTRAINT `medecin_interne_paiements_ibfk_1` FOREIGN KEY (`id_acte`) REFERENCES `medecin_interne_actes` (`id_acte`) ON DELETE CASCADE,
  CONSTRAINT `medecin_interne_paiements_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `medecin_interne_paiements_ibfk_3` FOREIGN KEY (`annule_par`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_plafond_consommables
CREATE TABLE IF NOT EXISTS `medecin_interne_plafond_consommables` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_doctor` int(11) NOT NULL,
  `id_produit` int(11) NOT NULL,
  `quantite_max` int(11) NOT NULL DEFAULT 1,
  `est_actif` tinyint(1) NOT NULL DEFAULT 1,
  `created_by` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_doctor_produit` (`id_doctor`,`id_produit`),
  KEY `id_produit` (`id_produit`),
  CONSTRAINT `medecin_interne_plafond_consommables_ibfk_1` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`),
  CONSTRAINT `medecin_interne_plafond_consommables_ibfk_2` FOREIGN KEY (`id_produit`) REFERENCES `produits` (`id_produit`)
) ENGINE=InnoDB AUTO_INCREMENT=4149 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_situations
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
) ENGINE=InnoDB AUTO_INCREMENT=197 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. medecin_interne_supplements
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
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. menu_items
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

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. menu_items_admin
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

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. migration_decharges_log
CREATE TABLE IF NOT EXISTS `migration_decharges_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `date_migration` datetime DEFAULT current_timestamp(),
  `dossiers_liberes` int(11) DEFAULT NULL,
  `dossiers_assignes` int(11) DEFAULT NULL,
  `dossiers_marques_payes` int(11) DEFAULT NULL,
  `decharges_recalculees` int(11) DEFAULT NULL,
  `doublons_detectes` int(11) DEFAULT NULL,
  `incoherences_detectees` int(11) DEFAULT NULL,
  `statut` varchar(50) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. movements_stock
CREATE TABLE IF NOT EXISTS `movements_stock` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `product_id` int(11) DEFAULT NULL,
  `user_id` int(11) DEFAULT NULL,
  `movement_type` varchar(255) DEFAULT NULL,
  `quantity` int(11) DEFAULT NULL,
  `supplier` varchar(255) DEFAULT NULL,
  `person` varchar(255) DEFAULT NULL,
  `service` varchar(255) DEFAULT NULL,
  `date` datetime NOT NULL,
  `stock_type` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  KEY `product_id` (`product_id`),
  KEY `FK_movements_stock_personnel` (`user_id`),
  CONSTRAINT `FK_movements_stock_personnel` FOREIGN KEY (`user_id`) REFERENCES `personnel` (`id_personnel`),
  CONSTRAINT `movements_stock_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `stock` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. pending_tasks
CREATE TABLE IF NOT EXISTS `pending_tasks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `task_type` varchar(50) DEFAULT NULL,
  `description` text DEFAULT NULL,
  `status` enum('PENDING','PROCESSING','COMPLETED','FAILED') DEFAULT 'PENDING',
  `priority` int(11) DEFAULT 5,
  `created_at` datetime DEFAULT current_timestamp(),
  `started_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `result` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_status` (`status`),
  KEY `idx_priority` (`priority`),
  KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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

-- Listage de la structure de table dbsmartv6. personnel_roles
CREATE TABLE IF NOT EXISTS `personnel_roles` (
  `id_personnel` int(11) NOT NULL,
  `id_role` int(11) NOT NULL,
  PRIMARY KEY (`id_personnel`,`id_role`) USING BTREE,
  KEY `id_role` (`id_role`),
  CONSTRAINT `personnel_roles_ibfk_1` FOREIGN KEY (`id_personnel`) REFERENCES `personnel` (`id_personnel`) ON DELETE CASCADE,
  CONSTRAINT `personnel_roles_ibfk_2` FOREIGN KEY (`id_role`) REFERENCES `roles` (`id_role`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. planning
CREATE TABLE IF NOT EXISTS `planning` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_service` varchar(255) NOT NULL,
  `shift_date` date NOT NULL,
  `employee_id` int(11) NOT NULL,
  `shift_type` varchar(50) NOT NULL DEFAULT '',
  `id_pointage` int(50) DEFAULT 0,
  `id_created_par` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_planning` (`id_service`,`shift_date`,`employee_id`) USING BTREE,
  KEY `FK_planning_personnel` (`employee_id`),
  CONSTRAINT `FK_planning_personnel` FOREIGN KEY (`employee_id`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=2586 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. pointages
CREATE TABLE IF NOT EXISTS `pointages` (
  `id_pointage` int(11) NOT NULL AUTO_INCREMENT,
  `id_employe` int(11) NOT NULL,
  `date_pointage` date NOT NULL,
  `commentaire` varchar(255) DEFAULT NULL,
  `shift_type` varchar(50) NOT NULL,
  `id_service` int(11) NOT NULL DEFAULT 0,
  `prix` decimal(10,2) DEFAULT 0.00,
  `prix_acte` decimal(10,2) DEFAULT 0.00,
  `paiement` decimal(10,2) DEFAULT 0.00,
  `id_created_par` int(11) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_pointage`),
  KEY `FK_pointages_r_personnel` (`id_employe`),
  KEY `FK_pointages_r_services` (`id_service`),
  KEY `FK_pointages_r_personnel_2` (`id_created_par`) USING BTREE,
  CONSTRAINT `FK_pointages_r_personnel` FOREIGN KEY (`id_employe`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_pointages_r_personnel_2` FOREIGN KEY (`id_created_par`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_pointages_r_services` FOREIGN KEY (`id_service`) REFERENCES `services` (`id_service`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=2113 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. pointages_actes
CREATE TABLE IF NOT EXISTS `pointages_actes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_acte` int(11) DEFAULT NULL,
  `id_pointage` int(11) DEFAULT NULL,
  `nbr_actes` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `FK__honoraires_acte` (`id_acte`),
  KEY `FK__pointages` (`id_pointage`),
  CONSTRAINT `FK__honoraires_acte` FOREIGN KEY (`id_acte`) REFERENCES `honoraires_acte` (`id_acte`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK__pointages` FOREIGN KEY (`id_pointage`) REFERENCES `pointages` (`id_pointage`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. privileges
CREATE TABLE IF NOT EXISTS `privileges` (
  `id_privilege` int(11) NOT NULL AUTO_INCREMENT,
  `nom_privilege` varchar(100) NOT NULL,
  `type_privilege` varchar(50) DEFAULT NULL,
  `libelle_privilege` varchar(100) DEFAULT NULL,
  `description` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id_privilege`) USING BTREE,
  UNIQUE KEY `nomp` (`nom_privilege`)
) ENGINE=InnoDB AUTO_INCREMENT=224 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. produits
CREATE TABLE IF NOT EXISTS `produits` (
  `id_produit` int(11) NOT NULL AUTO_INCREMENT,
  `description` text NOT NULL,
  `prix_achat` decimal(10,2) NOT NULL DEFAULT 0.00,
  `pourcentage_marge` decimal(5,2) NOT NULL DEFAULT 50.00,
  `prix` decimal(10,2) DEFAULT NULL COMMENT 'Prix de vente calculé automatiquement',
  `est_actif` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `id_created_par` int(11) NOT NULL DEFAULT 0,
  `id_updated_par` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_produit`) USING BTREE,
  KEY `FK_produits_personnel` (`id_created_par`),
  KEY `FK_produits_personnel_updated` (`id_updated_par`),
  KEY `idx_description` (`description`(255)),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_updated_at` (`updated_at`),
  KEY `idx_prix_achat` (`prix_achat`),
  CONSTRAINT `FK_produits_personnel` FOREIGN KEY (`id_created_par`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION,
  CONSTRAINT `FK_produits_personnel_updated` FOREIGN KEY (`id_updated_par`) REFERENCES `personnel` (`id_personnel`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=532 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. rapports
CREATE TABLE IF NOT EXISTS `rapports` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `titre` varchar(255) NOT NULL,
  `details` text NOT NULL,
  `auteur` varchar(255) NOT NULL,
  `date` datetime NOT NULL DEFAULT current_timestamp(),
  `file_path` varchar(1000) DEFAULT NULL,
  `audio_path` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=51 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. reports
CREATE TABLE IF NOT EXISTS `reports` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `report_id` varchar(100) DEFAULT NULL,
  `clinic_id` varchar(100) DEFAULT NULL,
  `submitted_by` varchar(100) DEFAULT NULL,
  `submitted_by_role` varchar(50) DEFAULT NULL,
  `report_type` varchar(50) DEFAULT NULL,
  `description` text DEFAULT NULL,
  `status` varchar(30) DEFAULT NULL,
  `image_url` text DEFAULT NULL,
  `submitted_at` datetime DEFAULT NULL,
  `assigned_admin_id` varchar(100) DEFAULT NULL,
  `internal_notes` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. roles
CREATE TABLE IF NOT EXISTS `roles` (
  `id_role` int(11) NOT NULL AUTO_INCREMENT,
  `nom_role` varchar(100) NOT NULL,
  PRIMARY KEY (`id_role`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=45 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. roles_privileges
CREATE TABLE IF NOT EXISTS `roles_privileges` (
  `id_role` int(11) NOT NULL,
  `id_privilege` int(11) NOT NULL,
  PRIMARY KEY (`id_role`,`id_privilege`) USING BTREE,
  KEY `id_privilege` (`id_privilege`) USING BTREE,
  CONSTRAINT `roles_privileges_ibfk_1` FOREIGN KEY (`id_role`) REFERENCES `roles` (`id_role`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `roles_privileges_ibfk_2` FOREIGN KEY (`id_privilege`) REFERENCES `privileges` (`id_privilege`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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

-- Listage de la structure de procédure dbsmartv6. sp_calculer_balance_dossier
DELIMITER //
CREATE PROCEDURE `sp_calculer_balance_dossier`(
    IN p_id_dossier INT,
    OUT p_balance DECIMAL(10,2)
)
BEGIN
    SELECT 
        COALESCE(SUM(decaissement_clinique), 0) - 
        COALESCE(SUM(encaissement_doctor), 0) + 
        COALESCE(SUM(compensation), 0)
    INTO p_balance
    FROM doctor_situations
    WHERE id_dossier = p_id_dossier;
END//
DELIMITER ;

-- Listage de la structure de procédure dbsmartv6. sp_get_balance_dossier
DELIMITER //
CREATE PROCEDURE `sp_get_balance_dossier`(
                       IN p_id_dossier INT,
                       OUT p_balance DECIMAL(10, 2),
                       OUT p_reste DECIMAL(10, 2)
                   )
BEGIN
                       SELECT balance, reste_a_regler
                       INTO p_balance, p_reste
                       FROM v_situation_dossier
                       WHERE id_dossier = p_id_dossier;
                   END//
DELIMITER ;

-- Listage de la structure de procédure dbsmartv6. sp_recalculer_balance_dossier
DELIMITER //
CREATE PROCEDURE `sp_recalculer_balance_dossier`(
    IN p_id_dossier INT,
    IN p_type_dossier VARCHAR(20)
)
BEGIN
    DECLARE v_part DECIMAL(12,2);
    DECLARE v_enc_patient DECIMAL(12,2);
    DECLARE v_enc_medecin DECIMAL(12,2);
    DECLARE v_decaissement DECIMAL(12,2);
    DECLARE v_compensation DECIMAL(12,2);
    DECLARE v_balance DECIMAL(12,2);
    
    IF p_type_dossier = 'BLOC' THEN
        SELECT 
            dp.prix_total,
            COALESCE(SUM(ds.encaissement_patient), 0),
            COALESCE(SUM(ds.encaissement_doctor), 0),
            COALESCE(SUM(ds.decaissement_clinique), 0),
            COALESCE(SUM(ds.compensation), 0)
        INTO v_part, v_enc_patient, v_enc_medecin, v_decaissement, v_compensation
        FROM location_bloc_dossier_patient dp
        LEFT JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
        WHERE dp.id_dossier = p_id_dossier
        GROUP BY dp.id_dossier;
    ELSE
        SELECT 
            a.part_gyneco,
            COALESCE(SUM(ags.encaissement_patient), 0),
            COALESCE(SUM(ags.encaissement_gyneco), 0),
            COALESCE(SUM(ags.decaissement_clinique), 0),
            COALESCE(SUM(ags.compensation), 0)
        INTO v_part, v_enc_patient, v_enc_medecin, v_decaissement, v_compensation
        FROM accouchement_dossiers a
        LEFT JOIN accouchement_gyneco_situations ags ON a.id_dossier = ags.id_dossier
        WHERE a.id_dossier = p_id_dossier
        GROUP BY a.id_dossier;
    END IF;
    
    SET v_balance = (v_enc_patient + v_enc_medecin + v_decaissement + v_compensation) - v_part;
    
    SELECT 
        v_part as part_medecin,
        v_enc_patient as encaissement_patient,
        v_enc_medecin as encaissement_medecin,
        v_decaissement as decaissement,
        v_compensation as compensation,
        v_balance as balance,
        CASE 
            WHEN v_balance > 0.01 THEN 'CLINIQUE_DOIT_PAYER'
            WHEN v_balance < -0.01 THEN 'MEDECIN_DOIT_PAYER'
            ELSE 'EQUILIBRE'
        END as statut;
END//
DELIMITER ;

-- Listage de la structure de procédure dbsmartv6. sp_recalculer_prix_accouchement
DELIMITER //
CREATE PROCEDURE `sp_recalculer_prix_accouchement`(IN p_id_dossier INT)
BEGIN
    DECLARE v_prix_produits DECIMAL(12,2) DEFAULT 0;
    DECLARE v_prix_actes DECIMAL(12,2) DEFAULT 0;
    DECLARE v_prix_anesthesie DECIMAL(12,2) DEFAULT 0;
    DECLARE v_prix_explorations DECIMAL(12,2) DEFAULT 0;
    DECLARE v_prix_nuitees DECIMAL(12,2) DEFAULT 0;
    DECLARE v_prix_base DECIMAL(12,2) DEFAULT 0;
    DECLARE v_prix_total DECIMAL(12,2) DEFAULT 0;
    
    -- Calcul produits
    SELECT COALESCE(SUM(qte_utilisee * prix_unitaire), 0) INTO v_prix_produits
    FROM accouchement_dossier_produits WHERE id_dossier = p_id_dossier;
    
    -- Calcul actes
    SELECT COALESCE(SUM(qte_utilisee * prix_unitaire), 0) INTO v_prix_actes
    FROM accouchement_dossier_actes WHERE id_dossier = p_id_dossier;
    
    -- Calcul anesthésie
    SELECT COALESCE(SUM(honoraires_calcules), 0) INTO v_prix_anesthesie
    FROM accouchement_dossier_anesthesie WHERE id_dossier = p_id_dossier;
    
    -- Calcul explorations
    SELECT COALESCE(SUM(prix), 0) INTO v_prix_explorations
    FROM accouchement_dossier_explorations WHERE id_dossier = p_id_dossier;
    
    -- Calcul nuitées
    SELECT COALESCE(SUM(prix_total), 0) INTO v_prix_nuitees
    FROM accouchement_dossier_nuitees WHERE id_dossier = p_id_dossier;
    
    -- Prix de base
    SELECT prix_base INTO v_prix_base
    FROM accouchement_dossiers WHERE id_dossier = p_id_dossier;
    
    -- Prix total
    SET v_prix_total = v_prix_base + v_prix_produits + v_prix_actes 
                     + v_prix_anesthesie + v_prix_explorations + v_prix_nuitees;
    
    -- Mise à jour
    UPDATE accouchement_dossiers SET
        prix_produits = v_prix_produits,
        prix_actes = v_prix_actes,
        prix_anesthesie = v_prix_anesthesie,
        prix_explorations = v_prix_explorations,
        prix_nuitees = v_prix_nuitees,
        prix_total = v_prix_total
    WHERE id_dossier = p_id_dossier;
END//
DELIMITER ;

-- Listage de la structure de procédure dbsmartv6. sp_traiter_paiement
DELIMITER //
CREATE PROCEDURE `sp_traiter_paiement`(
    IN p_id_doctor INT,
    IN p_montant DECIMAL(10,2),
    IN p_type_operation VARCHAR(20),
    OUT p_montant_traite DECIMAL(10,2),
    OUT p_nb_dossiers INT
)
BEGIN
    DECLARE v_id_dossier INT;
    DECLARE v_reste DECIMAL(10,2);
    DECLARE v_montant_a_traiter DECIMAL(10,2);
    DECLARE v_montant_restant DECIMAL(10,2);
    DECLARE done INT DEFAULT FALSE;
    
    DECLARE cur_dossiers CURSOR FOR
        SELECT id_dossier, ABS(reste_a_regler) as reste
        FROM v_situation_dossier
        WHERE id_doctor = p_id_doctor
          AND (
              (p_type_operation = 'ENCAISSEMENT' AND reste_a_regler < 0) OR
              (p_type_operation = 'DECHARGE' AND reste_a_regler > 0)
          )
        ORDER BY location_date ASC;
    
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
    
    SET p_montant_traite = 0;
    SET p_nb_dossiers = 0;
    SET v_montant_restant = p_montant;
    
    OPEN cur_dossiers;
    
    read_loop: LOOP
        FETCH cur_dossiers INTO v_id_dossier, v_reste;
        
        IF done OR v_montant_restant <= 0 THEN
            LEAVE read_loop;
        END IF;
        
        SET v_montant_a_traiter = LEAST(v_montant_restant, v_reste);
        
        IF p_type_operation = 'ENCAISSEMENT' THEN
            INSERT INTO doctor_situations (
                id_doctor, id_dossier, encaissement_doctor, payment_date
            ) VALUES (
                p_id_doctor, v_id_dossier, v_montant_a_traiter, NOW()
            );
        ELSE
            INSERT INTO doctor_situations (
                id_doctor, id_dossier, decaissement_clinique, payment_date
            ) VALUES (
                p_id_doctor, v_id_dossier, v_montant_a_traiter, NOW()
            );
        END IF;
        
        SET p_montant_traite = p_montant_traite + v_montant_a_traiter;
        SET v_montant_restant = v_montant_restant - v_montant_a_traiter;
        SET p_nb_dossiers = p_nb_dossiers + 1;
    END LOOP;
    
    CLOSE cur_dossiers;
END//
DELIMITER ;

-- Listage de la structure de table dbsmartv6. specialty
CREATE TABLE IF NOT EXISTS `specialty` (
  `id_specialty` int(11) NOT NULL AUTO_INCREMENT,
  `name_specialty` varchar(50) NOT NULL,
  PRIMARY KEY (`id_specialty`),
  UNIQUE KEY `Index 2` (`name_specialty`,`id_specialty`),
  KEY `Index 3` (`name_specialty`)
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de procédure dbsmartv6. stats_medecin_complete
DELIMITER //
CREATE PROCEDURE `stats_medecin_complete`(IN p_id_doctor INT)
    READS SQL DATA
BEGIN
    SELECT
        vsm.*,
        calcul_potentiel_compensation(p_id_doctor) AS potentiel_compensation
    FROM v_situation_medecin AS vsm
    WHERE vsm.id_doctor = p_id_doctor;

    SELECT
        type_operation,
        COUNT(*)               AS nombre_operations,
        SUM(montant)           AS total_montant,
        SUM(montant_paye)      AS total_paye,
        SUM(reste)             AS total_reste,
        AVG(montant)           AS montant_moyen
    FROM operations_financieres_medecin
    WHERE id_doctor = p_id_doctor
    GROUP BY type_operation;

    SELECT
        statut_paiement,
        COUNT(*)               AS nombre_dossiers,
        SUM(prix_total)        AS total_prix,
        SUM(reste_a_regler)    AS total_reste
    FROM v_situation_dossier
    WHERE id_doctor = p_id_doctor
    GROUP BY statut_paiement;
END//
DELIMITER ;

-- Listage de la structure de table dbsmartv6. stock
CREATE TABLE IF NOT EXISTS `stock` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `item` varchar(255) NOT NULL,
  `category` varchar(255) NOT NULL,
  `quantity` int(11) NOT NULL,
  `description` text DEFAULT NULL,
  `type` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  KEY `FK_stock_personnel` (`user_id`),
  CONSTRAINT `FK_stock_personnel` FOREIGN KEY (`user_id`) REFERENCES `personnel` (`id_personnel`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. system_logs
CREATE TABLE IF NOT EXISTS `system_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `level` enum('INFO','WARNING','ERROR','DEBUG') DEFAULT 'INFO',
  `message` text DEFAULT NULL,
  `id_personnel` int(11) DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `user_agent` text DEFAULT NULL,
  `timestamp` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_timestamp` (`timestamp`),
  KEY `idx_level` (`level`),
  KEY `id_personnel` (`id_personnel`),
  CONSTRAINT `system_logs_ibfk_1` FOREIGN KEY (`id_personnel`) REFERENCES `personnel` (`id_personnel`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de table dbsmartv6. system_settings
CREATE TABLE IF NOT EXISTS `system_settings` (
  `setting_key` varchar(100) NOT NULL,
  `setting_value` text DEFAULT NULL,
  `description` text DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`setting_key`),
  KEY `idx_updated` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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

-- Listage de la structure de table dbsmartv6. user_sessions
CREATE TABLE IF NOT EXISTS `user_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_personnel` int(11) NOT NULL,
  `session_id` varchar(100) DEFAULT NULL,
  `login_time` datetime DEFAULT current_timestamp(),
  `logout_time` datetime DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `user_agent` text DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_id_personnel` (`id_personnel`),
  KEY `idx_login_time` (`login_time`),
  CONSTRAINT `user_sessions_ibfk_1` FOREIGN KEY (`id_personnel`) REFERENCES `personnel` (`id_personnel`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de vue dbsmartv6. v_accouchement_detail
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_accouchement_detail` 
);

-- Listage de la structure de vue dbsmartv6. v_accouchement_liste
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_accouchement_liste` (
	`id_dossier` INT(11) NOT NULL,
	`patiente` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_accouchement` DATE NOT NULL,
	`type_accouchement` ENUM('VOIE_BASSE','CESARIENNE') NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`type_tarification` ENUM('CONVENTION','PAYANT') NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`prix_total` DECIMAL(12,2) NULL,
	`montant_paye` DECIMAL(12,2) NULL,
	`balance_medecin` DECIMAL(10,2) NULL COMMENT 'Balance avec le gynécologue',
	`statut_paiement` ENUM('SOLDE','COMPLEMENT_PATIENT','SURPLUS_CLINIQUE','EN_ATTENTE','GYNECO_DOIT_PAYER','CLINIQUE_DOIT_PAYER') NULL COLLATE 'utf8mb4_unicode_ci',
	`mode_paiement` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`gyneco_nom` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`est_gyneco_interne` TINYINT(1) NULL,
	`badge_color` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci',
	`reste_a_payer` DECIMAL(13,2) NULL,
	`balance_absolue` DECIMAL(10,2) NULL,
	`date_format` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci',
	`date_creation` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci',
	`jours_depuis_accouchement` INT(8) NULL
);

-- Listage de la structure de vue dbsmartv6. v_accouchement_paiements
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_accouchement_paiements` (
	`id_dossier` INT(11) NOT NULL,
	`patiente` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_accouchement` DATE NOT NULL,
	`gyneco_nom` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`est_gyneco_interne` TINYINT(1) NULL,
	`prix_total` DECIMAL(12,2) NULL,
	`montant_paye` DECIMAL(12,2) NULL,
	`balance_medecin` DECIMAL(10,2) NULL COMMENT 'Balance avec le gynécologue',
	`statut_paiement` ENUM('SOLDE','COMPLEMENT_PATIENT','SURPLUS_CLINIQUE','EN_ATTENTE','GYNECO_DOIT_PAYER','CLINIQUE_DOIT_PAYER') NULL COLLATE 'utf8mb4_unicode_ci',
	`mode_paiement` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`reste_a_payer` DECIMAL(13,2) NULL,
	`balance_absolue` DECIMAL(10,2) NULL,
	`jours_attente` INT(8) NULL,
	`urgence_color` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci',
	`flux_paiement` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci'
);

-- Listage de la structure de vue dbsmartv6. v_accouchement_resume
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_accouchement_resume` (
	`id_dossier` INT(11) NOT NULL,
	`id_gyneco` INT(11) NOT NULL,
	`patiente` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_accouchement` DATE NOT NULL,
	`heure_accouchement` TIME NULL,
	`type_accouchement` ENUM('VOIE_BASSE','CESARIENNE') NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`type_tarification` ENUM('CONVENTION','PAYANT') NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`est_gyneco_interne` TINYINT(1) NULL,
	`gyneco_nom` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`gyneco_est_interne` TINYINT(1) NULL,
	`prix_base` DECIMAL(12,2) NOT NULL,
	`prix_produits` DECIMAL(12,2) NULL,
	`prix_actes` DECIMAL(12,2) NULL,
	`prix_anesthesie` DECIMAL(12,2) NULL,
	`prix_nuitees` DECIMAL(12,2) NULL COMMENT 'Suppléments nuitées uniquement',
	`prix_explorations` DECIMAL(12,2) NULL,
	`prix_total` DECIMAL(12,2) NULL,
	`supplement_gyneco` DECIMAL(12,2) NULL COMMENT 'Supplément demandé par gynéco externe',
	`part_clinique` DECIMAL(12,2) NULL,
	`part_gyneco` DECIMAL(12,2) NULL,
	`nuitees_incluses` INT(11) NULL COMMENT '1 pour voie basse, 2 pour césarienne',
	`montant_paye` DECIMAL(12,2) NULL,
	`mode_paiement` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`balance_medecin` DECIMAL(10,2) NULL COMMENT 'Balance avec le gynécologue',
	`statut_paiement` ENUM('SOLDE','COMPLEMENT_PATIENT','SURPLUS_CLINIQUE','EN_ATTENTE','GYNECO_DOIT_PAYER','CLINIQUE_DOIT_PAYER') NULL COLLATE 'utf8mb4_unicode_ci',
	`observations` TEXT NULL COLLATE 'utf8mb4_unicode_ci',
	`created_by` INT(11) NULL,
	`created_at` TIMESTAMP NULL,
	`updated_at` TIMESTAMP NULL,
	`cree_par_nom` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`reste_a_payer` DECIMAL(13,2) NULL,
	`type_gyneco` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci',
	`type_accouchement_libelle` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`type_tarification_libelle` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`mode_paiement_libelle` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`statut_paiement_libelle` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci'
);

-- Listage de la structure de vue dbsmartv6. v_accouchement_situation_gyneco
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_accouchement_situation_gyneco` (
	`id_gyneco` INT(11) NOT NULL,
	`nom_gyneco` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`est_interne` TINYINT(1) NULL,
	`total_dossiers` BIGINT(21) NOT NULL,
	`total_part_gyneco` DECIMAL(34,2) NULL,
	`total_encaisse_patient` DECIMAL(34,2) NULL,
	`total_encaisse_gyneco` DECIMAL(34,2) NULL,
	`total_decaisse` DECIMAL(34,2) NULL,
	`total_compensation` DECIMAL(34,2) NULL,
	`balance` DECIMAL(38,2) NULL
);

-- Listage de la structure de vue dbsmartv6. v_accouchement_stats
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_accouchement_stats` (
	`id_gyneco` INT(11) NOT NULL,
	`gyneco_nom` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`est_gyneco_interne` TINYINT(1) NULL,
	`total_accouchements` BIGINT(21) NOT NULL,
	`nb_voie_basse` BIGINT(21) NOT NULL,
	`nb_cesarienne` BIGINT(21) NOT NULL,
	`nb_convention` BIGINT(21) NOT NULL,
	`nb_payant` BIGINT(21) NOT NULL,
	`total_ca` DECIMAL(34,2) NULL,
	`total_encaisse` DECIMAL(34,2) NULL,
	`total_part_clinique` DECIMAL(34,2) NULL,
	`total_part_gyneco` DECIMAL(34,2) NULL,
	`balance_totale` DECIMAL(32,2) NULL,
	`moyenne_prix_total` DECIMAL(16,6) NULL,
	`moyenne_montant_paye` DECIMAL(16,6) NULL,
	`nb_solde` BIGINT(21) NOT NULL,
	`nb_en_attente` BIGINT(21) NOT NULL,
	`premier_accouchement` DATE NULL,
	`dernier_accouchement` DATE NULL
);

-- Listage de la structure de vue dbsmartv6. v_accouchements_sans_documents
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

-- Listage de la structure de vue dbsmartv6. v_config_clinique_grouped
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_config_clinique_grouped` (
	`categorie` ENUM('identite','coordonnees','fiscal','bancaire','juridique','autre') NULL COLLATE 'utf8mb4_unicode_ci',
	`config_json` MEDIUMTEXT NULL COLLATE 'utf8mb4_unicode_ci'
);

-- Listage de la structure de vue dbsmartv6. v_config_facture
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_config_facture` (
	`cle` VARCHAR(1) NOT NULL COMMENT 'Clé de configuration (ex: NOM_CLINIQUE, NIF, etc.)' COLLATE 'utf8mb4_unicode_ci',
	`valeur` TEXT NOT NULL COMMENT 'Valeur de la configuration' COLLATE 'utf8mb4_unicode_ci',
	`categorie` ENUM('identite','coordonnees','fiscal','bancaire','juridique','autre') NULL COLLATE 'utf8mb4_unicode_ci',
	`libelle` VARCHAR(1) NOT NULL COMMENT 'Libellé descriptif' COLLATE 'utf8mb4_unicode_ci'
);

-- Listage de la structure de vue dbsmartv6. v_documents_accouchements
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_documents_accouchements` (
	`id_document` INT(11) NOT NULL,
	`id_dossier` INT(11) NOT NULL,
	`patiente` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`type_document` ENUM('CERTIFICAT_ACCOUCHEMENT','CONGE_MATERNITE','COMPTE_RENDU_POST_PARTUM','COMPTE_RENDU_OPERATOIRE') NOT NULL COLLATE 'utf8mb4_uca1400_ai_ci',
	`genere_par_nom` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`date_generation` DATETIME NULL,
	`date_accouchement` DATE NULL
);

-- Listage de la structure de vue dbsmartv6. v_dossiers_a_regler
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_dossiers_a_regler` (
	`type_dossier` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_general_ci',
	`id_dossier` INT(11) NOT NULL,
	`patient` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_general_ci',
	`location_date` DATE NULL,
	`id_doctor` INT(11) NOT NULL,
	`medecin` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`part_medecin` DECIMAL(12,2) NULL,
	`reste` DECIMAL(38,2) NULL,
	`statut` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci'
);

-- Listage de la structure de vue dbsmartv6. v_dossiers_incoherents
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_dossiers_incoherents` (
	`id_dossier` INT(11) NOT NULL,
	`patiente` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_accouchement` DATE NOT NULL,
	`gyneco_paye` TINYINT(1) NULL,
	`id_decharge_gyneco` INT(11) NULL,
	`numero_decharge` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`statut_decharge` ENUM('BROUILLON','VALIDE','PAIEMENT_PARTIEL','PAYE','ANNULE') NULL COLLATE 'utf8mb4_unicode_ci',
	`type_probleme` VARCHAR(1) NULL COLLATE 'utf8mb4_uca1400_ai_ci'
);

-- Listage de la structure de vue dbsmartv6. v_dossiers_non_decharges
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_dossiers_non_decharges` (
	`id_dossier` INT(11) NOT NULL,
	`patiente` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_accouchement` DATE NOT NULL,
	`id_gyneco` INT(11) NOT NULL,
	`gyneco_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`type_accouchement` ENUM('VOIE_BASSE','CESARIENNE') NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`type_tarification` ENUM('CONVENTION','PAYANT') NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`part_gyneco` DECIMAL(12,2) NULL,
	`gyneco_paye` TINYINT(1) NULL,
	`id_decharge_gyneco` INT(11) NULL
);

-- Listage de la structure de vue dbsmartv6. v_factures_resume
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_factures_resume` (
	`id` INT(11) NOT NULL,
	`numero_facture` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`type_facture` ENUM('facture','proforma') NULL COLLATE 'utf8mb4_unicode_ci',
	`date_facture` DATE NOT NULL,
	`date_echeance` DATE NULL,
	`patient_nom` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`patient_prenom` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`patient_adresse` TEXT NULL COLLATE 'utf8mb4_unicode_ci',
	`patient_telephone` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`total_ht` DECIMAL(10,2) NULL,
	`total_tva_9` DECIMAL(10,2) NULL,
	`total_tva_19` DECIMAL(10,2) NULL,
	`total_tva` DECIMAL(10,2) NULL,
	`total_ttc` DECIMAL(10,2) NULL,
	`total_debours` DECIMAL(10,2) NULL,
	`mode_paiement` ENUM('especes','cheque','carte','virement','autre') NULL COLLATE 'utf8mb4_unicode_ci',
	`droit_timbre` DECIMAL(10,2) NULL,
	`total_net` DECIMAL(10,2) NULL,
	`remise_pourcentage` DECIMAL(5,2) NULL,
	`remise_montant` DECIMAL(10,2) NULL,
	`notes` TEXT NULL COLLATE 'utf8mb4_unicode_ci',
	`conditions_paiement` TEXT NULL COLLATE 'utf8mb4_unicode_ci',
	`statut` ENUM('brouillon','valide','annule') NULL COLLATE 'utf8mb4_unicode_ci',
	`date_validation` DATETIME NULL,
	`valide_par` INT(11) NULL,
	`created_at` TIMESTAMP NULL,
	`updated_at` TIMESTAMP NULL,
	`created_by` INT(11) NULL,
	`patient_nif` VARCHAR(1) NULL COMMENT 'Numéro d\'identification fiscale du patient' COLLATE 'utf8mb4_unicode_ci',
	`patient_rc` VARCHAR(1) NULL COMMENT 'Registre de commerce du patient' COLLATE 'utf8mb4_unicode_ci',
	`patient_article` VARCHAR(1) NULL COMMENT 'Numéro d\'article du patient' COLLATE 'utf8mb4_unicode_ci',
	`patient_raison_sociale` VARCHAR(1) NULL COMMENT 'Raison sociale si entreprise' COLLATE 'utf8mb4_unicode_ci',
	`numero_cheque` VARCHAR(1) NULL COMMENT 'Numéro de chèque si paiement par chèque' COLLATE 'utf8mb4_unicode_ci',
	`date_annulation` DATETIME NULL,
	`annule_par` INT(11) NULL,
	`montant_paye_caisse` DECIMAL(10,2) NULL COMMENT 'Montant total payé en caisse (TTC avec timbre)',
	`proforma_origine_id` INT(11) NULL,
	`proforma_origine_numero` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`est_transforme` TINYINT(1) NULL,
	`patient_oid_his` VARCHAR(1) NULL COMMENT 'OID du patient dans HIS' COLLATE 'utf8mb4_unicode_ci',
	`patient_code_his` VARCHAR(1) NULL COMMENT 'Code du patient dans HIS' COLLATE 'utf8mb4_unicode_ci',
	`donnee_au_patient` TINYINT(1) NULL COMMENT 'Indique si la facture a été remise au patient',
	`date_remise_patient` DATETIME NULL COMMENT 'Date de remise au patient',
	`remise_par` INT(11) NULL COMMENT 'Personnel qui a remis la facture',
	`patient_complet` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`nombre_lignes` BIGINT(21) NOT NULL,
	`ht_tva_9` DECIMAL(32,2) NULL,
	`ht_tva_19` DECIMAL(32,2) NULL,
	`debours_calcule` DECIMAL(32,2) NULL,
	`nombre_debours` BIGINT(21) NOT NULL,
	`createur` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`validateur` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci'
);

-- Listage de la structure de vue dbsmartv6. v_kt_decharges_completes
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_kt_decharges_completes` (
	`id_decharge` INT(11) NOT NULL,
	`id_doctor` INT(11) NOT NULL,
	`numero_decharge` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_decharge` DATE NOT NULL,
	`montant_total` DECIMAL(10,2) NOT NULL,
	`montant_paye` DECIMAL(10,2) NULL,
	`montant_restant` DECIMAL(10,2) NOT NULL,
	`statut` ENUM('EN_COURS','PARTIEL','SOLDE','ANNULEE') NULL COLLATE 'utf8mb4_unicode_ci',
	`observations` TEXT NULL COLLATE 'utf8mb4_unicode_ci',
	`id_createur` INT(11) NOT NULL,
	`date_creation` TIMESTAMP NULL,
	`id_modificateur` INT(11) NULL,
	`date_modification` DATETIME NULL,
	`id_annulateur` INT(11) NULL,
	`date_annulation` DATETIME NULL,
	`raison_annulation` TEXT NULL COLLATE 'utf8mb4_unicode_ci',
	`nom_medecin` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`name_specialty` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`nb_dossiers` BIGINT(21) NULL,
	`nb_tranches` BIGINT(21) NULL,
	`nb_tranches_annulees` BIGINT(21) NULL,
	`montant_annule` DECIMAL(32,2) NULL
);

-- Listage de la structure de vue dbsmartv6. v_kt_doctor_stats
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_kt_doctor_stats` (
	`id` INT(11) NOT NULL,
	`first_name` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_general_ci',
	`last_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`id_specialty` INT(11) NULL,
	`name_specialty` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`nb_dossiers` BIGINT(21) NOT NULL,
	`total_part_operateur` DECIMAL(32,2) NULL,
	`total_payment` DECIMAL(32,2) NULL,
	`solde` DECIMAL(33,2) NULL
);

-- Listage de la structure de vue dbsmartv6. v_medecin_interne_actes_resume
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_medecin_interne_actes_resume` (
	`id_acte` INT(11) NOT NULL,
	`patient` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`date_acte` DATE NOT NULL,
	`nom_acte` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`est_annule` TINYINT(1) NULL COMMENT 'Indique si l\'acte est annulé',
	`motif_annulation` TEXT NULL COMMENT 'Motif de l\'annulation' COLLATE 'utf8mb4_unicode_ci',
	`annule_at` DATETIME NULL COMMENT 'Date et heure d\'annulation',
	`doctor_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`nom_specialite` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`pourcentage_medecin` DECIMAL(5,2) NOT NULL,
	`prix_acte_base` DECIMAL(10,2) NOT NULL,
	`total_deductions` DECIMAL(10,2) NULL COMMENT 'Somme: consommables + hospitalisation + supplements + actes_supp + anesthesie',
	`base_calcul` DECIMAL(10,2) NULL,
	`part_medecin` DECIMAL(10,2) NULL,
	`part_clinique` DECIMAL(10,2) NULL,
	`montant_paye_caisse` DECIMAL(10,2) NULL,
	`difference_paiement` DECIMAL(10,2) NULL,
	`statut_paiement` ENUM('EQUILIBRE','COMPLEMENT_MEDECIN','SURPLUS_CLINIQUE','AUCUN_PAIEMENT') NULL COLLATE 'utf8mb4_unicode_ci',
	`balance` DECIMAL(36,2) NULL
);

-- Listage de la structure de vue dbsmartv6. v_medecin_interne_decharges_resume
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_medecin_interne_decharges_resume` (
	`id_decharge` INT(11) NOT NULL,
	`numero_decharge` VARCHAR(1) NOT NULL COMMENT 'Numéro unique généré automatiquement' COLLATE 'utf8mb4_unicode_ci',
	`date_decharge` DATE NOT NULL COMMENT 'Date de création de la décharge',
	`periode_debut` DATE NOT NULL COMMENT 'Début de la période couverte',
	`periode_fin` DATE NOT NULL COMMENT 'Fin de la période couverte',
	`medecin_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`specialite` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`nb_actes` INT(11) NULL COMMENT 'Nombre d\'actes dans la décharge',
	`montant_total` DECIMAL(12,2) NOT NULL COMMENT 'Montant total des honoraires',
	`montant_paye_total` DECIMAL(12,2) NULL COMMENT 'Montant total payé (somme des tranches)',
	`solde_restant` DECIMAL(12,2) NULL COMMENT 'Solde restant à payer',
	`nb_tranches` INT(11) NULL COMMENT 'Nombre de tranches de paiement',
	`statut` ENUM('BROUILLON','VALIDE','PAIEMENT_PARTIEL','PAYE','ANNULE') NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`mode_paiement` ENUM('ESPECES','CHEQUE','CARTE','VIREMENT','TPE') NULL COLLATE 'utf8mb4_unicode_ci',
	`created_by_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`created_at` TIMESTAMP NULL,
	`validated_by_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`validated_at` TIMESTAMP NULL,
	`paid_by_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`paid_at` TIMESTAMP NULL,
	`pourcentage_paye` DECIMAL(18,2) NULL
);

-- Listage de la structure de vue dbsmartv6. v_medecin_interne_paiements_summary
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_medecin_interne_paiements_summary` (
	`id_acte` INT(11) NOT NULL,
	`prix_acte_base` DECIMAL(10,2) NOT NULL,
	`montant_paye_caisse` DECIMAL(10,2) NULL,
	`part_medecin` DECIMAL(10,2) NULL,
	`est_annule` TINYINT(1) NULL COMMENT 'Indique si l\'acte est annulé',
	`mode_calcul` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`montant_total_a_payer` DECIMAL(15,2) NULL,
	`total_paye` DECIMAL(34,2) NULL,
	`reste_a_payer` DECIMAL(35,2) NULL,
	`nombre_paiements` BIGINT(21) NOT NULL,
	`dernier_paiement` DATETIME NULL
);

-- Listage de la structure de vue dbsmartv6. v_medecin_interne_situation_financiere
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_medecin_interne_situation_financiere` (
	`id_doctor` INT(11) NOT NULL,
	`medecin_name` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`specialite` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`total_actes` BIGINT(21) NOT NULL,
	`actes_non_payes` DECIMAL(22,0) NULL,
	`total_honoraires` DECIMAL(32,2) NULL,
	`honoraires_payes` DECIMAL(32,2) NULL,
	`honoraires_non_payes` DECIMAL(32,2) NULL,
	`nb_decharges` BIGINT(21) NOT NULL,
	`nb_decharges_payees` BIGINT(21) NOT NULL,
	`nb_decharges_en_cours` BIGINT(21) NOT NULL,
	`ca_total_genere` DECIMAL(32,2) NULL,
	`part_clinique_totale` DECIMAL(32,2) NULL,
	`total_actes_annules` BIGINT(21) NOT NULL
);

-- Listage de la structure de vue dbsmartv6. v_situation_medecin_globale
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_situation_medecin_globale` (
	`id_doctor` INT(11) NOT NULL,
	`nom_complet` VARCHAR(1) NULL COLLATE 'utf8mb4_general_ci',
	`name_specialty` VARCHAR(1) NULL COLLATE 'utf8mb4_unicode_ci',
	`total_dossiers_bloc` BIGINT(21) NULL,
	`ca_bloc` DECIMAL(32,2) NULL,
	`total_dossiers_accouchement` BIGINT(21) NULL,
	`ca_accouchement` DECIMAL(34,2) NULL,
	`balance_bloc` DECIMAL(36,2) NULL,
	`balance_accouchement` DECIMAL(38,2) NULL
);

-- Listage de la structure de vue dbsmartv6. v_tva_actives
-- Création d'une table temporaire pour palier aux erreurs de dépendances de VIEW
CREATE TABLE `v_tva_actives` (
	`id` INT(11) NOT NULL,
	`code` VARCHAR(1) NOT NULL COMMENT 'Code unique (ex: ACTE_MEDICAL, HOSPITALISATION, DEBOURS)' COLLATE 'utf8mb4_unicode_ci',
	`libelle` VARCHAR(1) NOT NULL COMMENT 'Libellé descriptif' COLLATE 'utf8mb4_unicode_ci',
	`taux_tva` DECIMAL(5,2) NOT NULL COMMENT 'Taux de TVA en %',
	`taux_decimal` DECIMAL(8,4) NULL,
	`libelle_complet` VARCHAR(1) NOT NULL COLLATE 'utf8mb4_unicode_ci',
	`description` TEXT NULL COMMENT 'Description détaillée' COLLATE 'utf8mb4_unicode_ci'
);

-- Listage de la structure de table dbsmartv6. videos
CREATE TABLE IF NOT EXISTS `videos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `bloc` varchar(50) DEFAULT NULL,
  `medcin` varchar(50) DEFAULT NULL,
  `patient` varchar(50) DEFAULT NULL,
  `date` varchar(255) DEFAULT '0',
  `time` varchar(50) DEFAULT NULL,
  `name` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Les données exportées n'étaient pas sélectionnées.

-- Listage de la structure de déclencheur dbsmartv6. before_insert_accouchement_dossiers
SET @OLDTMP_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO';
DELIMITER //
CREATE TRIGGER `dbsmartv6`.before_insert_accouchement_dossiers
BEFORE INSERT ON accouchement_dossiers
FOR EACH ROW
BEGIN
    -- Initialisation des valeurs NULL
    IF NEW.prix_base IS NULL THEN SET NEW.prix_base = 0; END IF;
    IF NEW.prix_produits IS NULL THEN SET NEW.prix_produits = 0; END IF;
    IF NEW.prix_actes IS NULL THEN SET NEW.prix_actes = 0; END IF;
    IF NEW.prix_anesthesie IS NULL THEN SET NEW.prix_anesthesie = 0; END IF;
    IF NEW.prix_nuitees IS NULL THEN SET NEW.prix_nuitees = 0; END IF;
    IF NEW.prix_explorations IS NULL THEN SET NEW.prix_explorations = 0; END IF;
    IF NEW.supplement_gyneco IS NULL THEN SET NEW.supplement_gyneco = 0; END IF;
    IF NEW.montant_paye IS NULL THEN SET NEW.montant_paye = 0; END IF;
    IF NEW.mode_paiement IS NULL THEN SET NEW.mode_paiement = 'DIRECT'; END IF;

    -- Calcul du prix total
    SET NEW.prix_total = NEW.prix_base + NEW.prix_produits + NEW.prix_actes +
                         NEW.prix_anesthesie + NEW.prix_nuitees + NEW.prix_explorations;

    -- ✅ CALCUL DE LA BALANCE SELON MODE PAIEMENT
    IF NEW.est_gyneco_interne = 1 THEN
        -- INTERNE : balance = montant_paye - prix_total
        SET NEW.balance_medecin = NEW.montant_paye - NEW.prix_total;
    ELSE
        -- EXTERNE : dépend du mode de paiement
        IF NEW.mode_paiement = 'VIA_GYNECO' THEN
            -- Patient paie gynéco → Gynéco doit reverser part_clinique
            -- balance positive = gynéco doit à la clinique
            IF NEW.part_clinique IS NOT NULL THEN
                SET NEW.balance_medecin = NEW.part_clinique - NEW.montant_paye;
            ELSE
                SET NEW.balance_medecin = 0;
            END IF;
        ELSE
            -- DIRECT ou DIFFERE : Patient paie clinique → Clinique doit reverser part_gyneco
            -- balance négative = clinique doit au gynéco
            IF NEW.part_gyneco IS NOT NULL THEN
                SET NEW.balance_medecin = NEW.montant_paye - NEW.part_gyneco;
            ELSE
                SET NEW.balance_medecin = 0;
            END IF;
        END IF;
    END IF;

    -- ✅ CALCUL DU STATUT SELON MODE PAIEMENT
    IF NEW.est_gyneco_interne = 1 THEN
        -- INTERNE
        IF ABS(NEW.balance_medecin) < 0.01 THEN
            SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
        ELSEIF NEW.balance_medecin > 0 THEN
            SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
        ELSE
            SET NEW.statut_paiement = 'COMPLEMENT_PATIENT';
        END IF;
    ELSE
        -- EXTERNE
        IF NEW.mode_paiement = 'VIA_GYNECO' THEN
            -- Balance positive = gynéco doit
            IF ABS(NEW.balance_medecin) < 0.01 THEN
                SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';  -- Soldé
            ELSEIF NEW.balance_medecin > 0 THEN
                SET NEW.statut_paiement = 'GYNECO_DOIT_PAYER';
            ELSE
                SET NEW.statut_paiement = 'CLINIQUE_DOIT_PAYER';
            END IF;
        ELSE
            -- DIRECT/DIFFERE : Balance négative = clinique doit
            IF ABS(NEW.balance_medecin) < 0.01 THEN
                SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';  -- Soldé
            ELSEIF NEW.balance_medecin > 0 THEN
                SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
            ELSE
                SET NEW.statut_paiement = 'CLINIQUE_DOIT_PAYER';
            END IF;
        END IF;
    END IF;
END//
DELIMITER ;
SET SQL_MODE=@OLDTMP_SQL_MODE;

-- Listage de la structure de déclencheur dbsmartv6. before_insert_paiement
SET @OLDTMP_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO';
DELIMITER //
CREATE TRIGGER `dbsmartv6`.before_insert_paiement
BEFORE INSERT ON medecin_interne_paiements
FOR EACH ROW
BEGIN
    IF NEW.numero_bon IS NULL THEN
        SET NEW.numero_bon = generate_numero_bon();
    END IF;
END//
DELIMITER ;
SET SQL_MODE=@OLDTMP_SQL_MODE;

-- Listage de la structure de déclencheur dbsmartv6. before_update_accouchement_dossiers
SET @OLDTMP_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO';
DELIMITER //
CREATE TRIGGER `dbsmartv6`.before_update_accouchement_dossiers
BEFORE UPDATE ON accouchement_dossiers
FOR EACH ROW
BEGIN
    -- S'assurer que mode_paiement n'est pas NULL
    IF NEW.mode_paiement IS NULL THEN 
        SET NEW.mode_paiement = 'DIRECT'; 
    END IF;

    -- Calcul du prix total
    SET NEW.prix_total = NEW.prix_base + NEW.prix_produits + NEW.prix_actes +
                         NEW.prix_anesthesie + NEW.prix_nuitees + NEW.prix_explorations;

    -- ✅ CALCUL DE LA BALANCE SELON MODE PAIEMENT
    IF NEW.est_gyneco_interne = 1 THEN
        -- INTERNE
        SET NEW.balance_medecin = NEW.montant_paye - NEW.prix_total;
    ELSE
        -- EXTERNE : dépend du mode de paiement
        IF NEW.mode_paiement = 'VIA_GYNECO' THEN
            -- Gynéco doit reverser part_clinique
            SET NEW.balance_medecin = NEW.part_clinique - NEW.montant_paye;
        ELSE
            -- DIRECT/DIFFERE : Clinique doit reverser part_gyneco
            SET NEW.balance_medecin = NEW.montant_paye - NEW.part_gyneco;
        END IF;
    END IF;

    -- ✅ CALCUL DU STATUT SELON MODE PAIEMENT
    IF NEW.est_gyneco_interne = 1 THEN
        -- INTERNE
        IF ABS(NEW.balance_medecin) < 0.01 THEN
            SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
        ELSEIF NEW.balance_medecin > 0 THEN
            SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
        ELSE
            SET NEW.statut_paiement = 'COMPLEMENT_PATIENT';
        END IF;
    ELSE
        -- EXTERNE
        IF NEW.mode_paiement = 'VIA_GYNECO' THEN
            IF ABS(NEW.balance_medecin) < 0.01 THEN
                SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
            ELSEIF NEW.balance_medecin > 0 THEN
                SET NEW.statut_paiement = 'GYNECO_DOIT_PAYER';
            ELSE
                SET NEW.statut_paiement = 'CLINIQUE_DOIT_PAYER';
            END IF;
        ELSE
            -- DIRECT/DIFFERE
            IF ABS(NEW.balance_medecin) < 0.01 THEN
                SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
            ELSEIF NEW.balance_medecin > 0 THEN
                SET NEW.statut_paiement = 'SURPLUS_CLINIQUE';
            ELSE
                SET NEW.statut_paiement = 'CLINIQUE_DOIT_PAYER';
            END IF;
        END IF;
    END IF;
END//
DELIMITER ;
SET SQL_MODE=@OLDTMP_SQL_MODE;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_accouchement_detail`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_accouchement_detail` AS SELECT
    d.*,
    CONCAT(doc.first_name, ' ', doc.last_name) AS gyneco_nom,
    doc.est_interne AS gyneco_est_interne,
    CONCAT(p.nom, ' ', p.prenom) AS cree_par_nom,

    -- Compteurs
    (SELECT COUNT(*) FROM accouchement_dossier_produits WHERE id_dossier = d.id_dossier) AS nb_produits,
    (SELECT COUNT(*) FROM accouchement_dossier_actes WHERE id_dossier = d.id_dossier) AS nb_actes,
    (SELECT COUNT(*) FROM accouchement_dossier_nuitees WHERE id_dossier = d.id_dossier) AS nb_hospitalisations,
    (SELECT COUNT(*) FROM accouchement_dossier_explorations WHERE id_dossier = d.id_dossier) AS nb_explorations,
    (SELECT COUNT(*) FROM accouchement_dossier_anesthesie WHERE id_dossier = d.id_dossier) AS nb_anesthesistes,

    -- Total nuitées
    (SELECT COALESCE(SUM(nombre_nuitees), 0) FROM accouchement_dossier_nuitees WHERE id_dossier = d.id_dossier) AS total_nuitees

FROM accouchement_dossiers d
LEFT JOIN doctors doc ON d.id_gyneco = doc.id
LEFT JOIN personnel p ON d.created_by = p.id_personnel 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_accouchement_liste`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_accouchement_liste` AS SELECT 
    d.id_dossier,
    d.patiente,
    d.date_accouchement,
    d.type_accouchement,
    d.type_tarification,
    d.prix_total,
    d.montant_paye,
    d.balance_medecin,
    d.statut_paiement,
    d.mode_paiement,
    CONCAT(doc.first_name, ' ', doc.last_name) AS gyneco_nom,
    d.est_gyneco_interne,
    
    -- Indicateurs visuels
    CASE 
        WHEN d.statut_paiement = 'SOLDE' THEN 'success'
        WHEN d.statut_paiement IN ('SURPLUS_CLINIQUE', 'CLINIQUE_DOIT_PAYER') THEN 'info'
        WHEN d.statut_paiement IN ('COMPLEMENT_PATIENT', 'GYNECO_DOIT_PAYER') THEN 'warning'
        ELSE 'secondary'
    END AS badge_color,
    
    -- Montants importants
    (d.prix_total - d.montant_paye) AS reste_a_payer,
    ABS(d.balance_medecin) AS balance_absolue,
    
    -- Dates
    DATE_FORMAT(d.date_accouchement, '%d/%m/%Y') AS date_format,
    DATE_FORMAT(d.created_at, '%d/%m/%Y %H:%i') AS date_creation,
    DATEDIFF(NOW(), d.date_accouchement) AS jours_depuis_accouchement

FROM accouchement_dossiers d
LEFT JOIN doctors doc ON d.id_gyneco = doc.id 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_accouchement_paiements`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_accouchement_paiements` AS SELECT 
    d.id_dossier,
    d.patiente,
    d.date_accouchement,
    CONCAT(doc.first_name, ' ', doc.last_name) AS gyneco_nom,
    d.est_gyneco_interne,
    d.prix_total,
    d.montant_paye,
    d.balance_medecin,
    d.statut_paiement,
    d.mode_paiement,
    
    -- Calculs
    (d.prix_total - d.montant_paye) AS reste_a_payer,
    ABS(d.balance_medecin) AS balance_absolue,
    
    -- Délais
    DATEDIFF(NOW(), d.date_accouchement) AS jours_attente,
    
    CASE 
        WHEN DATEDIFF(NOW(), d.date_accouchement) > 30 THEN 'danger'
        WHEN DATEDIFF(NOW(), d.date_accouchement) > 15 THEN 'warning'
        ELSE 'info'
    END AS urgence_color,
    
    -- Informations paiement
    CASE 
        WHEN d.mode_paiement = 'VIA_GYNECO' THEN 'Patient → Gynéco → Clinique'
        WHEN d.mode_paiement = 'DIFFERE' THEN 'En attente d\'encaissement'
        ELSE 'Paiement direct'
    END AS flux_paiement

FROM accouchement_dossiers d
LEFT JOIN doctors doc ON d.id_gyneco = doc.id
WHERE d.statut_paiement IN ('COMPLEMENT_PATIENT', 'GYNECO_DOIT_PAYER')
   OR (d.mode_paiement IN ('VIA_GYNECO', 'DIFFERE') AND d.montant_paye < d.prix_total)
ORDER BY d.date_accouchement ASC 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_accouchement_resume`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_accouchement_resume` AS SELECT 
    -- Informations de base
    d.id_dossier,
    d.id_gyneco,
    d.patiente,
    d.date_accouchement,
    d.heure_accouchement,
    d.type_accouchement,
    d.type_tarification,
    d.est_gyneco_interne,
    
    -- Informations gynécologue
    CONCAT(doc.first_name, ' ', doc.last_name) AS gyneco_nom,
    doc.est_interne AS gyneco_est_interne,
    
    -- Prix détaillés
    d.prix_base,
    d.prix_produits,
    d.prix_actes,
    d.prix_anesthesie,
    d.prix_nuitees,
    d.prix_explorations,
    d.prix_total,
    
    -- Parts
    d.supplement_gyneco,
    d.part_clinique,
    d.part_gyneco,
    
    -- Hospitalisation
    d.nuitees_incluses,
    
    -- Paiement (NOUVELLES COLONNES)
    d.montant_paye,
    d.mode_paiement,
    d.balance_medecin,
    d.statut_paiement,
    
    -- Observations
    d.observations,
    
    -- Métadonnées
    d.created_by,
    d.created_at,
    d.updated_at,
    CONCAT(p.nom, ' ', p.prenom) AS cree_par_nom,
    
    -- Calculs supplémentaires
    (d.prix_total - d.montant_paye) AS reste_a_payer,
    
    CASE 
        WHEN d.est_gyneco_interne = 1 THEN 'Interne'
        ELSE 'Externe'
    END AS type_gyneco,
    
    CASE d.type_accouchement
        WHEN 'VOIE_BASSE' THEN 'Voie Basse'
        WHEN 'CESARIENNE' THEN 'Césarienne'
        ELSE d.type_accouchement
    END AS type_accouchement_libelle,
    
    CASE d.type_tarification
        WHEN 'CONVENTION' THEN 'Convention'
        WHEN 'PAYANT' THEN 'Payant'
        ELSE d.type_tarification
    END AS type_tarification_libelle,
    
    CASE d.mode_paiement
        WHEN 'DIRECT' THEN 'Paiement direct'
        WHEN 'VIA_GYNECO' THEN 'Via gynécologue'
        WHEN 'DIFFERE' THEN 'Paiement différé'
        ELSE d.mode_paiement
    END AS mode_paiement_libelle,
    
    CASE d.statut_paiement
        WHEN 'SOLDE' THEN '✓ Soldé'
        WHEN 'SURPLUS_CLINIQUE' THEN '+ Surplus clinique'
        WHEN 'COMPLEMENT_PATIENT' THEN '− Complément patient'
        WHEN 'GYNECO_DOIT_PAYER' THEN '− Gynéco doit payer'
        WHEN 'CLINIQUE_DOIT_PAYER' THEN '+ Clinique doit payer'
        ELSE d.statut_paiement
    END AS statut_paiement_libelle

FROM accouchement_dossiers d
LEFT JOIN doctors doc ON d.id_gyneco = doc.id
LEFT JOIN personnel p ON d.created_by = p.id_personnel 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_accouchement_situation_gyneco`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_accouchement_situation_gyneco` AS SELECT 
    doc.id as id_gyneco,
    CONCAT(doc.first_name, ' ', doc.last_name) as nom_gyneco,
    doc.est_interne,
    COUNT(DISTINCT d.id_dossier) as total_dossiers,
    COALESCE(SUM(d.part_gyneco), 0) as total_part_gyneco,
    COALESCE(SUM(gs.encaissement_patient), 0) as total_encaisse_patient,
    COALESCE(SUM(gs.encaissement_gyneco), 0) as total_encaisse_gyneco,
    COALESCE(SUM(gs.decaissement_clinique), 0) as total_decaisse,
    COALESCE(SUM(gs.compensation), 0) as total_compensation,
    (COALESCE(SUM(gs.encaissement_patient), 0) 
     + COALESCE(SUM(gs.encaissement_gyneco), 0) 
     + COALESCE(SUM(gs.decaissement_clinique), 0)
     + COALESCE(SUM(gs.compensation), 0)
     - COALESCE(SUM(d.part_gyneco), 0)) as balance
FROM doctors doc
LEFT JOIN accouchement_dossiers d ON doc.id = d.id_gyneco
LEFT JOIN accouchement_gyneco_situations gs ON d.id_dossier = gs.id_dossier
WHERE doc.id_specialty IN (SELECT id_specialty FROM specialty WHERE name_specialty LIKE '%gyn%')
GROUP BY doc.id 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_accouchement_stats`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_accouchement_stats` AS SELECT 
    d.id_gyneco,
    CONCAT(doc.first_name, ' ', doc.last_name) AS gyneco_nom,
    d.est_gyneco_interne,
    
    -- Compteurs
    COUNT(*) AS total_accouchements,
    COUNT(CASE WHEN d.type_accouchement = 'VOIE_BASSE' THEN 1 END) AS nb_voie_basse,
    COUNT(CASE WHEN d.type_accouchement = 'CESARIENNE' THEN 1 END) AS nb_cesarienne,
    COUNT(CASE WHEN d.type_tarification = 'CONVENTION' THEN 1 END) AS nb_convention,
    COUNT(CASE WHEN d.type_tarification = 'PAYANT' THEN 1 END) AS nb_payant,
    
    -- Montants
    COALESCE(SUM(d.prix_total), 0) AS total_ca,
    COALESCE(SUM(d.montant_paye), 0) AS total_encaisse,
    COALESCE(SUM(d.part_clinique), 0) AS total_part_clinique,
    COALESCE(SUM(d.part_gyneco), 0) AS total_part_gyneco,
    COALESCE(SUM(d.balance_medecin), 0) AS balance_totale,
    
    -- Moyennes
    COALESCE(AVG(d.prix_total), 0) AS moyenne_prix_total,
    COALESCE(AVG(d.montant_paye), 0) AS moyenne_montant_paye,
    
    -- Statuts paiement
    COUNT(CASE WHEN d.statut_paiement = 'SOLDE' THEN 1 END) AS nb_solde,
    COUNT(CASE WHEN d.statut_paiement IN ('COMPLEMENT_PATIENT', 'GYNECO_DOIT_PAYER') THEN 1 END) AS nb_en_attente,
    
    -- Dates
    MIN(d.date_accouchement) AS premier_accouchement,
    MAX(d.date_accouchement) AS dernier_accouchement

FROM accouchement_dossiers d
LEFT JOIN doctors doc ON d.id_gyneco = doc.id
GROUP BY d.id_gyneco, gyneco_nom, d.est_gyneco_interne 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_accouchements_sans_documents`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_accouchements_sans_documents` AS SELECT 
    `a`.`id_dossier` AS `id_dossier`,
    `a`.`patiente` AS `patiente`,
    `a`.`date_accouchement` AS `date_accouchement`,
    CONCAT(`g`.`first_name`, ' ', IFNULL(`g`.`last_name`, '')) AS `gyneco_name`,
    `a`.`prix_total` AS `prix_total`,
    `a`.`montant_paye` AS `montant_paye`,
    `a`.`statut_financier` AS `statut_financier`,
    `a`.`documents_generes` AS `documents_generes`,
    (CASE 
        WHEN (`a`.`documents_generes` = 1) THEN 'Généré' 
        ELSE 'Non Généré' 
    END) AS `status_documents`
FROM (`accouchement_dossiers` `a` 
LEFT JOIN `doctors` `g` ON((`a`.`id_gyneco` = `g`.`id`))) 
WHERE (`a`.`documents_generes` = 0) 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_config_clinique_grouped`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_config_clinique_grouped` AS SELECT 
    categorie,
    JSON_OBJECTAGG(cle, valeur) as config_json
FROM config_clinique
GROUP BY categorie 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_config_facture`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_config_facture` AS SELECT 
    cle,
    valeur,
    categorie,
    libelle
FROM config_clinique
WHERE est_actif = TRUE 
  AND est_affiche_facture = TRUE
ORDER BY ordre 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_documents_accouchements`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_documents_accouchements` AS SELECT 
    dg.id_document,
    dg.id_dossier,
    d.patiente,
    dg.type_document,
    CONCAT(p.nom, ' ', p.prenom) as genere_par_nom,
    dg.date_generation,
    d.date_accouchement
FROM accouchement_documents_generes dg
LEFT JOIN accouchement_dossiers d ON dg.id_dossier = d.id_dossier
LEFT JOIN personnel p ON dg.genere_par = p.id_personnel
ORDER BY dg.date_generation DESC 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_dossiers_a_regler`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_dossiers_a_regler` AS -- =====================
-- DOSSIERS BLOC
-- =====================
SELECT 
    CAST('BLOC' AS CHAR(20)) COLLATE utf8mb4_general_ci AS type_dossier,
    dp.id_dossier,
    dp.patient COLLATE utf8mb4_general_ci AS patient,
    dp.location_date,
    dp.id_doctor,
    CONCAT(doc.first_name, ' ', doc.last_name) COLLATE utf8mb4_general_ci AS medecin,
    dp.prix_total AS part_medecin,

    ( COALESCE(SUM(ds.encaissement_patient), 0)
    + COALESCE(SUM(ds.encaissement_doctor), 0)
    + COALESCE(SUM(ds.decaissement_clinique), 0)
    + COALESCE(SUM(ds.compensation), 0)
    - dp.prix_total ) AS reste,

    CAST(
        CASE 
            WHEN ( COALESCE(SUM(ds.encaissement_patient), 0)
                 + COALESCE(SUM(ds.encaissement_doctor), 0)
                 + COALESCE(SUM(ds.decaissement_clinique), 0)
                 + COALESCE(SUM(ds.compensation), 0)
                 - dp.prix_total ) > 0.01
                THEN 'CLINIQUE_DOIT'

            WHEN ( COALESCE(SUM(ds.encaissement_patient), 0)
                 + COALESCE(SUM(ds.encaissement_doctor), 0)
                 + COALESCE(SUM(ds.decaissement_clinique), 0)
                 + COALESCE(SUM(ds.compensation), 0)
                 - dp.prix_total ) < -0.01
                THEN 'MEDECIN_DOIT'

            ELSE 'EQUILIBRE'
        END AS CHAR(20)
    ) COLLATE utf8mb4_general_ci AS statut

FROM location_bloc_dossier_patient dp
LEFT JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
LEFT JOIN doctors doc ON dp.id_doctor = doc.id
GROUP BY dp.id_dossier
HAVING ABS(reste) > 0.01

UNION ALL

-- =====================
-- DOSSIERS ACCOUCHEMENT
-- =====================
SELECT 
    CAST('accouchement_dossiers' AS CHAR(20)) COLLATE utf8mb4_general_ci AS type_dossier,
    a.id_dossier,
    a.patiente COLLATE utf8mb4_general_ci AS patient,
    a.date_accouchement AS location_date,
    a.id_gyneco AS id_doctor,
    CONCAT(doc.first_name, ' ', doc.last_name) COLLATE utf8mb4_general_ci AS medecin,
    a.part_gyneco AS part_medecin,

    ( COALESCE(SUM(ags.encaissement_patient), 0)
    + COALESCE(SUM(ags.encaissement_gyneco), 0)
    + COALESCE(SUM(ags.decaissement_clinique), 0)
    + COALESCE(SUM(ags.compensation), 0)
    - a.part_gyneco ) AS reste,

    CAST(
        CASE 
            WHEN ( COALESCE(SUM(ags.encaissement_patient), 0)
                 + COALESCE(SUM(ags.encaissement_gyneco), 0)
                 + COALESCE(SUM(ags.decaissement_clinique), 0)
                 + COALESCE(SUM(ags.compensation), 0)
                 - a.part_gyneco ) > 0.01
                THEN 'CLINIQUE_DOIT'

            WHEN ( COALESCE(SUM(ags.encaissement_patient), 0)
                 + COALESCE(SUM(ags.encaissement_gyneco), 0)
                 + COALESCE(SUM(ags.decaissement_clinique), 0)
                 + COALESCE(SUM(ags.compensation), 0)
                 - a.part_gyneco ) < -0.01
                THEN 'GYNECO_DOIT'

            ELSE 'EQUILIBRE'
        END AS CHAR(20)
    ) COLLATE utf8mb4_general_ci AS statut

FROM accouchement_dossiers a
LEFT JOIN accouchement_gyneco_situations ags ON a.id_dossier = ags.id_dossier
LEFT JOIN doctors doc ON a.id_gyneco = doc.id
GROUP BY a.id_dossier
HAVING ABS(reste) > 0.01 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_dossiers_incoherents`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_dossiers_incoherents` AS SELECT 
    d.id_dossier,
    d.patiente,
    d.date_accouchement,
    d.gyneco_paye,
    d.id_decharge_gyneco,
    dech.numero_decharge,
    dech.statut as statut_decharge,
    CASE 
        WHEN d.gyneco_paye = 1 AND d.id_decharge_gyneco IS NULL 
            THEN 'Marqué payé mais sans décharge'
        WHEN d.gyneco_paye = 0 AND d.id_decharge_gyneco IS NOT NULL AND dech.statut = 'PAYE'
            THEN 'Dans décharge payée mais marqué non payé'
        WHEN d.id_decharge_gyneco IS NOT NULL AND dech.statut = 'ANNULE'
            THEN 'Lié à décharge annulée'
        ELSE 'Autre incohérence'
    END as type_probleme
FROM accouchement_dossiers d
LEFT JOIN gyneco_interne_decharges dech ON d.id_decharge_gyneco = dech.id_decharge
WHERE d.est_gyneco_interne = 1
  AND (
      (d.gyneco_paye = 1 AND d.id_decharge_gyneco IS NULL) OR
      (d.gyneco_paye = 0 AND d.id_decharge_gyneco IS NOT NULL AND dech.statut = 'PAYE') OR
      (d.id_decharge_gyneco IS NOT NULL AND dech.statut = 'ANNULE')
  ) 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_dossiers_non_decharges`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_dossiers_non_decharges` AS SELECT 
    d.id_dossier,
    d.patiente,
    d.date_accouchement,
    d.id_gyneco,
    CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name,
    d.type_accouchement,
    d.type_tarification,
    d.part_gyneco,
    d.gyneco_paye,
    d.id_decharge_gyneco
FROM accouchement_dossiers d
LEFT JOIN doctors doc ON d.id_gyneco = doc.id
WHERE d.est_gyneco_interne = 1
  AND d.gyneco_paye = 0
  AND d.id_decharge_gyneco IS NULL
ORDER BY d.date_accouchement DESC 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_factures_resume`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_factures_resume` AS SELECT
    f.*,  -- ✅ Ceci inclut déjà patient_oid_his et patient_code_his
    CONCAT(f.patient_nom, ' ', f.patient_prenom) as patient_complet,
    COUNT(fl.id) as nombre_lignes,
    SUM(CASE WHEN fl.taux_tva = 9 THEN fl.montant_ht ELSE 0 END) as ht_tva_9,
    SUM(CASE WHEN fl.taux_tva = 19 THEN fl.montant_ht ELSE 0 END) as ht_tva_19,
    SUM(CASE WHEN fl.est_debours = TRUE THEN fl.montant_ht ELSE 0 END) as debours_calcule,
    COUNT(CASE WHEN fl.est_debours = TRUE THEN 1 END) as nombre_debours,
    CONCAT(p.nom, ' ', p.prenom) as createur,
    CONCAT(v.nom, ' ', v.prenom) as validateur
FROM factures f
LEFT JOIN facture_lignes fl ON f.id = fl.facture_id
LEFT JOIN personnel p ON f.created_by = p.id_personnel
LEFT JOIN personnel v ON f.valide_par = v.id_personnel
GROUP BY f.id 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_kt_decharges_completes`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_kt_decharges_completes` AS SELECT 
    d.id_decharge,
    d.id_doctor,
    d.numero_decharge,
    d.date_decharge,
    d.montant_total,
    d.montant_paye,
    d.montant_restant,
    d.statut,
    d.observations,
    d.id_createur,
    d.date_creation,
    d.id_modificateur,
    d.date_modification,
    d.id_annulateur,
    d.date_annulation,
    d.raison_annulation,
    
    -- Informations du médecin
    CONCAT(doc.first_name, ' ', doc.last_name) as nom_medecin,
    spec.name_specialty,
    
    -- Nombre de dossiers
    (SELECT COUNT(*) 
     FROM kt_decharges_dossiers dd 
     WHERE dd.id_decharge = d.id_decharge) as nb_dossiers,
    
    -- Nombre de tranches actives
    (SELECT COUNT(*) 
     FROM kt_decharges_tranches dt 
     WHERE dt.id_decharge = d.id_decharge 
       AND dt.statut = 'ACTIVE') as nb_tranches,
    
    -- Nombre de tranches annulées
    (SELECT COUNT(*) 
     FROM kt_decharges_tranches dt 
     WHERE dt.id_decharge = d.id_decharge 
       AND dt.statut = 'ANNULEE') as nb_tranches_annulees,
    
    -- Montant total annulé
    (SELECT COALESCE(SUM(dt.montant_tranche), 0) 
     FROM kt_decharges_tranches dt 
     WHERE dt.id_decharge = d.id_decharge 
       AND dt.statut = 'ANNULEE') as montant_annule

FROM kt_decharges_paiement d
LEFT JOIN doctors doc ON d.id_doctor = doc.id
LEFT JOIN specialty spec ON doc.id_specialty = spec.id_specialty 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_kt_doctor_stats`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_kt_doctor_stats` AS SELECT 
    d.id,
    d.first_name,
    d.last_name,
    d.id_specialty,
    s.name_specialty,
    COUNT(DISTINCT kdp.id_dossier) as nb_dossiers,
    COALESCE(SUM(kdp.part_operateur), 0) as total_part_operateur,
    COALESCE(SUM(kdp.payment), 0) as total_payment,
    COALESCE(SUM(kdp.part_operateur), 0) - COALESCE(SUM(kdp.payment), 0) as solde
FROM doctors d
LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
LEFT JOIN kt_dossier_patient kdp ON d.id = kdp.id_doctor
GROUP BY d.id, d.first_name, d.last_name, d.id_specialty, s.name_specialty 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_medecin_interne_actes_resume`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_medecin_interne_actes_resume` AS SELECT 
    a.id_acte,
    a.patient,
    a.date_acte,
    a.nom_acte,
    a.est_annule,
    a.motif_annulation,
    a.annule_at,
    CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
    a.nom_specialite,
    a.pourcentage_medecin,
    a.prix_acte_base,
    a.total_deductions,
    a.base_calcul,
    a.part_medecin,
    a.part_clinique,
    a.montant_paye_caisse,
    a.difference_paiement,
    a.statut_paiement,
    
    -- Calcul de la balance (reste à régler) - uniquement pour actes non annulés
    CASE 
        WHEN a.est_annule = TRUE THEN 0
        ELSE a.part_medecin - (
            COALESCE((SELECT SUM(encaissement_patient) FROM medecin_interne_situations WHERE id_acte = a.id_acte), 0) +
            COALESCE((SELECT SUM(encaissement_doctor) FROM medecin_interne_situations WHERE id_acte = a.id_acte), 0) +
            COALESCE((SELECT SUM(decaissement_clinique) FROM medecin_interne_situations WHERE id_acte = a.id_acte), 0) -
            COALESCE((SELECT SUM(compensation) FROM medecin_interne_situations WHERE id_acte = a.id_acte), 0)
        )
    END as balance
FROM medecin_interne_actes a
JOIN doctors d ON a.id_doctor = d.id 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_medecin_interne_decharges_resume`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_medecin_interne_decharges_resume` AS SELECT 
    d.id_decharge,
    d.numero_decharge,
    d.date_decharge,
    d.periode_debut,
    d.periode_fin,
    CONCAT(doc.first_name, ' ', doc.last_name) AS medecin_name,
    s.name_specialty AS specialite,
    d.nb_actes,
    d.montant_total,
    d.montant_paye_total,
    d.solde_restant,
    d.nb_tranches,
    d.statut,
    d.mode_paiement,
    CONCAT(p_created.nom, ' ', p_created.prenom) AS created_by_name,
    d.created_at,
    CONCAT(p_validated.nom, ' ', p_validated.prenom) AS validated_by_name,
    d.validated_at,
    CONCAT(p_paid.nom, ' ', p_paid.prenom) AS paid_by_name,
    d.paid_at,
    -- Calcul du pourcentage payé
    CASE 
        WHEN d.montant_total > 0 THEN 
            ROUND((d.montant_paye_total / d.montant_total * 100), 2)
        ELSE 0 
    END AS pourcentage_paye
FROM medecin_interne_decharges d
LEFT JOIN doctors doc ON d.id_doctor = doc.id
LEFT JOIN specialty s ON doc.id_specialty = s.id_specialty
LEFT JOIN personnel p_created ON d.created_by = p_created.id_personnel
LEFT JOIN personnel p_validated ON d.validated_by = p_validated.id_personnel
LEFT JOIN personnel p_paid ON d.paid_by = p_paid.id_personnel
ORDER BY d.date_decharge DESC, d.id_decharge DESC 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_medecin_interne_paiements_summary`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_medecin_interne_paiements_summary` AS SELECT 
    a.id_acte,
    a.prix_acte_base,
    a.montant_paye_caisse,
    a.part_medecin,
    a.est_annule,
    
    -- Mode de calcul pour déterminer le montant total à payer
    a.mode_calcul,
    
    -- Montant total à payer selon le mode (0 si annulé)
    CASE 
        WHEN a.est_annule = TRUE THEN 0
        WHEN a.mode_calcul = 'PRIX_BASE' THEN 
            a.prix_acte_base + 
            COALESCE(a.prix_consommables_specifiques, 0) + 
            COALESCE(a.prix_hospitalisation_hors_forfait, 0) + 
            COALESCE(a.prix_supplements, 0) + 
            COALESCE(a.prix_actes_supplementaires, 0) + 
            COALESCE(a.prix_anesthesie, 0)
        ELSE 
            a.prix_acte_base
    END AS montant_total_a_payer,
    
    -- Total payé (tous les paiements non annulés, 0 si acte annulé)
    CASE 
        WHEN a.est_annule = TRUE THEN 0
        ELSE COALESCE(SUM(CASE WHEN p.est_annule = FALSE THEN p.montant_paye ELSE 0 END), 0)
    END AS total_paye,
    
    -- Reste à payer (0 si acte annulé)
    CASE 
        WHEN a.est_annule = TRUE THEN 0
        WHEN a.mode_calcul = 'PRIX_BASE' THEN 
            (a.prix_acte_base + 
             COALESCE(a.prix_consommables_specifiques, 0) + 
             COALESCE(a.prix_hospitalisation_hors_forfait, 0) + 
             COALESCE(a.prix_supplements, 0) + 
             COALESCE(a.prix_actes_supplementaires, 0) + 
             COALESCE(a.prix_anesthesie, 0)) - 
            COALESCE(SUM(CASE WHEN p.est_annule = FALSE THEN p.montant_paye ELSE 0 END), 0)
        ELSE 
            a.prix_acte_base - COALESCE(SUM(CASE WHEN p.est_annule = FALSE THEN p.montant_paye ELSE 0 END), 0)
    END AS reste_a_payer,
    
    -- Nombre de paiements
    COUNT(CASE WHEN p.est_annule = FALSE THEN 1 END) AS nombre_paiements,
    
    -- Dernier paiement
    MAX(CASE WHEN p.est_annule = FALSE THEN p.date_paiement END) AS dernier_paiement
    
FROM medecin_interne_actes a
LEFT JOIN medecin_interne_paiements p ON a.id_acte = p.id_acte
GROUP BY a.id_acte 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_medecin_interne_situation_financiere`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_medecin_interne_situation_financiere` AS SELECT 
    d.id AS id_doctor,
    CONCAT(d.first_name, ' ', d.last_name) AS medecin_name,
    s.name_specialty AS specialite,
    
    -- Actes (uniquement les non annulés)
    COUNT(DISTINCT CASE WHEN a.est_annule = FALSE THEN a.id_acte END) AS total_actes,
    SUM(CASE WHEN a.est_annule = FALSE AND COALESCE(a.medecin_paye, 0) = 0 THEN 1 ELSE 0 END) AS actes_non_payes,
    
    -- Honoraires (uniquement pour actes non annulés)
    COALESCE(SUM(CASE WHEN a.est_annule = FALSE THEN a.part_medecin ELSE 0 END), 0) AS total_honoraires,
    COALESCE(SUM(CASE WHEN a.est_annule = FALSE AND a.medecin_paye = 1 THEN a.part_medecin ELSE 0 END), 0) AS honoraires_payes,
    COALESCE(SUM(CASE WHEN a.est_annule = FALSE AND COALESCE(a.medecin_paye, 0) = 0 THEN a.part_medecin ELSE 0 END), 0) AS honoraires_non_payes,
    
    -- Décharges
    COUNT(DISTINCT dech.id_decharge) AS nb_decharges,
    COUNT(DISTINCT CASE WHEN dech.statut = 'PAYE' THEN dech.id_decharge END) AS nb_decharges_payees,
    COUNT(DISTINCT CASE WHEN dech.statut IN ('BROUILLON','VALIDE','PAIEMENT_PARTIEL') THEN dech.id_decharge END) AS nb_decharges_en_cours,
    
    -- CA généré (uniquement actes non annulés)
    COALESCE(SUM(CASE WHEN a.est_annule = FALSE THEN a.prix_acte_base ELSE 0 END), 0) AS ca_total_genere,
    COALESCE(SUM(CASE WHEN a.est_annule = FALSE THEN a.part_clinique ELSE 0 END), 0) AS part_clinique_totale,
    
    -- Statistiques d'annulation
    COUNT(DISTINCT CASE WHEN a.est_annule = TRUE THEN a.id_acte END) AS total_actes_annules
    
FROM doctors d
JOIN specialty s ON d.id_specialty = s.id_specialty
LEFT JOIN medecin_interne_actes a ON d.id = a.id_doctor
LEFT JOIN medecin_interne_decharges dech ON d.id = dech.id_doctor AND dech.statut != 'ANNULE'
WHERE d.est_interne = 1
  AND s.name_specialty IN ('ORTHOPÉDIE', 'CHIRURGIE GÉNÉRALE')
GROUP BY d.id
ORDER BY total_honoraires DESC 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_situation_medecin_globale`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_situation_medecin_globale` AS SELECT 
    d.id as id_doctor,
    CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
    s.name_specialty,
    
    -- Stats BLOC
    (SELECT COUNT(DISTINCT dp.id_dossier) 
     FROM location_bloc_dossier_patient dp WHERE dp.id_doctor = d.id) as total_dossiers_bloc,
    
    (SELECT COALESCE(SUM(dp.prix_total), 0) 
     FROM location_bloc_dossier_patient dp WHERE dp.id_doctor = d.id) as ca_bloc,
    
    -- Stats ACCOUCHEMENT
    (SELECT COUNT(DISTINCT a.id_dossier) 
     FROM accouchement_dossiers a WHERE a.id_gyneco = d.id) as total_dossiers_accouchement,
    
    (SELECT COALESCE(SUM(a.part_gyneco), 0) 
     FROM accouchement_dossiers a WHERE a.id_gyneco = d.id) as ca_accouchement,
    
    -- Balance BLOC
    (SELECT 
        COALESCE(SUM(ds.encaissement_patient), 0) + 
        COALESCE(SUM(ds.encaissement_doctor), 0) + 
        COALESCE(SUM(ds.decaissement_clinique), 0) + 
        COALESCE(SUM(ds.compensation), 0) - 
        COALESCE(SUM(dp.prix_total), 0)
     FROM location_bloc_dossier_patient dp
     LEFT JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
     WHERE dp.id_doctor = d.id) as balance_bloc,
    
    -- Balance ACCOUCHEMENT
    (SELECT 
        COALESCE(SUM(ags.encaissement_patient), 0) + 
        COALESCE(SUM(ags.encaissement_gyneco), 0) + 
        COALESCE(SUM(ags.decaissement_clinique), 0) + 
        COALESCE(SUM(ags.compensation), 0) - 
        COALESCE(SUM(a.part_gyneco), 0)
     FROM accouchement_dossiers a
     LEFT JOIN accouchement_gyneco_situations ags ON a.id_dossier = ags.id_dossier
     WHERE a.id_gyneco = d.id) as balance_accouchement

FROM doctors d
LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
ORDER BY d.last_name, d.first_name 
;

-- Suppression de la table temporaire et création finale de la structure de VIEW
DROP TABLE IF EXISTS `v_tva_actives`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `v_tva_actives` AS SELECT 
    id,
    code,
    libelle,
    taux_tva,
    ROUND(taux_tva / 100, 4) AS taux_decimal,
    CONCAT(libelle, ' (', taux_tva, '%)') AS libelle_complet,
    description
FROM config_tva
WHERE est_actif = TRUE
ORDER BY ordre, libelle 
;

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
