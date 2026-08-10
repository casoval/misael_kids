from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DerivacionViewSet, VinculoCentroMisaelViewSet,
    BuscarPacienteCentroMisaelView, VincularCentroMisaelView,
    PlanesTrabajoCentroMisaelView,
    ConsultaVinculoCentroMisaelView, DerivacionesCentroMisaelView,
)
router = DefaultRouter()
router.register(r"derivaciones",   DerivacionViewSet,       basename="derivacion")
router.register(r"vinculos-centro-misael", VinculoCentroMisaelViewSet, basename="vinculo-centro-misael")
urlpatterns = [
    # Saliente: Misael Kids -> Centro Misael
    path("centro-misael/buscar/", BuscarPacienteCentroMisaelView.as_view(), name="cm-buscar"),
    path("centro-misael/vincular/", VincularCentroMisaelView.as_view(), name="cm-vincular"),
    path("centro-misael/planes-trabajo/", PlanesTrabajoCentroMisaelView.as_view(), name="cm-planes-trabajo"),
    # Entrante: Centro Misael -> Misael Kids (autenticado con CENTRO_MISAEL_API_KEY)
    path("consulta/vinculo/", ConsultaVinculoCentroMisaelView.as_view(), name="cm-consulta-vinculo"),
    path("consulta/derivaciones/", DerivacionesCentroMisaelView.as_view(), name="cm-consulta-derivaciones"),
    path("", include(router.urls)),
]
