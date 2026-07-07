# app/prestation_location_bloc/export_location.py
import base64
import io
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, List, Optional, Tuple

from flask import flash, make_response, redirect, request, send_file, url_for
from num2words import num2words
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app import app, get_db_connection
from app.error import handle_errors
from app.prestation_location_bloc.location_bloc import to_decimal
from app.utils.utiles import login_required


def format_currency(value):
    """Formate une valeur en devise"""

    try:
        if isinstance(value, Decimal):
            return f"{float( value ):,.2f} DA"

        return f"{float( value ):,.2f} DA"

    except:
        return "0.00 DA"


def format_date(date_value):
    """Formate une date"""

    if date_value:
        if isinstance(date_value, str):
            return date_value

        return date_value.strftime("%d/%m/%Y")

    return "N/A"


@app.route("/location_bloc/export")
@login_required
@handle_errors()
def location_bloc_export():
    """
    Export Excel avec formatage professionnel
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer les mêmes filtres que la liste
        date_debut = request.args.get("date_debut")
        date_fin = request.args.get("date_fin")
        doctor_filter = request.args.get("doctor", "all")
        bloc_filter = request.args.get("bloc", "all")
        type_filter = request.args.get("type", "all")
        statut_filter = request.args.get("statut", "all")
        q = request.args.get("q", "").strip()

        # Tri
        sort_field = request.args.get("sort_field", "")
        sort_order = request.args.get("sort_order", "desc")

        # Construire la requête (identique à location_bloc_list)
        query = """
                SELECT d.*,
                       doc.first_name,
                       doc.last_name,
                       b.name_bloc,
                       f.name_forfait
                FROM location_bloc_dossier_patient d
                         LEFT JOIN doctors doc ON d.id_doctor = doc.id
                         LEFT JOIN bloc b ON d.id_bloc = b.id_bloc
                         LEFT JOIN location_bloc_forfait_actes f ON d.forfait_id = f.id_forfait
                WHERE 1 = 1 \
                """
        params = {}

        if date_debut:
            query += " AND d.location_date >= %(date_debut)s"
            params["date_debut"] = date_debut
        if date_fin:
            query += " AND d.location_date <= %(date_fin)s"
            params["date_fin"] = date_fin
        if doctor_filter != "all":
            query += " AND d.id_doctor = %(doctor)s"
            params["doctor"] = doctor_filter
        if bloc_filter != "all":
            query += " AND d.id_bloc = %(bloc)s"
            params["bloc"] = bloc_filter
        if type_filter != "all":
            query += " AND d.type_tarification = %(type)s"
            params["type"] = type_filter
        if statut_filter != "all":
            query += " AND d.statut_paiement = %(statut)s"
            params["statut"] = statut_filter
        if q:
            query += " AND (d.patient LIKE %(q)s OR d.nom_acte LIKE %(q)s)"
            params["q"] = f"%{q}%"

        # Appliquer le tri
        order_by_map = {
            "location_date": "d.location_date",
            "prix_total": "d.prix_total",
            "duree_reelle": "d.duree_reelle",
            "doctor_name": "doc.last_name",
            "patient": "d.patient",
            "bloc": "b.name_bloc",
            "statut": "d.statut_paiement",
        }

        if sort_field and sort_field in order_by_map:
            order_column = order_by_map[sort_field]
            order_direction = "ASC" if sort_order == "asc" else "DESC"
            query += f" ORDER BY {order_column} {order_direction}, d.id_dossier DESC"
        else:
            query += " ORDER BY d.location_date DESC, d.id_dossier DESC"

        cursor.execute(query, params)
        dossiers = cursor.fetchall()

        # Créer le workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Locations Bloc"

        # Styles
        header_fill = PatternFill(
            start_color="667eea", end_color="667eea", fill_type="solid"
        )
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        # En-têtes
        headers = [
            "N° Dossier",
            "Date",
            "Heure",
            "Patient",
            "Acte",
            "Médecin",
            "Bloc",
            "Type",
            "Durée (min)",
            "Prix Total (DA)",
            "Statut",
        ]

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

        # Données
        for row_idx, dossier in enumerate(dossiers, 2):
            # Formatage de l'heure
            heure = ""
            if dossier.get("heure_operation"):
                heure_val = dossier["heure_operation"]
                if isinstance(heure_val, str):
                    heure = heure_val
                elif hasattr(heure_val, "seconds"):  # timedelta
                    hours = heure_val.seconds // 3600
                    minutes = (heure_val.seconds % 3600) // 60
                    heure = f"{hours:02d}:{minutes:02d}"

            row_data = [
                f"D-{dossier.get( 'id_dossier', 0 ):05d}",
                (
                    dossier["location_date"].strftime("%d/%m/%Y")
                    if dossier.get("location_date")
                    else ""
                ),
                heure,
                dossier.get("patient", ""),
                dossier.get("nom_acte", ""),
                f"Dr. {dossier.get( 'first_name', '' )} {dossier.get( 'last_name', '' )}",
                dossier.get("name_bloc", ""),
                dossier.get("type_tarification", ""),
                dossier.get("duree_reelle", 0) or 0,
                float(dossier.get("prix_total", 0) or 0),
                dossier.get("statut_paiement", ""),
            ]

            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = border

                # Alignement
                if col_idx in [9, 10]:  # Durée et Prix
                    cell.alignment = Alignment(horizontal="right")
                else:
                    cell.alignment = Alignment(horizontal="left")

                # Format nombre pour le prix
                if col_idx == 10:
                    cell.number_format = "#,##0.00"

        # Ligne de total
        total_row = len(dossiers) + 2
        total_amount = sum(float(d.get("prix_total", 0) or 0) for d in dossiers)

        ws.cell(row=total_row, column=9, value="TOTAL:").font = Font(bold=True)
        total_cell = ws.cell(row=total_row, column=10, value=total_amount)
        total_cell.font = Font(bold=True, color="0000FF")
        total_cell.number_format = "#,##0.00"

        # Ajuster les largeurs de colonnes
        column_widths = [12, 12, 10, 20, 30, 20, 15, 10, 12, 15, 15]
        for col, width in enumerate(column_widths, 1):
            col_letter = chr(64 + col)  # A, B, C, etc.
            ws.column_dimensions[col_letter].width = width

        # Sauvegarder dans un buffer
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # Nom du fichier avec date
        from datetime import datetime

        filename = f"locations_bloc_{datetime.now().strftime( '%Y%m%d_%H%M%S' )}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        app.logger.error(f"Erreur export Excel: {str( e )}")
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors de l'export: {str( e )}", "danger")
        return redirect(url_for("location_bloc_list"))

    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if connection:
            try:
                connection.close()
            except:
                pass


# ============================================================================
# CLASSE PDFStoryBuilder - GESTION INTELLIGENTE DES PAGES
# ============================================================================


class PDFStoryBuilder:
    """
    Helper optimisé pour la gestion automatique des sauts de page
    """

    def __init__(self, doc):
        self.doc = doc
        self.story = []
        page_width, page_height = doc.pagesize
        self.available_width = page_width - doc.leftMargin - doc.rightMargin
        self.available_height = page_height - doc.topMargin - doc.bottomMargin
        self.remaining = self.available_height

    def _measure(self, flow) -> float:
        """Mesure la hauteur d'un flowable"""
        try:
            w, h = flow.wrap(self.available_width, self.available_height)
            return h
        except Exception:
            return 50  # Estimation conservative

    def add(self, flow, keep_together: bool = False):
        """
        Ajoute un flowable avec gestion automatique des sauts de page

        Args:
            flow: Flowable à ajouter
            keep_together: Si True, force le flowable sur une nouvelle page si nécessaire
        """
        if isinstance(flow, (list, tuple)):
            for sub in flow:
                self.add(sub, keep_together)
            return self

        h = self._measure(flow)

        # Flowable trop grand pour une page
        if h > self.available_height:
            self.story.append(flow)
            self.remaining = 0
            return self

        # Pas assez de place et keep_together activé
        if keep_together and h > self.remaining:
            self.story.append(PageBreak())
            self.remaining = self.available_height

        # Pas assez de place sans keep_together
        elif h > self.remaining:
            self.story.append(PageBreak())
            self.remaining = self.available_height

        self.story.append(flow)
        self.remaining -= h
        return self

    def add_page_break(self):
        """Force un saut de page"""
        self.story.append(PageBreak())
        self.remaining = self.available_height
        return self

    @staticmethod
    def _add_page_number(canvas, doc):
        """Ajoute numérotation et informations de pied de page"""
        canvas.saveState()
        canvas.setFont("Helvetica", 7)

        # Numéro de page (en haut à droite)
        page_txt = f"Page {doc.page}"
        canvas.drawRightString(
            doc.pagesize[0] - doc.rightMargin, doc.bottomMargin / 2, page_txt
        )

        # Informations du dossier (en bas)
        gen_dt = getattr(doc, "generated_at", None)
        dossier_id = getattr(doc, "dossier_id", None)
        dossier = getattr(doc, "_dossier_data", {})

        if gen_dt and dossier_id:
            # Date de génération (gauche)
            canvas.drawString(
                doc.leftMargin,
                doc.bottomMargin / 2 - 6,
                f"Généré le {gen_dt.strftime( '%d/%m/%Y à %H:%M' )} - "
                f"Créé le: {format_date( dossier.get( 'date_creation' ) )} "
                f"Par: {safe_get( dossier, 'cree_par_nom', 'N/A' )}",
            )

            # Numéro dossier (droite)
            canvas.drawRightString(
                doc.pagesize[0] - doc.rightMargin,
                doc.bottomMargin / 2 - 6,
                f"D-{dossier_id:05d}",
            )

        canvas.restoreState()

    def build(self):
        """Construit le PDF final"""
        # Nettoyage des PageBreak en fin de document
        while self.story and isinstance(self.story[-1], PageBreak):
            self.story.pop()

        self.doc.build(
            self.story,
            onFirstPage=self._add_page_number,
            onLaterPages=self._add_page_number,
        )


