import math

import pymysql
from flask import flash, g, jsonify, redirect, render_template, request, url_for

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required

# ==================== CONSTANTES ====================
PRIX_BLOC_ORTHO = 30000  # Orthopédie
PRIX_BLOC_AUTRE = 25000  # Autres spécialités
PRIX_SUPPLEMENT_30MIN = 5000  # Pour chaque 30 min après 90 min
PRIX_NUIT = 12000  # Par nuit


def calcul_prix_bloc(duree_min, id_specialty):
    """
    Calcule le prix du bloc opératoire selon la durée et la spécialité

    Args:
        duree_min: Durée en minutes
        id_specialty: ID de la spécialité

    Returns:
        dict avec prix_base, prix_supplement, prix_total
    """
    if not duree_min or duree_min <= 0:
        return {"prix_base": 0, "prix_supplement": 0, "prix_total": 0}

    # Déterminer le prix de base selon la spécialité
    # Supposons que id_specialty pour orthopédie = 1 ou contient "ortho"
    # Adapter selon votre configuration réelle
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT name_specialty FROM specialty WHERE id_specialty = %s", (id_specialty,)
    )
    specialty = cursor.fetchone()
    cursor.close()
    connection.close()

    is_ortho = specialty and "ortho" in specialty["name_specialty"].lower()
    prix_base = PRIX_BLOC_ORTHO if is_ortho else PRIX_BLOC_AUTRE

    prix_supplement = 0
    if duree_min > 90:
        # Nombre de tranches de 30 min au-delà de 90 min
        duree_supplement = duree_min - 90
        nb_tranches = math.ceil(duree_supplement / 30)
        prix_supplement = nb_tranches * PRIX_SUPPLEMENT_30MIN

    return {
        "prix_base": prix_base,
        "prix_supplement": prix_supplement,
        "prix_total": prix_base + prix_supplement,
        "is_ortho": is_ortho,
    }


def calcul_prix_nuits(nbr_nuit):
    """Calcule le prix total des nuits"""
    if not nbr_nuit or nbr_nuit <= 0:
        return 0
    return nbr_nuit * PRIX_NUIT


