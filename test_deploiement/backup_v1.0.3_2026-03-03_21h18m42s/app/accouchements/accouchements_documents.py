# app/accouchements_documents.py
import os
from datetime import datetime
from io import BytesIO

from flask import g
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from app import app


DOCS_STORAGE_PATH = os.path.join(app.root_path, 'static', 'documents', 'accouchements')
os.makedirs(DOCS_STORAGE_PATH, exist_ok=True)


def get_common_styles():
    """Retourne les styles standards pour les documents"""
    styles = getSampleStyleSheet()
    return styles

def format_date(date_value):
    """Formate une date"""
    if date_value:
        if isinstance(date_value, str):
            return date_value
        return date_value.strftime('%d/%m/%Y')
    return ''

def create_header(story):
    """Ajoute l'en-tête standard avec le logo Inaya"""
    try:
        logo_path = os.path.join(app.root_path, 'static', 'images', 'entet_inaya.png')
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=10*cm, height=3*cm)
            story.append(logo)
            story.append(Spacer(1, 0.5*cm))
    except Exception as e:
        print(f"Erreur logo: {e}")
        pass

def create_footer(story, doc_width):
    """Ajoute le pied de page standard"""
    story.append(Spacer(1, 1.5*cm))
    footer_style = ParagraphStyle('Footer', fontSize=8, alignment=TA_CENTER, textColor=colors.white)
    footer_text = """Tél : 023.62.88.62<br/>
Site web : www.inayaclinic.com<br/>
Email : contact@inayaclinic.com<br/>
Adresse : 04 Rue Duguet Vieux Kouba, Alger"""

    footer_table = Table([[Paragraph(footer_text, footer_style)]], colWidths=[doc_width])
    footer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#4a5568')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(footer_table)


def generer_tous_documents_accouchement(cursor, id_dossier):
    """
    Génère les 4 documents obligatoires pour un accouchement
    """
    cursor.execute(
        """
        SELECT d.*,
               CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name
        FROM accouchement_dossiers d
        LEFT JOIN doctors doc ON d.id_gyneco = doc.id
        WHERE d.id_dossier = %s
        """, (id_dossier,)
    )

    dossier = cursor.fetchone()
    if not dossier:
        raise ValueError(f"Dossier {id_dossier} non trouvé")

    # Générer chaque document
    docs = [
        ('CERTIFICAT_ACCOUCHEMENT', generer_certificat_accouchement),
        ('CONGE_MATERNITE', generer_conge_maternite),
        ('COMPTE_RENDU_POST_PARTUM', generer_compte_rendu_post_partum),
    ]

    # Ajouter compte rendu opératoire si césarienne
    if dossier['type_accouchement'] == 'CESARIENNE':
        docs.append(('COMPTE_RENDU_OPERATOIRE', generer_compte_rendu_operatoire))

    for doc_type, generateur in docs:
        pdf_data, contenu_json = generateur(dossier)
        sauvegarder_document(cursor, id_dossier, doc_type, pdf_data, contenu_json)


def sauvegarder_document(cursor, id_dossier, type_document, pdf_data, contenu_json):
    """Sauvegarde un document PDF et enregistre en DB"""
    import json

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{id_dossier}_{type_document}_{timestamp}.pdf"
    filepath = os.path.join(DOCS_STORAGE_PATH, filename)

    with open(filepath, 'wb') as f:
        f.write(pdf_data)

    cursor.execute(
        """
        INSERT INTO accouchement_documents_generes
            (id_dossier, type_document, contenu_json, fichier_path, genere_par)
        VALUES (%s, %s, %s, %s, %s)
        """, (
            id_dossier,
            type_document,
            json.dumps(contenu_json),
            filepath,
            g.user['id_personnel']
        )
    )


# ============================================================================
# 1️⃣ COMPTE RENDU MÉDICAL DU POST-PARTUM
# ============================================================================

