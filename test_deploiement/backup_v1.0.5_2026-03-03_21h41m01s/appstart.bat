cd /d "C:\inaya.clinique"
waitress-serve --threads=4 --listen=0.0.0.0:8080 --max-request-body-size=52428800 app:app > waitress.log 2>&1