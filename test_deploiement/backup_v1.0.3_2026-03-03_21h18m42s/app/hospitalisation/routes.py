"""
Routes du module Hospitalisation
Plan d'étage interactif, admissions, transferts, sorties
"""

from datetime import datetime
from math import ceil

from flask import (
    g,
    jsonify,
    render_template,
    request,
    session,
)

from app import app, get_db_connection, get_pg_connection
from app.error import handle_errors
from app.utils.utiles import login_required

# ================================================================
#  HELPERS
# ================================================================


def _fetch_patient_from_his(patient_oid):
    """Recherche un patient dans le HIS PostgreSQL par son OID."""
    try:
        conn = get_pg_connection()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pat_oid, pat_nom, pat_prenom, pat_date_naissance, pat_sexe
            FROM t_patient
            WHERE pat_oid = %s
            LIMIT 1
        """,
            (patient_oid,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {
                "oid": row[0],
                "nom": row[1],
                "prenom": row[2],
                "date_naissance": str(row[3]) if row[3] else None,
                "sexe": row[4],
            }
    except Exception as e:
        print(f"Erreur HIS patient lookup: {e}")
    return None


def _search_patients_his(search_term, limit=20):
    """Recherche de patients dans le HIS PostgreSQL."""
    try:
        conn = get_pg_connection()
        if not conn:
            return []
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pat_oid, pat_nom, pat_prenom, pat_date_naissance, pat_sexe
            FROM t_patient
            WHERE UPPER(pat_nom) LIKE UPPER(%s)
               OR UPPER(pat_prenom) LIKE UPPER(%s)
               OR pat_oid LIKE %s
            ORDER BY pat_nom, pat_prenom
            LIMIT %s
        """,
            (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%", limit),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "oid": r[0],
                "nom": r[1],
                "prenom": r[2],
                "date_naissance": str(r[3]) if r[3] else None,
                "sexe": r[4],
                "display": f"{r[1]} {r[2]}",
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Erreur HIS patient search: {e}")
    return []


def _calculate_stay_cost(date_debut, date_fin, prix_nuit, service_data):
    """
    Calcule le coût d'un séjour.
    - Séjour court (<seuil heures) : tarif_fixe + (heures * prix_nuit/24)
    - Séjour normal : jours * prix_nuit (minimum 1 nuit)
    """
    if not date_fin:
        date_fin = datetime.now()

    delta = date_fin - date_debut
    total_hours = delta.total_seconds() / 3600

    seuil = service_data.get("seuil_sejour_court_heures", 24) or 24
    tarif_fixe = float(service_data.get("tarif_sejour_court", 0) or 0)
    prix = float(prix_nuit)

    is_short = total_hours < seuil

    if is_short:
        tarif_horaire = prix / 24
        cout_variable = round(tarif_horaire * total_hours, 2)
        cout_total = round(tarif_fixe + cout_variable, 2)
        formule = f"Fixe({tarif_fixe}) + {round(total_hours,1)}h × {round(tarif_horaire,2)}/h = {cout_total}"
        return {
            "cout_total": cout_total,
            "est_sejour_court": True,
            "duree_heures": round(total_hours, 2),
            "jours": 0,
            "tarif_fixe": tarif_fixe,
            "tarif_horaire": round(tarif_horaire, 2),
            "cout_variable": cout_variable,
            "formule": formule,
        }
    else:
        jours = max(1, ceil(total_hours / 24))
        cout_total = round(jours * prix, 2)
        formule = f"{jours} nuit(s) × {prix}/nuit = {cout_total}"
        return {
            "cout_total": cout_total,
            "est_sejour_court": False,
            "duree_heures": round(total_hours, 2),
            "jours": jours,
            "tarif_fixe": 0,
            "tarif_horaire": 0,
            "cout_variable": 0,
            "formule": formule,
        }


def _close_attribution(conn, cursor, id_attribution, user_id):
    """Ferme une attribution de lit (date_fin = now) et recalcule le coût."""
    now = datetime.now()

    # Récupérer l'attribution et les données du service
    cursor.execute(
        """
        SELECT al.date_debut, al.prix_nuit_applique, al.id_admission, al.id_lit, al.id_service
        FROM hosp_attributions_lits al
        WHERE al.id_attribution = %s AND al.date_fin IS NULL
    """,
        (id_attribution,),
    )
    attr = cursor.fetchone()

    if not attr:
        return None

    service_data = {}

    cost_info = _calculate_stay_cost(
        attr["date_debut"], now, attr["prix_nuit_applique"], service_data
    )

    cursor.execute(
        """
        UPDATE hosp_attributions_lits
        SET date_fin = %s,
            est_sejour_court = %s,
            cout_calcule = %s,
            tarif_fixe_applique = %s,
            updated_by = %s, updated_at = NOW()
        WHERE id_attribution = %s
    """,
        (
            now,
            cost_info["est_sejour_court"],
            cost_info["cout_total"],
            cost_info["tarif_fixe"],
            user_id,
            id_attribution,
        ),
    )

    # Libérer le lit
    cursor.execute(
        "UPDATE hosp_lits SET est_occupe = 0 WHERE id_lit = %s", (attr["id_lit"],)
    )

    # Sauvegarder dans l'historique
    cursor.execute(
        """
        SELECT c.numero_chambre, l.numero_lit, s.service_name
        FROM hosp_lits l
        JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
        JOIN services s ON c.id_service = s.id_service
        WHERE l.id_lit = %s
    """,
        (attr["id_lit"],),
    )
    info = cursor.fetchone()

    cursor.execute(
        """
        SELECT patient_oid, patient_nom FROM hosp_admissions WHERE id_admission = %s
    """,
        (attr["id_admission"],),
    )
    admission_info = cursor.fetchone()

    if info and admission_info:
        cursor.execute(
            """
            INSERT INTO hosp_historique_sejours
            (id_admission, patient_oid, patient_nom, id_lit, id_chambre, id_service,
             numero_lit, numero_chambre, nom_service,
             date_debut, date_fin, duree_heures, prix_nuit_applique, cout_periode, est_sejour_court)
            VALUES (%s, %s, %s, %s,
                    (SELECT id_chambre FROM hosp_lits WHERE id_lit = %s),
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                attr["id_admission"],
                admission_info["patient_oid"],
                admission_info["patient_nom"],
                attr["id_lit"],
                attr["id_lit"],
                attr["id_service"],
                info["numero_lit"],
                info["numero_chambre"],
                info["service_name"],
                attr["date_debut"],
                now,
                cost_info["duree_heures"],
                attr["prix_nuit_applique"],
                cost_info["cout_total"],
                cost_info["est_sejour_court"],
            ),
        )

    return {
        "id_admission": attr["id_admission"],
        "cost": cost_info["cout_total"],
        "id_lit": attr["id_lit"],
        "id_service": attr["id_service"],
    }


def _recalculate_admission_cost(cursor, id_admission):
    """Recalcule le coût total d'une admission depuis ses attributions."""
    cursor.execute(
        """
        SELECT COALESCE(SUM(cout_calcule), 0) as total
        FROM hosp_attributions_lits
        WHERE id_admission = %s
    """,
        (id_admission,),
    )
    result = cursor.fetchone()
    total = float(result["total"]) if result else 0

    # Pour l'attribution en cours, calculer en temps réel
    cursor.execute(
        """
        SELECT al.date_debut, al.prix_nuit_applique, al.id_service
        FROM hosp_attributions_lits al
        WHERE al.id_admission = %s AND al.date_fin IS NULL
    """,
        (id_admission,),
    )
    current = cursor.fetchone()

    if current:
        service_data = {}
        cost_info = _calculate_stay_cost(
            current["date_debut"],
            datetime.now(),
            current["prix_nuit_applique"],
            service_data,
        )
        total += cost_info["cout_total"]

    # Calcul des consommations et actes
    # 1. Obtenir toutes les inclusions (par chambre ou par service)
    cursor.execute(
        """
        SELECT id_service, id_chambre, id_produit, quantite_par_nuit 
        FROM hosp_produits_inclus
    """
    )
    inclusions = cursor.fetchall()
    incl_dict = {}
    for inc in inclusions:
        cle = (
            f"{inc['id_chambre']}" if inc["id_chambre"] else f"srv_{inc['id_service']}"
        )
        if cle not in incl_dict:
            incl_dict[cle] = {}
        incl_dict[cle][inc["id_produit"]] = inc["quantite_par_nuit"]

    # 2. Calculer les produits inclus par le total des nuits passées
    produits_inclus_total = {}

    # Récupérer toutes les attributions pour calculer les nuits
    cursor.execute(
        """
        SELECT al.id_service, l.id_chambre as lit_chambre, al.date_debut, COALESCE(al.date_fin, NOW()) as limite_fin
        FROM hosp_attributions_lits al
        LEFT JOIN hosp_lits l ON al.id_lit = l.id_lit
        WHERE al.id_admission = %s
    """,
        (id_admission,),
    )
    attributions = cursor.fetchall()

    for attr in attributions:
        chambre_id = attr["chambre_id"] if "chambre_id" in attr else attr["lit_chambre"]
        cle_chambre = f"{chambre_id}"
        cle_service = f"srv_{attr['id_service']}"
        dict_incl = incl_dict.get(cle_chambre, incl_dict.get(cle_service, {}))

        delta = attr["limite_fin"] - attr["date_debut"]
        heures = delta.total_seconds() / 3600
        jours = (
            max(1, ceil(heures / 24)) if heures >= 24 else 0
        )  # Inclus après 1 nuit complète minimum

        for id_prod, qte_nuit in dict_incl.items():
            if id_prod not in produits_inclus_total:
                produits_inclus_total[id_prod] = 0
            produits_inclus_total[id_prod] += jours * qte_nuit

    # 3. Calculer les consommations
    cursor.execute(
        """
        SELECT type_element, id_element, quantite, prix_unitaire
        FROM hosp_consommations
        WHERE id_admission = %s AND est_annule = 0
    """,
        (id_admission,),
    )
    consommations = cursor.fetchall()

    cout_consommations = 0
    consos_groupes = {}  # pour cumuler les qtés de produits

    for c in consommations:
        if c["type_element"] == "produit":
            id_prod = c["id_element"]
            if id_prod not in consos_groupes:
                consos_groupes[id_prod] = {"qte": 0, "prix": c["prix_unitaire"]}
            consos_groupes[id_prod]["qte"] += c["quantite"]
        else:
            # Actes, Labo, Radio facturés à 100%
            cout_consommations += c["quantite"] * float(c["prix_unitaire"])

    # 4. Ajouter le surplus des produits
    for id_prod, data in consos_groupes.items():
        qte_totale = data["qte"]
        qte_incluse = produits_inclus_total.get(id_prod, 0)
        qte_facturable = max(0, qte_totale - qte_incluse)
        cout_consommations += qte_facturable * float(data["prix"])

    total += cout_consommations

    cursor.execute(
        """
        UPDATE hosp_admissions SET cout_total = %s WHERE id_admission = %s
    """,
        (total, id_admission),
    )

    return total


# ================================================================
#  PAGE ROUTES
# ================================================================


@app.route("/hospitalisation/services")
@login_required
@handle_errors()
def hospitalisation_services():
    """Liste des services hospitaliers."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM hosp_chambres c WHERE c.id_service = s.id_service AND c.est_active = 1) as nb_chambres,
                   (SELECT COUNT(*) FROM hosp_lits l
                    JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
                    WHERE c.id_service = s.id_service AND l.est_actif = 1) as nb_lits,
                   (SELECT COUNT(*) FROM hosp_lits l
                    JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
                    WHERE c.id_service = s.id_service AND l.est_actif = 1 AND l.est_occupe = 1) as nb_occupes,
                   (SELECT COUNT(*) FROM hosp_demandes_admission d
                    WHERE d.id_service = s.id_service AND d.statut = 'en_attente') as nb_attente
            FROM services s
            WHERE s.est_hospitalier = 1
            ORDER BY s.service_name
        """
        )
        services = cursor.fetchall()
    finally:
        conn.close()

    return render_template(
        "hospitalisation/services_list.html",
        title="Hospitalisation - Services",
        services=services,
        user=g.user,
    )


@app.route("/hospitalisation/floor_plan/<int:id_service>")
@login_required
@handle_errors()
def hospitalisation_floor_plan(id_service):
    """Page plan d'étage pour un service donné."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Récupérer le service
        cursor.execute(
            "SELECT * FROM services WHERE id_service = %s AND est_hospitalier = 1",
            (id_service,),
        )
        service = cursor.fetchone()
        if not service:
            # flash("Service non trouvé ou non hospitalier.", "error") # Removed flash
            return render_template(
                "hospitalisation/services_list.html",
                title="Hospitalisation",
                services=[],
                user=g.user,
            )

        # Récupérer les chambres avec infos type
        cursor.execute(
            """
            SELECT c.*, tc.nom_type, tc.capacite as type_capacite, tc.prix_unitaire as type_prix
            FROM hosp_chambres c
            JOIN type_chambre tc ON c.id_type_chambre = tc.id_type_chambre
            WHERE c.id_service = %s AND c.est_active = 1
            ORDER BY c.numero_chambre
        """,
            (id_service,),
        )
        chambres = cursor.fetchall()

        # Récupérer les lits pour chaque chambre
        chambres_data = []
        for chambre in chambres:
            cursor.execute(
                """
                SELECT l.*,
                       al.id_admission, al.date_debut as attr_debut, al.prix_nuit_applique,
                       a.patient_nom, a.patient_oid, a.date_admission
                FROM hosp_lits l
                LEFT JOIN hosp_attributions_lits al ON l.id_lit = al.id_lit AND al.date_fin IS NULL
                LEFT JOIN hosp_admissions a ON al.id_admission = a.id_admission AND a.statut = 'en_cours'
                WHERE l.id_chambre = %s AND l.est_actif = 1
                ORDER BY l.numero_lit
            """,
                (chambre["id_chambre"],),
            )
            lits = cursor.fetchall()
            chambres_data.append({**chambre, "lits": lits})

        # Demandes en attente pour ce service
        cursor.execute(
            """
            SELECT d.*, 
                   CONCAT(d.patient_nom) as display_name,
                   CONCAT(doc.last_name, ' ', doc.first_name) as medecin_nom
            FROM hosp_demandes_admission d
            LEFT JOIN doctors doc ON d.id_medecin = doc.id
            WHERE d.id_service = %s AND d.statut = 'en_attente'
            ORDER BY 
                FIELD(d.priorite, 'urgente', 'haute', 'normale', 'basse'),
                d.created_at ASC
        """,
            (id_service,),
        )
        demandes_attente = cursor.fetchall()

        # Statistiques
        cursor.execute(
            """
            SELECT 
                COUNT(DISTINCT l.id_lit) as total_lits,
                SUM(CASE WHEN l.est_occupe = 1 THEN 1 ELSE 0 END) as lits_occupes,
                SUM(CASE WHEN l.est_occupe = 0 AND l.est_actif = 1 THEN 1 ELSE 0 END) as lits_disponibles
            FROM hosp_lits l
            JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
            WHERE c.id_service = %s AND l.est_actif = 1 AND c.est_active = 1
        """,
            (id_service,),
        )
        stats = cursor.fetchone()

        # Autres services hospitaliers (pour transferts inter-services)
        cursor.execute(
            """
            SELECT id_service, service_name, color,
                   (SELECT COUNT(*) FROM hosp_lits l2
                    JOIN hosp_chambres c2 ON l2.id_chambre = c2.id_chambre
                    WHERE c2.id_service = s.id_service AND l2.est_actif = 1 AND l2.est_occupe = 0) as lits_dispo
            FROM services s
            WHERE s.est_hospitalier = 1 AND s.id_service != %s
            ORDER BY s.service_name
        """,
            (id_service,),
        )
        autres_services = cursor.fetchall()

        # Médecins disponibles
        cursor.execute(
            "SELECT id, CONCAT(last_name, ' ', first_name) as nom FROM doctors ORDER BY last_name, first_name"
        )
        medecins = cursor.fetchall()

    finally:
        conn.close()

    return render_template(
        "hospitalisation/floor_plan.html",
        title=f'Plan - {service["service_name"]}',
        service=service,
        chambres=chambres_data,
        demandes_attente=demandes_attente,
        stats=stats,
        autres_services=autres_services,
        medecins=medecins,
        user=g.user,
    )


# ================================================================
#  API ROUTES - AJAX
# ================================================================


@app.route("/hospitalisation/api/search_patients")
@login_required
@handle_errors()
def hospitalisation_search_patients():
    """Recherche de patients dans le HIS."""
    term = request.args.get("q", "").strip()
    if len(term) < 2:
        return jsonify({"results": []})
    results = _search_patients_his(term, limit=20)
    return jsonify({"results": results})


@app.route("/hospitalisation/api/add_admission_request", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_add_admission_request():
    """Créer une nouvelle demande d'admission."""
    patient_oid = request.form.get("patient_oid", "").strip()
    patient_nom = request.form.get("patient_nom", "").strip()
    id_service = request.form.get("id_service")
    id_medecin = request.form.get("id_medecin") or None
    motif = request.form.get("motif", "").strip()
    priorite = request.form.get("priorite", "normale")

    if not patient_oid or not patient_nom or not id_service:
        return (
            jsonify({"success": False, "error": "Champs obligatoires manquants"}),
            400,
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier qu'il n'y a pas déjà une demande en attente pour ce patient dans ce service
        cursor.execute(
            """
            SELECT COUNT(*) as cnt FROM hosp_demandes_admission
            WHERE patient_oid = %s AND id_service = %s AND statut = 'en_attente'
        """,
            (patient_oid, id_service),
        )
        if cursor.fetchone()["cnt"] > 0:
            return jsonify(
                {
                    "success": False,
                    "error": "Une demande en attente existe déjà pour ce patient dans ce service",
                }
            )

        cursor.execute(
            """
            INSERT INTO hosp_demandes_admission
            (patient_oid, patient_nom, id_service, id_medecin, motif, priorite, statut,
             created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'en_attente', %s, NOW())
        """,
            (
                patient_oid,
                patient_nom,
                id_service,
                id_medecin,
                motif,
                priorite,
                g.user["id_personnel"],
            ),
        )
        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Demande d'admission créée",
                "request_id": cursor.lastrowid,
                "patient_name": patient_nom,
            }
        )
    finally:
        conn.close()


