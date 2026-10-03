"""
inscripciones/serializers.py
"""
from datetime import date
from rest_framework import serializers
from .models import Inscripcion, Cobro, Pago, Devolucion, AbonoDiario


class PagoSerializer(serializers.ModelSerializer):
    metodo_pago_display = serializers.CharField(source='get_metodo_pago_display', read_only=True)

    class Meta:
        model  = Pago
        fields = [
            'id', 'cobro', 'monto', 'fecha_pago',
            'metodo_pago', 'metodo_pago_display', 'comprobante',
            'registrado_por', 'observacion', 'numero_recibo', 'abono_origen', 'created_at',
        ]
        read_only_fields = ['id', 'numero_recibo', 'abono_origen', 'created_at']


class AbonoDiarioSerializer(serializers.ModelSerializer):
    metodo_pago_display = serializers.CharField(source='get_metodo_pago_display', read_only=True)
    monto_aplicado      = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    monto_disponible    = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model  = AbonoDiario
        fields = [
            'id', 'inscripcion', 'monto', 'fecha_pago', 'metodo_pago', 'metodo_pago_display',
            'comprobante', 'registrado_por', 'observacion', 'numero_recibo', 'es_traspaso',
            'monto_aplicado', 'monto_disponible', 'created_at',
        ]
        read_only_fields = ['id', 'numero_recibo', 'registrado_por', 'created_at']


def validar_dias_semana(valor):
    """Lista de enteros 0-6 (0=lunes), sin repetir y ordenada. Vacío = todos los días."""
    if valor in (None, ''):
        return []
    if not isinstance(valor, (list, tuple)):
        raise serializers.ValidationError('Debe ser una lista de días (0=lunes ... 6=domingo).')
    try:
        dias = sorted({int(d) for d in valor})
    except (TypeError, ValueError):
        raise serializers.ValidationError('Los días deben ser números del 0 (lunes) al 6 (domingo).')
    if any(d < 0 or d > 6 for d in dias):
        raise serializers.ValidationError('Los días deben estar entre 0 (lunes) y 6 (domingo).')
    return dias


MAX_DIAS_PROGRAMADOS = 366


def validar_dias_programados(valor):
    """
    Lista de fechas ISO ('YYYY-MM-DD') elegidas en el calendario: sin repetir y
    ordenadas. Vacío = sin calendario (inscripción antigua o mensualidad).
    """
    if valor in (None, ''):
        return []
    if not isinstance(valor, (list, tuple)):
        raise serializers.ValidationError('Debe ser una lista de fechas (YYYY-MM-DD).')
    fechas = set()
    for v in valor:
        try:
            fechas.add(date.fromisoformat(str(v)[:10]).isoformat())
        except ValueError:
            raise serializers.ValidationError(f'La fecha "{v}" no es válida, usa formato YYYY-MM-DD.')
    if len(fechas) > MAX_DIAS_PROGRAMADOS:
        raise serializers.ValidationError(f'No se pueden elegir más de {MAX_DIAS_PROGRAMADOS} días.')
    return sorted(fechas)


class DevolucionSerializer(serializers.ModelSerializer):
    metodo_pago_display = serializers.CharField(source='get_metodo_pago_display', read_only=True)

    class Meta:
        model  = Devolucion
        fields = [
            'id', 'cobro', 'inscripcion', 'monto', 'fecha',
            'metodo_pago', 'metodo_pago_display', 'motivo',
            'registrado_por', 'numero_recibo', 'a_cuenta', 'created_at',
        ]
        read_only_fields = ['id', 'numero_recibo', 'a_cuenta', 'created_at']