# ============================================================================
# STYLES OPTIMISÉS
# ============================================================================


def create_pdf_styles():
    """Crée et retourne tous les styles PDF utilisés"""
    styles = getSampleStyleSheet()

    custom_styles = {
        "title": ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
            fontName="Helvetica-Bold",
            spaceAfter=4,
            spaceBefore=0,
        ),
        "subtitle": ParagraphStyle(
            "CustomSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4b5563"),
            fontName="Helvetica-Bold",
            spaceAfter=6,
        ),
        "header": ParagraphStyle(
            "CustomHeader",
            parent=styles["Heading2"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=3,
            spaceBefore=6,
            borderPadding=2,
        ),
        "subheader": ParagraphStyle(
            "CustomSubheader",
            parent=styles["Heading3"],
            fontSize=9,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#374151"),
            spaceAfter=2,
            spaceBefore=3,
        ),
        "normal": ParagraphStyle(
            "CustomNormal", parent=styles["Normal"], fontSize=8, leading=10
        ),
        "small": ParagraphStyle(
            "CustomSmall",
            parent=styles["Normal"],
            fontSize=7,
            leading=8,
            textColor=colors.HexColor("#6b7280"),
        ),
        "bold": ParagraphStyle(
            "CustomBold",
            parent=styles["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            leading=10,
        ),
        "info": ParagraphStyle(
            "CustomInfo",
            parent=styles["Normal"],
            fontSize=7,
            fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#3b82f6"),
            leading=9,
        ),
    }

    return custom_styles


def safe_get(dictionary: dict, key: str, default: Any = "N/A") -> Any:
    """Récupération sécurisée d'une valeur"""
    value = dictionary.get(key)
    return value if value is not None else default


# ============================================================================
# STYLES DE TABLEAUX RÉUTILISABLES
# ============================================================================


def get_table_style(header_color="#6366f1", alternate_rows=True, num_rows=None):
    """Retourne un style de tableau standard avec gestion des tables petites"""
    styles_list = [
        # En-tête
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    # Ajouter les styles de corps seulement s'il y a au moins 2 lignes (en-tête + données)
    if num_rows is None or num_rows > 1:
        styles_list.extend(
            [
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    (
                        [colors.white, colors.HexColor("#f9fafb")]
                        if alternate_rows
                        else [colors.white]
                    ),
                ),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ]
        )

    style = TableStyle(styles_list)
    return style


def create_info_table(data: List[List[str]], col_widths: List[float]) -> Table:
    """Crée un tableau d'informations stylisé avec gestion des erreurs"""
    table = Table(data, colWidths=col_widths)

    # Construire les styles en fonction du nombre de lignes
    styles_list = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]

    # Ajouter les styles de colonnes seulement s'il y a au moins une ligne
    if len(data) > 0:
        styles_list.extend(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f4f6")),
            ]
        )

    table.setStyle(TableStyle(styles_list))
    return table


