"""
APIs Flask pour consulter DIRECTEMENT les données HIS depuis PostgreSQL
Sans synchronisation - Lecture en temps réel
VERSION OPTIMISÉE avec détection de doublons et fusion d'historique
"""

import logging
from collections import defaultdict
from datetime import timedelta, date, datetime
from decimal import Decimal
from functools import wraps

import unicodedata
from dateutil import parser
from flask import render_template, jsonify, request
from rapidfuzz import fuzz

from app import app, get_pg_connection, safe_pg_execute, get_db_connection
from app.utils.utiles import login_required


logger = logging.getLogger(__name__)

# =====================================================
# CONSTANTES
# =====================================================
PAYMENT_TYPE_ENCAISSEMENT = 1
PAYMENT_TYPE_DECAISSEMENT = 0
GENDER_MALE = 1
GENDER_FEMALE = 2
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100
SIMILARITY_THRESHOLD = 85

# =====================================================
# DÉCORATEURS ET UTILITAIRES
# =====================================================

def handle_pg_errors(f):
    """Décorateur pour gérer les erreurs PostgreSQL"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        pg_conn = None
        pg_cur = None
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Erreur dans {f.__name__}: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f"Erreur serveur: {str(e)}"
            }), 500
        finally:
            if pg_cur:
                pg_cur.close()
            if pg_conn:
                pg_conn.close()
    return decorated_function


def pg_decimal_to_float(obj):
    """Convertir les types PostgreSQL en types JSON-sérialisables"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, timedelta):
        return obj.days
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: pg_decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [pg_decimal_to_float(item) for item in obj]
    return obj


def pg_row_to_dict(cursor, row):
    """Convertir une ligne PostgreSQL en dictionnaire avec clés en minuscules"""
    if not row:
        return None
    columns = [desc[0].lower() for desc in cursor.description]
    return dict(zip(columns, row))


def pg_rows_to_dict_list(cursor, rows):
    """Convertir plusieurs lignes PostgreSQL en liste de dictionnaires"""
    if not rows:
        return []
    columns = [desc[0].lower() for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def normalize_text(text):
    """Normaliser le texte pour comparaison"""
    if not text:
        return ""
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def format_gender(gender_value):
    """Formater la valeur du genre"""
    if gender_value in (GENDER_MALE, 'M', 'm'):
        return 'Homme'
    elif gender_value in (GENDER_FEMALE, 'F', 'f'):
        return 'Femme'
    return 'Non spécifié'


def format_date_string(date_value):
    """Formater une date en string"""
    if not date_value:
        return 'N/A'
    try:
        if isinstance(date_value, str):
            return date_value[:10]
        return date_value.strftime('%Y-%m-%d')
    except:
        return 'N/A'


# =====================================================
# REQUÊTES SQL OPTIMISÉES
# =====================================================

class SQLQueries:
    """Centralisation des requêtes SQL"""

    PATIENT_BASE_SELECT = '''
        SELECT 
            p."OID" as oid,
            p."Code" as code,
            p."FirstName" as first_name,
            p."LastName" as last_name,
            p."BirthDate" as birth_date,
            p."Gender" as gender,
            p."IdCardNumber" as id_card_number,
            EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) as age
    '''

    PATIENT_DETAILS = PATIENT_BASE_SELECT + ''',
            p."ThirdParty" as third_party,
            p."CardIdIssuance" as card_id_issuance,
            p."ModifiedOn" as sync_date,
            tp."Name" as third_party_name,
            tp."Mobile" as mobile,
            tp."Telephone" as telephone,
            tp."Email" as email,
            p."FirstName" || ' ' || p."LastName" as full_name
        FROM "Patient" p
        LEFT JOIN "ThirdParty" tp ON p."ThirdParty" = tp."OID"
    '''

    HOSPITALIZATIONS = '''
        SELECT 
            h."OID" as patient_oid,
            h."Code" as code,
            h."Patient",
            h."StartDate" as start_date,
            h."EndDate" as end_date,
            h."Amount" as amount,
            h."PatientPart" as patient_part,
            h."PatientPayment" as patient_payment,
            h."InsurancePayment" as insurance_payment,
            h."RestToPay" as rest_to_pay,
            h."Note" as note,
            d."FirstName" as doctor_first_name,
            d."LastName" as doctor_last_name,
            s."Label" as speciality_label,
            ms."Label" as service_label,
            r."Label" as room_label,
            p."Code" as patient_code,
            (COALESCE(h."EndDate"::date, CURRENT_DATE) - h."StartDate"::date) as nights_count
        FROM "Hospitalization" h
        LEFT JOIN "Doctor" d ON h."TreatingDoctor" = d."OID"
        LEFT JOIN "Speciality" s ON d."Speciality" = s."OID"
        LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
        LEFT JOIN "Room" r ON h."Room" = r."OID"
        LEFT JOIN "Patient" p ON h."Patient" = p."OID"
    '''

    PAYMENTS = '''
        SELECT 
            p."OID" as oid,
            p."Code" as code,
            p."Label" as label,
            p."Date" as date,
            p."Amount" as amount,
            p."Type" as type,
            p."Note" as note,
            pc."Label" as category_label,
            pt."Label" as type_label,
            pt."Type" as type_code,
            pat."Code" as patient_code
        FROM "Payment" p
        LEFT JOIN "PaymentCategory" pc ON p."Category" = pc."OID"
        LEFT JOIN "PaymentType" pt ON p."Type" = pt."OID"
        JOIN "ThirdParty" tp ON p."ThirdParty" = tp."OID"
        LEFT JOIN "Patient" pat ON tp."Patient" = pat."OID"
    '''

    MEDICAL_ACTS = '''
        SELECT 
            ma."OID" as oid,
            ma."Code" as code,
            ma."Label" as label,
            ma."Amount" as amount,
            ma."PatientPart" as patient_part,
            ma."PatientPayment" as patient_payment,
            ma."InsurancePayment" as insurance_payment,
            ma."ModifiedOn" as sync_date,
            mat."Label" as type_label,
            p."Code" as patient_code
        FROM "MedicalAct" ma
        LEFT JOIN "MedicalActType" mat ON ma."Type" = mat."OID"
        LEFT JOIN "Patient" p ON ma."Patient" = p."OID"
    '''
    LAB_EXAMS = '''
                SELECT le."OID"              as oid, 
                       le."Code"             as code, 
                       le."Label"            as label, 
                       le."Amount"           as amount, 
                       le."PatientPart"      as patient_part, 
                       le."PatientPayment"   as patient_payment, 
                       le."InsurancePayment" as insurance_payment, 
                       le."ModifiedOn"       as sync_date, 
                       le."RequestDate"      as request_date, 
                       le."SamplingDate"     as sampling_date, 
                       le."ValidatedOn"      as validated_on, 
                       le."Status"           as status, 
                       le."IsUrgent"         as is_urgent, 
                       le."Locked"           as locked, 
                       p."Code"              as patient_code, 
                       h."Code"              as hospitalization_code, 
                       h."StartDate"         as hospitalization_start, 
                       ms."Label"            as hospitalization_service, 
                       validator."FirstName" as validated_by_first_name, 
                       validator."LastName"  as validated_by_last_name, 
                       stage."Label"         as stage_label 
                FROM "LabExam" le
                         LEFT JOIN "Patient" p ON le."Patient" = p."OID"
                         LEFT JOIN "Hospitalization" h ON le."Hospitalization" = h."OID"
                         LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
                         LEFT JOIN "Doctor" validator ON le."ValidatedBy" = validator."OID"
                         LEFT JOIN "LabExamStage" stage ON le."Stage" = stage."OID" 
                '''

    # Dans la classe SQLQueries, remplacer NURSINGS par :
    NURSINGS = '''
               SELECT n."OID"              as oid, 
                      n."Code"             as code, 
                      n."Amount"           as amount, 
                      n."PatientPart"      as patient_part, 
                      n."PatientPayment"   as patient_payment, 
                      n."InsurancePayment" as insurance_payment, 
                      n."Date"             as date, 
                      n."Note"             as note, 
                      n."Status"           as status, 
                      p."Code"             as patient_code, 
                      h."Code"             as hospitalization_code, 
                      h."StartDate"        as hospitalization_start, 
                      ms."Label"           as hospitalization_service, 
                      nurse."FirstName"    as nurse_first_name, 
                      nurse."LastName"     as nurse_last_name, 
        nd."Observation" as observation,
        nd."Amount" as detail_amount,
        nd."Quantity" as quantity,
        nd."PatientPart" as detail_patient_part,
        nd."IsDone" as is_done,
                      na."Label"           as nursing_act_label, 
        na."Code" as nursing_act_code
               FROM "Nursing" n
                        LEFT JOIN "Patient" p ON n."Patient" = p."OID"
                        LEFT JOIN "Hospitalization" h ON n."Hospitalization" = h."OID"
                        LEFT JOIN "MedicalService" ms ON h."Service" = ms."OID"
                        LEFT JOIN "User" nurse ON n."Nurse" = nurse."OID"
    LEFT JOIN "NursingDetail" nd ON n."OID" = nd."Nursing"
    LEFT JOIN "NursingAct" na ON nd."NursingAct" = na."OID"
               '''

    RADIO_REQUESTS = '''
        SELECT 
            rr."OID" as oid,
            rr."Code" as code,
            rr."Amount" as amount,
            rr."PatientPart" as patient_part,
            rr."PatientPayment" as patient_payment,
            rr."InsurancePayment" as insurance_payment,
            rr."Date" as date,
            p."Code" as patient_code
        FROM "RadioRequest" rr
        LEFT JOIN "Patient" p ON rr."Patient" = p."OID"
    '''


# =====================================================
# SERVICES MÉTIER
# =====================================================

class PatientHistoryService:
    """Service pour gérer l'historique patient"""

    @staticmethod
    def calculate_balance(hospitalizations, medical_acts, lab_exams, nursings, radio_requests, encaissements):
        """Calculer la balance financière"""
        total_amount = (
            sum(h.get('amount', 0) or 0 for h in hospitalizations) +
            sum(a.get('amount', 0) or 0 for a in medical_acts) +
            sum(e.get('amount', 0) or 0 for e in lab_exams) +
            sum(n.get('amount', 0) or 0 for n in nursings) +
            sum(r.get('amount', 0) or 0 for r in radio_requests)
        )

        total_paid = sum(p.get('amount', 0) or 0 for p in encaissements)

        return {
            'total_amount': float(total_amount),
            'total_paid': float(total_paid),
            'balance': float(total_amount - total_paid),
            'hospitalization_insurance': float(sum(h.get('insurance_payment', 0) or 0 for h in hospitalizations)),
            'medical_acts_insurance': float(sum(a.get('insurance_payment', 0) or 0 for a in medical_acts)),
            'lab_exams_insurance': float(sum(e.get('insurance_payment', 0) or 0 for e in lab_exams)),
            'nursing_insurance': float(sum(n.get('insurance_payment', 0) or 0 for n in nursings)),
            'radio_insurance': float(sum(r.get('insurance_payment', 0) or 0 for r in radio_requests))
        }

    @staticmethod
    def fetch_patient_history(pg_cur, patient_oids):
        """Récupérer l'historique complet pour une liste de patient OIDs"""
        if not isinstance(patient_oids, (list, tuple)):
            patient_oids = [patient_oids]

        placeholders = ','.join(['%s'] * len(patient_oids))
        patient_oids_tuple = tuple(patient_oids)

        # Hospitalisations
        safe_pg_execute(
            pg_cur,
            SQLQueries.HOSPITALIZATIONS + f' WHERE h."Patient" IN ({placeholders}) ORDER BY h."StartDate" DESC',
            patient_oids_tuple
        )
        hospitalizations = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())

        # Paiements
        safe_pg_execute(
            pg_cur,
            SQLQueries.PAYMENTS + f' WHERE tp."Patient" IN ({placeholders}) ORDER BY p."Date" DESC',
            patient_oids_tuple
        )
        all_payments = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())
        encaissements = [p for p in all_payments if p.get('type_code') == PAYMENT_TYPE_ENCAISSEMENT]
        decaissements = [p for p in all_payments if p.get('type_code') == PAYMENT_TYPE_DECAISSEMENT]

        # Actes médicaux
        safe_pg_execute(
            pg_cur,
            SQLQueries.MEDICAL_ACTS + f' WHERE ma."Patient" IN ({placeholders}) ORDER BY ma."ModifiedOn" DESC',
            patient_oids_tuple
        )
        medical_acts = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())

        # Examens labo
        safe_pg_execute(
            pg_cur,
            SQLQueries.LAB_EXAMS + f' WHERE le."Patient" IN ({placeholders}) ORDER BY le."ModifiedOn" DESC',
            patient_oids_tuple
        )
        lab_exams = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())

        # Soins infirmiers
        safe_pg_execute(
            pg_cur,
            SQLQueries.NURSINGS + f' WHERE n."Patient" IN ({placeholders}) ORDER BY n."Date" DESC',
            patient_oids_tuple
        )
        nursings = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())

        # Examens radio
        safe_pg_execute(
            pg_cur,
            SQLQueries.RADIO_REQUESTS + f' WHERE rr."Patient" IN ({placeholders}) ORDER BY rr."Date" DESC',
            patient_oids_tuple
        )
        radio_requests = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())

        return {
            'hospitalizations': hospitalizations,
            'all_payments': all_payments,
            'encaissements': encaissements,
            'decaissements': decaissements,
            'medical_acts': medical_acts,
            'lab_exams': lab_exams,
            'nursings': nursings,
            'radio_requests': radio_requests
        }


