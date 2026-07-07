"""
Service de gestion des configurations - Version optimisée
Gère la configuration de la clinique et les taux de TVA
"""
from decimal import Decimal, InvalidOperation
from functools import lru_cache, wraps
from typing import Dict, Optional, List, Tuple
from contextlib import contextmanager
import logging

from flask import render_template, jsonify, request

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


# Configuration du logging
logger = logging.getLogger(__name__)


# ============================================================================
# DÉCORATEURS ET UTILITAIRES
# ============================================================================

def clear_cache_on_update(func):
    """Décorateur pour vider le cache après une mise à jour"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if result:
            ConfigService.get_clinique_info.cache_clear()
            ConfigService.get_tva_par_code.cache_clear()
            ConfigService.get_tous_tva_actifs.cache_clear()
        return result
    return wrapper


@contextmanager
def get_db_cursor(commit=False):
    """Context manager pour gérer les connexions DB proprement"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        yield cursor
        if commit:
            connection.commit()
    except Exception as e:
        connection.rollback()
        logger.error(f"Erreur DB: {e}")
        raise
    finally:
        cursor.close()
        connection.close()


# ============================================================================
# VALIDATEURS
# ============================================================================

class ConfigValidator:
    """Classe de validation des configurations"""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Valide un email"""
        if not email:
            return True  # Email vide accepté
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Valide un numéro de téléphone algérien"""
        if not phone:
            return True
        import re
        # Format: 021-XX-XX-XX ou 0XXX-XX-XX-XX
        pattern = r'^0\d{2,3}-\d{2}-\d{2}-\d{2}$'
        return bool(re.match(pattern, phone))

    @staticmethod
    def validate_url(url: str) -> bool:
        """Valide une URL"""
        if not url:
            return True
        import re
        pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}.*$'
        return bool(re.match(pattern, url))

    @staticmethod
    def validate_tva_rate(rate: Decimal) -> bool:
        """Valide un taux de TVA (0-100)"""
        try:
            return Decimal('0') <= rate <= Decimal('100')
        except (InvalidOperation, TypeError):
            return False

    @staticmethod
    def validate_config_value(type_donnee: str, valeur: str) -> Tuple[bool, str]:
        """Valide une valeur de configuration selon son type"""
        if type_donnee == 'email':
            if not ConfigValidator.validate_email(valeur):
                return False, "Format d'email invalide"
        elif type_donnee == 'telephone':
            if not ConfigValidator.validate_phone(valeur):
                return False, "Format de téléphone invalide (ex: 021-82-72-71)"
        elif type_donnee == 'url':
            if not ConfigValidator.validate_url(valeur):
                return False, "Format d'URL invalide (ex: https://example.com)"
        return True, ""


# ============================================================================
# SERVICE PRINCIPAL
# ============================================================================

