import uuid
from datetime import date, datetime

from django.http import HttpResponse
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import SoloAdminDirectoraORecepcionista, SoloAdminODirectora
from asistencia.models import Asistencia
from inscripciones.models import Cobro
from . import services


def _uuid(valor, campo):
    if not valor:
        return None
    try:
        return uuid.UUID(valor)
    except ValueError:
        raise ValidationError({campo: 'Valor inválido.'})


def _fecha(valor, campo):
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValidationError({campo: 'La fecha debe tener formato AAAA-MM-DD.'})


def construir_filtros(request, reporte=None):
    """
    Lee los filtros de la URL, iguales para pantalla, CSV y PDF:
      - período: `mes=AAAA-MM`, o `desde` y `hasta` (AAAA-MM-DD; un solo día = mismo valor).
        Sin nada, el mes en curso.
      - `sucursal`, `sala`, `usuario` (id); `estado`, `tipo` (de cobro), `metodo`.
    """
    qp = request.query_params
    if qp.get('desde') or qp.get('hasta'):
        if not (qp.get('desde') and qp.get('hasta')):
            raise ValidationError({'desde': 'Indica la fecha inicial y la final.'})
        desde, hasta = _fecha(qp['desde'], 'desde'), _fecha(qp['hasta'], 'hasta')
    else:
        try:
            anio, mes = (int(x) for x in (qp.get('mes') or date.today().strftime('%Y-%m')).split('-'))
            desde, hasta = services.rango_mes(anio, mes)
        except (ValueError, TypeError):
            raise ValidationError({'mes': 'El mes debe tener formato AAAA-MM.'})
    if desde > hasta:
        raise ValidationError({'desde': 'La fecha inicial no puede ser posterior a la final.'})
    if (hasta - desde).days + 1 > services.MAX_DIAS:
        raise ValidationError({'hasta': f'El período no puede pasar de {services.MAX_DIAS} días.'})

    estado = qp.get('estado') or None
    if estado:
        validos = [e for e, _ in (Asistencia.ESTADOS if reporte == 'asistencia' else Cobro.ESTADOS)]
        if estado not in validos:
            raise ValidationError({'estado': 'Estado inválido.'})
    tipo = qp.get('tipo') or None
    if tipo and tipo not in [t for t, _ in Cobro.TIPOS]:
        raise ValidationError({'tipo': 'Tipo de cobro inválido.'})
    metodo = qp.get('metodo') or None
    if metodo and metodo not in [m for m, _ in Cobro.METODOS_PAGO]:
        raise ValidationError({'metodo': 'Método de pago inválido.'})
    return services.Filtros(
        desde=desde, hasta=hasta, sucursal=_uuid(qp.get('sucursal'), 'sucursal'),
        sala=_uuid(qp.get('sala'), 'sala'), estado=estado, tipo=tipo,
        usuario=_uuid(qp.get('usuario'), 'usuario'), metodo=metodo)


def _sin_cache(respuesta):
    respuesta['Cache-Control'] = 'no-store'      # datos de niños y cobros: que no queden en cachés
    return respuesta


class _ConsultaBase(APIView):
    """Para VER reportes en pantalla: admin, directora y recepcionista (los mismos que ven Cobros/caja)."""
    permission_classes = [SoloAdminDirectoraORecepcionista]


class _DescargaBase(APIView):
    """Para SACAR información en archivos (CSV, PDF): solo admin y directora. La recepcionista no descarga."""
    permission_classes = [SoloAdminODirectora]


class ResumenView(_ConsultaBase):
    """GET /api/reportes/resumen/?mes=AAAA-MM | desde=&hasta=&sucursal=<id> → todo lo que muestra la pantalla."""

    def get(self, request):
        f = construir_filtros(request)
        return Response(services.resumen_general(f.desde, f.hasta, f.sucursal))


class CierreCajaView(_ConsultaBase):
    """
    GET /api/reportes/cierre-caja/?desde=&hasta=&sucursal=&usuario=&metodo=
    Cuánto debe quedar en efectivo, transferencia y QR, día por día, con el detalle de cada movimiento.
    """

    def get(self, request):
        f = construir_filtros(request)
        cierre = services.cierre_caja(f.desde, f.hasta, f.sucursal, f.usuario, f.metodo, con_detalle=True)
        for m in cierre['movimientos']:
            m['fecha'] = m['fecha'].isoformat()
            m['creado'] = m['creado'].isoformat() if m['creado'] else None
        return Response(cierre)


class ExportarView(_DescargaBase):
    """GET /api/reportes/exportar/<asistencia|cobros|ninos|inventario|deudas|cierre-caja>/?…"""

    def get(self, request, tipo):
        exportador = services.EXPORTADORES.get(tipo)
        if exportador is None:
            raise NotFound('Ese reporte no existe.')
        f = construir_filtros(request, tipo)
        nombre, cabecera, filas = exportador(f)
        respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
        respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
        respuesta['X-Filas'] = str(services.escribir_csv(respuesta, cabecera, filas))   # sin contar la cabecera
        return _sin_cache(respuesta)


class PdfView(_DescargaBase):
    """GET /api/reportes/pdf/<informe-economico|cierre-caja|asistencia|cobros|deudas|ninos|inventario>/?…"""

    def get(self, request, tipo):
        from . import pdf_reportes
        generador = pdf_reportes.GENERADORES.get(tipo)
        if generador is None:
            raise NotFound('Ese reporte no existe.')
        f = construir_filtros(request, tipo)
        contenido, nombre, filas = generador(f, request.user)
        respuesta = HttpResponse(contenido, content_type='application/pdf')
        respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
        respuesta['X-Filas'] = str(filas)
        return _sin_cache(respuesta)