class DuplicateDetectionService:
    """Service pour la détection de doublons"""

    @staticmethod
    def detect_duplicates(patients, threshold=SIMILARITY_THRESHOLD, block_by="birth_year"):
        """Détecter les doublons potentiels avec blocking intelligent"""
        blocks = defaultdict(list)

        # Blocking pour optimiser les comparaisons
        for p in patients:
            if block_by == "birth_date" and p.get("birth_date"):
                key = f"bd_{p['birth_date'].isoformat()}"
            elif block_by == "birth_year" and p.get("birth_date"):
                key = f"by_{p['birth_date'].year}"
            else:
                key = "all"

            last_first = (p.get("_norm_last", "")[:1] if p.get("_norm_last") else "#")
            blocks[(key, last_first)].append(p)

        candidates = []

        # Comparaisons par paires dans chaque bloc
        for block_key, plist in blocks.items():
            n = len(plist)
            if n < 2:
                continue

            for i in range(n):
                a = plist[i]
                for j in range(i + 1, n):
                    b = plist[j]
                    score, reasons = DuplicateDetectionService._calculate_similarity(a, b)

                    if score >= threshold:
                        candidates.append({
                            "a_oid": a["oid"],
                            "b_oid": b["oid"],
                            "a_name": a["full_name"],
                            "b_name": b["full_name"],
                            "a_birth": a["birth_date"].isoformat() if a.get("birth_date") else "",
                            "b_birth": b["birth_date"].isoformat() if b.get("birth_date") else "",
                            "score": round(float(score), 1),
                            "reasons": reasons
                        })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    @staticmethod
    def _calculate_similarity(a, b):
        """Calculer le score de similarité entre deux patients"""
        reasons = []
        score = 0

        # Identifiants exacts = score maximum
        if a.get("ssn") and b.get("ssn") and a["ssn"] == b["ssn"]:
            score = max(score, 100)
            reasons.append("SSN identique")

        if a.get("idcard") and b.get("idcard") and a["idcard"] == b["idcard"]:
            score = max(score, 100)
            reasons.append("Carte ID identique")

        if a.get("passport") and b.get("passport") and a["passport"] == b["passport"]:
            score = max(score, 100)
            reasons.append("Passeport identique")

        # Nom + date de naissance exacts
        if (a.get("_norm_full") and b.get("_norm_full") and
            a["_norm_full"] == b["_norm_full"] and
            a.get("birth_date") and b.get("birth_date") and
            a["birth_date"] == b["birth_date"]):
            score = max(score, 98)
            reasons.append("Nom/prénom exact + naissance")

        # Similarité fuzzy des noms
        name_sim = fuzz.token_sort_ratio(a.get("_norm_full", ""), b.get("_norm_full", ""))
        last_sim = fuzz.ratio(a.get("_norm_last", ""), b.get("_norm_last", "")) if a.get("_norm_last") and b.get("_norm_last") else 0
        first_sim = fuzz.ratio(a.get("_norm_first", ""), b.get("_norm_first", "")) if a.get("_norm_first") and b.get("_norm_first") else 0
        avg_name = (name_sim * 0.6) + (last_sim * 0.25) + (first_sim * 0.15)

        # Boost pour date de naissance
        birth_boost = 0
        if a.get("birth_date") and b.get("birth_date"):
            if a["birth_date"] == b["birth_date"]:
                birth_boost = 15
                reasons.append("Même date de naissance")
            elif a["birth_date"].year == b["birth_date"].year:
                birth_boost = 6
                reasons.append("Même année de naissance")

        # Parents
        parents_score = 0
        if a.get("_norm_father") and b.get("_norm_father"):
            parents_score += fuzz.token_sort_ratio(a["_norm_father"], b["_norm_father"]) * 0.2
        if a.get("_norm_mother") and b.get("_norm_mother"):
            parents_score += fuzz.token_sort_ratio(a["_norm_mother"], b["_norm_mother"]) * 0.2
        parents_score = min(parents_score, 15)

        if parents_score > 5:
            reasons.append("Noms des parents similaires")

        # Score final
        fuzzy_score = avg_name * 0.8 + birth_boost + parents_score
        score = max(score, fuzzy_score)

        # Raisons supplémentaires
        if name_sim > 90:
            reasons.append(f"Nom très similaire ({int(name_sim)}%)")
        elif name_sim > 75:
            reasons.append(f"Nom similaire ({int(name_sim)}%)")

        return score, reasons


