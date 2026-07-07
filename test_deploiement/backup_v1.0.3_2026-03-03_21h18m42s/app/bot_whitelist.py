# app/bot_whitelist.py

from flask import render_template, request, redirect, url_for, flash, jsonify
from app import app, get_db_connection
from app.utils.utiles import login_required
import pymysql


# ==================== FONCTIONS HELPER ====================

def get_whitelist_users( include_inactive = False ):
    """Récupère la liste des utilisateurs autorisés"""
    conn = get_db_connection()
    if not conn:
        return [ ]

    try:
        cursor = conn.cursor()

        where_clause = "" if include_inactive else "WHERE w.is_active = TRUE"

        query = f"""
            SELECT 
                w.*,
                p.nom as added_by_name,
                p.prenom as added_by_firstname
            FROM bot_telegram_whitelist w
            LEFT JOIN personnel p ON w.added_by = p.id_personnel
            {where_clause}
            ORDER BY w.added_at DESC
        """

        cursor.execute( query )
        users = cursor.fetchall()
        cursor.close()
        return users

    except pymysql.MySQLError as e:
        print( f"Erreur récupération whitelist: {e}" )
        return [ ]
    finally:
        conn.close()


def get_whitelist_user_by_id( whitelist_id ):
    """Récupère un utilisateur de la whitelist par son ID"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT w.*,
                   p.nom    as added_by_name,
                   p.prenom as added_by_firstname
            FROM bot_telegram_whitelist w
                     LEFT JOIN personnel p ON w.added_by = p.id_personnel
            WHERE w.id = %s
                       """, (whitelist_id,)
            )
        user = cursor.fetchone()
        cursor.close()
        return user

    except pymysql.MySQLError as e:
        print( f"Erreur récupération utilisateur: {e}" )
        return None
    finally:
        conn.close()


def get_whitelist_user_by_telegram_id( telegram_user_id ):
    """Récupère un utilisateur par son ID Telegram"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM bot_telegram_whitelist
            WHERE user_id = %s
              AND is_active = TRUE
                       """, (telegram_user_id,)
            )
        user = cursor.fetchone()
        cursor.close()
        return user

    except pymysql.MySQLError as e:
        print( f"Erreur récupération par Telegram ID: {e}" )
        return None
    finally:
        conn.close()


def add_whitelist_user(
        user_id, username = None, first_name = None, last_name = None,
        added_by = None, notes = None
        ):
    """Ajoute un utilisateur à la whitelist"""
    conn = get_db_connection()
    if not conn:
        return False, "Erreur de connexion à la base de données"

    try:
        cursor = conn.cursor()

        # Vérifier si l'utilisateur existe déjà
        cursor.execute( "SELECT id, is_active FROM bot_telegram_whitelist WHERE user_id = %s", (user_id,) )
        existing = cursor.fetchone()

        if existing:
            if existing[ 'is_active' ]:
                return False, "Cet utilisateur est déjà dans la liste blanche"
            else:
                # Réactiver l'utilisateur
                cursor.execute(
                    """
                    UPDATE bot_telegram_whitelist
                    SET is_active  = TRUE,
                        username   = %s,
                        first_name = %s,
                        last_name  = %s,
                        notes      = %s,
                        added_by   = %s,
                        added_at   = NOW()
                    WHERE user_id = %s
                               """, (username, first_name, last_name, notes, added_by, user_id)
                    )
                conn.commit()
                cursor.close()
                return True, "Utilisateur réactivé avec succès"

        # Ajouter le nouvel utilisateur
        cursor.execute(
            """
            INSERT INTO bot_telegram_whitelist
                (user_id, username, first_name, last_name, added_by, notes, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                       """, (user_id, username, first_name, last_name, added_by, notes)
            )

        conn.commit()
        cursor.close()
        return True, "Utilisateur ajouté avec succès"

    except pymysql.MySQLError as e:
        print( f"Erreur ajout utilisateur: {e}" )
        return False, f"Erreur base de données: {str( e )}"
    finally:
        conn.close()


