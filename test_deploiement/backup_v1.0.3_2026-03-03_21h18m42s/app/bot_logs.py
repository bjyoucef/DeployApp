# app/bot_logs.py

from flask import render_template, request, jsonify
from app import app, get_db_connection
from app.utils.utiles import login_required
import pymysql
from datetime import datetime


# ==================== RÉCUPÉRATION DES LOGS ====================

def get_logs_filtered(
        user_id = None,
        action_type = None,
        start_date = None,
        end_date = None,
        search = None,
        limit = 100,
        offset = 0
        ):
    """Récupère les logs avec filtres"""
    conn = get_db_connection()
    if not conn:
        return [ ], 0

    try:
        cursor = conn.cursor()

        # Construction de la requête WHERE
        where_clauses = [ ]
        params = [ ]

        if user_id:
            where_clauses.append( "l.user_id = %s" )
            params.append( user_id )

        if action_type and action_type != 'all':
            where_clauses.append( "l.action_type = %s" )
            params.append( action_type )

        if start_date:
            where_clauses.append( "l.created_at >= %s" )
            params.append( start_date )

        if end_date:
            where_clauses.append( "l.created_at <= %s" )
            params.append( end_date )

        if search:
            where_clauses.append( "(l.action_name LIKE %s OR l.message_text LIKE %s OR s.username LIKE %s)" )
            search_param = f"%{search}%"
            params.extend( [ search_param, search_param, search_param ] )

        where_clause = " AND " + " AND ".join( where_clauses ) if where_clauses else ""

        # Compter le total
        count_query = f"""
            SELECT COUNT(*) as total
            FROM bot_telegram_logs l
            LEFT JOIN bot_telegram_sessions s ON l.user_id = s.user_id
            WHERE 1=1 {where_clause}
        """
        cursor.execute( count_query, params )
        total = cursor.fetchone()[ 'total' ]

        # Récupérer les logs
        query = f"""
            SELECT 
                l.*,
                s.username,
                s.first_name,
                s.last_name
            FROM bot_telegram_logs l
            LEFT JOIN bot_telegram_sessions s ON l.user_id = s.user_id
            WHERE 1=1 {where_clause}
            ORDER BY l.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend( [ limit, offset ] )
        cursor.execute( query, params )
        logs = cursor.fetchall()

        cursor.close()
        return logs, total

    except pymysql.MySQLError as e:
        print( f"Erreur récupération logs: {e}" )
        return [ ], 0
    finally:
        conn.close()


def get_users_list():
    """Récupère la liste des utilisateurs ayant utilisé le bot"""
    conn = get_db_connection()
    if not conn:
        return [ ]

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id,
                   username,
                   first_name,
                   last_name,
                   total_commands + total_buttons as total_actions,
                   last_login
            FROM bot_telegram_sessions
            WHERE is_active = TRUE
            ORDER BY last_login DESC
                       """
                )
        users = cursor.fetchall()
        cursor.close()
        return users
    except pymysql.MySQLError as e:
        print( f"Erreur récupération utilisateurs: {e}" )
        return [ ]
    finally:
        conn.close()