# =====================================================
# ROUTES API
# =====================================================

def _get_his_patient_simple(patient_oid):
    """Helper interne pour récupérer les noms d'un patient HIS (pour fallback recherche)"""
    pg_conn = get_pg_connection()
    if not pg_conn:
        return None
        
    try:
        pg_cur = pg_conn.cursor()
        query = 'SELECT "FirstName", "LastName" FROM "Patient" WHERE "OID" = %s'
        safe_pg_execute(pg_cur, query, (patient_oid,))
        row = pg_cur.fetchone()
        return pg_row_to_dict(pg_cur, row) if row else None
    except Exception as e:
        logger.error(f"Erreur fetch patient simple: {e}")
        return None
    finally:
        try:
            pg_conn.close()
        except:
            pass

@app.route('/api/his-direct/patients/search', methods=['GET'])
@handle_pg_errors
def his_direct_search_patients():
    """Rechercher des patients DIRECTEMENT depuis PostgreSQL"""
    search_term = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', DEFAULT_SEARCH_LIMIT)), MAX_SEARCH_LIMIT)
    gender_filter = request.args.get('gender', '').strip()
    min_age = request.args.get('min_age', type=int)

    if not search_term or len(search_term) < 2:
        return jsonify({
            'success': False,
            'message': 'Terme de recherche trop court (min 2 caractères)'
        }), 400

    pg_conn = get_pg_connection()
    if not pg_conn:
        return jsonify({'success': False, 'message': 'Erreur connexion PostgreSQL'}), 500

    pg_cur = pg_conn.cursor()

    search_words = search_term.split()
    search_pattern = f"%{search_term}%"

    # ✅ Construire la clause WHERE pour le genre
    # Support pour valeurs numériques (1/2) ET textuelles ('M'/'F'/'m'/'f')
    gender_clause = ""

    if gender_filter:
        logger.info(f"🔍 Filtre genre reçu: {gender_filter}")
        if gender_filter.upper() in ('F', 'FEMME', 'FEMALE', '2'):
            # Support complet: numérique 2 OU texte 'F'/'f'/'FEMALE'/'Femme'/etc.
            gender_clause = " AND (p.\"Gender\" = 2 OR UPPER(CAST(p.\"Gender\" AS TEXT)) IN ('F', 'FEMALE', 'FEMME'))"
            logger.info(f"✅ Filtre appliqué: Femmes uniquement")
        elif gender_filter.upper() in ('M', 'HOMME', 'MALE', '1'):
            # Support complet: numérique 1 OU texte 'M'/'m'/'MALE'/'Homme'/etc.
            gender_clause = " AND (p.\"Gender\" = 1 OR UPPER(CAST(p.\"Gender\" AS TEXT)) IN ('M', 'MALE', 'HOMME'))"
            logger.info(f"✅ Filtre appliqué: Hommes uniquement")

    # ✅ Construire la clause WHERE pour l'âge minimum
    age_clause = ""
    if min_age is not None and min_age > 0:
        # Age >= min_age <=> BirthDate <= (CURRENT_DATE - min_age years)
        age_clause = f" AND p.\"BirthDate\" <= CURRENT_DATE - INTERVAL '{min_age} years'"
        logger.info(f"✅ Filtre âge minimum appliqué: {min_age} ans")

    # ✅✅✅ CORRECTION : Réorganiser l'ordre des paramètres
    if len(search_words) >= 2:
        word1 = f"%{search_words[0]}%"
        word2 = f"%{search_words[1]}%"

        query = SQLQueries.PATIENT_DETAILS + f'''
            WHERE (
                (p."FirstName" ILIKE %s AND p."LastName" ILIKE %s)
               OR (p."FirstName" ILIKE %s AND p."LastName" ILIKE %s)
               OR p."Code" ILIKE %s
               OR p."IdCardNumber" ILIKE %s
               OR (p."FirstName" || ' ' || p."LastName") ILIKE %s
            )
            {gender_clause}
            {age_clause}
            ORDER BY
                CASE
                    WHEN LOWER(p."FirstName") = LOWER(%s) AND LOWER(p."LastName") = LOWER(%s) THEN 1
                    WHEN LOWER(p."FirstName") = LOWER(%s) AND LOWER(p."LastName") = LOWER(%s) THEN 1
                    ELSE 2
                END, p."LastName", p."FirstName"
            LIMIT %s
        '''

        # ✅✅✅ ORDRE CORRECT DES PARAMÈTRES
        params = [
            # 1. Paramètres de recherche WHERE (7 paramètres)
            word1, word2, word2, word1,
            search_pattern, search_pattern, search_pattern
        ]

        # Note: Le filtre genre est intégré directement dans la clause SQL (pas de paramètre)

        # 3. Paramètres ORDER BY (4 paramètres)
        params.extend([
            search_words[0], search_words[1],
            search_words[1], search_words[0]
        ])

        # 4. LIMIT (1 paramètre)
        params.append(limit)

        logger.info(f"📊 Nombre de paramètres: {len(params)}, Nombre de %s: {query.count('%s')}")
        safe_pg_execute(pg_cur, query, tuple(params))

    else:
        # Recherche avec un seul mot
        query = SQLQueries.PATIENT_DETAILS + f'''
            WHERE (
                p."FirstName" ILIKE %s
               OR p."LastName" ILIKE %s
               OR p."Code" ILIKE %s
               OR p."IdCardNumber" ILIKE %s
               OR (p."FirstName" || ' ' || p."LastName") ILIKE %s
            )
            {gender_clause}
            {age_clause}
            ORDER BY
                CASE
                    WHEN LOWER(p."FirstName") = LOWER(%s) THEN 1
                    WHEN LOWER(p."LastName") = LOWER(%s) THEN 1
                    WHEN LOWER(p."Code") = LOWER(%s) THEN 1
                    WHEN LOWER(p."FirstName") LIKE LOWER(%s) THEN 2
                    WHEN LOWER(p."LastName") LIKE LOWER(%s) THEN 2
                    ELSE 3
                END, p."LastName", p."FirstName"
            LIMIT %s
        '''

        # ✅✅✅ ORDRE CORRECT DES PARAMÈTRES
        params = [
            # 1. Paramètres de recherche WHERE (5 paramètres)
            search_pattern, search_pattern, search_pattern,
            search_pattern, search_pattern
        ]

        # Note: Le filtre genre est intégré directement dans la clause SQL (pas de paramètre)

        # 3. Paramètres ORDER BY (5 paramètres)
        params.extend([
            search_term, search_term, search_term,
            f'{search_term}%', f'{search_term}%'
        ])

        # 4. LIMIT (1 paramètre)
        params.append(limit)

        logger.info(f"📊 Nombre de paramètres: {len(params)}, Nombre de %s: {query.count('%s')}")
        safe_pg_execute(pg_cur, query, tuple(params))
    patients = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())

    logger.info(f"📊 Résultats: {len(patients)} patient(s) trouvé(s) avec filtre genre: {gender_filter or 'Aucun'}, age min: {min_age or 'Aucun'}")

    return jsonify({
        'success': True,
        'count': len(patients),
        'patients': pg_decimal_to_float(patients),
        'debug': {
            'gender_filter_applied': gender_filter,
            'gender_clause': gender_clause if gender_clause else None
        } if app.debug else None
    })

