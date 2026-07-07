import sys
sys.path.append('c:\\Users\\badja\\SynologyDrive\\Coding\\CODDING\\web server\\11 2025')
from app import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT statut_financier, COUNT(*) as cnt FROM accouchement_dossiers GROUP BY statut_financier")
rows = cursor.fetchall()
for row in rows:
    print(dict(row))
conn.close()
