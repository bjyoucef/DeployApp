from flask import render_template, g, request, jsonify, session
from functools import wraps


def handle_errors():
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                # Log de l'erreur (optionnel)
                print(f"Erreur : {str(e)}")

                # Renvoi d'une page HTML personnalisée
                if request.accept_mimetypes['text/html']:
                    return render_template('error/general_error.html', error_message=str(e),user=g.user), 500

                # Renvoi d'une réponse JSON en cas de requête API
                return jsonify({"error": "Une erreur est survenue", "details": str(e)}), 500

        return wrapped

    return decorator


def log_activity(action):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user_id = session.get('user_id', 'anonymous')
            # Logique pour enregistrer l'activité
            print(f"User {user_id} performed {action}")
            return f(*args, **kwargs)
        return wrapped
    return decorator



# @app.route('/delete_item/<int:item_id>', methods=['POST'])
# @login_required
# @permission_required('DELETE_ITEM')
# @log_activity('delete_item')
# def delete_item(item_id):
#     # Logique de suppression de l'élément
#     pass



# from flask_limiter import Limiter
#
# limiter = Limiter(app, key_func=lambda: session.get('user_id', 'anonymous'))
#
# @app.route('/login', methods=['POST'])
# @limiter.limit("5 per minute")  # 5 requêtes par minute
# def login():
#     # Logique de connexion
#     pass