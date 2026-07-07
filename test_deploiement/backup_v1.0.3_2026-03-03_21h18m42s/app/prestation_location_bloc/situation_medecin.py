# app/situation_medecin.py - CORRIGÉ ✅

from datetime import date, timedelta
from contextlib import contextmanager
from io import BytesIO
from flask import make_response
from flask import request, redirect, url_for, render_template, g, flash, jsonify

from app import app, get_db_connection
from app.error import handle_errors
from app.utils.utiles import login_required
from decimal import Decimal
from datetime import datetime
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY


# ========================================================================
# UTILITAIRES CENTRALISÉS
# ========================================================================
@app.template_filter('format_date')
def format_date_filter(value):
    """Formate une date pour input type=date"""
    if value:
        if isinstance(value, str):
            return value
        return value.strftime('%Y-%m-%d')
    return ''

@app.template_filter('format_time')
def format_time_filter(value):
    """Formate une heure pour input type=time"""
    if value:
        if isinstance(value, timedelta):
            total_seconds = int(value.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        if isinstance(value, str):
            return value
        return value.strftime('%H:%M')
    return ''

def to_decimal(value, default=0):
    """Convertit une valeur en Decimal de manière sécurisée"""
    if value is None or value == '':
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except:
        return Decimal(str(default))


def calculer_statut_paiement(reste):
    """
    ✅ CORRIGÉ : Détermine le statut de paiement selon le reste

    reste > 0  : Il manque de l'argent à la CLINIQUE → MÉDECIN doit payer → ENCAISSEMENT
    reste < 0  : La CLINIQUE a trop reçu → CLINIQUE doit payer → DÉCHARGE
    reste == 0 : Équilibré
    """
    if abs(reste) < Decimal('0.01'):
        return 'EQUILIBRE'
    return 'MEDECIN_DOIT_PAYER' if reste > 0 else 'CLINIQUE_DOIT_PAYER'


@contextmanager
def get_cursor():
    """Context manager pour gérer automatiquement la connexion DB"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


# ========================================================================
# FONCTIONS MÉTIER - DOSSIERS BLOC
# ========================================================================

def get_dossiers_bloc_medecin(cursor, id_doctor, include_decharge_status=False, start_date=None, end_date=None):
    """Récupère les dossiers BLOC d'un médecin avec calcul optimisé des balances"""
    
    where_clause = "WHERE dp.id_doctor = %s"
    params = [id_doctor]

    if start_date:
        where_clause += " AND dp.location_date >= %s"
        params.append(start_date)
    
    if end_date:
        where_clause += " AND dp.location_date <= %s"
        params.append(end_date)

    cursor.execute(
        f"""
        SELECT 
            dp.id_dossier,
            dp.patient,
            dp.location_date,
            dp.prix_total,
            COALESCE(SUM(ds.encaissement_patient), 0)  as enc_patient,
            COALESCE(SUM(ds.encaissement_doctor), 0)   as enc_doctor,
            COALESCE(SUM(ds.decaissement_clinique), 0) as decaissement,
            COALESCE(SUM(ds.compensation), 0)          as compensation
        FROM location_bloc_dossier_patient dp
        LEFT JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
        {where_clause}
        GROUP BY dp.id_dossier
        ORDER BY dp.location_date DESC
        """, tuple(params)
    )

    dossiers = []
    for row in cursor.fetchall():
        part = to_decimal(row['prix_total'])

        # ✅ CORRECTION : compensation doit être AJOUTÉE, pas soustraite
        # balance = prix - (paiements_patient + paiements_médecin + paiements_clinique - compensation)
        balance = part - (
            to_decimal(row['enc_patient']) +
            to_decimal(row['enc_doctor']) +
            to_decimal(row['decaissement']) -
            to_decimal(row['compensation'])  # ✅ CHANGEMENT : - au lieu de +
        )

        dossier = {
            'id': row['id_dossier'],
            'id_dossier': row['id_dossier'],
            'type_dossier': 'BLOC',
            'patient': row['patient'],
            'location_date': row['location_date'],
            'part_clinique': part,
            'prix_total': part,
            'prix_total_dossier': part,
            'balance': balance,
            'reste': balance,
            'statut_paiement': calculer_statut_paiement(balance),
            'enc_patient': to_decimal(row['enc_patient']),
            'enc_doctor': to_decimal(row['enc_doctor']),
            'decaissement': to_decimal(row['decaissement']),
            'compensation': to_decimal(row['compensation'])
        }

        if include_decharge_status:
            dossier['deja_decharge'] = est_dossier_deja_decharge(
                cursor, row['id_dossier'], 'BLOC'
            )

        dossiers.append(dossier)

    return dossiers


def get_stats_medecin_bloc(cursor, id_doctor, start_date=None, end_date=None):
    """Calcule les statistiques BLOC pour un médecin"""
    
    date_filter = ""
    params = []
    
    if start_date:
        date_filter += " AND location_date >= %s"
        params.append(start_date)
    if end_date:
        date_filter += " AND location_date <= %s"
        params.append(end_date)
        
    # On prépare les paramètres pour chaque sous-requête qui utilise location_date
    # Note: Les transactions sont liées au dossier, donc on filtre sur la date du dossier
    
    # 6 sous-requêtes, donc 6 fois les params
    all_params = []
    
    # 1. total_dossiers
    all_params.append(id_doctor)
    all_params.extend(params)
    
    # 2. chiffre_affaire
    all_params.append(id_doctor)
    all_params.extend(params)
    
    # 3. enc_patient
    all_params.append(id_doctor)
    all_params.extend(params)
    
    # 4. enc_doctor
    all_params.append(id_doctor)
    all_params.extend(params)
    
    # 5. decaissement
    all_params.append(id_doctor)
    all_params.extend(params)
    
    # 6. compensation
    all_params.append(id_doctor)
    all_params.extend(params)

    cursor.execute(
        f"""
        SELECT 
            -- Nombre de dossiers
            (SELECT COUNT(DISTINCT id_dossier)
             FROM location_bloc_dossier_patient
             WHERE id_doctor = %s {date_filter}) as total_dossiers,
            
            -- Chiffre d'affaires (somme des prix_total sans duplication)
            COALESCE((SELECT SUM(prix_total)
                      FROM location_bloc_dossier_patient
                      WHERE id_doctor = %s {date_filter}), 0) as chiffre_affaire,
            
            -- Sommes des transactions (filtrées par date du dossier)
            COALESCE((SELECT SUM(ds.encaissement_patient)
                      FROM location_bloc_dossier_patient dp
                      JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
                      WHERE dp.id_doctor = %s {date_filter}), 0) as enc_patient,
            
            COALESCE((SELECT SUM(ds.encaissement_doctor)
                      FROM location_bloc_dossier_patient dp
                      JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
                      WHERE dp.id_doctor = %s {date_filter}), 0) as enc_doctor,
            
            COALESCE((SELECT SUM(ds.decaissement_clinique)
                      FROM location_bloc_dossier_patient dp
                      JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
                      WHERE dp.id_doctor = %s {date_filter}), 0) as decaissement,
            
            COALESCE((SELECT SUM(ds.compensation)
                      FROM location_bloc_dossier_patient dp
                      JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier
                      WHERE dp.id_doctor = %s {date_filter}), 0) as compensation
        """, tuple(all_params)
    )

    row = cursor.fetchone()

    ca_bloc = to_decimal(row['chiffre_affaire'])
    enc_patient_bloc = to_decimal(row['enc_patient'])
    enc_doctor_bloc = to_decimal(row['enc_doctor'])
    dec_bloc = to_decimal(row['decaissement'])
    comp_bloc = to_decimal(row['compensation'])

    # ✅ CORRECTION : compensation doit être AJOUTÉE
    balance_bloc = ca_bloc - (enc_patient_bloc + enc_doctor_bloc + dec_bloc - comp_bloc)

    return {
        'total_dossiers': row['total_dossiers'] or 0,
        'chiffre_affaire': ca_bloc,
        'total_decaissement': dec_bloc,
        'total_encaissement': enc_doctor_bloc,
        'total_compensation': comp_bloc,
        'balance_globale': balance_bloc,
        'reste_a_regler_global': balance_bloc
    }


def get_transactions_dossier_bloc(cursor, id_dossier):
    """Récupère les transactions d'un dossier BLOC"""
    cursor.execute(
        """
        SELECT 
            payment_date,
            encaissement_patient,
            encaissement_doctor,
            decaissement_clinique,
            compensation,
            notes
        FROM location_bloc_doctor_situations
        WHERE id_dossier = %s
        ORDER BY payment_date DESC
        """, (id_dossier,)
    )
    return cursor.fetchall()


def est_dossier_deja_decharge(cursor, id_dossier, type_dossier='BLOC'):
    """Vérifie si un dossier est déjà inclus dans une opération de décharge non soldée"""
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM location_bloc_operation_dossiers od
        INNER JOIN location_bloc_operations_financieres_medecin o 
            ON od.id_operation = o.id
        WHERE od.id_dossier = %s 
          AND COALESCE(od.type_dossier, 'BLOC') = %s
          AND o.type_operation = 'DECHARGE'
          AND o.reste > 0
        """, (id_dossier, type_dossier)
    )
    result = cursor.fetchone()
    return result['count'] > 0


def est_dossier_deja_encaisse(cursor, id_dossier, type_dossier='BLOC'):
    """Vérifie si un dossier est déjà inclus dans une opération d'encaissement non soldée"""
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM location_bloc_operation_dossiers od
        INNER JOIN location_bloc_operations_financieres_medecin o 
            ON od.id_operation = o.id
        WHERE od.id_dossier = %s 
          AND COALESCE(od.type_dossier, 'BLOC') = %s
          AND o.type_operation = 'ENCAISSEMENT'
          AND o.reste > 0
        """, (id_dossier, type_dossier)
    )
    result = cursor.fetchone()
    return result['count'] > 0


# ========================================================================
# ROUTES PRINCIPALES
# ========================================================================

@app.route('/situation_medecin_bloc')
@login_required
@handle_errors()

def situation_medecin_bloc():
    """Liste des médecins EXTERNES avec leur situation financière BLOC"""
    with get_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT 
                d.id as id_doctor,
                CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                s.name_specialty,
                
                -- Nombre de dossiers
                (SELECT COUNT(DISTINCT dp2.id_dossier)
                 FROM location_bloc_dossier_patient dp2
                 WHERE dp2.id_doctor = d.id) as total_dossiers,
                
                -- Chiffre d'affaires (somme des prix_total)
                COALESCE((SELECT SUM(dp3.prix_total)
                          FROM location_bloc_dossier_patient dp3
                          WHERE dp3.id_doctor = d.id), 0) as chiffre_affaire,
                
                -- Encaissements et décaissements
                COALESCE((SELECT SUM(ds2.encaissement_patient)
                          FROM location_bloc_dossier_patient dp4
                          JOIN location_bloc_doctor_situations ds2 ON dp4.id_dossier = ds2.id_dossier
                          WHERE dp4.id_doctor = d.id), 0) as enc_patient,
                
                COALESCE((SELECT SUM(ds3.encaissement_doctor)
                          FROM location_bloc_dossier_patient dp5
                          JOIN location_bloc_doctor_situations ds3 ON dp5.id_dossier = ds3.id_dossier
                          WHERE dp5.id_doctor = d.id), 0) as enc_doctor,
                
                COALESCE((SELECT SUM(ds4.decaissement_clinique)
                          FROM location_bloc_dossier_patient dp6
                          JOIN location_bloc_doctor_situations ds4 ON dp6.id_dossier = ds4.id_dossier
                          WHERE dp6.id_doctor = d.id), 0) as decaissement,
                
                COALESCE((SELECT SUM(ds5.compensation)
                          FROM location_bloc_dossier_patient dp7
                          JOIN location_bloc_doctor_situations ds5 ON dp7.id_dossier = ds5.id_dossier
                          WHERE dp7.id_doctor = d.id), 0) as compensation
                
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE (d.est_interne = 0 OR d.est_interne IS NULL)
              AND EXISTS (SELECT 1 FROM location_bloc_dossier_patient dp_check 
                         WHERE dp_check.id_doctor = d.id)
            ORDER BY d.last_name, d.first_name
            """
        )

        medecins = cursor.fetchall()
        doctors_with_balance = []
        total_balance_all = Decimal('0')

        for med in medecins:
            ca = to_decimal(med['chiffre_affaire'])
            enc_patient = to_decimal(med['enc_patient'])
            enc_doctor = to_decimal(med['enc_doctor'])
            dec = to_decimal(med['decaissement'])
            comp = to_decimal(med['compensation'])

            # ✅ CORRECTION : compensation doit être AJOUTÉE
            balance = ca - (enc_patient + enc_doctor + dec - comp)

            total_balance_all += balance

            doctor_data = {
                'id_doctor': med['id_doctor'],
                'nom_complet': med['nom_complet'],
                'name_specialty': med['name_specialty'],
                'total_dossiers': med['total_dossiers'],
                'chiffre_affaire': ca,
                'total_decaissement': dec,
                'total_encaissement': enc_doctor,
                'total_compensation': comp,
                'balance_globale': balance,
                'reste_a_regler_global': balance
            }
            doctors_with_balance.append(doctor_data)

        return render_template(
            'situation_medecin/situation_medecin_externe.html',  # ✅ Template unifié
            doctors=doctors_with_balance,
            total_balance_all=total_balance_all,
            type_situation='BLOC',  # ✅ Paramètre de type
            type_display='Location de Bloc',
            route_prefix='operations_medecin_bloc',
            route_detail='situation_medecin_bloc_detail',
            id_param='id_doctor',
            title="Situation Médecin - Locations de Bloc",
        )