class CobroSerializer(serializers.ModelSerializer):
    tipo_display   = serializers.CharField(source='get_tipo_display', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    nino_nombre    = serializers.CharField(
        source='inscripcion.nino.nombre_completo', read_only=True
    )
    nino_foto      = serializers.ImageField(source='inscripcion.nino.foto', read_only=True)
    nino_genero    = serializers.CharField(source='inscripcion.nino.genero', read_only=True)
    monto_pagado     = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    saldo_pendiente  = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    pagos            = PagoSerializer(many=True, read_only=True)
    devoluciones     = DevolucionSerializer(many=True, read_only=True)

    class Meta:
        model  = Cobro
        fields = [
            'id', 'inscripcion', 'nino_nombre', 'nino_foto', 'nino_genero',
            'tipo', 'tipo_display', 'periodo', 'periodo_inicio', 'periodo_fin',
            'monto_base', 'monto_final', 'monto_pagado', 'saldo_pendiente',
            'fecha_emision', 'fecha_vencimiento',
            'estado', 'estado_display',
            'fecha_pago', 'metodo_pago', 'comprobante',
            'monto_condonado', 'monto_condonado_inicial', 'motivo_condonacion',
            'registrado_por', 'observacion', 'pagos', 'devoluciones',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'fecha_emision', 'created_at', 'updated_at', 'monto_condonado_inicial']

    def validate(self, data):
        # La creación directa por este endpoint solo está permitida para
        # cobros "extra" (paseos, materiales, etc.). Las mensualidades y los
        # cobros diarios SIEMPRE deben salir del flujo controlado
        # (generar_ciclo_mensual / asistencia), que es el único lugar que
        # garantiza no duplicar un periodo ya cobrado. Si se permitiera crear
        # estos tipos aquí también, existiría un tercer camino sin ese
        # control, aunque el constraint de BD igual evitaría el duplicado
        # exacto (lo haría con un error 500 feo en vez de uno claro).
        if self.instance is None:
            tipo = data.get('tipo')
            if tipo in (Cobro.TIPO_MENSUALIDAD, Cobro.TIPO_DIARIO):
                raise serializers.ValidationError({
                    'tipo': 'Los cobros de mensualidad o diario no se crean aquí directamente: '
                            'usa "Generar mensualidad" en la inscripción, o deja que se genere '
                            'solo al marcar asistencia. Este formulario es solo para cobros extra.'
                })
        return data


class InscripcionSerializer(serializers.ModelSerializer):
    nino_nombre       = serializers.CharField(source='nino.nombre_completo', read_only=True)
    nino_foto         = serializers.ImageField(source='nino.foto', read_only=True)
    nino_genero       = serializers.CharField(source='nino.genero', read_only=True)
    sucursal_nombre   = serializers.CharField(source='sucursal.nombre', read_only=True)
    sala_nombre       = serializers.CharField(source='sala.nombre', read_only=True)
    turno_nombre      = serializers.CharField(source='turno.nombre', read_only=True)
    tipo_ajuste_display   = serializers.CharField(source='get_tipo_ajuste_display', read_only=True)
    modalidad_display     = serializers.CharField(source='get_modalidad_pago_display', read_only=True)
    costo_mensual_final   = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    costo_diario_final    = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    dias_semana_display   = serializers.CharField(read_only=True)
    cobros                = CobroSerializer(many=True, read_only=True)

    class Meta:
        model  = Inscripcion
        fields = [
            'id', 'nino', 'nino_nombre', 'nino_foto', 'nino_genero',
            'sucursal', 'sucursal_nombre',
            'sala', 'sala_nombre',
            'turno', 'turno_nombre',
            'modalidad_pago', 'modalidad_display',
            'fecha_inicio', 'fecha_fin',
            'dias_semana', 'dias_semana_display', 'dias_programados',
            'costo_mensual', 'costo_diario',
            'tipo_ajuste', 'tipo_ajuste_display',
            'porcentaje_ajuste', 'monto_ajuste', 'motivo_ajuste',
            'costo_mensual_final', 'costo_diario_final',
            'activa', 'inscripcion_origen', 'cobros',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        # En la modalidad por día con calendario, el primer día se deduce de las
        # fechas elegidas, así que no hace falta mandarlo.
        extra_kwargs = {'fecha_inicio': {'required': False}}

    def validate_dias_semana(self, valor):
        return validar_dias_semana(valor)

    def validate_dias_programados(self, valor):
        return validar_dias_programados(valor)

    def validate(self, data):
        # Los días de la semana solo existen en la modalidad por día: en una
        # mensualidad se ignoran (se guardan vacíos) para no dejar basura.
        modalidad = data.get('modalidad_pago', getattr(self.instance, 'modalidad_pago', None))
        if modalidad == Inscripcion.MODALIDAD_MENSUAL:
            data['dias_semana'] = []
            data['dias_programados'] = []
        elif self.instance is not None:
            # Las fechas del calendario de una inscripción existente solo se
            # cambian con /actualizar-dias/ (valida lo ya asistido y deja
            # historial de ampliación/reducción), nunca editando la inscripción.
            data.pop('dias_programados', None)

        # Por día con calendario: el primer día de asistencia es la primera fecha elegida.
        if self.instance is None:
            if data.get('dias_programados') and modalidad == Inscripcion.MODALIDAD_DIARIA:
                data['fecha_inicio'] = date.fromisoformat(data['dias_programados'][0])
            elif not data.get('fecha_inicio'):
                raise serializers.ValidationError({'fecha_inicio': 'Este campo es requerido.'})

        # Un niño solo puede tener UNA inscripción activa en todo el sistema.
        # Para cambiarlo de sala/turno/sucursal se debe usar el endpoint
        # de transferencia (POST /inscripciones/{id}/transferir/), no crear
        # una segunda inscripción.
        nino   = data.get('nino', getattr(self.instance, 'nino', None))
        activa = data.get('activa', getattr(self.instance, 'activa', True))
        if nino and activa:
            ya_tiene_activa = Inscripcion.objects.filter(
                nino=nino, activa=True
            ).exclude(id=self.instance.id if self.instance else None).exists()
            if ya_tiene_activa:
                raise serializers.ValidationError(
                    {'nino': 'Este niño/a ya tiene una inscripción activa. '
                              'Usa la opción "Transferir" para cambiarlo de sala, turno o sucursal '
                              'en lugar de crear una nueva inscripción.'}
                )

        # Una inscripción dada de baja NO se reactiva: si el niño regresa se crea una inscripción
        # nueva (así quedan bien la fecha de baja, el historial y el traslado del saldo a favor).
        if self.instance is not None and not self.instance.activa and data.get('activa') is True:
            raise serializers.ValidationError({'activa': (
                'Una inscripción dada de baja no se puede reactivar. Si el niño/a regresa, '
                'crea una inscripción nueva: su saldo a favor pasa a ella.')})

        # Un niño que vuelve tras una baja no puede abrir una inscripción nueva mientras
        # deba algo de la anterior: primero se cobra. El saldo a favor NO compensa esa
        # deuda (se cobra aparte y el saldo pasa a la inscripción nueva).
        if nino and activa and self.instance is None:
            from .services import deuda_cerradas_del_nino
            deuda, detalle = deuda_cerradas_del_nino(nino)
            if deuda > 0:
                origen = ', '.join(d['etiqueta'] for d in detalle)
                raise serializers.ValidationError({'nino': (
                    f'No se puede inscribir de nuevo: debe Bs. {deuda} de su inscripción anterior ({origen}). '
                    'Primero debe quedar al día: en la lista pon el filtro Estado en "Dadas de baja", '
                    'busca al niño y cobra la deuda en 💳 Pagos (el saldo a favor no la compensa).')})

        # Sala debe pertenecer a la sucursal
        sala     = data.get('sala')
        sucursal = data.get('sucursal')
        turno    = data.get('turno')
        if sala and sucursal and sala.sucursal != sucursal:
            raise serializers.ValidationError(
                {'sala': 'La sala no pertenece a la sucursal seleccionada.'}
            )
        if turno and sala and turno.sala != sala:
            raise serializers.ValidationError(
                {'turno': 'El turno no pertenece a la sala seleccionada.'}
            )
        # Verificar capacidad disponible en sala+turno
        if sala and turno:
            inscritos = Inscripcion.objects.filter(
                sala=sala, turno=turno, activa=True
            ).exclude(id=self.instance.id if self.instance else None).count()
            if inscritos >= sala.capacidad_maxima:
                raise serializers.ValidationError(
                    {'sala': f'La sala {sala.nombre} ya alcanzó su capacidad máxima ({sala.capacidad_maxima} niños).'}
                )
        return data

    def create(self, validated_data):
        # Si no se especifican costos, copiarlos del turno
        turno = validated_data.get('turno')
        if turno:
            if 'costo_mensual' not in validated_data or not validated_data.get('costo_mensual'):
                validated_data['costo_mensual'] = turno.costo_mensual
            if 'costo_diario' not in validated_data or not validated_data.get('costo_diario'):
                validated_data['costo_diario'] = turno.costo_diario
        return super().create(validated_data)


class InscripcionResumenSerializer(serializers.ModelSerializer):
    """Versión compacta para listas."""
    nino_nombre         = serializers.CharField(source='nino.nombre_completo', read_only=True)
    nino_foto           = serializers.ImageField(source='nino.foto', read_only=True)
    nino_genero         = serializers.CharField(source='nino.genero', read_only=True)
    sucursal_nombre     = serializers.CharField(source='sucursal.nombre', read_only=True)
    sala_nombre         = serializers.CharField(source='sala.nombre', read_only=True)
    turno_nombre        = serializers.CharField(source='turno.nombre', read_only=True)
    modalidad_display   = serializers.CharField(source='get_modalidad_pago_display', read_only=True)
    costo_mensual_final = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    costo_diario_final  = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    dias_semana_display = serializers.CharField(read_only=True)
    estado_pago         = serializers.SerializerMethodField()
    deuda_cerrada       = serializers.SerializerMethodField()

    def get_estado_pago(self, obj):
        # Import local: services importa los modelos y evita ciclos al cargar.
        from .services import estado_pago
        return estado_pago(obj)

    def get_deuda_cerrada(self, obj):
        """Lo que aún se debe en una inscripción dada de baja (en las activas es 0: ahí rige estado_pago)."""
        if obj.activa:
            return 0
        from .services import deuda_abierta
        return deuda_abierta(obj)

    class Meta:
        model  = Inscripcion
        fields = [
            'id', 'nino', 'nino_nombre', 'nino_foto', 'nino_genero',
            'sucursal_nombre', 'sala_nombre', 'turno_nombre',
            'modalidad_pago', 'modalidad_display', 'tipo_ajuste',
            'costo_mensual_final', 'costo_diario_final',
            'dias_semana', 'dias_semana_display', 'dias_programados',
            'activa', 'fecha_inicio', 'estado_pago', 'deuda_cerrada',
        ]
