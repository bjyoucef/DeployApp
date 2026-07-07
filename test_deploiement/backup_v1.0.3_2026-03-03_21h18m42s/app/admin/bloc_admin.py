import pymysql
from flask import request, redirect, url_for, render_template, flash

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


@app.route('/bloc_admin', methods=['GET'])
@login_required
@handle_errors()

def bloc_admin():
    """Page d'administration des blocs"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer tous les blocs
    cursor.execute("SELECT * FROM bloc ORDER BY name_bloc")
    blocs = cursor.fetchall()

    # Pour chaque bloc, récupérer les produits inclus
    for bloc in blocs:
        cursor.execute(
            """
            SELECT p.id_produit, p.description, bp.qte
            FROM bloc_produits_inclus bp
            INNER JOIN produits p ON bp.id_produit = p.id_produit
            WHERE bp.id_bloc = %s
            ORDER BY p.description
            """, (bloc['id_bloc'],)
        )
        produits = cursor.fetchall()
        bloc['produits_inclus'] = produits

    cursor.close()
    connection.close()

    return render_template(
        'admin/bloc_admin.html',
        title="Gestion des Blocs",
        blocs=blocs
    )


@app.route('/bloc/nouveau', methods=['GET'])
@login_required
@handle_errors()

def nouveau_bloc():
    """Page pour créer un nouveau bloc"""
    return render_template(
        'admin/bloc_form.html',
        title="Nouveau Bloc Opératoire",
        mode='create'
    )


@app.route('/bloc/modifier/<int:id_bloc>', methods=['GET'])
@login_required
@handle_errors()

def modifier_bloc(id_bloc):
    """Page pour modifier un bloc existant"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM bloc WHERE id_bloc = %s", (id_bloc,))
    bloc = cursor.fetchone()

    cursor.close()
    connection.close()

    if not bloc:
        flash('Bloc non trouvé', 'danger')
        return redirect(url_for('bloc_admin'))

    return render_template(
        'admin/bloc_form.html',
        title=f"Modifier {bloc['name_bloc']}",
        mode='edit',
        bloc=bloc
    )


@app.route('/bloc/produits/<int:id_bloc>', methods=['GET'])
@login_required
@handle_errors()

def gerer_produits_bloc(id_bloc):
    """Page pour gérer les produits d'un bloc"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer le bloc
    cursor.execute("SELECT * FROM bloc WHERE id_bloc = %s", (id_bloc,))
    bloc = cursor.fetchone()

    if not bloc:
        flash('Bloc non trouvé', 'danger')
        return redirect(url_for('bloc_admin'))

    # Récupérer les produits inclus
    cursor.execute(
        """
        SELECT p.id_produit, p.description, p.prix, bp.qte, bp.id
        FROM bloc_produits_inclus bp
        INNER JOIN produits p ON bp.id_produit = p.id_produit
        WHERE bp.id_bloc = %s
        ORDER BY p.description
        """, (id_bloc,)
    )
    produits_inclus = cursor.fetchall()

    # Récupérer tous les produits disponibles
    cursor.execute("SELECT * FROM produits ORDER BY description")
    tous_produits = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
            'admin/produits/bloc_produits.html',
        title=f"Produits - {bloc['name_bloc']}",
        bloc=bloc,
        produits_inclus=produits_inclus,
        tous_produits=tous_produits
    )


@app.route('/add_bloc', methods=['POST'])
@login_required
@handle_errors()

def add_bloc():
    """Ajouter un nouveau bloc"""
    name_bloc = request.form['name_bloc']
    ipserver = request.form.get('ipserver') or None
    port = request.form.get('port') or None
    prix = request.form['prix']
    duree_base = request.form.get('duree_base', 90)
    prix_supplement_30min = request.form['prix_supplement_30min']
    description = request.form.get('description', '')

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
            INSERT INTO bloc (name_bloc, ipserver, port, prix, duree_base,
                            prix_supplement_30min, description, est_actif)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """
        cursor.execute(
            sql, (
                name_bloc, ipserver, port, prix, duree_base,
                prix_supplement_30min, description
            )
        )

        connection.commit()
        flash('Bloc ajouté avec succès', 'success')

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur lors de l\'ajout du bloc : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('bloc_admin'))


@app.route('/update_bloc', methods=['POST'])
@login_required
@handle_errors()

