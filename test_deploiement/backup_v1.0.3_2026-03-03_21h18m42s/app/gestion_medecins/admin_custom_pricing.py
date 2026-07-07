# app/location_bloc.py - Routes d'administration
from flask import request, render_template, g, flash, redirect, url_for, jsonify

from app import app, get_db_connection
from app.accouchements.accouchements import to_decimal
from app.utils.utiles import login_required


@app.route('/gestion_medecins/tarifs_personnalises')
@login_required
def admin_tarifs_personnalises():
    """Interface de gestion des tarifs personnalisés"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Récupérer tous les médecins
        cursor.execute("""
            SELECT id, 
                   CONCAT(first_name, ' ', last_name) as name,
                   id_specialty
            FROM doctors
            WHERE est_interne = 0 OR est_interne IS NULL
            ORDER BY last_name, first_name
        """)
        doctors = cursor.fetchall()
        
        # Récupérer tous les forfaits
        cursor.execute("""
            SELECT id_forfait, name_forfait, prix_forfait, duree_forfait, nbr_nuit
            FROM location_bloc_forfait_actes
            WHERE est_actif = 1
            ORDER BY name_forfait
        """)
        forfaits = cursor.fetchall()
        
        # Récupérer tous les types de chambres
        cursor.execute("""
            SELECT id_type_chambre, nom_type, prix_unitaire, est_standard
            FROM type_chambre
            WHERE est_actif = 1
            ORDER BY prix_unitaire
        """)
        types_chambres = cursor.fetchall()
        
        # Récupérer les forfaits personnalisés existants
        cursor.execute("""
            SELECT fm.id,
                   fm.id_doctor,
                   fm.id_forfait,
                   fm.prix_personnalise,
                   fm.est_actif,
                   fm.date_debut,
                   fm.date_fin,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   f.name_forfait,
                   f.prix_forfait as prix_standard
            FROM location_bloc_forfait_medecin fm
            JOIN doctors d ON fm.id_doctor = d.id
            JOIN location_bloc_forfait_actes f ON fm.id_forfait = f.id_forfait
            ORDER BY d.last_name, d.first_name, f.name_forfait
        """)
        forfaits_personnalises = cursor.fetchall()
        
        # Récupérer les prix chambres personnalisés existants
        cursor.execute("""
            SELECT pcm.id,
                   pcm.id_doctor,
                   pcm.id_type_chambre,
                   pcm.prix_personnalise,
                   pcm.est_actif,
                   pcm.date_debut,
                   pcm.date_fin,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   tc.nom_type,
                   tc.prix_unitaire as prix_standard
            FROM location_bloc_prix_chambre_medecin pcm
            JOIN doctors d ON pcm.id_doctor = d.id
            JOIN type_chambre tc ON pcm.id_type_chambre = tc.id_type_chambre
            ORDER BY d.last_name, d.first_name, tc.nom_type
        """)
        prix_chambres_personnalises = cursor.fetchall()
        
        # Récupérer les configurations de nuitées pré-op
        cursor.execute("""
            SELECT lbmc.id,
                   lbmc.id_doctor,
                   lbmc.nuitees_preop_gratuites_max,
                   lbmc.est_actif,
                   lbmc.date_debut,
                   lbmc.date_fin,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name
            FROM location_bloc_medecin_config lbmc
            JOIN doctors d ON lbmc.id_doctor = d.id
            ORDER BY d.last_name, d.first_name
        """)
        configs_nuitees_preop = cursor.fetchall()

        # ── KT : Actes disponibles ──
        cursor.execute("""
            SELECT id_acte, name_acte_kt, prix_payant, honoraires_payant,
                   prix_urgence, honoraires_urgence
            FROM kt_actes
            ORDER BY name_acte_kt
        """)
        actes_kt = cursor.fetchall()

        # ── KT : Conventions actives ──
        cursor.execute("""
            SELECT id_convention, code_convention, nom_convention
            FROM kt_conventions WHERE est_active = 1
            ORDER BY nom_convention
        """)
        conventions_kt = cursor.fetchall()

        # ── Pourcentages Médecin Interne ──
        cursor.execute("""
            SELECT d.id, CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   s.name_specialty, d.pourcentage_medecin_interne
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.est_interne = 1
            ORDER BY d.last_name, d.first_name
        """)
        medecins_internes_pourcentages = cursor.fetchall()

        # ── Produits (pour modal plafond consommables) ──
        cursor.execute("""
            SELECT id_produit, description, prix
            FROM produits
            ORDER BY description
        """)
        produits_list = cursor.fetchall()

        return render_template(
                'gestion_medecins/admin_tarifs_personnalises.html',
            doctors=doctors,
            forfaits=forfaits,
            types_chambres=types_chambres,
            forfaits_personnalises=forfaits_personnalises,
            prix_chambres_personnalises=prix_chambres_personnalises,
            configs_nuitees_preop=configs_nuitees_preop,
            actes_kt=actes_kt,
            conventions_kt=conventions_kt,
            medecins_internes_pourcentages=medecins_internes_pourcentages,
            produits_list=produits_list,
            title="Gestion des tarifs personnalisés"
        )
        
    except Exception as e:
        app.logger.error(f"Erreur admin_tarifs_personnalises: {str(e)}")
        flash(f'Erreur: {str(e)}', 'danger')
        return redirect(url_for('index_admin'))
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/gestion_medecins/tarifs_personnalises/ajouter_forfait', methods=['POST'])
@login_required
def admin_ajouter_forfait_personnalise():
    """Ajouter un forfait personnalisé pour un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        id_doctor = request.form.get('id_doctor')
        id_forfait = request.form.get('id_forfait')
        prix_personnalise = request.form.get('prix_personnalise', '').strip()
        date_debut = request.form.get('date_debut') or None
        date_fin = request.form.get('date_fin') or None
        
        if not id_doctor or not id_forfait:
            flash('Médecin et forfait requis', 'danger')
            return redirect(url_for('admin_tarifs_personnalises'))

        prix_personnalise_decimal = to_decimal(prix_personnalise) if prix_personnalise else None

        cursor.execute("""
            SELECT id FROM location_bloc_forfait_medecin
            WHERE id_doctor = %s AND id_forfait = %s
        """, (id_doctor, id_forfait))
        
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE location_bloc_forfait_medecin
                SET prix_personnalise = %s,
                    date_debut = %s,
                    date_fin = %s,
                    est_actif = 1
                WHERE id = %s
            """, (prix_personnalise_decimal, date_debut, date_fin, existing['id']))
            flash('Forfait personnalisé mis à jour', 'success')
        else:
            cursor.execute("""
                INSERT INTO location_bloc_forfait_medecin
                (id_doctor, id_forfait, prix_personnalise, date_debut, date_fin, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_doctor, id_forfait, prix_personnalise_decimal, date_debut, date_fin, g.user['id_personnel']))
            flash('Forfait personnalisé ajouté', 'success')
        
        connection.commit()
        
    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur ajouter forfait personnalisé: {str(e)}")
        flash(f'Erreur: {str(e)}', 'danger')
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    
    return redirect(url_for('admin_tarifs_personnalises'))