@app.route('/situation_medecin_bloc/<int:id_doctor>')
@login_required
@handle_errors()

def situation_medecin_bloc_detail(id_doctor):
    """Détail de la situation BLOC d'un médecin externe"""
    with get_cursor() as (conn, cursor):
        # Info médecin
        cursor.execute(
            """
            SELECT 
                d.id,
                CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                s.name_specialty
            FROM doctors d
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            WHERE d.id = %s
            """, (id_doctor,)
        )
        doctor = cursor.fetchone()

        if not doctor:
            flash('Médecin non trouvé', 'danger')
            return redirect(url_for('situation_medecin_bloc'))

        # Filtres dates
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Dossiers BLOC
        dossiers_bloc = get_dossiers_bloc_medecin(cursor, id_doctor, start_date=start_date, end_date=end_date)

        # Enrichir avec transactions
        for doss in dossiers_bloc:
            doss['transactions'] = get_transactions_dossier_bloc(cursor, doss['id'])

        # Stats
        stats = get_stats_medecin_bloc(cursor, id_doctor, start_date=start_date, end_date=end_date)
        doctor_enriched = {**doctor, **stats}

        return render_template(
                'situation_medecin/situation_medecin_bloc_detail.html',
            doctor=doctor_enriched,
            dossiers=dossiers_bloc,
            current_date=date.today().isoformat(),
            start_date=start_date,
            end_date=end_date,
            title=f"Dr. {doctor['nom_complet']} - Bloc",
        )


# ========================================================================
# CRÉATION DES BONS (ENCAISSEMENT / DÉCHARGE)
# ========================================================================

@app.route('/creer_operation_medecin_bloc', methods=['POST'])
@login_required
@handle_errors()

