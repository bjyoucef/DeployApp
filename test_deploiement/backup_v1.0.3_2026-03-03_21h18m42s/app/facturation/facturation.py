import io
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from flask import render_template, redirect, url_for, flash, jsonify, g, request, send_file, session
from num2words import num2words
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

from app import app, get_db_connection
from app.facturation.config_clinique_tva import ConfigService
from app.error import handle_errors
from app.utils.utiles import login_required


# ============================================================================
# CONFIGURATION ET CONSTANTES
# ============================================================================

@dataclass
class FactureData:
    """Encapsulation des données de facture"""
    type_facture: str
    date_facture: str
    patient_nom: str
    patient_prenom: str
    patient_adresse: str = ""
    patient_telephone: str = ""
    patient_raison_sociale: str = ""
    patient_nif: Optional[str] = None
    patient_rc: Optional[str] = None
    patient_article: Optional[str] = None
    mode_paiement: str = "especes"
    numero_cheque: Optional[str] = None
    notes: str = ""
    montant_paye_caisse: Optional[Decimal] = None


NB = {
    'noir': colors.black,
    'gris_fonce': colors.HexColor("#333333"),
    'gris_moyen': colors.HexColor("#666666"),
    'gris_clair': colors.HexColor("#CCCCCC"),
    'blanc': colors.white,
}

def get_clinique_info_cached():
    """Récupère les infos clinique avec cache"""
    return ConfigService.get_clinique_info()


# ============================================================================
# CALCULATEUR DE FACTURE - LOGIQUE CENTRALISÉE
# ============================================================================

