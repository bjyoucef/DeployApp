# app/bons_paiement.py - Gestion des bons de paiement patients pour accouchements

import json
from qrcode.main import QRCode
import io
import base64
from datetime import datetime
from decimal import Decimal

from flask import redirect, url_for, g, flash, render_template, request, jsonify, make_response

from app import app, get_db_connection
from app.accouchements.accouchements import recalculer_dossier
from app.error import handle_errors
from app.utils.utiles import login_required


def to_decimal( value, default = 0 ) -> Decimal:
    """Convertit une valeur en Decimal de manière sécurisée"""
    if value is None or value == '':
        return Decimal( str( default ) )
    try:
        return Decimal( str( value ) )
    except:
        return Decimal( str( default ) )


def generer_numero_bon() -> str:
    """Génère un numéro de bon unique"""
    now = datetime.now()
    return f"BON-{now.strftime( '%Y%m%d-%H%M%S' )}"


def generer_qr_code( data: str ) -> str:
    """Génère un QR code en base64"""
    qr = QRCode( version = 1, box_size = 10, border = 4 )
    qr.add_data( data )
    qr.make( fit = True )

    img = qr.make_image( fill_color = "black", back_color = "white" )
    buffer = io.BytesIO()
    img.save( buffer, format = 'PNG' )

    return base64.b64encode( buffer.getvalue() ).decode("utf-8")


# ==============================================================================
# CRÉATION DE BON
# ==============================================================================

@app.route( '/accouchement/<int:id_dossier>/creer-bon-paiement', methods = [ 'GET', 'POST' ] )
@login_required
@handle_errors()

