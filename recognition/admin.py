"""
Vue Admin personnalisée pour synchroniser le trombinoscope TSP
==============================================================

S'authentifie automatiquement avec login/mot de passe TSP (via CAS).

INSTALLATION:
1. Copie ce fichier dans recognition/admin.py
2. Copie le template sync_trombi.html dans recognition/templates/admin/recognition/student/
3. Relance le serveur: python manage.py runserver
4. Va sur http://127.0.0.1:8000/admin/recognition/student/sync_trombi/
"""

import re
import time
import requests
from urllib.parse import urljoin

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

    username = forms.CharField(
        label="Login TSP",
        widget=forms.TextInput(attrs={
            'class': 'vTextField',
            'style': 'width: 300px;',
            'placeholder': 'ton_login',
            'autocomplete': 'username',
        }),
        help_text="Ton identifiant TSP (ex: arobert)"
    )

    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'vTextField',
            'style': 'width: 300px;',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        }),
        help_text="Ton mot de passe TSP"
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
    )

    encode_faces = forms.BooleanField(
        label="Encoder les visages automatiquement",
        initial=True,
        required=False,
        help_text="Utilise l'IA pour encoder les visages (peut être long)"
    )


# =============================================================================
# SCRAPER AVEC AUTHENTIFICATION CAS
# =============================================================================

class TrombiScraper:
    """Scraper pour le trombinoscope TSP avec authentification CAS"""

    BASE_URL = "https://trombi.imtbs-tsp.eu"
    LOGIN_URL = "https://trombi.imtbs-tsp.eu/etudiants.php?login"
    ETUDIANTS_URL = "https://trombi.imtbs-tsp.eu/etudiants.php"
    PHOTO_URL = "https://trombi.imtbs-tsp.eu/photo.php"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        })
        self.authenticated = False

    def authenticate(self, username, password):
        """S'authentifie via CAS de l'IMT"""
        try:
            # 1. Aller sur la page de login (redirige vers CAS)
            response = self.session.get(self.LOGIN_URL, allow_redirects=True, timeout=15)

            # 2. Parser le formulaire CAS
            soup = BeautifulSoup(response.text, 'html.parser')
            form = soup.find('form')

            if not form:
                print("Formulaire CAS non trouvé")
                return False

            # URL d'action du formulaire
            action = form.get('action', '')
            if not action.startswith('http'):
                action = urljoin(response.url, action)

            # Récupérer tous les champs cachés (tokens CSRF, etc.)
            data = {}
            for input_tag in form.find_all('input'):
                name = input_tag.get('name')
                value = input_tag.get('value', '')
                if name:
                    data[name] = value

            # Ajouter les identifiants
            data['username'] = username
            data['password'] = password

            # 3. Soumettre le formulaire
            response = self.session.post(action, data=data, allow_redirects=True, timeout=15)

            # 4. Vérifier si connecté
            if 'Connexion</span></a>' in response.text and '?login' in response.text:
                return False

            self.authenticated = True
            return True

        except Exception as e:
            print(f"Erreur auth: {e}")
            return False

    def search(self, ecole='', annee=''):
        """Recherche des étudiants"""
        if not self.authenticated:
            return []

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
            print(f"Erreur recherche: {e}")

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


# =============================================================================
# ADMIN PERSONNALISÉ
# =============================================================================

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    """Admin pour les étudiants avec bouton de synchronisation"""

    # Template personnalisé avec bouton Sync
    change_list_template = 'admin/recognition/student/change_list.html'

    list_display = ['last_name', 'first_name', 'email', 'school', 'year', 'has_photo', 'has_encoding']
    list_filter = ['school', 'year']
    search_fields = ['first_name', 'last_name', 'email']
    ordering = ['last_name', 'first_name']

    readonly_fields = ['created_at', 'updated_at']

    actions = ['encode_faces']

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

    # Action pour encoder les visages manuellement
    def encode_faces(self, request, queryset):
        try:
            from .face_recognition_utils import encode_student_faces
            count = 0
            for student in queryset:
                if student.photo and not student.face_encoding:
                    if encode_student_faces(student):
                        count += 1
            self.message_user(request, f"✅ {count} visage(s) encodé(s)")
        except ImportError:
            self.message_user(request, "❌ face_recognition non installé", level=messages.ERROR)
    encode_faces.short_description = "🤖 Encoder les visages sélectionnés"

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

        if BeautifulSoup is None:
            messages.error(request, "❌ BeautifulSoup non installé. Lance: pip install beautifulsoup4")
            return redirect('..')

        if request.method == 'POST':
            form = TrombiSyncForm(request.POST)

            if form.is_valid():
                username = form.cleaned_data['username']
                password = form.cleaned_data['password']
                ecole = form.cleaned_data['ecole']
                annees = form.cleaned_data['annees']
                download_photos = form.cleaned_data['download_photos']
                encode_faces_option = form.cleaned_data['encode_faces']

                # Créer le scraper et s'authentifier
                scraper = TrombiScraper()

                if not scraper.authenticate(username, password):
                    messages.error(request, "❌ Échec de connexion. Vérifie ton login/mot de passe TSP.")
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

                # Importer les étudiants
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
                        photo_downloaded = False
                        if download_photos and data['photo_url'] and not student.photo:
                            photo_content = scraper.download_photo(data['photo_url'])
                            if photo_content:
                                filename = f"{data['uid']}.jpg"
                                student.photo.save(filename, ContentFile(photo_content), save=True)
                                photo_downloaded = True

                        # Encoder le visage automatiquement
                        if encode_faces_option and can_encode and student.photo:
                            if photo_downloaded or not student.face_encoding:
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

                messages.success(
                    request,
                    f"✅ Synchronisation terminée ! {created} créés, {updated} mis à jour, {encoded} visages encodés."
                )
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

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_sync_button'] = True
        return super().changelist_view(request, extra_context=extra_context)


# Personnaliser le site admin
admin.site.site_header = "TSP IDENTINT - Administration"
admin.site.site_title = "TSP IDENTINT Admin"
admin.site.index_title = "Gestion de la reconnaissance faciale"