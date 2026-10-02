"""
inscripciones/views.py
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import reduce
from operator import or_
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Count, Q, Sum
from rest_framework import viewsets, filters, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import PermisoFinanzas, filtrar_por_alcance
from .models import Inscripcion, Cobro, Pago, Devolucion, AbonoDiario, DiasContratados
from .serializers import (
    InscripcionSerializer, InscripcionResumenSerializer, CobroSerializer,
    PagoSerializer, DevolucionSerializer, AbonoDiarioSerializer, validar_dias_semana,
    validar_dias_programados,
)
from .services import (
    generar_ciclo_mensual, calendario_pagos_mensual, calendario_pagos_diario,
    cobro_anterior_pendiente, etiqueta_periodo, asignar_numero_recibo,
    resumen_financiero,
    aplicar_saldo, resumen_diario, registrar_dias_contratados,
    dias_contratados_total, trasladar_cuenta_diaria, deuda_diaria,
    actualizar_dias_programados, DiasProgramadosError,
    ciclo_vigente, calcular_ajuste_precio, continuar_ciclos_en_inscripcion_nueva,
    mover_saldo_disponible, trasladar_saldo_del_nino, deuda_abierta, saldo_a_favor,
    devolver_saldo, SaldoInsuficiente, estado_pago_mensual,
    ESTADOS_ABIERTOS,
)


class InscripcionViewSet(viewsets.ModelViewSet):
    queryset = Inscripcion.objects.select_related(
        'nino', 'sucursal', 'sala', 'turno'
    ).prefetch_related('cobros').all()
    permission_classes = [PermisoFinanzas]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ['nino__nombres', 'nino__apellidos']

    def get_queryset(self):
        # Sin este filtro, cualquier cuenta de tutor podía ver (y, vía las
        # acciones de detalle: cobros-pendientes, calendario-pagos,
        # registrar-pago...) tocar la inscripción de CUALQUIER niño con
        # solo cambiar el id en la URL — no solo la de su propio hijo.
        return filtrar_por_alcance(super().get_queryset(), self.request.user, 'nino')
    filterset_fields   = ['sucursal', 'sala', 'turno', 'modalidad_pago', 'tipo_ajuste', 'activa']

    # Valores del filtro ?estado_pago= (solo aplica a inscripciones activas,
    # que son las únicas con cuenta corriente).
    FILTROS_ESTADO_PAGO = {
        'al_dia':       ('al_dia',),
        'deuda':        ('deuda',),
        'sin_registro': ('sin_dias', 'sin_cobro'),   # aún sin días acordados / sin cobro generado
    }

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.action != 'list':
            return queryset
        valor = self.request.query_params.get('estado_pago')
        if not valor:
            return queryset
        niveles = self.FILTROS_ESTADO_PAGO.get(valor)
        if niveles is None:
            raise ValidationError({'estado_pago': 'Valor no válido (al_dia, deuda o sin_registro).'})
        from .services import estado_pago
        ids = []
        for insc in queryset.filter(activa=True):
            e = estado_pago(insc)
            if e and e['nivel'] in niveles:
                ids.append(insc.id)
        return queryset.filter(id__in=ids)

    def get_serializer_class(self):
        if self.action == 'list':
            return InscripcionResumenSerializer
        return InscripcionSerializer

    def perform_create(self, serializer):
        """
        Al crear una inscripción con modalidad mensual, se genera de una
        vez el primer cobro (el del mes/ciclo en que se está inscribiendo),
        para no obligar a un paso manual aparte. La modalidad diaria no
        necesita esto: su cobro se genera solo al marcar asistencia.
        """
        inscripcion = serializer.save()
        if inscripcion.activa and inscripcion.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
            generar_ciclo_mensual(inscripcion, ciclo_num=0, usuario=self.request.user)
        elif inscripcion.modalidad_pago == Inscripcion.MODALIDAD_DIARIA:
            # Los días acordados salen del calendario; en inscripciones antiguas
            # (sin calendario) se puede mandar a mano `dias_contratados`.
            if inscripcion.dias_programados:
                dias = len(inscripcion.dias_programados)
            else:
                try:
                    dias = int(self.request.data.get('dias_contratados') or 0)
                except (TypeError, ValueError):
                    dias = 0
            if dias > 0:
                registrar_dias_contratados(
                    inscripcion, dias, tipo=DiasContratados.TIPO_INICIAL,
                    nota='Días acordados al inscribir.', usuario=self.request.user)
        if inscripcion.activa:
            # Un niño que vuelve tras una baja: su saldo a favor pasa a la inscripción nueva.
            trasladar_saldo_del_nino(inscripcion, self.request.user)

    @action(detail=True, methods=['post'], url_path='generar-cobro-mensual')
    def generar_cobro_mensual(self, request, pk=None):
        """
        Genera el siguiente cobro de mensualidad de esta inscripción
        (normalmente para renovar el ciclo del mes siguiente; el primer
        ciclo ya se genera solo al crear la inscripción).

        Se puede pasar `ciclo` (entero, 0 = primer mes desde fecha_inicio)
        para generar un ciclo específico de la grilla automática, o
        `periodo_inicio` (fecha YYYY-MM-DD) para arrancar un ciclo nuevo
        con una fecha elegida a mano —pensado para reanudar después de una
        pausa, sin arrastrar los meses en que el niño no vino. Si se manda
        `periodo_inicio`, tiene prioridad sobre `ciclo`.
        """
        inscripcion = self.get_object()

        periodo_inicio_param = request.data.get('periodo_inicio')
        periodo_inicio = None
        if periodo_inicio_param:
            try:
                periodo_inicio = date.fromisoformat(periodo_inicio_param)
            except ValueError:
                return Response({'error': 'La fecha de inicio no es válida, usa formato YYYY-MM-DD.'},
                                 status=status.HTTP_400_BAD_REQUEST)

        ciclo_num = None
        if periodo_inicio is None:
            ciclo_param = request.data.get('ciclo')
            if ciclo_param is not None:
                try:
                    ciclo_num = int(ciclo_param)
                except (TypeError, ValueError):
                    return Response({'error': 'El ciclo debe ser un número entero.'}, status=status.HTTP_400_BAD_REQUEST)

        cobro = generar_ciclo_mensual(
            inscripcion, ciclo_num=ciclo_num, periodo_inicio=periodo_inicio, usuario=request.user
        )
        if cobro is None:
            return Response(
                {'error': 'Ya existe un cobro de mensualidad para ese ciclo.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(CobroSerializer(cobro).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='transferir')
    def transferir(self, request, pk=None):
        """
        Transfiere al niño de esta inscripción a otra sala/turno/sucursal.
        Cierra la inscripción actual (activa=False, fecha_fin) y crea una
        inscripción nueva enlazada, sin dejar nunca dos inscripciones activas
        para el mismo niño al mismo tiempo. El historial de cobros de la
        inscripción anterior se conserva intacto.

        Mensual → mensual con un ciclo en curso: el ciclo NO se duplica. Pasa
        a la inscripción nueva y solo se compensa la diferencia de precio
        contra lo ya pagado: si el turno nuevo cuesta lo mismo no cambia nada;
        si cuesta menos, lo que sobra queda como saldo a favor del niño; si
        cuesta más, el ciclo queda con lo que falta por cobrar (o se cierra
        con lo pagado: `cerrar_con_lo_pagado` + `motivo_cierre`).
        Con `simular=true` solo devuelve qué pasaría, sin cambiar nada.
        """
        from core.models import Sala, Turno, Sucursal

        inscripcion_actual = self.get_object()
        if not inscripcion_actual.activa:
            return Response(
                {'error': 'Esta inscripción ya no está activa; no se puede transferir.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data        = request.data
        sucursal_id = data.get('sucursal', inscripcion_actual.sucursal_id)
        sala_id     = data.get('sala')
        turno_id    = data.get('turno')
        if not sala_id or not turno_id:
            return Response(
                {'error': 'Debes indicar la nueva sala y turno de destino.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            sucursal = Sucursal.objects.get(pk=sucursal_id)
            sala     = Sala.objects.get(pk=sala_id)
            turno    = Turno.objects.get(pk=turno_id)
        except (Sucursal.DoesNotExist, Sala.DoesNotExist, Turno.DoesNotExist):
            return Response({'error': 'Sucursal, sala o turno no válidos.'}, status=status.HTTP_400_BAD_REQUEST)

        if sala.sucursal_id != sucursal.id:
            return Response({'error': 'La sala no pertenece a la sucursal seleccionada.'}, status=status.HTTP_400_BAD_REQUEST)
        if turno.sala_id != sala.id:
            return Response({'error': 'El turno no pertenece a la sala seleccionada.'}, status=status.HTTP_400_BAD_REQUEST)

        # Si es la misma sala+turno actual, no tiene sentido "transferir"
        if sala.id == inscripcion_actual.sala_id and turno.id == inscripcion_actual.turno_id:
            return Response(
                {'error': 'El destino es la misma sala y turno actuales.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar cupo en el destino (sin contar la inscripción que se va a cerrar)
        ocupados = Inscripcion.objects.filter(
            sala=sala, turno=turno, activa=True
        ).exclude(id=inscripcion_actual.id).count()
        if ocupados >= sala.capacidad_maxima:
            return Response(
                {'error': f'La sala {sala.nombre} ya alcanzó su capacidad máxima ({sala.capacidad_maxima} niños).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        hoy = date.today()
        # Se convierte a date: antes quedaba como texto y generar_ciclo_mensual
        # fallaba al transferir hacia una mensualidad (TypeError → 500).
        try:
            fecha_transferencia = (date.fromisoformat(data['fecha_transferencia'])
                                   if data.get('fecha_transferencia') else hoy)
        except ValueError:
            return Response({'error': 'La fecha de transferencia no es válida, usa formato YYYY-MM-DD.'},
                            status=status.HTTP_400_BAD_REQUEST)

        modalidad_destino = data.get('modalidad_pago', inscripcion_actual.modalidad_pago)
        dias_semana_destino = (
            validar_dias_semana(data.get('dias_semana', inscripcion_actual.dias_semana))
            if modalidad_destino == Inscripcion.MODALIDAD_DIARIA else []
        )
        # Calendario: si se mandan fechas nuevas rigen esas; si no, el niño conserva
        # las fechas que aún le quedan por delante en su calendario.
        dias_prog_destino, aviso_calendario = [], None
        if modalidad_destino == Inscripcion.MODALIDAD_DIARIA:
            if data.get('dias_programados'):
                dias_prog_destino = validar_dias_programados(data.get('dias_programados'))
            elif inscripcion_actual.dias_programados:
                dias_prog_destino = [f for f in inscripcion_actual.dias_programados
                                     if f >= fecha_transferencia.isoformat()]
                if not dias_prog_destino:
                    aviso_calendario = ('A su calendario no le quedaban días por delante, así que la nueva '
                                        'inscripción quedó sin días elegidos. Elígelos en su cuenta (Ajustar días).')

        # Precio: si el turno de destino cuesta igual que el actual, la
        # inscripción conserva su precio (incluido un precio negociado) y no
        # hay nada que compensar; si cuesta distinto, rige el del turno nuevo.
        # Un precio indicado explícitamente en la petición manda sobre ambos.
        try:
            costo_mensual = (Decimal(str(data['costo_mensual'])) if data.get('costo_mensual')
                             else inscripcion_actual.costo_mensual if turno.costo_mensual == inscripcion_actual.turno.costo_mensual
                             else turno.costo_mensual)
            costo_diario  = (Decimal(str(data['costo_diario'])) if data.get('costo_diario')
                             else inscripcion_actual.costo_diario if turno.costo_diario == inscripcion_actual.turno.costo_diario
                             else turno.costo_diario)
            ajuste = {
                'tipo_ajuste':       data.get('tipo_ajuste', inscripcion_actual.tipo_ajuste),
                'porcentaje_ajuste': Decimal(str(data.get('porcentaje_ajuste', inscripcion_actual.porcentaje_ajuste))),
                'monto_ajuste':      Decimal(str(data.get('monto_ajuste', inscripcion_actual.monto_ajuste))),
            }
        except InvalidOperation:
            return Response({'error': 'Un monto indicado no es un número válido.'}, status=status.HTTP_400_BAD_REQUEST)

        # ¿Continúa el ciclo mensual en curso? (mensual → mensual con un ciclo vigente)
        continua = (inscripcion_actual.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL
                    and modalidad_destino == Inscripcion.MODALIDAD_MENSUAL)
        vigente = ciclo_vigente(inscripcion_actual, fecha_transferencia) if continua else None
        plan = None
        if vigente:
            precio_nuevo = Inscripcion(costo_mensual=costo_mensual, **ajuste).costo_mensual_final
            plan = calcular_ajuste_precio(vigente, precio_nuevo)
            plan.update({'periodo_inicio': vigente.periodo_inicio, 'periodo_fin': vigente.periodo_fin})

        cerrar = str(data.get('cerrar_con_lo_pagado', '')).lower() in ('1', 'true', 'si', 'sí')
        motivo_cierre = (data.get('motivo_cierre') or '').strip()
        if cerrar and plan and plan['por_cobrar'] > 0 and not motivo_cierre:
            return Response({'error': 'Para cerrar el ciclo con lo pagado debes indicar el motivo.'},
                            status=status.HTTP_400_BAD_REQUEST)

        advertencias = [aviso_calendario] if aviso_calendario else []
        deuda_anterior = deuda_abierta(inscripcion_actual) - (vigente.saldo_pendiente if vigente and vigente.estado in ESTADOS_ABIERTOS else 0)
        if continua and deuda_anterior > 0:
            advertencias.append(
                f'Quedan ciclos anteriores sin pagar por {deuda_anterior} Bs. en la inscripción cerrada; no se transfieren.')

        # Simulación: muestra qué pasaría con el dinero sin cambiar nada.
        if str(data.get('simular', '')).lower() in ('1', 'true', 'si', 'sí'):
            return Response({
                'simulacion': True,
                'continua_ciclo': bool(vigente),
                'ciclo': plan,
                'costo_mensual_nuevo': Inscripcion(costo_mensual=costo_mensual, **ajuste).costo_mensual_final,
                'advertencias': advertencias,
            })

        with transaction.atomic():
            # Cerrar la inscripción actual (el historial de cobros queda intacto, ligado a ella)
            inscripcion_actual.activa    = False
            inscripcion_actual.fecha_fin = fecha_transferencia
            inscripcion_actual.save()

            # Crear la nueva inscripción activa, heredando lo que no se indique explícitamente
            nueva = Inscripcion.objects.create(
                nino                = inscripcion_actual.nino,
                sucursal            = sucursal,
                sala                = sala,
                turno               = turno,
                modalidad_pago      = modalidad_destino,
                fecha_inicio        = fecha_transferencia,
                dias_semana         = dias_semana_destino,
                dias_programados    = dias_prog_destino,
                costo_mensual       = costo_mensual,
                costo_diario        = costo_diario,
                motivo_ajuste       = data.get(
                    'motivo_transferencia',
                    f'Transferido desde {inscripcion_actual.sala} / {inscripcion_actual.turno} el {fecha_transferencia}.'
                ),
                activa              = True,
                inscripcion_origen  = inscripcion_actual,
                **ajuste,
            )
            nueva.refresh_from_db()
            if nueva.dias_programados and inscripcion_actual.modalidad_pago != Inscripcion.MODALIDAD_DIARIA:
                registrar_dias_contratados(
                    nueva, len(nueva.dias_programados), tipo=DiasContratados.TIPO_INICIAL,
                    usuario=request.user, nota='Días elegidos en el calendario al transferir.')

            resultado_ciclo = None
            if inscripcion_actual.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
                mover_saldo_disponible(inscripcion_actual, nueva)   # su saldo a favor sigue siendo suyo
            if nueva.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
                if continua:
                    resultado_ciclo = continuar_ciclos_en_inscripcion_nueva(
                        inscripcion_actual, nueva, fecha_transferencia, request.user, cerrar, motivo_cierre)
                if resultado_ciclo is None:
                    generar_ciclo_mensual(nueva, ciclo_num=0, usuario=request.user)

        respuesta = InscripcionSerializer(nueva).data
        respuesta['advertencias'] = advertencias
        if resultado_ciclo is not None:
            respuesta['transferencia'] = {'continua_ciclo': True, 'ciclo': resultado_ciclo,
                                          'saldo_a_favor': saldo_a_favor(nueva)}
        if inscripcion_actual.modalidad_pago == Inscripcion.MODALIDAD_DIARIA:
            # El saldo a favor y los días acordados del niño no se pierden al transferirlo.
            respuesta['traspaso'] = trasladar_cuenta_diaria(inscripcion_actual, nueva, request.user)
        return Response(respuesta, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='devolver-saldo')
    def devolver_saldo_action(self, request, pk=None):
        """
        Devuelve al tutor parte o todo el SALDO A FAVOR de la cuenta del niño
        (dinero que no se aplicó a ningún cobro). Es una devolución como las de
        siempre: lleva recibo y sale de caja. Funciona también en inscripciones
        cerradas (el caso típico: el niño se dio de baja y dejó saldo).

        Body: `monto` (hasta el saldo disponible), `motivo` (obligatorio),
        `metodo_pago` (efectivo | transferencia | qr) y `fecha` (opcional).
        """
        inscripcion = self.get_object()
        try:
            monto = Decimal(str(request.data.get('monto')))
        except (InvalidOperation, TypeError):
            return Response({'error': 'El monto no es un número válido.'}, status=status.HTTP_400_BAD_REQUEST)
        motivo = (request.data.get('motivo') or '').strip()
        if not motivo:
            return Response({'error': 'Indica el motivo de la devolución.'}, status=status.HTTP_400_BAD_REQUEST)
        metodo = request.data.get('metodo_pago', Cobro.METODO_EFECTIVO)
        if metodo not in dict(Cobro.METODOS_PAGO):
            return Response({'error': 'Método de pago no válido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            fecha = date.fromisoformat(request.data['fecha']) if request.data.get('fecha') else date.today()
        except ValueError:
            return Response({'error': 'La fecha no es válida, usa formato YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            dev = devolver_saldo(inscripcion, monto, metodo, motivo, request.user, fecha)
        except SaldoInsuficiente as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'devolucion': DevolucionSerializer(dev).data,
            'saldo_a_favor': saldo_a_favor(inscripcion),
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cerrar')
    def cerrar(self, request, pk=None):
        """
        Da de baja al niño (ya no viene). Cierra la inscripción (activa=False,
        fecha_fin); si regresa más adelante se crea una inscripción nueva y
        el saldo a favor que haya dejado pasa a ella.

        Body (todo opcional): `fecha_fin` (por defecto hoy), `motivo`,
        `cerrar_con_lo_pagado` + `motivo_cierre`, `devolver_saldo` (devuelve
        de una vez todo el saldo a favor, con `metodo_pago`).

        - Mensualidades de ciclos futuros que nadie pagó se anulan; si ya
          tienen pagos se avisa (habría que devolver ese dinero).
        - El ciclo en curso queda como estaba; con `cerrar_con_lo_pagado` se
          da por saldado con lo que ya se pagó (misma condonación de "Cerrar
          con lo pagado"; exige `motivo_cierre`).
        - Los cobros anteriores sin pagar siguen siendo deuda de la inscripción
          cerrada: se informan, no se borran.
        - La respuesta informa la deuda pendiente y el saldo a favor.
        """
        inscripcion = self.get_object()
        if not inscripcion.activa:
            return Response({'error': 'Esta inscripción ya está cerrada.'}, status=status.HTTP_400_BAD_REQUEST)
        data = request.data
        try:
            fecha_fin = date.fromisoformat(data['fecha_fin']) if data.get('fecha_fin') else date.today()
        except ValueError:
            return Response({'error': 'La fecha no es válida, usa formato YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        if fecha_fin < inscripcion.fecha_inicio:
            return Response({'error': 'La baja no puede ser anterior al inicio de la inscripción.'},
                            status=status.HTTP_400_BAD_REQUEST)
        cerrar_pagado = str(data.get('cerrar_con_lo_pagado', '')).lower() in ('1', 'true', 'si', 'sí')
        motivo_cierre = (data.get('motivo_cierre') or '').strip()
        if cerrar_pagado and not motivo_cierre:
            return Response({'error': 'Para cerrar el ciclo con lo pagado debes indicar el motivo.'},
                            status=status.HTTP_400_BAD_REQUEST)

        advertencias, anulados, condonado = [], 0, 0
        with transaction.atomic():
            if inscripcion.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
                # Ciclos que empiezan después de la baja
                for futuro in Cobro.objects.filter(
                    inscripcion=inscripcion, tipo=Cobro.TIPO_MENSUALIDAD, periodo_inicio__gt=fecha_fin,
                ).exclude(estado=Cobro.ESTADO_ANULADO):
                    if futuro.pagos.exists() or futuro.monto_condonado > 0:
                        advertencias.append(
                            f'El ciclo {etiqueta_periodo(futuro)} ya tiene pagos y no se anuló: '
                            'revísalo en Cobros (puede requerir una devolución).')
                        continue
                    futuro.estado = Cobro.ESTADO_ANULADO
                    futuro.observacion = (f'{futuro.observacion}\n' if futuro.observacion else '') + \
                        f'Anulado automáticamente: baja el {fecha_fin:%d/%m/%Y}.'
                    futuro.save(update_fields=['estado', 'observacion'])
                    anulados += 1
                if cerrar_pagado:
                    actual = ciclo_vigente(inscripcion, fecha_fin)
                    if actual and actual.estado in ESTADOS_ABIERTOS and actual.saldo_pendiente > 0:
                        condonado = actual.saldo_pendiente
                        actual.monto_condonado = actual.monto_condonado_inicial = condonado
                        actual.motivo_condonacion = motivo_cierre
                        actual.registrado_por = request.user
                        actual.save(update_fields=['monto_condonado', 'monto_condonado_inicial',
                                                   'motivo_condonacion', 'registrado_por'])
                        actual.recalcular_estado()

            nota = f'Baja el {fecha_fin:%d/%m/%Y}.' + (f' {data["motivo"]}' if data.get('motivo') else '')
            inscripcion.activa = False
            inscripcion.fecha_fin = fecha_fin
            inscripcion.motivo_ajuste = (f'{inscripcion.motivo_ajuste}\n{nota}'.strip()
                                         if inscripcion.motivo_ajuste else nota)
            inscripcion.save()

        devolucion = None
        if str(data.get('devolver_saldo', '')).lower() in ('1', 'true', 'si', 'sí') and saldo_a_favor(inscripcion) > 0:
            metodo = data.get('metodo_pago', Cobro.METODO_EFECTIVO)
            devolucion = devolver_saldo(
                inscripcion, saldo_a_favor(inscripcion),
                metodo if metodo in dict(Cobro.METODOS_PAGO) else Cobro.METODO_EFECTIVO,
                f'Baja del {fecha_fin:%d/%m/%Y}: devolución del saldo a favor.', request.user)
        deuda, saldo = deuda_abierta(inscripcion), saldo_a_favor(inscripcion)
        if deuda > 0:
            advertencias.append(f'Quedan cobros sin pagar por {deuda} Bs. en esta inscripción cerrada.')
        if saldo > 0:
            advertencias.append(
                f'El niño deja {saldo} Bs. de saldo a favor: si vuelve, pasarán a su nueva inscripción. '
                'Si prefieres devolverlos, usa "Devolver saldo" en su panel de pagos.')
        return Response({
            'inscripcion':       InscripcionSerializer(inscripcion).data,
            'deuda_pendiente':   deuda,
            'saldo_a_favor':     saldo,
            'ciclos_anulados':   anulados,
            'monto_condonado':   condonado,
            'devolucion':        DevolucionSerializer(devolucion).data if devolucion else None,
            'advertencias':      advertencias,
        })

    @action(detail=True, methods=['get'], url_path='cobros-pendientes')
    def cobros_pendientes(self, request, pk=None):
        """Lista los cobros pendientes, parciales y vencidos de esta inscripción."""
        inscripcion = self.get_object()
        cobros = inscripcion.cobros.filter(
            estado__in=[Cobro.ESTADO_PENDIENTE, Cobro.ESTADO_PARCIAL, Cobro.ESTADO_VENCIDO]
        ).order_by('fecha_vencimiento')
        serializer = CobroSerializer(cobros, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='calendario-pagos')
    def calendario_pagos(self, request, pk=None):
        """
        Todo lo necesario para pintar la vista visual de "Pagos" de esta
        inscripción en una sola llamada: si es modalidad mensual, devuelve
        los ciclos mes a mes; si es diaria, el calendario del mes pedido
        (por defecto el mes actual, o ?anio=YYYY&mes=M).
        """
        inscripcion = self.get_object()

        if inscripcion.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
            return Response({
                'modalidad': 'mensual',
                'ciclos':    calendario_pagos_mensual(inscripcion),
                'saldo_a_favor': saldo_a_favor(inscripcion),   # lo que sobró de un cambio de turno, p. ej.
                'cuenta':    estado_pago_mensual(inscripcion),
            })

        hoy  = date.today()
        anio = int(request.query_params.get('anio', hoy.year))
        mes  = int(request.query_params.get('mes', hoy.month))
        if not (1 <= mes <= 12):
            return Response({'error': 'El mes debe estar entre 1 y 12.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'modalidad':  'diaria',
            'calendario': calendario_pagos_diario(inscripcion, anio, mes),
            'resumen':    resumen_diario(inscripcion),
        })

    # ── Modalidad "por día": abonos, días acordados y cambio de modalidad ──
    def _exigir_diaria(self, inscripcion):
        if inscripcion.modalidad_pago != Inscripcion.MODALIDAD_DIARIA:
            return Response({'error': 'Esta acción solo aplica a inscripciones con modalidad por día.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return None

    @action(detail=True, methods=['get'], url_path='resumen-diario')
    def resumen_diario_action(self, request, pk=None):
        """Saldo a favor, deuda, días acordados vs cobrados, abonos y alertas."""
        inscripcion = self.get_object()
        error = self._exigir_diaria(inscripcion)
        return error or Response(resumen_diario(inscripcion))

    @action(detail=True, methods=['post'], url_path='registrar-abono')
    def registrar_abono(self, request, pk=None):
        """
        El tutor entrega dinero para los días de asistencia de su hijo, por
        adelantado o después de que ya hubo días cobrados. El monto queda
        como saldo a favor y se aplica solo a los cobros diarios, del más
        antiguo al más nuevo (los días futuros se irán cubriendo a medida
        que se marque asistencia).

        Body: monto (obligatorio), metodo_pago, fecha_pago, observacion, y
        `dias` (opcional): cuántos días acordados cubre este abono; se anota
        como días iniciales o como ampliación en el control de días.
        """
        inscripcion = self.get_object()
        error = self._exigir_diaria(inscripcion)
        if error:
            return error

        try:
            monto = Decimal(str(request.data.get('monto')))
        except (InvalidOperation, TypeError):
            return Response({'error': 'El monto no es un número válido.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto <= 0:
            return Response({'error': 'El monto del abono debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto >= Decimal('1000000'):
            return Response({'error': 'El monto es demasiado grande.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fecha_pago = date.fromisoformat(request.data['fecha_pago']) if request.data.get('fecha_pago') else date.today()
        except ValueError:
            return Response({'error': 'La fecha no es válida, usa formato YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        dias = 0
        if request.data.get('dias') not in (None, '', 0, '0'):
            try:
                dias = int(request.data.get('dias'))
            except (TypeError, ValueError):
                return Response({'error': 'Los días deben ser un número entero.'}, status=status.HTTP_400_BAD_REQUEST)
            if dias < 0:
                return Response({'error': 'Los días no pueden ser negativos.'}, status=status.HTTP_400_BAD_REQUEST)

        metodo = request.data.get('metodo_pago', Cobro.METODO_EFECTIVO)
        if metodo not in dict(Cobro.METODOS_PAGO):
            return Response({'error': 'Método de pago no válido.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            abono = AbonoDiario.objects.create(
                inscripcion=inscripcion, monto=monto, fecha_pago=fecha_pago, metodo_pago=metodo,
                observacion=request.data.get('observacion', ''), registrado_por=request.user,
            )
            asignar_numero_recibo(abono)
            aplicado = aplicar_saldo(inscripcion)
            # Con calendario, los días acordados son los días elegidos en él:
            # un abono no los modifica (antes se sumaban encima y el contador
            # quedaba desfasado). Solo las inscripciones antiguas, sin
            # calendario, siguen anotando los días del abono.
            if dias > 0 and not inscripcion.dias_programados:
                registrar_dias_contratados(
                    inscripcion, dias, nota=f'Abono de {monto} Bs. del {fecha_pago:%d/%m/%Y}.', usuario=request.user)

        abono.refresh_from_db()
        return Response({
            'abono':         AbonoDiarioSerializer(abono).data,
            'aplicado_a_dias_pendientes': aplicado,
            'resumen':       resumen_diario(inscripcion),
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='contratar-dias')
    def contratar_dias(self, request, pk=None):
        """
        Anota un cambio en los días acordados con el tutor, sin que medie un
        pago: `tipo` = ampliacion | reduccion (| inicial si aún no hay),
        `cantidad` (> 0) y `nota` opcional. Queda en el historial.
        """
        inscripcion = self.get_object()
        error = self._exigir_diaria(inscripcion)
        if error:
            return error
        try:
            cantidad = int(request.data.get('cantidad'))
        except (TypeError, ValueError):
            return Response({'error': 'La cantidad debe ser un número entero.'}, status=status.HTTP_400_BAD_REQUEST)
        if cantidad <= 0:
            return Response({'error': 'La cantidad de días debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
        tipo = request.data.get('tipo') or DiasContratados.TIPO_AMPLIACION
        if tipo not in dict(DiasContratados.TIPOS):
            return Response({'error': 'Tipo no válido (inicial, ampliacion o reduccion).'}, status=status.HTTP_400_BAD_REQUEST)
        if tipo == DiasContratados.TIPO_REDUCCION and cantidad > dias_contratados_total(inscripcion):
            return Response({'error': 'No se puede reducir más de los días contratados.'}, status=status.HTTP_400_BAD_REQUEST)
        registrar_dias_contratados(
            inscripcion, cantidad, tipo=tipo, nota=request.data.get('nota', ''), usuario=request.user)
        return Response(resumen_diario(inscripcion), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='actualizar-dias')
    def actualizar_dias(self, request, pk=None):
        """
        Cambia los días del calendario de una inscripción por día (aumentar o
        disminuir). Body: `dias` (lista completa de fechas YYYY-MM-DD que
        quedan elegidas) y `nota` opcional. Lo agregado se anota como
        ampliación y lo quitado como reducción en el historial de días
        acordados; no se puede quitar un día que ya tiene asistencia o cobro.
        """
        inscripcion = self.get_object()
        error = self._exigir_diaria(inscripcion)
        if error:
            return error
        dias = validar_dias_programados(request.data.get('dias'))
        try:
            agregadas, quitadas = actualizar_dias_programados(
                inscripcion, dias, nota=(request.data.get('nota') or '').strip(), usuario=request.user)
        except DiasProgramadosError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        inscripcion.refresh_from_db()
        return Response({
            'agregadas': agregadas, 'quitadas': quitadas,
            'inscripcion': InscripcionSerializer(inscripcion).data,
            'resumen': resumen_diario(inscripcion),
        })

    @action(detail=True, methods=['post'], url_path='cambiar-modalidad')
    def cambiar_modalidad(self, request, pk=None):
        """
        Pasa al niño de por día a mensual (o al revés) en la misma sala y
        turno. Igual que `transferir`, no edita la inscripción: la cierra
        (activa=False, fecha_fin) y crea una nueva enlazada, así el
        historial de cobros, pagos, descuentos y recibos queda intacto.

        Body (todo opcional): `modalidad` (por defecto la opuesta),
        `fecha_inicio` (por defecto hoy), `costo_mensual`/`costo_diario`
        (por defecto los de la inscripción actual, respetando precios
        negociados), `dias_semana` (si el destino es por día) y `motivo`.

        - El ajuste (beca/descuento) se hereda.
        - De por día a mensual, el saldo a favor se aplica a la primera
          mensualidad; lo que sobre queda en la inscripción cerrada.
        - Los días cobrados sin pagar siguen en la inscripción cerrada (no
          bloquean la mensualidad) y se informan en `traspaso`.
        """
        actual = self.get_object()
        if not actual.activa:
            return Response({'error': 'Esta inscripción ya no está activa; no se puede cambiar de modalidad.'},
                            status=status.HTTP_400_BAD_REQUEST)
        data = request.data

        destino = data.get('modalidad') or (
            Inscripcion.MODALIDAD_MENSUAL if actual.modalidad_pago == Inscripcion.MODALIDAD_DIARIA
            else Inscripcion.MODALIDAD_DIARIA)
        if destino not in (Inscripcion.MODALIDAD_MENSUAL, Inscripcion.MODALIDAD_DIARIA):
            return Response({'error': 'Modalidad no válida.'}, status=status.HTTP_400_BAD_REQUEST)
        if destino == actual.modalidad_pago:
            return Response({'error': 'La inscripción ya tiene esa modalidad.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fecha_inicio = date.fromisoformat(data['fecha_inicio']) if data.get('fecha_inicio') else date.today()
        except ValueError:
            return Response({'error': 'La fecha no es válida, usa formato YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        if fecha_inicio < actual.fecha_inicio:
            return Response({'error': 'La nueva modalidad no puede empezar antes que la inscripción actual.'},
                            status=status.HTTP_400_BAD_REQUEST)

        dias_semana = (validar_dias_semana(data.get('dias_semana', []))
                       if destino == Inscripcion.MODALIDAD_DIARIA else [])
        # Por día con calendario: el primer día es la primera fecha elegida.
        dias_prog = (validar_dias_programados(data.get('dias_programados'))
                     if destino == Inscripcion.MODALIDAD_DIARIA else [])
        if dias_prog:
            fecha_inicio = date.fromisoformat(dias_prog[0])
            if fecha_inicio < actual.fecha_inicio:
                return Response({'error': 'La nueva modalidad no puede empezar antes que la inscripción actual.'},
                                status=status.HTTP_400_BAD_REQUEST)
        nota = f'Cambio de modalidad ({actual.get_modalidad_pago_display()} → ' \
               f'{dict(Inscripcion.MODALIDADES)[destino]}) el {fecha_inicio:%d/%m/%Y}.'
        if data.get('motivo'):
            nota += f' {data["motivo"]}'

        advertencias = []
        if actual.modalidad_pago == Inscripcion.MODALIDAD_DIARIA and Cobro.objects.filter(
            inscripcion=actual, tipo=Cobro.TIPO_DIARIO, fecha_vencimiento=fecha_inicio
        ).exclude(estado=Cobro.ESTADO_ANULADO).exists():
            advertencias.append(
                f'El {fecha_inicio:%d/%m/%Y} ya tiene un día cobrado en la modalidad por día y también '
                'será el primer día de la mensualidad. Si no quieres cobrarlo dos veces, elige el día siguiente.')

        with transaction.atomic():
            actual.activa = False
            actual.fecha_fin = max(fecha_inicio - relativedelta(days=1), actual.fecha_inicio)
            actual.save()

            nueva = Inscripcion.objects.create(
                nino=actual.nino, sucursal=actual.sucursal, sala=actual.sala, turno=actual.turno,
                modalidad_pago=destino, fecha_inicio=fecha_inicio, dias_semana=dias_semana,
                dias_programados=dias_prog,
                costo_mensual=data.get('costo_mensual') or actual.costo_mensual,
                costo_diario=data.get('costo_diario') or actual.costo_diario,
                tipo_ajuste=actual.tipo_ajuste, porcentaje_ajuste=actual.porcentaje_ajuste,
                monto_ajuste=actual.monto_ajuste,
                motivo_ajuste=(f'{actual.motivo_ajuste}\n{nota}'.strip() if actual.motivo_ajuste else nota),
                activa=True, inscripcion_origen=actual,
            )
            if destino == Inscripcion.MODALIDAD_MENSUAL:
                generar_ciclo_mensual(nueva, ciclo_num=0, usuario=request.user)
            traspaso = trasladar_cuenta_diaria(actual, nueva, request.user)
            if dias_prog:
                registrar_dias_contratados(
                    nueva, len(dias_prog), tipo=DiasContratados.TIPO_INICIAL, usuario=request.user,
                    nota='Días elegidos en el calendario al cambiar de modalidad.')

        traspaso['deuda_dias_pendientes'] = deuda_diaria(actual) if actual.modalidad_pago == Inscripcion.MODALIDAD_DIARIA else 0
        if traspaso['saldo_restante'] > 0 and destino == Inscripcion.MODALIDAD_MENSUAL:
            advertencias.append(
                f'Quedó un saldo a favor de {traspaso["saldo_restante"]} Bs. sin aplicar (la mensualidad ya estaba cubierta). '
                'Queda en su cuenta y cubrirá las próximas mensualidades.')
        if traspaso['deuda_dias_pendientes'] > 0:
            advertencias.append(
                f'Quedan días cobrados sin pagar por {traspaso["deuda_dias_pendientes"]} Bs. en la inscripción por día cerrada.')
        return Response({
            'inscripcion': InscripcionSerializer(nueva).data,
            'traspaso':    traspaso,
            'advertencias': advertencias,
        }, status=status.HTTP_201_CREATED)


class CobroViewSet(viewsets.ModelViewSet):
    queryset = Cobro.objects.select_related(
        'inscripcion__nino', 'inscripcion__sucursal', 'registrado_por'
    ).all()
    serializer_class   = CobroSerializer
    permission_classes = [PermisoFinanzas]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['inscripcion', 'tipo', 'estado', 'metodo_pago',
                          'inscripcion__sucursal', 'inscripcion__sala']
    ordering_fields    = ['fecha_emision', 'fecha_vencimiento', 'monto_final']
    ordering           = ['-fecha_emision']

    def get_queryset(self):
        # Mismo motivo que en InscripcionViewSet: sin esto, un tutor podía
        # leer (y, vía registrar-pago/registrar-devolucion/cerrar-con-lo-
        # pagado si alguna vez se relaja el permiso de escritura) el cobro
        # de cualquier niño, no solo el suyo.
        return filtrar_por_alcance(super().get_queryset(), self.request.user, 'inscripcion__nino')

    # ── Estadísticas y movimientos de caja ────────────────────────────────
    # Se calculan aquí (servidor) y no en el navegador: la paginación de DRF
    # ignora `page_size` (fija 25), así que sumar desde el front truncaba los
    # totales en cuanto había más de 25 cobros.
    ROLES_CAJA = ('admin', 'directora', 'recepcionista')

    def _exigir_rol_caja(self, request):
        if request.user.rol not in self.ROLES_CAJA:
            raise PermissionDenied('No tienes permiso para ver la caja.')

    @action(detail=False, methods=['get'], url_path='resumen')
    def resumen(self, request):
        """
        Tarjetas de la pantalla de Cobros.
        - pendiente: saldo por cobrar de todos los cobros abiertos (pendiente,
          parcial o vencido), NO anulados, ya descontando pagos, devoluciones
          y condonado. Incluye a los vencidos.
        - vencido: la parte de lo pendiente cuyo vencimiento ya pasó.
        - mes: caja real del mes = pagos con fecha del mes - devoluciones con
          fecha del mes (en cualquier cobro, sin importar su estado).
        Parámetros opcionales: `mes` (YYYY-MM, por defecto el actual), `sucursal`.
        """
        self._exigir_rol_caja(request)
        hoy = date.today()
        sucursal = request.query_params.get('sucursal')
        try:
            anio, mes = (int(x) for x in (request.query_params.get('mes') or hoy.strftime('%Y-%m')).split('-'))
            date(anio, mes, 1)
        except (ValueError, TypeError):
            return Response({'error': 'El mes debe tener formato YYYY-MM.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resumen_financiero(anio, mes, sucursal))

    @action(detail=False, methods=['get'], url_path='movimientos')
    def movimientos(self, request):
        """
        Libro de caja: pagos (ingresos) y devoluciones (egresos) mezclados en
        orden cronológico inverso, con totales de TODO el filtro (no solo de
        la página). Filtros: desde, hasta (YYYY-MM-DD), tipo (pago|devolucion),
        metodo_pago, sucursal, search (nombre del niño). Paginado con
        `page` y `page_size` (máx. 100).
        """
        self._exigir_rol_caja(request)
        qp = request.query_params
        try:
            desde = date.fromisoformat(qp['desde']) if qp.get('desde') else None
            hasta = date.fromisoformat(qp['hasta']) if qp.get('hasta') else None
            page      = max(int(qp.get('page', 1)), 1)
            page_size = min(max(int(qp.get('page_size', 25)), 1), 100)
        except ValueError:
            return Response({'error': 'Fechas (YYYY-MM-DD) o paginación inválidas.'},
                            status=status.HTTP_400_BAD_REQUEST)
        tipo, metodo = qp.get('tipo', ''), qp.get('metodo_pago', '')
        sucursal, search = qp.get('sucursal', ''), qp.get('search', '').strip()

        def filtrar(qs, campo_fecha, via='cobro__inscripcion', tambien=None):
            # `tambien`: segundo camino hacia la inscripción (las devoluciones del
            # saldo a favor cuelgan de la inscripción, no de un cobro).
            vias = [via] + ([tambien] if tambien else [])
            if desde:    qs = qs.filter(**{f'{campo_fecha}__gte': desde})
            if hasta:    qs = qs.filter(**{f'{campo_fecha}__lte': hasta})
            if metodo:   qs = qs.filter(metodo_pago=metodo)
            if sucursal: qs = qs.filter(reduce(or_, [Q(**{f'{v}__sucursal': sucursal}) for v in vias]))
            for palabra in search.split():
                qs = qs.filter(reduce(or_, [
                    Q(**{f'{v}__nino__{campo}__icontains': palabra})
                    for v in vias for campo in ('nombres', 'apellidos')]))
            return qs

        rel = ('cobro__inscripcion__nino', 'registrado_por')
        # Un Pago con abono_origen es la aplicación de un abono ya contado:
        # el ingreso de caja es el AbonoDiario (ver más abajo), no sus aplicaciones.
        pagos  = filtrar(Pago.objects.select_related(*rel).filter(abono_origen__isnull=True), 'fecha_pago')
        abonos = filtrar(AbonoDiario.objects.select_related('inscripcion__nino', 'registrado_por').filter(es_traspaso=False),
                         'fecha_pago', via='inscripcion')
        devs   = filtrar(Devolucion.objects.select_related(*rel, 'inscripcion__nino').filter(a_cuenta=False),
                         'fecha', tambien='inscripcion')
        if tipo == 'pago':
            devs = devs.none()
        elif tipo == 'devolucion':
            pagos  = pagos.none()
            abonos = abonos.none()

        cero = Decimal('0')
        tp = pagos.aggregate(t=Sum('monto'), n=Count('id'))
        ta = abonos.aggregate(t=Sum('monto'), n=Count('id'))
        tp = {'t': (tp['t'] or cero) + (ta['t'] or cero), 'n': (tp['n'] or 0) + (ta['n'] or 0)}
        td = devs.aggregate(t=Sum('monto'), n=Count('id'))
        por_metodo = {}
        for m, _ in Cobro.METODOS_PAGO:
            por_metodo[m] = {'ingresos': cero, 'devoluciones': cero, 'neto': cero}
        for fila in list(pagos.values('metodo_pago').annotate(t=Sum('monto'))) + \
                    list(abonos.values('metodo_pago').annotate(t=Sum('monto'))):
            fila_m = por_metodo.setdefault(fila['metodo_pago'], {'ingresos': cero, 'devoluciones': cero, 'neto': cero})
            fila_m['ingresos'] += fila['t']
        for fila in devs.values('metodo_pago').annotate(t=Sum('monto')):
            por_metodo.setdefault(fila['metodo_pago'], {'ingresos': cero, 'devoluciones': cero, 'neto': cero})['devoluciones'] = fila['t']
        for v in por_metodo.values():
            v['neto'] = v['ingresos'] - v['devoluciones']

        # Se traen solo las filas necesarias de cada lado (hasta el final de la
        # página pedida) y se mezclan por fecha.
        limite = page * page_size
        filas = []
        for x in pagos.order_by('-fecha_pago', '-created_at')[:limite]:
            filas.append(('pago', x, x.fecha_pago, x.observacion))
        for x in abonos.order_by('-fecha_pago', '-created_at')[:limite]:
            filas.append(('abono', x, x.fecha_pago, x.observacion))
        for x in devs.order_by('-fecha', '-created_at')[:limite]:
            filas.append(('devolucion', x, x.fecha, x.motivo))
        filas.sort(key=lambda f: (f[2], f[1].created_at), reverse=True)
        pagina = filas[(page - 1) * page_size: page * page_size]

        results = []
        for kind, x, fecha, detalle in pagina:
            es_abono = kind == 'abono'
            cobro_x = None if es_abono else x.cobro          # None: abono o devolución del saldo a favor
            insc = cobro_x.inscripcion if cobro_x else x.inscripcion
            results.append({
                'tipo':           'pago' if es_abono else kind,   # el abono es un ingreso más
                'es_abono':       es_abono,
                'id':             str(x.id),
                'fecha':          fecha.isoformat(),
                'monto':          x.monto,
                'nino_nombre':    insc.nino.nombre_completo,
                'concepto':       ('Abono por adelantado (por día)' if es_abono
                                   else f'{cobro_x.get_tipo_display()} {cobro_x.periodo}'.strip() if cobro_x
                                   else 'Devolución del saldo a favor'),
                'metodo_pago':    x.metodo_pago,
                'metodo_display': x.get_metodo_pago_display(),
                'detalle':        detalle,
                'numero_recibo':  x.numero_recibo,
                'registrado_por': x.registrado_por.nombre_completo if x.registrado_por else None,
            })

        count = (tp['n'] or 0) + (td['n'] or 0)
        return Response({
            'count': count, 'page': page, 'page_size': page_size,
            'total_pages': max((count + page_size - 1) // page_size, 1),
            'results': results,
            'totales': {
                'ingresos':              tp['t'] or cero,
                'cantidad_pagos':        tp['n'],
                'devoluciones':          td['t'] or cero,
                'cantidad_devoluciones': td['n'],
                'neto':                  (tp['t'] or cero) - (td['t'] or cero),
                'por_metodo':            por_metodo,
            },
        })

    @action(detail=True, methods=['post'], url_path='registrar-pago')
    def registrar_pago(self, request, pk=None):
        """
        Registra un abono/cuota sobre este cobro. Puede ser el pago completo
        o un pago parcial: se acepta un `monto` explícito (si no se manda,
        se asume que se está cubriendo TODO el saldo pendiente, para no
        romper compatibilidad con quien ya llamaba este endpoint sin monto).

        Un mismo cobro puede recibir varios pagos parciales hasta llegar a
        monto_final (ej. 2 pagos de 200 sobre una mensualidad de 650: el
        cobro queda en estado "parcial" con saldo_pendiente = 250).
        """
        cobro = self.get_object()
        if cobro.estado == Cobro.ESTADO_ANULADO:
            return Response({'error': 'Este cobro está anulado, no se le pueden registrar pagos.'},
                             status=status.HTTP_400_BAD_REQUEST)
        if cobro.saldo_pendiente <= 0:
            return Response({'error': 'Este cobro ya está cubierto por completo.'},
                             status=status.HTTP_400_BAD_REQUEST)

        anterior = cobro_anterior_pendiente(cobro)
        if anterior:
            return Response({
                'error': f'Primero hay que cerrar {etiqueta_periodo(anterior)}, que sigue abierto. '
                         'Los cobros se cierran en orden.'
            }, status=status.HTTP_400_BAD_REQUEST)

        monto_raw = request.data.get('monto')
        if monto_raw in (None, ''):
            monto = cobro.saldo_pendiente  # comportamiento anterior: pagar todo lo que falta
        else:
            try:
                monto = Decimal(str(monto_raw))
            except InvalidOperation:
                return Response({'error': 'El monto no es un número válido.'}, status=status.HTTP_400_BAD_REQUEST)

        if monto <= 0:
            return Response({'error': 'El monto del pago debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto > cobro.saldo_pendiente:
            return Response(
                {'error': f'El monto ({monto}) supera el saldo pendiente ({cobro.saldo_pendiente}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pago = Pago.objects.create(
            cobro          = cobro,
            monto          = monto,
            fecha_pago     = request.data.get('fecha_pago') or date.today(),
            metodo_pago    = request.data.get('metodo_pago', Cobro.METODO_EFECTIVO),
            observacion    = request.data.get('observacion', ''),
            registrado_por = request.user,
        )
        asignar_numero_recibo(pago)

        # Reflejar el último pago también en el propio Cobro (compatibilidad con reportes)
        cobro.fecha_pago  = pago.fecha_pago
        cobro.metodo_pago = pago.metodo_pago
        cobro.save(update_fields=['fecha_pago', 'metodo_pago'])
        cobro.recalcular_estado()
        cobro.refresh_from_db()

        return Response(CobroSerializer(cobro).data)

    @action(detail=True, methods=['post'], url_path='cerrar-con-lo-pagado')
    def cerrar_con_lo_pagado(self, request, pk=None):
        """
        Da por saldado el cobro con lo que ya se pagó, condonando el resto.
        Útil cuando por alguna circunstancia (acuerdo con la familia, caso
        social, error de cobro, etc.) se decide que la mensualidad queda
        "pagada" aunque no se haya cubierto el 100% del monto original.
        Requiere `motivo`. Queda registrado el monto condonado para auditoría.
        """
        cobro = self.get_object()
        if cobro.estado in (Cobro.ESTADO_PAGADO, Cobro.ESTADO_ANULADO):
            return Response({'error': 'Este cobro ya está cerrado (pagado o anulado).'},
                             status=status.HTTP_400_BAD_REQUEST)

        anterior = cobro_anterior_pendiente(cobro)
        if anterior:
            return Response({
                'error': f'Primero hay que cerrar {etiqueta_periodo(anterior)}, que sigue abierto. '
                         'Los cobros se cierran en orden.'
            }, status=status.HTTP_400_BAD_REQUEST)

        motivo = request.data.get('motivo', '').strip()
        if not motivo:
            return Response({'error': 'Debes indicar el motivo para cerrar el cobro con lo pagado.'},
                             status=status.HTTP_400_BAD_REQUEST)

        cobro.monto_condonado         = cobro.saldo_pendiente
        cobro.monto_condonado_inicial = cobro.saldo_pendiente
        cobro.motivo_condonacion      = motivo
        cobro.registrado_por          = request.user
        cobro.save(update_fields=[
            'monto_condonado', 'monto_condonado_inicial',
            'motivo_condonacion', 'registrado_por',
        ])
        cobro.recalcular_estado()
        cobro.refresh_from_db()

        return Response(CobroSerializer(cobro).data)

    @action(detail=True, methods=['post'], url_path='registrar-devolucion')
    def registrar_devolucion(self, request, pk=None):
        """
        Registra una devolución de dinero sobre este cobro (ej. se cobró de
        más, la familia se dio de baja y hay saldo a favor, un error de
        cobro). Resta de lo pagado: si el cobro estaba "pagado" por pago
        real (sin condonación) y se devuelve una parte, recalcular_estado()
        lo reabre solo — y a partir de ahí vuelve a aplicar la regla de
        "cerrar en orden" con los cobros posteriores, como corresponde.

        Excepción: si el cobro ya se había cerrado con "Cerrar con lo
        pagado" (monto_condonado > 0), la devolución NO reabre el mes —
        el monto condonado se incrementa en el mismo monto devuelto para
        que el mes se mantenga "pagado" (ver ajuste más abajo).

        No se puede devolver más de lo que efectivamente se pagó (lo
        condonado nunca fue dinero real, no hay nada que devolver de eso).
        Requiere `motivo`.
        """
        cobro = self.get_object()

        monto_raw = request.data.get('monto')
        try:
            monto = Decimal(str(monto_raw))
        except (InvalidOperation, TypeError):
            return Response({'error': 'El monto no es un número válido.'}, status=status.HTTP_400_BAD_REQUEST)

        if monto <= 0:
            return Response({'error': 'El monto a devolver debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto > cobro.monto_pagado:
            return Response(
                {'error': f'No se puede devolver más de lo pagado ({cobro.monto_pagado} Bs.).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        motivo = request.data.get('motivo', '').strip()
        if not motivo:
            return Response({'error': 'Debes indicar el motivo de la devolución.'}, status=status.HTTP_400_BAD_REQUEST)

        devolucion = Devolucion.objects.create(
            cobro          = cobro,
            monto          = monto,
            fecha          = request.data.get('fecha') or date.today(),
            metodo_pago    = request.data.get('metodo_pago', Cobro.METODO_EFECTIVO),
            motivo         = motivo,
            registrado_por = request.user,
        )
        asignar_numero_recibo(devolucion)

        # Si el mes ya se había cerrado con "Cerrar con lo pagado" (tiene
        # condonación), esta devolución NO debe reabrirlo: la decisión de
        # darlo por saldado ya se tomó. El monto condonado absorbe la
        # diferencia devuelta, así el mes se mantiene "pagado" y no vuelve
        # a pedir un pago que ya se había perdonado.
        if cobro.monto_condonado > 0 or cobro.monto_condonado_inicial is not None:
            # Se recalcula el condonado para que pagado neto + condonado siga
            # sumando el monto final (en vez de sumar a ciegas lo devuelto,
            # que dejaba el mes en "parcial" si los números ya estaban desfasados).
            nuevo_condonado = max(cobro.monto_final - cobro.monto_pagado, 0)
            nota_ajuste = (
                f'Ajuste {date.today().isoformat()}: condonado {cobro.monto_condonado} → '
                f'{nuevo_condonado} Bs. por devolución de {monto} Bs. '
                f'(motivo devolución: {motivo}).'
            )
            cobro.monto_condonado    = nuevo_condonado
            cobro.motivo_condonacion = (
                f'{cobro.motivo_condonacion}\n{nota_ajuste}'.strip()
                if cobro.motivo_condonacion else nota_ajuste
            )
            cobro.save(update_fields=['monto_condonado', 'motivo_condonacion'])

        cobro.recalcular_estado()
        cobro.refresh_from_db()

        return Response(CobroSerializer(cobro).data, status=status.HTTP_201_CREATED)
