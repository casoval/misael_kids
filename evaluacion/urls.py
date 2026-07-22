from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HitoDesarrolloViewSet, EvaluacionNinoViewSet
router = DefaultRouter()
router.register(r"hitos",       HitoDesarrolloViewSet, basename="hito")
router.register(r"evaluaciones", EvaluacionNinoViewSet, basename="evaluacion")
urlpatterns = [path("", include(router.urls))]