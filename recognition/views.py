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
    if request.method != 'POST':
        return redirect('recognition:home')

    form = PhotoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, error)
        return redirect('recognition:home')

    photo = request.FILES['photo']
    temp_path = default_storage.save(f'temp/{photo.name}', ContentFile(photo.read()))
    full_path = default_storage.path(temp_path)

    from .face_recognition_utils import find_matching_students
    result = find_matching_students(full_path, top_k=10)

    if result['error']:
        messages.error(request, result['error'])
        default_storage.delete(temp_path)
        return redirect('recognition:home')

    request.session['uploaded_photo_path'] = temp_path
    request.session['uploaded_photo_name'] = photo.name
    request.session['matches'] = [
        {'student_id': m['student'].id, 'similarity': m['similarity']}
        for m in result['matches']
    ]

    if len(result['matches']) == 0:
        messages.warning(request, 'Aucune correspondance trouvée dans la base de données.')
    else:
        messages.success(request, f"{len(result['matches'])} correspondance(s) trouvée(s) !")

    return redirect('recognition:preview')


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
    from .models import Student
    context = {
        'total_students': Student.objects.count(),
        'encoded_students': Student.objects.exclude(face_encoding='').exclude(face_encoding__isnull=True).count(),
    }
    return render(request, 'recognition/about.html', context)

def legal(request):
    return render(request, 'recognition/legal.html')