class CalculateurFacture:
    """Classe pour gérer tous les calculs de facture"""

    @staticmethod
    def calculer_droit_timbre(montant_ttc_sans_timbre: Decimal, mode_paiement: str) -> Decimal:
        """Calcule le droit de timbre selon la loi de finances 2025 (LF 2025)

        Barème:
        - ≤ 300 DA        : Pas de timbre
        - ≤ 30 000 DA     : 1% du montant
        - ≤ 100 000 DA    : 1.5% du montant
        - > 100 000 DA    : 2% du montant

        IMPORTANT : Le calcul se fait sur le montant EXACT, sans arrondi préalable
        """
        # Vérifications préliminaires
        if mode_paiement != 'especes' or not montant_ttc_sans_timbre or montant_ttc_sans_timbre <= 300:
            return Decimal('0.00')

        # ✅ CORRECTION : Utiliser le montant EXACT sans arrondi par tranche
        montant = montant_ttc_sans_timbre

        # Déterminer le taux selon les tranches
        if montant <= 30000:
            taux = Decimal('0.01')      # 1%
        elif montant <= 100000:
            taux = Decimal('0.015')     # 1.5%
        else:
            taux = Decimal('0.02')      # 2%

        print(f"DEBUG: Calcul timbre - Montant exact: {montant}, Taux: {taux}")

        # Calcul direct sur le montant exact
        droit_timbre = (montant * taux).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Minimum 5 DA
        resultat = max(droit_timbre, Decimal('5.00'))

        print(f"DEBUG: Calcul timbre - Timbre calculé: {droit_timbre}, Résultat final: {resultat}")

        return resultat

    @staticmethod
    def extraire_montant_facturable_depuis_net(montant_net: Decimal, mode_paiement: str) -> Decimal:
        """Déduit le montant facturable (sans timbre) depuis le NET À PAYER (Montant Caisse)

        Formule inverse : Montant Facturable + Timbre(Montant Facturable) = Net
        On cherche à retrouver le Montant Facturable qui aboutit à ce Net.
        """
        if not montant_net:
            return Decimal('0.00')

        mode_normalise = str(mode_paiement).strip().lower() if mode_paiement else ''
        print(f"DEBUG: extraire START (Net: {montant_net}, ModeRaw: '{mode_paiement}', ModeNorm: '{mode_normalise}')")

        if mode_normalise != 'especes':
            print(f"DEBUG: extraire ABORT - Mode mismatch '{mode_normalise}' != 'especes'")
            return montant_net
            
        if montant_net <= 300:
             print(f"DEBUG: extraire ABORT - Montant <= 300")
             return montant_net

        # On teste les tranches inverses
        # 1% (<= 30k facturable -> max ~30300 net)
        # 1.5% (30k < facturable <= 100k -> 30300 < net <= ~101500)
        # 2% (> 100k facturable -> net > 102000)

        c = float(montant_net)

        # Tranche > 100k
        # Approx seuil : 100000 * 1.02 = 102000
        if c > 101500:
            return (montant_net / Decimal('1.02')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Tranche 30k - 100k
        # Seuil bas : 30000 * 1.01 = 30300
        if c > 30300:
             # Essai avec 1.5%
             hypothese = (montant_net / Decimal('1.015')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
             if hypothese <= 100000:
                 return hypothese
             # Si ça dépasse 100k, théoriquement on bascule sur 2%, mais la marge est faible.
             # On garde la logique simple : si on est là, c'est probablement du 1.5% ou erreur de quelques centimes.
             return hypothese

        # Tranche <= 30k
        # Check minimum 5 DA. Si montant_facturable < 500 => timbre = 5 => net = facturable + 5
        # 500 * 0.01 = 5. Donc seuil ~505 DA.
        if c <= 505:
            if c > 5:
                # Timbre forfaitaire de 5 DA
                return montant_net - Decimal('5.00')
            else:
                return montant_net

        # Sinon 1%
        return (montant_net / Decimal('1.01')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def calculer_ligne(quantite: Decimal, prix_unitaire: Decimal, taux_tva: Decimal,
                       est_debours: bool, mode_calcul: str = 'ht',
                       montant_ttc_exact: Optional[Decimal] = None) -> Dict[str, Decimal]:

        """Calcule les montants d'une ligne avec respect du mode de saisie"""

        if mode_calcul == 'ttc' and montant_ttc_exact is not None:
            montant_ttc = montant_ttc_exact

            if est_debours:
                return {
                    'montant_ht': montant_ttc,
                    'montant_tva': Decimal('0.00'),
                    'montant_ttc': montant_ttc
                }

            montant_ht = (montant_ttc / (1 + taux_tva / 100)).quantize(Decimal('0.01'))
            montant_tva = montant_ttc - montant_ht

            return {
                'montant_ht': montant_ht,
                'montant_tva': montant_tva,
                'montant_ttc': montant_ttc
            }

        # Mode HT
        montant_ht = (quantite * prix_unitaire).quantize(Decimal('0.01'))

        if est_debours:
            return {
                'montant_ht': montant_ht,
                'montant_tva': Decimal('0.00'),
                'montant_ttc': montant_ht
            }

        montant_tva = (montant_ht * (taux_tva / 100)).quantize(Decimal('0.01'))
        montant_ttc = montant_ht + montant_tva

        return {
            'montant_ht': montant_ht,
            'montant_tva': montant_tva,
            'montant_ttc': montant_ttc
        }

    @staticmethod
    def calculer_totaux_lignes(cursor, facture_id: int) -> Dict[str, Decimal]:
        """Calcule tous les totaux à partir des lignes de facture"""
        cursor.execute(
            """
            SELECT montant_ht, montant_tva, montant_ttc, taux_tva, est_debours
            FROM facture_lignes
            WHERE facture_id = %s
            """,
            (facture_id,)
        )

        totaux = {
            'total_ht': Decimal('0.00'),
            'total_tva_9': Decimal('0.00'),
            'total_tva_19': Decimal('0.00'),
            'total_tva': Decimal('0.00'),
            'total_ttc': Decimal('0.00'),
            'total_debours': Decimal('0.00')
        }

        for ligne in cursor.fetchall():
            if ligne['est_debours']:
                totaux['total_debours'] += Decimal(str(ligne['montant_ht']))
            else:
                totaux['total_ht'] += Decimal(str(ligne['montant_ht']))
                totaux['total_ttc'] += Decimal(str(ligne['montant_ttc']))

                montant_tva = Decimal(str(ligne['montant_tva']))
                totaux['total_tva'] += montant_tva

                taux_tva = Decimal(str(ligne['taux_tva']))
                if taux_tva == Decimal('9'):
                    totaux['total_tva_9'] += montant_tva
                elif taux_tva == Decimal('19'):
                    totaux['total_tva_19'] += montant_tva

        return {k: v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) for k, v in totaux.items()}


    @staticmethod
    def recalculer_facture_complete(cursor, facture_id: int) -> Dict[str, Decimal]:
        """Recalcule tous les montants d'une facture et met à jour en base

        Logique:
        - TOTAL TTC = Montant facturable (sans timbre) = TOTAL TTC + débours des lignes
        - Timbre global calculé = basé sur le "Montant facturable" (<=30k: 1%, <=100k: 1.5%, >100k: 2%)
        - Montant Payé en Caisse = Timbre global calculé + Montant facturable
        - TOTAL NET À PAYER  = ( Montant Payé en Caisse ) si présente
        """
        totaux = CalculateurFacture.calculer_totaux_lignes(cursor, facture_id)

        cursor.execute(
            "SELECT mode_paiement, montant_paye_caisse FROM factures WHERE id = %s",
            (facture_id,)
        )
        facture = cursor.fetchone()

        if not facture:
            raise ValueError(f"Facture {facture_id} introuvable")

        # Calculer le montant facturable par défaut (Somme des lignes)
        montant_ttc_calcule = totaux['total_ttc'] + totaux['total_debours']

        print(f"DEBUG: Raw DB montant_paye_caisse: {facture.get('montant_paye_caisse')} (Type: {type(facture.get('montant_paye_caisse'))})")

        # "TOTAL TTC = Montant facturable (sans timbre)"
        # Si 'montant_paye_caisse' est défini dans la DB, on l'utilise comme le "Montant facturable" manuel
        if facture['montant_paye_caisse']:
            montant_net_saisi = Decimal(str(facture['montant_paye_caisse']))
            # On inverse le calcul pour trouver le montant facturable
            montant_facturable = CalculateurFacture.extraire_montant_facturable_depuis_net(
                montant_net_saisi,
                facture['mode_paiement']
            )
            print(f"DEBUG: extraire_montant RETURNED: {montant_facturable}")
        else:
            montant_facturable = montant_ttc_calcule

        # "Timbre global calculé" (Calculé sur le montant facturable)
        droit_timbre = CalculateurFacture.calculer_droit_timbre(
            montant_facturable,
            facture['mode_paiement']
        )

        # "Montant Payé en Caisse = Timbre global calculé + Montant facturable"
        montant_paye_final = (montant_facturable + droit_timbre).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        # "TOTAL NET À PAYER = ( Montant Payé en Caisse ) si présente"
        total_net = montant_paye_final

        print(f"DEBUG: Recalcul Facture {facture_id}")
        print(f"DEBUG: - Montant Facturable (TTC/Caisse): {montant_facturable}")
        print(f"DEBUG: - Droit Timbre Calculé: {droit_timbre}")
        print(f"DEBUG: - Total Net à Payer: {total_net}")

        cursor.execute(
            """
            UPDATE factures
            SET total_ht = %s, total_tva_9 = %s, total_tva_19 = %s,
                total_tva = %s, total_ttc = %s, total_debours = %s,
                droit_timbre = %s, total_net = %s
            WHERE id = %s
            """,
            (
                totaux['total_ht'], totaux['total_tva_9'], totaux['total_tva_19'],
                totaux['total_tva'], totaux['total_ttc'], totaux['total_debours'],
                droit_timbre, total_net, facture_id
            )
        )

        return {
            **totaux,
            'droit_timbre': droit_timbre,
            'total_net': total_net,
            'montant_ttc_sans_timbre': montant_facturable # Retourne le montant facturable utilisé
        }


# ============================================================================
# UTILITAIRES
# ============================================================================

@contextmanager
def get_db_cursor(commit=True):
    """Context manager pour gérer automatiquement les connexions DB"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        yield cursor
        if commit:
            connection.commit()
    except Exception as e:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def safe_float(value):
    """Conversion sécurisée en float (optimisée)"""
    if value is None:
        return 0.0
    return float(value)


def build_filter_query(base_conditions=None):
    """Construit dynamiquement les conditions de filtrage (évite la duplication)"""
    if base_conditions is None:
        base_conditions = []

    conditions = list(base_conditions)
    params = []

    return conditions, params


def format_montant(montant):
    """Formate un montant avec séparation des milliers"""
    return f"{montant:,.2f}".replace(",", " ")


class FactureService:
    """Service pour gérer la logique métier des factures"""

    @staticmethod
    def calculer_ligne_exact(quantite: Decimal, prix_unitaire: Decimal,
                             taux_tva: Decimal, est_debours: bool,
                             mode_calcul: str = 'ht',
                             montant_ttc_exact: Optional[Decimal] = None) -> Dict:
        """
        Calcule les montants d'une ligne avec respect du mode de saisie

        Args:
            quantite: Quantité
            prix_unitaire: Prix unitaire HT
            taux_tva: Taux de TVA (ex: 9, 19)
            est_debours: Si c'est un débours (pas de TVA)
            mode_calcul: 'ht' ou 'ttc'
            montant_ttc_exact: Si mode_calcul='ttc', le montant TTC exact voulu

        Returns:
            Dict avec montant_ht, montant_tva, montant_ttc
        """

        if mode_calcul == 'ttc' and montant_ttc_exact is not None:
            # MODE TTC : Garantir le TTC exact
            montant_ttc = montant_ttc_exact

            if est_debours:
                montant_ht = montant_ttc
                montant_tva = Decimal('0.00')
            else:
                # Calcul HT avec haute précision puis arrondi
                montant_ht = (montant_ttc / (1 + taux_tva / 100)).quantize(Decimal('0.01'))
                # TVA par différence pour garantir TTC exact
                montant_tva = montant_ttc - montant_ht

            return {
                'montant_ht': montant_ht,
                'montant_tva': montant_tva,
                'montant_ttc': montant_ttc
            }

        else:
            # MODE HT : Calcul classique
            montant_ht = (quantite * prix_unitaire).quantize(Decimal('0.01'))

            if est_debours:
                return {
                    'montant_ht': montant_ht,
                    'montant_tva': Decimal('0.00'),
                    'montant_ttc': montant_ht
                }

            montant_tva = (montant_ht * (taux_tva / 100)).quantize(Decimal('0.01'))
            montant_ttc = montant_ht + montant_tva

            return {
                'montant_ht': montant_ht,
                'montant_tva': montant_tva,
                'montant_ttc': montant_ttc
            }

    @staticmethod
    def generer_numero_facture(cursor, type_facture: str, date_obj) -> str:
        """Génère un numéro de facture unique"""
        year_suffix = str(date_obj.year)[-2:]
        prefix = "PRO" if type_facture == "proforma" else "FAC"
        prefix_with_year = f"{prefix}{year_suffix}"

        cursor.execute(
            """
            SELECT numero_facture
            FROM factures
            WHERE type_facture = %s AND YEAR(date_facture) = %s 
                  AND numero_facture LIKE %s
            ORDER BY id DESC LIMIT 1
            """,
            (type_facture, date_obj.year, f"{prefix_with_year}%")
        )

        last_facture = cursor.fetchone()
        if last_facture:
            last_num = int(last_facture["numero_facture"][-5:])
            return f"{prefix_with_year}{str(last_num + 1).zfill(5)}"
        return f"{prefix_with_year}00001"

    @staticmethod
    def valider_donnees_patient(data: FactureData) -> Tuple[bool, Optional[str]]:
        """Valide les données patient"""
        if data.patient_raison_sociale:
            if not data.patient_raison_sociale.strip():
                return False, "La raison sociale est obligatoire pour une entreprise"
        else:
            if not data.patient_nom or not data.patient_prenom:
                return False, "Le nom et prénom du patient sont obligatoires"
        return True, None

    @staticmethod
    def creer_facture(cursor, data: FactureData, created_by: int) -> Tuple[int, str]:
        """Crée une nouvelle facture et retourne son ID et numéro"""
        date_obj = datetime.strptime(data.date_facture, '%Y-%m-%d') if isinstance(
            data.date_facture, str) else data.date_facture

        numero_facture = FactureService.generer_numero_facture(cursor, data.type_facture, date_obj)

        cursor.execute(
            """
            INSERT INTO factures (
                numero_facture, type_facture, date_facture,
                patient_nom, patient_prenom, patient_adresse, patient_telephone,
                patient_raison_sociale, patient_nif, patient_rc, patient_article,
                notes, mode_paiement, numero_cheque, montant_paye_caisse, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                numero_facture, data.type_facture, date_obj,
                data.patient_nom, data.patient_prenom, data.patient_adresse, data.patient_telephone,
                data.patient_raison_sociale, data.patient_nif, data.patient_rc, data.patient_article,
                data.notes, data.mode_paiement, data.numero_cheque, data.montant_paye_caisse,
                created_by
            )
        )

        return cursor.lastrowid, numero_facture

    @staticmethod
    def verifier_modification_autorisee(cursor, facture_id: int) -> Tuple[bool, Optional[str]]:
        """Vérifie si la facture peut être modifiée"""
        cursor.execute(
            "SELECT statut FROM factures WHERE id = %s FOR UPDATE",
            (facture_id,)
        )
        facture = cursor.fetchone()

        if not facture:
            return False, "Facture introuvable"

        if facture["statut"] != "brouillon":
            return False, "Seules les factures brouillon peuvent être modifiées"

        return True, None

    @staticmethod
    def calculer_ligne(quantite: Decimal, prix_unitaire: Decimal,
                       taux_tva: Decimal, est_debours: bool) -> Dict:
        """Calcule les montants d'une ligne de facture"""
        # Arrondi à 2 décimales pour éviter les erreurs de précision
        montant_ht = (quantite * prix_unitaire).quantize(Decimal('0.01'))

        if est_debours:
            return {
                'montant_ht': montant_ht,
                'montant_tva': Decimal(0),
                'montant_ttc': montant_ht
            }

        # Calcul TVA avec arrondi
        montant_tva = (montant_ht * (taux_tva / 100)).quantize(Decimal('0.01'))
        montant_ttc = (montant_ht + montant_tva).quantize(Decimal('0.01'))

        return {
            'montant_ht': montant_ht,
            'montant_tva': montant_tva,
            'montant_ttc': montant_ttc
        }


class QueryBuilder:
    """Constructeur de requêtes SQL avec filtres dynamiques"""

    @staticmethod
    def build_facture_filters(params: dict) -> Tuple[List[str], List]:
        """Construit les filtres pour les requêtes de factures"""
        filters = []
        values = []

        if params.get('statut'):
            filters.append("vfr.statut = %s")
            values.append(params['statut'])

        if params.get('recherche_patient'):
            filters.append("""(
                LOWER(vfr.patient_nom) LIKE LOWER(%s) OR 
                LOWER(vfr.patient_prenom) LIKE LOWER(%s) OR
                LOWER(vfr.patient_complet) LIKE LOWER(%s) OR
                LOWER(vfr.numero_facture) LIKE LOWER(%s)
            )""")
            search_param = f"%{params['recherche_patient']}%"
            values.extend([search_param] * 4)

        if params.get('avec_debours') == "oui":
            filters.append("vfr.total_debours > 0")
        elif params.get('avec_debours') == "non":
            filters.append("(vfr.total_debours = 0 OR vfr.total_debours IS NULL)")

        if params.get('date_debut'):
            filters.append("vfr.date_facture >= %s")
            values.append(params['date_debut'])

        if params.get('date_fin'):
            filters.append("vfr.date_facture <= %s")
            values.append(params['date_fin'])

        return filters, values


# ============================================================================
# ROUTES FLASK
# ============================================================================

@app.route("/facturation")
@login_required
@handle_errors()

def facturation():
    """Liste des factures avec statistiques détaillées"""
    type_facture = request.args.get("type", "facture")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset = (page - 1) * per_page

    filter_params = {
        'statut': request.args.get("statut", ""),
        'recherche_patient': request.args.get("recherche_patient", ""),
        'avec_debours': request.args.get("avec_debours", ""),
        'date_debut': request.args.get("date_debut", ""),
        'date_fin': request.args.get("date_fin", ""),
        'donnee_patient': request.args.get("donnee_patient", "")
    }

    filters = []
    values = []
    if filter_params['donnee_patient'] == "oui":
        filters.append("f.donnee_au_patient = TRUE")
    elif filter_params['donnee_patient'] == "non":
        filters.append("(f.donnee_au_patient = FALSE OR f.donnee_au_patient IS NULL)")

    if filter_params['statut']:
        filters.append("f.statut = %s")
        values.append(filter_params['statut'])

    if filter_params['recherche_patient']:
        filters.append("""(
            LOWER(f.patient_nom) LIKE LOWER(%s) OR 
            LOWER(f.patient_prenom) LIKE LOWER(%s) OR
            LOWER(CONCAT(f.patient_nom, ' ', f.patient_prenom)) LIKE LOWER(%s) OR
            LOWER(f.numero_facture) LIKE LOWER(%s)
        )""")
        search_param = f"%{filter_params['recherche_patient']}%"
        values.extend([search_param] * 4)

    if filter_params['avec_debours'] == "oui":
        filters.append("f.total_debours > 0")
    elif filter_params['avec_debours'] == "non":
        filters.append("(f.total_debours = 0 OR f.total_debours IS NULL)")

    if filter_params['date_debut']:
        filters.append("f.date_facture >= %s")
        values.append(filter_params['date_debut'])

    if filter_params['date_fin']:
        filters.append("f.date_facture <= %s")
        values.append(filter_params['date_fin'])

    base_where = "WHERE f.type_facture = %s"
    where_clause = base_where + (" AND " + " AND ".join(filters) if filters else "")
    params = [type_facture] + values

    with get_db_cursor(commit=False) as cursor:
    # ✅ STATISTIQUES DÉTAILLÉES AVEC TVA 9% et 19%
        cursor.execute(
            f"""
            SELECT 
                COUNT(*) as total_factures,
                COALESCE(SUM(f.total_ht), 0) as total_ht,
                COALESCE(SUM(f.total_tva), 0) as total_tva,
            COALESCE(SUM(f.total_tva_9), 0) as total_tva_9,
            COALESCE(SUM(f.total_tva_19), 0) as total_tva_19,
                COALESCE(SUM(f.total_ttc), 0) as total_ttc,
                COALESCE(SUM(f.total_debours), 0) as total_debours,
                
                -- Comptage par statut
                SUM(CASE WHEN f.statut = 'brouillon' THEN 1 ELSE 0 END) as nb_brouillon,
                SUM(CASE WHEN f.statut = 'valide' THEN 1 ELSE 0 END) as nb_valide,
                SUM(CASE WHEN f.statut = 'annule' THEN 1 ELSE 0 END) as nb_annule,
                
            -- Totaux TTC détaillés par statut
                COALESCE(SUM(CASE WHEN f.statut = 'brouillon' THEN f.total_net ELSE 0 END), 0) as total_ttc_brouillon,
                COALESCE(SUM(CASE WHEN f.statut = 'valide' THEN f.total_net ELSE 0 END), 0) as total_ttc_valide,
                COALESCE(SUM(CASE WHEN f.donnee_au_patient = TRUE THEN f.total_net ELSE 0 END), 0) as total_ttc_remise,
                COALESCE(SUM(CASE WHEN f.statut = 'valide' AND (f.donnee_au_patient = FALSE OR f.donnee_au_patient IS NULL) THEN f.total_net ELSE 0 END), 0) as total_ttc_en_attente
            FROM factures f
            {where_clause}
            """,
            params
        )
        stats = cursor.fetchone()
        total_count = stats['total_factures']

        # Liste paginée
        cursor.execute(
            f"""
            SELECT 
                f.*,
                CONCAT(f.patient_nom, ' ', f.patient_prenom) as patient_complet,
                CONCAT(pc.nom, ' ', pc.prenom) as createur,
                CONCAT(pv.nom, ' ', pv.prenom) as validateur,
                CONCAT(pr.nom, ' ', pr.prenom) as remise_par_nom
            FROM factures f
            LEFT JOIN personnel pc ON f.created_by = pc.id_personnel
            LEFT JOIN personnel pv ON f.valide_par = pv.id_personnel
            LEFT JOIN personnel pr ON f.remise_par = pr.id_personnel
            {where_clause}
            ORDER BY f.date_facture DESC, f.numero_facture DESC
            LIMIT %s OFFSET %s
            """,
            params + [per_page, offset]
        )
        factures = cursor.fetchall()

    total_pages = (total_count + per_page - 1) // per_page

    return render_template(
        "facturation/liste.html",
        factures=factures,
        type_facture=type_facture,
        stats=stats,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
    )


@app.route("/facturation/nouvelle", methods=["GET", "POST"])
@login_required
@handle_errors()

def nouvelle_facture():
    """Créer une nouvelle facture"""
    if request.method == "POST":
        try:
            montant_caisse = None
            montant_caisse_str = request.form.get("montant_paye_caisse", "").strip()
            if montant_caisse_str:
                montant_caisse = Decimal(montant_caisse_str)

            # ✅ Récupérer les références HIS
            patient_oid_his = request.form.get("patient_oid_his", "").strip() or None
            patient_code_his = request.form.get("patient_code_his", "").strip() or None

            facture_data = FactureData(
                type_facture=request.form.get("type_facture", "facture"),
                date_facture=request.form.get("date_facture", datetime.now().date()),
                patient_nom=request.form.get("patient_nom", "").strip(),
                patient_prenom=request.form.get("patient_prenom", "").strip(),
                patient_adresse=request.form.get("patient_adresse", "").strip(),
                patient_telephone=request.form.get("patient_telephone", "").strip(),
                patient_raison_sociale=request.form.get("patient_raison_sociale", "").strip(),
                patient_nif=request.form.get("patient_nif", "").strip() or None,
                patient_rc=request.form.get("patient_rc", "").strip() or None,
                patient_article=request.form.get("patient_article", "").strip() or None,
                mode_paiement=request.form.get("mode_paiement", "especes"),
                numero_cheque=request.form.get("numero_cheque", "").strip() or None,
                notes=request.form.get("notes", ""),
                montant_paye_caisse=montant_caisse
            )

            valid, error_msg = FactureService.valider_donnees_patient(facture_data)
            if not valid:
                flash(error_msg, "error")
                return redirect(url_for("nouvelle_facture"))

            with get_db_cursor() as cursor:
                facture_id, numero_facture = FactureService.creer_facture(
                    cursor, facture_data, g.user['id_personnel']
                )

                # ✅ Enregistrer les références HIS si présentes
                if patient_oid_his:
                    cursor.execute(
                        """
                        UPDATE factures 
                        SET patient_oid_his = %s, patient_code_his = %s
                        WHERE id = %s
                        """,
                        (patient_oid_his, patient_code_his, facture_id)
                    )

            flash(f"Facture {numero_facture} créée avec succès", "success")
            return redirect(url_for("editer_facture", facture_id=facture_id))

        except Exception as e:
            flash(f"Erreur lors de la création: {str(e)}", "error")
            return redirect(url_for("nouvelle_facture"))

    # ✅ AJOUT : Récupérer les taux de TVA
    taux_tva_disponibles = ConfigService.get_tous_tva_actifs()

    return render_template(
        "facturation/nouvelle.html",
        date_actuelle=datetime.now().strftime('%Y-%m-%d'),
        taux_tva_disponibles=taux_tva_disponibles  # ✅ Passer au template
    )


@app.route("/facturation/editer/<int:facture_id>", methods=["GET"])
@login_required
@handle_errors()

def editer_facture(facture_id):
    """Éditer une facture"""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT f.*,
                   CONCAT(pc.nom, ' ', pc.prenom) as createur_nom,
                   CONCAT(pv.nom, ' ', pv.prenom) as validateur_nom
            FROM factures f
            LEFT JOIN personnel pc ON f.created_by = pc.id_personnel
            LEFT JOIN personnel pv ON f.valide_par = pv.id_personnel
            WHERE f.id = %s
            """,
            (facture_id,)
        )
        facture = cursor.fetchone()

        if not facture:
            flash("Facture introuvable", "error")
            return redirect(url_for("facturation"))

        # ✅ MODIFICATION : Vérifier les permissions selon le statut
        if facture['statut'] == 'valide':
            # Facture validée : nécessite le privilège spécial
            if 'MODIFIER_FACTURE_VALIDEE' not in session.get('privileges', []):
                flash("Vous n'avez pas l'autorisation de modifier une facture validée", "error")
                return redirect(url_for("voir_facture", facture_id=facture_id))
        elif facture['statut'] == 'annule':
            # Facture annulée : interdiction totale
            flash("Impossible de modifier une facture annulée", "error")
            return redirect(url_for("voir_facture", facture_id=facture_id))

        cursor.execute(
            "SELECT * FROM facture_lignes WHERE facture_id = %s ORDER BY ordre, id",
            (facture_id,)
        )
        lignes = cursor.fetchall()

    # ✅ Récupérer les taux de TVA configurables
    taux_tva_disponibles = ConfigService.get_tous_tva_actifs()

    return render_template(
        "facturation/editer.html",
        facture=facture,
        lignes=lignes,
        taux_tva_disponibles=taux_tva_disponibles
    )


@app.route("/facturation/modifier_patient/<int:facture_id>", methods=["POST"])
@login_required
@handle_errors()

def modifier_patient_facture(facture_id):
    """Modifier les informations patient - VERSION OPTIMISÉE"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Extraction des données en une fois
        patient_data = {
            'nom': request.form.get("patient_nom", "").strip(),
            'prenom': request.form.get("patient_prenom", "").strip(),
            'adresse': request.form.get("patient_adresse", "").strip(),
            'telephone': request.form.get("patient_telephone", "").strip(),
            'raison_sociale': request.form.get("patient_raison_sociale", "").strip(),
            'nif': request.form.get("patient_nif", "").strip(),
            'rc': request.form.get("patient_rc", "").strip(),
            'article': request.form.get("patient_article", "").strip(),
            # ✅ AJOUT : Références HIS
            'oid_his': request.form.get("patient_oid_his", "").strip() or None,
            'code_his': request.form.get("patient_code_his", "").strip() or None
        }

        # Vérification et mise à jour en une transaction
        cursor.execute(
            "SELECT statut FROM factures WHERE id = %s FOR UPDATE",
            (facture_id,)
        )
        facture = cursor.fetchone()

        if not facture:
            return jsonify({"success": False, "message": "Facture introuvable"}), 404

        if facture["statut"] == 'annule':
            return jsonify({
                "success": False,
                "message": "Impossible de modifier une facture annulée"
            }), 400

        if facture["statut"] == 'valide':
            if 'MODIFIER_FACTURE_VALIDEE' not in session.get('privileges', []):
                return jsonify({
                    "success": False,
                    "message": "Vous n'avez pas l'autorisation de modifier une facture validée"
                }), 403

        # Mise à jour optimisée
        cursor.execute(
            """
            UPDATE factures
            SET patient_nom            = %s,
                patient_prenom         = %s,
                patient_adresse        = %s,
                patient_telephone      = %s,
                patient_raison_sociale = %s,
                patient_nif            = %s,
                patient_rc             = %s,
                patient_article        = %s,
                patient_oid_his        = %s,
                patient_code_his       = %s
            WHERE id = %s
            """,
            (
                patient_data['nom'], patient_data['prenom'],
                patient_data['adresse'], patient_data['telephone'],
                patient_data['raison_sociale'],
                patient_data['nif'] or None,
                patient_data['rc'] or None,
                patient_data['article'] or None,
                patient_data['oid_his'],
                patient_data['code_his'],
                facture_id
            )
        )

        connection.commit()
        return jsonify({"success": True, "message": "Informations patient mises à jour"})

    except Exception as e:
        connection.rollback()
        return jsonify({"success": False, "message": f"Erreur: {str(e)}"}), 400
    finally:
        cursor.close()
        connection.close()


@app.route("/facturation/ajouter_ligne", methods=["POST"])
@login_required
@handle_errors()

def ajouter_ligne_facture():
    """Ajouter une ligne à une facture"""
    try:
        facture_id = request.form.get("facture_id")
        type_ligne = request.form.get("type_ligne")
        designation = request.form.get("designation")
        quantite = Decimal(request.form.get("quantite", 1))
        prix_unitaire = Decimal(request.form.get("prix_unitaire", 0))
        taux_tva = Decimal(request.form.get("taux_tva", 0))
        description = request.form.get("description", "")
        reference_justificatif = request.form.get("reference_justificatif", "")
        est_debours = (type_ligne == 'debours')

        # Récupérer les montants précalculés
        mode_calcul = request.form.get("mode_calcul", "ht")
        montant_ttc_calcule = request.form.get("montant_ttc_calcule")
        montant_tva_calcule = request.form.get("montant_tva_calcule")

        with get_db_cursor() as cursor:
            # Vérification
            cursor.execute(
                "SELECT statut FROM factures WHERE id = %s FOR UPDATE",
                (facture_id,)
            )
            facture = cursor.fetchone()

            if not facture or facture["statut"] != "brouillon" and 'MODIFIER_FACTURE_VALIDEE' not in session.get( 'privileges', [ ] ):
                flash("Modification impossible", "error")
                return redirect(url_for("editer_facture", facture_id=facture_id))

            # Calcul des montants
            if mode_calcul == 'ttc' and montant_ttc_calcule and montant_tva_calcule:
                montant_ttc = Decimal(montant_ttc_calcule)
                montant_tva = Decimal(montant_tva_calcule)
                montant_ht = montant_ttc - montant_tva
            else:
                montants = CalculateurFacture.calculer_ligne(
                    quantite, prix_unitaire, taux_tva, est_debours
                )
                montant_ht = montants['montant_ht']
                montant_tva = montants['montant_tva']
                montant_ttc = montants['montant_ttc']

            # Insertion
            cursor.execute(
                """
                INSERT INTO facture_lignes (
                    facture_id, type_ligne, est_debours, designation,
                    quantite, prix_unitaire, montant_ht,
                    taux_tva, montant_tva, montant_ttc,
                    description, reference_justificatif
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    facture_id, type_ligne, est_debours, designation,
                    quantite, prix_unitaire, montant_ht,
                    taux_tva, montant_tva, montant_ttc,
                    description, reference_justificatif if est_debours else None
                )
            )

            # Recalcul
            CalculateurFacture.recalculer_facture_complete(cursor, facture_id)

        flash("Ligne ajoutée avec succès", "success")
        return redirect(url_for("editer_facture", facture_id=facture_id))

    except Exception as e:
        flash(f"Erreur lors de l'ajout: {str(e)}", "error")
        return redirect(url_for("editer_facture", facture_id=facture_id))


@app.route("/facturation/supprimer_ligne/<int:ligne_id>", methods=["POST"])
@login_required
@handle_errors()

def supprimer_ligne_facture(ligne_id):
    """Supprimer une ligne de facture"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT facture_id FROM facture_lignes WHERE id = %s", (ligne_id,))
            result = cursor.fetchone()

            if not result:
                return jsonify({"success": False, "message": "Ligne introuvable"}), 404

            facture_id = result['facture_id']
            cursor.execute("DELETE FROM facture_lignes WHERE id = %s", (ligne_id,))
            CalculateurFacture.recalculer_facture_complete(cursor, facture_id)

        return jsonify({"success": True, "message": "Ligne supprimée avec succès"})

    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur: {str(e)}"}), 400


@app.route("/facturation/update_montant_caisse/<int:facture_id>", methods=["POST"])
@login_required
@handle_errors()

def update_montant_caisse(facture_id):
    """Mettre à jour le montant payé en caisse"""
    try:
        montant_paye_caisse = request.form.get("montant_paye_caisse", None)
        montant_caisse_decimal = Decimal(montant_paye_caisse) if montant_paye_caisse else None

        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE factures SET montant_paye_caisse = %s WHERE id = %s",
                (montant_caisse_decimal, facture_id)
            )
            totaux = CalculateurFacture.recalculer_facture_complete(cursor, facture_id)

        return jsonify({
            "success": True,
            "droit_timbre": float(totaux['droit_timbre']),
            "total_net": float(totaux['total_net']),
            "message": "Montant enregistré"
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur: {str(e)}"}), 400


@app.route("/facturation/lignes/<int:facture_id>", methods=["GET"])
@login_required
@handle_errors()

def get_lignes_facture(facture_id):
    """Retourner uniquement les lignes de facture - VERSION OPTIMISÉE"""
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM facture_lignes WHERE facture_id = %s ORDER BY ordre, id",
        (facture_id,)
    )
    lignes = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template("facturation/lignes_table.html", lignes=lignes)


@app.route("/facturation/totaux/<int:facture_id>", methods=["GET"])
@login_required
@handle_errors()

def get_totaux_facture(facture_id):
    """Retourner les totaux de la facture"""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("SELECT * FROM factures WHERE id = %s", (facture_id,))
        facture = cursor.fetchone()

        if not facture:
            return jsonify({"success": False, "message": "Facture introuvable"}), 404

        return jsonify({
            "success": True,
            "total_ht": float(facture["total_ht"]),
            "total_tva": float(facture["total_tva"]),
            "total_tva_9": float(facture["total_tva_9"]),
            "total_tva_19": float(facture["total_tva_19"]),
            "total_ttc": float(facture["total_ttc"]),
            "total_debours": float(facture["total_debours"]),
            "droit_timbre": float(facture["droit_timbre"]),
            "total_net": float(facture["total_net"])
        })


@app.route("/facturation/valider/<int:facture_id>", methods=["POST"])
@login_required
@handle_errors()

def valider_facture(facture_id):
    """Valider une facture"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE factures
                SET statut = 'valide', date_validation = NOW(), valide_par = %s
                WHERE id = %s AND statut = 'brouillon'
                """,
                (g.user["id_personnel"], facture_id)
            )

        flash("Facture validée avec succès", "success")
        return redirect(url_for("voir_facture", facture_id=facture_id))

    except Exception as e:
        flash(f"Erreur lors de la validation: {str(e)}", "error")
        return redirect(url_for("editer_facture", facture_id=facture_id))