@app.route('/api/his-direct/patients/<int:patient_oid>/cis-history', methods=['GET'])
@login_required
@handle_pg_errors
def his_direct_get_cis_history(patient_oid):
    """
    Récupère l'historique des dossiers CIS (Interne) liés à ce patient HIS.
    Modules interrogés :
    1. Accouchements (via patient_oid)
    2. Médecin Interne (via patient_oid_his)
    3. Location Bloc (via patient_oid_his)
    4. Prestation KT (via patient_oid_his)
    """
    cis_dossiers = []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Accouchements (via patient_oid)
        try:
            cursor.execute("""
                SELECT 
                    ad.id_dossier, 
                    ad.date_accouchement as date, 
                    CONCAT('Accouchement') as type,
                    CONCAT(d.first_name, ' ', d.last_name) as doctor,
                    CONCAT('Dossier #', ad.id_dossier) as description,
                    CASE 
                        WHEN ad.statut_medical = 'VALIDE' THEN 'Terminé' 
                        WHEN ad.statut_paiement = 'SOLDE' THEN 'Payé'
                        ELSE 'En cours' 
                    END as status
                FROM accouchement_dossiers ad
                LEFT JOIN doctors d ON ad.id_gyneco = d.id
                WHERE ad.patient_oid = %s
            """, (patient_oid,))
            
            for row in cursor.fetchall():
                cis_dossiers.append({
                    'date': row['date'],
                    'type': 'Accouchement',
                    'doctor': row['doctor'],
                    'description': row['description'],
                    'status': row['status'],
                    'link': f"/accouchement/{row['id_dossier']}",
                    'raw_date': row['date']
                })
        except Exception as e:
            logger.error(f"Erreur fetch Accouchements: {e}")

        # Récupérer les infos patient HIS pour le fallback nom
        patient_names = []
        try:
            his_patient = _get_his_patient_simple(patient_oid)
            if his_patient:
                fn = (his_patient.get('FirstName') or '').strip()
                ln = (his_patient.get('LastName') or '').strip()
                if fn and ln:
                    # Variantes de nom (Nom Prénom et Prénom Nom)
                    patient_names.append(f"{ln} {fn}")
                    patient_names.append(f"{fn} {ln}")
        except Exception as e:
            logger.error(f"Erreur récupération nom patient HIS: {e}")

        logger.info(f"Recherche CIS pour OID {patient_oid}. Noms potentiels: {patient_names}")

        # Helper pour construire la clause WHERE flexible
        def build_where_clause(prefix):
            params = [patient_oid]
            clause = f"{prefix}.patient_oid_his = %s"
            
            if patient_names:
                name_placeholders = ', '.join(['%s'] * len(patient_names))
                clause += f" OR {prefix}.patient IN ({name_placeholders})"
                params.extend(patient_names)
                
            return clause, params

        # 2. Médecin Interne
        try:
            where_clause, params = build_where_clause('mia')
            query = f"""
                SELECT 
                    mia.id_acte as id_dossier, 
                    mia.date_acte as date, 
                    CONCAT('Médecin Interne') as type,
                    CONCAT(d.first_name, ' ', d.last_name) as doctor,
                    mia.nom_acte as description,
                    CASE 
                        WHEN mia.statut_paiement = 'PAYE' THEN 'Payé'
                        ELSE 'Non Payé' 
                    END as status,
                    mia.patient_oid_his,
                    mia.patient
                FROM medecin_interne_actes mia
                LEFT JOIN doctors d ON mia.id_doctor = d.id
                WHERE {where_clause}
            """
            cursor.execute(query, tuple(params))
            
            for row in cursor.fetchall():
                # Marquer si c'est une correspondance par nom uniquement
                is_name_match = str(row.get('patient_oid_his')) != str(patient_oid)
                match_note = " (Nom)" if is_name_match else ""
                
                cis_dossiers.append({
                    'date': row['date'],
                    'type': 'Médecin Interne',
                    'doctor': row['doctor'],
                    'description': f"{row['description']}{match_note}",
                    'status': row['status'],
                    'link': f"/medecin_interne/actes/{row['id_dossier']}",
                    'raw_date': row['date']
                })
        except Exception as e:
            logger.error(f"Erreur fetch Médecin Interne: {e}")

        # 3. Location Bloc
        try:
            where_clause, params = build_where_clause('lbd')
            query = f"""
                SELECT 
                    lbd.id_dossier, 
                    lbd.date_creation as date, 
                    CONCAT('Location Bloc') as type,
                    CONCAT(d.first_name, ' ', d.last_name) as doctor,
                    CONCAT('Location Bloc #', lbd.id_dossier) as description,
                    CASE 
                         WHEN lbd.statut_paiement = 'PAYE' THEN 'Payé'
                         ELSE 'En cours'
                    END as status,
                    lbd.patient_oid_his
                FROM location_bloc_dossier_patient lbd
                LEFT JOIN doctors d ON lbd.id_doctor = d.id
                WHERE {where_clause}
            """
            cursor.execute(query, tuple(params))
            
            for row in cursor.fetchall():
                is_name_match = str(row.get('patient_oid_his')) != str(patient_oid)
                match_note = " (Nom)" if is_name_match else ""

                cis_dossiers.append({
                    'date': row['date'], 
                    'type': 'Location Bloc',
                    'doctor': row['doctor'],
                    'description': f"{row['description']}{match_note}",
                    'status': row['status'],
                    'link': f"/location_bloc/{row['id_dossier']}",
                    'raw_date': row['date']
                })
        except Exception as e:
            logger.error(f"Erreur fetch Location Bloc: {e}")

        # 4. Prestation KT
        try:
            # Pour KT, on garde uniquement OID pour l'instant car nom colonne incertaine
            cursor.execute("""
                SELECT 
                    kdp.id_dossier, 
                    kdp.acte_date as date, 
                    CONCAT('Prestation KT') as type,
                    CONCAT(d.first_name, ' ', d.last_name) as doctor,
                    CONCAT('Dossier KT #', kdp.id_dossier) as description,
                    'En cours' as status
                FROM kt_dossier_patient kdp
                LEFT JOIN doctors d ON kdp.id_doctor = d.id
                WHERE kdp.patient_oid_his = %s
            """, (patient_oid,))
            
            for row in cursor.fetchall():
                cis_dossiers.append({
                    'date': row['date'],
                    'type': 'Prestation KT',
                    'doctor': row['doctor'],
                    'description': row['description'] or 'Dossier KT',
                    'status': row['status'],
                    'link': f"/kt_dossier_detail/{row['id_dossier']}",
                    'raw_date': row['date']
                })
        except Exception as e:
            logger.error(f"Erreur fetch Prestation KT: {e}")

    finally:
        cursor.close()
        conn.close()

    # Sort by date descending
    cis_dossiers.sort(key=lambda x: x['raw_date'] if x['raw_date'] else datetime.min, reverse=True)
    
    # Format dates for JSON
    for d in cis_dossiers:
        if d['raw_date']:
            if isinstance(d['raw_date'], str):
                 d['date'] = d['raw_date'][:10]
            else:
                d['date'] = d['raw_date'].strftime('%Y-%m-%d')
        del d['raw_date'] # Remove non-serializable object

    return jsonify({
        'success': True,
        'cis_dossiers': cis_dossiers
    })

@app.route('/api/his-direct/patients/<int:patient_oid>', methods=['GET'])
@handle_pg_errors
def his_direct_get_patient_details(patient_oid):
    """Obtenir les détails d'un patient DIRECTEMENT depuis PostgreSQL"""
    pg_conn = get_pg_connection()
    if not pg_conn:
        return jsonify({'success': False, 'message': 'Erreur connexion PostgreSQL'}), 500

    pg_cur = pg_conn.cursor()

    safe_pg_execute(
        pg_cur,
        SQLQueries.PATIENT_DETAILS + ' WHERE p."OID" = %s',
        (patient_oid,)
    )

    patient_row = pg_cur.fetchone()

    if not patient_row:
        return jsonify({'success': False, 'message': 'Patient non trouvé'}), 404

    patient = pg_row_to_dict(pg_cur, patient_row)

    return jsonify({
        'success': True,
        'patient': pg_decimal_to_float(patient)
    })


@app.route('/api/his-direct/patients/<int:patient_oid>/history', methods=['GET'])
@handle_pg_errors
def his_direct_get_patient_history(patient_oid):
    """Obtenir l'historique complet d'un patient"""
    pg_conn = get_pg_connection()
    if not pg_conn:
        return jsonify({'success': False, 'message': 'Erreur connexion PostgreSQL'}), 500

    pg_cur = pg_conn.cursor()

    # Récupérer le patient
    safe_pg_execute(
        pg_cur,
        SQLQueries.PATIENT_BASE_SELECT + ' FROM "Patient" p WHERE p."OID" = %s',
        (patient_oid,)
    )

    patient_row = pg_cur.fetchone()
    if not patient_row:
        return jsonify({'success': False, 'message': 'Patient non trouvé'}), 404

    patient = pg_row_to_dict(pg_cur, patient_row)

    # Récupérer l'historique
    history_data = PatientHistoryService.fetch_patient_history(pg_cur, [patient_oid])

    # Calculer la balance
    balance = PatientHistoryService.calculate_balance(
        history_data['hospitalizations'],
        history_data['medical_acts'],
        history_data['lab_exams'],
        history_data['nursings'],
        history_data['radio_requests'],
        history_data['encaissements']
    )

    history = {
        'patient': pg_decimal_to_float(patient),
        'balance': balance,
        'hospitalizations': {
            'count': len(history_data['hospitalizations']),
            'data': pg_decimal_to_float(history_data['hospitalizations'])
        },
        'payments': {
            'count': len(history_data['all_payments']),
            'data': pg_decimal_to_float(history_data['all_payments'])
        },
        'encaissements': {
            'count': len(history_data['encaissements']),
            'total': sum(p.get('amount', 0) or 0 for p in history_data['encaissements']),
            'data': pg_decimal_to_float(history_data['encaissements'])
        },
        'decaissements': {
            'count': len(history_data['decaissements']),
            'total': sum(p.get('amount', 0) or 0 for p in history_data['decaissements']),
            'data': pg_decimal_to_float(history_data['decaissements'])
        },
        'medical_acts': {
            'count': len(history_data['medical_acts']),
            'data': pg_decimal_to_float(history_data['medical_acts'])
        },
        'lab_exams': {
            'count': len(history_data['lab_exams']),
            'data': pg_decimal_to_float(history_data['lab_exams'])
        },
        'nursings': {
            'count': len(history_data['nursings']),
            'data': pg_decimal_to_float(history_data['nursings'])
        },
        'radio_requests': {
            'count': len(history_data['radio_requests']),
            'data': pg_decimal_to_float(history_data['radio_requests'])
        }
    }

    return jsonify({'success': True, 'history': history})