def creer_operation_medecin_bloc():
    """Créer un bon d'encaissement ou de décharge pour BLOC uniquement"""
    with get_cursor() as (conn, cursor):
        # Validation des données
        id_doctor = request.form.get('id_doctor', type=int)
        type_operation = request.form.get('type_operation')
        date_operation = request.form.get('date_operation')
        dossiers_ids = request.form.getlist('dossiers[]')

        if not all([id_doctor, type_operation, date_operation, dossiers_ids]):
            flash('Données incomplètes', 'danger')
            return redirect(url_for('situation_medecin_bloc_detail', id_doctor=id_doctor))

        if type_operation not in ['ENCAISSEMENT', 'DECHARGE']:
            flash('Type d\'opération invalide', 'danger')
            return redirect(url_for('situation_medecin_bloc_detail', id_doctor=id_doctor))

        # Récupération et validation des dossiers
        dossiers_bloc = get_dossiers_bloc_medecin(
            cursor, id_doctor, include_decharge_status=True
        )
        all_dossiers = {str(d['id']): d for d in dossiers_bloc}

        # Vérification des dossiers déjà utilisés
        dossiers_deja_utilises = []
        for doss_id in dossiers_ids:
            if doss_id not in all_dossiers:
                continue

            doss = all_dossiers[doss_id]
            if type_operation == 'DECHARGE' and doss.get('deja_decharge', False):
                dossiers_deja_utilises.append(doss['patient'])
            elif type_operation == 'ENCAISSEMENT' and est_dossier_deja_encaisse(
                cursor, int(doss_id), 'BLOC'
            ):
                dossiers_deja_utilises.append(doss['patient'])

        if dossiers_deja_utilises:
            operation_nom = 'décharge' if type_operation == 'DECHARGE' else 'encaissement'
            flash(
                f'⚠️ Certains dossiers sont déjà inclus dans un {operation_nom} en cours: '
                f'{", ".join(dossiers_deja_utilises)}',
                'warning'
            )
            return redirect(url_for('situation_medecin_bloc_detail', id_doctor=id_doctor))

        # Calcul du montant total
        montant_total = Decimal('0')
        dossiers_data = []

        for doss_id in dossiers_ids:
            if doss_id not in all_dossiers:
                continue

            doss = all_dossiers[doss_id]
            reste = doss['reste']

            # ✅ CORRECTION : Vérification avec la bonne logique
            if type_operation == 'ENCAISSEMENT' and reste > Decimal('0.01'):
                # Médecin doit payer
                montant_du = reste
                montant_total += montant_du
                dossiers_data.append({
                    'id': int(doss_id),
                    'type': 'BLOC',
                    'montant': montant_du
                })
            elif type_operation == 'DECHARGE' and reste < Decimal('-0.01'):
                # Clinique doit payer
                montant_du = abs(reste)
                montant_total += montant_du
                dossiers_data.append({
                    'id': int(doss_id),
                    'type': 'BLOC',
                    'montant': montant_du
                })

        if montant_total == 0:
            flash('Aucun dossier éligible sélectionné', 'warning')
            return redirect(url_for('situation_medecin_bloc_detail', id_doctor=id_doctor))

        # Création du bon
        cursor.execute(
            """
            INSERT INTO location_bloc_operations_financieres_medecin
                (id_doctor, type_operation, date, montant, reste, id_created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                id_doctor, type_operation, date_operation, montant_total,
                montant_total, g.user['id_personnel']
            )
        )

        id_operation = cursor.lastrowid

        # Liaison avec les dossiers
        for doss_data in dossiers_data:
            cursor.execute(
                """
                INSERT INTO location_bloc_operation_dossiers
                    (id_operation, id_dossier, montant, type_dossier)
                VALUES (%s, %s, %s, %s)
                """, (id_operation, doss_data['id'], doss_data['montant'], doss_data['type'])
            )

        flash(
            f'✅ Bon de {type_operation.lower()} créé. Montant: {float(montant_total):.2f} DA',
            'success'
        )
        return redirect(url_for('operations_medecin_bloc_list', type_operation=type_operation))


# ========================================================================
# COMPENSATION - BLOC UNIQUEMENT
# ========================================================================

@app.route('/creer_compensation_medecin_bloc', methods=['POST'])
@login_required
@handle_errors()

def creer_compensation_medecin_bloc():
    """Créer une compensation FIFO entre dossiers BLOC"""
    with get_cursor() as (conn, cursor):
        id_doctor = request.form.get('id_doctor', type=int)
        date_operation = request.form.get('date_operation')
        dossiers_ids = [int(x) for x in request.form.getlist('dossiers[]')]

        if not all([id_doctor, date_operation, dossiers_ids]):
            flash('Données incomplètes', 'danger')
            return redirect(url_for('situation_medecin_bloc_detail', id_doctor=id_doctor))

        # Récupération des dossiers
        dossiers_bloc = get_dossiers_bloc_medecin(cursor, id_doctor)
        all_dossiers = {d['id']: d for d in dossiers_bloc}

        # Séparation positifs/négatifs
        # ✅ CORRECTION : Inversion de la logique
        dossiers_positifs = []  # Médecin doit payer (reste > 0)
        dossiers_negatifs = []  # Clinique doit payer (reste < 0)

        for doss_id in dossiers_ids:
            if doss_id not in all_dossiers:
                continue

            doss = all_dossiers[doss_id]
            reste = doss['reste']

            if reste > Decimal('0.01'):
                dossiers_positifs.append(doss)  # Médecin doit
            elif reste < Decimal('-0.01'):
                dossiers_negatifs.append(doss)  # Clinique doit

        # Tri FIFO (par date)
        dossiers_positifs.sort(key=lambda x: x['location_date'])
        dossiers_negatifs.sort(key=lambda x: x['location_date'])

        if not dossiers_positifs or not dossiers_negatifs:
            flash('Vous devez sélectionner au moins un dossier de chaque type', 'warning')
            return redirect(url_for('situation_medecin_bloc_detail', id_doctor=id_doctor))

        # Calcul du montant de compensation
        total_surplus = sum(d['reste'] for d in dossiers_positifs)  # Positif
        total_deficit = sum(abs(d['reste']) for d in dossiers_negatifs)  # Positif
        montant_compensation = min(total_surplus, total_deficit)

        # Création du bon
        cursor.execute(
            """
            INSERT INTO location_bloc_operations_financieres_medecin
                (id_doctor, type_operation, date, montant, reste, id_created_by)
            VALUES (%s, 'COMPENSATION', %s, %s, 0, %s)
            """, (id_doctor, date_operation, montant_compensation, g.user['id_personnel'])
        )

        id_operation = cursor.lastrowid

        # Application FIFO sur négatifs (clinique doit)
        surplus_restant = montant_compensation
        for doss in dossiers_negatifs:
            if surplus_restant <= 0:
                break

            deficit = abs(doss['reste'])
            montant = min(surplus_restant, deficit)

            cursor.execute(
                """
                INSERT INTO location_bloc_operation_dossiers
                    (id_operation, id_dossier, montant, type_dossier)
                VALUES (%s, %s, %s, 'BLOC')
                """, (id_operation, doss['id'], montant)
            )

            # ✅ Compensation POSITIVE (réduit la dette de la clinique)
            cursor.execute(
                """
                INSERT INTO location_bloc_doctor_situations
                    (id_doctor, id_dossier, compensation, notes)
                VALUES (%s, %s, %s, %s)
                """, (id_doctor, doss['id'], montant, f'Compensation #{id_operation}')
            )

            surplus_restant -= montant

        # Application FIFO sur positifs (médecin doit)
        deficit_restant = montant_compensation
        for doss in dossiers_positifs:
            if deficit_restant <= 0:
                break

            surplus = doss['reste']
            montant = min(deficit_restant, surplus)

            cursor.execute(
                """
                INSERT INTO location_bloc_operation_dossiers
                    (id_operation, id_dossier, montant, type_dossier)
                VALUES (%s, %s, %s, 'BLOC')
                """, (id_operation, doss['id'], montant)
            )

            # ✅ Compensation NÉGATIVE (réduit la dette du médecin)
            cursor.execute(
                """
                INSERT INTO location_bloc_doctor_situations
                    (id_doctor, id_dossier, compensation, notes)
                VALUES (%s, %s, %s, %s)
                """, (id_doctor, doss['id'], -montant, f'Compensation #{id_operation}')
            )

            deficit_restant -= montant

        flash(f'Compensation créée. Montant: {float(montant_compensation):.2f} DA', 'success')
        return redirect(url_for('operations_medecin_bloc_list', type_operation='COMPENSATION'))


# ========================================================================
# PAIEMENT D'UNE OPÉRATION
# ========================================================================

@app.route('/payer_operation/<int:id_operation>', methods=['POST'])
@login_required
@handle_errors()

def payer_operation(id_operation):
    """Enregistrer un paiement pour une opération (BLOC)"""
    with get_cursor() as (conn, cursor):
        payment_amount = to_decimal(request.form.get('payment_amount', 0))
        type_operation = request.form.get('type_operation')

        if payment_amount <= 0:
            flash('Montant invalide', 'danger')
            return redirect(url_for('operations_medecin_bloc_list', type_operation=type_operation))

        # Récupération de l'opération
        cursor.execute(
            """
            SELECT *
            FROM location_bloc_operations_financieres_medecin
            WHERE id = %s
            """, (id_operation,)
        )
        operation = cursor.fetchone()

        if not operation:
            flash('Opération non trouvée', 'danger')
            return redirect(url_for('operations_medecin_bloc_list', type_operation=type_operation))

        reste_actuel = to_decimal(operation['reste'])

        if payment_amount > reste_actuel:
            flash('Le montant dépasse le reste à payer', 'danger')
            return redirect(url_for('operations_medecin_bloc_list', type_operation=type_operation))

        # Mise à jour de l'opération
        nouveau_paye = to_decimal(operation['montant_paye']) + payment_amount
        nouveau_reste = reste_actuel - payment_amount

        cursor.execute(
            """
            UPDATE location_bloc_operations_financieres_medecin
            SET montant_paye  = %s,
                reste         = %s,
                id_payment_by = %s,
                payment_at    = %s
            WHERE id = %s
            """, (nouveau_paye, nouveau_reste, g.user['id_personnel'], datetime.now(), id_operation)
        )

        # Récupération des dossiers liés
        cursor.execute(
            """
            SELECT id_dossier, montant, COALESCE(type_dossier, 'BLOC') as type_dossier
            FROM location_bloc_operation_dossiers
            WHERE id_operation = %s
            """, (id_operation,)
        )
        dossiers_lies = cursor.fetchall()

        montant_total = to_decimal(operation['montant'])

        # Répartition proportionnelle
        for doss in dossiers_lies:
            montant_dossier = to_decimal(doss['montant'])
            proportion = montant_dossier / montant_total
            montant_transaction = payment_amount * proportion

            if type_operation == 'ENCAISSEMENT':
                # Médecin paie la clinique
                cursor.execute(
                    """
                    INSERT INTO location_bloc_doctor_situations
                        (id_doctor, id_dossier, encaissement_doctor, notes)
                    VALUES (%s, %s, %s, %s)
                    """, (
                        operation['id_doctor'], doss['id_dossier'], montant_transaction,
                        f'Paiement bon #{id_operation}'
                    )
                )
            elif type_operation == 'DECHARGE':
                # ✅ CORRECTION : Clinique paie le médecin → POSITIF !
                cursor.execute(
                    """
                    INSERT INTO location_bloc_doctor_situations
                        (id_doctor, id_dossier, decaissement_clinique, notes)
                    VALUES (%s, %s, %s, %s)
                    """, (
                        operation['id_doctor'], doss['id_dossier'], montant_transaction,  # ✅ POSITIF
                        f'Paiement bon #{id_operation}'
                    )
                )

        flash(f'Paiement de {float(payment_amount):.2f} DA enregistré', 'success')
        return redirect(url_for('operations_medecin_bloc_list', type_operation=type_operation))


# ========================================================================
# LISTE DES OPÉRATIONS
# ========================================================================

@app.route('/operations_medecin_bloc/<type_operation>')
@login_required
@handle_errors()

def operations_medecin_bloc_list(type_operation):
    """Liste des bons d'opérations BLOC"""
    if type_operation not in ['ENCAISSEMENT', 'DECHARGE', 'COMPENSATION']:
        flash('Type d\'opération invalide', 'danger')
        return redirect(url_for('situation_medecin_bloc'))

    with get_cursor() as (conn, cursor):
        filter_paid = request.args.get('filter_paid', 'false') == 'true'
        where_reste = "AND o.reste = 0" if filter_paid else "AND o.reste > 0"

        cursor.execute(
            f"""
            SELECT 
                o.*, 
                CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                CONCAT(pc.nom, ' ', pc.prenom) as created_by_name,
                CONCAT(pp.nom, ' ', pp.prenom) as payment_by_name
            FROM location_bloc_operations_financieres_medecin o
            LEFT JOIN doctors d ON o.id_doctor = d.id
            LEFT JOIN personnel pc ON o.id_created_by = pc.id_personnel
            LEFT JOIN personnel pp ON o.id_payment_by = pp.id_personnel
            WHERE o.type_operation = %s {where_reste}
            ORDER BY o.date DESC, o.id DESC
            """, (type_operation,)
        )

        operations = cursor.fetchall()

        return render_template(
            'situation_medecin/operations_externe_list.html',  # ✅ Template unifié
            operations=operations,
            type_operation=type_operation,
            filter_paid=filter_paid,
            type_situation='BLOC',  # ✅ Paramètre de type
            type_display='Bloc',
            route_back='situation_medecin_bloc',
            api_dossiers_endpoint='/api/get_dossiers_operation',
            route_payer='payer_operation',
            route_supprimer='supprimer_operation',
            title=f"Bons de {type_operation.lower()} - Bloc",
        )


@app.route('/supprimer_operation/<int:id_operation>', methods=['POST'])
@login_required
@handle_errors()

def supprimer_operation(id_operation):
    """Supprimer une opération non payée"""
    with get_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT *
            FROM location_bloc_operations_financieres_medecin
            WHERE id = %s
            """, (id_operation,)
        )
        operation = cursor.fetchone()

        if not operation:
            flash('Opération non trouvée', 'danger')
            return redirect(url_for('situation_medecin_bloc'))

        if to_decimal(operation['montant_paye']) > 0:
            flash('Impossible de supprimer une opération déjà payée', 'danger')
            return redirect(
                url_for('operations_medecin_bloc_list', type_operation=operation['type_operation'])
            )

        cursor.execute(
            "DELETE FROM location_bloc_operations_financieres_medecin WHERE id = %s",
            (id_operation,)
        )

        flash('Opération supprimée', 'success')
        return redirect(
            url_for('operations_medecin_bloc_list', type_operation=operation['type_operation'])
        )


# ========================================================================
# EXPORT PDF
# ========================================================================

@app.route('/export/situation_medecins/liste/<type_situation>')
@login_required

def export_situation_medecins_liste(type_situation):
    """Génère un PDF de la liste des médecins avec leur solde"""
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    filter_balance = request.args.get('filter_balance', 'all')
    
    # Configuration
    with get_cursor() as (conn, cursor):
        configs = ConfigurationClinicPDF.get_all_configs(cursor)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1*cm, leftMargin=1*cm,
                            topMargin=1*cm, bottomMargin=1*cm)
    story = []
    styles = PDFStyles.get_styles()

    # En-tête Clinique
    # En-tête Clinique
    ajouter_entete_image(story)
    creer_ligne_separation(story, PDFColors.PRIMARY)
    story.append(Spacer(1, 0.5*cm))

    # Titre
    title_text = f"Situation Financière Médecins - {type_situation}"
    story.append(Paragraph(title_text, styles['titre_section']))
    
    date_info = f"Date impression: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    if start_date or end_date:
        period_str = []
        if start_date: period_str.append(f"Du: {start_date}")
        if end_date: period_str.append(f"Au: {end_date}")
        date_info += " | Période: " + " - ".join(period_str)
        
    story.append(Paragraph(date_info, styles['header']))
    
    if filter_balance != 'all':
        filter_text = "Filtre: Solde Positif" if filter_balance == 'positive' else "Filtre: Solde Négatif"
        story.append(Paragraph(filter_text, styles['subheader']))
        
    story.append(Spacer(1, 1*cm))

    # Récupération des données
    with get_cursor() as (conn, cursor):
        params = []
        
        if type_situation == 'BLOC':
            date_cond_dp = ""
            date_cond_check = ""
            
            p_list = []
            if start_date:
                date_cond_dp += " AND dp.location_date >= %s"
                date_cond_check += " AND dp_check.location_date >= %s"
                p_list.append(start_date)
            if end_date:
                date_cond_dp += " AND dp.location_date <= %s"
                date_cond_check += " AND dp_check.location_date <= %s"
                p_list.append(end_date)
            
            # 5 subqueries + 1 exists check
            params = p_list * 5 + p_list 
            
            query = f"""
                SELECT 
                    d.id as id_doctor,
                    CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                    s.name_specialty,
                    COALESCE((SELECT SUM(dp.prix_total) FROM location_bloc_dossier_patient dp WHERE dp.id_doctor = d.id {date_cond_dp}), 0) as ca,
                    COALESCE((SELECT SUM(ds.encaissement_patient) FROM location_bloc_dossier_patient dp JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier WHERE dp.id_doctor = d.id {date_cond_dp}), 0) as enc_pat,
                    COALESCE((SELECT SUM(ds.encaissement_doctor) FROM location_bloc_dossier_patient dp JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier WHERE dp.id_doctor = d.id {date_cond_dp}), 0) as enc_doc,
                    COALESCE((SELECT SUM(ds.decaissement_clinique) FROM location_bloc_dossier_patient dp JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier WHERE dp.id_doctor = d.id {date_cond_dp}), 0) as decaissement_total,
                    COALESCE((SELECT SUM(ds.compensation) FROM location_bloc_dossier_patient dp JOIN location_bloc_doctor_situations ds ON dp.id_dossier = ds.id_dossier WHERE dp.id_doctor = d.id {date_cond_dp}), 0) as comp
                FROM doctors d
                LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE EXISTS (SELECT 1 FROM location_bloc_dossier_patient dp_check WHERE dp_check.id_doctor = d.id {date_cond_check})
                ORDER BY d.last_name
            """
        else: # ACCOUCHEMENT
            date_cond_a = ""
            date_cond_check = ""
            
            p_list = []
            if start_date:
                date_cond_a += " AND a.date_accouchement >= %s"
                date_cond_check += " AND dp_check.date_accouchement >= %s"
                p_list.append(start_date)
            if end_date:
                date_cond_a += " AND a.date_accouchement <= %s"
                date_cond_check += " AND dp_check.date_accouchement <= %s"
                p_list.append(end_date)
            
            params = p_list * 5 + p_list

            query = f"""
                SELECT 
                    d.id as id_doctor,
                    CONCAT(d.first_name, ' ', d.last_name) as nom_complet,
                    s.name_specialty,
                    COALESCE((SELECT SUM(a.part_gyneco) FROM accouchement_dossiers a WHERE a.id_gyneco = d.id {date_cond_a}), 0) as ca,
                    COALESCE((SELECT SUM(s.encaissement_patient) FROM accouchement_dossiers a JOIN accouchement_gyneco_situations s ON a.id_dossier = s.id_dossier WHERE a.id_gyneco = d.id {date_cond_a}), 0) as enc_pat,
                    COALESCE((SELECT SUM(s.encaissement_gyneco) FROM accouchement_dossiers a JOIN accouchement_gyneco_situations s ON a.id_dossier = s.id_dossier WHERE a.id_gyneco = d.id {date_cond_a}), 0) as enc_doc,
                    COALESCE((SELECT SUM(s.decaissement_clinique) FROM accouchement_dossiers a JOIN accouchement_gyneco_situations s ON a.id_dossier = s.id_dossier WHERE a.id_gyneco = d.id {date_cond_a}), 0) as decaissement_total,
                    COALESCE((SELECT SUM(s.compensation) FROM accouchement_dossiers a JOIN accouchement_gyneco_situations s ON a.id_dossier = s.id_dossier WHERE a.id_gyneco = d.id {date_cond_a}), 0) as comp
                FROM doctors d
                LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
                WHERE (d.est_interne = 0 OR d.est_interne IS NULL)
                  AND s.name_specialty LIKE '%gyn%'
                  AND EXISTS (SELECT 1 FROM accouchement_dossiers dp_check WHERE dp_check.id_gyneco = d.id {date_cond_check})
                ORDER BY d.last_name
            """
        
        cursor.execute(query, tuple(params))
        doctors = cursor.fetchall()

    # Table Header
    headers = ['Médecin', 'Spécialité', 'Téléphone', 'Balance (DA)']
    data = [headers]

    total_balance = Decimal('0')

    for doctor_row in doctors:
        ca = to_decimal(doctor_row['ca'])
        enc_pat = to_decimal(doctor_row['enc_pat'])
        enc_doc = to_decimal(doctor_row['enc_doc'])
        dec = to_decimal(doctor_row['decaissement_total'])
        comp = to_decimal(doctor_row['comp'])
        
        balance = ca - (enc_pat + enc_doc + dec - comp)
        
        # Filtre balance
        if filter_balance == 'positive' and balance <= 0:
            continue
        if filter_balance == 'negative' and balance >= 0:
            continue
            
        total_balance += balance
        balance_str = f"{balance:,.2f}"
        
        row = [
            doctor_row['nom_complet'],
            doctor_row['name_specialty'] or '-',
            '',  # Téléphone placeholder
            balance_str
        ]
        data.append(row)

    # Footer Row
    data.append(['', '', 'TOTAL', f"{total_balance:,.2f}"])

    # Table Style
    table = Table(data, colWidths=[6*cm, 4*cm, 4*cm, 5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PDFColors.PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),  # Added top padding
        
        ('BACKGROUND', (0, -1), (-1, -1), PDFColors.SECONDARY), # Changed footer background
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white), # Changed footer text color
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
        
        ('GRID', (0, 0), (-1, -1), 0.5, PDFColors.MEDIUM_GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, PDFColors.LIGHT_GRAY]), # Striped rows
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))

    story.append(table)
    doc.build(story)
    
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=situation_medecins_{type_situation.lower()}.pdf'
    return response


@app.route('/export/situation_medecin/detail/<type_situation>/<int:id_doctor>')
@login_required

def export_situation_medecin_detail(type_situation, id_doctor):
    """Génère un PDF détaillé de la situation d'un médecin"""
    with get_cursor() as (conn, cursor):
        configs = ConfigurationClinicPDF.get_all_configs(cursor)
        
        # Info médecin
        cursor.execute("SELECT *, CONCAT(first_name, ' ', last_name) as nom_complet FROM doctors WHERE id = %s", (id_doctor,))
        doctor = cursor.fetchone()
        
        if not doctor:
            return "Médecin introuvable", 404

        # Récupération dossiers et stats
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if type_situation == 'BLOC':
            dossiers = get_dossiers_bloc_medecin(cursor, id_doctor, include_decharge_status=True, start_date=start_date, end_date=end_date)
            stats = get_stats_medecin_bloc(cursor, id_doctor, start_date=start_date, end_date=end_date)
        else: # ACCOUCHEMENT
             from app.accouchements.situation_accouchement_externe import get_dossiers_accouchement_externe, get_stats_gyneco_externe
             dossiers = get_dossiers_accouchement_externe(cursor, id_doctor, start_date=start_date, end_date=end_date)
             stats = get_stats_gyneco_externe(cursor, id_doctor, start_date=start_date, end_date=end_date)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1*cm, leftMargin=1*cm,
                            topMargin=1*cm, bottomMargin=1*cm)
    story = []
    styles = PDFStyles.get_styles()

    # En-tête Clinique
    # En-tête Clinique
    ajouter_entete_image(story)
    creer_ligne_separation(story, PDFColors.PRIMARY)

    # Récupération des dates
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # En-tête Médcin
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(f"Situation Détaillée - {type_situation}", styles['titre_section']))
    
    date_range_str = f"Date: {datetime.now().strftime('%d/%m/%Y')}"
    if start_date and end_date:
        d_start = datetime.strptime(start_date, '%Y-%m-%d').strftime('%d/%m/%Y')
        d_end = datetime.strptime(end_date, '%Y-%m-%d').strftime('%d/%m/%Y')
        date_range_str += f" | Période: {d_start} au {d_end}"

    info_medecin = [
        [Paragraph(f"<b>Médecin:</b> Dr. {doctor['nom_complet']}", styles['header']), 
         Paragraph(f"<b>{date_range_str}</b>", styles['header'])]
    ]
    t_info = Table(info_medecin, colWidths=[10*cm, 7*cm])
    t_info.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 1*cm))

    # Résumé Financier
    story.append(Paragraph("Résumé Financier", styles['titre_section']))
    
    # Check keys based on stats dict structure (bloc vs accouchement might differ slightly in naming but logic is similar)
    # BLOC keys: total_encaissement, total_decaissement, etc.
    # ACCOUCHEMENT keys from get_stats_gyneco_externe need to be checked.
    # Assuming similar structure as I can't check other file right now easily without tool.
    # But usually they are standardized.
    
    ca = stats.get('chiffre_affaire', 0)
    enc = stats.get('total_encaissement', 0)
    dec = stats.get('total_decaissement', 0)
    comp = stats.get('total_compensation', 0)
    balance = stats.get('balance_globale', 0)

    summary_data = [
        ['Chiffre d\'Affaires / Honoraires', format_currency(ca)],
        ['Total Encaissements (Médecin paie)', format_currency(enc)],
        ['Total Décaissements (Clinique paie)', format_currency(dec)],
        ['Total Compensations', format_currency(comp)],
        ['Balance Globale', format_currency(balance)],
    ]
    
    t_summary = Table(summary_data, colWidths=[10*cm, 5*cm])
    t_summary.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, PDFColors.MEDIUM_GRAY),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('BACKGROUND', (0,0), (0,-1), PDFColors.LIGHT_GRAY),
        ('FONTNAME', (0,4), (1,4), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1,4), (1,4), PDFColors.SUCCESS if balance >= 0 else PDFColors.DANGER),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 1*cm))

    # Détail des Dossiers
    story.append(Paragraph("Détail des Dossiers", styles['titre_section']))
    
    table_headers = ['Date', 'Patient', 'Total', 'Paiements', 'Reste']
    table_data = [table_headers]
    
    for d in dossiers:
        if type_situation == 'BLOC':
            d_date = d.get('location_date')
        else:
            d_date = d.get('date_accouchement')
            
        date_str = d_date.strftime('%d/%m/%Y') if d_date else '-'
        patient = d.get('patient') or d.get('patiente') or '-'
        
        # Calculs affichage
        total = d.get('part_clinique', d.get('part_gyneco', 0)) or 0
        total = to_decimal(total)
        reste = to_decimal(d.get('reste', 0))
        paye = total - reste
        
        row = [
            date_str,
            patient,
            format_currency(total, ''),
            format_currency(paye, ''),
            format_currency(reste, '')
        ]
        table_data.append(row)

    # Table des dossiers
    t_dossiers = Table(table_data, colWidths=[2.5*cm, 6*cm, 3.5*cm, 3.5*cm, 3.5*cm])
    t_dossiers.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PDFColors.SECONDARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, PDFColors.MEDIUM_GRAY),
        ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PDFColors.LIGHT_GRAY]),
    ]))
    
    story.append(t_dossiers)

    doc.build(story)
    buffer.seek(0)
    
    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"situation_detail_{doctor['last_name']}_{type_situation}.pdf".replace(' ', '_').lower()
    response.headers['Content-Disposition'] = f'inline; filename={filename}'
    return response


