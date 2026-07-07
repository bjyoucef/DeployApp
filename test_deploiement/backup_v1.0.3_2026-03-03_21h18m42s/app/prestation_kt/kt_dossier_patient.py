import os
from decimal import Decimal

from flask import (
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from app import app, get_db_connection
from app.error import handle_errors
from app.prestation_kt.kt_tarifs import resoudre_prix
from app.utils.utiles import login_required, save_files


def safe_str(value):
    """Convertit de manière sécurisée une valeur en string, retourne '' si None"""
    return str(value) if value is not None else ""


def safe_int(value):
    """Convertit de manière sécurisée une valeur en int, retourne 0 si None"""
    return int(value) if value is not None else 0


def safe_float(value):
    """Convertit de manière sécurisée une valeur en float, retourne 0.0 si None"""
    return float(value) if value is not None else 0.0


@app.route("/kt_dossier_patient/create", methods=["GET"])
@login_required
@handle_errors()
def kt_dossier_create():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Médecins (Intervenants)
        cursor.execute(
            """
            SELECT id, CONCAT(first_name, ' ', last_name) as name
            FROM doctors
            WHERE id_specialty IN (11, 19, 20)
            ORDER BY first_name, last_name
        """
        )
        doctors = [{"id": row["id"], "name": row["name"]} for row in cursor.fetchall()]

        # 2. Actes KT
        cursor.execute("SELECT * FROM kt_actes ORDER BY name_acte_kt")
        acts_kt = cursor.fetchall()

        # 2b. Conventions actives
        cursor.execute(
            "SELECT * FROM kt_conventions WHERE est_active = 1 ORDER BY nom_convention"
        )
        conventions_kt = cursor.fetchall()

        # 3. Produits
        cursor.execute(
            "SELECT id_produit, description, prix FROM produits ORDER BY description"
        )
        produits = cursor.fetchall()

        # 4. Actes Anesthésie
        cursor.execute(
            "SELECT * FROM anesthesie_type_acte WHERE est_actif=1 ORDER BY nom_acte"
        )
        actes_anesthesie = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    from datetime import datetime

    return render_template(
        "prestation_kt/kt_dossier_create.html",
        doctors=doctors,
        acts_kt=acts_kt,
        produits=produits,
        actes_anesthesie=actes_anesthesie,
        conventions_kt=conventions_kt,
        title="Nouveau Dossier KT",
        user=g.user,
        today=datetime.now().strftime("%Y-%m-%d"),
    )


@app.route("/kt_dossier_patient", methods=["GET", "POST"])
@login_required
@handle_errors()
def kt_dossier_patient():
    """Version optimisée avec AJAX et recherche avancée"""

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer les médecins et actes pour les formulaires
        cursor.execute(
            """
                       SELECT id, CONCAT(first_name, ' ', last_name) as name
                       FROM doctors
                       WHERE id_specialty IN (11, 19, 20)
                       ORDER BY first_name, last_name
                       """
        )
        doctors = [{"id": row["id"], "name": row["name"]} for row in cursor.fetchall()]

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "prestation_kt/kt_dossier_patient.html",
        doctors=doctors,
        title="Gestion des Dossiers",
    )


@app.route("/api/kt_dossier/check_dossier", methods=["GET"])
@login_required
def kt_check_dossier():
    patient_name = request.args.get("patient_name")
    if not patient_name:
        return jsonify({"exists": False})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check active dossiers created in the last 30 days
        cursor.execute(
            """
            SELECT id_dossier, acte_date
            FROM kt_dossier_patient
            WHERE patient LIKE %s
            ORDER BY acte_date DESC
            LIMIT 1
        """,
            (f"{patient_name}%",),
        )
        dossier = cursor.fetchone()
        if dossier:
            # Format date for display
            date_str = (
                dossier["acte_date"].strftime("%d/%m/%Y")
                if dossier["acte_date"]
                else "Date inconnue"
            )
            return jsonify(
                {
                    "exists": True,
                    "message": f"⚠️ Attention : Un dossier KT existe déjà pour ce patient (Date : {date_str}). Voulez-vous vraiment en créer un nouveau ?",
                }
            )
        return jsonify({"exists": False})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/kt_dossiers", methods=["GET"])