@app.route('/api/his-direct/patients/merged-history', methods=['POST'])
@handle_pg_errors
def his_direct_get_merged_patient_history():
    """Obtenir l'historique FUSIONNÉ pour les patients SÉLECTIONNÉS manuellement"""
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Content-Type doit être application/json'}), 400

    data = request.get_json()
    patient_oids = data.get('patient_oids', [])

    if not patient_oids or len(patient_oids) == 0:
        return jsonify({'success': False, 'message': 'Aucun patient sélectionné'}), 400

    pg_conn = get_pg_connection()
    if not pg_conn:
        return jsonify({'success': False, 'message': 'Erreur connexion PostgreSQL'}), 500

    pg_cur = pg_conn.cursor()

    # Patient principal
    main_patient_oid = patient_oids[0]
    safe_pg_execute(
        pg_cur,
        SQLQueries.PATIENT_BASE_SELECT + ' FROM "Patient" p WHERE p."OID" = %s',
        (main_patient_oid,)
    )

    patient_row = pg_cur.fetchone()
    if not patient_row:
        return jsonify({'success': False, 'message': 'Patient principal non trouvé'}), 404

    patient = pg_row_to_dict(pg_cur, patient_row)

    # Tous les patients sélectionnés
    placeholders = ','.join(['%s'] * len(patient_oids))
    safe_pg_execute(
        pg_cur,
        SQLQueries.PATIENT_BASE_SELECT + f' FROM "Patient" p WHERE p."OID" IN ({placeholders})',
        tuple(patient_oids)
    )

    all_patients = [pg_row_to_dict(pg_cur, row) for row in pg_cur.fetchall()]

    # Historique fusionné
    history_data = PatientHistoryService.fetch_patient_history(pg_cur, patient_oids)

    # Balance
    balance = PatientHistoryService.calculate_balance(
        history_data['hospitalizations'],
        history_data['medical_acts'],
        history_data['lab_exams'],
        history_data['nursings'],
        history_data['radio_requests'],
        history_data['encaissements']
    )

    history = {
        'patient': pg_decimal_to_float(patient),
        'all_patients': pg_decimal_to_float(all_patients),
        'merged_count': len(patient_oids) - 1,
        'balance': balance,
        'hospitalizations': {
            'count': len(history_data['hospitalizations']),
            'data': pg_decimal_to_float(history_data['hospitalizations'])
        },
        'payments': {
            'count': len(history_data['all_payments']),
            'data': pg_decimal_to_float(history_data['all_payments'])
        },
        'encaissements': {
            'count': len(history_data['encaissements']),
            'total': sum(p.get('amount', 0) or 0 for p in history_data['encaissements']),
            'data': pg_decimal_to_float(history_data['encaissements'])
        },
        'decaissements': {
            'count': len(history_data['decaissements']),
            'total': sum(p.get('amount', 0) or 0 for p in history_data['decaissements']),
            'data': pg_decimal_to_float(history_data['decaissements'])
        },
        'medical_acts': {
            'count': len(history_data['medical_acts']),
            'data': pg_decimal_to_float(history_data['medical_acts'])
        },
        'lab_exams': {
            'count': len(history_data['lab_exams']),
            'data': pg_decimal_to_float(history_data['lab_exams'])
        },
        'nursings': {
            'count': len(history_data['nursings']),
            'data': pg_decimal_to_float(history_data['nursings'])
        },
        'radio_requests': {
            'count': len(history_data['radio_requests']),
            'data': pg_decimal_to_float(history_data['radio_requests'])
        }
    }

    return jsonify({'success': True, 'history': history})


@app.route('/api/his-direct/patients/<int:patient_oid>/duplicates', methods=['GET'])
@handle_pg_errors
def his_direct_detect_patient_duplicates(patient_oid):
    """Détecter les doublons potentiels pour un patient"""
    pg_conn = get_pg_connection()
    if not pg_conn:
        return jsonify({'success': False, 'message': 'Erreur connexion PostgreSQL'}), 500

    pg_cur = pg_conn.cursor()

    # Patient de référence
    safe_pg_execute(
        pg_cur,
        SQLQueries.PATIENT_BASE_SELECT + ''',
            p."SocialSecurityNumber" as ssn,
            p."PassportNumber" as passport,
            p."FatherName" as father_name,
            p."MotherName" as mother_name,
            p."FirstName" || ' ' || p."LastName" as full_name
        FROM "Patient" p
        WHERE p."OID" = %s''',
        (patient_oid,)
    )

    ref_patient = pg_row_to_dict(pg_cur, pg_cur.fetchone())
    if not ref_patient:
        return jsonify({'success': False, 'message': 'Patient non trouvé'}), 404

    # Rechercher des patients similaires
    birth_year = ref_patient['birth_date'].year if ref_patient.get('birth_date') else None

    if birth_year:
        safe_pg_execute(
            pg_cur,
            SQLQueries.PATIENT_BASE_SELECT + ''',
                p."SocialSecurityNumber" as ssn,
                p."PassportNumber" as passport,
                p."FatherName" as father_name,
                p."MotherName" as mother_name,
                p."FirstName" || ' ' || p."LastName" as full_name
            FROM "Patient" p
            WHERE p."OID" != %s
              AND EXTRACT(YEAR FROM p."BirthDate") = %s
            LIMIT 100''',
            (patient_oid, birth_year)
        )
    else:
        safe_pg_execute(
            pg_cur,
            SQLQueries.PATIENT_BASE_SELECT + ''',
                p."SocialSecurityNumber" as ssn,
                p."PassportNumber" as passport,
                p."FatherName" as father_name,
                p."MotherName" as mother_name,
                p."FirstName" || ' ' || p."LastName" as full_name
            FROM "Patient" p
            WHERE p."OID" != %s
            LIMIT 100''',
            (patient_oid,)
        )

    candidates = [pg_row_to_dict(pg_cur, row) for row in pg_cur.fetchall()]

    # Normaliser et comparer
    ref_patient['_norm_full'] = normalize_text(ref_patient.get('full_name', ''))
    ref_patient['_norm_first'] = normalize_text(ref_patient.get('first_name', ''))
    ref_patient['_norm_last'] = normalize_text(ref_patient.get('last_name', ''))
    ref_patient['_norm_father'] = normalize_text(ref_patient.get('father_name', ''))
    ref_patient['_norm_mother'] = normalize_text(ref_patient.get('mother_name', ''))

    for c in candidates:
        c['_norm_full'] = normalize_text(c.get('full_name', ''))
        c['_norm_first'] = normalize_text(c.get('first_name', ''))
        c['_norm_last'] = normalize_text(c.get('last_name', ''))
        c['_norm_father'] = normalize_text(c.get('father_name', ''))
        c['_norm_mother'] = normalize_text(c.get('mother_name', ''))

    duplicates = []
    for candidate in candidates:
        score, reasons = DuplicateDetectionService._calculate_similarity(ref_patient, candidate)
        if score >= SIMILARITY_THRESHOLD:
            duplicates.append({
                'oid': candidate['oid'],
                'code': candidate['code'],
                'first_name': candidate['first_name'],
                'last_name': candidate['last_name'],
                'birth_date': format_date_string(candidate.get('birth_date')),
                'age': candidate.get('age'),
                'id_card_number': candidate.get('id_card_number'),
                'match_score': round(score, 1),
                'match_reasons': reasons
            })

    duplicates.sort(key=lambda x: x['match_score'], reverse=True)

    return jsonify({
        'success': True,
        'reference_patient': pg_decimal_to_float(ref_patient),
        'duplicates': pg_decimal_to_float(duplicates),
        'count': len(duplicates)
    })