def generer_compte_rendu_post_partum(dossier):
    """Génère le compte rendu médical du post-partum selon le modèle exact"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1*cm,
        bottomMargin=1*cm,
        leftMargin=2*cm,
        rightMargin=2*cm
    )
    story = []
    
    # 1. En-tête
    create_header(story)

    # 2. Titre
    style_title = ParagraphStyle(
        'Title',
        fontSize=14,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        spaceAfter=12
    )
    story.append(Paragraph("<u>COMPTE RENDU MEDICAL DU POST-PARTUM</u>", style_title))
    story.append(Spacer(1, 0.5*cm))

    # 3. Date
    style_date = ParagraphStyle('Date', fontSize=10, alignment=TA_RIGHT)
    story.append(Paragraph(f"Alger le : {datetime.now().strftime('%d/%m/%Y')}", style_date))
    story.append(Spacer(1, 0.5*cm))

    # 4. Identification Patient
    style_subtitle = ParagraphStyle('Subtitle', fontSize=11, fontName='Helvetica-Bold', spaceAfter=6)
    story.append(Paragraph("<u>IDENTIFICATION DE LA PATIENTE :</u>", style_subtitle))
    story.append(Spacer(1, 0.2*cm))

    patiente = dossier.get('patiente', '').upper()
    age = dossier.get('age_patiente', '...')
    
    # Tableau infos
    gr = dossier.get('groupage_sanguin', '...')
    rh = dossier.get('rhesus', '...')
    parite = dossier.get('parite', 'G...P...C...')
    ddr = format_date(dossier.get('ddr')) or '...'
    age_gest = dossier.get('age_gestationnel', '...')

    info_data = [
        [f"Nom Prénom: {patiente}"],
        [f"Age : {age} ans", f"Groupage : {gr}      Rhésus : {rh}"],
        [f"Parité : {parite}", f"DDR : {ddr}      AGE GEST : {age_gest}"]
    ]

    info_table = Table(info_data, colWidths=[17*cm])
    info_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.8*cm))

    # 5. Corps du rapport
    style_normal = ParagraphStyle('Normal', fontSize=10, leading=14)
    style_bold = ParagraphStyle('Bold', fontSize=10, leading=14, fontName='Helvetica-Bold')

    # Urgence
    story.append(Paragraph("<u>Urgence :</u>", style_subtitle))
    
    gyneco = dossier.get('gyneco_name', 'Dr ...........................')
    date_acc = datetime.strptime(str(dossier.get('date_accouchement')), '%Y-%m-%d').strftime('%d/%m/%Y')
    
    story.append(Paragraph(
        f"Je soussigné(e) <b>Dr {gyneco}</b> certifie que la patiente susnommée a accouché le <b>{date_acc}</b>.",
        style_normal
    ))
    story.append(Spacer(1, 0.5*cm))

    # Mode d'accouchement
    story.append(Paragraph("<u>Mode d'accouchement :</u>", style_subtitle))
    
    type_acc = dossier.get('type_accouchement')
    details = dossier.get('mode_accouchement_detail', '') or ''

    # Cases à cocher (caractères unicode)
    CHECKED = "☒"
    UNCHECKED = "☐"

    if type_acc == 'VOIE_BASSE':
        story.append(Paragraph(f"{CHECKED} <b>Par voie basse</b>", style_normal))
        story.append(Paragraph(f"{UNCHECKED} Avec péridurale", style_normal))
        story.append(Paragraph(f"{UNCHECKED} Avec épisiotomie", style_normal))
        story.append(Paragraph(f"{UNCHECKED} Avec forceps", style_normal))
    else:
        story.append(Paragraph(f"{CHECKED} <b>Par césarienne</b>", style_normal))
        
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("<b>Dans le cadre de l'urgence :</b>", style_bold))
        story.append(Paragraph(f"{UNCHECKED} ERCF PATHOLOGIQUE / SOUFFRANCE FŒTALE AIGUE", style_normal))
        story.append(Paragraph(f"{UNCHECKED} LIQUIDE AMNIOTIQUE TEINTÉ", style_normal))
        story.append(Paragraph(f"{UNCHECKED} DILATATION STATIONNAIRE", style_normal))
        story.append(Paragraph(f"{UNCHECKED} DÉFAUT D'ENGAGEMENT", style_normal))
        # ... autres motifs urgence

        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("<b>Prophylactique :</b>", style_bold))
        story.append(Paragraph(f"{UNCHECKED} UTÉRUS CICATRICIEL", style_normal))
        story.append(Paragraph(f"{UNCHECKED} BASSIN VICIÉ", style_normal))
        story.append(Paragraph(f"{UNCHECKED} PRÉSENTATION DU SIÈGE", style_normal))
        story.append(Paragraph(f"{UNCHECKED} MACROSOMIE", style_normal))

    story.append(Spacer(1, 0.5*cm))

    # Pathologies maternelles
    story.append(Paragraph("<u>Pathologies maternelles associées :</u>", style_subtitle))
    
    # Récupérer pathologies stockées ou concaténer pathologie_grossesse
    path_mat = dossier.get('pathologies_maternelles') or ''
    path_grossesse = dossier.get('pathologie_grossesse') or ''
    
    combined_path = []
    if path_mat: combined_path.append(path_mat)
    if path_grossesse: combined_path.append(path_grossesse)
    
    final_path = " / ".join(combined_path) if combined_path else "Néant"

    story.append(Paragraph(final_path, style_normal))

    story.append(Spacer(1, 0.5*cm))

    # Observation / Conclusion
    story.append(Paragraph("<u>Observation / Complications :</u>", style_subtitle))
    
    obs = dossier.get('observations', '') or dossier.get('complications_medicales', '')
    if not obs:
        obs = "RAS (Rien à signaler)"
    
    story.append(Paragraph(obs, style_normal))
    
    # 6. Signature
    story.append(Spacer(1, 1.5*cm))
    style_sign = ParagraphStyle('Sign', fontSize=11, alignment=TA_RIGHT, fontName='Helvetica-Bold')
    story.append(Paragraph("Le Gynécologue", style_sign))
    
    # 7. Footer
    create_footer(story, doc.width)

    doc.build(story)
    return buffer.getvalue(), {'patiente': patiente, 'date': date_acc}


# ============================================================================
# 2️⃣ CERTIFICAT D'ACCOUCHEMENT
# ============================================================================

def generer_certificat_accouchement(dossier):
    """Génère le certificat d'accouchement"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1*cm,
        bottomMargin=1*cm,
        leftMargin=2*cm,
        rightMargin=2*cm
    )
    story = []

    create_header(story)

    # Date
    style_date = ParagraphStyle('Date', fontSize=10, alignment=TA_RIGHT)
    story.append(Paragraph(f"Alger le : {datetime.now().strftime('%d/%m/%Y')}", style_date))
    story.append(Spacer(1, 1.5*cm))

    # Titre
    style_title = ParagraphStyle(
        'Title',
        fontSize=18,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#ec4899'),
        spaceAfter=20
    )
    story.append(Paragraph("CERTIFICAT D'ACCOUCHEMENT", style_title))
    story.append(Spacer(1, 1.5*cm))

    # Corps
    style_body = ParagraphStyle('Body', fontSize=12, leading=24, alignment=TA_LEFT)
    
    gyneco = dossier.get('gyneco_name', 'Dr ....................')
    patiente = dossier.get('patiente', '...........................').upper()
    nom_epoux = dossier.get('nom_epoux')
    if nom_epoux:
        patiente += f" épse {nom_epoux.upper()}"
        
    date_acc = datetime.strptime(str(dossier.get('date_accouchement')), '%Y-%m-%d').strftime('%d/%m/%Y')
    
    sexe = dossier.get('sexe_bebe', '.........')
    prenom = dossier.get('prenom_bebe', '....................')

    poids_kg = dossier.get('poids_naissance')
    poids_g = int(poids_kg * 1000) if poids_kg else '....'

    texte = f"""
    Je soussigné(e), <b>Dr {gyneco}</b><br/><br/>
    Certifie avoir pratiqué l'accouchement de Mme <b>{patiente}</b><br/><br/>
    Le <b>{date_acc}</b><br/><br/>
    D'un nouveau-né de sexe <b>{sexe}</b><br/>
    Pésant <b>{poids_g} g</b><br/>
    Prénommé(e) <b>{prenom}</b><br/><br/>
    <font size=10>Ce certificat est délivré pour servir et valoir ce que de droit.</font>
    """
    story.append(Paragraph(texte, style_body))

    # Signature
    story.append(Spacer(1, 2*cm))
    style_sign = ParagraphStyle('Sign', fontSize=12, alignment=TA_RIGHT, fontName='Helvetica-Bold')
    story.append(Paragraph("Le Médecin", style_sign))

    create_footer(story, doc.width)

    doc.build(story)
    return buffer.getvalue(), {'patiente': patiente, 'date': date_acc}


