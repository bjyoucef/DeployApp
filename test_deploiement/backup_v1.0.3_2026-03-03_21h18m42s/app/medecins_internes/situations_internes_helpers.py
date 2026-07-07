# app/situations_internes_helpers.py
"""
Fonctions communes pour la gestion des situations financières des médecins internes
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Tuple, Dict


def to_decimal( value, default = 0 ) -> Decimal:
    """Convertit une valeur en Decimal de manière sécurisée"""
    if value is None or value == '':
        return Decimal( str( default ) )
    try:
        return Decimal( str( value ) )
    except (Exception,):
        return Decimal( str( default ) )


def get_periode_defaut() -> Tuple[ str, str ]:
    """Retourne la période par défaut (mois en cours)"""
    today = datetime.now()
    debut = today.replace( day = 1 ).strftime( '%Y-%m-%d' )
    if today.month == 12:
        fin = today.replace( day = 31 ).strftime( '%Y-%m-%d' )
    else:
        fin = (today.replace( month = today.month + 1, day = 1 ) - timedelta( days = 1 )).strftime( '%Y-%m-%d' )
    return debut, fin


def get_situation_paiements_gyneco( cursor, id_gyneco: int, date_debut: str, date_fin: str ) -> Dict:
    """
    Récupère la situation des paiements pour un gynécologue interne
    """
    cursor.execute(
        """
        SELECT COALESCE(SUM(part_gyneco), 0)                                 as total_honoraires,
               COUNT(*)                                                      as total_dossiers,
               SUM(CASE WHEN COALESCE(gyneco_paye, 0) = 0 THEN 1 ELSE 0 END) as nb_non_payes
        FROM accouchement_dossiers
        WHERE id_gyneco = %s
          AND est_gyneco_interne = 1
          AND date_accouchement BETWEEN %s AND %s
          AND (est_annule IS NULL OR est_annule = 0)
                   """, (id_gyneco, date_debut, date_fin)
        )

    result = cursor.fetchone()
    total_honoraires = to_decimal( result[ 'total_honoraires' ] )
    nb_non_payes = int( result[ 'nb_non_payes' ] or 0 )

    cursor.execute(
        """
        SELECT COUNT(DISTINCT dech.id_decharge)          as nb_decharges,
               COALESCE(SUM(dech.montant_paye_total), 0) as montant_paye
        FROM gyneco_interne_decharges dech
        WHERE dech.id_gyneco = %s
          AND dech.statut != 'ANNULE'
          AND dech.periode_debut >= %s
          AND dech.periode_fin <= %s
                   """, (id_gyneco, date_debut, date_fin)
        )

    result = cursor.fetchone()
    montant_paye = to_decimal( result[ 'montant_paye' ] or 0 )
    nb_decharges = int( result[ 'nb_decharges' ] or 0 )

    solde_restant = total_honoraires - montant_paye
    pourcentage_paye = float( (montant_paye / total_honoraires * 100) ) if total_honoraires > 0 else 0

    return {
            'total_honoraires': total_honoraires,
            'montant_paye': montant_paye,
            'solde_restant': solde_restant,
            'nb_decharges': nb_decharges,
            'nb_items_non_payes': nb_non_payes,
            'pourcentage_paye': pourcentage_paye
            }


def get_situation_paiements_medecin( cursor, id_doctor: int, date_debut: str, date_fin: str ) -> Dict:
    """
    Récupère la situation des paiements pour un médecin interne
    """
    cursor.execute(
        """
        SELECT COALESCE(SUM(part_medecin), 0)                                 as total_honoraires,
               COUNT(*)                                                       as total_actes,
               SUM(CASE WHEN COALESCE(medecin_paye, 0) = 0 THEN 1 ELSE 0 END) as nb_non_payes
        FROM medecin_interne_actes
        WHERE id_doctor = %s
          AND date_acte BETWEEN %s AND %s
          AND (est_annule IS NULL OR est_annule = 0)
                   """, (id_doctor, date_debut, date_fin)
        )

    result = cursor.fetchone()
    total_honoraires = to_decimal( result[ 'total_honoraires' ] )
    nb_non_payes = int( result[ 'nb_non_payes' ] or 0 )

    cursor.execute(
        """
        SELECT COUNT(DISTINCT dech.id_decharge)          as nb_decharges,
               COALESCE(SUM(dech.montant_paye_total), 0) as montant_paye
        FROM medecin_interne_decharges dech
        WHERE dech.id_doctor = %s
          AND dech.statut != 'ANNULE'
          AND dech.periode_debut >= %s
          AND dech.periode_fin <= %s
                   """, (id_doctor, date_debut, date_fin)
        )

    result = cursor.fetchone()
    montant_paye = to_decimal( result[ 'montant_paye' ] or 0 )
    nb_decharges = int( result[ 'nb_decharges' ] or 0 )

    solde_restant = total_honoraires - montant_paye
    pourcentage_paye = float( (montant_paye / total_honoraires * 100) ) if total_honoraires > 0 else 0

    return {
            'total_honoraires': total_honoraires,
            'montant_paye': montant_paye,
            'solde_restant': solde_restant,
            'nb_decharges': nb_decharges,
            'nb_items_non_payes': nb_non_payes,
            'pourcentage_paye': pourcentage_paye
            }