def update_whitelist_user(
        whitelist_id, username = None, first_name = None,
        last_name = None, notes = None, is_active = True
        ):
    """Met à jour un utilisateur de la whitelist"""
    conn = get_db_connection()
    if not conn:
        return False, "Erreur de connexion à la base de données"

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE bot_telegram_whitelist
            SET username   = %s,
                first_name = %s,
                last_name  = %s,
                notes      = %s,
                is_active  = %s
            WHERE id = %s
                       """, (username, first_name, last_name, notes, is_active, whitelist_id)
            )

        conn.commit()
        cursor.close()
        return True, "Utilisateur mis à jour avec succès"

    except pymysql.MySQLError as e:
        print( f"Erreur mise à jour utilisateur: {e}" )
        return False, f"Erreur base de données: {str( e )}"
    finally:
        conn.close()


def delete_whitelist_user( whitelist_id ):
    """Désactive un utilisateur de la whitelist (soft delete)"""
    conn = get_db_connection()
    if not conn:
        return False, "Erreur de connexion à la base de données"

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE bot_telegram_whitelist
            SET is_active = FALSE
            WHERE id = %s
                       """, (whitelist_id,)
            )

        conn.commit()
        cursor.close()
        return True, "Utilisateur désactivé avec succès"

    except pymysql.MySQLError as e:
        print( f"Erreur désactivation utilisateur: {e}" )
        return False, f"Erreur base de données: {str( e )}"
    finally:
        conn.close()


def hard_delete_whitelist_user( whitelist_id ):
    """Supprime définitivement un utilisateur de la whitelist"""
    conn = get_db_connection()
    if not conn:
        return False, "Erreur de connexion à la base de données"

    try:
        cursor = conn.cursor()
        cursor.execute( "DELETE FROM bot_telegram_whitelist WHERE id = %s", (whitelist_id,) )
        conn.commit()
        cursor.close()
        return True, "Utilisateur supprimé définitivement"

    except pymysql.MySQLError as e:
        print( f"Erreur suppression utilisateur: {e}" )
        return False, f"Erreur base de données: {str( e )}"
    finally:
        conn.close()


def update_last_login( telegram_user_id ):
    """Met à jour la dernière connexion d'un utilisateur"""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE bot_telegram_whitelist
            SET last_login = NOW()
            WHERE user_id = %s
                       """, (telegram_user_id,)
            )
        conn.commit()
        cursor.close()
    except pymysql.MySQLError as e:
        print( f"Erreur mise à jour last_login: {e}" )
    finally:
        conn.close()


def get_active_telegram_ids():
    """Récupère la liste des IDs Telegram actifs (pour remplacer TELEGRAM_ALLOWED_USERS)"""
    conn = get_db_connection()
    if not conn:
        return [ ]

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id
            FROM bot_telegram_whitelist
            WHERE is_active = TRUE
                       """
                )
        results = cursor.fetchall()
        cursor.close()
        return [ row[ 'user_id' ] for row in results ]

    except pymysql.MySQLError as e:
        print( f"Erreur récupération IDs actifs: {e}" )
        return [ ]
    finally:
        conn.close()


# ==================== ROUTES ====================

@app.route( '/bot_whitelist' )
@login_required
def bot_whitelist_index():
    """Page principale de gestion de la whitelist"""
    # Vérifier les permissions (tu peux ajouter un privilege spécifique)
    # if not has_permission('manage_bot_whitelist'):
    #     flash("Vous n'avez pas les permissions nécessaires", "danger")
    #     return redirect(url_for('index'))
    show_inactive = request.args.get( 'show_inactive', 'false' ) == 'true'
    users = get_whitelist_users( include_inactive = show_inactive )

    return render_template(
            'bot_telegram/index_whitelist.html',
            users = users,
            show_inactive = show_inactive
            )


@app.route( '/bot_whitelist/add', methods = [ 'GET', 'POST' ] )
@login_required
def bot_whitelist_add():
    """Ajouter un utilisateur à la whitelist"""
    if request.method == 'POST':
        user_id = request.form.get( 'user_id' )
        username = request.form.get( 'username' ) or None
        first_name = request.form.get( 'first_name' ) or None
        last_name = request.form.get( 'last_name' ) or None
        notes = request.form.get( 'notes' ) or None

        # Validation
        if not user_id:
            flash( "L'ID Telegram est obligatoire", "danger" )
            return render_template( 'bot_telegram/form_whitelist.html', action = 'add' )

        try:
            user_id = int( user_id )
        except ValueError:
            flash( "L'ID Telegram doit être un nombre", "danger" )
            return render_template( 'bot_telegram/form_whitelist.html', action = 'add' )

        # Récupérer l'ID du personnel connecté
        from flask import session

        added_by = session.get( 'user_id' )

        success, message = add_whitelist_user(
                user_id = user_id,
                username = username,
                first_name = first_name,
                last_name = last_name,
                added_by = added_by,
                notes = notes
                )

        if success:
            flash( message, "success" )
            return redirect( url_for( 'bot_whitelist_index' ) )
        else:
            flash( message, "danger" )
            return render_template( 'bot_telegram/form_whitelist.html', action = 'add' )

    return render_template( 'bot_telegram/form_whitelist.html', action = 'add' )


