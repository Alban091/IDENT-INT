from django.urls import path
from . import views

app_name = 'recognition'

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_photo, name='upload_photo'),
    path('preview/', views.preview, name='preview'),
    path('about/', views.about, name='about'),
# Route de test pour la page 500 (à supprimer en production)
    path('test-500/', lambda request: 1/0, name='test_500'),
]