@app.route('/gestion_medecins/tarifs_personnalises/ajouter_prix_chambre', methods=['POST'])
@login_required
def admin_ajouter_prix_chambre_personnalise():
    """Ajouter un prix de chambre personnalisé pour un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        id_doctor = request.form.get('id_doctor')
        id_type_chambre = request.form.get('id_type_chambre')
        prix_personnalise = request.form.get('prix_personnalise')
        date_debut = request.form.get('date_debut') or None
        date_fin = request.form.get('date_fin') or None
        
        if not id_doctor or not id_type_chambre or not prix_personnalise:
            flash('Tous les champs sont requis', 'danger')
            return redirect(url_for('admin_tarifs_personnalises'))
        
        prix_personnalise_decimal = to_decimal(prix_personnalise)

        cursor.execute("""
            SELECT id FROM location_bloc_prix_chambre_medecin
            WHERE id_doctor = %s AND id_type_chambre = %s
        """, (id_doctor, id_type_chambre))
        
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE location_bloc_prix_chambre_medecin
                SET prix_personnalise = %s,
                    date_debut = %s,
                    date_fin = %s,
                    est_actif = 1
                WHERE id = %s
            """, (prix_personnalise_decimal, date_debut, date_fin, existing['id']))
            flash('Prix chambre personnalisé mis à jour', 'success')
        else:
            cursor.execute("""
                INSERT INTO location_bloc_prix_chambre_medecin
                (id_doctor, id_type_chambre, prix_personnalise, date_debut, date_fin, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_doctor, id_type_chambre, prix_personnalise_decimal, date_debut, date_fin, g.user['id_personnel']))
            flash('Prix chambre personnalisé ajouté', 'success')
        
        connection.commit()
        
    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur ajouter prix chambre personnalisé: {str(e)}")
        flash(f'Erreur: {str(e)}', 'danger')
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    
    return redirect(url_for('admin_tarifs_personnalises'))


@app.route('/gestion_medecins/tarifs_personnalises/supprimer_forfait/<int:id>', methods=['POST'])
@login_required
def admin_supprimer_forfait_personnalise(id):
    """Supprimer un forfait personnalisé"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM location_bloc_forfait_medecin WHERE id = %s", (id,))
        connection.commit()
        flash('Forfait personnalisé supprimé', 'success')
        
    except Exception as e:
        connection.rollback()
        flash(f'Erreur: {str(e)}', 'danger')
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    
    return redirect(url_for('admin_tarifs_personnalises'))