@app.route("/api/patient/search")
def api_patient_search():
    """Recherche rapide de patient pour autocomplétion"""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    conn = get_pg_connection()
    if not conn:
        return jsonify([])

    cur = conn.cursor()

    sql = '''
        SELECT
            "OID", "FirstName", "LastName", "BirthDate",
            "SocialSecurityNumber", "IdCardNumber"
        FROM "Patient"
        WHERE
            unaccent(lower("FirstName")) LIKE unaccent(lower(%s))
            OR unaccent(lower("LastName")) LIKE unaccent(lower(%s))
            OR "SocialSecurityNumber" = %s
            OR "IdCardNumber" = %s
        ORDER BY "ModifiedOn" DESC
        LIMIT 20
    '''

    like = f"%{q}%"
    safe_pg_execute(cur, sql, (like, like, q, q))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify([
        {
            "oid": r[0],
            "label": f"{r[1] or ''} {r[2] or ''} ({r[0]})",
            "birth": r[3].date().isoformat() if r[3] else ""
        }
        for r in rows
    ])


# =====================================================
# PAGE DE DÉTECTION DE DOUBLONS
# =====================================================

def load_patients(limit=None):
    """Charger les patients depuis PostgreSQL pour l'analyse des doublons"""
    conn = get_pg_connection()
    if not conn:
        return []

    cur = conn.cursor()

    q = '''
        SELECT "OID", "FirstName", "LastName", "BirthDate", "SocialSecurityNumber",
               "IdCardNumber", "PassportNumber", "FatherName", "MotherName"
        FROM "Patient"
    '''

    if limit:
        q += " LIMIT %s"
        safe_pg_execute(cur, q, (limit,))
    else:
        safe_pg_execute(cur, q)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    patients = []
    for r in rows:
        oid, fn, ln, birth, ssn, idcard, passport, father, mother = r

        # Normaliser la date de naissance
        birth_date = None
        if birth:
            try:
                birth_date = parser.parse(str(birth)).date()
            except Exception:
                birth_date = None

        patients.append({
            "oid": oid,
            "first_name": fn or "",
            "last_name": ln or "",
            "full_name": f"{fn or ''} {ln or ''}".strip(),
            "birth_date": birth_date,
            "ssn": (ssn or "").strip(),
            "idcard": (idcard or "").strip(),
            "passport": (passport or "").strip(),
            "father": father or "",
            "mother": mother or "",
            # Versions normalisées pour comparaison
            "_norm_full": normalize_text(f"{fn or ''} {ln or ''}"),
            "_norm_first": normalize_text(fn or ""),
            "_norm_last": normalize_text(ln or ""),
            "_norm_father": normalize_text(father or ""),
            "_norm_mother": normalize_text(mother or "")
        })

    return patients


# =====================================================
# NOUVELLES ROUTES POUR LES PAGES
# =====================================================

@app.route( '/his_patient_duplicates' )
@login_required
def duplicates_page():
    """Page de détection de doublons"""
    return render_template( 'his/his_patient_duplicates.html' )


@app.route( '/his_patient_search' )
def search_page():
    """Page de recherche intelligente"""
    return render_template( 'his/his_patient_search.html' )


@app.route( '/api/his-direct/duplicates/detect' )
@handle_pg_errors
def api_detect_duplicates():
    """API pour la détection de doublons"""
    threshold = float( request.args.get( 'threshold', 85 ) )
    block_by = request.args.get( 'block_by', 'birth_year' )

    # Charger tous les patients (avec limite pour les tests)
    patients = load_patients( limit = 1000 )

    # Détecter les doublons
    candidates = DuplicateDetectionService.detect_duplicates(
            patients,
            threshold = threshold,
            block_by = block_by
            )

    # Calculer les statistiques
    high_risk = len( [ c for c in candidates if c[ 'score' ] >= 90 ] )

    return jsonify(
            {
                    'success': True,
                    'candidates': pg_decimal_to_float( candidates ),
                    'count': len( candidates ),
                    'stats': {
                            'total_patients': len( patients ),
                            'duplicates_found': len( candidates ),
                            'high_risk': high_risk,
                            'merged_count': 0  # À implémenter avec une base de données
                            }
                    }
            )


@app.route( '/api/his-direct/duplicates/compare/<int:oid_a>/<int:oid_b>' )
@handle_pg_errors
def api_compare_patients( oid_a, oid_b ):
    """Comparaison détaillée entre deux patients"""
    pg_conn = get_pg_connection()
    pg_cur = pg_conn.cursor()

    # Récupérer les deux patients
    safe_pg_execute(
            pg_cur,
            SQLQueries.PATIENT_BASE_SELECT + ''',
            p."SocialSecurityNumber" as ssn,
            p."PassportNumber" as passport,
            p."FatherName" as father_name,
            p."MotherName" as mother_name,
            p."FirstName" || ' ' || p."LastName" as full_name
        FROM "Patient" p
        WHERE p."OID" IN (%s, %s)''',
            (oid_a, oid_b)
            )

    patients = { row[ 0 ]: pg_row_to_dict( pg_cur, row ) for row in pg_cur.fetchall() }

    if len( patients ) != 2:
        return jsonify( { 'success': False, 'message': 'Patients non trouvés' } ), 404

    patient_a = patients.get( oid_a )
    patient_b = patients.get( oid_b )

    # Normaliser pour comparaison
    patient_a[ '_norm' ] = {
            'full': normalize_text( patient_a.get( 'full_name', '' ) ),
            'first': normalize_text( patient_a.get( 'first_name', '' ) ),
            'last': normalize_text( patient_a.get( 'last_name', '' ) ),
            'father': normalize_text( patient_a.get( 'father_name', '' ) ),
            'mother': normalize_text( patient_a.get( 'mother_name', '' ) )
            }

    patient_b[ '_norm' ] = {
            'full': normalize_text( patient_b.get( 'full_name', '' ) ),
            'first': normalize_text( patient_b.get( 'first_name', '' ) ),
            'last': normalize_text( patient_b.get( 'last_name', '' ) ),
            'father': normalize_text( patient_b.get( 'father_name', '' ) ),
            'mother': normalize_text( patient_b.get( 'mother_name', '' ) )
            }

    # Calculer les similarités
    similarities = [ ]
    overall_score = 0

    # Similarité des noms
    name_score = fuzz.token_sort_ratio(
            patient_a[ '_norm' ][ 'full' ],
            patient_b[ '_norm' ][ 'full' ]
            )
    similarities.append(
            {
                    'field': 'Nom complet',
                    'score': name_score,
                    'details': f"{patient_a[ 'full_name' ]} ↔ {patient_b[ 'full_name' ]}"
                    }
            )
    overall_score += name_score * 0.4

    # Similarité des dates de naissance
    birth_score = 0
    if patient_a.get( 'birth_date' ) and patient_b.get( 'birth_date' ):
        if patient_a[ 'birth_date' ] == patient_b[ 'birth_date' ]:
            birth_score = 100
            details = "Dates identiques"
        elif patient_a[ 'birth_date' ].year == patient_b[ 'birth_date' ].year:
            birth_score = 80
            details = "Même année de naissance"
        else:
            birth_score = 30
            details = "Années différentes"
    similarities.append(
            {
                    'field': 'Date naissance',
                    'score': birth_score,
                    'details': details if patient_a.get( 'birth_date' ) and patient_b.get(
                        'birth_date'
                        ) else "Données manquantes"
                    }
            )
    overall_score += birth_score * 0.3

    # Similarité des parents
    parents_score = 0
    if patient_a.get( 'father_name' ) and patient_b.get( 'father_name' ):
        parents_score += fuzz.ratio(
                patient_a[ '_norm' ][ 'father' ],
                patient_b[ '_norm' ][ 'father' ]
                ) * 0.5

    if patient_a.get( 'mother_name' ) and patient_b.get( 'mother_name' ):
        parents_score += fuzz.ratio(
                patient_a[ '_norm' ][ 'mother' ],
                patient_b[ '_norm' ][ 'mother' ]
                ) * 0.5

    similarities.append(
            {
                    'field': 'Noms parents',
                    'score': parents_score,
                    'details': "Comparaison des noms des parents"
                    }
            )
    overall_score += parents_score * 0.2

    # Identifiants
    id_score = 0
    if (patient_a.get( 'id_card_number' ) and patient_b.get( 'id_card_number' ) and
            patient_a[ 'id_card_number' ] == patient_b[ 'id_card_number' ]):
        id_score = 100
        details = "Même numéro de carte d'identité"
    elif (patient_a.get( 'ssn' ) and patient_b.get( 'ssn' ) and
          patient_a[ 'ssn' ] == patient_b[ 'ssn' ]):
        id_score = 100
        details = "Même numéro de sécurité sociale"
    else:
        details = "Identifiants différents"

    similarities.append(
            {
                    'field': 'Identifiants',
                    'score': id_score,
                    'details': details
                    }
            )
    overall_score += id_score * 0.1

    overall_score = round( overall_score, 1 )

    # Recommandation
    if overall_score >= 90:
        recommendation = "TRÈS PROBABLE - Ces patients sont très probablement la même personne."
    elif overall_score >= 80:
        recommendation = "PROBABLE - Forte probabilité de doublon. Recommandé de fusionner."
    elif overall_score >= 70:
        recommendation = "POSSIBLE - Possibilité de doublon. Vérification recommandée."
    else:
        recommendation = "PEU PROBABLE - Peu de chances qu'il s'agisse de la même personne."

    return jsonify(
            {
                    'success': True,
                    'patient_a': pg_decimal_to_float( patient_a ),
                    'patient_b': pg_decimal_to_float( patient_b ),
                    'similarities': similarities,
                    'overall_score': overall_score,
                    'recommendation': recommendation
                    }
            )