@app.route("/facturation/annuler/<int:facture_id>", methods=["POST"])
@login_required
@handle_errors()

def annuler_facture(facture_id):
    """Annuler une facture validée - VERSION OPTIMISÉE"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Vérification et mise à jour en une transaction
        cursor.execute(
            """
            SELECT statut, numero_facture, donnee_au_patient 
            FROM factures 
            WHERE id = %s 
            FOR UPDATE
            """,
            (facture_id,)
        )
        facture = cursor.fetchone()

        if not facture:
            flash("Facture introuvable.", "error")
            return redirect(url_for("facturation"))

        if facture["statut"] == "annule":
            flash("Cette facture est déjà annulée.", "warning")
            return redirect(url_for("voir_facture", facture_id=facture_id))

        # ✅ VÉRIFICATION : Empêcher l'annulation si donnée au patient
        if facture["donnee_au_patient"]:
            flash(
                "Impossible d'annuler cette facture : elle a déjà été donnée au patient. "
                "Veuillez d'abord récupérer la facture (annuler la remise) avant de l'annuler.",
                "error"
            )
            return redirect(url_for("voir_facture", facture_id=facture_id))

        # Mise à jour
        cursor.execute("""
                       UPDATE factures
                       SET statut          = 'annule',
                           date_annulation = NOW(),
                           annule_par      = %s
                       WHERE id = %s
                       """, (g.user['id_personnel'], facture_id))

        connection.commit()

        flash(f"Facture {facture['numero_facture']} annulée avec succès.", "success")
        return redirect(url_for("voir_facture", facture_id=facture_id))

    except Exception as e:
        connection.rollback()
        flash(f"Erreur lors de l'annulation : {str(e)}", "error")
        return redirect(url_for("voir_facture", facture_id=facture_id))
    finally:
        cursor.close()
        connection.close()


@app.route( "/facturation/marquer_donnee/<int:facture_id>", methods = [ "POST" ] )
@login_required
@handle_errors()

def marquer_facture_donnee(facture_id):
    """Marquer une facture comme donnée au patient"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Vérifier que la facture existe et est validée
        cursor.execute(
                """
                SELECT numero_facture, statut, donnee_au_patient
                FROM factures
                WHERE id = %s
                    FOR
                UPDATE
                """,
                (facture_id,)
                )
        facture = cursor.fetchone()

        if not facture:
            app.logger.error( f"Facture {facture_id} introuvable" )
            return jsonify(
                    {
                            "success": False,
                            "message": "Facture introuvable"
                            }
                    ), 404

        app.logger.info(
            f"Facture {facture_id} - Statut: {facture[ 'statut' ]}, Donnée: {facture[ 'donnee_au_patient' ]}"
            )

        if facture[ "statut" ] != "valide":
            app.logger.warning( f"Tentative de marquer facture {facture_id} non validée" )
            return jsonify(
                    {
                            "success": False,
                            "message": f"Seules les factures validées peuvent être marquées comme données. Statut actuel: {facture[ 'statut' ]}"
                            }
                    ), 400

        if facture[ "donnee_au_patient" ]:
            app.logger.warning( f"Facture {facture_id} déjà marquée comme donnée" )
            return jsonify(
                    {
                            "success": False,
                            "message": "Cette facture est déjà marquée comme donnée au patient"
                            }
                    ), 400

        # Marquer comme donnée
        cursor.execute(
                """
                UPDATE factures
                SET donnee_au_patient = TRUE,
                    date_remise_patient = NOW(),
                    remise_par = %s
                WHERE id = %s
                """,
                (g.user[ "id_personnel" ], facture_id)
                )

        # Vérifier que la mise à jour a fonctionné
        if cursor.rowcount == 0:
            app.logger.error( f"Aucune ligne mise à jour pour facture {facture_id}" )
            connection.rollback()
            return jsonify(
                    {
                            "success": False,
                            "message": "Erreur lors de la mise à jour"
                            }
                    ), 500

        connection.commit()
        app.logger.info(
            f"✅ Facture {facture[ 'numero_facture' ]} marquée comme donnée par utilisateur {g.user[ 'id_personnel' ]}"
            )

        # Vérification post-commit
        cursor.execute(
                "SELECT donnee_au_patient FROM factures WHERE id = %s",
                (facture_id,)
                )
        verification = cursor.fetchone()
        app.logger.info( f"Vérification post-commit: donnee_au_patient = {verification[ 'donnee_au_patient' ]}" )

        return jsonify(
                {
                        "success": True,
                        "message": f"Facture {facture[ 'numero_facture' ]} marquée comme donnée au patient"
                        }
                ), 200

    except Exception as e:
        connection.rollback()
        app.logger.error( f"❌ Erreur lors du marquage facture {facture_id}: {str( e )}", exc_info = True )
        return jsonify(
                {
                        "success": False,
                        "message": f"Erreur: {str( e )}"
                        }
                ), 500
    finally:
        cursor.close()
        connection.close()
