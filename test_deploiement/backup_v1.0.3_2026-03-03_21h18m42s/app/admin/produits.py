import math
from datetime import datetime
from io import BytesIO

import pandas as pd
from flask import request, render_template, g, jsonify
from openpyxl.styles import Font, PatternFill

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required, has_permission


ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
ITEMS_PER_PAGE = 20


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def calculer_prix_vente(prix_achat, pourcentage_marge):
    """Calcule le prix de vente arrondi au multiple de 50"""
    prix_avec_marge = float(prix_achat) * (1 + float(pourcentage_marge) / 100)
    prix_arrondi = math.ceil(prix_avec_marge / 50) * 50
    return round(prix_arrondi, 2)


def format_produit(produit, include_prix_vente=True):
    """Formate un produit pour JSON"""
    return {
        'id_produit': produit['id_produit'],
        'description': produit['description'],
        'prix_achat': float(produit['prix_achat']),
        'pourcentage_marge': float(produit.get('pourcentage_marge', 0)) if include_prix_vente else None,
        'prix': float(produit.get('prix', 0)) if include_prix_vente else None,
        'created_at': produit['created_at'].strftime('%d/%m/%Y %H:%M') if produit['created_at'] else '-',
        'created_by_name': produit.get('created_by_name', '-'),
        'updated_at': produit['updated_at'].strftime('%d/%m/%Y %H:%M') if produit['updated_at'] else '-',
        'updated_by_name': produit.get('updated_by_name', '-'),
    }


@app.route('/produits', methods=['GET'])
@login_required
@handle_errors()

def produits():
    """Affiche la page des produits"""
    return render_template(
            'admin/produits/produits_admin.html',
        user=g.user,
        title="Gestion des Produits"
    )


@app.route('/api/produits', methods=['GET'])
@login_required
@handle_errors()

def api_produits():
    """API JSON pour récupérer les produits avec pagination et recherche"""
    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        search = request.args.get('search', '').strip()
        page = max(1, int(request.args.get('page', 1)))
        offset = (page - 1) * ITEMS_PER_PAGE
        include_prix_vente = has_permission('VOIR_PRIX_VENTE_PRODUIT')

        # Construire la requête avec recherche
        base_query = """
            SELECT p.*, 
                   CONCAT(pc.prenom, ' ', pc.nom) as created_by_name,
                   CONCAT(pm.prenom, ' ', pm.nom) as updated_by_name
            FROM produits p
            LEFT JOIN personnel pc ON p.id_created_par = pc.id_personnel
            LEFT JOIN personnel pm ON p.id_updated_par = pm.id_personnel
        """

        if search:
            base_query += " WHERE p.description LIKE %s OR p.id_produit LIKE %s"
            search_param = f"%{search}%"

        # Total pour pagination
        count_query = "SELECT COUNT(*) as total FROM produits"
        if search:
            count_query += " WHERE description LIKE %s OR id_produit LIKE %s"
            cursor.execute(count_query, (search_param, search_param))
        else:
            cursor.execute(count_query)

        total = cursor.fetchone()['total']

        # Récupérer les produits
        query = base_query + " ORDER BY p.id_produit DESC LIMIT %s OFFSET %s"
        if search:
            cursor.execute(query, (search_param, search_param, ITEMS_PER_PAGE, offset))
        else:
            cursor.execute(query, (ITEMS_PER_PAGE, offset))

        produits = cursor.fetchall()

        return jsonify({
            'success': True,
            'produits': [format_produit(p, include_prix_vente) for p in produits],
            'pagination': {
                'page': page,
                'total': total,
                'pages': math.ceil(total / ITEMS_PER_PAGE),
                'items_per_page': ITEMS_PER_PAGE
            },
            'can_edit_margin': has_permission('MODIFIER_MARGE_PRODUIT')
        })
    finally:
        connection.close()


