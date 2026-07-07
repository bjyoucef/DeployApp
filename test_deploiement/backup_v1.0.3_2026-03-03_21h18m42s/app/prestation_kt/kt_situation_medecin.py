from decimal import Decimal, InvalidOperation

from flask import flash, g, jsonify, redirect, render_template, request, url_for
from num2words import num2words

from app import app, get_db_connection
from app.decharge_paiment import insert_decharge
from app.error import handle_errors
from app.utils.utiles import login_required


def safe_str(value):
    return str(value) if value is not None else ""


def safe_float(value):
    try:
        return float(value) if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def safe_int(value):
    try:
        return int(value) if value is not None else 0
    except (ValueError, TypeError):
        return 0


@app.route("/kt_situation_medecin")
@login_required
@handle_errors()
def kt_situation_medecin():
    """Version ULTRA-OPTIMISÉE avec une seule requête agrégée incluant UP"""

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # 🔥 REQUÊTE UNIQUE OPTIMISÉE avec agrégation directe incluant UP
        cursor.execute(
            """
            SELECT 
                d.id,
                COALESCE(d.first_name, '') AS first_name,
                COALESCE(d.last_name, '') AS last_name,
                d.id_specialty,
                COALESCE(s.name_specialty, '') AS name_specialty,
                COALESCE(SUM(kdp.part_operateur), 0) - COALESCE(SUM(kdp.payment), 0) AS total_solde,
                COUNT(DISTINCT kdp.id_dossier) AS nb_dossiers,
                COALESCE(SUM(kdp.part_operateur_up_medecin), 0) as total_up_medecin,
                COALESCE(SUM(kdp.part_operateur_up_clinique), 0) as total_up_clinique,
                COALESCE(SUM(kdp.up_medecin), 0) as total_up_medecin_brut,
                COALESCE(SUM(kdp.up_clinique), 0) as total_up_clinique_brut,
                EXISTS (
                    SELECT 1 
                    FROM kt_decharges_paiement dp 
                    WHERE dp.id_doctor = d.id 
                      AND dp.statut IN ('EN_COURS', 'PARTIEL')
                ) AS has_unpaid_decharge
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            LEFT JOIN kt_dossier_patient kdp ON d.id = kdp.id_doctor
            WHERE d.id_specialty IN (11, 19, 20)
            GROUP BY d.id, d.first_name, d.last_name, d.id_specialty, s.name_specialty
            ORDER BY d.first_name, d.last_name
        """
        )

        doctors_raw = cursor.fetchall()

        doctors = []
        total_solde_all_doctors = 0.0

        for doctor_raw in doctors_raw:
            doctor = {
                "id": safe_int(doctor_raw["id"]),
                "first_name": safe_str(doctor_raw["first_name"]),
                "last_name": safe_str(doctor_raw["last_name"]),
                "id_specialty": safe_int(doctor_raw["id_specialty"]),
                "name_specialty": safe_str(doctor_raw["name_specialty"]),
                "total_solde": safe_float(doctor_raw["total_solde"]),
                "nb_dossiers": safe_int(doctor_raw["nb_dossiers"]),
                "total_up_medecin": safe_float(doctor_raw["total_up_medecin"]),
                "total_up_clinique": safe_float(doctor_raw["total_up_clinique"]),
                "total_up_medecin_brut": safe_float(
                    doctor_raw["total_up_medecin_brut"]
                ),
                "total_up_clinique_brut": safe_float(
                    doctor_raw["total_up_clinique_brut"]
                ),
                "has_unpaid_decharge": bool(doctor_raw["has_unpaid_decharge"]),
            }
            doctors.append(doctor)
            total_solde_all_doctors += doctor["total_solde"]

        # Récupérer les spécialités
        cursor.execute(
            "SELECT * FROM specialty WHERE id_specialty IN (11, 19, 20) ORDER BY name_specialty"
        )
        specialties = cursor.fetchall()

    except Exception as e:
        print(f"Erreur dans kt_situation_medecin: {e}")
        import traceback

        traceback.print_exc()

        doctors = []
        specialties = []
        total_solde_all_doctors = 0.0

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return render_template(
        "prestation_kt/kt_situation_medecin.html",
        title="Situation médecin",
        doctors=doctors,
        specialties=specialties,
        total_solde_all_doctors=total_solde_all_doctors,
        user=g.user,
    )


