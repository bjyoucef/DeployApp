# app/location_bloc.py
import math
from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

from flask import flash, g, jsonify, redirect, render_template, request, url_for

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


def convert_decimals_to_float(data):
    """Convertit recursivement tous les Decimal en float"""
    if isinstance(data, dict):
        return {key: convert_decimals_to_float(value) for key, value in data.items()}
    elif isinstance(data, (list, tuple)):
        return [convert_decimals_to_float(item) for item in data]
    elif isinstance(data, Decimal):
        return float(data)
    else:
        return data


def to_decimal(value, default=0):
    """Convertit une valeur en Decimal de manière securisee"""
    if value is None or value == "":
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except:
        return Decimal(str(default))


def calculer_supplement_duree(bloc, duree_reelle, duree_base_override=None):
    """Calcule uniquement le supplement de duree

    Args:
        bloc: Dictionnaire contenant les infos du bloc
        duree_reelle: Durée réelle de l'opération en minutes
        duree_base_override: Durée de base à utiliser (ex: duree_forfait).
                            Si None, utilise la duree_base du bloc
    """
    # Utiliser la durée du forfait si fournie, sinon la durée du bloc
    if duree_base_override is not None:
        duree_base = int(duree_base_override)
    else:
        duree_base = int(bloc.get("duree_base", 90))

    prix_supp = to_decimal(bloc.get("prix_supplement_30min", 5000))

    if duree_reelle <= duree_base:
        return Decimal("0")

    minutes_supplementaires = duree_reelle - duree_base
    tranches_supplementaires = math.ceil(minutes_supplementaires / 30)

    return tranches_supplementaires * prix_supp


def calculer_prix_bloc(bloc, duree_reelle):
    """Calcule le prix du bloc selon la duree"""
    prix = to_decimal(bloc["prix"])
    duree_base = int(bloc.get("duree_base", 90))
    prix_supp = to_decimal(bloc.get("prix_supplement_30min", 5000))

    if duree_reelle <= duree_base:
        return prix

    minutes_supplementaires = duree_reelle - duree_base
    tranches_supplementaires = math.ceil(minutes_supplementaires / 30)

    return prix + (tranches_supplementaires * prix_supp)


def calculer_supplements_produits(cursor, id_dossier):
    """Calcule le total des supplements de produits"""
    cursor.execute(
        """
        SELECT SUM(GREATEST(0, qte_utilisee - qte_incluse) * prix_unitaire) as total_supplements
        FROM location_bloc_dossier_produits
        WHERE id_dossier = %s
    """,
        (id_dossier,),
    )

    result = cursor.fetchone()
    return (
        to_decimal(result["total_supplements"])
        if result and result["total_supplements"]
        else Decimal("0")
    )


def calculer_supplements_actes(cursor, id_dossier):
    """Calcule le total des suppléments d'actes"""
    cursor.execute(
        """
        SELECT SUM(GREATEST(0, qte_utilisee - qte_incluse) * prix_unitaire) as total_supplements
        FROM location_bloc_dossier_patient_actes
        WHERE id_dossier = %s
    """,
        (id_dossier,),
    )

    result = cursor.fetchone()
    return (
        to_decimal(result["total_supplements"])
        if result and result["total_supplements"]
        else Decimal("0")
    )


def calculer_nombre_nuitees(date_entree, date_sortie):
    """Calcule le nombre de nuitees entre deux dates"""
    if isinstance(date_entree, str):
        date_entree = datetime.strptime(date_entree, "%Y-%m-%d").date()
    if isinstance(date_sortie, str):
        date_sortie = datetime.strptime(date_sortie, "%Y-%m-%d").date()

    delta = date_sortie - date_entree
    return max(0, delta.days)


def get_prix_chambre_standard(cursor):
    """Recupère le prix unitaire d'une chambre standard"""
    cursor.execute(
        """
        SELECT prix_unitaire
        FROM type_chambre
        WHERE est_standard = 1
          AND est_actif = 1
        ORDER BY prix_unitaire ASC
        LIMIT 1
    """
    )

    result = cursor.fetchone()
    return to_decimal(result["prix_unitaire"]) if result else Decimal("0")


def get_forfaits_pour_medecin(cursor, id_doctor):
    """
    Récupère TOUS les forfaits actifs avec les prix personnalisés du médecin si configurés.
    """
    cursor.execute(
        """
        SELECT f.id_forfait,
               f.name_forfait,
               f.prix_forfait as prix_standard,
               COALESCE(fm.prix_personnalise, f.prix_forfait) as prix_forfait,
               f.duree_forfait,
               f.nbr_nuit,
               f.description,
               f.est_actif,
               CASE 
                   WHEN fm.id IS NOT NULL AND fm.prix_personnalise IS NOT NULL 
                   THEN 'PERSONNALISE'
                   ELSE 'STANDARD'
               END as source_prix,
               fm.prix_personnalise as prix_personnalise_raw
        FROM location_bloc_forfait_actes f
        LEFT JOIN location_bloc_forfait_medecin fm 
               ON f.id_forfait = fm.id_forfait
              AND fm.id_doctor = %s
              AND fm.est_actif = 1
              AND (fm.date_debut IS NULL OR fm.date_debut <= CURDATE())
              AND (fm.date_fin IS NULL OR fm.date_fin >= CURDATE())
        WHERE f.est_actif = 1
        ORDER BY f.name_forfait
    """,
        (id_doctor,),
    )

    return cursor.fetchall()


def get_prix_forfait_pour_medecin(cursor, id_doctor, id_forfait):
    """
    Récupère le prix d'un forfait spécifique pour un médecin.
    Retourne le prix personnalisé si configuré, sinon le prix standard.
    """
    # D'abord vérifier s'il y a un prix personnalisé
    cursor.execute(
        """
        SELECT fm.prix_personnalise
        FROM location_bloc_forfait_medecin fm
        WHERE fm.id_doctor = %s 
          AND fm.id_forfait = %s
          AND fm.est_actif = 1
          AND (fm.date_debut IS NULL OR fm.date_debut <= CURDATE())
          AND (fm.date_fin IS NULL OR fm.date_fin >= CURDATE())
        LIMIT 1
    """,
        (id_doctor, id_forfait),
    )

    result = cursor.fetchone()
    if result and result["prix_personnalise"] is not None:
        return to_decimal(result["prix_personnalise"])

    # Sinon, retourner le prix standard du forfait
    cursor.execute(
        """
        SELECT prix_forfait
        FROM location_bloc_forfait_actes
        WHERE id_forfait = %s
    """,
        (id_forfait,),
    )

    forfait = cursor.fetchone()
    return to_decimal(forfait["prix_forfait"]) if forfait else Decimal("0")


def get_prix_chambres_pour_medecin(cursor, id_doctor):
    """
    Récupère TOUS les types de chambres avec les prix personnalisés du médecin si configurés.
    """
    cursor.execute(
        """
        SELECT tc.id_type_chambre,
               tc.nom_type,
               tc.prix_unitaire as prix_standard,
               COALESCE(pcm.prix_personnalise, tc.prix_unitaire) as prix_unitaire,
               tc.est_standard,
               tc.description,
               tc.capacite,
               tc.est_actif,
               CASE
                   WHEN pcm.id IS NOT NULL THEN 'PERSONNALISE'
                   ELSE 'STANDARD'
               END as source_prix
        FROM type_chambre tc
        LEFT JOIN location_bloc_prix_chambre_medecin pcm
               ON tc.id_type_chambre = pcm.id_type_chambre
              AND pcm.id_doctor = %s
              AND pcm.est_actif = 1
              AND (pcm.date_debut IS NULL OR pcm.date_debut <= CURDATE())
              AND (pcm.date_fin IS NULL OR pcm.date_fin >= CURDATE())
        WHERE tc.est_actif = 1
        ORDER BY tc.prix_unitaire
    """,
        (id_doctor,),
    )

    return cursor.fetchall()


def get_prix_chambre_standard_pour_medecin(cursor, id_doctor):
    """
    Récupère le prix d'une chambre standard pour un médecin.
    Prend en compte les prix personnalisés si définis.
    """
    cursor.execute(
        """
        SELECT COALESCE(pcm.prix_personnalise, tc.prix_unitaire) as prix_unitaire
        FROM type_chambre tc
        LEFT JOIN location_bloc_prix_chambre_medecin pcm
               ON tc.id_type_chambre = pcm.id_type_chambre
              AND pcm.id_doctor = %s
              AND pcm.est_actif = 1
              AND (pcm.date_debut IS NULL OR pcm.date_debut <= CURDATE())
              AND (pcm.date_fin IS NULL OR pcm.date_fin >= CURDATE())
        WHERE tc.est_standard = 1
          AND tc.est_actif = 1
        ORDER BY COALESCE(pcm.prix_personnalise, tc.prix_unitaire) ASC
        LIMIT 1
    """,
        (id_doctor,),
    )

    result = cursor.fetchone()
    return to_decimal(result["prix_unitaire"]) if result else Decimal("0")


def get_nuitees_preop_autorisees(cursor, id_doctor: int) -> int:
    """
    Récupère le nombre de nuitées pré-opératoires gratuites autorisées pour un médecin.
    """
    cursor.execute(
        """
        SELECT nuitees_preop_gratuites_max
        FROM location_bloc_medecin_config
        WHERE id_doctor = %s
          AND est_actif = 1
          AND (date_debut IS NULL OR date_debut <= CURDATE())
          AND (date_fin IS NULL OR date_fin >= CURDATE())
        ORDER BY id DESC
        LIMIT 1
    """,
        (id_doctor,),
    )

    result = cursor.fetchone()
    return int(result["nuitees_preop_gratuites_max"]) if result else 0