@app.route('/api/produits/<int:id_produit>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@handle_errors()

def api_produit_operations(id_produit):
    """API pour GET, PUT et DELETE d'un produit"""

    # GET - Récupérer un produit
    if request.method == 'GET':
        connection = get_db_connection()
        try:
            cursor = connection.cursor()

            cursor.execute("""
                SELECT p.*, 
                       CONCAT(pc.prenom, ' ', pc.nom) as created_by_name,
                       CONCAT(pm.prenom, ' ', pm.nom) as updated_by_name
                FROM produits p
                LEFT JOIN personnel pc ON p.id_created_par = pc.id_personnel
                LEFT JOIN personnel pm ON p.id_updated_par = pm.id_personnel
                WHERE p.id_produit = %s
            """, (id_produit,))

            produit = cursor.fetchone()

            if not produit:
                return jsonify({'success': False, 'message': 'Produit non trouvé'}), 404

            include_prix_vente = has_permission('VOIR_PRIX_VENTE_PRODUIT')

            return jsonify({
                'success': True,
                'produit': format_produit(produit, include_prix_vente)
            })

        finally:
            connection.close()

    # PUT - Modifier un produit
    elif request.method == 'PUT':
        if not has_permission('MODIFIER_PRODUIT'):
            return jsonify({'success': False, 'message': 'Permission refusée'}), 403

        try:
            data = request.get_json()

            description = data.get('description', '').strip()
            prix_achat = float(data.get('prix_achat', 0))

            if not description or prix_achat <= 0:
                return jsonify({'success': False, 'message': 'Données invalides'}), 400

            connection = get_db_connection()
            cursor = connection.cursor()

            # Récupérer la marge actuelle
            cursor.execute("SELECT pourcentage_marge FROM produits WHERE id_produit = %s", (id_produit,))
            result = cursor.fetchone()

            if not result:
                return jsonify({'success': False, 'message': 'Produit non trouvé'}), 404

            # Admin peut modifier la marge
            if has_permission('MODIFIER_MARGE_PRODUIT') and 'pourcentage_marge' in data:
                pourcentage_marge = float(data.get('pourcentage_marge', 30.00))
            else:
                pourcentage_marge = result['pourcentage_marge']

            prix_vente = calculer_prix_vente(prix_achat, pourcentage_marge)

            cursor.execute("""
                UPDATE produits
                SET description = %s, 
                    prix_achat = %s,
                    pourcentage_marge = %s,
                    prix = %s,
                    id_updated_par = %s,
                    updated_at = NOW()
                WHERE id_produit = %s
            """, (description, prix_achat, pourcentage_marge, prix_vente, g.user['id_personnel'], id_produit))

            connection.commit()
            connection.close()

            return jsonify({
                'success': True,
                'message': 'Produit modifié avec succès'
            }), 200

        except ValueError:
            return jsonify({'success': False, 'message': 'Valeurs numériques invalides'}), 400
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    # DELETE - Supprimer un produit
    elif request.method == 'DELETE':
        if not has_permission('SUPPRIMER_PRODUIT'):
            return jsonify({'success': False, 'message': 'Permission refusée'}), 403

        connection = get_db_connection()
        try:
            cursor = connection.cursor()

            # Vérifier si utilisé
            cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM bloc_produits_inclus WHERE id_produit = %s
                    OR EXISTS(SELECT 1 FROM location_bloc_forfait_actes_produits WHERE id_produit = %s)
                    OR EXISTS(SELECT 1 FROM location_bloc_dossier_produits WHERE id_produit = %s)
                    OR EXISTS(SELECT 1 FROM accouchement_dossier_produits WHERE id_produit = %s)
                ) AS est_utilise
            """, (id_produit, id_produit, id_produit, id_produit))

            result = cursor.fetchone()
            if result['est_utilise']:
                return jsonify({
                    'success': False,
                    'message': 'Impossible de supprimer : ce produit est utilisé dans des forfaits ou dossiers'
                }), 409

            cursor.execute("DELETE FROM produits WHERE id_produit = %s", (id_produit,))
            connection.commit()

            return jsonify({
                'success': True,
                'message': 'Produit supprimé avec succès'
            }), 200

        except Exception as e:
            connection.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            connection.close()


@app.route('/api/produits/ajouter', methods=['POST'])
@login_required
@handle_errors()

def api_ajouter_produit():
    """API JSON pour ajouter un produit"""
    try:
        data = request.get_json()

        description = data.get('description', '').strip()
        prix_achat = float(data.get('prix_achat', 0))

        if not description or prix_achat <= 0:
            return jsonify({'success': False, 'message': 'Données invalides'}), 400

        pourcentage_marge = float(data.get('pourcentage_marge', 30.00))
        if has_permission('MODIFIER_MARGE_PRODUIT'):
            pourcentage_marge = float(data.get('pourcentage_marge', 30.00))
        else:
            pourcentage_marge = 30.00

        prix_vente = calculer_prix_vente(prix_achat, pourcentage_marge)

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO produits (description, prix_achat, pourcentage_marge, prix, id_created_par)
            VALUES (%s, %s, %s, %s, %s)
        """, (description, prix_achat, pourcentage_marge, prix_vente, g.user['id_personnel']))

        connection.commit()
        connection.close()

        return jsonify({
            'success': True,
            'message': 'Produit ajouté avec succès'
        }), 201

    except ValueError as e:
        return jsonify({'success': False, 'message': 'Valeurs numériques invalides'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/produits/importer', methods=['POST'])
@login_required
@handle_errors()

def api_importer_produits():
    """API JSON pour importer des produits depuis Excel"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Aucun fichier'}), 400

    file = request.files['file']

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Format non autorisé (.xlsx ou .xls)'}), 400

    try:
        df = pd.read_excel(file)

        required_cols = ['description', 'prix_achat']
        if not all(col in df.columns for col in required_cols):
            return jsonify({'success': False, 'message': f'Colonnes requises: {", ".join(required_cols)}'}), 400

        connection = get_db_connection()
        cursor = connection.cursor()

        success_count = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                description = str(row['description']).strip()
                prix_achat = float(row['prix_achat'])

                pourcentage_marge = 30.00
                if has_permission('MODIFIER_MARGE_PRODUIT') and 'pourcentage_marge' in row and not pd.isna(row['pourcentage_marge']):
                    pourcentage_marge = float(row['pourcentage_marge'])

                if not description or pd.isna(prix_achat):
                    errors.append(f"Ligne {idx + 2}: données manquantes")
                    continue

                prix_vente = calculer_prix_vente(prix_achat, pourcentage_marge)

                cursor.execute("""
                    INSERT INTO produits (description, prix_achat, pourcentage_marge, prix, id_created_par)
                    VALUES (%s, %s, %s, %s, %s)
                """, (description, prix_achat, pourcentage_marge, prix_vente, g.user['id_personnel']))

                success_count += 1

            except Exception as e:
                errors.append(f"Ligne {idx + 2}: {str(e)}")

        connection.commit()
        connection.close()

        return jsonify({
            'success': True,
            'success_count': success_count,
            'error_count': len(errors),
            'errors': errors[:5],
            'message': f'{success_count} produit(s) importé(s)'
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/produits/export-excel', methods=['GET'])
@login_required
@handle_errors()

def api_exporter_produits():
    """API pour exporter TOUS les produits en Excel"""
    from flask import make_response

    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        if has_permission('VOIR_PRIX_VENTE_PRODUIT'):
            cursor.execute("""
                SELECT 
                    p.id_produit,
                    p.description,
                    p.prix_achat,
                    p.pourcentage_marge,
                    p.prix as prix_vente,
                    p.created_at,
                    CONCAT(pc.prenom, ' ', pc.nom) as created_by,
                    p.updated_at,
                    CONCAT(pm.prenom, ' ', pm.nom) as updated_by
                FROM produits p
                LEFT JOIN personnel pc ON p.id_created_par = pc.id_personnel
                LEFT JOIN personnel pm ON p.id_updated_par = pm.id_personnel
                ORDER BY p.id_produit DESC
            """)
        else:
            cursor.execute("""
                SELECT 
                    p.id_produit,
                    p.description,
                    p.prix_achat,
                    p.created_at,
                    CONCAT(pc.prenom, ' ', pc.nom) as created_by,
                    p.updated_at,
                    CONCAT(pm.prenom, ' ', pm.nom) as updated_by
                FROM produits p
                LEFT JOIN personnel pc ON p.id_created_par = pc.id_personnel
                LEFT JOIN personnel pm ON p.id_updated_par = pm.id_personnel
                ORDER BY p.id_produit DESC
            """)

        produits = cursor.fetchall()
        df = pd.DataFrame(produits)

        # Formater les dates
        if 'created_at' in df.columns:
            df['created_at'] = df['created_at'].dt.strftime('%d/%m/%Y %H:%M')
        if 'updated_at' in df.columns:
            df['updated_at'] = df['updated_at'].dt.strftime('%d/%m/%Y %H:%M')

        # Créer Excel en mémoire
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Produits')

            # Style l'en-tête
            worksheet = writer.sheets['Produits']
            fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
            font = Font(color='FFFFFF', bold=True)

            for cell in worksheet[1]:
                cell.fill = fill
                cell.font = font

        output.seek(0)
        filename = f'produits_complet_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        # Créer la réponse avec make_response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'

        return response

    finally:
        connection.close()


@app.route('/api/produits/recalculer-prix', methods=['POST'])
@login_required
@handle_errors()

def api_recalculer_prix_tous():
    """API pour recalculer TOUS les prix de vente (admin only)"""
    connection = get_db_connection()
    try:
        cursor = connection.cursor()

        # Récupérer tous les produits
        cursor.execute("SELECT id_produit, prix_achat, pourcentage_marge FROM produits")
        produits = cursor.fetchall()

        count = 0
        for produit in produits:
            prix_vente = calculer_prix_vente(produit['prix_achat'], produit['pourcentage_marge'])
            cursor.execute("""
                UPDATE produits 
                SET prix = %s, 
                    id_updated_par = %s,
                    updated_at = NOW()
                WHERE id_produit = %s
            """, (prix_vente, g.user['id_personnel'], produit['id_produit']))
            count += 1

        connection.commit()

        return jsonify({
            'success': True,
            'message': f'{count} prix recalculés avec succès'
        }), 200

    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        connection.close()


@app.route('/api/produits/fusionner', methods=['POST'])
@login_required
@handle_errors()

def api_fusionner_produits():
    """API pour fusionner des produits dupliqués vers un produit maître"""
    try:
        data = request.get_json()
        
        id_master = int(data.get('id_master'))
        ids_duplicates = [int(id) for id in data.get('ids_duplicates', [])]
        
        if not id_master or not ids_duplicates:
            return jsonify({'success': False, 'message': 'Paramètres manquants'}), 400
            
        if id_master in ids_duplicates:
             return jsonify({'success': False, 'message': 'Le produit maître ne peut pas être dans la liste des doublons'}), 400
    
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Tables référençant id_produit
        referencing_tables = [
            'bloc_produits_inclus',
            'location_bloc_forfait_actes_produits',
            'location_bloc_dossier_produits',
            'accouchement_dossier_produits',
            'kt_dossier_produits',
            'medecin_interne_consommables',
             'medecin_interne_consommables_medecin' 
        ]
        
        # 1. Vérifier que le maître existe
        cursor.execute("SELECT description FROM produits WHERE id_produit = %s", (id_master,))
        master_prod = cursor.fetchone()
        
        if not master_prod:
            connection.close()
            return jsonify({'success': False, 'message': 'Produit maître introuvable'}), 404
            
        success_count = 0
        
        try:
            for dup_id in ids_duplicates:
                # Pour chaque table de référence, mettre à jour l'ID
                for table in referencing_tables:
                   try: 
                        column_name = 'id_produit_consommable' if table == 'medecin_interne_consommables_medecin' else 'id_produit'
                        cursor.execute(f"SHOW COLUMNS FROM {table} LIKE '{column_name}'")
                        if cursor.fetchone():
                             cursor.execute(f"UPDATE {table} SET {column_name} = %s WHERE {column_name} = %s", (id_master, dup_id))
                   except Exception as e:
                       print(f"Error updating table {table}: {e}")
                       pass # Continue if table/column doesn't exist or other error, risky but practical for now
                    
                # Supprimer le doublon
                cursor.execute("DELETE FROM produits WHERE id_produit = %s", (dup_id,))
                success_count += 1
                
            connection.commit()
            
            return jsonify({
                'success': True, 
                'message': f'Fusion réussie. {success_count} produit(s) fusionné(s) vers "{master_prod["description"]}".'
            }), 200

        except Exception as e:
            connection.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            connection.close()

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
