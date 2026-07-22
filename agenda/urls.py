from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlanificacionGrupalViewSet, PlanIndividualViewSet, ObjetivoIndividualViewSet, RegistroObjetivoViewSet
router = DefaultRouter()
router.register(r"planificaciones", PlanificacionGrupalViewSet, basename="planificacion")
router.register(r"planes-individuales", PlanIndividualViewSet, basename="plan-individual")
router.register(r"objetivos", ObjetivoIndividualViewSet, basename="objetivo")
router.register(r"registros-objetivos", RegistroObjetivoViewSet, basename="registro-objetivo")
urlpatterns = [path("", include(router.urls))]