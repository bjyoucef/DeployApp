"""
Script de test pour la génération des documents d'accouchement
Permet de tester la génération sans passer par l'interface web

Usage:
    python test_generation_docs.py <id_dossier>
"""

import sys
import os


# Ajouter le répertoire parent au path
sys.path.insert( 0, os.path.dirname( os.path.dirname( os.path.abspath( __file__ ) ) ) )

from app import get_db_connection
from app.accouchements.accouchements_documents import generer_tous_documents_accouchement


def test_generation( id_dossier ):
    """Teste la génération de documents pour un dossier"""

    print( f"\n{'=' * 60}" )
    print( f"TEST DE GÉNÉRATION - DOSSIER #{id_dossier}" )
    print( f"{'=' * 60}\n" )

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Vérifier que le dossier existe
        cursor.execute(
            """
            SELECT d.*,
                   CONCAT(doc.first_name, ' ', doc.last_name) as gyneco_name
            FROM accouchement_dossiers d
                     LEFT JOIN doctors doc ON d.id_gyneco = doc.id
            WHERE d.id_dossier = %s
                       """, (id_dossier,)
            )

        dossier = cursor.fetchone()

        if not dossier:
            print( f"❌ ERREUR: Dossier #{id_dossier} non trouvé\n" )
            return False

        # Afficher les informations du dossier
        print( f"✓ Dossier trouvé:" )
        print( f"  - Patiente: {dossier[ 'patiente' ]}" )
        print( f"  - Gynécologue: {dossier[ 'gyneco_name' ]}" )
        print( f"  - Date: {dossier[ 'date_accouchement' ]}" )
        print( f"  - Type: {dossier[ 'type_accouchement' ]}" )
        print( f"  - Tarification: {dossier[ 'type_tarification' ]}" )
        print()

        # Tester la génération
        print( "🔄 Génération des documents en cours...\n" )

        try:
            generer_tous_documents_accouchement( cursor, id_dossier )
            print( "✅ Génération réussie !\n" )

            # Vérifier les documents créés
            cursor.execute(
                """
                SELECT type_document, fichier_path, date_generation
                FROM accouchement_documents_generes
                WHERE id_dossier = %s
                ORDER BY date_generation DESC
                           """, (id_dossier,)
                )

            documents = cursor.fetchall()

            if documents:
                print( f"📄 Documents générés ({len( documents )}):" )
                for doc in documents:
                    doc_type = doc[ 'type_document' ]
                    filepath = doc[ 'fichier_path' ]
                    exists = "✓" if os.path.exists( filepath ) else "✗"

                    # Taille du fichier
                    if os.path.exists( filepath ):
                        size_kb = os.path.getsize( filepath ) / 1024
                        size_str = f"{size_kb:.1f} KB"
                    else:
                        size_str = "N/A"

                    print( f"  {exists} {doc_type}" )
                    print( f"     Fichier: {os.path.basename( filepath )}" )
                    print( f"     Taille: {size_str}" )
                    print()

                conn.commit()
                return True
            else:
                print( "⚠️  Aucun document trouvé en base de données\n" )
                return False

        except Exception as e:
            print( f"❌ ERREUR lors de la génération:" )
            print( f"   {str( e )}\n" )

            import traceback

            print( "Traceback complet:" )
            print( traceback.format_exc() )

            conn.rollback()
            return False

    finally:
        cursor.close()
        conn.close()


def main():
    """Point d'entrée du script"""

    if len( sys.argv ) < 2:
        print( "\n❌ Usage: python test_generation_docs.py <id_dossier>" )
        print( "\nExemple: python test_generation_docs.py 42\n" )
        sys.exit( 1 )

    try:
        id_dossier = int( sys.argv[ 1 ] )
    except ValueError:
        print( f"\n❌ ERREUR: '{sys.argv[ 1 ]}' n'est pas un ID valide\n" )
        sys.exit( 1 )

    success = test_generation( id_dossier )

    if success:
        print( "=" * 60 )
        print( "✅ TEST RÉUSSI" )
        print( "=" * 60 + "\n" )
        sys.exit( 0 )
    else:
        print( "=" * 60 )
        print( "❌ TEST ÉCHOUÉ" )
        print( "=" * 60 + "\n" )
        sys.exit( 1 )


if __name__ == "__main__":
    main()