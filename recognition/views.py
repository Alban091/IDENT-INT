from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os
from .forms import PhotoUploadForm


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

            # Sauvegarder le chemin dans la session
            request.session['uploaded_photo_path'] = temp_path
            request.session['uploaded_photo_name'] = photo.name

            messages.success(request, 'Photo uploadée avec succès !')
            return redirect('recognition:preview')
        else:
            # Afficher les erreurs
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

    return redirect('recognition:home')


def preview(request):
    """Affichage de la photo uploadée"""
    photo_path = request.session.get('uploaded_photo_path')
    photo_name = request.session.get('uploaded_photo_name')

    if not photo_path:
        messages.warning(request, "Aucune photo n'a été uploadée.")
        return redirect('recognition:home')

    context = {
        'photo_url': default_storage.url(photo_path),
        'photo_name': photo_name
    }

    return render(request, 'recognition/preview.html', context)