@app.route('/gestion_medecins/tarifs_personnalises/supprimer_prix_chambre/<int:id>', methods=['POST'])
@login_required
def admin_supprimer_prix_chambre_personnalise(id):
    """Supprimer un prix chambre personnalisé"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        cursor.execute("DELETE FROM location_bloc_prix_chambre_medecin WHERE id = %s", (id,))
        connection.commit()
        flash('Prix chambre personnalisé supprimé', 'success')
        
    except Exception as e:
        connection.rollback()
        flash(f'Erreur: {str(e)}', 'danger')
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    
    return redirect(url_for('admin_tarifs_personnalises'))




@app.route('/gestion_medecins/tarifs_personnalises/configurer_nuitees_preop', methods=['POST'])
@login_required
def admin_configurer_nuitees_preop():
    """Ajouter/Modifier la configuration de nuitées pré-op d'un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        id_doctor = request.form.get('id_doctor')
        nuitees_max = request.form.get('nuitees_preop_gratuites_max', 0)
        date_debut = request.form.get('date_debut') or None
        date_fin = request.form.get('date_fin') or None

        if not id_doctor:
            flash('Veuillez sélectionner un médecin', 'danger')
            return redirect(url_for('admin_tarifs_personnalises') + '#nuitees-preop')

        # Convertir en entier
        try:
            nuitees_max = int(nuitees_max)
            # Limiter à 1 maximum
            nuitees_max = min(max(0, nuitees_max), 1)
        except ValueError:
            nuitees_max = 0

        # Vérifier si une configuration existe déjà
        cursor.execute("""
            SELECT id FROM location_bloc_medecin_config
            WHERE id_doctor = %s
        """, (id_doctor,))

        existing = cursor.fetchone()

        if existing:
            # Mettre à jour
            cursor.execute("""
                UPDATE location_bloc_medecin_config
                SET nuitees_preop_gratuites_max = %s,
                    date_debut = %s,
                    date_fin = %s,
                    est_actif = 1,
                    updated_at = NOW()
                WHERE id = %s
            """, (nuitees_max, date_debut, date_fin, existing['id']))
            flash('Configuration mise à jour avec succès', 'success')
        else:
            # Insérer
            cursor.execute("""
                INSERT INTO location_bloc_medecin_config
                (id_doctor, nuitees_preop_gratuites_max, date_debut, date_fin, est_actif, created_by)
                VALUES (%s, %s, %s, %s, 1, %s)
            """, (id_doctor, nuitees_max, date_debut, date_fin, g.user['id_personnel']))
            flash('Configuration ajoutée avec succès', 'success')

        connection.commit()

    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur configurer_nuitees_preop: {str(e)}")
        flash(f'Erreur: {str(e)}', 'danger')

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return redirect(url_for('admin_tarifs_personnalises') + '#nuitees-preop')


@app.route('/gestion_medecins/tarifs_personnalises/supprimer_config_nuitees_preop/<int:id>', methods=['POST'])
@login_required

