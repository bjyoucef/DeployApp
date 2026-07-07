from datetime import datetime
from io import BytesIO

from flask import make_response
from flask import render_template, g
from xhtml2pdf import pisa

from app import app, get_db_connection
from app.utils.utiles import login_required
from app.error import handle_errors


# exporte la miste des emprunts cles
@app.route('/export_pdf', methods=['GET'])
@login_required
@handle_errors()
def export_pdf():
    user = g.user

    # Récupérer les emprunts
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT e.*, p.nom AS nom_personne, c.numero_cle,c.description
            FROM cles_mouvement  e
            JOIN personnel p ON e.personne_id = p.id
            JOIN cles c ON e.cle_id = c.id
            WHERE e.date_retour IS NULL""")
    emprunts = cursor.fetchall()
    conn.close()

    # Générer le HTML à partir des données
    current_date = datetime.now().strftime("%d %B %Y")  # Format de date
    html = render_template('emprunts_pdf.html', emprunts=emprunts, current_date=current_date, user=g.user)

    # Create a BytesIO buffer for the PDF
    pdf_buffer = BytesIO()

    # Create PDF
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

    # Check for errors
    if pisa_status.err:
        return "Error generating PDF"

    # Move the buffer cursor to the beginning
    pdf_buffer.seek(0)

    # Create response
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=emprunts.pdf'

    return response


# REMISE DE CLÉ
@app.route('/export_retour_pdf/<int:id>', methods=['GET'])
@login_required
@handle_errors()
def export_retour_pdf(id):
    user = g.user

    # Récupérer les emprunts
    conn = get_db_connection()
    cursor = conn.cursor()

    # Récupérer l'ID de la clé de l'emprunt avec jointure pour les infos de la personne
    cursor.execute("""
                SELECT e.*,
                p_prend.nom AS nom_personne_prend,
                p_prend.prenom AS prenom_personne_prend,
                p_prend.role AS role_personne_prend,

                p_donne.nom AS nom_personne_donne,
                p_donne.prenom AS prenom_personne_donne,
                p_donne.role AS role_personne_donne,

                p_recoit.nom AS nom_personne_recoit,
                p_recoit.prenom AS prenom_personne_recoit,
                p_recoit.role AS role_personne_recoit,

                p_retourne.nom AS nom_personne_retourne,
                p_retourne.prenom AS prenom_personne_retourne,
                p_retourne.role AS role_personne_retourne,

                c.numero_cle,
                c.description
                FROM cles_mouvement  e
                LEFT JOIN personnel p_prend ON e.personne_id_prend = p_prend.id_personnel
                LEFT JOIN personnel p_donne ON e.personne_id_donne = p_donne.id_personnel
                LEFT JOIN personnel p_recoit ON e.personne_id_recoit = p_recoit.id_personnel
                LEFT JOIN personnel p_retourne ON e.personne_id_retourne = p_retourne.id_personnel
                LEFT JOIN cles c ON e.cle_id = c.id
        WHERE e.id = %s
    """, (id,))
    emprunts_info = cursor.fetchone()
    conn.close()

    # Vérifier si les données ont été trouvées
    if emprunts_info is None:
        return "Aucun emprunt trouvé avec cet ID.", 404

    # Générer le HTML à partir des données
    current_date = datetime.now().strftime("%d %B %Y")  # Format de date
    html = render_template('pdf/export_retour_pdf.html', emprunts_info=emprunts_info, current_date=current_date,
                           user=user)

    # Créer un buffer BytesIO pour le PDF
    pdf_buffer = BytesIO()

    # Créer le PDF
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

    # Vérifier les erreurs
    if pisa_status.err:
        return "Erreur lors de la génération du PDF", 500

    # Déplacer le curseur du buffer au début
    pdf_buffer.seek(0)

    # Créer la réponse
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=emprunts.pdf'

    return response


@app.route('/export_donne_pdf/<int:id>', methods=['GET'])
@login_required
@handle_errors()
def export_donne_pdf(id):
    user = g.user

    # Récupérer les emprunts
    conn = get_db_connection()
    cursor = conn.cursor()

    # Récupérer l'ID de la clé de l'emprunt avec jointure pour les infos de la personne
    cursor.execute("""
                SELECT e.*,
                p_prend.nom AS nom_personne_prend,
                p_prend.prenom AS prenom_personne_prend,
                p_prend.role AS role_personne_prend,

                p_donne.nom AS nom_personne_donne,
                p_donne.prenom AS prenom_personne_donne,
                p_donne.role AS role_personne_donne,

                p_recoit.nom AS nom_personne_recoit,
                p_recoit.prenom AS prenom_personne_recoit,
                p_recoit.role AS role_personne_recoit,

                p_retourne.nom AS nom_personne_retourne,
                p_retourne.prenom AS prenom_personne_retourne,
                p_retourne.role AS role_personne_retourne,

                c.numero_cle,
                c.description
                FROM cles_mouvement  e
                LEFT JOIN personnel p_prend ON e.personne_id_prend = p_prend.id_personnel
                LEFT JOIN personnel p_donne ON e.personne_id_donne = p_donne.id_personnel
                LEFT JOIN personnel p_recoit ON e.personne_id_recoit = p_recoit.id_personnel
                LEFT JOIN personnel p_retourne ON e.personne_id_retourne = p_retourne.id_personnel
                LEFT JOIN cles c ON e.cle_id = c.id
        WHERE e.id = %s
    """, (id,))
    emprunts_info = cursor.fetchone()
    conn.close()

    # Vérifier si les données ont été trouvées
    if emprunts_info is None:
        return "Aucun emprunt trouvé avec cet ID.", 404

    # Générer le HTML à partir des données
    current_date = datetime.now().strftime("%d %B %Y")  # Format de date
    html = render_template('pdf/export_donne_pdf.html', emprunts_info=emprunts_info, current_date=current_date,
                           user=user)

    # Créer un buffer BytesIO pour le PDF
    pdf_buffer = BytesIO()

    # Créer le PDF
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

    # Vérifier les erreurs
    if pisa_status.err:
        return "Erreur lors de la génération du PDF", 500

    # Déplacer le curseur du buffer au début
    pdf_buffer.seek(0)

    # Créer la réponse
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=emprunts.pdf'

    return response


@app.route('/export_manquant_pdf/<int:id>', methods=['GET'])
@login_required
@handle_errors()
def export_manquant_pdf(id):
    user = g.user

    # Récupérer les emprunts
    conn = get_db_connection()
    cursor = conn.cursor()

    # Récupérer l'ID de la clé de l'emprunt avec jointure pour les infos de la personne
    cursor.execute("""
                SELECT cm.*,
                p_marquee_manque.nom AS nom_marquee_manque,
                p_marquee_manque.prenom AS prenom_marquee_manque,
                p_marquee_manque.role AS role_marquee_manque,

                p_perte.nom AS nom_perte,
                p_perte.prenom AS prenom_perte,
                p_perte.role AS role_perte,

                p_marquee_retrevie.nom AS nom_marquee_retrevie,
                p_marquee_retrevie.prenom AS prenom_marquee_retrevie,
                p_marquee_retrevie.role AS role_marquee_retrevie,

                p_retrevie.nom AS nom_retrevie,
                p_retrevie.prenom AS prenom_retrevie,
                p_retrevie.role AS role_retrevie,

                c.numero_cle,
                c.description
                FROM cles_mouvement cm
                LEFT JOIN personnel p_marquee_manque ON cm.personne_id_marquee_manque = p_marquee_manque.id_personnel
                LEFT JOIN personnel p_perte ON cm.personne_id_perte = p_perte.id_personnel
                LEFT JOIN personnel p_marquee_retrevie ON cm.personne_id_marquee_retrevie = p_marquee_retrevie.id_personnel
                LEFT JOIN personnel p_retrevie ON cm.personne_id_retrevie = p_retrevie.id_personnel
                LEFT JOIN cles c ON cm.cle_id = c.id
        WHERE cm.id = %s
    """, (id,))
    cles_manquantes = cursor.fetchone()
    conn.close()

    # Vérifier si les données ont été trouvées
    if cles_manquantes is None:
        return "Aucun emprunt trouvé avec cet ID.", 404

    # Générer le HTML à partir des données
    current_date = datetime.now().strftime("%d %B %Y")  # Format de date
    html = render_template('pdf/export_manquant_pdf.html', cles_manquantes=cles_manquantes, current_date=current_date,
                           user=user)

    # Créer un buffer BytesIO pour le PDF
    pdf_buffer = BytesIO()

    # Créer le PDF
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

    # Vérifier les erreurs
    if pisa_status.err:
        return "Erreur lors de la génération du PDF", 500

    # Déplacer le curseur du buffer au début
    pdf_buffer.seek(0)

    # Créer la réponse
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=emprunts.pdf'

    return response


@app.route('/export_retrouvee_pdf/<int:id>', methods=['GET'])
@login_required
@handle_errors()
def export_retrouvee_pdf(id):
    user = g.user

    # Récupérer les emprunts
    conn = get_db_connection()
    cursor = conn.cursor()

    # Récupérer l'ID de la clé de l'emprunt avec jointure pour les infos de la personne
    cursor.execute("""
                SELECT cm.*,
                p_marquee_manque.nom AS nom_marquee_manque,
                p_marquee_manque.prenom AS prenom_marquee_manque,
                p_marquee_manque.role AS role_marquee_manque,

                p_perte.nom AS nom_perte,
                p_perte.prenom AS prenom_perte,
                p_perte.role AS role_perte,

                p_marquee_retrevie.nom AS nom_marquee_retrevie,
                p_marquee_retrevie.prenom AS prenom_marquee_retrevie,
                p_marquee_retrevie.role AS role_marquee_retrevie,

                p_retrevie.nom AS nom_retrevie,
                p_retrevie.prenom AS prenom_retrevie,
                p_retrevie.role AS role_retrevie,

                c.numero_cle,
                c.description
                FROM cles_mouvement cm
                LEFT JOIN personnel p_marquee_manque ON cm.personne_id_marquee_manque = p_marquee_manque.id_personnel
                LEFT JOIN personnel p_perte ON cm.personne_id_perte = p_perte.id_personnel
                LEFT JOIN personnel p_marquee_retrevie ON cm.personne_id_marquee_retrevie = p_marquee_retrevie.id_personnel
                LEFT JOIN personnel p_retrevie ON cm.personne_id_retrevie = p_retrevie.id_personnel
                LEFT JOIN cles c ON cm.cle_id = c.id
        WHERE cm.id = %s
    """, (id,))
    cles_manquantes = cursor.fetchone()
    conn.close()

    # Vérifier si les données ont été trouvées
    if cles_manquantes is None:
        return "Aucun emprunt trouvé avec cet ID.", 404

    # Générer le HTML à partir des données
    current_date = datetime.now().strftime("%d %B %Y")  # Format de date
    html = render_template('pdf/export_retrouvee_pdf.html', cles_manquantes=cles_manquantes, current_date=current_date,
                           user=user)

    # Créer un buffer BytesIO pour le PDF
    pdf_buffer = BytesIO()

    # Créer le PDF
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

    # Vérifier les erreurs
    if pisa_status.err:
        return "Erreur lors de la génération du PDF", 500

    # Déplacer le curseur du buffer au début
    pdf_buffer.seek(0)

    # Créer la réponse
    response = make_response(pdf_buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=emprunts.pdf'

    return response
