from datetime import date
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from .models import Asistencia
from .serializers import AsistenciaSerializer
from inscripciones.models import Cobro


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

    def perform_create(self, serializer):
        asistencia = serializer.save(registrado_por=self.request.user)
        # Si la inscripción es de modalidad diaria y el niño está presente,
        # generar cobro automáticamente
        inscripcion = asistencia.inscripcion
        if (asistencia.estado == Asistencia.ESTADO_PRESENTE and
                inscripcion.modalidad_pago == 'diaria'):
            periodo = asistencia.fecha.strftime('%Y-%m-%d')
            if not Cobro.objects.filter(
                inscripcion=inscripcion,
                periodo=periodo,
                tipo=Cobro.TIPO_DIARIO
            ).exists():
                Cobro.objects.create(
                    inscripcion       = inscripcion,
                    tipo              = Cobro.TIPO_DIARIO,
                    periodo           = periodo,
                    monto_base        = inscripcion.costo_diario,
                    monto_final       = inscripcion.costo_diario_final,
                    fecha_vencimiento = asistencia.fecha,
                    registrado_por    = self.request.user,
                )

    @action(detail=False, methods=['get'], url_path='hoy')
    def hoy(self, request):
        """Lista la asistencia de hoy filtrable por sala y turno."""
        hoy  = date.today()
        sala  = request.query_params.get('sala')
        turno = request.query_params.get('turno')
        qs    = self.queryset.filter(fecha=hoy)
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
        qs    = self.queryset.filter(fecha__year=año, fecha__month=mes)
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
