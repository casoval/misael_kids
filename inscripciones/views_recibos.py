"""
inscripciones/views_recibos.py

Vistas que renderizan el recibo imprimible (HTML listo para imprimir o
guardar como PDF desde el navegador) de un Pago o una Devolucion.

No usan DRF serializers porque no devuelven JSON: devuelven HTML directo,
pensado para abrirse en una pestaña nueva desde el panel y usar
Ctrl+P / "Guardar como PDF" del navegador — el template ya trae el CSS
@page necesario para que la impresión salga en tamaño carta con las 2
copias (cliente / administración) una al lado de la otra.
"""
import base64
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from rest_framework.views import APIView

from accounts.permissions import EsAdminDirectoraOAdministrativo
from .models import Cobro, Pago, Devolucion
from .services import MESES_ES

LOGO_PATH = Path(settings.BASE_DIR) / 'frontend' / 'img' / 'logo_recibo.jpg'


def _logo_base64():
    try:
        return base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')
    except FileNotFoundError:
        return None


def _concepto_cobro(cobro):
    if cobro.tipo == Cobro.TIPO_MENSUALIDAD and cobro.periodo_inicio:
        return f'Mensualidad de {MESES_ES[cobro.periodo_inicio.month]} {cobro.periodo_inicio.year}'
    if cobro.tipo == Cobro.TIPO_DIARIO:
        return f'Cobro por día — {cobro.fecha_vencimiento.strftime("%d/%m/%Y")}'
    return cobro.periodo or 'Cobro extra'


def _tutor_principal(nino):
    rel = nino.tutores.filter(es_principal=True).select_related('tutor').first() \
        or nino.tutores.select_related('tutor').first()
    return rel.tutor if rel else None


def _contexto_recibo(cobro, *, es_devolucion, numero_recibo, monto, fecha,
                      metodo_pago_display, nota, registrado_por, creado):
    inscripcion = cobro.inscripcion
    nino = inscripcion.nino
    tutor = _tutor_principal(nino)
    return {
        'logo_base64':         _logo_base64(),
        'nino':                nino,
        'tutor':               tutor,
        'sucursal':            inscripcion.sucursal,
        'inscripcion':         inscripcion,
        'concepto':            _concepto_cobro(cobro),
        'tipo_display':        cobro.get_tipo_display(),
        'es_devolucion':       es_devolucion,
        'numero_recibo':       numero_recibo,
        'monto':               monto,
        'fecha':               fecha,
        'metodo_pago_display': metodo_pago_display,
        'nota':                nota,
        'registrado_por':      registrado_por,
        'creado':              creado,
    }


class ReciboPagoView(APIView):
    """GET /api/inscripciones/recibos/pago/<uuid>/ — recibo de un Pago."""
    permission_classes = [EsAdminDirectoraOAdministrativo]

    def get(self, request, pago_id):
        pago = get_object_or_404(
            Pago.objects.select_related(
                'cobro__inscripcion__nino', 'cobro__inscripcion__sucursal', 'registrado_por'
            ),
            pk=pago_id,
        )
        contexto = _contexto_recibo(
            pago.cobro,
            es_devolucion=False,
            numero_recibo=pago.numero_recibo,
            monto=pago.monto,
            fecha=pago.fecha_pago,
            metodo_pago_display=pago.get_metodo_pago_display(),
            nota=pago.observacion,
            registrado_por=pago.registrado_por.nombre_completo if pago.registrado_por else None,
            creado=pago.created_at,
        )
        html = render_to_string('recibos/recibo.html', contexto)
        return HttpResponse(html, content_type='text/html; charset=utf-8')


class ReciboDevolucionView(APIView):
    """GET /api/inscripciones/recibos/devolucion/<uuid>/ — recibo de una Devolucion."""
    permission_classes = [EsAdminDirectoraOAdministrativo]

    def get(self, request, devolucion_id):
        devolucion = get_object_or_404(
            Devolucion.objects.select_related(
                'cobro__inscripcion__nino', 'cobro__inscripcion__sucursal', 'registrado_por'
            ),
            pk=devolucion_id,
        )
        contexto = _contexto_recibo(
            devolucion.cobro,
            es_devolucion=True,
            numero_recibo=devolucion.numero_recibo,
            monto=devolucion.monto,
            fecha=devolucion.fecha,
            metodo_pago_display=devolucion.get_metodo_pago_display(),
            nota=devolucion.motivo,
            registrado_por=devolucion.registrado_por.nombre_completo if devolucion.registrado_por else None,
            creado=devolucion.created_at,
        )
        html = render_to_string('recibos/recibo.html', contexto)
        return HttpResponse(html, content_type='text/html; charset=utf-8')
