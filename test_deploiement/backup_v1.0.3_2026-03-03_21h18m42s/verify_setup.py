#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_setup.py

Script de vérification pour s'assurer que tout est configuré correctement.
Exécutez ce script AVANT de mettre en production.

Usage:
    python verify_setup.py
"""

import os
import sys
import json
from datetime import datetime

# ANSI colors for terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

class Verifier:
    def __init__(self):
        self.checks = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def check_file_exists(self, path, description):
        """Vérifier qu'un fichier existe"""
        exists = os.path.exists(path)
        status = "✓" if exists else "✗"
        color = GREEN if exists else RED
        self.checks.append((status, color, description, path))
        if exists:
            self.passed += 1
        else:
            self.failed += 1

    def check_file_contains(self, path, content_search, description):
        """Vérifier qu'un fichier contient une chaîne"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                found = content_search in content
                status = "✓" if found else "✗"
                color = GREEN if found else RED
                self.checks.append((status, color, description, path))
                if found:
                    self.passed += 1
                else:
                    self.failed += 1
        except Exception as e:
            self.checks.append(("⚠", YELLOW, f"{description} (Erreur: {str(e)})", path))
            self.warnings += 1

    def check_directory_exists(self, path, description):
        """Vérifier qu'un répertoire existe"""
        exists = os.path.isdir(path)
        status = "✓" if exists else "⚠"
        color = GREEN if exists else YELLOW
        self.checks.append((status, color, description, path))
        if exists:
            self.passed += 1
        else:
            self.warnings += 1

    def print_results(self):
        """Afficher les résultats"""
        print("\n" + "="*80)
        print(f"{CYAN}VÉRIFICATION DU SYSTÈME - Génération de Documents d'Accouchement{RESET}")
        print("="*80 + "\n")

        for status, color, desc, path in self.checks:
            print(f"{color}{status}{RESET} {desc}")
            print(f"  📍 {path}\n")

        print("="*80)
        print(f"{GREEN}✓ Réussis : {self.passed}{RESET}")
        print(f"{RED}✗ Échoués : {self.failed}{RESET}")
        print(f"{YELLOW}⚠ Avertissements : {self.warnings}{RESET}")
        print("="*80 + "\n")

        if self.failed == 0 and self.warnings <= 1:
            print(f"{GREEN}✅ SYSTÈME PRÊT POUR LA PRODUCTION !{RESET}\n")
            return True
        elif self.failed == 0:
            print(f"{YELLOW}⚠️  SYSTÈME OPÉRATIONNEL AVEC AVERTISSEMENTS{RESET}\n")
            return True
        else:
            print(f"{RED}❌ PROBLÈMES DÉTECTÉS - Voir les détails ci-dessus{RESET}\n")
            return False