def calculer_nuitees_facturables_avec_tarifs_medecin(
    cursor, id_dossier: int, id_doctor: int, forfait_id: Optional[int] = None
) -> Tuple[Decimal, int, int, List[Dict[str, Any]]]:
    """
    Calcule les nuitées facturables en tenant compte des tarifs personnalisés du médecin
    et de la configuration des nuitées pré-op gratuites.
    """
    # Récupérer les hospitalisations avec prix personnalisés
    cursor.execute(
        """
        SELECT dn.*,
               tc.nom_type,
               tc.est_standard,
               COALESCE(pcm.prix_personnalise, tc.prix_unitaire) as prix_chambre
        FROM location_bloc_dossier_nuitees dn
        JOIN type_chambre tc ON dn.id_type_chambre = tc.id_type_chambre
        LEFT JOIN location_bloc_prix_chambre_medecin pcm
               ON tc.id_type_chambre = pcm.id_type_chambre
              AND pcm.id_doctor = %s
              AND pcm.est_actif = 1
              AND (pcm.date_debut IS NULL OR pcm.date_debut <= CURDATE())
              AND (pcm.date_fin IS NULL OR pcm.date_fin >= CURDATE())
        WHERE dn.id_dossier = %s
        ORDER BY dn.date_entree
    """,
        (id_doctor, id_dossier),
    )

    rows = cursor.fetchall()

    if not rows:
        return Decimal("0.00"), 0, 0, []

    # Prix chambre standard pour ce médecin
    prix_chambre_standard = get_prix_chambre_standard_pour_medecin(cursor, id_doctor)

    # Nuitées incluses dans le forfait
    nuitees_inclues_forfait = 0
    if forfait_id:
        cursor.execute(
            """
            SELECT nbr_nuit
            FROM location_bloc_forfait_actes
            WHERE id_forfait = %s
        """,
            (forfait_id,),
        )
        f = cursor.fetchone()
        if f:
            nuitees_inclues_forfait = int(f.get("nbr_nuit") or 0)

    # Récupérer le nombre de nuitées pré-op autorisées pour ce médecin
    nuitees_preop_autorisees = get_nuitees_preop_autorisees(cursor, id_doctor)

    # Compter les nuitées pré-op gratuites demandées (chambres standard uniquement)
    nuitees_preop_demandees = sum(
        1 for h in rows if h.get("nuit_pre_op_gratuite") and h.get("est_standard")
    )

    # Limiter au nombre autorisé
    nuitees_preop_gratuites_effectives = min(
        nuitees_preop_demandees, nuitees_preop_autorisees
    )

    # Calcul détaillé nuit par nuit
    prix_total_nuitees = Decimal("0.00")
    total_nuitees = 0
    nuitees_facturables = 0
    nuitees_preop_restantes = nuitees_preop_gratuites_effectives
    nuitees_forfait_restantes = nuitees_inclues_forfait
    details = []

    for hosp in rows:
        nb_nuits = int(hosp.get("nombre_nuitees") or 0)
        total_nuitees += nb_nuits
        prix_chambre = to_decimal(hosp.get("prix_chambre"))
        est_standard = bool(hosp.get("est_standard"))
        preop_utilisee = False
        prix_hospitalisation = Decimal("0.00")

        for _ in range(nb_nuits):
            # 1️⃣ Nuit pré-op gratuite (si autorisée et disponible)
            if (
                not preop_utilisee
                and nuitees_preop_restantes > 0
                and est_standard
                and hosp.get("nuit_pre_op_gratuite")
            ):
                nuitees_preop_restantes -= 1
                preop_utilisee = True
                continue

            # 2️⃣ Nuit couverte par le forfait
            if nuitees_forfait_restantes > 0:
                nuitees_forfait_restantes -= 1
                # Si chambre non standard, payer la différence
                if not est_standard:
                    diff = prix_chambre - prix_chambre_standard
                    if diff > Decimal("0"):
                        prix_hospitalisation += diff
                continue

            # 3️⃣ Nuit facturée normalement
            prix_hospitalisation += prix_chambre

        # Comptage des nuitées facturables
        nuitees_gratuites_ce_sejour = (
            1
            if hosp.get("nuit_pre_op_gratuite")
            and est_standard
            and nuitees_preop_autorisees > 0
            else 0
        ) + min(nb_nuits, nuitees_inclues_forfait)
        nuitees_facturables += max(0, nb_nuits - nuitees_gratuites_ce_sejour)

        # Détail par hospitalisation
        details.append(
            {
                "id_nuitee": hosp["id_nuitee"],
                "prix_total": prix_hospitalisation.quantize(Decimal("0.01")),
            }
        )

        prix_total_nuitees += prix_hospitalisation

    return (
        prix_total_nuitees.quantize(Decimal("0.01")),
        total_nuitees,
        nuitees_facturables,
        details,
    )


def calculer_prix_explorations(cursor, id_dossier):
    """Calcule le prix total des explorations pour un dossier"""
    cursor.execute(
        """
        SELECT SUM(prix) as total
        FROM location_bloc_dossier_explorations
        WHERE id_dossier = %s
    """,
        (id_dossier,),
    )

    result = cursor.fetchone()
    return to_decimal(result["total"]) if result and result["total"] else Decimal("0")


@app.route("/api/get_forfait_info/<int:forfait_id>")
@login_required
def get_forfait_info(forfait_id):
    """Retourne les informations d'un forfait incluant les nuitees"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id_forfait, name_forfait, prix_forfait, duree_forfait, nbr_nuit, description
        FROM location_bloc_forfait_actes
        WHERE id_forfait = %s
    """,
        (forfait_id,),
    )

    forfait = cursor.fetchone()
    return jsonify(convert_decimals_to_float(forfait) if forfait else {})


@app.route("/api/get_prix_chambre_standard")
@login_required
def api_get_prix_chambre_standard():
    """Retourne le prix d'une chambre standard"""
    connection = get_db_connection()
    cursor = connection.cursor()

    prix_standard = get_prix_chambre_standard(cursor)
    return jsonify({"prix_unitaire": float(prix_standard)})


@app.route("/api/get_types_chambres")
@login_required
def get_types_chambres():
    """Retourne la liste des types de chambres disponibles"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id_type_chambre, nom_type, prix_unitaire, description, est_standard
        FROM type_chambre
        WHERE est_actif = 1
        ORDER BY prix_unitaire
    """
    )

    chambres = cursor.fetchall()
    return jsonify(convert_decimals_to_float(chambres))


@app.route("/location_bloc", methods=["GET"])
@login_required
@handle_errors()
def location_bloc_list():
    """Liste des locations de bloc avec pagination"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Filtres
        date_debut = request.args.get("date_debut")
        date_fin = request.args.get("date_fin")
        doctor_filter = request.args.get("doctor", "all")
        bloc_filter = request.args.get("bloc", "all")
        type_filter = request.args.get("type", "all")
        statut_filter = request.args.get("statut", "all")
        q = request.args.get("q", "").strip()

        # Pagination
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 15
        offset = (page - 1) * per_page

        # Construction des clauses WHERE
        where_clauses = ["1=1"]
        params = {}

        if date_debut:
            where_clauses.append("d.location_date >= %(date_debut)s")
            params["date_debut"] = date_debut

        if date_fin:
            where_clauses.append("d.location_date <= %(date_fin)s")
            params["date_fin"] = date_fin

        if doctor_filter and doctor_filter != "all":
            where_clauses.append("d.id_doctor = %(doctor)s")
            params["doctor"] = doctor_filter

        if bloc_filter and bloc_filter != "all":
            where_clauses.append("d.id_bloc = %(bloc)s")
            params["bloc"] = bloc_filter

        if type_filter and type_filter != "all":
            where_clauses.append("d.type_tarification = %(type)s")
            params["type"] = type_filter

        if statut_filter and statut_filter != "all":
            where_clauses.append("d.statut_paiement = %(statut)s")
            params["statut"] = statut_filter

        if q:
            where_clauses.append("(d.patient LIKE %(q)s OR d.nom_acte LIKE %(q)s)")
            params["q"] = f"%{q}%"

        where_sql = " AND ".join(where_clauses)

        # Base FROM clause
        base_from = """
            FROM location_bloc_dossier_patient d
            LEFT JOIN doctors doc ON d.id_doctor = doc.id
            LEFT JOIN personnel perso ON d.created_by = perso.id_personnel
            LEFT JOIN bloc b ON d.id_bloc = b.id_bloc
            LEFT JOIN location_bloc_forfait_actes f ON d.forfait_id = f.id_forfait
        """

        # ✅ CORRECTION : Requête de comptage séparée
        count_query = f"SELECT COUNT(*) as total {base_from} WHERE {where_sql}"
        cursor.execute(count_query, params)
        count_result = cursor.fetchone()
        total_count = count_result.get("total", 0) if count_result else 0

        # Requête de données
        data_query = f"""
            SELECT d.*,
                   doc.first_name,
                   doc.last_name,
                   b.name_bloc,
                   f.name_forfait,
                   perso.nom,
                   perso.prenom
            {base_from}
            WHERE {where_sql}
            ORDER BY d.location_date DESC, d.id_dossier DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """
        params["limit"] = per_page
        params["offset"] = offset

        cursor.execute(data_query, params)
        dossiers = cursor.fetchall()

        total_pages = max(1, ceil(total_count / per_page)) if total_count > 0 else 1

        # Récupérer les données de référence
        cursor.execute(
            """
            SELECT id, CONCAT(first_name, ' ', last_name) as name 
            FROM doctors 
            WHERE est_interne = 0 OR est_interne IS NULL 
            ORDER BY last_name, first_name
        """
        )
        doctors = cursor.fetchall()

        cursor.execute(
            "SELECT id_bloc, name_bloc FROM bloc WHERE est_actif = 1 ORDER BY name_bloc"
        )
        blocs = cursor.fetchall()

        return render_template(
            "location_bloc/list.html",
            total_count=total_count,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            dossiers=dossiers,
            doctors=doctors,
            blocs=blocs,
            filters={
                "date_debut": date_debut or "",
                "date_fin": date_fin or "",
                "doctor": doctor_filter,
                "bloc": bloc_filter,
                "type": type_filter or "all",
                "statut": statut_filter or "all",
                "q": q,
            },
            title="Locations de Bloc",
        )

    except Exception as e:
        app.logger.error(f"Erreur dans location_bloc_list: {str(e)}")
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors du chargement: {str(e)}", "danger")
        return redirect(url_for("index"))

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


@app.route("/location_bloc/ajax", methods=["GET"])
@login_required
def location_bloc_list_ajax():
    """Route AJAX pour le rechargement partiel avec tri"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Filtres + recherche
        date_debut = request.args.get("date_debut") or None
        date_fin = request.args.get("date_fin") or None
        doctor_filter = request.args.get("doctor", "all")
        bloc_filter = request.args.get("bloc", "all")
        type_filter = request.args.get("type", "all")
        statut_filter = request.args.get("statut", "all")
        q = request.args.get("q", "").strip()

        # Pagination
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 15
        offset = (page - 1) * per_page

        # TRI
        sort_field = request.args.get("sort_field", "")
        sort_order = request.args.get("sort_order", "desc")

        # Construction des clauses WHERE
        where_clauses = ["1=1"]
        params = {}

        if date_debut:
            where_clauses.append("d.location_date >= %(date_debut)s")
            params["date_debut"] = date_debut

        if date_fin:
            where_clauses.append("d.location_date <= %(date_fin)s")
            params["date_fin"] = date_fin

        if doctor_filter and doctor_filter != "all":
            where_clauses.append("d.id_doctor = %(doctor)s")
            params["doctor"] = doctor_filter

        if bloc_filter and bloc_filter != "all":
            where_clauses.append("d.id_bloc = %(bloc)s")
            params["bloc"] = bloc_filter

        if type_filter and type_filter != "all":
            where_clauses.append("d.type_tarification = %(type)s")
            params["type"] = type_filter

        if statut_filter and statut_filter != "all":
            where_clauses.append("d.statut_paiement = %(statut)s")
            params["statut"] = statut_filter

        if q:
            where_clauses.append("(d.patient LIKE %(q)s OR d.nom_acte LIKE %(q)s)")
            params["q"] = f"%{q}%"

        where_sql = " AND ".join(where_clauses)

        base_from = """
            FROM location_bloc_dossier_patient d
            LEFT JOIN doctors doc ON d.id_doctor = doc.id
            LEFT JOIN bloc b ON d.id_bloc = b.id_bloc
            LEFT JOIN location_bloc_forfait_actes f ON d.forfait_id = f.id_forfait
        """

        # Total count
        count_query = f"SELECT COUNT(*) as cnt {base_from} WHERE {where_sql}"
        cursor.execute(count_query, params)
        count_result = cursor.fetchone()
        total_count = count_result.get("cnt", 0) if count_result else 0

        # ORDER BY avec tri
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
            order_by = f"ORDER BY {order_column} {order_direction}, d.id_dossier DESC"
        else:
            order_by = "ORDER BY d.location_date DESC, d.id_dossier DESC"

        # Data query with ordering + pagination
        data_query = f"""
            SELECT d.*, doc.first_name, doc.last_name, b.name_bloc, f.name_forfait
            {base_from}
            WHERE {where_sql}
            {order_by}
            LIMIT %(limit)s OFFSET %(offset)s
        """
        params["limit"] = per_page
        params["offset"] = offset

        cursor.execute(data_query, params)
        dossiers = cursor.fetchall()

        total_pages = max(1, ceil(total_count / per_page))

        # Render partial (table + pagination + stats)
        return render_template(
            "location_bloc/_table.html",
            dossiers=dossiers,
            page=page,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            filters={
                "date_debut": date_debut or "",
                "date_fin": date_fin or "",
                "doctor": doctor_filter,
                "bloc": bloc_filter,
                "type": type_filter or "all",
                "statut": statut_filter or "all",
                "q": q,
            },
        )

    except Exception as e:
        app.logger.error(f"Erreur AJAX: {str(e)}")
        import traceback

        app.logger.error(traceback.format_exc())
        return render_template(
            "location_bloc/_table.html",
            dossiers=[],
            page=1,
            total_pages=1,
            total_count=0,
            filters={},
        )

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


