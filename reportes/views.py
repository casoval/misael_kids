import uuid
from datetime import date

from django.http import HttpResponse
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import SoloAdminDirectoraORecepcionista
from . import services


class _ReporteBase(APIView):
    """Solo admin, directora y recepcionista (los mismos que ven Cobros/caja)."""
    permission_classes = [SoloAdminDirectoraORecepcionista]

    @staticmethod
    def parametros(request):
        qp = request.query_params
        try:
            anio, mes = (int(x) for x in (qp.get('mes') or date.today().strftime('%Y-%m')).split('-'))
            date(anio, mes, 1)
        except (ValueError, TypeError):
            raise ValidationError({'mes': 'El mes debe tener formato AAAA-MM.'})
        sucursal = qp.get('sucursal') or None
        if sucursal:
            try:
                sucursal = uuid.UUID(sucursal)
            except ValueError:
                raise ValidationError({'sucursal': 'Sucursal inválida.'})
        return anio, mes, sucursal


class ResumenView(_ReporteBase):
    """GET /api/reportes/resumen/?mes=AAAA-MM&sucursal=<id> → todo lo que muestra la pantalla."""

    def get(self, request):
        anio, mes, sucursal = self.parametros(request)
        return Response(services.resumen_general(anio, mes, sucursal))


class ExportarView(_ReporteBase):
    """GET /api/reportes/exportar/<asistencia|cobros|ninos|inventario>/?mes=AAAA-MM&sucursal=<id>"""

    def get(self, request, tipo):
        exportador = services.EXPORTADORES.get(tipo)
        if exportador is None:
            raise NotFound('Ese reporte no existe.')
        anio, mes, sucursal = self.parametros(request)
        nombre, cabecera, filas = exportador(anio, mes, sucursal)
        respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
        respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
        respuesta['Cache-Control'] = 'no-store'      # datos de niños y cobros: que no queden en cachés
        respuesta['X-Filas'] = str(services.escribir_csv(respuesta, cabecera, filas))   # sin contar la cabecera
        return respuesta
