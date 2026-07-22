from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MensajeViewSet, AvisoViewSet
router = DefaultRouter()
router.register(r"mensajes", MensajeViewSet, basename="mensaje")
router.register(r"avisos",   AvisoViewSet,   basename="aviso")
urlpatterns = [path("", include(router.urls))]