def main():
    v = Verifier()

    print(f"\n{CYAN}Scan du répertoire projet...{RESET}\n")

    base_path = os.path.dirname(os.path.abspath(__file__))

    # ========================================================================
    # 1. Vérifier les fichiers Python modifiés/créés
    # ========================================================================
    print(f"{CYAN}[1] Fichiers Python{RESET}")

    v.check_file_exists(
        os.path.join(base_path, 'app/accouchements/accouchements_documents.py'),
        "Module des générateurs de documents"
    )

    v.check_file_exists(
        os.path.join(base_path, 'app/accouchements/accouchements.py'),
        "Module principal des accouchements"
    )

    # Vérifier que les imports sont présents
    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements.py'),
        "generer_tous_documents_accouchement",
        "Import de la fonction de génération"
    )

    # Vérifier les nouvelles routes
    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements.py'),
        "/generer-documents",
        "Route POST pour générer les documents"
    )

    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements.py'),
        "/telecharger-documents",
        "Route GET pour télécharger les documents"
    )

    # ========================================================================
    # 2. Vérifier les fichiers de documentation
    # ========================================================================
    print(f"\n{CYAN}[2] Documentation{RESET}")

    v.check_file_exists(
        os.path.join(base_path, 'migrations_accouchements_documents.sql'),
        "Fichier de migration SQL"
    )

    v.check_file_exists(
        os.path.join(base_path, 'GUIDE_IMPLEMENTATION_DOCUMENTS.md'),
        "Guide d'implémentation"
    )

    v.check_file_exists(
        os.path.join(base_path, 'template_snippet_documents.html'),
        "Snippet HTML pour le template"
    )

    v.check_file_exists(
        os.path.join(base_path, 'RESUME_FINAL.md'),
        "Résumé final du projet"
    )

    v.check_file_exists(
        os.path.join(base_path, 'tests_documents.py'),
        "Tests unitaires"
    )

    # ========================================================================
    # 3. Vérifier les répertoires
    # ========================================================================
    print(f"\n{CYAN}[3] Répertoires{RESET}")

    v.check_directory_exists(
        os.path.join(base_path, 'app/accouchements'),
        "Répertoire des accouchements"
    )

    v.check_directory_exists(
        os.path.join(base_path, 'app/templates/accouchement'),
        "Répertoire des templates accouchement"
    )

    v.check_directory_exists(
        os.path.join(base_path, 'app/static/documents'),
        "Répertoire des documents statiques"
    )

    # ========================================================================
    # 4. Vérifier les fonctions essentielles
    # ========================================================================
    print(f"\n{CYAN}[4] Fonctions essentielles{RESET}")

    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements_documents.py'),
        "def generer_certificat_accouchement",
        "Fonction : generer_certificat_accouchement"
    )

    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements_documents.py'),
        "def generer_conge_maternite",
        "Fonction : generer_conge_maternite"
    )

    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements_documents.py'),
        "def generer_compte_rendu_post_partum",
        "Fonction : generer_compte_rendu_post_partum"
    )

    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements_documents.py'),
        "def generer_compte_rendu_operatoire",
        "Fonction : generer_compte_rendu_operatoire"
    )

    v.check_file_contains(
        os.path.join(base_path, 'app/accouchements/accouchements_documents.py'),
        "def sauvegarder_document",
        "Fonction : sauvegarder_document"
    )

    # ========================================================================
    # 5. Vérifier les dépendances Python
    # ========================================================================
    print(f"\n{CYAN}[5] Dépendances Python{RESET}")

    try:
        import flask
        v.checks.append(("✓", GREEN, "Flask", "Module Flask"))
        v.passed += 1
    except ImportError:
        v.checks.append(("✗", RED, "Flask", "Module Flask"))
        v.failed += 1

    try:
        import reportlab
        v.checks.append(("✓", GREEN, "ReportLab", "Module ReportLab"))
        v.passed += 1
    except ImportError:
        v.checks.append(("✗", RED, "ReportLab", "Module ReportLab"))
        v.failed += 1

    try:
        import mysql.connector
        v.checks.append(("✓", GREEN, "MySQL Connector", "Module MySQL"))
        v.passed += 1
    except ImportError:
        v.checks.append(("⚠", YELLOW, "MySQL Connector", "Module MySQL (PyMySQL peut être utilisé)"))
        v.warnings += 1

    # ========================================================================
    # Afficher les résultats
    # ========================================================================
    success = v.print_results()

    # ========================================================================
    # Afficher les étapes suivantes
    # ========================================================================
    if success:
        print(f"{CYAN}ÉTAPES SUIVANTES :{RESET}\n")
        print("1. Exécuter la migration SQL:")
        print("   mysql -u user -p database < migrations_accouchements_documents.sql\n")
        print("2. Lire le guide d'implémentation:")
        print("   cat GUIDE_IMPLEMENTATION_DOCUMENTS.md\n")
        print("3. Ajouter le snippet au template detail.html:")
        print("   cat template_snippet_documents.html\n")
        print("4. Exécuter les tests:")
        print("   python -m pytest tests_documents.py -v\n")
        print("5. Vérifier les permissions utilisateurs\n")
    else:
        print(f"{RED}Veuillez corriger les problèmes ci-dessus avant de continuer.{RESET}\n")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