@app.route( '/bot_whitelist/edit/<int:whitelist_id>', methods = [ 'GET', 'POST' ] )
@login_required
def bot_whitelist_edit( whitelist_id ):
    """Modifier un utilisateur de la whitelist"""
    user = get_whitelist_user_by_id( whitelist_id )

    if not user:
        flash( "Utilisateur non trouvé", "danger" )
        return redirect( url_for( 'bot_whitelist_index' ) )

    if request.method == 'POST':
        username = request.form.get( 'username' ) or None
        first_name = request.form.get( 'first_name' ) or None
        last_name = request.form.get( 'last_name' ) or None
        notes = request.form.get( 'notes' ) or None
        is_active = request.form.get( 'is_active' ) == 'on'

        success, message = update_whitelist_user(
                whitelist_id = whitelist_id,
                username = username,
                first_name = first_name,
                last_name = last_name,
                notes = notes,
                is_active = is_active
                )

        if success:
            flash( message, "success" )
            return redirect( url_for( 'bot_whitelist_index' ) )
        else:
            flash( message, "danger" )

    return render_template( 'bot_telegram/form_whitelist.html', action = 'edit', user = user )


@app.route( '/bot_whitelist/delete/<int:whitelist_id>', methods = [ 'POST' ] )
@login_required
def bot_whitelist_delete( whitelist_id ):
    """Désactiver un utilisateur de la whitelist"""
    success, message = delete_whitelist_user( whitelist_id )

    if success:
        flash( message, "success" )
    else:
        flash( message, "danger" )

    return redirect( url_for( 'bot_whitelist_index' ) )


@app.route( '/bot_whitelist/hard_delete/<int:whitelist_id>', methods = [ 'POST' ] )
@login_required
def bot_whitelist_hard_delete( whitelist_id ):
    """Supprimer définitivement un utilisateur"""
    success, message = hard_delete_whitelist_user( whitelist_id )

    if success:
        flash( message, "warning" )
    else:
        flash( message, "danger" )

    return redirect( url_for( 'bot_whitelist_index' ) )


@app.route( '/bot_whitelist/activate/<int:whitelist_id>', methods = [ 'POST' ] )
@login_required
def bot_whitelist_activate( whitelist_id ):
    """Réactiver un utilisateur"""
    user = get_whitelist_user_by_id( whitelist_id )

    if user:
        success, message = update_whitelist_user(
                whitelist_id = whitelist_id,
                username = user[ 'username' ],
                first_name = user[ 'first_name' ],
                last_name = user[ 'last_name' ],
                notes = user[ 'notes' ],
                is_active = True
                )

        if success:
            flash( "Utilisateur réactivé avec succès", "success" )
        else:
            flash( message, "danger" )
    else:
        flash( "Utilisateur non trouvé", "danger" )

    return redirect( url_for( 'bot_whitelist_index' ) )


# ==================== API POUR LE BOT ====================

@app.route( '/bot_whitelist/api/check/<int:telegram_user_id>' )
def bot_whitelist_api_check( telegram_user_id ):
    """API pour vérifier si un utilisateur est autorisé (utilisé par le bot)"""
    user = get_whitelist_user_by_telegram_id( telegram_user_id )

    if user:
        # Mettre à jour la dernière connexion
        update_last_login( telegram_user_id )

        return jsonify(
                {
                        'authorized': True,
                        'user': {
                                'id': user[ 'id' ],
                                'user_id': user[ 'user_id' ],
                                'username': user[ 'username' ],
                                'first_name': user[ 'first_name' ],
                                'last_name': user[ 'last_name' ]
                                }
                        }
                )
    else:
        return jsonify( { 'authorized': False } ), 403


@app.route( '/bot_whitelist/api/list' )
def bot_whitelist_api_list():
    """API pour récupérer la liste des IDs autorisés (pour le bot)"""
    ids = get_active_telegram_ids()
    return jsonify( { 'allowed_ids': ids } )