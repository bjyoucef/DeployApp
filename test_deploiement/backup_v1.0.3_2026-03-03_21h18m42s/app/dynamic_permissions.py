from flask import g, session, request
import pymysql

# Note: We need to import app/db but circular imports might be an issue.
# We will use lazy import or app context.
from app import get_db_connection

class DynamicPermissionService:
    _routes_cache = {}  # { (endpoint, method): privilege_name }
    _ui_cache = {}      # { page_route: [ {selector, privilege} ] }

    @staticmethod
    def load_configurations():
        """Charge toutes les configurations en cache pour éviter les requêtes DB à chaque appel"""
        # Nécessite un contexte d'application ou une connexion active
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # 1. Charger Routes Config
                cursor.execute("""
                    SELECT arc.endpoint, arc.method, p.nom_privilege 
                    FROM actes_routes_config arc
                    JOIN privileges p ON arc.id_privilege = p.id_privilege
                """)
                # Structure: { ('manage_employees', 'POST'): 'MODIFIER_EMPLOYE' }
                temp_routes = {}
                for row in cursor.fetchall():
                    key = (row['endpoint'], row['method'])
                    temp_routes[key] = row['nom_privilege']
                
                DynamicPermissionService._routes_cache = temp_routes

                # 2. Charger UI Config
                cursor.execute("""
                    SELECT auc.page_route, auc.element_selector, p.nom_privilege 
                    FROM actes_ui_config auc
                    JOIN privileges p ON auc.id_privilege = p.id_privilege
                """)
                
                # Structure: { 'manage_employees': [ {selector: '#btn-add', privilege: 'AJOUTER_EMPLOYE'} ] }
                temp_ui = {}
                for row in cursor.fetchall():
                    page = row['page_route']
                    if page not in temp_ui:
                        temp_ui[page] = []
                    
                    temp_ui[page].append({
                        'selector': row['element_selector'],
                        'privilege': row['nom_privilege']
                    })
                
                DynamicPermissionService._ui_cache = temp_ui
                    
        except Exception as e:
            print(f"Erreur chargement permissions dynamiques: {e}")
            # Ne pas bloquer l'app si DB down, mais logger
        finally:
            connection.close()

    @staticmethod
    def reload_cache():
        return DynamicPermissionService.load_configurations()

    @staticmethod
    def get_route_privilege(endpoint, method):
        # Chercher correspondance exacte (ENDPOINT + METHOD)
        priv = DynamicPermissionService._routes_cache.get((endpoint, method))
        if priv:
            return priv
        
        # Chercher correspondance générique (ENDPOINT + ANY)
        priv = DynamicPermissionService._routes_cache.get((endpoint, 'ANY'))
        return priv

    @staticmethod
    def get_ui_permissions(page_route):
        return DynamicPermissionService._ui_cache.get(page_route, [])

    @staticmethod
    def get_protected_routes_url_map():
        """
        Génère une map { url: privilege } pour le frontend.
        Ne retourne que les routes sans arguments (liens directs).
        """
        from flask import url_for
        
        url_map = {}
        for (endpoint, method), privilege in DynamicPermissionService._routes_cache.items():
            if method == 'GET' or method == 'ANY':
                try:
                    # On tente de générer l'URL sans arguments
                    url = url_for(endpoint)
                    url_map[url] = privilege
                except Exception:
                    # Ignore routes that require args (e.g. /edit/<id>)
                    pass
        return url_map

# Instance globale (ou singleton)
permission_service = DynamicPermissionService()
