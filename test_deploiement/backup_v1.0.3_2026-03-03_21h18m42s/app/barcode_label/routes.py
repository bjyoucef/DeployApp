
from flask import render_template, request, redirect, url_for, flash, g
from app import app, get_db_connection
from app.barcode_label.utils import generate_barcode_base64, format_date_gs1, generate_gs1_string
from app.utils.utiles import login_required, handle_errors
import math

# Configuration
ITEMS_PER_PAGE = 20


@app.route('/barcode/create', methods=['GET', 'POST'])
@login_required
@handle_errors()

def create_barcode_label():
    """
    Route pour créer une étiquette code-barres.
    GET: Affiche le formulaire.
    POST: Enregistre les données et affiche l'étiquette pour impression.
    """
    if request.method == 'POST':
        product_name = request.form.get('product_name')
        gtin = request.form.get('gtin')
        lot = request.form.get('lot')
        sn = request.form.get('sn') # Optionnel
        exp_date = request.form.get('exp_date') # Format YYYY-MM-DD
        
        # Validation
        if not all([product_name, gtin, lot, exp_date]):
             flash("Tous les champs obligatoires sont requis.", "error")
             return redirect(url_for('create_barcode_label'))

        # Enregistrement
        conn = get_db_connection()
        label_id = None
        try:
            cursor = conn.cursor()
            sql = """
                INSERT INTO barcode_history (product_name, gtin, lot, sn, exp_date, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (product_name, gtin, lot, sn, exp_date, g.user['id_personnel']))
            conn.commit()
            label_id = cursor.lastrowid
        except Exception as e:
            flash(f"Erreur lors de l'enregistrement : {str(e)}", "error")
            return redirect(url_for('create_barcode_label'))
        finally:
            conn.close()

        # Si succès, redirection vers la vue d'impression pour éviter de reposter le formulaire (PRG)
        return redirect(url_for('reprint_barcode_label', label_id=label_id))

    return render_template('barcode_label/create.html')


@app.route('/barcode/reprint/<int:label_id>')
@login_required
@handle_errors()

def reprint_barcode_label(label_id):
    """
    Régénère et affiche une étiquette existante depuis l'historique.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        sql = "SELECT * FROM barcode_history WHERE id = %s"
        cursor.execute(sql, (label_id,))
        label_data = cursor.fetchone()
    finally:
        conn.close()

    if not label_data:
        flash("Étiquette non trouvée.", "error")
        return redirect(url_for('search_barcode_history'))

    # Préparation des données
    exp_date_str = str(label_data['exp_date']) # YYYY-MM-DD
    gs1_date = format_date_gs1(exp_date_str)
    
    # Affichage date (DD-MM-YY)
    try:
        display_date = label_data['exp_date'].strftime('%d-%m-%y')
    except:
        display_date = exp_date_str

    # Génération chaîne GS1 (Human Readable - avec parenthèses)
    # Utiliser le GTIN enregistré ou le défaut si manquant (anciens enregistrements)
    gtin = label_data.get('gtin')
    barcode_text_display = generate_gs1_string(gtin, gs1_date, label_data['lot'], label_data['sn'])
    
    # Pour l'encodage Barcode : On retire les parenthèses pour optimiser la densité (Code Set C possible pour les chiffres)
    # et éviter d'encoder des caractères inutiles qui allongent le code-barres.
    # Note: Dans un vrai GS1-128 strict, on devrait gérer le FNC1, mais retirer les parens est la première étape 
    # pour la lisibilité sur petite étiquette.
    barcode_clean = barcode_text_display.replace('(', '').replace(')', '')
    
    # Génération Image
    barcode_image = generate_barcode_base64(barcode_clean)

    return render_template(
        'barcode_label/label.html',
        product_name=label_data['product_name'],
        gtin=gtin,
        lot=label_data['lot'],
        sn=label_data['sn'],
        exp_date=display_date,
        barcode_image=barcode_image,
        barcode_text=barcode_text_display
    )

