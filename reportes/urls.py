"""
reportes/urls.py — rutas de la API (se completarán con los ViewSets)
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# Los ViewSets se registrarán aquí

urlpatterns = [
    path('', include(router.urls)),
]