@app.route("/forfait", methods=["GET", "POST"])
@login_required
@handle_errors()
def forfait():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT f.*, s.name_specialty
        FROM location_bloc_forfait_actes f
        LEFT JOIN specialty s ON f.id_specialty = s.id_specialty
        ORDER BY f.name_forfait DESC
    """
    )
    forfaits = cursor.fetchall()

    # Compter les produits et actes pour chaque forfait
    for forfait in forfaits:
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM location_bloc_forfait_actes_produits
            WHERE id_forfait = %s
        """,
            (forfait["id_forfait"],),
        )
        forfait["nb_produits"] = cursor.fetchone()["count"]

        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM location_bloc_forfait_actes_inclus
            WHERE id_forfait = %s
        """,
            (forfait["id_forfait"],),
        )
        forfait["nb_actes"] = cursor.fetchone()["count"]

    cursor.execute("SELECT * FROM specialty ORDER BY name_specialty")
    specialtys = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/forfait_admin.html",
        title="Gestion des Forfaits",
        forfaits=forfaits,
        specialtys=specialtys,
        user=g.user,
    )


@app.route("/forfait/<int:id_forfait>/configure", methods=["GET"])
@login_required
@handle_errors()
def configure_forfait(id_forfait):
    """Page de configuration d'un forfait"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer le forfait
    cursor.execute(
        """
        SELECT f.*, s.name_specialty
        FROM location_bloc_forfait_actes f
        LEFT JOIN specialty s ON f.id_specialty = s.id_specialty
        WHERE f.id_forfait = %s
    """,
        (id_forfait,),
    )
    forfait = cursor.fetchone()

    if not forfait:
        flash("Forfait introuvable", "danger")
        return redirect(url_for("forfait"))

    # Produits inclus avec leurs prix
    cursor.execute(
        """
        SELECT p.id_produit, p.description, p.prix, fp.qte,
               (p.prix * fp.qte) as total_produit
        FROM location_bloc_forfait_actes_produits fp
        INNER JOIN produits p ON fp.id_produit = p.id_produit
        WHERE fp.id_forfait = %s
        ORDER BY p.description
    """,
        (id_forfait,),
    )
    produits_inclus = cursor.fetchall()

    # Actes inclus
    cursor.execute(
        """
        SELECT a.id_acte, a.nom_acte, a.prix
        FROM location_bloc_forfait_actes_inclus fa
        INNER JOIN actes_supplement a ON fa.id_acte = a.id_acte
        WHERE fa.id_forfait = %s
        ORDER BY a.nom_acte
    """,
        (id_forfait,),
    )
    actes_inclus = cursor.fetchall()

    # Listes disponibles
    cursor.execute("SELECT * FROM produits WHERE est_actif = 1 ORDER BY description")
    produits = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM actes_supplement WHERE est_actif = 1 ORDER BY nom_acte"
    )
    actes = cursor.fetchall()

    cursor.execute("SELECT * FROM specialty ORDER BY name_specialty")
    specialtys = cursor.fetchall()

    cursor.close()
    connection.close()

    # ==================== CALCULS ====================
    # Total produits
    total_produits = sum(float(p.get("total_produit", 0) or 0) for p in produits_inclus)

    # Total actes
    total_actes = sum(float(a.get("prix", 0) or 0) for a in actes_inclus)

    # Prix bloc opératoire
    duree = forfait.get("duree_forfait")
    prix_bloc_dict = calcul_prix_bloc(duree, forfait.get("id_specialty"))
    prix_bloc = prix_bloc_dict["prix_total"]

    # Prix nuits
    nbr_nuit = forfait.get("nbr_nuit")
    prix_nuits = calcul_prix_nuits(nbr_nuit)

    # Total calculé
    total_calcule = total_produits + total_actes + prix_bloc + prix_nuits

    # Prix proposé par l'admin
    prix_admin = float(forfait.get("prix_forfait", 0) or 0)

    # Différence
    difference = prix_admin - total_calcule

    return render_template(
        "admin/forfait_configure.html",
        title=f"Configuration - {forfait['name_forfait']}",
        forfait=forfait,
        produits_inclus=produits_inclus,
        actes_inclus=actes_inclus,
        produits=produits,
        actes=actes,
        specialtys=specialtys,
        total_produits=total_produits,
        total_actes=total_actes,
        prix_bloc=prix_bloc,
        prix_bloc_base=prix_bloc_dict["prix_base"],
        prix_bloc_supplement=prix_bloc_dict["prix_supplement"],
        is_ortho=prix_bloc_dict["is_ortho"],
        prix_nuits=prix_nuits,
        total_calcule=total_calcule,
        prix_admin=prix_admin,
        difference=difference,
        # Constantes
        PRIX_BLOC_ORTHO=PRIX_BLOC_ORTHO,
        PRIX_BLOC_AUTRE=PRIX_BLOC_AUTRE,
        PRIX_SUPPLEMENT_30MIN=PRIX_SUPPLEMENT_30MIN,
        PRIX_NUIT=PRIX_NUIT,
    )


