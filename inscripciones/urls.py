from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InscripcionViewSet, CobroViewSet
from .views_recibos import ReciboPagoView, ReciboDevolucionView

router = DefaultRouter()
router.register(r'inscripciones', InscripcionViewSet, basename='inscripcion')
router.register(r'cobros',        CobroViewSet,       basename='cobro')

urlpatterns = [
    path('', include(router.urls)),
    path('recibos/pago/<uuid:pago_id>/', ReciboPagoView.as_view(), name='recibo-pago'),
    path('recibos/devolucion/<uuid:devolucion_id>/', ReciboDevolucionView.as_view(), name='recibo-devolucion'),
]
