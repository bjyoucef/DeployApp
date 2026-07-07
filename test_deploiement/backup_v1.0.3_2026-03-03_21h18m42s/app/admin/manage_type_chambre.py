# app/manage_type_chambre.py

from flask import request, render_template, jsonify
from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


# ========================================================================
# GESTION DES TYPES DE CHAMBRES
# ========================================================================

@app.route('/gestion_type_chambres')
@login_required
@handle_errors()

def gestion_type_chambres():
    """Page de gestion CRUD des types de chambres"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupération de tous les types de chambres avec statistiques
        cursor.execute(
            """
            SELECT tc.id_type_chambre,
                   tc.nom_type,
                   tc.prix_unitaire,
                   tc.est_standard,
                   tc.description,
                   tc.capacite,
                   tc.est_actif,
                   tc.created_at
            FROM type_chambre tc
            GROUP BY tc.id_type_chambre, tc.nom_type, tc.prix_unitaire, 
                     tc.est_standard, tc.description, tc.capacite, 
                     tc.est_actif, tc.created_at
            ORDER BY tc.est_actif DESC, tc.nom_type
            """
        )
        types_chambres = cursor.fetchall()

        return render_template(
            'admin/gestion_type_chambres.html',
            types_chambres=types_chambres,
            title="Gestion des Types de Chambres"
        )

    finally:
        cursor.close()
        connection.close()


@app.route('/ajouter_type_chambre', methods=['POST'])
@login_required
@handle_errors()

def ajouter_type_chambre():
    """Ajouter un type de chambre"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        nom_type = request.form.get('nom_type', '').strip()
        prix_unitaire = request.form.get('prix_unitaire', '0').strip()
        capacite = request.form.get('capacite', '1').strip()
        description = request.form.get('description', '').strip()
        est_standard = 1 if request.form.get('est_standard') == 'on' else 0
        est_actif = 1 if request.form.get('est_actif') == 'on' else 0

        # Validation
        if not nom_type:
            return jsonify({'success': False, 'error': 'Le nom du type est obligatoire'}), 400

        try:
            prix_unitaire = float(prix_unitaire)
            capacite = int(capacite)
            
            if prix_unitaire < 0:
                return jsonify({'success': False, 'error': 'Le prix ne peut pas être négatif'}), 400
            
            if capacite < 1:
                return jsonify({'success': False, 'error': 'La capacité doit être au moins 1'}), 400
                
        except ValueError:
            return jsonify({'success': False, 'error': 'Prix ou capacité invalide'}), 400

        # Vérifier si le type existe déjà
        cursor.execute(
            "SELECT id_type_chambre FROM type_chambre WHERE nom_type = %s",
            (nom_type,)
        )

        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'Un type de chambre avec ce nom existe déjà'}), 400

        # Insertion
        cursor.execute(
            """
            INSERT INTO type_chambre (nom_type, prix_unitaire, capacite, description, 
                                     est_standard, est_actif)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (nom_type, prix_unitaire, capacite, description, est_standard, est_actif)
        )

        connection.commit()

        return jsonify({
            'success': True,
            'message': f'Type de chambre "{nom_type}" ajouté avec succès'
        })

    except Exception as e:
        connection.rollback()
        app.logger.error(f'Erreur ajout type chambre: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/modifier_type_chambre/<int:id_type_chambre>', methods=['POST'])
@login_required
@handle_errors()

def modifier_type_chambre(id_type_chambre):
    """Modifier un type de chambre"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        nom_type = request.form.get('nom_type', '').strip()
        prix_unitaire = request.form.get('prix_unitaire', '0').strip()
        capacite = request.form.get('capacite', '1').strip()
        description = request.form.get('description', '').strip()
        est_standard = 1 if request.form.get('est_standard') == 'on' else 0
        est_actif = 1 if request.form.get('est_actif') == 'on' else 0

        # Validation
        if not nom_type:
            return jsonify({'success': False, 'error': 'Le nom du type est obligatoire'}), 400

        try:
            prix_unitaire = float(prix_unitaire)
            capacite = int(capacite)
            
            if prix_unitaire < 0:
                return jsonify({'success': False, 'error': 'Le prix ne peut pas être négatif'}), 400
            
            if capacite < 1:
                return jsonify({'success': False, 'error': 'La capacité doit être au moins 1'}), 400
                
        except ValueError:
            return jsonify({'success': False, 'error': 'Prix ou capacité invalide'}), 400

        # Vérifier que le type existe
        cursor.execute("SELECT id_type_chambre FROM type_chambre WHERE id_type_chambre = %s", 
                      (id_type_chambre,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Type de chambre non trouvé'}), 404

        # Vérifier si un autre type porte déjà ce nom
        cursor.execute(
            """
            SELECT id_type_chambre
            FROM type_chambre
            WHERE nom_type = %s AND id_type_chambre != %s
            """,
            (nom_type, id_type_chambre)
        )

        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'Un autre type de chambre porte déjà ce nom'}), 400

        # Mise à jour
        cursor.execute(
            """
            UPDATE type_chambre
            SET nom_type = %s,
                prix_unitaire = %s,
                capacite = %s,
                description = %s,
                est_standard = %s,
                est_actif = %s
            WHERE id_type_chambre = %s
            """,
            (nom_type, prix_unitaire, capacite, description, 
             est_standard, est_actif, id_type_chambre)
        )

        connection.commit()

        return jsonify({
            'success': True,
            'message': f'Type de chambre "{nom_type}" modifié avec succès'
        })

    except Exception as e:
        connection.rollback()
        app.logger.error(f'Erreur modification type chambre: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/get_type_chambre/<int:id_type_chambre>')
@login_required
@handle_errors()

def get_type_chambre(id_type_chambre):
    """Récupère les informations d'un type de chambre"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT id_type_chambre, nom_type, prix_unitaire, capacite, 
                   description, est_standard, est_actif
            FROM type_chambre
            WHERE id_type_chambre = %s
            """,
            (id_type_chambre,)
        )

        type_chambre = cursor.fetchone()

        if not type_chambre:
            return jsonify({'success': False, 'error': 'Type de chambre non trouvé'}), 404

        return jsonify({
            'success': True,
            'type_chambre': {
                'id_type_chambre': type_chambre['id_type_chambre'],
                'nom_type': type_chambre['nom_type'],
                'prix_unitaire': float(type_chambre['prix_unitaire']),
                'capacite': type_chambre['capacite'],
                'description': type_chambre['description'],
                'est_standard': type_chambre['est_standard'],
                'est_actif': type_chambre['est_actif']
            }
        })

    except Exception as e:
        app.logger.error(f'Erreur get_type_chambre: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/toggle_actif_type_chambre/<int:id_type_chambre>', methods=['POST'])
@login_required
@handle_errors()

def toggle_actif_type_chambre(id_type_chambre):
    """Activer/Désactiver un type de chambre"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT est_actif, nom_type FROM type_chambre WHERE id_type_chambre = %s",
            (id_type_chambre,)
        )
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'success': False, 'error': 'Type de chambre non trouvé'}), 404

        nouveau_statut = 0 if result['est_actif'] else 1
        
        cursor.execute(
            "UPDATE type_chambre SET est_actif = %s WHERE id_type_chambre = %s",
            (nouveau_statut, id_type_chambre)
        )
        
        connection.commit()

        statut_text = "activé" if nouveau_statut else "désactivé"
        return jsonify({
            'success': True,
            'message': f'Type "{result["nom_type"]}" {statut_text} avec succès',
            'est_actif': nouveau_statut
        })

    except Exception as e:
        connection.rollback()
        app.logger.error(f'Erreur toggle actif: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()
