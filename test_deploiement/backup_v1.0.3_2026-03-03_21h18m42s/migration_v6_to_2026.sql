-- Script de migration dbsmartv6 -> dbsmart2026

SET FOREIGN_KEY_CHECKS=0;

-- 1. Table doctors
ALTER TABLE `doctors`
ADD COLUMN `_migration_old_kt_id` int(11) DEFAULT NULL AFTER `est_interne`,
ADD COLUMN `pourcentage_medecin_interne` decimal(5,2) DEFAULT NULL AFTER `_migration_old_kt_id`;

-- 2. Table accouchement_dossiers
ALTER TABLE `accouchement_dossiers`
ADD COLUMN `age_patiente` int(11) DEFAULT NULL AFTER `patiente`,
ADD COLUMN `type_cesarienne` enum('URGENCE','PROPHYLACTIQUE') DEFAULT NULL COMMENT 'Type de césarienne (urgence ou prophylactique)' AFTER `type_accouchement`,
ADD COLUMN `instrumentation` text DEFAULT NULL COMMENT 'Instrumentation utilisée (forceps, ventouse, etc.)' AFTER `gestes_chirurgicaux`,
ADD COLUMN `notes_cliniques` text DEFAULT NULL COMMENT 'Notes cliniques diverses' AFTER `observations`,
ADD COLUMN `observations_medicales` text DEFAULT NULL COMMENT 'Observations médicales (complications, suivi, etc.)' AFTER `notes_cliniques`,
ADD COLUMN `date_validation_medical` datetime DEFAULT NULL AFTER `date_generation_documents`,
ADD COLUMN `validateur_medical_id` int(11) DEFAULT NULL AFTER `date_validation_medical`,
CHANGE COLUMN `valide_financier_le` `date_validation_finance` datetime DEFAULT NULL,
CHANGE COLUMN `valide_financier_par` `validateur_finance_id` int(11) DEFAULT NULL,
ADD COLUMN `nom_epoux` varchar(255) DEFAULT NULL COMMENT 'Nom du mari/époux de la patiente' AFTER `validateur_finance_id`,
ADD COLUMN `ta_postop` varchar(50) DEFAULT NULL COMMENT 'Tension Artérielle post-opératoire (ex: 12/8)' AFTER `nom_epoux`,
ADD COLUMN `diurese_postop` varchar(100) DEFAULT NULL COMMENT 'Diurèse post-opératoire' AFTER `ta_postop`,
ADD COLUMN `reveil_postop` text DEFAULT NULL COMMENT 'État au réveil post-opératoire' AFTER `diurese_postop`,
ADD COLUMN `compte_compresses` text DEFAULT NULL COMMENT 'Compte des compresses chirurgicales' AFTER `reveil_postop`,
ADD COLUMN `hemostases` text DEFAULT NULL COMMENT 'Hémostases effectuées' AFTER `compte_compresses`,
ADD COLUMN `est_annule` tinyint(1) DEFAULT 0 AFTER `hemostases`,
ADD COLUMN `motif_annulation` text DEFAULT NULL AFTER `est_annule`,
ADD COLUMN `annule_par` int(11) DEFAULT NULL AFTER `motif_annulation`,
ADD COLUMN `annule_at` datetime DEFAULT NULL AFTER `annule_par`;

-- Suppression de colonnes non présentes dans le dump local
ALTER TABLE `accouchement_dossiers`
DROP COLUMN `charge_supplements`,
DROP COLUMN `duree_conge`;

-- Modification des enums (gestion des données existantes)
ALTER TABLE `accouchement_dossiers` MODIFY COLUMN `statut_medical` varchar(50) DEFAULT 'NON_VALIDE';
ALTER TABLE `accouchement_dossiers` MODIFY COLUMN `statut_financier` varchar(50) DEFAULT 'NON_VALIDE';

UPDATE `accouchement_dossiers` SET `statut_medical` = 'NON_VALIDE' WHERE `statut_medical` = 'BROUILLON';
UPDATE `accouchement_dossiers` SET `statut_medical` = 'VALIDE' WHERE `statut_medical` = 'VALIDE_MEDICAL';
UPDATE `accouchement_dossiers` SET `statut_medical` = 'EN_ATTENTE' WHERE `statut_medical` = 'DOCUMENTS_GENERES'; 

UPDATE `accouchement_dossiers` SET `statut_financier` = 'VALIDE' WHERE `statut_financier` = 'COMPLETE';

ALTER TABLE `accouchement_dossiers` MODIFY COLUMN `statut_medical` enum('NON_VALIDE','VALIDE','EN_ATTENTE') DEFAULT 'NON_VALIDE';
ALTER TABLE `accouchement_dossiers` MODIFY COLUMN `statut_financier` enum('NON_VALIDE','VALIDE','EN_ATTENTE') DEFAULT 'NON_VALIDE';

-- 3. Table kt_doctor_situations
ALTER TABLE `kt_doctor_situations` DROP FOREIGN KEY `FK_kt_doctor_situations_kt_doctors`;
ALTER TABLE `kt_doctor_situations` ADD CONSTRAINT `FK_kt_doctor_situations_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`);