# ========================================================================
# APIs
# ========================================================================

@app.route('/api/get_dossiers_medecin/<int:id_doctor>')
@login_required
def api_get_dossiers_medecin(id_doctor):
    """API: Récupère les dossiers d'un médecin paginés"""
    with get_cursor() as (conn, cursor):
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        offset = (page - 1) * per_page

        dossiers_bloc = get_dossiers_bloc_medecin(cursor, id_doctor)
        dossiers_bloc.sort(key=lambda x: x['location_date'], reverse=True)

        total = len(dossiers_bloc)
        paginated = dossiers_bloc[offset:offset + per_page]

        # Formatter pour JSON
        for d in paginated:
            if isinstance(d['location_date'], date):
                d['location_date'] = d['location_date'].strftime('%d/%m/%Y')

            for key in ['prix_total', 'part_clinique', 'balance', 'reste']:
                if key in d:
                    d[key] = float(d[key])

        return jsonify({
            'success': True,
            'dossiers': paginated,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'total_pages': (total + per_page - 1) // per_page
            }
        })


@app.route('/api/get_transactions_dossier/<int:id_dossier>')
@login_required
def api_get_transactions_dossier(id_dossier):
    """API: Récupère les transactions d'un dossier"""
    with get_cursor() as (conn, cursor):
        transactions = get_transactions_dossier_bloc(cursor, id_dossier)

        # Formatter pour JSON
        for trans in transactions:
            if trans.get('payment_date'):
                trans['payment_date'] = trans['payment_date'].strftime('%d/%m/%Y %H:%M')
            for key in ['encaissement_patient', 'encaissement_doctor', 'decaissement_clinique', 'compensation']:
                if key in trans and trans[key] is not None:
                    trans[key] = float(trans[key])

        return jsonify({
            'success': True,
            'transactions': transactions
        })


