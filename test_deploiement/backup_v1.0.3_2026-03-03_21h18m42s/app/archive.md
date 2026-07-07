Agis comme un architecte logiciel expert en Python et Flask. Je souhaite développer un systeme d'archivage pour les dossiers médicaux du CIS. Je vais te fournir une mind-map fonctionnelle détaillée qui sert de cahier des charges.

Ta tâche est de :

    Définir la structure des dossiers du projet Flask.

    Écrire le code des sql de base de données  en respectant scrupuleusement les relations et contraintes définies (notamment la segmentation par médecin et le calcul d'épaisseur).

    Lister les dépendances nécessaires (requirements.txt).

Voici les spécifications issues de la mind-map :

Données Physiques :

    Dossiers : 'Simple' (2mm) ou 'Avec Convention' (4mm).

    Boîtes : 'Petite' (9cm) ou 'Grande' (15cm). Attributs : dimensions, capacité dynamique basée sur l'épaisseur cumulée des dossiers.

    Rangement : Étagères avec coordonnées (Colonne, Ligne, Position).

Règles Métier (Crucial) :

    Segmentation stricte : Une boîte appartient à un seul médecin. On ne mélange pas les médecins dans une même boîte.

    Capacité : Elle se calcule par épaisseur_totale_dossiers <= épaisseur_boite.

    Création auto : Si une boîte est pleine pour le Médecin X, le système doit prévoir la création d'une nouvelle boîte.

    Entrée : Un nouveau dossier à archiver (avec son épaisseur et l'ID du médecin).

    Recherche : Trouver la première boîte disponible appartenant spécifiquement à ce médecin qui a encore assez d'espace (épaisseur_boite - épaisseur_actuelle >= épaisseur_dossier).

    Création : Si aucune boîte n'est disponible pour ce médecin, déclencher la création d'une nouvelle boîte (type par défaut : Petite) et lui assigner un emplacement libre dans les rayonnages (première coordonnée vide trouvée par date et services).

    Sortie : Retourner l'ID de la boîte et l'emplacement précis.

Gère les cas d'erreurs (ex: plus de place physique dans les étagères).
créer une vue HTML/CSS (avec un peu de JS) qui affiche un Plan de Localisation Visuel.

Besoins :

    Une grille représentant une étagère (Lignes X Colonnes).

    Chaque cellule de la grille représente un emplacement.

    Si l'emplacement est occupé par une boîte, afficher une couleur (ex: vert) et au survol (tooltip), afficher le nom du médecin et le taux de remplissage (%).

    Si l'emplacement est vide, afficher une couleur grise.

    Intègre un champ de recherche en haut : si je tape un numéro de dossier ou un nom de patient, la boîte correspondante doit clignoter ou être mise en surbrillance dans le schéma.

Propose le code HTML (Jinja2) et le CSS correspondant.

Base-toi sur cette structure pour générer le code complet et l'initialisation de l'app.
# CIS Archivage — Plan de Travail & Architecture

## 1. Types de Dossiers
*Définition des unités physiques de base pour le calcul de capacité.*
- **Dossier Simple**
  - Épaisseur fixe de 2 mm pour les dossiers standards.
- **Dossier Avec Convention**
  - Épaisseur fixe de 4 mm pour les dossiers volumineux ou spécifiques.
- **Attributs Métadonnées**
  - Association des propriétés physiques aux données cliniques (ID patient, type).

## 2. Types de Boîtes & Conteneurs
*Gestion des contenants physiques et de leurs limites.*
- **Petite Boîte**
  - Hauteur standard de 9 cm (valeur par défaut configurable).
- **Grande Boîte**
  - Hauteur standard de 15 cm (valeur par défaut configurable).
- **Configuration des Attributs**
  - Gestion dynamique : nom, dimensions (Lxlxh), épaisseur max supportée.
- **Calcul de Capacité**
  - Algorithme déterminant le nombre de dossiers max selon leurs épaisseurs cumulées.

## 3. Stratégie de Segmentation (Règles Métier)
*Logique stricte de répartition des dossiers dans les boîtes.*
- **Segmentation par Médecin**
  - Règle stricte : une boîte contient uniquement les dossiers d'un seul médecin.
- **Indépendance des Capacités**
  - Le taux de remplissage est calculé isolément pour chaque médecin/boîte.
- **Création Automatique**
  - Génération d'une nouvelle boîte dès que la précédente atteint sa saturation (épaisseur max).
- **Réaffectation Dynamique**
  - Gestion des cas de débordement ou d'espace insuffisant via création de nouveaux contenants.

## 4. Affectation Automatique & Rangement
*Algorithmes de placement et d'organisation dans l'espace.*
- **Critères de Tri**
  - Priorisation par Spécialité, Médecin traitant, puis Ordre chronologique.
- **Algorithme de Placement**
  - Recherche de la première boîte disponible (du médecin concerné) ou empilement par date.
- **Gestion des Étagères**
  - Organisation spatiale par coordonnées : Colonne (X), Ligne (Y), Position (Z).
- **Identifiant d'Emplacement**
  - Nomenclature unique (ex : "Étagère A - Col 2 - Ligne 3").

## 5. Étiquetage & QR Code
*Pont entre le stock physique et la gestion numérique.*
- **Génération QR Unique**
  - Création d'un code unique encodant l'ID de la boîte et son emplacement.
- **Action de Scan**
  - Redirection vers une vue mobile listant le contenu de la boîte scannée.
- **Lien Dossier Digital**
  - Accès direct à la fiche patient numérique depuis la liste du contenu physique.

## 6. Recherche & Consultation
*Expérience utilisateur pour retrouver une archive.*
- **Moteur de Recherche Multicritère**
  - Filtres : Numéro dossier, Nom patient, Spécialité, Médecin, Date archivage.
- **Affichage des Résultats**
  - Indication précise : Nom de la boîte + Coordonnées physiques (Étagère/Col/Ligne).
- **Plan de Localisation Visuel**
  - Schéma graphique interactif montrant l'emplacement de la boîte dans le rayonnage.

## 7. Interface Admin / Configuration
*Outils de gestion pour les super-utilisateurs.*
- **CRUD Configuration**
  - Interfaces pour créer/modifier les types de boîtes, rayonnages et règles.
- **Historique & Logs**
  - Journalisation complète des mouvements (entrées, sorties, déplacements).
- **Export Inventaire**
  - Génération de rapports d'état du stock en format CSV ou PDF.

## 8. Sécurité & Permissions
*Contrôle d'accès et intégrité des données.*
- **Gestion des Rôles (RBAC)**
  - Niveaux : Admin (tout), Archiviste (écriture), Médecin (consultation sienne), Lecture seule.
- **Sauvegarde Métadonnées**
  - Processus de backup/restore pour la base de données des emplacements.
- **Journal d'Accès**
  - Tracabilité des connexions et des consultations de dossiers sensibles.

## 9. Intégration Flask (Architecture Technique)
*Composants logiciels Backend et Frontend.*
- **API Endpoints**
  - Routes REST pour : Création dossier, Recherche, Gen QR, Update emplacement.
- **Web UI : Vue Boîte**
  - Interface affichant la liste des dossiers contenus dans une boîte spécifique.
- **Web UI : Plan d'Étagères**
  - Représentation visuelle (Grille CSS/Canvas) des rayonnages et taux d'occupation.
- **Module Scanner Mobile**
  - Interface web responsive optimisée pour l'utilisation via caméra smartphone/tablette.

## 10. Scalabilité & Maintenance
*Performance et gestion du cycle de vie.*
- **Performance Gros Volumes**
  - Indexation DB et pagination pour gérer un nombre illimité d'archives.
- **Migration de Données**
  - Scripts d'import pour intégrer un inventaire existant (Legacy) vers la nouvelle structure.
- **Maintenance Préventive**
  - Alertes sur les boîtes presque pleines ou les étagères saturées.