from datetime import datetime

from flask import g, render_template, request, redirect, url_for

from app import app, get_db_connection
from app.utils.utiles import login_required, has_permission
from app.error import handle_errors


@app.route('/stock')
@login_required
@handle_errors()

def stock():
    user = g.user
    user_id = user['id_personnel']

    # Base query
    query_base = 'SELECT * FROM stock '
    query_conditions = []
    query_params = []

    # Conditions basées sur les permissions utilisateur
    stock_types = []
    if has_permission('ACCES_AU_DEPARTEMENT_IT'):
        stock_types.append("IT")

    if has_permission('ACCES_AU_DEPARTEMENT_TECHNIQUE'):
        stock_types.append("Tech")

    if has_permission('ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'):
        stock_types.append("Appro")

    if stock_types:
        query_conditions.append("type IN (%s)" % ','.join(['%s'] * len(stock_types)))
        query_params.extend(stock_types)

    # Générer le WHERE clause
    query_where_clause = ""
    if query_conditions:
        query_where_clause = f"WHERE {' OR '.join(query_conditions)}"

    final_query = f"""
        {query_base}
        {query_where_clause}
    """

    # Exécuter la requête
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(final_query, query_params)
    items = cursor.fetchall()
    conn.close()

    return render_template('stock.html', title='Stock', items=items, user=g.user)


# Route to add a new item
@app.route('/add_item', methods=['GET', 'POST'])
@login_required
@handle_errors()

def add_item():
    if request.method == 'POST':
        item = request.form.get('name')
        category = request.form.get('category')
        quantity = request.form.get('quantity')
        description = request.form.get('description')
        mes = ('', '')

        # Récupération des infos de l'utilisateur
        user = g.user
        user_id = user['id_personnel']

        # Définition du type de stock selon les privilèges de l'utilisateur
        stock_types = ['Simple']  # Valeur par défaut pour un utilisateur simple
        # Vérifier les privilèges de l'utilisateur et assigner les types de stock appropriés
        if has_permission('ACCES_AU_DEPARTEMENT_IT'):
            stock_types.append('IT')
        if has_permission('ACCES_AU_DEPARTEMENT_TECHNIQUE'):
            stock_types.append('Tech')
        if has_permission('ACCES_AU_DEPARTEMENT_APPROVISIONNEMENT'):
            stock_types.append('Appro')

        stock_type = ', '.join(stock_types)  # Liste des types de stock associés à l'utilisateur

        try:
            # Connexion à la base de données et ajout de l'item
            conn = get_db_connection()
            cursor = conn.cursor()

            # Préparer la requête d'insertion
            cursor.execute(
                'INSERT INTO stock (item, category, quantity, description, type, user_id) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (item, category, quantity, description, stock_type, user_id)
            )
            conn.commit()

            # Récupérer l'ID du produit inséré
            cursor.execute(
                'SELECT id FROM stock WHERE item = %s AND category = %s AND type = %s AND user_id = %s',
                (item, category, stock_type, user_id)
            )
            product_id = cursor.fetchone()['id']

            # Enregistrer le mouvement (entrée dans le stock)
            date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                'INSERT INTO movements_stock (product_id, movement_type, quantity, date, user_id, stock_type) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (product_id, 'int', quantity, date, user_id, stock_type)
            )
            conn.commit()

        except Exception as e:
            # Gérer les erreurs
            conn.rollback()
            mes = (f"Erreur lors de l'ajout de l'article : {e}", 'danger')
        finally:
            # Assurer la fermeture du curseur et de la connexion
            cursor.close()
            conn.close()

        mes = ('Item added successfully!', 'success')
        return redirect(url_for('stock', message=mes[0], category=mes[1]))

    return redirect(url_for('stock', title='Stock', user=g.user))


