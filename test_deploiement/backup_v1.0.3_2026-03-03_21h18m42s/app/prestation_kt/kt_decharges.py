import io
import json
import os
from datetime import datetime
from decimal import Decimal

import qrcode
from flask import request, redirect, url_for, render_template, g, flash, jsonify, current_app, make_response
from qrcode.main import QRCode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required


def generer_numero_decharge():
    """Génère un numéro de décharge unique au format DECH-KT-YYYYMM-XXX"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    prefix = f"DECH-KT-{datetime.now().strftime('%Y%m')}"
    
    cursor.execute("""
        SELECT numero_decharge 
        FROM kt_decharges_paiement 
        WHERE numero_decharge LIKE %s 
        ORDER BY id_decharge DESC 
        LIMIT 1
    """, (f"{prefix}%",))
    
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    
    if result:
        last_num = int(result['numero_decharge'].split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1
    
    return f"{prefix}-{new_num:03d}"


@app.route('/kt_decharges')
@login_required
@handle_errors()

def kt_decharges():
    """Liste des décharges KT avec traçabilité"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Filtres
        statut_filter = request.args.get('statut', 'all')
        doctor_filter = request.args.get('doctor', 'all')
        
        query = """
            SELECT 
                d.*,
                CONCAT(p_createur.prenom, ' ', p_createur.nom) as createur,
                CONCAT(p_modif.prenom, ' ', p_modif.nom) as modificateur
            FROM v_kt_decharges_completes d
            LEFT JOIN personnel p_createur ON d.id_createur = p_createur.id_personnel
            LEFT JOIN personnel p_modif ON d.id_modificateur = p_modif.id_personnel
            INNER JOIN doctors doc ON d.id_doctor = doc.id
            WHERE doc.id_specialty IN (11, 19, 20)
        """
        params = []
        
        if statut_filter != 'all':
            query += " AND d.statut = %s"
            params.append(statut_filter)
        
        if doctor_filter != 'all':
            query += " AND d.id_doctor = %s"
            params.append(doctor_filter)
        
        query += " ORDER BY d.date_decharge DESC, d.id_decharge DESC"
        
        cursor.execute(query, params)
        decharges = cursor.fetchall()
        
        # Liste des médecins pour le filtre
        cursor.execute("""
            SELECT id, CONCAT(first_name, ' ', last_name) as name
            FROM doctors
            WHERE id_specialty IN (11, 19, 20)
            ORDER BY first_name, last_name
        """)
        doctors = cursor.fetchall()
        
        return render_template(
            'prestation_kt/kt_decharges_list.html',
            decharges=decharges,
            doctors=doctors,
            title="Décharges de Paiement KT",
            user=g.user
        )
    
    finally:
        cursor.close()
        connection.close()


@app.route('/api/kt_dossiers_non_decharges/<int:id_doctor>')
@login_required
@handle_errors()
def api_kt_dossiers_non_decharges(id_doctor):
    """Retourne les dossiers non déchargés d'un médecin"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT 
                kdp.id_dossier,
                kdp.patient,
                kdp.acte_date,
                COALESCE(kdp.part_operateur, 0) as part_operateur,
                COALESCE(kdp.part_operateur_up_medecin, 0) as part_operateur_up_medecin,
                COALESCE(kdp.part_operateur_up_clinique, 0) as part_operateur_up_clinique,
                (COALESCE(kdp.part_operateur, 0)) as montant_total,
                GROUP_CONCAT(
                    CASE 
                        WHEN a.nb > 1 THEN CONCAT('(x', a.nb, ') ', a.name_acte_kt)
                        ELSE a.name_acte_kt
                    END
                    ORDER BY a.name_acte_kt
                    SEPARATOR ', '
                ) as actes
            FROM kt_dossier_patient kdp
            LEFT JOIN (
                SELECT 
                    dak.id_dossier,
                    ak.name_acte_kt,
                    COUNT(*) as nb
                FROM kt_dossier_actes dak
                LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
                GROUP BY dak.id_dossier, ak.name_acte_kt
            ) a ON kdp.id_dossier = a.id_dossier
            WHERE kdp.id_doctor = %s
              AND kdp.id_dossier NOT IN (
                -- ✅ MODIFIÉ : Exclure uniquement les dossiers des décharges NON ANNULÉES
                SELECT dd.id_dossier
                FROM kt_decharges_dossiers dd
                         JOIN kt_decharges_paiement d ON dd.id_decharge = d.id_decharge
                WHERE d.statut != 'ANNULEE')
              AND (kdp.part_operateur - COALESCE(kdp.payment, 0)) > 0
            GROUP BY kdp.id_dossier
            ORDER BY kdp.acte_date DESC
        """, (id_doctor,))
        
        dossiers = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'dossiers': [{
                'id_dossier': d['id_dossier'],
                'patient': d['patient'],
                'acte_date': d['acte_date'].strftime('%d/%m/%Y') if d['acte_date'] else '',
                'actes': d['actes'] or '',
                'montant_total': float(d['montant_total']),
                'part_operateur_up_medecin': float(d['part_operateur_up_medecin']),
                'part_operateur_up_clinique': float(d['part_operateur_up_clinique'])
            } for d in dossiers]
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        cursor.close()
        connection.close()


@app.route('/creer_decharge_kt', methods=['POST'])
@login_required
@handle_errors()

