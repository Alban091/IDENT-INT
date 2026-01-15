from django.urls import path
from . import views

app_name = 'recognition'

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_photo, name='upload_photo'),
    path('preview/', views.preview, name='preview'),
]