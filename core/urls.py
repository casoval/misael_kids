"""
core/urls.py
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SucursalViewSet, SalaViewSet, TurnoViewSet

router = DefaultRouter()
router.register(r'sucursales', SucursalViewSet, basename='sucursal')
router.register(r'salas',      SalaViewSet,      basename='sala')
router.register(r'turnos',     TurnoViewSet,     basename='turno')

urlpatterns = [
    path('', include(router.urls)),
]