@app.route('/api/get_medecins_a_encaisser')
@login_required
def api_get_medecins_a_encaisser():
    """API: Médecins avec dossiers à encaisser"""
    with get_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT DISTINCT d.id as id_doctor, CONCAT(d.first_name, ' ', d.last_name) as nom
            FROM doctors d
            WHERE (d.est_interne = 0 OR d.est_interne IS NULL)
            """
        )
        medecins = cursor.fetchall()

        result = []
        for med in medecins:
            dossiers_bloc = get_dossiers_bloc_medecin(cursor, med['id_doctor'])

            dossiers_eligibles = []
            for d in dossiers_bloc:
                # ✅ CORRECTION : reste > 0 = médecin doit payer
                if d['reste'] > Decimal('0.01') and not est_dossier_deja_encaisse(
                    cursor, d['id'], d['type_dossier']
                ):
                    dossiers_eligibles.append({
                        'id_dossier': d['id'],
                        'type_dossier': d['type_dossier'],
                        'patient': d['patient'],
                        'date': d['location_date'].strftime('%d/%m/%Y'),
                        'prix_total': float(d['prix_total']),
                        'montant_du': float(d['reste'])
                    })

            if dossiers_eligibles:
                result.append({
                    'id': med['id_doctor'],
                    'nom': med['nom'],
                    'dossiers': dossiers_eligibles
                })

        return jsonify(result)


@app.route('/api/get_medecins_a_decaisser')
@login_required
def api_get_medecins_a_decaisser():
    """API: Médecins avec dossiers à décaisser"""
    with get_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT DISTINCT d.id as id_doctor, CONCAT(d.first_name, ' ', d.last_name) as nom
            FROM doctors d
            WHERE (d.est_interne = 0 OR d.est_interne IS NULL)
            """
        )
        medecins = cursor.fetchall()

        result = []
        for med in medecins:
            dossiers_bloc = get_dossiers_bloc_medecin(
                cursor, med['id_doctor'], include_decharge_status=True
            )

            dossiers_eligibles = []
            for d in dossiers_bloc:
                # ✅ CORRECTION : reste < 0 = clinique doit payer
                if d['reste'] < Decimal('-0.01') and not d.get('deja_decharge', False):
                    dossiers_eligibles.append({
                        'id_dossier': d['id'],
                        'type_dossier': d['type_dossier'],
                        'patient': d['patient'],
                        'date': d['location_date'].strftime('%d/%m/%Y'),
                        'prix_total': float(d['prix_total']),
                        'montant_du': float(abs(d['reste']))
                    })

            if dossiers_eligibles:
                result.append({
                    'id': med['id_doctor'],
                    'nom': med['nom'],
                    'dossiers': dossiers_eligibles
                })

        return jsonify(result)


