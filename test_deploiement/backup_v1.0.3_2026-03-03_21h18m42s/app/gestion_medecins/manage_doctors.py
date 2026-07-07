# app/situation_medecin.py

from flask import request, render_template, jsonify
from unidecode import unidecode
from rapidfuzz import fuzz
import jellyfish
import re
from app import app, get_db_connection
from app.auth import chargement
from app.error import handle_errors
from app.utils.utiles import login_required


# ============================================================================
# UTILITAIRES DE SIMILARITÉ
# ============================================================================

def normalize_name(s: str) -> str:
    """Normalise un nom: supprime accents, titres, ponctuation."""
    if not s:
        return ''
    s = s.strip().lower()
    for t in ('dr', 'dr.', 'docteur', 'md', 'pr', 'pr.', 'professeur'):
        if s.startswith(t + ' '):
            s = s[len(t) + 1:]
        s = s.replace(t + '.', '').replace(t, '')
    s = unidecode(s)
    s = re.sub(r'[^a-z0-9\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def name_score(first_a, last_a, first_b, last_b, specialty_match=False):
    """Score combiné entre deux noms (0..100)."""
    norm_a = normalize_name(f"{first_a} {last_a}")
    norm_b = normalize_name(f"{first_b} {last_b}")

    if not norm_a or not norm_b:
        return 0

    # Score fuzzy avec plusieurs méthodes
    token_sort = fuzz.token_sort_ratio(norm_a, norm_b)
    token_set = fuzz.token_set_ratio(norm_a, norm_b)
    partial = fuzz.partial_ratio(norm_a, norm_b)

    # Score phonétique - Metaphone
    try:
        meta_a = jellyfish.metaphone(norm_a)
        meta_b = jellyfish.metaphone(norm_b)
        phonetic_meta = 100 if meta_a and meta_b and meta_a == meta_b else 0
    except:
        phonetic_meta = 0

    # Score phonétique - Soundex sur nom de famille
    try:
        soundex_a = jellyfish.soundex(normalize_name(last_a))
        soundex_b = jellyfish.soundex(normalize_name(last_b))
        phonetic_soundex = 100 if soundex_a == soundex_b else 0
    except:
        phonetic_soundex = 0

    # Score Jaro-Winkler (bon pour les fautes de frappe)
    try:
        jaro = jellyfish.jaro_winkler_similarity(norm_a, norm_b) * 100
    except:
        jaro = 0

    # Moyenne pondérée
    score = (
        0.30 * token_sort +
        0.20 * token_set +
        0.15 * partial +
        0.10 * phonetic_meta +
        0.10 * phonetic_soundex +
        0.15 * jaro
    )

    # Bonus si même spécialité
    if specialty_match:
        score = min(100, score + 8)

    return round(score, 2)





def get_confidence_level(score):
    """Retourne le niveau de confiance basé sur le score."""
    if score >= 90:
        return {'level': 'high', 'label': 'Très probable', 'color': 'danger'}
    elif score >= 75:
        return {'level': 'medium', 'label': 'Probable', 'color': 'warning'}
    else:
        return {'level': 'low', 'label': 'Possible', 'color': 'info'}


def find_similar_doctors(cursor, first_name, last_name, specialty_id=None,
                         exclude_id=None, top_n=5, threshold=50):
    """Trouve les médecins similaires à un nom donné."""
    cursor.execute("""
        SELECT d.id, d.first_name, d.last_name, d.id_specialty, 
               d.est_interne, s.name_specialty
        FROM doctors d
        LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
    """)
    doctors = cursor.fetchall()

    candidates = []
    for doc in doctors:
        if exclude_id and doc['id'] == exclude_id:
            continue

        specialty_match = (specialty_id and doc['id_specialty'] == int(specialty_id))
        score = name_score(
            first_name, last_name,
            doc['first_name'], doc['last_name'],
            specialty_match
        )

        if score >= threshold:
            candidates.append({
                'id': doc['id'],
                'first_name': doc['first_name'],
                'last_name': doc['last_name'],
                'id_specialty': doc['id_specialty'],
                'name_specialty': doc['name_specialty'],
                'est_interne': doc['est_interne'],
                'score': score,
                'confidence': get_confidence_level(score)
            })

    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:top_n]


