# app/medecin_interne_paiements.py
"""
Gestion des paiements par tranches pour les actes médicaux
Génération de bons de paiement
"""

from decimal import Decimal
from io import BytesIO

from flask import flash, g, jsonify, redirect, render_template, request, url_for
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required

# ========================================================================
# UTILITAIRES
# ========================================================================


def to_decimal(value, default=0):
    """Convertit une valeur en Decimal de manière sécurisée"""
    if value is None or value == "":
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except:
        return Decimal(str(default))


def get_montant_total_a_payer(cursor, id_acte):
    """
    Calcule le montant total à payer selon le mode de calcul
    """
    cursor.execute(
        """
        SELECT prix_acte_base,
               mode_calcul,
               prix_consommables_specifiques,
               prix_hospitalisation_hors_forfait,
               prix_supplements,
               prix_actes_supplementaires,
               prix_anesthesie
        FROM medecin_interne_actes
        WHERE id_acte = %s
                   """,
        (id_acte,),
    )

    acte = cursor.fetchone()
    if not acte:
        return Decimal("0")

    prix_base = to_decimal(acte["prix_acte_base"])

    if acte["mode_calcul"] == "PRIX_BASE":
        # Mode PRIX_BASE : montant total = prix_base + tous les suppléments
        total_supplements = (
            to_decimal(acte["prix_consommables_specifiques"])
            + to_decimal(acte["prix_hospitalisation_hors_forfait"])
            + to_decimal(acte["prix_supplements"])
            + to_decimal(acte["prix_actes_supplementaires"])
            + to_decimal(acte["prix_anesthesie"])
        )
        return prix_base + total_supplements
    else:
        # Mode PRIX_TOTAL : montant total = prix_base (qui inclut déjà tout)
        return prix_base


def get_paiements_summary(cursor, id_acte):
    """
    Récupère le résumé des paiements pour un acte
    """
    montant_total = get_montant_total_a_payer(cursor, id_acte)

    cursor.execute(
        """
        SELECT COALESCE(SUM(montant_paye), 0) as total_paye,
               COUNT(*)                       as nombre_paiements
        FROM medecin_interne_paiements
        WHERE id_acte = %s
          AND est_annule = FALSE
                   """,
        (id_acte,),
    )

    result = cursor.fetchone()
    total_paye = to_decimal(result["total_paye"])

    return {
        "montant_total": montant_total,
        "total_paye": total_paye,
        "reste_a_payer": montant_total - total_paye,
        "nombre_paiements": result["nombre_paiements"],
        "pourcentage_paye": (
            float((total_paye / montant_total * 100)) if montant_total > 0 else 0
        ),
    }


# ========================================================================
# ROUTES - LISTE DES PAIEMENTS
# ========================================================================