def creer_decharge_kt():
    """Crée une nouvelle décharge avec dossiers sélectionnés et traçabilité"""
    try:
        id_doctor = request.form.get('id_doctor')
        date_decharge = request.form.get('date_decharge')
        observations = request.form.get('observations', '')
        dossiers_ids = request.form.getlist('dossiers[]')
        
        if not id_doctor or not date_decharge or not dossiers_ids:
            flash("Veuillez remplir tous les champs obligatoires et sélectionner au moins un dossier.", "danger")
            return redirect(url_for('kt_situation_medecin'))
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Calculer le montant total
        placeholders = ','.join(['%s'] * len(dossiers_ids))
        cursor.execute(f"""
            SELECT SUM(part_operateur) as total
            FROM kt_dossier_patient
            WHERE id_dossier IN ({placeholders})
              AND id_doctor = %s
        """, dossiers_ids + [id_doctor])
        
        result = cursor.fetchone()
        montant_total = Decimal(str(result['total'])) if result['total'] else Decimal('0')
        
        if montant_total <= 0:
            flash("Montant total invalide.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('kt_situation_medecin'))
        
        # Générer numéro de décharge
        numero_decharge = generer_numero_decharge()
        
        # Insérer la décharge avec traçabilité
        cursor.execute("""
            INSERT INTO kt_decharges_paiement 
            (id_doctor, numero_decharge, date_decharge, montant_total, 
             montant_restant, observations, id_createur, date_creation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (id_doctor, numero_decharge, date_decharge, montant_total,
              montant_total, observations, g.user['id_personnel']))
        
        connection.commit()
        id_decharge = cursor.lastrowid
        
        # Insérer les dossiers liés
        for id_dossier in dossiers_ids:
            cursor.execute("""
                SELECT part_operateur
                FROM kt_dossier_patient
                WHERE id_dossier = %s
            """, (id_dossier,))
            
            dossier = cursor.fetchone()
            if dossier:
                cursor.execute("""
                    INSERT INTO kt_decharges_dossiers 
                    (id_decharge, id_dossier, montant_dossier)
                    VALUES (%s, %s, %s)
                """, (id_decharge, id_dossier, dossier['part_operateur']))
        
        connection.commit()
        
        flash(f"Décharge {numero_decharge} créée avec succès pour un montant de {montant_total} DA.", "success")
        return redirect(url_for('kt_decharges'))
    
    except Exception as e:
        if connection:
            connection.rollback()
        flash(f"Erreur lors de la création de la décharge : {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(url_for('kt_situation_medecin'))
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route( '/annuler_decharge_kt/<int:id_decharge>', methods = [ 'POST' ] )
@login_required
@handle_errors()

def annuler_decharge_kt(id_decharge):
    """Annule une décharge avec traçabilité complète"""
    try:
        raison_annulation = request.form.get('raison_annulation', '')

        if not raison_annulation:
            flash("La raison d'annulation est obligatoire.", "danger")
            return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))

        connection = get_db_connection()
        cursor = connection.cursor()

        # Vérifier que la décharge existe et n'est pas déjà annulée
        cursor.execute("""
            SELECT statut, numero_decharge, montant_paye
            FROM kt_decharges_paiement
            WHERE id_decharge = %s
        """, (id_decharge,))

        decharge = cursor.fetchone()

        if not decharge:
            flash("Décharge non trouvée.", "danger")
            return redirect(url_for('kt_decharges'))

        if decharge['statut'] == 'ANNULEE':
            flash("Cette décharge est déjà annulée.", "warning")
            return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))

        # ✅ NOUVEAU : Récupérer le montant payé via les tranches ACTIVES
        cursor.execute("""
            SELECT COALESCE(SUM(montant_tranche), 0) as total_paye_actif
            FROM kt_decharges_tranches
            WHERE id_decharge = %s
              AND statut = 'ACTIVE'
        """, (id_decharge,))

        montant_paye_actif = Decimal(str(cursor.fetchone()['total_paye_actif']))

        # ✅ NOUVEAU : Récupérer les dossiers et ajuster leur payment
        cursor.execute("""
            SELECT dd.id_dossier,
                   dd.montant_dossier,
                   COALESCE(kdp.payment, 0) as payment_actuel,
                   d.montant_total
            FROM kt_decharges_dossiers dd
            JOIN kt_dossier_patient kdp ON dd.id_dossier = kdp.id_dossier
            JOIN kt_decharges_paiement d ON dd.id_decharge = d.id_decharge
            WHERE dd.id_decharge = %s
        """, (id_decharge,))

        dossiers = cursor.fetchall()

        if dossiers and montant_paye_actif > 0:
            # ✅ MODIFICATION FIFO : Annulation selon la logique LIFO (Last-In, First-Out)
            # On retire l'argent en commençant par les dossiers les plus récents (qui ont théoriquement reçu l'argent en dernier)
            # pour préserver le paiement des dossiers les plus anciens.
            
            # Trier les dossiers du plus récent au plus ancien
            # Note: Si `dossiers` n'est pas déjà trié correctement par la requête, on pourrait le faire en python, 
            # mais ici on va modifier la requête SQL pour s'en assurer.
            pass  # La logique est déplacée dans la modification de la requête ci-dessous
            
        # Refaire la requête avec le bon tri pour l'annulation (DESC)
        cursor.execute("""
            SELECT dd.id_dossier,
                   COALESCE(kdp.payment, 0) as payment_actuel
            FROM kt_decharges_dossiers dd
            JOIN kt_dossier_patient kdp ON dd.id_dossier = kdp.id_dossier
            WHERE dd.id_decharge = %s
            ORDER BY kdp.acte_date DESC, kdp.id_dossier DESC
        """, (id_decharge,))
        
        dossiers_sorted = cursor.fetchall()
        
        reste_a_annuler = montant_paye_actif
        
        for dossier in dossiers_sorted:
            if reste_a_annuler <= 0:
                break
                
            payment_actuel = Decimal(str(dossier['payment_actuel']))
            
            if payment_actuel > 0:
                # On retire ce qu'on peut de ce dossier (soit tout ce qu'il a, soit le reste à annuler)
                retrait_dossier = min(reste_a_annuler, payment_actuel)
                
                nouveau_payment = payment_actuel - retrait_dossier
                
                cursor.execute("""
                    UPDATE kt_dossier_patient
                    SET payment = %s
                    WHERE id_dossier = %s
                """, (nouveau_payment, dossier['id_dossier']))
                
                reste_a_annuler -= retrait_dossier

        # Annuler toutes les tranches de la décharge
        cursor.execute("""
            UPDATE kt_decharges_tranches
            SET statut = 'ANNULEE',
                date_annulation = NOW(),
                id_annulateur = %s,
                raison_annulation = %s
            WHERE id_decharge = %s
              AND statut = 'ACTIVE'
        """, (g.user['id_personnel'], raison_annulation, id_decharge))

        # Annuler la décharge
        cursor.execute("""
            UPDATE kt_decharges_paiement
            SET statut = 'ANNULEE',
                date_annulation = NOW(),
                id_annulateur = %s,
                raison_annulation = %s,
                id_modificateur = %s,
                date_modification = NOW()
            WHERE id_decharge = %s
        """, (g.user['id_personnel'], raison_annulation, g.user['id_personnel'], id_decharge))

        # ✅ IMPORTANT : NE PAS supprimer les dossiers pour garder la traçabilité
        # Les dossiers restent dans kt_decharges_dossiers avec statut ANNULEE de la décharge

        connection.commit()

        flash(f"Décharge {decharge['numero_decharge']} annulée avec succès. Soldes des dossiers mis à jour.", "success")
        return redirect(url_for('kt_decharges'))

    except Exception as e:
        if connection:
            connection.rollback()
        flash(f"Erreur lors de l'annulation : {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route( '/annuler_tranche_kt/<int:id_tranche>', methods = [ 'POST' ] )
@login_required
@handle_errors()

def annuler_tranche_kt( id_tranche ):
    """Annule une tranche de paiement avec traçabilité au lieu de la supprimer"""
    try:
        raison_annulation = request.form.get('raison_annulation', '')

        if not raison_annulation:
            flash("La raison d'annulation est obligatoire.", "danger")
            return redirect(request.referrer or url_for('kt_decharges'))

        connection = get_db_connection()
        cursor = connection.cursor()

        # Récupérer info de la tranche
        cursor.execute("""
            SELECT id_decharge, montant_tranche, statut
            FROM kt_decharges_tranches
            WHERE id_tranche = %s
        """, (id_tranche,) )

        tranche = cursor.fetchone()

        if not tranche:
            flash("Tranche non trouvée.", "danger")
            return redirect(url_for('kt_decharges'))

        if tranche['statut'] == 'ANNULEE':
            flash("Cette tranche est déjà annulée.", "warning")
            return redirect(url_for('kt_decharge_detail', id_decharge=tranche['id_decharge']))

        id_decharge = tranche['id_decharge']
        montant_tranche = Decimal(str(tranche['montant_tranche']))

        # ✅ FIFO LOGIC : Annulation d'une tranche (LIFO Removal)
        # On doit retirer le montant de la tranche en partant des dossiers les plus récents (payés en dernier)
        cursor.execute("""
            SELECT dd.id_dossier,
                   COALESCE(kdp.payment, 0) as payment_actuel
            FROM kt_decharges_dossiers dd
            JOIN kt_dossier_patient kdp ON dd.id_dossier = kdp.id_dossier
            WHERE dd.id_decharge = %s
            ORDER BY kdp.acte_date DESC, kdp.id_dossier DESC
        """, (id_decharge,))

        dossiers = cursor.fetchall()

        if dossiers:
            reste_a_annuler = montant_tranche

            for dossier in dossiers:
                if reste_a_annuler <= 0:
                    break

                payment_actuel = Decimal(str(dossier['payment_actuel']))

                if payment_actuel > 0:
                    # On retire le maximum possible de ce dossier
                    retrait_dossier = min(reste_a_annuler, payment_actuel)
                    
                    nouveau_payment = payment_actuel - retrait_dossier

                    cursor.execute("""
                        UPDATE kt_dossier_patient
                        SET payment = %s
                        WHERE id_dossier = %s
                    """, (nouveau_payment, dossier['id_dossier']))

                    reste_a_annuler -= retrait_dossier

        # Annuler la tranche
        cursor.execute("""
            UPDATE kt_decharges_tranches
            SET statut = 'ANNULEE',
                date_annulation = NOW(),
                id_annulateur = %s,
                raison_annulation = %s
            WHERE id_tranche = %s
        """, (g.user[ 'id_personnel' ], raison_annulation, id_tranche) )

        # Recalculer les montants
        cursor.execute("""
            SELECT COALESCE(SUM(montant_tranche), 0) as total_paye
            FROM kt_decharges_tranches
            WHERE id_decharge = %s
              AND statut = 'ACTIVE'
        """, (id_decharge,) )

        total_paye = Decimal(str(cursor.fetchone()['total_paye']))

        cursor.execute("""
            SELECT montant_total FROM kt_decharges_paiement
            WHERE id_decharge = %s
        """, (id_decharge,) )

        montant_total = Decimal(str(cursor.fetchone()['montant_total']))
        montant_restant = montant_total - total_paye

        if montant_restant >= montant_total:
            statut = 'EN_COURS'
        elif montant_restant > 0:
            statut = 'PARTIEL'
        else:
            statut = 'SOLDE'

        cursor.execute("""
            UPDATE kt_decharges_paiement
            SET montant_paye = %s,
                montant_restant = %s,
                statut = %s,
                id_modificateur = %s,
                date_modification = NOW()
            WHERE id_decharge = %s
        """, (total_paye, montant_restant, statut, g.user[ 'id_personnel' ], id_decharge) )

        connection.commit()

        flash( f"Tranche de {montant_tranche} DA annulée. Soldes des dossiers mis à jour.", "success" )
        return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))

    except Exception as e:
        if connection:
            connection.rollback()
        flash(f"Erreur : {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(url_for('kt_decharges'))

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.route('/kt_decharge_detail/<int:id_decharge>')
@handle_errors()
def kt_decharge_detail(id_decharge):
    """Détails d'une décharge avec traçabilité"""
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Informations de la décharge avec traçabilité complète
        cursor.execute("""
            SELECT 
                d.*,
                CONCAT(p_createur.prenom, ' ', p_createur.nom) as createur,
                CONCAT(p_modif.prenom, ' ', p_modif.nom) as modificateur,
                CONCAT(p_annulateur.prenom, ' ', p_annulateur.nom) as annulateur
            FROM v_kt_decharges_completes d
            LEFT JOIN personnel p_createur ON d.id_createur = p_createur.id_personnel
            LEFT JOIN personnel p_modif ON d.id_modificateur = p_modif.id_personnel
            LEFT JOIN personnel p_annulateur ON d.id_annulateur = p_annulateur.id_personnel
            WHERE d.id_decharge = %s
        """, (id_decharge,))
        
        decharge = cursor.fetchone()
        
        if not decharge:
            flash("Décharge non trouvée.", "danger")
            return redirect(url_for('kt_decharges'))
        
        # Dossiers de la décharge
        cursor.execute("""
            SELECT 
                dd.id_dossier,
                dd.montant_dossier,
                kdp.patient,
                kdp.acte_date,
                GROUP_CONCAT(
                    ak.name_acte_kt
                    ORDER BY ak.name_acte_kt
                    SEPARATOR ', '
                ) as actes
            FROM kt_decharges_dossiers dd
            JOIN kt_dossier_patient kdp ON dd.id_dossier = kdp.id_dossier
            LEFT JOIN kt_dossier_actes dak ON kdp.id_dossier = dak.id_dossier
            LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
            WHERE dd.id_decharge = %s
            GROUP BY dd.id_dossier
            ORDER BY kdp.acte_date DESC
        """, (id_decharge,))
        
        dossiers = cursor.fetchall()
        
        # Tranches de paiement (TOUTES, y compris annulées) avec traçabilité complète
        cursor.execute("""
            SELECT 
                dt.*,
                CONCAT(p_createur.prenom, ' ', p_createur.nom) as createur,
                CONCAT(p_annulateur.prenom, ' ', p_annulateur.nom) as annulateur
            FROM kt_decharges_tranches dt
            LEFT JOIN personnel p_createur ON dt.id_createur = p_createur.id_personnel
            LEFT JOIN personnel p_annulateur ON dt.id_annulateur = p_annulateur.id_personnel
            WHERE dt.id_decharge = %s
            ORDER BY dt.numero_tranche
        """, (id_decharge,))
        
        tranches = cursor.fetchall()
        
        return render_template(
            'prestation_kt/kt_decharge_detail.html',
            decharge=decharge,
            dossiers=dossiers,
            tranches=tranches,
            title=f"Décharge {decharge['numero_decharge']}",
            user=g.user
        )
    
    finally:
        cursor.close()
        connection.close()


@app.route('/kt_decharge_pdf/<int:id_decharge>')
@login_required
@handle_errors()

def kt_decharge_pdf(id_decharge):
    """Génère le PDF d'une décharge"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Récupérer toutes les informations nécessaires avec traçabilité
        cursor.execute("""
            SELECT 
                d.*,
                CONCAT(p_createur.prenom, ' ', p_createur.nom) as createur,
                CONCAT(p_modif.prenom, ' ', p_modif.nom) as modificateur
            FROM v_kt_decharges_completes d
            LEFT JOIN personnel p_createur ON d.id_createur = p_createur.id_personnel
            LEFT JOIN personnel p_modif ON d.id_modificateur = p_modif.id_personnel
            WHERE d.id_decharge = %s
        """, (id_decharge,))

        decharge = cursor.fetchone()

        if not decharge:
            flash("Décharge non trouvée.", "danger")
            return redirect(url_for('kt_decharges'))

        # Dossiers
        cursor.execute("""
            SELECT 
                dd.id_dossier,
                dd.montant_dossier,
                kdp.patient,
                kdp.acte_date,
                GROUP_CONCAT(
                    ak.name_acte_kt
                    ORDER BY ak.name_acte_kt
                    SEPARATOR ', '
                ) as actes
            FROM kt_decharges_dossiers dd
            JOIN kt_dossier_patient kdp ON dd.id_dossier = kdp.id_dossier
            LEFT JOIN kt_dossier_actes dak ON kdp.id_dossier = dak.id_dossier
            LEFT JOIN kt_actes ak ON dak.id_acte = ak.id_acte
            WHERE dd.id_decharge = %s
            GROUP BY dd.id_dossier
            ORDER BY kdp.acte_date DESC
        """, (id_decharge,))

        dossiers = cursor.fetchall()

        # Tranches
        cursor.execute("""
            SELECT 
                dt.*,
                CONCAT(p.prenom, ' ', p.nom) as createur
            FROM kt_decharges_tranches dt
            LEFT JOIN personnel p ON dt.id_createur = p.id_personnel
            WHERE dt.id_decharge = %s
            ORDER BY dt.numero_tranche
        """, (id_decharge,))

        tranches = cursor.fetchall()


        return generer_pdf_decharge(decharge, dossiers, tranches)

    except Exception as e:
        flash(f"Erreur lors de la génération du PDF : {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))

    finally:
        cursor.close()
        connection.close()


@app.route('/ajouter_tranche_kt/<int:id_decharge>', methods=['POST'])
@login_required
@handle_errors()

def ajouter_tranche_kt(id_decharge):
    """Ajoute une tranche de paiement avec traçabilité et met à jour les dossiers"""
    try:
        montant_tranche = Decimal(request.form.get('montant_tranche', '0'))
        date_paiement = request.form.get('date_paiement')
        mode_paiement = request.form.get('mode_paiement', 'ESPECE')
        reference_paiement = request.form.get('reference_paiement', '')
        observations = request.form.get('observations', '')
        
        if montant_tranche <= 0 or not date_paiement:
            flash("Montant et date sont obligatoires.", "danger")
            return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))
        
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Vérifier le montant restant
        cursor.execute("""
            SELECT montant_restant, montant_total FROM kt_decharges_paiement
            WHERE id_decharge = %s
        """, (id_decharge,))
        
        decharge = cursor.fetchone()
        
        if not decharge:
            flash("Décharge non trouvée.", "danger")
            return redirect(url_for('kt_decharges'))
        
        if montant_tranche > Decimal(str(decharge['montant_restant'])):
            flash("Le montant de la tranche dépasse le montant restant.", "danger")
            return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))
        
        # Numéro de tranche
        cursor.execute("""
            SELECT COALESCE(MAX(numero_tranche), 0) + 1 as next_num
            FROM kt_decharges_tranches
            WHERE id_decharge = %s
        """, (id_decharge,))
        
        numero_tranche = cursor.fetchone()['next_num']
        
        # Insérer la tranche avec traçabilité
        cursor.execute("""
            INSERT INTO kt_decharges_tranches
            (id_decharge, numero_tranche, montant_tranche, date_paiement,
             mode_paiement, reference_paiement, observations, id_createur, date_creation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (id_decharge, numero_tranche, montant_tranche, date_paiement,
              mode_paiement, reference_paiement, observations, g.user['id_personnel']))
        
        # ✅ FIFO LOGIC : Répartition séquentielle par date (Ancien -> Récent)
        # On récupère les dossiers triés par date croissante
        cursor.execute("""
            SELECT dd.id_dossier, 
                   COALESCE(kdp.payment, 0) as payment_actuel,
                   COALESCE(kdp.part_operateur, 0) as part_operateur
            FROM kt_decharges_dossiers dd
            JOIN kt_dossier_patient kdp ON dd.id_dossier = kdp.id_dossier
            WHERE dd.id_decharge = %s
            ORDER BY kdp.acte_date ASC, kdp.id_dossier ASC
        """, (id_decharge,))

        dossiers = cursor.fetchall()

        reste_a_distribuer = montant_tranche

        for dossier in dossiers:
            if reste_a_distribuer <= 0:
                break

            payment_actuel = Decimal(str(dossier['payment_actuel']))
            part_operateur = Decimal(str(dossier['part_operateur']))
            
            # Calculer combien il reste à payer sur ce dossier
            reste_a_payer_dossier = max(Decimal('0'), part_operateur - payment_actuel)
            
            if reste_a_payer_dossier > 0:
                # On paie soit le reste du montant à distribuer, soit le reste à payer du dossier (le plus petit des deux)
                montant_pour_ce_dossier = min(reste_a_distribuer, reste_a_payer_dossier)
                
                nouveau_payment = payment_actuel + montant_pour_ce_dossier
                
                # Sécurité supplémentaire : s'assurer que le paiement ne dépasse jamais le part_operateur
                if nouveau_payment > part_operateur:
                    nouveau_payment = part_operateur
                    montant_pour_ce_dossier = part_operateur - payment_actuel
                
                cursor.execute("""
                    UPDATE kt_dossier_patient
                    SET payment = %s
                    WHERE id_dossier = %s
                """, (nouveau_payment, dossier['id_dossier']))
                
                reste_a_distribuer -= montant_pour_ce_dossier

        # Mettre à jour la décharge avec traçabilité de modification
        cursor.execute("""
            SELECT montant_total, montant_paye 
            FROM kt_decharges_paiement 
            WHERE id_decharge = %s
        """, (id_decharge,))
        
        current = cursor.fetchone()
        montant_total = Decimal(str(current['montant_total']))
        montant_paye = Decimal(str(current['montant_paye'])) + montant_tranche
        montant_restant = montant_total - montant_paye
        
        # Déterminer le statut
        if montant_restant <= 0:
            statut = 'SOLDE'
        elif montant_paye > 0:
            statut = 'PARTIEL'
        else:
            statut = 'EN_COURS'
        
        cursor.execute("""
            UPDATE kt_decharges_paiement
            SET montant_paye = %s,
                montant_restant = %s,
                statut = %s,
                id_modificateur = %s,
                date_modification = NOW()
            WHERE id_decharge = %s
        """, (montant_paye, montant_restant, statut, g.user['id_personnel'], id_decharge))
        
        connection.commit()
        
        flash(f"Tranche de {montant_tranche} DA ajoutée avec succès. Soldes des dossiers mis à jour.", "success")
        return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))
    
    except Exception as e:
        if connection:
            connection.rollback()
        flash(f"Erreur : {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(url_for('kt_decharge_detail', id_decharge=id_decharge))
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()



def generer_qr_code_decharge( decharge, base_url = None ):
    """
    Génère un QR Code avec URL directe pour vérification instantanée

    Args:
        decharge: Dictionnaire contenant les informations de la décharge
        base_url: URL de base de l'application (requis)

    Returns:
        Image QR Code ou None si erreur
    """


    try:
        # Utiliser l'URL de base ou une valeur par défaut
        if not base_url:
            base_url = current_app.config.get('BASE_URL')

        # Créer un token de vérification sécurisé
        import hashlib
        import base64

        # Données à encoder dans l'URL
        verification_data = {
            'n': decharge['numero_decharge'],
            't': float(decharge.get('montant_total', 0.0)),
            'p': float(decharge.get('montant_paye', 0.0)),
            'r': float(decharge.get('montant_restant', 0.0)),
            's': decharge.get('statut', ''),
            'd': decharge.get('date_decharge').strftime('%Y-%m-%d') if decharge.get('date_decharge') else '',
            'ts': datetime.now().strftime('%Y%m%d%H%M%S')
        }

        # Convertir en JSON compact
        json_data = json.dumps(verification_data, ensure_ascii=False, separators=(',', ':'))

        # Encoder en base64 pour l'URL
        encoded_data = base64.urlsafe_b64encode(json_data.encode('utf-8')).decode('utf-8')

        # Générer hash de sécurité
        secret_key = current_app.config.get('SECRET_KEY', 'default_secret_key')
        security_hash = hashlib.sha256(
            f"{json_data}{secret_key}".encode('utf-8')
        ).hexdigest()[:16]

        # Construire l'URL complète
        verification_url = f"{base_url}/verifier_decharge?data={encoded_data}&hash={security_hash}"

        # Configuration optimale du QR Code pour URL
        qr = QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=2,
        )

        qr.add_data(verification_url)
        qr.make(fit=True)

        # Génération de l'image
        img_qr = qr.make_image(
            fill_color="#000000",
                back_color = "white"
                )

        # Conversion en buffer pour ReportLab
        qr_buf = io.BytesIO()
        img_qr.save( qr_buf, format = 'PNG' )
        qr_buf.seek( 0 )

        return qr_buf

    except Exception as e:
        # Log de l'erreur pour debugging
        print( f"Erreur génération QR Code: {str( e )}" )
        import traceback

        traceback.print_exc()
        return None