def handle_unique_merge(cursor, table, column, id_cible, id_source):
    """Gère la fusion pour les tables avec contraintes d'unicité."""
    # Identifier la colonne d'unicité secondaire
    unique_cols = {
        'location_bloc_forfait_medecin': 'id_forfait',
        'location_bloc_medecin_config': None,  # Unique sur id_doctor seul
        'location_bloc_prix_chambre_medecin': 'id_type_chambre'
    }

    secondary_col = unique_cols.get(table)

    if secondary_col is None:
        # Table unique sur le médecin seul - garder celui du cible
        cursor.execute(f"SELECT id FROM {table} WHERE {column} = %s", (id_cible,))
        if not cursor.fetchone():
            cursor.execute(f"UPDATE {table} SET {column} = %s WHERE {column} = %s",
                          (id_cible, id_source))
            count = cursor.rowcount
        else:
            cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", (id_source,))
            count = 0
    else:
        # Mettre à jour seulement les enregistrements non conflictuels
        cursor.execute(f"""
            UPDATE {table} 
            SET {column} = %s 
            WHERE {column} = %s 
            AND {secondary_col} NOT IN (
                SELECT {secondary_col} FROM (
                    SELECT {secondary_col} FROM {table} WHERE {column} = %s
                ) as existing
            )
        """, (id_cible, id_source, id_cible))
        count = cursor.rowcount
        # Supprimer les doublons restants
        cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", (id_source,))

    return count


# ============================================================================
# ROUTES - GESTION DES MÉDECINS
# ============================================================================

