# app/medecin_interne_actes.py
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal

from flask import flash, g, jsonify, redirect, render_template, request, url_for

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


@contextmanager
def get_cursor():
    """Context manager pour gérer automatiquement la connexion DB"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def build_pagination_url(**kwargs):
    """Construit l'URL de pagination en conservant les filtres"""
    params = request.args.copy()
    for key, value in kwargs.items():
        if value is not None:
            params[key] = value
        elif key in params:
            params.pop(key)
    return "?" + "&".join(f"{k}={v}" for k, v in params.items())


def get_pourcentage_medecin_interne(cursor, id_doctor):
    """
    Retourne le pourcentage du médecin interne.
    Lit la valeur depuis la colonne `pourcentage_medecin_interne` de la table `doctors`.
    Fallback à 50% si non configuré.
    """
    if not id_doctor:
        return Decimal("50.00")

    cursor.execute(
        """
        SELECT pourcentage_medecin_interne
        FROM doctors
        WHERE id = %s
    """,
        (id_doctor,),
    )
    row = cursor.fetchone()

    if row and row.get("pourcentage_medecin_interne") is not None:
        return Decimal(str(row["pourcentage_medecin_interne"]))
    return Decimal("50.00")


def get_paiement_status_for_list(cursor, actes):
    """
    Enrichit la liste des actes avec les informations de paiement

    Args:
        cursor: Curseur de base de données
        actes: Liste des actes à enrichir

    Returns:
        Liste des actes enrichie avec paiement_status
    """
    if not actes:
        return actes

    # Récupérer les IDs des actes
    acte_ids = [acte["id_acte"] for acte in actes]
    placeholders = ",".join(["%s"] * len(acte_ids))

    # Récupérer les résumés de paiements
    query = f"""
        SELECT 
            a.id_acte,
            a.prix_acte_base,
            a.mode_calcul,
            a.prix_consommables_specifiques,
            a.prix_hospitalisation_hors_forfait,
            a.prix_supplements,
            a.prix_actes_supplementaires,
            a.prix_anesthesie,

            -- Montant total selon le mode
            CASE 
                WHEN a.mode_calcul = 'PRIX_BASE' THEN 
                    a.prix_acte_base + 
                    COALESCE(a.prix_consommables_specifiques, 0) + 
                    COALESCE(a.prix_hospitalisation_hors_forfait, 0) + 
                    COALESCE(a.prix_supplements, 0) + 
                    COALESCE(a.prix_actes_supplementaires, 0) + 
                    COALESCE(a.prix_anesthesie, 0)
                ELSE 
                    a.prix_acte_base
            END AS montant_total,

            -- Total payé
            COALESCE(SUM(CASE WHEN p.est_annule = FALSE THEN p.montant_paye ELSE 0 END), 0) AS total_paye,

            -- Nombre de paiements
            COUNT(CASE WHEN p.est_annule = FALSE THEN 1 END) AS nombre_paiements

        FROM medecin_interne_actes a
        LEFT JOIN medecin_interne_paiements p ON a.id_acte = p.id_acte
        WHERE a.id_acte IN ({placeholders})
        GROUP BY a.id_acte
    """

    cursor.execute(query, acte_ids)
    paiements_data = {row["id_acte"]: row for row in cursor.fetchall()}

    # Enrichir chaque acte
    for acte in actes:
        id_acte = acte["id_acte"]
        if id_acte in paiements_data:
            data = paiements_data[id_acte]

            montant_total = Decimal(str(data["montant_total"] or 0))
            total_paye = Decimal(str(data["total_paye"] or 0))
            reste_a_payer = montant_total - total_paye

            pourcentage_paye = 0
            if montant_total > 0:
                pourcentage_paye = float((total_paye / montant_total * 100))

            # Déterminer le statut
            if reste_a_payer <= Decimal("0.01"):
                statut = "COMPLET"
                statut_class = "success"
                statut_icon = "check-circle"
            elif total_paye > 0:
                statut = "PARTIEL"
                statut_class = "warning"
                statut_icon = "clock"
            else:
                statut = "AUCUN"
                statut_class = "danger"
                statut_icon = "exclamation-circle"

            acte["paiement_status"] = {
                "montant_total": float(montant_total),
                "total_paye": float(total_paye),
                "reste_a_payer": float(reste_a_payer),
                "pourcentage_paye": pourcentage_paye,
                "nombre_paiements": data["nombre_paiements"],
                "statut": statut,
                "statut_class": statut_class,
                "statut_icon": statut_icon,
            }
        else:
            # Pas de données de paiement
            acte["paiement_status"] = {
                "montant_total": 0,
                "total_paye": 0,
                "reste_a_payer": 0,
                "pourcentage_paye": 0,
                "nombre_paiements": 0,
                "statut": "AUCUN",
                "statut_class": "danger",
                "statut_icon": "exclamation-circle",
            }

    return actes


def calculer_acte(
    prix_acte_base,
    prix_consommables=0,
    prix_hospitalisation=0,
    prix_supplements=0,
    prix_actes_supp=0,
    prix_anesthesie=0,
    pourcentage_medecin=50,
    mode_calcul="PRIX_TOTAL",
    prix_consommables_supplement=None,
):
    """
    Calcule les parts médecin/clinique selon le mode choisi

    MODE PRIX_TOTAL: Le prix inclut les suppléments, on déduit tout avant calcul
      - Si des plafonds sont configurés (prix_consommables_supplement fourni),
        seul le dépassement des consommables (supplement) est déduit.
      - Sinon, toutes les consommables sont déduites (comportement historique).
    MODE PRIX_BASE: Le prix n'inclut PAS les suppléments - Patient paie tout
    """
    prix_acte_base = to_decimal(prix_acte_base)
    prix_consommables = to_decimal(prix_consommables)
    prix_hospitalisation = to_decimal(prix_hospitalisation)
    prix_supplements = to_decimal(prix_supplements)
    prix_actes_supp = to_decimal(prix_actes_supp)
    prix_anesthesie = to_decimal(prix_anesthesie)
    pourcentage_medecin = to_decimal(pourcentage_medecin)

    if mode_calcul == "PRIX_TOTAL":
        # Déterminer le montant consommables à déduire
        if prix_consommables_supplement is not None:
            # Plafonds configurés: seul le dépassement (supplement) est déduit
            conso_a_deduire = to_decimal(prix_consommables_supplement)
        else:
            # Pas de plafonds: toutes les consommables sont déduites (ancien comportement)
            conso_a_deduire = prix_consommables

        total_deductions = (
            conso_a_deduire
            + prix_hospitalisation
            + prix_supplements
            + prix_actes_supp
            + prix_anesthesie
        )

        base_calcul = prix_acte_base - total_deductions
        if base_calcul < 0:
            base_calcul = Decimal("0")

        part_medecin = (base_calcul * pourcentage_medecin) / Decimal("100")
        part_clinique = base_calcul - part_medecin

    else:  # PRIX_BASE
        # Mode 2: PAS de déductions - Patient paie TOUT
        total_deductions = Decimal("0")  # PAS DE DÉDUCTIONS

        base_calcul = prix_acte_base  # Prix de base complet
        part_medecin = (base_calcul * pourcentage_medecin) / Decimal("100")

        # Clinique reçoit : sa part + TOUS les suppléments
        tous_supplements = (
            prix_consommables
            + prix_hospitalisation
            + prix_supplements
            + prix_actes_supp
            + prix_anesthesie
        )
        part_clinique = (base_calcul - part_medecin) + tous_supplements

    return {
        "total_deductions": total_deductions,
        "base_calcul": base_calcul,
        "part_medecin": part_medecin,
        "part_clinique": part_clinique,
        "mode_calcul": mode_calcul,
    }


def calculer_statut_paiement(balance):
    """
    Détermine le statut de paiement selon la balance
    balance > 0  : Médecin doit payer → COMPLEMENT_MEDECIN
    balance < 0  : Clinique doit payer → SURPLUS_CLINIQUE
    balance == 0 : Équilibré
    """
    if abs(balance) < Decimal("0.01"):
        return "EQUILIBRE"
    return "COMPLEMENT_MEDECIN" if balance > 0 else "SURPLUS_CLINIQUE"


# ========================================================================
# ROUTES - LISTE
# ========================================================================


@app.route("/medecin_interne/actes")
@login_required
@handle_errors()
def medecin_interne_actes_list():
    """Liste des actes des médecins internes avec filtres"""
    with get_cursor() as (conn, cursor):
        # Filtres
        date_debut = request.args.get("date_debut")
        date_fin = request.args.get("date_fin")
        doctor_filter = request.args.get("doctor", "all")
        specialite_filter = request.args.get("specialite", "all")
        statut_filter = request.args.get("statut", "all")
        statut_annulation = request.args.get("statut_annulation", "actifs")  # NOUVEAU
        q = request.args.get("q", "").strip()

        # Pagination
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 10
        offset = (page - 1) * per_page

        # ========== CONSTRUCTION DE LA CLAUSE WHERE (commune) ==========
        where_conditions = []
        params = {}

        # Filtre statut annulation - NOUVEAU
        if statut_annulation == "actifs":
            where_conditions.append("a.est_annule = FALSE")
        elif statut_annulation == "annules":
            where_conditions.append("a.est_annule = TRUE")
        # Si 'tous', pas de filtre

        if date_debut:
            where_conditions.append("a.date_acte >= %(date_debut)s")
            params["date_debut"] = date_debut
        if date_fin:
            where_conditions.append("a.date_acte <= %(date_fin)s")
            params["date_fin"] = date_fin
        if doctor_filter != "all":
            where_conditions.append("a.id_doctor = %(doctor)s")
            params["doctor"] = doctor_filter
        if specialite_filter != "all":
            where_conditions.append("a.id_specialite = %(specialite)s")
            params["specialite"] = specialite_filter
        if statut_filter != "all":
            where_conditions.append("a.statut_paiement = %(statut)s")
            params["statut"] = statut_filter
        if q:
            where_conditions.append("(a.patient LIKE %(q)s OR a.nom_acte LIKE %(q)s)")
            params["q"] = f"%{q}%"

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # ========== REQUÊTE DE COMPTAGE ==========
        count_query = f"""
            SELECT COUNT(*) as total
            FROM medecin_interne_actes a
            LEFT JOIN doctors d ON a.id_doctor = d.id
            LEFT JOIN specialty s ON a.id_specialite = s.id_specialty
            LEFT JOIN personnel p ON a.created_by = p.id_personnel
            WHERE {where_clause}
        """
        cursor.execute(count_query, params)
        count_result = cursor.fetchone()
        total_count = count_result.get("total", 0) if count_result else 0

        # ========== REQUÊTE DE SOMME (uniquement pour actes non annulés) ==========
        sum_query = f"""
            SELECT COALESCE(SUM(a.part_medecin), 0) as total_amount
            FROM medecin_interne_actes a
            LEFT JOIN doctors d ON a.id_doctor = d.id
            LEFT JOIN specialty s ON a.id_specialite = s.id_specialty
            LEFT JOIN personnel p ON a.created_by = p.id_personnel
            WHERE {where_clause}
        """
        cursor.execute(sum_query, params)
        sum_result = cursor.fetchone()
        total_amount = float(sum_result.get("total_amount", 0)) if sum_result else 0.0

        # ========== REQUÊTE PRINCIPALE AVEC DONNÉES ==========
        data_query = f"""
            SELECT a.*,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   s.name_specialty,
                   CONCAT(p.nom, ' ', p.prenom) as created_by_name,
                   CONCAT(p_annule.nom, ' ', p_annule.prenom) as annule_par_name
            FROM medecin_interne_actes a
            LEFT JOIN doctors d ON a.id_doctor = d.id
            LEFT JOIN specialty s ON a.id_specialite = s.id_specialty
            LEFT JOIN personnel p ON a.created_by = p.id_personnel
            LEFT JOIN personnel p_annule ON a.annule_par = p_annule.id_personnel
            WHERE {where_clause}
            ORDER BY a.date_acte DESC, a.id_acte DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """
        params["limit"] = per_page
        params["offset"] = offset

        cursor.execute(data_query, params)
        actes = cursor.fetchall()
        actes = get_paiement_status_for_list(cursor, actes)

        # ========== CALCUL DES PAGES ==========
        from math import ceil

        total_pages = ceil(total_count / per_page) if total_count > 0 else 1

        # Récupérer données de référence pour filtres
        cursor.execute(
            """
            SELECT id, CONCAT(first_name, ' ', last_name) as name
            FROM doctors
            WHERE est_interne = 1
            ORDER BY last_name, first_name
        """
        )
        doctors = cursor.fetchall()

        cursor.execute(
            "SELECT id_specialty, name_specialty FROM specialty ORDER BY name_specialty"
        )
        specialites = cursor.fetchall()

        return render_template(
            "medecin_interne/actes_list.html",
            actes=actes,
            total_count=total_count,
            total_amount=total_amount,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            doctors=doctors,
            specialites=specialites,
            filters={
                "date_debut": date_debut or "",
                "date_fin": date_fin or "",
                "doctor": doctor_filter,
                "specialite": specialite_filter,
                "statut": statut_filter or "all",
                "statut_annulation": statut_annulation,  # NOUVEAU
                "q": q,
            },
            title="Actes Médecins Internes",
        )