def generer_pdf_decharge( decharge, dossiers, tranches ):
    """
    PDF compact avec QR code amélioré
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Décharge {decharge['numero_decharge']}"
    )

    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=18, textColor=colors.HexColor('#667eea'),
        spaceAfter=8, alignment=TA_CENTER, fontName='Helvetica-Bold'
    )
    style_sous_titre = ParagraphStyle(
        'CustomSubtitle', parent=styles['Heading2'],
        fontSize=11, textColor=colors.HexColor('#764ba2'),
        spaceAfter=6, spaceBefore=6, fontName='Helvetica-Bold'
    )
    style_normal = ParagraphStyle(
        'CustomNormal', parent=styles['Normal'],
        fontSize=9, spaceAfter=4, fontName='Helvetica'
    )
    style_info = ParagraphStyle(
        'CustomInfo', parent=styles['Normal'],
        fontSize=8.5, textColor=colors.HexColor('#6c757d'), fontName='Helvetica'
    )

    elements = []

    # ========== HEADER avec QR Code amélioré ==========
    logo_path = os.path.join(current_app.root_path, 'static', 'images', 'entet_inaya.png')

    # Génération QR Code amélioré
    qr_size = 2.8 * cm  # Taille légèrement augmentée pour meilleure lisibilité
    qr_flowable = None

    # Récupérer l'URL de base depuis la config Flask (optionnel)
    base_url = current_app.config.get('BASE_URL', 'http://localhost:8080')

    qr_buffer = generer_qr_code_decharge(decharge, base_url)
    if qr_buffer:
        qr_size = 2.8 * cm
        qr_flowable = Image(qr_buffer, width=qr_size, height=qr_size)
    # Construction du header
    cells = []
    col_widths = []

    # Logo
    if os.path.exists(logo_path):
        cell_logo = Image(logo_path, width=8 * cm, height=2 * cm)
        cells.append(cell_logo)
        col_widths.append(8.5 * cm)

    # Informations centrales
    info_centre = [
        Paragraph("<b>CLINIQUE INAYA</b>",
                 ParagraphStyle('ClinicName', parent=style_info, fontSize=11, textColor=colors.HexColor('#667eea'))),
        Paragraph("Gestion des Décharges KT", style_info)
    ]
    cells.append(info_centre)
    col_widths.append(None)  # Expand

    # QR Code
    if qr_flowable:
        qr_cell = [
            qr_flowable,
            Paragraph('<para alignment="center"><font size="6">Scannez pour vérifier</font></para>',
                     style_info)
        ]
        cells.append(qr_cell)
        col_widths.append(qr_size + 0.4 * cm)

    header_table = Table([cells], colWidths=col_widths)
    header_table.setStyle(
        TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])
    )
    elements.append(header_table)
    elements.append(Spacer(1, 0.1 * cm))

    # Ligne de séparation
    line_table = Table([['']], colWidths=[doc.width], rowHeights=[0.09 * cm])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#667eea')),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 0.15 * cm))
    # ========== TITRE avec indication d'annulation ==========
    elements.append(Paragraph("DÉCHARGE DE PAIEMENT", style_titre))

    titre_decharge = f"<b>N° {decharge['numero_decharge']}</b>"
    if decharge.get('statut') == 'ANNULEE':
        titre_decharge += " - <font color='red'>ANNULÉE</font>"

    elements.append(Paragraph(titre_decharge,
                              ParagraphStyle('NumDecharge', parent=style_sous_titre, alignment=TA_CENTER,
                                             textColor=colors.HexColor('#667eea'))))
    elements.append(Spacer(1, 0.1 * cm))

    # ========== ALERTE ANNULATION si applicable ==========
    if decharge.get('statut') == 'ANNULEE':
        alert_data = [[
            Paragraph("<font color='red'><b>⚠ DÉCHARGE ANNULÉE</b></font>", style_normal),
            Paragraph(f"<b>Annulée le:</b> {decharge.get('date_annulation').strftime('%d/%m/%Y à %H:%M') if decharge.get('date_annulation') else '-'}", style_info),
            Paragraph(f"<b>Par:</b> {decharge.get('annulateur', '-')}", style_info),
        ]]
        alert_table = Table(alert_data, colWidths=[doc.width/3]*3)
        alert_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8d7da')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#721c24')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#f5c6cb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(alert_table)
        elements.append(Spacer(1, 0.15 * cm))

        if decharge.get('raison_annulation'):
            elements.append(Paragraph(f"<b>Raison:</b> {decharge['raison_annulation']}", style_normal))
            elements.append(Spacer(1, 0.15 * cm))

    # ========== INFORMATIONS GÉNÉRALES ==========
    elements.append(Paragraph("INFORMATIONS GÉNÉRALES", style_sous_titre))
    info_data = [
        ['Médecin:', f"Dr. {decharge.get('nom_medecin', '-')}" ],
        ['Spécialité:', decharge.get('name_specialty') or '-' ],
        ['Date de décharge:', decharge.get('date_decharge').strftime('%d/%m/%Y') if decharge.get('date_decharge') else '-' ],
        ['Nombre de dossiers:', str(decharge.get('nb_dossiers', 0)) ],
        ['Statut:', format_statut(decharge.get('statut')) ],
    ]
    info_table = Table(info_data, colWidths=[4.4 * cm, doc.width - 4.4 * cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e9ecef')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.15 * cm))

    # ========== DOSSIERS ==========
    if dossiers:
        elements.append(Paragraph("DOSSIERS INCLUS", style_sous_titre))
        dossiers_data = [['N° Dossier', 'Patient', 'Date Acte', 'Actes', 'Montant (DA)']]
        for dossier in dossiers:
            dossiers_data.append([
                str(dossier.get('id_dossier', '')),
                (dossier.get('patient') or '')[:28],
                dossier.get('acte_date').strftime('%d/%m/%Y') if dossier.get('acte_date') else '-',
                (dossier.get('actes') or '-')[:36],
                f"{float(dossier.get('montant_dossier', 0.0)):,.2f}".replace(',', ' ')
            ])
        total_dossiers = sum(float(d.get('montant_dossier', 0.0)) for d in dossiers)
        dossiers_data.append(['', '', '', 'TOTAL:', f"{total_dossiers:,.2f}".replace(',', ' ')])
        colw = [2.2 * cm, 4 * cm, 2.4 * cm, doc.width - (2.2+4+2.4)*cm - 2.6*cm, 2.6 * cm]
        dossiers_table = Table(dossiers_data, colWidths=colw)
        dossiers_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e9ecef')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fa')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(dossiers_table)
        elements.append(Spacer(1, 0.15 * cm))

    # ========== RÉSUMÉ FINANCIER ==========
    elements.append(Paragraph("RÉSUMÉ FINANCIER", style_sous_titre))
    montant_total = float(decharge.get('montant_total', 0.0))
    montant_paye = float(decharge.get('montant_paye', 0.0))
    montant_restant = float(decharge.get('montant_restant', 0.0))
    montant_annule = float(decharge.get('montant_annule', 0.0))

    finance_data = [
        ['Description', 'Montant (DA)'],
        ['Montant Total', f"{montant_total:,.2f}".replace(',', ' ')],
        ['Montant Payé (actif)', f"{montant_paye:,.2f}".replace(',', ' ')],
    ]

    if montant_annule > 0:
        finance_data.append(['Montant Annulé', f"{montant_annule:,.2f}".replace(',', ' ')])

    finance_data.append(['Montant Restant', f"{montant_restant:,.2f}".replace(',', ' ')])

    finance_table = Table(finance_data, colWidths=[doc.width * 0.65, doc.width * 0.35])

    style_list = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e9ecef')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]

    # Mettre en surbrillance la ligne "Montant Annulé" si elle existe
    if montant_annule > 0:
        annule_row = len(finance_data) - 2  # Avant-dernière ligne
        style_list.append(('BACKGROUND', (0, annule_row), (-1, annule_row), colors.HexColor('#fff3cd')))
        style_list.append(('TEXTCOLOR', (0, annule_row), (-1, annule_row), colors.HexColor('#856404')))

    finance_table.setStyle(TableStyle(style_list))
    elements.append(finance_table)
    elements.append(Spacer(1, 0.15 * cm))

    # ========== TRANCHES avec indication des annulations ==========
    if tranches:
        elements.append(Paragraph("HISTORIQUE DES PAIEMENTS", style_sous_titre))

        tranches_data = [['N°', 'Date', 'Montant (DA)', 'Mode', 'Statut', 'Référence']]

        for tranche in tranches:
            statut_display = "ACTIVE" if tranche.get('statut') == 'ACTIVE' else "ANNULÉE"

            # Formater le montant différemment si annulé
            montant_str = f"{float(tranche.get('montant_tranche', 0.0)):,.2f}".replace(',', ' ')
            if tranche.get('statut') == 'ANNULEE':
                montant_str = f"({montant_str})"  # Entre parenthèses pour montant annulé

            tranches_data.append([
                str(tranche.get('numero_tranche', '')),
                tranche.get('date_paiement').strftime('%d/%m/%Y') if tranche.get('date_paiement') else '-',
                montant_str,
                format_mode_paiement(tranche.get('mode_paiement')),
                statut_display,
                (tranche.get('reference_paiement') or '-')[:20]
            ])

            # Ajouter la raison d'annulation si disponible
            if tranche.get('statut') == 'ANNULEE' and tranche.get('raison_annulation'):
                tranches_data.append([
                    '',
                    '',
                    '',
                    Paragraph(f"<font size='7' color='red'>Raison: {tranche['raison_annulation'][:60]}</font>", style_info),
                    '',
                    ''
                ])

        tranches_table = Table(tranches_data,
                              colWidths=[1.4*cm, 2.4*cm, 3*cm, 3*cm, 2.5*cm, doc.width - (1.4+2.4+3+3+2.5)*cm])

        tranches_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#56ab2f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e9ecef')),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]

        # Colorer les lignes annulées
        for i, tranche in enumerate(tranches, 1):
            if tranche.get('statut') == 'ANNULEE':
                tranches_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fff3cd')))
                tranches_style.append(('TEXTCOLOR', (0, i), (-1, i), colors.HexColor('#856404')))

        tranches_table.setStyle(TableStyle(tranches_style))
        elements.append(tranches_table)
        elements.append(Spacer(1, 0.15 * cm))

    # ========== OBSERVATIONS ==========
    if decharge.get('observations'):
        elements.append(Paragraph("OBSERVATIONS", style_sous_titre))
        elements.append(Paragraph(decharge.get('observations', ''), style_normal))
        elements.append(Spacer(1, 0.15 * cm))

    # ========== TRAÇABILITÉ COMPLÈTE ==========
    elements.append(Paragraph("TRAÇABILITÉ", style_sous_titre))
    tracabilite_data = [
        ['Créé par:', decharge.get('createur', '-')],
        ['Date de création:', decharge.get('date_creation', datetime.now()).strftime('%d/%m/%Y %H:%M') if decharge.get('date_creation') else '-']
    ]

    if decharge.get('modificateur'):
        tracabilite_data.extend([
            ['Modifié par:', decharge.get('modificateur', '-')],
            ['Date de modification:', decharge.get('date_modification').strftime('%d/%m/%Y %H:%M') if decharge.get('date_modification') else '-']
        ])

    if decharge.get('statut') == 'ANNULEE':
        tracabilite_data.extend([
            ['Annulée par:', decharge.get('annulateur', '-')],
            ['Date d\'annulation:', decharge.get('date_annulation').strftime('%d/%m/%Y %H:%M') if decharge.get('date_annulation') else '-']
        ])

    trac_table = Table(tracabilite_data, colWidths=[4.4 * cm, doc.width - 4.4 * cm])
    trac_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f8f9fa')),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#e9ecef')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(trac_table)
    elements.append(Spacer(1, 0.2 * cm))

    # ========== FOOTER ==========
    footer_text = Paragraph(
        f'<para alignment="center"><font size="7" color="#6c757d">Document généré le {datetime.now().strftime("%d/%m/%Y %H:%M")} — Décharge N° {decharge["numero_decharge"]}</font></para>',
        style_info
    )
    elements.append(footer_text)

    # Build PDF
    doc.build(elements)

    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename="Decharge_{decharge["numero_decharge"]}.pdf"'
    return response


def format_statut( statut ):
    """Formate le statut pour l'affichage"""
    statuts = {
            'EN_COURS': 'En cours',
            'PARTIEL': 'Paiement partiel',
        'SOLDE': 'Soldé',
        'ANNULEE': 'Annulée'
            }
    return statuts.get( statut, statut )