@app.route("/api/location_bloc/search_forfait")
@login_required
def search_forfait():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id_forfait, name_forfait, prix_forfait
        FROM location_bloc_forfait_actes
        WHERE est_actif = 1 AND name_forfait LIKE %s
        LIMIT 5
    """,
        (f"%{q}%",),
    )
    results = convert_decimals_to_float(cursor.fetchall())
    conn.close()
    return jsonify(results)


@app.route("/api/location_bloc/check_dossier", methods=["GET"])
@login_required
def location_bloc_check_dossier():
    patient_oid = request.args.get("patient_oid")
    if not patient_oid:
        return jsonify({"exists": False})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check active dossiers created in the last 30 days
        cursor.execute(
            """
            SELECT id_dossier, location_date, type_tarification
            FROM location_bloc_dossier_patient
            WHERE patient_oid_his = %s
              AND location_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            ORDER BY location_date DESC
            LIMIT 1
        """,
            (patient_oid,),
        )
        dossier = cursor.fetchone()

        if dossier:
            # Format date for display
            date_str = (
                dossier["location_date"].strftime("%d/%m/%Y")
                if dossier["location_date"]
                else "Date inconnue"
            )
            return jsonify(
                {
                    "exists": True,
                    "message": f"⚠️ Attention : Un dossier de location bloc existe déjà pour ce patient (Date : {date_str}, Type : {dossier['type_tarification']}). Voulez-vous vraiment en créer un nouveau ?",
                }
            )
        return jsonify({"exists": False})
    finally:
        cursor.close()
        conn.close()


@app.route("/location_bloc/create", methods=["GET", "POST"])
@login_required
@handle_errors()
def location_bloc_create():
    """Creation d'une location de bloc"""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "GET":
            cursor.execute(
                """
                SELECT id, CONCAT(COALESCE(first_name, ''), ' ', COALESCE(last_name, '')) as name
                FROM doctors
                WHERE est_interne = 0
                   OR est_interne IS NULL
                ORDER BY last_name, first_name
            """
            )
            doctors = cursor.fetchall()

            cursor.execute(
                """
                SELECT id_bloc,
                       name_bloc,
                       prix,
                       duree_base,
                       prix_supplement_30min,
                       description,
                       est_actif
                FROM bloc
                WHERE est_actif = 1
                ORDER BY name_bloc
            """
            )
            blocs = cursor.fetchall()

            cursor.execute(
                """
                SELECT id_produit, description, prix
                FROM produits
                ORDER BY description
            """
            )
            produits = convert_decimals_to_float(cursor.fetchall())

            cursor.execute(
                """
                SELECT id_acte, nom_acte, prix
                FROM actes_supplement
                WHERE est_actif = 1
                ORDER BY nom_acte
            """
            )
            actes = convert_decimals_to_float(cursor.fetchall())

            return render_template(
                "location_bloc/create.html",
                doctors=doctors,
                blocs=blocs,
                forfaits=[],
                produits=produits,
                actes=actes,
                title="Nouvelle Location de Bloc",
            )

        # POST - Traitement du formulaire
        if request.method == "POST":
            # Validation des champs obligatoires
            required_fields = [
                "id_doctor",
                "patient",
                "location_date",
                "type_tarification",
                "id_bloc",
                "duree_reelle",
            ]
            for field in required_fields:
                if not request.form.get(field):
                    flash(f"Le champ {field} est obligatoire", "danger")
                    return redirect(url_for("location_bloc_create"))

            # Recuperation des donnees de base
            id_doctor = request.form["id_doctor"]
            patient_oid = request.form.get("patient_oid")
            patient_name = request.form.get("patient", "").strip()
            location_date = request.form["location_date"]
            heure_operation = request.form.get("heure_operation", "").strip() or None
            nom_acte = request.form.get("nom_acte", "").strip() or None
            type_tarification = request.form["type_tarification"]
            id_bloc = request.form["id_bloc"]
            forfait_id = (
                request.form.get("forfait_id")
                if type_tarification == "FORFAIT"
                else None
            )
            print("*************************************", patient_oid)
            try:
                duree_reelle = int(request.form["duree_reelle"])
                if duree_reelle <= 0:
                    raise ValueError("La duree doit être positive")
            except ValueError as e:
                flash(f"Duree invalide: {str(e)}", "danger")
                return redirect(url_for("location_bloc_create"))

            montant_paye_caisse = to_decimal(request.form.get("montant_paye_caisse", 0))
            observations = request.form.get("observations", "").strip()

            if type_tarification == "FORFAIT" and not forfait_id:
                flash("Veuillez selectionner un forfait", "danger")
                return redirect(url_for("location_bloc_create"))

            # Recuperation du bloc
            cursor.execute("SELECT * FROM bloc WHERE id_bloc = %s", (id_bloc,))
            bloc = cursor.fetchone()

            if not bloc:
                flash("Bloc operatoire non trouve", "danger")
                return redirect(url_for("location_bloc_create"))

            # Calcul du prix selon le type de tarification
            if type_tarification == "FORFAIT":
                if not forfait_id:
                    flash("Veuillez sélectionner un forfait", "danger")
                    return redirect(url_for("location_bloc_create"))

                # Utiliser le prix personnalisé du médecin
                prix_bloc = get_prix_forfait_pour_medecin(cursor, id_doctor, forfait_id)

                # Récupérer les infos du forfait
                cursor.execute(
                    "SELECT * FROM location_bloc_forfait_actes WHERE id_forfait = %s",
                    (forfait_id,),
                )
                forfait = cursor.fetchone()
                if not forfait:
                    flash("Forfait non trouvé", "danger")
                    return redirect(url_for("location_bloc_create"))

                # ✅ CORRECTION : Utiliser la durée du forfait pour le calcul du supplément
                prix_supplement_duree = calculer_supplement_duree(
                    bloc, duree_reelle, forfait.get("duree_forfait")
                )
            else:
                prix_bloc = to_decimal(bloc["prix"])
                # Pour la tarification à la durée, utiliser la durée du bloc
                prix_supplement_duree = calculer_supplement_duree(bloc, duree_reelle)

            # Génération QR UUID
            import uuid as _uuid

            qr_uuid = str(_uuid.uuid4())

            # Insertion du dossier principal
            cursor.execute(
                """
                INSERT INTO location_bloc_dossier_patient (
                    qr_uuid,
                    id_doctor, patient, patient_oid_his, location_date,
                    heure_operation, nom_acte,
                    type_tarification, id_bloc, forfait_id,
                    duree_reelle,
                    prix_bloc, prix_supplement_duree,
                    montant_paye_caisse, observations,
                    created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s,
                         %s, %s, %s,
                         %s,
                         %s, %s,
                         %s, %s,
                         %s)
            """,
                (
                    qr_uuid,
                    id_doctor,
                    patient_name,
                    patient_oid,
                    location_date,
                    heure_operation,
                    nom_acte,
                    type_tarification,
                    id_bloc,
                    forfait_id,
                    duree_reelle,
                    prix_bloc,
                    prix_supplement_duree,
                    montant_paye_caisse,
                    observations,
                    g.user["id_personnel"],
                ),
            )

            id_dossier = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO location_bloc_doctor_situations (id_doctor, id_dossier, encaissement_patient)
                VALUES (%s, %s, %s)
            """,
                (id_doctor, id_dossier, montant_paye_caisse),
            )

            # GESTION DES PRODUITS
            if type_tarification == "FORFAIT" and forfait_id:
                cursor.execute(
                    """
                    SELECT fp.id_produit, COALESCE(fp.qte, 0) as qte, COALESCE(p.prix, 0) as prix
                    FROM location_bloc_forfait_actes_produits fp
                    JOIN produits p ON fp.id_produit = p.id_produit
                    WHERE fp.id_forfait = %s
                """,
                    (forfait_id,),
                )
                produits_forfait = cursor.fetchall()

                for prod in produits_forfait:
                    qte_utilisee_key = f'produit_inclus_{prod["id_produit"]}'
                    qte_utilisee = to_decimal(
                        request.form.get(qte_utilisee_key, prod["qte"])
                    )
                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_produits (
                            id_dossier, id_produit, qte_incluse, qte_utilisee,
                            prix_unitaire, source_inclusion
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            prod["id_produit"],
                            prod["qte"],
                            qte_utilisee,
                            prod["prix"],
                            "FORFAIT",
                        ),
                    )
            else:
                cursor.execute(
                    """
                    SELECT bp.id_produit, COALESCE(bp.qte, 0) as qte, COALESCE(p.prix, 0) as prix
                    FROM bloc_produits_inclus bp
                    JOIN produits p ON bp.id_produit = p.id_produit
                    WHERE bp.id_bloc = %s
                """,
                    (id_bloc,),
                )
                produits_bloc = cursor.fetchall()

                for prod in produits_bloc:
                    qte_utilisee_key = f'produit_inclus_{prod["id_produit"]}'
                    qte_utilisee = to_decimal(
                        request.form.get(qte_utilisee_key, prod["qte"])
                    )
                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_produits (
                            id_dossier, id_produit, qte_incluse, qte_utilisee,
                            prix_unitaire, source_inclusion
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            prod["id_produit"],
                            prod["qte"],
                            qte_utilisee,
                            prod["prix"],
                            "BLOC",
                        ),
                    )

            # Produits supplementaires
            produits_supp_ids = request.form.getlist("produit_supp_id[]")
            produits_supp_qtes = request.form.getlist("produit_supp_qte[]")

            for i, prod_id in enumerate(produits_supp_ids):
                if prod_id and prod_id.strip():
                    try:
                        qte = to_decimal(
                            produits_supp_qtes[i] if i < len(produits_supp_qtes) else 1
                        )
                        if qte > 0:
                            cursor.execute(
                                "SELECT COALESCE(prix, 0) as prix FROM produits WHERE id_produit = %s",
                                (prod_id,),
                            )
                            prod_info = cursor.fetchone()
                            if prod_info:
                                cursor.execute(
                                    """
                                    INSERT INTO location_bloc_dossier_produits (
                                        id_dossier, id_produit, qte_incluse, qte_utilisee,
                                        prix_unitaire, source_inclusion
                                    ) VALUES (%s, %s, %s, %s, %s, %s)
                                """,
                                    (
                                        id_dossier,
                                        prod_id,
                                        0,
                                        qte,
                                        prod_info["prix"],
                                        "SUPPLEMENTAIRE",
                                    ),
                                )
                    except (ValueError, KeyError):
                        continue

            # GESTION DES ACTES
            # 1. Actes inclus dans le forfait
            if type_tarification == "FORFAIT" and forfait_id:
                cursor.execute(
                    """
                    SELECT fa.id_acte, a.nom_acte, COALESCE(a.prix, 0) as prix
                    FROM location_bloc_forfait_actes_inclus fa
                    JOIN actes_supplement a ON fa.id_acte = a.id_acte
                    WHERE fa.id_forfait = %s
                """,
                    (forfait_id,),
                )
                actes_forfait = cursor.fetchall()

                for acte in actes_forfait:
                    qte_utilisee_key = f'acte_inclus_{acte["id_acte"]}'
                    qte_utilisee = to_decimal(request.form.get(qte_utilisee_key, 1))
                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_patient_actes (
                            id_dossier, id_acte, qte_incluse, qte_utilisee,
                            prix_unitaire, source_inclusion
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            acte["id_acte"],
                            1,
                            qte_utilisee,
                            acte["prix"],
                            "FORFAIT",
                        ),
                    )

            # Actes supplementaires
            actes_supp_ids = request.form.getlist("acte_supp_id[]")
            actes_supp_qtes = request.form.getlist("acte_supp_qte[]")

            for i, acte_id in enumerate(actes_supp_ids):
                if acte_id and acte_id.strip():
                    try:
                        qte = to_decimal(
                            actes_supp_qtes[i] if i < len(actes_supp_qtes) else 1
                        )
                        if qte > 0:
                            cursor.execute(
                                "SELECT COALESCE(prix, 0) as prix FROM actes_supplement WHERE id_acte = %s",
                                (acte_id,),
                            )
                            acte_info = cursor.fetchone()
                            if acte_info:
                                cursor.execute(
                                    """
                                    INSERT INTO location_bloc_dossier_patient_actes (
                                        id_dossier, id_acte, qte_incluse, qte_utilisee,
                                        prix_unitaire, source_inclusion
                                    ) VALUES (%s, %s, %s, %s, %s, %s)
                                """,
                                    (
                                        id_dossier,
                                        acte_id,
                                        0,
                                        qte,
                                        acte_info["prix"],
                                        "SUPPLEMENTAIRE",
                                    ),
                                )
                    except (ValueError, KeyError):
                        continue

            # Calcul du prix total des supplements
            prix_produits_supplementaires = calculer_supplements_produits(
                cursor, id_dossier
            )
            prix_actes_supplementaires = calculer_supplements_actes(cursor, id_dossier)

            # GESTION DES nuitees (MULTIPLES)
            dates_entree = request.form.getlist("date_entree_hospitalisation[]")
            dates_sortie = request.form.getlist("date_sortie_hospitalisation[]")
            types_chambre = request.form.getlist("id_type_chambre[]")
            nuits_pre_op = request.form.getlist("nuit_pre_op_gratuite[]")

            # COMPTAGE DES nuitees PRE-OP GRATUITES
            nuitees_preop_autorisees = get_nuitees_preop_autorisees(cursor, id_doctor)
            nuit_pre_op_compteur = 0

            for i in range(len(dates_entree)):
                if dates_entree[i] and dates_sortie[i] and types_chambre[i]:
                    cursor.execute(
                        """
                        SELECT est_standard, prix_unitaire
                        FROM type_chambre
                        WHERE id_type_chambre = %s
                    """,
                        (types_chambre[i],),
                    )
                    chambre = cursor.fetchone()

                    if not chambre:
                        continue

                    nombre_nuitees = calculer_nombre_nuitees(
                        dates_entree[i], dates_sortie[i]
                    )

                    # Verifier si cette hospitalisation demande une nuit pre-op gratuite
                    nuit_pre_op_gratuite = False

                    # Verifier si l'index i est dans la liste des pre-op gratuites
                    if i < len(nuits_pre_op) and nuits_pre_op[i] == "1":
                        # Verifier si la chambre est standard (condition obligatoire)
                        if chambre.get("est_standard", False):
                            # Verifier si c'est la première nuit pre-op gratuite
                            if nuit_pre_op_compteur < nuitees_preop_autorisees:
                                nuit_pre_op_gratuite = True
                                nuit_pre_op_compteur += 1
                                app.logger.info(
                                    f"DEBUG - Nuit pre-op gratuite accordee pour l'hospitalisation {i + 1}"
                                )
                            else:
                                app.logger.info(
                                    f"DEBUG - Nuit pre-op gratuite REFUSEE pour l'hospitalisation {i + 1} : deja {nuitees_preop_autorisees} accordee(s)"
                                )
                                flash(
                                    f"Attention : La nuit pre-op gratuite pour l'hospitalisation {i + 1} a ete ignoree car maximum {nuitees_preop_autorisees} autorisee(s) par dossier",
                                    "warning",
                                )
                        else:
                            app.logger.info(
                                f"DEBUG - Nuit pre-op gratuite REFUSEE pour l'hospitalisation {i + 1} : chambre non standard"
                            )
                            flash(
                                f"Attention : La nuit pre-op gratuite n'est pas disponible pour les chambres non-standard (hospitalisation {i + 1})",
                                "warning",
                            )

                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_nuitees (
                            id_dossier, id_type_chambre, date_entree, date_sortie,
                            nombre_nuitees, nuit_pre_op_gratuite, prix_unitaire, prix_total
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            types_chambre[i],
                            dates_entree[i],
                            dates_sortie[i],
                            nombre_nuitees,
                            nuit_pre_op_gratuite,
                            to_decimal(chambre["prix_unitaire"]),
                            0,
                        ),
                    )

            # Avertissement si plus de nuits pre-op demandees qu'autorisees
            nuit_pre_op_demandees = sum(1 for n in nuits_pre_op if n == "1")
            if nuit_pre_op_demandees > nuitees_preop_autorisees:
                flash(
                    f"Attention : {nuit_pre_op_demandees} nuitees pre-operatoires gratuites demandees, mais seulement {nuitees_preop_autorisees} autorisee(s).",
                    "warning",
                )

            # CALCUL du prix total des nuitees avec tarifs personnalisés
            prix_nuitees, total_nuitees, nuitees_facturables, nuitees_details = (
                calculer_nuitees_facturables_avec_tarifs_medecin(
                    cursor, id_dossier, id_doctor, forfait_id
                )
            )

            # MISE À JOUR du prix de chaque hospitalisation
            if nuitees_details:
                for d in nuitees_details:
                    cursor.execute(
                        """
                        UPDATE location_bloc_dossier_nuitees
                        SET prix_total = %s
                        WHERE id_nuitee = %s
                    """,
                        (d["prix_total"], d["id_nuitee"]),
                    )

            # GESTION DES EXPLORATIONS
            exploration_types = request.form.getlist("exploration_type[]")
            exploration_noms = request.form.getlist("exploration_nom[]")
            exploration_dates = request.form.getlist("exploration_date[]")
            exploration_prix = request.form.getlist("exploration_prix[]")
            exploration_obs = request.form.getlist("exploration_obs[]")

            prix_explorations = Decimal("0")

            for i, exp_type in enumerate(exploration_types):
                if i < len(exploration_prix) and exploration_prix[i]:
                    try:
                        exp_prix = to_decimal(exploration_prix[i])
                        if exp_prix > 0:
                            exp_nom = (
                                exploration_noms[i].strip()
                                if i < len(exploration_noms) and exploration_noms[i]
                                else None
                            )
                            exp_type_val = exp_type if exp_type else "AUTRE"
                            exp_date = (
                                exploration_dates[i]
                                if i < len(exploration_dates) and exploration_dates[i]
                                else None
                            )
                            exp_obs = (
                                exploration_obs[i].strip()
                                if i < len(exploration_obs) and exploration_obs[i]
                                else ""
                            )

                            # Si pas de nom, on en genère un base sur le type
                            if not exp_nom:
                                if exp_type_val == "IMAGERIE":
                                    exp_nom = "Imagerie medicale"
                                elif exp_type_val == "LABORATOIRE":
                                    exp_nom = "Analyse laboratoire"
                                else:
                                    exp_nom = "Exploration medicale"

                            cursor.execute(
                                """
                                INSERT INTO location_bloc_dossier_explorations (
                                    id_dossier, type_exploration, nom_exploration,
                                    date_exploration, prix, observations
                                ) VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    exp_type_val,
                                    exp_nom,
                                    exp_date,
                                    exp_prix,
                                    exp_obs,
                                ),
                            )

                            prix_explorations += exp_prix
                    except (ValueError, TypeError) as e:
                        app.logger.warning(f"Erreur dans l'exploration {i}: {str(e)}")
                        continue

            # GESTION DE L'ACTE D'ANESTHÉSIE
            acte_anesth_id = request.form.get("acte_anesth_id")
            intervenant1_id = request.form.get("intervenant1_id")  # Réanimateur
            intervenant2_id = request.form.get("intervenant2_id")  # Technicien

            from app.anesthesie_honoraires.anesthesie_honoraires import (
                calculer_honoraires_anesthesie,
                get_tarif_forfaitaire_anesthesie,
            )

            prix_anesthesie = Decimal("0")

            if acte_anesth_id and intervenant1_id and intervenant2_id:
                try:
                    # UN SEUL TARIF FORFAITAIRE pour l'acte (prix ajouté au dossier)
                    prix_anesthesie = get_tarif_forfaitaire_anesthesie(
                        cursor, acte_anesth_id
                    )

                    # Pour l'intervenant 1
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
                            # HONORAIRES pour l'intervenant (comptabilité interne)
                            honoraires1 = calculer_honoraires_anesthesie(
                                cursor,
                                acte_anesth_id,
                                intervenant1["id_type_intervenant"],
                                duree_reelle,
                            )

                            # Insérer avec honoraires (pour comptabilité interne)
                            cursor.execute(
                                """
                                INSERT INTO location_bloc_dossier_anesthesie
                                (id_dossier, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    acte_anesth_id,
                                    intervenant1_id,
                                    duree_reelle,
                                    honoraires1,
                                    g.user["id_personnel"],
                                ),
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
                            # HONORAIRES pour l'intervenant (comptabilité interne)
                            honoraires2 = calculer_honoraires_anesthesie(
                                cursor,
                                acte_anesth_id,
                                intervenant2["id_type_intervenant"],
                                duree_reelle,
                            )

                            # Insérer avec honoraires (pour comptabilité interne)
                            cursor.execute(
                                """
                                INSERT INTO location_bloc_dossier_anesthesie
                                (id_dossier, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    acte_anesth_id,
                                    intervenant2_id,
                                    duree_reelle,
                                    honoraires2,
                                    g.user["id_personnel"],
                                ),
                            )
                except Exception as e:
                    app.logger.warning(f"Erreur acte anesthésie: {str(e)}")

            # CALCUL DU PRIX TOTAL FINAL
            prix_total = (
                prix_bloc
                + prix_supplement_duree
                + prix_produits_supplementaires
                + prix_actes_supplementaires
                + prix_nuitees
                + prix_explorations
                + prix_anesthesie
            )

            # Calcul du statut de paiement
            difference_paiement = montant_paye_caisse - prix_total

            if difference_paiement < 0:
                statut_paiement = "COMPLEMENT_MEDECIN"
            elif difference_paiement > 0:
                statut_paiement = "SURPLUS_CLINIQUE"
            else:
                statut_paiement = "AUCUN_PAIEMENT"

            # Mise à jour du dossier avec les totaux
            cursor.execute(
                """
                UPDATE location_bloc_dossier_patient
                SET prix_produits_supplementaires = %s,
                    prix_nuitees = %s,
                    prix_explorations = %s,
                    prix_anesthesie = %s,
                    prix_total = %s,
                    difference_paiement = %s,
                    statut_paiement = %s
                WHERE id_dossier = %s
            """,
                (
                    prix_produits_supplementaires + prix_actes_supplementaires,
                    prix_nuitees,
                    prix_explorations,
                    prix_anesthesie,
                    prix_total,
                    difference_paiement,
                    statut_paiement,
                    id_dossier,
                ),
            )

            connection.commit()
            flash(
                f"Location de bloc creee avec succès. Prix total: {float(prix_total):.2f} DA",
                "success",
            )
            return redirect(url_for("location_bloc_detail", id_dossier=id_dossier))

    except Exception as e:
        if connection:
            try:
                connection.rollback()
            except:
                pass
        app.logger.error(f"Erreur lors de la creation: {str(e)}")
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors de la creation: {str(e)}", "danger")
        return redirect(url_for("location_bloc_create"))

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