# ============================================================================
# SECTIONS DU PDF
# ============================================================================


def add_header_section(builder, dossier: dict, styles: dict, qr_b64: str = None):
    """Ajoute l'en-tête du document avec logo à gauche et QR code à droite"""
    # Construire la ligne d'en-tête : Logo | Titre | QR Code
    header_elements = []

    # Logo
    logo_flow = None
    try:
        logo_flow = Image(
            "app/static/images/entet_inaya.png", width=10 * cm, height=3 * cm
        )
    except:
        logo_flow = Paragraph("", styles["normal"])

    # QR Code (si disponible)
    qr_flow = None
    if qr_b64:
        try:
            qr_buf = BytesIO(base64.b64decode(qr_b64))
            qr_flow = Image(qr_buf, width=2.5 * cm, height=2.5 * cm)
        except:
            qr_flow = Paragraph("", styles["normal"])

    if qr_flow:
        # Tableau : Logo à gauche, QR à droite
        header_table = Table(
            [[logo_flow, qr_flow]], colWidths=[builder.doc.width - 3 * cm, 3 * cm]
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        builder.add(header_table)
    else:
        if logo_flow:
            builder.add(logo_flow)

    builder.add(
        Paragraph(
            f"Dossier Médical N° D-{safe_get( dossier, 'id_dossier', 0 ):05d}",
            styles["subtitle"],
        )
    )

    # Ligne de séparation
    builder.add(Spacer(1, 0.4 * cm))
    separator = Table([[""]], colWidths=[builder.doc.width])
    separator.setStyle(
        TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#6366f1"))])
    )
    builder.add(separator)
    builder.add(Spacer(1, 0.4 * cm))


def add_general_info(builder, dossier: dict, styles: dict):
    """Ajoute les informations générales"""
    info_data = [
        [
            "Patient:",
            safe_get(dossier, "patient"),
            "Médecin:",
            safe_get(dossier, "doctor_name"),
        ],
        [
            "Date:",
            format_date(dossier.get("location_date")),
            "Heure:",
            safe_get(dossier, "heure_operation"),
        ],
        [
            "Intervention:",
            safe_get(dossier, "nom_acte"),
            "Durée:",
            f"{safe_get( dossier, 'duree_reelle', 0 )} min",
        ],
    ]
    info_table = create_info_table(info_data, [2.5 * cm, 6 * cm, 2.5 * cm, 6 * cm])
    builder.add(info_table, keep_together=True)
    builder.add(Spacer(1, 0.4 * cm))


def add_tarification(builder, dossier: dict, styles: dict):
    """Ajoute la section tarification"""
    builder.add(Paragraph("1. TARIFICATION", styles["header"]))

    tarif_data = [
        [
            "Bloc:",
            safe_get(dossier, "name_bloc"),
            "Type:",
            "Forfait" if dossier.get("type_tarification") == "FORFAIT" else "Durée",
        ],
        [
            "Prix base:",
            format_currency(dossier.get("prix_bloc", 0)),
            "Suppl. durée:",
            format_currency(dossier.get("prix_supplement_duree", 0)),
        ],
    ]

    if dossier.get("type_tarification") == "FORFAIT":
        tarif_data.append(
            [
                "Forfait:",
                safe_get(dossier, "name_forfait"),
                "Nuitées incl.:",
                f"{safe_get( dossier, 'forfait_nbr_nuit', 0 )}",
            ]
        )

    tarif_table = create_info_table(tarif_data, [3 * cm, 5.5 * cm, 3 * cm, 5.5 * cm])
    builder.add(tarif_table, keep_together=True)
    builder.add(Spacer(1, 0.4 * cm))


def add_products_section(builder, produits_groupes: dict, styles: dict):
    """Ajoute la section produits (optimisée)"""
    # Filtrer les produits avec écart != 0
    produits_inclus_avec_ecart = [
        prod
        for source in ("BLOC", "FORFAIT")
        for prod in produits_groupes.get(source, [])
        if prod.get("ecart", 0) != 0
    ]

    if not produits_inclus_avec_ecart and not produits_groupes.get("SUPPLEMENTAIRE"):
        return

    builder.add(Paragraph("2. PRODUITS", styles["header"]))

    # Produits inclus avec dépassements
    if produits_inclus_avec_ecart:
        builder.add(
            Paragraph("2.1 Produits inclus (dépassements)", styles["subheader"])
        )

        prod_data = [["Produit", "Incl.", "Util.", "Écart", "P.U.", "Suppl."]]
        for prod in produits_inclus_avec_ecart:
            ecart = prod.get("ecart", 0)
            prod_data.append(
                [
                    safe_get(prod, "produit_nom")[:35],
                    str(int(prod.get("qte_incluse", 0))),
                    str(int(prod.get("qte_utilisee", 0))),
                    f"+{ecart}" if ecart > 0 else str(ecart),
                    format_currency(prod.get("prix_unitaire", 0)),
                    format_currency(prod.get("prix_supplement", 0)),
                ]
            )

        prod_table = Table(
            prod_data,
            colWidths=[6 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 2.5 * cm, 2.5 * cm],
        )
        prod_table.setStyle(get_table_style("#f59e0b", num_rows=len(prod_data)))
        prod_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 1), (3, -1), "CENTER"),
                    ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        builder.add(prod_table, keep_together=True)
        builder.add(Spacer(1, 0.3 * cm))

    # Produits supplémentaires
    if produits_groupes.get("SUPPLEMENTAIRE"):
        label = (
            "2.2 Produits supplémentaires"
            if produits_inclus_avec_ecart
            else "2.1 Produits supplémentaires"
        )
        builder.add(Paragraph(label, styles["subheader"]))

        prod_supp_data = [["Produit", "Qté", "P.U.", "Total"]]
        for prod in produits_groupes["SUPPLEMENTAIRE"]:
            total = prod.get("qte_utilisee", 0) * prod.get("prix_unitaire", 0)
            prod_supp_data.append(
                [
                    safe_get(prod, "produit_nom")[:40],
                    str(int(prod.get("qte_utilisee", 0))),
                    format_currency(prod.get("prix_unitaire", 0)),
                    format_currency(total),
                ]
            )

        prod_supp_table = Table(
            prod_supp_data, colWidths=[8 * cm, 2 * cm, 3 * cm, 3 * cm]
        )
        prod_supp_table.setStyle(
            get_table_style("#10b981", num_rows=len(prod_supp_data))
        )
        prod_supp_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        builder.add(prod_supp_table, keep_together=True)

    builder.add(Spacer(1, 0.4 * cm))