@app.route("/add_forfait", methods=["POST"])
@login_required
@handle_errors()
def add_forfait():
    name_forfait = request.form.get("name_forfait", "").strip()
    id_specialty = request.form.get("specialty_forfait")
    duree_forfait = request.form.get("duree_forfait") or None
    nbr_nuit = request.form.get("nbr_nuit") or None
    prix_forfait = request.form.get("prix_forfait")

    if not name_forfait or not id_specialty or not prix_forfait:
        flash("Veuillez remplir tous les champs obligatoires", "warning")
        return redirect(url_for("forfait"))

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql_forfait = """
            INSERT INTO location_bloc_forfait_actes 
            (name_forfait, id_specialty, duree_forfait, nbr_nuit, prix_forfait)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(
            sql_forfait,
            (name_forfait, id_specialty, duree_forfait, nbr_nuit, prix_forfait),
        )
        id_forfait = cursor.lastrowid
        connection.commit()

        flash("Forfait ajouté avec succès", "success")
        # Rediriger vers la page de configuration
        return redirect(url_for("configure_forfait", id_forfait=id_forfait))
    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur lors de l'ajout du forfait : {str(e)}", "danger")
        return redirect(url_for("forfait"))
    finally:
        cursor.close()
        connection.close()


@app.route("/update_forfait", methods=["POST"])
@login_required
@handle_errors()
def update_forfait():
    id_forfait = request.form.get("id_forfait")
    name_forfait = request.form.get("name_forfait", "").strip()
    id_specialty = request.form.get("specialty_forfait")
    duree_forfait = request.form.get("duree_forfait") or None
    nbr_nuit = request.form.get("nbr_nuit") or None
    prix_forfait = request.form.get("prix_forfait")

    if not id_forfait or not name_forfait or not id_specialty or not prix_forfait:
        flash("Veuillez remplir tous les champs obligatoires", "warning")
        return redirect(url_for("configure_forfait", id_forfait=id_forfait))

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        sql_update = """
            UPDATE location_bloc_forfait_actes
            SET name_forfait = %s, id_specialty = %s, duree_forfait = %s, 
                nbr_nuit = %s, prix_forfait = %s
            WHERE id_forfait = %s
        """
        cursor.execute(
            sql_update,
            (
                name_forfait,
                id_specialty,
                duree_forfait,
                nbr_nuit,
                prix_forfait,
                id_forfait,
            ),
        )
        connection.commit()

        flash("Forfait mis à jour avec succès", "success")
    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur lors de la mise à jour : {str(e)}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("configure_forfait", id_forfait=id_forfait))


@app.route("/delete_forfait/<int:id_forfait>", methods=["POST"])
@login_required
@handle_errors()
def delete_forfait(id_forfait):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier si le forfait existe
        cursor.execute(
            "SELECT id_forfait FROM location_bloc_forfait_actes WHERE id_forfait = %s",
            (id_forfait,),
        )
        if not cursor.fetchone():
            flash("Forfait introuvable", "warning")
            return redirect(url_for("forfait"))

        # Supprimer le forfait (les éléments liés seront supprimés par CASCADE)
        cursor.execute(
            "DELETE FROM location_bloc_forfait_actes WHERE id_forfait = %s",
            (id_forfait,),
        )
        connection.commit()

        flash("Forfait supprimé avec succès", "success")
    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur lors de la suppression : {str(e)}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("forfait"))


# ==================== ROUTES AJAX POUR LES PRODUITS ====================


@app.route("/api/forfait/<int:id_forfait>/produit", methods=["POST"])
@login_required
@handle_errors()
def add_produit_to_forfait_ajax(id_forfait):
    """Ajoute un produit à un forfait via AJAX"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "message": "Aucune donnée reçue"}), 400

        id_produit = data.get("id_produit")
        qte = data.get("qte", 1)

        if not id_produit or not qte:
            return jsonify({"success": False, "message": "Données invalides"}), 400

        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier si le forfait existe
        cursor.execute(
            "SELECT id_forfait FROM location_bloc_forfait_actes WHERE id_forfait = %s",
            (id_forfait,),
        )
        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({"success": False, "message": "Forfait introuvable"}), 404

        # Vérifier si le produit existe ET récupérer son prix
        cursor.execute(
            """
            SELECT id_produit, description, prix 
            FROM produits 
            WHERE id_produit = %s
        """,
            (id_produit,),
        )
        produit = cursor.fetchone()

        if not produit:
            cursor.close()
            connection.close()
            return jsonify({"success": False, "message": "Produit introuvable"}), 404

        # Vérifier si le produit est déjà inclus
        cursor.execute(
            """
            SELECT id FROM location_bloc_forfait_actes_produits 
            WHERE id_forfait = %s AND id_produit = %s
        """,
            (id_forfait, id_produit),
        )

        if cursor.fetchone():
            cursor.close()
            connection.close()
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Ce produit est déjà inclus dans ce forfait",
                    }
                ),
                400,
            )

        # Ajouter le produit
        cursor.execute(
            """
            INSERT INTO location_bloc_forfait_actes_produits (id_forfait, id_produit, qte)
            VALUES (%s, %s, %s)
        """,
            (id_forfait, id_produit, qte),
        )

        connection.commit()
        cursor.close()
        connection.close()

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Produit ajouté avec succès",
                    "produit": {
                        "id_produit": produit["id_produit"],
                        "description": produit["description"],
                        "prix": float(produit["prix"]) if produit["prix"] else 0,
                        "qte": qte,
                    },
                }
            ),
            200,
        )

    except pymysql.MySQLError as e:
        if "connection" in locals():
            connection.rollback()
            cursor.close()
            connection.close()
        return (
            jsonify(
                {"success": False, "message": f"Erreur base de données : {str(e)}"}
            ),
            500,
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur serveur : {str(e)}"}), 500


@app.route("/api/forfait/<int:id_forfait>/produit/<int:id_produit>", methods=["DELETE"])
@login_required
@handle_errors()
def remove_produit_from_forfait_ajax(id_forfait, id_produit):
    """Supprime un produit d'un forfait via AJAX"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier si l'association existe
        cursor.execute(
            """
            SELECT id FROM location_bloc_forfait_actes_produits 
            WHERE id_forfait = %s AND id_produit = %s
        """,
            (id_forfait, id_produit),
        )

        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return (
                jsonify({"success": False, "message": "Association introuvable"}),
                404,
            )

        # Supprimer l'association
        cursor.execute(
            """
            DELETE FROM location_bloc_forfait_actes_produits 
            WHERE id_forfait = %s AND id_produit = %s
        """,
            (id_forfait, id_produit),
        )

        connection.commit()
        cursor.close()
        connection.close()

        return (
            jsonify({"success": True, "message": "Produit supprimé avec succès"}),
            200,
        )

    except pymysql.MySQLError as e:
        if "connection" in locals():
            connection.rollback()
            cursor.close()
            connection.close()
        return (
            jsonify(
                {"success": False, "message": f"Erreur base de données : {str(e)}"}
            ),
            500,
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur serveur : {str(e)}"}), 500


# ==================== ROUTES AJAX POUR LES ACTES ====================


@app.route("/api/forfait/<int:id_forfait>/acte", methods=["POST"])
@login_required
@handle_errors()
def add_acte_to_forfait_ajax(id_forfait):
    """Ajoute un acte à un forfait via AJAX"""
    try:
        data = request.get_json()
        id_acte = data.get("id_acte")

        if not id_acte:
            return jsonify({"success": False, "message": "Données invalides"}), 400

        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier si le forfait existe
        cursor.execute(
            "SELECT id_forfait FROM location_bloc_forfait_actes WHERE id_forfait = %s",
            (id_forfait,),
        )
        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return jsonify({"success": False, "message": "Forfait introuvable"}), 404

        # Vérifier si l'acte existe
        cursor.execute(
            """
            SELECT id_acte, nom_acte, prix 
            FROM actes_supplement 
            WHERE id_acte = %s
        """,
            (id_acte,),
        )
        acte = cursor.fetchone()

        if not acte:
            cursor.close()
            connection.close()
            return jsonify({"success": False, "message": "Acte introuvable"}), 404

        # Vérifier si l'acte est déjà inclus
        cursor.execute(
            """
            SELECT id FROM location_bloc_forfait_actes_inclus 
            WHERE id_forfait = %s AND id_acte = %s
        """,
            (id_forfait, id_acte),
        )

        if cursor.fetchone():
            cursor.close()
            connection.close()
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Cet acte est déjà inclus dans ce forfait",
                    }
                ),
                400,
            )

        # Ajouter l'acte
        cursor.execute(
            """
            INSERT INTO location_bloc_forfait_actes_inclus (id_forfait, id_acte)
            VALUES (%s, %s)
        """,
            (id_forfait, id_acte),
        )

        connection.commit()
        cursor.close()
        connection.close()

        return (
            jsonify(
                {
                    "success": True,
                    "message": "Acte ajouté avec succès",
                    "acte": {
                        "id_acte": acte["id_acte"],
                        "nom_acte": acte["nom_acte"],
                        "prix": float(acte["prix"]) if acte["prix"] else 0,
                    },
                }
            ),
            200,
        )

    except pymysql.MySQLError as e:
        if "connection" in locals():
            connection.rollback()
            cursor.close()
            connection.close()
        return (
            jsonify(
                {"success": False, "message": f"Erreur base de données : {str(e)}"}
            ),
            500,
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur serveur : {str(e)}"}), 500


@app.route("/api/forfait/<int:id_forfait>/acte/<int:id_acte>", methods=["DELETE"])
@login_required
@handle_errors()
def remove_acte_from_forfait_ajax(id_forfait, id_acte):
    """Supprime un acte d'un forfait via AJAX"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier si l'association existe
        cursor.execute(
            """
            SELECT id FROM location_bloc_forfait_actes_inclus 
            WHERE id_forfait = %s AND id_acte = %s
        """,
            (id_forfait, id_acte),
        )

        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return (
                jsonify({"success": False, "message": "Association introuvable"}),
                404,
            )

        # Supprimer l'association
        cursor.execute(
            """
            DELETE FROM location_bloc_forfait_actes_inclus 
            WHERE id_forfait = %s AND id_acte = %s
        """,
            (id_forfait, id_acte),
        )

        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({"success": True, "message": "Acte supprimé avec succès"}), 200

    except pymysql.MySQLError as e:
        if "connection" in locals():
            connection.rollback()
            cursor.close()
            connection.close()
        return (
            jsonify(
                {"success": False, "message": f"Erreur base de données : {str(e)}"}
            ),
            500,
        )
    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur serveur : {str(e)}"}), 500


@app.route("/duplicate_forfait/<int:id_forfait>", methods=["POST"])
@login_required
@handle_errors()
def duplicate_forfait(id_forfait):
    """Duplique un forfait avec tous ses produits et actes"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Récupérer le forfait original
        cursor.execute(
            """
            SELECT name_forfait, id_specialty, duree_forfait, nbr_nuit, prix_forfait
            FROM location_bloc_forfait_actes
            WHERE id_forfait = %s
                       """,
            (id_forfait,),
        )

        forfait_original = cursor.fetchone()

        if not forfait_original:
            flash("Forfait introuvable", "warning")
            return redirect(url_for("forfait"))

        # Créer le nouveau nom avec "(Copie)"
        new_name = f"{forfait_original[ 'name_forfait' ]} (Copie)"

        # Vérifier si le nom existe déjà et ajouter un numéro si nécessaire
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM location_bloc_forfait_actes
            WHERE name_forfait LIKE %s
                       """,
            (f"{forfait_original[ 'name_forfait' ]} (Copie%",),
        )

        count = cursor.fetchone()["count"]
        if count > 0:
            new_name = f"{forfait_original[ 'name_forfait' ]} (Copie {count + 1})"

        # Insérer le nouveau forfait
        cursor.execute(
            """
            INSERT INTO location_bloc_forfait_actes
                (name_forfait, id_specialty, duree_forfait, nbr_nuit, prix_forfait)
            VALUES (%s, %s, %s, %s, %s)
                       """,
            (
                new_name,
                forfait_original["id_specialty"],
                forfait_original["duree_forfait"],
                forfait_original["nbr_nuit"],
                forfait_original["prix_forfait"],
            ),
        )

        new_forfait_id = cursor.lastrowid

        # Copier les produits associés
        cursor.execute(
            """
            INSERT INTO location_bloc_forfait_actes_produits (id_forfait, id_produit, qte)
            SELECT %s, id_produit, qte
            FROM location_bloc_forfait_actes_produits
            WHERE id_forfait = %s
                       """,
            (new_forfait_id, id_forfait),
        )

        nb_produits = cursor.rowcount

        # Copier les actes associés
        cursor.execute(
            """
            INSERT INTO location_bloc_forfait_actes_inclus (id_forfait, id_acte)
            SELECT %s, id_acte
            FROM location_bloc_forfait_actes_inclus
            WHERE id_forfait = %s
                       """,
            (new_forfait_id, id_forfait),
        )

        nb_actes = cursor.rowcount

        connection.commit()

        flash(
            f"Forfait dupliqué avec succès : {nb_produits} produits et {nb_actes} actes copiés",
            "success",
        )

        # Rediriger vers la page de configuration du nouveau forfait
        return redirect(url_for("configure_forfait", id_forfait=new_forfait_id))

    except pymysql.MySQLError as e:
        connection.rollback()
        flash(f"Erreur lors de la duplication : {str( e )}", "danger")
        return redirect(url_for("forfait"))
    finally:
        cursor.close()
        connection.close()