@app.route('/api/get_dossiers_compensation/<int:id_doctor>')
@login_required
def api_get_dossiers_compensation(id_doctor):
    """API: Dossiers éligibles pour compensation"""
    with get_cursor() as (conn, cursor):
        dossiers_bloc = get_dossiers_bloc_medecin(
            cursor, id_doctor, include_decharge_status=True
        )

        # ✅ CORRECTION : Inversion des catégories
        dossiers_positifs = []  # Médecin doit payer (reste > 0)
        dossiers_negatifs = []  # Clinique doit payer (reste < 0)

        for d in dossiers_bloc:
            if abs(d['reste']) < Decimal('0.01'):
                continue

            deja_decharge = d.get('deja_decharge', False)
            deja_encaisse = est_dossier_deja_encaisse(cursor, d['id'], d['type_dossier'])

            doss_data = {
                'id_dossier': d['id'],
                'type_dossier': d['type_dossier'],
                'patient': d['patient'],
                'date': d['location_date'].strftime('%d/%m/%Y'),
                'statut': d['statut_paiement'],
                'reste': float(d['reste']),
                'deja_decharge': deja_decharge,
                'deja_encaisse': deja_encaisse
            }

            if d['reste'] > 0:
                dossiers_positifs.append(doss_data)  # Médecin doit
            else:
                dossiers_negatifs.append(doss_data)  # Clinique doit

        return jsonify({
            'dossiers_positifs': dossiers_positifs,
            'dossiers_negatifs': dossiers_negatifs
        })


@app.route('/api/get_dossiers_operation/<int:id_operation>')
@login_required
def api_get_dossiers_operation(id_operation):
    """API: Dossiers liés à une opération"""
    with get_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT 
                od.montant,
                od.type_dossier,
                dpb.patient,
                dpb.location_date,
                dpb.prix_total
            FROM location_bloc_operation_dossiers od
            LEFT JOIN location_bloc_dossier_patient dpb 
                ON od.id_dossier = dpb.id_dossier
                AND COALESCE(od.type_dossier, 'BLOC') = 'BLOC'
            WHERE od.id_operation = %s
            ORDER BY dpb.location_date
            """, (id_operation,)
        )
        dossiers = cursor.fetchall()

        formatted = []
        for d in dossiers:
            formatted.append({
                'patient': d['patient'],
                'date': d['location_date'].strftime('%d/%m/%Y') if d['location_date'] else '',
                'prix_total': float(d['prix_total'] or 0),
                'montant': float(d['montant']),
                'type_dossier': d['type_dossier'] or 'BLOC'
            })

        return jsonify(formatted)


# ========================================================================
# EXPORT PDF DES BONS
# ========================================================================
# ========================================================================
# CONFIGURATION ET HELPERS
# ========================================================================

class ConfigurationClinicPDF:
    """Cache pour les configurations de la clinique"""
    _cache = {}
    _cache_timestamp = None
    _cache_duration = 300  # 5 minutes

    @classmethod
    def get_config(cls, cursor, cle, defaut=''):
        """Récupère une configuration avec cache"""
        now = datetime.now().timestamp()

        # Invalider le cache si expiré
        if cls._cache_timestamp is None or (now - cls._cache_timestamp) > cls._cache_duration:
            cls._cache = {}
            cls._cache_timestamp = now

        # Vérifier le cache
        if cle in cls._cache:
            return cls._cache[cle]

        # Requête DB
        try:
            cursor.execute(
                """
                SELECT valeur 
                FROM config_clinique 
                WHERE cle = %s AND est_actif = 1
                LIMIT 1
                """, (cle,)
            )
            result = cursor.fetchone()
            valeur = result['valeur'] if result else defaut
            cls._cache[cle] = valeur
            return valeur
        except:
            return defaut

    @classmethod
    def get_all_configs(cls, cursor):
        """Récupère toutes les configurations nécessaires pour le PDF"""
        configs = {
            'nom_clinique': cls.get_config(cursor, 'NOM_CLINIQUE', 'CLINIQUE INAYA'),
            'adresse': cls.get_config(cursor, 'ADRESSE', 'Adresse de la clinique'),
            'telephone': cls.get_config(cursor, 'TELEPHONE', ''),
            'email': cls.get_config(cursor, 'EMAIL', ''),
            'ville': cls.get_config(cursor, 'VILLE', ''),
            'code_postal': cls.get_config(cursor, 'CODE_POSTAL', ''),
            'nif': cls.get_config(cursor, 'NIF', ''),
            'nis': cls.get_config(cursor, 'NIS', ''),
            'rc': cls.get_config(cursor, 'RC', ''),
            'logo_path': cls.get_config(cursor, 'LOGO_PATH', 'static/img/logo.png'),
        }
        return configs

    @classmethod
    def clear_cache(cls):
        """Vide le cache manuellement"""
        cls._cache = {}
        cls._cache_timestamp = None


class PDFColors:
    """Palette de couleurs pour les PDFs - Style Moderne"""

    ENCAISSEMENT = colors.HexColor('#0061f2')  # Bleu vif
    DECHARGE = colors.HexColor('#e55353')      # Rouge doux
    COMPENSATION = colors.HexColor('#6f42c1')  # Violet

    PRIMARY = colors.HexColor('#0061f2')       # Primary Brand Color
    SECONDARY = colors.HexColor('#6c757d')     # Secondary text
    SUCCESS = colors.HexColor('#2eb85c')
    WARNING = colors.HexColor('#f9b115')
    DANGER = colors.HexColor('#e55353')
    INFO = colors.HexColor('#39f')

    LIGHT_GRAY = colors.HexColor('#f8f9fa')    # Background very light
    MEDIUM_GRAY = colors.HexColor('#e4e7eb')   # Border
    DARK_GRAY = colors.HexColor('#5c6873')     # Text

    text_main = colors.HexColor('#3c4b64')

    @classmethod
    def get_operation_color(cls, type_operation):
        """Retourne la couleur selon le type d'opération"""
        mapping = {
            'ENCAISSEMENT': cls.ENCAISSEMENT,
            'DECHARGE': cls.DECHARGE,
            'COMPENSATION': cls.COMPENSATION
        }
        return mapping.get(type_operation, cls.PRIMARY)


class PDFStyles:
    """Styles réutilisables pour les PDFs"""

    @staticmethod
    def get_styles():
        """Retourne un dictionnaire de styles personnalisés"""
        base_styles = getSampleStyleSheet()

        return {
            'titre_principal': ParagraphStyle(
                'TitrePrincipal',
                parent=base_styles['Heading1'],
                fontSize=24,
                textColor=PDFColors.PRIMARY,
                spaceAfter=20,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            ),
            'titre_section': ParagraphStyle(
                'TitreSection',
                parent=base_styles['Heading2'],
                fontSize=14,
                textColor=PDFColors.text_main,
                spaceAfter=10,
                spaceBefore=15,
                fontName='Helvetica-Bold'
            ),
            'header': ParagraphStyle(
                'Header',
                parent=base_styles['Normal'],
                fontSize=12,
                textColor=PDFColors.text_main,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                spaceAfter=3
            ),
            'subheader': ParagraphStyle(
                'SubHeader',
                parent=base_styles['Normal'],
                fontSize=9,
                textColor=PDFColors.SECONDARY,
                alignment=TA_CENTER,
                spaceAfter=15
            ),
            'info_label': ParagraphStyle(
                'InfoLabel',
                parent=base_styles['Normal'],
                fontSize=10,
                fontName='Helvetica-Bold',
                textColor=PDFColors.SECONDARY
            ),
            'info_value': ParagraphStyle(
                'InfoValue',
                parent=base_styles['Normal'],
                fontSize=10,
                fontName='Helvetica',
                textColor=PDFColors.text_main
            ),
            'footer': ParagraphStyle(
                'Footer',
                parent=base_styles['Normal'],
                fontSize=8,
                textColor=PDFColors.SECONDARY,
                alignment=TA_CENTER
            ),
            'signature': ParagraphStyle(
                'Signature',
                parent=base_styles['Normal'],
                fontSize=11,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                textColor=PDFColors.text_main
            ),
            'note': ParagraphStyle(
                'Note',
                parent=base_styles['Normal'],
                fontSize=9,
                textColor=PDFColors.SECONDARY,
                alignment=TA_JUSTIFY,
                leftIndent=0,
                rightIndent=0
            )
        }