@app.route( '/api/his-direct/search/intelligent' )
@handle_pg_errors
def api_intelligent_search():
    """Recherche intelligente avec filtres optimisée"""
    query = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 20)), MAX_SEARCH_LIMIT)
    offset = (page - 1) * limit

    logger.info(f"🔍 Recherche: query='{query}', page={page}, limit={limit}")
    logger.info(f"📋 Tous les paramètres reçus: {dict(request.args)}")

    pg_conn = get_pg_connection()
    pg_cur = pg_conn.cursor()

    base_query = '''
        SELECT
            p."OID" as oid,
            p."Code" as code,
            p."FirstName" as first_name,
            p."LastName" as last_name,
            p."BirthDate" as birth_date,
            p."Gender" as gender,
            p."IdCardNumber" as id_card_number,
            EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) as age,
            (SELECT MAX(h."StartDate") 
             FROM "Hospitalization" h 
             WHERE h."Patient" = p."OID") as last_visit,
            COALESCE(
                (SELECT SUM(h."Amount") FROM "Hospitalization" h WHERE h."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(ma."Amount") FROM "MedicalAct" ma WHERE ma."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(le."Amount") FROM "LabExam" le WHERE le."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(n."Amount") FROM "Nursing" n WHERE n."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(rr."Amount") FROM "RadioRequest" rr WHERE rr."Patient" = p."OID"), 0
            ) as total_charged,
            COALESCE(
                (SELECT SUM(h."PatientPayment") FROM "Hospitalization" h WHERE h."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(ma."PatientPayment") FROM "MedicalAct" ma WHERE ma."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(le."PatientPayment") FROM "LabExam" le WHERE le."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(n."PatientPayment") FROM "Nursing" n WHERE n."Patient" = p."OID"), 0
            ) + COALESCE(
                (SELECT SUM(rr."PatientPayment") FROM "RadioRequest" rr WHERE rr."Patient" = p."OID"), 0
            ) as total_paid
        FROM "Patient" p
    '''

    where_clauses = []
    params = []  # ✅ Liste unique de paramètres
    order_by = 'p."ModifiedOn" DESC'

    # ===== TRAITEMENT DE LA REQUÊTE =====
    if query:
        query_lower = query.lower().strip()

        if query_lower.startswith('code:'):
            code = query[5:].strip()
            where_clauses.append('LOWER(p."Code") LIKE LOWER(%s)')
            params.append(f'%{code}%')
            order_by = 'p."Code"'

        elif query_lower.startswith('carte:') or query_lower.startswith('card:'):
            card = query.split(':', 1)[1].strip()
            where_clauses.append('p."IdCardNumber" LIKE %s')
            params.append(f'%{card}%')
            order_by = 'p."IdCardNumber"'

        elif query_lower.startswith('age:'):
            age_expr = query[4:].strip()
            if age_expr.startswith('>'):
                age = int(age_expr[1:].strip())
                where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) > %s')
                params.append(age)
            elif age_expr.startswith('<'):
                age = int(age_expr[1:].strip())
                where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) < %s')
                params.append(age)
            elif age_expr.startswith('='):
                age = int(age_expr[1:].strip())
                where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) = %s')
                params.append(age)
            else:
                age = int(age_expr)
                where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) = %s')
                params.append(age)

        else:
            words = query.split()
            if len(words) >= 2:
                search_conditions = []
                search_conditions.append(
                    '(LOWER(p."FirstName") LIKE LOWER(%s) AND LOWER(p."LastName") LIKE LOWER(%s))'
                )
                params.extend([f'%{words[0]}%', f'%{words[1]}%'])

                search_conditions.append(
                    '(LOWER(p."LastName") LIKE LOWER(%s) AND LOWER(p."FirstName") LIKE LOWER(%s))'
                )
                params.extend([f'%{words[0]}%', f'%{words[1]}%'])

                full_query = ' '.join(words)
                search_conditions.append(
                    "LOWER(p.\"FirstName\" || ' ' || p.\"LastName\") LIKE LOWER(%s)"
                )
                params.append(f'%{full_query}%')

                where_clauses.append(f"({' OR '.join(search_conditions)})")

                # ✅ ORDER BY - on note sa position pour plus tard
                order_by_params = [words[0], words[1], words[0], words[1], f'{words[0]}%', f'{words[1]}%']
                order_by = f'''
                    CASE 
                        WHEN LOWER(p."FirstName") = LOWER(%s) AND LOWER(p."LastName") = LOWER(%s) THEN 1
                        WHEN LOWER(p."LastName") = LOWER(%s) AND LOWER(p."FirstName") = LOWER(%s) THEN 2
                        WHEN LOWER(p."FirstName") LIKE LOWER(%s) AND LOWER(p."LastName") LIKE LOWER(%s) THEN 3
                        ELSE 4
                    END, p."LastName", p."FirstName"
                '''
            else:
                where_clauses.append('''(
                    LOWER(p."FirstName") LIKE LOWER(%s) OR
                    LOWER(p."LastName") LIKE LOWER(%s) OR
                    LOWER(p."Code") LIKE LOWER(%s) OR
                    p."IdCardNumber" LIKE %s
                )''')
                search_pattern = f'%{query}%'
                params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

                # ✅ ORDER BY - on note sa position pour plus tard
                order_by_params = [query, query, query, f'{query}%', f'{query}%']
                order_by = f'''
                    CASE
                        WHEN LOWER(p."FirstName") = LOWER(%s) THEN 1
                        WHEN LOWER(p."LastName") = LOWER(%s) THEN 1
                        WHEN LOWER(p."Code") = LOWER(%s) THEN 1
                        WHEN LOWER(p."FirstName") LIKE LOWER(%s) THEN 2
                        WHEN LOWER(p."LastName") LIKE LOWER(%s) THEN 2
                        ELSE 3
                    END, p."LastName", p."FirstName"
                '''

    # ===== FILTRES ADDITIONNELS =====

    # ✅ Filtre GENRE avec validation stricte
    gender_param = request.args.get('gender', '').strip().upper()
    if gender_param:
        logger.info(f"🔧 Filtre genre reçu: '{gender_param}'")
        if gender_param in ('M', 'HOMME', 'MALE', '1'):
            where_clauses.append('p."Gender" = %s')
            params.append(GENDER_MALE)  # 1
            logger.info(f"✅ Filtre genre appliqué: Hommes (Gender = {GENDER_MALE})")
        elif gender_param in ('F', 'FEMME', 'FEMALE', '2'):
            where_clauses.append('p."Gender" = %s')
            params.append(GENDER_FEMALE)  # 2
            logger.info(f"✅ Filtre genre appliqué: Femmes (Gender = {GENDER_FEMALE})")
        else:
            logger.warning(f"⚠️ Valeur de genre invalide ignorée: '{gender_param}'")

    # ✅ Filtre ÂGE (min/max)
    min_age_str = request.args.get('min_age', '').strip()
    max_age_str = request.args.get('max_age', '').strip()

    if min_age_str:
        try:
            min_age = int(min_age_str)
            where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) >= %s')
            params.append(min_age)
            logger.info(f"✅ Filtre âge min appliqué: {min_age}")
        except ValueError:
            logger.warning(f"⚠️ Valeur min_age invalide ignorée: '{min_age_str}'")

    if max_age_str:
        try:
            max_age = int(max_age_str)
            where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) <= %s')
            params.append(max_age)
            logger.info(f"✅ Filtre âge max appliqué: {max_age}")
        except ValueError:
            logger.warning(f"⚠️ Valeur max_age invalide ignorée: '{max_age_str}'")

    # ✅ Filtre RANGE d'âge
    age_range = request.args.get('age_range', '').strip()
    if age_range == 'child':
        where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) < 18')
        logger.info("✅ Filtre âge appliqué: Enfants")
    elif age_range == 'adult':
        where_clauses.append('EXTRACT(YEAR FROM AGE(CURRENT_DATE, p."BirthDate")) >= 18')
        logger.info("✅ Filtre âge appliqué: Adultes")

    # ✅ Filtre DATE de création
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    if start_date:
        where_clauses.append('p."ModifiedOn"::date >= %s')
        params.append(start_date)
        logger.info(f"✅ Filtre date début appliqué: {start_date}")

    if end_date:
        where_clauses.append('p."ModifiedOn"::date <= %s')
        params.append(end_date)
        logger.info(f"✅ Filtre date fin appliqué: {end_date}")

    # ✅ Filtre TIERS PAYANT
    third_party = request.args.get('third_party', '').strip()
    if third_party == 'has':
        where_clauses.append('p."ThirdParty" IS NOT NULL')
        logger.info("✅ Filtre tiers payant: Avec")
    elif third_party == 'none':
        where_clauses.append('p."ThirdParty" IS NULL')
        logger.info("✅ Filtre tiers payant: Sans")

    # ✅ Filtre SOLDE
    balance_status = request.args.get('balance_status', '').strip()

    # ===== CONSTRUCTION FINALE =====

    # ✅✅✅ Requête COUNT (sans ORDER BY ni LIMIT)
    count_query = 'SELECT COUNT(*) FROM "Patient" p'
    if where_clauses:
        count_query += ' WHERE ' + ' AND '.join(where_clauses)

    # Les paramètres COUNT sont exactement ceux de WHERE (sans ORDER BY)
    count_params = params.copy()

    logger.info(f"📢 COUNT Query: {count_query}")
    logger.info(f"📢 COUNT Params ({len(count_params)}): {count_params}")

    safe_pg_execute(pg_cur, count_query, tuple(count_params))
    total = pg_cur.fetchone()[0]

    # ✅✅✅ Requête SELECT (avec ORDER BY et LIMIT)
    select_query = base_query
    if where_clauses:
        select_query += ' WHERE ' + ' AND '.join(where_clauses)

    select_query += f' ORDER BY {order_by} LIMIT %s OFFSET %s'

    # Les paramètres SELECT = WHERE + ORDER BY + LIMIT/OFFSET
    select_params = params.copy()

    # Ajouter les paramètres ORDER BY si ils existent
    if 'order_by_params' in locals():
        select_params.extend(order_by_params)

    # Ajouter LIMIT et OFFSET
    select_params.extend([limit, offset])

    logger.info(f"📊 SELECT Params totaux ({len(select_params)}): {select_params}")
    logger.info(f"📊 Nombre de %s dans SELECT: {select_query.count('%s')}")

    safe_pg_execute(pg_cur, select_query, tuple(select_params))
    results = pg_rows_to_dict_list(pg_cur, pg_cur.fetchall())

    # Calculer le solde et appliquer le filtre
    filtered_results = []
    for patient in results:
        patient['balance'] = (patient.get('total_charged', 0) or 0) - (patient.get('total_paid', 0) or 0)

        if balance_status:
            if balance_status == 'positive' and patient['balance'] <= 0:
                continue
            elif balance_status == 'negative' and patient['balance'] >= 0:
                continue
            elif balance_status == 'zero' and patient['balance'] != 0:
                continue

        filtered_results.append(patient)

    if balance_status:
        total = len(filtered_results)

    # Statistiques
    stats = calculate_search_stats(pg_cur, filtered_results)

    logger.info(f"✅ Recherche terminée: {len(filtered_results)} résultats sur {total} total")

    return jsonify({
        'success': True,
        'results': pg_decimal_to_float(filtered_results),
        'total': total,
        'page': page,
        'limit': limit,
        'query': query,
        'filters_applied': {
            'gender': gender_param if gender_param and gender_param in ('M', 'F', 'HOMME', 'FEMME', 'MALE', 'FEMALE', '1', '2') else None,
            'age_range': age_range if age_range else None,
            'min_age': min_age_str if min_age_str else None,
            'max_age': max_age_str if max_age_str else None,
            'balance_status': balance_status if balance_status else None
        },
        'stats': stats
    })


