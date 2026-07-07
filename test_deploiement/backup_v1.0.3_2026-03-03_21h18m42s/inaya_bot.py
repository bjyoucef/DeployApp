import json
import logging
from datetime import timedelta, datetime
from typing import Optional, Dict, Any

import psycopg2
import pymysql
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from app.bot_whitelist import get_active_telegram_ids
from config.config import Config


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = Config.TELEGRAM_BOT_TOKEN


# Configuration MariaDB pour les logs
MARIADB_CONFIG = {
        'host': Config.DB_HOST,  # Utiliser ta config existante
        'user': Config.DB_USER,
        'password': Config.DB_PASSWORD,
        'database': Config.DB_NAME,
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
        }


def get_mariadb_connection():
    """Connexion à MariaDB pour les logs"""
    try:
        connection = pymysql.connect( **MARIADB_CONFIG )
        return connection
    except pymysql.MySQLError as e:
        logger.error( f"Erreur connexion MariaDB pour logs: {e}" )
        return None


class BotLogger:
    """Classe pour gérer les logs du bot Telegram"""


    @staticmethod
    def log_action(
            user_id: int,
            action_type: str,
            action_name: str,
            username: Optional[ str ] = None,
            first_name: Optional[ str ] = None,
            last_name: Optional[ str ] = None,
            action_data: Optional[ Dict[ str, Any ] ] = None,
            message_text: Optional[ str ] = None,
            success: bool = True,
            error_message: Optional[ str ] = None,
            session_id: Optional[ str ] = None
            ) -> bool:
        """
        Enregistre une action dans les logs

        Args:
            user_id: ID Telegram de l'utilisateur
            action_type: Type d'action ('command', 'button', 'query', 'error', 'login')
            action_name: Nom de la commande ou du bouton
            username: Username Telegram
            first_name: Prénom
            last_name: Nom
            action_data: Données supplémentaires (dict qui sera converti en JSON)
            message_text: Texte du message original
            success: Action réussie ou non
            error_message: Message d'erreur si échec
            session_id: ID de session

        Returns:
            bool: True si l'enregistrement a réussi
        """
        conn = get_mariadb_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()

            # Convertir action_data en JSON si présent
            action_data_json = json.dumps( action_data, ensure_ascii = False ) if action_data else None

            query = """
                    INSERT INTO bot_telegram_logs
                    (user_id, username, first_name, last_name, action_type, action_name,
                     action_data, message_text, success, error_message, session_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) \
                    """

            cursor.execute(
                query, (
                            user_id, username, first_name, last_name, action_type, action_name,
                            action_data_json, message_text, success, error_message, session_id
                            )
                )

            conn.commit()
            cursor.close()
            return True

        except pymysql.MySQLError as e:
            logger.error( f"Erreur lors de l'enregistrement du log: {e}" )
            return False
        finally:
            conn.close()


    @staticmethod
    def update_session(
            user_id: int, username: Optional[ str ] = None,
            first_name: Optional[ str ] = None, last_name: Optional[ str ] = None
            ) -> bool:
        """Met à jour ou crée une session utilisateur"""
        conn = get_mariadb_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()

            query = """
                    INSERT INTO bot_telegram_sessions
                    (user_id, username, first_name, last_name, first_login, last_login, total_commands, total_buttons)
                    VALUES (%s, %s, %s, %s, NOW(), NOW(), 0, 0)
                    ON DUPLICATE KEY UPDATE username   = VALUES(username), \
                                            first_name = VALUES(first_name), \
                                            last_name  = VALUES(last_name), \
                                            last_login = NOW(), \
                                            is_active  = TRUE \
                    """

            cursor.execute( query, (user_id, username, first_name, last_name) )
            conn.commit()
            cursor.close()
            return True

        except pymysql.MySQLError as e:
            logger.error( f"Erreur mise à jour session: {e}" )
            return False
        finally:
            conn.close()


    @staticmethod
    def increment_action_counter( user_id: int, action_type: str ) -> bool:
        """Incrémente le compteur d'actions pour un utilisateur"""
        conn = get_mariadb_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()

            if action_type == 'command':
                field = 'total_commands'
            elif action_type == 'button':
                field = 'total_buttons'
            else:
                return True  # Ne rien faire pour les autres types

            query = f"""
                UPDATE bot_telegram_sessions 
                SET {field} = {field} + 1
                WHERE user_id = %s
            """

            cursor.execute( query, (user_id,) )
            conn.commit()
            cursor.close()
            return True

        except pymysql.MySQLError as e:
            logger.error( f"Erreur incrémentation compteur: {e}" )
            return False
        finally:
            conn.close()


    @staticmethod
    def get_user_logs( user_id: int, limit: int = 50 ) -> list:
        """Récupère les derniers logs d'un utilisateur"""
        conn = get_mariadb_connection()
        if not conn:
            return [ ]

        try:
            cursor = conn.cursor()

            query = """
                    SELECT * \
                    FROM bot_telegram_logs
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s \
                    """

            cursor.execute( query, (user_id, limit) )
            logs = cursor.fetchall()
            cursor.close()
            return logs

        except pymysql.MySQLError as e:
            logger.error( f"Erreur récupération logs: {e}" )
            return [ ]
        finally:
            conn.close()


    @staticmethod
    def get_all_logs( limit: int = 100, action_type: Optional[ str ] = None ) -> list:
        """Récupère tous les logs (pour admin)"""
        conn = get_mariadb_connection()
        if not conn:
            return [ ]

        try:
            cursor = conn.cursor()

            if action_type:
                query = """
                        SELECT * \
                        FROM bot_telegram_logs
                        WHERE action_type = %s
                        ORDER BY created_at DESC
                        LIMIT %s \
                        """
                cursor.execute( query, (action_type, limit) )
            else:
                query = """
                        SELECT * \
                        FROM bot_telegram_logs
                        ORDER BY created_at DESC
                        LIMIT %s \
                        """
                cursor.execute( query, (limit,) )

            logs = cursor.fetchall()
            cursor.close()
            return logs

        except pymysql.MySQLError as e:
            logger.error( f"Erreur récupération tous les logs: {e}" )
            return [ ]
        finally:
            conn.close()


    @staticmethod
    def get_user_stats( user_id: int ) -> Optional[ Dict ]:
        """Récupère les statistiques d'un utilisateur"""
        conn = get_mariadb_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor()

            # Session info
            query_session = """
                            SELECT * \
                            FROM bot_telegram_sessions
                            WHERE user_id = %s \
                            """
            cursor.execute( query_session, (user_id,) )
            session = cursor.fetchone()

            # Action counts
            query_actions = """
                            SELECT action_type, \
                                   COUNT(*)        as count, \
                                   MAX(created_at) as last_action
                            FROM bot_telegram_logs
                            WHERE user_id = %s
                            GROUP BY action_type \
                            """
            cursor.execute( query_actions, (user_id,) )
            actions = cursor.fetchall()

            # Most used actions
            query_top_actions = """
                                SELECT action_name, \
                                       COUNT(*) as count
                                FROM bot_telegram_logs
                                WHERE user_id = %s
                                GROUP BY action_name
                                ORDER BY count DESC
                                LIMIT 5 \
                                """
            cursor.execute( query_top_actions, (user_id,) )
            top_actions = cursor.fetchall()

            cursor.close()

            return {
                    'session': session,
                    'actions': actions,
                    'top_actions': top_actions
                    }

        except pymysql.MySQLError as e:
            logger.error( f"Erreur récupération stats utilisateur: {e}" )
            return None
        finally:
            conn.close()


    @staticmethod
    def get_global_stats() -> Optional[ Dict ]:
        """Récupère les statistiques globales du bot"""
        conn = get_mariadb_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor()

            # Total users
            cursor.execute(
                "SELECT COUNT(DISTINCT user_id) as total FROM bot_telegram_sessions WHERE is_active = TRUE"
                )
            total_users = cursor.fetchone()[ 'total' ]

            # Total actions today
            cursor.execute(
                """
                SELECT COUNT(*) as total
                FROM bot_telegram_logs
                WHERE DATE(created_at) = CURDATE()
                           """
                )
            actions_today = cursor.fetchone()[ 'total' ]

            # Active users today
            cursor.execute(
                """
                SELECT COUNT(DISTINCT user_id) as total
                FROM bot_telegram_logs
                WHERE DATE(created_at) = CURDATE()
                           """
                )
            active_today = cursor.fetchone()[ 'total' ]

            # Most active users
            cursor.execute(
                """
                SELECT l.user_id,
                       s.username,
                       s.first_name,
                       COUNT(*) as actions
                FROM bot_telegram_logs l
                         LEFT JOIN bot_telegram_sessions s ON l.user_id = s.user_id
                WHERE DATE(l.created_at) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY l.user_id, s.username, s.first_name
                ORDER BY actions DESC
                LIMIT 5
                           """
                )
            top_users = cursor.fetchall()

            # Most used actions
            cursor.execute(
                """
                SELECT action_name,
                       COUNT(*) as count
                FROM bot_telegram_logs
                WHERE DATE(created_at) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY action_name
                ORDER BY count DESC
                LIMIT 10
                           """
                )
            top_actions = cursor.fetchall()

            cursor.close()

            return {
                    'total_users': total_users,
                    'actions_today': actions_today,
                    'active_today': active_today,
                    'top_users': top_users,
                    'top_actions': top_actions
                    }

        except pymysql.MySQLError as e:
            logger.error( f"Erreur récupération stats globales: {e}" )
            return None
        finally:
            conn.close()


# Fonction helper pour extraire les infos utilisateur
def get_user_info( update ) -> Dict[ str, Any ]:
    """Extrait les informations de l'utilisateur depuis l'update Telegram"""
    user = update.effective_user
    if not user:
        return { }

    return {
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
            }
# ==================== WRAPPER POUR LOGGER LES COMMANDES ====================

def log_command( func ):
    """Décorateur pour logger automatiquement les commandes"""


    async def wrapper( update: Update, context: ContextTypes.DEFAULT_TYPE ):
        user_info = get_user_info( update )
        command_name = func.__name__.replace( '_command', '' ).replace( '_', ' ' )

        # Log du début de la commande
        BotLogger.update_session( **user_info )
        BotLogger.log_action(
                action_type = 'command',
                action_name = command_name,
                message_text = update.message.text if update.message else None,
                **user_info
                )
        BotLogger.increment_action_counter( user_info[ 'user_id' ], 'command' )

        try:
            # Exécuter la commande
            result = await func( update, context )
            return result
        except Exception as e:
            # Logger l'erreur
            BotLogger.log_action(
                    action_type = 'error',
                    action_name = command_name,
                    success = False,
                    error_message = str( e ),
                    **user_info
                    )
            raise


    return wrapper


# Configuration PostgreSQL
PG_CONFIG = {
    'host': Config.PG_HOST,
    'port': Config.PG_PORT,
    'database': Config.PG_DB,
    'user': Config.PG_USER,
    'password': Config.PG_PASSWORD,
    'options': Config.PG_OPTIONS
}


def get_pg_connection():
    """Connexion PostgreSQL en lecture seule"""
    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;")
    cur.close()
    return conn


def get_valid_payment_filter():
    """
    Retourne la clause SQL pour filtrer les paiements valides.
    Exclut les virements entre caisses individuelles (VFE/VFD)
    SAUF si le compte est bancaire (Type=0) ou COFFRES 2025
    """
    return """
        AND (
            pt."Code" NOT IN ('VFE', 'VFD')
            OR a."Type" = 0
            OR a."Code" = 'COFFRES2025'
        )
    """


# Cache des IDs autorisés (rafraîchi toutes les 5 minutes)
_whitelist_cache = None
_whitelist_cache_time = None

def is_authorized( update: Update ) -> bool:
    """Vérifie l'autorisation de l'utilisateur"""
    user = update.effective_user
    if not user:
        return False

    allowed_users = get_active_telegram_ids()
    return user.id in allowed_users

