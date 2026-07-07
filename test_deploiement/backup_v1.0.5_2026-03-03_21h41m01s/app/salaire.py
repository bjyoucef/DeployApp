from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from flask import Response
from flask import request, redirect, url_for, render_template, g, flash
from num2words import num2words
from xhtml2pdf import pisa

from app import app, get_db_connection
from app.decharge_paiment import insert_decharge
from app.error import handle_errors
from app.utiles import login_required, permission_required, redirect_with_message


@app.route('/salaire', methods=['GET', 'POST'])
@login_required
@handle_errors()
@permission_required('ACCES_AUX_SALAIRE')
def salaire():
    id_employe = request.args.get('id_employe', type=int)
    id_service = request.args.get('id_service', type=int)
    shift_type = request.args.get('shift_type', type=str)
    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)

    user = g.user
    user_id = user['id_personnel']

    # Connexion à la base de données
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Récupérer ou insérer les dates existantes
        cursor.execute("""
            SELECT start_date, end_date FROM config_date WHERE user_id = %s AND page = 'salaire'
        """, (user_id,))
        result = cursor.fetchone()

        if not result:
            cursor.execute("""
                INSERT INTO config_date (user_id, page, start_date, end_date) 
                VALUES (%s, 'salaire', '2025-01-01', '2025-01-01')
            """, (user_id,))
            connection.commit()

            cursor.execute("""
                SELECT start_date, end_date FROM config_date WHERE user_id = %s AND page = 'salaire'
            """, (user_id,))
            result = cursor.fetchone()

        current_start_date = result['start_date'] or "2025-01-01"
        current_end_date = result['end_date'] or "2025-01-01"

        # Mise à jour des dates si elles sont différentes des valeurs stockées
        if start_date and start_date != str(current_start_date):
            cursor.execute("""
                UPDATE config_date SET start_date = %s WHERE user_id = %s AND page = 'salaire'
            """, (start_date, user_id))

        if end_date and end_date != str(current_end_date):
            cursor.execute("""
                UPDATE config_date SET end_date = %s WHERE user_id = %s AND page = 'salaire'
            """, (end_date, user_id))

        connection.commit()

        start_date = start_date or str(current_start_date)
        end_date = end_date or str(current_end_date)

        # Récupérer la liste des employés
        cursor.execute("""
            SELECT DISTINCT po.id_employe AS id_personnel, CONCAT(p.nom, ' ', p.prenom) AS full_name
                        FROM pointages po
            LEFT JOIN personnel p ON po.id_employe = p.id_personnel
        """)
        employes = cursor.fetchall()

        # Récupérer la liste des services
        cursor.execute("""
            SELECT DISTINCT po.id_service AS id_service, s.service_name
                            FROM pointages po
            LEFT JOIN services s ON po.id_service = s.id_service
        """)
        services = cursor.fetchall()

        # Construire la requête de filtrage
        query = """
            SELECT CONCAT(per.nom, ' ', per.prenom) AS full_name, 
                            p.id_employe, 
                            SUM(p.prix) AS prix_total, 
                            SUM(p.paiement) AS paiement_total
            FROM pointages p
            JOIN personnel per ON p.id_employe = per.id_personnel 
            WHERE p.date_pointage BETWEEN %s AND %s
        """
        params = [start_date, end_date]

        if id_employe:
            query += " AND p.id_employe = %s"
            params.append(id_employe)

            cursor.execute("""
                SELECT DISTINCT po.id_service AS id_service, s.service_name
                                FROM pointages po
                LEFT JOIN services s ON po.id_service = s.id_service 
                WHERE po.id_employe = %s
            """, (id_employe,))
            services = cursor.fetchall()

        if id_service:
            query += " AND p.id_service = %s"
            params.append(id_service)

            cursor.execute("""
                SELECT DISTINCT po.id_employe AS id_personnel, 
                       CONCAT(p.nom, ' ', p.prenom) AS full_name
                            FROM pointages po
                LEFT JOIN personnel p ON po.id_employe = p.id_personnel 
                WHERE po.id_service = %s
            """, (id_service,))
            employes = cursor.fetchall()

        if shift_type:
            query += " AND p.shift_type = %s"
            params.append(shift_type)

        # Pour éviter les erreurs d'agrégation, on ordonne par la date minimale de pointage
        query += " GROUP BY p.id_employe "
        cursor.execute(query, params)
        pointages = cursor.fetchall()

        total_salaire = sum(Decimal(p['prix_total'] or 0) for p in pointages)
        total_paiement = sum(Decimal(p['paiement_total'] or 0) for p in pointages)
        rest_a_payer = total_salaire - total_paiement

        cursor.execute("""
    SELECT p.id_pointage, p.id_employe, 
           CONCAT(COALESCE(per.nom, ''), ' ', COALESCE(per.prenom, '')) AS full_name, 
                   s.service_name, p.date_pointage, p.shift_type, 
           p.prix, p.prix_acte, COALESCE(p.paiement, 0) AS paiement
            FROM pointages p
            JOIN personnel per ON p.id_employe = per.id_personnel
            JOIN services s ON p.id_service = s.id_service
            WHERE p.date_pointage BETWEEN %s AND %s
""", (start_date, end_date))

        pointagesDetail = cursor.fetchall()


        # Grouper les détails par employé
        details_by_employe = {}
        for detail in pointagesDetail:
            emp_id = detail['id_employe']
            details_by_employe.setdefault(emp_id, []).append(detail)

        # Associer à chaque pointage ses détails
        for p in pointages:
            p['pointagesDetail'] = details_by_employe.get(p['id_employe'], [])

    except Exception as e:
        print(f"An error occurred: {e}")
        return "An error occurred", 500

    return render_template(
        'salaire.html',
        pointages=pointages,
        employes=employes,
        services=services,
        id_employe=id_employe,
        id_service=id_service,
        shift_type=shift_type,
        start_date=start_date,
        end_date=end_date,
        total_salaire=total_salaire,
        total_paiement=total_paiement,
        rest_a_payee=rest_a_payer,
        title="Salaires",
        user=g.user
    )

@app.route('/add_decharge_salaire', methods=['POST'])
@login_required
@handle_errors()
@permission_required('CREER_DECHARGE_SALAIRE')
def add_decharge_salaire():
    """Ajoute une nouvelle décharge de paiement pour un médecin KT."""
    full_name = request.form.get('full_name', '').strip()
    amount = request.form.get('amount', '').strip()
    date = request.form.get('date', '').strip()
    id_employe = request.form.get('id_employe', '').strip()
    dossiers = request.form.get('dossiers', '').strip()
    dossiers_list = [line.strip() for line in dossiers.splitlines() if line.strip()]

    # Validation des champs obligatoires
    if not full_name or not amount or not date:
        flash("Tous les champs sont requis.", "danger")
        return redirect(url_for('salaire'))

    # Validation du montant
    try:
        amount = Decimal(amount)
        if amount <= 0:
            flash("Erreur : Le montant doit être supérieur à zéro.", "danger")
            return redirect(url_for('salaire'))
        amount_in_words = num2words(float(amount), lang='fr').upper()
    except (InvalidOperation, ValueError):
        flash("Erreur : Montant invalide.", "danger")
        return redirect(url_for('salaire'))

    # Insertion de la décharge
    error = insert_decharge(full_name, None, id_employe, amount, date, dossiers_list, g.user['id_personnel'])
    if error:
        flash(error, "danger")
    else:
        flash("Décharge ajoutée avec succès.", "success")

    return redirect(url_for('salaire'))
