from django import forms


class PhotoUploadForm(forms.Form):
    """Formulaire simple pour uploader une photo (sans stockage)"""

    photo = forms.ImageField(
        label='',
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/png,image/jpg',
            'id': 'photoInput',
            'style': 'display: none;'
        })
    )

    def clean_photo(self):
        """Validation de la photo"""
        photo = self.cleaned_data.get('photo')

        if photo:
            # Vérifier le type de fichier
            if not photo.content_type in ['image/jpeg', 'image/png', 'image/jpg']:
                raise forms.ValidationError("Format non supporté. Utilisez JPG ou PNG.")

            # Vérifier la taille (10 MB max)
            if photo.size > 10 * 1024 * 1024:
                raise forms.ValidationError("La photo est trop volumineuse (max 10 MB).")

        return photo