@app.route("/location_bloc/<int:id_dossier>")
@login_required
def location_bloc_detail(id_dossier):
    """Detail d'une location de bloc"""
    app.logger.info(f"Chargement du dossier {id_dossier}")

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Recuperation du dossier avec les infos du forfait
        cursor.execute(
            """
            SELECT d.*,
                   CONCAT(pc.nom, ' ', pc.prenom) as cree_par_nom,
                   d.patient_oid_his as patient_oid,
                   CONCAT(doc.first_name, ' ', doc.last_name) as doctor_name,
                   b.name_bloc,
                   b.prix,
                   b.duree_base,
                   b.prix_supplement_30min,
                   f.name_forfait,
                   f.duree_forfait,
                   f.prix_forfait,
                   f.nbr_nuit as forfait_nbr_nuit
            FROM location_bloc_dossier_patient d
            LEFT JOIN doctors doc ON d.id_doctor = doc.id
            LEFT JOIN bloc b ON d.id_bloc = b.id_bloc
            LEFT JOIN location_bloc_forfait_actes f ON d.forfait_id = f.id_forfait
            LEFT JOIN personnel pc ON pc.id_personnel = d.created_by
            WHERE d.id_dossier = %s
        """,
            (id_dossier,),
        )

        dossier = cursor.fetchone()

        if not dossier:
            flash("Dossier non trouve", "danger")
            return redirect(url_for("location_bloc_list"))

        # Convertir None en valeurs par defaut
        dossier_safe = {}
        for key, value in dossier.items():
            if value is None:
                if key in [
                    "prix",
                    "prix_forfait",
                    "prix_supplement_30min",
                    "prix_bloc",
                    "prix_supplement_duree",
                    "prix_produits_supplementaires",
                    "prix_nuitees",
                    "prix_explorations",
                    "prix_total",
                    "montant_paye_caisse",
                    "difference_paiement",
                ]:
                    dossier_safe[key] = 0
                elif key in [
                    "duree_base",
                    "duree_forfait",
                    "duree_reelle",
                    "forfait_nbr_nuit",
                ]:
                    dossier_safe[key] = 0
                elif key in [
                    "name_bloc",
                    "name_forfait",
                    "doctor_name",
                    "patient",
                    "nom_acte",
                    "observations",
                    "statut_paiement",
                ]:
                    dossier_safe[key] = ""
                else:
                    dossier_safe[key] = value
            else:
                dossier_safe[key] = value

        # Recuperation des produits consommes
        cursor.execute(
            """
            SELECT dp.*,
                   p.description as produit_nom,
                   COALESCE(dp.qte_utilisee, 0) - COALESCE(dp.qte_incluse, 0) as ecart,
                   GREATEST(0, COALESCE(dp.qte_utilisee, 0) - COALESCE(dp.qte_incluse, 0)) *
                   COALESCE(dp.prix_unitaire, 0) as prix_supplement
            FROM location_bloc_dossier_produits dp
            JOIN produits p ON dp.id_produit = p.id_produit
            WHERE dp.id_dossier = %s
            ORDER BY dp.source_inclusion, p.description
        """,
            (id_dossier,),
        )

        produits = cursor.fetchall()

        # Recuperation des actes realises
        cursor.execute(
            """
            SELECT da.*,
                   a.nom_acte,
                   COALESCE(da.qte_utilisee, 0) - COALESCE(da.qte_incluse, 0) as ecart,
                   GREATEST(0, COALESCE(da.qte_utilisee, 0) - COALESCE(da.qte_incluse, 0)) *
                   COALESCE(da.prix_unitaire, 0) as prix_supplement
            FROM location_bloc_dossier_patient_actes da
            JOIN actes_supplement a ON da.id_acte = a.id_acte
            WHERE da.id_dossier = %s
            ORDER BY da.source_inclusion, a.nom_acte
        """,
            (id_dossier,),
        )

        actes = cursor.fetchall()

        # Nettoyer les produits
        produits_safe = []
        for prod in produits:
            prod_safe = {}
            for key, value in prod.items():
                if value is None:
                    if key in [
                        "qte_incluse",
                        "qte_utilisee",
                        "prix_unitaire",
                        "ecart",
                        "prix_supplement",
                    ]:
                        prod_safe[key] = 0
                    elif key in ["source_inclusion", "produit_nom"]:
                        prod_safe[key] = ""
                    else:
                        prod_safe[key] = value
                else:
                    prod_safe[key] = value
            produits_safe.append(prod_safe)

        # Nettoyer les actes
        actes_safe = []
        for acte in actes:
            acte_safe = {}
            for key, value in acte.items():
                if value is None:
                    if key in [
                        "qte_incluse",
                        "qte_utilisee",
                        "prix_unitaire",
                        "ecart",
                        "prix_supplement",
                    ]:
                        acte_safe[key] = 0
                    elif key in ["source_inclusion", "nom_acte"]:
                        acte_safe[key] = ""
                    else:
                        acte_safe[key] = value
                else:
                    acte_safe[key] = value
            actes_safe.append(acte_safe)

        # Recuperation des nuitees (TOUTES)
        cursor.execute(
            """
            SELECT dn.*,
                   tc.nom_type as type_chambre_nom,
                   tc.est_standard,
                   tc.prix_unitaire as prix_chambre
            FROM location_bloc_dossier_nuitees dn
            LEFT JOIN type_chambre tc ON dn.id_type_chambre = tc.id_type_chambre
            WHERE dn.id_dossier = %s
            ORDER BY dn.date_entree
        """,
            (id_dossier,),
        )

        nuitees = cursor.fetchall()

        # Recuperation des explorations
        cursor.execute(
            """
            SELECT *
            FROM location_bloc_dossier_explorations
            WHERE id_dossier = %s
            ORDER BY date_exploration DESC
        """,
            (id_dossier,),
        )

        explorations = cursor.fetchall()

        # Nettoyer les nuitees
        nuitees_safe = []
        for nuitee in nuitees:
            nuitee_safe = {}
            for key, value in nuitee.items():
                if value is None:
                    if key in ["nombre_nuitees"]:
                        nuitee_safe[key] = 0
                    elif key in ["prix_unitaire", "prix_total"]:
                        nuitee_safe[key] = 0
                    else:
                        nuitee_safe[key] = ""
                else:
                    nuitee_safe[key] = value
            nuitees_safe.append(nuitee_safe)

        # Nettoyer les explorations
        explorations_safe = []
        for exploration in explorations:
            exp_safe = {}
            for key, value in exploration.items():
                if value is None:
                    if key in ["prix"]:
                        exp_safe[key] = 0
                    else:
                        exp_safe[key] = ""
                else:
                    exp_safe[key] = value
            explorations_safe.append(exp_safe)

        # Récupération des actes d'anesthésie
        cursor.execute(
            """
            SELECT da.id_dossier_anesthesie,
                   da.id_dossier,
                   da.id_acte_anesthesie,
                   aa.nom_acte,
                   aa.tarif_forfaitaire,
                   CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                   ti.nom_type as type_intervenant,
                   da.honoraires_calcules,
                   da.duree_reelle,
                   da.observations,
                   da.date_creation
            FROM location_bloc_dossier_anesthesie da
            JOIN anesthesie_type_acte aa ON da.id_acte_anesthesie = aa.id_acte_anesthesie
            JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
            JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
            WHERE da.id_dossier = %s
            ORDER BY da.date_creation
        """,
            (id_dossier,),
        )

        actes_anesthesie = cursor.fetchall()

        # Grouper par acte (normalement 1 seul acte avec 2 lignes)
        actes_anesthesie_groupes = {}
        for acte in actes_anesthesie:
            id_acte = acte["id_acte_anesthesie"]
            if id_acte not in actes_anesthesie_groupes:
                actes_anesthesie_groupes[id_acte] = {
                    "nom_acte": acte["nom_acte"],
                    "tarif_forfaitaire": to_decimal(acte["tarif_forfaitaire"]),
                    "duree_reelle": acte["duree_reelle"],
                    "intervenants": [],
                    "total_honoraires": Decimal("0"),
                }
            actes_anesthesie_groupes[id_acte]["intervenants"].append(
                {
                    "nom": acte["nom_personnel"],
                    "type": acte["type_intervenant"],
                    "honoraires": to_decimal(acte["honoraires_calcules"]),
                }
            )
            actes_anesthesie_groupes[id_acte]["total_honoraires"] += to_decimal(
                acte["honoraires_calcules"]
            )

        # Grouper les produits par source
        produits_groupes = {"BLOC": [], "FORFAIT": [], "SUPPLEMENTAIRE": []}
        for prod in produits_safe:
            source = prod.get("source_inclusion", "SUPPLEMENTAIRE")
            if source in produits_groupes:
                produits_groupes[source].append(prod)

        # Grouper les actes par source
        actes_groupes = {"FORFAIT": [], "SUPPLEMENTAIRE": []}
        for acte in actes_safe:
            source = acte.get("source_inclusion", "SUPPLEMENTAIRE")
            if source in actes_groupes:
                actes_groupes[source].append(acte)

        # Calculer les supplements separes
        prix_produits_supplementaires = sum(p["prix_supplement"] for p in produits_safe)
        prix_actes_supplementaires = sum(a["prix_supplement"] for a in actes_safe)

        return render_template(
            "location_bloc/detail.html",
            dossier=dossier_safe,
            actes_anesthesie_groupes=actes_anesthesie_groupes,
            prix_anesthesie=sum(
                a["tarif_forfaitaire"] for a in actes_anesthesie_groupes.values()
            ),
            produits_groupes=produits_groupes,
            actes_groupes=actes_groupes,
            nuitees=nuitees_safe,
            explorations=explorations_safe,
            prix_produits_supplementaires=prix_produits_supplementaires,
            prix_actes_supplementaires=prix_actes_supplementaires,
            title=f"Dossier #{id_dossier}",
        )

    except Exception as e:
        app.logger.error(
            f"Erreur dans location_bloc_detail pour dossier {id_dossier}: {str(e)}"
        )
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors du chargement du dossier: {str(e)}", "danger")
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