def safe_float(value, default=0.0) -> float:
    """Convertit une valeur en float de manière sécurisée"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def format_currency(amount: float) -> str:
    """Formate un montant en devise"""
    if amount is None:
        return "0.00 DA"
    return f"{amount:,.2f} DA".replace(",", " ")


def format_percentage(value: float) -> str:
    """Formate un pourcentage"""
    return f"{value:.1f}%"


def parse_date(date_str: str) -> datetime:
    """Parse une date au format DD/MM/YYYY"""
    try:
        return datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        raise ValueError("Format de date invalide. Utilisez DD/MM/YYYY")


def get_main_menu_keyboard():
    """Retourne le clavier du menu principal"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Aujourd'hui", callback_data="today"),
            InlineKeyboardButton("📅 Hier", callback_data="yesterday")
        ],
        [
            InlineKeyboardButton("📆 Cette semaine", callback_data="this_week"),
            InlineKeyboardButton("📆 Semaine dernière", callback_data="last_week")
        ],
        [
            InlineKeyboardButton("📅 Ce mois", callback_data="this_month"),
            InlineKeyboardButton("📅 Mois dernier", callback_data="last_month")
        ],
        [
            InlineKeyboardButton("🎯 Raccourcis", callback_data="shortcuts"),
            InlineKeyboardButton("💰 État caisse", callback_data="caisse_today")
        ],
        [
            InlineKeyboardButton("🏥 Hospitalisation", callback_data="shortcuts_hospi"),
        ],
            [
                    InlineKeyboardButton( "❓ Aide", callback_data = "help" )
                    ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_shortcuts_keyboard():
    """Retourne le clavier des raccourcis - VERSION COMPLÈTE"""
    keyboard = [
        [
            InlineKeyboardButton("💰 Encaissement", callback_data="shortcut_enc"),
            InlineKeyboardButton("💸 Décaissement", callback_data="shortcut_dec")
        ],
        [
            InlineKeyboardButton("📊 Par méthode", callback_data="shortcut_method"),
            InlineKeyboardButton("📋 Par catégorie", callback_data="shortcut_category")
        ],
        [
            InlineKeyboardButton("👨‍⚕️ Médecins", callback_data="shortcut_doctors"),
            InlineKeyboardButton("💳 Types paiement", callback_data="shortcut_payment_types")
        ],
        [
            InlineKeyboardButton("📊 Activité comptes", callback_data="shortcut_account_stats")
        ],
        [
            InlineKeyboardButton("📈 Tendances", callback_data="shortcut_trends"),
            InlineKeyboardButton("🏆 Top 5", callback_data="shortcut_top5")
        ],
        [
            InlineKeyboardButton("📉 Comparaison", callback_data="shortcut_comparison"),
            InlineKeyboardButton("💹 Prévisions", callback_data="shortcut_forecast")
        ],
        [InlineKeyboardButton("🔙 Retour au menu", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_period_selection_keyboard(action: str):
    """Retourne le clavier de sélection de période pour une action"""
    keyboard = [
        [
            InlineKeyboardButton("Aujourd'hui", callback_data=f"{action}_today"),
            InlineKeyboardButton("Hier", callback_data=f"{action}_yesterday")
        ],
        [
            InlineKeyboardButton("Cette semaine", callback_data=f"{action}_week"),
            InlineKeyboardButton("Ce mois", callback_data=f"{action}_month")
        ],
        [
            InlineKeyboardButton("Mois dernier", callback_data=f"{action}_last_month"),
            InlineKeyboardButton("Année en cours", callback_data=f"{action}_year")
        ],
        [InlineKeyboardButton("🔙 Retour", callback_data="shortcuts")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_date_range(period: str) -> tuple:
    """Retourne les dates de début et fin pour une période donnée"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        return today, today
    elif period == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    elif period == "this_week" or period == "week":
        start_week = today - timedelta(days=today.weekday())
        return start_week, today
    elif period == "last_week":
        start_last_week = today - timedelta(days=today.weekday() + 7)
        end_last_week = start_last_week + timedelta(days=6)
        return start_last_week, end_last_week
    elif period == "this_month" or period == "month":
        start_month = today.replace(day=1)
        return start_month, today
    elif period == "last_month":
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        return first_day_last_month, last_day_last_month
    elif period == "year":
        start_year = today.replace(month=1, day=1)
        return start_year, today

    return today, today


# ==================== COMMANDES DE BASE ====================
@log_command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Menu principal"""
    if not is_authorized(update):
        user_info = get_user_info( update )
        BotLogger.log_action(
                action_type = 'login',
                action_name = 'unauthorized_access',
                success = False,
                error_message = 'Accès non autorisé',
                **user_info
                )
        await update.message.reply_text("⛔ Accès refusé")
        logger.warning(f"Tentative accès bot: {update.effective_user.id}")
        return

    # Log de connexion réussie
    user_info = get_user_info( update )
    BotLogger.log_action(
            action_type = 'login',
            action_name = 'successful_login',
            **user_info
            )

    reply_markup = get_main_menu_keyboard()

    await update.message.reply_text(
        f"🏦 *Bot Finance INAYA*\n\n"
        f"Sélectionnez une période ou une action rapide",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

@log_command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /aide - Affiche l'aide COMPLÈTE"""
    if not is_authorized(update):
        return

    help_text = """
🏦 *GUIDE COMPLET - BOT FINANCE INAYA*

*📊 COMMANDES RAPIDES:*
/start - Menu principal interactif
/jour - Rapport financier du jour
/caisse - État actuel de la caisse
/semaine - Synthèse hebdomadaire
/alertes - Vérifier les alertes

*🏥 HOSPITALISATION:*
/hospi - Rapport du jour
/hospi_date DD/MM/YYYY
  _Statistiques pour une date précise_

/hospi_periode DD/MM/YYYY DD/MM/YYYY
  _Rapport sur une période_

*📅 RAPPORTS PAR DATE:*
/encaissement DD/MM/YYYY
  _Encaissements d'une date précise_

/decaissement DD/MM/YYYY
  _Décaissements d'une date précise_

/plage DD/MM/YYYY DD/MM/YYYY
  _Rapport détaillé sur une période_

*🎯 ANALYSES AVANCÉES:*
- Soldes des comptes bancaires et caisses
- Paiements aux médecins par type
- Répartition par méthode de paiement
- Statistiques par type de paiement
- Activité par compte/caisse
- Tendances et évolutions
- Top 5 des catégories
- Comparaisons périodiques
- **Hospitalisation et occupation des lits**

*💡 RACCOURCIS PRATIQUES:*
Utilisez le menu /start puis "🎯 Raccourcis" ou "🏥 Hospitalisation" pour accéder rapidement à toutes les analyses disponibles.

*📋 FORMAT DES DATES:*
Toujours utiliser: DD/MM/YYYY
Exemple: 15/01/2026


*🔐 SÉCURITÉ:*
Toutes les données sont en lecture seule. Aucune modification n'est possible via le bot.

*ℹ️ NOTE:*
Les virements entre caisses individuelles ne sont pas comptabilisés pour éviter la double comptabilisation.
    """

    await update.message.reply_text(help_text, parse_mode="Markdown")


# ==================== RAPPORTS FINANCIERS DE BASE ====================

async def get_daily_report(date: datetime) -> dict:
    """Récupère le rapport financier DÉTAILLÉ pour une date donnée"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()

        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)

        valid_filter = get_valid_payment_filter()

        # Encaissements
        cur.execute(f"""
            SELECT COALESCE(SUM(p."Amount"), 0) as total, COUNT(*) as nb_trans
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" < %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
        """, (start_date, end_date))
        enc_total, enc_count = cur.fetchone()

        # Décaissements
        cur.execute(f"""
            SELECT COALESCE(SUM(p."Amount"), 0) as total, COUNT(*) as nb_trans
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" < %s
              AND pt."Type" = 0 AND p."Status" != -1
              {valid_filter}
        """, (start_date, end_date))
        dec_total, dec_count = cur.fetchone()

        # Méthodes de paiement (détaillé)
        cur.execute(f"""
            SELECT 
                pm."Label",
                COALESCE(SUM(p."Amount"), 0) as total,
                COUNT(*) as nb_trans,
                COALESCE(AVG(p."Amount"), 0) as avg_amount
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentMethod" pm ON p."Method" = pm."OID"
            WHERE p."Date" >= %s AND p."Date" < %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
            GROUP BY pm."Label"
            ORDER BY total DESC
        """, (start_date, end_date))
        methods = cur.fetchall()

        # Catégories (détaillé)
        cur.execute(f"""
            SELECT 
                pc."Label",
                COALESCE(SUM(p."Amount"), 0) as total,
                pt."Type",
                COUNT(*) as nb_trans
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentCategory" pc ON p."Category" = pc."OID"
            WHERE p."Date" >= %s AND p."Date" < %s
              AND p."Status" != -1
              {valid_filter}
            GROUP BY pc."Label", pt."Type"
            ORDER BY total DESC
        """, (start_date, end_date))
        categories = cur.fetchall()

        # Top 3 transactions
        cur.execute(f"""
            SELECT 
                p."Amount",
                pt."Label" as type_label,
                pm."Label" as method_label,
                EXTRACT(HOUR FROM p."Date") as hour
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentMethod" pm ON p."Method" = pm."OID"
            WHERE p."Date" >= %s AND p."Date" < %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
            ORDER BY p."Amount" DESC
            LIMIT 3
        """, (start_date, end_date))
        top_transactions = cur.fetchall()

        cur.close()
        return {
            'encaissement': safe_float(enc_total),
            'encaissement_count': enc_count,
            'decaissement': safe_float(dec_total),
            'decaissement_count': dec_count,
            'solde': safe_float(enc_total) - safe_float(dec_total),
            'methods': methods,
            'categories': categories,
            'top_transactions': top_transactions,
            'date': date
        }
    finally:
        conn.close()


async def get_range_report(start_date: datetime, end_date: datetime) -> dict:
    """Récupère le rapport financier ENRICHI pour une plage de dates"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        # Totaux avec compteurs
        cur.execute(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as enc_total,
                COUNT(CASE WHEN pt."Type" = 1 THEN 1 END) as enc_count,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as dec_total,
                COUNT(CASE WHEN pt."Type" = 0 THEN 1 END) as dec_count
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
        """, (start_date, end_date_adj))
        enc_total, enc_count, dec_total, dec_count = cur.fetchone()

        # Évolution quotidienne détaillée
        cur.execute(f"""
            SELECT 
                DATE(p."Date") as jour,
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as enc,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as dec,
                COUNT(*) as nb_trans
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY DATE(p."Date")
            ORDER BY jour DESC
        """, (start_date, end_date_adj))
        daily_data = cur.fetchall()

        # Méthodes de paiement
        cur.execute(f"""
            SELECT 
                pm."Label",
                COALESCE(SUM(p."Amount"), 0) as total,
                COUNT(*) as nb_trans,
                COALESCE(AVG(p."Amount"), 0) as avg_amount
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentMethod" pm ON p."Method" = pm."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
            GROUP BY pm."Label"
            ORDER BY total DESC
        """, (start_date, end_date_adj))
        methods = cur.fetchall()

        # Catégories
        cur.execute(f"""
            SELECT 
                pc."Label",
                COALESCE(SUM(p."Amount"), 0) as total,
                pt."Type",
                COUNT(*) as nb_trans
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentCategory" pc ON p."Category" = pc."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY pc."Label", pt."Type"
            ORDER BY total DESC
        """, (start_date, end_date_adj))
        categories = cur.fetchall()

        cur.close()
        return {
            'encaissement': safe_float(enc_total),
            'encaissement_count': enc_count,
            'decaissement': safe_float(dec_total),
            'decaissement_count': dec_count,
            'solde': safe_float(enc_total) - safe_float(dec_total),
            'daily_data': daily_data,
            'methods': methods,
            'categories': categories,
            'start_date': start_date,
            'end_date': end_date
        }
    finally:
        conn.close()


def format_daily_report(data: dict, show_back_button: bool = False) -> tuple:
    """Formate le rapport journalier ENRICHI"""
    date_str = data['date'].strftime("%d/%m/%Y")

    text = f"📊 *RAPPORT FINANCIER - {date_str}*\n\n"

    # Résumé principal
    text += f"💰 *ENCAISSEMENTS*\n"
    text += f"   Montant: {format_currency(data['encaissement'])}\n"
    text += f"   Transactions: {data['encaissement_count']}\n"
    if data['encaissement_count'] > 0:
        avg_enc = data['encaissement'] / data['encaissement_count']
        text += f"   Moyenne: {format_currency(avg_enc)}\n"

    text += f"\n💸 *DÉCAISSEMENTS*\n"
    text += f"   Montant: {format_currency(data['decaissement'])}\n"
    text += f"   Transactions: {data['decaissement_count']}\n"
    if data['decaissement_count'] > 0:
        avg_dec = data['decaissement'] / data['decaissement_count']
        text += f"   Moyenne: {format_currency(avg_dec)}\n"

    text += f"\n━━━━━━━━━━━━━━━\n"
    solde_icon = "📈" if data['solde'] > 0 else "📉" if data['solde'] < 0 else "➖"
    text += f"{solde_icon} *SOLDE: {format_currency(data['solde'])}*\n"

    # Top transactions
    if data.get('top_transactions'):
        text += f"\n🏆 *TOP 3 ENCAISSEMENTS:*\n"
        for amount, type_label, method_label, hour in data['top_transactions']:
            method_info = f" ({method_label})" if method_label else ""
            text += f"  • {format_currency(safe_float(amount))}{method_info}\n"

    # Détails par méthode
    if data['methods']:
        text += f"\n📊 *PAR MÉTHODE DE PAIEMENT:*\n"
        for method, amount, nb_trans, avg in data['methods'][:3]:
            method_name = method or "Non spécifié"
            text += f"  • {method_name}: {format_currency(safe_float(amount))}\n"
            text += f"    ({nb_trans} trans. • moy: {format_currency(safe_float(avg))})\n"

    keyboard = None
    if show_back_button:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Menu principal", callback_data="back_main"),
            InlineKeyboardButton("📊 Détails", callback_data="today")
        ]])

    return text, keyboard


def format_range_report(data: dict, show_back_button: bool = False) -> tuple:
    """Formate le rapport de plage ENRICHI"""
    start_str = data['start_date'].strftime("%d/%m/%Y")
    end_str = data['end_date'].strftime("%d/%m/%Y")

    text = f"📅 *RAPPORT - {start_str} au {end_str}*\n\n"

    # Résumé global
    text += f"💰 *ENCAISSEMENTS*\n"
    text += f"   Total: {format_currency(data['encaissement'])}\n"
    text += f"   Transactions: {data['encaissement_count']}\n"
    if data['encaissement_count'] > 0:
        avg_enc = data['encaissement'] / data['encaissement_count']
        text += f"   Moyenne/trans: {format_currency(avg_enc)}\n"

    text += f"\n💸 *DÉCAISSEMENTS*\n"
    text += f"   Total: {format_currency(data['decaissement'])}\n"
    text += f"   Transactions: {data['decaissement_count']}\n"
    if data['decaissement_count'] > 0:
        avg_dec = data['decaissement'] / data['decaissement_count']
        text += f"   Moyenne/trans: {format_currency(avg_dec)}\n"

    text += f"\n━━━━━━━━━━━━━━━\n"
    text += f"🏦 *SOLDE: {format_currency(data['solde'])}*\n"

    # Analyse par période
    if data.get('daily_data'):
        nb_jours = len(data['daily_data'])
        avg_daily_enc = data['encaissement'] / nb_jours
        avg_daily_dec = data['decaissement'] / nb_jours

        text += f"\n📈 *MOYENNES QUOTIDIENNES ({nb_jours} jours):*\n"
        text += f"   Encaissements: {format_currency(avg_daily_enc)}\n"
        text += f"   Décaissements: {format_currency(avg_daily_dec)}\n"
        text += f"   Solde moyen: {format_currency(avg_daily_enc - avg_daily_dec)}\n"

        # Meilleur et pire jour
        best_day = max(data['daily_data'], key=lambda x: safe_float(x[1]))
        worst_day = min(data['daily_data'], key=lambda x: safe_float(x[1]))

        text += f"\n🏆 *RECORDS:*\n"
        text += f"   Meilleur jour: {best_day[0].strftime('%d/%m')}\n"
        text += f"      {format_currency(safe_float(best_day[1]))}\n"
        text += f"   Plus faible: {worst_day[0].strftime('%d/%m')}\n"
        text += f"      {format_currency(safe_float(worst_day[1]))}\n"

    # Top méthodes
    if data.get('methods'):
        text += f"\n💳 *TOP MÉTHODES:*\n"
        for method, amount, nb_trans, avg in data['methods'][:3]:
            method_name = method or "Non spécifié"
            pct = (safe_float(amount) / data['encaissement'] * 100) if data['encaissement'] > 0 else 0
            text += f"  • {method_name}: {format_currency(safe_float(amount))}\n"
            text += f"    ({format_percentage(pct)} • {nb_trans} trans.)\n"

    # Évolution récente
    if data.get('daily_data'):
        text += f"\n📊 *ÉVOLUTION RÉCENTE:*\n"
        for jour, enc, dec, nb_trans in data['daily_data'][:5]:
            solde = safe_float(enc) - safe_float(dec)
            icon = "📈" if solde > 0 else "📉" if solde < 0 else "➖"
            text += f"{icon} {jour.strftime('%d/%m')}: {format_currency(solde)}\n"

        if len(data['daily_data']) > 5:
            text += f"\n_({len(data['daily_data']) - 5} autres jours...)_"

    keyboard = None
    if show_back_button:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Menu principal", callback_data="back_main")
        ]])

    return text, keyboard


# ==================== ANALYSES AVANCÉES ====================


async def show_by_payment_type(start_date: datetime, end_date: datetime) -> str:
    """Affiche le détail COMPLET par type de paiement"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        # Analyse par type avec détails
        cur.execute(f"""
            SELECT 
                pt."Label",
                pt."Code",
                COALESCE(SUM(p."Amount"), 0) as total,
                COUNT(*) as nb_transactions,
                COALESCE(AVG(p."Amount"), 0) as moyenne,
                COALESCE(MIN(p."Amount"), 0) as min_amount,
                COALESCE(MAX(p."Amount"), 0) as max_amount,
                pt."Type"
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY pt."Label", pt."Code", pt."Type"
            ORDER BY pt."Type" DESC, total DESC
        """, (start_date, end_date_adj))
        payment_types = cur.fetchall()
        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"💳 *ANALYSE PAR TYPE DE PAIEMENT*\n{period}\n\n"

        # Séparer encaissements et décaissements
        encaissements = [pt for pt in payment_types if pt[7] == 1]
        decaissements = [pt for pt in payment_types if pt[7] == 0]

        if encaissements:
            total_enc = sum(safe_float(pt[2]) for pt in encaissements)
            total_trans_enc = sum(pt[3] for pt in encaissements)

            text += f"*💰 ENCAISSEMENTS*\n"
            text += f"Total: {format_currency(total_enc)}\n"
            text += f"Transactions: {total_trans_enc}\n\n"

            for label, code, amount, nb, avg, min_amt, max_amt, _ in encaissements:
                pct = (safe_float(amount) / total_enc * 100) if total_enc > 0 else 0
                text += f"📌 *{label}* ({code})\n"
                text += f"   💵 Montant: {format_currency(safe_float(amount))}\n"
                text += f"   📊 Part: {format_percentage(pct)}\n"
                text += f"   🔢 Trans: {nb}\n"
                text += f"   📈 Moyenne: {format_currency(safe_float(avg))}\n"
                text += f"   📉 Min/Max: {format_currency(safe_float(min_amt))} / {format_currency(safe_float(max_amt))}\n\n"

        if decaissements:
            total_dec = sum(safe_float(pt[2]) for pt in decaissements)
            total_trans_dec = sum(pt[3] for pt in decaissements)

            text += f"*💸 DÉCAISSEMENTS*\n"
            text += f"Total: {format_currency(total_dec)}\n"
            text += f"Transactions: {total_trans_dec}\n\n"

            for label, code, amount, nb, avg, min_amt, max_amt, _ in decaissements:
                pct = (safe_float(amount) / total_dec * 100) if total_dec > 0 else 0
                text += f"📌 *{label}* ({code})\n"
                text += f"   💵 Montant: {format_currency(safe_float(amount))}\n"
                text += f"   📊 Part: {format_percentage(pct)}\n"
                text += f"   🔢 Trans: {nb}\n"
                text += f"   📈 Moyenne: {format_currency(safe_float(avg))}\n"
                text += f"   📉 Min/Max: {format_currency(safe_float(min_amt))} / {format_currency(safe_float(max_amt))}\n\n"

        # Résumé comparatif
        if encaissements and decaissements:
            text += f"━━━━━━━━━━━━━━━\n"
            text += f"📊 *BILAN GLOBAL*\n"
            solde = total_enc - total_dec
            text += f"Solde: {format_currency(solde)}\n"
            text += f"Total trans: {total_trans_enc + total_trans_dec}"

        return text
    finally:
        conn.close()


async def show_doctors_payments(start_date: datetime, end_date: datetime) -> str:
    """Affiche l'analyse DÉTAILLÉE des paiements médecins"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        # Analyse complète des paiements médecins
        cur.execute(f"""
            SELECT 
                pt."Label",
                pt."Code",
                COALESCE(SUM(p."Amount"), 0) as total,
                COUNT(*) as nb_transactions,
                COALESCE(AVG(p."Amount"), 0) as moyenne,
                COALESCE(MIN(p."Amount"), 0) as min_amount,
                COALESCE(MAX(p."Amount"), 0) as max_amount,
                COUNT(DISTINCT DATE(p."Date")) as nb_jours_actifs
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND p."Status" != -1
              AND pt."Code" IN ('Ext', 'Kt', 'Hon', 'Ppm')
              {valid_filter}
            GROUP BY pt."Label", pt."Code", pt."Type"
            ORDER BY total DESC
        """, (start_date, end_date_adj))
        doctors_data = cur.fetchall()

        # Évolution quotidienne
        cur.execute(f"""
            SELECT 
                DATE(p."Date") as jour,
                COALESCE(SUM(p."Amount"), 0) as total
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND p."Status" != -1
              AND pt."Code" IN ('Ext', 'Kt', 'Hon', 'Ppm')
              {valid_filter}
            GROUP BY DATE(p."Date")
            ORDER BY jour DESC
            LIMIT 7
        """, (start_date, end_date_adj))
        daily_doctors = cur.fetchall()

        cur.close()

        if not doctors_data:
            return "❌ Aucun paiement médecin trouvé pour cette période."

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        total_doctors = sum(safe_float(d[2]) for d in doctors_data)
        total_trans = sum(d[3] for d in doctors_data)

        text = f"👨‍⚕️ *ANALYSE PAIEMENTS MÉDECINS*\n{period}\n\n"

        # Résumé global
        text += f"*📊 VUE D'ENSEMBLE*\n"
        text += f"💰 Total payé: {format_currency(total_doctors)}\n"
        text += f"🔢 Transactions: {total_trans}\n"
        text += f"📈 Moyenne/trans: {format_currency(total_doctors/total_trans if total_trans > 0 else 0)}\n\n"
        text += f"━━━━━━━━━━━━━━━\n\n"

        # Détail par type
        for label, code, amount, nb, avg, min_amt, max_amt, nb_jours in doctors_data:
            pct = (safe_float(amount) / total_doctors * 100) if total_doctors > 0 else 0
            icon = "💼" if code == "Hon" else "🏥" if code == "Kt" else "🔬" if code == "Ext" else "💊"

            text += f"{icon} *{label}*\n"
            text += f"   💵 Montant: {format_currency(safe_float(amount))}\n"
            text += f"   📊 Part: {format_percentage(pct)}\n"
            text += f"   🔢 Transactions: {nb}\n"
            text += f"   📅 Jours actifs: {nb_jours}\n"
            text += f"   📈 Moyenne: {format_currency(safe_float(avg))}\n"
            text += f"   📉 Min/Max: {format_currency(safe_float(min_amt))} / {format_currency(safe_float(max_amt))}\n"

            if nb_jours > 0:
                avg_per_day = safe_float(amount) / nb_jours
                text += f"   📆 Moy/jour: {format_currency(avg_per_day)}\n"
            text += "\n"

        # Évolution récente
        if daily_doctors:
            text += f"📈 *ÉVOLUTION RÉCENTE (7 derniers jours)*\n"
            for jour, montant in daily_doctors:
                text += f"  {jour.strftime('%d/%m')}: {format_currency(safe_float(montant))}\n"

        return text
    finally:
        conn.close()


async def show_account_statistics(start_date: datetime, end_date: datetime) -> str:
    """Statistiques DÉTAILLÉES des comptes/caisses"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        cur.execute(f"""
            SELECT 
                a."Label",
                a."Type",
                a."Code",
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as encaissements,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as decaissements,
                COUNT(*) as nb_trans,
                COUNT(DISTINCT DATE(p."Date")) as nb_jours_actifs,
                a."Balance" as solde_actuel
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY a."Label", a."Type", a."Code", a."Balance"
        """, (start_date, end_date_adj))
        accounts_data = cur.fetchall()
        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"📊 *ACTIVITÉ DES COMPTES*\n{period}\n\n"

        # Séparer banques et caisses
        bank_accounts = [a for a in accounts_data if a[1] == 0]
        cash_accounts = [a for a in accounts_data if a[1] == 1]

        if bank_accounts:
            text += f"*💳 COMPTES BANCAIRES*\n\n"
            for label, _, code, enc, dec, nb_trans, nb_jours, solde in bank_accounts:
                account_name = label or "Non affecté"
                flux_total = safe_float(enc) + safe_float(dec)

                text += f"🏛 *{account_name}* ({code})\n"
                text += f"   💚 Entrées: {format_currency(safe_float(enc))}\n"
                text += f"   💸 Sorties: {format_currency(safe_float(dec))}\n"
                text += f"   📊 Transactions: {nb_trans}\n"

                text += "\n"

        if cash_accounts:
            text += f"*💰 CAISSES*\n\n"
            for label, _, code, enc, dec, nb_trans, nb_jours, solde in cash_accounts[:10]:
                account_name = label or "Non affecté"
                flux_total = safe_float(enc) + safe_float(dec)

                # Icône selon le solde et l'activité
                if safe_float(solde) < 0:
                    icon = "🔴"
                elif safe_float(solde) > 500000:
                    icon = "💎"
                elif flux_total > 1000000:
                    icon = "⭐"
                else:
                    icon = "💰"

                text += f"{icon} *{account_name}* ({code})\n"
                text += f"   💚 Entrées: {format_currency(safe_float(enc))}\n"
                text += f"   💸 Sorties: {format_currency(safe_float(dec))}\n"
                text += f"   📊 Trans: {nb_trans} sur {nb_jours} jours\n"

                text += "\n"

            if len(cash_accounts) > 10:
                text += f"_({len(cash_accounts) - 10} autres caisses...)_"

        return text
    finally:
        conn.close()


async def show_comparison(start_date: datetime, end_date: datetime) -> str:
    """Comparaison avec la période précédente"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        # Calculer la période précédente
        duration = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=duration - 1)

        # Période actuelle
        cur.execute(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as enc,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as dec,
                COUNT(*) as nb_trans
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
        """, (start_date, end_date_adj))
        current_enc, current_dec, current_trans = cur.fetchone()

        # Période précédente
        cur.execute(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as enc,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as dec,
                COUNT(*) as nb_trans
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
        """, (prev_start, prev_end))
        prev_enc, prev_dec, prev_trans = cur.fetchone()

        cur.close()

        current_enc = safe_float(current_enc)
        current_dec = safe_float(current_dec)
        prev_enc = safe_float(prev_enc)
        prev_dec = safe_float(prev_dec)

        # Calculs des variations
        enc_variation = ((current_enc - prev_enc) / prev_enc * 100) if prev_enc > 0 else 0
        dec_variation = ((current_dec - prev_dec) / prev_dec * 100) if prev_dec > 0 else 0
        solde_current = current_enc - current_dec
        solde_prev = prev_enc - prev_dec
        solde_variation = ((solde_current - solde_prev) / abs(solde_prev) * 100) if solde_prev != 0 else 0

        period_current = f"{start_date.strftime('%d/%m')} au {end_date.strftime('%d/%m/%Y')}"
        period_prev = f"{prev_start.strftime('%d/%m')} au {prev_end.strftime('%d/%m/%Y')}"

        text = f"📉📈 *ANALYSE COMPARATIVE*\n\n"
        text += f"*📅 PÉRIODE ACTUELLE*\n{period_current}\n\n"
        text += f"*📅 PÉRIODE PRÉCÉDENTE*\n{period_prev}\n\n"
        text += f"━━━━━━━━━━━━━━━\n\n"

        # Encaissements
        enc_icon = "📈" if enc_variation > 0 else "📉" if enc_variation < 0 else "➖"
        text += f"💰 *ENCAISSEMENTS*\n"
        text += f"   Actuel: {format_currency(current_enc)}\n"
        text += f"   Précédent: {format_currency(prev_enc)}\n"
        text += f"   {enc_icon} Variation: {format_percentage(abs(enc_variation))}"
        text += f" {'↗️' if enc_variation > 0 else '↘️' if enc_variation < 0 else '➡️'}\n"
        text += f"   Écart: {format_currency(current_enc - prev_enc)}\n\n"

        # Décaissements
        dec_icon = "📈" if dec_variation > 0 else "📉" if dec_variation < 0 else "➖"
        text += f"💸 *DÉCAISSEMENTS*\n"
        text += f"   Actuel: {format_currency(current_dec)}\n"
        text += f"   Précédent: {format_currency(prev_dec)}\n"
        text += f"   {dec_icon} Variation: {format_percentage(abs(dec_variation))}"
        text += f" {'↗️' if dec_variation > 0 else '↘️' if dec_variation < 0 else '➡️'}\n"
        text += f"   Écart: {format_currency(current_dec - prev_dec)}\n\n"

        # Solde
        solde_icon = "📈" if solde_variation > 0 else "📉" if solde_variation < 0 else "➖"
        text += f"🏦 *SOLDE*\n"
        text += f"   Actuel: {format_currency(solde_current)}\n"
        text += f"   Précédent: {format_currency(solde_prev)}\n"
        text += f"   {solde_icon} Variation: {format_percentage(abs(solde_variation))}"
        text += f" {'↗️' if solde_variation > 0 else '↘️' if solde_variation < 0 else '➡️'}\n"
        text += f"   Écart: {format_currency(solde_current - solde_prev)}\n\n"

        # Transactions
        trans_variation = ((current_trans - prev_trans) / prev_trans * 100) if prev_trans > 0 else 0
        text += f"📊 *TRANSACTIONS*\n"
        text += f"   Actuel: {current_trans}\n"
        text += f"   Précédent: {prev_trans}\n"
        text += f"   Variation: {format_percentage(abs(trans_variation))}"
        text += f" {'↗️' if trans_variation > 0 else '↘️' if trans_variation < 0 else '➡️'}\n\n"

        # Interprétation
        text += f"━━━━━━━━━━━━━━━\n"
        text += f"💡 *INTERPRÉTATION*\n"

        if enc_variation > 5:
            text += f"✅ Forte augmentation des encaissements\n"
        elif enc_variation < -5:
            text += f"⚠️ Baisse significative des encaissements\n"

        if dec_variation > 5:
            text += f"⚠️ Forte augmentation des décaissements\n"
        elif dec_variation < -5:
            text += f"✅ Réduction des décaissements\n"

        if solde_variation > 0:
            text += f"📈 Amélioration du solde global\n"
        elif solde_variation < 0:
            text += f"📉 Détérioration du solde global\n"

        return text
    finally:
        conn.close()


async def show_forecast(start_date: datetime, end_date: datetime) -> str:
    """Prévisions basées sur les données historiques"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        # Données de la période
        cur.execute(f"""
            SELECT 
                DATE(p."Date") as jour,
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as enc,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as dec
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY DATE(p."Date")
            ORDER BY jour
        """, (start_date, end_date_adj))
        daily_data = cur.fetchall()
        cur.close()

        if not daily_data or len(daily_data) < 7:
            return "❌ Données insuffisantes pour établir une prévision (minimum 7 jours requis)."

        # Calculs statistiques
        enc_values = [safe_float(d[1]) for d in daily_data]
        dec_values = [safe_float(d[2]) for d in daily_data]

        avg_enc = sum(enc_values) / len(enc_values)
        avg_dec = sum(dec_values) / len(dec_values)

        # Tendance (régression linéaire simple)
        n = len(enc_values)
        x_values = list(range(n))

        sum_x = sum(x_values)
        sum_y = sum(enc_values)
        sum_xy = sum(x * y for x, y in zip(x_values, enc_values))
        sum_x2 = sum(x * x for x in x_values)

        slope_enc = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0

        sum_y_dec = sum(dec_values)
        sum_xy_dec = sum(x * y for x, y in zip(x_values, dec_values))

        slope_dec = (n * sum_xy_dec - sum_x * sum_y_dec) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0

        # Prévisions pour les 7 prochains jours
        forecasts = []
        for i in range(1, 8):
            next_index = n + i
            forecast_enc = avg_enc + (slope_enc * next_index)
            forecast_dec = avg_dec + (slope_dec * next_index)
            forecast_solde = forecast_enc - forecast_dec

            next_date = end_date + timedelta(days=i)
            forecasts.append((next_date, forecast_enc, forecast_dec, forecast_solde))

        # Formatage
        period = f"{start_date.strftime('%d/%m')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"💹 *PRÉVISIONS FINANCIÈRES*\n\n"
        text += f"*📊 BASÉES SUR LA PÉRIODE*\n{period}\n"
        text += f"({len(daily_data)} jours de données)\n\n"
        text += f"━━━━━━━━━━━━━━━\n\n"

        # Moyennes actuelles
        text += f"*📈 MOYENNES QUOTIDIENNES ACTUELLES*\n"
        text += f"   Encaissements: {format_currency(avg_enc)}\n"
        text += f"   Décaissements: {format_currency(avg_dec)}\n"
        text += f"   Solde: {format_currency(avg_enc - avg_dec)}\n\n"

        # Tendances détectées
        text += f"*📉 TENDANCES DÉTECTÉES*\n"

        if abs(slope_enc) < 1000:
            text += f"   Encaissements: Stable ➡️\n"
        elif slope_enc > 0:
            text += f"   Encaissements: En hausse 📈 (+{format_currency(abs(slope_enc))}/jour)\n"
        else:
            text += f"   Encaissements: En baisse 📉 (-{format_currency(abs(slope_enc))}/jour)\n"

        if abs(slope_dec) < 1000:
            text += f"   Décaissements: Stable ➡️\n"
        elif slope_dec > 0:
            text += f"   Décaissements: En hausse 📈 (+{format_currency(abs(slope_dec))}/jour)\n"
        else:
            text += f"   Décaissements: En baisse 📉 (-{format_currency(abs(slope_dec))}/jour)\n"

        text += f"\n━━━━━━━━━━━━━━━\n\n"

        # Prévisions
        text += f"*🔮 PRÉVISIONS (7 PROCHAINS JOURS)*\n\n"

        total_forecast_enc = 0
        total_forecast_dec = 0

        for date, enc, dec, solde in forecasts[:7]:
            total_forecast_enc += enc
            total_forecast_dec += dec

            solde_icon = "📈" if solde > 0 else "📉" if solde < 0 else "➖"
            text += f"{date.strftime('%d/%m')} ({date.strftime('%A')[:3]})\n"
            text += f"   {solde_icon} Solde prévu: {format_currency(solde)}\n"
            text += f"   💰 Enc: {format_currency(enc)}\n"
            text += f"   💸 Déc: {format_currency(dec)}\n"

        text += f"\n━━━━━━━━━━━━━━━\n\n"

        # Totaux prévisionnels
        text += f"*📊 TOTAUX PRÉVISIONNELS (7 jours)*\n"
        text += f"   Encaissements: {format_currency(total_forecast_enc)}\n"
        text += f"   Décaissements: {format_currency(total_forecast_dec)}\n"
        text += f"   Solde prévu: {format_currency(total_forecast_enc - total_forecast_dec)}\n\n"

        text += f"⚠️ _Ces prévisions sont indicatives et basées sur l'historique récent._"

        return text
    finally:
        conn.close()


# ==================== FONCTIONS EXISTANTES ====================

async def show_encaissement_only(start_date: datetime, end_date: datetime) -> str:
    """Affiche uniquement les encaissements pour une période"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        cur.execute(f"""
            SELECT COALESCE(SUM(p."Amount"), 0), COUNT(*)
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
        """, (start_date, end_date_adj))
        total, count = cur.fetchone()

        cur.execute(f"""
            SELECT pm."Label", COALESCE(SUM(p."Amount"), 0), COUNT(*)
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentMethod" pm ON p."Method" = pm."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
            GROUP BY pm."Label"
            ORDER BY SUM(p."Amount") DESC
        """, (start_date, end_date_adj))
        methods = cur.fetchall()

        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"💰 *ENCAISSEMENTS - {period}*\n\n"
        text += f"*Total:* {format_currency(safe_float(total))}\n"
        text += f"*Transactions:* {count}\n"

        if count > 0:
            avg = safe_float(total) / count
            text += f"*Moyenne/trans:* {format_currency(avg)}\n"

        if methods:
            text += f"\n━━━━━━━━━━━━━━━\n\n"
            text += "*Par méthode de paiement:*\n"
            for method, amount, nb in methods:
                method_name = method or "Non spécifié"
                pct = (safe_float(amount) / safe_float(total) * 100) if safe_float(total) > 0 else 0
                text += f"\n• *{method_name}*\n"
                text += f"  {format_currency(safe_float(amount))} ({format_percentage(pct)})\n"
                text += f"  {nb} transactions\n"

        return text
    finally:
        conn.close()


async def show_decaissement_only(start_date: datetime, end_date: datetime) -> str:
    """Affiche uniquement les décaissements pour une période"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        cur.execute(f"""
            SELECT COALESCE(SUM(p."Amount"), 0), COUNT(*)
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND pt."Type" = 0 AND p."Status" != -1
              {valid_filter}
        """, (start_date, end_date_adj))
        total, count = cur.fetchone()

        cur.execute(f"""
            SELECT pc."Label", COALESCE(SUM(p."Amount"), 0), COUNT(*)
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentCategory" pc ON p."Category" = pc."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND pt."Type" = 0 AND p."Status" != -1
              {valid_filter}
            GROUP BY pc."Label"
            ORDER BY SUM(p."Amount") DESC
        """, (start_date, end_date_adj))
        categories = cur.fetchall()

        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"💸 *DÉCAISSEMENTS - {period}*\n\n"
        text += f"*Total:* {format_currency(safe_float(total))}\n"
        text += f"*Transactions:* {count}\n"

        if count > 0:
            avg = safe_float(total) / count
            text += f"*Moyenne/trans:* {format_currency(avg)}\n"

        if categories:
            text += f"\n━━━━━━━━━━━━━━━\n\n"
            text += "*Par catégorie:*\n"
            for cat, amount, nb in categories:
                cat_name = cat or "Non spécifié"
                pct = (safe_float(amount) / safe_float(total) * 100) if safe_float(total) > 0 else 0
                text += f"\n• *{cat_name}*\n"
                text += f"  {format_currency(safe_float(amount))} ({format_percentage(pct)})\n"
                text += f"  {nb} transactions\n"

        return text
    finally:
        conn.close()


async def show_by_method(start_date: datetime, end_date: datetime) -> str:
    """Affiche le détail par méthode de paiement"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        cur.execute(f"""
            SELECT COALESCE(SUM(p."Amount"), 0)
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
        """, (start_date, end_date_adj))
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT 
                pm."Label",
                COALESCE(SUM(p."Amount"), 0) as total,
                COUNT(*) as nb_transactions,
                COALESCE(AVG(p."Amount"), 0) as moyenne,
                COALESCE(MIN(p."Amount"), 0) as min_amount,
                COALESCE(MAX(p."Amount"), 0) as max_amount
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentMethod" pm ON p."Method" = pm."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s
              AND pt."Type" = 1 AND p."Status" != -1
              {valid_filter}
            GROUP BY pm."Label"
            ORDER BY total DESC
        """, (start_date, end_date_adj))
        methods = cur.fetchall()

        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"📊 *ENCAISSEMENTS PAR MÉTHODE*\n{period}\n\n"
        text += f"💰 *Total:* {format_currency(safe_float(total))}\n\n"

        if methods:
            text += "━━━━━━━━━━━━━━━\n\n"
            for method, amount, nb, avg, min_amt, max_amt in methods:
                method_name = method or "Non spécifié"
                percentage = (safe_float(amount) / safe_float(total) * 100) if safe_float(total) > 0 else 0

                text += f"💳 *{method_name}*\n"
                text += f"   💵 Montant: {format_currency(safe_float(amount))}\n"
                text += f"   📊 Part: {format_percentage(percentage)}\n"
                text += f"   🔢 Transactions: {nb}\n"
                text += f"   📈 Moyenne: {format_currency(safe_float(avg))}\n"
                text += f"   📉 Min/Max: {format_currency(safe_float(min_amt))} / {format_currency(safe_float(max_amt))}\n\n"
        else:
            text += "_Aucune donnée disponible_"

        return text
    finally:
        conn.close()


async def show_by_category(start_date: datetime, end_date: datetime) -> str:
    """Affiche le détail par catégorie"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        cur.execute(f"""
            SELECT COALESCE(SUM(p."Amount"), 0)
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
        """, (start_date, end_date_adj))
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT 
                pc."Label",
                COALESCE(SUM(p."Amount"), 0) as total,
                COUNT(*) as nb_transactions,
                pt."Type"
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentCategory" pc ON p."Category" = pc."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY pc."Label", pt."Type"
            ORDER BY total DESC
        """, (start_date, end_date_adj))
        categories = cur.fetchall()

        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"📋 *DÉTAIL PAR CATÉGORIE*\n{period}\n\n"
        text += f"💰 *Total global:* {format_currency(safe_float(total))}\n\n"

        if categories:
            encaissements = [c for c in categories if c[3] == 1]
            decaissements = [c for c in categories if c[3] == 0]

            if encaissements:
                text += "*💰 ENCAISSEMENTS:*\n"
                for cat, amount, nb, _ in encaissements:
                    cat_name = cat or "Non spécifié"
                    text += f"\n• *{cat_name}*\n"
                    text += f"  {format_currency(safe_float(amount))}\n"
                    text += f"  {nb} transactions\n"

            if decaissements:
                text += "\n*💸 DÉCAISSEMENTS:*\n"
                for cat, amount, nb, _ in decaissements:
                    cat_name = cat or "Non spécifié"
                    text += f"\n• *{cat_name}*\n"
                    text += f"  {format_currency(safe_float(amount))}\n"
                    text += f"  {nb} transactions\n"
        else:
            text += "_Aucune donnée disponible_"

        return text
    finally:
        conn.close()


async def show_trends(start_date: datetime, end_date: datetime) -> str:
    """Affiche les tendances (évolution quotidienne)"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        cur.execute(f"""
            SELECT 
                DATE(p."Date") as jour,
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as encaissement,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as decaissement,
                COUNT(*) as nb_transactions
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY DATE(p."Date")
            ORDER BY jour DESC
        """, (start_date, end_date_adj))
        daily_data = cur.fetchall()

        cur.execute(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN pt."Type" = 1 THEN p."Amount" ELSE 0 END), 0) as total_enc,
                COALESCE(SUM(CASE WHEN pt."Type" = 0 THEN p."Amount" ELSE 0 END), 0) as total_dec
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
        """, (start_date, end_date_adj))
        total_enc, total_dec = cur.fetchone()

        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"📈 *TENDANCES ET ÉVOLUTIONS*\n{period}\n\n"

        total_enc = safe_float(total_enc)
        total_dec = safe_float(total_dec)
        solde = total_enc - total_dec

        text += f"*📊 RÉSUMÉ GLOBAL*\n"
        text += f"💰 Encaissements: {format_currency(total_enc)}\n"
        text += f"💸 Décaissements: {format_currency(total_dec)}\n"
        text += f"🏦 Solde: {format_currency(solde)}\n\n"

        if daily_data and len(daily_data) > 1:
            nb_jours = len(daily_data)
            avg_enc = total_enc / nb_jours
            avg_dec = total_dec / nb_jours

            text += f"*📉 MOYENNES ({nb_jours} jours)*\n"
            text += f"   Encaissement/jour: {format_currency(avg_enc)}\n"
            text += f"   Décaissement/jour: {format_currency(avg_dec)}\n"
            text += f"   Solde moyen/jour: {format_currency(avg_enc - avg_dec)}\n\n"

            best_day = max(daily_data, key=lambda x: safe_float(x[1]))
            worst_day = min(daily_data, key=lambda x: safe_float(x[1]))

            text += f"*🏆 RECORDS*\n"
            text += f"   Meilleur jour:\n"
            text += f"      {best_day[0].strftime('%d/%m/%Y')}\n"
            text += f"      {format_currency(safe_float(best_day[1]))}\n"
            text += f"   Plus faible jour:\n"
            text += f"      {worst_day[0].strftime('%d/%m/%Y')}\n"
            text += f"      {format_currency(safe_float(worst_day[1]))}\n\n"

        if daily_data:
            text += f"*📊 ÉVOLUTION QUOTIDIENNE*\n"
            for jour, enc, dec, nb_trans in daily_data[:10]:
                solde_jour = safe_float(enc) - safe_float(dec)
                icon = "📈" if solde_jour > 0 else "📉" if solde_jour < 0 else "➖"
                text += f"{icon} {jour.strftime('%d/%m')}: {format_currency(solde_jour)}\n"
                text += f"   ({nb_trans} trans. • Enc: {format_currency(safe_float(enc))})\n"

            if len(daily_data) > 10:
                text += f"\n_({len(daily_data) - 10} autres jours...)_"
        else:
            text += "_Aucune donnée disponible_"

        return text
    finally:
        conn.close()


async def show_top5_categories(start_date: datetime, end_date: datetime) -> str:
    """Affiche le top 5 des catégories"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace(hour=23, minute=59, second=59)

        valid_filter = get_valid_payment_filter()

        cur.execute(f"""
            SELECT 
                pc."Label",
                COALESCE(SUM(p."Amount"), 0) as total,
                COUNT(*) as nb_transactions,
                pt."Type"
            FROM "Payment" p
            JOIN "PaymentType" pt ON p."Type" = pt."OID"
            LEFT JOIN "Account" a ON p."Account" = a."OID"
            LEFT JOIN "PaymentCategory" pc ON p."Category" = pc."OID"
            WHERE p."Date" >= %s AND p."Date" <= %s AND p."Status" != -1
            {valid_filter}
            GROUP BY pc."Label", pt."Type"
            ORDER BY total DESC
            LIMIT 5
        """, (start_date, end_date_adj))
        top_categories = cur.fetchall()

        cur.close()

        period = start_date.strftime("%d/%m/%Y")
        if start_date != end_date:
            period = f"{start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}"

        text = f"🏆 *TOP 5 CATÉGORIES*\n{period}\n\n"

        if top_categories:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, (cat, amount, nb, type_val) in enumerate(top_categories):
                cat_name = cat or "Non spécifié"
                type_icon = "💰" if type_val == 1 else "💸"

                text += f"{medals[i]} *{cat_name}*\n"
                text += f"   {type_icon} {format_currency(safe_float(amount))}\n"
                text += f"   📊 {nb} transactions\n"

                if nb > 0:
                    avg = safe_float(amount) / nb
                    text += f"   📈 Moyenne: {format_currency(avg)}\n"
                text += "\n"
        else:
            text += "_Aucune donnée disponible_"

        return text
    finally:
        conn.close()


# ==================== COMMANDES ====================
@log_command
async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /jour - Rapport du jour"""
    if not is_authorized(update):
        return

    await update.message.reply_text("⏳ Chargement des données...")

    try:
        data = await get_daily_report(datetime.now())
        text, keyboard = format_daily_report(data)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Erreur rapport journalier: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

@log_command
async def caisse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /caisse - État de la caisse"""
    if not is_authorized(update):
        return

    try:
        data = await get_daily_report(datetime.now())
        text = f"💰 *ÉTAT DE LA CAISSE*\n{datetime.now().strftime('%d/%m/%Y')}\n\n"
        text += f"💚 Encaissements: {format_currency(data['encaissement'])}\n"
        text += f"   ({data['encaissement_count']} transactions)\n\n"
        text += f"💸 Décaissements: {format_currency(data['decaissement'])}\n"
        text += f"   ({data['decaissement_count']} transactions)\n\n"
        text += f"━━━━━━━━━━━━━━━\n"

        solde_icon = "📈" if data['solde'] > 0 else "📉" if data['solde'] < 0 else "➖"
        text += f"{solde_icon} *SOLDE: {format_currency(data['solde'])}*"

        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erreur état caisse: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

@log_command
async def encaissement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /encaissement DATE"""
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /encaissement DD/MM/YYYY")
        return

    try:
        date = parse_date(context.args[0])
        data = await get_daily_report(date)
        text = f"💰 *ENCAISSEMENT*\n{date.strftime('%d/%m/%Y')}\n\n"
        text += f"Montant: {format_currency(data['encaissement'])}\n"
        text += f"Transactions: {data['encaissement_count']}"

        if data['encaissement_count'] > 0:
            avg = data['encaissement'] / data['encaissement_count']
            text += f"\nMoyenne: {format_currency(avg)}"

        await update.message.reply_text(text, parse_mode="Markdown")
    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Erreur encaissement: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

@log_command
async def decaissement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /decaissement DATE"""
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /decaissement DD/MM/YYYY")
        return

    try:
        date = parse_date(context.args[0])
        data = await get_daily_report(date)
        text = f"💸 *DÉCAISSEMENT*\n{date.strftime('%d/%m/%Y')}\n\n"
        text += f"Montant: {format_currency(data['decaissement'])}\n"
        text += f"Transactions: {data['decaissement_count']}"

        if data['decaissement_count'] > 0:
            avg = data['decaissement'] / data['decaissement_count']
            text += f"\nMoyenne: {format_currency(avg)}"

        await update.message.reply_text(text, parse_mode="Markdown")
    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Erreur décaissement: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

@log_command
async def plage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /plage DATE_DEBUT DATE_FIN"""
    if not is_authorized(update):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /plage DD/MM/YYYY DD/MM/YYYY")
        return

    await update.message.reply_text("⏳ Chargement des données...")

    try:
        start_date = parse_date(context.args[0])
        end_date = parse_date(context.args[1])

        if start_date > end_date:
            await update.message.reply_text("❌ La date de début doit être avant la date de fin")
            return

        data = await get_range_report(start_date, end_date)
        text, keyboard = format_range_report(data)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Erreur plage: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

@log_command
async def semaine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /semaine - Rapport de la semaine"""
    if not is_authorized(update):
        return

    await update.message.reply_text("⏳ Chargement des données...")

    try:
        today = datetime.now()
        start_week = today - timedelta(days=today.weekday())
        data = await get_range_report(start_week, today)
        text, keyboard = format_range_report(data)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Erreur rapport semaine: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")


# ==================== STATISTIQUES HOSPITALISATION ====================

async def get_hospitalization_stats( target_date: datetime ) -> dict:
    """Récupère les statistiques d'hospitalisation pour une date donnée"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()

        # Patients hospitalisés à cette date (présents ce jour-là)
        cur.execute(
            """
            SELECT ms."Label" as service,
                   ms."Code"  as code,
                   COUNT(*)   as nb_patients
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE h."StartDate" <= %s
              AND (h."EndDate" IS NULL OR h."EndDate" >= %s)
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_patients DESC
                    """, (target_date, target_date)
            )
        patients_par_service = cur.fetchall()

        # Total patients hospitalisés
        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE h."StartDate" <= %s
              AND (h."EndDate" IS NULL OR h."EndDate" >= %s)
              AND h."Status" != -1
                    """, (target_date, target_date)
            )
        total_patients = cur.fetchone()[ 0 ]

        # Admissions du jour
        cur.execute(
            """
            SELECT ms."Label" as service,
                   ms."Code"  as code,
                   COUNT(*)   as nb_admissions
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE DATE(h."StartDate") = DATE(%s)
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_admissions DESC
                    """, (target_date,)
            )
        admissions_par_service = cur.fetchall()

        # Total admissions
        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE DATE(h."StartDate") = DATE(%s)
              AND h."Status" != -1
                    """, (target_date,)
            )
        total_admissions = cur.fetchone()[ 0 ]

        # Sorties du jour
        cur.execute(
            """
            SELECT ms."Label" as service,
                   ms."Code"  as code,
                   COUNT(*)   as nb_sorties
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE DATE(h."EndDate") = DATE(%s)
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_sorties DESC
                    """, (target_date,)
            )
        sorties_par_service = cur.fetchall()

        # Total sorties
        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE DATE(h."EndDate") = DATE(%s)
              AND h."Status" != -1
                    """, (target_date,)
            )
        total_sorties = cur.fetchone()[ 0 ]

        # Taux d'occupation par service (si vous avez un nombre de lits défini)
        cur.execute(
            """
            SELECT ms."Label"                                                                         as service,
                   ms."Code"                                                                          as code,
                   COUNT(*)                                                                           as nb_patients,
                   COALESCE(AVG(EXTRACT(DAY FROM (COALESCE(h."EndDate", NOW()) - h."StartDate"))), 0) as duree_moyenne
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE h."StartDate" <= %s
              AND (h."EndDate" IS NULL OR h."EndDate" >= %s)
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_patients DESC
                    """, (target_date, target_date)
            )
        occupation_details = cur.fetchall()

        cur.close()
        return {
                'date': target_date,
                'patients_par_service': patients_par_service,
                'total_patients': total_patients,
                'admissions_par_service': admissions_par_service,
                'total_admissions': total_admissions,
                'sorties_par_service': sorties_par_service,
                'total_sorties': total_sorties,
                'occupation_details': occupation_details
                }
    finally:
        conn.close()


# ==================== FONCTIONS DE FORMATAGE SPÉCIFIQUES ====================

async def show_admissions_only( start_date: datetime, end_date: datetime ) -> str:
    """Affiche uniquement les admissions"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace( hour = 23, minute = 59, second = 59 )

        # Total admissions
        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE h."StartDate" >= %s
              AND h."StartDate" <= %s
              AND h."Status" != -1
                    """, (start_date, end_date_adj)
            )
        total_admissions = cur.fetchone()[ 0 ]

        # Admissions par service
        cur.execute(
            """
            SELECT ms."Label"                                                                         as service,
                   ms."Code"                                                                          as code,
                   COUNT(*)                                                                           as nb_admissions,
                   COALESCE(AVG(EXTRACT(DAY FROM (COALESCE(h."EndDate", NOW()) - h."StartDate"))), 0) as duree_moyenne
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE h."StartDate" >= %s
              AND h."StartDate" <= %s
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_admissions DESC
                    """, (start_date, end_date_adj)
            )
        admissions_par_service = cur.fetchall()

        # Évolution quotidienne
        cur.execute(
            """
            SELECT DATE(h."StartDate") as jour,
                   COUNT(*)            as nb_admissions
            FROM "Hospitalization" h
            WHERE h."StartDate" >= %s
              AND h."StartDate" <= %s
              AND h."Status" != -1
            GROUP BY DATE(h."StartDate")
            ORDER BY jour DESC
                    """, (start_date, end_date_adj)
            )
        evolution_quotidienne = cur.fetchall()

        cur.close()

        period = start_date.strftime( "%d/%m/%Y" )
        if start_date != end_date:
            period = f"{start_date.strftime( '%d/%m/%Y' )} au {end_date.strftime( '%d/%m/%Y' )}"

        text = f"➕ *ADMISSIONS - {period}*\n\n"
        text += f"*📊 TOTAL: {total_admissions} admission(s)*\n\n"

        if start_date != end_date:
            nb_jours = (end_date - start_date).days + 1
            moy = total_admissions / nb_jours
            text += f"📈 Moyenne/jour: {moy:.1f}\n\n"

        text += f"━━━━━━━━━━━━━━━\n\n"

        # Par service
        if admissions_par_service:
            text += f"*🏥 PAR SERVICE*\n\n"
            for service, code, nb, duree_moy in admissions_par_service:
                service_name = service or "Non affecté"
                code_str = f" ({code})" if code else ""
                pct = (nb / total_admissions * 100) if total_admissions > 0 else 0

                text += f"✅ *{service_name}{code_str}*\n"
                text += f"   Admissions: {nb} ({format_percentage( pct )})\n"
                text += f"   Durée moy séjour: {duree_moy:.1f} jours\n\n"

        # Évolution
        if evolution_quotidienne and len( evolution_quotidienne ) > 1:
            text += f"*📈 ÉVOLUTION QUOTIDIENNE*\n\n"
            for jour, nb in evolution_quotidienne[ :10 ]:
                text += f"📅 {jour.strftime( '%d/%m' )}: {nb} admission(s)\n"

            if len( evolution_quotidienne ) > 10:
                text += f"\n_({len( evolution_quotidienne ) - 10} autres jours...)_"

        return text
    finally:
        conn.close()


async def show_sorties_only( start_date: datetime, end_date: datetime ) -> str:
    """Affiche uniquement les sorties"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace( hour = 23, minute = 59, second = 59 )

        # Total sorties
        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE h."EndDate" >= %s
              AND h."EndDate" <= %s
              AND h."Status" != -1
                    """, (start_date, end_date_adj)
            )
        total_sorties = cur.fetchone()[ 0 ]

        # Sorties par service
        cur.execute(
            """
            SELECT ms."Label"                                                        as service,
                   ms."Code"                                                         as code,
                   COUNT(*)                                                          as nb_sorties,
                   COALESCE(AVG(EXTRACT(DAY FROM (h."EndDate" - h."StartDate"))), 0) as duree_moyenne
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE h."EndDate" >= %s
              AND h."EndDate" <= %s
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_sorties DESC
                    """, (start_date, end_date_adj)
            )
        sorties_par_service = cur.fetchall()

        # Évolution quotidienne
        cur.execute(
            """
            SELECT DATE(h."EndDate") as jour,
                   COUNT(*)          as nb_sorties
            FROM "Hospitalization" h
            WHERE h."EndDate" >= %s
              AND h."EndDate" <= %s
              AND h."Status" != -1
            GROUP BY DATE(h."EndDate")
            ORDER BY jour DESC
                    """, (start_date, end_date_adj)
            )
        evolution_quotidienne = cur.fetchall()

        cur.close()

        period = start_date.strftime( "%d/%m/%Y" )
        if start_date != end_date:
            period = f"{start_date.strftime( '%d/%m/%Y' )} au {end_date.strftime( '%d/%m/%Y' )}"

        text = f"➖ *SORTIES - {period}*\n\n"
        text += f"*📊 TOTAL: {total_sorties} sortie(s)*\n\n"

        if start_date != end_date:
            nb_jours = (end_date - start_date).days + 1
            moy = total_sorties / nb_jours
            text += f"📈 Moyenne/jour: {moy:.1f}\n\n"

        text += f"━━━━━━━━━━━━━━━\n\n"

        # Par service
        if sorties_par_service:
            text += f"*🏥 PAR SERVICE*\n\n"
            for service, code, nb, duree_moy in sorties_par_service:
                service_name = service or "Non affecté"
                code_str = f" ({code})" if code else ""
                pct = (nb / total_sorties * 100) if total_sorties > 0 else 0

                text += f"🚪 *{service_name}{code_str}*\n"
                text += f"   Sorties: {nb} ({format_percentage( pct )})\n"
                text += f"   Durée moy séjour: {duree_moy:.1f} jours\n\n"

        # Évolution
        if evolution_quotidienne and len( evolution_quotidienne ) > 1:
            text += f"*📈 ÉVOLUTION QUOTIDIENNE*\n\n"
            for jour, nb in evolution_quotidienne[ :10 ]:
                text += f"📅 {jour.strftime( '%d/%m' )}: {nb} sortie(s)\n"

            if len( evolution_quotidienne ) > 10:
                text += f"\n_({len( evolution_quotidienne ) - 10} autres jours...)_"

        return text
    finally:
        conn.close()


async def show_hospi_evolution( start_date: datetime, end_date: datetime ) -> str:
    """Affiche l'évolution des hospitalisations"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace( hour = 23, minute = 59, second = 59 )

        # Évolution combinée
        cur.execute(
            """
            SELECT jour,
                   SUM(admissions) as admissions,
                   SUM(sorties)    as sorties
            FROM (SELECT DATE(h."StartDate") as jour, COUNT(*) as admissions, 0 as sorties
                  FROM "Hospitalization" h
                  WHERE h."StartDate" >= %s
                    AND h."StartDate" <= %s
                    AND h."Status" != -1
                  GROUP BY DATE(h."StartDate")

                  UNION ALL

                  SELECT DATE(h."EndDate") as jour, 0 as admissions, COUNT(*) as sorties
                  FROM "Hospitalization" h
                  WHERE h."EndDate" >= %s
                    AND h."EndDate" <= %s
                    AND h."Status" != -1
                  GROUP BY DATE(h."EndDate")) combined
            GROUP BY jour
            ORDER BY jour DESC
                    """, (start_date, end_date_adj, start_date, end_date_adj)
            )
        evolution = cur.fetchall()

        # Totaux
        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE h."StartDate" >= %s
              AND h."StartDate" <= %s
              AND h."Status" != -1
                    """, (start_date, end_date_adj)
            )
        total_adm = cur.fetchone()[ 0 ]

        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE h."EndDate" >= %s
              AND h."EndDate" <= %s
              AND h."Status" != -1
                    """, (start_date, end_date_adj)
            )
        total_sort = cur.fetchone()[ 0 ]

        cur.close()

        period = f"{start_date.strftime( '%d/%m/%Y' )} au {end_date.strftime( '%d/%m/%Y' )}"

        text = f"📈 *ÉVOLUTION HOSPITALISATION*\n{period}\n\n"

        text += f"*📊 TOTAUX*\n"
        text += f"➕ Admissions: {total_adm}\n"
        text += f"➖ Sorties: {total_sort}\n"

        solde = total_adm - total_sort
        solde_icon = "📈" if solde > 0 else "📉" if solde < 0 else "➖"
        text += f"{solde_icon} Solde: {'+' if solde > 0 else ''}{solde}\n\n"

        if evolution:
            nb_jours = len( evolution )
            text += f"*📈 MOYENNES ({nb_jours} jours)*\n"
            text += f"   Admissions/jour: {total_adm / nb_jours:.1f}\n"
            text += f"   Sorties/jour: {total_sort / nb_jours:.1f}\n\n"

            text += f"━━━━━━━━━━━━━━━\n\n"
            text += f"*📊 ÉVOLUTION QUOTIDIENNE*\n\n"

            for jour, adm, sort in evolution[ :15 ]:
                solde_jour = adm - sort
                icon = "📈" if solde_jour > 0 else "📉" if solde_jour < 0 else "➖"

                text += f"{icon} {jour.strftime( '%d/%m' )}: "
                text += f"➕{adm} ➖{sort} "
                text += f"({'+' if solde_jour > 0 else ''}{solde_jour})\n"

            if len( evolution ) > 15:
                text += f"\n_({len( evolution ) - 15} autres jours...)_"

        return text
    finally:
        conn.close()


async def show_hospi_by_service( start_date: datetime, end_date: datetime ) -> str:
    """Affiche le détail par service"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace( hour = 23, minute = 59, second = 59 )

        # Statistiques par service
        cur.execute(
            """
            SELECT ms."Label"                                                                             as service,
                   ms."Code"                                                                              as code,
                   COUNT(DISTINCT CASE WHEN h."StartDate" >= %s AND h."StartDate" <= %s THEN h."OID" END) as admissions,
                   COUNT(DISTINCT CASE WHEN h."EndDate" >= %s AND h."EndDate" <= %s THEN h."OID" END)     as sorties,
                   COUNT(DISTINCT CASE
                                      WHEN h."StartDate" <= %s AND (h."EndDate" IS NULL OR h."EndDate" >= %s)
                                          THEN h."OID" END)                                               as presents,
                   COALESCE(AVG(CASE
                                    WHEN h."EndDate" IS NOT NULL
                                        THEN EXTRACT(DAY FROM (h."EndDate" - h."StartDate")) END),
                            0)                                                                            as duree_moyenne
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE h."Status" != -1
              AND (
                (h."StartDate" >= %s AND h."StartDate" <= %s)
                    OR (h."EndDate" >= %s AND h."EndDate" <= %s)
                    OR (h."StartDate" <= %s AND (h."EndDate" IS NULL OR h."EndDate" >= %s))
                )
            GROUP BY ms."Label", ms."Code"
            ORDER BY COUNT(DISTINCT CASE WHEN h."StartDate" >= %s AND h."StartDate" <= %s THEN h."OID" END) +
                     COUNT(DISTINCT CASE WHEN h."EndDate" >= %s AND h."EndDate" <= %s THEN h."OID" END) DESC
                    """, (
                    start_date, end_date_adj,  # Pour admissions
                    start_date, end_date_adj,  # Pour sorties
                    end_date_adj, end_date_adj,  # Pour presents
                    start_date, end_date_adj,  # WHERE clause admissions
                    start_date, end_date_adj,  # WHERE clause sorties
                    end_date_adj, end_date_adj,  # WHERE clause presents
                    start_date, end_date_adj,  # ORDER BY admissions
                    start_date, end_date_adj  # ORDER BY sorties
                    )
            )
        services_data = cur.fetchall()

        cur.close()

        period = start_date.strftime( "%d/%m/%Y" )
        if start_date != end_date:
            period = f"{start_date.strftime( '%d/%m/%Y' )} au {end_date.strftime( '%d/%m/%Y' )}"

        text = f"🏥 *ANALYSE PAR SERVICE*\n{period}\n\n"

        if services_data:
            total_adm = sum( s[ 2 ] for s in services_data )
            total_sort = sum( s[ 3 ] for s in services_data )
            total_pres = sum( s[ 4 ] for s in services_data )

            text += f"*📊 VUE D'ENSEMBLE*\n"
            text += f"➕ Total admissions: {total_adm}\n"
            text += f"➖ Total sorties: {total_sort}\n"
            text += f"👥 Patients présents: {total_pres}\n\n"
            text += f"━━━━━━━━━━━━━━━\n\n"

            for service, code, adm, sort, pres, duree_moy in services_data:
                service_name = service or "Non affecté"
                code_str = f" ({code})" if code else ""

                # Calculer les pourcentages
                pct_adm = (adm / total_adm * 100) if total_adm > 0 else 0
                pct_sort = (sort / total_sort * 100) if total_sort > 0 else 0
                pct_pres = (pres / total_pres * 100) if total_pres > 0 else 0

                # Icône selon l'activité
                activite = adm + sort
                if activite > 20:
                    icon = "⭐"
                elif activite > 10:
                    icon = "🔹"
                else:
                    icon = "📌"

                text += f"{icon} *{service_name}{code_str}*\n"
                text += f"   ➕ Admissions: {adm} ({format_percentage( pct_adm )})\n"
                text += f"   ➖ Sorties: {sort} ({format_percentage( pct_sort )})\n"
                text += f"   👥 Présents: {pres} ({format_percentage( pct_pres )})\n"
                text += f"   📊 Durée moy: {duree_moy:.1f} jours\n"
                text += f"   🔄 Flux total: {adm + sort}\n\n"
        else:
            text += "_Aucune donnée disponible_"

        return text
    finally:
        conn.close()


async def get_hospitalization_range_stats( start_date: datetime, end_date: datetime ) -> dict:
    """Récupère les statistiques d'hospitalisation pour une période"""
    conn = get_pg_connection()
    try:
        cur = conn.cursor()
        end_date_adj = end_date.replace( hour = 23, minute = 59, second = 59 )

        # Admissions par service sur la période
        cur.execute(
            """
            SELECT ms."Label"                                                                         as service,
                   ms."Code"                                                                          as code,
                   COUNT(*)                                                                           as nb_admissions,
                   COALESCE(AVG(EXTRACT(DAY FROM (COALESCE(h."EndDate", NOW()) - h."StartDate"))), 0) as duree_moyenne
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE h."StartDate" >= %s
              AND h."StartDate" <= %s
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_admissions DESC
                    """, (start_date, end_date_adj)
            )
        admissions_periode = cur.fetchall()

        # Sorties par service sur la période
        cur.execute(
            """
            SELECT ms."Label" as service,
                   ms."Code"  as code,
                   COUNT(*)   as nb_sorties
            FROM "Hospitalization" h
                     LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
            WHERE h."EndDate" >= %s
              AND h."EndDate" <= %s
              AND h."Status" != -1
            GROUP BY ms."Label", ms."Code"
            ORDER BY nb_sorties DESC
                    """, (start_date, end_date_adj)
            )
        sorties_periode = cur.fetchall()

        # Évolution quotidienne
        cur.execute(
            """
            SELECT DATE(h."StartDate") as jour,
                   COUNT(*)            as nb_admissions
            FROM "Hospitalization" h
            WHERE h."StartDate" >= %s
              AND h."StartDate" <= %s
              AND h."Status" != -1
            GROUP BY DATE(h."StartDate")
            ORDER BY jour DESC
                    """, (start_date, end_date_adj)
            )
        admissions_quotidiennes = cur.fetchall()

        cur.execute(
            """
            SELECT DATE(h."EndDate") as jour,
                   COUNT(*)          as nb_sorties
            FROM "Hospitalization" h
            WHERE h."EndDate" >= %s
              AND h."EndDate" <= %s
              AND h."Status" != -1
            GROUP BY DATE(h."EndDate")
            ORDER BY jour DESC
                    """, (start_date, end_date_adj)
            )
        sorties_quotidiennes = cur.fetchall()

        # Totaux
        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE h."StartDate" >= %s
              AND h."StartDate" <= %s
              AND h."Status" != -1
                    """, (start_date, end_date_adj)
            )
        total_admissions = cur.fetchone()[ 0 ]

        cur.execute(
            """
            SELECT COUNT(*)
            FROM "Hospitalization" h
            WHERE h."EndDate" >= %s
              AND h."EndDate" <= %s
              AND h."Status" != -1
                    """, (start_date, end_date_adj)
            )
        total_sorties = cur.fetchone()[ 0 ]

        cur.close()
        return {
                'start_date': start_date,
                'end_date': end_date,
                'admissions_periode': admissions_periode,
                'sorties_periode': sorties_periode,
                'admissions_quotidiennes': admissions_quotidiennes,
                'sorties_quotidiennes': sorties_quotidiennes,
                'total_admissions': total_admissions,
                'total_sorties': total_sorties
                }
    finally:
        conn.close()


def format_hospitalization_report( data: dict, show_back_button: bool = False ) -> tuple:
    """Formate le rapport d'hospitalisation pour une date"""
    date_str = data[ 'date' ].strftime( "%d/%m/%Y" )

    text = f"🏥 *RAPPORT HOSPITALISATION - {date_str}*\n\n"

    # Vue d'ensemble
    text += f"*📊 VUE D'ENSEMBLE*\n"
    text += f"👥 Patients hospitalisés: {data[ 'total_patients' ]}\n"
    text += f"➕ Admissions du jour: {data[ 'total_admissions' ]}\n"
    text += f"➖ Sorties du jour: {data[ 'total_sorties' ]}\n"

    solde = data[ 'total_admissions' ] - data[ 'total_sorties' ]
    solde_icon = "📈" if solde > 0 else "📉" if solde < 0 else "➖"
    text += f"{solde_icon} Variation: {'+' if solde > 0 else ''}{solde}\n\n"

    text += f"━━━━━━━━━━━━━━━\n\n"

    # Patients par service
    if data[ 'patients_par_service' ]:
        text += f"*👥 PATIENTS HOSPITALISÉS PAR SERVICE*\n\n"
        for service, code, nb_patients in data[ 'patients_par_service' ][ :10 ]:
            service_name = service or "Non affecté"
            code_str = f" ({code})" if code else ""
            text += f"🏥 {service_name}{code_str}\n"
            text += f"   Patients: {nb_patients}\n"

        if len( data[ 'patients_par_service' ] ) > 10:
            text += f"\n_+{len( data[ 'patients_par_service' ] ) - 10} autres services_\n"
        text += "\n"

    # Admissions du jour
    if data[ 'admissions_par_service' ]:
        text += f"*➕ ADMISSIONS DU JOUR*\n\n"
        for service, code, nb_admissions in data[ 'admissions_par_service' ]:
            service_name = service or "Non affecté"
            code_str = f" ({code})" if code else ""
            text += f"✅ {service_name}{code_str}: {nb_admissions}\n"
        text += "\n"
    else:
        text += f"*➕ ADMISSIONS DU JOUR*\nAucune admission\n\n"

    # Sorties du jour
    if data[ 'sorties_par_service' ]:
        text += f"*➖ SORTIES DU JOUR*\n\n"
        for service, code, nb_sorties in data[ 'sorties_par_service' ]:
            service_name = service or "Non affecté"
            code_str = f" ({code})" if code else ""
            text += f"🚪 {service_name}{code_str}: {nb_sorties}\n"
        text += "\n"
    else:
        text += f"*➖ SORTIES DU JOUR*\nAucune sortie\n\n"

    # Durée moyenne de séjour
    if data[ 'occupation_details' ]:
        text += f"*📈 OCCUPATION ET DURÉES*\n\n"
        for service, code, nb_patients, duree_moy in data[ 'occupation_details' ][ :5 ]:
            service_name = service or "Non affecté"
            text += f"🏥 {service_name}\n"
            text += f"   Patients: {nb_patients}\n"
            text += f"   Durée moy: {duree_moy:.1f} jours\n"

    keyboard = None
    if show_back_button:
        keyboard = InlineKeyboardMarkup(
                [
                        [
                                InlineKeyboardButton( "🔙 Menu principal", callback_data = "back_main" ),
                                InlineKeyboardButton( "📊 Raccourcis", callback_data = "shortcuts_hospi" )
                                ]
                        ]
                )

    return text, keyboard


def format_hospitalization_range_report( data: dict, show_back_button: bool = False ) -> tuple:
    """Formate le rapport d'hospitalisation pour une période"""
    start_str = data[ 'start_date' ].strftime( "%d/%m/%Y" )
    end_str = data[ 'end_date' ].strftime( "%d/%m/%Y" )

    text = f"🏥 *HOSPITALISATION - {start_str} au {end_str}*\n\n"

    # Résumé
    text += f"*📊 RÉSUMÉ DE LA PÉRIODE*\n"
    text += f"➕ Total admissions: {data[ 'total_admissions' ]}\n"
    text += f"➖ Total sorties: {data[ 'total_sorties' ]}\n"

    solde = data[ 'total_admissions' ] - data[ 'total_sorties' ]
    solde_icon = "📈" if solde > 0 else "📉" if solde < 0 else "➖"
    text += f"{solde_icon} Solde: {'+' if solde > 0 else ''}{solde}\n\n"

    # Moyennes
    nb_jours = (data[ 'end_date' ] - data[ 'start_date' ]).days + 1
    moy_admissions = data[ 'total_admissions' ] / nb_jours
    moy_sorties = data[ 'total_sorties' ] / nb_jours

    text += f"📈 *MOYENNES QUOTIDIENNES ({nb_jours} jours)*\n"
    text += f"   Admissions/jour: {moy_admissions:.1f}\n"
    text += f"   Sorties/jour: {moy_sorties:.1f}\n\n"

    text += f"━━━━━━━━━━━━━━━\n\n"

    # Admissions par service
    if data[ 'admissions_periode' ]:
        text += f"*➕ ADMISSIONS PAR SERVICE*\n\n"
        for service, code, nb_admissions, duree_moy in data[ 'admissions_periode' ][ :10 ]:
            service_name = service or "Non affecté"
            code_str = f" ({code})" if code else ""
            pct = (nb_admissions / data[ 'total_admissions' ] * 100) if data[ 'total_admissions' ] > 0 else 0

            text += f"🏥 {service_name}{code_str}\n"
            text += f"   Admissions: {nb_admissions} ({format_percentage( pct )})\n"
            text += f"   Durée moy: {duree_moy:.1f} jours\n"

        if len( data[ 'admissions_periode' ] ) > 10:
            text += f"\n_+{len( data[ 'admissions_periode' ] ) - 10} autres services_\n"
        text += "\n"

    # Sorties par service
    if data[ 'sorties_periode' ]:
        text += f"*➖ SORTIES PAR SERVICE*\n\n"
        for service, code, nb_sorties in data[ 'sorties_periode' ][ :10 ]:
            service_name = service or "Non affecté"
            code_str = f" ({code})" if code else ""
            pct = (nb_sorties / data[ 'total_sorties' ] * 100) if data[ 'total_sorties' ] > 0 else 0

            text += f"🚪 {service_name}{code_str}: {nb_sorties} ({format_percentage( pct )})\n"

        if len( data[ 'sorties_periode' ] ) > 10:
            text += f"\n_+{len( data[ 'sorties_periode' ] ) - 10} autres services_\n"
        text += "\n"

    # Évolution récente
    if data[ 'admissions_quotidiennes' ] or data[ 'sorties_quotidiennes' ]:
        text += f"*📊 ÉVOLUTION RÉCENTE*\n\n"

        # Combiner les données
        evolution = { }
        for jour, nb in data[ 'admissions_quotidiennes' ][ :7 ]:
            evolution[ jour ] = { 'admissions': nb, 'sorties': 0 }
        for jour, nb in data[ 'sorties_quotidiennes' ][ :7 ]:
            if jour in evolution:
                evolution[ jour ][ 'sorties' ] = nb
            else:
                evolution[ jour ] = { 'admissions': 0, 'sorties': nb }

        for jour in sorted( evolution.keys(), reverse = True )[ :7 ]:
            adm = evolution[ jour ][ 'admissions' ]
            sort = evolution[ jour ][ 'sorties' ]
            solde_jour = adm - sort
            icon = "📈" if solde_jour > 0 else "📉" if solde_jour < 0 else "➖"

            text += f"{icon} {jour.strftime( '%d/%m' )}: "
            text += f"➕{adm} ➖{sort} "
            text += f"({'+' if solde_jour > 0 else ''}{solde_jour})\n"

    keyboard = None
    if show_back_button:
        keyboard = InlineKeyboardMarkup(
                [
                        [
                                InlineKeyboardButton( "🔙 Menu principal", callback_data = "back_main" )
                                ]
                        ]
                )

    return text, keyboard


def get_shortcuts_hospi_keyboard():
    """Retourne le clavier des raccourcis hospitalisation"""
    keyboard = [
            [
                    InlineKeyboardButton( "👥 Patients actuels", callback_data = "hospi_current" ),
                    InlineKeyboardButton( "➕ Admissions", callback_data = "shortcut_hospi_adm" )
                    ],
            [
                    InlineKeyboardButton( "➖ Sorties", callback_data = "shortcut_hospi_sort" ),
                    InlineKeyboardButton( "📊 Statistiques", callback_data = "shortcut_hospi_stats" )
                    ],
            [
                    InlineKeyboardButton( "📈 Évolution", callback_data = "shortcut_hospi_evol" ),
                    InlineKeyboardButton( "🏥 Par service", callback_data = "shortcut_hospi_service" )
                    ],
            [ InlineKeyboardButton( "🔙 Retour au menu", callback_data = "back_main" ) ]
            ]
    return InlineKeyboardMarkup( keyboard )


# ==================== COMMANDES HOSPITALISATION ====================
@log_command
async def hospi_command( update: Update, context: ContextTypes.DEFAULT_TYPE ):
    """Commande /hospi - Rapport hospitalisation du jour"""
    if not is_authorized( update ):
        return

    await update.message.reply_text( "⏳ Chargement des données d'hospitalisation..." )

    try:
        data = await get_hospitalization_stats( datetime.now() )
        text, keyboard = format_hospitalization_report( data, show_back_button = True )
        await update.message.reply_text( text, parse_mode = "Markdown", reply_markup = keyboard )
    except Exception as e:
        logger.error( f"Erreur rapport hospitalisation: {e}" )
        await update.message.reply_text( f"❌ Erreur: {str( e )}" )

@log_command
async def hospi_date_command( update: Update, context: ContextTypes.DEFAULT_TYPE ):
    """Commande /hospi_date DD/MM/YYYY"""
    if not is_authorized( update ):
        return

    if not context.args:
        await update.message.reply_text( "Usage: /hospi_date DD/MM/YYYY" )
        return

    try:
        date = parse_date( context.args[ 0 ] )
        await update.message.reply_text( "⏳ Chargement des données..." )

        data = await get_hospitalization_stats( date )
        text, keyboard = format_hospitalization_report( data, show_back_button = True )
        await update.message.reply_text( text, parse_mode = "Markdown", reply_markup = keyboard )
    except ValueError as e:
        await update.message.reply_text( f"❌ {str( e )}" )
    except Exception as e:
        logger.error( f"Erreur hospi_date: {e}" )
        await update.message.reply_text( f"❌ Erreur: {str( e )}" )

@log_command
async def hospi_periode_command( update: Update, context: ContextTypes.DEFAULT_TYPE ):
    """Commande /hospi_periode DD/MM/YYYY DD/MM/YYYY"""
    if not is_authorized( update ):
        return

    if len( context.args ) < 2:
        await update.message.reply_text( "Usage: /hospi_periode DD/MM/YYYY DD/MM/YYYY" )
        return

    await update.message.reply_text( "⏳ Chargement des données..." )

    try:
        start_date = parse_date( context.args[ 0 ] )
        end_date = parse_date( context.args[ 1 ] )

        if start_date > end_date:
            await update.message.reply_text( "❌ La date de début doit être avant la date de fin" )
            return

        data = await get_hospitalization_range_stats( start_date, end_date )
        text, keyboard = format_hospitalization_range_report( data, show_back_button = True )
        await update.message.reply_text( text, parse_mode = "Markdown", reply_markup = keyboard )
    except ValueError as e:
        await update.message.reply_text( f"❌ {str( e )}" )
    except Exception as e:
        logger.error( f"Erreur hospi_periode: {e}" )
        await update.message.reply_text( f"❌ Erreur: {str( e )}" )


# ==================== GESTIONNAIRE DE BOUTONS ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestion COMPLÈTE des boutons inline"""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    try:
        if not is_authorized(update):
            return

        data = query.data

        # Menu principal
        if data == "back_main":
            reply_markup = get_main_menu_keyboard()
            await query.edit_message_text(
                "🏦 *Bot Finance INAYA*\n\n"
                "Sélectionnez une période ou une action rapide:",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return

        # Raccourcis
        if data == "shortcuts":
            reply_markup = get_shortcuts_keyboard()
            await query.edit_message_text(
                "🎯 *RACCOURCIS DISPONIBLES*\n\n"
                "Sélectionnez une analyse:",
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return

        # Raccourcis hospitalisation
        if data == "shortcuts_hospi":
            reply_markup = get_shortcuts_hospi_keyboard()
            await query.edit_message_text(
                    "🏥 *HOSPITALISATION*\n\n"
                    "Sélectionnez une analyse:",
                    parse_mode = "Markdown",
                    reply_markup = reply_markup
                    )
            return

        # Patients actuels (aujourd'hui)
        if data == "hospi_current":
            await query.edit_message_text( "⏳ Chargement..." )
            hospi_data = await get_hospitalization_stats( datetime.now() )
            text, keyboard = format_hospitalization_report( hospi_data, show_back_button = True )
            await query.edit_message_text( text, parse_mode = "Markdown", reply_markup = keyboard )
            return

        # Raccourcis hospitalisation avec sélection de période
        hospi_shortcuts = {
                "shortcut_hospi_adm": ("➕ *ADMISSIONS*\n\nSélectionnez une période:", "hospi_adm"),
                "shortcut_hospi_sort": ("➖ *SORTIES*\n\nSélectionnez une période:", "hospi_sort"),
                "shortcut_hospi_stats": ("📊 *STATISTIQUES*\n\nSélectionnez une période:", "hospi_stats"),
                "shortcut_hospi_evol": ("📈 *ÉVOLUTION*\n\nSélectionnez une période:", "hospi_evol"),
                "shortcut_hospi_service": ("🏥 *PAR SERVICE*\n\nSélectionnez une période:", "hospi_service"),
                }

        for shortcut, (message, action) in hospi_shortcuts.items():
            if data == shortcut:
                reply_markup = get_period_selection_keyboard( action )
                await query.edit_message_text( message, parse_mode = "Markdown", reply_markup = reply_markup )
                return

        if data.startswith( "hospi_adm_" ):
            period = data.replace( "hospi_adm_", "" )
            start_date, end_date = get_date_range( period )
            await query.edit_message_text( "⏳ Chargement admissions..." )

            try:
                text = await show_admissions_only( start_date, end_date )
                keyboard = InlineKeyboardMarkup(
                        [
                                [
                                        InlineKeyboardButton( "🔙 Retour", callback_data = "shortcuts_hospi" ),
                                        InlineKeyboardButton( "🏠 Menu", callback_data = "back_main" )
                                        ]
                                ]
                        )
                await query.edit_message_text( text, parse_mode = "Markdown", reply_markup = keyboard )
            except Exception as e:
                logger.error( f"Erreur admissions: {e}" )
                await query.edit_message_text( f"❌ Erreur: {str( e )}" )
            return

        if data.startswith( "hospi_sort_" ):
            period = data.replace( "hospi_sort_", "" )
            start_date, end_date = get_date_range( period )
            await query.edit_message_text( "⏳ Chargement sorties..." )

            try:
                text = await show_sorties_only( start_date, end_date )
                keyboard = InlineKeyboardMarkup(
                        [
                                [
                                        InlineKeyboardButton( "🔙 Retour", callback_data = "shortcuts_hospi" ),
                                        InlineKeyboardButton( "🏠 Menu", callback_data = "back_main" )
                                        ]
                                ]
                        )
                await query.edit_message_text( text, parse_mode = "Markdown", reply_markup = keyboard )
            except Exception as e:
                logger.error( f"Erreur sorties: {e}" )
                await query.edit_message_text( f"❌ Erreur: {str( e )}" )
            return

        if data.startswith( "hospi_stats_" ):
            period = data.replace( "hospi_stats_", "" )
            start_date, end_date = get_date_range( period )
            await query.edit_message_text( "⏳ Chargement statistiques..." )

            try:
                if start_date == end_date:
                    hospi_data = await get_hospitalization_stats( start_date )
                    text, _ = format_hospitalization_report( hospi_data, show_back_button = False )
                else:
                    hospi_data = await get_hospitalization_range_stats( start_date, end_date )
                    text, _ = format_hospitalization_range_report( hospi_data, show_back_button = False )

                keyboard = InlineKeyboardMarkup(
                        [
                                [
                                        InlineKeyboardButton( "🔙 Retour", callback_data = "shortcuts_hospi" ),
                                        InlineKeyboardButton( "🏠 Menu", callback_data = "back_main" )
                                        ]
                                ]
                        )
                await query.edit_message_text( text, parse_mode = "Markdown", reply_markup = keyboard )
            except Exception as e:
                logger.error( f"Erreur statistiques: {e}" )
                await query.edit_message_text( f"❌ Erreur: {str( e )}" )
            return

        if data.startswith( "hospi_evol_" ):
            period = data.replace( "hospi_evol_", "" )
            start_date, end_date = get_date_range( period )
            await query.edit_message_text( "⏳ Chargement évolution..." )

            try:
                text = await show_hospi_evolution( start_date, end_date )
                keyboard = InlineKeyboardMarkup(
                        [
                                [
                                        InlineKeyboardButton( "🔙 Retour", callback_data = "shortcuts_hospi" ),
                                        InlineKeyboardButton( "🏠 Menu", callback_data = "back_main" )
                                        ]
                                ]
                        )
                await query.edit_message_text( text, parse_mode = "Markdown", reply_markup = keyboard )
            except Exception as e:
                logger.error( f"Erreur évolution: {e}" )
                await query.edit_message_text( f"❌ Erreur: {str( e )}" )
            return

        if data.startswith( "hospi_service_" ):
            period = data.replace( "hospi_service_", "" )
            start_date, end_date = get_date_range( period )
            await query.edit_message_text( "⏳ Chargement par service..." )

            try:
                text = await show_hospi_by_service( start_date, end_date )
                keyboard = InlineKeyboardMarkup(
                        [
                                [
                                        InlineKeyboardButton( "🔙 Retour", callback_data = "shortcuts_hospi" ),
                                        InlineKeyboardButton( "🏠 Menu", callback_data = "back_main" )
                                        ]
                                ]
                        )
                await query.edit_message_text( text, parse_mode = "Markdown", reply_markup = keyboard )
            except Exception as e:
                logger.error( f"Erreur par service: {e}" )
                await query.edit_message_text( f"❌ Erreur: {str( e )}" )
            return
        # Aide
        if data == "help":
            help_text = """
            🏦 *AIDE RAPIDE*
            
            *Commandes principales:*
            /start - Menu principal
            /jour - Rapport du jour
            /caisse - État caisse
            /alertes - Vérifier alertes
            /semaine - Rapport semaine
            
            *Analyses disponibles:*
            ✅ Soldes comptes/caisses
            ✅ Paiements médecins
            ✅ Types de paiement
            ✅ Méthodes de paiement
            ✅ Activité par compte
            ✅ Tendances et évolutions
            ✅ Comparaisons périodes
            ✅ Prévisions financières
            
            Utilisez le menu pour accéder à toutes les fonctionnalités!
            """
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Menu principal", callback_data="back_main")
            ]])
            await query.edit_message_text(help_text, parse_mode="Markdown", reply_markup=keyboard)
            return

        # Sélecteurs de période pour chaque raccourci
        period_shortcuts = {
            "shortcut_enc": ("💰 *ENCAISSEMENTS*\n\nSélectionnez une période:", "enc"),
            "shortcut_dec": ("💸 *DÉCAISSEMENTS*\n\nSélectionnez une période:", "dec"),
            "shortcut_method": ("📊 *PAR MÉTHODE*\n\nSélectionnez une période:", "method"),
            "shortcut_category": ("📋 *PAR CATÉGORIE*\n\nSélectionnez une période:", "category"),
            "shortcut_doctors": ("👨‍⚕️ *PAIEMENTS MÉDECINS*\n\nSélectionnez une période:", "doctors"),
            "shortcut_payment_types": ("💳 *TYPES DE PAIEMENT*\n\nSélectionnez une période:", "payment_types"),
            "shortcut_account_stats": ("📊 *ACTIVITÉ COMPTES*\n\nSélectionnez une période:", "account_stats"),
            "shortcut_trends": ("📈 *TENDANCES*\n\nSélectionnez une période:", "trends"),
            "shortcut_top5": ("🏆 *TOP 5 CATÉGORIES*\n\nSélectionnez une période:", "top5"),
            "shortcut_comparison": ("📉 *COMPARAISON*\n\nSélectionnez une période:", "comparison"),
            "shortcut_forecast": ("💹 *PRÉVISIONS*\n\nBasées sur quelle période?", "forecast"),
        }

        for shortcut, (message, action) in period_shortcuts.items():
            if data == shortcut:
                reply_markup = get_period_selection_keyboard(action)
                await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)
                return

        # Traitement des actions avec période
        actions_map = {
            "enc_": (show_encaissement_only, "Encaissements"),
            "dec_": (show_decaissement_only, "Décaissements"),
            "method_": (show_by_method, "Méthodes"),
            "category_": (show_by_category, "Catégories"),
            "doctors_": (show_doctors_payments, "Paiements médecins"),
            "payment_types_": (show_by_payment_type, "Types de paiement"),
            "account_stats_": (show_account_statistics, "Activité comptes"),
            "trends_": (show_trends, "Tendances"),
            "top5_": (show_top5_categories, "Top 5"),
            "comparison_": (show_comparison, "Comparaison"),
            "forecast_": (show_forecast, "Prévisions"),
        }

        for prefix, (func, label) in actions_map.items():
            if data.startswith(prefix):
                period = data.replace(prefix, "")
                start_date, end_date = get_date_range(period)
                await query.edit_message_text(f"⏳ Chargement {label}...")

                try:
                    text = await func(start_date, end_date)
                    keyboard = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("🔙 Retour", callback_data="shortcuts"),
                                InlineKeyboardButton("🏠 Menu", callback_data="back_main"),
                            ]
                        ]
                    )
                    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
                except Exception as e:
                    logger.error(f"Erreur {label}: {e}")
                    await query.edit_message_text(f"❌ Erreur: {str(e)}")
                return

        # Périodes prédéfinies - Rapport complet
        if data in ["today", "yesterday", "this_week", "last_week", "this_month", "last_month"]:
            await query.edit_message_text("⏳ Chargement des données...")

            try:
                start_date, end_date = get_date_range(data)

                if start_date == end_date:
                    report_data = await get_daily_report(start_date)
                    text, keyboard = format_daily_report(report_data, show_back_button=True)
                else:
                    report_data = await get_range_report(start_date, end_date)
                    text, keyboard = format_range_report(report_data, show_back_button=True)

                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Erreur période {data}: {e}")
                await query.edit_message_text(f"❌ Erreur: {str(e)}")
            return

        # État caisse aujourd'hui
        if data == "caisse_today":
            await query.edit_message_text("⏳ Chargement...")

            try:
                report_data = await get_daily_report(datetime.now())
                text = f"💰 *ÉTAT DE LA CAISSE*\n{datetime.now().strftime('%d/%m/%Y')}\n\n"
                text += f"💚 Encaissements: {format_currency(report_data['encaissement'])}\n"
                text += f"   ({report_data['encaissement_count']} transactions)\n\n"
                text += f"💸 Décaissements: {format_currency(report_data['decaissement'])}\n"
                text += f"   ({report_data['decaissement_count']} transactions)\n\n"
                text += "━━━━━━━━━━━━━━━\n"

                solde_icon = "📈" if report_data["solde"] > 0 else "📉" if report_data["solde"] < 0 else "➖"
                text += f"{solde_icon} *SOLDE: {format_currency(report_data['solde'])}*"

                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔙 Menu principal", callback_data="back_main")]]
                )
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Erreur caisse: {e}")
                await query.edit_message_text(f"❌ Erreur: {str(e)}")
            return

    except Exception as e:
        logger.error(f"Erreur button_handler: {e}")
        try:
            await query.edit_message_text(f"❌ Une erreur s'est produite: {str(e)}")
        except Exception:
            logger.exception("Impossible d'éditer le message d'erreur au client.")


def main():
    """Lance le bot"""
    app = ApplicationBuilder().token(TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aide", help_command))
    app.add_handler(CommandHandler("jour", today_command))
    app.add_handler(CommandHandler("caisse", caisse_command))
    app.add_handler(CommandHandler("encaissement", encaissement_command))
    app.add_handler(CommandHandler("decaissement", decaissement_command))
    app.add_handler(CommandHandler("plage", plage_command))
    app.add_handler(CommandHandler("semaine", semaine_command))

    # NOUVELLES COMMANDES HOSPITALISATION
    app.add_handler(CommandHandler("hospi", hospi_command))
    app.add_handler(CommandHandler("hospi_date", hospi_date_command))
    app.add_handler(CommandHandler("hospi_periode", hospi_periode_command))

    # Boutons inline
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 Bot Finance démarré avec toutes les fonctionnalités")
    app.run_polling()


if __name__ == "__main__":
    main()