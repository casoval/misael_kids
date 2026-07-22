from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PersonalViewSet, AsignacionPersonalViewSet, AsistenciaPersonalViewSet

router = DefaultRouter()
router.register(r'personal',              PersonalViewSet,            basename='personal')
router.register(r'asignaciones',          AsignacionPersonalViewSet,  basename='asignacion-personal')
router.register(r'asistencia-personal',   AsistenciaPersonalViewSet,  basename='asistencia-personal')

urlpatterns = [path('', include(router.urls))]
