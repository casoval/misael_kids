from datetime import date, timedelta
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.db import IntegrityError, transaction

from .models import Asistencia
from .serializers import AsistenciaSerializer
from inscripciones.models import Cobro, Inscripcion
from personal.models import AsignacionPersonal
from inscripciones.services import generar_ciclo_mensual
from accounts.permissions import filtrar_por_tutor, NoEsTutor


class AsistenciaViewSet(viewsets.ModelViewSet):
    queryset = Asistencia.objects.select_related(
        'inscripcion__nino', 'inscripcion__sala',
        'inscripcion__turno', 'registrado_por'
    ).all()
    serializer_class   = AsistenciaSerializer
    # Lectura para cualquier autenticado (un tutor solo ve la asistencia de
    # su propio hijo, filtrado en get_queryset). Escritura solo personal del
    # centro: sin NoEsTutor, cualquier tutor podía marcar/editar asistencia
    # de CUALQUIER niño (el `inscripcion` del POST nunca se validaba contra
    # sus propios hijos) — y eso además puede disparar la generación
    # automática de un cobro de mensualidad para una familia ajena.
    permission_classes = [IsAuthenticated, NoEsTutor]
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

    # Texto que queda en `Cobro.observacion` cuando el sistema anula un cobro
    # diario por un cambio de asistencia. Sirve de marca: solo se reactiva un
    # cobro que anuló el sistema, nunca uno que anuló una persona a mano.
    MARCA_ANULACION_AUTO = 'Anulado automáticamente'

    def _anotar(self, cobro, texto):
        cobro.observacion = (cobro.observacion + '\n' if cobro.observacion else '') + texto

    def _generar_cobros_por_presencia(self, asistencia):
        """
        Genera (o reactiva) el cobro que corresponde a un niño que está presente.
        Devuelve 'reactivado' si volvió a abrir un cobro diario que el sistema
        había anulado, o None en cualquier otro caso.
        """
        inscripcion = asistencia.inscripcion
        if asistencia.estado != Asistencia.ESTADO_PRESENTE:
            return None

        if inscripcion.modalidad_pago == Inscripcion.MODALIDAD_DIARIA:
            # Cobro diario: uno por cada día que asiste
            periodo = asistencia.fecha.strftime('%Y-%m-%d')
            cobro = Cobro.objects.filter(
                inscripcion=inscripcion, periodo=periodo, tipo=Cobro.TIPO_DIARIO
            ).first()
            if cobro is None:
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
            elif (cobro.estado == Cobro.ESTADO_ANULADO
                  and self.MARCA_ANULACION_AUTO in (cobro.observacion or '')):
                # El niño volvió a quedar "presente" tras haberse anulado el
                # cobro por error de marcado: se reabre el mismo cobro (la
                # restricción de "un cobro diario por día" impide crear otro).
                cobro.estado = Cobro.ESTADO_PENDIENTE
                self._anotar(cobro, 'Reactivado: la asistencia volvió a marcarse como presente.')
                cobro.save(update_fields=['estado', 'observacion'])
                cobro.recalcular_estado()   # lo pasa a "vencido" si corresponde
                return 'reactivado'

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
        return None

    def _anular_cobro_diario(self, asistencia):
        """
        El niño dejó de estar "presente" (se marcó por error, o cambió a
        ausente/justificado): se anula el cobro diario de ese día, pero SOLO
        si nadie ha tocado plata todavía. Devuelve 'anulado', 'con_pagos'
        (había un cobro pero no se pudo anular) o None (no había nada que hacer).
        La mensualidad no se toca: no depende de los días que asista.
        """
        inscripcion = asistencia.inscripcion
        if inscripcion.modalidad_pago != Inscripcion.MODALIDAD_DIARIA:
            return None
        cobro = Cobro.objects.filter(
            inscripcion=inscripcion, tipo=Cobro.TIPO_DIARIO,
            periodo=asistencia.fecha.strftime('%Y-%m-%d'),
        ).first()
        if cobro is None or cobro.estado == Cobro.ESTADO_ANULADO:
            return None
        con_movimientos = (
            cobro.estado in (Cobro.ESTADO_PARCIAL, Cobro.ESTADO_PAGADO)
            or cobro.pagos.exists() or cobro.devoluciones.exists()
            or cobro.monto_condonado > 0
        )
        if con_movimientos:
            return 'con_pagos'
        cobro.estado = Cobro.ESTADO_ANULADO
        self._anotar(cobro, f'{self.MARCA_ANULACION_AUTO}: la asistencia del '
                            f'{asistencia.fecha:%d/%m/%Y} cambió a "{asistencia.get_estado_display()}".')
        cobro.save(update_fields=['estado', 'observacion'])
        return 'anulado'

    def perform_create(self, serializer):
        asistencia = serializer.save(registrado_por=self.request.user)
        self._generar_cobros_por_presencia(asistencia)

    def perform_update(self, serializer):
        """
        Antes solo `perform_create` tocaba cobros, así que corregir una
        asistencia ya guardada dejaba el cobro desfasado: pasar de Presente a
        Ausente no anulaba el cobro del día, y pasar de Ausente a Presente
        nunca lo generaba. Ahora el cobro sigue al cambio de estado.
        """
        with transaction.atomic():
            anterior   = serializer.instance.estado
            asistencia = serializer.save()
            self._cobro_info = None
            if anterior != asistencia.estado:
                if asistencia.estado == Asistencia.ESTADO_PRESENTE:
                    if self._generar_cobros_por_presencia(asistencia) == 'reactivado':
                        self._cobro_info = {
                            'accion': 'reactivado',
                            'mensaje': 'Se reactivó el cobro del día que se había anulado.'}
                elif anterior == Asistencia.ESTADO_PRESENTE:
                    resultado = self._anular_cobro_diario(asistencia)
                    if resultado == 'anulado':
                        self._cobro_info = {
                            'accion': 'anulado',
                            'mensaje': 'Se anuló el cobro del día porque ya no está presente.'}
                    elif resultado == 'con_pagos':
                        self._cobro_info = {
                            'accion': 'no_anulado',
                            'mensaje': 'El cobro del día NO se anuló porque ya tiene pagos, devoluciones '
                                       'o condonación. Revísalo en Cobros.'}

    def update(self, request, *args, **kwargs):
        self._cobro_info = None
        response = super().update(request, *args, **kwargs)
        if getattr(self, '_cobro_info', None):
            response.data = {**response.data, 'cobro_info': self._cobro_info}
        return response

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

    @action(detail=False, methods=['get'], url_path='historial')
    def historial(self, request):
        """
        Historial de asistencia en un rango de fechas (por defecto, los
        últimos 30 días), filtrable por niño/sala/turno/estado. Alimenta la
        tarjeta "Historial de asistencia" del frontend — antes esa tarjeta
        existía en el HTML pero no tenía ningún endpoint ni función que la
        llenara, así que era imposible ver ausencias o retrasos de un niño
        más allá del día que se tiene cargado en pantalla.

        Respeta el mismo filtro de tutores que el resto del ViewSet: un
        tutor solo puede pedir el historial de su propio hijo (vía `nino`).
        """
        hoy   = date.today()
        desde = request.query_params.get('desde') or (hoy - timedelta(days=30)).isoformat()
        hasta = request.query_params.get('hasta') or hoy.isoformat()
        nino  = request.query_params.get('nino')
        sala  = request.query_params.get('sala')
        turno = request.query_params.get('turno')
        estado = request.query_params.get('estado')

        qs = self.get_queryset().filter(fecha__gte=desde, fecha__lte=hasta)
        if nino:
            qs = qs.filter(inscripcion__nino=nino)
        if sala:
            qs = qs.filter(inscripcion__sala=sala)
        if turno:
            qs = qs.filter(inscripcion__turno=turno)
        if estado:
            qs = qs.filter(estado=estado)
        qs = qs.order_by('-fecha', 'inscripcion__nino__apellidos')[:500]

        serializer = AsistenciaSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    # ── Planilla de asistencia del día ────────────────────────────────
    @staticmethod
    def _url_media(request, archivo):
        """URL absoluta de un ImageField (o None si no hay archivo / falla el storage)."""
        if not archivo:
            return None
        try:
            url = archivo.url
        except Exception:
            return None
        return request.build_absolute_uri(url) if url.startswith('/') else url

    @staticmethod
    def _personas_del_nino(nino, fecha):
        """
        Personas que pueden aparecer como "quién entregó / quién retiró" para
        un niño: sus tutores activos y las personas autorizadas vigentes en
        `fecha`. Cada una lleva `puede_retirar`: un tutor marcado con
        puede_retirar=False sí puede traer al niño, pero no aparece como
        opción de retiro. Se elimina el duplicado si la misma persona figura
        como tutor y como autorizada.
        """
        personas, vistos = [], set()

        def agregar(nombre, parentesco, tipo, puede_retirar):
            clave = ' '.join(nombre.lower().split())
            if not clave or clave in vistos:
                return
            vistos.add(clave)
            personas.append({
                'nombre': nombre, 'parentesco': parentesco,
                'tipo': tipo, 'puede_retirar': puede_retirar,
            })

        relaciones = sorted(nino.tutores.all(), key=lambda nt: not nt.es_principal)
        for nt in relaciones:
            t = nt.tutor
            if t.activo:
                agregar(f'{t.nombres} {t.apellidos}'.strip(), t.get_parentesco_display(),
                        'tutor', nt.puede_retirar)
        for a in nino.autorizados.all():
            vigente = (
                a.activa
                and a.vigencia_desde <= fecha
                and (a.vigencia_hasta is None or a.vigencia_hasta >= fecha)
            )
            if vigente:
                agregar(f'{a.nombres} {a.apellidos}'.strip(), a.parentesco, 'autorizado', True)
        return personas

    @action(detail=False, methods=['get'], url_path='planilla')
    def planilla(self, request):
        """
        Todo lo que la pantalla de asistencia necesita para armar la lista del
        día en UNA sola llamada:

          - `educadoras`: el personal con asignación vigente en la
            sucursal/sala/turno elegidos (titulares primero).
          - `ninos`: los niños con inscripción activa en esos filtros, con su
            foto y la lista de personas que pueden entregarlos/retirarlos
            (para el selector rápido de las tarjetas y del detalle).

        Antes la pantalla traía la inscripción y luego pedía la ficha completa
        del niño cada vez que se abría el detalle; además las educadoras no
        se mostraban en ninguna parte de la asistencia.

        Solo personal del centro: un tutor no debe ver datos de otros niños ni
        de sus autorizados.
        """
        if request.user.rol == 'tutor':
            return Response({'detail': 'No tienes permiso para ver esta información.'},
                            status=status.HTTP_403_FORBIDDEN)

        try:
            fecha = date.fromisoformat(request.query_params.get('fecha') or date.today().isoformat())
        except ValueError:
            return Response({'fecha': 'Formato inválido, usa AAAA-MM-DD.'},
                            status=status.HTTP_400_BAD_REQUEST)
        sucursal = request.query_params.get('sucursal')
        sala     = request.query_params.get('sala')
        turno    = request.query_params.get('turno')

        # ── Educadoras responsables ──
        asignaciones = AsignacionPersonal.objects.select_related(
            'personal__usuario', 'sala', 'turno', 'sucursal'
        ).filter(
            activa=True, personal__activo=True, fecha_inicio__lte=fecha,
        ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha))
        if sucursal:
            asignaciones = asignaciones.filter(sucursal=sucursal)
        if sala:
            asignaciones = asignaciones.filter(sala=sala)
        if turno:
            asignaciones = asignaciones.filter(turno=turno)
        asignaciones = asignaciones.order_by(
            'sala__nombre', 'turno__hora_inicio', '-es_titular', 'personal__usuario__apellidos'
        )
        educadoras = [{
            'id': a.id,
            'personal_id': a.personal_id,
            'nombre': a.personal.usuario.nombre_completo,
            'rol': a.personal.get_rol_display(),
            'es_titular': a.es_titular,
            'foto': self._url_media(request, a.personal.foto),
            'sala': a.sala_id, 'sala_nombre': a.sala.nombre,
            'turno': a.turno_id, 'turno_nombre': a.turno.nombre,
        } for a in asignaciones]

        # ── Niños inscritos ──
        inscripciones = Inscripcion.objects.select_related(
            'nino', 'sala', 'turno'
        ).prefetch_related(
            'nino__tutores__tutor', 'nino__autorizados'
        ).filter(activa=True)
        if sucursal:
            inscripciones = inscripciones.filter(sucursal=sucursal)
        if sala:
            inscripciones = inscripciones.filter(sala=sala)
        if turno:
            inscripciones = inscripciones.filter(turno=turno)
        inscripciones = inscripciones.order_by('nino__apellidos', 'nino__nombres')

        ninos = [{
            'inscripcion': i.id,
            'nino': i.nino_id,
            'nino_nombre': i.nino.nombre_completo,
            'nino_foto': self._url_media(request, i.nino.foto),
            'sala': i.sala_id, 'sala_nombre': i.sala.nombre,
            'turno': i.turno_id, 'turno_nombre': i.turno.nombre,
            'personas': self._personas_del_nino(i.nino, fecha),
        } for i in inscripciones]

        return Response({'fecha': fecha.isoformat(), 'educadoras': educadoras, 'ninos': ninos})