# Routes AJAX
@app.route("/api/get_forfait_produits/<int:forfait_id>")
@login_required
def get_forfait_produits(forfait_id):
    """Retourne les produits inclus dans un forfait"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT fp.id_produit,
               fp.qte as quantite_incluse,
               p.description as nom,
               p.prix as prix_unitaire
        FROM location_bloc_forfait_actes_produits fp
        JOIN produits p ON fp.id_produit = p.id_produit
        WHERE fp.id_forfait = %s
        ORDER BY p.description
    """,
        (forfait_id,),
    )

    produits = cursor.fetchall()
    return jsonify(convert_decimals_to_float(produits))


@app.route("/api/get_bloc_produits/<int:bloc_id>")
@login_required
def get_bloc_produits(bloc_id):
    """Retourne les produits inclus dans un bloc"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT bp.id_produit,
               bp.qte as quantite_incluse,
               p.description as nom,
               p.prix as prix_unitaire
        FROM bloc_produits_inclus bp
        JOIN produits p ON bp.id_produit = p.id_produit
        WHERE bp.id_bloc = %s
        ORDER BY p.description
    """,
        (bloc_id,),
    )

    produits = cursor.fetchall()
    return jsonify(convert_decimals_to_float(produits))


@app.route("/location_bloc/<int:id_dossier>/delete", methods=["POST"])
@login_required
@handle_errors()
def location_bloc_delete(id_dossier):
    """Suppression d'une location de bloc"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Vérifier que le dossier existe
        cursor.execute(
            "SELECT patient, location_date FROM location_bloc_dossier_patient WHERE id_dossier = %s",
            (id_dossier,),
        )
        dossier = cursor.fetchone()

        if not dossier:
            flash("Dossier non trouve", "danger")
            return redirect(url_for("location_bloc_list"))

        # 1. Supprimer d'abord les enregistrements liés dans location_bloc_doctor_situations
        cursor.execute(
            "DELETE FROM location_bloc_doctor_situations WHERE id_dossier = %s",
            (id_dossier,),
        )

        # 2. Supprimer les autres relations (en cas d'erreurs futures)
        # Actes d'anesthésie
        cursor.execute(
            "DELETE FROM location_bloc_dossier_anesthesie WHERE id_dossier = %s",
            (id_dossier,),
        )

        # Produits
        cursor.execute(
            "DELETE FROM location_bloc_dossier_produits WHERE id_dossier = %s",
            (id_dossier,),
        )

        # Actes
        cursor.execute(
            "DELETE FROM location_bloc_dossier_patient_actes WHERE id_dossier = %s",
            (id_dossier,),
        )

        # Nuitées
        cursor.execute(
            "DELETE FROM location_bloc_dossier_nuitees WHERE id_dossier = %s",
            (id_dossier,),
        )

        # Explorations
        cursor.execute(
            "DELETE FROM location_bloc_dossier_explorations WHERE id_dossier = %s",
            (id_dossier,),
        )

        # 3. Enfin, supprimer le dossier principal
        cursor.execute(
            "DELETE FROM location_bloc_dossier_patient WHERE id_dossier = %s",
            (id_dossier,),
        )

        connection.commit()

        flash(
            f'Location de bloc pour {dossier["patient"]} du {dossier["location_date"].strftime("%d/%m/%Y")} supprimee avec succès',
            "success",
        )

    except Exception as e:
        connection.rollback()
        flash(f"Erreur lors de la suppression: {str(e)}", "danger")
        app.logger.error(f"Erreur de suppression dossier {id_dossier}: {str(e)}")

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

    return redirect(url_for("location_bloc_list"))


def format_date_for_html(date_value):
    """Convertit une date en format YYYY-MM-DD pour input type='date'"""
    if date_value is None:
        return ""
    if isinstance(date_value, str):
        # Si c'est déjà une chaîne, extraire juste la partie date
        return date_value.split(" ")[0]
    # Si c'est un objet date/datetime
    try:
        return date_value.strftime("%Y-%m-%d")
    except:
        return str(date_value).split(" ")[0]


@app.route("/location_bloc/<int:id_dossier>/edit", methods=["GET", "POST"])
@login_required
@handle_errors()
def location_bloc_edit(id_dossier):
    """Modification d'une location de bloc - VERSION COMPLÈTE"""
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        if request.method == "GET":
            # RÉCUPÉRATION DU DOSSIER
            cursor.execute(
                """
                SELECT d.*,
                       CONCAT(doc.first_name, ' ', doc.last_name) as doctor_name
                FROM location_bloc_dossier_patient d
                LEFT JOIN doctors doc ON d.id_doctor = doc.id
                WHERE d.id_dossier = %s
            """,
                (id_dossier,),
            )

            dossier = cursor.fetchone()
            if not dossier:
                flash("Dossier non trouvé", "danger")
                return redirect(url_for("location_bloc_list"))

            # RÉCUPÉRATION DES PRODUITS
            cursor.execute(
                """
                SELECT dp.*, p.description as produit_nom
                FROM location_bloc_dossier_produits dp
                JOIN produits p ON dp.id_produit = p.id_produit
                WHERE dp.id_dossier = %s
                ORDER BY dp.source_inclusion, p.description
            """,
                (id_dossier,),
            )
            produits_dossier = cursor.fetchall()

            # Grouper les produits par source
            produits_groupes = {"BLOC": [], "FORFAIT": [], "SUPPLEMENTAIRE": []}
            for prod in produits_dossier:
                source = prod.get("source_inclusion", "SUPPLEMENTAIRE")
                if source in produits_groupes:
                    produits_groupes[source].append(prod)

            # RÉCUPÉRATION DES ACTES
            cursor.execute(
                """
                SELECT da.*, a.nom_acte
                FROM location_bloc_dossier_patient_actes da
                JOIN actes_supplement a ON da.id_acte = a.id_acte
                WHERE da.id_dossier = %s
                ORDER BY da.source_inclusion, a.nom_acte
            """,
                (id_dossier,),
            )
            actes_dossier = cursor.fetchall()

            # Grouper les actes par source
            actes_groupes = {"FORFAIT": [], "SUPPLEMENTAIRE": []}
            for acte in actes_dossier:
                source = acte.get("source_inclusion", "SUPPLEMENTAIRE")
                if source in actes_groupes:
                    actes_groupes[source].append(acte)

            # RÉCUPÉRATION DES NUITÉES
            cursor.execute(
                """
                SELECT dn.*, tc.nom_type as type_chambre_nom
                FROM location_bloc_dossier_nuitees dn
                LEFT JOIN type_chambre tc ON dn.id_type_chambre = tc.id_type_chambre
                WHERE dn.id_dossier = %s
                ORDER BY dn.date_entree
            """,
                (id_dossier,),
            )
            nuitees = cursor.fetchall()

            # RÉCUPÉRATION DES EXPLORATIONS
            cursor.execute(
                """
                SELECT *
                FROM location_bloc_dossier_explorations
                WHERE id_dossier = %s
                ORDER BY date_exploration DESC
            """,
                (id_dossier,),
            )
            explorations = cursor.fetchall()
            # ✅ FORMATER LES DATES CORRECTEMENT
            nuitees_formatted = []
            for n in nuitees:
                n_copy = dict(n)
                n_copy["date_entree"] = format_date_for_html(n["date_entree"])
                n_copy["date_sortie"] = format_date_for_html(n["date_sortie"])
                nuitees_formatted.append(n_copy)

            # ✅ RÉCUPÉRATION DES ACTES D'ANESTHÉSIE
            cursor.execute(
                """
                SELECT da.id_dossier_anesthesie,
                       da.id_acte_anesthesie,
                       da.id_personnel_anesthesie,
                       aa.nom_acte,
                       aa.tarif_forfaitaire,
                       CONCAT(p.prenom, ' ', p.nom) as nom_personnel,
                       ti.nom_type as type_intervenant,
                       p.id_type_intervenant,
                       da.honoraires_calcules,
                       da.duree_reelle
                FROM location_bloc_dossier_anesthesie da
                JOIN anesthesie_type_acte aa ON da.id_acte_anesthesie = aa.id_acte_anesthesie
                JOIN anesthesie_personnel p ON da.id_personnel_anesthesie = p.id_personnel_anesthesie
                JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
                WHERE da.id_dossier = %s
                ORDER BY da.date_creation
            """,
                (id_dossier,),
            )
            actes_anesthesie = cursor.fetchall()

            # Préparer les données d'anesthésie pour JavaScript
            acte_anesth_id = None
            intervenant1_id = None
            intervenant2_id = None
            print(actes_anesthesie)
            if actes_anesthesie:
                # Prendre le premier acte (normalement il n'y en a qu'un)
                acte_anesth_id = actes_anesthesie[0]["id_acte_anesthesie"]

                # Identifier les intervenants par type
                for acte_anesth in actes_anesthesie:
                    type_intervenant = acte_anesth["type_intervenant"].lower()
                    if (
                        "réanimateur" in type_intervenant
                        or "reanimateur" in type_intervenant
                    ):
                        intervenant1_id = acte_anesth["id_personnel_anesthesie"]
                    elif "tech" in type_intervenant:
                        intervenant2_id = acte_anesth["id_personnel_anesthesie"]

            # RÉCUPÉRATION DES DONNÉES DE RÉFÉRENCE
            cursor.execute(
                """
                SELECT id, CONCAT(first_name, ' ', last_name) as name
                FROM doctors
                WHERE est_interne = 0 OR est_interne IS NULL
                ORDER BY last_name, first_name
            """
            )
            doctors = cursor.fetchall()

            cursor.execute(
                """
                SELECT *
                FROM bloc
                WHERE est_actif = 1
                ORDER BY name_bloc
            """
            )
            blocs = cursor.fetchall()

            cursor.execute(
                """
                SELECT *
                FROM location_bloc_forfait_actes
                WHERE est_actif = 1
                ORDER BY name_forfait
            """
            )
            forfaits = cursor.fetchall()

            cursor.execute("SELECT * FROM produits ORDER BY description")
            produits = cursor.fetchall()

            cursor.execute(
                """
                SELECT *
                FROM actes_supplement
                WHERE est_actif = 1
                ORDER BY nom_acte
            """
            )
            actes = cursor.fetchall()

            cursor.execute(
                """
                SELECT *
                FROM type_chambre
                WHERE est_actif = 1
                ORDER BY prix_unitaire
            """
            )
            types_chambres = cursor.fetchall()

            return render_template(
                "location_bloc/edit.html",
                dossier=dossier,
                produits_groupes=produits_groupes,
                actes_groupes=actes_groupes,
                nuitees=nuitees_formatted,
                explorations=explorations,
                # ✅ Ajouter les données d'anesthésie
                acte_anesth_id=acte_anesth_id,
                intervenant1_id=intervenant1_id,
                intervenant2_id=intervenant2_id,
                doctors=doctors,
                blocs=blocs,
                forfaits=forfaits,
                produits=convert_decimals_to_float(produits),
                actes=convert_decimals_to_float(actes),
                types_chambres=types_chambres,
                title=f"Modifier Dossier #{id_dossier}",
            )

        # POST - TRAITEMENT DU FORMULAIRE
        if request.method == "POST":
            # Validation des champs obligatoires
            required_fields = [
                "id_doctor",
                "patient",
                "location_date",
                "type_tarification",
                "id_bloc",
                "duree_reelle",
            ]
            for field in required_fields:
                if not request.form.get(field):
                    flash(f"Le champ {field} est obligatoire", "danger")
                    return redirect(
                        url_for("location_bloc_edit", id_dossier=id_dossier)
                    )

            # Récupération des données de base
            id_doctor = request.form["id_doctor"]
            patient = request.form["patient"].strip()
            location_date = request.form["location_date"]
            heure_operation = request.form.get("heure_operation", "").strip() or None
            nom_acte = request.form.get("nom_acte", "").strip() or None
            type_tarification = request.form["type_tarification"]
            id_bloc = request.form["id_bloc"]
            forfait_id = (
                request.form.get("forfait_id")
                if type_tarification == "FORFAIT"
                else None
            )

            try:
                duree_reelle = int(request.form["duree_reelle"])
                if duree_reelle <= 0:
                    raise ValueError("La durée doit être positive")
            except ValueError as e:
                flash(f"Durée invalide: {str(e)}", "danger")
                return redirect(url_for("location_bloc_edit", id_dossier=id_dossier))

            montant_paye_caisse = to_decimal(request.form.get("montant_paye_caisse", 0))
            observations = request.form.get("observations", "").strip()

            # Validation du forfait si type FORFAIT
            if type_tarification == "FORFAIT" and not forfait_id:
                flash("Veuillez sélectionner un forfait", "danger")
                return redirect(url_for("location_bloc_edit", id_dossier=id_dossier))

            # Récupération du bloc
            cursor.execute("SELECT * FROM bloc WHERE id_bloc = %s", (id_bloc,))
            bloc = cursor.fetchone()
            if not bloc:
                flash("Bloc opératoire non trouvé", "danger")
                return redirect(url_for("location_bloc_edit", id_dossier=id_dossier))

            # CALCUL DU PRIX SELON LE TYPE DE TARIFICATION
            if type_tarification == "FORFAIT":
                cursor.execute(
                    "SELECT * FROM location_bloc_forfait_actes WHERE id_forfait = %s",
                    (forfait_id,),
                )
                forfait = cursor.fetchone()
                if not forfait:
                    flash("Forfait non trouvé", "danger")
                    return redirect(
                        url_for("location_bloc_edit", id_dossier=id_dossier)
                    )
                prix_bloc = get_prix_forfait_pour_medecin(cursor, id_doctor, forfait_id)
                # ✅ CORRECTION : Utiliser la durée du forfait
                prix_supplement_duree = calculer_supplement_duree(
                    bloc, duree_reelle, forfait.get("duree_forfait")
                )
            else:
                prix_bloc = to_decimal(bloc["prix"])
                prix_supplement_duree = calculer_supplement_duree(bloc, duree_reelle)

            # MISE À JOUR DU DOSSIER PRINCIPAL
            cursor.execute(
                """
                UPDATE location_bloc_dossier_patient
                SET id_doctor = %s,
                    patient = %s,
                    location_date = %s,
                    heure_operation = %s,
                    nom_acte = %s,
                    type_tarification = %s,
                    id_bloc = %s,
                    forfait_id = %s,
                    duree_reelle = %s,
                    prix_bloc = %s,
                    prix_supplement_duree = %s,
                    montant_paye_caisse = %s,
                    observations = %s
                WHERE id_dossier = %s
            """,
                (
                    id_doctor,
                    patient,
                    location_date,
                    heure_operation,
                    nom_acte,
                    type_tarification,
                    id_bloc,
                    forfait_id,
                    duree_reelle,
                    prix_bloc,
                    prix_supplement_duree,
                    montant_paye_caisse,
                    observations,
                    id_dossier,
                ),
            )

            # GESTION DES PRODUITS
            # Suppression des anciens produits
            cursor.execute(
                "DELETE FROM location_bloc_dossier_produits WHERE id_dossier = %s",
                (id_dossier,),
            )

            # Produits inclus dans le forfait/bloc
            if type_tarification == "FORFAIT" and forfait_id:
                cursor.execute(
                    """
                    SELECT fp.id_produit, COALESCE(fp.qte, 0) as qte, COALESCE(p.prix, 0) as prix
                    FROM location_bloc_forfait_actes_produits fp
                    JOIN produits p ON fp.id_produit = p.id_produit
                    WHERE fp.id_forfait = %s
                """,
                    (forfait_id,),
                )
                produits_forfait = cursor.fetchall()

                for prod in produits_forfait:
                    qte_utilisee_key = f'produit_inclus_{prod["id_produit"]}'
                    qte_utilisee = to_decimal(
                        request.form.get(qte_utilisee_key, prod["qte"])
                    )
                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_produits
                        (id_dossier, id_produit, qte_incluse, qte_utilisee, prix_unitaire, source_inclusion)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            prod["id_produit"],
                            prod["qte"],
                            qte_utilisee,
                            prod["prix"],
                            "FORFAIT",
                        ),
                    )
            else:
                cursor.execute(
                    """
                    SELECT bp.id_produit, COALESCE(bp.qte, 0) as qte, COALESCE(p.prix, 0) as prix
                    FROM bloc_produits_inclus bp
                    JOIN produits p ON bp.id_produit = p.id_produit
                    WHERE bp.id_bloc = %s
                """,
                    (id_bloc,),
                )
                produits_bloc = cursor.fetchall()

                for prod in produits_bloc:
                    qte_utilisee_key = f'produit_inclus_{prod["id_produit"]}'
                    qte_utilisee = to_decimal(
                        request.form.get(qte_utilisee_key, prod["qte"])
                    )
                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_produits
                        (id_dossier, id_produit, qte_incluse, qte_utilisee, prix_unitaire, source_inclusion)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            prod["id_produit"],
                            prod["qte"],
                            qte_utilisee,
                            prod["prix"],
                            "BLOC",
                        ),
                    )

            # Produits supplémentaires
            produits_supp_ids = request.form.getlist("produit_supp_id[]")
            produits_supp_qtes = request.form.getlist("produit_supp_qte[]")

            for i, prod_id in enumerate(produits_supp_ids):
                if prod_id and prod_id.strip():
                    qte = to_decimal(
                        produits_supp_qtes[i] if i < len(produits_supp_qtes) else 1
                    )
                    if qte > 0:
                        cursor.execute(
                            "SELECT COALESCE(prix, 0) as prix FROM produits WHERE id_produit = %s",
                            (prod_id,),
                        )
                        prod_info = cursor.fetchone()
                        if prod_info:
                            cursor.execute(
                                """
                                INSERT INTO location_bloc_dossier_produits
                                (id_dossier, id_produit, qte_incluse, qte_utilisee, prix_unitaire,
                                 source_inclusion)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    prod_id,
                                    0,
                                    qte,
                                    prod_info["prix"],
                                    "SUPPLEMENTAIRE",
                                ),
                            )

            # GESTION DES ACTES
            # Suppression des anciens actes
            cursor.execute(
                "DELETE FROM location_bloc_dossier_patient_actes WHERE id_dossier = %s",
                (id_dossier,),
            )

            # Actes inclus dans le forfait
            if type_tarification == "FORFAIT" and forfait_id:
                cursor.execute(
                    """
                    SELECT fa.id_acte, a.nom_acte, COALESCE(a.prix, 0) as prix
                    FROM location_bloc_forfait_actes_inclus fa
                    JOIN actes_supplement a ON fa.id_acte = a.id_acte
                    WHERE fa.id_forfait = %s
                """,
                    (forfait_id,),
                )
                actes_forfait = cursor.fetchall()

                for acte in actes_forfait:
                    qte_utilisee_key = f'acte_inclus_{acte["id_acte"]}'
                    qte_utilisee = to_decimal(request.form.get(qte_utilisee_key, 1))
                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_patient_actes
                        (id_dossier, id_acte, qte_incluse, qte_utilisee, prix_unitaire, source_inclusion)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            acte["id_acte"],
                            1,
                            qte_utilisee,
                            acte["prix"],
                            "FORFAIT",
                        ),
                    )

            # Actes supplémentaires
            actes_supp_ids = request.form.getlist("acte_supp_id[]")
            actes_supp_qtes = request.form.getlist("acte_supp_qte[]")

            for i, acte_id in enumerate(actes_supp_ids):
                if acte_id and acte_id.strip():
                    qte = to_decimal(
                        actes_supp_qtes[i] if i < len(actes_supp_qtes) else 1
                    )
                    if qte > 0:
                        cursor.execute(
                            "SELECT COALESCE(prix, 0) as prix FROM actes_supplement WHERE id_acte = %s",
                            (acte_id,),
                        )
                        acte_info = cursor.fetchone()
                        if acte_info:
                            cursor.execute(
                                """
                                INSERT INTO location_bloc_dossier_patient_actes
                                (id_dossier, id_acte, qte_incluse, qte_utilisee, prix_unitaire,
                                 source_inclusion)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    acte_id,
                                    0,
                                    qte,
                                    acte_info["prix"],
                                    "SUPPLEMENTAIRE",
                                ),
                            )

            # GESTION DES NUITÉES (MULTIPLES)
            # Suppression des anciennes nuitées
            cursor.execute(
                "DELETE FROM location_bloc_dossier_nuitees WHERE id_dossier = %s",
                (id_dossier,),
            )

            dates_entree = request.form.getlist("date_entree_hospitalisation[]")
            dates_sortie = request.form.getlist("date_sortie_hospitalisation[]")
            types_chambre = request.form.getlist("id_type_chambre[]")
            nuits_pre_op = request.form.getlist("nuit_pre_op_gratuite[]")

            # Récupérer le nombre de nuitées pré-op autorisées pour ce médecin
            nuitees_preop_autorisees = get_nuitees_preop_autorisees(cursor, id_doctor)

            # Compteur de nuitées pré-op accordées
            nuit_pre_op_compteur = 0

            for i in range(len(dates_entree)):
                if dates_entree[i] and dates_sortie[i] and types_chambre[i]:
                    cursor.execute(
                        """
                        SELECT est_standard, prix_unitaire
                        FROM type_chambre
                        WHERE id_type_chambre = %s
                    """,
                        (types_chambre[i],),
                    )

                    chambre = cursor.fetchone()
                    if not chambre:
                        continue

                    nombre_nuitees = calculer_nombre_nuitees(
                        dates_entree[i], dates_sortie[i]
                    )

                    # Vérifier si nuit pré-op gratuite demandée ET autorisée
                    nuit_pre_op_gratuite = False

                    if i < len(nuits_pre_op) and nuits_pre_op[i] == "1":
                        # Vérifier si le médecin est autorisé
                        if nuitees_preop_autorisees == 0:
                            flash(
                                f"Attention : Ce médecin n'est pas autorisé à offrir des nuitées pré-op gratuites. "
                                f"La demande pour l'hospitalisation {i + 1} a été ignorée.",
                                "warning",
                            )
                        # Vérifier si chambre standard
                        elif not chambre.get("est_standard", False):
                            flash(
                                f"Attention : La nuit pré-op gratuite n'est pas disponible pour les chambres "
                                f"non-standard (hospitalisation {i + 1})",
                                "warning",
                            )
                        # Vérifier si quota pas dépassé
                        elif nuit_pre_op_compteur >= nuitees_preop_autorisees:
                            flash(
                                f"Attention : Maximum {nuitees_preop_autorisees} nuitée(s) pré-op gratuite(s) autorisée(s). "
                                f"La demande pour l'hospitalisation {i + 1} a été ignorée.",
                                "warning",
                            )
                        else:
                            # Tout est OK, accorder la nuit pré-op gratuite
                            nuit_pre_op_gratuite = True
                            nuit_pre_op_compteur += 1
                            app.logger.info(
                                f"Nuit pré-op gratuite accordée pour l'hospitalisation {i + 1}"
                            )

                    cursor.execute(
                        """
                        INSERT INTO location_bloc_dossier_nuitees
                        (id_dossier, id_type_chambre, date_entree, date_sortie,
                         nombre_nuitees, nuit_pre_op_gratuite, prix_unitaire, prix_total)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            id_dossier,
                            types_chambre[i],
                            dates_entree[i],
                            dates_sortie[i],
                            nombre_nuitees,
                            nuit_pre_op_gratuite,
                            to_decimal(chambre["prix_unitaire"]),
                            0,
                        ),
                    )

            # Calcul du prix total des nuitées avec tarifs personnalisés
            prix_nuitees, total_nuitees, nuitees_facturables, nuitees_details = (
                calculer_nuitees_facturables_avec_tarifs_medecin(
                    cursor, id_dossier, id_doctor, forfait_id
                )
            )

            # Mise à jour du prix de chaque hospitalisation
            if nuitees_details:
                for d in nuitees_details:
                    cursor.execute(
                        """
                        UPDATE location_bloc_dossier_nuitees
                        SET prix_total = %s
                        WHERE id_nuitee = %s
                    """,
                        (d["prix_total"], d["id_nuitee"]),
                    )

            # GESTION DES EXPLORATIONS
            # Suppression des anciennes explorations
            cursor.execute(
                "DELETE FROM location_bloc_dossier_explorations WHERE id_dossier = %s",
                (id_dossier,),
            )

            exploration_types = request.form.getlist("exploration_type[]")
            exploration_noms = request.form.getlist("exploration_nom[]")
            exploration_dates = request.form.getlist("exploration_date[]")
            exploration_prix = request.form.getlist("exploration_prix[]")
            exploration_obs = request.form.getlist("exploration_obs[]")

            prix_explorations = Decimal("0")

            for i, exp_type in enumerate(exploration_types):
                if i < len(exploration_prix) and exploration_prix[i]:
                    try:
                        exp_prix = to_decimal(exploration_prix[i])
                        if exp_prix > 0:
                            exp_nom = (
                                exploration_noms[i].strip()
                                if i < len(exploration_noms) and exploration_noms[i]
                                else None
                            )
                            exp_type_val = exp_type if exp_type else "AUTRE"
                            exp_date = (
                                exploration_dates[i]
                                if i < len(exploration_dates) and exploration_dates[i]
                                else None
                            )
                            exp_obs = (
                                exploration_obs[i].strip()
                                if i < len(exploration_obs) and exploration_obs[i]
                                else ""
                            )

                            # Si pas de nom, on en génère un basé sur le type
                            if not exp_nom:
                                if exp_type_val == "IMAGERIE":
                                    exp_nom = "Imagerie médicale"
                                elif exp_type_val == "LABORATOIRE":
                                    exp_nom = "Analyse laboratoire"
                                else:
                                    exp_nom = "Exploration médicale"

                            cursor.execute(
                                """
                                INSERT INTO location_bloc_dossier_explorations
                                (id_dossier, type_exploration, nom_exploration, date_exploration, prix,
                                 observations)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    exp_type_val,
                                    exp_nom,
                                    exp_date,
                                    exp_prix,
                                    exp_obs,
                                ),
                            )

                            prix_explorations += exp_prix
                    except (ValueError, TypeError) as e:
                        app.logger.warning(f"Erreur dans l'exploration {i}: {str(e)}")
                        continue

            # GESTION DE L'ACTE D'ANESTHÉSIE
            # Suppression des anciens actes d'anesthésie
            cursor.execute(
                "DELETE FROM location_bloc_dossier_anesthesie WHERE id_dossier = %s",
                (id_dossier,),
            )

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
                    # UN SEUL TARIF FORFAITAIRE pour l'acte
                    prix_anesthesie = get_tarif_forfaitaire_anesthesie(
                        cursor, acte_anesth_id
                    )

                    # Pour l'intervenant 1
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
                                INSERT INTO location_bloc_dossier_anesthesie
                                (id_dossier, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    acte_anesth_id,
                                    intervenant1_id,
                                    duree_reelle,
                                    honoraires1,
                                    g.user["id_personnel"],
                                ),
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
                                INSERT INTO location_bloc_dossier_anesthesie
                                (id_dossier, id_acte_anesthesie, id_personnel_anesthesie,
                                 duree_reelle, honoraires_calcules, created_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                                (
                                    id_dossier,
                                    acte_anesth_id,
                                    intervenant2_id,
                                    duree_reelle,
                                    honoraires2,
                                    g.user["id_personnel"],
                                ),
                            )
                except Exception as e:
                    app.logger.warning(f"Erreur acte anesthésie: {str(e)}")

            # CALCUL DES SUPPLÉMENTS
            prix_produits_supplementaires = calculer_supplements_produits(
                cursor, id_dossier
            )
            prix_actes_supplementaires = calculer_supplements_actes(cursor, id_dossier)

            # CALCUL DU PRIX TOTAL FINAL
            prix_total = (
                prix_bloc
                + prix_supplement_duree
                + prix_produits_supplementaires
                + prix_actes_supplementaires
                + prix_nuitees
                + prix_explorations
                + prix_anesthesie
            )

            # Calcul du statut de paiement
            difference_paiement = montant_paye_caisse - prix_total

            if difference_paiement < 0:
                statut_paiement = "COMPLEMENT_MEDECIN"
            elif difference_paiement > 0:
                statut_paiement = "SURPLUS_CLINIQUE"
            else:
                statut_paiement = "AUCUN_PAIEMENT"

            # MISE À JOUR FINALE DU DOSSIER
            cursor.execute(
                """
                UPDATE location_bloc_dossier_patient
                SET prix_produits_supplementaires = %s,
                    prix_nuitees = %s,
                    prix_explorations = %s,
                    prix_anesthesie = %s,
                    prix_total = %s,
                    difference_paiement = %s,
                    statut_paiement = %s
                WHERE id_dossier = %s
            """,
                (
                    prix_produits_supplementaires + prix_actes_supplementaires,
                    prix_nuitees,
                    prix_explorations,
                    prix_anesthesie,
                    prix_total,
                    difference_paiement,
                    statut_paiement,
                    id_dossier,
                ),
            )

            # Mise à jour de la situation médecin
            cursor.execute(
                """
                UPDATE location_bloc_doctor_situations
                SET encaissement_patient = %s
                WHERE id_dossier = %s
            """,
                (montant_paye_caisse, id_dossier),
            )

            connection.commit()
            flash(
                f"Dossier modifié avec succès. Prix total: {float(prix_total):.2f} DA",
                "success",
            )
            return redirect(url_for("location_bloc_detail", id_dossier=id_dossier))

    except Exception as e:
        if connection:
            try:
                connection.rollback()
            except:
                pass
        app.logger.error(f"Erreur lors de la modification: {str(e)}")
        import traceback

        app.logger.error(traceback.format_exc())
        flash(f"Erreur lors de la modification: {str(e)}", "danger")
        return redirect(url_for("location_bloc_edit", id_dossier=id_dossier))

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