@app.route("/medecin_interne/actes/<int:id_acte>/paiements")
@login_required
@handle_errors()
def medecin_interne_paiements_patients_list(id_acte):
    """Liste des paiements pour un acte"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer l'acte
        cursor.execute(
            """
            SELECT a.*,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name
            FROM medecin_interne_actes a
                     LEFT JOIN doctors d ON a.id_doctor = d.id
            WHERE a.id_acte = %s
                       """,
            (id_acte,),
        )

        acte = cursor.fetchone()
        if not acte:
            flash("Acte non trouvé", "danger")
            return redirect(url_for("medecin_interne_actes_list"))

        # Récupérer les paiements
        cursor.execute(
            """
            SELECT p.*,
                   CONCAT(pe.nom, ' ', pe.prenom) as created_by_name,
                   CONCAT(pa.nom, ' ', pa.prenom) as annule_by_name
            FROM medecin_interne_paiements p
                     LEFT JOIN personnel pe ON p.created_by = pe.id_personnel
                     LEFT JOIN personnel pa ON p.annule_par = pa.id_personnel
            WHERE p.id_acte = %s
            ORDER BY p.date_paiement DESC, p.id_paiement DESC
                       """,
            (id_acte,),
        )

        paiements = cursor.fetchall()

        # Résumé des paiements
        summary = get_paiements_summary(cursor, id_acte)

        return render_template(
            "medecin_interne/paiements_list.html",
            acte=acte,
            paiements=paiements,
            summary=summary,
            title=f"Paiements - Acte #{id_acte}",
        )

    finally:
        cursor.close()
        connection.close()


# ========================================================================
# ROUTES - AJOUTER UN PAIEMENT
# ========================================================================


@app.route("/medecin_interne/actes/<int:id_acte>/paiements/add", methods=["POST"])
@login_required
@handle_errors()
def medecin_interne_paiements_add(id_acte):
    """Ajouter un paiement"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Validation
        montant = to_decimal(request.form.get("montant_paye"))
        if montant <= 0:
            flash("Le montant doit être supérieur à 0", "danger")
            return redirect(
                url_for("medecin_interne_paiements_patients_list", id_acte=id_acte)
            )

        # Vérifier le reste à payer
        summary = get_paiements_summary(cursor, id_acte)
        if montant > summary["reste_a_payer"]:
            flash(
                f"Le montant ne peut pas dépasser le reste à payer ({float( summary[ 'reste_a_payer' ] ):.2f} DA)",
                "danger",
            )
            return redirect(
                url_for("medecin_interne_paiements_patients_list", id_acte=id_acte)
            )
        # Vérifier que l'acte n'est pas annulé
        cursor.execute(
            """
            SELECT est_annule
            FROM medecin_interne_actes
            WHERE id_acte = %s
        """,
            (id_acte,),
        )

        acte = cursor.fetchone()
        if not acte:
            flash("Acte non trouvé", "danger")
            return redirect(url_for("medecin_interne_actes_list"))

        if acte["est_annule"]:
            flash(
                "Impossible d'enregistrer un paiement sur un acte annulé. "
                "Restaurez d'abord l'acte si nécessaire.",
                "danger",
            )
            return redirect(
                url_for("medecin_interne_paiements_patients_list", id_acte=id_acte)
            )
        # Récupérer les données
        mode_paiement = request.form.get("mode_paiement", "ESPECES")
        reference_paiement = request.form.get("reference_paiement", "").strip() or None
        nom_banque = request.form.get("nom_banque", "").strip() or None
        date_echeance = request.form.get("date_echeance") or None
        observations = request.form.get("observations", "").strip()

        # Insérer le paiement
        cursor.execute(
            """
            INSERT INTO medecin_interne_paiements
            (id_acte, montant_paye, mode_paiement, reference_paiement,
             nom_banque, date_echeance, observations, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       """,
            (
                id_acte,
                montant,
                mode_paiement,
                reference_paiement,
                nom_banque,
                date_echeance,
                observations,
                g.user["id_personnel"],
            ),
        )

        id_paiement = cursor.lastrowid

        # Récupérer le numéro de bon généré
        cursor.execute(
            "SELECT numero_bon FROM medecin_interne_paiements WHERE id_paiement = %s",
            (id_paiement,),
        )
        result = cursor.fetchone()
        numero_bon = result["numero_bon"]

        connection.commit()

        flash(f"Paiement enregistré avec succès. Bon N° {numero_bon}", "success")
        return redirect(
            url_for("medecin_interne_paiements_patients_list", id_acte=id_acte)
        )

    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur ajout paiement: {str( e )}")
        flash(f"Erreur lors de l'enregistrement: {str( e )}", "danger")
        return redirect(
            url_for("medecin_interne_paiements_patients_list", id_acte=id_acte)
        )

    finally:
        cursor.close()
        connection.close()


# ========================================================================
# ROUTES - ANNULER UN PAIEMENT
# ========================================================================