@app.route('/barcode/sheet/setup/<int:label_id>')
@login_required
@handle_errors()

def sheet_setup(label_id):
    """
    Configure l'impression en planche A4 pour une étiquette donnée.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM barcode_history WHERE id = %s", (label_id,))
        label = cursor.fetchone()
    finally:
        conn.close()

    if not label:
        flash("Étiquette non trouvée.", "error")
        return redirect(url_for('search_barcode_history'))

    return render_template('barcode_label/sheet_setup.html', label=label)

@app.route('/barcode/sheet/print/<int:label_id>')
@login_required
@handle_errors()

def print_sheet(label_id):
    """
    Génère la planche A4 d'étiquettes.
    """
    # 1. Récupération des données de l'étiquette
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM barcode_history WHERE id = %s", (label_id,))
        label_data = cursor.fetchone()
    finally:
        conn.close()

    if not label_data:
        return "Label not found", 404

    # 2. Récupération des paramètres de configuration (Layout)
    rows = int(request.args.get('rows', 8))
    cols = int(request.args.get('cols', 3))
    quantity = int(request.args.get('quantity', rows * cols))
    gap_x = float(request.args.get('gap_x', 0))
    gap_y = float(request.args.get('gap_y', 0))
    margin_top = float(request.args.get('margin_top', 0))
    margin_bottom = float(request.args.get('margin_bottom', 0))
    margin_left = float(request.args.get('margin_left', 0))
    margin_right = float(request.args.get('margin_right', 0))
    width = float(request.args.get('width', 0))
    height = float(request.args.get('height', 0))
    
    # Dimensions manuelles (si fournies, sinon CSS gère le grid)
    # On passe tout au template pour le CSS dynamique
    
    # 3. Génération de l'image Barcode (Une seule fois pour tout le monde pour l'instant)
    exp_date_str = str(label_data['exp_date'])
    gs1_date = format_date_gs1(exp_date_str)
    try:
        display_date = label_data['exp_date'].strftime('%d-%m-%y')
    except:
        display_date = exp_date_str
        
    gtin = label_data.get('gtin')
    barcode_data = generate_gs1_string(gtin, gs1_date, label_data['lot'], label_data['sn'])
    
    # Optimisation densité : on retire les parens pour l'encodage
    barcode_clean = barcode_data.replace('(', '').replace(')', '')
    barcode_image = generate_barcode_base64(barcode_clean)

    # 4. Rendu
    return render_template(
        'barcode_label/sheet_print.html',
        label=label_data,
        barcode_image=barcode_image,
        barcode_text=barcode_data,
        display_date=display_date,
        rows=rows,
        cols=cols,
        quantity=quantity,
        gap_x=gap_x,
        gap_y=gap_y,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
        margin_left=margin_left,
        margin_right=margin_right,
        width=width,
        height=height,
        gtin=gtin # Passer le gtin au template
    )


@app.route('/barcode/history')
@login_required
@handle_errors()

def search_barcode_history():
    """
    Affiche l'historique des étiquettes générées avec pagination.
    """
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Count total items
        cursor.execute("SELECT COUNT(*) as count FROM barcode_history")
        total_items = cursor.fetchone()['count']
        total_pages = math.ceil(total_items / ITEMS_PER_PAGE)

        # Fetch items
        sql = """
            SELECT h.*, p.nom as user_name, p.prenom as user_surname
            FROM barcode_history h
            LEFT JOIN personnel p ON h.created_by = p.id_personnel
            ORDER BY h.created_at DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(sql, (ITEMS_PER_PAGE, offset))
        history = cursor.fetchall()
        
        # Format name
        for item in history:
            if item['user_name']:
                item['user_name'] = f"{item['user_name']} {item['user_surname'] or ''}"

    finally:
        conn.close()

    return render_template(
        'barcode_label/history.html',
        history=history,
        current_page=page,
        total_pages=total_pages
    )

