import time

from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path
from django.core.files.base import ContentFile
from django import forms

from .models import Student
from .trombi import TrombiScraper


class TrombiSyncForm(forms.Form):
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


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    change_list_template = 'admin/recognition/student/change_list.html'

    list_display = ['last_name', 'first_name', 'email', 'school', 'year', 'has_photo', 'has_encoding']
    list_filter = ['school', 'year']
    search_fields = ['first_name', 'last_name', 'email']
    ordering = ['last_name', 'first_name']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['encode_faces']

    fieldsets = (
        ('Identité', {'fields': ('first_name', 'last_name', 'email')}),
        ('Scolarité', {'fields': ('school', 'year', 'promotion')}),
        ('Photo', {'fields': ('photo', 'photo_url')}),
        ('Reconnaissance faciale', {'fields': ('face_encoding',), 'classes': ('collapse',)}),
        ('Métadonnées', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def has_photo(self, obj):
        return bool(obj.photo)
    has_photo.boolean = True
    has_photo.short_description = "Photo"

    def has_encoding(self, obj):
        return bool(obj.face_encoding)
    has_encoding.boolean = True
    has_encoding.short_description = "Encodage"

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

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('sync_trombi/', self.admin_site.admin_view(self.sync_trombi_view), name='sync_trombi'),
        ]
        return custom_urls + urls

    def sync_trombi_view(self, request):
        if request.method == 'POST':
            form = TrombiSyncForm(request.POST)
            if form.is_valid():
                username = form.cleaned_data['username']
                password = form.cleaned_data['password']
                ecole = form.cleaned_data['ecole']
                annees = form.cleaned_data['annees']
                download_photos = form.cleaned_data['download_photos']
                encode_faces_option = form.cleaned_data['encode_faces']

                scraper = TrombiScraper()
                if not scraper.authenticate(username, password):
                    messages.error(request, "❌ Échec de connexion. Vérifie ton login/mot de passe TSP.")
                    return redirect('.')

                ecoles = ['TSP', 'IMT-BS'] if ecole == 'all' else [ecole]

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

                try:
                    from .face_recognition_utils import encode_student_faces
                    can_encode = True
                except ImportError:
                    can_encode = False

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

                        photo_downloaded = False
                        if download_photos and data['photo_url'] and not student.photo:
                            photo_content = scraper.download_photo(data['photo_url'])
                            if photo_content:
                                filename = f"{data['uid']}.jpg"
                                student.photo.save(filename, ContentFile(photo_content), save=True)
                                photo_downloaded = True

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


admin.site.site_header = "TSP IDENTINT - Administration"
admin.site.site_title = "TSP IDENTINT Admin"
admin.site.index_title = "Gestion de la reconnaissance faciale"