from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NinoViewSet, TutorViewSet, PersonaAutorizadaViewSet, DocumentoViewSet

router = DefaultRouter()
router.register(r'ninos',       NinoViewSet,              basename='nino')
router.register(r'tutores',     TutorViewSet,             basename='tutor')
router.register(r'autorizados', PersonaAutorizadaViewSet, basename='autorizado')
router.register(r'documentos',  DocumentoViewSet,         basename='documento')

urlpatterns = [path('', include(router.urls))]
