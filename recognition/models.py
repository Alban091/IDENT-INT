from django.db import models
import json


class Student(models.Model):

    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")

    school = models.CharField(max_length=100, blank=True, null=True, verbose_name="École")
    year = models.CharField(max_length=100, blank=True, null=True, verbose_name="Année")
    promotion = models.CharField(max_length=50, blank=True, null=True, verbose_name="Promotion")

    photo = models.ImageField(upload_to='students_photos/', blank=True, null=True, verbose_name="Photo")
    photo_url = models.URLField(blank=True, null=True, verbose_name="URL photo trombinoscope")

    # Encodage facial (pour la reconnaissance)
    face_encoding = models.TextField(blank=True, null=True, verbose_name="Encodage facial")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de mise à jour")

    class Meta:
        verbose_name = "Étudiant"
        verbose_name_plural = "Étudiants"
        ordering = ['last_name', 'first_name']
        unique_together = ['first_name', 'last_name', 'email']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.year or 'N/A'})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def set_face_encoding(self, encoding_array):
        if encoding_array is not None:
            self.face_encoding = json.dumps(encoding_array.tolist())

    def get_face_encoding(self):
        if self.face_encoding:
            import numpy as np
            return np.array(json.loads(self.face_encoding))
        return None