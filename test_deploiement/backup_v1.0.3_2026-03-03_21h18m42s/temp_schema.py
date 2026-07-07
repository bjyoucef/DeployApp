from app import get_db_connection

conn = get_db_connection()
c = conn.cursor()

tables = [
    'location_bloc_dossier_patient',
    'accouchement_dossiers',
    'kt_dossier_patient',
    'medecin_interne_actes',
    'medecin_interne_anesthesie',
    'location_bloc_dossier_anesthesie',
    'kt_dossier_anesthesie',
    'accouchement_dossier_anesthesie',
]

for t in tables:
    c.execute(f"SHOW COLUMNS FROM {t}")
    cols = [r['Field'] for r in c.fetchall()]
    cancel_cols = [col for col in cols if 'annul' in col.lower() or 'statut' in col.lower() or 'cancel' in col.lower()]
    print(f"{t}: {cancel_cols}")

conn.close()
