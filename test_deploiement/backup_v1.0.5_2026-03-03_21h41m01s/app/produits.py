
from flask import request, redirect, url_for, render_template, g, flash

from app import app, get_db_connection
from app.utiles import login_required, permission_required
from app.error import handle_errors


@app.route('/produits', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_PRODUITS')
def produits():
    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        if request.method == 'POST':
            # Ajouter un produit
            description = request.form['description']
            prix = request.form['prix']
            id_created_par = 1  # ID de l'utilisateur (exemple)
            cursor.execute("""
                INSERT INTO produits (description, prix, id_created_par)
                VALUES (%s, %s, %s)
            """, (description, prix, id_created_par))
            connection.commit()
            flash('Produit ajouté avec succès', 'success')
            return redirect(url_for('produits'))

        # Récupérer tous les produits
        cursor.execute("SELECT * FROM produits ORDER BY id_produit DESC")
        produits = cursor.fetchall()
    finally:
        connection.close()

    return render_template('produits.html', produits=produits,user=g.user,title="Gestion des Produits")


@app.route('/modifier-produit/<int:id_produit>', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_PRODUITS')
def modifier_produit(id_produit):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        if request.method == 'POST':
            # Mettre à jour un produit
            description = request.form['description']
            prix = request.form['prix']
            cursor.execute("""
                UPDATE produits
                SET description = %s, prix = %s, updated_at = NOW()
                WHERE id_produit = %s
            """, (description, prix, id_produit))
            connection.commit()
            flash('Produit modifié avec succès', 'success')
            return redirect(url_for('produits'))

        # Récupérer les détails du produit
        cursor.execute("SELECT * FROM produits WHERE id_produit = %s", (id_produit,))
        produit = cursor.fetchone()
        if not produit:
            flash('Produit introuvable', 'danger')
            return redirect(url_for('produits'))
    finally:
        connection.close()

    return redirect(url_for('produits'))
