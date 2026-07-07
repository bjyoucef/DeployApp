
import io
import base64
import datetime
from barcode import Code128
from barcode.writer import ImageWriter

def format_date_gs1(date_str):
    """
    Convertit une date YYYY-MM-DD en format GS1 (YYMMDD).
    Args:
        date_str (str): Date au format 'YYYY-MM-DD'
    Returns:
        str: Date au format 'YYMMDD' ou '000000' si invalide.
    """
    try:
        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%y%m%d')
    except (ValueError, TypeError):
        return "000000"

def generate_gs1_string(gtin, exp_date, lot, sn):
    """
    Génère la chaîne de données brute pour un barcode GS1-128.
    Format standard: (01)GTIN(17)EXP(10)LOT(21)SN
    
    Args:
        gtin (str): Global Trade Item Number (14 chiffres)
        exp_date (str): Date d'expiration (YYMMDD)
        lot (str): Numéro de lot (alphanurérique, longueur variable)
        sn (str): Numéro de série (alphanurérique, longueur variable)
        
    Returns:
        str: Chaîne de données formatée.
    """
    # Note: python-barcode gère automatiquement le caractère de start/stop et le checksum.
    # Les parenthèses (01), (17) sont des Application Identifiers (AI) pour l'affichage humain ("Human Readable").
    # Pour l'encodage technique Code128, ces parenthèses sont souvent utilisées telles quelles par les librairies simplifiées,
    # ou mappées au caractère FNC1. 
    # Avec python-barcode Code128, passer les parenthèses dans la string encode les caractères '(' et ')',
    # ce qui est une pratique courante pour simuler du GS1 visuellement compatible 
    # (bien que techniquement du Code 128 standard).
    
    return f"(01){gtin}(17){exp_date}(10){lot}" + (f"(21){sn}" if sn else "")

def generate_barcode_base64(data):
    """
    Génère un code-barres Code 128 et retourne l'image en encodage base64.
    
    Args:
        data (str): La chaîne de caractères à encoder.
    
    Returns:
        str: Chaîne base64 de l'image du code-barres.
    """
    rv = io.BytesIO()
    
    # Options de configuration pour l'image
    options = {
        "write_text": False,   # On gère le texte nous-mêmes en HTML
        "module_height": 15.0, # Hauteur des barres augmentée
        "module_width": 0.4,   # Largeur des barres (densité) légèrement augmentée
        "quiet_zone": 1.0,     # Marge blanche obligatoire
        "font_size": 0,        # Pas de texte
        "text_distance": 0,
    }
    
    Code128(data, writer=ImageWriter()).write(rv, options=options)
    
    rv.seek(0)
    img_str = base64.b64encode(rv.read()).decode('utf-8')
    
    return img_str