def get_dashboard_stats( days = 7 ):
    """Récupère les statistiques pour le dashboard"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()

        stats = { }

        # Total utilisateurs actifs
        cursor.execute(
            """
            SELECT COUNT(*) as total
            FROM bot_telegram_sessions
            WHERE is_active = TRUE
                       """
                )
        stats[ 'total_users' ] = cursor.fetchone()[ 'total' ]

        # Utilisateurs actifs aujourd'hui
        cursor.execute(
            """
            SELECT COUNT(DISTINCT user_id) as total
            FROM bot_telegram_logs
            WHERE DATE(created_at) = CURDATE()
                       """
                )
        stats[ 'active_today' ] = cursor.fetchone()[ 'total' ]

        # Total actions aujourd'hui
        cursor.execute(
            """
            SELECT COUNT(*) as total
            FROM bot_telegram_logs
            WHERE DATE(created_at) = CURDATE()
                       """
                )
        stats[ 'actions_today' ] = cursor.fetchone()[ 'total' ]

        # Total actions période
        cursor.execute(
            f"""
            SELECT COUNT(*) as total
            FROM bot_telegram_logs
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        """, (days,)
            )
        stats[ 'actions_period' ] = cursor.fetchone()[ 'total' ]

        # Actions par type (période)
        cursor.execute(
            f"""
            SELECT 
                action_type,
                COUNT(*) as count
            FROM bot_telegram_logs
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY action_type
        """, (days,)
            )
        stats[ 'actions_by_type' ] = cursor.fetchall()

        # Top 10 actions
        cursor.execute(
            f"""
            SELECT 
                action_name,
                COUNT(*) as count
            FROM bot_telegram_logs
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY action_name
            ORDER BY count DESC
            LIMIT 10
        """, (days,)
            )
        stats[ 'top_actions' ] = cursor.fetchall()

        # Top 10 utilisateurs
        cursor.execute(
            f"""
            SELECT 
                l.user_id,
                s.username,
                s.first_name,
                s.last_name,
                COUNT(*) as count
            FROM bot_telegram_logs l
            LEFT JOIN bot_telegram_sessions s ON l.user_id = s.user_id
            WHERE l.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY l.user_id, s.username, s.first_name, s.last_name
            ORDER BY count DESC
            LIMIT 10
        """, (days,)
            )
        stats[ 'top_users' ] = cursor.fetchall()

        # Activité par jour (derniers 30 jours)
        cursor.execute(
            """
            SELECT DATE(created_at)        as date,
                   COUNT(*)                as count,
                   COUNT(DISTINCT user_id) as unique_users
            FROM bot_telegram_logs
            WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY DATE(created_at)
            ORDER BY date ASC
                       """
                )
        stats[ 'daily_activity' ] = cursor.fetchall()

        # Taux d'erreur
        cursor.execute(
            f"""
            SELECT 
                COUNT(CASE WHEN success = FALSE THEN 1 END) as errors,
                COUNT(*) as total
            FROM bot_telegram_logs
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        """, (days,)
            )
        error_stats = cursor.fetchone()
        stats[ 'error_rate' ] = (error_stats[ 'errors' ] / error_stats[ 'total' ] * 100) if error_stats[
                                                                                                'total' ] > 0 else 0
        stats[ 'total_errors' ] = error_stats[ 'errors' ]

        cursor.close()
        return stats

    except pymysql.MySQLError as e:
        print( f"Erreur récupération statistiques: {e}" )
        return None
    finally:
        conn.close()


def get_user_detail_stats( user_id ):
    """Récupère les statistiques détaillées d'un utilisateur"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()

        stats = {}

        # Info session
        cursor.execute("""
            SELECT * FROM bot_telegram_sessions
            WHERE user_id = %s
        """, (user_id,))
        stats['session'] = cursor.fetchone()

        if not stats['session']:
            cursor.close()
            conn.close()
            return None

        # Total par type
        cursor.execute("""
            SELECT 
                action_type,
                COUNT(*) as count
            FROM bot_telegram_logs
            WHERE user_id = %s
            GROUP BY action_type
            ORDER BY count DESC
        """, (user_id,))
        stats['by_type'] = cursor.fetchall()

        # Actions favorites
        cursor.execute("""
            SELECT 
                action_name,
                COUNT(*) as count
            FROM bot_telegram_logs
            WHERE user_id = %s
            GROUP BY action_name
            ORDER BY count DESC
            LIMIT 10
        """, (user_id,))
        stats['favorite_actions'] = cursor.fetchall()

        # Activité par jour (30 derniers jours)
        cursor.execute("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as count
            FROM bot_telegram_logs
            WHERE user_id = %s
              AND created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """, (user_id,))
        stats['daily_activity'] = cursor.fetchall()

        # Dernières erreurs
        cursor.execute("""
            SELECT *
            FROM bot_telegram_logs
            WHERE user_id = %s AND success = FALSE
            ORDER BY created_at DESC
            LIMIT 10
        """, (user_id,))
        stats['recent_errors'] = cursor.fetchall()

        # Statistiques supplémentaires
        cursor.execute("""
            SELECT 
                MIN(created_at) as first_action,
                MAX(created_at) as last_action,
                COUNT(DISTINCT DATE(created_at)) as total_days,
                COUNT(*) as total_actions
            FROM bot_telegram_logs
            WHERE user_id = %s
        """, (user_id,))
        stats['summary'] = cursor.fetchone()

        cursor.close()
        return stats

    except pymysql.MySQLError as e:
        print(f"Erreur récupération stats utilisateur: {e}")
        return None
    finally:
        conn.close()


# ==================== ROUTES ====================

@app.route( '/bot_logs' )
@login_required
def bot_logs_index():
    """Page principale des logs du bot"""
    # Vérifier les permissions (tu peux ajouter un privilege spécifique)
    # if not has_permission('view_bot_logs'):
    #     return "Accès refusé", 403
    # Récupérer les paramètres de filtrage
    page = int( request.args.get( 'page', 1 ) )
    per_page = int( request.args.get( 'per_page', 50 ) )
    user_id = request.args.get( 'user_id', None )
    action_type = request.args.get( 'action_type', 'all' )
    start_date = request.args.get( 'start_date', None )
    end_date = request.args.get( 'end_date', None )
    search = request.args.get( 'search', None )

    # Calculer l'offset
    offset = (page - 1) * per_page

    # Récupérer les logs
    logs, total = get_logs_filtered(
            user_id = user_id,
            action_type = action_type,
            start_date = start_date,
            end_date = end_date,
            search = search,
            limit = per_page,
            offset = offset
            )

    # Récupérer la liste des utilisateurs pour le filtre
    users = get_users_list()

    # Calculer le nombre total de pages
    total_pages = (total + per_page - 1) // per_page

    return render_template(
            'bot_telegram/index_log.html',
            logs = logs,
            users = users,
            page = page,
            per_page = per_page,
            total = total,
            total_pages = total_pages,
            current_user_id = user_id,
            current_action_type = action_type,
            current_start_date = start_date,
            current_end_date = end_date,
            current_search = search
            )


@app.route( '/bot_logs/dashboard' )
@login_required
def bot_logs_dashboard():
    """Dashboard avec statistiques du bot"""
    days = int( request.args.get( 'days', 7 ) )
    stats = get_dashboard_stats( days = days )

    return render_template(
            'bot_telegram/dashboard_log.html',
            stats = stats,
            days = days
            )


@app.route( '/bot_logs/user/<int:user_id>' )
@login_required
def bot_logs_user_detail( user_id ):
    """Détail d'un utilisateur spécifique"""
    stats = get_user_detail_stats( user_id )

    if not stats:
        return "Utilisateur non trouvé", 404

    # Récupérer les derniers logs
    logs, _ = get_logs_filtered( user_id = user_id, limit = 50 )

    return render_template(
            'bot_telegram/user_detail_log.html',
            stats = stats,
            logs = logs,
            user_id = user_id
            )


@app.route( '/bot_logs/api/stats' )
@login_required
def bot_logs_api_stats():
    """API pour récupérer les statistiques en JSON"""
    days = int( request.args.get( 'days', 7 ) )
    stats = get_dashboard_stats( days = days )

    # Convertir les dates en string pour JSON
    if stats and stats.get( 'daily_activity' ):
        for activity in stats[ 'daily_activity' ]:
            if 'date' in activity:
                activity[ 'date' ] = activity[ 'date' ].strftime( '%Y-%m-%d' )

    return jsonify( stats )


@app.route( '/bot_logs/export' )
@login_required
def bot_logs_export():
    """Export des logs en CSV"""
    from io import StringIO
    import csv
    from flask import Response

    # Récupérer les paramètres de filtrage
    user_id = request.args.get( 'user_id', None )
    action_type = request.args.get( 'action_type', 'all' )
    start_date = request.args.get( 'start_date', None )
    end_date = request.args.get( 'end_date', None )

    # Récupérer tous les logs sans limite
    logs, _ = get_logs_filtered(
            user_id = user_id,
            action_type = action_type,
            start_date = start_date,
            end_date = end_date,
            limit = 10000
            )

    # Créer le CSV
    si = StringIO()
    writer = csv.writer( si )

    # En-têtes
    writer.writerow(
            [
                    'Date', 'Heure', 'User ID', 'Username', 'Nom', 'Type',
                    'Action', 'Succès', 'Message', 'Erreur'
                    ]
            )

    # Données
    for log in logs:
        writer.writerow(
                [
                        log[ 'created_at' ].strftime( '%Y-%m-%d' ),
                        log[ 'created_at' ].strftime( '%H:%M:%S' ),
                        log[ 'user_id' ],
                        log.get( 'username', '' ),
                        f"{log.get( 'first_name', '' )} {log.get( 'last_name', '' )}".strip(),
                        log[ 'action_type' ],
                        log[ 'action_name' ],
                        'Oui' if log[ 'success' ] else 'Non',
                        log.get( 'message_text', '' )[ :50 ] if log.get( 'message_text' ) else '',
                        log.get( 'error_message', '' )
                        ]
                )

    # Créer la réponse
    output = si.getvalue()
    si.close()

    response = Response(
            output,
            mimetype = 'text/csv',
            headers = {
                    'Content-Disposition': f'attachment; filename=bot_logs_{datetime.now().strftime( "%Y%m%d_%H%M%S" )}.csv'
                    }
            )

    return response