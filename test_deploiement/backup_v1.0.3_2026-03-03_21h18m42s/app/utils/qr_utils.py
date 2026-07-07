"""
Utilitaires QR Code pour les dossiers.
Fournit les fonctions de génération UUID et QR Code base64
utilisées par tous les modules (accouchement, bloc, kt, internes).
"""

import uuid
import qrcode
from io import BytesIO
import base64
from flask import current_app
import hashlib
import urllib.parse
import json
from datetime import datetime
from qrcode.main import QRCode

def generer_uuid_dossier():
    """Génère un UUID v4 permanent pour un dossier."""
    return str(uuid.uuid4())


def generer_qr_base64(source_module, qr_uuid):
    """
    Génère l'image QR Code en base64 pour inclusion dans un PDF ou une étiquette.

    Args:
        source_module: 'MATERNITE', 'BLOC_EXTERNE', 'PRESTATION KT', ou 'BLOC_INTERNE'
        qr_uuid: UUID permanent du dossier

    Returns:
        str: Image PNG encodée en base64
    """
    base_url = current_app.config.get('BASE_URL', 'http://localhost:8080')

    # URL-safe module name (espaces → underscores pour l'URL)
    module_url = source_module.replace(' ', '_')
    url = f"{base_url}/dossier/scan/{module_url}/{qr_uuid}"
    qr = QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=2,
    )

    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#000000", back_color="white")
    buf = BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


# Mapping des modules source vers leurs métadonnées de table
# (table, pk_col, patient_col, date_col, doctor_col)
MODULE_TABLE_MAP = {
    'MATERNITE': (
        'accouchement_dossiers',
        'id_dossier',
        'patiente',
        'date_accouchement',
        'id_gyneco'
    ),
    'BLOC_EXTERNE': (
        'location_bloc_dossier_patient',
        'id_dossier',
        'patient',
        'location_date',
        'id_doctor'
    ),
    'PRESTATION_KT': (
        'kt_dossier_patient',
        'id_dossier',
        'patient',
        'acte_date',
        'id_doctor'
    ),
    'BLOC_INTERNE': (
        'medecin_interne_actes',
        'id_acte',
        'patient',
        'date_acte',
        'id_doctor'
    ),
}

# Mapping source_module DB value → module URL key
# Les valeurs en DB contiennent des espaces ('PRESTATION KT')
# mais les URLs utilisent des underscores ('PRESTATION_KT')
SOURCE_MODULE_TO_URL = {
    'MATERNITE': 'MATERNITE',
    'BLOC_EXTERNE': 'BLOC_EXTERNE',
    'PRESTATION KT': 'PRESTATION_KT',
    'BLOC_INTERNE': 'BLOC_INTERNE',
}

URL_TO_SOURCE_MODULE = {v: k for k, v in SOURCE_MODULE_TO_URL.items()}


# Labels humains pour chaque module
MODULE_LABELS = {
    'MATERNITE': 'Maternité',
    'BLOC_EXTERNE': 'Bloc Opératoire',
    'PRESTATION_KT': 'Cathétérisme (KT)',
    'BLOC_INTERNE': 'Médecin Interne',
}