@app.route("/hospitalisation/api/admit_patient", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_admit_patient():
    """Admettre un patient (drag & drop vers un lit)."""
    data = request.get_json()
    request_id = data.get("request_id")
    bed_id = data.get("bed_id")
    continue_admission_id = data.get("continue_admission_id")

    if not request_id or not bed_id:
        return jsonify({"success": False, "error": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Récupérer la demande
        cursor.execute(
            """
            SELECT d.*
            FROM hosp_demandes_admission d
            WHERE d.id_demande = %s AND d.statut = 'en_attente'
        """,
            (request_id,),
        )
        demande = cursor.fetchone()
        if not demande:
            return jsonify(
                {"success": False, "error": "Demande introuvable ou déjà traitée"}
            )

        # Vérifier que le lit est disponible
        cursor.execute(
            """
            SELECT l.*, c.id_service, c.prix_nuit, c.numero_chambre,
                   tc.prix_unitaire as type_prix
            FROM hosp_lits l
            JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
            JOIN type_chambre tc ON c.id_type_chambre = tc.id_type_chambre
            WHERE l.id_lit = %s AND l.est_occupe = 0 AND l.est_actif = 1
        """,
            (bed_id,),
        )
        lit = cursor.fetchone()
        if not lit:
            return jsonify({"success": False, "error": "Lit non disponible"})

        now = datetime.now()
        user_id = g.user["id_personnel"]
        prix_nuit = (
            float(lit["prix_nuit"])
            if float(lit["prix_nuit"]) > 0
            else float(lit["type_prix"])
        )

        # Cas transfert inter-service : continuer l'admission existante
        if continue_admission_id:
            admission_id = int(continue_admission_id)

            # Vérifier que l'admission existe et est en cours
            cursor.execute(
                "SELECT * FROM hosp_admissions WHERE id_admission = %s AND statut = 'en_cours'",
                (admission_id,),
            )
            if not cursor.fetchone():
                return jsonify(
                    {"success": False, "error": "Admission source introuvable"}
                )

            continuation = True
        else:
            # Nouvelle admission
            cursor.execute(
                """
                INSERT INTO hosp_admissions
                (id_demande, patient_oid, patient_nom, statut, date_admission, created_by, created_at)
                VALUES (%s, %s, %s, 'en_cours', %s, %s, NOW())
            """,
                (
                    request_id,
                    demande["patient_oid"],
                    demande["patient_nom"],
                    now,
                    user_id,
                ),
            )
            admission_id = cursor.lastrowid
            continuation = False

        # Créer l'attribution de lit
        cursor.execute(
            """
            INSERT INTO hosp_attributions_lits
            (id_admission, id_lit, id_service, date_debut, prix_nuit_applique, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """,
            (admission_id, bed_id, lit["id_service"], now, prix_nuit, user_id),
        )

        # Marquer le lit comme occupé
        cursor.execute(
            "UPDATE hosp_lits SET est_occupe = 1 WHERE id_lit = %s", (bed_id,)
        )

        # Mettre à jour la demande
        cursor.execute(
            """
            UPDATE hosp_demandes_admission
            SET statut = 'admis', updated_by = %s, updated_at = NOW()
            WHERE id_demande = %s
        """,
            (user_id, request_id),
        )

        conn.commit()

        return jsonify(
            {
                "success": True,
                "admission_id": admission_id,
                "patient_name": demande["patient_nom"],
                "continuation": continuation,
                "message": "Patient admis avec succès",
            }
        )
    finally:
        conn.close()


@app.route("/hospitalisation/api/transfer_patient", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_transfer_patient():
    """Transfert intra-service (lit à lit dans le même service)."""
    data = request.get_json()
    admission_id = data.get("admission_id")
    new_bed_id = data.get("new_bed_id")
    reason = data.get("reason", "Transfert intra-service")

    if not admission_id or not new_bed_id:
        return jsonify({"success": False, "error": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        user_id = g.user["id_personnel"]

        # Récupérer l'attribution actuelle
        cursor.execute(
            """
            SELECT al.*, c.id_service
            FROM hosp_attributions_lits al
            JOIN hosp_lits l ON al.id_lit = l.id_lit
            JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
            WHERE al.id_admission = %s AND al.date_fin IS NULL
        """,
            (admission_id,),
        )
        current_attr = cursor.fetchone()
        if not current_attr:
            return jsonify(
                {"success": False, "error": "Attribution actuelle introuvable"}
            )

        # Vérifier le nouveau lit
        cursor.execute(
            """
            SELECT l.*, c.id_service, c.prix_nuit, tc.prix_unitaire as type_prix
            FROM hosp_lits l
            JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
            JOIN type_chambre tc ON c.id_type_chambre = tc.id_type_chambre
            WHERE l.id_lit = %s AND l.est_occupe = 0 AND l.est_actif = 1
        """,
            (new_bed_id,),
        )
        new_lit = cursor.fetchone()
        if not new_lit:
            return jsonify({"success": False, "error": "Nouveau lit non disponible"})

        # Fermer l'attribution actuelle
        _close_attribution(conn, cursor, current_attr["id_attribution"], user_id)

        # Créer nouvelle attribution
        now = datetime.now()
        prix_nuit = (
            float(new_lit["prix_nuit"])
            if float(new_lit["prix_nuit"]) > 0
            else float(new_lit["type_prix"])
        )

        cursor.execute(
            """
            INSERT INTO hosp_attributions_lits
            (id_admission, id_lit, id_service, date_debut, prix_nuit_applique, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """,
            (admission_id, new_bed_id, new_lit["id_service"], now, prix_nuit, user_id),
        )

        # Marquer le nouveau lit comme occupé
        cursor.execute(
            "UPDATE hosp_lits SET est_occupe = 1 WHERE id_lit = %s", (new_bed_id,)
        )

        # Enregistrer le transfert
        cursor.execute(
            """
            INSERT INTO hosp_transferts
            (id_admission, id_attribution_source, id_service_source, id_service_dest,
             type_transfert, date_transfert, motif, created_by, created_at)
            VALUES (%s, %s, %s, %s, 'intra_service', NOW(), %s, %s, NOW())
        """,
            (
                admission_id,
                current_attr["id_attribution"],
                current_attr["id_service"],
                new_lit["id_service"],
                reason,
                user_id,
            ),
        )

        # Recalculer le coût total
        _recalculate_admission_cost(cursor, admission_id)

        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Transfert intra-service effectué",
                "transfer_type": "intra_service",
            }
        )
    finally:
        conn.close()


@app.route("/hospitalisation/api/transfer_to_service", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_transfer_to_service():
    """Transfert inter-services (patient va dans la liste d'attente du service cible)."""
    data = request.get_json()
    admission_id = data.get("admission_id")
    new_service_id = data.get("new_service_id")
    reason = data.get("reason", "Transfert inter-services")

    if not admission_id or not new_service_id:
        return jsonify({"success": False, "error": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        user_id = g.user["id_personnel"]

        # Récupérer l'attribution actuelle
        cursor.execute(
            """
            SELECT al.*
            FROM hosp_attributions_lits al
            WHERE al.id_admission = %s AND al.date_fin IS NULL
        """,
            (admission_id,),
        )
        current_attr = cursor.fetchone()
        if not current_attr:
            return jsonify(
                {"success": False, "error": "Attribution actuelle introuvable"}
            )

        # Récupérer l'admission
        cursor.execute(
            "SELECT * FROM hosp_admissions WHERE id_admission = %s AND statut = 'en_cours'",
            (admission_id,),
        )
        admission = cursor.fetchone()
        if not admission:
            return jsonify({"success": False, "error": "Admission introuvable"})

        # Fermer l'attribution actuelle
        _close_attribution(conn, cursor, current_attr["id_attribution"], user_id)

        # Enregistrer le transfert
        cursor.execute(
            """
            INSERT INTO hosp_transferts
            (id_admission, id_attribution_source, id_service_source, id_service_dest,
             type_transfert, date_transfert, motif, created_by, created_at)
            VALUES (%s, %s, %s, %s, 'inter_service', NOW(), %s, %s, NOW())
        """,
            (
                admission_id,
                current_attr["id_attribution"],
                current_attr["id_service"],
                new_service_id,
                reason,
                user_id,
            ),
        )

        # Créer une nouvelle demande dans le service cible (liée à l'admission existante)
        cursor.execute(
            """
            INSERT INTO hosp_demandes_admission
            (patient_oid, patient_nom, id_service, statut, motif, priorite,
             id_admission_source, created_by, created_at)
            VALUES (%s, %s, %s, 'en_attente', %s, 'normale', %s, %s, NOW())
        """,
            (
                admission["patient_oid"],
                admission["patient_nom"],
                new_service_id,
                reason,
                admission_id,
                user_id,
            ),
        )

        # Recalculer le coût
        _recalculate_admission_cost(cursor, admission_id)

        conn.commit()

        # Nom du service de destination
        cursor.execute(
            "SELECT service_name FROM services WHERE id_service = %s", (new_service_id,)
        )
        dest_service = cursor.fetchone()

        return jsonify(
            {
                "success": True,
                "message": f'Patient transféré vers {dest_service["service_name"] if dest_service else "le service"}',
                "transfer_type": "inter_service_continuous",
            }
        )
    finally:
        conn.close()


@app.route(
    "/hospitalisation/api/discharge_patient/<int:admission_id>", methods=["GET", "POST"]
)
@login_required
@handle_errors()
def hospitalisation_discharge_patient(admission_id):
    """Sortie d'un patient."""
    if request.method == "GET":
        # Retourner les infos pour préparer le formulaire de sortie
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT a.*, al.id_lit, al.date_debut, al.prix_nuit_applique,
                       l.numero_lit, c.numero_chambre, s.service_name
                FROM hosp_admissions a
                LEFT JOIN hosp_attributions_lits al ON a.id_admission = al.id_admission AND al.date_fin IS NULL
                LEFT JOIN hosp_lits l ON al.id_lit = l.id_lit
                LEFT JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
                LEFT JOIN services s ON c.id_service = s.id_service
                WHERE a.id_admission = %s
            """,
                (admission_id,),
            )
            admission = cursor.fetchone()
            if not admission:
                return jsonify({"success": False, "error": "Admission introuvable"})
            return jsonify({"success": True, "admission": dict(admission)})
        finally:
            conn.close()

    # POST: effectuer la sortie
    destination = request.form.get("discharge_destination", "domicile")
    notes = request.form.get("discharge_notes", "")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        user_id = g.user["id_personnel"]
        now = datetime.now()

        # Fermer l'attribution actuelle si elle existe
        cursor.execute(
            """
            SELECT id_attribution FROM hosp_attributions_lits
            WHERE id_admission = %s AND date_fin IS NULL
        """,
            (admission_id,),
        )
        current_attr = cursor.fetchone()
        if current_attr:
            _close_attribution(conn, cursor, current_attr["id_attribution"], user_id)

        # Recalculer le coût final
        total_cost = _recalculate_admission_cost(cursor, admission_id)

        # Mettre à jour l'admission
        cursor.execute(
            """
            UPDATE hosp_admissions
            SET statut = 'sorti', date_sortie = %s,
                motif_sortie = %s, destination_sortie = %s,
                cout_total = %s,
                updated_by = %s, updated_at = NOW()
            WHERE id_admission = %s
        """,
            (now, notes, destination, total_cost, user_id, admission_id),
        )

        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Sortie enregistrée avec succès",
                "total_cost": total_cost,
            }
        )
    finally:
        conn.close()


@app.route("/hospitalisation/api/cancel_request/<int:request_id>", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_cancel_request(request_id):
    """Annuler une demande d'admission."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE hosp_demandes_admission
            SET statut = 'annule', updated_by = %s, updated_at = NOW()
            WHERE id_demande = %s AND statut = 'en_attente'
        """,
            (g.user["id_personnel"], request_id),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify(
                {"success": False, "error": "Demande introuvable ou déjà traitée"}
            )

        return jsonify({"success": True, "message": "Demande annulée"})
    finally:
        conn.close()


@app.route("/hospitalisation/api/admission_detail/<int:admission_id>")
@login_required
@handle_errors()
def hospitalisation_admission_detail(admission_id):
    """Détails complets d'une admission pour le modal."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Admission
        cursor.execute(
            """
            SELECT a.*
            FROM hosp_admissions a
            WHERE a.id_admission = %s
        """,
            (admission_id,),
        )
        admission = cursor.fetchone()
        if not admission:
            return jsonify({"success": False, "error": "Admission introuvable"})

        # Lit actuel
        cursor.execute(
            """
            SELECT al.*, l.numero_lit, c.numero_chambre, c.prix_nuit,
                   s.service_name, s.id_service,
                   s.tarif_sejour_court, s.seuil_sejour_court_heures,
                   tc.nom_type
            FROM hosp_attributions_lits al
            JOIN hosp_lits l ON al.id_lit = l.id_lit
            JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
            JOIN services s ON c.id_service = s.id_service
            JOIN type_chambre tc ON c.id_type_chambre = tc.id_type_chambre
            WHERE al.id_admission = %s AND al.date_fin IS NULL
        """,
            (admission_id,),
        )
        current_bed = cursor.fetchone()

        # Toutes les attributions (parcours détaillé)
        cursor.execute(
            """
            SELECT al.*, l.numero_lit, c.numero_chambre, c.prix_nuit,
                   s.service_name, s.tarif_sejour_court, s.seuil_sejour_court_heures
            FROM hosp_attributions_lits al
            JOIN hosp_lits l ON al.id_lit = l.id_lit
            JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
            JOIN services s ON c.id_service = s.id_service
            WHERE al.id_admission = %s
            ORDER BY al.date_debut ASC
        """,
            (admission_id,),
        )
        attributions = cursor.fetchall()

        # Construire le parcours détaillé
        detailed_journey = []
        cumulative_cost = 0
        sejours_courts = []
        sejours_normaux = []

        for attr in attributions:
            service_data = {
                "tarif_sejour_court": attr["tarif_sejour_court"],
                "seuil_sejour_court_heures": attr["seuil_sejour_court_heures"],
            }

            date_debut = attr["date_debut"] or datetime.now()
            prix_nuit = float(attr["prix_nuit_applique"] or 0)

            if attr["date_fin"]:
                cost_info = _calculate_stay_cost(
                    date_debut,
                    attr["date_fin"],
                    prix_nuit,
                    service_data,
                )
            else:
                cost_info = _calculate_stay_cost(
                    date_debut,
                    datetime.now(),
                    prix_nuit,
                    service_data,
                )

            cumulative_cost += cost_info["cout_total"]

            period = {
                "service": attr["service_name"],
                "room": attr["numero_chambre"],
                "bed": attr["numero_lit"],
                "start_date": (
                    attr["date_debut"].isoformat() if attr["date_debut"] else None
                ),
                "end_date": attr["date_fin"].isoformat() if attr["date_fin"] else None,
                "night_price": prix_nuit,
                "is_current": attr["date_fin"] is None,
                "is_short_stay": cost_info["est_sejour_court"],
                "duration_hours": cost_info["duree_heures"],
                "days": cost_info["jours"],
                "period_cost": cost_info["cout_total"],
                "cumulative_cost": round(cumulative_cost, 2),
                "billing_details": {
                    "formule": cost_info["formule"],
                    "tarif_fixe_service": cost_info["tarif_fixe"],
                    "tarif_horaire": cost_info["tarif_horaire"],
                    "cout_variable": cost_info["cout_variable"],
                    "duree_heures": cost_info["duree_heures"],
                },
            }
            detailed_journey.append(period)

            if cost_info["est_sejour_court"]:
                sejours_courts.append(
                    {
                        "service": attr["service_name"],
                        "duree_heures": cost_info["duree_heures"],
                        "prix_nuit_applique": prix_nuit,
                        "tarif_fixe_service": cost_info["tarif_fixe"],
                        "tarif_horaire": cost_info["tarif_horaire"],
                        "cout_variable": cost_info["cout_variable"],
                        "cout_total": cost_info["cout_total"],
                        "formule": cost_info["formule"],
                    }
                )
            else:
                sejours_normaux.append(
                    {
                        "service": attr["service_name"],
                        "jours": cost_info["jours"],
                        "prix_nuit": prix_nuit,
                        "cout_total": cost_info["cout_total"],
                    }
                )

        # Transferts
        cursor.execute(
            """
            SELECT t.*, 
                   s_src.service_name as from_service,
                   s_dst.service_name as to_service
            FROM hosp_transferts t
            JOIN services s_src ON t.id_service_source = s_src.id_service
            JOIN services s_dst ON t.id_service_dest = s_dst.id_service
            WHERE t.id_admission = %s
            ORDER BY t.date_transfert ASC
        """,
            (admission_id,),
        )
        transfers = cursor.fetchall()

        transfers_data = []
        for t in transfers:
            transfers_data.append(
                {
                    "date": (
                        t["date_transfert"].isoformat() if t["date_transfert"] else None
                    ),
                    "from_service": t["from_service"],
                    "to_service": t["to_service"],
                    "type": t["type_transfert"],
                    "reason": t["motif"],
                    "financial_impact": {
                        "impact_description": f"Transfert {t['type_transfert']}",
                        "price_difference": 0,
                    },
                }
            )

        # Consommations
        cursor.execute(
            """
            SELECT c.*,
                   CONCAT(p.nom, ' ', p.prenom) as createur,
                   CONCAT(p2.nom, ' ', p2.prenom) as annulateur
            FROM hosp_consommations c
            LEFT JOIN personnel p ON c.created_by = p.id_personnel
            LEFT JOIN personnel p2 ON c.annule_by = p2.id_personnel
            WHERE c.id_admission = %s
            ORDER BY c.date_consommation DESC
        """,
            (admission_id,),
        )
        raw_consos = cursor.fetchall()

        consommations = []
        total_actes = 0

        for c in raw_consos:
            consommations.append(
                {
                    "id": c["id_consommation"],
                    "type": c["type_element"],
                    "libelle": c["libelle"],
                    "quantite": c["quantite"],
                    "prix_unitaire": float(c["prix_unitaire"] or 0),
                    "total": float(c["prix_unitaire"] or 0) * c["quantite"],
                    "date": (
                        c["date_consommation"].isoformat()
                        if c["date_consommation"]
                        else None
                    ),
                    "createur": c["createur"],
                    "est_annule": c["est_annule"],
                    "annule_by": c["annulateur"],
                    "annule_at": c["annule_at"].isoformat() if c["annule_at"] else None,
                    "motif_annulation": c["motif_annulation"],
                }
            )
            if not c["est_annule"]:
                if c["type_element"] != "produit":
                    total_actes += c["quantite"] * float(c["prix_unitaire"] or 0)

        # Durée totale
        date_admission = admission["date_admission"] or datetime.now()
        date_ref = admission["date_sortie"] or datetime.now()
        total_hours = (date_ref - date_admission).total_seconds() / 3600
        total_days = max(1, ceil(total_hours / 24))

        # Historique des admissions du même patient
        cursor.execute(
            """
            SELECT id_admission, date_admission, date_sortie, statut, cout_total
            FROM hosp_admissions
            WHERE patient_oid = %s AND id_admission != %s
            ORDER BY date_admission DESC
            LIMIT 10
        """,
            (admission["patient_oid"], admission_id),
        )
        past_admissions = cursor.fetchall()

        result = {
            "id": admission["id_admission"],
            "patient": {
                "last_name": (
                    admission["patient_nom"].split(" ")[0]
                    if admission["patient_nom"]
                    else ""
                ),
                "first_name": (
                    " ".join(admission["patient_nom"].split(" ")[1:])
                    if admission["patient_nom"]
                    and len(admission["patient_nom"].split(" ")) > 1
                    else ""
                ),
            },
            "status": admission["statut"],
            "admission_date": (
                admission["date_admission"].isoformat()
                if admission["date_admission"]
                else None
            ),
            "discharge_date": (
                admission["date_sortie"].isoformat()
                if admission["date_sortie"]
                else None
            ),
            "estimated_cost": round(cumulative_cost, 2),
            "length_of_stay_hours": round(total_hours, 2),
            "length_of_stay_days": total_days,
            "length_of_stay": total_days,
            "bed": (
                {
                    "bed_number": current_bed["numero_lit"] if current_bed else None,
                    "room": {
                        "room_number": (
                            current_bed["numero_chambre"] if current_bed else None
                        ),
                        "service": current_bed["service_name"] if current_bed else None,
                        "night_price": (
                            float(current_bed["prix_nuit_applique"] or 0)
                            if current_bed
                            else 0
                        ),
                        "room_type": current_bed["nom_type"] if current_bed else None,
                    },
                }
                if current_bed
                else None
            ),
            "detailed_journey": detailed_journey,
            "transfers_history": transfers_data,
            "billing_summary": {
                "nombre_sejours_courts": len(sejours_courts),
                "nombre_sejours_normaux": len(sejours_normaux),
                "sejours_courts": sejours_courts,
                "sejours_normaux": sejours_normaux,
                "total_actes": total_actes,
            },
            "consommations": consommations,
            "patient_admissions_history": [
                {
                    "admission_date": (
                        pa["date_admission"].isoformat()
                        if pa["date_admission"]
                        else None
                    ),
                    "discharge_date": (
                        pa["date_sortie"].isoformat() if pa["date_sortie"] else None
                    ),
                    "status": pa["statut"],
                    "total_cost": float(pa["cout_total"] or 0),
                    "length_of_stay": (
                        max(
                            1,
                            ceil(
                                (
                                    (pa["date_sortie"] or datetime.now())
                                    - pa["date_admission"]
                                ).total_seconds()
                                / 86400
                            ),
                        )
                        if pa["date_admission"]
                        else 0
                    ),
                    "attending_doctor": "N/A",
                    "services_visited": [],
                    "cost_breakdown": [],
                }
                for pa in past_admissions
            ],
        }

        return jsonify({"success": True, "admission": result})
    finally:
        conn.close()


@app.route("/hospitalisation/api/check_requests_status", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_check_requests_status():
    """Vérifier le statut de demandes d'admission (polling)."""
    data = request.get_json()
    request_ids = data.get("request_ids", [])

    if not request_ids:
        return jsonify({"processed_requests": []})

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        format_strings = ",".join(["%s"] * len(request_ids))
        cursor.execute(
            f"""
            SELECT id_demande FROM hosp_demandes_admission
            WHERE id_demande IN ({format_strings}) AND statut != 'en_attente'
        """,
            tuple(request_ids),
        )
        processed = [row["id_demande"] for row in cursor.fetchall()]

        return jsonify({"processed_requests": processed})
    finally:
        conn.close()


# ================================================================
#  CONSOMMATIONS & INCLUSIONS API
# ================================================================


@app.route("/hospitalisation/api/add_consommation", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_add_consommation():
    """Ajouter une consommation (Produit, Acte, Radio, Labo) à une admission."""
    data = request.get_json()
    id_admission = data.get("id_admission")
    type_element = data.get("type_element")
    id_element = data.get("id_element") or None
    libelle = data.get("libelle")
    quantite = data.get("quantite", 1)
    prix_unitaire = data.get("prix_unitaire", 0.0)

    if not id_admission or not type_element or not libelle:
        return jsonify({"success": False, "error": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier admission
        cursor.execute(
            "SELECT statut FROM hosp_admissions WHERE id_admission = %s",
            (id_admission,),
        )
        adm = cursor.fetchone()
        if not adm:
            return jsonify({"success": False, "error": "Admission introuvable"}), 404

        cursor.execute(
            """
            INSERT INTO hosp_consommations 
            (id_admission, type_element, id_element, libelle, quantite, prix_unitaire, created_by, date_consommation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """,
            (
                id_admission,
                type_element,
                id_element,
                libelle,
                quantite,
                prix_unitaire,
                g.user["id_personnel"],
            ),
        )

        # Recalculer le total
        new_total = _recalculate_admission_cost(cursor, id_admission)
        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Consommation enregistrée.",
                "new_total": new_total,
            }
        )
    finally:
        conn.close()


@app.route(
    "/hospitalisation/api/cancel_consommation/<int:id_consommation>", methods=["POST"]
)
@login_required
@handle_errors()
def hospitalisation_cancel_consommation(id_consommation):
    """Annuler (soft-delete) une consommation avec traçabilité."""
    # Check privilege
    if "HOSP_ANNULER_CONSOMMATION" not in session.get("privileges", []):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Vous n'avez pas le privilège pour annuler une consommation.",
                }
            ),
            403,
        )

    data = request.get_json()
    motif = data.get("motif_annulation", "Erreur de saisie")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id_admission, est_annule FROM hosp_consommations WHERE id_consommation = %s",
            (id_consommation,),
        )
        conso = cursor.fetchone()
        if not conso:
            return jsonify({"success": False, "error": "Consommation introuvable"}), 404
        if conso["est_annule"] == 1:
            return jsonify({"success": False, "error": "Déjà annulée"}), 400

        cursor.execute(
            """
            UPDATE hosp_consommations 
            SET est_annule = 1, annule_by = %s, annule_at = NOW(), motif_annulation = %s
            WHERE id_consommation = %s
        """,
            (g.user["id_personnel"], motif, id_consommation),
        )

        new_total = _recalculate_admission_cost(cursor, conso["id_admission"])
        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Consommation annulée avec succès.",
                "new_total": new_total,
            }
        )
    finally:
        conn.close()


@app.route("/hospitalisation/api/search_items_for_billing")
@login_required
@handle_errors()
def hospitalisation_search_items_for_billing():
    """Recherche de produits ou actes pour la saisie de consommation."""
    term = request.args.get("q", "").strip()
    item_type = request.args.get("type", "produit")  # produit ou acte

    if len(term) < 2:
        return jsonify({"results": []})

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        results = []

        if item_type == "produit":
            cursor.execute(
                """
                SELECT id_produit as id, description as text, prix as price
                FROM produits
                WHERE est_actif = 1 AND description LIKE %s
                LIMIT 50
            """,
                (f"%{term}%",),
            )
            results = cursor.fetchall()
        elif item_type == "acte":
            # actes_supplement is the new table without conventions
            cursor.execute(
                """
                SELECT id_acte as id, nom_acte as text, prix as price
                FROM actes_supplement
                WHERE est_actif = 1 AND nom_acte LIKE %s
                LIMIT 50
            """,
                (f"%{term}%",),
            )
            results = cursor.fetchall()

        # Format for select2 / choices or generic JS
        formatted = [
            {"id": r["id"], "text": r["text"], "price": float(r["price"] or 0)}
            for r in results
        ]
        return jsonify({"results": formatted})
    finally:
        conn.close()


@app.route("/hospitalisation/api/produits_inclus")
@login_required
@handle_errors()
def hospitalisation_produits_inclus():
    """Récupérer la liste des produits inclus pour un service ou une chambre."""
    id_service = request.args.get("id_service")
    id_chambre = request.args.get("id_chambre")

    if not id_service and not id_chambre:
        return jsonify({"success": False, "error": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if id_chambre:
            cursor.execute(
                """
                SELECT pi.id_inclusion, pi.id_produit, p.description as nom_produit, pi.quantite_par_nuit 
                FROM hosp_produits_inclus pi
                JOIN produits p ON pi.id_produit = p.id_produit
                WHERE pi.id_chambre = %s
            """,
                (id_chambre,),
            )
        else:
            cursor.execute(
                """
                SELECT pi.id_inclusion, pi.id_produit, p.description as nom_produit, pi.quantite_par_nuit 
                FROM hosp_produits_inclus pi
                JOIN produits p ON pi.id_produit = p.id_produit
                WHERE pi.id_service = %s AND pi.id_chambre IS NULL
            """,
                (id_service,),
            )

        inclus = cursor.fetchall()
        return jsonify({"success": True, "produits": inclus})
    finally:
        conn.close()


@app.route("/hospitalisation/api/save_produits_inclus", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_save_produits_inclus():
    """Enregistrer (ajouter ou modifier) la liste des produits inclus d'un coup."""
    data = request.get_json()
    id_service = data.get("id_service")
    id_chambre = data.get("id_chambre")
    produits = data.get("produits", [])  # [{id_produit, quantite_par_nuit}]

    if not id_service and not id_chambre:
        return jsonify({"success": False, "error": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Supprimer l'ancienne configuration
        if id_chambre:
            cursor.execute(
                "DELETE FROM hosp_produits_inclus WHERE id_chambre = %s", (id_chambre,)
            )
            id_service_val = id_service or None  # Parfois on passe les deux
            for p in produits:
                cursor.execute(
                    """
                    INSERT INTO hosp_produits_inclus (id_service, id_chambre, id_produit, quantite_par_nuit, created_by)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                    (
                        id_service_val,
                        id_chambre,
                        p["id_produit"],
                        p["quantite_par_nuit"],
                        g.user["id_personnel"],
                    ),
                )
        else:
            cursor.execute(
                "DELETE FROM hosp_produits_inclus WHERE id_service = %s AND id_chambre IS NULL",
                (id_service,),
            )
            for p in produits:
                cursor.execute(
                    """
                    INSERT INTO hosp_produits_inclus (id_service, id_chambre, id_produit, quantite_par_nuit, created_by)
                    VALUES (%s, NULL, %s, %s, %s)
                """,
                    (
                        id_service,
                        p["id_produit"],
                        p["quantite_par_nuit"],
                        g.user["id_personnel"],
                    ),
                )

        conn.commit()
        return jsonify({"success": True, "message": "Configuration sauvegardée"})
    finally:
        conn.close()


@app.route("/hospitalisation/api/room_detail/<int:room_id>")
@login_required
@handle_errors()
def hospitalisation_room_detail(room_id):
    """Détails d'une chambre."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.*, tc.nom_type, tc.prix_unitaire, tc.capacite as type_capacite,
                   s.service_name
            FROM hosp_chambres c
            JOIN type_chambre tc ON c.id_type_chambre = tc.id_type_chambre
            JOIN services s ON c.id_service = s.id_service
            WHERE c.id_chambre = %s
        """,
            (room_id,),
        )
        chambre = cursor.fetchone()
        if not chambre:
            return jsonify({"success": False, "error": "Chambre introuvable"})

        cursor.execute(
            """
            SELECT l.*, 
                   a.patient_nom, a.patient_oid, a.id_admission, a.date_admission
            FROM hosp_lits l
            LEFT JOIN hosp_attributions_lits al ON l.id_lit = al.id_lit AND al.date_fin IS NULL
            LEFT JOIN hosp_admissions a ON al.id_admission = a.id_admission AND a.statut = 'en_cours'
            WHERE l.id_chambre = %s AND l.est_actif = 1
            ORDER BY l.numero_lit
        """,
            (room_id,),
        )
        lits = cursor.fetchall()

        return jsonify(
            {
                "success": True,
                "room": dict(chambre),
                "beds": [dict(lit) for lit in lits],
            }
        )
    finally:
        conn.close()


# ================================================================
#  ADMIN / CONFIGURATION
# ================================================================


@app.route("/hospitalisation/config")
@login_required
@handle_errors()
def hospitalisation_config():
    """Page de configuration: services, chambres, lits."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Tous les services
        cursor.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM hosp_chambres c WHERE c.id_service = s.id_service) as nb_chambres,
                   (SELECT COUNT(*) FROM hosp_lits l
                    JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
                    WHERE c.id_service = s.id_service) as nb_lits
            FROM services s WHERE s.est_hospitalier = 1
            ORDER BY s.service_name
        """
        )
        services = cursor.fetchall()

        # Types de chambre
        cursor.execute(
            "SELECT * FROM type_chambre WHERE est_actif = 1 ORDER BY nom_type"
        )
        types_chambre = cursor.fetchall()

        # Chambres avec détails
        cursor.execute(
            """
            SELECT c.*, s.service_name, tc.nom_type,
                   (SELECT COUNT(*) FROM hosp_lits l WHERE l.id_chambre = c.id_chambre) as nb_lits,
                   (SELECT COUNT(*) FROM hosp_lits l WHERE l.id_chambre = c.id_chambre AND l.est_occupe = 1) as nb_occupes
            FROM hosp_chambres c
            JOIN services s ON c.id_service = s.id_service
            JOIN type_chambre tc ON c.id_type_chambre = tc.id_type_chambre
            ORDER BY s.service_name, c.numero_chambre
        """
        )
        chambres = cursor.fetchall()

        # Lits avec détails
        cursor.execute(
            """
            SELECT l.*, c.numero_chambre, s.service_name, s.id_service
            FROM hosp_lits l
            JOIN hosp_chambres c ON l.id_chambre = c.id_chambre
            JOIN services s ON c.id_service = s.id_service
            ORDER BY s.service_name, c.numero_chambre, l.numero_lit
        """
        )
        lits = cursor.fetchall()

    finally:
        conn.close()

    return render_template(
        "hospitalisation/config.html",
        title="Configuration Hospitalisation",
        services=services,
        types_chambre=types_chambre,
        chambres=chambres,
        lits=lits,
        user=g.user,
    )


# ---------- Services Config ----------


@app.route("/hospitalisation/api/config/service/<int:id_service>", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_config_service(id_service):
    """Mettre à jour la config hospitalisation d'un service."""
    data = request.get_json()
    est_hospitalier = data.get("est_hospitalier", 0)
    tarif_fixe = data.get("tarif_sejour_court", 0)
    seuil = data.get("seuil_sejour_court_heures", 24)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE services
            SET est_hospitalier = %s,
                tarif_sejour_court = %s,
                seuil_sejour_court_heures = %s
            WHERE id_service = %s
        """,
            (est_hospitalier, tarif_fixe, seuil, id_service),
        )
        conn.commit()
        return jsonify({"success": True, "message": "Service mis à jour"})
    finally:
        conn.close()


# ---------- Chambres CRUD ----------


@app.route("/hospitalisation/api/config/chambre", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_config_chambre_create():
    """Créer une nouvelle chambre."""
    data = request.get_json()
    id_service = data.get("id_service")
    id_type_chambre = data.get("id_type_chambre")
    numero_chambre = data.get("numero_chambre", "").strip()
    prix_nuit = data.get("prix_nuit", 0)
    etage = data.get("etage", "").strip() or None
    notes = data.get("notes", "").strip() or None

    if not id_service or not id_type_chambre or not numero_chambre:
        return (
            jsonify({"success": False, "error": "Champs obligatoires manquants"}),
            400,
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier que le numéro est unique dans le service
        cursor.execute(
            """
            SELECT COUNT(*) as cnt FROM hosp_chambres
            WHERE id_service = %s AND numero_chambre = %s
        """,
            (id_service, numero_chambre),
        )
        if cursor.fetchone()["cnt"] > 0:
            return jsonify(
                {
                    "success": False,
                    "error": f"Le numéro {numero_chambre} existe déjà dans ce service",
                }
            )

        cursor.execute(
            """
            INSERT INTO hosp_chambres
            (id_service, id_type_chambre, numero_chambre, prix_nuit, etage, notes,
             created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """,
            (
                id_service,
                id_type_chambre,
                numero_chambre,
                prix_nuit,
                etage,
                notes,
                g.user["id_personnel"],
            ),
        )
        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Chambre {numero_chambre} créée",
                "id_chambre": cursor.lastrowid,
            }
        )
    finally:
        conn.close()


@app.route("/hospitalisation/api/config/chambre/<int:id_chambre>", methods=["PUT"])
@login_required
@handle_errors()
def hospitalisation_config_chambre_update(id_chambre):
    """Mettre à jour une chambre."""
    data = request.get_json()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        fields = []
        values = []
        for key in ["id_type_chambre", "numero_chambre", "prix_nuit", "etage", "notes"]:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])

        if not fields:
            return jsonify({"success": False, "error": "Aucun champ à mettre à jour"})

        fields.append("updated_by = %s")
        values.append(g.user["id_personnel"])
        values.append(id_chambre)

        cursor.execute(
            f"""
            UPDATE hosp_chambres SET {', '.join(fields)}, updated_at = NOW()
            WHERE id_chambre = %s
        """,
            values,
        )
        conn.commit()

        return jsonify({"success": True, "message": "Chambre mise à jour"})
    finally:
        conn.close()


@app.route(
    "/hospitalisation/api/config/chambre/<int:id_chambre>/toggle", methods=["POST"]
)
@login_required
@handle_errors()
def hospitalisation_config_chambre_toggle(id_chambre):
    """Activer/désactiver une chambre."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE hosp_chambres SET est_active = NOT est_active,
            updated_by = %s, updated_at = NOW()
            WHERE id_chambre = %s
        """,
            (g.user["id_personnel"], id_chambre),
        )
        conn.commit()
        return jsonify({"success": True, "message": "Statut chambre modifié"})
    finally:
        conn.close()


@app.route("/hospitalisation/api/config/chambre/<int:id_chambre>", methods=["DELETE"])
@login_required
@handle_errors()
def hospitalisation_config_chambre_delete(id_chambre):
    """Supprimer une chambre (uniquement si aucun lit occupé)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier qu'aucun lit n'est occupé
        cursor.execute(
            """
            SELECT COUNT(*) as cnt FROM hosp_lits
            WHERE id_chambre = %s AND est_occupe = 1
        """,
            (id_chambre,),
        )
        if cursor.fetchone()["cnt"] > 0:
            return jsonify(
                {
                    "success": False,
                    "error": "Impossible: des lits sont occupés dans cette chambre",
                }
            )

        cursor.execute("DELETE FROM hosp_chambres WHERE id_chambre = %s", (id_chambre,))
        conn.commit()

        return jsonify({"success": True, "message": "Chambre supprimée"})
    finally:
        conn.close()


# ---------- Lits CRUD ----------


@app.route("/hospitalisation/api/config/lit", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_config_lit_create():
    """Créer un nouveau lit."""
    data = request.get_json()
    id_chambre = data.get("id_chambre")
    numero_lit = data.get("numero_lit", "").strip()
    notes = data.get("notes", "").strip() or None

    if not id_chambre or not numero_lit:
        return (
            jsonify({"success": False, "error": "Champs obligatoires manquants"}),
            400,
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier unicité du numéro de lit dans la chambre
        cursor.execute(
            """
            SELECT COUNT(*) as cnt FROM hosp_lits
            WHERE id_chambre = %s AND numero_lit = %s
        """,
            (id_chambre, numero_lit),
        )
        if cursor.fetchone()["cnt"] > 0:
            return jsonify(
                {
                    "success": False,
                    "error": f"Le lit {numero_lit} existe déjà dans cette chambre",
                }
            )

        cursor.execute(
            """
            INSERT INTO hosp_lits (id_chambre, numero_lit, notes, created_at)
            VALUES (%s, %s, %s, NOW())
        """,
            (id_chambre, numero_lit, notes),
        )
        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Lit {numero_lit} créé",
                "id_lit": cursor.lastrowid,
            }
        )
    finally:
        conn.close()


@app.route("/hospitalisation/api/config/lit/<int:id_lit>", methods=["PUT"])
@login_required
@handle_errors()
def hospitalisation_config_lit_update(id_lit):
    """Mettre à jour un lit."""
    data = request.get_json()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        fields = []
        values = []
        for key in ["numero_lit", "notes"]:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])

        if not fields:
            return jsonify({"success": False, "error": "Aucun champ à mettre à jour"})

        values.append(id_lit)

        cursor.execute(
            f"""
            UPDATE hosp_lits SET {', '.join(fields)}, updated_at = NOW()
            WHERE id_lit = %s
        """,
            values,
        )
        conn.commit()

        return jsonify({"success": True, "message": "Lit mis à jour"})
    finally:
        conn.close()


@app.route("/hospitalisation/api/config/lit/<int:id_lit>/toggle", methods=["POST"])
@login_required
@handle_errors()
def hospitalisation_config_lit_toggle(id_lit):
    """Activer/désactiver un lit."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier que le lit n'est pas occupé
        cursor.execute("SELECT est_occupe FROM hosp_lits WHERE id_lit = %s", (id_lit,))
        lit = cursor.fetchone()
        if lit and lit["est_occupe"]:
            return jsonify(
                {
                    "success": False,
                    "error": "Impossible: ce lit est actuellement occupé",
                }
            )

        cursor.execute(
            """
            UPDATE hosp_lits SET est_actif = NOT est_actif, updated_at = NOW()
            WHERE id_lit = %s
        """,
            (id_lit,),
        )
        conn.commit()
        return jsonify({"success": True, "message": "Statut lit modifié"})
    finally:
        conn.close()


@app.route("/hospitalisation/api/config/lit/<int:id_lit>", methods=["DELETE"])
@login_required
@handle_errors()
def hospitalisation_config_lit_delete(id_lit):
    """Supprimer un lit (uniquement s'il n'est pas occupé)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT est_occupe FROM hosp_lits WHERE id_lit = %s", (id_lit,))
        lit = cursor.fetchone()
        if lit and lit["est_occupe"]:
            return jsonify(
                {
                    "success": False,
                    "error": "Impossible: ce lit est actuellement occupé",
                }
            )

        cursor.execute("DELETE FROM hosp_lits WHERE id_lit = %s", (id_lit,))
        conn.commit()

        return jsonify({"success": True, "message": "Lit supprimé"})
    finally:
        conn.close()


# ---------- Batch: Ajouter plusieurs lits à une chambre ----------


@app.route(
    "/hospitalisation/api/config/chambre/<int:id_chambre>/batch_lits", methods=["POST"]
)
@login_required
@handle_errors()
def hospitalisation_config_batch_lits(id_chambre):
    """Ajouter plusieurs lits d'un coup à une chambre."""
    data = request.get_json()
    prefix = data.get("prefix", "Lit")
    count = data.get("count", 1)
    start_from = data.get("start_from", 1)

    if count < 1 or count > 20:
        return (
            jsonify({"success": False, "error": "Nombre de lits invalide (1-20)"}),
            400,
        )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        created = 0

        for i in range(start_from, start_from + count):
            numero = f"{prefix} {i}" if prefix else str(i)
            try:
                cursor.execute(
                    """
                    INSERT INTO hosp_lits (id_chambre, numero_lit, created_at)
                    VALUES (%s, %s, NOW())
                """,
                    (id_chambre, numero),
                )
                created += 1
            except Exception:
                # Skip les doublons
                continue

        conn.commit()

        return jsonify(
            {
                "success": True,
                "message": f"{created} lit(s) créé(s)",
                "created": created,
            }
        )
    finally:
        conn.close()