-- 4. Table kt_dossier_patient
ALTER TABLE `kt_dossier_patient` DROP FOREIGN KEY `FK_kt_dossier_patient_kt_doctors`;
ALTER TABLE `kt_dossier_patient` ADD CONSTRAINT `FK_kt_dossier_patient_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`);

-- 5. Table kt_programme
ALTER TABLE `kt_programme` DROP FOREIGN KEY `FK_kt_programme_kt_doctors`;
ALTER TABLE `kt_programme` ADD CONSTRAINT `FK_kt_programme_doctors` FOREIGN KEY (`id_doctor`) REFERENCES `doctors` (`id`);

-- 6. Table medecin_interne_actes
ALTER TABLE `medecin_interne_actes`
ADD COLUMN `duree_bloc` int(11) DEFAULT 90 AFTER `annule_at`;

ALTER TABLE `medecin_interne_actes`
ADD KEY `idx_est_annule` (`est_annule`),
ADD KEY `idx_annule_par` (`annule_par`);

ALTER TABLE `medecin_interne_actes`
ADD CONSTRAINT `fk_acte_annule_par` FOREIGN KEY (`annule_par`) REFERENCES `personnel` (`id_personnel`);

-- 7. Table medecin_interne_actes_supplementaires
ALTER TABLE `medecin_interne_actes_supplementaires` DROP FOREIGN KEY `medecin_interne_actes_supplementaires_ibfk_2`;
ALTER TABLE `medecin_interne_actes_supplementaires` ADD CONSTRAINT `FK_medecin_interne_actes_supplementaires_location_bloc_acte` FOREIGN KEY (`id_type_acte`) REFERENCES `location_bloc_acte` (`id_acte`);

-- 8. Table medecin_interne_anesthesie
ALTER TABLE `medecin_interne_anesthesie`
ADD COLUMN `est_annule` tinyint(1) DEFAULT 0 AFTER `date_creation`,
ADD COLUMN `annule_par` int(11) DEFAULT NULL AFTER `est_annule`,
ADD COLUMN `annule_at` datetime DEFAULT NULL AFTER `annule_par`,
ADD COLUMN `motif_annulation` text DEFAULT NULL AFTER `annule_at`;

-- 9. Table medecin_interne_consommables
ALTER TABLE `medecin_interne_consommables`
ADD COLUMN `est_annule` tinyint(1) DEFAULT 0 AFTER `prix_total`,
ADD COLUMN `annule_par` int(11) DEFAULT NULL AFTER `est_annule`,
ADD COLUMN `annule_at` datetime DEFAULT NULL AFTER `annule_par`,
ADD COLUMN `motif_annulation` text DEFAULT NULL AFTER `annule_at`;

-- 10. Table medecin_interne_hospitalisation
ALTER TABLE `medecin_interne_hospitalisation`
ADD COLUMN `est_annule` tinyint(1) DEFAULT 0 AFTER `nombre_nuitees_facturees`,
ADD COLUMN `annule_par` int(11) DEFAULT NULL AFTER `est_annule`,
ADD COLUMN `annule_at` datetime DEFAULT NULL AFTER `annule_par`,
ADD COLUMN `motif_annulation` text DEFAULT NULL AFTER `annule_at`;

-- 11. Table medecin_interne_situations
ALTER TABLE `medecin_interne_situations`
ADD COLUMN `est_annule` tinyint(1) DEFAULT 0 AFTER `created_by`,
ADD COLUMN `annule_par` int(11) DEFAULT NULL AFTER `est_annule`,
ADD COLUMN `annule_at` datetime DEFAULT NULL AFTER `annule_par`,
ADD COLUMN `motif_annulation` text DEFAULT NULL AFTER `annule_at`;

-- 12. Table medecin_interne_supplements
ALTER TABLE `medecin_interne_supplements`
ADD COLUMN `est_annule` tinyint(1) DEFAULT 0 AFTER `observations`,
ADD COLUMN `annule_par` int(11) DEFAULT NULL AFTER `est_annule`,
ADD COLUMN `annule_at` datetime DEFAULT NULL AFTER `annule_par`,
ADD COLUMN `motif_annulation` text DEFAULT NULL AFTER `annule_at`;

-- 13. Table menu_items
ALTER TABLE `menu_items`
ADD COLUMN `tooltip` varchar(255) DEFAULT NULL;

-- 14. Table menu_items_admin
ALTER TABLE `menu_items_admin`
ADD COLUMN `tooltip` varchar(255) DEFAULT NULL;

-- 15. Table services
ALTER TABLE `services`
CHANGE COLUMN `tarif_fixe_sejour_court` `tarif_sejour_court` decimal(10,2) DEFAULT 0.00 COMMENT 'Tarif fixe pour sejour court (<24h)';

-- Recréation de la vue v_accouchements_sans_documents pour correspondre aux nouveaux champs
DROP VIEW IF EXISTS `v_accouchements_sans_documents`;
CREATE VIEW `v_accouchements_sans_documents` AS 
SELECT 
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
WHERE (`a`.`documents_generes` = 0);

SET FOREIGN_KEY_CHECKS=1;
