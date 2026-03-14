"""
Translation module for DeployApp.
Provides dictionaries for French (fr) and English (en) UI strings.
"""

import os
import json
from pathlib import Path

# Try to load language from config once
APP_DIR = Path(__file__).parent
CONFIG_FILE = APP_DIR / "deploy_config.json"

_current_lang = "fr"

try:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            _current_lang = cfg.get("language", "fr")
except Exception:
    pass

def set_language(lang: str):
    global _current_lang
    if lang in ('fr', 'en'):
        _current_lang = lang

def get_language() -> str:
    return _current_lang

def tr(key: str, **kwargs) -> str:
    """Returns the translation for the given key in the current language."""
    text = TRANSLATIONS.get(key, {}).get(_current_lang, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text

TRANSLATIONS = {
    # --- Form / Options UI ---
    "app_title": {"fr": "Déploiement Serveur Réseau", "en": "Network Server Deployment"},
    "deploy_method_box": {"fr": "🛠 Méthode", "en": "🛠 Method"},
    "method_smb": {"fr": "SMB / Local", "en": "SMB / Local"},
    "method_ssh": {"fr": "SSH / SFTP", "en": "SSH / SFTP"},
    
    "lbl_local_dir": {"fr": "📂 Dossier Local", "en": "📂 Local Folder"},
    "lbl_remote_dir": {"fr": "🌐 Dossier Serveur", "en": "🌐 Remote Folder"},
    "btn_browse": {"fr": "Parcourir", "en": "Browse"},
    
    "lbl_ssh_host": {"fr": "Hôte SSH:", "en": "SSH Host:"},
    "lbl_ssh_user": {"fr": "Utilisateur:", "en": "User:"},
    "lbl_ssh_password": {"fr": "Mot de passe:", "en": "Password:"},
    "lbl_ssh_port": {"fr": "Port:", "en": "Port:"},
    "lbl_ssh_key": {"fr": "Clé privée:", "en": "Private Key:"},
    "btn_browse_key": {"fr": "Parcourir", "en": "Browse"},
    
    "btn_test_ssh": {"fr": "🔌 Tester la connexion", "en": "🔌 Test Connection"},
    "btn_test_ssh_loading": {"fr": "🔌 Connexion en cours...", "en": "🔌 Connecting..."},
    
    "btn_exclusions": {"fr": "⚙ Exclusions", "en": "⚙ Exclusions"},
    "lbl_hash_md5": {"fr": "Hash MD5", "en": "MD5 Hash"},
    "lbl_auto_backup": {"fr": "Backup auto", "en": "Auto Backup"},
    
    "btn_restart_server": {"fr": "🔄 Redémarrer", "en": "🔄 Restart"},
    "btn_restart_server_loading": {"fr": "🔄 Redémarrage...", "en": "🔄 Restarting..."},
    "btn_backup_db": {"fr": "💾 Backup BDD", "en": "💾 DB Backup"},
    "btn_backup_db_loading": {"fr": "💾 Backup en cours...", "en": "💾 Backing up..."},
    
    "btn_scan": {"fr": "🔍 Scanner", "en": "🔍 Scan"},
    "btn_deploy": {"fr": "🚀 Déployer", "en": "🚀 Deploy"},
    
    "btn_minor": {"fr": "Mineur +1", "en": "Minor +1"},
    "btn_major": {"fr": "Majeur +1", "en": "Major +1"},
    
    # --- Stats ---
    "stat_total": {"fr": "📦 Total", "en": "📦 Total"},
    "stat_new": {"fr": "✨ Nouveaux", "en": "✨ New"},
    "stat_modified": {"fr": "📝 Modifiés", "en": "📝 Modified"},
    "stat_deleted": {"fr": "🗑 Supprimés", "en": "🗑 Deleted"},
    "stat_uptodate": {"fr": "✅ À jour", "en": "✅ Up-to-date"},
    "stat_success": {"fr": "Succès", "en": "Success"},
    "stat_errors": {"fr": "Erreurs", "en": "Errors"},
    
    # --- Tabs ---
    "tab_files": {"fr": "📄 Fichiers", "en": "📄 Files"},
    "tab_logs": {"fr": "📋 Logs", "en": "📋 Logs"},
    "tab_history": {"fr": "📊 Historique", "en": "📊 History"},
    "tab_changelog": {"fr": "📋 Changelog", "en": "📋 Changelog"},
    
    "btn_tab_refresh": {"fr": "🔄 Rafraîchir", "en": "🔄 Refresh"},
    "btn_tab_export": {"fr": "📥 Exporter", "en": "📥 Export"},
    
    # --- Files Tab Filters & Selection ---
    "filter_all": {"fr": "Tous", "en": "All"},
    "filter_new": {"fr": "🆕 Nouveaux", "en": "🆕 New"},
    "filter_modified": {"fr": "📝 Modifiés", "en": "📝 Modified"},
    "filter_deleted": {"fr": "🗑 Supprimés", "en": "🗑 Deleted"},
    "search_placeholder": {"fr": "🔍 Rechercher...", "en": "🔍 Search..."},
    
    "btn_sel_all": {"fr": "☑ Tout Sélectionner", "en": "☑ Select All"},
    "btn_desel_all": {"fr": "☐ Tout Désélectionner", "en": "☐ Deselect All"},
    
    # --- Main file tree headers ---
    "col_check": {"fr": "✓", "en": "✓"},
    "col_status": {"fr": "Statut", "en": "Status"},
    "col_file": {"fr": "Fichier", "en": "File"},
    "col_size": {"fr": "Taille", "en": "Size"},
    "col_local": {"fr": "Local", "en": "Local"},
    "col_remote": {"fr": "Serveur", "en": "Server"},
    
    # --- Logs Tab ---
    "btn_clear_logs": {"fr": "🗑 Effacer les logs", "en": "🗑 Clear logs"},
    
    # --- History Tab Headers ---
    "col_hist_version": {"fr": "Version", "en": "Version"},
    "col_hist_date": {"fr": "Date", "en": "Date"},
    "col_hist_status": {"fr": "Statut", "en": "Status"},
    "col_hist_total": {"fr": "Total", "en": "Total"},
    "col_hist_success": {"fr": "Succès", "en": "Success"},
    "col_hist_errors": {"fr": "Erreurs", "en": "Errors"},
    "col_hist_duration": {"fr": "Durée", "en": "Duration"},
    
    # --- Changelog Tab Headers ---
    "col_cl_version": {"fr": "Version", "en": "Version"},
    "col_cl_date": {"fr": "Date", "en": "Date"},
    "col_cl_added": {"fr": "✨ Ajoutés", "en": "✨ Added"},
    "col_cl_modified": {"fr": "📝 Modifiés", "en": "📝 Modified"},
    "col_cl_deleted": {"fr": "🗑 Supprimés", "en": "🗑 Deleted"},
    "col_cl_result": {"fr": "Résultat", "en": "Result"},
    "col_cl_duration": {"fr": "Durée", "en": "Duration"},
    
    # --- Status bar ---
    "status_ready": {"fr": "Prêt", "en": "Ready"},
    "status_ssh_test": {"fr": "Test de la connexion SSH...", "en": "Testing SSH connection..."},
    "status_restarting": {"fr": "Redémarrage des services en cours...", "en": "Restarting services..."},
    "status_restart_error": {"fr": "Erreur au redémarrage", "en": "Restart error"},
    "status_backup": {"fr": "Création du backup MariaDB...", "en": "Creating MariaDB backup..."},
    "status_backup_error": {"fr": "Erreur backup BDD", "en": "DB backup error"},
    "status_scan_loading": {"fr": "Chargement du diff pour {file}...", "en": "Loading diff for {file}..."},
    "status_scan_in_progress": {"fr": "Analyse en cours...", "en": "Scanning..."},
    "status_scan_ssh_error": {"fr": "Échec connexion SSH", "en": "SSH connection failed"},
    "status_scan_ready": {"fr": "Prêt — {count} fichier(s) à déployer", "en": "Ready — {count} file(s) to deploy"},
    "status_deploy_in_progress": {"fr": "Déploiement {version} en cours...", "en": "Deploying {version}..."},
    "log_svc_stop_port": {"fr": "Arrêt du service sur le port {port}...", "en": "Stopping service on port {port}..."},
    "log_svc_stop_warn": {"fr": "Warning lors de l'arrêt : {err}", "en": "Warning during stop: {err}"},
    "log_svc_write_scripts": {"fr": "Écriture des scripts de démarrage dans {rdir} via SFTP...", "en": "Writing startup scripts to {rdir} via SFTP..."},
    "log_svc_config_task": {"fr": "Configuration de la tâche planifiée...", "en": "Configuring scheduled task..."},
    "log_svc_setup_task": {"fr": "Setup tâche: exit={exit} out={out} err={err}", "en": "Task setup: exit={exit} out={out} err={err}"},
    "log_svc_started": {"fr": "✅ Service lancé (tâche SYSTEM '{task}', redémarrage auto, au boot).", "en": "✅ Service started (SYSTEM task '{task}', auto-restart, on boot)."},
    "log_svc_task_err": {"fr": "❌ Erreur configuration tâche : {err}", "en": "❌ Task configuration error: {err}"},
    "log_svc_nginx_restart": {"fr": "Redémarrage de Nginx...", "en": "Restarting Nginx..."},
    "log_svc_all_ok": {"fr": "✅ Redémarrage des services effectué avec succès.", "en": "✅ Services restarted successfully."},
    "log_backup_db_ok": {"fr": "✅ Backup de la base de données terminé.", "en": "✅ Database backup complete."},
    "log_exclusion_added": {"fr": "🚫 Exclusion ajoutée : « {pat} »", "en": "🚫 Exclusion added: « {pat} »"},
    "log_scan_start": {"fr": "  ANALYSE DES FICHIERS ({method})", "en": "  FILE SCANNING ({method})"},
    "log_scan_local": {"fr": "📂 Local  : {path}", "en": "📂 Local  : {path}"},
    "log_scan_remote": {"fr": "📡 Serveur : {path}", "en": "📡 Remote : {path}"},
    "log_ssh_connecting": {"fr": "Connexion SSH vers {host}...", "en": "SSH connection to {host}..."},
    "log_ssh_connected": {"fr": "✅ Connecté via SSH/SFTP.", "en": "✅ Connected via SSH/SFTP."},
    "log_ssh_error": {"fr": "❌ Erreur connexion SSH : {err}", "en": "❌ SSH connection error: {err}"},
    "log_ssh_fail": {"fr": "Échec connexion SSH", "en": "SSH connection failed"},
    "log_files_found": {"fr": "{count} fichiers trouvés dans le dossier local", "en": "{count} files found in local folder"},
    "log_threads": {"fr": "{count} threads parallèles", "en": "{count} parallel threads"},
    "log_scan_err": {"fr": "  ❌ Erreur scan : {err}", "en": "  ❌ Scan error: {err}"},
    "log_search_deleted": {"fr": "\n🔍 Recherche des fichiers supprimés localement...", "en": "\n🔍 Searching for locally deleted files..."},
    "log_deleted_file": {"fr": "  🗑 [Supprimé] {file}", "en": "  🗑 [Deleted] {file}"},
    "log_scan_done": {"fr": "✅ Analyse terminée : {new} nouveaux, {mod} modifiés, {del_c} supprimés, {upd} à jour", "en": "✅ Scan complete: {new} new, {mod} modified, {del_c} deleted, {upd} up-to-date"},
    "log_deploy_cancel": {"fr": "Déploiement annulé.", "en": "Deployment cancelled."},
    "log_deploy_success": {"fr": "🚀 Déploiement réussi pour {version}", "en": "🚀 Deployment successful for {version}"},
    "log_deploy_partial": {"fr": "⚠️ Déploiement avec erreurs pour {version}", "en": "⚠️ Deployment with errors for {version}"},
    "log_deploy_stats": {"fr": "⚡ {success} copiés, {err} erreurs — Durée: {duration:.1f}s", "en": "⚡ {success} copied, {err} errors — Duration: {duration:.1f}s"},
    "log_create_backup": {"fr": "📦 Création du backup : {path}", "en": "📦 Creating backup: {path}"},
    "log_backup_ssh_ok": {"fr": "  ✅ Backup SSH réussi.", "en": "  ✅ SSH Backup successful."},
    "log_backup_ok": {"fr": "  ✅ Backup réussi.", "en": "  ✅ Backup successful."},
    "log_backup_err": {"fr": "  ❌ Erreur Backup : {err}", "en": "  ❌ Backup error: {err}"},
    
    "err_size_mismatch": {"fr": "Taille incorrecte après copie : {copied} vs {local}", "en": "Incorrect size after copy: {copied} vs {local}"},
    "err_size_mismatch_ssh": {"fr": "Taille incorrecte après copie SSH : {remote} vs {local}", "en": "Incorrect size after SSH copy: {remote} vs {local}"},
    "err_write_version": {"fr": "Erreur écriture VERSION : {err}", "en": "Error writing VERSION: {err}"},
    "err_paramiko_missing": {"fr": "La bibliothèque 'paramiko' n'est pas installée. Impossible d'utiliser SSH.", "en": "The 'paramiko' library is not installed. Impossible to use SSH."},
    "csv_header": {"fr": "Version,Date,Statut,Total,Succès,Erreurs,Durée(s),Local,Serveur\n", "en": "Version,Date,Status,Total,Success,Errors,Duration(s),Local,Remote\n"},
    "log_changelog_saved": {"fr": "📋 Changelog enregistré dans la base de données", "en": "📋 Changelog saved in the database"},
    "err_changelog_sqlite": {"fr": "⚠ Erreur enregistrement changelog SQLite : {err}", "en": "⚠ Error saving SQLite changelog: {err}"},
    "err_changelog_write": {"fr": "⚠ Erreur écriture changelog ({dir}) : {err}", "en": "⚠ Error writing changelog ({dir}): {err}"},
    "log_version_bumped": {"fr": "VERSION →", "en": "VERSION →"},
    "log_deleted_from_server": {"fr": "(supprimé du serveur)", "en": "(deleted from server)"},
    "log_written_both": {"fr": "(écrit dans local + serveur)", "en": "(written to local + remote)"},
    "changelog_desc": {"fr": "Toutes les modifications du projet sont documentées ici.", "en": "All modifications to the project are documented here."},
    "log_deployed_on": {"fr": "Déployé le", "en": "Deployed on"},
    
    "err_save_config": {"fr": "Erreur de sauvegarde config : {err}", "en": "Config save error: {err}"},
    "err_not_connected": {"fr": "Pas connecté.", "en": "Not connected."},
    "err_sftp_not_connected": {"fr": "SFTP non connecté.", "en": "SFTP not connected."},
    "err_read_remote": {"fr": "❌ Erreur lecture fichier distant : {err}", "en": "❌ Error reading remote file: {err}"},
    "log_version_arrow_v": {"fr": "🏷 Version → v{v}", "en": "🏷 Version → v{v}"},
    "date_format_long": {"fr": "%d/%m/%Y à %H:%M:%S", "en": "%Y-%m-%d at %H:%M:%S"},
    
    # --- Context Menus ---
    "ctx_diff": {"fr": "🔍 Comparer les modifications (Diff)", "en": "🔍 Compare changes (Diff)"},
    "ctx_exclude_file": {"fr": "🚫 Exclure le fichier  « {name} »", "en": "🚫 Exclude file  « {name} »"},
    "ctx_exclude_folder": {"fr": "📁 Exclure le dossier  « {name} »", "en": "📁 Exclude folder  « {name} »"},
    
    # --- MessageBoxes ---
    "msg_err_title": {"fr": "Erreur", "en": "Error"},
    "msg_warn_title": {"fr": "Avertissement", "en": "Warning"},
    "msg_info_title": {"fr": "Info", "en": "Info"},
    "msg_success_title": {"fr": "Succès", "en": "Success"},
    "msg_confirm_title": {"fr": "Confirmer le déploiement", "en": "Confirm Deployment"},
    "msg_bin_title": {"fr": "Fichier binaire", "en": "Binary File"},
    
    "err_local_dir_missing": {"fr": "Configurez d'abord le dossier local.", "en": "Configure local folder first."},
    "err_ssh_host_missing": {"fr": "Veuillez entrer l'hôte SSH.", "en": "Please specify the SSH host."},
    "msg_ssh_success": {"fr": "Connexion SSH réussie !", "en": "SSH connection successful!"},
    "msg_ssh_fail": {"fr": "Échec de connexion :\n{err}", "en": "Connection failed :\n{err}"},
    "title_bump_major": {"fr": "Version Majeure", "en": "Major Version"},
    "title_bump_minor": {"fr": "Version Mineure", "en": "Minor Version"},
    "lbl_diff_local": {"fr": "Dossier Local", "en": "Local Folder"},
    "lbl_diff_remote": {"fr": "Dossier Serveur", "en": "Remote Folder"},
    "title_select_ssh_key": {"fr": "Sélectionner la clé privée SSH", "en": "Select SSH Private Key"},
    "msg_binary_local": {"fr": "Le fichier local semble être binaire ou illisible :\n", "en": "Local file seems to be binary or unreadable:\n"},
    "msg_binary_remote": {"fr": "Le fichier distant semble être binaire ou illisible :\n", "en": "Remote file seems to be binary or unreadable:\n"},
    "msg_file_not_found": {"fr": "Fichier non trouvé : ", "en": "File not found: "},
    
    "question_restart": {
        "fr": "Voulez-vous vraiment redémarrer les services Waitress et Nginx sur le serveur ?",
        "en": "Do you really want to restart Waitress and Nginx services on the server?"
    },
    "msg_restart_success": {"fr": "Les services ont été redémarrés avec succès.", "en": "Services restarted successfully."},
    "msg_restart_fail": {"fr": "Échec du redémarrage :\n{err}", "en": "Restart failed:\n{err}"},
    
    "question_backup": {
        "fr": "Voulez-vous lancer la sauvegarde de MariaDB sur le serveur ?",
        "en": "Do you want to start the MariaDB backup on the server?"
    },
    "msg_backup_success": {"fr": "Sauvegarde de la base de données réussie.", "en": "Database backup successful."},
    "msg_backup_fail": {"fr": "Échec de la sauvegarde :\n{err}", "en": "Backup failed:\n{err}"},
    
    "question_bump_major": {
        "fr": "Bumper de {current} → {new_ver} ?\n\nCeci réinitialisera MINOR et PATCH à 0.",
        "en": "Bump from {current} → {new_ver} ?\n\nThis will reset MINOR and PATCH to 0."
    },
    "question_bump_minor": {
        "fr": "Bumper de {current} → {new_ver} ?\n\nCeci réinitialisera PATCH à 0.",
        "en": "Bump from {current} → {new_ver} ?\n\nThis will reset PATCH to 0."
    },

    
    "err_local_invalid": {"fr": "Dossier local invalide.", "en": "Invalid local folder."},
    "warn_smb_path": {
        "fr": "Le chemin serveur ne semble pas être un partage réseau :\n\n{path}\n\nUn chemin réseau commence normalement par \\\\serveur\\...\nVoulez-vous continuer quand même ?",
        "en": "Server path doesn't look like a network share:\n\n{path}\n\nNetwork shares usually start with \\\\server\\...\nDo you want to continue anyway?"
    },
    
    "msg_no_file_selected": {"fr": "Aucun fichier sélectionné.", "en": "No items selected."},
    "confirm_deploy_msg": {
        "fr": "Déployer {count} fichier(s) via {method} ?\n\n   🆕 Nouveaux : {new}\n   📝 Modifiés : {mod}\n   🗑 Supprimés : {del}\n   📦 Taille copie : {size}\n\nDestination : {dest}",
        "en": "Deploy {count} file(s) via {method}?\n\n   🆕 New : {new}\n   📝 Modified : {mod}\n   🗑 Deleted : {del}\n   📦 Copy size : {size}\n\nDestination : {dest}"
    },
    
    "msg_export_hist_success": {"fr": "Historique exporté vers :\n{path}", "en": "History exported to:\n{path}"},
    "msg_export_cl_success": {"fr": "Changelog exporté vers :\n{path}", "en": "Changelog exported to:\n{path}"},
    "msg_export_fail": {"fr": "Échec de l'export : {err}", "en": "Export failed: {err}"},
    
    "msg_no_hist_files": {"fr": "Aucun fichier enregistré pour ce déploiement.", "en": "No files recorded for this deployment."},
    "msg_no_cl_files": {"fr": "Aucun fichier enregistré pour ce changelog.", "en": "No files recorded for this changelog."},
    
    # --- Dialogs: Detail & Diff ---
    "dlg_diff_title": {"fr": "🔍 Diff — {name}", "en": "🔍 Diff — {name}"},
    "dlg_diff_header": {"fr": "🔍 Comparaison : {name}", "en": "🔍 Comparison : {name}"},
    "dlg_diff_added": {"fr": "Ajouté (local)", "en": "Added (local)"},
    "dlg_diff_deleted": {"fr": "Supprimé (serveur)", "en": "Deleted (server)"},
    "dlg_diff_col_local": {"fr": "  📂  LOCAL (votre version)", "en": "  📂  LOCAL (your version)"},
    "dlg_diff_col_remote": {"fr": "  🌐  SERVEUR (version distante)", "en": "  🌐  SERVER (remote version)"},
    "dlg_diff_stats": {
        "fr": "Local: {local} lignes  |  Serveur: {remote} lignes",
        "en": "Local: {local} lines  |  Server: {remote} lines"
    },
    "dlg_diff_stats_full": {
        "fr": "Local: {local} lignes  |  Serveur: {remote} lignes  |  <span style='color:{color_new}'>+{add} ajout(s)</span>  |  <span style='color:{color_del}'>-{del_c} suppression(s)</span>",
        "en": "Local: {local} lines  |  Server: {remote} lines  |  <span style='color:{color_new}'>+{add} addition(s)</span>  |  <span style='color:{color_del}'>-{del_c} deletion(s)</span>"
    },
    "dlg_close": {"fr": "Fermer", "en": "Close"},
    
    "dlg_hist_title": {"fr": "Détail du déploiement #{id}", "en": "Deployment Details #{id}"},
    "dlg_hist_header": {"fr": "📋 Déploiement #{id} — {count} fichier(s)", "en": "📋 Deployment #{id} — {count} file(s)"},
    
    "dlg_cl_title": {"fr": "📋 Changelog {version}", "en": "📋 Changelog {version}"},
    "dlg_cl_header": {"fr": "📋 Changelog {version} — {date}", "en": "📋 Changelog {version} — {date}"},
    "dlg_cl_stats": {
        "fr": "✨ {add} ajouté(s)  |  📝 {mod} modifié(s)  |  🗑 {del_c} supprimé(s)",
        "en": "✨ {add} added  |  📝 {mod} modified  |  🗑 {del_c} deleted"
    },
    "dlg_cl_added": {"fr": "✨ Ajoutés", "en": "✨ Added"},
    "dlg_cl_modified": {"fr": "📝 Modifiés", "en": "📝 Modified"},
    "dlg_cl_deleted": {"fr": "🗑 Supprimés", "en": "🗑 Deleted"},
    
    # --- Dialog: Exclusions ---
    "dlg_excl_title": {"fr": "Configurations d'exclusions", "en": "Exclusion Settings"},
    "dlg_excl_info": {"fr": "Sélectionnez les dossiers/fichiers à ignorer :", "en": "Select folders/files to ignore:"},
    "dlg_excl_help": {
        "fr": "(Cochez pour ignorer. Utilisez le bouton Supprimer pour retirer un élément de la liste.)",
        "en": "(Check to ignore. Use Remove button to delete an item from the list.)"
    },
    "btn_check_all": {"fr": "Tout cocher", "en": "Check All"},
    "btn_uncheck_all": {"fr": "Tout décocher", "en": "Uncheck All"},
    "search_excl_ph": {"fr": "🔍 Rechercher un pattern...", "en": "🔍 Search pattern..."},
    "add_excl_ph": {"fr": "ex: *.log, node_modules...", "en": "e.g., *.log, node_modules..."},
    "btn_add": {"fr": "Ajouter", "en": "Add"},
    "btn_add_folder": {"fr": "📁 Ajouter un dossier...", "en": "📁 Add Folder..."},
    "btn_remove_sel": {"fr": "Supprimer le(s) sélectionné(s) de la liste", "en": "Remove selected from list"},
    "btn_save": {"fr": "Sauvegarder", "en": "Save"},
    "dlg_excl_folder_sel": {"fr": "Sélectionner un dossier à exclure", "en": "Select a folder to exclude"},
    "dlg_select_key": {"fr": "Sélectionner la clé privée SSH", "en": "Select SSH private key"},
    "dlg_local_dir": {"fr": "Dossier Local", "en": "Local Folder"},
    "dlg_remote_dir": {"fr": "Dossier Serveur", "en": "Remote Folder"},
    "dlg_export_hist": {"fr": "Exporter l'historique", "en": "Export History"},
    "dlg_export_cl": {"fr": "Exporter le Changelog", "en": "Export Changelog"},

    # --- FileStatus format strings ---
    "fs_new": {"fr": "Nouveau", "en": "New"},
    "fs_modified": {"fr": "Modifié", "en": "Modified"},
    "fs_uptodate": {"fr": "À jour", "en": "Up-to-date"},
    "fs_deleted": {"fr": "Supprimé", "en": "Deleted"},
    
    # --- Status formats for history list ---
    "hist_status_success": {"fr": "✅ Succès", "en": "✅ Success"},
    "hist_status_partial": {"fr": "⚠ Partiel", "en": "⚠ Partial"},
    "hist_status_failed": {"fr": "❌ Échec", "en": "❌ Failed"},
    "hist_status_ip": {"fr": "⏳ En cours", "en": "⏳ In progress"}
}
