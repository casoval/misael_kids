from datetime import date
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.db import IntegrityError

from .models import Asistencia
from .serializers import AsistenciaSerializer
from inscripciones.models import Cobro, Inscripcion
from inscripciones.services import generar_ciclo_mensual
from accounts.permissions import filtrar_por_tutor


class AsistenciaViewSet(viewsets.ModelViewSet):
    queryset = Asistencia.objects.select_related(
        'inscripcion__nino', 'inscripcion__sala',
        'inscripcion__turno', 'registrado_por'
    ).all()
    serializer_class   = AsistenciaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = [
        'fecha', 'estado', 'retiro_autorizado',
        'inscripcion__sucursal', 'inscripcion__sala', 'inscripcion__turno',
    ]
    ordering = ['-fecha']

    def get_queryset(self):
        # Sin esto, un tutor podía consultar la asistencia diaria de
        # cualquier niño de cualquier sala, no solo la de su propio hijo.
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'inscripcion__nino')

    def perform_create(self, serializer):
        asistencia  = serializer.save(registrado_por=self.request.user)
        inscripcion = asistencia.inscripcion
        if asistencia.estado != Asistencia.ESTADO_PRESENTE:
            return

        if inscripcion.modalidad_pago == Inscripcion.MODALIDAD_DIARIA:
            # Cobro diario: uno por cada día que asiste (comportamiento existente)
            periodo = asistencia.fecha.strftime('%Y-%m-%d')
            if not Cobro.objects.filter(
                inscripcion=inscripcion,
                periodo=periodo,
                tipo=Cobro.TIPO_DIARIO
            ).exists():
                try:
                    Cobro.objects.create(
                        inscripcion       = inscripcion,
                        tipo              = Cobro.TIPO_DIARIO,
                        periodo           = periodo,
                        monto_base        = inscripcion.costo_diario,
                        monto_final       = inscripcion.costo_diario_final,
                        fecha_vencimiento = asistencia.fecha,
                        registrado_por    = self.request.user,
                    )
                except IntegrityError:
                    # Mismo caso que en generar_ciclo_mensual: dos marcas de
                    # asistencia casi simultáneas para el mismo niño y día.
                    pass

        elif inscripcion.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
            # Mensualidad: la primera vez que el niño asiste dentro de un
            # ciclo que todavía no tiene cobro generado, se genera solo —
            # es la confirmación real de que continúa, no una suposición
            # por calendario. Si el papá/mamá ya avisó antes que continúa,
            # el cobro se puede generar manualmente desde "Cobros" o el
            # botón "Generar mensualidades" en cualquier otro momento; en
            # ese caso esta asistencia simplemente cae dentro del ciclo
            # que ya existe y no duplica nada.
            cubierto = Cobro.objects.filter(
                inscripcion    = inscripcion,
                tipo           = Cobro.TIPO_MENSUALIDAD,
                periodo_inicio__lte = asistencia.fecha,
                periodo_fin__gt     = asistencia.fecha,
            ).exists()
            if not cubierto:
                generar_ciclo_mensual(inscripcion, usuario=self.request.user)

    @action(detail=False, methods=['get'], url_path='hoy')
    def hoy(self, request):
        """Lista la asistencia de hoy filtrable por sala y turno."""
        hoy  = date.today()
        sala  = request.query_params.get('sala')
        turno = request.query_params.get('turno')
        qs    = self.get_queryset().filter(fecha=hoy)
        if sala:
            qs = qs.filter(inscripcion__sala=sala)
        if turno:
            qs = qs.filter(inscripcion__turno=turno)
        serializer = AsistenciaSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='resumen-mensual')
    def resumen_mensual(self, request):
        """Resumen de asistencia de un mes para una sala."""
        año   = int(request.query_params.get('año', date.today().year))
        mes   = int(request.query_params.get('mes', date.today().month))
        sala  = request.query_params.get('sala')
        qs    = self.get_queryset().filter(fecha__year=año, fecha__month=mes)
        if sala:
            qs = qs.filter(inscripcion__sala=sala)
        total     = qs.count()
        presentes = qs.filter(estado=Asistencia.ESTADO_PRESENTE).count()
        ausentes  = qs.filter(estado=Asistencia.ESTADO_AUSENTE).count()
        justif    = qs.filter(estado=Asistencia.ESTADO_AUSENTE_JUSTIFICADO).count()
        return Response({
            'año': año, 'mes': mes,
            'total': total, 'presentes': presentes,
            'ausentes': ausentes, 'justificados': justif,
        })
