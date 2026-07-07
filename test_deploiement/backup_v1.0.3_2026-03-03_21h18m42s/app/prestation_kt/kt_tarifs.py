"""
Utilitaire de résolution des prix et tarifs pour les actes KT.
Gère la logique de fallback (4 niveaux) :
  1. Tarif médecin par convention (kt_medecin_tarifs WHERE id_convention = X)
  2. Tarif médecin standard     (kt_medecin_tarifs WHERE id_convention IS NULL)
  3. Prix convention             (kt_actes_conventions)
  4. Prix standard acte          (kt_actes.prix_payant / prix_urgence)
"""


def resoudre_prix(cursor, id_acte, id_convention, id_doctor, est_urgence=False):
    """
    Résout le prix et les honoraires pour un acte donné.

    Hiérarchie de résolution (non-urgence) :
        1. Tarif médecin spécifique à la convention
        2. Prix de la convention (kt_actes_conventions)
        3. Tarif médecin standard payante (UNIQUEMENT si aucune convention)
        4. Prix standard de l'acte (kt_actes.prix_payant)

    Hiérarchie de résolution (urgence) :
        1. Tarif urgence médecin spécifique
        2. Prix urgence standard de l'acte

    Args:
        cursor: DB cursor (DictCursor)
        id_acte: ID de l'acte
        id_convention: ID de la convention (None = payante hors convention)
        id_doctor: ID du médecin
        est_urgence: True si le dossier est en urgence

    Returns:
        tuple: (prix, part_operateur, source)
            - prix: le prix clinique résolu
            - part_operateur: les honoraires médecin résolus
            - source: 'MEDECIN_CONV', 'MEDECIN_STD', 'CONVENTION', 'PAYANTE' ou 'URGENCE'
    """
    from decimal import Decimal

    # ========================================
    # CAS URGENCE
    # ========================================
    if est_urgence:
        # 1. Tarif urgence médecin spécifique ?
        cursor.execute("""
            SELECT prix, part_operateur FROM kt_medecin_tarifs
            WHERE id_doctor = %s AND id_acte = %s
              AND est_urgence = 1 AND est_actif = 1
            LIMIT 1
        """, (id_doctor, id_acte))
        tarif = cursor.fetchone()
        if tarif:
            return Decimal(str(tarif['prix'])), Decimal(str(tarif['part_operateur'])), 'MEDECIN_URG'

        # 2. Fallback : prix urgence standard de l'acte
        cursor.execute("""
            SELECT prix_urgence, honoraires_urgence
            FROM kt_actes WHERE id_acte = %s
        """, (id_acte,))
        acte = cursor.fetchone()
        if acte:
            return Decimal(str(acte['prix_urgence'])), Decimal(str(acte['honoraires_urgence'])), 'URGENCE'

        return Decimal('0'), Decimal('0'), 'URGENCE'

    # ========================================
    # CAS NORMAL (non urgence)
    # ========================================

    # 1. Tarif médecin spécifique pour CETTE convention ?
    if id_convention:
        cursor.execute("""
            SELECT prix, part_operateur FROM kt_medecin_tarifs
            WHERE id_doctor = %s AND id_acte = %s
              AND id_convention = %s AND est_urgence = 0 AND est_actif = 1
            LIMIT 1
        """, (id_doctor, id_acte, id_convention))
        tarif = cursor.fetchone()
        if tarif:
            return Decimal(str(tarif['prix'])), Decimal(str(tarif['part_operateur'])), 'MEDECIN_CONV'

    # 2. Prix de la convention (kt_actes_conventions) ?
    #    → S'applique quand une convention est sélectionnée mais
    #      le médecin n'a pas de tarif spécifique pour cette convention
    if id_convention:
        cursor.execute("""
            SELECT prix, part_operateur FROM kt_actes_conventions
            WHERE id_acte = %s AND id_convention = %s AND est_actif = 1
        """, (id_acte, id_convention))
        conv = cursor.fetchone()
        if conv:
            return Decimal(str(conv['prix'])), Decimal(str(conv['part_operateur'])), 'CONVENTION'

    # 3. Tarif médecin STANDARD (payante, sans convention) ?
    #    → S'applique UNIQUEMENT quand aucune convention n'est sélectionnée
    if not id_convention:
        cursor.execute("""
            SELECT prix, part_operateur FROM kt_medecin_tarifs
            WHERE id_doctor = %s AND id_acte = %s
              AND id_convention IS NULL AND est_urgence = 0 AND est_actif = 1
            LIMIT 1
        """, (id_doctor, id_acte))
        tarif = cursor.fetchone()
        if tarif:
            return Decimal(str(tarif['prix'])), Decimal(str(tarif['part_operateur'])), 'MEDECIN_STD'

    # 4. Fallback : prix standard payante de l'acte
    cursor.execute("""
        SELECT prix_payant, honoraires_payant
        FROM kt_actes WHERE id_acte = %s
    """, (id_acte,))
    acte = cursor.fetchone()
    if acte:
        return Decimal(str(acte['prix_payant'])), Decimal(str(acte['honoraires_payant'])), 'PAYANTE'

    return Decimal('0'), Decimal('0'), 'PAYANTE'


def get_conventions_for_acte(cursor, id_acte):
    """
    Retourne la liste des conventions associées à un acte avec leurs prix.

    Returns:
        list of dict: [{'id_convention', 'code_convention', 'nom_convention', 'prix', 'part_operateur'}, ...]
    """
    cursor.execute("""
        SELECT 
            c.id_convention,
            c.code_convention,
            c.nom_convention,
            ac.prix,
            ac.part_operateur
        FROM kt_actes_conventions ac
        JOIN kt_conventions c ON ac.id_convention = c.id_convention
        WHERE ac.id_acte = %s AND ac.est_actif = 1 AND c.est_active = 1
        ORDER BY c.nom_convention
    """, (id_acte,))
    return cursor.fetchall()