@app.route("/facturation/annuler_remise/<int:facture_id>", methods=["POST"])
@login_required
@handle_errors()

def annuler_remise_facture(facture_id):
    """Annuler la remise d'une facture au patient"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT numero_facture, donnee_au_patient 
                FROM factures 
                WHERE id = %s
                """,
                (facture_id,)
            )
            facture = cursor.fetchone()

            if not facture:
                app.logger.error(f"Facture {facture_id} introuvable pour annulation remise")
                return jsonify({
                    "success": False,
                    "message": "Facture introuvable"
                }), 404

            if not facture["donnee_au_patient"]:
                app.logger.warning(f"Tentative annulation remise facture {facture_id} non donnée")
                return jsonify({
                    "success": False,
                    "message": "Cette facture n'est pas marquée comme donnée"
                }), 400

            # Annuler la remise
            cursor.execute(
                """
                UPDATE factures
                SET donnee_au_patient = FALSE,
                    date_remise_patient = NULL,
                    remise_par = NULL
                WHERE id = %s
                """,
                (facture_id,)
            )

            app.logger.info(f"Remise annulée pour facture {facture['numero_facture']}")

        return jsonify({
            "success": True,
            "message": "Remise annulée avec succès"
        }), 200

    except Exception as e:
        app.logger.error(f"Erreur annulation remise facture {facture_id}: {str(e)}")
        return jsonify(
            {
                    "success": False,
                    "message": f"Erreur: {str( e )}"
                    }
                ), 500


