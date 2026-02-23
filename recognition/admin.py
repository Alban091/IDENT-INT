"""
Vue Admin personnalisée pour synchroniser le trombinoscope TSP
==============================================================

Ce fichier ajoute une page dans l'admin Django avec un formulaire
pour entrer le cookie PHPSESSID et lancer la synchronisation.

INSTALLATION:
1. Copie ce fichier dans recognition/admin.py (remplace le contenu existant)
2. Relance le serveur: python manage.py runserver
3. Va sur http://127.0.0.1:8000/admin/recognition/student/sync_trombi/
"""

import re
import time
import requests
from io import BytesIO

from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path
from django.core.files.base import ContentFile
from django import forms

from .models import Student

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


# =============================================================================
# FORMULAIRE DE SYNCHRONISATION
# =============================================================================

class TrombiSyncForm(forms.Form):
    """Formulaire pour la synchronisation du trombinoscope"""

    cookie = forms.CharField(
        label="Cookie PHPSESSID",
        widget=forms.TextInput(attrs={
            'class': 'vTextField',
            'style': 'width: 400px;',
            'placeholder': 'Colle ton cookie PHPSESSID ici'
        }),
        help_text="Récupère-le dans DevTools > Application > Cookies après t'être connecté sur trombi.imtbs-tsp.eu"
    )

    ecole = forms.ChoiceField(
        label="École",
        choices=[
            ('TSP', 'Télécom SudParis'),
            ('IMT-BS', 'IMT Business School'),
            ('all', 'Les deux'),
        ],
        initial='TSP'
    )

    annees = forms.MultipleChoiceField(
        label="Années à synchroniser",
        choices=[
            ('fi_1', '1ère année ingénieur'),
            ('fi_2', '2ème année ingénieur'),
            ('fi_3', '3ème année ingénieur'),
            ('bac_1', 'Bachelor 1'),
            ('bac_2', 'Bachelor 2'),
            ('bac_3', 'Bachelor 3'),
        ],
        initial=['fi_1', 'fi_2', 'fi_3'],
        widget=forms.CheckboxSelectMultiple
    )

    download_photos = forms.BooleanField(
        label="Télécharger les photos",
        initial=True,
        required=False,
        help_text="Décocher pour importer seulement les noms et emails"
    )

    encode_faces = forms.BooleanField(
        label="Encoder les visages automatiquement",
        initial=True,
        required=False,
        help_text="Utilise l'IA pour encoder les visages (peut être long)"
    )


# =============================================================================
# SCRAPER (version simplifiée intégrée)
# =============================================================================

