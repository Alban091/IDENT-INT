"""
Commande Django pour synchroniser le trombinoscope TSP
======================================================
S'authentifie automatiquement avec ton login/mot de passe TSP.

USAGE:
------
python manage.py sync_trombi --username ton_login --password ton_mdp

OPTIONS:
--------
--username   : Ton login TSP (ex: arobert)
--password   : Ton mot de passe TSP
--ecole      : TSP ou IMT-BS (défaut: TSP)
--annee      : fi_1, fi_2, fi_3, etc. (défaut: toutes)
--no-encode  : Ne pas encoder les visages
"""

import os
import re
import time
import requests
from urllib.parse import urljoin, urlparse, parse_qs

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from recognition.models import Student

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


class Command(BaseCommand):
    help = 'Synchronise le trombinoscope TSP avec authentification automatique'

    BASE_URL = "https://trombi.imtbs-tsp.eu"
    LOGIN_URL = "https://trombi.imtbs-tsp.eu/etudiants.php?login"
    ETUDIANTS_URL = "https://trombi.imtbs-tsp.eu/etudiants.php"
    PHOTO_URL = "https://trombi.imtbs-tsp.eu/photo.php"

    # URL CAS de l'IMT
    CAS_URL = "https://cas.imt-bs-tsp.eu/cas/login"

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, required=True, help='Login TSP')
        parser.add_argument('--password', type=str, required=True, help='Mot de passe TSP')
        parser.add_argument('--ecole', type=str, default='TSP', choices=['TSP', 'IMT-BS', 'all'])
        parser.add_argument('--annee', type=str, default='all', help='fi_1, fi_2, fi_3, bac_1, etc.')
        parser.add_argument('--no-encode', action='store_true', help='Ne pas encoder les visages')

    def handle(self, *args, **options):
        if BeautifulSoup is None:
            raise CommandError("Installe BeautifulSoup: pip install beautifulsoup4")

        username = options['username']
        password = options['password']

        # Créer une session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        })

        # S'authentifier
        self.stdout.write("🔐 Connexion en cours...")
        if not self.authenticate(username, password):
            raise CommandError("❌ Échec de l'authentification. Vérifie ton login/mot de passe.")
        self.stdout.write(self.style.SUCCESS("✅ Connecté !"))

        # Définir les années
        if options['annee'] == 'all':
            annees = ['fi_1', 'fi_2', 'fi_3']
        else:
            annees = [options['annee']]

        # Définir les écoles
        if options['ecole'] == 'all':
            ecoles = ['TSP', 'IMT-BS']
        else:
            ecoles = [options['ecole']]

        # Importer l'encodeur
        can_encode = not options['no_encode']
        if can_encode:
            try:
                from recognition.face_recognition_utils import encode_student_faces
                self.encode_func = encode_student_faces
            except ImportError:
                self.stdout.write(self.style.WARNING("⚠️ face_recognition non disponible, encodage désactivé"))
                can_encode = False

        # Scraper
        all_students = []
        seen_uids = set()

        for ecole in ecoles:
            for annee in annees:
                self.stdout.write(f"📚 {ecole} - {annee}...")
                students = self.search_students(ecole, annee)

                for s in students:
                    if s['uid'] not in seen_uids:
                        seen_uids.add(s['uid'])
                        s['annee'] = annee
                        all_students.append(s)

                self.stdout.write(f"   → {len(students)} trouvés")
                time.sleep(0.3)

        self.stdout.write(f"\n📊 Total: {len(all_students)} étudiants")

        # Importer
        created = 0
        updated = 0
        encoded = 0

        for i, data in enumerate(all_students, 1):
            self.stdout.write(f"[{i}/{len(all_students)}] {data['prenom']} {data['nom_famille']}...", ending=" ")

            try:
                student, was_created = Student.objects.update_or_create(
                    email=data['email'],
                    defaults={
                        'first_name': data['prenom'],
                        'last_name': data['nom_famille'],
                        'school': data['ecole'],
                        'year': data['annee'],
                        'photo_url': data['photo_url'],
                    }
                )

                # Télécharger la photo si pas encore fait
                photo_downloaded = False
                if data['photo_url'] and not student.photo:
                    photo_content = self.download_photo(data['photo_url'])
                    if photo_content:
                        filename = f"{data['uid']}.jpg"
                        student.photo.save(filename, ContentFile(photo_content), save=True)
                        photo_downloaded = True

                # Encoder le visage
                if can_encode and student.photo:
                    if photo_downloaded or not student.face_encoding:
                        try:
                            if self.encode_func(student):
                                encoded += 1
                        except Exception as e:
                            pass

                if was_created:
                    created += 1
                    self.stdout.write(self.style.SUCCESS("✅ créé"))
                else:
                    updated += 1
                    self.stdout.write("🔄 mis à jour")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ {e}"))

            time.sleep(0.1)

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"✅ Créés: {created}"))
        self.stdout.write(f"🔄 Mis à jour: {updated}")
        self.stdout.write(f"🤖 Encodés: {encoded}")

    def authenticate(self, username, password):
        """S'authentifie via CAS"""
        try:
            # 1. Aller sur la page de login du trombi (redirige vers CAS)
            response = self.session.get(self.LOGIN_URL, allow_redirects=True)

            # 2. Parser la page CAS pour trouver le formulaire
            soup = BeautifulSoup(response.text, 'html.parser')

            # Trouver le formulaire de login
            form = soup.find('form')
            if not form:
                self.stderr.write("Formulaire CAS non trouvé")
                return False

            # Récupérer l'URL d'action du formulaire
            action = form.get('action', '')
            if not action.startswith('http'):
                action = urljoin(response.url, action)

            # Récupérer tous les champs cachés
            data = {}
            for input_tag in form.find_all('input'):
                name = input_tag.get('name')
                value = input_tag.get('value', '')
                if name:
                    data[name] = value

            # Ajouter username et password
            data['username'] = username
            data['password'] = password

            # 3. Soumettre le formulaire
            response = self.session.post(action, data=data, allow_redirects=True)

            # 4. Vérifier si on est connecté
            # Si on voit "Déconnexion" ou si on n'a plus "Connexion", c'est bon
            if 'Connexion</span></a>' in response.text and '?login' in response.text:
                return False

            return True

        except Exception as e:
            self.stderr.write(f"Erreur auth: {e}")
            return False

    def search_students(self, ecole='', annee=''):
        """Recherche des étudiants"""
        students = []

        data = {
            'etu[user]': '',
            'etu[ecole]': ecole,
            'etu[annee]': annee,
        }

        try:
            response = self.session.post(self.ETUDIANTS_URL, data=data, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')

            for fiche in soup.find_all('div', class_='ldapFiche'):
                student = self._parse_fiche(fiche, ecole)
                if student:
                    students.append(student)

        except Exception as e:
            self.stderr.write(f"Erreur recherche: {e}")

        return students

    def _parse_fiche(self, fiche, ecole_default='TSP'):
        """Parse une fiche étudiant"""
        try:
            classes = fiche.get('class', [])
            ecole = 'TSP' if 'TSP' in classes else 'IMT-BS' if 'IMT-BS' in classes else ecole_default

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

            nom_div = fiche.find('div', class_='ldapNom')
            nom_complet = nom_div.text.strip() if nom_div else ""

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

            email = ""
            email_link = fiche.find('a', href=re.compile(r'^mailto:'))
            if email_link:
                email = email_link['href'].replace('mailto:', '')

            return {
                'uid': uid,
                'prenom': prenom,
                'nom_famille': nom_famille,
                'email': email,
                'ecole': ecole,
                'photo_url': photo_url,
            }
        except:
            return None

    def download_photo(self, photo_url):
        """Télécharge une photo"""
        try:
            response = self.session.get(photo_url, timeout=15)
            if response.status_code == 200 and len(response.content) > 100:
                return response.content
        except:
            pass
        return None