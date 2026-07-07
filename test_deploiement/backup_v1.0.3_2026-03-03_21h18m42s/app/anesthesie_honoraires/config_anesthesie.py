# Routes pour la configuration de l'anesthésie
from flask import request, render_template, jsonify

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


@app.route('/anesthesie/configuration')
@login_required
@handle_errors()

def anesthesie_configuration():
    """Page de configuration de l'anesthésie"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupération des actes d'anesthésie avec tarif forfaitaire
    cursor.execute(
        """
        SELECT id_acte_anesthesie,
               nom_acte,
               description,
               tarif_forfaitaire,
               est_actif,
               date_creation
        FROM anesthesie_type_acte
        ORDER BY nom_acte
        """
    )
    actes = cursor.fetchall()

    # Récupération du personnel
    cursor.execute(
        """
        SELECT p.id_personnel_anesthesie,
               p.nom,
               p.prenom,
               CONCAT(p.prenom, ' ', p.nom) as nom_complet,
               p.id_type_intervenant,
               ti.nom_type,
               p.est_actif,
               p.date_creation
        FROM anesthesie_personnel p
        JOIN anesthesie_intervenant_type ti ON p.id_type_intervenant = ti.id_type_intervenant
        ORDER BY ti.nom_type, p.nom, p.prenom
        """
    )
    personnel = cursor.fetchall()

    # Récupération des types d'intervenants
    cursor.execute(
        """
        SELECT id_type_intervenant, nom_type, description, est_actif
        FROM anesthesie_intervenant_type
        ORDER BY nom_type
        """
    )
    types_intervenants = cursor.fetchall()

    # Récupération des tarifs (honoraires intervenants uniquement)
    cursor.execute(
        """
        SELECT t.id_tarif,
               t.id_acte_anesthesie,
               aa.nom_acte,
               t.id_type_intervenant,
               ti.nom_type,
               t.honoraires_base,
               t.supplement_30min,
               t.duree_avant_supplement,
               t.est_actif
        FROM anesthesie_tarifs t
        JOIN anesthesie_type_acte aa ON t.id_acte_anesthesie = aa.id_acte_anesthesie
        JOIN anesthesie_intervenant_type ti ON t.id_type_intervenant = ti.id_type_intervenant
        ORDER BY aa.nom_acte, ti.nom_type
        """
    )
    tarifs = cursor.fetchall()

    return render_template(
        'anesthesie_honoraires/config_anesthesie.html',
        actes=actes,
        personnel=personnel,
        types_intervenants=types_intervenants,
        tarifs=tarifs,
        title="Configuration Anesthésie",
    )


# ========================================================================
# ROUTES CRUD POUR LES ACTES D'ANESTHÉSIE
# ========================================================================

@app.route('/api/anesthesie/actes', methods=['POST'])
@login_required

def api_create_acte_anesthesie():
    """Créer un nouvel acte d'anesthésie"""
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO anesthesie_type_acte
                (nom_acte, description, tarif_forfaitaire)
            VALUES (%s, %s, %s)
            """, (
                data['nom_acte'],
                data.get('description'),
                data.get('tarif_forfaitaire')
            )
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Acte créé avec succès',
                'id': cursor.lastrowid
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/anesthesie/actes/<int:id_acte>', methods=['PUT'])
@login_required

def api_update_acte_anesthesie(id_acte):
    """Modifier un acte d'anesthésie"""
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE anesthesie_type_acte
            SET nom_acte               = %s,
                description            = %s,
                tarif_forfaitaire      = %s
            WHERE id_acte_anesthesie = %s
            """, (
                data['nom_acte'],
                data.get('description'),
                data.get('tarif_forfaitaire'),
                id_acte
            )
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Acte modifié avec succès'
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/anesthesie/actes/<int:id_acte>/toggle', methods=['POST'])
@login_required

def api_toggle_acte_anesthesie(id_acte):
    """Activer/Désactiver un acte d'anesthésie"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE anesthesie_type_acte
            SET est_actif = NOT est_actif
            WHERE id_acte_anesthesie = %s
            """, (id_acte,)
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Statut modifié avec succès'
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


# ========================================================================
# ROUTES CRUD POUR LE PERSONNEL
# ========================================================================

@app.route('/api/anesthesie/personnel', methods=['POST'])
@login_required

def api_create_personnel_anesthesie():
    """Créer un nouveau personnel d'anesthésie"""
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO anesthesie_personnel
                (nom, prenom, id_type_intervenant)
            VALUES (%s, %s, %s)
            """, (
                data['nom'],
                data['prenom'],
                data['id_type_intervenant'],
            )
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Personnel créé avec succès',
                'id': cursor.lastrowid
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/anesthesie/personnel/<int:id_personnel>', methods=['PUT'])
@login_required

def api_update_personnel_anesthesie(id_personnel):
    """Modifier un personnel d'anesthésie"""
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE anesthesie_personnel
            SET nom                 = %s,
                prenom              = %s,
                id_type_intervenant = %s
            WHERE id_personnel_anesthesie = %s
            """, (
                data['nom'],
                data['prenom'],
                data['id_type_intervenant'],
                id_personnel
            )
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Personnel modifié avec succès'
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/anesthesie/personnel/<int:id_personnel>/toggle', methods=['POST'])
@login_required

def api_toggle_personnel_anesthesie(id_personnel):
    """Activer/Désactiver un personnel d'anesthésie"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE anesthesie_personnel
            SET est_actif = NOT est_actif
            WHERE id_personnel_anesthesie = %s
            """, (id_personnel,)
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Statut modifié avec succès'
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


# ========================================================================
# ROUTES CRUD POUR LES TARIFS (HONORAIRES INTERVENANTS)
# ========================================================================

@app.route('/api/anesthesie/tarifs', methods=['POST'])
@login_required

def api_create_tarif_anesthesie():
    """Créer un nouveau tarif d'honoraires intervenant"""
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO anesthesie_tarifs
            (id_acte_anesthesie, id_type_intervenant, honoraires_base,
             supplement_30min, duree_avant_supplement)
            VALUES (%s, %s, %s, %s, %s)
            """, (
                data['id_acte_anesthesie'],
                data['id_type_intervenant'],
                data['honoraires_base'],
                data.get('supplement_30min'),
                data.get('duree_avant_supplement')
            )
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Tarif créé avec succès',
                'id': cursor.lastrowid
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/anesthesie/tarifs/<int:id_tarif>', methods=['PUT'])
@login_required

def api_update_tarif_anesthesie(id_tarif):
    """Modifier un tarif d'honoraires intervenant"""
    data = request.get_json()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE anesthesie_tarifs
            SET honoraires_base        = %s,
                supplement_30min       = %s,
                duree_avant_supplement = %s
            WHERE id_tarif = %s
            """, (
                data['honoraires_base'],
                data.get('supplement_30min'),
                data.get('duree_avant_supplement'),
                id_tarif
            )
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Tarif modifié avec succès'
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/anesthesie/tarifs/<int:id_tarif>/toggle', methods=['POST'])
@login_required

def api_toggle_tarif_anesthesie(id_tarif):
    """Activer/Désactiver un tarif d'anesthésie"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE anesthesie_tarifs
            SET est_actif = NOT est_actif
            WHERE id_tarif = %s
            """, (id_tarif,)
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Statut modifié avec succès'
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/anesthesie/tarifs/<int:id_tarif>', methods=['DELETE'])
@login_required

def api_delete_tarif_anesthesie(id_tarif):
    """Supprimer un tarif d'anesthésie"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM anesthesie_tarifs
            WHERE id_tarif = %s
            """, (id_tarif,)
        )

        connection.commit()

        return jsonify(
            {
                'success': True,
                'message': 'Tarif supprimé avec succès'
            }
        )
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400