def format_mode_paiement( mode ):
    """Formate le mode de paiement pour l'affichage"""
    modes = {
            'ESPECE': 'Espèce',
            'CHEQUE': 'Chèque',
            'VIREMENT': 'Virement',
            'AUTRE': 'Autre'
            }
    return modes.get( mode, mode )

@app.route( '/verifier_decharge' )
def page_verification_decharge():
    """
    Page publique de vérification de décharge via QR Code
    Accessible sans authentification pour permettre la vérification externe
    La page se charge automatiquement avec les paramètres de l'URL
    """
    return render_template( 'prestation_kt/verifier_decharge.html' )


@app.route( '/api/verifier_decharge', methods = [ 'POST' ] )
@handle_errors()
def verifier_decharge():
    """
    API de vérification de l'authenticité d'une décharge via données QR Code
    """
    connection = None
    cursor = None

    try:
        qr_data = request.get_json()

        # Validation des données reçues
        if not qr_data:
            return jsonify({
                'success': False,
                'error': 'Aucune donnée reçue'
            }), 400

        if qr_data.get('type') != 'DECHARGE_KT':
            return jsonify({
                'success': False,
                'error': 'Type de QR Code invalide'
            }), 400

        numero_decharge = qr_data.get('numero')

        if not numero_decharge:
            return jsonify({
                'success': False,
                'error': 'Numéro de décharge manquant'
            }), 400

        # Récupération des informations de la requête
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')

        # Vérification du hash de sécurité
        provided_hash = qr_data.get('hash')
        hash_valid = True

        if provided_hash:
            import hashlib
            import json

            # ⚠️ IMPORTANT: Reconstruire EXACTEMENT le même format que lors de la génération
            verification_data = {
                'n': qr_data.get('numero'),
                't': float(qr_data.get('montant_total', 0)),
                'p': float(qr_data.get('montant_paye', 0)),
                'r': float(qr_data.get('montant_restant', 0)),
                's': qr_data.get('statut', ''),
                'd': qr_data.get('date', ''),
                'ts': qr_data.get('timestamp', '')
            }

            json_data = json.dumps(verification_data, ensure_ascii=False, separators=(',', ':'))
            secret_key = current_app.config.get('SECRET_KEY', 'default_secret_key')
            expected_hash = hashlib.sha256(
                f"{json_data}{secret_key}".encode('utf-8')
            ).hexdigest()[:16]

            if provided_hash != expected_hash:
                hash_valid = False
                print(f"Hash fourni: {provided_hash}")
                print(f"Hash attendu: {expected_hash}")
                print(f"JSON data: {json_data}")

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT 
                d.numero_decharge,
                d.montant_total,
                d.montant_paye,
                d.montant_restant,
                d.statut,
                d.date_decharge,
                (SELECT COUNT(*) FROM kt_decharges_dossiers dd WHERE dd.id_decharge = d.id_decharge) as nb_dossiers,
                CONCAT(doc.first_name, ' ', doc.last_name) as medecin,
                spec.name_specialty
            FROM kt_decharges_paiement d
            LEFT JOIN doctors doc ON d.id_doctor = doc.id
            LEFT JOIN specialty spec ON doc.id_specialty = spec.id_specialty
            WHERE d.numero_decharge = %s
        """, (numero_decharge,))

        decharge_db = cursor.fetchone()

        # Variable pour stocker si la décharge est valide
        is_valid = False

        if not decharge_db:
            # Enregistrer la tentative de vérification échouée
            cursor.execute("""
                INSERT INTO kt_verifications_log 
                (numero_decharge, date_verification, ip_address, user_agent, is_valid)
                VALUES (%s, NOW(), %s, %s, 0)
            """, (numero_decharge, ip_address, user_agent))
            connection.commit()

            return jsonify({
                'success': False,
                'error': 'Décharge non trouvée dans la base de données',
                'valid': False
            }), 404

        # Vérification de cohérence des montants (tolérance de 0.01 DA)
        montant_total_ok = abs(
            float(decharge_db['montant_total']) - float(qr_data.get('montant_total', 0))
        ) < 0.01

        montant_paye_ok = abs(
            float(decharge_db['montant_paye']) - float(qr_data.get('montant_paye', 0))
        ) < 0.01

        montant_restant_ok = abs(
            float(decharge_db['montant_restant']) - float(qr_data.get('montant_restant', 0))
        ) < 0.01

        # Vérification du statut
        statut_ok = decharge_db['statut'] == qr_data.get('statut')

        # La décharge est valide si tous les critères sont respectés
        is_valid = all([
            hash_valid,
            montant_total_ok,
            montant_paye_ok,
            montant_restant_ok,
            statut_ok
        ])

        # ⭐ ENREGISTRER LA VÉRIFICATION DANS LES LOGS
        cursor.execute("""
            INSERT INTO kt_verifications_log 
            (numero_decharge, date_verification, ip_address, user_agent, is_valid)
            VALUES (%s, NOW(), %s, %s, %s)
        """, (numero_decharge, ip_address, user_agent, 1 if is_valid else 0))
        connection.commit()

        # Construction de la réponse
        response_data = {
            'success': True,
            'valid': is_valid,
            'decharge': {
                'numero': decharge_db['numero_decharge'],
                'medecin': decharge_db.get('medecin', 'N/A'),
                'specialite': decharge_db.get('name_specialty', 'N/A'),
                'montant_total': float(decharge_db['montant_total']),
                'montant_paye': float(decharge_db['montant_paye']),
                'montant_restant': float(decharge_db['montant_restant']),
                'statut': format_statut(decharge_db['statut']),
                'date': decharge_db['date_decharge'].strftime('%d/%m/%Y') if decharge_db['date_decharge'] else 'N/A',
                'nb_dossiers': int(decharge_db.get('nb_dossiers', 0))
            }
        }

        # Ajout des détails de non-correspondance si invalide
        if not is_valid:
            response_data['inconsistencies'] = []

            if not hash_valid:
                response_data['inconsistencies'].append({
                    'field': 'hash',
                    'message': 'Hash de sécurité invalide - QR Code possiblement falsifié'
                })

            if not montant_total_ok:
                response_data['inconsistencies'].append({
                    'field': 'montant_total',
                    'qr_value': f"{float(qr_data.get('montant_total', 0)):,.2f} DA",
                    'db_value': f"{float(decharge_db['montant_total']):,.2f} DA"
                })

            if not montant_paye_ok:
                response_data['inconsistencies'].append({
                    'field': 'montant_paye',
                    'qr_value': f"{float(qr_data.get('montant_paye', 0)):,.2f} DA",
                    'db_value': f"{float(decharge_db['montant_paye']):,.2f} DA"
                })

            if not montant_restant_ok:
                response_data['inconsistencies'].append({
                    'field': 'montant_restant',
                    'qr_value': f"{float(qr_data.get('montant_restant', 0)):,.2f} DA",
                    'db_value': f"{float(decharge_db['montant_restant']):,.2f} DA"
                })

            if not statut_ok:
                response_data['inconsistencies'].append({
                    'field': 'statut',
                    'qr_value': qr_data.get('statut'),
                    'db_value': decharge_db['statut']
                })

        return jsonify(response_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Erreur serveur : {str(e)}'
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route( '/api/decharge_info/<numero_decharge>' )
@handle_errors()
def api_decharge_info( numero_decharge ):
    """
    API pour récupérer les informations complètes d'une décharge
    Accessible publiquement pour permettre la vérification
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT 
                d.*,
                   CONCAT(doc.first_name, ' ', doc.last_name)                                     as medecin,
                   spec.name_specialty,
                   (SELECT COUNT(*) FROM kt_decharges_dossiers WHERE id_decharge = d.id_decharge) as nb_dossiers,
                   (SELECT COUNT(*) FROM kt_decharges_tranches WHERE id_decharge = d.id_decharge) as nb_tranches
            FROM kt_decharges_paiement d
                     LEFT JOIN doctors doc ON d.id_doctor = doc.id
                     LEFT JOIN specialty spec ON doc.id_specialty = spec.id_specialty
            WHERE d.numero_decharge = %s
                       """, (numero_decharge,)
            )

        decharge = cursor.fetchone()

        if not decharge:
            return jsonify(
                    {
                            'success': False,
                            'error': 'Décharge non trouvée'
                            }
                    ), 404

        # Récupération des tranches
        cursor.execute("""
            SELECT 
                numero_tranche,
                   montant_tranche,
                   date_paiement,
                   mode_paiement,
                   reference_paiement
            FROM kt_decharges_tranches
            WHERE id_decharge = %s
            ORDER BY numero_tranche
                       """, (decharge[ 'id_decharge' ],)
            )

        tranches = cursor.fetchall()

        cursor.close()
        connection.close()

        return jsonify(
                {
                        'success': True,
                        'decharge': {
                                'numero': decharge[ 'numero_decharge' ],
                                'medecin': decharge.get( 'medecin', 'N/A' ),
                                'specialite': decharge.get( 'name_specialty', 'N/A' ),
                                'date_decharge': decharge[ 'date_decharge' ].strftime( '%d/%m/%Y' ) if decharge[
                                    'date_decharge' ] else 'N/A',
                                'montant_total': float( decharge[ 'montant_total' ] ),
                                'montant_paye': float( decharge[ 'montant_paye' ] ),
                                'montant_restant': float( decharge[ 'montant_restant' ] ),
                                'statut': format_statut( decharge[ 'statut' ] ),
                                'nb_dossiers': int( decharge[ 'nb_dossiers' ] ),
                                'nb_tranches': int( decharge[ 'nb_tranches' ] ),
                                'observations': decharge.get( 'observations', '' ),
                                'tranches': [ {
                                        'numero': t[ 'numero_tranche' ],
                                        'montant': float( t[ 'montant_tranche' ] ),
                                        'date': t[ 'date_paiement' ].strftime( '%d/%m/%Y' ) if t[
                                            'date_paiement' ] else 'N/A',
                                        'mode': format_mode_paiement( t[ 'mode_paiement' ] ),
                                        'reference': t.get( 'reference_paiement', '' )
                                        } for t in tranches ]
                                }
                        }
                )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify(
                {
                        'success': False,
                        'error': f'Erreur serveur : {str( e )}'
                        }
                ), 500


@app.route( '/kt_verifications_log' )
@login_required
@handle_errors()

def kt_verifications_log():
    """Liste des vérifications de décharges avec statistiques"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Filtres
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )
        numero_decharge = request.args.get( 'numero_decharge', '' )
        validite = request.args.get( 'validite', 'all' )  # all, valid, invalid

        query = """
                SELECT vl.id_verification, \
                       vl.numero_decharge, \
                       vl.date_verification, \
                       vl.ip_address, \
                       vl.user_agent, \
                       vl.is_valid, \
                       CONCAT(doc.first_name, ' ', doc.last_name) as medecin, \
                       d.montant_total, \
                       d.statut
                FROM kt_verifications_log vl
                         LEFT JOIN kt_decharges_paiement d ON vl.numero_decharge = d.numero_decharge
                         LEFT JOIN doctors doc ON d.id_doctor = doc.id
                WHERE 1 = 1 \
                """
        params = [ ]

        if date_debut:
            query += " AND DATE(vl.date_verification) >= %s"
            params.append( date_debut )

        if date_fin:
            query += " AND DATE(vl.date_verification) <= %s"
            params.append( date_fin )

        if numero_decharge:
            query += " AND vl.numero_decharge LIKE %s"
            params.append( f"%{numero_decharge}%" )

        if validite == 'valid':
            query += " AND vl.is_valid = 1"
        elif validite == 'invalid':
            query += " AND vl.is_valid = 0"

        query += " ORDER BY vl.date_verification DESC LIMIT 1000"

        cursor.execute( query, params )
        logs = cursor.fetchall()

        # Statistiques
        cursor.execute(
            """
            SELECT COUNT(*)                                      as total_verifications,
                   SUM(CASE WHEN is_valid = 1 THEN 1 ELSE 0 END) as verifications_valides,
                   SUM(CASE WHEN is_valid = 0 THEN 1 ELSE 0 END) as verifications_invalides,
                   COUNT(DISTINCT numero_decharge)               as decharges_verifiees,
                   COUNT(DISTINCT ip_address)                    as ip_uniques,
                   COUNT(DISTINCT DATE(date_verification))       as jours_avec_verifications
            FROM kt_verifications_log
            WHERE 1 = 1
            """ + (f" AND DATE(date_verification) >= '{date_debut}'" if date_debut else "") +
            (f" AND DATE(date_verification) <= '{date_fin}'" if date_fin else "")
            )

        stats = cursor.fetchone()

        # Top décharges vérifiées
        cursor.execute(
            """
            SELECT vl.numero_decharge,
                   COUNT(*)                                         as nb_verifications,
                   SUM(CASE WHEN vl.is_valid = 1 THEN 1 ELSE 0 END) as nb_valides,
                   SUM(CASE WHEN vl.is_valid = 0 THEN 1 ELSE 0 END) as nb_invalides,
                   MAX(vl.date_verification)                        as derniere_verification,
                   CONCAT(doc.first_name, ' ', doc.last_name)       as medecin
            FROM kt_verifications_log vl
                     LEFT JOIN kt_decharges_paiement d ON vl.numero_decharge = d.numero_decharge
                     LEFT JOIN doctors doc ON d.id_doctor = doc.id
            GROUP BY vl.numero_decharge
            ORDER BY nb_verifications DESC
            LIMIT 10
                       """
            )

        top_decharges = cursor.fetchall()

        return render_template(
                'admin/kt_verifications_log.html',
                logs = logs,
                stats = stats,
                top_decharges = top_decharges,
                title = "Journal des Vérifications de Décharges",
                user = g.user
                )

    finally:
        cursor.close()
        connection.close()