def add_acts_section(builder, actes_groupes: dict, styles: dict):
    """Ajoute la section actes (optimisée)"""
    actes_inclus_avec_ecart = [
        acte for acte in actes_groupes.get("FORFAIT", []) if acte.get("ecart", 0) != 0
    ]

    if not actes_inclus_avec_ecart and not actes_groupes.get("SUPPLEMENTAIRE"):
        return

    builder.add(Paragraph("3. ACTES", styles["header"]))

    # Actes inclus avec dépassements
    if actes_inclus_avec_ecart:
        builder.add(
            Paragraph("3.1 Actes inclus (dépassements forfait)", styles["subheader"])
        )

        actes_data = [["Acte", "Incl.", "Util.", "Écart", "P.U.", "Suppl."]]
        for acte in actes_inclus_avec_ecart:
            ecart = acte.get("ecart", 0)
            actes_data.append(
                [
                    safe_get(acte, "nom_acte")[:35],
                    str(int(acte.get("qte_incluse", 0))),
                    str(int(acte.get("qte_utilisee", 0))),
                    f"+{ecart}" if ecart > 0 else str(ecart),
                    format_currency(acte.get("prix_unitaire", 0)),
                    format_currency(acte.get("prix_supplement", 0)),
                ]
            )

        actes_table = Table(
            actes_data,
            colWidths=[6 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 2.5 * cm, 2.5 * cm],
        )
        actes_table.setStyle(get_table_style("#f59e0b", num_rows=len(actes_data)))
        actes_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 1), (3, -1), "CENTER"),
                    ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        builder.add(actes_table, keep_together=True)
        builder.add(Spacer(1, 0.3 * cm))

    # Actes supplémentaires
    if actes_groupes.get("SUPPLEMENTAIRE"):
        label = (
            "3.2 Actes supplémentaires"
            if actes_inclus_avec_ecart
            else "3.1 Actes supplémentaires"
        )
        builder.add(Paragraph(label, styles["subheader"]))

        actes_supp_data = [["Acte", "Qté", "P.U.", "Total"]]
        for acte in actes_groupes["SUPPLEMENTAIRE"]:
            total = acte.get("qte_utilisee", 0) * acte.get("prix_unitaire", 0)
            actes_supp_data.append(
                [
                    safe_get(acte, "nom_acte")[:40],
                    str(int(acte.get("qte_utilisee", 0))),
                    format_currency(acte.get("prix_unitaire", 0)),
                    format_currency(total),
                ]
            )

        actes_supp_table = Table(
            actes_supp_data, colWidths=[8 * cm, 2 * cm, 3 * cm, 3 * cm]
        )
        actes_supp_table.setStyle(
            get_table_style("#10b981", num_rows=len(actes_supp_data))
        )
        actes_supp_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        builder.add(actes_supp_table, keep_together=True)

    builder.add(Spacer(1, 0.4 * cm))


def add_hospitalization_section(
    builder, nuitees: List[dict], dossier: dict, styles: dict
):
    """Ajoute la section hospitalisation"""
    if not nuitees:
        return

    builder.add(Paragraph("4. HOSPITALISATION", styles["header"]))

    # Récapitulatif global
    total_nuitees = sum(n.get("nombre_nuitees", 0) for n in nuitees)
    total_prix = sum(n.get("prix_total", 0) for n in nuitees)
    nuits_gratuites = sum(1 for n in nuitees if n.get("nuit_pre_op_gratuite"))

    recap_data = [
        ["Total nuitées:", str(total_nuitees), "Gratuites:", str(nuits_gratuites)],
        [
            "Incluses:",
            str(safe_get(dossier, "forfait_nbr_nuit", 0)),
            "Prix total:",
            format_currency(total_prix),
        ],
    ]
    recap_table = create_info_table(recap_data, [3.5 * cm, 3 * cm, 3.5 * cm, 3.5 * cm])
    builder.add(recap_table, keep_together=True)
    builder.add(Spacer(1, 0.3 * cm))

    # Détail par hospitalisation
    for i, nuitee in enumerate(nuitees):
        detail_data = [
            [f"Hospitalisation #{i + 1}", ""],
            ["Type:", safe_get(nuitee, "type_chambre_nom")],
            [
                "Dates:",
                f"{format_date( nuitee.get( 'date_entree' ) )} → {format_date( nuitee.get( 'date_sortie' ) )}",
            ],
            ["Nuitées:", str(safe_get(nuitee, "nombre_nuitees", 0))],
            ["Prix:", format_currency(nuitee.get("prix_total", 0))],
        ]

        if nuitee.get("nuit_pre_op_gratuite"):
            detail_data.append(["✓ Nuit pré-op gratuite", ""])

        detail_table = Table(
            detail_data, colWidths=[4 * cm, (builder.doc.width / 2) - 4 * cm]
        )
        detail_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("SPAN", (0, 0), (-1, 0)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 3),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                ]
            )
        )

        builder.add(detail_table, keep_together=True)
        if i < len(nuitees) - 1:
            builder.add(Spacer(1, 0.2 * cm))

    builder.add(Spacer(1, 0.4 * cm))