# ========================================================================
# ROUTES - CRÉATION
# ========================================================================


@app.route("/api/medecin_interne/actes")
@login_required
def api_medecin_interne_actes():
    """Retourne la liste des actes médicaux disponibles"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT id_acte, nom_acte, prix
            FROM actes_supplement
            WHERE est_actif = 1
            ORDER BY nom_acte
            """
        )

        actes = cursor.fetchall()

        def convert_decimals(data):
            if isinstance(data, list):
                return [convert_decimals(item) for item in data]
            elif isinstance(data, dict):
                return {key: convert_decimals(value) for key, value in data.items()}
            elif isinstance(data, Decimal):
                return float(data)
            return data

        return jsonify(convert_decimals(actes))
    except Exception as e:
        app.logger.error(f"Erreur API actes: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route("/api/medecin_interne/check_dossier", methods=["GET"])
@login_required
def medecin_interne_check_dossier():
    patient_oid = request.args.get("patient_oid")
    if not patient_oid:
        return jsonify({"exists": False})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check active acts created in the last 7 days
        cursor.execute(
            """
            SELECT id_acte, date_acte, nom_acte
            FROM medecin_interne_actes
            WHERE patient_oid_his = %s
              AND date_acte >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            ORDER BY date_acte DESC
            LIMIT 1
        """,
            (patient_oid,),
        )
        acte = cursor.fetchone()

        if acte:
            # Format date for display
            date_str = (
                acte["date_acte"].strftime("%d/%m/%Y")
                if acte["date_acte"]
                else "Date inconnue"
            )
            return jsonify(
                {
                    "exists": True,
                    "message": f"⚠️ Attention : Un acte existe déjà pour ce patient (Date : {date_str}, Acte : {acte['nom_acte']}). Voulez-vous vraiment en créer un nouveau ?",
                }
            )
        return jsonify({"exists": False})
    finally:
        cursor.close()
        conn.close()


@app.route("/medecin_interne/actes/create", methods=["GET", "POST"])
@login_required
@handle_errors()
def medecin_interne_actes_create():
    """Création d'un acte médecin interne - VERSION REFACTORISÉE"""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "GET":
            # Récupérer les médecins internes
            cursor.execute(
                """
                SELECT d.id, CONCAT(d.first_name, ' ', d.last_name) as name, s.name_specialty
                FROM doctors d
                LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.est_interne = 1
                ORDER BY d.last_name, d.first_name
            """
            )
            doctors = cursor.fetchall()

            # Récupérer les produits
            cursor.execute(
                "SELECT id_produit, description, prix FROM produits ORDER BY description"
            )
            produits = cursor.fetchall()

            # Récupérer les types de chambres (incluant réanimation)
            cursor.execute(
                """
                SELECT id_type_chambre, nom_type, prix_unitaire, est_standard
                FROM type_chambre
                WHERE est_actif = 1
                ORDER BY prix_unitaire
            """
            )
            types_chambres = cursor.fetchall()

            # Récupérer les actes médicaux
            cursor.execute(
                """
                SELECT id_acte, nom_acte, prix
                FROM actes_supplement
                WHERE est_actif = 1
                ORDER BY nom_acte
            """
            )
            actes = cursor.fetchall()

            def convert_decimals(data):
                if isinstance(data, list):
                    return [convert_decimals(item) for item in data]
                elif isinstance(data, dict):
                    return {key: convert_decimals(value) for key, value in data.items()}
                elif isinstance(data, Decimal):
                    return float(data)
                return data

            return render_template(
                "medecin_interne/actes_create.html",
                doctors=doctors,
                produits=convert_decimals(produits),
                types_chambres=convert_decimals(types_chambres),
                actes=convert_decimals(actes),
                title="Nouvel Acte Médecin Interne",
            )

        # POST - Traitement
        if request.method == "POST":
            # Validation
            required_fields = ["id_doctor", "patient", "date_acte", "prix_acte_base"]
            for field in required_fields:
                if not request.form.get(field):
                    flash(f"Le champ {field} est obligatoire", "danger")
                    return redirect(url_for("medecin_interne_actes_create"))

            # Récupération des données
            id_doctor = request.form["id_doctor"]
            patient_oid = request.form.get("patient_oid")
            patient = request.form["patient"].strip()
            date_acte = request.form["date_acte"]
            heure_acte = request.form.get("heure_acte", "").strip() or None
            nom_acte = request.form.get("nom_acte", "").strip() or None
            duree_bloc_raw = request.form.get("duree_bloc")
            duree_bloc = int(duree_bloc_raw) if duree_bloc_raw and duree_bloc_raw.strip() else 90
            prix_acte_base = to_decimal(request.form["prix_acte_base"])
            montant_paye_caisse = to_decimal(request.form.get("montant_paye_caisse", 0))
            observations = request.form.get("observations", "").strip()
            mode_calcul = request.form.get("mode_calcul", "PRIX_TOTAL")
            nuitees_incluses_tarif = int(request.form.get("nuitees_incluses_tarif", 0))
            # Récupérer la spécialité du médecin
            cursor.execute(
                """
                SELECT d.id_specialty, s.name_specialty
                FROM doctors d
                LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.id = %s
            """,
                (id_doctor,),
            )
            doctor_info = cursor.fetchone()

            id_specialite = doctor_info["id_specialty"] if doctor_info else None
            nom_specialite = doctor_info["name_specialty"] if doctor_info else None
            pourcentage_medecin = get_pourcentage_medecin_interne(cursor, id_doctor)

            # ========== CONSOMMABLES MÉDECIN (NOUVEAUX) ==========
            prix_consommables_medecin = Decimal("0")
            cons_med_descriptions = request.form.getlist(
                "consommable_medecin_description[]"
            )
            cons_med_prix = request.form.getlist("consommable_medecin_prix[]")

            # ========== CONSOMMABLES SPÉCIFIQUES ==========
            prix_consommables = Decimal("0")
            consommables_ids = request.form.getlist("consommable_id[]")
            consommables_qtes = request.form.getlist("consommable_qte[]")

            # ========== HOSPITALISATION (incluant réanimation) ==========
            prix_hospitalisation = Decimal("0")
            dates_entree = request.form.getlist("hosp_date_entree[]")
            dates_sortie = request.form.getlist("hosp_date_sortie[]")
            types_chambre_ids = request.form.getlist("hosp_type_chambre[]")

            # ========== SUPPLÉMENTS (Imagerie, Labo, Autres) ==========
            prix_supplements = Decimal("0")
            supp_types = request.form.getlist("supplement_type[]")
            supp_descriptions = request.form.getlist("supplement_description[]")
            supp_prix = request.form.getlist("supplement_prix[]")

            # ========== ACTES SUPPLÉMENTAIRES ==========
            prix_actes_supplementaires = Decimal("0")
            actes_supp_ids = request.form.getlist("acte_supp_id[]")
            actes_supp_qtes = request.form.getlist("acte_supp_qte[]")

            # Génération QR UUID
            import uuid as _uuid

            qr_uuid = str(_uuid.uuid4())

            # Insertion de l'acte principal
            cursor.execute(
                """
                INSERT INTO medecin_interne_actes
                (qr_uuid, id_doctor, patient,patient_oid_his, date_acte, heure_acte, nom_acte, duree_bloc,
                 id_specialite, nom_specialite, pourcentage_medecin,
     prix_acte_base, montant_paye_caisse, observations,
     nuitees_incluses_tarif, created_by)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    qr_uuid,
                    id_doctor,
                    patient,
                    patient_oid,
                    date_acte,
                    heure_acte,
                    nom_acte,
                    duree_bloc,
                    id_specialite,
                    nom_specialite,
                    pourcentage_medecin,
                    prix_acte_base,
                    montant_paye_caisse,
                    observations,
                    nuitees_incluses_tarif,
                    g.user["id_personnel"],
                ),
            )

            id_acte = cursor.lastrowid

            # Insérer le paiement patient
            if montant_paye_caisse > 0:
                # 1. Dans la situation (pour le calcul du médecin)
                cursor.execute(
                    """
                    INSERT INTO medecin_interne_situations
                    (id_doctor, id_acte, encaissement_patient, created_by)
                    VALUES (%s, %s, %s, %s)
                """,
                    (id_doctor, id_acte, montant_paye_caisse, g.user["id_personnel"]),
                )

                # 2. Dans l'historique des paiements (pour la gestion patient)
                cursor.execute(
                    """
                    INSERT INTO medecin_interne_paiements
                    (id_acte, montant_paye, mode_paiement, created_by, observations)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                    (
                        id_acte,
                        montant_paye_caisse,
                        "ESPECES",
                        g.user["id_personnel"],
                        "Encaissement initial à la création",
                    ),
                )

            # ========== INSERTION CONSOMMABLES ==========
            for i, cons_id in enumerate(consommables_ids):
                if cons_id and cons_id.strip():
                    qte = to_decimal(
                        consommables_qtes[i] if i < len(consommables_qtes) else 1
                    )
                    if qte > 0:
                        cursor.execute(
                            "SELECT prix, description FROM produits WHERE id_produit = %s",
                            (cons_id,),
                        )
                        prod = cursor.fetchone()
                        if prod:
                            prix_unit = to_decimal(prod["prix"])
                            prix_total = prix_unit * qte
                            prix_consommables += prix_total

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_consommables
                                (id_acte, id_produit, description, quantite, prix_unitaire, prix_total)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_acte,
                                    cons_id,
                                    prod["description"],
                                    qte,
                                    prix_unit,
                                    prix_total,
                                ),
                            )
            # 4. INSÉRER les consommables médecin (MAINTENANT avec id_acte)
            for i in range(len(cons_med_descriptions)):
                if cons_med_descriptions[i] and cons_med_prix[i]:
                    prix = to_decimal(cons_med_prix[i])
                    if prix > 0:
                        prix_consommables_medecin += prix

                        cursor.execute(
                            """
                            INSERT INTO medecin_interne_consommables_medecin
                                (id_acte, description, prix)
                            VALUES (%s, %s, %s)
                                       """,
                            (id_acte, cons_med_descriptions[i], prix),
                        )
            # ========== INSERTION HOSPITALISATIONS (incluant réanimation) ==========
            for i in range(len(dates_entree)):
                if dates_entree[i] and dates_sortie[i] and types_chambre_ids[i]:
                    cursor.execute(
                        """
                        SELECT prix_unitaire, nom_type FROM type_chambre WHERE id_type_chambre = %s
                    """,
                        (types_chambre_ids[i],),
                    )
                    chambre = cursor.fetchone()
                    if chambre:
                        d_entree = datetime.strptime(dates_entree[i], "%Y-%m-%d").date()
                        d_sortie = datetime.strptime(dates_sortie[i], "%Y-%m-%d").date()
                        nb_jours_total = (d_sortie - d_entree).days

                        # NOUVEAU: Calculer les nuitées à facturer
                        # On déduit les nuitées incluses du nombre total
                        nb_jours_a_facturer = max(
                            0, nb_jours_total - nuitees_incluses_tarif
                        )

                        prix_unit = to_decimal(chambre["prix_unitaire"])

                        # Prix calculé sur les nuitées à facturer seulement
                        prix_total = prix_unit * nb_jours_a_facturer
                        prix_hospitalisation += prix_total

                        # Déterminer si c'est de la réanimation
                        est_reanimation = (
                            "RÉANIMATION" in chambre["nom_type"].upper()
                            or "REANIMATION" in chambre["nom_type"].upper()
                        )

                        # MODIFIER: Stocker à la fois le nombre total et le nombre facturé
                        cursor.execute(
                            """
                            INSERT INTO medecin_interne_hospitalisation
                            (id_acte, id_type_chambre, date_entree, date_sortie,
                             nombre_nuitees, nombre_nuitees_facturees,
                             prix_unitaire, prix_total, est_hors_forfait, type_hospitalisation)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                                       """,
                            (
                                id_acte,
                                types_chambre_ids[i],
                                dates_entree[i],
                                dates_sortie[i],
                                nb_jours_total,
                                nb_jours_a_facturer,  # NOUVEAU: deux valeurs
                                prix_unit,
                                prix_total,
                                "REANIMATION" if est_reanimation else "STANDARD",
                            ),
                        )

            # ========== INSERTION SUPPLÉMENTS ==========
            for i in range(len(supp_types)):
                if supp_types[i] and supp_prix[i]:
                    prix = to_decimal(supp_prix[i])
                    if prix > 0:
                        prix_supplements += prix
                        desc = (
                            supp_descriptions[i] if i < len(supp_descriptions) else ""
                        )

                        cursor.execute(
                            """
                            INSERT INTO medecin_interne_supplements
                            (id_acte, type_supplement, description, prix)
                            VALUES (%s, %s, %s, %s)
                        """,
                            (id_acte, supp_types[i], desc, prix),
                        )

            # ========== INSERTION ACTES SUPPLÉMENTAIRES ==========
            for i, acte_id in enumerate(actes_supp_ids):
                if acte_id and acte_id.strip():
                    qte = to_decimal(
                        actes_supp_qtes[i] if i < len(actes_supp_qtes) else 1
                    )
                    if qte > 0:
                        cursor.execute(
                            "SELECT prix, nom_acte FROM actes_supplement WHERE id_acte = %s",
                            (acte_id,),
                        )
                        acte = cursor.fetchone()
                        if acte:
                            prix_unit = to_decimal(acte["prix"])
                            prix_total = prix_unit * qte
                            prix_actes_supplementaires += prix_total

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_actes_supplementaires
                                (id_acte_principal, id_type_acte, nom_acte, quantite, prix_unitaire, prix_total)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_acte,
                                    acte_id,
                                    acte["nom_acte"],
                                    qte,
                                    prix_unit,
                                    prix_total,
                                ),
                            )

            # ========== GESTION DE L'ANESTHÉSIE/RÉANIMATION ==========
            acte_anesth_id = request.form.get("acte_anesth_id")
            intervenant1_id = request.form.get("intervenant1_id")
            intervenant2_id = request.form.get("intervenant2_id")

            from app.anesthesie_honoraires.anesthesie_honoraires import (
                calculer_honoraires_anesthesie,
                get_tarif_forfaitaire_anesthesie,
            )

            prix_anesthesie = Decimal("0")

            if acte_anesth_id and intervenant1_id and intervenant2_id:
                try:
                    # Prix pour le dossier
                    prix_anesthesie = get_tarif_forfaitaire_anesthesie(
                        cursor, acte_anesth_id
                    )
                    duree_reelle = duree_bloc

                    # Pour l'intervenant 1 (anesthésiste/réanimateur)
                    if intervenant1_id:
                        cursor.execute(
                            """
                            SELECT id_type_intervenant
                            FROM anesthesie_personnel
                            WHERE id_personnel_anesthesie = %s
                        """,
                            (intervenant1_id,),
                        )
                        intervenant1 = cursor.fetchone()

                        if intervenant1:
                            honoraires1 = calculer_honoraires_anesthesie(
                                cursor,
                                acte_anesth_id,
                                intervenant1["id_type_intervenant"],
                                duree_reelle,
                            )

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_anesthesie
                                (id_acte, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_acte,
                                    acte_anesth_id,
                                    intervenant1_id,
                                    duree_reelle,
                                    honoraires1,
                                    g.user["id_personnel"],
                                ),
                            )

                            app.logger.info(
                                f"Intervenant 1 enregistré: ID={intervenant1_id}, Honoraires={honoraires1}"
                            )

                    # Pour l'intervenant 2
                    if intervenant2_id:
                        cursor.execute(
                            """
                            SELECT id_type_intervenant
                            FROM anesthesie_personnel
                            WHERE id_personnel_anesthesie = %s
                        """,
                            (intervenant2_id,),
                        )
                        intervenant2 = cursor.fetchone()

                        if intervenant2:
                            honoraires2 = calculer_honoraires_anesthesie(
                                cursor,
                                acte_anesth_id,
                                intervenant2["id_type_intervenant"],
                                duree_reelle,
                            )

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_anesthesie
                                (id_acte, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_acte,
                                    acte_anesth_id,
                                    intervenant2_id,
                                    duree_reelle,
                                    honoraires2,
                                    g.user["id_personnel"],
                                ),
                            )
                            app.logger.info(
                                f"Intervenant 2 enregistré: ID={intervenant2_id}, Honoraires={honoraires2}"
                            )

                    app.logger.info(
                        f"Acte anesthésie enregistré avec succès - Prix total: {prix_anesthesie}"
                    )

                except Exception as e:
                    app.logger.error(
                        f"ERREUR lors de l'enregistrement de l'acte anesthésie: {str( e )}"
                    )
                    app.logger.error(
                        f"Détails - acte_anesth_id: {acte_anesth_id}, intervenant1: {intervenant1_id}, intervenant2: {intervenant2_id}"
                    )
                    import traceback

                    app.logger.error(traceback.format_exc())
                    # ⚠️ Ne pas bloquer la création de l'acte principal
                    # mais informer l'utilisateur
                    flash(
                        f"Attention: L'acte d'anesthésie n'a pas pu être enregistré: {str( e )}",
                        "warning",
                    )
                except Exception as e:
                    app.logger.warning(f"Erreur acte anesthésie: {str(e)}")

            # ========== MISE À JOUR DES CALCULS FINAUX ==========

            # -- Calcul du supplément consommables (plafonnement) --
            prix_consommables_supplement = None
            if mode_calcul == "PRIX_TOTAL":
                cursor.execute(
                    """
                    SELECT id_produit, quantite_max
                    FROM medecin_interne_plafond_consommables
                    WHERE id_doctor = %s AND est_actif = 1
                """,
                    (id_doctor,),
                )
                plafonds_rows = cursor.fetchall()

                if plafonds_rows:
                    # Par défaut 0 (gratuit) sauf si dépassement
                    prix_consommables_supplement = Decimal("0")
                    # Construire un dict {id_produit: qte_max}
                    plafonds_dict = {
                        r["id_produit"]: r["quantite_max"] for r in plafonds_rows
                    }

                    # Récupérer les consommables insérés pour cet acte
                    cursor.execute(
                        """
                        SELECT id_produit, quantite, prix_unitaire
                        FROM medecin_interne_consommables
                        WHERE id_acte = %s
                    """,
                        (id_acte,),
                    )
                    conso_rows = cursor.fetchall()

                    # Calculer le supplément par produit
                    prix_consommables_supplement = Decimal("0")
                    for conso in conso_rows:
                        qte_consommee = to_decimal(conso["quantite"])
                        prix_unit = to_decimal(conso["prix_unitaire"])
                        qte_plafond = Decimal(
                            str(plafonds_dict.get(conso["id_produit"], 0))
                        )
                        exces = qte_consommee - qte_plafond
                        if exces > 0:
                            prix_consommables_supplement += prix_unit * exces

            calcul_final = calculer_acte(
                prix_acte_base,
                prix_consommables,
                prix_hospitalisation,
                prix_supplements,
                prix_actes_supplementaires,
                prix_anesthesie,
                pourcentage_medecin,
                mode_calcul,
                prix_consommables_supplement=prix_consommables_supplement,
            )
            # AJOUTER les consommables médecin à la part médecin
            part_medecin_finale = (
                calcul_final["part_medecin"] + prix_consommables_medecin
            )

            # Ajuster la différence de paiement
            difference_paiement = montant_paye_caisse - part_medecin_finale
            statut_paiement = calculer_statut_paiement(
                part_medecin_finale - montant_paye_caisse
            )

            cursor.execute(
                """
                UPDATE medecin_interne_actes
                SET prix_consommables_specifiques = %s,
                    prix_hospitalisation_hors_forfait = %s,
                    prix_supplements = %s,
                    prix_actes_supplementaires = %s,
                    prix_anesthesie = %s,
                    prix_consommables_medecin = %s,
                    total_deductions = %s,
                    base_calcul = %s,
                    part_medecin = %s,
                    part_clinique = %s,
                    difference_paiement = %s,
                    statut_paiement = %s,
                    mode_calcul = %s
                WHERE id_acte = %s
            """,
                (
                    prix_consommables,
                    prix_hospitalisation,
                    prix_supplements,
                    prix_actes_supplementaires,
                    prix_anesthesie,
                    prix_consommables_medecin,
                    calcul_final["total_deductions"],
                    calcul_final["base_calcul"],
                    part_medecin_finale,
                    calcul_final["part_clinique"],
                    difference_paiement,
                    statut_paiement,
                    mode_calcul,
                    id_acte,
                ),
            )

            connection.commit()

            flash(
                f'Acte créé avec succès. Part médecin: {float(calcul_final["part_medecin"]):.2f} DA',
                "success",
            )
            return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

    except Exception as e:
        if connection:
            try:
                connection.rollback()
            except:
                pass
        app.logger.error(f"Erreur création acte médecin interne: {str(e)}")
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors de la création: {str(e)}", "danger")
        return redirect(url_for("medecin_interne_actes_create"))

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