@app.route( '/api/kt_verification_details/<int:id_verification>' )
@handle_errors()
def api_kt_verification_details( id_verification ):
    """Détails d'une vérification spécifique"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT vl.*,
                   d.montant_total,
                   d.montant_paye,
                   d.montant_restant,
                   d.statut,
                   d.date_decharge,
                   CONCAT(doc.first_name, ' ', doc.last_name) as medecin,
                   spec.name_specialty
            FROM kt_verifications_log vl
                     LEFT JOIN kt_decharges_paiement d ON vl.numero_decharge = d.numero_decharge
                     LEFT JOIN doctors doc ON d.id_doctor = doc.id
                     LEFT JOIN specialty spec ON doc.id_specialty = spec.id_specialty
            WHERE vl.id_verification = %s
                       """, (id_verification,)
            )

        verification = cursor.fetchone()

        if not verification:
            return jsonify( { 'success': False, 'error': 'Vérification non trouvée' } ), 404

        return jsonify(
                {
                        'success': True,
                        'verification': {
                                'id': verification[ 'id_verification' ],
                                'numero_decharge': verification[ 'numero_decharge' ],
                                'date_verification': verification[ 'date_verification' ].strftime(
                                    '%d/%m/%Y %H:%M:%S'
                                    ),
                                'ip_address': verification[ 'ip_address' ],
                                'user_agent': verification[ 'user_agent' ],
                                'is_valid': bool( verification[ 'is_valid' ] ),
                                'medecin': verification.get( 'medecin', 'N/A' ),
                                'specialite': verification.get( 'name_specialty', 'N/A' ),
                                'montant_total': float( verification[ 'montant_total' ] ) if verification.get(
                                    'montant_total'
                                    ) else 0,
                                'statut': format_statut( verification[ 'statut' ] ) if verification.get(
                                    'statut'
                                    ) else 'N/A'
                                }
                        }
                )

    except Exception as e:
        return jsonify( { 'success': False, 'error': str( e ) } ), 500

    finally:
        cursor.close()
        connection.close()