# ============================================================================
# 3️⃣ CONGÉ DE MATERNITÉ
# ============================================================================

def generer_conge_maternite(dossier):
    """Génère le congé de maternité"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1*cm,
        bottomMargin=1*cm,
        leftMargin=2*cm,
        rightMargin=2*cm
    )
    story = []

    create_header(story)

    # Date
    style_date = ParagraphStyle('Date', fontSize=10, alignment=TA_RIGHT)
    story.append(Paragraph(f"Alger le : {datetime.now().strftime('%d/%m/%Y')}", style_date))
    story.append(Spacer(1, 1.5*cm))

    # Titre
    style_title = ParagraphStyle(
        'Title',
        fontSize=18,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#ec4899'),
        spaceAfter=20
    )
    story.append(Paragraph("CONGÉ DE MATERNITÉ", style_title))
    story.append(Spacer(1, 1.5*cm))

    # Corps
    style_body = ParagraphStyle('Body', fontSize=12, leading=24, alignment=TA_LEFT)
    
    gyneco = dossier.get('gyneco_name', 'Dr ....................')
    patiente = dossier.get('patiente', '...........................').upper()
    date_acc = datetime.strptime(str(dossier.get('date_accouchement')), '%Y-%m-%d').strftime('%d/%m/%Y')

    texte = f"""
    Je soussigné(e), <b>Dr {gyneco}</b><br/><br/>
    Certifie que Mme <b>{patiente}</b><br/>
    Ayant accouché le <b>{date_acc}</b><br/><br/>
    Nécessite un congé de maternité de <b>150 jours</b> (Cent cinquante jours)<br/>
    À compter de ce jour, sauf complications.<br/><br/>
    <font size=10>Ce certificat est délivré pour servir et valoir ce que de droit.</font>
    """
    story.append(Paragraph(texte, style_body))

    # Signature
    story.append(Spacer(1, 3*cm))
    style_sign = ParagraphStyle('Sign', fontSize=12, alignment=TA_RIGHT, fontName='Helvetica-Bold')
    story.append(Paragraph("Le Médecin", style_sign))

    create_footer(story, doc.width)

    doc.build(story)
    return buffer.getvalue(), {'patiente': patiente, 'date': date_acc}


# ============================================================================
# 4️⃣ COMPTE RENDU OPÉRATOIRE
# ============================================================================

def generer_compte_rendu_operatoire(dossier):
    """Génère le compte rendu opératoire selon le modèle exact"""
    from app.accouchements.accouchements import get_pg_connection, get_db_connection

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm
    )
    story = []

    # Styles
    styles = getSampleStyleSheet()
    style_normal = styles['Normal']
    style_normal.fontSize = 10
    style_normal.leading = 12

    style_bold = ParagraphStyle('Bold', parent=style_normal, fontName='Helvetica-Bold')
    style_center = ParagraphStyle('Center', parent=style_bold, alignment=TA_CENTER, fontSize=14)
    style_section = ParagraphStyle('Section', parent=style_bold, fontSize=11, spaceBefore=6, spaceAfter=6,
                                   textColor=colors.HexColor('#450A54'))  # Violet Inaya

    # 1. En-tête
    create_header(story)

    # 2. Titre
    story.append(Paragraph("<u>COMPTE RENDU OPÉRATOIRE - CÉSARIENNE</u>", style_center))
    story.append(Spacer(1, 0.5 * cm))

    # 3. Identification Patient (Tableau complet)
    patiente = dossier.get('patiente', '').upper()
    nom_epoux = dossier.get('nom_epoux', '')
    if nom_epoux:
        patiente += f" épse {nom_epoux.upper()}"

    age = f"{dossier.get('age_patiente') or '...'} ans"
    gs = f"{dossier.get('groupage_sanguin') or '...'} {dossier.get('rhesus') or ''}"
    parite = dossier.get('parite') or 'G...P...'
    date_op = format_date(dossier.get('date_accouchement'))
    heure_op = str(dossier.get('heure_accouchement') or '..:..')[:5]

    data_ident = [
        [Paragraph(f"<b>PATIENTE :</b> {patiente}", style_normal), Paragraph(f"<b>AGE :</b> {age}", style_normal)],
        [Paragraph(f"<b>GROUPE SANGUIN :</b> {gs}", style_normal), Paragraph(f"<b>PARITÉ :</b> {parite}", style_normal)],
        [Paragraph(f"<b>DATE :</b> {date_op}", style_normal), Paragraph(f"<b>HEURE :</b> {heure_op}", style_normal)]
    ]

    t_ident = Table(data_ident, colWidths=[9 * cm, 9 * cm])
    t_ident.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_ident)
    story.append(Spacer(1, 0.5 * cm))

    # 4. Équipe Médicale
    gyneco = dossier.get('gyneco_name', 'Dr ....................')
    
    # Récupération Réanimateur (Anesthésiste)
    reanimateur = "Dr ...................."
    id_dossier = dossier.get('id_dossier')
    if id_dossier:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Chercher le médecin intervenant type 'MEDECIN' (Réanimateur) lié à l'anesthésie
                cursor.execute("""
                    SELECT CONCAT(p.prenom, ' ', p.nom) as nom_complet
                    FROM accouchement_dossier_anesthesie da
                    JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
                    WHERE da.id_dossier = %s AND p.type_personnel = 'MEDECIN'
                    LIMIT 1
                """, (id_dossier,))
                res = cursor.fetchone()
                if res and res['nom_complet']:
                    reanimateur = f"Dr {res['nom_complet']}"
        except Exception as e:
            print(f"Erreur recuperation reanimateur: {e}")
        finally:
            conn.close()

    data_equipe = [
        [Paragraph(f"<b>OPÉRATEUR :</b> {gyneco}", style_normal), Paragraph(f"<b>RÉANIMATEUR :</b> {reanimateur}", style_normal)],
        [Paragraph("<b>AIDE OPÉRATOIRE :</b> ....................", style_normal), Paragraph("<b>PÉDIATRE :</b> ....................", style_normal)]
    ]

    t_equipe = Table(data_equipe, colWidths=[9 * cm, 9 * cm])
    t_equipe.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_equipe)
    story.append(Spacer(1, 0.5 * cm))

    # 5. Diagnostic & Intervention
    indication = dossier.get('indication_cesarienne', '........................................')
    type_cesarienne = dossier.get('type_cesarienne', 'CÉSARIENNE')
    
    story.append(Paragraph(f"<b>DIAGNOSTIC PRÉ-OPÉRATOIRE :</b> {indication}", style_normal))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(f"<b>INTERVENTION :</b> {type_cesarienne}", style_normal))
    story.append(Spacer(1, 0.5 * cm))

    # 6. Détails de l'intervention
    story.append(Paragraph("<u>PROTOCOLE OPÉRATOIRE :</u>", style_section))

    # Champs techniques avec valeurs par défaut ou placeholders
    incision = "Incision de Pfannenstiel" 
    hysterotomie = "Segmentaire transversale"
    
    # Données bébé
    sexe = dossier.get('sexe_bebe', '.........')
    poids = f"{int(dossier.get('poids_naissance') * 1000)}g" if dossier.get('poids_naissance') else ".......g"
    apgar = dossier.get('apgar_score', '../10')
    extraction_txt = f"Extraction d'un nouveau-né de sexe <b>{sexe}</b>, poids <b>{poids}</b>, Apgar <b>{apgar}</b>. Cri immédiat."

    delivrance = "Délivrance artificielle complète."
    revision = "Révision utérine effectuée, vacuité vérifiée. Annexes explorées et saines."
    
    # Fermeture (récupéré ou placeholder)
    fermeture = dossier.get('fermeture') or "Fermeture utérine en 2 plans (surjet + points séparés). Péritonisation. Fermeture pariétale plan par plan. Surjet intradermique."
    
    # Hémostase & Compresses (Nouveaux champs)
    hemostase_txt = dossier.get('hemostases') or "Hémostase soigneuse et satisfaisante."
    compresses_txt = dossier.get('compte_compresses') or "Compte des compresses et champs correct."

    data_proto = [
        [Paragraph("<b>INCISION :</b>", style_bold), Paragraph(incision, style_normal)],
        [Paragraph("<b>HYSTÉROTOMIE :</b>", style_bold), Paragraph(hysterotomie, style_normal)],
        [Paragraph("<b>EXTRACTION :</b>", style_bold), Paragraph(extraction_txt, style_normal)],
        [Paragraph("<b>DÉLIVRANCE :</b>", style_bold), Paragraph(delivrance, style_normal)],
        [Paragraph("<b>RÉVISION :</b>", style_bold), Paragraph(revision, style_normal)],
        [Paragraph("<b>FERMETURE :</b>", style_bold), Paragraph(fermeture, style_normal)],
        [Paragraph("<b>HÉMOSTASE :</b>", style_bold), Paragraph(hemostase_txt, style_normal)],
        [Paragraph("<b>COMPT. COMPRESSES :</b>", style_bold), Paragraph(compresses_txt, style_normal)],
    ]

    t_proto = Table(data_proto, colWidths=[4 * cm, 14 * cm])
    t_proto.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_proto)
    story.append(Spacer(1, 0.5 * cm))

    # 7. Données Post-Opératoires Immédiates (Nouveau Tableau)
    story.append(Paragraph("<u>SURVEILLANCE POST-OPÉRATOIRE IMMÉDIATE (SDPI) :</u>", style_section))

    ta = dossier.get('ta_postop') or "....... cmHg"
    diurese = dossier.get('diurese_postop') or "....... cc"
    reveil = dossier.get('reveil_postop') or "Satisfaisant"
    
    data_postop = [
        [Paragraph(f"<b>TA :</b> {ta}", style_normal), Paragraph(f"<b>DIURÈSE :</b> {diurese}", style_normal), Paragraph(f"<b>RÉVEIL :</b> {reveil}", style_normal)]
    ]

    t_postop = Table(data_postop, colWidths=[6 * cm, 6 * cm, 6 * cm])
    t_postop.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_postop)

    # 8. Signature
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("<u>L'OPÉRATEUR</u>", ParagraphStyle('SignTitle', parent=style_bold, alignment=TA_RIGHT)))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(f"Dr {gyneco}", ParagraphStyle('SignName', parent=style_normal, alignment=TA_RIGHT)))

    # Footer
    create_footer(story, doc.width)

    doc.build(story)
    return buffer.getvalue(), {'patiente': patiente, 'date': date_op}