@app.route('/gestion_medecins')
@login_required
@handle_errors()
def gestion_medecins():
    """Page de gestion CRUD des médecins"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupération de tous les médecins avec statistiques
        cursor.execute("""
            SELECT d.id                                   as id_doctor,
                   d.first_name,
                   d.last_name,
                   d.telephone,
                   CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                   s.id_specialty,
                   s.name_specialty,
                   d.est_interne,

                   (SELECT COUNT(DISTINCT id_dossier) FROM location_bloc_dossier_patient WHERE id_doctor = d.id) as total_dossiers_bloc,

                   (SELECT COUNT(DISTINCT id_acte) FROM medecin_interne_actes WHERE id_doctor = d.id) as total_dossiers_interne,

                   (SELECT COUNT(DISTINCT id_dossier) FROM accouchement_dossiers WHERE id_gyneco = d.id) as total_dossiers_accouchement,
                   
                   (SELECT COUNT(DISTINCT id_dossier) FROM kt_dossier_patient WHERE id_doctor = d.id) as total_dossiers_kt

            FROM doctors d
                     LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            ORDER BY d.last_name, d.first_name
        """)
        medecins = cursor.fetchall()

        # Calculate totals in Python
        grand_total_dossiers = 0
        for m in medecins:
            # Ensure values are not None
            bloc = m.get('total_dossiers_bloc') or 0
            interne = m.get('total_dossiers_interne') or 0
            acc = m.get('total_dossiers_accouchement') or 0
            kt = m.get('total_dossiers_kt') or 0
            
            m['total_dossiers'] = bloc + interne + acc + kt
            grand_total_dossiers += m['total_dossiers']

        # Récupération des spécialités
        cursor.execute("SELECT * FROM specialty ORDER BY name_specialty")
        specialties = cursor.fetchall()

        return render_template(
                'gestion_medecins/gestion_medecins.html',
            medecins=medecins,
            specialties=specialties,
            total_dossiers=grand_total_dossiers,
            title="Gestion des Médecins",
        )

    finally:
        cursor.close()
        connection.close()


@app.route('/ajouter_medecin', methods=['POST'])
@login_required
@handle_errors()

def ajouter_medecin():
    """Ajouter un médecin avec détection intelligente de doublons."""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        telephone = request.form.get('telephone', '').strip()
        specialty = request.form.get('specialty')
        est_interne = 1 if request.form.get('est_interne') == 'on' else 0
        force = request.form.get('force') == 'true'  # Forcer l'ajout

        if not all([first_name, last_name, specialty]):
            return jsonify({'success': False, 'error': 'Tous les champs sont obligatoires'}), 400

        # Recherche de doublons (sauf si forcé)
        if not force:
            similar = find_similar_doctors(cursor, first_name, last_name, specialty)

            if similar:
                top = similar[0]
                if top['score'] >= 90:
                    return jsonify({
                        'success': False,
                        'error': f"Doublon très probable détecté (score: {top['score']}%)",
                        'duplicate_warning': True,
                        'suggestions': similar[:3]
                    }), 400
                elif top['score'] >= 75:
                    return jsonify({
                        'success': False,
                        'error': f"Médecin similaire trouvé (score: {top['score']}%). Vérifiez avant de continuer.",
                        'duplicate_warning': True,
                        'can_force': True,
                        'suggestions': similar[:3]
                    }), 400

        # Insertion
        cursor.execute("""
            INSERT INTO doctors (first_name, last_name, telephone, id_specialty, est_interne)
            VALUES (%s, %s, %s, %s, %s)
        """, (first_name, last_name, telephone, specialty, est_interne))

        connection.commit()
        chargement()

        return jsonify({
            'success': True,
            'message': f'Dr. {first_name} {last_name} ajouté avec succès',
            'id': cursor.lastrowid
        })

    except Exception as e:
        connection.rollback()
        app.logger.error(f'Erreur ajout médecin: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/modifier_medecin/<int:id_doctor>', methods=['POST'])
@login_required
@handle_errors()

def modifier_medecin(id_doctor):
    """Modifier un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        telephone = request.form.get('telephone', '').strip()
        specialty = request.form.get('specialty')
        est_interne = 1 if request.form.get('est_interne') == 'on' else 0

        if not all([first_name, last_name, specialty]):
            return jsonify({'success': False, 'error': 'Tous les champs sont obligatoires'}), 400

        # Vérifier que le médecin existe
        cursor.execute("SELECT id FROM doctors WHERE id = %s", (id_doctor,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Médecin non trouvé'}), 404

        # Vérifier si un autre médecin porte déjà ce nom
        cursor.execute("""
            SELECT id
            FROM doctors
            WHERE first_name = %s
              AND last_name = %s
              AND id != %s
        """, (first_name, last_name, id_doctor))

        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'Un autre médecin porte déjà ce nom'}), 400

        # Mise à jour
        cursor.execute("""
            UPDATE doctors
            SET first_name   = %s,
                last_name    = %s,
                telephone    = %s,
                id_specialty = %s,
                est_interne  = %s
            WHERE id = %s
        """, (first_name, last_name, telephone, specialty, est_interne, id_doctor))

        connection.commit()
        chargement()
        return jsonify({
            'success': True,
            'message': f'Dr. {first_name} {last_name} modifié avec succès'
        })

    except Exception as e:
        connection.rollback()
        app.logger.error(f'Erreur modification médecin: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/get_medecin/<int:id_doctor>')
@login_required
@handle_errors()