@app.route("/kt_doctor_details/<int:id_doctor>")
@login_required
@handle_errors()
def kt_doctor_details(id_doctor):
    """API AJAX pour charger les détails d'un médecin à la demande incluant UP"""

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Récupérer les dossiers avec leurs transactions en UNE SEULE requête MISE À JOUR
        cursor.execute(
            """
            SELECT 
                kdp.id_dossier,
                COALESCE(kdp.patient, '') as patient_name,
                COALESCE(kdp.payment, 0) as payment,
                COALESCE(kdp.part_operateur, 0) as part_operateur,
                COALESCE(kdp.up_medecin, 0) as up_medecin,
                COALESCE(kdp.up_clinique, 0) as up_clinique,
                COALESCE(kdp.part_operateur_up_medecin, 0) as part_operateur_up_medecin,
                COALESCE(kdp.part_operateur_up_clinique, 0) as part_operateur_up_clinique,
                kdp.duree_operation,
                CONCAT(COALESCE(anes.prenom, ''), ' ', COALESCE(anes.nom, '')) as anesthesiste_name,
                CONCAT(COALESCE(rea.prenom, ''), ' ', COALESCE(rea.nom, '')) as reanimateur_name,
        
        /* Agrégation avec comptage */
                GROUP_CONCAT(
            CONCAT_WS('|',
                        COALESCE(kdp.acte_date, ''),
                CASE 
                    WHEN a.nb > 1 THEN CONCAT('(x', a.nb, ') ', COALESCE(a.code_cnas, ''))
                    ELSE COALESCE(a.code_cnas, '')
                END,
                CASE 
                    WHEN a.nb > 1 THEN CONCAT('(x', a.nb, ') ', COALESCE(a.name_acte_kt, ''))
                    ELSE COALESCE(a.name_acte_kt, '')
                END,
                        COALESCE(kdp.urgence, 0),
                COALESCE(a.convention, ''),
                COALESCE(a.part_operateur, 0)
                    )
            ORDER BY a.name_acte_kt
                    SEPARATOR ';;'
                ) as transactions_data
            FROM kt_dossier_patient kdp
    
    LEFT JOIN (
        SELECT 
            dak.id_dossier,
            dak.id_acte,
            ak.code_cnas,
            ak.name_acte_kt,
            dak.convention,
            SUM(dak.part_operateur) as part_operateur,
            COUNT(*) as nb
        FROM kt_dossier_actes dak
        LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
        GROUP BY dak.id_dossier, dak.id_acte, ak.code_cnas, ak.name_acte_kt, dak.convention
    ) a ON kdp.id_dossier = a.id_dossier
    
            LEFT JOIN anesthesie_personnel anes ON kdp.id_anesthesiste = anes.id_personnel_anesthesie
            LEFT JOIN anesthesie_personnel rea ON kdp.id_reanimateur = rea.id_personnel_anesthesie
            WHERE kdp.id_doctor = %s
            GROUP BY kdp.id_dossier, kdp.patient, kdp.payment, kdp.part_operateur,
                     kdp.up_medecin, kdp.up_clinique, kdp.part_operateur_up_medecin,
             kdp.part_operateur_up_clinique, kdp.duree_operation, kdp.acte_date, kdp.urgence,
                     anes.prenom, anes.nom, rea.prenom, rea.nom
            ORDER BY kdp.id_dossier DESC
        """,
            (id_doctor,),
        )

        dossiers_raw = cursor.fetchall()

        dossiers = []
        for dossier_raw in dossiers_raw:
            # Parser les transactions agrégées
            transactions = []
            transactions_str = dossier_raw.get("transactions_data", "")

            if transactions_str:
                for trans_data in transactions_str.split(";;"):
                    parts = trans_data.split("|")
                    if len(parts) == 6:
                        transactions.append(
                            {
                                "acte_date": parts[0],
                                "code_cnas": parts[1],
                                "name_acte_kt": parts[2],
                                "urgence": int(parts[3]) if parts[3] else 0,
                                "convention": parts[4],
                                "part_operateur_acte": (
                                    float(parts[5]) if parts[5] else 0.0
                                ),
                            }
                        )

            dossier = {
                "id_dossier": dossier_raw["id_dossier"],
                "patient_name": dossier_raw["patient_name"],
                "payment": float(dossier_raw["payment"]),
                "part_operateur": float(dossier_raw["part_operateur"]),
                "up_medecin": float(dossier_raw["up_medecin"]),
                "up_clinique": float(dossier_raw["up_clinique"]),
                "part_operateur_up_medecin": float(
                    dossier_raw["part_operateur_up_medecin"]
                ),
                "part_operateur_up_clinique": float(
                    dossier_raw["part_operateur_up_clinique"]
                ),
                "duree_operation": dossier_raw["duree_operation"],
                "anesthesiste_name": dossier_raw["anesthesiste_name"].strip(),
                "reanimateur_name": dossier_raw["reanimateur_name"].strip(),
                "transactions": transactions,
            }
            dossiers.append(dossier)

        return jsonify({"success": True, "dossiers": dossiers})

    except Exception as e:
        print(f"Erreur kt_doctor_details: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/add_decharge_paiment_kt", methods=["POST"])
@login_required
@handle_errors()
def add_decharge_paiment_kt():
    """Ajoute une nouvelle décharge de paiement pour un médecin KT."""
    doctor_name = request.form.get("doctor_name", "").strip()
    amount = request.form.get("amount", "").strip()
    date = request.form.get("date", "").strip()
    id_doctor_kt = request.form.get("id_doctor_kt", "").strip()
    dossiers = request.form.get("dossiers", "").strip()
    dossiers_list = [line.strip() for line in dossiers.splitlines() if line.strip()]

    # Validation des champs obligatoires
    if not doctor_name or not amount or not date or not id_doctor_kt:
        flash("Tous les champs sont requis.", "danger")
        return redirect(url_for("kt_situation_medecin"))

    # Validation du montant
    try:
        amount = Decimal(amount)
        if amount <= 0:
            flash("Erreur : Le montant doit être supérieur à zéro.", "danger")
            return redirect(url_for("kt_situation_medecin"))
        amount_in_words = num2words(float(amount), lang="fr").upper()
    except (InvalidOperation, ValueError):
        flash("Erreur : Montant invalide.", "danger")
        return redirect(url_for("kt_situation_medecin"))

    # Insertion de la décharge
    error = insert_decharge(
        doctor_name,
        id_doctor_kt,
        None,
        amount,
        date,
        dossiers_list,
        g.user["id_personnel"],
    )
    if error:
        flash(error, "danger")
    else:
        flash("Décharge ajoutée avec succès.", "success")

    return redirect(url_for("decharges"))