def creer_bon_paiement( id_dossier ):
    """Crée un bon de paiement pour un dossier d'accouchement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Récupérer le dossier
        cursor.execute(
            """
            SELECT d.*,
                   CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name,
                   doc.est_interne                            as gyneco_interne
            FROM accouchement_dossiers d
                     LEFT JOIN doctors doc ON d.id_gyneco = doc.id
            WHERE d.id_dossier = %s
                       """, (id_dossier,)
            )

        dossier = cursor.fetchone()

        if not dossier:
            flash( 'Dossier non trouvé', 'danger' )
            return redirect( url_for( 'accouchement_list' ) )

        if request.method == 'GET':
            # Vérifier si un bon existe déjà
            cursor.execute(
                """
                SELECT *
                FROM accouchement_bons_paiement
                WHERE id_dossier = %s
                  AND statut != 'ANNULE'
                ORDER BY created_at DESC
                LIMIT 1
                           """, (id_dossier,)
                )
            bon_existant = cursor.fetchone()

            # Calculer le montant à payer
            prix_total = to_decimal( dossier[ 'prix_total' ] )
            montant_paye = to_decimal( dossier[ 'montant_paye' ] )
            montant_restant = prix_total - montant_paye

            return render_template(
                    'accouchement/bons/creer_bon.html',
                    dossier = dossier,
                    bon_existant = bon_existant,
                    montant_restant = float( montant_restant ),
                    title = "Créer un bon de paiement"
                    )

        # POST - Création du bon
        type_bon = request.form.get( 'type_bon', 'INITIAL' )
        montant_a_payer = to_decimal( request.form.get( 'montant_a_payer', 0 ) )
        date_echeance = request.form.get( 'date_echeance' ) or None
        description = request.form.get( 'description', '' ).strip()

        if montant_a_payer <= 0:
            flash( 'Le montant doit être supérieur à 0', 'danger' )
            return redirect( url_for( 'creer_bon_paiement', id_dossier = id_dossier ) )

        # Générer numéro unique
        numero_bon = generer_numero_bon()

        # Construire les détails JSON
        details = {
                'prix_base': float( dossier[ 'prix_base' ] or 0 ),
                'prix_produits': float( dossier[ 'prix_produits' ] or 0 ),
                'prix_actes': float( dossier[ 'prix_actes' ] or 0 ),
                'prix_anesthesie': float( dossier[ 'prix_anesthesie' ] or 0 ),
                'prix_nuitees': float( dossier[ 'prix_nuitees' ] or 0 ),
                'prix_explorations': float( dossier[ 'prix_explorations' ] or 0 ),
                'prix_total': float( dossier[ 'prix_total' ] or 0 ),
                'montant_deja_paye': float( dossier[ 'montant_paye' ] or 0 )
                }

        # Données QR Code
        qr_data = json.dumps(
                {
                        'numero_bon': numero_bon,
                        'id_dossier': id_dossier,
                        'montant': float( montant_a_payer ),
                        'patient': dossier[ 'patiente' ]
                        }
                )

        qr_code_b64 = generer_qr_code( qr_data )

        # Insertion
        cursor.execute(
            """
            INSERT INTO accouchement_bons_paiement
            (id_dossier, numero_bon, type_bon, montant_total, montant_a_payer,
             montant_restant, description, details_json, date_emission, date_echeance,
             qr_code_data, emis_par, statut)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'EN_ATTENTE')
                       """, (
                    id_dossier, numero_bon, type_bon,
                    dossier[ 'prix_total' ], montant_a_payer, montant_a_payer,
                    description, json.dumps( details ), datetime.now(), date_echeance,
                    qr_code_b64, g.user[ 'id_personnel' ]
                    )
            )

        id_bon = cursor.lastrowid
        conn.commit()

        flash( f'✅ Bon de paiement {numero_bon} créé avec succès', 'success' )
        return redirect( url_for( 'detail_bon_paiement', id_bon = id_bon ) )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur création bon: {e}' )
        flash( f'Erreur: {str( e )}', 'danger' )
        return redirect( url_for( 'accouchement_detail', id_dossier = id_dossier ) )
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# DÉTAIL BON
# ==============================================================================

@app.route( '/accouchement/bon-paiement/<int:id_bon>' )
@login_required
@handle_errors()

def detail_bon_paiement( id_bon ):
    """Affiche les détails d'un bon de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT b.*,
                   d.patiente,
                   d.date_accouchement,
                   d.type_accouchement,
                   d.type_tarification,
                   d.prix_total,
                   CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name,
                   CONCAT(p.nom, ' ', p.prenom)               as emis_par_nom
            FROM accouchement_bons_paiement b
                     JOIN accouchement_dossiers d ON b.id_dossier = d.id_dossier
                     LEFT JOIN doctors doc ON d.id_gyneco = doc.id
                     LEFT JOIN personnel p ON b.emis_par = p.id_personnel
            WHERE b.id_bon = %s
                       """, (id_bon,)
            )

        bon = cursor.fetchone()

        if not bon:
            flash( 'Bon non trouvé', 'danger' )
            return redirect( url_for( 'accouchement_list' ) )

        # Récupérer les paiements
        cursor.execute(
            """
            SELECT p.*, CONCAT(per.nom, ' ', per.prenom) as encaisse_par_nom
            FROM accouchement_paiements_bons p
                     LEFT JOIN personnel per ON p.encaisse_par = per.id_personnel
            WHERE p.id_bon = %s
            ORDER BY p.date_paiement DESC
                       """, (id_bon,)
            )

        paiements = cursor.fetchall()

        # Parser les détails JSON
        details = json.loads( bon[ 'details_json' ] ) if bon[ 'details_json' ] else { }

        return render_template(
                'accouchement/bons/detail_bon.html',
                bon = bon,
                paiements = paiements,
                details = details,
                title = f"Bon {bon[ 'numero_bon' ]}"
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# ENREGISTRER PAIEMENT
# ==============================================================================

@app.route( '/accouchement/bon-paiement/<int:id_bon>/payer', methods = [ 'POST' ] )
@login_required
@handle_errors()

def payer_bon( id_bon ):
    """Enregistre un paiement sur un bon"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Récupérer le bon
        cursor.execute(
            """
            SELECT b.montant_a_payer, b.montant_paye as bon_montant_paye, 
                   b.montant_restant, b.id_dossier, b.statut
            FROM accouchement_bons_paiement b
            WHERE b.id_bon = %s
                       """, (id_bon,)
            )

        bon = cursor.fetchone()

        if not bon:
            return jsonify( { 'success': False, 'error': 'Bon non trouvé' } ), 404

        if bon[ 'statut' ] == 'ANNULE':
            return jsonify( { 'success': False, 'error': 'Bon annulé' } ), 400

        # Données du formulaire
        montant = to_decimal( request.form.get( 'montant', 0 ) )
        mode_paiement = request.form.get( 'mode_paiement', 'ESPECES' )
        reference = request.form.get( 'reference_transaction', '' )
        numero_cheque = request.form.get( 'numero_cheque', '' )
        banque = request.form.get( 'banque', '' )
        notes = request.form.get( 'notes', '' )

        montant_restant = to_decimal( bon[ 'montant_restant' ] )

        if montant <= 0:
            return jsonify( { 'success': False, 'error': 'Montant invalide' } ), 400

        if montant > montant_restant:
            return jsonify(
                    {
                            'success': False,
                            'error': f'Montant supérieur au reste à payer ({montant_restant} DA)'
                            }
                    ), 400

        # Enregistrer le paiement
        cursor.execute(
            """
            INSERT INTO accouchement_paiements_bons
            (id_bon, montant, mode_paiement, reference_transaction,
             numero_cheque, banque, date_paiement, encaisse_par, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       """, (
                    id_bon, montant, mode_paiement, reference,
                    numero_cheque, banque, datetime.now(),
                    g.user[ 'id_personnel' ], notes
                    )
            )

        # Mettre à jour le bon
        nouveau_paye = to_decimal( bon[ 'bon_montant_paye' ] ) + montant
        nouveau_restant = to_decimal( bon[ 'montant_a_payer' ] ) - nouveau_paye

        nouveau_statut = 'PAYE_COMPLET' if nouveau_restant <= 0 else 'PAYE_PARTIEL'
        date_paiement_complet = datetime.now() if nouveau_statut == 'PAYE_COMPLET' else None

        cursor.execute(
            """
            UPDATE accouchement_bons_paiement
            SET montant_paye          = %s,
                montant_restant       = %s,
                statut                = %s,
                date_paiement_complet = %s,
                encaisse_par          = %s
            WHERE id_bon = %s
                       """, (
                    nouveau_paye, nouveau_restant, nouveau_statut,
                    date_paiement_complet, g.user[ 'id_personnel' ], id_bon
                    )
            )

        # Mettre à jour le dossier d'accouchement
        cursor.execute(
            """
            UPDATE accouchement_dossiers d
            SET d.montant_paye = COALESCE(d.montant_paye, 0) + %s
            WHERE d.id_dossier = %s
                       """, (montant, bon['id_dossier'])
            )


        recalculer_dossier( cursor, bon[ 'id_dossier' ] )

        conn.commit()

        flash( f'✅ Paiement de {float( montant ):.2f} DA enregistré', 'success' )
        return jsonify(
                {
                        'success': True,
                        'message': 'Paiement enregistré',
                        'nouveau_restant': float( nouveau_restant ),
                        'statut': nouveau_statut
                        }
                )

    except Exception as e:
        conn.rollback()
        app.logger.error( f'Erreur paiement: {e}' )
        return jsonify( { 'success': False, 'error': str( e ) } ), 500
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# LISTE DES BONS
# ==============================================================================