def get_medecin(id_doctor):
    """Récupère les informations d'un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT d.id, d.first_name, d.last_name, d.telephone, d.id_specialty, d.est_interne, s.name_specialty
            FROM doctors d
                     LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
        """, (id_doctor,))

        medecin = cursor.fetchone()

        if not medecin:
            return jsonify({'success': False, 'error': 'Médecin non trouvé'}), 404

        return jsonify({
            'success': True,
            'medecin': {
                'id': medecin['id'],
                'first_name': medecin['first_name'],
                'last_name': medecin['last_name'],
                'telephone': medecin['telephone'],
                'id_specialty': medecin['id_specialty'],
                'name_specialty': medecin['name_specialty'],
                'est_interne': medecin['est_interne']
            }
        })

    except Exception as e:
        app.logger.error(f'Erreur get_medecin: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()



@app.route('/api/comparer_medecins/<int:id1>/<int:id2>')
@login_required
@handle_errors()

def comparer_medecins(id1, id2):
    """Compare deux médecins et retourne le score détaillé."""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT d.id, d.first_name, d.last_name, d.id_specialty, 
                   d.est_interne, s.name_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id IN (%s, %s)
        """, (id1, id2))

        doctors = cursor.fetchall()
        if len(doctors) != 2:
            return jsonify({'success': False, 'error': 'Médecins non trouvés'}), 404

        d1, d2 = (doctors[0], doctors[1]) if doctors[0]['id'] == id1 else (doctors[1], doctors[0])

        # Calcul détaillé des scores
        norm_a = normalize_name(f"{d1['first_name']} {d1['last_name']}")
        norm_b = normalize_name(f"{d2['first_name']} {d2['last_name']}")

        details = {
            'token_sort': fuzz.token_sort_ratio(norm_a, norm_b),
            'token_set': fuzz.token_set_ratio(norm_a, norm_b),
            'partial': fuzz.partial_ratio(norm_a, norm_b),
            'jaro_winkler': round(jellyfish.jaro_winkler_similarity(norm_a, norm_b) * 100, 2),
            'metaphone_match': jellyfish.metaphone(norm_a) == jellyfish.metaphone(norm_b),
            'soundex_match': jellyfish.soundex(normalize_name(d1['last_name'])) ==
                            jellyfish.soundex(normalize_name(d2['last_name'])),
            'same_specialty': d1['id_specialty'] == d2['id_specialty']
        }

        specialty_match = d1['id_specialty'] == d2['id_specialty'] and d1['id_specialty'] is not None
        final_score = name_score(d1['first_name'], d1['last_name'],
                                  d2['first_name'], d2['last_name'], specialty_match)

        return jsonify({
            'success': True,
            'medecin1': dict(d1),
            'medecin2': dict(d2),
            'score': final_score,
            'confidence': get_confidence_level(final_score),
            'details': details,
            'normalized': {'a': norm_a, 'b': norm_b}
        })

    except Exception as e:
        app.logger.error(f'Erreur comparaison: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/stats_medecin/<int:id_doctor>')
@login_required
@handle_errors()

def stats_medecin(id_doctor):
    """Récupère les statistiques détaillées d'un médecin pour la fusion"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Exécution d'une seule requête optimisée pour récupérer toutes les stats
        query = """
            SELECT 
                (SELECT COUNT(*) FROM location_bloc_dossier_patient WHERE id_doctor = %s) as dossiers_bloc,
                (SELECT COUNT(*) FROM location_bloc_doctor_situations WHERE id_doctor = %s) as situations_bloc,
                (SELECT COUNT(*) FROM location_bloc_forfait_medecin WHERE id_doctor = %s) as forfaits,
                (SELECT COUNT(*) FROM location_bloc_medecin_config WHERE id_doctor = %s) as configs,
                (SELECT COUNT(*) FROM location_bloc_operations_financieres_medecin WHERE id_doctor = %s) as operations_bloc,
                (SELECT COUNT(*) FROM location_bloc_prix_chambre_medecin WHERE id_doctor = %s) as prix_chambres,
                (SELECT COUNT(*) FROM accouchement_dossiers WHERE id_gyneco = %s) as accouchements,
                (SELECT COUNT(*) FROM accouchement_gyneco_situations WHERE id_gyneco = %s) as situations_accouchement,
                (SELECT COUNT(*) FROM accouchement_operations_financieres_gyneco WHERE id_gyneco = %s) as operations_accouchement,
                (SELECT COUNT(*) FROM gyneco_interne_decharges WHERE id_gyneco = %s) as decharges_gyneco,
                (SELECT COUNT(*) FROM medecin_interne_actes WHERE id_doctor = %s) as actes_interne,
                (SELECT COUNT(*) FROM medecin_interne_decharges WHERE id_doctor = %s) as decharges_interne,
                (SELECT COUNT(*) FROM medecin_interne_operations_financieres WHERE id_doctor = %s) as operations_interne,
                (SELECT COUNT(*) FROM medecin_interne_situations WHERE id_doctor = %s) as situations_interne
        """
        
        # On répète l'ID pour chaque sous-requête (14 fois)
        params = tuple([id_doctor] * 14)
        
        cursor.execute(query, params)
        result = cursor.fetchone()
        
        if result:
            stats = result
            stats['total'] = sum(result.values())
        else:
             # Fallback cas improbable
            stats = {
                'dossiers_bloc': 0, 'situations_bloc': 0, 'forfaits': 0, 
                'configs': 0, 'operations_bloc': 0, 'prix_chambres': 0,
                'accouchements': 0, 'situations_accouchement': 0, 
                'operations_accouchement': 0, 'decharges_gyneco': 0,
                'actes_interne': 0, 'decharges_interne': 0, 
                'operations_interne': 0, 'situations_interne': 0,
                'total': 0
            }

        return jsonify({'success': True, 'stats': stats})

    except Exception as e:
        app.logger.error(f'Erreur stats médecin: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/fusionner_medecins', methods=['POST'])
@login_required
@handle_errors()

def fusionner_medecins():
    """Fusionne deux médecins avec rapport détaillé."""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        id_cible = request.form.get('id_cible', type=int)
        id_source = request.form.get('id_source', type=int)

        if not id_cible or not id_source:
            return jsonify({'success': False, 'error': 'IDs médecins requis'}), 400

        if id_cible == id_source:
            return jsonify({'success': False, 'error': 'Impossible de fusionner un médecin avec lui-même'}), 400

        # Vérifier l'existence et récupérer les infos
        cursor.execute("""
            SELECT id, first_name, last_name FROM doctors WHERE id IN (%s, %s)
        """, (id_cible, id_source))
        medecins = {m['id']: m for m in cursor.fetchall()}

        if len(medecins) != 2:
            return jsonify({'success': False, 'error': 'Médecin(s) non trouvé(s)'}), 404

        # Tables à mettre à jour avec leur configuration
        tables_config = [
            ('location_bloc_dossier_patient', 'id_doctor', False),
            ('location_bloc_doctor_situations', 'id_doctor', False),
            ('location_bloc_forfait_medecin', 'id_doctor', True),  # Unique constraint
            ('location_bloc_medecin_config', 'id_doctor', True),   # Unique constraint
            ('location_bloc_operations_financieres_medecin', 'id_doctor', False),
            ('location_bloc_prix_chambre_medecin', 'id_doctor', True),  # Unique constraint
            ('accouchement_dossiers', 'id_gyneco', False),
            ('accouchement_gyneco_situations', 'id_gyneco', False),
            ('accouchement_operations_financieres_gyneco', 'id_gyneco', False),
            ('gyneco_interne_decharges', 'id_gyneco', False),
            ('medecin_interne_actes', 'id_doctor', False),
            ('medecin_interne_decharges', 'id_doctor', False),
            ('medecin_interne_operations_financieres', 'id_doctor', False),
            ('medecin_interne_situations', 'id_doctor', False),
        ]

        rapport = {}

        for table, column, has_unique in tables_config:
            try:
                if has_unique:
                    # Gérer les contraintes d'unicité
                    rapport[table] = handle_unique_merge(cursor, table, column, id_cible, id_source)
                else:
                    cursor.execute(f"UPDATE {table} SET {column} = %s WHERE {column} = %s",
                                   (id_cible, id_source))
                    rapport[table] = cursor.rowcount
            except Exception as e:
                app.logger.warning(f"Table {table} ignorée: {str(e)}")
                rapport[table] = 0

        # Supprimer le médecin source
        cursor.execute("DELETE FROM doctors WHERE id = %s", (id_source,))

        connection.commit()
        chargement()

        source_name = f"Dr. {medecins[id_source]['first_name']} {medecins[id_source]['last_name']}"
        cible_name = f"Dr. {medecins[id_cible]['first_name']} {medecins[id_cible]['last_name']}"
        total = sum(rapport.values())

        return jsonify({
            'success': True,
            'message': f'Fusion réussie: {source_name} → {cible_name}',
            'total_records': total,
            'rapport': rapport
        })

    except Exception as e:
        connection.rollback()
        app.logger.error(f'Erreur fusion: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/get_medecin_full_info/<int:id_doctor>')
@login_required
@handle_errors()

def get_medecin_full_info(id_doctor):
    """Récupère les informations complètes d'un médecin pour le modal"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Infos de base + Spécialité
        cursor.execute("""
            SELECT d.id, d.first_name, d.last_name, d.telephone, d.est_interne, 
                   s.name_specialty, s.id_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
        """, (id_doctor,))
        medecin = cursor.fetchone()

        if not medecin:
            return jsonify({'success': False, 'error': 'Médecin non trouvé'}), 404

        return jsonify({
            'success': True,
            'medecin': medecin,
        })

    except Exception as e:
        app.logger.error(f'Erreur get_medecin_full_info: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        connection.close()