# Routes AJAX
@app.route("/api/get_forfait_actes/<int:forfait_id>")
@login_required
def get_forfait_actes(forfait_id):
    """Retourne les actes inclus dans un forfait"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT fa.id_acte,
                   a.nom_acte as nom,
                   COALESCE(a.prix, 0) as prix_unitaire
            FROM location_bloc_forfait_actes_inclus fa
            JOIN actes_supplement a ON fa.id_acte = a.id_acte
            WHERE fa.id_forfait = %s
            ORDER BY a.nom_acte
        """,
            (forfait_id,),
        )

        actes = cursor.fetchall()
        return jsonify(convert_decimals_to_float(actes))

    except Exception as e:
        app.logger.error(f"Erreur get_forfait_actes: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/api/calculer_prix_location_complet", methods=["POST"])
@login_required
def calculer_prix_location_complet():
    """Calcule le prix complet incluant les tarifs personnalisés du médecin"""
    data = request.get_json()
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        type_tarification = data.get("type_tarification")
        id_bloc = data.get("id_bloc")
        id_doctor = data.get("id_doctor")
        duree_reelle = int(data.get("duree_reelle", 90))
        forfait_id = data.get("forfait_id")

        # Récupération du bloc
        cursor.execute("SELECT * FROM bloc WHERE id_bloc = %s", (id_bloc,))
        bloc = cursor.fetchone()

        if not bloc:
            return jsonify({"error": "Bloc non trouvé"}), 404

        if type_tarification == "FORFAIT" and forfait_id:
            # Utiliser le prix personnalisé du médecin si configuré
            if id_doctor:
                prix_bloc = get_prix_forfait_pour_medecin(cursor, id_doctor, forfait_id)
            else:
                cursor.execute(
                    "SELECT prix_forfait FROM location_bloc_forfait_actes WHERE id_forfait = %s",
                    (forfait_id,),
                )
                forfait = cursor.fetchone()
                prix_bloc = (
                    to_decimal(forfait["prix_forfait"]) if forfait else Decimal("0")
                )

            # ✅ CORRECTION : Récupérer la durée du forfait et l'utiliser
            cursor.execute(
                "SELECT duree_forfait FROM location_bloc_forfait_actes WHERE id_forfait = %s",
                (forfait_id,),
            )
            forfait_info = cursor.fetchone()
            duree_forfait = forfait_info.get("duree_forfait") if forfait_info else None

            prix_supplement_duree = calculer_supplement_duree(
                bloc, duree_reelle, duree_forfait
            )
        else:
            prix_bloc = to_decimal(bloc["prix"])
            prix_supplement_duree = calculer_supplement_duree(bloc, duree_reelle)

        return jsonify(
            {
                "prix_bloc": float(prix_bloc),
                "prix_supplement_duree": float(prix_supplement_duree),
                "duree_reelle": duree_reelle,
            }
        )

    except Exception as e:
        app.logger.error(f"Erreur calculer_prix_location_complet: {str( e )}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/api/get_forfaits_medecin/<int:id_doctor>")