@app.route( '/accouchement/bons-paiement' )
@login_required
@handle_errors()

def liste_bons_paiement():
    """Liste de tous les bons de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Filtres
        statut = request.args.get( 'statut', 'all' )
        date_debut = request.args.get( 'date_debut', '' )
        date_fin = request.args.get( 'date_fin', '' )
        q = request.args.get( 'q', '' ).strip()

        where_clauses = [ "1=1" ]
        params = { }

        if statut != 'all':
            where_clauses.append( "b.statut = %(statut)s" )
            params[ 'statut' ] = statut

        if date_debut:
            where_clauses.append( "DATE(b.date_emission) >= %(date_debut)s" )
            params[ 'date_debut' ] = date_debut

        if date_fin:
            where_clauses.append( "DATE(b.date_emission) <= %(date_fin)s" )
            params[ 'date_fin' ] = date_fin

        if q:
            where_clauses.append( "(b.numero_bon LIKE %(q)s OR d.patiente LIKE %(q)s)" )
            params[ 'q' ] = f"%{q}%"

        where_sql = " AND ".join( where_clauses )

        # Requête principale - spécifier explicitement les colonnes pour éviter les ambiguïtés
        cursor.execute(
            f"""
            SELECT b.id_bon, b.numero_bon, b.type_bon, b.id_dossier,
                   b.montant_total, b.montant_a_payer, b.montant_paye, 
                   b.montant_restant, b.description, b.details_json, b.date_emission,
                   b.date_echeance, b.qr_code_data, b.emis_par, b.statut, b.created_at,
                   b.updated_at, b.encaisse_par, b.date_paiement_complet,
                   d.patiente, d.date_accouchement,
                   CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name
            FROM accouchement_bons_paiement b
            JOIN accouchement_dossiers d ON b.id_dossier = d.id_dossier
            LEFT JOIN doctors doc ON d.id_gyneco = doc.id
            WHERE {where_sql}
            ORDER BY b.date_emission DESC
        """, params
            )

        bons = cursor.fetchall()

        # Stats
        cursor.execute(
            f"""
            SELECT 
                COUNT(*) as total,
                COALESCE(SUM(b.montant_a_payer), 0) as total_a_payer,
                COALESCE(SUM(b.montant_paye), 0) as total_paye,
                COALESCE(SUM(b.montant_restant), 0) as total_restant
            FROM accouchement_bons_paiement b
            JOIN accouchement_dossiers d ON b.id_dossier = d.id_dossier
            WHERE {where_sql}
        """, params
            )

        stats = cursor.fetchone()

        return render_template(
                'accouchement/bons/liste_bons.html',
                bons = bons,
                stats = stats,
                filters = { 'statut': statut, 'date_debut': date_debut, 'date_fin': date_fin, 'q': q },
                title = "Bons de paiement"
                )

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# IMPRESSION BON
# ==============================================================================

@app.route( '/accouchement/bon-paiement/<int:id_bon>/imprimer' )
@login_required
@handle_errors()

def imprimer_bon( id_bon ):
    """Génère un PDF du bon de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT b.*,
                   d.patiente,
                   d.date_accouchement,
                   d.type_accouchement,
                   d.type_tarification,
                   CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name,
                   CONCAT(p.nom, ' ', p.prenom)               as emis_par_nom
            FROM accouchement_bons_paiement b
                     JOIN accouchement_dossiers d ON b.id_dossier = d.id_dossier
                     LEFT JOIN doctors doc ON d.id_gyneco = doc.id
                     LEFT JOIN personnel p ON b.emis_par = p.id_personnel
            WHERE b.id_bon = %s
                       """, (id_bon,)
            )

        bon = cursor.fetchone()

        if not bon:
            flash( 'Bon non trouvé', 'danger' )
            return redirect( url_for( 'liste_bons_paiement' ) )

        details = json.loads( bon[ 'details_json' ] ) if bon[ 'details_json' ] else { }

        html = render_template(
                'accouchement/bons/imprimer_bon.html',
                bon = bon,
                details = details,
                date_impression = datetime.now().strftime( '%d/%m/%Y %H:%M' )
                )

        # Si vous avez weasyprint ou pdfkit, générer PDF
        # Sinon retourner HTML pour impression
        response = make_response( html )
        response.headers[ 'Content-Type' ] = 'text/html'

        return response

    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# ANNULER BON
# ==============================================================================

@app.route( '/accouchement/bon-paiement/<int:id_bon>/annuler', methods = [ 'POST' ] )
@login_required
@handle_errors()

def annuler_bon( id_bon ):
    """Annule un bon de paiement"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT *
            FROM accouchement_bons_paiement
            WHERE id_bon = %s
                       """, (id_bon,)
            )

        bon = cursor.fetchone()

        if not bon:
            flash( 'Bon non trouvé', 'danger' )
            return redirect( url_for( 'liste_bons_paiement' ) )

        if bon[ 'statut' ] == 'PAYE_COMPLET':
            flash( 'Impossible d\'annuler un bon déjà payé', 'danger' )
            return redirect( url_for( 'detail_bon_paiement', id_bon = id_bon ) )

        # Annuler
        cursor.execute(
            """
            UPDATE accouchement_bons_paiement
            SET statut = 'ANNULE'
            WHERE id_bon = %s
                       """, (id_bon,)
            )

        conn.commit()

        flash( '✅ Bon annulé', 'success' )
        return redirect( url_for( 'liste_bons_paiement' ) )

    except Exception as e:
        conn.rollback()
        flash( f'Erreur: {str( e )}', 'danger' )
        return redirect( url_for( 'detail_bon_paiement', id_bon = id_bon ) )
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# API
# ==============================================================================

@app.route( '/api/bon-paiement/<numero_bon>' )
@login_required
def api_get_bon_by_numero( numero_bon ):
    """Récupère un bon par son numéro (pour scan QR code)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT b.*, d.patiente
            FROM accouchement_bons_paiement b
                     JOIN accouchement_dossiers d ON b.id_dossier = d.id_dossier
            WHERE b.numero_bon = %s
                       """, (numero_bon,)
            )

        bon = cursor.fetchone()

        if not bon:
            return jsonify( { 'success': False, 'error': 'Bon non trouvé' } ), 404

        return jsonify(
                {
                        'success': True,
                        'bon': {
                                'id_bon': bon[ 'id_bon' ],
                                'numero_bon': bon[ 'numero_bon' ],
                                'patient': bon[ 'patiente' ],
                                'montant_a_payer': float( bon[ 'montant_a_payer' ] ),
                                'montant_paye': float( bon[ 'montant_paye' ] ),
                                'montant_restant': float( bon[ 'montant_restant' ] ),
                                'statut': bon[ 'statut' ]
                                }
                        }
                )

    finally:
        cursor.close()
        conn.close()