def admin_supprimer_config_nuitees_preop(id):
    """Supprimer une configuration de nuitées pré-op"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM location_bloc_medecin_config WHERE id = %s", (id,))
        connection.commit()
        flash('Configuration supprimée avec succès', 'success')

    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur supprimer_config_nuitees_preop: {str(e)}")
        flash(f'Erreur: {str(e)}', 'danger')

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return redirect(url_for('admin_tarifs_personnalises') + '#nuitees-preop')


# ============================================================
# ONGLET 4 : TARIFS KT MÉDECIN – API JSON (kt_medecin_tarifs)
# ============================================================


@app.route('/api/gestion_medecins/tarifs_kt', methods=['GET'])
@login_required
def api_tarifs_kt_list():
    """Liste tous les tarifs KT médecin (JSON)"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            SELECT mt.id,
                   mt.id_doctor,
                   mt.id_acte,
                   mt.id_convention,
                   mt.est_urgence,
                   mt.prix,
                   mt.part_operateur,
                   mt.est_actif,
                   CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                   a.name_acte_kt,
                   c.nom_convention
            FROM kt_medecin_tarifs mt
            JOIN doctors d ON mt.id_doctor = d.id
            JOIN kt_actes a ON mt.id_acte = a.id_acte
            LEFT JOIN kt_conventions c ON mt.id_convention = c.id_convention
            ORDER BY d.last_name, d.first_name, a.name_acte_kt
        """)
        tarifs = cursor.fetchall()
        for t in tarifs:
            t['prix'] = float(t['prix']) if t['prix'] else 0
            t['part_operateur'] = float(t['part_operateur']) if t['part_operateur'] else 0
        return jsonify({'success': True, 'tarifs': tarifs})
    finally:
        cursor.close()
        connection.close()


@app.route('/api/gestion_medecins/tarifs_kt', methods=['POST'])
@login_required
def api_tarifs_kt_add():
    """Ajouter/mettre à jour un tarif KT (JSON in, JSON out)"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        data = request.get_json()
        id_doctor = data.get('id_doctor')
        id_acte = data.get('id_acte')
        id_convention = data.get('id_convention') or None
        est_urgence = 1 if data.get('est_urgence') else 0
        prix = to_decimal(str(data.get('prix', 0)))
        part_operateur = to_decimal(str(data.get('part_operateur', 0)))

        if not id_doctor or not id_acte:
            return jsonify({'success': False, 'message': 'Médecin et acte requis'}), 400

        # Vérifier doublon
        if id_convention:
            cursor.execute("""
                SELECT id FROM kt_medecin_tarifs
                WHERE id_doctor = %s AND id_acte = %s AND id_convention = %s AND est_urgence = %s
            """, (id_doctor, id_acte, id_convention, est_urgence))
        else:
            cursor.execute("""
                SELECT id FROM kt_medecin_tarifs
                WHERE id_doctor = %s AND id_acte = %s AND id_convention IS NULL AND est_urgence = %s
            """, (id_doctor, id_acte, est_urgence))

        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE kt_medecin_tarifs
                SET prix = %s, part_operateur = %s, est_actif = 1,
                    updated_by = %s, updated_at = NOW()
                WHERE id = %s
            """, (prix, part_operateur, g.user['id_personnel'], existing['id']))
            msg = 'Tarif KT médecin mis à jour'
        else:
            cursor.execute("""
                INSERT INTO kt_medecin_tarifs
                (id_doctor, id_acte, id_convention, est_urgence, prix, part_operateur, est_actif, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, 1, %s)
            """, (id_doctor, id_acte, id_convention, est_urgence, prix, part_operateur, g.user['id_personnel']))
            msg = 'Tarif KT médecin ajouté'

        connection.commit()
        return jsonify({'success': True, 'message': msg})

    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur api_tarifs_kt_add: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/gestion_medecins/tarifs_kt/<int:id>/delete', methods=['POST'])
@login_required
def api_tarifs_kt_delete(id):
    """Supprimer un tarif KT (JSON)"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM kt_medecin_tarifs WHERE id = %s", (id,))
        connection.commit()
        return jsonify({'success': True, 'message': 'Tarif supprimé'})
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/gestion_medecins/tarifs_kt/<int:id>/toggle', methods=['POST'])
@login_required
def api_tarifs_kt_toggle(id):
    """Activer/Désactiver un tarif KT (JSON)"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            UPDATE kt_medecin_tarifs
            SET est_actif = IF(est_actif = 1, 0, 1),
                updated_by = %s, updated_at = NOW()
            WHERE id = %s
        """, (g.user['id_personnel'], id))
        connection.commit()
        return jsonify({'success': True, 'message': 'Statut mis à jour'})
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


# ========================================================================
# API - POURCENTAGE MÉDECIN INTERNE
# ========================================================================