@app.route("/forfait/<int:id_forfait>/print", methods=["GET"])
@login_required
@handle_errors()
def print_forfait(id_forfait):
    """Page d'impression d'un forfait (sans détail des prix)"""
    from datetime import datetime

    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupérer le forfait
    cursor.execute(
        """
        SELECT f.*, s.name_specialty
        FROM location_bloc_forfait_actes f
        LEFT JOIN specialty s ON f.id_specialty = s.id_specialty
        WHERE f.id_forfait = %s
    """,
        (id_forfait,),
    )
    forfait = cursor.fetchone()

    if not forfait:
        flash("Forfait introuvable", "danger")
        return redirect(url_for("forfait"))

    # Produits inclus (juste quantité, pas de prix unitaires affichés)
    cursor.execute(
        """
        SELECT p.description, fp.qte
        FROM location_bloc_forfait_actes_produits fp
        INNER JOIN produits p ON fp.id_produit = p.id_produit
        WHERE fp.id_forfait = %s
        ORDER BY p.description
    """,
        (id_forfait,),
    )
    produits_inclus = cursor.fetchall()

    # Actes inclus
    cursor.execute(
        """
        SELECT a.nom_acte
        FROM location_bloc_forfait_actes_inclus fa
        INNER JOIN actes_supplement a ON fa.id_acte = a.id_acte
        WHERE fa.id_forfait = %s
        ORDER BY a.nom_acte
    """,
        (id_forfait,),
    )
    actes_inclus = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "admin/forfait_print.html",
        forfait=forfait,
        produits_inclus=produits_inclus,
        actes_inclus=actes_inclus,
        today=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
