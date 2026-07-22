from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InscripcionViewSet, CobroViewSet

router = DefaultRouter()
router.register(r'inscripciones', InscripcionViewSet, basename='inscripcion')
router.register(r'cobros',        CobroViewSet,       basename='cobro')

urlpatterns = [path('', include(router.urls))]
