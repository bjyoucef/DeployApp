"""
Routes CRUD pour la gestion des conventions KT.
"""
from flask import request, redirect, url_for, render_template, g, flash, jsonify

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


# ============================================================
# PAGE ADMIN : Liste des conventions
# ============================================================
@app.route('/admin/conventions_kt')
@login_required
@handle_errors()

def conventions_kt():
    """Liste des conventions avec le nombre d'actes associés."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT c.*,
                   COUNT(ac.id) as nb_actes
            FROM kt_conventions c
            LEFT JOIN kt_actes_conventions ac ON c.id_convention = ac.id_convention AND ac.est_actif = 1
            GROUP BY c.id_convention
            ORDER BY c.nom_convention
        """)
        conventions = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'admin/kt_conventions.html',
        conventions=conventions,
        title="Gestion des Conventions"
    )


# ============================================================
# AJOUTER une convention
# ============================================================
@app.route('/admin/conventions_kt/add', methods=['POST'])
@login_required
@handle_errors()

def add_convention_kt():
    """Ajoute une nouvelle convention."""
    code = request.form.get('code_convention', '').strip().upper()
    nom = request.form.get('nom_convention', '').strip()

    if not code or not nom:
        flash("Le code et le nom de la convention sont obligatoires.", "danger")
        return redirect(url_for('conventions_kt'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO kt_conventions (code_convention, nom_convention, created_by, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (code, nom, g.user['id_personnel']))
        conn.commit()
        flash(f"Convention '{nom}' ajoutée avec succès.", "success")
    except Exception as e:
        conn.rollback()
        if 'Duplicate' in str(e):
            flash(f"Le code '{code}' existe déjà.", "danger")
        else:
            flash(f"Erreur : {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('conventions_kt'))


# ============================================================
# MODIFIER une convention
# ============================================================
@app.route('/admin/conventions_kt/update', methods=['POST'])
@login_required
@handle_errors()

def update_convention_kt():
    """Met à jour une convention existante."""
    id_convention = request.form.get('id_convention')
    code = request.form.get('code_convention', '').strip().upper()
    nom = request.form.get('nom_convention', '').strip()
    est_active = 1 if request.form.get('est_active') else 0

    if not id_convention or not code or not nom:
        flash("Tous les champs sont obligatoires.", "danger")
        return redirect(url_for('conventions_kt'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE kt_conventions
            SET code_convention = %s, nom_convention = %s, est_active = %s,
                updated_by = %s, updated_at = NOW()
            WHERE id_convention = %s
        """, (code, nom, est_active, g.user['id_personnel'], id_convention))
        conn.commit()
        flash(f"Convention '{nom}' mise à jour.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erreur : {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('conventions_kt'))


# ============================================================
# API : Liste des conventions (pour les selects dynamiques)
# ============================================================
@app.route('/api/conventions_kt')
@login_required
@handle_errors()
def api_conventions_kt():
    """Retourne la liste des conventions actives en JSON."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id_convention, code_convention, nom_convention
            FROM kt_conventions
            WHERE est_active = 1
            ORDER BY nom_convention
        """)
        conventions = cursor.fetchall()
        return jsonify({'success': True, 'conventions': conventions})
    finally:
        cursor.close()
        conn.close()


# ============================================================
# API : Conventions associées à un acte (avec prix)
# ============================================================
@app.route('/api/conventions_acte_kt/<int:id_acte>')
@login_required
@handle_errors()
def api_conventions_acte_kt(id_acte):
    """Retourne les conventions associées à un acte spécifique avec leurs prix."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                c.id_convention,
                c.code_convention,
                c.nom_convention,
                ac.prix,
                ac.part_operateur
            FROM kt_actes_conventions ac
            JOIN kt_conventions c ON ac.id_convention = c.id_convention
            WHERE ac.id_acte = %s AND ac.est_actif = 1 AND c.est_active = 1
            ORDER BY c.nom_convention
        """, (id_acte,))
        conventions = cursor.fetchall()

        # Convertir les Decimal en float pour JSON
        for conv in conventions:
            conv['prix'] = float(conv['prix']) if conv['prix'] else 0
            conv['part_operateur'] = float(conv['part_operateur']) if conv['part_operateur'] else 0

        return jsonify({'success': True, 'conventions': conventions})
    finally:
        cursor.close()
        conn.close()
