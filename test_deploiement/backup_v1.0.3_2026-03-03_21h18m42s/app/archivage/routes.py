import json
import os
import re

from flask import flash, g, jsonify, redirect, render_template, request, url_for

from app import app, get_db_connection
from app.archivage.utils import archiver_dossier, generer_emplacements_pour_rayonnage
from app.utils.utiles import handle_errors, login_required

# ==============================================================================
# DASHBOARD & VUES PRINCIPALES
# ==============================================================================


@app.route("/archivage/")
@login_required
@handle_errors()
def archivage_index():
    """Tableau de bord principal de l'archivage."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Stats globales optimisées en une seule requête
        cursor.execute(
            """
            SELECT 
                (SELECT COUNT(*) FROM archivage_boites) as total_boites,
                (SELECT COUNT(*) FROM archivage_dossiers) as total_dossiers,
                (SELECT COUNT(*) FROM archivage_emplacements WHERE est_occupe = 1) as emplacements_occupes,
                (SELECT COUNT(*) FROM archivage_emplacements) as emplacements_total
        """
        )
        stats = cursor.fetchone()

        # Calcul du taux d'occupation
        taux_occupation = 0
        if stats["emplacements_total"] > 0:
            taux_occupation = round(
                (stats["emplacements_occupes"] / stats["emplacements_total"]) * 100, 1
            )

        # Liste des dernières entrées
        cursor.execute(
            """
            SELECT d.*, b.numero_archive, 
                   CONCAT(doc.last_name, ' ', doc.first_name) as medecin_nom,
                   d.type_dossier, d.statut,
                   DATE_FORMAT(d.date_archivage, '%d/%m/%Y %H:%i') as date_formatee,
                   s.date_sortie, s.motif as sortie_motif,
                   CONCAT(COALESCE(ps.prenom, ''), ' ', COALESCE(ps.nom, '')) as sorti_par_nom
            FROM archivage_dossiers d
            JOIN archivage_boites b ON d.id_boite = b.id
            LEFT JOIN doctors doc ON b.id_medecin = doc.id
            LEFT JOIN archivage_dossiers_sorties s ON d.id = s.id_dossier AND s.date_retour IS NULL
            LEFT JOIN personnel ps ON s.sorti_par = ps.id_personnel
            ORDER BY d.date_archivage DESC
            LIMIT 10
        """
        )
        derniers_dossiers = cursor.fetchall()

        return render_template(
            "archivage/index.html",
            total_boites=stats["total_boites"],
            total_dossiers=stats["total_dossiers"],
            total_emplacements_occupes=stats["emplacements_occupes"],
            taux_occupation=taux_occupation,
            derniers_dossiers=derniers_dossiers,
        )

    finally:
        conn.close()


@app.route("/archivage/plan")
@login_required
@handle_errors()
def archivage_plan_visuel():
    """Affiche la grille visuelle des rayonnages (Optimisé)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Récupérer TOUS les rayonnages avec les infos de zonage et de spécialités
        cursor.execute(
            """
            SELECT 
                r.id, r.nom_zone, r.code_etagere, r.nb_lignes, r.largeur_cm, 
                r.est_interne, r.est_partageable,
                GROUP_CONCAT(ars.id_specialty) as specialties
            FROM archivage_rayonnages r
            LEFT JOIN archivage_rayonnage_specialites ars ON r.id = ars.id_rayonnage
            GROUP BY r.id, r.nom_zone, r.code_etagere, r.nb_lignes, r.largeur_cm, r.est_interne, r.est_partageable
            ORDER BY r.nom_zone, r.code_etagere
        """
        )
        rayonnages = cursor.fetchall()

        # Récupérer les spécialités pour le formulaire
        cursor.execute(
            "SELECT id_specialty, name_specialty FROM specialty ORDER BY name_specialty"
        )
        all_specialties = cursor.fetchall()

        # 2. Récupérer TOUS les emplacements avec cumul des boîtes
        cursor.execute(
            """
            SELECT 
                e.id_rayonnage, 
                e.colonne_x, e.ligne_y,
                r.largeur_cm,
                COUNT(b.id) as nb_boites,
                COALESCE(SUM(t.epaisseur_max_mm), 0) as occupe_mm
            FROM archivage_emplacements e
            JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            LEFT JOIN archivage_boites b ON b.id_emplacement = e.id
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            GROUP BY e.id, r.largeur_cm
            ORDER BY e.id_rayonnage, e.ligne_y DESC, e.colonne_x ASC
        """
        )
        all_cells = cursor.fetchall()

        # 3. Organiser les cellules par rayonnage
        from collections import defaultdict

        cells_by_shelf = defaultdict(list)

        for row in all_cells:
            # Calcul du pourcentage de remplissage de l'emplacement (largeur utilisée)
            capacite_mm = row["largeur_cm"] * 10
            pct = 0
            if capacite_mm > 0:
                pct = min(100, int((row["occupe_mm"] / capacite_mm) * 100))

            est_occupe = row["nb_boites"] > 0

            cell_obj = {
                "est_occupe": est_occupe,
                "est_pleine": pct >= 100,
                "remplissage_pct": pct,
                "nb_boites": row["nb_boites"],
                "ligne_y": row["ligne_y"],
                "colonne_x": row["colonne_x"],
            }
            cells_by_shelf[row["id_rayonnage"]].append(cell_obj)

        # 4. Organiser par zones pour l'affichage
        zones = {}
        for r in rayonnages:
            shelf_id = r["id"]
            # Construire l'objet rayonnage
            shelf_data = {
                "id": shelf_id,
                "nom_zone": r["nom_zone"] if r["nom_zone"] else "Zone Sans Nom",
                "code_etagere": r["code_etagere"],
                "nb_lignes": r["nb_lignes"],
                "largeur_cm": r["largeur_cm"],
                "specialties": r["specialties"],  # Remplacement de id_specialty
                "est_interne": r["est_interne"],
                "est_partageable": r["est_partageable"],
                "cells": cells_by_shelf[shelf_id],
            }

            z_name = shelf_data["nom_zone"]
            if z_name not in zones:
                zones[z_name] = []
            zones[z_name].append(shelf_data)

        # 5. Fetch doctors for modal usage
        cursor.execute(
            """
            SELECT d.id, d.last_name, d.first_name, s.name_specialty 
            FROM doctors d 
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty 
            ORDER BY d.last_name, d.first_name
        """
        )
        all_doctors = cursor.fetchall()

        # 6. Charger la configuration du layout (JSON)
        layout_config = {}
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "layout.json"
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    layout_config = json.load(f)
        except Exception as e:
            print(f"Erreur chargement layout: {e}")

        return render_template(
            "archivage/plan_visuel.html",
            zones=zones,
            all_specialties=all_specialties,
            all_doctors=all_doctors,
            layout_config=layout_config,
        )

    finally:
        conn.close()


