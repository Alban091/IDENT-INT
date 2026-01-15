from django.urls import path
from . import views

app_name = 'recognition'

urlpatterns = [
# Page d'accueil / upload
    path('', views.home, name='home'),
]