@login_required
def api_get_forfaits_medecin(id_doctor):
    """
    Retourne tous les forfaits avec prix personnalisés si configurés.
    Si id_doctor = 0, retourne les forfaits standards sans personnalisation.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        if id_doctor == 0:
            # Pas de médecin sélectionné - retourner les forfaits standards
            cursor.execute(
                """
                SELECT 
                    id_forfait,
                    name_forfait,
                    prix_forfait as prix_standard,
                    prix_forfait,
                    duree_forfait,
                    nbr_nuit,
                    description,
                    est_actif,
                    'STANDARD' as source_prix,
                    NULL as prix_personnalise_raw
                FROM location_bloc_forfait_actes
                WHERE est_actif = 1
                ORDER BY name_forfait
            """
            )
            forfaits = cursor.fetchall()
        else:
            # Médecin sélectionné - retourner les forfaits avec prix personnalisés
            forfaits = get_forfaits_pour_medecin(cursor, id_doctor)

        return jsonify(convert_decimals_to_float(forfaits))

    except Exception as e:
        app.logger.error(f"Erreur get_forfaits_medecin: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/api/get_prix_forfait_medecin/<int:id_doctor>/<int:id_forfait>")
@login_required
def api_get_prix_forfait_medecin(id_doctor, id_forfait):
    """Retourne le prix d'un forfait pour un médecin (personnalisé ou standard)"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        prix = get_prix_forfait_pour_medecin(cursor, id_doctor, id_forfait)

        # Récupérer aussi les infos du forfait
        cursor.execute(
            """
            SELECT f.id_forfait, f.name_forfait, f.prix_forfait as prix_standard,
                   f.duree_forfait, f.nbr_nuit
            FROM location_bloc_forfait_actes f
            WHERE f.id_forfait = %s
        """,
            (id_forfait,),
        )
        forfait = cursor.fetchone()

        return jsonify(
            {
                "id_forfait": id_forfait,
                "prix_forfait": float(prix),
                "prix_standard": float(forfait["prix_standard"]) if forfait else 0,
                "name_forfait": forfait["name_forfait"] if forfait else "",
                "duree_forfait": forfait["duree_forfait"] if forfait else 0,
                "nbr_nuit": forfait["nbr_nuit"] if forfait else 0,
                "est_personnalise": (
                    float(prix) != float(forfait["prix_standard"]) if forfait else False
                ),
            }
        )

    except Exception as e:
        app.logger.error(f"Erreur get_prix_forfait_medecin: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/api/get_prix_chambres_medecin/<int:id_doctor>")
