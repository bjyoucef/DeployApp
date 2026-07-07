from flask import render_template
from app import app
from app.error import handle_errors
from app.utils.utiles import login_required


@app.route('/')
def index():

    return render_template('index.html', title='Home')

@app.route('/admin')
@login_required
@handle_errors()
def index_admin():
    return render_template('admin/index_admin.html', title='Admin Home')

@app.route('/decharges_r')
@login_required
@handle_errors()
def decharges_r():
    return render_template('decharges_raccourcis.html', title='Decharges raccourcis')

# ==========================================
# ROUTE DE TEST POUR LES ERREURS (A RETIRER PLUS TARD)
# ==========================================
import pymysql
from werkzeug.exceptions import abort

@app.route('/test-error/<error_type>')
@handle_errors()
def test_error(error_type):
    if error_type == 'db':
        # Simuler une erreur de base de données
        raise pymysql.MySQLError("Simulation d'une erreur de connexion MySQL")
    elif error_type == '404':
        # Simuler une erreur 404
        abort(404)
    elif error_type == 'generic':
        # Simuler une erreur générique
        raise Exception("Simulation d'une erreur inattendue")
    else:
        return f"Type d'erreur inconnu : {error_type}. Essayez 'db', '404' ou 'generic'."