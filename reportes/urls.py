"""
reportes/urls.py — rutas de la API de reportes
"""
from django.urls import path
from .views import ResumenView, ExportarView

urlpatterns = [
    path('resumen/',            ResumenView.as_view(),   name='reportes-resumen'),
    path('exportar/<str:tipo>/', ExportarView.as_view(), name='reportes-exportar'),
]