@app.route("/facturation/transformer_proforma/<int:proforma_id>", methods=["POST"])
@login_required
@handle_errors()

def transformer_proforma(proforma_id):
    """Transformer un proforma validé en facture - VERSION OPTIMISÉE"""
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # ============================================================================
        # OPTIMISATION: Transaction complète avec FOR UPDATE
        # ============================================================================
        cursor.execute("""
                       SELECT *
                       FROM factures
                       WHERE id = %s
                         AND type_facture = 'proforma'
                         AND statut = 'valide'
                         AND est_transforme = FALSE
                           FOR
                       UPDATE
                       """, (proforma_id,))

        proforma = cursor.fetchone()

        if not proforma:
            flash("Proforma introuvable, non validé ou déjà transformé", "error")
            return redirect(url_for("voir_facture", facture_id=proforma_id))

        # Récupération des lignes
        cursor.execute("""
                       SELECT *
                       FROM facture_lignes
                       WHERE facture_id = %s
                       ORDER BY ordre, id
                       """, (proforma_id,))
        lignes_proforma = cursor.fetchall()

        # Génération du numéro de facture
        date_obj = datetime.now()
        year_suffix = str(date_obj.year)[-2:]
        prefix_with_year = f"FAC{year_suffix}"

        cursor.execute(
            """
            SELECT numero_facture
            FROM factures
            WHERE type_facture = 'facture'
              AND YEAR(date_facture) = %s
              AND numero_facture LIKE %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (date_obj.year, f"{prefix_with_year}%")
        )

        last_facture = cursor.fetchone()
        if last_facture:
            last_num = int(last_facture["numero_facture"][-5:])
            numero_facture = f"{prefix_with_year}{str(last_num + 1).zfill(5)}"
        else:
            numero_facture = f"{prefix_with_year}00001"

        # Création de la facture
        cursor.execute(
            """
            INSERT INTO factures (numero_facture, type_facture, date_facture,
                                  patient_nom, patient_prenom, patient_adresse, patient_telephone,
                                  patient_raison_sociale, patient_nif, patient_rc, patient_article,
                                  mode_paiement, numero_cheque, montant_paye_caisse,
                                  notes, created_by,
                                  proforma_origine_id, proforma_origine_numero)
            SELECT %s,
                   'facture',
                   %s,
                   patient_nom,
                   patient_prenom,
                   patient_adresse,
                   patient_telephone,
                   patient_raison_sociale,
                   patient_nif,
                   patient_rc,
                   patient_article,
                   mode_paiement,
                   numero_cheque,
                   montant_paye_caisse,
                   CONCAT('Facture issue du proforma ', numero_facture,
                          CASE
                              WHEN notes IS NOT NULL AND notes != ''
                                  THEN CONCAT('. Notes originales: ', notes)
                              ELSE '' END),
                   %s,
                   %s,
                   numero_facture
            FROM factures
            WHERE id = %s
            """,
            (numero_facture, date_obj.date(), g.user['id_personnel'],
             proforma_id, proforma_id)
        )

        facture_id = cursor.lastrowid

        # Copie des lignes en batch
        for ligne in lignes_proforma:
            cursor.execute(
                """
                INSERT INTO facture_lignes (facture_id, type_ligne, est_debours, designation,
                                            quantite, prix_unitaire, montant_ht,
                                            taux_tva, montant_tva, montant_ttc,
                                            description, reference_justificatif, ordre)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    facture_id, ligne['type_ligne'], ligne['est_debours'],
                    ligne['designation'], ligne['quantite'], ligne['prix_unitaire'],
                    ligne['montant_ht'], ligne['taux_tva'], ligne['montant_tva'],
                    ligne['montant_ttc'], ligne.get('description'),
                    ligne.get('reference_justificatif'), ligne.get('ordre')
                )
            )

        # Marquer le proforma comme transformé
        cursor.execute(
            "UPDATE factures SET est_transforme = TRUE WHERE id = %s",
            (proforma_id,)
        )

        connection.commit()

        flash(f"Proforma {proforma['numero_facture']} transformé en facture {numero_facture} avec succès", "success")
        return redirect(url_for("editer_facture", facture_id=facture_id))

    except Exception as e:
        connection.rollback()
        flash(f"Erreur lors de la transformation : {str(e)}", "error")
        return redirect(url_for("voir_facture", facture_id=proforma_id))
    finally:
        cursor.close()
        connection.close()


@app.route("/facturation/voir/<int:facture_id>")
@login_required
@handle_errors()

