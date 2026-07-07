import os
import secrets
from typing import List
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class Config:
    SECRET_KEY = secrets.token_hex( 32 )
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    # # IDs Telegram autorisés (séparés par virgule)
    # TELEGRAM_ALLOWED_USERS: List[int] = [
    #     int(user_id.strip())
    #     for user_id in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    #     if user_id.strip()
    #         ]

    # ======================
    # MariaDB (APP PRINCIPALE)
    # ======================
    DB_HOST = os.getenv('DB_HOST')
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_NAME = os.getenv('DB_NAME')
    DB_PORT = int(os.getenv('DB_PORT'))

    # ======================
    # PostgreSQL HIS (LECTURE SEULE)
    # ======================
    PG_HOST = os.getenv('PG_HOST')
    PG_DB = os.getenv('PG_DB')
    PG_PORT = int(os.getenv('PG_PORT'))
    PG_USER = os.getenv('PG_USER')
    PG_PASSWORD = os.getenv('PG_PASSWORD')

    # Force PostgreSQL READ-ONLY
    PG_OPTIONS = "-c default_transaction_read_only=on"

    # ======================
    # Uploads
    # ======================
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'app/uploads/')

    @classmethod
    def validate(cls):
        """Valide que toutes les variables obligatoires sont définies"""
        required = {
            'TELEGRAM_BOT_TOKEN': cls.TELEGRAM_BOT_TOKEN,
            'DB_PASSWORD': cls.DB_PASSWORD,
            'PG_PASSWORD': cls.PG_PASSWORD,
        }

        missing = [key for key, value in required.items() if not value]

        if missing:
            raise ValueError(
                f"❌ Variables d'environnement manquantes: {', '.join(missing)}\n"
                f"Veuillez les définir dans le fichier .env"
            )