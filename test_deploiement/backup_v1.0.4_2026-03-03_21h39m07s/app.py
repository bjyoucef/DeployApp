import os
from app import app
from waitress import serve

# Créer le dossier d'uploads si nécessaire
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if __name__ == '__main__':
    # app.run(ssl_context=('certificat/certificate.crt', 'certificat/private.key') , host='0.0.0.0', port=8080, debug=True)

    serve(app, host='0.0.0.0', port=8080)  # Pas besoin de ssl_context ici
