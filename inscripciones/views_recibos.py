"""
inscripciones/views_recibos.py

Vistas que devuelven el PDF real de un Pago o una Devolucion, generado
con inscripciones/pdf_generator.py (reportlab). Se sirve como
application/pdf; el panel lo muestra en un iframe y ahí mismo se puede
imprimir o descargar con los controles nativos del visor de PDF del
navegador.
"""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied

from accounts.permissions import EsAdminDirectoraOAdministrativo
from .models import Pago, Devolucion
from .pdf_generator import generar_recibo_pdf, generar_devolucion_pdf


def _verificar_acceso_tutor(request, nino):
    """
    Estas vistas van directo por UUID (no pasan por un queryset filtrado
    como CobroViewSet), así que sin este chequeo cualquier cuenta de tutor
    podía descargar el recibo de CUALQUIER pago con solo conocer/adivinar
    el UUID, sin importar de qué niño fuera.
    """
    if request.user.rol != 'tutor':
        return
    es_su_hijo = nino.tutores.filter(tutor__usuario=request.user).exists()
    if not es_su_hijo:
        raise PermissionDenied('Este recibo no pertenece a un hijo vinculado a tu cuenta.')


class ReciboPagoView(APIView):
    """GET /api/inscripciones/recibos/pago/<uuid>/ — PDF del recibo de un Pago."""
    permission_classes = [EsAdminDirectoraOAdministrativo]

    def get(self, request, pago_id):
        pago = get_object_or_404(
            Pago.objects.select_related(
                'cobro__inscripcion__nino', 'cobro__inscripcion__sucursal', 'registrado_por'
            ).prefetch_related('cobro__inscripcion__nino__tutores__tutor'),
            pk=pago_id,
        )
        _verificar_acceso_tutor(request, pago.cobro.inscripcion.nino)
        pdf_bytes = generar_recibo_pdf(pago)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="recibo_{pago.numero_recibo}.pdf"'
        return response


class ReciboDevolucionView(APIView):
    """GET /api/inscripciones/recibos/devolucion/<uuid>/ — PDF del recibo de una Devolucion."""
    permission_classes = [EsAdminDirectoraOAdministrativo]

    def get(self, request, devolucion_id):
        devolucion = get_object_or_404(
            Devolucion.objects.select_related(
                'cobro__inscripcion__nino', 'cobro__inscripcion__sucursal', 'registrado_por'
            ).prefetch_related('cobro__inscripcion__nino__tutores__tutor'),
            pk=devolucion_id,
        )
        _verificar_acceso_tutor(request, devolucion.cobro.inscripcion.nino)
        pdf_bytes = generar_devolucion_pdf(devolucion)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="devolucion_{devolucion.numero_recibo}.pdf"'
        return response
