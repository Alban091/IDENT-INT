"""
Commande Django pour scraper le trombinoscope TSP
=================================================

INSTALLATION:
-------------
1. Crée les dossiers dans ton projet:
   recognition/
   └── management/
       └── commands/
           └── scrape_trombi.py  ← ce fichier

2. Crée un fichier __init__.py vide dans chaque dossier:
   recognition/management/__init__.py
   recognition/management/commands/__init__.py

USAGE:
------
python manage.py scrape_trombi --cookie "TON_PHPSESSID_ICI"

OPTIONS:
--------
--cookie     : Cookie PHPSESSID (obligatoire)
--ecole      : "TSP" ou "IMT-BS" (défaut: TSP)
--annee      : "fi_1", "fi_2", "fi_3", etc. (défaut: toutes)
--dry-run    : Affiche ce qui serait fait sans modifier la BDD
--alphabet   : Scrape par ordre alphabétique (si limites de résultats)
"""

import os
import re
import time
import requests
from io import BytesIO
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from recognition.models import Student

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


class Command(BaseCommand):
    help = 'Scrape le trombinoscope TSP et importe les étudiants dans la base de données'

    # Configuration
    BASE_URL = "https://trombi.imtbs-tsp.eu"
    ETUDIANTS_URL = "https://trombi.imtbs-tsp.eu/etudiants.php"
    PHOTO_URL = "https://trombi.imtbs-tsp.eu/photo.php"
    REQUEST_DELAY = 0.3

    def add_arguments(self, parser):
        parser.add_argument(
            '--cookie',
            type=str,
            required=True,
            help='Cookie PHPSESSID de ta session connectée'
        )
        parser.add_argument(
            '--ecole',
            type=str,
            default='TSP',
            choices=['TSP', 'IMT-BS', 'all'],
            help='École à scraper (défaut: TSP)'
        )
        parser.add_argument(
            '--annee',
            type=str,
            default='all',
            help='Année à scraper: fi_1, fi_2, fi_3, bac_1, etc. (défaut: all)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les étudiants sans les importer'
        )
        parser.add_argument(
            '--alphabet',
            action='store_true',
            help='Scrape par ordre alphabétique (contourne les limites)'
        )
        parser.add_argument(
            '--skip-photos',
            action='store_true',
            help='Importe seulement les métadonnées, pas les photos'
        )

    def handle(self, *args, **options):
        # Vérifier BeautifulSoup
        if BeautifulSoup is None:
            raise CommandError(
                "BeautifulSoup n'est pas installé. "
                "Lance: pip install beautifulsoup4"
            )

        self.cookie = options['cookie']
        self.dry_run = options['dry_run']
        self.skip_photos = options['skip_photos']

        # Créer la session
        self.session = requests.Session()
        self.session.cookies.set('PHPSESSID', self.cookie, domain='trombi.imtbs-tsp.eu')
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9',
            'Referer': self.ETUDIANTS_URL,
        })

        # Test de connexion
        self.stdout.write("🔐 Test de connexion...")
        if not self._test_connection():
            raise CommandError("Connexion échouée. Vérifie ton cookie PHPSESSID.")
        self.stdout.write(self.style.SUCCESS("✅ Connecté!"))

        # Définir les écoles et années
        if options['ecole'] == 'all':
            ecoles = ['TSP', 'IMT-BS']
        else:
            ecoles = [options['ecole']]

        if options['annee'] == 'all':
            annees = ['fi_1', 'fi_2', 'fi_3', 'bac_1', 'bac_2', 'bac_3']
        else:
            annees = [options['annee']]

        # Scraper
        if options['alphabet']:
            students_data = self._scrape_alphabet(ecoles[0])
        else:
            students_data = self._scrape_by_criteria(ecoles, annees)

        self.stdout.write(f"\n📊 {len(students_data)} étudiants trouvés")

        if self.dry_run:
            self.stdout.write(self.style.WARNING("\n🔍 MODE DRY-RUN - Aucune modification"))
            for s in students_data[:10]:
                self.stdout.write(f"   - {s['nom']} ({s['email']})")
            if len(students_data) > 10:
                self.stdout.write(f"   ... et {len(students_data) - 10} autres")
            return

        # Importer dans Django
        self._import_students(students_data)

    def _test_connection(self):
        """Teste si le cookie est valide"""
        try:
            response = self.session.get(self.ETUDIANTS_URL, timeout=10)
            # Si "Connexion" apparaît, on n'est pas connecté
            if 'Connexion</span></a>' in response.text and '?login' in response.text:
                return False
            return True
        except Exception as e:
            self.stderr.write(f"Erreur: {e}")
            return False

    def _search(self, ecole='', annee='', nom=''):
        """Effectue une recherche sur le trombinoscope"""
        students = []

        data = {
            'etu[user]': nom,
            'etu[ecole]': ecole,
            'etu[annee]': annee,
        }

        try:
            response = self.session.post(self.ETUDIANTS_URL, data=data, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Parser les fiches
            fiches = soup.find_all('div', class_='ldapFiche')

            for fiche in fiches:
                student = self._parse_fiche(fiche, ecole)
                if student:
                    students.append(student)

        except Exception as e:
            self.stderr.write(f"Erreur recherche: {e}")

        return students

    def _parse_fiche(self, fiche, ecole_default='TSP'):
        """Parse une fiche HTML étudiant"""
        try:
            # École depuis les classes CSS
            classes = fiche.get('class', [])
            ecole = 'TSP' if 'TSP' in classes else 'IMT-BS' if 'IMT-BS' in classes else ecole_default

            # UID depuis l'URL de la photo
            photo_img = fiche.find('img')
            uid = None
            photo_url = None

            if photo_img and photo_img.get('src'):
                match = re.search(r'uid=([^&]+)', photo_img['src'])
                if match:
                    uid = match.group(1)
                    photo_url = f"{self.PHOTO_URL}?uid={uid}&h=320&w=240"

            if not uid:
                return None

            # Nom complet
            nom_div = fiche.find('div', class_='ldapNom')
            nom_complet = nom_div.text.strip() if nom_div else ""

            # Séparer prénom / nom de famille
            parts = nom_complet.split()
            prenom, nom_famille = "", ""

            for i, part in enumerate(parts):
                if part.isupper():
                    prenom = " ".join(parts[:i])
                    nom_famille = " ".join(parts[i:])
                    break

            if not nom_famille and parts:
                prenom = parts[0]
                nom_famille = " ".join(parts[1:]) if len(parts) > 1 else ""

            # Email
            email = ""
            email_link = fiche.find('a', href=re.compile(r'^mailto:'))
            if email_link:
                email = email_link['href'].replace('mailto:', '')

            return {
                'uid': uid,
                'nom': nom_complet,
                'prenom': prenom,
                'nom_famille': nom_famille,
                'email': email,
                'ecole': ecole,
                'photo_url': photo_url,
            }

        except Exception as e:
            return None

    def _scrape_by_criteria(self, ecoles, annees):
        """Scrape par école et année"""
        all_students = []
        seen_uids = set()

        for ecole in ecoles:
            for annee in annees:
                self.stdout.write(f"📚 {ecole} - {annee}...")

                students = self._search(ecole=ecole, annee=annee)

                for s in students:
                    if s['uid'] not in seen_uids:
                        seen_uids.add(s['uid'])
                        s['annee'] = annee
                        all_students.append(s)

                self.stdout.write(f"   → {len(students)} trouvés")
                time.sleep(self.REQUEST_DELAY)

        return all_students

    def _scrape_alphabet(self, ecole):
        """Scrape lettre par lettre"""
        all_students = []
        seen_uids = set()

        for letter in "abcdefghijklmnopqrstuvwxyz":
            self.stdout.write(f"🔤 Lettre '{letter.upper()}'...", ending=" ")

            students = self._search(ecole=ecole, nom=letter)
            count = 0

            for s in students:
                if s['uid'] not in seen_uids:
                    seen_uids.add(s['uid'])
                    all_students.append(s)
                    count += 1

            self.stdout.write(f"{count} nouveaux")
            time.sleep(self.REQUEST_DELAY)

        return all_students

    def _import_students(self, students_data):
        """Importe les étudiants dans Django"""
        self.stdout.write("\n📥 Import dans la base de données...")

        created = 0
        updated = 0
        errors = 0

        for i, data in enumerate(students_data, 1):
            self.stdout.write(f"   [{i}/{len(students_data)}] {data['nom']}...", ending=" ")

            try:
                # Chercher ou créer l'étudiant
                student, was_created = Student.objects.update_or_create(
                    email=data['email'],
                    defaults={
                        'first_name': data['prenom'],
                        'last_name': data['nom_famille'],
                        'school': data['ecole'],
                        'year': data.get('annee', ''),
                        'photo_url': data['photo_url'],
                    }
                )

                # Télécharger la photo si demandé
                if not self.skip_photos and data['photo_url'] and not student.photo:
                    if self._download_photo(student, data['photo_url']):
                        student.save()

                if was_created:
                    created += 1
                    self.stdout.write(self.style.SUCCESS("✅ créé"))
                else:
                    updated += 1
                    self.stdout.write("🔄 mis à jour")

            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"❌ {e}"))

            time.sleep(0.1)

        # Résumé
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"✅ Créés: {created}"))
        self.stdout.write(f"🔄 Mis à jour: {updated}")
        if errors:
            self.stdout.write(self.style.ERROR(f"❌ Erreurs: {errors}"))

    def _download_photo(self, student, photo_url):
        """Télécharge et attache la photo à l'étudiant"""
        try:
            response = self.session.get(photo_url, timeout=15)

            if response.status_code == 200 and len(response.content) > 100:
                # Nom de fichier
                filename = f"{student.email.split('@')[0]}.jpg"

                # Sauvegarder via le champ ImageField
                student.photo.save(
                    filename,
                    ContentFile(response.content),
                    save=False
                )
                return True

        except Exception as e:
            self.stderr.write(f"Photo error: {e}")

        return False