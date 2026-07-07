from datetime import timedelta

from flask import request, session, render_template, g, redirect
from werkzeug.security import generate_password_hash, check_password_hash

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import redirect_with_message, login_required, has_permission


@app.route('/edit_pass', methods=['POST'])
@login_required
@handle_errors()
def edit_pass():
    user_name = g.user['username']
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']

    if not (current_password and new_password and confirm_password):
        return redirect_with_message('index', "Tous les champs doivent être remplis.", 'danger')

    if new_password != confirm_password:
        return redirect_with_message('index', "Les nouveaux mots de passe ne correspondent pas.", 'danger')

    connection = get_db_connection()


    cursor = connection.cursor()
    cursor.execute('SELECT password FROM personnel WHERE username = %s', (user_name,))
    userS = cursor.fetchone()

    if userS:
        # Vérification du mot de passe (hash ou clair pour compatibilité)
        password_is_valid = check_password_hash(userS['password'], current_password)
        if not password_is_valid and userS['password'] == current_password:
            password_is_valid = True

        if password_is_valid:
            if current_password == new_password:
                return redirect_with_message('index', "Le nouveau mot de passe doit être différent de l'ancien.",
                                             'danger')
            else:
                # Hashage du nouveau mot de passe
                hashed_password = generate_password_hash(new_password)
                cursor.execute('UPDATE personnel SET password = %s WHERE username = %s', (hashed_password, user_name))
                connection.commit()
                return redirect_with_message('index', "Mot de passe changé avec succès !", 'success')

    return redirect_with_message('index', "Mot de passe actuel incorrect.", 'danger')




@app.route('/login', methods=['GET', 'POST'])
@handle_errors()
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = 'remember_me' in request.form  # Vérifier si la case est cochée

        connection = get_db_connection()


        cursor = connection.cursor()
        cursor.execute('SELECT * FROM personnel WHERE username = %s', (username,))
        user = cursor.fetchone()

        # Vérification du mot de passe (hash ou clair)
        password_is_valid = False
        if user:
            if check_password_hash(user['password'], password):
                password_is_valid = True
            elif user['password'] == password:
                password_is_valid = True
                # Migration automatique vers le hashage si le mot de passe est encore en clair
                new_hash = generate_password_hash(password)
                cursor.execute('UPDATE personnel SET password = %s WHERE username = %s', (new_hash, username))
                connection.commit()

        if user and password_is_valid:
            # Mise à jour de la dernière connexion
            cursor.execute('UPDATE personnel SET last_login = NOW() WHERE id_personnel = %s', (user['id_personnel'],))
            connection.commit()

            session['user_id'] = user['id_personnel']
            session['username'] = user['username']
            session['privileges'] = load_user_permissions(user['id_personnel'])

            if remember_me:
                # Si "Garder la session active" est coché, prolonger la session
                session.permanent = True  # Par défaut, la session Flask expire après une certaine période
                app.permanent_session_lifetime = timedelta(days=30)  # Session valide pendant 30 jours
            else:
                session.permanent = False  # La session expire à la fin de la session du navigateur

            return redirect_with_message('index', f"Bonjour {user['nom']} {user['prenom']}, vous êtes connecté.", 'success')
        else:
            return redirect_with_message('index', "Nom d'utilisateur ou mot de passe incorrect.", 'danger')

    return render_template('layout.html', title='Connexion', user=g.user)


@app.route('/charger_user_privileges', methods=['GET', 'POST'])
@handle_errors()
@login_required
def charger_user_privileges():
    user_id = session.get('user_id')
    if not user_id:
        return redirect_with_message(
            'login', 'Vous devez être connecté pour accéder à cette fonctionnalité.', 'danger')
    else:
        chargement()
    return redirect(request.referrer)

def chargement():
    user_id = session.get('user_id')

    connection = get_db_connection()
    cursor = connection.cursor()

    # Sélectionner l'utilisateur par ID
    cursor.execute('SELECT * FROM personnel WHERE id_personnel = %s', (user_id,))
    user = cursor.fetchone()

    if not user:
        return redirect_with_message(
            'index', "Utilisateur introuvable.", 'danger')

    # Charger les privilèges de l'utilisateur
    privileges = load_user_permissions(user['id_personnel'])
    session['privileges'] = privileges
    g.user = user


@app.route('/logout')
@login_required
@handle_errors()
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('privileges', None)

    return redirect_with_message('index', "Déconnexion réussie !", 'success')


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None

    connection = get_db_connection()

    try:
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM personnel WHERE id_personnel = %s', (user_id,))
        user = cursor.fetchone()
        return user
    except:
        return None
    finally:
        connection.close()


@app.before_request
def load_logged_in_user():
    g.user = get_current_user()  # Stocker l'utilisateur globalement
    if g.user:
        # Recharger les privilèges à chaque requête pour garantir qu'ils sont à jour
        g.privileges = load_user_permissions(g.user['id_personnel'])
        # Mettre à jour la session pour la cohérence (optionnel mais utile pour d'autres parties de l'app)
        session['privileges'] = g.privileges
    else:
        g.privileges = []

    # Mise à jour de la dernière activité (si utilisateur connecté)
    if g.user:
        try:
             # Optimisation : On pourrait vérifier si la dernière maj est récente pour éviter trop d'écritures
             # Mais pour l'instant on fait simple pour garantir le "En ligne"
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("UPDATE personnel SET last_activity = NOW() WHERE id_personnel = %s", (g.user['id_personnel'],))
            connection.commit()
            connection.close()
        except Exception as e:
            # On ne veut pas bloquer toute l'app si ça échoue
            print(f"Erreur update last_activity: {e}")


def load_user_permissions(user_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    query = """ SELECT p.nom_privilege
        FROM personnel_roles pr
        INNER JOIN roles_privileges rp ON pr.id_role = rp.id_role
        INNER JOIN privileges p ON rp.id_privilege = p.id_privilege
        WHERE pr.id_personnel = %s """
    cursor.execute(query, (user_id,))

    privileges = [row['nom_privilege'] for row in cursor.fetchall()]
    connection.close()

    return privileges




# if not has_permission('modifier_utilisateurs'):
#     flash('Vous n\'avez pas la permission de modifier les utilisateurs.', 'danger')
#     return redirect(url_for('dashboard'))


# <ul>
#     {% if 'voir_utilisateurs' in session.privileges %}
#     <li><a href="{{ url_for('gestion_utilisateurs') }}">Gérer les utilisateurs</a></li>
#     {% endif %}
#     {% if 'voir_rapports' in session.privileges %}
#     <li><a href="{{ url_for('voir_rapports') }}">Voir les rapports</a></li>
#     {% endif %}
# </ul>


def get_user_accessible_blocs(user):
    blocs_access = []

    if has_permission('ACCES_BLOC_601'):
        blocs_access.append('601')
    if has_permission('ACCES_BLOC_602'):
        blocs_access.append('602')
    if has_permission('ACCES_BLOC_501'):
        blocs_access.append('501')
    if has_permission('ACCES_BLOC_502'):
        blocs_access.append('502')
    if has_permission('ACCES_BLOC_401'):
        blocs_access.append('401')
    if has_permission('ACCES_BLOC_CPRE'):
        blocs_access.append('cpre')
    return blocs_access