def add_explorations_section(builder, explorations: List[dict], styles: dict):
    """Ajoute la section explorations"""
    if not explorations:
        return

    builder.add(Paragraph("5. EXPLORATIONS", styles["header"]))

    exp_data = [["Type", "Nom", "Date", "Prix"]]
    total_exp = Decimal("0")

    type_map = {"IMAGERIE": "Imagerie", "LABORATOIRE": "Labo", "AUTRE": "Autre"}

    for exp in explorations:
        exp_type = type_map.get(exp.get("type_exploration", "AUTRE"), "Autre")
        exp_data.append(
            [
                exp_type,
                safe_get(exp, "nom_exploration")[:30],
                format_date(exp.get("date_exploration")),
                format_currency(exp.get("prix", 0)),
            ]
        )
        total_exp += Decimal(str(exp.get("prix", 0)))

    exp_data.append(["", "", "TOTAL:", format_currency(total_exp)])

    exp_table = Table(exp_data, colWidths=[2.5 * cm, 7 * cm, 3 * cm, 3 * cm])
    exp_table.setStyle(get_table_style("#3b82f6", num_rows=len(exp_data)))
    exp_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (2, -1), (-1, -1), 1, colors.black),
            ]
        )
    )

    builder.add(exp_table, keep_together=True)
    builder.add(Spacer(1, 0.4 * cm))


def add_anesthesia_section(
    builder, nom_acte: str, tarif_forfaitaire: float, styles: dict
):
    """Ajoute la section anesthésie simplifiée (acte + tarif seulement)"""

    builder.add(Paragraph("6. ANESTHÉSIE", styles["header"]))

    # Créer un tableau simple avec l'acte et le tarif
    anesth_data = [
        ["Acte:", nom_acte],
        ["Tarif forfaitaire:", format_currency(tarif_forfaitaire)],
    ]

    anesth_table = Table(anesth_data, colWidths=[4 * cm, 10 * cm])
    anesth_table.setStyle(
        TableStyle(
            [
                # Style général
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 5),
                # Style de la première colonne (labels)
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f7ff")),
                # Style de la deuxième colonne (valeurs)
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("ALIGN", (1, 1), (1, 1), "RIGHT"),  # Aligner le tarif à droite
            ]
        )
    )

    builder.add(anesth_table, keep_together=True)
    builder.add(Spacer(1, 0.4 * cm))


def add_financial_summary(
    builder,
    dossier: dict,
    prix_produits_supplementaires: float,
    prix_actes_supplementaires: float,
    tarif_forfaitaire_anesthesie: float,
    styles: dict,
):
    """Ajoute le récapitulatif financier"""

    builder.add(Paragraph("7. RÉCAPITULATIF FINANCIER", styles["header"]))

    recap_data = []

    def add_if_positive(label, value):
        if value and value > 0:
            recap_data.append([label, format_currency(value)])

    # Lignes conditionnelles (> 0)
    add_if_positive("Prix bloc/forfait:", dossier.get("prix_bloc", 0))
    add_if_positive("Supplément durée:", dossier.get("prix_supplement_duree", 0))
    add_if_positive("Suppléments produits:", prix_produits_supplementaires)
    add_if_positive("Suppléments actes:", prix_actes_supplementaires)
    add_if_positive("Nuitées:", dossier.get("prix_nuitees", 0))
    add_if_positive("Explorations:", dossier.get("prix_explorations", 0))
    add_if_positive("Anesthésie:", tarif_forfaitaire_anesthesie)
    # Séparateur
    recap_data.append(["", ""])

    # Totaux (toujours affichés)
    recap_data.extend(
        [
            ["TOTAL:", format_currency(dossier.get("prix_total", 0))],
            ["Payé caisse:", format_currency(dossier.get("montant_paye_caisse", 0))],
            ["DIFFÉRENCE:", format_currency(dossier.get("difference_paiement", 0))],
        ]
    )

    recap_table = Table(recap_data, colWidths=[11 * cm, 5.5 * cm])
    recap_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -4), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, -3), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -3), (-1, -1), 11),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -3), (-1, -3), 2, colors.HexColor("#6366f1")),
                ("LINEABOVE", (0, -1), (-1, -1), 2, colors.HexColor("#6366f1")),
                ("BOX", (0, -3), (-1, -1), 1.5, colors.HexColor("#6366f1")),
                ("BACKGROUND", (0, -3), (-1, -3), colors.HexColor("#dbeafe")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fee2e2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    builder.add(recap_table, keep_together=True)

    # Statut de paiement
    statut = dossier.get("statut_paiement")
    if statut:
        statut_map = {
            "COMPLEMENT_MEDECIN": "Complément médecin à percevoir",
            "SURPLUS_CLINIQUE": "Surplus à rembourser",
            "AUCUN_PAIEMENT": "Paiement équilibré",
        }
        builder.add(Spacer(1, 0.3 * cm))
        builder.add(
            Paragraph(
                f"<b>Statut:</b> {statut_map.get( statut, statut )}", styles["bold"]
            )
        )

    builder.add(Spacer(1, 0.4 * cm))


def add_observations(builder, dossier: dict, styles: dict):
    """Ajoute les observations"""
    if not dossier.get("observations"):
        return

    builder.add(Paragraph("8. OBSERVATIONS", styles["header"]))
    builder.add(Paragraph(dossier.get("observations", ""), styles["normal"]))


# ============================================================================
# FONCTION PRINCIPALE DE GÉNÉRATION
# ============================================================================


def generate_dossier_pdf(
    dossier: dict,
    produits_groupes: dict,
    actes_groupes: dict,
    nuitees: List[dict],
    explorations: List[dict],
    prix_produits_supplementaires: float,
    prix_actes_supplementaires: float,
    nom_acte_anesthesie: Optional[str] = None,
    tarif_forfaitaire_anesthesie: float = 0,
    qr_b64: Optional[str] = None,
) -> bytes:
    """
    Génère le PDF du dossier - Version optimisée

    Args:
        dossier: Dictionnaire contenant les infos du dossier
        produits_groupes: Produits groupés par source
        actes_groupes: Actes groupés par source
        nuitees: Liste des nuitées
        explorations: Liste des explorations
        prix_produits_supplementaires: Total suppléments produits
        prix_actes_supplementaires: Total suppléments actes
        nom_acte_anesthesie: Nom de l'acte d'anesthésie (optionnel)
        tarif_forfaitaire_anesthesie: Tarif forfaitaire de l'acte d'anesthésie
    Returns:
        bytes: Données PDF
    """
    buffer = BytesIO()

    # Configuration du document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1 * cm,
        bottomMargin=1.5 * cm,
        title=f"Dossier D-{dossier.get( 'id_dossier', 0 ):05d}",
        author="Clinique INAYA",
    )

    # Métadonnées
    doc.dossier_id = dossier.get("id_dossier", 0)
    doc.generated_at = datetime.now()
    doc._dossier_data = dossier

    # Builder et styles
    builder = PDFStoryBuilder(doc)
    styles = create_pdf_styles()

    # Construction du document
    add_header_section(builder, dossier, styles, qr_b64=qr_b64)
    add_general_info(builder, dossier, styles)
    add_tarification(builder, dossier, styles)
    add_products_section(builder, produits_groupes, styles)
    add_acts_section(builder, actes_groupes, styles)
    add_hospitalization_section(builder, nuitees, dossier, styles)
    add_explorations_section(builder, explorations, styles)

    if nom_acte_anesthesie and tarif_forfaitaire_anesthesie > 0:
        add_anesthesia_section(
            builder, nom_acte_anesthesie, tarif_forfaitaire_anesthesie, styles
        )

    add_financial_summary(
        builder,
        dossier,
        prix_produits_supplementaires,
        prix_actes_supplementaires,
        tarif_forfaitaire_anesthesie,  # NOUVEAU
        styles,
    )
    add_observations(builder, dossier, styles)

    # Génération finale
    builder.build()

    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes


# ============================================================================
# FONCTION D'EXPORT (ROUTE FLASK)
# ============================================================================


def export_dossier_to_pdf_backend(
    dossier_id: int,
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Fonction principale pour exporter un dossier en PDF (optimisée)

    Args:
        dossier_id: ID du dossier à exporter

    Returns:
        tuple: (pdf_data, filename) ou (None, None) en cas d'erreur
    """
    from app import app, get_db_connection

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # ========== REQUÊTE OPTIMISÉE - DOSSIER ==========
        cursor.execute(
            """
            SELECT d.*,
                   CONCAT(pc.nom, ' ', pc.prenom)             as cree_par_nom,
                   CONCAT(doc.first_name, ' ', doc.last_name) as doctor_name,
                   b.name_bloc,
                   f.name_forfait,
                   f.nbr_nuit                                 as forfait_nbr_nuit
            FROM location_bloc_dossier_patient d
                     LEFT JOIN doctors doc ON d.id_doctor = doc.id
                     LEFT JOIN bloc b ON d.id_bloc = b.id_bloc
                     LEFT JOIN location_bloc_forfait_actes f ON d.forfait_id = f.id_forfait
                     LEFT JOIN personnel pc ON pc.id_personnel = d.created_by
            WHERE d.id_dossier = %s
            """,
            (dossier_id,),
        )

        dossier = cursor.fetchone()
        if not dossier:
            return None, None

        # ========== NETTOYAGE DES DONNÉES ==========
        dossier_safe = {
            key: (
                value
                if value is not None
                else (
                    0
                    if key
                    in [
                        "prix_bloc",
                        "prix_supplement_duree",
                        "prix_produits_supplementaires",
                        "prix_nuitees",
                        "prix_explorations",
                        "prix_anesthesie",
                        "prix_total",
                        "montant_paye_caisse",
                        "difference_paiement",
                        "duree_reelle",
                        "forfait_nbr_nuit",
                    ]
                    else ""
                )
            )
            for key, value in dossier.items()
        }

        # ========== REQUÊTES GROUPÉES POUR PERFORMANCE ==========
        # Produits
        cursor.execute(
            """
            SELECT dp.*,
                   p.description                                              as produit_nom,
                   COALESCE(dp.qte_utilisee, 0) - COALESCE(dp.qte_incluse, 0) as ecart,
                   GREATEST(0, COALESCE(dp.qte_utilisee, 0) - COALESCE(dp.qte_incluse, 0)) *
                   COALESCE(dp.prix_unitaire, 0)                              as prix_supplement
            FROM location_bloc_dossier_produits dp
                     JOIN produits p ON dp.id_produit = p.id_produit
            WHERE dp.id_dossier = %s
            ORDER BY dp.source_inclusion, p.description
            """,
            (dossier_id,),
        )
        produits = cursor.fetchall()

        # Actes
        cursor.execute(
            """
            SELECT da.*,
                   a.nom_acte,
                   COALESCE(da.qte_utilisee, 0) - COALESCE(da.qte_incluse, 0) as ecart,
                   GREATEST(0, COALESCE(da.qte_utilisee, 0) - COALESCE(da.qte_incluse, 0)) *
                   COALESCE(da.prix_unitaire, 0)                              as prix_supplement
            FROM location_bloc_dossier_patient_actes da
                     JOIN actes_supplement a ON da.id_acte = a.id_acte
            WHERE da.id_dossier = %s
            ORDER BY da.source_inclusion, a.nom_acte
            """,
            (dossier_id,),
        )
        actes = cursor.fetchall()

        # Nuitées
        cursor.execute(
            """
            SELECT dn.*, tc.nom_type as type_chambre_nom
            FROM location_bloc_dossier_nuitees dn
                     LEFT JOIN type_chambre tc ON dn.id_type_chambre = tc.id_type_chambre
            WHERE dn.id_dossier = %s
            ORDER BY dn.date_entree
            """,
            (dossier_id,),
        )
        nuitees = cursor.fetchall()

        # Explorations
        cursor.execute(
            """
            SELECT *
            FROM location_bloc_dossier_explorations
            WHERE id_dossier = %s
            ORDER BY date_exploration DESC
            """,
            (dossier_id,),
        )
        explorations = cursor.fetchall()

        # ========== NOUVEAU : ANESTHÉSIE ==========
        cursor.execute(
            """
            SELECT DISTINCT 
                   aa.nom_acte,
                aa.tarif_forfaitaire
            FROM location_bloc_dossier_anesthesie da
                     JOIN anesthesie_type_acte aa ON da.id_acte_anesthesie = aa.id_acte_anesthesie
            WHERE da.id_dossier = %s
            LIMIT 1
            """,
            (dossier_id,),
        )
        acte_anesthesie = cursor.fetchone()

        # Récupérer le nom et le tarif forfaitaire de l'acte d'anesthésie
        nom_acte_anesthesie = None
        tarif_forfaitaire_anesthesie = Decimal("0")
        if acte_anesthesie:
            nom_acte_anesthesie = acte_anesthesie["nom_acte"]
            tarif_forfaitaire_anesthesie = (
                to_decimal(acte_anesthesie["tarif_forfaitaire"])
                if acte_anesthesie["tarif_forfaitaire"]
                else Decimal("0")
            )
        # ========== GROUPEMENT DES DONNÉES ==========
        produits_groupes = {"BLOC": [], "FORFAIT": [], "SUPPLEMENTAIRE": []}
        for prod in produits:
            source = prod.get("source_inclusion", "SUPPLEMENTAIRE")
            if source in produits_groupes:
                produits_groupes[source].append(prod)

        actes_groupes = {"FORFAIT": [], "SUPPLEMENTAIRE": []}
        for acte in actes:
            source = acte.get("source_inclusion", "SUPPLEMENTAIRE")
            if source in actes_groupes:
                actes_groupes[source].append(acte)

        # ========== CALCULS ==========
        prix_produits_supplementaires = sum(
            p.get("prix_supplement", 0) for p in produits
        )
        prix_actes_supplementaires = sum(a.get("prix_supplement", 0) for a in actes)

        # ========== QR CODE ==========
        qr_b64 = None
        if dossier_safe.get("qr_uuid"):
            try:
                from app.utils.qr_utils import generer_qr_base64

                qr_b64 = generer_qr_base64("BLOC_EXTERNE", dossier_safe["qr_uuid"])
            except Exception:
                pass

        # ========== GÉNÉRATION PDF ==========
        pdf_data = generate_dossier_pdf(
            dossier_safe,
            produits_groupes,
            actes_groupes,
            nuitees,
            explorations,
            prix_produits_supplementaires,
            prix_actes_supplementaires,
            nom_acte_anesthesie,
            tarif_forfaitaire_anesthesie,
            qr_b64=qr_b64,
        )

        # ========== NOM DU FICHIER ==========
        patient_name = dossier_safe.get("patient", "Inconnu").replace(" ", "_")
        date_operation = format_date(dossier_safe.get("location_date"))
        filename = f"Dossier_D-{dossier_id:05d}_{patient_name}_{date_operation}.pdf"

        return pdf_data, filename

    except Exception as e:
        app.logger.error(f"Erreur génération PDF: {str( e )}")
        import traceback

        app.logger.error(traceback.format_exc())
        return None, None

    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if connection:
            try:
                connection.close()
            except:
                pass


@app.route("/location_bloc/<int:id_dossier>/pdf_download")
@login_required
def location_bloc_pdf_download(id_dossier):
    """Telechargement du dossier en PDF (backend)"""

    try:
        app.logger.info(f"Génération PDF pour dossier {id_dossier}")

        # Générer le PDF
        pdf_data, filename = export_dossier_to_pdf_backend(id_dossier)

        if not pdf_data:
            app.logger.error(f"PDF data est None pour dossier {id_dossier}")

            flash("Erreur lors de la génération du PDF", "danger")

            return redirect(url_for("location_bloc_detail", id_dossier=id_dossier))

        # Créer la réponse
        from flask import make_response

        response = make_response(pdf_data)

        response.headers["Content-Type"] = "application/pdf"

        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

        app.logger.info(f"PDF généré avec succès pour dossier {id_dossier}")

        return response

    except Exception as e:
        app.logger.error(
            f"Erreur lors du téléchargement du PDF pour dossier {id_dossier}: {str( e )}"
        )

        import traceback

        app.logger.error(traceback.format_exc())

        flash(f"Erreur lors de la génération du PDF: {str( e )}", "danger")

        return redirect(url_for("location_bloc_detail", id_dossier=id_dossier))


# ========================================================================
# EXPORT PDF BON
# ========================================================================


@app.route("/exporter_operation_pdf/<int:id_operation>")
@login_required
def exporter_operation_pdf(id_operation):
    """Exporter un bon en PDF"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupération de l'opération
        cursor.execute(
            """
            SELECT o.*,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   CONCAT(pc.nom, ' ', pc.prenom)         as created_by_name
            FROM location_bloc_operations_financieres_medecin o
                     LEFT JOIN doctors d ON o.id_doctor = d.id
                     LEFT JOIN personnel pc ON o.id_created_by = pc.id_personnel
            WHERE o.id = %s
            """,
            (id_operation,),
        )
        operation = cursor.fetchone()

        if not operation:
            flash("Opération non trouvée", "danger")
            return redirect(url_for("situation_medecin"))

        # Récupération des dossiers
        cursor.execute(
            """
            SELECT od.montant,
                   dp.patient,
                   dp.location_date,
                   dp.prix_total
            FROM location_bloc_operation_dossiers od
                     INNER JOIN location_bloc_dossier_patient dp ON od.id_dossier = dp.id_dossier
            WHERE od.id_operation = %s
            ORDER BY dp.location_date
            """,
            (id_operation,),
        )
        dossiers = cursor.fetchall()

        # Génération du PDF
        pdf_data = generer_bon_pdf(operation, dossiers)

        # Nom du fichier
        type_op = operation["type_operation"].lower()
        filename = f"Bon_{type_op}_{id_operation}_{operation[ 'doctor_name' ].replace( ' ', '_' )}.pdf"

        response = make_response(pdf_data)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response

    finally:
        cursor.close()
        connection.close()


def generer_bon_pdf(operation, dossiers):
    """Génère le PDF pour une opération"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )

    styles = getSampleStyleSheet()
    story = []

    # Logo
    try:
        logo = Image("app/static/images/entet_inaya.png", width=10 * cm, height=3 * cm)
        story.append(logo)
        story.append(Spacer(1, 8))
    except:
        pass

    # Déterminer le type
    type_operation = operation["type_operation"]
    couleurs = {
        "ENCAISSEMENT": colors.HexColor("#2e7d32"),
        "DECHARGE": colors.HexColor("#1976d2"),
        "COMPENSATION": colors.HexColor("#f57c00"),
    }
    couleur = couleurs.get(type_operation, colors.HexColor("#1976d2"))

    # Titre
    titres = {
        "ENCAISSEMENT": "BON D'ENCAISSEMENT",
        "DECHARGE": "BON DE DÉCHARGE",
        "COMPENSATION": "BON DE COMPENSATION",
    }
    titre = titres.get(type_operation, "BON") + f" N° {operation[ 'id' ]:05d}"

    titre_style = ParagraphStyle(
        "TitreDocument",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=couleur,
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    story.append(Paragraph(titre, titre_style))
    story.append(Spacer(1, 8))

    # Informations principales
    info_data = [
        ["Médecin:", operation["doctor_name"]],
        ["Créé par:", operation.get("created_by_name", "N/A")],
        [
            "Date:",
            (
                operation["created_at"].strftime("%d/%m/%Y %H:%M")
                if operation["created_at"]
                else "N/A"
            ),
        ],
    ]

    info_table = Table(info_data, colWidths=[3.5 * cm, 14 * cm])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story.append(info_table)
    story.append(Spacer(1, 10))

    # Liste des dossiers
    header_style = ParagraphStyle(
        "CustomHeader",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#283593"),
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )

    story.append(Paragraph("Détail des dossiers", header_style))
    story.append(Spacer(1, 4))

    if dossiers:
        dossiers_data = [["Patient", "Date", "Prix total", "Montant"]]

        for d in dossiers:
            dossiers_data.append(
                [
                    d["patient"],
                    (
                        d["location_date"].strftime("%d/%m/%Y")
                        if d["location_date"]
                        else "N/A"
                    ),
                    f"{float( d[ 'prix_total' ] ):,.2f} DA",
                    f"{float( d[ 'montant' ] ):,.2f} DA",
                ]
            )

        dossiers_table = Table(
            dossiers_data, colWidths=[6 * cm, 3 * cm, 4 * cm, 4.5 * cm]
        )
        dossiers_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), couleur),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("ALIGN", (2, 0), (-1, 0), "RIGHT"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f5f5f5")],
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        story.append(dossiers_table)

    story.append(Spacer(1, 10))

    # Récapitulatif
    montant = float(operation["montant"])
    montant_paye = float(operation["montant_paye"])
    reste = float(operation["reste"])

    story.append(Paragraph("Récapitulatif", header_style))
    story.append(Spacer(1, 4))

    recap_data = [
        ["Montant total:", f"{montant:,.2f} DA"],
        ["Montant payé:", f"{montant_paye:,.2f} DA"],
        ["Reste à payer:", f"{reste:,.2f} DA"],
    ]

    recap_table = Table(recap_data, colWidths=[10 * cm, 7.5 * cm])
    recap_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEABOVE", (0, -1), (-1, -1), 2, couleur),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story.append(recap_table)
    story.append(Spacer(1, 10))

    # Montant en lettres
    montant_lettres = num2words(montant, lang="fr").capitalize()

    normal_style = ParagraphStyle(
        "CustomNormal", parent=styles["Normal"], fontSize=10, leading=12
    )

    lettres_style = ParagraphStyle(
        "Lettres",
        parent=normal_style,
        fontSize=10,
        textColor=couleur,
        fontName="Helvetica-Bold",
        spaceAfter=6,
    )

    story.append(
        Paragraph(f"<b>Arrêté le présent bon à la somme de :</b>", normal_style)
    )
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"{montant_lettres} dinars algériens", lettres_style))
    story.append(Spacer(1, 12))

    # Signatures
    signature_data = [
        [
            Paragraph(
                "<b>Signature du médecin</b><br/><br/><br/>_________________",
                normal_style,
            ),
            "",
            Paragraph(
                "<b>Cachet et signature<br/>de la clinique</b><br/><br/>_________________",
                normal_style,
            ),
        ]
    ]

    signature_table = Table(signature_data, colWidths=[6 * cm, 5.5 * cm, 6 * cm])
    signature_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    story.append(signature_table)
    story.append(Spacer(1, 8))

    # Footer
    footer_style = ParagraphStyle(
        "Footer",
        parent=normal_style,
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER,
    )

    story.append(
        Paragraph(
            f"Document généré le {datetime.now().strftime( '%d/%m/%Y à %H:%M' )} - Clinique INAYA",
            footer_style,
        )
    )

    doc.build(story)

    pdf_data = buffer.getvalue()
    buffer.close()

    return pdf_data