# ========================================================================
# ROUTES - DÉTAIL
# ========================================================================


@app.route("/medecin_interne/actes/<int:id_acte>")
@login_required
@handle_errors()
@handle_errors()
def medecin_interne_actes_detail(id_acte):
    """Détail d'un acte médecin interne"""
    with get_cursor() as (conn, cursor):
        # Récupérer l'acte
        cursor.execute(
            """
            SELECT a.*,
                   CONCAT(d.first_name, ' ', d.last_name)     as doctor_name,
                   s.name_specialty,
                   CONCAT(p.nom, ' ', p.prenom)               as created_by_name,
                   CONCAT(p_annule.nom, ' ', p_annule.prenom) as annule_par_name
            FROM medecin_interne_actes a
                     LEFT JOIN doctors d ON a.id_doctor = d.id
                     LEFT JOIN specialty s ON a.id_specialite = s.id_specialty
                     LEFT JOIN personnel p ON a.created_by = p.id_personnel
                     LEFT JOIN personnel p_annule ON a.annule_par = p_annule.id_personnel
            WHERE a.id_acte = %s
                       """,
            (id_acte,),
        )

        acte = cursor.fetchone()
        if not acte:
            flash("Acte non trouvé", "danger")
            return redirect(url_for("medecin_interne_actes_list"))

        # Récupérer les consommables
        cursor.execute(
            """
            SELECT c.*, p.description as produit_nom
            FROM medecin_interne_consommables c
            LEFT JOIN produits p ON c.id_produit = p.id_produit
            WHERE c.id_acte = %s
        """,
            (id_acte,),
        )
        consommables = cursor.fetchall()

        # Récupérer les hospitalisations (incluant réanimation)
        cursor.execute(
            """
            SELECT h.*, t.nom_type as type_chambre_nom, t.est_standard
            FROM medecin_interne_hospitalisation h
            LEFT JOIN type_chambre t ON h.id_type_chambre = t.id_type_chambre
            WHERE h.id_acte = %s
            ORDER BY h.date_entree
        """,
            (id_acte,),
        )
        hospitalisations = cursor.fetchall()

        # Récupérer les suppléments
        cursor.execute(
            """
            SELECT * FROM medecin_interne_supplements
            WHERE id_acte = %s
            ORDER BY type_supplement
        """,
            (id_acte,),
        )
        supplements = cursor.fetchall()

        # Récupérer les actes supplémentaires
        cursor.execute(
            """
            SELECT * FROM medecin_interne_actes_supplementaires
            WHERE id_acte_principal = %s
        """,
            (id_acte,),
        )
        actes_supplementaires = cursor.fetchall()

        # Récupérer les actes d'anesthésie/réanimation
        cursor.execute(
            """
            SELECT ma.*, ata.nom_acte, CONCAT(ap.prenom, ' ', ap.nom) as nom_personnel,
                   ait.nom_type as type_intervenant
            FROM medecin_interne_anesthesie ma
            LEFT JOIN anesthesie_type_acte ata ON ma.id_acte_anesthesie = ata.id_acte_anesthesie
            LEFT JOIN anesthesie_personnel ap ON ma.id_personnel_anesthesie = ap.id_personnel_anesthesie
            LEFT JOIN anesthesie_intervenant_type ait ON ap.id_type_intervenant = ait.id_type_intervenant
            WHERE ma.id_acte = %s
        """,
            (id_acte,),
        )
        anesthesie = cursor.fetchall()
        # Récupérer les consommables médecin
        cursor.execute(
            """
            SELECT *
            FROM medecin_interne_consommables_medecin
            WHERE id_acte = %s
                       """,
            (id_acte,),
        )
        consommables_medecin = cursor.fetchall()

        # Récupérer le total des paiements (tranches)
        from app.medecins_internes.medecin_interne_paiements_patient import (
            get_paiements_summary,
        )

        # Récupérer le résumé des paiements
        summary_paiements = get_paiements_summary(cursor, id_acte)
        total_deja_paye = summary_paiements["total_paye"]
        total_paiements_tranches = summary_paiements["total_paye"]

        return render_template(
            "medecin_interne/actes_detail.html",
            acte=acte,
            consommables=consommables,
            consommables_medecin=consommables_medecin,
            hospitalisations=hospitalisations,
            supplements=supplements,
            actes_supplementaires=actes_supplementaires,
            anesthesie=anesthesie,
            total_deja_paye=total_deja_paye,
            total_paiements_tranches=total_paiements_tranches,
            title=f"Acte #{id_acte}",
        )


