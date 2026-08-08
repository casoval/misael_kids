from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DerivacionViewSet, PlanTrabajoMisaelViewSet, VinculoCentroMisaelViewSet,
    BuscarPacienteCentroMisaelView, VincularCentroMisaelView,
    SincronizarDocumentosCentroMisaelView, PendientesCentroMisaelView,
)
router = DefaultRouter()
router.register(r"derivaciones",   DerivacionViewSet,       basename="derivacion")
router.register(r"planes-misael",  PlanTrabajoMisaelViewSet, basename="plan-misael")
router.register(r"vinculos-centro-misael", VinculoCentroMisaelViewSet, basename="vinculo-centro-misael")
urlpatterns = [
    path("centro-misael/buscar/", BuscarPacienteCentroMisaelView.as_view(), name="cm-buscar"),
    path("centro-misael/vincular/", VincularCentroMisaelView.as_view(), name="cm-vincular"),
    path("centro-misael/sincronizar/", SincronizarDocumentosCentroMisaelView.as_view(), name="cm-sincronizar"),
    path("centro-misael/pendientes/", PendientesCentroMisaelView.as_view(), name="cm-pendientes"),
    path("", include(router.urls)),
]