@app.route("/archivage/plan/detail/<int:id_rayonnage>")
@login_required
@handle_errors()
def archivage_detail_rayonnage(id_rayonnage):
    """Affiche une vue détaillée d'un seul rayonnage."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Info Rayonnage
        cursor.execute(
            "SELECT * FROM archivage_rayonnages WHERE id = %s", (id_rayonnage,)
        )
        rayonnage = cursor.fetchone()

        if not rayonnage:
            flash("Rayonnage non trouvé.", "error")
            return redirect(url_for("archivage_plan_visuel"))

        # Fetch all doctors for configuration Modal
        cursor.execute(
            "SELECT id, last_name, first_name FROM doctors ORDER BY last_name, first_name"
        )
        all_doctors = cursor.fetchall()

        # 2. Emplacements avec toutes les informations
        cursor.execute(
            """
            SELECT 
                e.id as emplacement_id, e.colonne_x, e.ligne_y,
                e.est_partageable as cell_est_partageable,
                GROUP_CONCAT(res_doc.last_name ORDER BY res_doc.last_name SEPARATOR ', ') as reserved_medecins_noms,
                b.id as box_id,
                b.numero_archive, 
                b.epaisseur_actuelle_mm, 
                b.est_pleine,
                t.epaisseur_max_mm,
                CONCAT(doc.last_name, ' ', doc.first_name) as medecin_nom,
                (SELECT COUNT(*) FROM archivage_dossiers WHERE id_boite = b.id) as nb_dossiers
            FROM archivage_emplacements e
            LEFT JOIN archivage_emplacements_medecins aem ON e.id = aem.id_emplacement
            LEFT JOIN doctors res_doc ON aem.id_medecin = res_doc.id -- Médecins réservés
            LEFT JOIN archivage_boites b ON b.id_emplacement = e.id
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            LEFT JOIN doctors doc ON b.id_medecin = doc.id -- Médecin de la boîte
            WHERE e.id_rayonnage = %s
            GROUP BY e.id, e.colonne_x, e.ligne_y, b.id
            ORDER BY e.ligne_y DESC, e.colonne_x ASC, b.id ASC
        """,
            (id_rayonnage,),
        )

        raw_cells = cursor.fetchall()

        # Mapping (x, y) -> Data
        cells_map = {}
        nb_colonnes = 1

        for row in raw_cells:
            key = (row["colonne_x"], row["ligne_y"])
            nb_colonnes = max(nb_colonnes, row["colonne_x"])

            # Initialiser l'emplacement
            if key not in cells_map:
                cells_map[key] = {
                    "id_emplacement": row["emplacement_id"],
                    "est_occupe": False,
                    "boites": [],
                    "largeur_restante_mm": rayonnage["largeur_cm"] * 10,
                    "reserved_medecins_noms": row["reserved_medecins_noms"],
                    "cell_est_partageable": row["cell_est_partageable"],
                }

            # Ajouter la boîte si présente
            if row["box_id"]:
                cells_map[key]["est_occupe"] = True

                # Calcul pourcentage remplissage boite
                pct = 0
                box_width_mm = row["epaisseur_max_mm"] or 100  # Default fallback

                if box_width_mm > 0:
                    pct = min(
                        100, int((row["epaisseur_actuelle_mm"] / box_width_mm) * 100)
                    )

                boite_data = {
                    "id": row["box_id"],
                    "numero_archive": row["numero_archive"],
                    "medecin_nom": (
                        row["medecin_nom"] if row["medecin_nom"] else "Inconnu"
                    ),
                    "remplissage_pct": pct,
                    "est_pleine": row["est_pleine"],
                    "nb_dossiers": row["nb_dossiers"] or 0,
                    "epaisseur_mm": box_width_mm,
                }

                cells_map[key]["boites"].append(boite_data)
                cells_map[key]["largeur_restante_mm"] -= box_width_mm

        # Zones pour le transfert
        cursor.execute(
            "SELECT DISTINCT nom_zone FROM archivage_rayonnages WHERE nom_zone IS NOT NULL ORDER BY nom_zone"
        )
        zones_transfert = cursor.fetchall()

        return render_template(
            "archivage/detail_rayonnage.html",
            rayonnage=rayonnage,
            cells_map=cells_map,
            nb_colonnes=nb_colonnes,
            all_doctors=all_doctors,
            zones_transfert=zones_transfert,
        )

    finally:
        conn.close()


@app.route("/archivage/config/cellule/modifier", methods=["POST"])
@login_required
@handle_errors()
def archivage_modifier_cellule():
    """Modifier la configuration d'une cellule spécifique."""
    cell_id = request.form.get("cell_id")
    id_rayonnage = request.form.get("id_rayonnage")
    id_medecin = request.form.get("id_medecin")
    est_partageable = request.form.get("est_partageable")  # '1', '0', or ''

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Convert inputs
        val_id_medecin = int(id_medecin) if id_medecin and id_medecin.strip() else None

        val_est_partageable = None
        if est_partageable == "1":
            val_est_partageable = 1
        elif est_partageable == "0":
            val_est_partageable = 0

        cursor.execute(
            """
            UPDATE archivage_emplacements
            SET id_medecin = %s, est_partageable = %s
            WHERE id = %s
        """,
            (val_id_medecin, val_est_partageable, cell_id),
        )

        conn.commit()
        flash("Configuration de la cellule mise à jour.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Erreur update cellule: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("archivage_detail_rayonnage", id_rayonnage=id_rayonnage))


# ==============================================================================
# API & RECHERCHE
# ==============================================================================


@app.route("/archivage/api/layout/save", methods=["POST"])
@login_required
@handle_errors()
def archivage_api_save_layout():
    """Sauvegarde la configuration du layout (grid-area) dans un fichier JSON."""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "Données invalides"}), 400

        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "layout.json"
        )

        with open(config_path, "w") as f:
            json.dump(data, f, indent=4)

        return jsonify({"success": True, "message": "Layout sauvegardé avec succès"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/archivage/api/search-location")
@login_required
@handle_errors()
def archivage_api_search():
    """API pour la recherche interactive sur le plan."""
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"found": False, "message": "Recherche vide"})

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Recherche multi-critères
        sql = """
            SELECT 
                b.id as boite_id, 
                b.numero_archive,
                r.id as rayonnage_id, 
                r.code_etagere, 
                r.nom_zone,
                e.colonne_x, 
                e.ligne_y,
                MAX(d.nom_patient) as nom_patient,
                MAX(d.id_patient_his) as id_patient_his
            FROM archivage_boites b
            LEFT JOIN archivage_dossiers d ON b.id = d.id_boite
            JOIN archivage_emplacements e ON b.id_emplacement = e.id
            JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE 
                d.id_patient_his LIKE %s 
                OR d.nom_patient LIKE %s
                OR b.numero_archive LIKE %s
            GROUP BY 
                b.id, b.numero_archive, r.id, r.code_etagere, r.nom_zone, e.colonne_x, e.ligne_y
        """
        search_term = f"%{query}%"
        cursor.execute(sql, (search_term, search_term, search_term))
        results = cursor.fetchall()

        if results:
            # Si plusieurs résultats, retourner la liste
            if len(results) > 1:
                return jsonify(
                    {
                        "found": True,
                        "multiple": True,
                        "results": [
                            {
                                "boite_id": r["boite_id"],
                                "location_text": f"{r['code_etagere']} - Col {r['colonne_x']}, Ligne {r['ligne_y']}",
                                "rayonnage_id": r["rayonnage_id"],
                                "patient": r["nom_patient"],
                                "numero_archive": r["numero_archive"],
                                "col": r["colonne_x"],
                                "ligne": r["ligne_y"],
                            }
                            for r in results
                        ],
                    }
                )

            # Un seul résultat
            result = results[0]
            return jsonify(
                {
                    "found": True,
                    "multiple": False,
                    "boite_id": result["boite_id"],
                    "location_text": f"Rayon {result['code_etagere']} - Col {result['colonne_x']}, Ligne {result['ligne_y']}",
                    "rayonnage_id": result["rayonnage_id"],
                    "rayonnage": result["code_etagere"],
                    "zone": result["nom_zone"],
                    "col": result["colonne_x"],
                    "ligne": result["ligne_y"],
                    "patient": result["nom_patient"],
                }
            )
        else:
            return jsonify({"found": False, "message": "Aucun résultat trouvé"})

    except Exception as e:
        return jsonify({"found": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/archivage/api/box/<int:box_id>/details")
@login_required
@handle_errors()
def archivage_api_box_details(box_id):
    """API pour récupérer les détails d'une boîte et ses dossiers."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Info Boîte
        cursor.execute(
            """
            SELECT 
                b.id, b.numero_archive, b.epaisseur_actuelle_mm, b.est_pleine,
                t.nom as type_boite, t.epaisseur_max_mm,
                CONCAT(doc.last_name, ' ', doc.first_name) as medecin_nom,
                s.name_specialty as specialite
            FROM archivage_boites b
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            LEFT JOIN doctors doc ON b.id_medecin = doc.id
            LEFT JOIN specialty s ON doc.id_specialty = s.id_specialty
            WHERE b.id = %s
        """,
            (box_id,),
        )
        boite = cursor.fetchone()

        if not boite:
            return jsonify({"error": "Boîte introuvable"}), 404

        # Add computed percentage
        ep_actuelle = boite["epaisseur_actuelle_mm"] or 0
        ep_max = boite["epaisseur_max_mm"] or 100

        if boite["est_pleine"]:
            boite["remplissage_pct"] = 100
        elif ep_max > 0:
            boite["remplissage_pct"] = min(100, int((ep_actuelle / ep_max) * 100))
        else:
            boite["remplissage_pct"] = 0

        # 2. Liste des dossiers de base et l'archiveur
        cursor.execute(
            """
            SELECT 
                d.id, d.nom_patient, d.type_dossier, d.id_patient_his,
                DATE_FORMAT(d.date_archivage, '%%d/%%m/%%Y %%H:%%i') as date_heure_archivage,
                d.source_module, d.id_source, d.statut,
                CONCAT(p.nom, ' ', p.prenom) as archiveur,
                s.date_sortie, s.motif as sortie_motif,
                CONCAT(COALESCE(ps.prenom, ''), ' ', COALESCE(ps.nom, '')) as sorti_par_nom,
                DATE_FORMAT(
                   COALESCE(
                       IF(d.source_module='MATERNITE', 
                       (SELECT date_accouchement FROM accouchement_dossiers WHERE accouchement_dossiers.id_dossier=d.id_source),
                       IF(d.source_module='BLOC_EXTERNE', 
                       (SELECT str_to_date(location_date, '%%d/%%m/%%Y') FROM location_bloc_dossier_patient WHERE location_bloc_dossier_patient.id_dossier=d.id_source),
                       IF(d.source_module='PRESTATION KT', (SELECT acte_date FROM kt_dossier_patient WHERE kt_dossier_patient.id_dossier=d.id_source LIMIT 1),
                       IF(d.source_module='BLOC_INTERNE', (SELECT date_creation FROM medecin_interne_actes WHERE medecin_interne_actes.id_acte=d.id_source), 
                       d.date_archivage))))
                   ), '%%d/%%m/%%Y') as date_acte
            FROM archivage_dossiers d
            LEFT JOIN personnel p ON d.archive_par = p.id_personnel
            LEFT JOIN archivage_dossiers_sorties s ON d.id = s.id_dossier AND s.date_retour IS NULL
            LEFT JOIN personnel ps ON s.sorti_par = ps.id_personnel
            WHERE d.id_boite = %s
            ORDER BY d.date_archivage DESC
        """,
            (box_id,),
        )
        dossiers_raw = cursor.fetchall()

        # 3. Enrichir les dossiers avec les noms des actes
        dossiers = []
        for d in dossiers_raw:
            actes_noms = []
            source_module = d["source_module"]
            id_source = d["id_source"]

            if source_module == "MATERNITE":
                actes_noms.append("Accouchement/Maternité")
            elif source_module == "PRESTATION KT":
                cursor.execute(
                    """
                    SELECT a.name_acte_kt 
                    FROM kt_dossier_actes da
                    JOIN kt_actes a ON da.id_acte = a.id_acte
                    WHERE da.id_dossier = %s
                """,
                    (id_source,),
                )
                for row in cursor.fetchall():
                    nom_acte = (
                        row["name_acte_kt"]
                        if "name_acte_kt" in row
                        else row.get("nom_acte")
                    )
                    if nom_acte:
                        actes_noms.append(nom_acte)
            elif source_module == "BLOC_INTERNE":
                cursor.execute(
                    "SELECT nom_acte FROM medecin_interne_actes WHERE id_acte = %s",
                    (id_source,),
                )
                main_acte = cursor.fetchone()
                if main_acte and main_acte["nom_acte"]:
                    actes_noms.append(main_acte["nom_acte"])

                cursor.execute(
                    """
                    SELECT nom_acte 
                    FROM medecin_interne_actes_supplementaires 
                    WHERE id_acte_principal = %s
                """,
                    (id_source,),
                )
                for row in cursor.fetchall():
                    if row["nom_acte"]:
                        actes_noms.append(row["nom_acte"])
            elif source_module == "BLOC_EXTERNE":
                cursor.execute(
                    "SELECT nom_acte FROM location_bloc_dossier_patient WHERE id_dossier = %s",
                    (id_source,),
                )
                main_acte = cursor.fetchone()
                if main_acte and main_acte["nom_acte"]:
                    actes_noms.append(main_acte["nom_acte"])

                cursor.execute(
                    """
                    SELECT a.nom_acte 
                    FROM location_bloc_dossier_patient_actes da
                    JOIN actes_supplement a ON da.id_acte = a.id_acte
                    WHERE da.id_dossier = %s
                """,
                    (id_source,),
                )
                for row in cursor.fetchall():
                    if row["nom_acte"] and row["nom_acte"] not in actes_noms:
                        actes_noms.append(row["nom_acte"])

            # Use `dict(d)` because dict cursor rows might not support arbitrary modification
            d_dict = dict(d)
            if d_dict.get("date_sortie"):
                d_dict["date_sortie"] = (
                    d_dict["date_sortie"].strftime("%d/%m/%Y %H:%M")
                    if hasattr(d_dict["date_sortie"], "strftime")
                    else d_dict["date_sortie"]
                )

            d_dict["actes_noms"] = (
                ", ".join(actes_noms) if actes_noms else "Non spécifié"
            )
            dossiers.append(d_dict)

        return jsonify({"boite": boite, "dossiers": dossiers})

    finally:
        conn.close()


# ==============================================================================
# CONFIGURATION / CRUD RAYONNAGES
# ==============================================================================


@app.route("/archivage/config/rayonnages/nouveau", methods=["POST"])
@login_required
@handle_errors()
def archivage_nouveau_rayonnage():
    """Création d'un nouveau rayonnage avec validation."""
    nom_zone = request.form.get("nom_zone", "").strip()

    # Validation des dimensions
    try:
        nb_lignes = int(request.form.get("nb_lignes", 7))
        largeur_cm = int(request.form.get("largeur_cm", 100))
        # Nouveaux champs
        id_specialties = request.form.getlist("id_specialty[]")
        if not id_specialties:
            # Fallback for old forms if needed
            single_id = request.form.get("id_specialty")
            if single_id:
                id_specialties = [single_id]

        est_interne = request.form.get("est_interne") == "1"  # Checkbox or select 1/0
        est_partageable = request.form.get("est_partageable") == "1"  # Checkbox 1/0

        if nb_lignes < 1 or nb_lignes > 30:
            raise ValueError("Nombre de lignes invalide (1-30)")
        if largeur_cm < 10 or largeur_cm > 300:
            raise ValueError("Largeur invalide (10-300 cm)")
    except ValueError as e:
        flash(f"Erreur de validation: {str(e)}", "error")
        return redirect(url_for("archivage_plan_visuel"))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Génération automatique du code si vide
        prefix = "R"
        nom_clean = nom_zone.lower().strip() if nom_zone else ""

        if "face" in nom_clean and "gauche" in nom_clean:
            prefix = "FG"
        elif (
            "face" in nom_clean
            and ("milieu" in nom_clean or "central" in nom_clean)
            and "centre" not in nom_clean
        ):
            prefix = "FM"
        elif "face" in nom_clean and ("droit" in nom_clean or "droite" in nom_clean):
            prefix = "FD"
        elif "centre" in nom_clean and "face" in nom_clean:
            prefix = "CF"
        elif "centre" in nom_clean and "dos" in nom_clean:
            prefix = "CD"
        elif "centre" in nom_clean:
            prefix = "C"
        elif ("entree" in nom_clean or "entrée" in nom_clean) and "gauche" in nom_clean:
            prefix = "EG"
        elif ("entree" in nom_clean or "entrée" in nom_clean) and (
            "droit" in nom_clean or "droite" in nom_clean
        ):
            prefix = "ED"
        elif "entree" in nom_clean or "entrée" in nom_clean:
            prefix = "E"
        elif "gauche" in nom_clean:
            prefix = "G"
        elif "droit" in nom_clean or "droite" in nom_clean:
            prefix = "D"
        elif nom_clean:
            prefix = nom_zone[0].upper()

        # Trouver le prochain numéro disponible
        cursor.execute(
            """
            SELECT code_etagere FROM archivage_rayonnages 
            WHERE nom_zone = %s AND code_etagere LIKE %s
            ORDER BY code_etagere DESC LIMIT 1
        """,
            (nom_zone, f"{prefix}%"),
        )

        last = cursor.fetchone()
        next_num = 1

        if last:
            # Extraire le numéro du dernier code
            match = re.search(r"\d+$", last["code_etagere"])
            if match:
                next_num = int(match.group()) + 1

        code_etagere = f"{prefix}{next_num}"

        # Insertion
        cursor.execute(
            """
            INSERT INTO archivage_rayonnages (nom_zone, code_etagere, nb_lignes, largeur_cm, est_interne, est_partageable)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
            (
                nom_zone,
                code_etagere,
                nb_lignes,
                largeur_cm,
                1 if est_interne else 0,
                1 if est_partageable else 0,
            ),
        )
        rayonnage_id = cursor.lastrowid

        # Insertion des spécialités
        if id_specialties:
            for spec_id in id_specialties:
                if spec_id:
                    cursor.execute(
                        """
                        INSERT INTO archivage_rayonnage_specialites (id_rayonnage, id_specialty)
                        VALUES (%s, %s)
                    """,
                        (rayonnage_id, spec_id),
                    )

        # Génération des emplacements
        generer_emplacements_pour_rayonnage(rayonnage_id, nb_lignes, cursor=cursor)

        conn.commit()

        flash(f"Rayonnage '{code_etagere}' créé avec succès.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Erreur lors de la création: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("archivage_plan_visuel"))


@app.route("/archivage/config/rayonnages/modifier", methods=["POST"])
@login_required
@handle_errors()
def archivage_modifier_rayonnage():
    """Modification d'un rayonnage existant."""
    id_rayonnage = request.form.get("id")
    nom_zone = request.form.get("nom_zone", "").strip()

    # Validation
    try:
        nb_lignes = int(request.form.get("nb_lignes"))
        largeur_cm = int(request.form.get("largeur_cm", 100))
        # Nouveaux champs
        id_specialties = request.form.getlist("id_specialty[]")
        if not id_specialties:
            single_id = request.form.get("id_specialty")
            if single_id:
                id_specialties = [single_id]

        est_interne = request.form.get("est_interne") == "1"
        est_partageable = request.form.get("est_partageable") == "1"

        if nb_lignes < 1 or nb_lignes > 30:
            raise ValueError("Lignes: 1-30")
        if largeur_cm < 10 or largeur_cm > 500:
            raise ValueError("Largeur invalide (10-500 cm)")
    except ValueError as e:
        flash(f"Dimensions invalides: {str(e)}", "error")
        return redirect(url_for("archivage_plan_visuel"))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier que le rayonnage existe
        cursor.execute(
            "SELECT * FROM archivage_rayonnages WHERE id = %s", (id_rayonnage,)
        )
        if not cursor.fetchone():
            flash("Rayonnage introuvable", "error")
            return redirect(url_for("archivage_plan_visuel"))

        cursor.execute(
            """
            UPDATE archivage_rayonnages 
            SET nb_lignes=%s, largeur_cm=%s, est_interne=%s, est_partageable=%s
            WHERE id=%s
        """,
            (
                nb_lignes,
                largeur_cm,
                1 if est_interne else 0,
                1 if est_partageable else 0,
                id_rayonnage,
            ),
        )

        # 1. DELETE existing specialties
        cursor.execute(
            "DELETE FROM archivage_rayonnage_specialites WHERE id_rayonnage = %s",
            (id_rayonnage,),
        )

        # 2. INSERT new specialties
        if id_specialties:
            for spec_id in id_specialties:
                if spec_id:
                    cursor.execute(
                        """
                        INSERT INTO archivage_rayonnage_specialites (id_rayonnage, id_specialty)
                        VALUES (%s, %s)
                    """,
                        (id_rayonnage, spec_id),
                    )

        generer_emplacements_pour_rayonnage(id_rayonnage, nb_lignes, cursor=cursor)

        # Nettoyage des emplacements hors limites (seulement vides)
        cursor.execute(
            """
            DELETE FROM archivage_emplacements 
            WHERE id_rayonnage = %s 
              AND (ligne_y > %s OR colonne_x > 1)
              AND est_occupe = 0
        """,
            (id_rayonnage, nb_lignes),
        )

        # Vérifier emplacements orphelins occupés
        cursor.execute(
            """
            SELECT COUNT(*) as cnt FROM archivage_emplacements 
            WHERE id_rayonnage = %s 
              AND (ligne_y > %s OR colonne_x > 1)
              AND est_occupe = 1
        """,
            (id_rayonnage, nb_lignes),
        )

        orphans = cursor.fetchone()["cnt"]

        # === NEW: Update Row Configurations ===
        for y in range(1, nb_lignes + 1):
            selected_doctors = request.form.getlist(f"medecins_ligne_{y}")
            est_partageable_row = request.form.get(f"partageable_ligne_{y}")

            val_est_partageable = (
                int(est_partageable_row) if est_partageable_row in ["0", "1"] else None
            )

            # Get Cell IDs
            cursor.execute(
                "SELECT id FROM archivage_emplacements WHERE id_rayonnage = %s AND ligne_y = %s",
                (id_rayonnage, y),
            )
            c_rows = cursor.fetchall()
            c_ids = [c["id"] for c in c_rows]

            if not c_ids:
                continue

            placeholders = ", ".join(["%s"] * len(c_ids))

            # Update est_partageable
            cursor.execute(
                f"UPDATE archivage_emplacements SET est_partageable = %s WHERE id IN ({placeholders})",
                (val_est_partageable, *c_ids),
            )

            # Update M2M
            cursor.execute(
                f"DELETE FROM archivage_emplacements_medecins WHERE id_emplacement IN ({placeholders})",
                tuple(c_ids),
            )

            if selected_doctors:
                insert_values = []
                for cid in c_ids:
                    for doc_id in selected_doctors:
                        insert_values.append((cid, int(doc_id)))
                if insert_values:
                    cursor.executemany(
                        "INSERT INTO archivage_emplacements_medecins (id_emplacement, id_medecin) VALUES (%s, %s)",
                        insert_values,
                    )

        conn.commit()

        if orphans > 0:
            flash(
                f"Rayonnage modifié. ATTENTION: {orphans} emplacement(s) occupé(s) hors limites!",
                "warning",
            )
        else:
            flash("Rayonnage mis à jour avec succès", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Erreur: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("archivage_plan_visuel"))


@app.route("/archivage/config/rayonnages/supprimer/<int:id>")
@login_required
@handle_errors()
def archivage_supprimer_rayonnage(id):
    """Suppression d'un rayonnage (seulement si vide)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Vérifier existence
        cursor.execute(
            "SELECT code_etagere FROM archivage_rayonnages WHERE id = %s", (id,)
        )
        rayonnage = cursor.fetchone()
        if not rayonnage:
            flash("Rayonnage introuvable", "error")
            return redirect(url_for("archivage_plan_visuel"))

        # Vérifier si vide
        cursor.execute(
            """
            SELECT COUNT(*) as cnt 
            FROM archivage_emplacements 
            WHERE id_rayonnage = %s AND est_occupe = 1
        """,
            (id,),
        )

        if cursor.fetchone()["cnt"] > 0:
            flash("Impossible: ce rayonnage contient des boîtes!", "error")
            return redirect(url_for("archivage_plan_visuel"))

        # Suppression (les emplacements seront supprimés en cascade)
        cursor.execute("DELETE FROM archivage_rayonnages WHERE id = %s", (id,))
        conn.commit()

        flash(f"Rayonnage '{rayonnage['code_etagere']}' supprimé", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Erreur: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("archivage_plan_visuel"))


# ==============================================================================
# CONFIGURATION TYPES DE BOÎTES
# ==============================================================================


@app.route("/archivage/config/types-boites")
@login_required
@handle_errors()
def archivage_admin_types_boites():
    """Administration des types de boîtes."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.*, 
                   COUNT(b.id) as nb_boites_utilisees
            FROM archivage_types_boites t
            LEFT JOIN archivage_boites b ON t.id = b.id_type_boite
            GROUP BY t.id
            ORDER BY t.nom
        """
        )
        types = cursor.fetchall()
        return render_template("archivage/config_types_boites.html", types=types)
    finally:
        conn.close()


@app.route("/archivage/config/types-boites/update", methods=["POST"])
@login_required
@handle_errors()
def archivage_update_type_boite():
    """Mise à jour d'un type de boîte."""
    type_id = request.form.get("type_id")

    try:
        hauteur_cm = float(request.form.get("hauteur_cm"))
        epaisseur_max_mm = float(request.form.get("epaisseur_max_mm"))

        if hauteur_cm <= 0 or epaisseur_max_mm <= 0:
            raise ValueError("Valeurs positives requises")

    except ValueError as e:
        flash(f"Valeurs invalides: {str(e)}", "error")
        return redirect(url_for("archivage_admin_types_boites"))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE archivage_types_boites 
            SET hauteur_cm = %s, epaisseur_max_mm = %s
            WHERE id = %s
        """,
            (hauteur_cm, epaisseur_max_mm, type_id),
        )
        conn.commit()

        flash("Paramètres mis à jour", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erreur: {str(e)}", "error")
    finally:
        conn.close()

    return redirect(url_for("archivage_admin_types_boites"))


@app.route(
    "/archivage/config/rayonnage/<int:id_rayonnage>/edit-rows", methods=["GET", "POST"]
)
@login_required
@handle_errors()
def archivage_configurer_rayonnage_lignes(id_rayonnage):
    """Configuration avancée du rayonnage par étagère (Ligne)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Info Rayonnage
        cursor.execute(
            "SELECT * FROM archivage_rayonnages WHERE id = %s", (id_rayonnage,)
        )
        rayonnage = cursor.fetchone()

        if not rayonnage:
            flash("Rayonnage introuvable", "error")
            return redirect(url_for("archivage_plan_visuel"))

        if request.method == "POST":
            # === SAUVEGARDE ===
            try:
                # Pour chaque ligne
                for y in range(1, rayonnage["nb_lignes"] + 1):
                    # 1. Récupérer les médecins sélectionnés pour cette ligne
                    selected_doctors = request.form.getlist(
                        f"medecins_ligne_{y}"
                    )  # List of IDs
                    est_partageable = request.form.get(
                        f"partageable_ligne_{y}"
                    )  # '1', '0' or None

                    val_est_partageable = (
                        int(est_partageable) if est_partageable in ["0", "1"] else None
                    )

                    # 2. Récupérer TOUS les emplacements de cette ligne
                    cursor.execute(
                        "SELECT id FROM archivage_emplacements WHERE id_rayonnage = %s AND ligne_y = %s",
                        (id_rayonnage, y),
                    )
                    cells = cursor.fetchall()
                    cell_ids = [c["id"] for c in cells]

                    if not cell_ids:
                        continue

                    # 3. Mettre à jour est_partageable pour toutes les cellules
                    # Note: On écrase la config individuelle par celle de la ligne
                    placeholders = ", ".join(["%s"] * len(cell_ids))
                    cursor.execute(
                        f"UPDATE archivage_emplacements SET est_partageable = %s WHERE id IN ({placeholders})",
                        (val_est_partageable, *cell_ids),
                    )

                    # 4. Mettre à jour les médecins (M2M)
                    # D'abord supprimer les anciens
                    cursor.execute(
                        f"DELETE FROM archivage_emplacements_medecins WHERE id_emplacement IN ({placeholders})",
                        tuple(cell_ids),
                    )

                    # Puis insérer les nouveaux (pour CHAQUE cellule de la ligne)
                    if selected_doctors:
                        insert_values = []
                        for cid in cell_ids:
                            for doc_id in selected_doctors:
                                insert_values.append((cid, int(doc_id)))

                        if insert_values:
                            cursor.executemany(
                                "INSERT INTO archivage_emplacements_medecins (id_emplacement, id_medecin) VALUES (%s, %s)",
                                insert_values,
                            )

                conn.commit()
                flash("Configuration des étagères mise à jour avec succès.", "success")
                return redirect(
                    url_for("archivage_detail_rayonnage", id_rayonnage=id_rayonnage)
                )

            except Exception as e:
                conn.rollback()
                flash(f"Erreur lors de la sauvegarde: {str(e)}", "error")

        # === AFFICHAGE (GET) ===

        # Liste des médecins
        cursor.execute(
            "SELECT id, last_name, first_name FROM doctors ORDER BY last_name, first_name"
        )
        all_doctors = cursor.fetchall()

        # Configuration actuelle (agrégée par ligne)
        # On suppose que la ligne est configurée de manière homogène. On prend la config de la col 1.
        cursor.execute(
            """
            SELECT 
                e.ligne_y, e.est_partageable,
                GROUP_CONCAT(aem.id_medecin) as medecin_ids
            FROM archivage_emplacements e
            LEFT JOIN archivage_emplacements_medecins aem ON e.id = aem.id_emplacement
            WHERE e.id_rayonnage = %s AND e.colonne_x = 1
            GROUP BY e.ligne_y
        """,
            (id_rayonnage,),
        )

        rows_config_raw = cursor.fetchall()
        rows_config = {}
        for r in rows_config_raw:
            m_ids = []
            if r["medecin_ids"]:
                m_ids = [int(x) for x in r["medecin_ids"].split(",")]

            rows_config[r["ligne_y"]] = {
                "est_partageable": r["est_partageable"],
                "medecin_ids": m_ids,
            }

        return render_template(
            "archivage/config_rayonnage_lignes.html",
            rayonnage=rayonnage,
            all_doctors=all_doctors,
            rows_config=rows_config,
        )

    finally:
        conn.close()


@app.route("/archivage/api/rayonnage/<int:id_rayonnage>/config-lignes")
@login_required
def archivage_api_get_row_config(id_rayonnage):
    """API pour obtenir la config des lignes d'un rayonnage."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # On suppose que la ligne est configurée de manière homogène. On prend la config de la col 1.
        cursor.execute(
            """
            SELECT 
                e.ligne_y, e.est_partageable,
                GROUP_CONCAT(aem.id_medecin) as medecin_ids
            FROM archivage_emplacements e
            LEFT JOIN archivage_emplacements_medecins aem ON e.id = aem.id_emplacement
            WHERE e.id_rayonnage = %s AND e.colonne_x = 1
            GROUP BY e.ligne_y
        """,
            (id_rayonnage,),
        )

        rows = cursor.fetchall()

        data = {}
        for r in rows:
            m_ids = []
            if r["medecin_ids"]:
                m_ids = [int(x) for x in r["medecin_ids"].split(",")]
            data[r["ligne_y"]] = {
                "est_partageable": r["est_partageable"],
                "medecin_ids": m_ids,
            }

        return jsonify(data)
    finally:
        conn.close()


@app.route("/archivage/api/doctors/filter")
@login_required
def archivage_api_filter_doctors():
    """Filtre les médecins selon spécialité et type."""
    specialties = request.args.getlist("specialty_id")
    specialties = [s for s in specialties if s]  # Remove empty strings

    est_interne = request.args.get("est_interne")  # '0', '1' or empty

    query = """
        SELECT d.id, d.last_name, d.first_name, s.name_specialty, d.est_interne
        FROM doctors d
        LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
        WHERE 1=1
    """
    params = []

    if specialties:
        placeholders = ", ".join(["%s"] * len(specialties))
        query += f" AND d.id_specialty IN ({placeholders})"
        params.extend(specialties)

    if est_interne is not None and est_interne != "":
        query += " AND d.est_interne = %s"
        params.append(est_interne)

    query += " ORDER BY d.last_name, d.first_name"

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        doctors = cursor.fetchall()

        # Format for Choice.js
        result = []
        for doc in doctors:
            label = f"Dr. {doc['last_name']} {doc['first_name']}"
            if doc["name_specialty"]:
                label += f" - {doc['name_specialty']}"
            if doc["est_interne"]:
                label += " (Interne)"

            result.append(
                {
                    "value": doc["id"],
                    "label": label,
                    "selected": False,
                    "disabled": False,
                }
            )

        return jsonify(result)
    finally:
        conn.close()


# ==============================================================================
# DOSSIERS CLINIQUES (VUE UNIFIÉE)
# ==============================================================================


@app.route("/archivage/dossiers_cliniques")
@login_required
@handle_errors()
def archivage_dossiers_cliniques():
    """Vue unifiée de tous les dossiers cliniques pour archivage (Accouchement, Bloc, KT, Interne)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Filtres
        etat_archivage = request.args.get("etat_archivage", "all")
        id_doctor = request.args.get("doctor", "all")
        search_query = request.args.get("q", "").strip()

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 40, type=int)
        if per_page <= 0:
            per_page = 40
        offset = (page - 1) * per_page

        # Requête UNION ALL de base
        union_query = """
            SELECT 
                'BLOC_EXTERNE' COLLATE utf8mb4_general_ci as source_module,
                id_dossier as id_source,
                patient COLLATE utf8mb4_general_ci as nom_patient,
                CAST(patient_oid_his AS CHAR) COLLATE utf8mb4_general_ci as patient_oid_his,
                location_date as date_acte,
                id_doctor
            FROM location_bloc_dossier_patient
            
            UNION ALL
            
            SELECT 
                'BLOC_INTERNE' COLLATE utf8mb4_general_ci as source_module,
                id_acte as id_source,
                patient COLLATE utf8mb4_general_ci as nom_patient,
                CAST(patient_oid_his AS CHAR) COLLATE utf8mb4_general_ci as patient_oid_his,
                date_acte,
                id_doctor
            FROM medecin_interne_actes
            
            UNION ALL
            
            SELECT 
                'PRESTATION KT' COLLATE utf8mb4_general_ci as source_module,
                id_dossier as id_source,
                patient COLLATE utf8mb4_general_ci as nom_patient,
                CAST(patient_oid_his AS CHAR) COLLATE utf8mb4_general_ci as patient_oid_his,
                acte_date as date_acte,
                id_doctor
            FROM kt_dossier_patient
            
            UNION ALL
            
            SELECT 
                'MATERNITE' COLLATE utf8mb4_general_ci as source_module,
                id_dossier as id_source,
                patiente COLLATE utf8mb4_general_ci as nom_patient,
                CAST(patient_oid AS CHAR) COLLATE utf8mb4_general_ci as patient_oid_his,
                date_accouchement as date_acte,
                id_gyneco as id_doctor
            FROM accouchement_dossiers
        """

        where_clauses = ["1=1"]
        params = []

        if etat_archivage == "archive":
            where_clauses.append("ad.id IS NOT NULL")
        elif etat_archivage == "non_archive":
            where_clauses.append("ad.id IS NULL")

        if id_doctor != "all":
            where_clauses.append("base.id_doctor = %s")
            params.append(id_doctor)

        if search_query:
            where_clauses.append(
                "(base.nom_patient LIKE %s OR ab.numero_archive LIKE %s)"
            )
            params.extend([f"%{search_query}%", f"%{search_query}%"])

        where_sql = " AND ".join(where_clauses)

        # Requête de comptage
        count_query = f"""
            SELECT COUNT(*) as total
            FROM (
                {union_query}
            ) as base
            LEFT JOIN archivage_dossiers ad ON 
                ad.source_module = base.source_module AND ad.id_source = base.id_source
            LEFT JOIN archivage_boites ab ON ad.id_boite = ab.id AND ab.id_medecin = base.id_doctor
            WHERE {where_sql}
        """
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()["total"]
        total_pages = (total_records + per_page - 1) // per_page
        if total_pages == 0:
            total_pages = 1

        # Requête principale avec pagination
        full_query = f"""
            SELECT 
                base.*,
                CONCAT(doc.last_name, ' ', doc.first_name) as doctor_name,
                ad.id as id_archivage,
                ad.date_archivage,
                ab.numero_archive as numero_boite,
                ab.id_emplacement,
                ae.colonne_x, ae.ligne_y,
                ar.id as id_rayonnage,
                ar.nom_zone, ar.code_etagere
            FROM (
                {union_query}
            ) as base
            LEFT JOIN doctors doc ON base.id_doctor = doc.id
            LEFT JOIN archivage_dossiers ad ON 
                ad.source_module = base.source_module AND ad.id_source = base.id_source
            LEFT JOIN archivage_boites ab ON ad.id_boite = ab.id AND ab.id_medecin = base.id_doctor
            LEFT JOIN archivage_emplacements ae ON ab.id_emplacement = ae.id
            LEFT JOIN archivage_rayonnages ar ON ae.id_rayonnage = ar.id
            WHERE {where_sql}
            ORDER BY base.date_acte DESC
            LIMIT %s OFFSET %s
        """

        params.extend([per_page, offset])
        cursor.execute(full_query, params)
        dossiers_list = cursor.fetchall()

        # Top 10 médecins avec le plus de dossiers NON archivés
        top_medecins_query = f"""
            SELECT base.id_doctor, CONCAT(doc.last_name, ' ', doc.first_name) as doctor_name, COUNT(*) as pending_count
            FROM (
                {union_query}
            ) as base
            LEFT JOIN doctors doc ON base.id_doctor = doc.id
            LEFT JOIN archivage_dossiers ad ON 
                ad.source_module = base.source_module AND ad.id_source = base.id_source
            WHERE ad.id IS NULL
            GROUP BY base.id_doctor, doc.last_name, doc.first_name
            ORDER BY pending_count DESC
            LIMIT 10
        """
        cursor.execute(top_medecins_query)
        top_medecins_pending = cursor.fetchall()

        # Enrichir les dossiers avec les noms des actes et conventions
        enriched_dossiers = []
        for d in dossiers_list:
            d_dict = dict(d)
            actes_noms = []
            convention_info = None
            source_module = d["source_module"]
            id_source = d["id_source"]

            if source_module == "MATERNITE":
                actes_noms.append("Accouchement/Maternité")
                cursor.execute(
                    "SELECT type_tarification FROM accouchement_dossiers WHERE id_dossier = %s",
                    (id_source,),
                )
                maternite = cursor.fetchone()
                if maternite and maternite["type_tarification"] == "CONVENTION":
                    convention_info = "Conventionné"

            elif source_module == "PRESTATION KT":
                cursor.execute(
                    """
                    SELECT a.name_acte_kt, c.nom_convention 
                    FROM kt_dossier_actes da
                    JOIN kt_actes a ON da.id_acte = a.id_acte
                    LEFT JOIN kt_conventions c ON da.id_convention = c.id_convention
                    WHERE da.id_dossier = %s
                """,
                    (id_source,),
                )
                for row in cursor.fetchall():
                    nom_acte = (
                        row["name_acte_kt"]
                        if "name_acte_kt" in row
                        else row.get("nom_acte")
                    )
                    if nom_acte:
                        actes_noms.append(nom_acte)
                    if row["nom_convention"] and not convention_info:
                        convention_info = row["nom_convention"]

            elif source_module == "BLOC_INTERNE":
                # Acte principal
                cursor.execute(
                    "SELECT nom_acte FROM medecin_interne_actes WHERE id_acte = %s",
                    (id_source,),
                )
                main_acte = cursor.fetchone()
                if main_acte and main_acte["nom_acte"]:
                    actes_noms.append(main_acte["nom_acte"])

                # Actes supplémentaires
                cursor.execute(
                    """
                    SELECT nom_acte 
                    FROM medecin_interne_actes_supplementaires 
                    WHERE id_acte_principal = %s
                """,
                    (id_source,),
                )
                for row in cursor.fetchall():
                    if row["nom_acte"]:
                        actes_noms.append(row["nom_acte"])

            elif source_module == "BLOC_EXTERNE":
                # Acte principal
                cursor.execute(
                    "SELECT nom_acte FROM location_bloc_dossier_patient WHERE id_dossier = %s",
                    (id_source,),
                )
                main_acte = cursor.fetchone()
                if main_acte and main_acte["nom_acte"]:
                    actes_noms.append(main_acte["nom_acte"])

                # Actes via table de liaison
                cursor.execute(
                    """
                    SELECT a.nom_acte 
                    FROM location_bloc_dossier_patient_actes da
                    JOIN actes_supplement a ON da.id_acte = a.id_acte
                    WHERE da.id_dossier = %s
                """,
                    (id_source,),
                )
                for row in cursor.fetchall():
                    if row["nom_acte"] and row["nom_acte"] not in actes_noms:
                        actes_noms.append(row["nom_acte"])

            d_dict["actes_noms"] = (
                ", ".join(actes_noms) if actes_noms else "Non spécifié"
            )
            d_dict["convention_info"] = convention_info
            enriched_dossiers.append(d_dict)

        dossiers_list = enriched_dossiers

        # Médecins pour le filtre
        cursor.execute(
            """
            SELECT id, CONCAT(last_name, ' ', first_name) as title 
            FROM doctors 
            WHERE id IN (
                SELECT DISTINCT id_doctor FROM location_bloc_dossier_patient
                UNION
                SELECT DISTINCT id_doctor FROM medecin_interne_actes
                UNION
                SELECT DISTINCT id_doctor FROM kt_dossier_patient
                UNION
                SELECT DISTINCT id_gyneco FROM accouchement_dossiers
            )
            ORDER BY last_name, first_name
        """
        )
        doctors = cursor.fetchall()

        # Types de boîtes pour la sélection
        cursor.execute(
            "SELECT id, nom, epaisseur_max_mm FROM archivage_types_boites ORDER BY epaisseur_max_mm ASC"
        )
        types_boites = cursor.fetchall()

        return render_template(
            "archivage/dossiers_cliniques.html",
            dossiers=dossiers_list,
            doctors=doctors,
            types_boites=types_boites,
            top_medecins_pending=top_medecins_pending,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_records=total_records,
            filters={
                "etat_archivage": etat_archivage,
                "doctor": id_doctor,
                "q": search_query,
                "per_page": per_page,
            },
        )
    finally:
        conn.close()


@app.route("/archivage/api/check_box_space", methods=["POST"])
@login_required
@handle_errors()
def archivage_api_check_box_space():
    """Vérifie si le médecin a déjà une boîte avec de l'espace pour ce dossier."""
    data = request.get_json()
    id_doctor = data.get("id_doctor")
    source_module = data.get("source_module")
    id_source = data.get("id_source")

    if not id_doctor or not source_module or not id_source:
        return jsonify({"success": False, "message": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        type_dossier = "SIMPLE"

        if source_module == "MATERNITE":
            cursor.execute(
                "SELECT type_tarification FROM accouchement_dossiers WHERE id_dossier = %s",
                (id_source,),
            )
            maternite = cursor.fetchone()
            if maternite and maternite["type_tarification"] == "CONVENTION":
                type_dossier = "CONVENTION"
        elif source_module == "PRESTATION KT":
            cursor.execute(
                "SELECT COUNT(*) as has_conv FROM kt_dossier_actes WHERE id_dossier = %s AND id_convention IS NOT NULL",
                (id_source,),
            )
            kt = cursor.fetchone()
            if kt and kt["has_conv"] > 0:
                type_dossier = "CONVENTION"

        from app.archivage.utils import (
            EPAISSEUR_DOSSIER_CONVENTION,
            EPAISSEUR_DOSSIER_SIMPLE,
            verifier_espace_boite_medecin,
        )

        epaisseur = (
            EPAISSEUR_DOSSIER_CONVENTION
            if type_dossier == "CONVENTION"
            else EPAISSEUR_DOSSIER_SIMPLE
        )

        numero_archive = verifier_espace_boite_medecin(id_doctor, epaisseur)
        has_space = numero_archive is not None

        return jsonify(
            {"success": True, "has_space": has_space, "numero_archive": numero_archive}
        )
    finally:
        conn.close()


@app.route("/archivage/api/auto_archive", methods=["POST"])
@login_required
@handle_errors()
def archivage_api_auto_archive():
    """Propose et effectue l'archivage automatique d'un dossier."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Données invalides"}), 400

    id_patient_his = data.get("patient_oid_his")
    nom_patient = data.get("nom_patient")
    id_doctor = data.get("id_doctor")
    source_module = data.get("source_module")
    id_source = data.get("id_source")  # Added for precise querying
    id_type_boite_preferee = data.get("type_boite_preferee")

    if not nom_patient or not id_doctor or not source_module or not id_source:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Informations patient, médecin ou source manquantes",
                }
            ),
            400,
        )

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Détermination automatique du type de dossier (Épaisseur)
        type_dossier = "SIMPLE"  # Par défaut

        if source_module == "MATERNITE":
            cursor.execute(
                "SELECT type_tarification FROM accouchement_dossiers WHERE id_dossier = %s",
                (id_source,),
            )
            maternite = cursor.fetchone()
            if maternite and maternite["type_tarification"] == "CONVENTION":
                type_dossier = "CONVENTION"

        elif source_module == "PRESTATION KT":
            # Vérifier s'il y a un id_convention lié à ce dossier
            cursor.execute(
                "SELECT COUNT(*) as has_conv FROM kt_dossier_actes WHERE id_dossier = %s AND id_convention IS NOT NULL",
                (id_source,),
            )
            kt = cursor.fetchone()
            if kt and kt["has_conv"] > 0:
                type_dossier = "CONVENTION"

        # Pour BLOC_INTERNE et BLOC_EXTERNE, c'est toujours 'SIMPLE' pour l'instant.

        user_id = g.user["id_personnel"] if g.user else None

        # Effectuer l'archivage
        dossier_id, id_boite = archiver_dossier(
            id_patient_his=id_patient_his,
            nom_patient=nom_patient,
            type_dossier=type_dossier,
            id_medecin=id_doctor,
            user_id=user_id,
            source_module=source_module,
            id_source=id_source,
            id_type_boite_preferee=id_type_boite_preferee,
        )

        # Récupérer les informations de la boîte pour le message de succès
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    ab.numero_archive,
                    ar.nom_zone, 
                    ar.code_etagere,
                    ae.ligne_y,
                    ae.colonne_x
                FROM archivage_boites ab
                LEFT JOIN archivage_emplacements ae ON ab.id_emplacement = ae.id
                LEFT JOIN archivage_rayonnages ar ON ae.id_rayonnage = ar.id
                WHERE ab.id = %s
            """,
                (id_boite,),
            )
            box_info = cursor.fetchone()

            message = "Dossier archivé avec succès."
            if box_info and box_info["nom_zone"]:
                message = f"Dossier archivé dans la boîte {box_info['numero_archive']} (Zone: {box_info['nom_zone']}, Étagère: {box_info['code_etagere']}, Ligne: {box_info['ligne_y']}, Col: {box_info['colonne_x']})."

            return jsonify({"success": True, "message": message, "box_info": box_info})
        finally:
            conn.close()

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/archivage/api/check_bulk_needs", methods=["POST"])
@login_required
@handle_errors()
def archivage_api_check_bulk_needs():
    """Vérifie si de nouvelles boîtes sont nécessaires pour une sélection de dossiers."""
    data = request.get_json()
    dossiers = data.get("dossiers", [])

    if not dossiers:
        return jsonify({"success": False, "message": "Aucun dossier sélectionné"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        from app.archivage.utils import (
            EPAISSEUR_DOSSIER_CONVENTION,
            EPAISSEUR_DOSSIER_SIMPLE,
        )

        # Grouper les dossiers par médecin pour calculer l'épaisseur requise
        besoins_par_medecin = {}
        for d in dossiers:
            id_medecin = d.get("id_doctor")
            if not id_medecin:
                continue

            type_dossier = "SIMPLE"
            source_module = d.get("source_module")
            id_source = d.get("id_source")

            if source_module == "MATERNITE":
                cursor.execute(
                    "SELECT type_tarification FROM accouchement_dossiers WHERE id_dossier = %s",
                    (id_source,),
                )
                maternite = cursor.fetchone()
                if maternite and maternite["type_tarification"] == "CONVENTION":
                    type_dossier = "CONVENTION"
            elif source_module == "PRESTATION KT":
                cursor.execute(
                    "SELECT COUNT(*) as has_conv FROM kt_dossier_actes WHERE id_dossier = %s AND id_convention IS NOT NULL",
                    (id_source,),
                )
                kt = cursor.fetchone()
                if kt and kt["has_conv"] > 0:
                    type_dossier = "CONVENTION"

            epaisseur = (
                EPAISSEUR_DOSSIER_CONVENTION
                if type_dossier == "CONVENTION"
                else EPAISSEUR_DOSSIER_SIMPLE
            )
            besoins_par_medecin[id_medecin] = (
                besoins_par_medecin.get(id_medecin, 0) + epaisseur
            )

        medecins_need_box = []

        # Pour chaque médecin, vérifier s'il a assez de place cumulée dans ses boîtes *actuelles*
        for id_medecin, epaisseur_requise in besoins_par_medecin.items():
            cursor.execute(
                """
                SELECT SUM(t.epaisseur_max_mm - b.epaisseur_actuelle_mm) as espace_dispo
                FROM archivage_boites b
                JOIN archivage_types_boites t ON b.id_type_boite = t.id
                WHERE b.id_medecin = %s AND b.est_pleine = 0
            """,
                (id_medecin,),
            )
            result = cursor.fetchone()
            espace_dispo = (
                result["espace_dispo"] if result and result["espace_dispo"] else 0
            )

            if epaisseur_requise > espace_dispo:
                # Il a besoin d'une nouvelle boîte. On récupère son nom.
                cursor.execute(
                    """
                    SELECT CONCAT(d.last_name, ' ', d.first_name, COALESCE(CONCAT(' (', s.name_specialty, ')'), '')) as title 
                    FROM doctors d
                    LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
                    WHERE d.id = %s
                """,
                    (id_medecin,),
                )
                doc_info = cursor.fetchone()
                title = doc_info["title"] if doc_info else f"Médecin n°{id_medecin}"

                medecins_need_box.append({"id_medecin": id_medecin, "title": title})

        return jsonify(
            {
                "success": True,
                "needs_boxes": len(medecins_need_box) > 0,
                "doctors": medecins_need_box,
            }
        )

    finally:
        conn.close()


@app.route("/archivage/api/auto_archive_bulk", methods=["POST"])
@login_required
@handle_errors()
def archivage_api_auto_archive_bulk():
    """Archive un lot de dossiers en appliquant la logique de décalage chronologique."""
    data = request.get_json()
    dossiers = data.get("dossiers", [])
    box_preferences = data.get(
        "box_preferences", {}
    )  # { "id_medecin": "id_type_boite" }

    if not dossiers:
        return jsonify({"success": False, "message": "Aucun dossier sélectionné"}), 400

    user_id = g.user["id_personnel"] if g.user else None

    from app.archivage.utils import archiver_dossiers_masse

    try:
        results = archiver_dossiers_masse(dossiers, box_preferences, user_id)

        return jsonify(
            {
                "success": True,
                "message": f"{results.get('total_archived', 0)} dossiers archivés avec succès.",
                "details": results,
            }
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ==============================================================================
# MODE DÉPLACEMENT ET VUE ZONE
# ==============================================================================


@app.route("/archivage/plan/zone/<string:nom_zone>")
@login_required
@handle_errors()
def archivage_detail_zone(nom_zone):
    """Affiche une vue consolidée de tous les rayonnages d'une zone avec Drag & Drop."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Info Zone (Rayonnages)
        cursor.execute(
            "SELECT * FROM archivage_rayonnages WHERE nom_zone = %s ORDER BY code_etagere",
            (nom_zone,),
        )
        rayonnages = cursor.fetchall()

        if not rayonnages:
            flash(f"Zone '{nom_zone}' introuvable ou vide.", "error")
            return redirect(url_for("archivage_plan_visuel"))

        # 2. Fetch all doctors for configuration Modal
        cursor.execute(
            "SELECT id, last_name, first_name FROM doctors ORDER BY last_name, first_name"
        )
        all_doctors = cursor.fetchall()

        # List of other zones for transfer
        cursor.execute(
            "SELECT DISTINCT nom_zone FROM archivage_rayonnages WHERE nom_zone != %s AND nom_zone IS NOT NULL ORDER BY nom_zone",
            (nom_zone,),
        )
        zones_transfert = cursor.fetchall()

        # 3. Récupérer TOUTES les cellules pour TOUS les rayonnages de la zone
        rayonnage_ids = tuple([r["id"] for r in rayonnages])
        if not rayonnage_ids:
            return redirect(url_for("archivage_plan_visuel"))

        placeholders = ", ".join(["%s"] * len(rayonnage_ids))

        cursor.execute(
            f"""
            SELECT 
                r.id as rayonnage_id,
                e.id as emplacement_id, e.colonne_x, e.ligne_y,
                e.est_partageable as cell_est_partageable,
                GROUP_CONCAT(res_doc.last_name ORDER BY res_doc.last_name SEPARATOR ', ') as reserved_medecins_noms,
                b.id as box_id,
                b.numero_archive, 
                b.epaisseur_actuelle_mm, 
                b.est_pleine,
                b.id_medecin as box_medecin_id,
                doc.id_specialty as box_specialty_id,
                t.epaisseur_max_mm,
                CONCAT(doc.last_name, ' ', doc.first_name) as medecin_nom,
                (SELECT COUNT(*) FROM archivage_dossiers WHERE id_boite = b.id) as nb_dossiers
            FROM archivage_emplacements e
            JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            LEFT JOIN archivage_emplacements_medecins aem ON e.id = aem.id_emplacement
            LEFT JOIN doctors res_doc ON aem.id_medecin = res_doc.id
            LEFT JOIN archivage_boites b ON b.id_emplacement = e.id
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            LEFT JOIN doctors doc ON b.id_medecin = doc.id
            WHERE e.id_rayonnage IN ({placeholders})
            GROUP BY r.id, e.id, e.colonne_x, e.ligne_y, b.id
            ORDER BY r.code_etagere, e.ligne_y DESC, e.colonne_x ASC, b.id ASC
        """,
            rayonnage_ids,
        )

        raw_cells = cursor.fetchall()

        # Mapping: rayonnage_id -> cells_map (which is (x,y) -> config)
        zone_data = {}
        for r in rayonnages:
            zone_data[r["id"]] = {"rayonnage": r, "cells_map": {}, "nb_colonnes": 1}

        for row in raw_cells:
            rid = row["rayonnage_id"]
            key = (row["colonne_x"], row["ligne_y"])
            r_data = zone_data[rid]
            r_data["nb_colonnes"] = max(r_data["nb_colonnes"], row["colonne_x"])

            if key not in r_data["cells_map"]:
                r_data["cells_map"][key] = {
                    "id_emplacement": row["emplacement_id"],
                    "est_occupe": False,
                    "boites": [],
                    "largeur_restante_mm": r_data["rayonnage"]["largeur_cm"] * 10,
                    "reserved_medecins_noms": row["reserved_medecins_noms"],
                    "cell_est_partageable": row["cell_est_partageable"],
                }

            if row["box_id"]:
                r_data["cells_map"][key]["est_occupe"] = True
                pct = 0
                box_width_mm = row["epaisseur_max_mm"] or 100
                if box_width_mm > 0:
                    pct = min(
                        100, int((row["epaisseur_actuelle_mm"] / box_width_mm) * 100)
                    )

                boite_data = {
                    "id": row["box_id"],
                    "numero_archive": row["numero_archive"],
                    "medecin_nom": (
                        row["medecin_nom"] if row["medecin_nom"] else "Inconnu"
                    ),
                    "id_medecin": row["box_medecin_id"],
                    "id_specialty": row["box_specialty_id"],
                    "remplissage_pct": pct,
                    "est_pleine": row["est_pleine"],
                    "nb_dossiers": row["nb_dossiers"] or 0,
                    "epaisseur_mm": box_width_mm,
                }

                r_data["cells_map"][key]["boites"].append(boite_data)
                r_data["cells_map"][key]["largeur_restante_mm"] -= box_width_mm

        return render_template(
            "archivage/detail_zone.html",
            nom_zone=nom_zone,
            zone_data=zone_data,
            all_doctors=all_doctors,
            zones_transfert=zones_transfert,
        )

    finally:
        conn.close()


@app.route("/archivage/api/move_box", methods=["POST"])
@login_required
@handle_errors()
def archivage_api_move_box():
    """Déplace une boîte vers un nouvel emplacement via Drag & Drop."""
    data = request.json
    box_id = data.get("box_id")
    new_emplacement_id = data.get("new_emplacement_id")
    force_config = data.get("force_config", False)

    if not box_id or not new_emplacement_id:
        return jsonify({"success": False, "message": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Get box info
        cursor.execute(
            """
            SELECT b.id, b.id_emplacement, b.id_medecin, doc.id_specialty, t.epaisseur_max_mm
            FROM archivage_boites b
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            LEFT JOIN doctors doc ON b.id_medecin = doc.id
            WHERE b.id = %s
        """,
            (box_id,),
        )
        boite = cursor.fetchone()

        if not boite:
            return jsonify({"success": False, "message": "Boîte introuvable"}), 404

        old_emplacement_id = boite["id_emplacement"]
        box_width = boite["epaisseur_max_mm"] or 100
        box_medecin_id = boite["id_medecin"]
        box_specialty_id = boite["id_specialty"]

        if str(old_emplacement_id) == str(new_emplacement_id):
            return jsonify({"success": True, "message": "Boîte déjà à cet emplacement"})

        # 2. Get new emplacement info & check capacity
        cursor.execute(
            """
            SELECT e.id, e.id_rayonnage, r.largeur_cm,
                   (SELECT COALESCE(SUM(t2.epaisseur_max_mm), 0) FROM archivage_boites b2 JOIN archivage_types_boites t2 ON b2.id_type_boite = t2.id WHERE b2.id_emplacement = e.id) as occupe_mm
            FROM archivage_emplacements e
            JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE e.id = %s
        """,
            (new_emplacement_id,),
        )
        new_emp = cursor.fetchone()

        if not new_emp:
            return (
                jsonify({"success": False, "message": "Emplacement cible introuvable"}),
                404,
            )

        capacite_mm = new_emp["largeur_cm"] * 10
        espace_restant = capacite_mm - new_emp["occupe_mm"]

        if espace_restant < box_width:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Espace insuffisant sur cette cellule. (Requis: {box_width/10}cm, Dispo: {espace_restant/10}cm)",
                    }
                ),
                400,
            )

        # 3. Check Specialty/Doctor compatibility on the rayonnage
        new_rayonnage_id = new_emp["id_rayonnage"]

        # Specialites allowed on this rayonnage
        cursor.execute(
            "SELECT id_specialty FROM archivage_rayonnage_specialites WHERE id_rayonnage = %s",
            (new_rayonnage_id,),
        )
        allowed_specs = cursor.fetchall()

        requires_warning = False
        warning_msg = ""

        # If the rayonnage has assigned specialties and the box's specialty is NOT in them
        if allowed_specs and box_specialty_id is not None:
            allowed_spec_ids = [s["id_specialty"] for s in allowed_specs]
            if box_specialty_id not in allowed_spec_ids:
                requires_warning = True
                cursor.execute(
                    "SELECT name_specialty FROM specialty WHERE id_specialty = %s",
                    (box_specialty_id,),
                )
                spec_name = (
                    cursor.fetchone()["name_specialty"]
                    if cursor.rowcount
                    else "Inconnue"
                )
                warning_msg = f"Cette zone n'est pas configurée pour la spécialité {spec_name}. Voulez-vous ajouter cette spécialité à la configuration du rayonnage ?"

        if requires_warning and not force_config:
            return (
                jsonify(
                    {
                        "success": False,
                        "needs_confirmation": True,
                        "message": warning_msg,
                    }
                ),
                200,
            )

        # 4. Perform the move

        if force_config and requires_warning:
            # Add specialty to rayonnage config to silence future warnings
            cursor.execute(
                "INSERT IGNORE INTO archivage_rayonnage_specialites (id_rayonnage, id_specialty) VALUES (%s, %s)",
                (new_rayonnage_id, box_specialty_id),
            )

        # Update Box
        cursor.execute(
            "UPDATE archivage_boites SET id_emplacement = %s WHERE id = %s",
            (new_emplacement_id, box_id),
        )

        # Update Old Emplacement (mark unoccupied if no boxes left)
        cursor.execute(
            """
            UPDATE archivage_emplacements 
            SET est_occupe = (SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END FROM archivage_boites WHERE id_emplacement = %s)
            WHERE id = %s
        """,
            (old_emplacement_id, old_emplacement_id),
        )

        # Update New Emplacement
        cursor.execute(
            "UPDATE archivage_emplacements SET est_occupe = 1, id_boite_actuelle = %s WHERE id = %s",
            (box_id, new_emplacement_id),
        )

        # Log DEPLACEMENT_ZONE for all dossiers in this box
        from app.archivage.utils import log_historique

        cursor.execute(
            "SELECT id FROM archivage_dossiers WHERE id_boite = %s AND statut != 'DESARCHIVE'",
            (box_id,),
        )
        dossiers_in_box = cursor.fetchall()
        # Get zone names for logging
        cursor.execute(
            "SELECT r.nom_zone FROM archivage_emplacements e JOIN archivage_rayonnages r ON e.id_rayonnage = r.id WHERE e.id = %s",
            (old_emplacement_id,),
        )
        old_zone_row = cursor.fetchone()
        cursor.execute(
            "SELECT r.nom_zone FROM archivage_emplacements e JOIN archivage_rayonnages r ON e.id_rayonnage = r.id WHERE e.id = %s",
            (new_emplacement_id,),
        )
        new_zone_row = cursor.fetchone()
        old_zone_name = old_zone_row["nom_zone"] if old_zone_row else None
        new_zone_name = new_zone_row["nom_zone"] if new_zone_row else None
        user_id = g.user["id_personnel"] if g.user else None
        for d in dossiers_in_box:
            log_historique(
                d["id"],
                "DEPLACEMENT_ZONE",
                user_id,
                cursor,
                zone_avant=old_zone_name,
                zone_apres=new_zone_name,
                commentaire=f"Déplacement boîte via drag & drop",
            )

        conn.commit()
        return jsonify({"success": True, "message": "Boîte déplacée avec succès."})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@app.route("/archivage/api/transfer_box_zone", methods=["POST"])
@login_required
@handle_errors()
def archivage_api_transfer_box_zone():
    """Transfère automatiquement une boîte vers une autre zone."""
    data = request.json
    box_id = data.get("box_id")
    target_zone = data.get("target_zone")

    if not box_id or not target_zone:
        return jsonify({"success": False, "message": "Paramètres manquants"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. Get Box info
        cursor.execute(
            """
            SELECT b.id, b.id_emplacement, b.id_medecin, t.epaisseur_max_mm
            FROM archivage_boites b
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            WHERE b.id = %s
        """,
            (box_id,),
        )
        boite = cursor.fetchone()

        if not boite:
            return jsonify({"success": False, "message": "Boîte introuvable"}), 404

        old_emplacement_id = boite["id_emplacement"]
        box_width = boite["epaisseur_max_mm"] or 100
        box_medecin_id = boite["id_medecin"]

        # 2. Use specialized logic to find free spot in the target zone ONLY (needs update in utils.py)
        from app.archivage.utils import trouver_emplacement_libre

        # Find cell
        try:
            # Assuming we updated trouver_emplacement_libre to take nom_zone
            new_emplacement_id = trouver_emplacement_libre(
                box_width, box_medecin_id, nom_zone=target_zone, cursor=cursor
            )
        except Exception as e:
            return (
                jsonify(
                    {"success": False, "message": f"Transfert impossible: {str(e)}"}
                ),
                400,
            )

        # 3. Perform move
        cursor.execute(
            "UPDATE archivage_boites SET id_emplacement = %s WHERE id = %s",
            (new_emplacement_id, box_id),
        )

        # Mark occupancies
        cursor.execute(
            """
            UPDATE archivage_emplacements 
            SET est_occupe = (SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END FROM archivage_boites WHERE id_emplacement = %s)
            WHERE id = %s
        """,
            (old_emplacement_id, old_emplacement_id),
        )

        cursor.execute(
            "UPDATE archivage_emplacements SET est_occupe = 1, id_boite_actuelle = %s WHERE id = %s",
            (box_id, new_emplacement_id),
        )

        # Log DEPLACEMENT_ZONE for all dossiers in this box
        from app.archivage.utils import log_historique

        cursor.execute(
            "SELECT id FROM archivage_dossiers WHERE id_boite = %s AND statut != 'DESARCHIVE'",
            (box_id,),
        )
        dossiers_in_box = cursor.fetchall()
        # Get old zone name
        cursor.execute(
            "SELECT r.nom_zone FROM archivage_emplacements e JOIN archivage_rayonnages r ON e.id_rayonnage = r.id WHERE e.id = %s",
            (old_emplacement_id,),
        )
        old_zone_row = cursor.fetchone()
        old_zone_name = old_zone_row["nom_zone"] if old_zone_row else None
        user_id = g.user["id_personnel"] if g.user else None
        for d in dossiers_in_box:
            log_historique(
                d["id"],
                "DEPLACEMENT_ZONE",
                user_id,
                cursor,
                zone_avant=old_zone_name,
                zone_apres=target_zone,
                commentaire=f"Transfert de zone automatique",
            )

        conn.commit()
        return jsonify(
            {
                "success": True,
                "message": f"Boîte transférée vers la zone {target_zone} avec succès.",
            }
        )

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


# ==============================================================================
# GESTION DES BOÎTES & ÉTIQUETTES (QR CODE)
# ==============================================================================


@app.route("/archivage/boites")
@login_required
@handle_errors()
def archivage_boites_list():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    search_query = request.args.get("q", "").strip()
    id_medecin = request.args.get("medecin", "all")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Build query
        base_query = """
            FROM archivage_boites b
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            LEFT JOIN doctors m ON b.id_medecin = m.id
            LEFT JOIN specialty s ON m.id_specialty = s.id_specialty
            LEFT JOIN archivage_emplacements e ON b.id_emplacement = e.id
            LEFT JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE 1=1
        """
        params = []

        if search_query:
            base_query += " AND (b.numero_archive LIKE %s OR CONCAT(m.first_name, ' ', COALESCE(m.last_name, '')) LIKE %s)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])

        if id_medecin != "all":
            base_query += " AND b.id_medecin = %s"
            params.append(id_medecin)

        # Count total
        cursor.execute(f"SELECT COUNT(*) as total {base_query}", params)
        total_records = cursor.fetchone()["total"]
        total_pages = (total_records + per_page - 1) // per_page
        # Fetch data
        query = f"""
            SELECT b.*, 
                   CONCAT(m.first_name, ' ', COALESCE(m.last_name, '')) as doctor_name, 
                   s.name_specialty as specialite_nom,
                   r.nom_zone, r.code_etagere, e.colonne_x, e.ligne_y,
                   ROUND((b.epaisseur_actuelle_mm / NULLIF(t.epaisseur_max_mm, 0)) * 100) as remplissage_pct,
                   (SELECT COUNT(*) FROM archivage_dossiers WHERE id_boite = b.id) as nb_dossiers
            {base_query}
            ORDER BY b.id DESC
            LIMIT %s OFFSET %s
        """
        fetch_params = params + [per_page, offset]
        cursor.execute(query, fetch_params)
        boites = cursor.fetchall()

        # Fetch filter options
        cursor.execute(
            "SELECT id as id, CONCAT(first_name, ' ', COALESCE(last_name, '')) as titre FROM doctors ORDER BY first_name"
        )
        doctors = cursor.fetchall()

    finally:
        conn.close()

    return render_template(
        "archivage/boites_list.html",
        boites=boites,
        page=page,
        total_pages=total_pages,
        total_records=total_records,
        doctors=doctors,
        filters={"q": search_query, "medecin": id_medecin},
    )


@app.route("/archivage/boite/detail/<string:numero_archive>")
@handle_errors()
def archivage_boite_detail(numero_archive):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Fetch Boite Details
        cursor.execute(
            """
            SELECT b.*, CONCAT(m.first_name, ' ', COALESCE(m.last_name, '')) as doctor_name, s.name_specialty as specialite_nom,
                   r.nom_zone, r.code_etagere, e.colonne_x, e.ligne_y,
                   ROUND((b.epaisseur_actuelle_mm / NULLIF(t.epaisseur_max_mm, 0)) * 100) as remplissage_pct
            FROM archivage_boites b
            LEFT JOIN archivage_types_boites t ON b.id_type_boite = t.id
            LEFT JOIN doctors m ON b.id_medecin = m.id
            LEFT JOIN specialty s ON m.id_specialty = s.id_specialty
            LEFT JOIN archivage_emplacements e ON b.id_emplacement = e.id
            LEFT JOIN archivage_rayonnages r ON e.id_rayonnage = r.id
            WHERE b.numero_archive = %s
        """,
            (numero_archive,),
        )
        boite = cursor.fetchone()

        if not boite:
            flash("Boîte introuvable.", "error")
            return redirect(url_for("archivage_index"))

        # Fetch all dossiers in this box
        query_dossiers = """
            SELECT 
                d.id as id_archive,
                d.source_module, 
                d.id_source, 
                d.nom_patient, 
                d.id_patient_his, 
                d.date_archivage as date_acte, 
                d.statut,
                b.numero_archive,
                s.motif as sortie_motif,
                s.date_sortie,
                s.date_retour_prevue,
                CONCAT(COALESCE(p.prenom, ''), ' ', COALESCE(p.nom, '')) as sorti_par_nom
            FROM archivage_dossiers d 
            JOIN archivage_boites b ON d.id_boite = b.id 
            LEFT JOIN archivage_dossiers_sorties s ON d.id = s.id_dossier AND s.date_retour IS NULL
            LEFT JOIN personnel p ON s.sorti_par = p.id_personnel
            WHERE b.id = %s 
            ORDER BY d.date_archivage DESC 
        """
        cursor.execute(query_dossiers, (boite["id"],))
        dossiers = cursor.fetchall()

    finally:
        conn.close()

    return render_template(
        "archivage/boite_detail.html", boite=boite, dossiers=dossiers
    )