def calculate_search_stats( pg_cur, results ):
    """Calculer les statistiques pour les résultats de recherche"""
    active_count = 0
    total_balance = 0.0  # ✅ Initialiser comme float

    for patient in results:
        if patient.get('last_visit'):
            last_visit_date = patient['last_visit']
            if isinstance(last_visit_date, str):
                last_visit_date = datetime.fromisoformat(last_visit_date.replace('Z', '+00:00'))
            days_since = (
                datetime.now(last_visit_date.tzinfo) - last_visit_date).days if last_visit_date.tzinfo else (
                datetime.now() - last_visit_date).days
            if days_since <= 30:
                active_count += 1

        balance = patient.get('balance', 0)
        if balance and balance > 0:
            total_balance += float(balance)  # ✅ Convertir en float

    # Visites aujourd'hui
    try:
        safe_pg_execute(
            pg_cur, '''
                SELECT COUNT(*)
                FROM "Hospitalization"
                WHERE "StartDate"::date = CURRENT_DATE
            '''
        )
        today_visits = pg_cur.fetchone()[0] or 0
    except Exception as e:
        logger.error(f"Erreur calcul stats visites: {e}")
        today_visits = 0

    return {
            'total_patients': len( results ),
            'active_patients': active_count,
            'today_visits': today_visits,
            'balance_due': round( total_balance / 1000.0, 2 )  # ✅ En milliers avec arrondi
            }

@app.route( '/api/his-direct/stats' )
@handle_pg_errors
def api_general_stats():
    """Statistiques générales"""
    pg_conn = get_pg_connection()
    pg_cur = pg_conn.cursor()

    # Nombre total de patients
    safe_pg_execute( pg_cur, 'SELECT COUNT(*) FROM "Patient"' )
    total_patients = pg_cur.fetchone()[ 0 ]

    # Patients avec hospitalisations actives
    safe_pg_execute(
        pg_cur, '''
                SELECT COUNT(DISTINCT h."Patient")
                FROM "Hospitalization" h
                WHERE h."EndDate" IS NULL
                   OR h."EndDate" > CURRENT_DATE
                            '''
        )
    active_patients = pg_cur.fetchone()[ 0 ]

    # Visites aujourd'hui
    safe_pg_execute(
        pg_cur, '''
                SELECT COUNT(*)
                FROM "Hospitalization"
                WHERE "StartDate"::date = CURRENT_DATE
                            '''
        )
    today_visits = pg_cur.fetchone()[ 0 ]

    # Solde total à recouvrer
    safe_pg_execute(
        pg_cur, '''
                SELECT COALESCE(SUM("RestToPay"), 0)
                FROM "Hospitalization"
                WHERE "RestToPay" > 0
                            '''
        )
    balance_due = pg_cur.fetchone()[ 0 ]

    # Nombre de fusions (exemple - à adapter)
    merged_count = 0

    return jsonify(
            {
                    'success': True,
                    'total_patients': total_patients,
                    'active_patients': active_patients,
                    'today_visits': today_visits,
                    'balance_due': float( balance_due ),
                    'merged_count': merged_count
                    }
            )


@app.route( '/api/his-direct/stats/search' )
@handle_pg_errors
def api_search_stats():
    """Statistiques pour la page de recherche"""
    pg_conn = get_pg_connection()
    pg_cur = pg_conn.cursor()

    # Nombre total de patients
    safe_pg_execute( pg_cur, 'SELECT COUNT(*) FROM "Patient"' )
    total_patients = pg_cur.fetchone()[ 0 ]

    # Patients actifs (avec activité récente)
    safe_pg_execute(
        pg_cur, '''
                SELECT COUNT(DISTINCT p."OID")
                FROM "Patient" p
                         JOIN "Hospitalization" h ON p."OID" = h."Patient"
                WHERE h."StartDate" >= CURRENT_DATE - INTERVAL '30 days'
                            '''
        )
    active_patients = pg_cur.fetchone()[ 0 ]

    # Visites aujourd'hui
    safe_pg_execute(
        pg_cur, '''
                SELECT COUNT(*)
                FROM "Hospitalization"
                WHERE "StartDate"::date = CURRENT_DATE
                            '''
        )
    today_visits = pg_cur.fetchone()[ 0 ]

    # Solde total à recouvrer (en milliers)
    safe_pg_execute(
        pg_cur, '''
                SELECT COALESCE(SUM("RestToPay"), 0) / 1000
                FROM "Hospitalization"
                WHERE "RestToPay" > 0
                            '''
        )
    balance_due_k = pg_cur.fetchone()[ 0 ]

    return jsonify(
            {
                    'success': True,
                    'total_patients': total_patients,
                    'active_patients': active_patients,
                    'today_visits': today_visits,
                    'balance_due': float( balance_due_k )
                    }
            )