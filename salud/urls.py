from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IncidenteSaludViewSet
router = DefaultRouter()
router.register(r"incidentes", IncidenteSaludViewSet, basename="incidente")
urlpatterns = [path("", include(router.urls))]