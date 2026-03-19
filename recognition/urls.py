from django.urls import path
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from . import views

app_name = 'recognition'


def logout_view(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect('recognition:home')


urlpatterns = [
    path('', views.home, name='home'),
    path('upload/', views.upload_photo, name='upload_photo'),
    path('preview/', views.preview, name='preview'),
    path('about/', views.about, name='about'),

    # Authentification
    path('login/', auth_views.LoginView.as_view(
        template_name='recognition/login.html',
        next_page='recognition:home'
    ), name='login'),
    path('logout/', logout_view, name='logout'),
]