# Route to edit an existing item
@app.route('/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@handle_errors()

def edit_item(item_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if request.method == 'POST':
            item = request.form['name']
            category = request.form['category']
            description = request.form['description']

            cursor.execute('UPDATE stock SET item =%s, category=%s, description=%s WHERE id=%s',
                           (item, category, description, item_id))
            conn.commit()

            return redirect(url_for('stock', message="Article mis à jour avec succès !", category="success"))

        cursor.execute('SELECT * FROM stock WHERE id=%s', (item_id,))
        item = cursor.fetchone()
    except Exception as e:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('stock', title='Stock', item=item, user=g.user))


# Route for adding a new item (purchase stock entry)
@app.route('/entry/<int:product_id>', methods=['GET', 'POST'])
@login_required
@handle_errors()

def add_stock_entry(product_id):
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            quantity = int(request.form.get('quantity', 0))
            supplier = request.form.get('supplier', '').strip()
            date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Validation des données
            if quantity <= 0 or not supplier:
                return redirect(url_for('stock',messages="La quantité doit être positive et le fournisseur est obligatoire.", category="danger"))

            conn = get_db_connection()
            cursor = conn.cursor()

            # Update stock quantity
            cursor.execute('UPDATE stock SET quantity = quantity + %s WHERE id = %s', (quantity, product_id))

            # Log the movement (entry)
            cursor.execute(
                'INSERT INTO movements_stock (product_id, movement_type, quantity, supplier, date) VALUES (%s, %s, %s, %s, %s)',
                (product_id, 'entry', quantity, supplier, date))

            conn.commit()
        except Exception as e:
            conn.rollback()
            return redirect(
                url_for('stock', messages=f"Erreur lors de l'ajout de l'entrée au stock : {e}",
                        category="danger"))
        finally:
            cursor.close()
            conn.close()

    return redirect(url_for('stock', title='Stock', user=g.user))


# Route for stock exit (distribution)
@app.route('/exit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@handle_errors()

def add_stock_exit(product_id):
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            quantity = int(request.form.get('quantity', 0))
            person = request.form.get('person', '').strip()
            service = request.form.get('service', '').strip()
            date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Validation des données
            if quantity <= 0 or not person or not service:
                return redirect(url_for('stock', message="Tous les champs sont obligatoires et la quantité doit être positive.", category="danger"))

            conn = get_db_connection()
            cursor = conn.cursor()

            # Vérifier la disponibilité du stock
            cursor.execute('SELECT quantity FROM stock WHERE id = %s', (product_id,))
            stock = cursor.fetchone()
            if not stock or stock['quantity'] < quantity:
                return redirect(url_for('stock', message="Quantité insuffisante en stock.", category="danger"))

            # Réduire la quantité en stock
            cursor.execute(
                '''UPDATE stock SET quantity = quantity - %s WHERE id = %s''',
                (quantity, product_id)
            )

            # Insérer un mouvement de sortie dans la table `movements_stock`
            cursor.execute(
                '''INSERT INTO movements_stock (product_id, movement_type, quantity, person, service, date)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (product_id, 'exit', quantity, person, service, date)
            )

            conn.commit()
            return redirect(url_for('stock', message="Sortie de stock enregistrée avec succès.", category="success"))
        except Exception as e:
            conn.rollback()
            return redirect(url_for('stock', message=f"Erreur lors de la sortie de stock : {e}", category="danger"))
        finally:
            cursor.close()
            conn.close()

    return redirect(url_for('stock', title='Stock', user=g.user))


# Route for viewing stock movements_stock (both entry and exit)
@app.route('/movements_stock')
@login_required
@handle_errors()

def view_movements_stock():
    user = g.user
    user_id = user['id_personnel']
    is_admin = user['is_admin']
    is_it = user['is_it']
    is_tech = user['is_tech']
    is_appro = user['is_appro']
    ac_stock = user['ac_stock']

    # Base query
    sql = 'SELECT m.id, s.item, m.movement_type, m.quantity, m.person, m.service, m.supplier, m.date FROM movements_stock m JOIN stock s ON m.product_id = s.id '
    params = []

    if is_admin:  # Admin, accès complet
        pass  # Pas besoin de modifier la requête SQL, admin voit tout

    elif ac_stock:  # Si l'utilisateur a accès au stock
        filters = []
        if is_it:  # IT avec accès au stock
            filters.append('m.stock_type = %s')
            params.append('IT')
        if is_tech:  # Tech avec accès au stock
            filters.append('m.stock_type = %s')
            params.append('Tech')
        if is_appro:  # Appro avec accès au stock
            filters.append('m.stock_type = %s')
            params.append('Appro')

        if filters:  # Si des filtres existent, les ajouter avec "OR"
            sql += 'WHERE (' + ' OR '.join(filters) + ') '
        else:  # Si aucun rôle spécifique, filtrer par user_id
            sql += 'WHERE m.user_id = %s'
            params.append(user_id)
    else:
        return "Accès refusé", 403  # Accès interdit si aucune autorisation

    sql += 'ORDER BY m.date DESC'  # Ajout de l'ordre par date

    # Exécution de la requête
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    movements_stock = cursor.fetchall()
    conn.close()

    return render_template('movements_stock.html', title='Stock', movements_stock=movements_stock, user=g.user)