@login_required
def api_get_prix_chambres_medecin(id_doctor):
    """
    Retourne tous les types de chambres avec prix personnalisés si configurés.
    Si id_doctor = 0, retourne les chambres avec prix standards.
    """
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        if id_doctor == 0:
            # Pas de médecin - retourner les chambres standards
            cursor.execute(
                """
                SELECT 
                    id_type_chambre,
                    nom_type,
                    prix_unitaire as prix_standard,
                    prix_unitaire,
                    est_standard,
                    description,
                    capacite,
                    est_actif,
                    'STANDARD' as source_prix
                FROM type_chambre
                WHERE est_actif = 1
                ORDER BY prix_unitaire
            """
            )
            chambres = cursor.fetchall()
        else:
            # Médecin sélectionné - retourner les chambres avec prix personnalisés
            chambres = get_prix_chambres_pour_medecin(cursor, id_doctor)

        return jsonify(convert_decimals_to_float(chambres))

    except Exception as e:
        app.logger.error(f"Erreur get_prix_chambres_medecin: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/api/get_nuitees_preop_autorisees/<int:id_doctor>")
@login_required
def api_get_nuitees_preop_autorisees(id_doctor):
    """
    Retourne le nombre de nuitées pré-op autorisées pour un médecin.
    Si id_doctor = 0, retourne 0.
    """
    if id_doctor == 0:
        return jsonify({"nuitees_preop_autorisees": 0, "id_doctor": 0})

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        nuitees = get_nuitees_preop_autorisees(cursor, id_doctor)

        return jsonify({"nuitees_preop_autorisees": nuitees, "id_doctor": id_doctor})

    except Exception as e:
        app.logger.error(f"Erreur api_get_nuitees_preop_autorisees: {str(e)}")
        return jsonify({"nuitees_preop_autorisees": 0, "error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route("/api/get_prix_chambre_standard_medecin/<int:id_doctor>")
@login_required
def api_get_prix_chambre_standard_medecin(id_doctor):
    """Retourne le prix standard d'une chambre pour un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        prix = get_prix_chambre_standard_pour_medecin(cursor, id_doctor)
        return jsonify({"prix_unitaire": float(prix)})

    except Exception as e:
        app.logger.error(f"Erreur get_prix_chambre_standard_medecin: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
