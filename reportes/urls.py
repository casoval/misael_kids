"""
reportes/urls.py — rutas de la API de reportes
"""
from django.urls import path
from .views import ResumenView, CierreCajaView, ExportarView, PdfView

urlpatterns = [
    path('resumen/',             ResumenView.as_view(),    name='reportes-resumen'),
    path('cierre-caja/',         CierreCajaView.as_view(), name='reportes-cierre-caja'),
    path('exportar/<str:tipo>/', ExportarView.as_view(),   name='reportes-exportar'),
    path('pdf/<str:tipo>/',      PdfView.as_view(),        name='reportes-pdf'),
]
