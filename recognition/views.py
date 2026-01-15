from django.shortcuts import render

def home(request):
    """Page d'accueil"""
    return render(request, 'recognition/home.html')