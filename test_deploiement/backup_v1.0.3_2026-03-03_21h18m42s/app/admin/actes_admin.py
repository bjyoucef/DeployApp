# app/prestation_location_bloc/actes_admin.py
import pymysql
from flask import flash, g, redirect, render_template, request, url_for

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


@app.route("/actes_admin", methods=["GET"])
@login_required
@handle_errors()
def actes_admin():
    """Page d'administration des actes"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer tous les actes
    cursor.execute(
        """
        SELECT a.*,
               (SELECT COUNT(*) FROM location_bloc_forfait_actes_inclus WHERE id_acte = a.id_acte) as nbr_forfaits
        FROM actes_supplement a
        ORDER BY a.nom_acte
        """
    )
    actes = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/actes_admin.html",
        title="Gestion des Actes",
        actes=actes,
    )


@app.route("/add_acte_location", methods=["POST"])
@login_required
@handle_errors()
def add_acte_location():
    """Ajouter un nouveau acte"""
    nom_acte = request.form["nom_acte"].strip()
    prix = request.form.get("prix", 0)

    if not nom_acte:
        flash("Le nom de l'acte est obligatoire", "danger")
        return redirect(url_for("actes_admin"))

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
              INSERT INTO actes_supplement (nom_acte, prix, est_actif, created_by)
              VALUES (%s, %s, 1, %s) \
              """
        cursor.execute(sql, (nom_acte, prix, g.user["id_personnel"]))

        connection.commit()
        flash(f'Acte "{nom_acte}" ajouté avec succès', "success")

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur lors de l'ajout de l'acte : {e}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("actes_admin"))


@app.route("/update_acte_location", methods=["POST"])
@login_required
@handle_errors()
def update_acte_location():
    """Mettre à jour un acte existant"""
    id_acte = request.form["id_acte"]
    nom_acte = request.form["nom_acte"].strip()
    prix = request.form.get("prix", 0)
    est_actif = 1 if request.form.get("est_actif") == "on" else 0

    if not nom_acte:
        flash("Le nom de l'acte est obligatoire", "danger")
        return redirect(url_for("actes_admin"))

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
              UPDATE actes_supplement
              SET nom_acte  = %s, \
                  prix      = %s, \
                  est_actif = %s
              WHERE id_acte = %s \
              """
        cursor.execute(sql, (nom_acte, prix, est_actif, id_acte))

        connection.commit()
        flash(f'Acte "{nom_acte}" mis à jour avec succès', "success")

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur lors de la mise à jour : {e}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("actes_admin"))


@app.route("/delete_acte_location/<int:id_acte>", methods=["POST"])
@login_required
@handle_errors()
def delete_acte_location(id_acte):
    """Supprimer un acte"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier s'il y a des dossiers liés à cet acte
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM location_bloc_dossier_patient_actes
            WHERE id_acte = %s
            """,
            (id_acte,),
        )
        result = cursor.fetchone()

        if result["count"] > 0:
            flash(
                "Impossible de supprimer cet acte car il est utilisé dans des dossiers",
                "warning",
            )
        else:
            # Vérifier le nom de l'acte avant suppression
            cursor.execute(
                "SELECT nom_acte FROM actes_supplement WHERE id_acte = %s", (id_acte,)
            )
            acte = cursor.fetchone()

            sql = "DELETE FROM actes_supplement WHERE id_acte = %s"
            cursor.execute(sql, (id_acte,))
            connection.commit()
            flash(f'Acte "{acte[ "nom_acte" ]}" supprimé avec succès', "success")

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur : {e}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("actes_admin"))


@app.route("/toggle_acte_status/<int:id_acte>", methods=["POST"])
@login_required
@handle_errors()
def toggle_acte_status(id_acte):
    """Activer/désactiver un acte"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
              UPDATE actes_supplement
              SET est_actif = IF(est_actif = 1, 0, 1)
              WHERE id_acte = %s \
              """
        cursor.execute(sql, (id_acte,))
        connection.commit()
        flash("Statut de l'acte modifié avec succès", "success")

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur : {e}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("actes_admin"))


@app.route("/add_acte_to_forfait/<int:id_forfait>", methods=["POST"])
@login_required
@handle_errors()
def add_acte_to_forfait(id_forfait):
    """Ajouter un acte à un forfait"""
    id_acte = request.form["id_acte"]

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier si l'acte est déjà inclus
        sql_check = """
                    SELECT id \
                    FROM location_bloc_forfait_actes_inclus
                    WHERE id_forfait = %s \
                      AND id_acte = %s \
                    """
        cursor.execute(sql_check, (id_forfait, id_acte))

        if cursor.fetchone():
            flash("L'acte est déjà inclus dans ce forfait", "warning")
        else:
            # Ajouter l'acte
            sql_insert = """
                         INSERT INTO location_bloc_forfait_actes_inclus (id_forfait, id_acte)
                         VALUES (%s, %s) \
                         """
            cursor.execute(sql_insert, (id_forfait, id_acte))
            connection.commit()
            flash("Acte ajouté au forfait avec succès", "success")

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur : {e}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("forfait"))


@app.route("/remove_acte_from_forfait/<int:id_forfait>/<int:id_acte>", methods=["POST"])
@login_required
@handle_errors()
def remove_acte_from_forfait(id_forfait, id_acte):
    """Retirer un acte d'un forfait"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql = """
              DELETE \
              FROM location_bloc_forfait_actes_inclus
              WHERE id_forfait = %s \
                AND id_acte = %s \
              """
        cursor.execute(sql, (id_forfait, id_acte))
        connection.commit()
        flash("Acte supprimé du forfait avec succès", "success")

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur : {e}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("forfait"))