@login_required
@handle_errors()
def api_kt_dossiers():
    """API AJAX pour récupérer les dossiers avec filtres et recherche"""

    # Paramètres de pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    offset = (page - 1) * per_page

    # Filtres
    doctor_filter = request.args.get("doctor", "all")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    search_query = request.args.get("search", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Requête de base MISE À JOUR avec les nouveaux champs
        count_query = """
                      SELECT COUNT(DISTINCT d.id_dossier) as total
                      FROM kt_dossier_patient d
                               LEFT JOIN doctors doc ON d.id_doctor = doc.id
                               LEFT JOIN anesthesie_personnel anes ON d.id_anesthesiste = anes.id_personnel_anesthesie
                               LEFT JOIN anesthesie_personnel rea ON d.id_reanimateur = rea.id_personnel_anesthesie
                               LEFT JOIN (SELECT dak.id_dossier,
                                                 ak.code_cnas,
                                                 ak.name_acte_kt,
                                                 dak.convention,
                                                 SUM(dak.part_operateur) as part_operateur,
                                                 COUNT(*)                as nb
                                          FROM kt_dossier_actes dak
                                                   LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
                                          GROUP BY dak.id_dossier, dak.id_acte) a ON d.id_dossier = a.id_dossier
                      WHERE 1 = 1 \
                      """

        base_query = """
                     SELECT d.id_dossier,
                            CONCAT(COALESCE(doc.first_name, ''), ' ', COALESCE(doc.last_name, ''))   as doctor_name,
                            COALESCE(d.patient, '')                                                  as patient_name,
                            d.patient_oid_his,
                            d.acte_date,
                            d.urgence,
                            d.vip,
                            d.compte_rendu_path,
                           d.compte_rendu_nom_original,
                           d.compte_rendu_date_upload,
                            COALESCE(d.prix_dossier_esp, 0)                                          as prix_dossier_esp,
                            COALESCE(d.part_operateur_extrat, 0)                                     as part_operateur_extrat,
                            COALESCE(d.up_medecin, 0)                                                as up_medecin,
                            COALESCE(d.up_clinique, 0)                                               as up_clinique,
                            COALESCE(d.part_operateur_up_medecin, 0)                                 as part_operateur_up_medecin,
                            COALESCE(d.part_operateur_up_clinique, 0)                                as part_operateur_up_clinique,
                            d.duree_operation,
                            CONCAT(COALESCE(anes.prenom, ''), ' ', COALESCE(anes.nom, ''))           as anesthesiste_name,
                            CONCAT(COALESCE(rea.prenom, ''), ' ', COALESCE(rea.nom, ''))             as reanimateur_name,

                         /* Codes CNAS avec quantité */
                            GROUP_CONCAT(
                                    CASE
                                        WHEN a.nb > 1 THEN CONCAT(' (x', a.nb, ') ', a.code_cnas)
                                        ELSE a.code_cnas
                                        END
                                    ORDER BY a.code_cnas
                                    SEPARATOR ', '
                            )                                                                        as code_cnas,

                         /* Noms des actes avec quantité */
                            GROUP_CONCAT(
                                    CASE
                                        WHEN a.nb > 1 THEN CONCAT(' (x', a.nb, ') ', a.name_acte_kt)
                                        ELSE a.name_acte_kt
                                        END
                                    ORDER BY a.name_acte_kt
                                    SEPARATOR ', '
                            )                                                                        as name_acte_kt,

                            GROUP_CONCAT(DISTINCT a.convention ORDER BY a.convention SEPARATOR ', ') as convention,
                            SUM(a.part_operateur)                                                    as part_operateur_acte,
                            COALESCE(d.payment, 0)                                                   as payment,
                            COALESCE(d.part_operateur, 0)                                            as part_operateur

                     FROM kt_dossier_patient d
                              LEFT JOIN doctors doc ON d.id_doctor = doc.id
                              LEFT JOIN anesthesie_personnel anes ON d.id_anesthesiste = anes.id_personnel_anesthesie
                              LEFT JOIN anesthesie_personnel rea ON d.id_reanimateur = rea.id_personnel_anesthesie

                              LEFT JOIN (SELECT dak.id_dossier,
                                                dak.id_acte,
                                                ak.code_cnas,
                                                ak.name_acte_kt,
                                                dak.convention,
                                                SUM(dak.part_operateur) as part_operateur,
                                                COUNT(*)                as nb
                                         FROM kt_dossier_actes dak
                                                  LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
                                         GROUP BY dak.id_dossier, dak.id_acte, ak.code_cnas, ak.name_acte_kt,
                                                  dak.convention) a ON d.id_dossier = a.id_dossier
                     WHERE 1 = 1 \
                     """

        query_filters = " AND doc.id_specialty IN (11, 19, 20)"
        query_params = []

        # Filtre médecin
        if doctor_filter != "all":
            query_filters += " AND d.id_doctor = %s"
            query_params.append(doctor_filter)

        # Filtre dates
        if start_date:
            query_filters += " AND d.acte_date >= %s"
            query_params.append(start_date)

        if end_date:
            query_filters += " AND d.acte_date <= %s"
            query_params.append(end_date)

        # Recherche globale
        if search_query:
            query_filters += """ AND (
                d.patient LIKE %s 
                OR CONCAT(doc.first_name, ' ', doc.last_name) LIKE %s
                OR a.code_cnas LIKE %s
                OR a.name_acte_kt LIKE %s
                OR d.id_dossier LIKE %s
                OR CONCAT(anes.prenom, ' ', anes.nom) LIKE %s
                OR CONCAT(rea.prenom, ' ', rea.nom) LIKE %s
            )"""
            search_pattern = f"%{search_query}%"
            query_params.extend([search_pattern] * 7)

        # Compter le total
        cursor.execute(count_query + query_filters, query_params)
        total_records = cursor.fetchone()["total"]
        total_pages = (total_records + per_page - 1) // per_page

        # Requête principale avec pagination
        full_query = (
            base_query
            + query_filters
            + """
            GROUP BY d.id_dossier
            ORDER BY d.id_dossier DESC
            LIMIT %s OFFSET %s
        """
        )
        query_params.extend([per_page, offset])

        cursor.execute(full_query, query_params)
        dossiers_raw = cursor.fetchall()

        # Formater les résultats
        dossiers = []
        for row in dossiers_raw:
            dossier = {
                "id_dossier": safe_int(row["id_dossier"]),
                "doctor_name": safe_str(row["doctor_name"]),
                "patient_name": safe_str(row["patient_name"]),
                "patient_oid_his": safe_str(row["patient_oid_his"]),
                "acte_date": (
                    row["acte_date"].strftime("%d/%m/%Y") if row["acte_date"] else ""
                ),
                "urgence": safe_int(row["urgence"]),
                "vip": safe_int(row["vip"]),
                "code_cnas": safe_str(row["code_cnas"]),
                "name_acte_kt": safe_str(row["name_acte_kt"]),
                "convention": safe_str(row["convention"]),
                "prix_dossier_esp": safe_float(row["prix_dossier_esp"]),
                "part_operateur_extrat": safe_float(row["part_operateur_extrat"]),
                "part_operateur_acte": safe_float(row["part_operateur_acte"]),
                "up_medecin": safe_float(row["up_medecin"]),
                "up_clinique": safe_float(row["up_clinique"]),
                "part_operateur_up_medecin": safe_float(
                    row["part_operateur_up_medecin"]
                ),
                "part_operateur_up_clinique": safe_float(
                    row["part_operateur_up_clinique"]
                ),
                "duree_operation": safe_int(row["duree_operation"]),
                "anesthesiste_name": safe_str(row["anesthesiste_name"]).strip(),
                "payment": safe_float(row["payment"]),
                "part_operateur": safe_float(row["part_operateur"]),
                "reanimateur_name": safe_str(row["reanimateur_name"]).strip(),
                "compte_rendu_path": safe_str(row["compte_rendu_path"]),
                "compte_rendu_nom_original": safe_str(row["compte_rendu_nom_original"]),
                "compte_rendu_date_upload": (
                    row["compte_rendu_date_upload"].strftime("%d/%m/%Y %H:%M")
                    if row["compte_rendu_date_upload"]
                    else None
                ),
            }
            dossiers.append(dossier)

        return jsonify(
            {
                "success": True,
                "dossiers": dossiers,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_pages": total_pages,
                    "total_records": total_records,
                },
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/ajouter_dossier_kt", methods=["POST"])
@login_required
@handle_errors()
def ajouter_dossier_kt():
    """Ajoute un dossier KT et ses actes associés avec calculs et validations."""

    def get_form_value(field, default=None, cast_func=None):
        """Retrieve a form value with optional casting and default fallback."""
        value = request.form.get(field, default)
        if cast_func:
            try:
                return cast_func(value) if value else default
            except ValueError:
                flash(f"Le champ '{field}' est invalide.", "danger")
                return None
        return value

    def validate_required_fields(fields):
        """Ensure all required fields are present and valid."""
        missing_fields = [field for field in fields if not request.form.get(field)]
        if missing_fields:
            for field in missing_fields:
                flash(f"Le champ '{field}' est obligatoire.", "danger")
            return False
        return True

    required_fields = ["id_doctor", "patient", "acte_date"]
    if not validate_required_fields(required_fields):
        return redirect(url_for("kt_dossier_patient"))

    form_data = {
        "id_doctor": request.form["id_doctor"],
        "patient": request.form["patient"],
        "acte_date": request.form["acte_date"],
        "nbr_nuite": get_form_value("nbr_nuite", 0, int),
        "vip": request.form.get("vip"),
        "nbr_nuite_conjoint": get_form_value("nbr_nuite_conjoint", 0, int),
        "urgenceCheck": request.form.get("urgenceCheck"),
        "extra_percentage": get_form_value("extraPercentage", 20, int),
        "extras": get_form_value("extras", 0, Decimal),
        "up_medecin": get_form_value("up_medecin", 0, Decimal),
        "up_clinique": get_form_value("up_clinique", 0, Decimal),
        "id_anesthesiste": get_form_value(
            "id_anesthesiste", None, lambda x: int(x) if x and x != "" else None
        ),
        "id_reanimateur": get_form_value(
            "id_reanimateur", None, lambda x: int(x) if x and x != "" else None
        ),
        "duree_operation": get_form_value(
            "duree_operation", None, lambda x: int(x) if x and x != "" else None
        ),
        "id_acte_anesthesie": get_form_value(
            "id_acte_anesthesie", None, lambda x: int(x) if x and x != "" else None
        ),
        "observations_anesthesie": get_form_value("observations_anesthesie", ""),
        "patient_oid_his": get_form_value(
            "patient_oid_his", None, lambda x: int(x) if x and x != "" else None
        ),
    }

    # Validation : Si anesthésiste OU réanimateur présent, durée ET acte obligatoires
    if form_data["id_anesthesiste"] or form_data["id_reanimateur"]:
        if not form_data["duree_operation"]:
            flash(
                "La durée d'opération est obligatoire si un anesthésiste ou réanimateur est présent.",
                "danger",
            )
            return redirect(url_for("kt_dossier_patient"))
        if not form_data["id_acte_anesthesie"]:
            flash(
                "Le type d'acte d'anesthésie est obligatoire si un anesthésiste ou réanimateur est présent.",
                "danger",
            )
            return redirect(url_for("kt_dossier_patient"))

    # Import de la fonction de calcul
    # ⭐ CORRECTION CRITIQUE : Filtrer uniquement les actes KT (pas l'acte d'anesthésie)
    import re

    acte_keys = [key for key in request.form.keys() if re.match(r"id_acte_\d+$", key)]

    # NOUVEAU : Vérification qu'au moins un acte KT est présent
    if not acte_keys:
        flash("Vous devez ajouter au moins un acte médical KT.", "danger")
        return redirect(url_for("kt_dossier_patient"))

    prix_nuit_extra_standard = Decimal("15000")
    prix_nuit_extra_vip = Decimal("30000")
    prix_nuit_vip = Decimal("18000")
    prix_hospitalisation = Decimal("0")
    kt_nights = 0

    total_part_operateur = Decimal("0")
    total_part_clinique = Decimal("0")
    prix_dossier_convention = Decimal("0")
    prix_dossier_esp = Decimal("0")
    part_operateur = Decimal("0")
    part_clinique_convention = Decimal("0")
    part_clinique_esp = Decimal("0")

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Calculs de base - tout en Decimal
        prix_conjoint = Decimal(form_data["nbr_nuite_conjoint"]) * Decimal("8000")
        prix_extras = form_data["extras"]
        part_operateur_extrat = (
            form_data["extras"]
            * Decimal(form_data["extra_percentage"])
            / Decimal("100")
        )

        # Calculs UP Médecin (80% médecin, 20% clinique)
        part_operateur_up_medecin = form_data["up_medecin"] * Decimal("0.80")
        part_clinique_up_medecin = form_data["up_medecin"] * Decimal("0.20")

        # Calculs UP Clinique (20% médecin, 80% clinique)
        part_operateur_up_clinique = form_data["up_clinique"] * Decimal("0.20")
        part_clinique_up_clinique = form_data["up_clinique"] * Decimal("0.80")

        # Génération QR UUID
        import uuid as _uuid

        qr_uuid = str(_uuid.uuid4())

        # Insertion du dossier principal
        query = """INSERT INTO kt_dossier_patient (qr_uuid, id_doctor, patient, acte_date, nbr_nuite, vip,
                                                   nbr_nuite_conjoint, prix_conjoint, extras, part_operateur_extrat,
                                                   up_medecin, up_clinique, part_operateur_up_medecin,
                                                   part_operateur_up_clinique,
                                                   id_anesthesiste, id_reanimateur, duree_operation, patient_oid_his)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        values = (
            qr_uuid,
            form_data["id_doctor"],
            form_data["patient"],
            form_data["acte_date"],
            form_data["nbr_nuite"],
            form_data["vip"],
            form_data["nbr_nuite_conjoint"],
            prix_conjoint,
            prix_extras,
            part_operateur_extrat,
            form_data["up_medecin"],
            form_data["up_clinique"],
            part_operateur_up_medecin,
            part_operateur_up_clinique,
            form_data["id_anesthesiste"],
            form_data["id_reanimateur"],
            form_data["duree_operation"],
            form_data["patient_oid_his"],
        )
        cursor.execute(query, values)
        connection.commit()
        id_dossier = cursor.lastrowid

        # ========================================
        # CRÉATION DES ACTES D'ANESTHÉSIE
        # ========================================
        from app.anesthesie_honoraires.anesthesie_honoraires import (
            calculer_honoraires_anesthesie,
            get_tarif_forfaitaire_anesthesie,
        )

        prix_anesthesie_dossier = Decimal("0")

        if form_data["id_acte_anesthesie"] and form_data["duree_operation"]:
            # ✅ UN SEUL TARIF FORFAITAIRE (prix fixe pour le dossier)
            prix_anesthesie_dossier = get_tarif_forfaitaire_anesthesie(
                cursor, form_data["id_acte_anesthesie"]
            )

            # Pour l'anesthésiste
            if form_data["id_anesthesiste"]:
                cursor.execute(
                    """
                    SELECT id_type_intervenant
                    FROM anesthesie_personnel
                    WHERE id_personnel_anesthesie = %s
                """,
                    (form_data["id_anesthesiste"],),
                )

                personnel_data = cursor.fetchone()

                if personnel_data:
                    id_type = personnel_data["id_type_intervenant"]

                    # ✅ HONORAIRES (rémunération variable avec durée)
                    honoraires = calculer_honoraires_anesthesie(
                        cursor,
                        form_data["id_acte_anesthesie"],
                        id_type,
                        form_data["duree_operation"],
                    )

                    # Insérer avec les honoraires (pour comptabilité interne)
                    cursor.execute(
                        """
                        INSERT INTO kt_dossier_anesthesie (id_dossier, id_acte_anesthesie,
                                                           id_personnel_anesthesie,
                                                           duree_reelle, honoraires_calcules, observations)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            form_data["id_acte_anesthesie"],
                            form_data["id_anesthesiste"],
                            form_data["duree_operation"],
                            honoraires,
                            form_data["observations_anesthesie"],
                        ),
                    )
                    connection.commit()

            # Pour le réanimateur
            if form_data["id_reanimateur"]:
                cursor.execute(
                    """
                    SELECT id_type_intervenant
                    FROM anesthesie_personnel
                    WHERE id_personnel_anesthesie = %s
                """,
                    (form_data["id_reanimateur"],),
                )

                personnel_data = cursor.fetchone()

                if personnel_data:
                    id_type = personnel_data["id_type_intervenant"]

                    # ✅ HONORAIRES (rémunération variable avec durée)
                    honoraires = calculer_honoraires_anesthesie(
                        cursor,
                        form_data["id_acte_anesthesie"],
                        id_type,
                        form_data["duree_operation"],
                    )

                    # Insérer avec les honoraires (pour comptabilité interne)
                    cursor.execute(
                        """
                        INSERT INTO kt_dossier_anesthesie (id_dossier, id_acte_anesthesie,
                                                           id_personnel_anesthesie,
                                                           duree_reelle, honoraires_calcules, observations)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            form_data["id_acte_anesthesie"],
                            form_data["id_reanimateur"],
                            form_data["duree_operation"],
                            honoraires,
                            form_data["observations_anesthesie"],
                        ),
                    )
                    connection.commit()

        # ========================================
        # TRAITEMENT DES ACTES KT
        # ========================================
        for key in acte_keys:
            acte_id = request.form.get(key)

            # Vérifier que l'acte est sélectionné
            if not acte_id:
                flash(
                    "Veuillez sélectionner un type d'acte pour tous les actes.",
                    "danger",
                )
                connection.rollback()
                return redirect(url_for("kt_dossier_patient"))

            # Extraire l'index de l'acte
            index = key.split("_")[-1]

            # Récupérer l'id_convention (nullable: None = payante hors convention)
            id_convention_raw = request.form.get(f"id_convention_{index}")
            id_convention = (
                int(id_convention_raw)
                if id_convention_raw and id_convention_raw.strip()
                else None
            )

            # Récupérer le label de convention pour rétro-compatibilité
            convention_label = request.form.get(f"convention_acte_kt_{index}", "")
            if not convention_label:
                if id_convention:
                    cursor.execute(
                        "SELECT code_convention FROM kt_conventions WHERE id_convention = %s",
                        (id_convention,),
                    )
                    row = cursor.fetchone()
                    convention_label = (
                        row["code_convention"].lower() if row else "convention"
                    )
                elif form_data["urgenceCheck"]:
                    convention_label = "urgence"
                else:
                    convention_label = "payante"

            # Récupérer les données de base de l'acte (nbr_nuit)
            cursor.execute(
                "SELECT id_acte, nbr_nuit FROM kt_actes WHERE id_acte = %s", (acte_id,)
            )
            kt_data = cursor.fetchone()

            if not kt_data:
                flash(f"L'acte ID {acte_id} n'existe pas.", "danger")
                connection.rollback()
                return redirect(url_for("kt_dossier_patient"))

            # ✅ RÉSOLUTION DU PRIX via la chaîne de fallback
            est_urgence = bool(form_data["urgenceCheck"])
            prix_resolu, part_operateur_resolu, source = resoudre_prix(
                cursor,
                int(acte_id),
                id_convention,
                int(form_data["id_doctor"]),
                est_urgence,
            )

            # Répartition convention vs espèces
            if id_convention and not est_urgence:
                # Convention : le prix va dans part_clinique_convention
                part_clinique_convention = prix_resolu
                part_clinique_esp = Decimal("0")
            else:
                # Payante ou urgence : le prix va dans part_clinique_esp
                part_clinique_esp = prix_resolu
                part_clinique_convention = Decimal("0")

            part_operateur = part_operateur_resolu
            total_part_clinique += prix_resolu
            total_part_operateur += part_operateur_resolu

            cursor.execute(
                """
                INSERT INTO kt_dossier_actes (id_dossier, id_acte, id_convention, convention, part_operateur,
                                              part_clinique_convention, part_clinique_esp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    id_dossier,
                    acte_id,
                    id_convention,
                    convention_label,
                    part_operateur,
                    part_clinique_convention,
                    part_clinique_esp,
                ),
            )
            connection.commit()

            prix_dossier_convention += part_clinique_convention
            prix_dossier_esp += part_clinique_esp
            part_clinique_convention = Decimal("0")
            part_clinique_esp = Decimal("0")
            kt_nights += kt_data["nbr_nuit"]

        # Ajout des prix supplémentaires
        prix_dossier_esp += (
            prix_extras
            + form_data["up_medecin"]
            + form_data["up_clinique"]
            + prix_anesthesie_dossier
        )

        # Hospitalisation
        extra_nights = form_data["nbr_nuite"] - kt_nights
        if extra_nights > 0:
            prix_hospitalisation += Decimal(extra_nights) * (
                prix_nuit_extra_vip if form_data["vip"] else prix_nuit_extra_standard
            )
        prix_hospitalisation += Decimal(kt_nights) * (
            prix_nuit_vip if form_data["vip"] else Decimal("0")
        )

        # Total part opérateur (actes + extras + UP)
        total_part_operateur += (
            part_operateur_extrat
            + part_operateur_up_medecin
            + part_operateur_up_clinique
        )

        # Mise à jour du dossier avec les totaux
        cursor.execute(
            """
                       UPDATE kt_dossier_patient
                       SET urgence                 = %s,
                           prix_hospitalisation    = %s,
                           part_operateur          = %s,
                           prix_dossier_convention = %s,
                           prix_dossier_esp        = %s
                       WHERE id_dossier = %s
                       """,
            (
                form_data["urgenceCheck"],
                prix_hospitalisation,
                total_part_operateur,
                prix_dossier_convention,
                prix_dossier_esp,
                id_dossier,
            ),
        )
        connection.commit()

        # Situation médecin
        cursor.execute(
            """
                       INSERT INTO kt_doctor_situations
                           (id_doctor, id_dossier, part_operateur)
                       VALUES (%s, %s, %s)
                       """,
            (form_data["id_doctor"], id_dossier, total_part_operateur),
        )
        connection.commit()

        flash("Dossier et actes ajoutés avec succès.", "success")

        # ========================================
        # GESTION DES PRODUITS CONSOMMÉS
        # ========================================
        produits_supp_ids = request.form.getlist("produit_supp_id[]")
        produits_supp_qtes = request.form.getlist("produit_supp_qte[]")

        if produits_supp_ids:
            total_prix_produits = Decimal("0")

            for i, prod_id in enumerate(produits_supp_ids):
                if prod_id and prod_id.strip():
                    try:
                        qte = (
                            int(produits_supp_qtes[i])
                            if i < len(produits_supp_qtes)
                            else 1
                        )
                        if qte > 0:
                            # Récupérer prix unitaire
                            cursor.execute(
                                "SELECT prix FROM produits WHERE id_produit = %s",
                                (prod_id,),
                            )
                            prod_data = cursor.fetchone()
                            prix_unitaire = (
                                prod_data["prix"] if prod_data else Decimal("0")
                            )

                            cursor.execute(
                                """
                                INSERT INTO kt_dossier_produits (id_dossier, id_produit, qte, prix_unitaire, created_by)
                                VALUES (%s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    prod_id,
                                    qte,
                                    prix_unitaire,
                                    g.user["id_personnel"],
                                ),
                            )

                            total_prix_produits += Decimal(qte) * Decimal(prix_unitaire)
                    except (ValueError, TypeError):
                        continue

            # Mise à jour du prix total du dossier si nécessaire (Optionnel, selon règles de gestion)
            # Pour l'instant on garde le prix calculé précédemment, mais on pourrait ajouter le prix des produits
            # Si le prix des produits doit impacter le prix global, décommenter ci-dessous :
            # cursor.execute("UPDATE kt_dossier_patient SET prix_dossier_esp = prix_dossier_esp + %s WHERE id_dossier = %s", (total_prix_produits, id_dossier))
            # connection.commit()

        connection.commit()
        return redirect(url_for("kt_dossier_patient"))

    except Exception as e:
        if connection:
            connection.rollback()
        flash(f"Une erreur est survenue : {str(e)}", "danger")
        import traceback

        traceback.print_exc()
        return redirect(url_for("kt_dossier_patient"))

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


# ============================================================
# API : Résolution de prix en temps réel (pour le frontend)
# ============================================================
@app.route("/api/kt/resoudre_prix", methods=["POST"])
@login_required
@handle_errors()
def api_resoudre_prix():
    """
    Résout le prix d'un acte en fonction du médecin, de la convention et de l'urgence.
    Utilisé par le frontend pour afficher les prix dynamiques.

    JSON Input: { id_acte, id_convention (nullable), id_doctor, est_urgence }
    JSON Output: { success, prix, part_operateur, source }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Données JSON requises"}), 400

    id_acte = data.get("id_acte")
    id_doctor = data.get("id_doctor")
    if not id_acte or not id_doctor:
        return (
            jsonify(
                {"success": False, "error": "id_acte et id_doctor sont obligatoires"}
            ),
            400,
        )

    id_convention_raw = data.get("id_convention")
    id_convention = int(id_convention_raw) if id_convention_raw else None
    est_urgence = bool(data.get("est_urgence", False))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        prix, part_operateur, source = resoudre_prix(
            cursor, int(id_acte), id_convention, int(id_doctor), est_urgence
        )
        return jsonify(
            {
                "success": True,
                "prix": float(prix),
                "part_operateur": float(part_operateur),
                "source": source,
            }
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/autocompletekt", methods=["GET"])
@login_required
def autocompletekt():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify([])

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
                SELECT DISTINCT patient
                FROM kt_dossier_patient
                WHERE patient LIKE %s
                ORDER BY patient
                LIMIT 20
                """,
        (f"%{query}%",),
    )

    patients = [{"patient": row["patient"]} for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(patients)


@app.route("/export_kt_dossiers", methods=["GET"])
@login_required
@handle_errors()
def export_kt_dossiers():
    """Exporte les dossiers KT en fichier Excel avec filtres"""
    import io

    from flask import send_file
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    # Récupérer les filtres
    doctor_filter = request.args.get("doctor", "all")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    search_query = request.args.get("search", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Requête de base (similaire à l'API) MISE À JOUR
        base_query = """
                     SELECT d.id_dossier, \
                            CONCAT(COALESCE(doc.first_name, ''), ' ', COALESCE(doc.last_name, '')) as doctor_name, \
                            COALESCE(d.patient, '')                                                as patient_name,
                            d.patient_oid_his, \
                            d.acte_date, \
                            d.urgence, \
                            d.vip, \
                            d.nbr_nuite, \
                            d.nbr_nuite_conjoint, \
                            d.prix_conjoint, \
                            d.extras, \
                            d.prix_hospitalisation, \
                            COALESCE(d.prix_dossier_esp, 0)                                        as prix_dossier_esp, \
                            COALESCE(d.prix_dossier_convention, 0)                                 as prix_dossier_convention, \
                            COALESCE(d.part_operateur, 0)                                          as part_operateur, \
                            COALESCE(d.part_operateur_extrat, 0)                                   as part_operateur_extrat, \
                            COALESCE(d.up_medecin, 0)                                              as up_medecin, \
                            COALESCE(d.up_clinique, 0)                                             as up_clinique, \
                            COALESCE(d.part_operateur_up_medecin, 0)                               as part_operateur_up_medecin, \
                            COALESCE(d.part_operateur_up_clinique, 0)                              as part_operateur_up_clinique, \
                            d.duree_operation, \
                            CONCAT(COALESCE(anes.prenom, ''), ' ', COALESCE(anes.nom, ''))         as anesthesiste_name, \
                            CONCAT(COALESCE(rea.prenom, ''), ' ', COALESCE(rea.nom, ''))           as reanimateur_name,

                         /* Avec comptage des occurrences */ \
                            GROUP_CONCAT( \
                                    CASE \
                                        WHEN a.nb > 1 THEN CONCAT('(x', a.nb, ') ', COALESCE(a.code_cnas, '')) \
                                        ELSE COALESCE(a.code_cnas, '') \
                                        END \
                                    ORDER BY a.code_cnas \
                                    SEPARATOR ', ' \
                            )                                                                      as code_cnas, \
 \
                            GROUP_CONCAT( \
                                    CASE \
                                        WHEN a.nb > 1 THEN CONCAT('(x', a.nb, ') ', COALESCE(a.name_acte_kt, '')) \
                                        ELSE COALESCE(a.name_acte_kt, '') \
                                        END \
                                    ORDER BY a.name_acte_kt \
                                    SEPARATOR ', ' \
                            )                                                                      as name_acte_kt, \
 \
                            GROUP_CONCAT(DISTINCT COALESCE(a.convention, '') ORDER BY a.convention SEPARATOR \
                                         ', ')                                                     as convention, \
                            SUM(COALESCE(a.part_operateur, 0))                                     as part_operateur_acte, \
                            SUM(COALESCE(a.part_clinique_esp, 0))                                  as part_clinique_esp, \
                            SUM(COALESCE(a.part_clinique_convention, 0))                           as part_clinique_convention

                     FROM kt_dossier_patient d
                              LEFT JOIN doctors doc ON d.id_doctor = doc.id
                              LEFT JOIN anesthesie_personnel anes ON d.id_anesthesiste = anes.id_personnel_anesthesie
                              LEFT JOIN anesthesie_personnel rea ON d.id_reanimateur = rea.id_personnel_anesthesie

                              LEFT JOIN (SELECT dak.id_dossier, \
                                                dak.id_acte, \
                                                ak.code_cnas, \
                                                ak.name_acte_kt, \
                                                dak.convention, \
                                                SUM(dak.part_operateur)           as part_operateur, \
                                                SUM(dak.part_clinique_esp)        as part_clinique_esp, \
                                                SUM(dak.part_clinique_convention) as part_clinique_convention, \
                                                COUNT(*)                          as nb \
                                         FROM kt_dossier_actes dak \
                                                  LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte \
                                         GROUP BY dak.id_dossier, dak.id_acte, ak.code_cnas, ak.name_acte_kt,
                                                  dak.convention) a \
                                        ON d.id_dossier = a.id_dossier

                     WHERE 1 = 1 \
                     """
        query_filters = " AND doc.id_specialty IN (11, 19, 20)"
        query_params = []

        # Appliquer les filtres
        if doctor_filter != "all":
            query_filters += " AND d.id_doctor = %s"
            query_params.append(doctor_filter)

        if start_date:
            query_filters += " AND d.acte_date >= %s"
            query_params.append(start_date)

        if end_date:
            query_filters += " AND d.acte_date <= %s"
            query_params.append(end_date)

        if search_query:
            query_filters += """ AND (
                d.patient LIKE %s 
                OR CONCAT(doc.first_name, ' ', doc.last_name) LIKE %s
                OR ak.code_cnas LIKE %s
                OR ak.name_acte_kt LIKE %s
                OR d.id_dossier LIKE %s
                OR CONCAT(anes.prenom, ' ', anes.nom) LIKE %s
                OR CONCAT(rea.prenom, ' ', rea.nom) LIKE %s
            )"""
            search_pattern = f"%{search_query}%"
            query_params.extend([search_pattern] * 7)

        full_query = (
            base_query
            + query_filters
            + """
            GROUP BY d.id_dossier
            ORDER BY d.id_dossier DESC
        """
        )

        cursor.execute(full_query, query_params)
        dossiers = cursor.fetchall()

        # Créer le workbook Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Dossiers KT"

        # Styles
        header_fill = PatternFill(
            start_color="667EEA", end_color="667EEA", fill_type="solid"
        )
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )
        center_alignment = Alignment(horizontal="center", vertical="center")
        right_alignment = Alignment(horizontal="right", vertical="center")

        # En-têtes MISES À JOUR
        headers = [
            "N° Dossier",
            "Médecin",
            "Patient",
            "Date",
            "Code CNAS",
            "Nom Acte",
            "Convention",
            "Urgence",
            "VIP",
            "Nuits Patient",
            "Nuits Conjoint",
            "Prix Conjoint",
            "Extras",
            "UP Médecin",
            "UP Clinique",
            "Anesthésiste",
            "Réanimateur",
            "Durée Op. (min)",
            "Prix Hospitalisation",
            "Part Op. Acte",
            "Part Op. Extra",
            "Part Op. UP Méd.",
            "Part Op. UP Clin.",
            "Part Op. Extra + UP" "Part Op. Total",
            "Prix Dossier ESP",
            "Prix Dossier Convention",
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_alignment
            cell.border = border

        # Données
        for row_num, dossier in enumerate(dossiers, 2):
            # Calculer Part Op. Extra + UP
            part_operateur_extra_total = (
                float(dossier["part_operateur_extrat"] or 0)
                + float(dossier["part_operateur_up_medecin"] or 0)
                + float(dossier["part_operateur_up_clinique"] or 0)
            )

            data_row = [
                dossier["id_dossier"],
                dossier["doctor_name"],
                dossier["patient_name"],
                dossier["patient_oid_his"],
                (
                    dossier["acte_date"].strftime("%d/%m/%Y")
                    if dossier["acte_date"]
                    else ""
                ),
                dossier["code_cnas"],
                dossier["name_acte_kt"],
                dossier["convention"],
                "Oui" if dossier["urgence"] else "Non",
                "Oui" if dossier["vip"] else "Non",
                dossier["nbr_nuite"] or 0,
                dossier["nbr_nuite_conjoint"] or 0,
                float(dossier["prix_conjoint"] or 0),
                float(dossier["extras"] or 0),
                float(dossier["up_medecin"] or 0),
                float(dossier["up_clinique"] or 0),
                dossier["anesthesiste_name"].strip() or "",
                dossier["reanimateur_name"].strip() or "",
                dossier["duree_operation"] or "",
                float(dossier["prix_hospitalisation"] or 0),
                float(dossier["part_operateur_acte"] or 0),
                float(dossier["part_operateur_extrat"] or 0),
                float(dossier["part_operateur_up_medecin"] or 0),
                float(dossier["part_operateur_up_clinique"] or 0),
                part_operateur_extra_total,
                float(dossier["part_operateur"] or 0),
                float(dossier["prix_dossier_esp"] or 0),
                float(dossier["prix_dossier_convention"] or 0),
            ]

            for col_num, value in enumerate(data_row, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = value
                cell.border = border

                # Alignement selon le type
                if isinstance(value, (int, float)) and col_num > 9:
                    cell.alignment = right_alignment
                    if col_num >= 12:  # Colonnes monétaires
                        cell.number_format = "#,##0.00"
                else:
                    cell.alignment = center_alignment

                # Colorer les lignes urgentes
                if dossier["urgence"]:
                    cell.fill = PatternFill(
                        start_color="FFE0E0", end_color="FFE0E0", fill_type="solid"
                    )

        # Ajuster les largeurs de colonnes
        column_widths = {
            "A": 12,
            "B": 20,
            "C": 25,
            "D": 12,
            "E": 15,
            "F": 30,
            "G": 12,
            "H": 10,
            "I": 8,
            "J": 12,
            "K": 15,
            "L": 15,
            "M": 12,
            "N": 12,
            "O": 12,
            "P": 20,
            "Q": 20,
            "R": 15,
            "S": 18,
            "T": 18,
            "U": 18,
            "V": 18,
            "W": 18,
            "X": 20,
            "Y": 18,
            "Z": 20,
        }

        for col, width in column_widths.items():
            ws.column_dimensions[col].width = width

        # Ajouter ligne de totaux
        total_row = len(dossiers) + 2
        ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True)
        ws.cell(row=total_row, column=1).fill = PatternFill(
            start_color="F0F0F0", end_color="F0F0F0", fill_type="solid"
        )

        # Formules pour les totaux (colonnes numériques)
        for col in [12, 13, 14, 15, 19, 20, 21, 22, 23, 24, 25, 26]:
            cell = ws.cell(row=total_row, column=col)
            cell.value = f"=SUM({get_column_letter(col)}2:{get_column_letter(col)}{total_row - 1})"
            cell.font = Font(bold=True)
            cell.number_format = "#,##0.00"
            cell.alignment = right_alignment
            cell.fill = PatternFill(
                start_color="F0F0F0", end_color="F0F0F0", fill_type="solid"
            )

        # Sauvegarder dans un buffer
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # Générer le nom du fichier
        filename = f"Dossiers_KT_{start_date or 'tous'}_{end_date or 'tous'}.xlsx"

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        flash(f"Erreur lors de l'export : {str(e)}", "danger")
        return redirect(url_for("kt_dossier_patient"))

    finally:
        cursor.close()
        connection.close()


@app.route("/supprimer_dossier_kt", methods=["POST"])
@login_required
@handle_errors()
def supprimer_dossier_kt():
    """Supprime un dossier KT et ses données associées."""
    id_dossier = request.form.get("id_dossier")

    if not id_dossier:
        flash("ID dossier manquant.", "danger")
        return redirect(url_for("kt_dossier_patient"))

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM kt_dossier_actes WHERE id_dossier = %s", (id_dossier,)
        )
        cursor.execute(
            "DELETE FROM kt_doctor_situations WHERE id_dossier = %s", (id_dossier,)
        )
        cursor.execute(
            "DELETE FROM kt_dossier_patient WHERE id_dossier = %s", (id_dossier,)
        )

        connection.commit()
        flash("Dossier supprimé avec succès.", "success")

    except Exception as e:
        connection.rollback()
        flash(f"Erreur lors de la suppression : {str(e)}", "danger")

    finally:
        connection.close()

    return redirect(url_for("kt_dossier_patient"))


@app.route("/api/kt_personnel_anesthesie", methods=["GET"])
@login_required
def api_kt_personnel_anesthesie():
    """Retourne la liste du personnel d'anesthésie pour les selects"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
                       SELECT p.id_personnel_anesthesie,
                              CONCAT(p.prenom, ' ', p.nom) as nom_complet,
                              p.id_type_intervenant,
                              t.nom_type
                       FROM anesthesie_personnel p
                                JOIN anesthesie_intervenant_type t ON p.id_type_intervenant = t.id_type_intervenant
                       WHERE p.est_actif = 1
                       ORDER BY t.nom_type, p.nom, p.prenom
                       """
        )

        personnel = cursor.fetchall()
        return jsonify({"success": True, "personnel": personnel})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route("/kt_dossier_detail/<int:id_dossier>")
@login_required
@handle_errors()
def kt_dossier_detail(id_dossier):
    """Affiche les détails complets d'un dossier KT"""

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer les informations du dossier principal
        cursor.execute(
            """
                       SELECT d.*,
                              CONCAT(COALESCE(doc.first_name, ''), ' ', COALESCE(doc.last_name, '')) as doctor_name,
                              COALESCE(s.name_specialty, '')                                         as specialty_name,
                              CONCAT(COALESCE(anes.prenom, ''), ' ', COALESCE(anes.nom, ''))         as anesthesiste_name,
                              CONCAT(COALESCE(rea.prenom, ''), ' ', COALESCE(rea.nom, ''))           as reanimateur_name,
                              anes.id_type_intervenant                                               as anesthesiste_type,
                              rea.id_type_intervenant                                                as reanimateur_type
                       FROM kt_dossier_patient d
                              LEFT JOIN doctors doc ON d.id_doctor = doc.id
                                LEFT JOIN specialty s ON doc.id_specialty = s.id_specialty
                                LEFT JOIN anesthesie_personnel anes ON d.id_anesthesiste = anes.id_personnel_anesthesie
                                LEFT JOIN anesthesie_personnel rea ON d.id_reanimateur = rea.id_personnel_anesthesie
                       WHERE d.id_dossier = %s
                       """,
            (id_dossier,),
        )

        dossier = cursor.fetchone()

        if not dossier:
            flash("Dossier non trouvé.", "danger")
            return redirect(url_for("kt_dossier_patient"))

        # Récupérer les actes KT du dossier
        cursor.execute(
            """
                       SELECT da.*,
                              ak.name_acte_kt,
                              ak.code_cnas
                       FROM kt_dossier_actes da
                                LEFT JOIN kt_actes ak ON da.id_acte = ak.id_acte
                       WHERE da.id_dossier = %s
                       ORDER BY da.id_dossier
                       """,
            (id_dossier,),
        )

        actes = cursor.fetchall()

        # Récupérer les actes d'anesthésie
        cursor.execute(
            """
                       SELECT da.*,
                              aa.nom_acte                  as nom_acte_anesthesie,
                              CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                              ti.nom_type                  as type_intervenant
                       FROM kt_dossier_anesthesie da
                                JOIN anesthesie_type_acte aa ON da.id_acte_anesthesie = aa.id_acte_anesthesie
                                JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
                                JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
                       WHERE da.id_dossier = %s
                       ORDER BY da.id_dossier_anesthesie
                       """,
            (id_dossier,),
        )

        actes_anesthesie = cursor.fetchall()

        # Récupérer tous les médecins pour l'édition
        cursor.execute(
            """
                       SELECT id, CONCAT(first_name, ' ', last_name) as name
                       FROM doctors
                       ORDER BY first_name, last_name
                       """
        )
        doctors = cursor.fetchall()

        # Récupérer tous les actes KT pour l'édition
        cursor.execute("SELECT * FROM kt_actes ORDER BY name_acte_kt")
        acts_kt = cursor.fetchall()

        return render_template(
            "prestation_kt/kt_dossier_detail.html",
            dossier=dossier,
            actes=actes,
            actes_anesthesie=actes_anesthesie,
            doctors=doctors,
            acts_kt=acts_kt,
            title=f"Dossier #{id_dossier}",
            user=g.user,
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        flash(f"Erreur lors du chargement du dossier: {str(e)}", "danger")
        return redirect(url_for("kt_dossier_patient"))

    finally:
        cursor.close()
        connection.close()


@app.route("/modifier_dossier_kt/<int:id_dossier>", methods=["POST"])
@login_required
@handle_errors()
def modifier_dossier_kt(id_dossier):
    """Modifie un dossier KT existant"""

    def get_form_value(field, default=None, cast_func=None):
        value = request.form.get(field, default)
        if cast_func:
            try:
                return cast_func(value) if value else default
            except ValueError:
                flash(f"Le champ '{field}' est invalide.", "danger")
                return None
        return value

    # Récupération des données du formulaire
    form_data = {
        "id_doctor": request.form["id_doctor"],
        "patient": request.form["patient"],
        "acte_date": request.form["acte_date"],
        "nbr_nuite": get_form_value("nbr_nuite", 0, int),
        "vip": request.form.get("vip"),
        "nbr_nuite_conjoint": get_form_value("nbr_nuite_conjoint", 0, int),
        "urgenceCheck": request.form.get("urgenceCheck"),
        "extra_percentage": get_form_value("extraPercentage", 20, int),
        "extras": get_form_value("extras", 0, Decimal),
        "up_medecin": get_form_value("up_medecin", 0, Decimal),
        "up_clinique": get_form_value("up_clinique", 0, Decimal),
        "id_anesthesiste": get_form_value(
            "id_anesthesiste", None, lambda x: int(x) if x and x != "" else None
        ),
        "id_reanimateur": get_form_value(
            "id_reanimateur", None, lambda x: int(x) if x and x != "" else None
        ),
        "duree_operation": get_form_value(
            "duree_operation", None, lambda x: int(x) if x and x != "" else None
        ),
        "id_acte_anesthesie": get_form_value(
            "id_acte_anesthesie", None, lambda x: int(x) if x and x != "" else None
        ),
        "observations_anesthesie": get_form_value("observations_anesthesie", ""),
    }

    # Validation anesthésie
    if form_data["id_anesthesiste"] or form_data["id_reanimateur"]:
        if not form_data["duree_operation"]:
            flash(
                "La durée d'opération est obligatoire si un anesthésiste ou réanimateur est présent.",
                "danger",
            )
            return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))
        if not form_data["id_acte_anesthesie"]:
            flash(
                "Le type d'acte d'anesthésie est obligatoire si un anesthésiste ou réanimateur est présent.",
                "danger",
            )
            return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))

    # Import de la fonction de calcul
    # Filtrer les actes KT
    import re

    acte_keys = [key for key in request.form.keys() if re.match(r"id_acte_\d+$", key)]

    if not acte_keys:
        flash("Vous devez avoir au moins un acte médical KT.", "danger")
        return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))

    # Constantes de prix
    prix_nuit_extra_standard = Decimal("15000")
    prix_nuit_extra_vip = Decimal("30000")
    prix_nuit_vip = Decimal("18000")
    prix_hospitalisation = Decimal("0")
    kt_nights = 0

    total_part_operateur = Decimal("0")
    total_part_clinique = Decimal("0")
    prix_dossier_convention = Decimal("0")
    prix_dossier_esp = Decimal("0")
    part_operateur = Decimal("0")
    part_clinique_convention = Decimal("0")
    part_clinique_esp = Decimal("0")

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Calculs de base
        prix_conjoint = Decimal(form_data["nbr_nuite_conjoint"]) * Decimal("8000")
        prix_extras = form_data["extras"]
        part_operateur_extrat = (
            form_data["extras"]
            * Decimal(form_data["extra_percentage"])
            / Decimal("100")
        )

        # Calculs UP Médecin
        part_operateur_up_medecin = form_data["up_medecin"] * Decimal("0.80")
        part_clinique_up_medecin = form_data["up_medecin"] * Decimal("0.20")

        # Calculs UP Clinique
        part_operateur_up_clinique = form_data["up_clinique"] * Decimal("0.20")
        part_clinique_up_clinique = form_data["up_clinique"] * Decimal("0.80")

        # Mise à jour du dossier principal
        cursor.execute(
            """
                       UPDATE kt_dossier_patient
                       SET id_doctor                  = %s,
                           patient                    = %s,
                           acte_date                  = %s,
                           nbr_nuite                  = %s,
                           vip                        = %s,
                           nbr_nuite_conjoint         = %s,
                           prix_conjoint              = %s,
                           extras                     = %s,
                           part_operateur_extrat      = %s,
                           up_medecin                 = %s,
                           up_clinique                = %s,
                           part_operateur_up_medecin  = %s,
                           part_operateur_up_clinique = %s,
                           id_anesthesiste            = %s,
                           id_reanimateur             = %s,
                           duree_operation            = %s
                       WHERE id_dossier = %s
                       """,
            (
                form_data["id_doctor"],
                form_data["patient"],
                form_data["acte_date"],
                form_data["nbr_nuite"],
                form_data["vip"],
                form_data["nbr_nuite_conjoint"],
                prix_conjoint,
                prix_extras,
                part_operateur_extrat,
                form_data["up_medecin"],
                form_data["up_clinique"],
                part_operateur_up_medecin,
                part_operateur_up_clinique,
                form_data["id_anesthesiste"],
                form_data["id_reanimateur"],
                form_data["duree_operation"],
                id_dossier,
            ),
        )
        connection.commit()

        # Supprimer les anciens actes d'anesthésie
        cursor.execute(
            "DELETE FROM kt_dossier_anesthesie WHERE id_dossier = %s", (id_dossier,)
        )
        connection.commit()

        from app.anesthesie_honoraires.anesthesie_honoraires import (
            calculer_honoraires_anesthesie,
            get_tarif_forfaitaire_anesthesie,
        )

        prix_anesthesie_dossier = Decimal("0")

        # Recréer les actes d'anesthésie si nécessaire
        if form_data["id_acte_anesthesie"] and form_data["duree_operation"]:
            # ✅ UN SEUL TARIF FORFAITAIRE (prix fixe pour le dossier)
            prix_anesthesie_dossier = get_tarif_forfaitaire_anesthesie(
                cursor, form_data["id_acte_anesthesie"]
            )

            # Pour l'anesthésiste
            if form_data["id_anesthesiste"]:
                cursor.execute(
                    """
                    SELECT id_type_intervenant
                    FROM anesthesie_personnel
                    WHERE id_personnel_anesthesie = %s
                """,
                    (form_data["id_anesthesiste"],),
                )

                personnel_data = cursor.fetchone()
                if personnel_data:
                    id_type = personnel_data["id_type_intervenant"]

                    # ✅ HONORAIRES (rémunération variable)
                    honoraires = calculer_honoraires_anesthesie(
                        cursor,
                        form_data["id_acte_anesthesie"],
                        id_type,
                        form_data["duree_operation"],
                    )

                    cursor.execute(
                        """
                        INSERT INTO kt_dossier_anesthesie
                        (id_dossier, id_acte_anesthesie, id_personnel_anesthesie,
                         duree_reelle, honoraires_calcules, observations)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            form_data["id_acte_anesthesie"],
                            form_data["id_anesthesiste"],
                            form_data["duree_operation"],
                            honoraires,
                            form_data["observations_anesthesie"],
                        ),
                    )
                    connection.commit()

            # Pour le réanimateur
            if form_data["id_reanimateur"]:
                cursor.execute(
                    """
                    SELECT id_type_intervenant
                    FROM anesthesie_personnel
                    WHERE id_personnel_anesthesie = %s
                """,
                    (form_data["id_reanimateur"],),
                )

                personnel_data = cursor.fetchone()
                if personnel_data:
                    id_type = personnel_data["id_type_intervenant"]

                    # ✅ HONORAIRES (rémunération variable)
                    honoraires = calculer_honoraires_anesthesie(
                        cursor,
                        form_data["id_acte_anesthesie"],
                        id_type,
                        form_data["duree_operation"],
                    )

                    cursor.execute(
                        """
                        INSERT INTO kt_dossier_anesthesie
                        (id_dossier, id_acte_anesthesie, id_personnel_anesthesie,
                         duree_reelle, honoraires_calcules, observations)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            form_data["id_acte_anesthesie"],
                            form_data["id_reanimateur"],
                            form_data["duree_operation"],
                            honoraires,
                            form_data["observations_anesthesie"],
                        ),
                    )
                    connection.commit()

        # Supprimer les anciens actes KT
        cursor.execute(
            "DELETE FROM kt_dossier_actes WHERE id_dossier = %s", (id_dossier,)
        )
        connection.commit()

        # Recréer les actes KT
        for key in acte_keys:
            acte_id = request.form.get(key)

            if not acte_id:
                flash(
                    "Veuillez sélectionner un type d'acte pour tous les actes.",
                    "danger",
                )
                connection.rollback()
                return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))

            index = key.split("_")[-1]

            # Récupérer l'id_convention (nullable: None = payante hors convention)
            id_convention_raw = request.form.get(f"id_convention_{index}")
            id_convention = (
                int(id_convention_raw)
                if id_convention_raw and id_convention_raw.strip()
                else None
            )

            # Récupérer le label de convention pour rétro-compatibilité
            convention_label = request.form.get(f"convention_acte_kt_{index}", "")
            if not convention_label:
                if id_convention:
                    cursor.execute(
                        "SELECT code_convention FROM kt_conventions WHERE id_convention = %s",
                        (id_convention,),
                    )
                    row = cursor.fetchone()
                    convention_label = (
                        row["code_convention"].lower() if row else "convention"
                    )
                elif form_data["urgenceCheck"]:
                    convention_label = "urgence"
                else:
                    convention_label = "payante"

            # Récupérer les données de base de l'acte (nbr_nuit)
            cursor.execute(
                "SELECT id_acte, nbr_nuit FROM kt_actes WHERE id_acte = %s", (acte_id,)
            )
            kt_data = cursor.fetchone()

            if not kt_data:
                flash(f"L'acte ID {acte_id} n'existe pas.", "danger")
                connection.rollback()
                return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))

            # ✅ RÉSOLUTION DU PRIX via la chaîne de fallback
            est_urgence = bool(form_data["urgenceCheck"])
            prix_resolu, part_operateur_resolu, source = resoudre_prix(
                cursor,
                int(acte_id),
                id_convention,
                int(form_data["id_doctor"]),
                est_urgence,
            )

            # Répartition convention vs espèces
            if id_convention and not est_urgence:
                part_clinique_convention = prix_resolu
                part_clinique_esp = Decimal("0")
            else:
                part_clinique_esp = prix_resolu
                part_clinique_convention = Decimal("0")

            part_operateur = part_operateur_resolu
            total_part_clinique += prix_resolu
            total_part_operateur += part_operateur_resolu

            cursor.execute(
                """
                INSERT INTO kt_dossier_actes
                (id_dossier, id_acte, id_convention, convention, part_operateur,
                 part_clinique_convention, part_clinique_esp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    id_dossier,
                    acte_id,
                    id_convention,
                    convention_label,
                    part_operateur,
                    part_clinique_convention,
                    part_clinique_esp,
                ),
            )
            connection.commit()

            prix_dossier_convention += part_clinique_convention
            prix_dossier_esp += part_clinique_esp
            part_clinique_convention = Decimal("0")
            part_clinique_esp = Decimal("0")
            kt_nights += kt_data["nbr_nuit"]

        # Ajout des prix supplémentaires
        prix_dossier_esp += (
            prix_extras
            + form_data["up_medecin"]
            + form_data["up_clinique"]
            + prix_anesthesie_dossier
        )

        # Hospitalisation
        extra_nights = form_data["nbr_nuite"] - kt_nights
        if extra_nights > 0:
            prix_hospitalisation += Decimal(extra_nights) * (
                prix_nuit_extra_vip if form_data["vip"] else prix_nuit_extra_standard
            )
        prix_hospitalisation += Decimal(kt_nights) * (
            prix_nuit_vip if form_data["vip"] else Decimal("0")
        )

        # Total part opérateur
        total_part_operateur += (
            part_operateur_extrat
            + part_operateur_up_medecin
            + part_operateur_up_clinique
        )

        # Mise à jour finale avec les totaux
        cursor.execute(
            """
                       UPDATE kt_dossier_patient
                       SET urgence                 = %s,
                           prix_hospitalisation    = %s,
                           part_operateur          = %s,
                           prix_dossier_convention = %s,
                           prix_dossier_esp        = %s
                       WHERE id_dossier = %s
                       """,
            (
                form_data["urgenceCheck"],
                prix_hospitalisation,
                total_part_operateur,
                prix_dossier_convention,
                prix_dossier_esp,
                id_dossier,
            ),
        )
        connection.commit()

        # Mettre à jour la situation médecin
        cursor.execute(
            """
                       UPDATE kt_doctor_situations
                       SET part_operateur = %s
                       WHERE id_dossier = %s
                       """,
            (total_part_operateur, id_dossier),
        )
        connection.commit()

        flash("Dossier modifié avec succès.", "success")
        return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))

    except Exception as e:
        if connection:
            connection.rollback()
        flash(f"Une erreur est survenue : {str(e)}", "danger")
        import traceback

        traceback.print_exc()
        return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/upload_compte_rendu_kt", methods=["POST"])
@login_required
@handle_errors()
def upload_compte_rendu_kt():
    """Upload un compte-rendu Word pour un dossier KT"""
    from datetime import datetime

    id_dossier = request.form.get("id_dossier")

    if not id_dossier:
        return jsonify({"success": False, "error": "ID dossier manquant"}), 400

    if "compte_rendu_file" not in request.files:
        return jsonify({"success": False, "error": "Aucun fichier fourni"}), 400

    file = request.files["compte_rendu_file"]

    if file.filename == "":
        return jsonify({"success": False, "error": "Nom de fichier vide"}), 400

    # Vérifier l'extension
    if not file.filename.lower().endswith((".doc", ".docx")):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Seuls les fichiers .doc et .docx sont acceptés",
                }
            ),
            400,
        )

    # Vérifier la taille (10 MB max)
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)

    if file_length > 10 * 1024 * 1024:  # 10 MB
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Le fichier est trop volumineux (max 10 MB)",
                }
            ),
            400,
        )

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Vérifier si un compte-rendu existe déjà
        cursor.execute(
            """
            SELECT compte_rendu_path
            FROM kt_dossier_patient
            WHERE id_dossier = %s
                       """,
            (id_dossier,),
        )

        existing = cursor.fetchone()

        # Supprimer l'ancien fichier si existe
        if existing and existing["compte_rendu_path"]:
            old_file_path = os.path.join(
                app.config["UPLOAD_FOLDER"], existing["compte_rendu_path"]
            )
            if os.path.exists(old_file_path):

                try:
                    os.remove(old_file_path)
                except Exception as e:
                    logger.error(
                        f"Erreur lors de la suppression de l'ancien fichier : {e}"
                    )

        # Sauvegarder le nouveau fichier
        save_path = f"kt_comptes_rendus/{id_dossier}"
        file_path = save_files([file], save_path)

        if not file_path:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Erreur lors de la sauvegarde du fichier",
                    }
                ),
                500,
            )

        # Mettre à jour la base de données
        cursor.execute(
            """
            UPDATE kt_dossier_patient
            SET compte_rendu_path         = %s,
                compte_rendu_nom_original = %s,
                compte_rendu_date_upload  = %s
            WHERE id_dossier = %s
                       """,
            (file_path, file.filename, datetime.now(), id_dossier),
        )

        connection.commit()

        return jsonify(
            {
                "success": True,
                "message": "Compte-rendu uploadé avec succès",
                "file_path": file_path,
            }
        )

    except Exception as e:
        connection.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/download_compte_rendu_kt/<int:id_dossier>")
@login_required
@handle_errors()
def download_compte_rendu_kt(id_dossier):
    """Télécharge le compte-rendu d'un dossier KT"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT compte_rendu_path, compte_rendu_nom_original
            FROM kt_dossier_patient
            WHERE id_dossier = %s
                       """,
            (id_dossier,),
        )

        dossier = cursor.fetchone()

        if not dossier or not dossier["compte_rendu_path"]:
            flash("Aucun compte-rendu trouvé pour ce dossier", "warning")
            return redirect(url_for("kt_dossier_patient"))

        # Utiliser le chemin relatif stocké dans la DB
        relative_path = dossier["compte_rendu_path"]

        # Construire le chemin absolu vers le dossier uploads
        uploads_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "uploads"
        )
        file_path = os.path.join(uploads_path, relative_path)

        # Vérifier si le fichier existe
        if not os.path.exists(file_path):
            flash("Le fichier du compte-rendu n'existe plus", "danger")
            return redirect(url_for("kt_dossier_patient"))

        # Extraire le répertoire et le nom du fichier
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)

        return send_from_directory(
            directory,
            filename,
            as_attachment=True,
            download_name=dossier["compte_rendu_nom_original"],
        )

    except Exception as e:
        flash(f"Erreur lors du téléchargement : {str( e )}", "danger")
        import traceback

        traceback.print_exc()  # Pour debug
        return redirect(url_for("kt_dossier_patient"))

    finally:
        cursor.close()
        connection.close()


@app.route("/api/check_compte_rendu_kt/<int:id_dossier>")
@login_required
@handle_errors()
def api_check_compte_rendu_kt(id_dossier):
    """Vérifie si un compte-rendu existe pour un dossier"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT compte_rendu_path, compte_rendu_nom_original, compte_rendu_date_upload
            FROM kt_dossier_patient
            WHERE id_dossier = %s
                       """,
            (id_dossier,),
        )

        result = cursor.fetchone()

        return jsonify(
            {
                "exists": bool(result and result["compte_rendu_path"]),
                "filename": result["compte_rendu_nom_original"] if result else None,
                "upload_date": (
                    result["compte_rendu_date_upload"].strftime("%d/%m/%Y %H:%M")
                    if result and result["compte_rendu_date_upload"]
                    else None
                ),
            }
        )

    finally:
        cursor.close()
        connection.close()


# ============================================================
# EXPORT PDF INDIVIDUEL — DOSSIER KT
# ============================================================


@app.route("/kt_dossier/<int:id_dossier>/export-pdf")
@login_required
@handle_errors()
def kt_dossier_export_pdf(id_dossier):
    """Export PDF d'un dossier KT avec QR code"""
    import base64 as b64module
    from io import BytesIO

    from flask import make_response
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # ── Dossier principal ──
        cursor.execute(
            """
            SELECT d.*,
                   CONCAT(COALESCE(doc.first_name, ''), ' ', COALESCE(doc.last_name, '')) as doctor_name,
                   COALESCE(s.name_specialty, '')                                         as specialty_name,
                   CONCAT(COALESCE(anes.prenom, ''), ' ', COALESCE(anes.nom, ''))         as anesthesiste_name,
                   CONCAT(COALESCE(rea.prenom, ''), ' ', COALESCE(rea.nom, ''))           as reanimateur_name
            FROM kt_dossier_patient d
                LEFT JOIN doctors doc ON d.id_doctor = doc.id
                LEFT JOIN specialty s ON doc.id_specialty = s.id_specialty
                LEFT JOIN anesthesie_personnel anes ON d.id_anesthesiste = anes.id_personnel_anesthesie
                LEFT JOIN anesthesie_personnel rea ON d.id_reanimateur = rea.id_personnel_anesthesie
            WHERE d.id_dossier = %s
        """,
            (id_dossier,),
        )
        dossier = cursor.fetchone()

        if not dossier:
            flash("Dossier non trouvé", "danger")
            return redirect(url_for("kt_dossier_patient"))

        # ── Actes KT ──
        cursor.execute(
            """
            SELECT da.*, ak.name_acte_kt, ak.code_cnas
            FROM kt_dossier_actes da
                LEFT JOIN kt_actes ak ON da.id_acte = ak.id_acte
            WHERE da.id_dossier = %s
            ORDER BY da.id_dossier
        """,
            (id_dossier,),
        )
        actes = cursor.fetchall()

        # ── Anesthésie ──
        cursor.execute(
            """
            SELECT da.*,
                   aa.nom_acte                  as nom_acte_anesthesie,
                   CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                   ti.nom_type                  as type_intervenant
            FROM kt_dossier_anesthesie da
                JOIN anesthesie_type_acte aa ON da.id_acte_anesthesie = aa.id_acte_anesthesie
                JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
                JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
            WHERE da.id_dossier = %s
        """,
            (id_dossier,),
        )
        actes_anesthesie = cursor.fetchall()

        # ════════════════════════════════════════
        # GÉNÉRATION PDF
        # ════════════════════════════════════════
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.2 * cm,
            leftMargin=1.2 * cm,
            topMargin=1 * cm,
            bottomMargin=1.5 * cm,
            title=f"Dossier KT #{id_dossier}",
            author="Clinique INAYA",
        )

        story = []
        styles = getSampleStyleSheet()

        # ── Styles personnalisés ──
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#6366f1"),
            fontName="Helvetica-Bold",
            spaceAfter=4,
        )
        header_style = ParagraphStyle(
            "CustomHeader",
            parent=styles["Heading2"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=3,
            spaceBefore=6,
        )
        normal_style = ParagraphStyle(
            "CustomNormal", parent=styles["Normal"], fontSize=9, leading=12
        )
        bold_style = ParagraphStyle(
            "CustomBold", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold"
        )

        # ── Logo + QR Code ──
        try:
            logo = Image(
                "app/static/images/entet_inaya.png", width=10 * cm, height=3 * cm
            )
        except:
            logo = Paragraph("", styles["Normal"])

        qr_img_flow = None
        if dossier.get("qr_uuid"):
            try:
                from app.utils.qr_utils import generer_qr_base64

                qr_b64_str = generer_qr_base64("PRESTATION KT", dossier["qr_uuid"])
                qr_buf = BytesIO(b64module.b64decode(qr_b64_str))
                qr_img_flow = Image(qr_buf, width=2.5 * cm, height=2.5 * cm)
            except:
                pass

        if qr_img_flow:
            header_table = Table(
                [[logo, qr_img_flow]], colWidths=[doc.width - 3 * cm, 3 * cm]
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
            story.append(header_table)
        else:
            story.append(logo)
        story.append(Spacer(1, 0.3 * cm))

        # ── Titre ──
        story.append(
            Paragraph(
                f"Dossier Cathétérisme N° KT-{dossier.get('id_dossier', 0):05d}",
                title_style,
            )
        )
        story.append(Spacer(1, 0.3 * cm))

        # Séparateur
        sep = Table([[""]], colWidths=[doc.width])
        sep.setStyle(
            TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#6366f1"))])
        )
        story.append(sep)
        story.append(Spacer(1, 0.4 * cm))

        # ── 1. Informations Générales ──
        story.append(Paragraph("1. INFORMATIONS GÉNÉRALES", header_style))

        def fmt_date(d):
            if d:
                try:
                    return d.strftime("%d/%m/%Y")
                except:
                    return str(d)
            return "N/A"

        def fmt_money(v):
            try:
                return f"{float(v or 0):,.2f} DA"
            except:
                return "0.00 DA"

        info_data = [
            ["Patient:", str(dossier.get("patient", "N/A"))],
            ["Médecin:", str(dossier.get("doctor_name", "N/A"))],
            ["Spécialité:", str(dossier.get("specialty_name", "N/A"))],
            ["Date de l'acte:", fmt_date(dossier.get("acte_date"))],
            ["Durée opération:", f"{dossier.get('duree_operation', 0) or 0} min"],
            ["VIP:", "Oui" if dossier.get("vip") else "Non"],
            ["Créé par:", str(dossier.get("created_by_name", "N/A"))],
        ]

        info_table = Table(info_data, colWidths=[4 * cm, doc.width - 4 * cm])
        info_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f7ff")),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(info_table)
        story.append(Spacer(1, 0.4 * cm))

        # ── 2. Actes KT ──
        if actes:
            story.append(Paragraph("2. ACTES CATHÉTÉRISME", header_style))
            actes_data = [["Acte", "Code CNAS", "Prix", "Part Opérateur"]]
            for a in actes:
                actes_data.append(
                    [
                        str(a.get("name_acte_kt", "N/A"))[:40],
                        str(a.get("code_cnas", "—")),
                        fmt_money(a.get("prix")),
                        fmt_money(a.get("part_operateur")),
                    ]
                )

            actes_table = Table(
                actes_data, colWidths=[7 * cm, 3 * cm, 3 * cm, 3.5 * cm]
            )
            actes_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f5f5f5")],
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(actes_table)
            story.append(Spacer(1, 0.4 * cm))

        # ── 3. Anesthésie ──
        if actes_anesthesie:
            story.append(Paragraph("3. ANESTHÉSIE", header_style))
            anes_data = [["Acte", "Intervenant", "Type", "Tarif"]]
            for a in actes_anesthesie:
                anes_data.append(
                    [
                        str(a.get("nom_acte_anesthesie", "N/A"))[:35],
                        str(a.get("nom_personnel", "N/A")),
                        str(a.get("type_intervenant", "N/A")),
                        fmt_money(a.get("tarif_forfaitaire")),
                    ]
                )

            anes_table = Table(
                anes_data, colWidths=[5 * cm, 4.5 * cm, 3.5 * cm, 3.5 * cm]
            )
            anes_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10b981")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f0fdf4")],
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(anes_table)
            story.append(Spacer(1, 0.4 * cm))

        # ── 4. Hospitalisation ──
        nbr_nuite = dossier.get("nbr_nuite", 0) or 0
        nbr_conj = dossier.get("nbr_nuite_conjoint", 0) or 0
        if nbr_nuite > 0 or nbr_conj > 0:
            story.append(Paragraph("4. HOSPITALISATION", header_style))
            hosp_data = []
            if nbr_nuite > 0:
                hosp_data.append(["Nuitées patient:", str(nbr_nuite)])
            if nbr_conj > 0:
                hosp_data.append(["Nuitées conjoint:", str(nbr_conj)])
                hosp_data.append(
                    ["Prix conjoint:", fmt_money(dossier.get("prix_conjoint"))]
                )
            if hosp_data:
                hosp_table = Table(hosp_data, colWidths=[4 * cm, doc.width - 4 * cm])
                hosp_table.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f7ff")),
                            ("PADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )
                story.append(hosp_table)
            story.append(Spacer(1, 0.4 * cm))

        # ── 5. Récapitulatif Financier ──
        story.append(Paragraph("5. RÉCAPITULATIF FINANCIER", header_style))

        recap_data = []

        def add_if_pos(label, value):
            try:
                v = float(value or 0)
                if v > 0:
                    recap_data.append([label, fmt_money(v)])
            except:
                pass

        add_if_pos("UP Médecin:", dossier.get("up_medecin"))
        add_if_pos("UP Clinique:", dossier.get("up_clinique"))
        add_if_pos("Extras:", dossier.get("extras"))
        add_if_pos("Part opérateur (extras):", dossier.get("part_operateur_extrat"))
        add_if_pos(
            "Part opérateur (UP Méd.):", dossier.get("part_operateur_up_medecin")
        )
        add_if_pos(
            "Part opérateur (UP Clin.):", dossier.get("part_operateur_up_clinique")
        )
        add_if_pos("Prix conjoint:", dossier.get("prix_conjoint"))

        # Separator
        recap_data.append(["", ""])

        # Totaux
        prix_total = float(dossier.get("prix_total", 0) or 0)
        montant_paye = float(dossier.get("montant_paye", 0) or 0)
        difference = prix_total - montant_paye

        recap_data.extend(
            [
                ["TOTAL:", fmt_money(prix_total)],
                ["Montant payé:", fmt_money(montant_paye)],
                ["DIFFÉRENCE:", fmt_money(difference)],
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
        story.append(recap_table)

        # ── Build PDF ──
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()

        # ── Réponse ──
        patient_name = str(dossier.get("patient", "Inconnu")).replace(" ", "_")
        date_acte = fmt_date(dossier.get("acte_date"))
        filename = f"Dossier_KT-{id_dossier:05d}_{patient_name}_{date_acte}.pdf"

        response = make_response(pdf_data)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        import traceback

        app.logger.error(f"Erreur export PDF KT: {str(e)}")
        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors de la génération du PDF: {str(e)}", "danger")
        return redirect(url_for("kt_dossier_detail", id_dossier=id_dossier))

    finally:
        cursor.close()
        connection.close()