class ConfigService:
    """Service pour gérer les configurations de la clinique et des TVA"""

    # ========================================================================
    # CONFIGURATION CLINIQUE
    # ========================================================================

    @staticmethod
    @lru_cache(maxsize=1)
    def get_clinique_info() -> Dict[str, str]:
        """
        Récupère toutes les informations de la clinique
        Mise en cache pour éviter les requêtes répétées
        """
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT cle, valeur
                    FROM config_clinique
                    WHERE est_actif = TRUE
                    ORDER BY ordre
                """)

                config = {row['cle']: row['valeur'] for row in cursor.fetchall()}

                # Retourner avec les mêmes clés que l'ancien dictionnaire
                return {
                    'nom': config.get('NOM_CLINIQUE', ''),
                    'adresse': config.get('ADRESSE', ''),
                    'nif': config.get('NIF', ''),
                    'nis': config.get('NIS', ''),
                    'rc': config.get('RC', ''),
                    'compte_bancaire': config.get('COMPTE_BANCAIRE', ''),
                    'telephone': config.get('TELEPHONE', ''),
                    'article': config.get('ARTICLE', ''),
                    'capital': config.get('CAPITAL_SOCIAL', ''),
                    'agence': config.get('AGENCE_BANCAIRE', ''),
                    'email': config.get('EMAIL', ''),
                    'site_web': config.get('SITE_WEB', ''),
                    'fax': config.get('FAX', ''),
                    'raison_sociale': config.get('RAISON_SOCIALE', ''),
                }
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos clinique: {e}")
            return {}

    @staticmethod
    def get_config_value(cle: str, defaut: str = '') -> str:
        """Récupère une valeur de configuration spécifique"""
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "SELECT valeur FROM config_clinique WHERE cle = %s",
                    (cle,)
                )
                result = cursor.fetchone()
                return result['valeur'] if result else defaut
        except Exception as e:
            logger.error(f"Erreur get_config_value pour {cle}: {e}")
            return defaut

    @staticmethod
    @clear_cache_on_update
    def update_config(cle: str, valeur: str) -> Tuple[bool, str]:
        """
        Met à jour une configuration
        Returns: (success, message)
        """
        try:
            # Récupérer le type de données pour validation
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT type_donnee, est_modifiable
                    FROM config_clinique
                    WHERE cle = %s
                    """,
                    (cle,)
                )
                result = cursor.fetchone()

                if not result:
                    return False, "Configuration introuvable"

                if not result['est_modifiable']:
                    return False, "Cette configuration n'est pas modifiable"

                # Valider la valeur
                is_valid, error_msg = ConfigValidator.validate_config_value(
                    result['type_donnee'], valeur
                )
                if not is_valid:
                    return False, error_msg

            # Mettre à jour
            with get_db_cursor(commit=True) as cursor:
                cursor.execute(
                    """
                    UPDATE config_clinique
                    SET valeur = %s
                    WHERE cle = %s AND est_modifiable = TRUE
                    """,
                    (valeur, cle)
                )

                if cursor.rowcount > 0:
                    logger.info(f"Configuration {cle} mise à jour: {valeur}")
                    return True, "Configuration mise à jour avec succès"
                else:
                    return False, "Aucune modification effectuée"

        except Exception as e:
            logger.error(f"Erreur update_config pour {cle}: {e}")
            return False, f"Erreur: {str(e)}"

    @staticmethod
    def get_config_par_categorie(categorie: str) -> List[Dict]:
        """Récupère toutes les configs d'une catégorie"""
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT cle, valeur, libelle, type_donnee, est_modifiable,
                           est_affiche_facture, categorie
                    FROM config_clinique
                    WHERE categorie = %s
                    ORDER BY ordre
                    """,
                    (categorie,)
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur get_config_par_categorie {categorie}: {e}")
            return []

    @staticmethod
    def get_toutes_categories() -> List[Dict]:
        """Récupère toutes les configurations groupées par catégorie"""
        categories = ['identite', 'coordonnees', 'fiscal', 'bancaire', 'juridique']
        result = {}
        for cat in categories:
            result[cat] = ConfigService.get_config_par_categorie(cat)
        return result

    # ========================================================================
    # CONFIGURATION TVA
    # ========================================================================

    @staticmethod
    @lru_cache(maxsize=128)
    def get_tva_par_code(code: str) -> Optional[Decimal]:
        """Récupère le taux de TVA pour un code donné"""
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT taux_tva
                    FROM config_tva
                    WHERE code = %s AND est_actif = TRUE
                    """,
                    (code,)
                )
                result = cursor.fetchone()
                return Decimal(str(result['taux_tva'])) if result else None
        except Exception as e:
            logger.error(f"Erreur get_tva_par_code pour {code}: {e}")
            return None

    @staticmethod
    @lru_cache(maxsize=1)
    def get_tous_tva_actifs() -> List[Dict]:
        """Récupère tous les taux de TVA"""
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT id, code, libelle, taux_tva, description, 
                       template_description, est_actif, ordre
                    FROM config_tva
                    ORDER BY ordre, libelle
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur get_tous_tva_actifs: {e}")
            return []

    @staticmethod
    def get_tva_options_html() -> str:
        """Génère les options HTML pour un select de TVA"""
        tvas = ConfigService.get_tous_tva_actifs()
        html_parts = []

        for tva in tvas:
            if tva['est_actif']:
                html_parts.append(
                    f'<option value="{tva["taux_tva"]}" data-code="{tva["code"]}">'
                    f'{tva["libelle"]} - {tva["taux_tva"]}%</option>'
                )

        return '\n'.join(html_parts)

    @staticmethod
    @clear_cache_on_update
    def update_tva(code: str, nouveau_taux: Decimal) -> Tuple[bool, str]:
        """
        Met à jour un taux de TVA
        Returns: (success, message)
        """
        try:
            # Valider le taux
            if not ConfigValidator.validate_tva_rate(nouveau_taux):
                return False, "Taux de TVA invalide (doit être entre 0 et 100)"

            with get_db_cursor(commit=True) as cursor:
                cursor.execute(
                    """
                    UPDATE config_tva
                    SET taux_tva = %s
                    WHERE code = %s
                    """,
                    (nouveau_taux, code)
                )

                if cursor.rowcount > 0:
                    logger.info(f"TVA {code} mise à jour: {nouveau_taux}%")
                    return True, "TVA mise à jour avec succès"
                else:
                    return False, "Code TVA introuvable"

        except Exception as e:
            logger.error(f"Erreur update_tva pour {code}: {e}")
            return False, f"Erreur: {str(e)}"

    @staticmethod
    @clear_cache_on_update
    def toggle_tva_status(tva_id: int, actif: bool) -> Tuple[bool, str]:
        """
        Active/désactive un taux de TVA
        Returns: (success, message)
        """
        try:
            with get_db_cursor(commit=True) as cursor:
                cursor.execute(
                    "UPDATE config_tva SET est_actif = %s WHERE id = %s",
                    (actif, tva_id)
                )

                if cursor.rowcount > 0:
                    status = "activée" if actif else "désactivée"
                    logger.info(f"TVA ID {tva_id} {status}")
                    return True, f"TVA {status} avec succès"
                else:
                    return False, "TVA introuvable"

        except Exception as e:
            logger.error(f"Erreur toggle_tva_status pour {tva_id}: {e}")
            return False, f"Erreur: {str(e)}"

    @staticmethod
    @clear_cache_on_update
    def add_tva(code: str, libelle: str, taux: Decimal,
                description: str = "") -> Tuple[bool, str]:
        """
        Ajoute un nouveau taux de TVA
        Returns: (success, message)
        """
        try:
            # Validation
            if not code or not libelle:
                return False, "Code et libellé obligatoires"

            if not ConfigValidator.validate_tva_rate(taux):
                return False, "Taux de TVA invalide (0-100)"

            code = code.strip().upper()

            with get_db_cursor(commit=True) as cursor:
                # Vérifier que le code n'existe pas
                cursor.execute(
                    "SELECT id FROM config_tva WHERE code = %s",
                    (code,)
                )
                if cursor.fetchone():
                    return False, "Ce code existe déjà"

                # Ordre max + 1
                cursor.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM config_tva")
                ordre = cursor.fetchone()[0]

                # Insérer
                cursor.execute(
                    """
                    INSERT INTO config_tva 
                    (code, libelle, taux_tva, description, ordre)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (code, libelle, taux, description, ordre)
                )

                logger.info(f"TVA ajoutée: {code} - {libelle} ({taux}%)")
                return True, "TVA ajoutée avec succès"

        except Exception as e:
            logger.error(f"Erreur add_tva: {e}")
            return False, f"Erreur: {str(e)}"

    @staticmethod
    def get_stats_tva() -> Dict:
        """Récupère les statistiques sur les TVA"""
        try:
            tvas = ConfigService.get_tous_tva_actifs()
            return {
                'total': len(tvas),
                'actifs': len([t for t in tvas if t['est_actif']]),
                'inactifs': len([t for t in tvas if not t['est_actif']]),
                'taux_9': len([t for t in tvas if t['taux_tva'] == Decimal('9.00')]),
                'taux_19': len([t for t in tvas if t['taux_tva'] == Decimal('19.00')]),
                'taux_0': len([t for t in tvas if t['taux_tva'] == Decimal('0.00')]),
            }
        except Exception as e:
            logger.error(f"Erreur get_stats_tva: {e}")
            return {}


# ============================================================================
# FONCTIONS D'AIDE POUR COMPATIBILITÉ
# ============================================================================

def get_clinique_info() -> Dict[str, str]:
    """Fonction helper pour compatibilité avec l'ancien code"""
    return ConfigService.get_clinique_info()


# ============================================================================
# ROUTES D'ADMINISTRATION DES CONFIGURATIONS
# ============================================================================

@app.route("/facturation/config/clinique")
@login_required
@handle_errors()

def admin_config_clinique():
    """Page d'administration de la configuration clinique"""
    configs_par_categorie = ConfigService.get_toutes_categories()

    return render_template(
        "facturation/config_clinique.html",
        configs=configs_par_categorie
    )


@app.route("/facturation/config/clinique/update", methods=["POST"])
@login_required
@handle_errors()

def update_config_clinique():
    """Met à jour une configuration clinique"""
    cle = request.form.get("cle")
    valeur = request.form.get("valeur", "").strip()

    if not cle:
        return jsonify({"success": False, "message": "Clé manquante"}), 400

    success, message = ConfigService.update_config(cle, valeur)

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 400


@app.route("/facturation/config/tva")
@login_required
@handle_errors()

def admin_config_tva():
    """Page d'administration des taux de TVA"""
    tvas = ConfigService.get_tous_tva_actifs()
    stats = ConfigService.get_stats_tva()

    return render_template(
        "facturation/config_tva.html",
        tvas=tvas,
        stats=stats
    )


@app.route("/facturation/config/tva/update", methods=["POST"])
@login_required
@handle_errors()

def update_config_tva():
    """Met à jour un taux de TVA"""
    code = request.form.get("code")
    taux_str = request.form.get("taux")

    if not code or not taux_str:
        return jsonify({"success": False, "message": "Paramètres manquants"}), 400

    try:
        taux = Decimal(taux_str)
    except (InvalidOperation, ValueError):
        return jsonify({"success": False, "message": "Taux invalide"}), 400

    success, message = ConfigService.update_tva(code, taux)

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 400


@app.route("/facturation/config/tva/toggle", methods=["POST"])
@login_required
@handle_errors()

def toggle_tva_status():
    """Active/désactive un taux de TVA"""
    tva_id_str = request.form.get("id")
    actif_str = request.form.get("actif")

    if not tva_id_str or actif_str is None:
        return jsonify({"success": False, "message": "Paramètres manquants"}), 400

    try:
        tva_id = int(tva_id_str)
        actif = actif_str == '1'
    except ValueError:
        return jsonify({"success": False, "message": "ID invalide"}), 400

    success, message = ConfigService.toggle_tva_status(tva_id, actif)

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 400


@app.route("/facturation/config/tva/add", methods=["POST"])
@login_required
@handle_errors()

def add_tva():
    """Ajoute un nouveau taux de TVA"""
    code = request.form.get("code", "").strip()
    libelle = request.form.get("libelle", "").strip()
    taux_str = request.form.get("taux")
    description = request.form.get("description", "").strip()

    if not code or not libelle or not taux_str:
        return jsonify({"success": False, "message": "Paramètres manquants"}), 400

    try:
        taux = Decimal(taux_str)
    except (InvalidOperation, ValueError):
        return jsonify({"success": False, "message": "Taux invalide"}), 400

    success, message = ConfigService.add_tva(code, libelle, taux, description)

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 400


@app.route("/facturation/config/tva/stats")
@login_required
@handle_errors()

def get_tva_stats():
    """Récupère les statistiques des TVA (API)"""
    stats = ConfigService.get_stats_tva()
    return jsonify({"success": True, "data": stats})


@app.route("/facturation/config/tva/update_template", methods=["POST"])
@login_required
@handle_errors()

def update_tva_template():
    """Met à jour le template de description d'une TVA"""
    tva_id_str = request.form.get("tva_id")
    template = request.form.get("template", "").strip()

    if not tva_id_str:
        return jsonify({"success": False, "message": "ID manquant"}), 400

    try:
        tva_id = int(tva_id_str)
    except ValueError:
        return jsonify({"success": False, "message": "ID invalide"}), 400

    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE config_tva
                SET template_description = %s
                WHERE id = %s
                """,
                (template if template else None, tva_id)
            )

            if cursor.rowcount > 0:
                # Vider le cache
                ConfigService.get_tous_tva_actifs.cache_clear()
                logger.info(f"Template TVA ID {tva_id} mis à jour")
                return jsonify({"success": True, "message": "Template enregistré avec succès"})
            else:
                return jsonify({"success": False, "message": "TVA introuvable"}), 404

    except Exception as e:
        logger.error(f"Erreur update_tva_template pour ID {tva_id}: {e}")
        return jsonify({"success": False, "message": f"Erreur: {str(e)}"}), 500