def update_bloc():
    """Mettre à jour un bloc existant"""
    id_bloc = request.form['id_bloc']
    name_bloc = request.form['name_bloc']
    ipserver = request.form.get('ipserver') or None
    port = request.form.get('port') or None
    prix = request.form['prix']
    duree_base = request.form.get('duree_base', 90)
    prix_supplement_30min = request.form['prix_supplement_30min']
    description = request.form.get('description', '')
    est_actif = 1 if request.form.get('est_actif') == 'on' else 0

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE bloc
            SET name_bloc = %s,
                ipserver = %s,
                port = %s,
                prix = %s,
                duree_base = %s,
                prix_supplement_30min = %s,
                description = %s,
                est_actif = %s
            WHERE id_bloc = %s
        """
        cursor.execute(
            sql, (
                name_bloc, ipserver, port, prix, duree_base,
                prix_supplement_30min, description, est_actif, id_bloc
            )
        )

        connection.commit()
        flash('Bloc mis à jour avec succès', 'success')

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur lors de la mise à jour : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('bloc_admin'))


@app.route('/delete_bloc/<int:id_bloc>', methods=['POST'])
@login_required
@handle_errors()

def delete_bloc(id_bloc):
    """Supprimer un bloc"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier s'il y a des dossiers liés à ce bloc
        cursor.execute(
            "SELECT COUNT(*) as count FROM location_bloc_dossier_patient WHERE id_bloc = %s",
            (id_bloc,)
        )
        result = cursor.fetchone()

        if result['count'] > 0:
            flash('Impossible de supprimer ce bloc car il est utilisé dans des dossiers', 'warning')
        else:
            # Supprimer d'abord les produits associés
            cursor.execute("DELETE FROM bloc_produits_inclus WHERE id_bloc = %s", (id_bloc,))
            # Puis supprimer le bloc
            cursor.execute("DELETE FROM bloc WHERE id_bloc = %s", (id_bloc,))
            connection.commit()
            flash('Bloc supprimé avec succès', 'success')

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('bloc_admin'))


@app.route('/toggle_bloc_status/<int:id_bloc>', methods=['POST'])
@login_required
@handle_errors()

def toggle_bloc_status(id_bloc):
    """Activer/désactiver un bloc"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE bloc
            SET est_actif = IF(est_actif = 1, 0, 1)
            WHERE id_bloc = %s
        """
        cursor.execute(sql, (id_bloc,))
        connection.commit()
        flash('Statut du bloc modifié avec succès', 'success')

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('bloc_admin'))


@app.route('/add_produit_to_bloc/<int:id_bloc>', methods=['POST'])
@login_required
@handle_errors()

def add_produit_to_bloc(id_bloc):
    """Ajouter un produit à un bloc"""
    id_produit = request.form['id_produit']
    qte = request.form['qte']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier si le produit est déjà inclus
        cursor.execute(
            """
            SELECT id FROM bloc_produits_inclus
            WHERE id_bloc = %s AND id_produit = %s
            """,
            (id_bloc, id_produit)
        )

        if cursor.fetchone():
            flash('Le produit est déjà inclus dans ce bloc', 'warning')
        else:
            cursor.execute(
                """
                INSERT INTO bloc_produits_inclus (id_bloc, id_produit, qte)
                VALUES (%s, %s, %s)
                """,
                (id_bloc, id_produit, qte)
            )
            connection.commit()
            flash('Produit ajouté au bloc avec succès', 'success')

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('gerer_produits_bloc', id_bloc=id_bloc))


@app.route('/update_produit_bloc/<int:id>', methods=['POST'])
@login_required
@handle_errors()

def update_produit_bloc(id):
    """Mettre à jour la quantité d'un produit dans un bloc"""
    qte = request.form['qte']
    id_bloc = request.form['id_bloc']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "UPDATE bloc_produits_inclus SET qte = %s WHERE id = %s",
            (qte, id)
        )
        connection.commit()
        flash('Quantité mise à jour avec succès', 'success')

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('gerer_produits_bloc', id_bloc=id_bloc))


@app.route('/remove_produit_from_bloc/<int:id>', methods=['POST'])
@login_required
@handle_errors()

def remove_produit_from_bloc(id):
    """Retirer un produit d'un bloc"""
    id_bloc = request.form['id_bloc']

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("DELETE FROM bloc_produits_inclus WHERE id = %s", (id,))
        connection.commit()
        flash('Produit supprimé du bloc avec succès', 'success')

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f'Erreur : {e}', 'danger')
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('gerer_produits_bloc', id_bloc=id_bloc))


@app.route( '/bloc/copier_produits', methods = [ 'GET' ] )
@login_required
@handle_errors()