class TrombiScraper:
    """Scraper pour le trombinoscope TSP"""

    BASE_URL = "https://trombi.imtbs-tsp.eu"
    ETUDIANTS_URL = "https://trombi.imtbs-tsp.eu/etudiants.php"
    PHOTO_URL = "https://trombi.imtbs-tsp.eu/photo.php"

    def __init__(self, cookie):
        self.session = requests.Session()
        self.session.cookies.set('PHPSESSID', cookie, domain='trombi.imtbs-tsp.eu')
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': self.ETUDIANTS_URL,
        })

    def test_connection(self):
        """Teste si le cookie est valide"""
        try:
            response = self.session.get(self.ETUDIANTS_URL, timeout=10)
            if 'Connexion</span></a>' in response.text and '?login' in response.text:
                return False
            return True
        except:
            return False

    def search(self, ecole='', annee='', nom=''):
        """Recherche des étudiants"""
        students = []

        data = {
            'etu[user]': nom,
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
            print(f"Erreur: {e}")

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
        """Télécharge une photo et retourne les bytes"""
        try:
            response = self.session.get(photo_url, timeout=15)
            if response.status_code == 200 and len(response.content) > 100:
                return response.content
        except:
            pass
        return None


# =============================================================================
# ADMIN PERSONNALISÉ
# =============================================================================

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    """Admin pour les étudiants avec bouton de synchronisation"""

    list_display = ['last_name', 'first_name', 'email', 'school', 'year', 'has_photo', 'has_encoding']
    list_filter = ['school', 'year']
    search_fields = ['first_name', 'last_name', 'email']
    ordering = ['last_name', 'first_name']

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Identité', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('Scolarité', {
            'fields': ('school', 'year', 'promotion')
        }),
        ('Photo', {
            'fields': ('photo', 'photo_url')
        }),
        ('Reconnaissance faciale', {
            'fields': ('face_encoding',),
            'classes': ('collapse',)
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_photo(self, obj):
        return bool(obj.photo)

    has_photo.boolean = True
    has_photo.short_description = "Photo"

    def has_encoding(self, obj):
        return bool(obj.face_encoding)

    has_encoding.boolean = True
    has_encoding.short_description = "Encodage"

    # =========================================================================
    # URLS PERSONNALISÉES
    # =========================================================================

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('sync_trombi/', self.admin_site.admin_view(self.sync_trombi_view), name='sync_trombi'),
        ]
        return custom_urls + urls

    # =========================================================================
    # VUE DE SYNCHRONISATION
    # =========================================================================

    def sync_trombi_view(self, request):
        """Vue pour synchroniser le trombinoscope"""

        # Vérifier que BeautifulSoup est installé
        if BeautifulSoup is None:
            messages.error(request, "BeautifulSoup n'est pas installé. Lance: pip install beautifulsoup4")
            return redirect('..')

        if request.method == 'POST':
            form = TrombiSyncForm(request.POST)

            if form.is_valid():
                cookie = form.cleaned_data['cookie']
                ecole = form.cleaned_data['ecole']
                annees = form.cleaned_data['annees']
                download_photos = form.cleaned_data['download_photos']
                encode_faces_option = form.cleaned_data['encode_faces']

                # Créer le scraper
                scraper = TrombiScraper(cookie)

                # Tester la connexion
                if not scraper.test_connection():
                    messages.error(request,
                                   "❌ Cookie invalide ou expiré. Reconnecte-toi sur trombi.imtbs-tsp.eu et récupère un nouveau cookie.")
                    return redirect('.')

                # Définir les écoles
                ecoles = ['TSP', 'IMT-BS'] if ecole == 'all' else [ecole]

                # Scraper
                all_students = []
                seen_uids = set()

                for ec in ecoles:
                    for annee in annees:
                        students = scraper.search(ecole=ec, annee=annee)
                        for s in students:
                            if s['uid'] not in seen_uids:
                                seen_uids.add(s['uid'])
                                s['annee'] = annee
                                all_students.append(s)
                        time.sleep(0.2)

                # Importer l'encodage facial
                try:
                    from .face_recognition_utils import encode_student_faces
                    can_encode = True
                except ImportError:
                    can_encode = False

                # Importer
                created = 0
                updated = 0
                encoded = 0

                for data in all_students:
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

                        # Télécharger la photo
                        if download_photos and data['photo_url'] and not student.photo:
                            photo_content = scraper.download_photo(data['photo_url'])
                            if photo_content:
                                filename = f"{data['uid']}.jpg"
                                student.photo.save(filename, ContentFile(photo_content), save=True)

                        # Encoder le visage automatiquement
                        if encode_faces_option and can_encode and student.photo and not student.face_encoding:
                            try:
                                if encode_student_faces(student):
                                    encoded += 1
                            except Exception as e:
                                print(f"Erreur encodage {student}: {e}")

                        if was_created:
                            created += 1
                        else:
                            updated += 1

                    except Exception as e:
                        print(f"Erreur: {e}")
                        continue

                messages.success(request,
                                 f"✅ Synchronisation terminée ! {created} créés, {updated} mis à jour, {encoded} visages encodés.")
                return redirect('..')

        else:
            form = TrombiSyncForm()

        context = {
            'form': form,
            'title': 'Synchroniser le Trombinoscope TSP',
            'opts': self.model._meta,
            'has_view_permission': True,
        }

        return render(request, 'admin/recognition/student/sync_trombi.html', context)

    # =========================================================================
    # AJOUTER LE BOUTON DANS LA LISTE
    # =========================================================================

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_sync_button'] = True
        return super().changelist_view(request, extra_context=extra_context)