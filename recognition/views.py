from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os
from .forms import PhotoUploadForm
from .models import Student


def home(request):
    """Page d'accueil avec formulaire d'upload"""
    form = PhotoUploadForm()
    context = {
        'form': form
    }
    return render(request, 'recognition/home.html', context)


def upload_photo(request):
    """Traitement de l'upload de photo (stockage temporaire en session)"""
    if request.method == 'POST':
        form = PhotoUploadForm(request.POST, request.FILES)

        if form.is_valid():
            photo = request.FILES['photo']

            # Stocker temporairement dans media/temp/ pour l'affichage
            temp_path = default_storage.save(f'temp/{photo.name}', ContentFile(photo.read()))
            full_path = default_storage.path(temp_path)

            # Analyser la photo avec la reconnaissance faciale
            from .face_recognition_utils import analyze_photo_quality, find_matching_students

            # Vérifier la qualité
            quality = analyze_photo_quality(full_path)

            if not quality['is_good_quality']:
                messages.error(request, quality['message'])
                # Supprimer la photo temporaire
                default_storage.delete(temp_path)
                return redirect('recognition:home')

            # Chercher les correspondances
            matches = find_matching_students(full_path, threshold=0.6)

            # Sauvegarder le chemin dans la session
            request.session['uploaded_photo_path'] = temp_path
            request.session['uploaded_photo_name'] = photo.name
            request.session['matches'] = [
                {
                    'student_id': m['student'].id,
                    'similarity': float(m['similarity'])
                }
                for m in matches
            ]

            if len(matches) == 0:
                messages.warning(request, 'Aucune correspondance trouvée dans la base de données.')
            else:
                messages.success(request, f'{len(matches)} correspondance(s) trouvée(s) !')

            return redirect('recognition:preview')
        else:
            # Afficher les erreurs
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

    return redirect('recognition:home')


def preview(request):
    """Affichage de la photo uploadée avec les résultats"""
    photo_path = request.session.get('uploaded_photo_path')
    photo_name = request.session.get('uploaded_photo_name')
    matches_data = request.session.get('matches', [])

    if not photo_path:
        messages.warning(request, "Aucune photo n'a été uploadée.")
        return redirect('recognition:home')

    # Récupérer les étudiants correspondants
    matches = []
    for match_data in matches_data:
        try:
            student = Student.objects.get(id=match_data['student_id'])
            matches.append({
                'student': student,
                'similarity': match_data['similarity']
            })
        except Student.DoesNotExist:
            continue

    context = {
        'photo_url': default_storage.url(photo_path),
        'photo_name': photo_name,
        'matches': matches,
        'has_matches': len(matches) > 0
    }

    return render(request, 'recognition/preview.html', context)


# Pages d'erreur personnalisées
def error_404(request, exception):
    """Page d'erreur 404 personnalisée"""
    return render(request, 'recognition/404.html', status=404)


def error_500(request):
    """Page d'erreur 500 personnalisée"""
    return render(request, 'recognition/500.html', status=500)


def about(request):
    """Page À propos - Présentation du projet"""
    return render(request, 'recognition/about.html')