def copier_produits_page():
    """Page pour copier les produits d'un bloc vers d'autres blocs"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer tous les blocs
    cursor.execute( "SELECT id_bloc, name_bloc, est_actif FROM bloc ORDER BY name_bloc" )
    blocs = cursor.fetchall()

    # Pour chaque bloc, compter les produits inclus
    for bloc in blocs:
        cursor.execute(
                "SELECT COUNT(*) as nb_produits FROM bloc_produits_inclus WHERE id_bloc = %s",
                (bloc[ 'id_bloc' ],)
                )
        result = cursor.fetchone()
        bloc[ 'nb_produits' ] = result[ 'nb_produits' ]

    cursor.close()
    connection.close()

    return render_template(
            'admin/produits/bloc_copier_produits.html',
            title = "Copier les Produits entre Blocs",
            blocs = blocs
            )


@app.route( '/bloc/get_produits/<int:id_bloc>', methods = [ 'GET' ] )
@login_required
@handle_errors()

def get_produits_bloc_json( id_bloc ):
    """API pour récupérer les produits d'un bloc en JSON"""
    from flask import jsonify

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
            """
            SELECT p.id_produit, p.description, p.prix, bp.qte
            FROM bloc_produits_inclus bp
                     INNER JOIN produits p ON bp.id_produit = p.id_produit
            WHERE bp.id_bloc = %s
            ORDER BY p.description
            """, (id_bloc,)
            )
    produits = cursor.fetchall()

    cursor.close()
    connection.close()

    # Convertir en liste de dictionnaires avec conversion des types
    produits_list = []
    for p in produits:
        produits_list.append({
            'id_produit': p['id_produit'],
            'description': p['description'],
            'prix': float(p['prix']) if p['prix'] else 0.0,
            'qte': float(p['qte']) if p['qte'] else 0.0
        })

    return jsonify(
            {
                    'success': True,
                    'produits': produits_list
                    }
            )


@app.route( '/bloc/copier_produits', methods = [ 'POST' ] )
@login_required
@handle_errors()

def copier_produits():
    """Copier les produits d'un bloc vers d'autres blocs"""

    id_bloc_source = request.form.get( 'id_bloc_source' )
    ids_blocs_destination = request.form.getlist( 'ids_blocs_destination[]' )
    mode_copie = request.form.get( 'mode_copie', 'ajouter' )  # 'ajouter' ou 'remplacer'

    if not id_bloc_source or not ids_blocs_destination:
        flash( 'Veuillez sélectionner un bloc source et au moins un bloc de destination', 'warning' )
        return redirect( url_for( 'copier_produits_page' ) )

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Récupérer les produits du bloc source
        cursor.execute(
                """
                SELECT id_produit, qte
                FROM bloc_produits_inclus
                WHERE id_bloc = %s
                """, (id_bloc_source,)
                )
        produits_source = cursor.fetchall()

        if not produits_source:
            flash( 'Le bloc source ne contient aucun produit', 'warning' )
            return redirect( url_for( 'copier_produits_page' ) )

        # Statistiques
        stats = {
                'blocs_traites': 0,
                'produits_ajoutes': 0,
                'produits_ignores': 0
                }

        # Pour chaque bloc de destination
        for id_bloc_dest in ids_blocs_destination:
            if id_bloc_dest == id_bloc_source:
                continue  # Ne pas copier sur soi-même

            # Si mode remplacer, supprimer d'abord les produits existants
            if mode_copie == 'remplacer':
                cursor.execute(
                        "DELETE FROM bloc_produits_inclus WHERE id_bloc = %s",
                        (id_bloc_dest,)
                        )

            # Copier chaque produit
            for produit in produits_source:
                # Vérifier si le produit existe déjà
                cursor.execute(
                        """
                        SELECT id
                        FROM bloc_produits_inclus
                        WHERE id_bloc = %s
                          AND id_produit = %s
                        """,
                        (id_bloc_dest, produit[ 'id_produit' ])
                        )
                existe = cursor.fetchone()

                if existe:
                    if mode_copie == 'ajouter':
                        # Produit déjà présent, on l'ignore
                        stats[ 'produits_ignores' ] += 1
                else:
                    # Ajouter le produit
                    cursor.execute(
                            """
                            INSERT INTO bloc_produits_inclus (id_bloc, id_produit, qte)
                            VALUES (%s, %s, %s)
                            """,
                            (id_bloc_dest, produit[ 'id_produit' ], produit[ 'qte' ])
                            )
                    stats[ 'produits_ajoutes' ] += 1

            stats[ 'blocs_traites' ] += 1

        connection.commit()

        # Message de succès détaillé
        message = f"Copie réussie : {stats[ 'produits_ajoutes' ]} produit(s) copié(s) vers {stats[ 'blocs_traites' ]} bloc(s)"
        if stats[ 'produits_ignores' ] > 0:
            message += f" ({stats[ 'produits_ignores' ]} produit(s) déjà présent(s) ignoré(s))"

        flash( message, 'success' )

    except pymysql.MySQLError as e:
        connection.rollback()
        flash( f'Erreur lors de la copie : {e}', 'danger' )
    finally:
        cursor.close()
        connection.close()

    return redirect( url_for( 'copier_produits_page' ) )