# ========================================================================
# API - POUR AJAX
# ========================================================================


@app.route("/api/medecin_interne/pourcentage/<int:id_doctor>")
@login_required
def api_medecin_interne_pourcentage(id_doctor):
    """Récupère le pourcentage d'un médecin selon sa spécialité"""
    with get_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT d.id_specialty, s.name_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
        """,
            (id_doctor,),
        )

        doctor = cursor.fetchone()
        if not doctor:
            return jsonify({"error": "Médecin non trouvé"}), 404

        pourcentage = float(get_pourcentage_medecin_interne(cursor, id_doctor))

        return jsonify(
            {
                "id_specialty": doctor["id_specialty"],
                "name_specialty": doctor["name_specialty"],
                "pourcentage_medecin": pourcentage,
            }
        )


@app.route("/api/medecin_interne/calculer", methods=["POST"])
@login_required
def api_medecin_interne_calculer():
    """Calcule les parts médecin/clinique"""
    data = request.get_json()

    calcul = calculer_acte(
        data.get("prix_acte_base", 0),
        data.get("prix_consommables", 0),
        data.get("prix_hospitalisation", 0),
        data.get("prix_supplements", 0),
        data.get("prix_actes_supp", 0),
        data.get("prix_anesthesie", 0),
        data.get("pourcentage_medecin", 50),
    )

    return jsonify(
        {
            "total_deductions": float(calcul["total_deductions"]),
            "base_calcul": float(calcul["base_calcul"]),
            "part_medecin": float(calcul["part_medecin"]),
            "part_clinique": float(calcul["part_clinique"]),
        }
    )


@app.route("/medecin_interne/actes/export")
@login_required
@handle_errors()
def medecin_interne_actes_export():
    """Export CSV des actes des médecins internes"""
    from io import BytesIO

    from flask import send_file
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    with get_cursor() as (conn, cursor):
        # Récupérer les mêmes filtres que la liste
        date_debut = request.args.get("date_debut")
        date_fin = request.args.get("date_fin")
        doctor_filter = request.args.get("doctor", "all")
        specialite_filter = request.args.get("specialite", "all")
        statut_filter = request.args.get("statut", "all")
        q = request.args.get("q", "").strip()

        # Construction de la requête (même logique que la liste)
        query = """
            SELECT a.*,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   s.name_specialty
            FROM medecin_interne_actes a
            LEFT JOIN doctors d ON a.id_doctor = d.id
            LEFT JOIN specialty s ON a.id_specialite = s.id_specialty
            WHERE 1 = 1
        """
        params = {}

        if date_debut:
            query += " AND a.date_acte >= %(date_debut)s"
            params["date_debut"] = date_debut
        if date_fin:
            query += " AND a.date_acte <= %(date_fin)s"
            params["date_fin"] = date_fin
        if doctor_filter != "all":
            query += " AND a.id_doctor = %(doctor)s"
            params["doctor"] = doctor_filter
        if specialite_filter != "all":
            query += " AND a.id_specialite = %(specialite)s"
            params["specialite"] = specialite_filter
        if statut_filter != "all":
            query += " AND a.statut_paiement = %(statut)s"
            params["statut"] = statut_filter
        if q:
            query += " AND (a.patient LIKE %(q)s OR a.nom_acte LIKE %(q)s)"
            params["q"] = f"%{q}%"

        query += " ORDER BY a.date_acte DESC, a.id_acte DESC"

        cursor.execute(query, params)
        actes = cursor.fetchall()

        # Créer le classeur Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Actes Médecins Internes"

        # Styles
        header_font = Font(bold=True, color="FFFFFF", size=12)
        header_fill = PatternFill(
            start_color="4472C4", end_color="4472C4", fill_type="solid"
        )
        header_alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )

        border_thin = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        # En-têtes
        headers = [
            "ID Acte",
            "Date",
            "Heure",
            "Patient",
            "Médecin",
            "Spécialité",
            "Nom Acte",
            "Durée Bloc",
            "Mode Calcul",
            "Prix Base",
            "Consommables",
            "Hospitalisation",
            "Suppléments",
            "Actes Supp.",
            "Anesthésie",
            "Total Déductions",
            "Base Calcul",
            "Pourcentage %",
            "Part Médecin",
            "Part Clinique",
            "Montant Payé",
            "Reste à Payer",
            "Statut Paiement",
        ]

        # Écrire les en-têtes
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border_thin

        # Définir la hauteur de la ligne d'en-tête
        ws.row_dimensions[1].height = 30

        # Variables pour les totaux
        total_prix_base = 0
        total_consommables = 0
        total_hospitalisation = 0
        total_supplements = 0
        total_actes_supp = 0
        total_anesthesie = 0
        total_deductions = 0
        total_base_calcul = 0
        total_part_medecin = 0
        total_part_clinique = 0
        total_montant_paye = 0
        total_reste_a_payer = 0

        # Écrire les données
        from app.medecins_internes.medecin_interne_paiements_patient import (
            get_paiements_summary,
        )

        for row_num, acte in enumerate(actes, 2):
            summary_paiements = get_paiements_summary(cursor, acte["id_acte"])

            # Calculer le reste à payer selon le mode de calcul
            if acte["mode_calcul"] == "PRIX_BASE":
                montant_total = (
                    float(acte["prix_acte_base"] or 0)
                    + float(acte["prix_consommables_specifiques"] or 0)
                    + float(acte["prix_hospitalisation_hors_forfait"] or 0)
                    + float(acte["prix_supplements"] or 0)
                    + float(acte["prix_actes_supplementaires"] or 0)
                    + float(acte["prix_anesthesie"] or 0)
                )
            else:
                montant_total = float(acte["prix_acte_base"] or 0)

            montant_paye = float(summary_paiements["total_paye"])
            reste_a_payer = montant_total - montant_paye

            # Valeurs numériques
            prix_base = float(acte["prix_acte_base"] or 0)
            consommables = float(acte["prix_consommables_specifiques"] or 0)
            hospitalisation = float(acte["prix_hospitalisation_hors_forfait"] or 0)
            supplements = float(acte["prix_supplements"] or 0)
            actes_supp = float(acte["prix_actes_supplementaires"] or 0)
            anesthesie = float(acte["prix_anesthesie"] or 0)
            deductions = float(acte["total_deductions"] or 0)
            base_calcul = float(acte["base_calcul"] or 0)
            part_medecin = float(acte["part_medecin"] or 0)
            part_clinique = float(acte["part_clinique"] or 0)

            # Accumuler les totaux
            total_prix_base += prix_base
            total_consommables += consommables
            total_hospitalisation += hospitalisation
            total_supplements += supplements
            total_actes_supp += actes_supp
            total_anesthesie += anesthesie
            total_deductions += deductions
            total_base_calcul += base_calcul
            total_part_medecin += part_medecin
            total_part_clinique += part_clinique
            total_montant_paye += montant_paye
            total_reste_a_payer += reste_a_payer

            # Formater l'heure
            heure_str = ""
            if acte.get("heure_acte"):
                if isinstance(acte["heure_acte"], timedelta):
                    total_seconds = int(acte["heure_acte"].total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    heure_str = f"{hours:02d}:{minutes:02d}"
                else:
                    heure_str = str(acte["heure_acte"])

            # Écrire la ligne
            row_data = [
                f"A-{acte['id_acte']:05d}",
                acte["date_acte"] if acte["date_acte"] else "",
                heure_str,
                acte["patient"],
                acte["doctor_name"],
                acte["name_specialty"] or "",
                acte["nom_acte"] or "",
                acte.get("duree_bloc", 0),
                "Prix Total" if acte["mode_calcul"] == "PRIX_TOTAL" else "Prix Base",
                prix_base,
                consommables,
                hospitalisation,
                supplements,
                actes_supp,
                anesthesie,
                deductions,
                base_calcul,
                float(acte["pourcentage_medecin"] or 0),
                part_medecin,
                part_clinique,
                montant_paye,
                reste_a_payer,
                acte["statut_paiement"] or "",
            ]

            for col_num, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = value
                cell.border = border_thin

                # Format pour les dates
                if col_num == 2 and value:
                    cell.number_format = "DD/MM/YYYY"

                # Format pour les montants (colonnes 10 à 22 sauf 18 qui est le pourcentage)
                if col_num in [10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22]:
                    cell.number_format = "#,##0.00"
                    cell.alignment = Alignment(horizontal="right")

                # Format pour le pourcentage
                if col_num == 18:
                    cell.number_format = "0.00"
                    cell.alignment = Alignment(horizontal="right")

        # Ajouter une ligne de totaux
        total_row = len(actes) + 2
        ws.cell(row=total_row, column=1).value = "TOTAUX"
        ws.cell(row=total_row, column=1).font = Font(bold=True, size=12)
        ws.cell(row=total_row, column=1).fill = PatternFill(
            start_color="E7E6E6", end_color="E7E6E6", fill_type="solid"
        )

        # Colonnes des totaux
        totaux_data = {
            10: total_prix_base,
            11: total_consommables,
            12: total_hospitalisation,
            13: total_supplements,
            14: total_actes_supp,
            15: total_anesthesie,
            16: total_deductions,
            17: total_base_calcul,
            19: total_part_medecin,
            20: total_part_clinique,
            21: total_montant_paye,
            22: total_reste_a_payer,
        }

        for col_num, value in totaux_data.items():
            cell = ws.cell(row=total_row, column=col_num)
            cell.value = value
            cell.number_format = "#,##0.00"
            cell.font = Font(bold=True, size=11)
            cell.fill = PatternFill(
                start_color="E7E6E6", end_color="E7E6E6", fill_type="solid"
            )
            cell.alignment = Alignment(horizontal="right")
            cell.border = border_thin

        # Remplir les cellules vides de la ligne totaux
        for col_num in range(2, 9):
            cell = ws.cell(row=total_row, column=col_num)
            cell.fill = PatternFill(
                start_color="E7E6E6", end_color="E7E6E6", fill_type="solid"
            )
            cell.border = border_thin

        # Colonne 18 (pourcentage) - laisser vide
        cell = ws.cell(row=total_row, column=18)
        cell.fill = PatternFill(
            start_color="E7E6E6", end_color="E7E6E6", fill_type="solid"
        )
        cell.border = border_thin

        # Ajuster la largeur des colonnes
        column_widths = {
            "A": 12,  # ID Acte
            "B": 12,  # Date
            "C": 8,  # Heure
            "D": 25,  # Patient
            "E": 25,  # Médecin
            "F": 20,  # Spécialité
            "G": 30,  # Nom Acte
            "H": 12,  # Durée Bloc
            "I": 12,  # Mode Calcul
            "J": 12,  # Prix Base
            "J": 13,  # Consommables
            "K": 14,  # Hospitalisation
            "L": 13,  # Suppléments
            "M": 12,  # Actes Supp.
            "N": 12,  # Anesthésie
            "O": 14,  # Total Déductions
            "P": 13,  # Base Calcul
            "Q": 12,  # Pourcentage
            "R": 14,  # Part Médecin
            "S": 13,  # Part Clinique
            "T": 13,  # Montant Payé
            "U": 13,  # Reste à Payer
            "V": 16,  # Statut Paiement
        }

        for col_letter, width in column_widths.items():
            ws.column_dimensions[col_letter].width = width

        # Figer la première ligne
        ws.freeze_panes = "A2"

        # Ajouter des informations en haut (avant les données)
        ws.insert_rows(1, 3)

        # Titre principal
        ws.merge_cells("A1:V1")
        title_cell = ws["A1"]
        title_cell.value = "EXPORT ACTES MÉDECINS INTERNES"
        title_cell.font = Font(bold=True, size=16, color="4472C4")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 25

        # Informations sur la période
        ws.merge_cells("A2:V2")
        info_cell = ws["A2"]
        info_text = f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
        if date_debut and date_fin:
            info_text += f" - Période: du {date_debut} au {date_fin}"
        elif date_debut:
            info_text += f" - À partir du {date_debut}"
        elif date_fin:
            info_text += f" - Jusqu'au {date_fin}"
        info_cell.value = info_text
        info_cell.font = Font(size=10, italic=True)
        info_cell.alignment = Alignment(horizontal="center")
        ws.row_dimensions[2].height = 20

        # Ligne vide
        ws.row_dimensions[3].height = 5

        # Sauvegarder dans un buffer
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        # Nom du fichier
        filename = (
            f"actes_medecins_internes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )


# ========================================================================
# ROUTES - MODIFICATION
# ========================================================================


@app.route("/medecin_interne/actes/<int:id_acte>/edit", methods=["GET", "POST"])
@login_required
@handle_errors()
@handle_errors()
def medecin_interne_actes_edit(id_acte):
    """Modification d'un acte médecin interne"""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "GET":
            # Récupérer l'acte
            cursor.execute(
                """
                SELECT a.*,
                       CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                       s.name_specialty
                FROM medecin_interne_actes a
                         LEFT JOIN doctors d ON a.id_doctor = d.id
                         LEFT JOIN specialty s ON a.id_specialite = s.id_specialty
                WHERE a.id_acte = %s
                           """,
                (id_acte,),
            )

            acte = cursor.fetchone()
            if not acte:
                flash("Acte non trouvé", "danger")
                return redirect(url_for("medecin_interne_actes_list"))

            # NOUVEAU : Vérifier si l'acte est annulé
            if acte["est_annule"]:
                flash(
                    "Impossible de modifier un acte annulé. "
                    "Vous devez d'abord le restaurer si vous souhaitez le modifier.",
                    "danger",
                )
                return redirect(
                    url_for("medecin_interne_actes_detail", id_acte=id_acte)
                )

            # Vérifier si l'acte peut être modifié
            # 1. Vérifier les paiements patients
            cursor.execute(
                """
                SELECT COUNT(*)                       as nb_paiements,
                       COALESCE(SUM(montant_paye), 0) as total_paye
                FROM medecin_interne_paiements
                WHERE id_acte = %s
                  AND est_annule = FALSE
                           """,
                (id_acte,),
            )

            paiements_info = cursor.fetchone()

            # 2. Vérifier si dans une décharge
            (
                cursor.execute(
                    """
                SELECT d.numero_decharge, d.statut
                FROM medecin_interne_decharges d
                WHERE d.id_decharge = %s
                           """,
                    (acte["id_decharge_medecin"],),
                )
                if acte["id_decharge_medecin"]
                else None
            )

            decharge_info = cursor.fetchone() if acte["id_decharge_medecin"] else None

            # Avertissements
            warnings = []
            if paiements_info["nb_paiements"] > 0:
                warnings.append(
                    f"⚠️ Attention : Cet acte a {paiements_info[ 'nb_paiements' ]} paiement(s) patient pour un total de {float( paiements_info[ 'total_paye' ] ):.2f} DA"
                )

            if decharge_info and decharge_info["statut"] in [
                "VALIDE",
                "PAIEMENT_PARTIEL",
                "PAYE",
            ]:
                warnings.append(
                    f"⚠️ Attention : Cet acte est dans la décharge {decharge_info[ 'numero_decharge' ]} ({decharge_info[ 'statut' ]})"
                )

            # Récupérer les médecins internes
            cursor.execute(
                """
                SELECT d.id, CONCAT(d.first_name, ' ', d.last_name) as name, s.name_specialty
                FROM doctors d
                         LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.est_interne = 1
                ORDER BY d.last_name, d.first_name
                           """
            )
            doctors = cursor.fetchall()

            # Récupérer les produits
            cursor.execute(
                "SELECT id_produit, description, prix FROM produits ORDER BY description"
            )
            produits = cursor.fetchall()

            # Récupérer les types de chambres
            cursor.execute(
                """
                SELECT id_type_chambre, nom_type, prix_unitaire, est_standard
                FROM type_chambre
                WHERE est_actif = 1
                ORDER BY prix_unitaire
                           """
            )
            types_chambres = cursor.fetchall()

            # Récupérer les actes médicaux
            cursor.execute(
                """
                SELECT id_acte, nom_acte, prix
                FROM actes_supplement
                WHERE est_actif = 1
                ORDER BY nom_acte
                           """
            )
            actes_types = cursor.fetchall()

            # Récupérer les consommables existants
            cursor.execute(
                """
                SELECT c.*, p.description as produit_nom
                FROM medecin_interne_consommables c
                         LEFT JOIN produits p ON c.id_produit = p.id_produit
                WHERE c.id_acte = %s
                           """,
                (id_acte,),
            )
            consommables_existants = cursor.fetchall()

            # Récupérer les hospitalisations existantes
            cursor.execute(
                """
                SELECT h.*, t.nom_type as type_chambre_nom
                FROM medecin_interne_hospitalisation h
                         LEFT JOIN type_chambre t ON h.id_type_chambre = t.id_type_chambre
                WHERE h.id_acte = %s
                ORDER BY h.date_entree
                           """,
                (id_acte,),
            )
            hospitalisations_existantes = cursor.fetchall()

            # Récupérer les suppléments existants
            cursor.execute(
                """
                SELECT *
                FROM medecin_interne_supplements
                WHERE id_acte = %s
                ORDER BY type_supplement
                           """,
                (id_acte,),
            )
            supplements_existants = cursor.fetchall()

            # Récupérer les actes supplémentaires existants
            cursor.execute(
                """
                SELECT *
                FROM medecin_interne_actes_supplementaires
                WHERE id_acte_principal = %s
                           """,
                (id_acte,),
            )
            actes_supp_existants = cursor.fetchall()

            # Récupérer l'anesthésie existante
            cursor.execute(
                """
                SELECT ma.*, ata.nom_acte
                FROM medecin_interne_anesthesie ma
                         LEFT JOIN anesthesie_type_acte ata ON ma.id_acte_anesthesie = ata.id_acte_anesthesie
                WHERE ma.id_acte = %s
                           """,
                (id_acte,),
            )
            anesthesie_existante = cursor.fetchall()

            # Récupérer les consommables médecin
            cursor.execute(
                """
                    SELECT *
                    FROM medecin_interne_consommables_medecin
                    WHERE id_acte = %s
                    """,
                (id_acte,),
            )
            consommables_medecin = cursor.fetchall()

            def convert_decimals(data):
                if isinstance(data, list):
                    return [convert_decimals(item) for item in data]
                elif isinstance(data, dict):
                    return {key: convert_decimals(value) for key, value in data.items()}
                elif isinstance(data, Decimal):
                    return float(data)
                elif hasattr(data, "isoformat"):
                    return data.isoformat()
                return data

            return render_template(
                "medecin_interne/actes_edit.html",
                acte=acte,
                doctors=doctors,
                produits=convert_decimals(produits),
                types_chambres=convert_decimals(types_chambres),
                actes_types=convert_decimals(actes_types),
                consommables_existants=convert_decimals(consommables_existants),
                hospitalisations_existantes=convert_decimals(
                    hospitalisations_existantes
                ),
                supplements_existants=convert_decimals(supplements_existants),
                actes_supp_existants=convert_decimals(actes_supp_existants),
                anesthesie_existante=convert_decimals(anesthesie_existante),
                consommables_medecin=convert_decimals(consommables_medecin),
                warnings=warnings,
                title=f"Modifier l'acte #{id_acte}",
            )

        # POST - Traitement de la modification
        if request.method == "POST":
            # Validation
            required_fields = ["id_doctor", "patient", "date_acte", "prix_acte_base"]
            for field in required_fields:
                if not request.form.get(field):
                    flash(f"Le champ {field} est obligatoire", "danger")
                    return redirect(
                        url_for("medecin_interne_actes_edit", id_acte=id_acte)
                    )

            # Récupération des données
            id_doctor = request.form["id_doctor"]
            patient = request.form["patient"].strip()
            date_acte = request.form["date_acte"]
            heure_acte = request.form.get("heure_acte", "").strip() or None
            nom_acte = request.form.get("nom_acte", "").strip() or None
            duree_bloc_str = request.form.get("duree_bloc", "").strip()
            duree_bloc = int(duree_bloc_str) if duree_bloc_str else 90
            prix_acte_base = to_decimal(request.form["prix_acte_base"])
            montant_paye_caisse = to_decimal(request.form.get("montant_paye_caisse", 0))
            observations = request.form.get("observations", "").strip()
            mode_calcul = request.form.get("mode_calcul", "PRIX_TOTAL")
            nuitees_incluses_tarif = int(request.form.get("nuitees_incluses_tarif", 0))

            # Vérifier que l'acte n'est pas annulé
            cursor.execute(
                """
                    SELECT est_annule
                    FROM medecin_interne_actes
                    WHERE id_acte = %s
                    """,
                (id_acte,),
            )

            acte_check = cursor.fetchone()
            if acte_check and acte_check["est_annule"]:
                flash("Impossible de modifier un acte annulé", "danger")
                return redirect(
                    url_for("medecin_interne_actes_detail", id_acte=id_acte)
                )

            # Récupérer la spécialité du médecin
            cursor.execute(
                """
                SELECT d.id_specialty, s.name_specialty
                FROM doctors d
                         LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE d.id = %s
                           """,
                (id_doctor,),
            )
            doctor_info = cursor.fetchone()

            id_specialite = doctor_info["id_specialty"] if doctor_info else None
            nom_specialite = doctor_info["name_specialty"] if doctor_info else None
            pourcentage_medecin = get_pourcentage_medecin_interne(cursor, id_doctor)

            # ========== SUPPRIMER LES ANCIENNES DONNÉES ==========
            cursor.execute(
                "DELETE FROM medecin_interne_consommables WHERE id_acte = %s",
                (id_acte,),
            )
            cursor.execute(
                "DELETE FROM medecin_interne_consommables_medecin WHERE id_acte = %s",
                (id_acte,),
            )
            cursor.execute(
                "DELETE FROM medecin_interne_hospitalisation WHERE id_acte = %s",
                (id_acte,),
            )
            cursor.execute(
                "DELETE FROM medecin_interne_supplements WHERE id_acte = %s", (id_acte,)
            )
            cursor.execute(
                "DELETE FROM medecin_interne_actes_supplementaires WHERE id_acte_principal = %s",
                (id_acte,),
            )
            cursor.execute(
                "DELETE FROM medecin_interne_anesthesie WHERE id_acte = %s", (id_acte,)
            )

            # ========== CONSOMMABLES SPÉCIFIQUES ==========
            prix_consommables = Decimal("0")
            consommables_ids = request.form.getlist("consommable_id[]")
            consommables_qtes = request.form.getlist("consommable_qte[]")

            for i, cons_id in enumerate(consommables_ids):
                if cons_id and cons_id.strip():
                    qte = to_decimal(
                        consommables_qtes[i] if i < len(consommables_qtes) else 1
                    )
                    if qte > 0:
                        cursor.execute(
                            "SELECT prix, description FROM produits WHERE id_produit = %s",
                            (cons_id,),
                        )
                        prod = cursor.fetchone()
                        if prod:
                            prix_unit = to_decimal(prod["prix"])
                            prix_total = prix_unit * qte
                            prix_consommables += prix_total

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_consommables
                                    (id_acte, id_produit, description, quantite, prix_unitaire, prix_total)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                           """,
                                (
                                    id_acte,
                                    cons_id,
                                    prod["description"],
                                    qte,
                                    prix_unit,
                                    prix_total,
                                ),
                            )

            # ========== HOSPITALISATION ==========
            prix_hospitalisation = Decimal("0")
            dates_entree = request.form.getlist("hosp_date_entree[]")
            dates_sortie = request.form.getlist("hosp_date_sortie[]")
            types_chambre_ids = request.form.getlist("hosp_type_chambre[]")

            for i in range(len(dates_entree)):
                if dates_entree[i] and dates_sortie[i] and types_chambre_ids[i]:
                    cursor.execute(
                        """
                        SELECT prix_unitaire, nom_type
                        FROM type_chambre
                        WHERE id_type_chambre = %s
                                   """,
                        (types_chambre_ids[i],),
                    )
                    chambre = cursor.fetchone()
                    if chambre:
                        d_entree = datetime.strptime(dates_entree[i], "%Y-%m-%d").date()
                        d_sortie = datetime.strptime(dates_sortie[i], "%Y-%m-%d").date()
                        nb_jours_total = (d_sortie - d_entree).days
                        nb_jours_a_facturer = max(
                            0, nb_jours_total - nuitees_incluses_tarif
                        )
                        prix_unit = to_decimal(chambre["prix_unitaire"])
                        prix_total = prix_unit * nb_jours_a_facturer
                        prix_hospitalisation += prix_total

                        est_reanimation = (
                            "RÉANIMATION" in chambre["nom_type"].upper()
                            or "REANIMATION" in chambre["nom_type"].upper()
                        )

                        cursor.execute(
                            """
                            INSERT INTO medecin_interne_hospitalisation
                            (id_acte, id_type_chambre, date_entree, date_sortie,
                             nombre_nuitees, nombre_nuitees_facturees,
                             prix_unitaire, prix_total, est_hors_forfait, type_hospitalisation)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                                       """,
                            (
                                id_acte,
                                types_chambre_ids[i],
                                dates_entree[i],
                                dates_sortie[i],
                                nb_jours_total,
                                nb_jours_a_facturer,
                                prix_unit,
                                prix_total,
                                "REANIMATION" if est_reanimation else "STANDARD",
                            ),
                        )

            # ========== SUPPLÉMENTS ==========
            prix_supplements = Decimal("0")
            supp_types = request.form.getlist("supplement_type[]")
            supp_descriptions = request.form.getlist("supplement_description[]")
            supp_prix = request.form.getlist("supplement_prix[]")

            for i in range(len(supp_types)):
                if supp_types[i] and supp_prix[i]:
                    prix = to_decimal(supp_prix[i])
                    if prix > 0:
                        prix_supplements += prix
                        desc = (
                            supp_descriptions[i] if i < len(supp_descriptions) else ""
                        )

                        cursor.execute(
                            """
                            INSERT INTO medecin_interne_supplements
                                (id_acte, type_supplement, description, prix)
                            VALUES (%s, %s, %s, %s)
                                       """,
                            (id_acte, supp_types[i], desc, prix),
                        )

            # ========== ACTES SUPPLÉMENTAIRES ==========
            prix_actes_supplementaires = Decimal("0")
            actes_supp_ids = request.form.getlist("acte_supp_id[]")
            actes_supp_qtes = request.form.getlist("acte_supp_qte[]")

            for i, acte_id in enumerate(actes_supp_ids):
                if acte_id and acte_id.strip():
                    qte = to_decimal(
                        actes_supp_qtes[i] if i < len(actes_supp_qtes) else 1
                    )
                    if qte > 0:
                        cursor.execute(
                            "SELECT prix, nom_acte FROM actes_supplement WHERE id_acte = %s",
                            (acte_id,),
                        )
                        acte_type = cursor.fetchone()
                        if acte_type:
                            prix_unit = to_decimal(acte_type["prix"])
                            prix_total = prix_unit * qte
                            prix_actes_supplementaires += prix_total

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_actes_supplementaires
                                (id_acte_principal, id_type_acte, nom_acte, quantite, prix_unitaire, prix_total)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                           """,
                                (
                                    id_acte,
                                    acte_id,
                                    acte_type["nom_acte"],
                                    qte,
                                    prix_unit,
                                    prix_total,
                                ),
                            )

            # ========== ANESTHÉSIE ==========
            acte_anesth_id = request.form.get("acte_anesth_id")
            intervenant1_id = request.form.get("intervenant1_id")
            intervenant2_id = request.form.get("intervenant2_id")

            from app.anesthesie_honoraires.anesthesie_honoraires import (
                calculer_honoraires_anesthesie,
                get_tarif_forfaitaire_anesthesie,
            )

            prix_anesthesie = Decimal("0")

            if acte_anesth_id and intervenant1_id and intervenant2_id:
                try:
                    prix_anesthesie = get_tarif_forfaitaire_anesthesie(
                        cursor, acte_anesth_id
                    )
                    duree_reelle = duree_bloc

                    if intervenant1_id:
                        cursor.execute(
                            """
                            SELECT id_type_intervenant
                            FROM anesthesie_personnel
                            WHERE id_personnel_anesthesie = %s
                                       """,
                            (intervenant1_id,),
                        )
                        intervenant1 = cursor.fetchone()

                        if intervenant1:
                            honoraires1 = calculer_honoraires_anesthesie(
                                cursor,
                                acte_anesth_id,
                                intervenant1["id_type_intervenant"],
                                duree_reelle,
                            )

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_anesthesie
                                (id_acte, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                           """,
                                (
                                    id_acte,
                                    acte_anesth_id,
                                    intervenant1_id,
                                    duree_reelle,
                                    honoraires1,
                                    g.user["id_personnel"],
                                ),
                            )

                    if intervenant2_id:
                        cursor.execute(
                            """
                            SELECT id_type_intervenant
                            FROM anesthesie_personnel
                            WHERE id_personnel_anesthesie = %s
                                       """,
                            (intervenant2_id,),
                        )
                        intervenant2 = cursor.fetchone()

                        if intervenant2:
                            honoraires2 = calculer_honoraires_anesthesie(
                                cursor,
                                acte_anesth_id,
                                intervenant2["id_type_intervenant"],
                                duree_reelle,
                            )

                            cursor.execute(
                                """
                                INSERT INTO medecin_interne_anesthesie
                                (id_acte, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                           """,
                                (
                                    id_acte,
                                    acte_anesth_id,
                                    intervenant2_id,
                                    duree_reelle,
                                    honoraires2,
                                    g.user["id_personnel"],
                                ),
                            )

                except Exception as e:
                    app.logger.warning(
                        f"Erreur anesthésie lors de la modification: {str( e )}"
                    )
                    flash(
                        f"Attention: L'anesthésie n'a pas pu être enregistrée: {str( e )}",
                        "warning",
                    )

            # ========== CONSOMMABLES MÉDECIN ==========
            prix_consommables_medecin = Decimal("0")
            cons_med_descriptions = request.form.getlist(
                "consommable_medecin_description[]"
            )
            cons_med_prix = request.form.getlist("consommable_medecin_prix[]")

            for i in range(len(cons_med_descriptions)):
                if cons_med_descriptions[i] and cons_med_prix[i]:
                    prix = to_decimal(cons_med_prix[i])
                    if prix > 0:
                        prix_consommables_medecin += prix

                        cursor.execute(
                            """
                            INSERT INTO medecin_interne_consommables_medecin
                                (id_acte, description, prix)
                            VALUES (%s, %s, %s)
                                       """,
                            (id_acte, cons_med_descriptions[i], prix),
                        )

            # ========== CALCULS FINAUX ==========

            # -- Calcul du supplément consommables (plafonnement) --
            prix_consommables_supplement = None
            if mode_calcul == "PRIX_TOTAL":
                cursor.execute(
                    """
                    SELECT id_produit, quantite_max
                    FROM medecin_interne_plafond_consommables
                    WHERE id_doctor = %s AND est_actif = 1
                """,
                    (id_doctor,),
                )
                plafonds_rows = cursor.fetchall()

                if plafonds_rows:
                    # Par défaut 0 (gratuit) sauf si dépassement car des plafonds sont configurés
                    prix_consommables_supplement = Decimal("0")
                    plafonds_dict = {
                        r["id_produit"]: r["quantite_max"] for r in plafonds_rows
                    }

                    cursor.execute(
                        """
                        SELECT id_produit, quantite, prix_unitaire
                        FROM medecin_interne_consommables
                        WHERE id_acte = %s
                    """,
                        (id_acte,),
                    )
                    conso_rows = cursor.fetchall()

                    prix_consommables_supplement = Decimal("0")
                    for conso in conso_rows:
                        qte_consommee = to_decimal(conso["quantite"])
                        prix_unit = to_decimal(conso["prix_unitaire"])
                        qte_plafond = Decimal(
                            str(plafonds_dict.get(conso["id_produit"], 0))
                        )
                        exces = qte_consommee - qte_plafond
                        if exces > 0:
                            prix_consommables_supplement += prix_unit * exces

            calcul_final = calculer_acte(
                prix_acte_base,
                prix_consommables,
                prix_hospitalisation,
                prix_supplements,
                prix_actes_supplementaires,
                prix_anesthesie,
                pourcentage_medecin,
                mode_calcul,
                prix_consommables_supplement=prix_consommables_supplement,
            )

            # AJOUTER les consommables médecin à la part médecin
            part_medecin_finale = (
                calcul_final["part_medecin"] + prix_consommables_medecin
            )

            difference_paiement = montant_paye_caisse - part_medecin_finale
            statut_paiement = calculer_statut_paiement(
                part_medecin_finale - montant_paye_caisse
            )

            # ========== MISE À JOUR DE L'ACTE ==========
            cursor.execute(
                """
                UPDATE medecin_interne_actes
                SET id_doctor                         = %s,
                    patient                           = %s,
                    date_acte                         = %s,
                    heure_acte                        = %s,
                    nom_acte                          = %s,
                    duree_bloc                        = %s,
                    id_specialite                     = %s,
                    nom_specialite                    = %s,
                    pourcentage_medecin               = %s,
                    prix_acte_base                    = %s,
                    nuitees_incluses_tarif            = %s,
                    prix_consommables_specifiques     = %s,
                    prix_hospitalisation_hors_forfait = %s,
                    prix_supplements                  = %s,
                    prix_actes_supplementaires        = %s,
                    prix_anesthesie                   = %s,
                    prix_consommables_medecin         = %s,
                    total_deductions                  = %s,
                    base_calcul                       = %s,
                    part_medecin                      = %s,
                    part_clinique                     = %s,
                    statut_paiement                   = %s,
                    mode_calcul                       = %s,
                    observations                      = %s,
                    updated_at                        = NOW(),
                    updated_by                        = %s
                WHERE id_acte = %s
                           """,
                (
                    id_doctor,
                    patient,
                    date_acte,
                    heure_acte,
                    nom_acte,
                    duree_bloc,
                    id_specialite,
                    nom_specialite,
                    pourcentage_medecin,
                    prix_acte_base,
                    nuitees_incluses_tarif,
                    prix_consommables,
                    prix_hospitalisation,
                    prix_supplements,
                    prix_actes_supplementaires,
                    prix_anesthesie,
                    prix_consommables_medecin,
                    calcul_final["total_deductions"],
                    calcul_final["base_calcul"],
                    part_medecin_finale,
                    calcul_final["part_clinique"],
                    statut_paiement,
                    mode_calcul,
                    observations,
                    g.user["id_personnel"],
                    id_acte,
                ),
            )

            connection.commit()

            flash(
                f"Acte modifié avec succès. Part médecin: {float( part_medecin_finale ):.2f} DA",
                "success",
            )
            return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

    except Exception as e:
        if connection:
            try:
                connection.rollback()
            except:
                pass
        app.logger.error(f"Erreur modification acte: {str( e )}")
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors de la modification: {str( e )}", "danger")
        return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

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


# À ajouter dans medecins_internes.py


@app.route("/medecin_interne/actes/<int:id_acte>/annuler", methods=["POST"])
@login_required
@handle_errors()
@handle_errors()
def medecin_interne_actes_annuler(id_acte):
    """Annuler un acte médecin interne"""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Récupérer le motif
        motif = request.form.get("motif_annulation", "").strip()
        if not motif:
            flash("Le motif d'annulation est obligatoire", "danger")
            return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

        # Vérifier que l'acte existe et n'est pas déjà annulé
        cursor.execute(
            """
            SELECT a.*,
                   d.numero_decharge,
                   d.statut as statut_decharge
            FROM medecin_interne_actes a
                     LEFT JOIN medecin_interne_decharges d ON a.id_decharge_medecin = d.id_decharge
            WHERE a.id_acte = %s
                       """,
            (id_acte,),
        )

        acte = cursor.fetchone()
        if not acte:
            flash("Acte non trouvé", "danger")
            return redirect(url_for("medecin_interne_actes_list"))

        if acte["est_annule"]:
            flash("Cet acte est déjà annulé", "warning")
            return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

        # Vérifier si l'acte est dans une décharge payée
        if acte["id_decharge_medecin"] and acte["statut_decharge"] == "PAYE":
            flash(
                f'Impossible d\'annuler cet acte : il est dans la décharge {acte[ "numero_decharge" ]} qui est déjà payée. '
                "Veuillez d'abord annuler ou modifier la décharge.",
                "danger",
            )
            return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

        # Vérifier s'il y a des paiements patients non annulés
        cursor.execute(
            """
            SELECT COUNT(*) as nb_paiements, SUM(montant_paye) as total_paye
            FROM medecin_interne_paiements
            WHERE id_acte = %s
              AND est_annule = FALSE
                       """,
            (id_acte,),
        )

        paiements = cursor.fetchone()

        if paiements["nb_paiements"] > 0:
            flash(
                f'Attention : Cet acte a {paiements[ "nb_paiements" ]} paiement(s) patient non annulé(s) '
                f'pour un total de {float( paiements[ "total_paye" ] ):.2f} DA. '
                "Ces paiements seront également marqués comme invalides.",
                "warning",
            )

        # Annuler l'acte
        cursor.execute(
            """
            UPDATE medecin_interne_actes
            SET est_annule       = TRUE,
                motif_annulation = %s,
                annule_par       = %s,
                annule_at        = NOW(),
                updated_at       = NOW(),
                updated_by       = %s
            WHERE id_acte = %s
                       """,
            (motif, g.user["id_personnel"], g.user["id_personnel"], id_acte),
        )

        # Annuler tous les paiements liés non encore annulés
        cursor.execute(
            """
            UPDATE medecin_interne_paiements
            SET est_annule = TRUE,
                motif_annulation = 'Annulation automatique suite à l annulation du dossier patient',
                annule_par = %s,
                annule_at = NOW()
            WHERE id_acte = %s AND est_annule = FALSE
            """,
            (g.user["id_personnel"], id_acte),
        )

        # 1. Annuler les consommables
        cursor.execute(
            """
            UPDATE medecin_interne_consommables
            SET est_annule = TRUE,
                motif_annulation = 'Annulation dossier patient',
                annule_par = %s,
                annule_at = NOW()
            WHERE id_acte = %s
        """,
            (g.user["id_personnel"], id_acte),
        )

        # 2. Annuler l'hospitalisation
        cursor.execute(
            """
            UPDATE medecin_interne_hospitalisation
            SET est_annule = TRUE,
                motif_annulation = 'Annulation dossier patient',
                annule_par = %s,
                annule_at = NOW()
            WHERE id_acte = %s
        """,
            (g.user["id_personnel"], id_acte),
        )

        # 3. Annuler les suppléments
        cursor.execute(
            """
            UPDATE medecin_interne_supplements
            SET est_annule = TRUE,
                motif_annulation = 'Annulation dossier patient',
                annule_par = %s,
                annule_at = NOW()
            WHERE id_acte = %s
        """,
            (g.user["id_personnel"], id_acte),
        )

        # 4. Annuler l'anesthésie
        cursor.execute(
            """
            UPDATE medecin_interne_anesthesie
            SET est_annule = TRUE,
                motif_annulation = 'Annulation dossier patient',
                annule_par = %s,
                annule_at = NOW()
            WHERE id_acte = %s
        """,
            (g.user["id_personnel"], id_acte),
        )

        # 5. Annuler la situation médecin (encaissement initial)
        cursor.execute(
            """
            UPDATE medecin_interne_situations
            SET est_annule = TRUE,
                motif_annulation = 'Annulation dossier patient',
                annule_par = %s,
                annule_at = NOW()
            WHERE id_acte = %s
        """,
            (g.user["id_personnel"], id_acte),
        )

        # 6. Annuler tous les paiements liés à cet acte
        cursor.execute(
            """
            UPDATE medecin_interne_paiements
            SET est_annule = TRUE,
                motif_annulation = 'Annulation dossier patient',
                annule_par = %s,
                annule_at = NOW()
            WHERE id_acte = %s AND est_annule = FALSE
        """,
            (g.user["id_personnel"], id_acte),
        )

        # Si l'acte est dans une décharge non payée, la mettre à jour
        if acte["id_decharge_medecin"] and acte["statut_decharge"] in [
            "BROUILLON",
            "VALIDE",
            "PAIEMENT_PARTIEL",
        ]:
            # Retirer l'acte de la décharge
            cursor.execute(
                """
                DELETE
                FROM medecin_interne_decharge_actes
                WHERE id_decharge = %s
                  AND id_acte = %s
                           """,
                (acte["id_decharge_medecin"], id_acte),
            )

            # Recalculer les totaux de la décharge
            cursor.execute(
                """
                UPDATE medecin_interne_decharges d
                SET montant_total = (SELECT COALESCE(SUM(montant_honoraires), 0)
                                     FROM medecin_interne_decharge_actes
                                     WHERE id_decharge = d.id_decharge),
                    nb_actes      = (SELECT COUNT(*)
                                     FROM medecin_interne_decharge_actes
                                     WHERE id_decharge = d.id_decharge),
                    solde_restant = montant_total - COALESCE(montant_paye_total, 0)
                WHERE id_decharge = %s
                           """,
                (acte["id_decharge_medecin"],),
            )

            # Retirer la référence de décharge de l'acte
            cursor.execute(
                """
                UPDATE medecin_interne_actes
                SET id_decharge_medecin = NULL
                WHERE id_acte = %s
                           """,
                (id_acte,),
            )

        connection.commit()

        flash(f"Acte #{id_acte} annulé avec succès", "success")
        return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

    except Exception as e:
        if connection:
            try:
                connection.rollback()
            except:
                pass
        app.logger.error(f"Erreur annulation acte: {str( e )}")
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors de l'annulation: {str( e )}", "danger")
        return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

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


@app.route("/medecin_interne/actes/<int:id_acte>/restaurer", methods=["POST"])
@login_required
@handle_errors()
@handle_errors()
def medecin_interne_actes_restaurer(id_acte):
    """Restaurer un acte annulé"""
    with get_cursor() as (conn, cursor):
        # Vérifier que l'acte existe et est annulé
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

        if not acte["est_annule"]:
            flash("Cet acte n'est pas annulé", "warning")
            return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))

        # Restaurer l'acte
        cursor.execute(
            """
            UPDATE medecin_interne_actes
            SET est_annule       = FALSE,
                motif_annulation = NULL,
                annule_par       = NULL,
                annule_at        = NULL,
                updated_at       = NOW(),
                updated_by       = %s
            WHERE id_acte = %s
                       """,
            (g.user["id_personnel"], id_acte),
        )

        # Restaurer les paiements annulés automatiquement
        cursor.execute(
            """
            UPDATE medecin_interne_paiements
            SET est_annule = FALSE,
                motif_annulation = NULL,
                annule_par = NULL,
                annule_at = NULL
            WHERE id_acte = %s
              AND est_annule = TRUE
              AND motif_annulation LIKE 'Annulation automatique%%'
            """,
            (id_acte,),
        )

        # Restaurer les détails (Consommables, Hosp, Supp, Anesth, Situations)
        tables_details = [
            "medecin_interne_consommables",
            "medecin_interne_hospitalisation",
            "medecin_interne_supplements",
            "medecin_interne_anesthesie",
            "medecin_interne_situations",
        ]

        for table in tables_details:
            cursor.execute(
                f"""
                UPDATE {table}
                SET est_annule = FALSE,
                    motif_annulation = NULL,
                    annule_par = NULL,
                    annule_at = NULL
                WHERE id_acte = %s
                  AND est_annule = TRUE
                  AND motif_annulation = 'Annulation dossier patient'
            """,
                (id_acte,),
            )

        flash(f"Acte #{id_acte} restauré avec succès", "success")
        return redirect(url_for("medecin_interne_actes_detail", id_acte=id_acte))


# ========================================================================
# EXPORT PDF
# ========================================================================


@app.route("/medecin_interne/actes/<int:id_acte>/export-pdf")
@login_required
@login_required
def medecin_interne_acte_export_pdf(id_acte):
    """Export PDF d'un acte médecin interne"""
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

    with get_cursor() as (conn, cursor):
        # Récupérer l'acte
        cursor.execute(
            """
            SELECT a.*,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   s.name_specialty,
                   CONCAT(p.nom, ' ', p.prenom)           as created_by_name
            FROM medecin_interne_actes a
                     LEFT JOIN doctors d ON a.id_doctor = d.id
                     LEFT JOIN specialty s ON a.id_specialite = s.id_specialty
                     LEFT JOIN personnel p ON a.created_by = p.id_personnel
            WHERE a.id_acte = %s
                       """,
            (id_acte,),
        )

        acte = cursor.fetchone()
        if not acte:
            flash("Acte non trouvé", "danger")
            return redirect(url_for("medecin_interne_actes_list"))

        # Récupérer les éléments liés
        cursor.execute(
            """
            SELECT c.*, p.description as produit_nom
            FROM medecin_interne_consommables c
                     LEFT JOIN produits p ON c.id_produit = p.id_produit
            WHERE c.id_acte = %s
                       """,
            (id_acte,),
        )
        consommables = cursor.fetchall()

        cursor.execute(
            """
            SELECT h.*, t.nom_type as type_chambre_nom, t.est_standard
            FROM medecin_interne_hospitalisation h
                     LEFT JOIN type_chambre t ON h.id_type_chambre = t.id_type_chambre
            WHERE h.id_acte = %s
            ORDER BY h.date_entree
                       """,
            (id_acte,),
        )
        hospitalisations = cursor.fetchall()

        cursor.execute(
            """
            SELECT *
            FROM medecin_interne_supplements
            WHERE id_acte = %s
            ORDER BY type_supplement
                       """,
            (id_acte,),
        )
        supplements = cursor.fetchall()

        cursor.execute(
            """
            SELECT *
            FROM medecin_interne_actes_supplementaires
            WHERE id_acte_principal = %s
                       """,
            (id_acte,),
        )
        actes_supplementaires = cursor.fetchall()

        cursor.execute(
            """
            SELECT ma.*,
                   ata.nom_acte,
                   CONCAT(ap.prenom, ' ', ap.nom) as nom_personnel,
                   ait.nom_type                   as type_intervenant
            FROM medecin_interne_anesthesie ma
                     LEFT JOIN anesthesie_type_acte ata ON ma.id_acte_anesthesie = ata.id_acte_anesthesie
                     LEFT JOIN anesthesie_personnel ap ON ma.id_personnel_anesthesie = ap.id_personnel_anesthesie
                     LEFT JOIN anesthesie_intervenant_type ait ON ap.id_type_intervenant = ait.id_type_intervenant
            WHERE ma.id_acte = %s
                       """,
            (id_acte,),
        )
        anesthesie = cursor.fetchall()

        # Générer le PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.2 * cm,
            leftMargin=1.2 * cm,
            topMargin=1 * cm,
            bottomMargin=1.5 * cm,
        )

        story = []
        styles = getSampleStyleSheet()

        # Styles personnalisés
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

        # Logo + QR Code
        try:
            logo = Image(
                "app/static/images/entet_inaya.png", width=10 * cm, height=3 * cm
            )
        except:
            logo = Paragraph("", styles["Normal"])

        # Generate QR code if qr_uuid exists
        qr_img_flow = None
        if acte.get("qr_uuid"):
            try:
                import base64 as b64module

                from app.utils.qr_utils import generer_qr_base64

                qr_b64_str = generer_qr_base64("BLOC_INTERNE", acte["qr_uuid"])
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

        # Titre
        story.append(
            Paragraph(
                f"Acte Médecin Interne N° A-{acte.get( 'id_acte', 0 ):05d}", title_style
            )
        )
        story.append(Spacer(1, 0.4 * cm))

        # Informations générales
        story.append(Paragraph("1. INFORMATIONS GÉNÉRALES", header_style))

        info_data = [
            [
                "Patient:",
                acte.get("patient", ""),
                "Médecin:",
                acte.get("doctor_name", ""),
            ],
            [
                "Spécialité:",
                acte.get("nom_specialite", ""),
                "Date:",
                (
                    acte.get("date_acte", "").strftime("%d/%m/%Y")
                    if acte.get("date_acte")
                    else ""
                ),
            ],
            [
                "Intervention:",
                acte.get("nom_acte", ""),
                "Mode calcul:",
                (
                    "Prix Total"
                    if acte.get("mode_calcul") == "PRIX_TOTAL"
                    else "Prix Base"
                ),
            ],
        ]

        info_table = Table(info_data, colWidths=[3.5 * cm, 5 * cm, 3 * cm, 5 * cm])
        info_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f4f6")),
                ]
            )
        )
        story.append(info_table)
        story.append(Spacer(1, 0.4 * cm))

        # Consommables
        if consommables:
            story.append(Paragraph("2. CONSOMMABLES SPÉCIFIQUES", header_style))
            cons_data = [["Produit", "Qté", "P.U.", "Total"]]
            for c in consommables:
                cons_data.append(
                    [
                        c.get("description", "")[:40],
                        str(int(c.get("quantite", 0))),
                        f"{float( c.get( 'prix_unitaire', 0 ) ):.2f} DA",
                        f"{float( c.get( 'prix_total', 0 ) ):.2f} DA",
                    ]
                )

            cons_table = Table(cons_data, colWidths=[8 * cm, 2 * cm, 3 * cm, 3 * cm])
            cons_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f59e0b")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ]
                )
            )
            story.append(cons_table)
            story.append(Spacer(1, 0.4 * cm))

        # Hospitalisations
        if hospitalisations:
            story.append(Paragraph("3. HOSPITALISATION", header_style))
            hosp_data = [
                [
                    "Type chambre",
                    "Entrée",
                    "Sortie",
                    "Nuitées",
                    "Facturées",
                    "Prix/nuit",
                    "Total",
                ]
            ]
            for h in hospitalisations:
                hosp_data.append(
                    [
                        h.get("type_chambre_nom", "")[:20],
                        (
                            h.get("date_entree", "").strftime("%d/%m/%Y")
                            if h.get("date_entree")
                            else ""
                        ),
                        (
                            h.get("date_sortie", "").strftime("%d/%m/%Y")
                            if h.get("date_sortie")
                            else ""
                        ),
                        str(int(h.get("nombre_nuitees", 0))),
                        str(int(h.get("nombre_nuitees_facturees", 0))),
                        f"{float( h.get( 'prix_unitaire', 0 ) ):.2f}",
                        f"{float( h.get( 'prix_total', 0 ) ):.2f}",
                    ]
                )

            hosp_table = Table(
                hosp_data,
                colWidths=[
                    3.5 * cm,
                    2.5 * cm,
                    2.5 * cm,
                    1.5 * cm,
                    1.5 * cm,
                    2 * cm,
                    2.5 * cm,
                ],
            )
            hosp_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ffffff")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3b82f6")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("ALIGN", (3, 1), (-1, -1), "CENTER"),
                    ]
                )
            )
            story.append(hosp_table)
            story.append(Spacer(1, 0.4 * cm))

        # Récapitulatif financier
        story.append(Paragraph("RÉCAPITULATIF FINANCIER", header_style))
        recap_data = []
        recap_data.append(
            ["Prix de base:", f"{float( acte.get( 'prix_acte_base', 0 ) ):.2f} DA"]
        )

        if float(acte.get("prix_hospitalisation_hors_forfait", 0)) > 0:
            recap_data.append(
                [
                    "Hospitalisation:",
                    f"{float( acte.get( 'prix_hospitalisation_hors_forfait', 0 ) ):.2f} DA",
                ]
            )

        if float(acte.get("prix_supplements", 0)) > 0:
            recap_data.append(
                ["Suppléments:", f"{float( acte.get( 'prix_supplements', 0 ) ):.2f} DA"]
            )

        if float(acte.get("prix_actes_supplementaires", 0)) > 0:
            recap_data.append(
                [
                    "Actes supp.:",
                    f"{float( acte.get( 'prix_actes_supplementaires', 0 ) ):.2f} DA",
                ]
            )

        if float(acte.get("prix_anesthesie", 0)) > 0:
            recap_data.append(
                ["Anesthésie:", f"{float( acte.get( 'prix_anesthesie', 0 ) ):.2f} DA"]
            )

        if float(acte.get("prix_consommables_specifiques", 0)) > 0:
            recap_data.append(
                [
                    "Consommables:",
                    f"{float( acte.get( 'prix_consommables_specifiques', 0 ) ):.2f} DA",
                ]
            )

        recap_data.append(
            [
                "Total déductions:",
                f"{float( acte.get( 'total_deductions', 0 ) ):.2f} DA",
            ]
        )
        recap_data.append(
            ["Base de calcul:", f"{float( acte.get( 'base_calcul', 0 ) ):.2f} DA"]
        )
        recap_data.append(
            [
                f"PART MÉDECIN ({acte.get( 'pourcentage_medecin', 0 )}%):",
                f"{float( acte.get( 'part_medecin', 0 ) ):.2f} DA",
            ]
        )

        recap_table = Table(recap_data, colWidths=[11 * cm, 5.5 * cm])
        recap_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -3), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, -2), (-1, -1), 11),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LINEABOVE", (0, -2), (-1, -2), 2, colors.HexColor("#6366f1")),
                    ("BACKGROUND", (0, -2), (-1, -2), colors.HexColor("#e0e7ff")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        story.append(recap_table)

        # Build PDF
        doc.build(story)

        pdf_data = buffer.getvalue()
        buffer.close()

        # Nom du fichier
        patient = acte.get("patient", "Inconnu").replace(" ", "_")
        date = (
            acte.get("date_acte", "").strftime("%Y%m%d")
            if acte.get("date_acte")
            else ""
        )
        filename = f"Acte_A-{id_acte:05d}_{patient}_{date}.pdf"

        response = make_response(pdf_data)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response
