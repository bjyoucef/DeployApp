from datetime import datetime, timedelta
from flask import request, render_template, g, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, get_db_connection
from app.utils.utiles import login_required, redirect_with_message
from app.error import handle_errors
import pymysql


# ============================================================================
# CONSTANTES
# ============================================================================
class SettingsMessages:
    """Messages pour les paramètres utilisateur"""
    PROFILE_UPDATED = "Votre profil a été mis à jour avec succès."
    PASSWORD_UPDATED = "Votre mot de passe a été modifié avec succès."
    PHONE_UPDATED = "Votre numéro de téléphone a été mis à jour."
    USERNAME_UPDATED = "Votre nom d'utilisateur a été modifié avec succès."
    
    CURRENT_PASSWORD_WRONG = "Le mot de passe actuel est incorrect."
    PASSWORD_MISMATCH = "Les nouveaux mots de passe ne correspondent pas."
    PASSWORD_SAME = "Le nouveau mot de passe doit être différent de l'ancien."
    USERNAME_EXISTS = "Ce nom d'utilisateur est déjà utilisé."
    NO_MODIFICATIONS = "Aucune modification n'a été effectuée."
    MISSING_FIELDS = "Veuillez remplir tous les champs requis."


# ============================================================================
# PAGE PRINCIPALE DES PARAMÈTRES
# ============================================================================
@app.route('/settings', methods=['GET'])
@login_required
@handle_errors()
def user_settings():
    """Page principale des paramètres utilisateur"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Récupérer les informations complètes de l'utilisateur
        cursor.execute("""
            SELECT p.*, s.service_name, c.numero as telephone
            FROM personnel p
            LEFT JOIN services s ON p.id_service = s.id_service
            LEFT JOIN contacts c ON p.id_phone = c.id
            WHERE p.id_personnel = %s
        """, (session.get('user_id'),))
        user_info = cursor.fetchone()
        
        # Récupérer les rôles de l'utilisateur
        cursor.execute("""
            SELECT r.nom_role
            FROM roles r
            INNER JOIN personnel_roles pr ON r.id_role = pr.id_role
            WHERE pr.id_personnel = %s
            ORDER BY r.nom_role
        """, (session.get('user_id'),))
        user_roles = cursor.fetchall()
        
        return render_template(
            'user_settings.html',
            title='Paramètres',
            user_info=user_info,
            user_roles=user_roles,
            user=g.user
        )
    finally:
        cursor.close()
        connection.close()


# ============================================================================
# MODIFICATION DU MOT DE PASSE
# ============================================================================
@app.route('/settings/password', methods=['POST'])
@login_required
@handle_errors()
def update_password():
    """Modifier le mot de passe de l'utilisateur"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validation
        if not all([current_password, new_password, confirm_password]):
            return redirect_with_message('user_settings', SettingsMessages.MISSING_FIELDS, 'danger')
        
        if new_password != confirm_password:
            return redirect_with_message('user_settings', SettingsMessages.PASSWORD_MISMATCH, 'danger')
        
        # Vérifier le mot de passe actuel
        cursor.execute(
            'SELECT password FROM personnel WHERE id_personnel = %s',
            (session.get('user_id'),)
        )
        user = cursor.fetchone()
        
        password_is_valid = False
        if user:
            # Vérifier hash ou texte clair (pour migration ascendante)
            if check_password_hash(user['password'], current_password):
                password_is_valid = True
            elif user['password'] == current_password:
                password_is_valid = True

        if not password_is_valid:
            return redirect_with_message('user_settings', SettingsMessages.CURRENT_PASSWORD_WRONG, 'danger')
        
        if current_password == new_password:
            # Note: Si l'ancien est en clair et le nouveau aussi, c'est égal.
            # Avec le hash, on ne peut pas comparer hash vs clear.
            # On compare le nouveau mot de passe clear avec l'ancien clear si disponible
            # Ou on check si le nouveau pass match le hash existant (ce qui veut dire que c'est le même)
            if check_password_hash(user['password'], new_password) or user['password'] == new_password:
                 return redirect_with_message('user_settings', SettingsMessages.PASSWORD_SAME, 'danger')
        
        # Hashage du nouveau mot de passe
        hashed_password = generate_password_hash(new_password)

        # Mise à jour du mot de passe
        cursor.execute(
            'UPDATE personnel SET password = %s, updated_at = NOW() WHERE id_personnel = %s',
            (hashed_password, session.get('user_id'))
        )
        connection.commit()
        
        return redirect_with_message('user_settings', SettingsMessages.PASSWORD_UPDATED, 'success')
        
    except Exception as e:
        connection.rollback()
        return redirect_with_message('user_settings', f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        connection.close()


# ============================================================================
# MODIFICATION DU NOM D'UTILISATEUR
# ============================================================================
@app.route('/settings/username', methods=['POST'])
@login_required
@handle_errors()
def update_username():
    """Modifier le nom d'utilisateur"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        new_username = request.form.get('new_username', '').strip()
        current_password = request.form.get('password_confirm', '').strip()
        
        # Validation
        if not all([new_username, current_password]):
            return redirect_with_message('user_settings', SettingsMessages.MISSING_FIELDS, 'danger')
        
        # Vérifier le mot de passe
        cursor.execute(
            'SELECT password, username FROM personnel WHERE id_personnel = %s',
            (session.get('user_id'),)
        )
        user = cursor.fetchone()
        
        password_is_valid = False
        if user:
            if check_password_hash(user['password'], current_password):
                 password_is_valid = True
            elif user['password'] == current_password:
                 password_is_valid = True
        
        if not password_is_valid:
            return redirect_with_message('user_settings', SettingsMessages.CURRENT_PASSWORD_WRONG, 'danger')
        
        if user['username'] == new_username:
            return redirect_with_message('user_settings', SettingsMessages.NO_MODIFICATIONS, 'warning')
        
        # Vérifier si le nom d'utilisateur existe déjà
        cursor.execute(
            'SELECT id_personnel FROM personnel WHERE username = %s AND id_personnel != %s',
            (new_username, session.get('user_id'))
        )
        if cursor.fetchone():
            return redirect_with_message('user_settings', SettingsMessages.USERNAME_EXISTS, 'danger')
        
        # Mise à jour
        cursor.execute(
            'UPDATE personnel SET username = %s, updated_at = NOW() WHERE id_personnel = %s',
            (new_username, session.get('user_id'))
        )
        connection.commit()
        
        # Mettre à jour la session
        session['username'] = new_username
        
        return redirect_with_message('user_settings', SettingsMessages.USERNAME_UPDATED, 'success')
        
    except Exception as e:
        connection.rollback()
        return redirect_with_message('user_settings', f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        connection.close()


# ============================================================================
# MODIFICATION DU TÉLÉPHONE
# ============================================================================
@app.route('/settings/phone', methods=['POST'])
@login_required
@handle_errors()
def update_phone():
    """Modifier le numéro de téléphone"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        new_phone = request.form.get('new_phone', '').strip()
        
        if not new_phone:
            return redirect_with_message('user_settings', SettingsMessages.MISSING_FIELDS, 'danger')
        
        # Récupérer l'ID du contact
        cursor.execute(
            'SELECT id_phone FROM personnel WHERE id_personnel = %s',
            (session.get('user_id'),)
        )
        result = cursor.fetchone()
        
        if result and result['id_phone']:
            # Mettre à jour le contact existant
            cursor.execute(
                'UPDATE contacts SET numero = %s WHERE id = %s',
                (new_phone, result['id_phone'])
            )
        else:
            # Créer un nouveau contact
            cursor.execute("""
                INSERT INTO contacts (nom, numero, id_personne_add)
                VALUES (%s, %s, %s)
            """, (f"{g.user['nom']} {g.user['prenom']}", new_phone, session.get('user_id')))
            
            id_contact = cursor.lastrowid
            cursor.execute(
                'UPDATE personnel SET id_phone = %s, updated_at = NOW() WHERE id_personnel = %s',
                (id_contact, session.get('user_id'))
            )
        
        connection.commit()
        
        return redirect_with_message('user_settings', SettingsMessages.PHONE_UPDATED, 'success')
        
    except Exception as e:
        connection.rollback()
        return redirect_with_message('user_settings', f"Erreur : {str(e)}", 'danger')
    finally:
        cursor.close()
        connection.close()


# ============================================================================
# API - HISTORIQUE DES ACTIONS
# ============================================================================
@app.route('/api/user/history')
@login_required
def get_user_history():
    """Récupère l'historique des actions de l'utilisateur connecté"""
    
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    limit = request.args.get('limit', 50, type=int)
    
    # Dates par défaut: dernier mois
    if not date_debut:
        date_debut = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not date_fin:
        date_fin = datetime.now().strftime('%Y-%m-%d')
    
    user_id = session.get('user_id')
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        history = []
        
        # 1. Accouchements créés
        cursor.execute("""
            SELECT 
                'Accouchement créé' as action_type,
                CONCAT('Dossier #', id_dossier, ' - ', patiente) as description,
                created_at as action_date,
                'fas fa-baby' as icon,
                'primary' as color
            FROM accouchement_dossiers
            WHERE created_by = %s 
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, date_debut, date_fin, limit))
        history.extend(cursor.fetchall())
        
        # 2. Factures créées
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN type_facture = 'facture' THEN 'Facture créée'
                    ELSE 'Proforma créée'
                END as action_type,
                CONCAT(numero_facture, ' - ', patient_nom, ' ', COALESCE(patient_prenom, '')) as description,
                created_at as action_date,
                'fas fa-file-invoice' as icon,
                'info' as color
            FROM factures
            WHERE created_by = %s
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, date_debut, date_fin, limit))
        history.extend(cursor.fetchall())
        
        # 3. Décharges gynéco créées
        cursor.execute("""
            SELECT 
                'Décharge gynéco créée' as action_type,
                CONCAT('Décharge #', numero_decharge) as description,
                created_at as action_date,
                'fas fa-file-medical' as icon,
                'success' as color
            FROM gyneco_interne_decharges
            WHERE created_by = %s
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, date_debut, date_fin, limit))
        history.extend(cursor.fetchall())
        
        # 4. Dossiers Location Bloc créés
        cursor.execute("""
            SELECT 
                'Dossier Location Bloc créé' as action_type,
                CONCAT('Dossier #', id_dossier, ' - ', patient) as description,
                date_creation as action_date,
                'fas fa-building' as icon,
                'warning' as color
            FROM location_bloc_dossier_patient
            WHERE created_by = %s
            AND DATE(date_creation) BETWEEN %s AND %s
            ORDER BY date_creation DESC
            LIMIT %s
        """, (user_id, date_debut, date_fin, limit))
        history.extend(cursor.fetchall())
        
        # 5. Décharges KT créées
        cursor.execute("""
            SELECT 
                'Décharge KT créée' as action_type,
                CONCAT('Décharge #', numero_decharge) as description,
                date_creation as action_date,
                'fas fa-heart' as icon,
                'danger' as color
            FROM kt_decharges_paiement
            WHERE id_createur = %s
            AND DATE(date_creation) BETWEEN %s AND %s
            ORDER BY date_creation DESC
            LIMIT %s
        """, (user_id, date_debut, date_fin, limit))
        history.extend(cursor.fetchall())
        
        # 6. Paiements encaissés (accouchements)
        cursor.execute("""
            SELECT 
                'Paiement encaissé' as action_type,
                CONCAT(FORMAT(montant, 0), ' DZD - ', mode_paiement) as description,
                created_at as action_date,
                'fas fa-money-bill-wave' as icon,
                'success' as color
            FROM accouchement_paiements_bons
            WHERE encaisse_par = %s
            AND DATE(created_at) BETWEEN %s AND %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, date_debut, date_fin, limit))
        history.extend(cursor.fetchall())
        
        # 7. Actes médecin interne créés
        cursor.execute("""
            SELECT 
                'Acte médecin interne créé' as action_type,
                CONCAT(nom_acte, ' - ', patient) as description,
                date_creation as action_date,
                'fas fa-stethoscope' as icon,
                'secondary' as color
            FROM medecin_interne_actes
            WHERE created_by = %s
            AND DATE(date_creation) BETWEEN %s AND %s
            ORDER BY date_creation DESC
            LIMIT %s
        """, (user_id, date_debut, date_fin, limit))
        history.extend(cursor.fetchall())
        
        # Trier par date décroissante et limiter
        history.sort(key=lambda x: x['action_date'] if x['action_date'] else datetime.min, reverse=True)
        history = history[:limit]
        
        # Calculer les statistiques
        stats = {
            'total_actions': len(history),
            'periode': {
                'debut': date_debut,
                'fin': date_fin
            }
        }
        
        return jsonify({
            'success': True,
            'history': history,
            'stats': stats
        })
        
    except pymysql.MySQLError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        cursor.close()
        connection.close()


# ============================================================================
# API - STATISTIQUES UTILISATEUR
# ============================================================================
@app.route('/api/user/stats')
@login_required
def get_user_stats():
    """Récupère les statistiques de l'utilisateur connecté"""
    
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    
    # Dates par défaut: dernier mois
    if not date_debut:
        date_debut = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not date_fin:
        date_fin = datetime.now().strftime('%Y-%m-%d')
    
    user_id = session.get('user_id')
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        stats = {}
        
        # Accouchements
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(prix_total), 0) as total
            FROM accouchement_dossiers
            WHERE created_by = %s AND DATE(created_at) BETWEEN %s AND %s
        """, (user_id, date_debut, date_fin))
        result = cursor.fetchone()
        stats['accouchements'] = {'count': result['count'], 'total': float(result['total'] or 0)}
        
        # Factures
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(total_ttc), 0) as total
            FROM factures
            WHERE created_by = %s AND DATE(created_at) BETWEEN %s AND %s
        """, (user_id, date_debut, date_fin))
        result = cursor.fetchone()
        stats['factures'] = {'count': result['count'], 'total': float(result['total'] or 0)}
        
        # Location Bloc
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(prix_total), 0) as total
            FROM location_bloc_dossier_patient
            WHERE created_by = %s AND DATE(date_creation) BETWEEN %s AND %s
        """, (user_id, date_debut, date_fin))
        result = cursor.fetchone()
        stats['location_bloc'] = {'count': result['count'], 'total': float(result['total'] or 0)}
        
        # Décharges gynéco
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(montant_total), 0) as total
            FROM gyneco_interne_decharges
            WHERE created_by = %s AND DATE(created_at) BETWEEN %s AND %s
        """, (user_id, date_debut, date_fin))
        result = cursor.fetchone()
        stats['decharges_gyneco'] = {'count': result['count'], 'total': float(result['total'] or 0)}
        
        # Décharges KT
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(montant_total), 0) as total
            FROM kt_decharges_paiement
            WHERE id_createur = %s AND DATE(date_creation) BETWEEN %s AND %s
        """, (user_id, date_debut, date_fin))
        result = cursor.fetchone()
        stats['decharges_kt'] = {'count': result['count'], 'total': float(result['total'] or 0)}
        
        # Paiements encaissés
        cursor.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(montant), 0) as total
            FROM accouchement_paiements_bons
            WHERE encaisse_par = %s AND DATE(created_at) BETWEEN %s AND %s
        """, (user_id, date_debut, date_fin))
        result = cursor.fetchone()
        stats['paiements'] = {'count': result['count'], 'total': float(result['total'] or 0)}
        
        return jsonify({
            'success': True,
            'stats': stats,
            'periode': {
                'debut': date_debut,
                'fin': date_fin
            }
        })
        
    except pymysql.MySQLError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        cursor.close()
        connection.close()
