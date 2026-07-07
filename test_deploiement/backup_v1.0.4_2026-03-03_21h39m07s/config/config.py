import os
import secrets


class Config:
    SECRET_KEY = secrets.token_hex(16)
    DB_HOST = os.getenv('DB_HOST', '192.168.10.9')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '@Dmin1548@')
    DB_NAME = os.getenv('DB_NAME', 'bsmartdb')

    # Configuration des uploads
    UPLOAD_FOLDER = 'app/uploads/'




