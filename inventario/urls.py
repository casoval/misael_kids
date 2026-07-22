from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ItemInventarioViewSet, MovimientoInventarioViewSet
router = DefaultRouter()
router.register(r"items",       ItemInventarioViewSet,      basename="item-inventario")
router.register(r"movimientos", MovimientoInventarioViewSet, basename="movimiento-inventario")
urlpatterns = [path("", include(router.urls))]