@app.route("/medecin_interne/paiements/<int:id_paiement>/annuler", methods=["POST"])
@login_required
@handle_errors()
def medecin_interne_paiements_annuler(id_paiement):
    """Annuler un paiement"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        motif = request.form.get("motif_annulation", "").strip()
        if not motif:
            flash("Le motif d'annulation est obligatoire", "danger")
            return redirect(request.referrer or url_for("medecin_interne_actes_list"))

        # Récupérer l'id_acte avant annulation
        cursor.execute(
            "SELECT id_acte FROM medecin_interne_paiements WHERE id_paiement = %s",
            (id_paiement,),
        )
        result = cursor.fetchone()
        if not result:
            flash("Paiement non trouvé", "danger")
            return redirect(url_for("medecin_interne_actes_list"))

        id_acte = result["id_acte"]

        # Annuler le paiement
        cursor.execute(
            """
            UPDATE medecin_interne_paiements
            SET est_annule = TRUE,
                motif_annulation = %s,
                annule_par = %s,
                annule_at = NOW()
            WHERE id_paiement = %s
              AND est_annule = FALSE
                       """,
            (motif, g.user["id_personnel"], id_paiement),
        )

        if cursor.rowcount == 0:
            flash("Ce paiement est déjà annulé", "warning")
        else:
            connection.commit()
            flash("Paiement annulé avec succès", "success")

        return redirect(
            url_for("medecin_interne_paiements_patients_list", id_acte=id_acte)
        )

    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur annulation paiement: {str( e )}")
        flash(f"Erreur lors de l'annulation: {str( e )}", "danger")
        return redirect(request.referrer or url_for("medecin_interne_actes_list"))

    finally:
        cursor.close()
        connection.close()


# ========================================================================
# ROUTES - BON DE PAIEMENT (PDF)
# ========================================================================


@app.route("/medecin_interne/paiements/<int:id_paiement>/bon")
@login_required
@handle_errors()
def medecin_interne_paiements_bon(id_paiement):
    """Générer un bon de paiement en PDF"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer les données du paiement et de l'acte
        cursor.execute(
            """
            SELECT p.*,
                   a.patient,
                   a.date_acte,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   CONCAT(pe.nom, ' ', pe.prenom)         as created_by_name
            FROM medecin_interne_paiements p
                     JOIN medecin_interne_actes a ON p.id_acte = a.id_acte
                     LEFT JOIN doctors d ON a.id_doctor = d.id
                     LEFT JOIN personnel pe ON p.created_by = pe.id_personnel
            WHERE p.id_paiement = %s
                       """,
            (id_paiement,),
        )

        paiement = cursor.fetchone()
        if not paiement:
            flash("Paiement non trouvé", "danger")
            return redirect(url_for("medecin_interne_actes_list"))

        # Récupérer le résumé des paiements
        summary = get_paiements_summary(cursor, paiement["id_acte"])

        # Générer le PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4, topMargin=1 * cm, bottomMargin=1 * cm
        )
        story = []
        styles = getSampleStyleSheet()

        # Style personnalisé pour le titre
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=colors.HexColor("#6366f1"),
            spaceAfter=30,
            alignment=TA_CENTER,
        )

        # Titre
        story.append(Paragraph("BON DE PAIEMENT", title_style))
        story.append(Spacer(1, 0.5 * cm))

        # Informations du bon
        bon_data = [
            ["Numéro de bon:", paiement["numero_bon"]],
            ["Date d'émission:", paiement["date_paiement"].strftime("%d/%m/%Y %H:%M")],
            ["Patient:", paiement["patient"]],
            ["Médecin:", paiement["doctor_name"]],
            [
                "Date de l'acte:",
                (
                    paiement["date_acte"].strftime("%d/%m/%Y")
                    if paiement["date_acte"]
                    else "N/A"
                ),
            ],
        ]

        bon_table = Table(bon_data, colWidths=[5 * cm, 12 * cm])
        bon_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(bon_table)
        story.append(Spacer(1, 1 * cm))

        # Détails du paiement
        story.append(Paragraph("DÉTAILS DU PAIEMENT", styles["Heading2"]))
        story.append(Spacer(1, 0.3 * cm))

        mode_paiement_text = {
            "ESPECES": "Espèces",
            "CHEQUE": "Chèque",
            "CARTE": "Carte bancaire",
            "VIREMENT": "Virement",
            "TPE": "Terminal de paiement",
        }.get(paiement["mode_paiement"], paiement["mode_paiement"])

        paiement_data = [
            ["Mode de paiement:", mode_paiement_text],
            ["Montant payé:", f"{float( paiement[ 'montant_paye' ] ):.2f} DA"],
        ]

        if paiement["reference_paiement"]:
            paiement_data.append(["Référence:", paiement["reference_paiement"]])
        if paiement["nom_banque"]:
            paiement_data.append(["Banque:", paiement["nom_banque"]])
        if paiement["date_echeance"]:
            paiement_data.append(
                ["Date d'échéance:", paiement["date_echeance"].strftime("%d/%m/%Y")]
            )

        paiement_table = Table(paiement_data, colWidths=[5 * cm, 12 * cm])
        paiement_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(paiement_table)
        story.append(Spacer(1, 1 * cm))

        # Résumé financier
        story.append(Paragraph("RÉSUMÉ FINANCIER", styles["Heading2"]))
        story.append(Spacer(1, 0.3 * cm))

        summary_data = [
            ["Montant total à payer:", f"{float( summary[ 'montant_total' ] ):.2f} DA"],
            ["Total payé:", f"{float( summary[ 'total_paye' ] ):.2f} DA"],
            ["Reste à payer:", f"{float( summary[ 'reste_a_payer' ] ):.2f} DA"],
        ]

        summary_table = Table(summary_data, colWidths=[5 * cm, 12 * cm])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                    (
                        "BACKGROUND",
                        (0, 2),
                        (1, 2),
                        (
                            colors.HexColor("#10b981")
                            if summary["reste_a_payer"] <= 0
                            else colors.HexColor("#ef4444")
                        ),
                    ),
                    ("TEXTCOLOR", (0, 0), (-1, 1), colors.black),
                    ("TEXTCOLOR", (0, 2), (1, 2), colors.white),
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("FONTSIZE", (0, 2), (1, 2), 13),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 1.5 * cm))

        # Observations
        if paiement["observations"]:
            story.append(Paragraph("OBSERVATIONS", styles["Heading3"]))
            story.append(Spacer(1, 0.2 * cm))
            story.append(Paragraph(paiement["observations"], styles["Normal"]))
            story.append(Spacer(1, 1 * cm))

        # Signature
        signature_data = [
            ["Émis par:", paiement["created_by_name"] or "N/A"],
            ["Signature du patient:", ""],
        ]

        signature_table = Table(signature_data, colWidths=[8.5 * cm, 8.5 * cm])
        signature_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 30),
                ]
            )
        )
        story.append(signature_table)

        # Générer le PDF
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        # Retourner le PDF
        from flask import make_response

        response = make_response(pdf)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = (
            f'inline; filename=bon_paiement_{paiement[ "numero_bon" ]}.pdf'
        )

        return response

    finally:
        cursor.close()
        connection.close()


# ========================================================================
# API - RÉSUMÉ DES PAIEMENTS
# ========================================================================


@app.route("/api/medecin_interne/actes/<int:id_acte>/paiements/summary")
@login_required
def api_medecin_interne_paiements_summary(id_acte):
    """Retourne le résumé des paiements pour un acte"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        summary = get_paiements_summary(cursor, id_acte)

        return jsonify(
            {
                "montant_total": float(summary["montant_total"]),
                "total_paye": float(summary["total_paye"]),
                "reste_a_payer": float(summary["reste_a_payer"]),
                "nombre_paiements": summary["nombre_paiements"],
                "pourcentage_paye": summary["pourcentage_paye"],
            }
        )

    except Exception as e:
        app.logger.error(f"Erreur API summary: {str( e )}")
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        connection.close()