def voir_facture(facture_id):
    """Voir le détail d'une facture - VERSION OPTIMISÉE"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Requête unique avec tous les JOINs
    cursor.execute("""
                   SELECT f.*,
                          CONCAT(pc.nom, ' ', pc.prenom) AS cree_par_nom,
                          CONCAT(pv.nom, ' ', pv.prenom) AS valide_par_nom,
                          CONCAT(pa.nom, ' ', pa.prenom) AS annule_par_nom,
                          CONCAT(pr.nom, ' ', pr.prenom) as remise_par_nom
                   FROM factures f
                            LEFT JOIN personnel pc ON pc.id_personnel = f.created_by
                            LEFT JOIN personnel pv ON pv.id_personnel = f.valide_par
                            LEFT JOIN personnel pa ON pa.id_personnel = f.annule_par
                            LEFT JOIN personnel pr ON f.remise_par = pr.id_personnel

                   WHERE f.id = %s
                   """, (facture_id,))

    facture = cursor.fetchone()

    if not facture:
        cursor.close()
        connection.close()
        flash("Facture introuvable", "error")
        return redirect(url_for("facturation"))

    cursor.execute(
        "SELECT * FROM facture_lignes WHERE facture_id = %s ORDER BY ordre, id",
        (facture_id,)
    )
    lignes = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "facturation/voir.html",
        facture=facture,
        lignes=lignes,
        clinique=get_clinique_info_cached()
    )


@app.route("/facturation/changer_mode_paiement/<int:facture_id>", methods=["POST"])
@login_required
@handle_errors()

def changer_mode_paiement(facture_id):
    """Changer le mode de paiement"""
    try:
        mode_paiement = request.form.get("mode_paiement")
        numero_cheque = request.form.get("numero_cheque", "").strip() if mode_paiement == "cheque" else None

        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE factures SET mode_paiement = %s, numero_cheque = %s WHERE id = %s",
                (mode_paiement, numero_cheque, facture_id)
            )
            totaux = CalculateurFacture.recalculer_facture_complete(cursor, facture_id)

        return jsonify({
            "success": True,
            "message": "Mode de paiement mis à jour",
            "droit_timbre": float(totaux["droit_timbre"])
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"Erreur: {str(e)}"}), 400




# ============================================================================
# EXPORT EXCEL - VERSION OPTIMISÉE (code identique mais avec meilleures requêtes)
# ============================================================================

@app.route("/facturation/export/excel")
@login_required
@handle_errors()

def export_factures_excel():
    """Export Excel - VERSION OPTIMISÉE"""
    connection = get_db_connection()
    cursor = connection.cursor()

    # Récupération des paramètres
    type_facture = request.args.get("type", "facture")
    statut = request.args.get("statut", "")
    recherche_patient = request.args.get("recherche_patient", "")
    avec_debours = request.args.get("avec_debours", "")
    date_debut = request.args.get("date_debut", "")
    date_fin = request.args.get("date_fin", "")

    types_factures = ["facture", "proforma"]

    wb = Workbook()
    wb.remove(wb.active)

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", start_color="0066CC")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    money_format = '#,##0.00 "DA"'
    center_align = Alignment(horizontal="center", vertical="center")

    # Construction des filtres communs (OPTIMISATION: Une seule fois)
    base_filters_sql = []
    base_params = []

    if statut:
        base_filters_sql.append("statut = %s")
        base_params.append(statut)

    if recherche_patient:
        base_filters_sql.append("""(
            LOWER(CONCAT(patient_nom, ' ', patient_prenom)) LIKE LOWER(%s)
            OR LOWER(numero_facture) LIKE LOWER(%s)
        )""")
        sp = f"%{recherche_patient}%"
        base_params.extend([sp, sp])

    if avec_debours == "oui":
        base_filters_sql.append("total_debours > 0")
    elif avec_debours == "non":
        base_filters_sql.append("(total_debours = 0 OR total_debours IS NULL)")

    if date_debut:
        base_filters_sql.append("date_facture >= %s")
        base_params.append(date_debut)

    if date_fin:
        base_filters_sql.append("date_facture <= %s")
        base_params.append(date_fin)

    # Pour chaque type de facture
    for type_facture_loop in types_factures:
        ws = wb.create_sheet(title=type_facture_loop.upper())

        # En-tête
        ws.insert_rows(1, amount=4)
        ws["A1"] = f"EXPORT {type_facture_loop.upper()}"
        ws["A1"].font = Font(bold=True, size=14)

        info = f"Type: {type_facture_loop.upper()}"
        if statut: info += f" | Statut: {statut.upper()}"
        if date_debut: info += f" | Début: {date_debut}"
        if date_fin: info += f" | Fin: {date_fin}"

        ws["A2"] = info
        ws["A2"].font = Font(italic=True, color="666666")
        ws["A3"] = f"Exporté le : {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        ws["A3"].font = Font(italic=True, size=9)

        ws.merge_cells("A1:Q1")
        ws.merge_cells("A2:Q2")
        ws.merge_cells("A3:Q3")

        # Headers
        headers = [
            "N° Facture", "Date", "Patient", "Total HT", "TVA 9%", "TVA 19%",
            "Total TVA", "Total TTC", "Débours", "Timbre", "Total Net",
    "Mode Paiement", "N° Chèque", "Statut",
    "Donnée patient", "Date remise",
    "Créé par", "Validé par", "Date Validation"
        ]

        header_row = 5
        for col, title in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=col, value=title)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        # Construction requête optimisée
        where_parts = ["type_facture = %s"] + base_filters_sql
        query = f"""
            SELECT vfr.*
            FROM v_factures_resume vfr
            WHERE {' AND '.join(where_parts)}
            ORDER BY vfr.date_facture DESC, vfr.numero_facture DESC
        """
        params = [type_facture_loop] + base_params

        cursor.execute(query, params)
        factures = cursor.fetchall()

        # Données
        data_start = header_row + 1
        for i, f in enumerate(factures):
            row = data_start + i
            ws.cell(row=row, column=1, value=f["numero_facture"])
            ws.cell(row=row, column=2, value=f["date_facture"].strftime("%d/%m/%Y"))
            ws.cell(row=row, column=3, value=f["patient_complet"])
            ws.cell(row=row, column=4, value=safe_float(f["total_ht"]))
            ws.cell(row=row, column=5, value=safe_float(f["total_tva_9"]))
            ws.cell(row=row, column=6, value=safe_float(f["total_tva_19"]))
            ws.cell(row=row, column=7, value=safe_float(f["total_tva"]))
            ws.cell(row=row, column=8, value=safe_float(f["total_ttc"]))
            ws.cell(row=row, column=9, value=safe_float(f["total_debours"]))
            ws.cell(row=row, column=10, value=safe_float(f["droit_timbre"]))
            ws.cell(row=row, column=11, value=safe_float(f["total_net"]))
            ws.cell(row=row, column=12, value=f["mode_paiement"].upper() if f["mode_paiement"] else "")
            ws.cell(row=row, column=13, value=f["numero_cheque"] or "")
            ws.cell(row=row, column=14, value=f["statut"].upper())
            ws.cell( row = row, column = 15, value = "Oui" if f[ "donnee_au_patient" ] else "Non" )
            ws.cell(
                row = row, column = 16,
                value = f[ "date_remise_patient" ].strftime( "%d/%m/%Y %H:%M" ) if f[ "date_remise_patient" ] else ""
                )
            ws.cell(row=row, column=17, value=f["createur"] or "")
            ws.cell(row=row, column=18, value=f["validateur"] or "")
            ws.cell(row=row, column=19,
                    value=f["date_validation"].strftime("%d/%m/%Y %H:%M") if f["date_validation"] else "")

            ws.cell(row=row, column=2).alignment = center_align
            ws.cell(row=row, column=12).alignment = center_align
            ws.cell(row=row, column=14).alignment = center_align

        data_end = data_start + len(factures) - 1 if factures else data_start

        # Format monétaire
        if factures:
            for row in ws.iter_rows(min_row=data_start, max_row=data_end, min_col=4, max_col=11):
                for cell in row:
                    cell.number_format = money_format
                    cell.alignment = Alignment(horizontal="right", vertical="center")

        # Table Excel
        if factures:
            table = ExcelTable(
                displayName=f"Table_{type_facture_loop}",
                ref=f"A{header_row}:Q{data_end}"
            )
            style = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
            table.tableStyleInfo = style
            ws.add_table(table)

        ws.freeze_panes = f"A{data_start}"

        # Totaux
        if factures:
            total_row = data_end + 2
            ws.cell(row=total_row, column=3, value="TOTAL").font = Font(bold=True)
            ws.cell(row=total_row, column=3).alignment = Alignment(horizontal="right")

            for col in range(4, 12):
                letter = chr(64 + col)
                c = ws.cell(row=total_row, column=col)
                c.value = f"=SUBTOTAL(109,{letter}{data_start}:{letter}{data_end})"
                c.font = Font(bold=True)
                c.number_format = money_format
                c.fill = PatternFill("solid", start_color="FFFFCC")
                c.alignment = Alignment(horizontal="right")

        # Largeurs colonnes
        column_widths = {
            'A': 15, 'B': 12, 'C': 30, 'D': 15, 'E': 15, 'F': 15, 'G': 15,
            'H': 15, 'I': 15, 'J': 12, 'K': 15, 'L': 18, 'M': 18, 'N': 12,
            'O': 20, 'P': 20, 'Q': 18
        }

        for col, width in column_widths.items():
            ws.column_dimensions[col].width = width

        ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
        ws.page_setup.fitToWidth = 1

    cursor.close()
    connection.close()

    # Sauvegarde
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"factures_complet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ============================================================================
# FONCTIONS PDF OPTIMISÉES
# ============================================================================
"""
Module de génération de PDF pour les factures - VERSION OPTIMISÉE
"""


# ============================================================================
# CONSTANTES DE CONFIGURATION PDF
# ============================================================================

class PDFConfig:
    """Configuration centralisée pour la génération PDF"""

    # Dimensions
    MARGIN_TOP = 0.8 * cm
    MARGIN_BOTTOM = 2.0 * cm
    MARGIN_LEFT = 1.5 * cm
    MARGIN_RIGHT = 1.5 * cm

    HEADER_HEIGHT = 5 * cm
    FOOTER_HEIGHT = 1.5 * cm

    LOGO_WIDTH = 2.5 * cm
    LOGO_HEIGHT = 2.5 * cm

    TITLE_BOX_WIDTH = 5 * cm
    TITLE_BOX_HEIGHT = 2.5 * cm

    # Colonnes tableau lignes
    COL_WIDTHS_LIGNES = [ 7.5 * cm, 2 * cm, 2.5 * cm, 1.8 * cm, 3.2 * cm ]
    COL_WIDTHS_TOTAUX = [ 4.5 * cm, 4.5 * cm ]
    COL_WIDTHS_FOOTER = [ 8 * cm, 9 * cm ]

    # Palette couleurs N&B
    PALETTE = {
            'noir': HexColor( '#000000' ),
            'blanc': HexColor( '#FFFFFF' ),
            'gris_clair': HexColor( '#E0E0E0' ),
            'gris_moyen': HexColor( '#808080' ),
            'gris_fonce': HexColor( '#404040' ),
            'rouge_debours': HexColor( '#E8505B' ),
            }

    # Tailles de police
    FONT_SIZES = {
            'titre_clinique': 15,
            'nom_client': 11,
            'label_section': 11,
            'texte_normal': 10,
            'texte_small': 9,
            'texte_tiny': 8,
            'texte_micro': 7,
            'numero_facture': 10,
            'type_document': 16,
            'total_ttc': 13,
            'watermark': 80,
            }


# ============================================================================
# GESTIONNAIRE DE CONTEXTE DB
# ============================================================================

@contextmanager
def db_connection():
    """Context manager pour la connexion à la base de données"""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


# ============================================================================
# FACTORY DE STYLES
# ============================================================================

class PDFStyleFactory:
    """Factory pour créer et mettre en cache les styles PDF"""

    _styles_cache = None


    @classmethod
    @lru_cache( maxsize = 1 )
    def get_base_styles( cls ):
        """Récupère les styles de base ReportLab"""
        return getSampleStyleSheet()


    @classmethod
    def get_styles( cls ) -> Dict[ str, ParagraphStyle ]:
        """Récupère tous les styles personnalisés (mis en cache)"""
        if cls._styles_cache is not None:
            return cls._styles_cache

        base = cls.get_base_styles()
        palette = PDFConfig.PALETTE
        fonts = PDFConfig.FONT_SIZES

        cls._styles_cache = {
                # En-tête et émetteur
                'emetteur_titre': ParagraphStyle(
                        "EmetteurTitre",
                        parent = base[ 'Normal' ],
                        fontName = "Helvetica-Bold",
                        fontSize = fonts[ 'titre_clinique' ],
                        textColor = palette[ 'noir' ],
                        leading = 18
                        ),
                'emetteur_texte': ParagraphStyle(
                        "EmetteurTexte",
                        parent = base[ 'Normal' ],
                        fontName = "Helvetica",
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        leading = 12
                        ),
                # Client
                'client_label': ParagraphStyle(
                        "ClientLabel",
                        parent = base[ 'Normal' ],
                        fontName = "Helvetica-Bold",
                        fontSize = fonts[ 'label_section' ],
                        textColor = palette[ 'noir' ],
                        backColor = palette[ 'blanc' ],
                        borderPadding = 6,
                        leading = 14
                        ),
                'client_value': ParagraphStyle(
                        "ClientValue",
                        parent = base[ 'Normal' ],
                        fontName = "Helvetica",
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        leading = 16
                        ),
                # Tableau lignes
                'table_header': ParagraphStyle(
                        'TableHeader',
                        parent = base[ 'Normal' ],
                        fontName = 'Helvetica-Bold',
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        alignment = TA_CENTER
                        ),
                'cell_normal': ParagraphStyle(
                        'CellNormal',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        leading = 13
                        ),
                'cell_center': ParagraphStyle(
                        'CellCenter',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        alignment = TA_CENTER,
                        leading = 13
                        ),
                'cell_right': ParagraphStyle(
                        'CellRight',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        alignment = TA_RIGHT,
                        leading = 13
                        ),
                'cell_right_bold': ParagraphStyle(
                        'CellRightBold',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        fontName = 'Helvetica-Bold',
                        alignment = TA_RIGHT,
                        leading = 13
                        ),
                # Totaux
                'total_label': ParagraphStyle(
                        'TotalLabel',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        alignment = TA_RIGHT,
                        fontName = "Helvetica"
                        ),
                'total_value': ParagraphStyle(
                        'TotalValue',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'texte_normal' ],
                        textColor = palette[ 'noir' ],
                        alignment = TA_RIGHT,
                        fontName = "Helvetica-Bold"
                        ),
                'total_grand': ParagraphStyle(
                        'TotalGrand',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'total_ttc' ],
                        textColor = palette[ 'noir' ],
                        fontName = "Helvetica-Bold",
                        alignment = TA_RIGHT
                        ),
                # Divers
                'proforma_ref': ParagraphStyle(
                        'ProformaRef',
                        parent = base[ 'Normal' ],
                        fontSize = fonts[ 'texte_small' ],
                        textColor = palette[ 'gris_fonce' ],
                        alignment = TA_CENTER
                        ),
                }

        return cls._styles_cache


# ============================================================================
# UTILITAIRES DE FORMATAGE
# ============================================================================

class FormatUtils:
    """Utilitaires de formatage pour les factures"""


    @staticmethod
    def format_montant( montant: float ) -> str:
        """Formate un montant avec séparateurs de milliers"""
        if montant is None:
            return "0,00"
        return f"{montant:,.2f}".replace( ",", " " ).replace( ".", "," )


    @staticmethod
    def get_nom_client( facture: Dict ) -> str:
        """Retourne le nom complet du client"""
        return (facture.get( 'patient_raison_sociale' ) or
                f"{facture[ 'patient_nom' ]} {facture[ 'patient_prenom' ]}")


    @staticmethod
    def get_mode_paiement_text( facture: Dict, avec_emoji: bool = True ) -> str:
        """Retourne le texte du mode de paiement"""
        modes = {
                'especes': ('💵 Espèces', 'Espèces'),
                'cheque': ('📝 Chèque', 'Chèque'),
                'virement': ('🏦 Virement', 'Virement'),
                'carte': ('💳 Carte bancaire', 'Carte bancaire')
                }
        mode = facture.get( 'mode_paiement', 'especes' )
        return modes.get( mode, (mode, mode) )[ 0 if avec_emoji else 1 ]


    @staticmethod
    def montant_en_lettres( montant: Decimal ) -> str:
        """Convertit un montant en toutes lettres"""
        montant = Decimal( str( montant ) ).quantize( Decimal( '0.01' ) )
        dinars = int( montant )
        centimes = int( (montant - dinars) * 100 )

        dinars_lettres = num2words( dinars, lang = 'fr' ).capitalize()
        centimes_lettres = num2words( centimes, lang = 'fr' )

        return f"<b>{dinars_lettres}</b> dinars et <b>{centimes_lettres}</b> centimes"


# ============================================================================
# GÉNÉRATEUR DE CONTENU PDF
# ============================================================================

class PDFContentGenerator:
    """Génère le contenu des différentes sections du PDF"""


    def __init__( self, facture: Dict, lignes: List[ Dict ] ):
        self.facture = facture
        self.lignes = lignes
        self.styles = PDFStyleFactory.get_styles()
        self.palette = PDFConfig.PALETTE
        self.config = PDFConfig


    def creer_logo_et_entete( self ) -> Table:
        """Crée le bloc logo + informations clinique"""
        # Logo
        try:
            logo = Image(
                    'app/static/images/logo_inaya.png',
                    width = self.config.LOGO_WIDTH,
                    height = self.config.LOGO_HEIGHT
                    )
        except Exception:
            logo = Spacer( self.config.LOGO_WIDTH, self.config.LOGO_HEIGHT )

        # Informations clinique
        if self.facture.get( 'statut' ) != 'valide':
            # Brouillon
            brouillon_style = ParagraphStyle(
                    'Brouillon',
                    parent = self.styles[ 'emetteur_titre' ],
                    fontSize = 30,
                    textColor = self.palette[ 'gris_moyen' ]
                    )
            return Paragraph( "BROUILLON", brouillon_style )

        # Facture valide
        clinique = ConfigService.get_clinique_info()

        emetteur_content = [
                Paragraph( f"<b>{clinique[ 'nom' ]}</b>", self.styles[ 'emetteur_titre' ] ),
                Spacer( 1, 3 * mm ),
                Paragraph(
                        f"{clinique[ 'adresse' ]}<br/>Tél: {clinique[ 'telephone' ]}",
                        self.styles[ 'emetteur_texte' ]
                        ),
                Paragraph(
                        f"<b>NIF:</b> {clinique[ 'nif' ]} | <b>NIS:</b> {clinique[ 'nis' ]}",
                        self.styles[ 'emetteur_texte' ]
                        ),
                Paragraph( f"<b>RC:</b> {clinique[ 'rc' ]}", self.styles[ 'emetteur_texte' ] ),
                Paragraph(
                        f"<b>Art:</b> {clinique[ 'article' ]} | <b>Capital:</b> {clinique[ 'capital' ]} DA",
                        self.styles[ 'emetteur_texte' ]
                        ),
                ]

        tbl = Table( [ [ logo, emetteur_content ] ], colWidths = [ 3 * cm, 14 * cm ] )
        tbl.setStyle(
                TableStyle(
                        [
                                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                                ('ALIGN', (1, 0), (1, 0), 'LEFT'),
                                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                ]
                        )
                )

        return tbl


    def creer_bloc_client( self ) -> Tuple[ Table, Table ]:
        """Crée le bloc d'informations client"""

        largeur = 17 * cm

        nom_client = escape(FormatUtils.get_nom_client(self.facture))
        adresse = escape(self.facture.get('patient_adresse', 'Adresse non renseignée'))
        telephone = escape(self.facture.get('patient_telephone', '-'))

        lignes = [
            f"<b><font size=11>{nom_client}</font></b>",
            f"<font size=10>{adresse}</font>",
            f"<font size=10><b>Tél :</b> {telephone}</font>",
        ]

        if self.facture.get('patient_nif'):
            lignes.append(
                f"<font size=10><b>NIF :</b> {escape(self.facture['patient_nif'])}</font>"
            )

        if self.facture.get('patient_rc'):
            lignes.append(
                f"<font size=10><b>RC :</b> {escape(self.facture['patient_rc'])}</font>"
            )

        client_info = "<br/>".join(lignes)

        # Label
        texte_label = (
            "FACTURÉ À"
            if self.facture.get('statut') == 'valide'
            else "BROUILLON"
        )

        label = Table(
            [[Paragraph(texte_label, self.styles['client_label'])]],
            colWidths=[largeur],
        )
        label.setStyle(
            TableStyle(
                [
                    ('BACKGROUND', (0, 0), (-1, -1), self.palette['blanc']),
                    ('LEFTPADDING', (0, 0), (-1, -1), 10),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]
            )
        )

        # Contenu
        contenu = Table(
            [[Paragraph(client_info, self.styles['client_value'])]],
            colWidths=[largeur],
        )
        contenu.setStyle(
            TableStyle(
                [
                    ('LEFTPADDING', (0, 0), (-1, -1), 10),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                    ('TOPPADDING', (0, 0), (-1, -1), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                    ('BOX', (0, 0), (-1, -1), 2, self.palette['noir']),
                    ('BACKGROUND', (0, 0), (-1, -1), self.palette['blanc']),
                ]
            )
        )

        return label, contenu


    def creer_tableau_lignes( self ) -> Table:
        """Crée le tableau des lignes de facture"""
        # En-têtes
        headers = [
                Paragraph( "DÉSIGNATION", self.styles[ 'table_header' ] ),
                Paragraph( "QTÉ", self.styles[ 'table_header' ] ),
                Paragraph( "PRIX U.", self.styles[ 'table_header' ] ),
                Paragraph( "TVA", self.styles[ 'table_header' ] ),
                Paragraph( "TOTAL", self.styles[ 'table_header' ] ),
                ]
        data = [ headers ]

        # Lignes de produits
        for ligne in self.lignes:
            # Nom produit
            nom_produit = f"<b>{ligne[ 'designation' ]}</b>"
            if ligne.get( "description" ):
                nom_produit += f"<br/><font size=8>{ligne[ 'description' ]}</font>"

            # Gestion débours
            if ligne.get( "est_debours" ):
                nom_produit = f"<font color='{self.palette[ 'rouge_debours' ]}'>"
                nom_produit += f"<b>{ligne[ 'designation' ]}</b> [Débours]</font>"
                if ligne.get( "description" ):
                    nom_produit += f"<br/><font size=8>{ligne[ 'description' ]}</font>"
                tva_str = "-"
                total_ligne = ligne[ "montant_ht" ]
            else:
                tva_str = f"{ligne[ 'taux_tva' ]:.0f}%"
                total_ligne = ligne[ "montant_ttc" ]

            data.append(
                    [
                            Paragraph( nom_produit, self.styles[ 'cell_normal' ] ),
                            Paragraph( f"{ligne[ 'quantite' ]:.2f}", self.styles[ 'cell_center' ] ),
                            Paragraph(
                                FormatUtils.format_montant( ligne[ 'prix_unitaire' ] ), self.styles[ 'cell_right' ]
                                ),
                            Paragraph( tva_str, self.styles[ 'cell_center' ] ),
                            Paragraph(
                                f"<b>{FormatUtils.format_montant( total_ligne )}</b>", self.styles[ 'cell_right_bold' ]
                                )
                            ]
                    )

        # Création du tableau
        tbl = Table( data, colWidths = self.config.COL_WIDTHS_LIGNES, repeatRows = 1 )

        tbl.setStyle(
                TableStyle(
                        [
                                # En-tête
                                ('BACKGROUND', (0, 0), (-1, 0), self.palette[ 'blanc' ]),
                                ('TEXTCOLOR', (0, 0), (-1, 0), self.palette[ 'noir' ]),
                                ('ALIGN', (1, 0), (-1, 0), 'CENTER'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 10),
                                ('TOPPADDING', (0, 0), (-1, 0), 10),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                                ('LINEBELOW', (0, 0), (-1, 0), 2, self.palette[ 'noir' ]),
                                # Corps
                                ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                                ('ALIGN', (3, 1), (3, -1), 'CENTER'),
                                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                                ('TOPPADDING', (0, 1), (-1, -1), 8),
                                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                                # Bordures
                                ('LINEBELOW', (0, 1), (-1, -1), 0.5, self.palette[ 'gris_clair' ]),
                                ('BOX', (0, 0), (-1, -1), 1, self.palette[ 'noir' ]),
                                ]
                        )
                )

        return tbl


    def creer_tableau_totaux( self ) -> Table:
        """Crée le tableau des totaux"""
        totaux_data = [
                [
                        Paragraph( "Total HT", self.styles[ 'total_label' ] ),
                        Paragraph(
                            f"{FormatUtils.format_montant( self.facture[ 'total_ht' ] )} DA",
                            self.styles[ 'total_value' ]
                            )
                        ]
                ]

        # TVA 9%
        if self.facture.get( 'total_tva_9', 0 ) > 0:
            totaux_data.append(
                    [
                            Paragraph( "TVA 9%", self.styles[ 'total_label' ] ),
                            Paragraph(
                                f"{FormatUtils.format_montant( self.facture[ 'total_tva_9' ] )} DA",
                                self.styles[ 'total_value' ]
                                )
                            ]
                    )

        # TVA 19%
        if self.facture.get( 'total_tva_19', 0 ) > 0:
            totaux_data.append(
                    [
                            Paragraph( "TVA 19%", self.styles[ 'total_label' ] ),
                            Paragraph(
                                f"{FormatUtils.format_montant( self.facture[ 'total_tva_19' ] )} DA",
                                self.styles[ 'total_value' ]
                                )
                            ]
                    )

        # Total TVA
        if self.facture.get( 'total_tva', 0 ) > 0:
            totaux_data.append(
                    [
                            Paragraph( "<b>Total TVA</b>", self.styles[ 'total_label' ] ),
                            Paragraph(
                                f"{FormatUtils.format_montant( self.facture[ 'total_tva' ] )} DA",
                                self.styles[ 'total_value' ]
                                )
                            ]
                    )

        # Débours
        if self.facture.get( 'total_debours', 0 ) > 0:
            totaux_data.append(
                    [
                            Paragraph( "Débours", self.styles[ 'total_label' ] ),
                            Paragraph(
                                f"{FormatUtils.format_montant( self.facture[ 'total_debours' ] )} DA",
                                self.styles[ 'total_value' ]
                                )
                            ]
                    )

        # Droit de timbre
        if self.facture.get( 'droit_timbre', 0 ) > 0:
            totaux_data.append(
                    [
                            Paragraph( "Droit de timbre", self.styles[ 'total_label' ] ),
                            Paragraph(
                                f"{FormatUtils.format_montant( self.facture[ 'droit_timbre' ] )} DA",
                                self.styles[ 'total_value' ]
                                )
                            ]
                    )

        # Total TTC
        totaux_data.append(
                [
                        Paragraph( "Total TTC ", self.styles[ 'total_grand' ] ),
                        Paragraph(
                            f"{FormatUtils.format_montant( self.facture[ 'total_net' ] )} DA",
                            self.styles[ 'total_grand' ]
                            )
                        ]
                )

        tbl = Table( totaux_data, colWidths = self.config.COL_WIDTHS_TOTAUX )
        tbl.setStyle(
                TableStyle(
                        [
                                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                ('TOPPADDING', (0, 0), (-1, -2), 4),
                                ('BOTTOMPADDING', (0, 0), (-1, -2), 4),
                                ('LINEABOVE', (0, -1), (-1, -1), 2, self.palette[ 'noir' ]),
                                ('TOPPADDING', (0, -1), (-1, -1), 8),
                                ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
                                ('BOX', (0, -1), (-1, -1), 2, self.palette[ 'noir' ]),
                                ]
                        )
                )

        return tbl


    def creer_bloc_footer_gauche( self ) -> Paragraph:
        """Crée le bloc de gauche du footer (paiement, montant en lettres, notes)"""
        content = ""

        # Mode de paiement
        if self.facture.get( 'mode_paiement' ):
            mode_paiement = FormatUtils.get_mode_paiement_text( self.facture, avec_emoji = False )
            content = f"<font size=10><b>Mode de paiement</b></font><br/>"
            content += f"<font size=9>{mode_paiement}</font>"

            if self.facture.get( 'numero_cheque' ):
                content += f"<br/><font size=9>Chèque N°: <b>{self.facture[ 'numero_cheque' ]}</b></font>"

        # Montant en lettres
        if self.facture.get( 'total_net' ) is not None:
            content += f"<br/><br/><font size=9>Arrêtée la présente facture à la somme de :</font><br/>"
            content += f"<font size=10>{FormatUtils.montant_en_lettres( self.facture[ 'total_net' ] )}</font>"

        # Notes
        if self.facture.get( 'notes' ):
            content += f"<br/><br/><font size=10><b>Notes</b></font><br/>"
            content += f"<font size=9>{self.facture[ 'notes' ]}</font>"

        return Paragraph( content, self.styles[ 'emetteur_texte' ] ) if content else Spacer( 1, 1 * mm )


# ============================================================================
# BACKGROUND DRAWER
# ============================================================================

class PDFBackgroundDrawer:
    """Dessine les éléments d'arrière-plan du PDF"""


    @staticmethod
    def draw_background( canvas, doc, facture: Optional[ Dict ] = None ):
        """Dessine l'arrière-plan noir et blanc"""
        width, height = A4
        canvas.saveState()
        palette = PDFConfig.PALETTE
        config = PDFConfig

        # === En-tête ===
        canvas.setStrokeColor( palette[ 'noir' ] )
        canvas.setLineWidth( 3 )
        canvas.line( 1 * cm, height - 0.5 * cm, width - 1 * cm, height - 0.5 * cm )
        canvas.setLineWidth( 1 )
        canvas.line( 1 * cm, height - config.HEADER_HEIGHT, width - 1 * cm, height - config.HEADER_HEIGHT )

        # === Encadré titre (facture valide uniquement) ===
        if facture and facture.get( 'statut' ) == 'valide':
            title_x = width - config.TITLE_BOX_WIDTH - 1.5 * cm
            title_y = height - config.TITLE_BOX_HEIGHT - 1.2 * cm

            # Rectangle
            canvas.setStrokeColor( palette[ 'noir' ] )
            canvas.setLineWidth( 2 )
            canvas.rect( title_x, title_y, config.TITLE_BOX_WIDTH, config.TITLE_BOX_HEIGHT, fill = 0, stroke = 1 )

            # Ligne de séparation
            canvas.setLineWidth( 1 )
            canvas.line(
                    title_x,
                    title_y + config.TITLE_BOX_HEIGHT - 0.8 * cm,
                    title_x + config.TITLE_BOX_WIDTH,
                    title_y + config.TITLE_BOX_HEIGHT - 0.8 * cm
                    )

            # Type de document
            canvas.setFont( "Helvetica-Bold", PDFConfig.FONT_SIZES[ 'type_document' ] )
            canvas.setFillColor( palette[ 'noir' ] )
            type_doc = "FACTURE" if facture[ "type_facture" ] == "facture" else "PROFORMA"
            canvas.drawCentredString(
                    title_x + config.TITLE_BOX_WIDTH / 2,
                    title_y + config.TITLE_BOX_HEIGHT - 0.6 * cm,
                    type_doc
                    )

            # Numéro
            canvas.setFont( "Helvetica-Bold", PDFConfig.FONT_SIZES[ 'numero_facture' ] )
            canvas.drawCentredString(
                    title_x + config.TITLE_BOX_WIDTH / 2,
                    title_y + config.TITLE_BOX_HEIGHT - 1.3 * cm,
                    f"N° {facture[ 'numero_facture' ]}"
                    )

            # Date
            canvas.setFont( "Helvetica", PDFConfig.FONT_SIZES[ 'texte_small' ] )
            date_str = facture[ 'date_facture' ].strftime( '%d/%m/%Y' )
            canvas.drawCentredString(
                    title_x + config.TITLE_BOX_WIDTH / 2,
                    title_y + config.TITLE_BOX_HEIGHT - 1.9 * cm,
                    f"Date : {date_str}"
                    )

        # === Pied de page ===
        canvas.setStrokeColor( palette[ 'noir' ] )
        canvas.setLineWidth( 2 )
        canvas.line( 1 * cm, config.FOOTER_HEIGHT, width - 1 * cm, config.FOOTER_HEIGHT )

        # Numéro de page
        page_num = canvas.getPageNumber()
        canvas.setFont( "Helvetica", PDFConfig.FONT_SIZES[ 'texte_tiny' ] + 1 )
        canvas.setFillColor( palette[ 'noir' ] )
        canvas.drawRightString( width - 1.5 * cm, 0.5 * cm, f"Page {page_num}" )

        # === Watermark ===
        canvas.saveState()
        canvas.translate( width / 2, height / 2 )
        canvas.rotate( 45 )
        canvas.setFont( "Helvetica-Bold", PDFConfig.FONT_SIZES[ 'watermark' ] )
        canvas.setFillColorRGB( 0, 0, 0, alpha = 0.02 )
        canvas.drawCentredString( 0, 0, "FACTURE" )
        canvas.restoreState()

        canvas.restoreState()


# ============================================================================
# GÉNÉRATEUR PRINCIPAL
# ============================================================================

class FacturePDFGenerator:
    """Générateur principal de PDF de facture"""


    def __init__( self, facture: Dict, lignes: List[ Dict ] ):
        self.facture = facture
        self.lignes = lignes
        self.content_gen = PDFContentGenerator( facture, lignes )


    def generer( self, buffer: io.BytesIO ) -> None:
        """Génère le PDF complet dans le buffer"""
        doc = SimpleDocTemplate(
                buffer,
                pagesize = A4,
                topMargin = PDFConfig.MARGIN_TOP,
                bottomMargin = PDFConfig.MARGIN_BOTTOM,
                leftMargin = PDFConfig.MARGIN_LEFT,
                rightMargin = PDFConfig.MARGIN_RIGHT
                )

        elements = [ ]

        # 1. Logo et en-tête
        elements.append( self.content_gen.creer_logo_et_entete() )
        elements.append( Spacer( 1, 1 * cm ) )

        # 2. Bloc client
        label_client, contenu_client = self.content_gen.creer_bloc_client()
        elements.append( label_client )
        elements.append( contenu_client )
        elements.append( Spacer( 1, 1.5 * cm ) )

        # 3. Référence proforma si applicable
        if self.facture.get( 'proforma_origine_numero' ):
            styles = PDFStyleFactory.get_styles()
            elements.append(
                    Paragraph(
                            f"<i>Facture issue du proforma {self.facture[ 'proforma_origine_numero' ]}</i>",
                            styles[ 'proforma_ref' ]
                            )
                    )
            elements.append( Spacer( 1, 0.3 * cm ) )

        # 4. Tableau des lignes
        elements.append( self.content_gen.creer_tableau_lignes() )
        elements.append( Spacer( 1, 0.8 * cm ) )

        # 5. Footer (notes/paiement + totaux)
        left_block = self.content_gen.creer_bloc_footer_gauche()
        right_block = self.content_gen.creer_tableau_totaux()

        footer_layout = Table(
                [ [ left_block, right_block ] ],
                colWidths = PDFConfig.COL_WIDTHS_FOOTER
                )
        footer_layout.setStyle(
                TableStyle(
                        [
                                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                                ]
                        )
                )

        elements.append( footer_layout )

        # 6. Génération avec background
        doc.build(
                elements,
                onFirstPage = lambda c, d: PDFBackgroundDrawer.draw_background( c, d, self.facture ),
                onLaterPages = lambda c, d: PDFBackgroundDrawer.draw_background( c, d, None )
                )


# ============================================================================
# ROUTE FLASK
# ============================================================================

@app.route( "/facturation/pdf/<int:facture_id>" )
@login_required
@handle_errors()
@handle_errors()
def generer_pdf_facture( facture_id ):
    """Générer le PDF d'une facture - VERSION OPTIMISÉE"""
    force_download = request.args.get( 'download', '0' ) == '1'

    # Récupération des données
    with db_connection() as cursor:
        # Facture
        cursor.execute( "SELECT * FROM factures WHERE id = %s", (facture_id,) )
        facture = cursor.fetchone()

        if not facture:
            flash( "Facture introuvable", "error" )
            return redirect( url_for( "facturation" ) )

        if facture[ "statut" ] == "annule":
            flash( "Impossible de générer le PDF d'une facture annulée.", "error" )
            return redirect( url_for( "voir_facture", facture_id = facture_id ) )

        # Lignes
        cursor.execute(
                "SELECT * FROM facture_lignes WHERE facture_id = %s ORDER BY ordre, id",
                (facture_id,)
                )
        lignes = cursor.fetchall()

    # Génération du PDF
    buffer = io.BytesIO()
    generator = FacturePDFGenerator( facture, lignes )
    generator.generer( buffer )

    # Envoi du fichier
    buffer.seek( 0 )
    filename = f"{facture[ 'numero_facture' ]}_NB.pdf"

    response = send_file(
            buffer,
            mimetype = "application/pdf",
            as_attachment = force_download,
            download_name = filename
            )

    if not force_download:
        response.headers[ 'Content-Disposition' ] = f'inline; filename="{filename}"'

    return response