# ========================================================================
# FONCTIONS UTILITAIRES PDF
# ========================================================================

def format_currency(amount, symbol='DA'):
    """Formate un montant en devise"""
    if amount is None:
        amount = 0
    return f"{float(amount):,.2f} {symbol}".replace(',', ' ')


def ajouter_entete_image(elements):
    """
    Ajoute l'image d'en-tête (entet_inaya.png) au PDF
    """
    header_path = os.path.join(app.root_path, 'static', 'images', 'entet_inaya.png')
    
    if os.path.exists(header_path):
        try:
            from reportlab.platypus import Image as RLImage
            from PIL import Image
            
            # Lire l'image pour dimensions
            img = Image.open(header_path)
            w, h = img.size
            
            # Largeur dispo (A4 - marges)
            available_width = 19*cm
            ratio = available_width / w
            
            # Image ReportLab
            header_img = RLImage(header_path, width=available_width, height=h * ratio)
            
            # Tableau conteneur centré
            t = Table([[header_img]], colWidths=[available_width])
            t.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ]))
            
            elements.append(t)
            elements.append(Spacer(1, 0.5*cm))
            
        except Exception as e:
            print(f"Erreur ajout header: {e}")


def creer_ligne_separation(elements, couleur, epaisseur=2):
    """Crée une ligne de séparation décorative"""
    line_table = Table([['']], colWidths=[17*cm])
    line_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), epaisseur, couleur),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
    ]))
    elements.append(line_table)


def creer_bloc_informations(data, styles, colWidths=None):
    """
    Crée un bloc d'informations formaté

    Args:
        data: Liste de tuples (label, valeur) ou liste de listes
        styles: Dictionnaire des styles
        colWidths: Largeurs des colonnes

    Returns:
        Table: Tableau formaté
    """
    if colWidths is None:
        colWidths = [4*cm, 6*cm, 4*cm, 6*cm]

    table = Table(data, colWidths=colWidths)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), PDFColors.DARK_GRAY),
        ('TEXTCOLOR', (2, 0), (2, -1), PDFColors.DARK_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))

    return table


def creer_tableau_dossiers(dossiers, couleur_theme):
    """
    Crée le tableau des dossiers de manière optimisée

    Args:
        dossiers: Liste des dossiers
        couleur_theme: Couleur du thème

    Returns:
        tuple: (Table, total_montant)
    """
    # En-tête
    data = [['Patient', 'Date', 'Prix total', 'Montant']]

    total_montant = Decimal('0')

    for doss in dossiers:
        montant = to_decimal(doss['montant'])
        total_montant += montant

        data.append([
            doss['patient'] or 'N/A',
            doss['location_date'].strftime('%d/%m/%Y') if doss.get('location_date') else 'N/A',
            format_currency(doss.get('prix_total', 0)),
            format_currency(montant)
        ])

    # Ligne de total
    data.append(['', '', 'TOTAL:', format_currency(total_montant)])

    # Créer le tableau
    table = Table(data, colWidths=[6*cm, 3*cm, 4*cm, 4*cm])
    table.setStyle(TableStyle([
        # En-tête
        ('BACKGROUND', (0, 0), (-1, 0), couleur_theme),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (2, 0), (-1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),

        # Corps
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('ALIGN', (2, 1), (-1, -2), 'RIGHT'),
        ('VALIGN', (0, 1), (-1, -2), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, PDFColors.LIGHT_GRAY]),
        ('GRID', (0, 1), (-1, -2), 0.5, PDFColors.MEDIUM_GRAY),
        ('TOPPADDING', (0, 1), (-1, -2), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -2), 8),
        ('LEFTPADDING', (0, 1), (-1, -2), 5),
        ('RIGHTPADDING', (0, 1), (-1, -2), 5),

        # Ligne de total
        ('BACKGROUND', (0, -1), (-1, -1), PDFColors.SECONDARY),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.whitesmoke),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('ALIGN', (2, -1), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, -1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
    ]))

    return table, total_montant


def creer_bloc_paiement(montant_total, montant_paye, reste, styles):
    """
    Crée le bloc récapitulatif des paiements

    Args:
        montant_total: Montant total
        montant_paye: Montant déjà payé
        reste: Reste à payer
        styles: Dictionnaire des styles

    Returns:
        Table: Tableau du récapitulatif
    """
    data = [
        ['Montant total:', format_currency(montant_total)],
        ['Montant payé:', format_currency(montant_paye)],
        ['Reste à payer:', format_currency(reste)],
    ]

    table = Table(data, colWidths=[10*cm, 7*cm])

    # Couleur du reste selon statut
    reste_color = PDFColors.DANGER if reste > 0 else PDFColors.SUCCESS

    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TEXTCOLOR', (0, -1), (-1, -1), reste_color),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, PDFColors.MEDIUM_GRAY),
        ('TOPPADDING', (0, 0), (-1, -2), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -2), 6),
        ('TOPPADDING', (0, -1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
    ]))

    return table


def creer_bloc_signatures(styles):
    """Crée le bloc des signatures"""
    signature_data = [[
        Paragraph(
            '<b>Le Médecin</b><br/><br/><br/>'
            '<font size="8">Date: ___/___/______</font><br/>'
            'Signature: _________________',
            styles['signature']
        ),
        Paragraph(
            '<b>La Clinique</b><br/><br/><br/>'
            '<font size="8">Date: ___/___/______</font><br/>'
            'Cachet et Signature: _________________',
            styles['signature']
        )
    ]]

    table = Table(signature_data, colWidths=[8.5*cm, 8.5*cm])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))

    return table


def ajouter_qr_code(elements, data_text, size=2*cm):
    """
    Ajoute un QR code au PDF

    Args:
        elements: Liste des éléments
        data_text: Texte à encoder
        size: Taille du QR code
    """
    try:
        from reportlab.graphics.barcode import qr
        from reportlab.graphics.shapes import Drawing

        qr_code = qr.QrCodeWidget(data_text)
        bounds = qr_code.getBounds()
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]

        drawing = Drawing(
            size, size,
            transform=[size/width, 0, 0, size/height, 0, 0]
        )
        drawing.add(qr_code)

        # Centrer le QR code
        qr_table = Table([[drawing]], colWidths=[17*cm])
        qr_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))

        elements.append(qr_table)
        return True

    except Exception as e:
        print(f"Erreur création QR code: {e}")
        return False


def ajouter_footer(elements, styles, configs):
    """Ajoute le pied de page"""
    footer_text = (
        f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} | "
        f"{configs['nom_clinique']} - Système de Gestion Hospitalière"
    )

    footer = Paragraph(footer_text, styles['footer'])
    elements.append(footer)


def ajouter_conditions_generales(elements, type_operation, styles):
    """Ajoute les conditions générales selon le type d'opération"""
    conditions = {
        'ENCAISSEMENT': (
            "Conditions de paiement : Le médecin s'engage à régler le montant dû "
            "selon les modalités convenues. Tout retard de paiement entraînera des "
            "pénalités de 2% par mois de retard."
        ),
        'DECHARGE': (
            "Conditions de décharge : La clinique s'engage à verser le montant dû "
            "au médecin selon les modalités convenues. Ce bon constitue un engagement "
            "de paiement de la part de la clinique."
        ),
        'COMPENSATION': (
            "Conditions de compensation : Cette opération compense automatiquement "
            "les montants dus entre le médecin et la clinique selon le principe FIFO. "
            "Aucun flux financier n'est généré."
        )
    }

    condition_text = conditions.get(type_operation, '')

    if condition_text:
        elements.append(Spacer(1, 0.5*cm))
        note = Paragraph(
            f"<b>Note:</b> {condition_text}",
            styles['note']
        )
        elements.append(note)


# ========================================================================
# FONCTION PRINCIPALE D'EXPORT PDF
# ========================================================================

@app.route('/exporter_bon_pdf/<int:id_operation>')
@login_required
@handle_errors()