@app.route('/api/gestion_medecins/pourcentage_medecin_interne/<int:id_doctor>', methods=['POST'])
@login_required
def api_admin_pourcentage_medecin_interne(id_doctor):
    """Met à jour le pourcentage médecin interne d'un médecin"""
    data = request.get_json()
    pourcentage = data.get('pourcentage')

    if pourcentage is None:
        return jsonify({'success': False, 'message': 'Pourcentage manquant'}), 400

    try:
        pourcentage = float(pourcentage)
        if pourcentage < 0 or pourcentage > 100:
            return jsonify({'success': False, 'message': 'Le pourcentage doit être entre 0 et 100'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Pourcentage invalide'}), 400

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            UPDATE doctors
            SET pourcentage_medecin_interne = %s
            WHERE id = %s
        """, (pourcentage, id_doctor))
        connection.commit()

        return jsonify({
            'success': True,
            'message': f'Pourcentage mis à jour: {pourcentage}%'
        })
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


# ========================================================================
# API - PLAFOND CONSOMMABLES MÉDECIN INTERNE
# ========================================================================

@app.route('/gestion_medecins/plafonds_medecins')
@login_required
def admin_plafonds_medecins():
    """Interface de gestion des plafonds de consommables par lot"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        # Récupérer tous les médecins (même logique que tarifs personnalisés)
        cursor.execute("""
            SELECT id, 
                   CONCAT(first_name, ' ', last_name) as name
            FROM doctors
            WHERE est_interne = 1
            ORDER BY last_name, first_name
        """)
        doctors = cursor.fetchall()

        # Récupérer la liste complète des produits
        cursor.execute("""
            SELECT id_produit, description, prix
            FROM produits
            ORDER BY description
        """)
        produits_list = cursor.fetchall()
        
        selected_doctor_id = request.args.get('doctor_id')
        
        return render_template(
                'gestion_medecins/medecin_plafonds_config.html',
            doctors=doctors,
            produits_list=produits_list,
            selected_doctor_id=int(selected_doctor_id) if selected_doctor_id else None
        )
    except Exception as e:
        app.logger.error(f"Erreur admin_plafonds_medecins: {str(e)}")
        flash(f'Erreur: {str(e)}', 'danger')
        return redirect(url_for('admin_tarifs_personnalises'))
    finally:
        if cursor: cursor.close()
        if connection: connection.close()



@app.route('/api/gestion_medecins/plafond_consommables_mi/<int:id_doctor>', methods=['GET'])
@login_required
def api_plafond_consommables_mi_list(id_doctor):
    """Liste les plafonds de consommables pour un médecin interne"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            SELECT pc.id, pc.id_produit, pc.quantite_max, pc.est_actif,
                   p.description as produit_nom, p.prix as prix_unitaire
            FROM medecin_interne_plafond_consommables pc
            JOIN produits p ON pc.id_produit = p.id_produit
            WHERE pc.id_doctor = %s
            ORDER BY p.description
        """, (id_doctor,))
        plafonds = cursor.fetchall()
        for pl in plafonds:
            pl['prix_unitaire'] = float(pl['prix_unitaire']) if pl['prix_unitaire'] else 0
        return jsonify({'success': True, 'plafonds': plafonds})
    finally:
        cursor.close()
        connection.close()


@app.route('/api/gestion_medecins/plafond_consommables_mi', methods=['POST'])
@login_required
def api_plafond_consommables_mi_save():
    """Ajouter/mettre à jour les plafonds de consommables d'un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        data = request.get_json()
        id_doctor = data.get('id_doctor')
        produits = data.get('produits', [])  # [{id_produit, quantite_max}, ...]

        if not id_doctor:
            return jsonify({'success': False, 'message': 'Médecin requis'}), 400

        # Supprimer les anciens plafonds de ce médecin
        cursor.execute("""
            DELETE FROM medecin_interne_plafond_consommables
            WHERE id_doctor = %s
        """, (id_doctor,))

        # Insérer les nouveaux
        for prod in produits:
            id_produit = prod.get('id_produit')
            quantite_max = int(prod.get('quantite_max', 1))
            if id_produit and quantite_max > 0:
                cursor.execute("""
                    INSERT INTO medecin_interne_plafond_consommables
                    (id_doctor, id_produit, quantite_max, created_by)
                    VALUES (%s, %s, %s, %s)
                """, (id_doctor, id_produit, quantite_max, g.user['id_personnel']))

        connection.commit()
        return jsonify({
            'success': True,
            'message': f'{len(produits)} plafond(s) configuré(s)'
        })

    except Exception as e:
        connection.rollback()
        app.logger.error(f"Erreur plafond_consommables_mi_save: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()


@app.route('/api/gestion_medecins/plafond_consommables_mi/<int:id>/delete', methods=['POST'])
@login_required
def api_plafond_consommables_mi_delete(id):
    """Supprimer un plafond de consommable"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM medecin_interne_plafond_consommables WHERE id = %s", (id,))
        connection.commit()
        return jsonify({'success': True, 'message': 'Plafond supprimé'})
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        connection.close()