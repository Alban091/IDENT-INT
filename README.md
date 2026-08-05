# TSP IDENTINT

Reconnaissance faciale des étudiants de Télécom SudParis et IMT-BS.
Projet pédagogique réalisé dans le cadre d'un cours de Python.

Le principe : on uploade une photo, l'application affiche la liste des étudiants
dont le visage ressemble le plus à celui de la photo, à partir des photos du
trombinoscope interne de l'école.

## Fonctionnalités

- Authentification automatique au trombinoscope via CAS
- Récupération et stockage local des photos et fiches étudiants
- Encodage facial des visages (vecteurs de 128 dimensions, via `face_recognition`)
- Recentrage automatique des visages avant comparaison
- Interface web : upload d'une photo → liste des étudiants ressemblants
- Commande de purge des données d'un étudiant (droit à l'effacement RGPD)

## Prérequis

- Python 3.10+
- `cmake` (nécessaire pour compiler `dlib`, dépendance de `face_recognition`)

```bash
# macOS
brew install cmake

# Linux (Ubuntu/Debian)
sudo apt-get install cmake build-essential
```

## Installation

```bash
git clone https://github.com/Alban091/IDENT-INT.git
cd IDENT-INT

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## Configuration

Copier le fichier d'exemple et renseigner ses valeurs :

```bash
cp .env.example .env
```

Générer une clé secrète Django :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Éditer `.env` :

```
TROMBI_USERNAME=ton_login_tsp
TROMBI_PASSWORD=ton_mot_de_passe
DJANGO_SECRET_KEY='cle-generee-ci-dessus'
DJANGO_DEBUG=True
```

Initialiser la base et créer un compte administrateur :

```bash
python manage.py migrate
python manage.py createsuperuser
```

## Utilisation

Synchroniser le trombinoscope (authentification CAS automatique via `.env`) :

```bash
python manage.py sync_trombi --ecole TSP --annee all
```

Les photos sont téléchargées dans `media/students_photos/` et les visages
encodés automatiquement. Options : `--ecole {TSP,IMT-BS,all}`,
`--annee {fi_1,fi_2,fi_3,bac_1,bac_2,bac_3,all}`, `--no-encode`.

Lancer le serveur :

```bash
python manage.py runserver
```

Puis ouvrir http://127.0.0.1:8000

La synchronisation est aussi accessible depuis l'admin Django
(http://127.0.0.1:8000/admin/) via le bouton « Synchroniser ».

Supprimer toutes les données d'un étudiant :

```bash
python manage.py purge_student --email prenom.nom@telecom-sudparis.eu
```

## Architecture

```
IDENT-INT/
├── recognition/                  Application principale
│   ├── models.py                 Modèle Student (fiche + encodage facial)
│   ├── views.py                  Vues web (accueil, upload, résultats)
│   ├── admin.py                  Admin Django + interface de synchronisation
│   ├── urls.py                   Routes
│   ├── trombi.py                 Scraper du trombinoscope (auth CAS)
│   ├── face_recognition_utils.py Détection, recentrage, encodage, matching
│   ├── tests.py                  Tests unitaires
│   └── management/commands/
│       ├── sync_trombi.py        Synchronisation en ligne de commande
│       └── purge_student.py      Suppression des données d'un étudiant
└── tsp_identint/                 Configuration du projet Django
```

## Tests

```bash
python manage.py test recognition
```

## Limites connues

- Certains étudiants ne sont pas référencés dans le trombinoscope, ou n'y ont pas
  de photo : le trombinoscope renvoie alors une image générique, comptabilisée
  séparément lors de la synchronisation.
- Les alternants ne forment pas une catégorie distincte dans le trombinoscope :
  ils sont répartis dans les années `fi_1` à `fi_3`.
- La synchronisation complète depuis l'interface admin est longue ; la commande
  en ligne de commande est préférable pour les gros volumes (SQLite ne gère pas
  les écritures concurrentes).
- La détection des photos manquantes repose sur la taille du fichier générique
  renvoyé par le trombinoscope, qui pourrait changer.

## Éthique et RGPD

Les photos et encodages faciaux sont des données biométriques sensibles
(article 9 du RGPD). Ce projet est strictement pédagogique : les données
restent locales, ne sont ni publiées ni partagées. Voir la page `/legal/`
du site et la commande `purge_student` pour le droit à l'effacement.

Contact : alban.robert@telecom-sudparis.eu