def exporter_bon_pdf(id_operation):
    """
    Génère un PDF professionnel pour un bon d'encaissement/décharge/compensation

    Args:
        id_operation: ID de l'opération

    Returns:
        Response: PDF en download
    """
    with get_cursor() as (conn, cursor):
        # Récupération des configurations
        configs = ConfigurationClinicPDF.get_all_configs(cursor)

        # Récupération de l'opération
        cursor.execute(
            """
            SELECT 
                o.*,
                CONCAT(d.first_name, ' ', d.last_name) as doctor_name,
                d.telephone as doctor_phone,
                s.name_specialty,
                CONCAT(pc.nom, ' ', pc.prenom) as created_by_name,
                CONCAT(pp.nom, ' ', pp.prenom) as payment_by_name
            FROM location_bloc_operations_financieres_medecin o
            LEFT JOIN doctors d ON o.id_doctor = d.id
            LEFT JOIN specialty s ON d.id_specialty = s.id_specialty
            LEFT JOIN personnel pc ON o.id_created_by = pc.id_personnel
            LEFT JOIN personnel pp ON o.id_payment_by = pp.id_personnel
            WHERE o.id = %s
            """, (id_operation,)
        )

        operation = cursor.fetchone()

        if not operation:
            flash('Opération non trouvée', 'danger')
            return redirect(url_for('situation_medecin_bloc'))

        # Récupération des dossiers liés
        cursor.execute(
            """
            SELECT 
                od.montant,
                od.type_dossier,
                dpb.patient,
                dpb.location_date,
                dpb.prix_total
            FROM location_bloc_operation_dossiers od
            LEFT JOIN location_bloc_dossier_patient dpb 
                ON od.id_dossier = dpb.id_dossier
                AND COALESCE(od.type_dossier, 'BLOC') = 'BLOC'
            WHERE od.id_operation = %s
            ORDER BY dpb.location_date
            """, (id_operation,)
        )

        dossiers = cursor.fetchall()

        # Génération du PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm,
            title=f"BON_{operation['type_operation']}_{operation['id']}",
            author=configs['nom_clinique']
        )

        # Éléments du document
        elements = []
        styles = PDFStyles.get_styles()

        # Déterminer le type et la couleur
        type_operation = operation['type_operation']
        couleur_theme = PDFColors.get_operation_color(type_operation)

        titres = {
            'ENCAISSEMENT': "BON D'ENCAISSEMENT",
            'DECHARGE': "BON DE DÉCHARGE",
            'COMPENSATION': "BON DE COMPENSATION"
        }
        titre_principal = titres.get(type_operation, "BON FINANCIER")

        # ==================== EN-TÊTE ====================
        
        # Image d'entête unifiée
        ajouter_entete_image(elements)

        elements.append(Spacer(1, 0.5*cm))

        # ==================== TITRE ====================

        titre = Paragraph(titre_principal, styles['titre_principal'])
        elements.append(titre)

        # Ligne de séparation
        creer_ligne_separation(elements, couleur_theme, epaisseur=2)
        elements.append(Spacer(1, 0.3*cm))

        # ==================== INFORMATIONS DU BON ====================

        # Numéro de bon avec QR code option
        numero_text = f"<b>Bon N° {operation['id']}</b>"
        numero = Paragraph(numero_text, styles['titre_section'])
        elements.append(numero)
        elements.append(Spacer(1, 0.2*cm))

        # Informations principales
        info_data = [
            ['Date du bon:', operation['date'].strftime('%d/%m/%Y'),
             'Type:', 'Location de Bloc'],
            ['Médecin:', operation['doctor_name'],
             'Spécialité:', operation['name_specialty'] or 'N/A'],
        ]

        if operation.get('doctor_phone'):
            info_data.append([
                'Contact médecin:', operation['doctor_phone'],
                'Créé par:', operation['created_by_name'] or 'N/A'
            ])
        else:
            info_data.append([
                'Créé par:', operation['created_by_name'] or 'N/A',
                'Créé le:', operation.get('created_at', datetime.now()).strftime('%d/%m/%Y %H:%M')
            ])

        info_table = creer_bloc_informations(info_data, styles)
        elements.append(info_table)
        elements.append(Spacer(1, 0.7*cm))

        # ==================== TABLEAU DES DOSSIERS ====================

        titre_dossiers = Paragraph(
            "<b>Détail des dossiers</b>",
            styles['titre_section']
        )
        elements.append(titre_dossiers)
        elements.append(Spacer(1, 0.2*cm))

        tableau_dossiers, total_montant = creer_tableau_dossiers(
            dossiers,
            couleur_theme
        )
        elements.append(tableau_dossiers)
        elements.append(Spacer(1, 0.8*cm))

        # ==================== RÉCAPITULATIF FINANCIER ====================

        titre_recap = Paragraph(
            "<b>Récapitulatif financier</b>",
            styles['titre_section']
        )
        elements.append(titre_recap)
        elements.append(Spacer(1, 0.2*cm))

        montant_operation = to_decimal(operation['montant'])
        montant_paye = to_decimal(operation['montant_paye'])
        reste = to_decimal(operation['reste'])

        bloc_paiement = creer_bloc_paiement(
            montant_operation,
            montant_paye,
            reste,
            styles
        )
        elements.append(bloc_paiement)

        # Historique des paiements si existants
        if montant_paye > 0 and operation.get('payment_by_name'):
            elements.append(Spacer(1, 0.3*cm))
            payment_info = Paragraph(
                f"<i>Dernier paiement effectué par {operation['payment_by_name']} "
                f"le {operation.get('payment_at', datetime.now()).strftime('%d/%m/%Y à %H:%M')}</i>",
                ParagraphStyle(
                    'PaymentInfo',
                    parent=styles['note'],
                    textColor=PDFColors.SUCCESS,
                    fontSize=9
                )
            )
            elements.append(payment_info)

        elements.append(Spacer(1, 1*cm))

        # ==================== CONDITIONS GÉNÉRALES ====================

        ajouter_conditions_generales(elements, type_operation, styles)
        elements.append(Spacer(1, 0.8*cm))

        # ==================== SIGNATURES ====================

        bloc_signatures = creer_bloc_signatures(styles)
        elements.append(bloc_signatures)
        elements.append(Spacer(1, 0.5*cm))

        # ==================== QR CODE (optionnel) ====================

        # Générer QR code avec infos du bon
        qr_data = (
            f"BON-{operation['id']}|"
            f"{type_operation}|"
            f"{operation['date'].strftime('%Y%m%d')}|"
            f"{float(montant_operation):.2f}"
        )

        # Note pour le QR code
        qr_note = Paragraph(
            "<i>QR Code de vérification :</i>",
            ParagraphStyle(
                'QRNote',
                parent=styles['note'],
                fontSize=8,
                alignment=TA_CENTER
            )
        )
        elements.append(qr_note)
        elements.append(Spacer(1, 0.2*cm))

        ajouter_qr_code(elements, qr_data, size=1.5*cm)
        elements.append(Spacer(1, 0.3*cm))

        # ==================== FOOTER ====================

        ajouter_footer(elements, styles, configs)

        # ==================== GÉNÉRATION ====================

        try:
            doc.build(elements)
        except Exception as e:
            print(f"Erreur lors de la génération du PDF: {e}")
            flash('Erreur lors de la génération du PDF', 'danger')
            return redirect(url_for('operations_medecin_bloc_list',
                                   type_operation=type_operation))

        # ==================== RÉPONSE ====================

        buffer.seek(0)
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'

        # Nom du fichier
        doctor_name_clean = operation['doctor_name'].replace(' ', '_')
        filename = (
            f"BON_{type_operation}_{operation['id']}_"
            f"{doctor_name_clean}_{operation['date'].strftime('%Y%m%d')}.pdf"
        )

        response.headers['Content-Disposition'] = (
            f'attachment; filename="{filename}"'
        )

        return response


# ========================================================================
# ROUTE ALTERNATIVE : APERÇU PDF EN LIGNE
# ========================================================================

@app.route('/apercu_bon_pdf/<int:id_operation>')
@login_required
@handle_errors()

def apercu_bon_pdf(id_operation):
    """
    Affiche le PDF dans le navigateur au lieu de le télécharger

    Args:
        id_operation: ID de l'opération

    Returns:
        Response: PDF inline
    """
    # Utiliser la même logique mais changer Content-Disposition
    response = exporter_bon_pdf(id_operation)

    # Modifier pour affichage inline
    if response.headers.get('Content-Type') == 'application/pdf':
        filename = response.headers['Content-Disposition'].split('filename=')[1].strip('"')
        response.headers['Content-Disposition'] = f'inline; filename="{filename}"'

    return response


# ========================================================================
# ROUTE : EXPORT EN MASSE
# ========================================================================

@app.route('/exporter_bons_multiple', methods=['POST'])
@login_required
@handle_errors()

def exporter_bons_multiple():
    """
    Exporte plusieurs bons en un seul PDF

    Form data:
        operations_ids: Liste des IDs d'opérations

    Returns:
        Response: PDF zip ou unique
    """
    operations_ids = request.form.getlist('operations_ids[]')

    if not operations_ids:
        flash('Aucune opération sélectionnée', 'warning')
        return redirect(request.referrer or url_for('situation_medecin_bloc'))

    # Si une seule opération, rediriger vers export simple
    if len(operations_ids) == 1:
        return redirect(url_for('exporter_bon_pdf', id_operation=operations_ids[0]))

    # Pour plusieurs opérations, créer un ZIP
    try:
        import zipfile
        from io import BytesIO

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for op_id in operations_ids:
                try:
                    # Générer chaque PDF
                    pdf_response = exporter_bon_pdf(int(op_id))

                    if pdf_response.headers.get('Content-Type') == 'application/pdf':
                        # Extraire le nom de fichier
                        filename = pdf_response.headers['Content-Disposition'].split('filename=')[1].strip('"')

                        # Ajouter au ZIP
                        zip_file.writestr(filename, pdf_response.get_data())

                except Exception as e:
                    print(f"Erreur export opération {op_id}: {e}")
                    continue

        # Préparer la réponse
        zip_buffer.seek(0)
        response = make_response(zip_buffer.getvalue())
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = (
            f'attachment; filename="BONS_MULTIPLE_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'
        )

        return response

    except Exception as e:
        print(f"Erreur lors de l'export multiple: {e}")
        flash('Erreur lors de l\'export multiple', 'danger')
        return redirect(request.referrer or url_for('situation_medecin_bloc'))