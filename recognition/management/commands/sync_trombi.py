import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from dotenv import load_dotenv

from recognition.models import Student
from recognition.trombi import TrombiScraper


class Command(BaseCommand):
    help = 'Synchronise le trombinoscope TSP avec authentification automatique CAS'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default=None)
        parser.add_argument('--password', type=str, default=None)
        parser.add_argument('--ecole', type=str, default='TSP', choices=['TSP', 'IMT-BS', 'all'])
        parser.add_argument('--annee', type=str, default='all', help='fi_1, fi_2, fi_3, bac_1, etc.')
        parser.add_argument('--no-encode', action='store_true', help='Ne pas encoder les visages')

    def handle(self, *args, **options):
        load_dotenv()
        username = options['username'] or os.getenv('TROMBI_USERNAME')
        password = options['password'] or os.getenv('TROMBI_PASSWORD')

        if not username or not password:
            raise CommandError(
                "Identifiants manquants. Renseigne .env (TROMBI_USERNAME/TROMBI_PASSWORD) "
                "ou utilise --username/--password"
            )

        scraper = TrombiScraper()

        self.stdout.write("🔐 Connexion en cours...")
        if not scraper.authenticate(username, password):
            raise CommandError("❌ Échec de l'authentification. Vérifie ton login/mot de passe.")
        self.stdout.write(self.style.SUCCESS("✅ Connecté !"))

        annees = ['fi_1', 'fi_2', 'fi_3'] if options['annee'] == 'all' else [options['annee']]
        ecoles = ['TSP', 'IMT-BS'] if options['ecole'] == 'all' else [options['ecole']]

        can_encode = not options['no_encode']
        encode_func = None
        if can_encode:
            try:
                from recognition.face_recognition_utils import encode_student_faces
                encode_func = encode_student_faces
            except ImportError:
                self.stdout.write(self.style.WARNING("⚠️ face_recognition non disponible, encodage désactivé"))
                can_encode = False

        all_students = []
        seen_uids = set()
        for ecole in ecoles:
            for annee in annees:
                self.stdout.write(f"📚 {ecole} - {annee}...")
                students = scraper.search(ecole=ecole, annee=annee)
                for s in students:
                    if s['uid'] not in seen_uids:
                        seen_uids.add(s['uid'])
                        s['annee'] = annee
                        all_students.append(s)
                self.stdout.write(f"   → {len(students)} trouvés")
                time.sleep(0.3)

        self.stdout.write(f"\n📊 Total: {len(all_students)} étudiants")

        created = 0
        updated = 0
        encoded = 0
        photos_real = 0
        photos_missing = 0

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

                photo_downloaded = False
                if data['photo_url'] and not student.photo:
                    photo_content = scraper.download_photo(data['photo_url'])
                    if photo_content:
                        filename = f"{data['uid']}.jpg"
                        student.photo.save(filename, ContentFile(photo_content), save=True)
                        photo_downloaded = True
                        if len(photo_content) != TrombiScraper.PLACEHOLDER_PHOTO_SIZE:
                            photos_real += 1
                        else:
                            photos_missing += 1
                if can_encode and student.photo:
                    if photo_downloaded or not student.face_encoding:
                        try:
                            if encode_func(student):
                                encoded += 1
                        except Exception:
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
        self.stdout.write(f"📸 Vraies photos téléchargées: {photos_real}")
        self.stdout.write(f"❌ Sans photo sur le trombi: {photos_missing}")
        self.stdout.write(f"🤖 Encodés: {encoded}")