"""
inscripciones/models.py
Inscripción del niño (sala+turno+sucursal) y gestión de cobros.
"""
from django.db import models
from django.core.exceptions import ValidationError
from datetime import date
from core.models import ModeloBase


class Inscripcion(ModeloBase):
    """
    Inscripción de un niño a una sucursal + sala + turno específico.
    Copia los costos base del turno pero permite ajustes individuales
    (descuentos, becas, precio especial).
    Un niño puede tener múltiples inscripciones activas en diferentes sucursales.
    """
    MODALIDAD_MENSUAL = 'mensual'
    MODALIDAD_DIARIA  = 'diaria'
    MODALIDADES = [
        (MODALIDAD_MENSUAL, 'Mensualidad'),
        (MODALIDAD_DIARIA,  'Por día'),
    ]

    AJUSTE_NINGUNO         = 'ninguno'
    AJUSTE_DESCUENTO_PCT   = 'descuento_porcentaje'
    AJUSTE_DESCUENTO_MONTO = 'descuento_monto'
    AJUSTE_BECA            = 'beca'
    TIPOS_AJUSTE = [
        (AJUSTE_NINGUNO,         'Sin ajuste'),
        (AJUSTE_DESCUENTO_PCT,   'Descuento en porcentaje'),
        (AJUSTE_DESCUENTO_MONTO, 'Descuento en monto fijo'),
        (AJUSTE_BECA,            'Beca (sin costo)'),
    ]

    nino              = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='inscripciones')
    sucursal          = models.ForeignKey('core.Sucursal', on_delete=models.CASCADE)
    sala              = models.ForeignKey('core.Sala', on_delete=models.CASCADE)
    turno             = models.ForeignKey('core.Turno', on_delete=models.CASCADE)
    modalidad_pago    = models.CharField(max_length=10, choices=MODALIDADES, default=MODALIDAD_MENSUAL)
    # Mensual: inicio del primer ciclo. Por día: primer día en que el niño asiste.
    fecha_inicio      = models.DateField()
    fecha_fin         = models.DateField(null=True, blank=True)
    # Solo modalidad diaria. Vacío = el niño está esperado todos los días desde
    # fecha_inicio. Con valores (0=lunes ... 6=domingo) solo aparece en la
    # planilla de asistencia esos días, y una falta sin aviso solo se cobra
    # esos días. Una asistencia "presente" en otro día igual se cobra.
    dias_semana       = models.JSONField(
        default=list, blank=True,
        help_text='Días de la semana en que asiste (0=lunes ... 6=domingo). Vacío = todos los días.'
    )

    # Costos copiados del turno pero editables individualmente
    costo_mensual     = models.DecimalField(max_digits=8, decimal_places=2)
    costo_diario      = models.DecimalField(max_digits=7, decimal_places=2)

    # Ajuste de precio (descuento o beca)
    tipo_ajuste       = models.CharField(max_length=25, choices=TIPOS_AJUSTE, default=AJUSTE_NINGUNO)
    porcentaje_ajuste = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                            help_text='Para tipo descuento_porcentaje: ej. 20.00 = 20%')
    monto_ajuste      = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                            help_text='Para tipo descuento_monto: monto fijo a descontar')
    motivo_ajuste     = models.TextField(blank=True, help_text='Justificación del ajuste o beca')
    activa            = models.BooleanField(default=True)

    # Trazabilidad: si esta inscripción nace de una transferencia (cambio de
    # sala/turno/sucursal), queda enlazada a la inscripción original que se cerró.
    inscripcion_origen = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transferencias', help_text='Inscripción anterior de la que proviene (si fue transferida).'
    )

    class Meta:
        verbose_name        = 'Inscripción'
        verbose_name_plural = 'Inscripciones'
        ordering            = ['-fecha_inicio']

    def __str__(self):
        return f'{self.nino} → {self.sala} {self.turno}'

    def clean(self):
        if self.sala.sucursal != self.sucursal:
            raise ValidationError('La sala debe pertenecer a la sucursal seleccionada.')
        if self.turno.sala != self.sala:
            raise ValidationError('El turno debe pertenecer a la sala seleccionada.')

    DIAS_SEMANA_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

    @property
    def dias_semana_display(self):
        if not self.dias_semana:
            return 'Todos los días'
        return ', '.join(self.DIAS_SEMANA_ES[d] for d in sorted(self.dias_semana))

    def es_dia_esperado(self, fecha):
        """
        ¿Le tocaba asistir al niño en `fecha`? Solo tiene sentido para la
        modalidad diaria: respeta fecha_inicio, fecha_fin y dias_semana.
        """
        if fecha < self.fecha_inicio:
            return False
        if self.fecha_fin and fecha > self.fecha_fin:
            return False
        if self.dias_semana:
            return fecha.weekday() in self.dias_semana
        return True

    def debe_cobrarse(self, estado_asistencia, fecha):
        """
        Regla de cobro de la modalidad diaria según la asistencia del día:
          - presente              → se cobra (vino, sea o no un día esperado)
          - ausente (sin aviso)   → se cobra, pero solo si era un día esperado
          - ausente justificado   → no se cobra (falta avisada)
        """
        if self.modalidad_pago != self.MODALIDAD_DIARIA:
            return False
        if estado_asistencia == 'presente':
            return True
        if estado_asistencia == 'ausente':
            return self.es_dia_esperado(fecha)
        return False

    @property
    def costo_mensual_final(self):
        """Costo mensual real aplicando el ajuste."""
        if self.tipo_ajuste == Inscripcion.AJUSTE_BECA:
            return 0
        if self.tipo_ajuste == Inscripcion.AJUSTE_DESCUENTO_PCT:
            return self.costo_mensual * (1 - self.porcentaje_ajuste / 100)
        if self.tipo_ajuste == Inscripcion.AJUSTE_DESCUENTO_MONTO:
            return max(0, self.costo_mensual - self.monto_ajuste)
        return self.costo_mensual

    @property
    def costo_diario_final(self):
        """Costo diario real aplicando el ajuste."""
        if self.tipo_ajuste == Inscripcion.AJUSTE_BECA:
            return 0
        if self.tipo_ajuste == Inscripcion.AJUSTE_DESCUENTO_PCT:
            return self.costo_diario * (1 - self.porcentaje_ajuste / 100)
        if self.tipo_ajuste == Inscripcion.AJUSTE_DESCUENTO_MONTO:
            return max(0, self.costo_diario - self.monto_ajuste)
        return self.costo_diario


class Cobro(ModeloBase):
    """
    Cobro individual generado por una inscripción.
    Puede ser mensualidad (generado automáticamente) o diario (al marcar asistencia).

    El monto de un Cobro puede pagarse en una sola vez o en varias cuotas
    (ver modelo `Pago`). `estado` se recalcula automáticamente según la suma
    de los pagos registrados frente a `monto_final`.
    """
    TIPO_MENSUALIDAD = 'mensualidad'
    TIPO_DIARIO      = 'diario'
    TIPO_EXTRA       = 'extra'
    TIPOS = [
        (TIPO_MENSUALIDAD, 'Mensualidad'),
        (TIPO_DIARIO,      'Cobro por día'),
        (TIPO_EXTRA,       'Cobro extra'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_PARCIAL   = 'parcial'
    ESTADO_PAGADO    = 'pagado'
    ESTADO_VENCIDO   = 'vencido'
    ESTADO_ANULADO   = 'anulado'
    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PARCIAL,   'Pago parcial'),
        (ESTADO_PAGADO,    'Pagado'),
        (ESTADO_VENCIDO,   'Vencido'),
        (ESTADO_ANULADO,   'Anulado'),
    ]

    METODO_EFECTIVO    = 'efectivo'
    METODO_TRANSFERENCIA = 'transferencia'
    METODO_QR          = 'qr'
    METODOS_PAGO = [
        (METODO_EFECTIVO,      'Efectivo'),
        (METODO_TRANSFERENCIA, 'Transferencia'),
        (METODO_QR,            'QR'),
    ]

    inscripcion       = models.ForeignKey(Inscripcion, on_delete=models.CASCADE, related_name='cobros')
    tipo              = models.CharField(max_length=15, choices=TIPOS)
    periodo           = models.CharField(
        max_length=30, blank=True,
        help_text='Etiqueta del período. Para mensualidades ancladas a la fecha de inscripción, ej: "2026-02-20 a 2026-03-20".'
    )
    # Ciclo real de facturación: para mensualidades NO sigue el mes calendario,
    # sigue la fecha de inicio de la inscripción. Si el niño se inscribió el 20,
    # cada ciclo corre de 20 a 20 del mes siguiente (periodo_fin = próximo vencimiento).
    periodo_inicio    = models.DateField(null=True, blank=True)
    periodo_fin       = models.DateField(null=True, blank=True)

    monto_base        = models.DecimalField(max_digits=8, decimal_places=2)
    monto_final       = models.DecimalField(max_digits=8, decimal_places=2)
    fecha_emision     = models.DateField(auto_now_add=True)
    fecha_vencimiento = models.DateField()
    estado            = models.CharField(max_length=15, choices=ESTADOS, default=ESTADO_PENDIENTE)

    # Último pago registrado (se mantiene por compatibilidad con reportes existentes;
    # el detalle real de cada abono vive en Pago, relación `pagos`).
    fecha_pago        = models.DateField(null=True, blank=True)
    metodo_pago       = models.CharField(max_length=20, choices=METODOS_PAGO, blank=True)
    comprobante       = models.FileField(upload_to='comprobantes/', null=True, blank=True)

    # Condonación / cierre con lo pagado: cuando por alguna circunstancia se
    # decide dar por saldada la deuda aunque no se haya pagado el 100%.
    monto_condonado    = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    motivo_condonacion = models.TextField(blank=True)
    # Foto del monto condonado tal como quedó al momento del cierre (acción
    # "Cerrar con lo pagado"). NUNCA se vuelve a tocar después. Sirve para que
    # el frontend pueda mostrar "condonado originalmente X, ahora Y" cuando
    # una devolución posterior ajusta `monto_condonado` (ver
    # `registrar_devolucion` en views.py) — así queda visible que el cierre
    # cambió y no se pierde de vista el valor con el que se cerró la primera vez.
    monto_condonado_inicial = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    registrado_por    = models.ForeignKey(
        'accounts.Usuario', on_delete=models.SET_NULL, null=True, blank=True
    )
    observacion       = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Cobro'
        verbose_name_plural = 'Cobros'
        ordering            = ['-fecha_emision']
        constraints = [
            # Una mensualidad es única por inscripción + ciclo (periodo_inicio).
            # Esto es lo que de verdad impide el duplicado, sin importar si se
            # generó desde el servicio, desde asistencia o a mano por la API.
            models.UniqueConstraint(
                fields=['inscripcion', 'tipo', 'periodo_inicio'],
                condition=models.Q(tipo='mensualidad'),
                name='uniq_cobro_mensualidad_por_ciclo',
            ),
            # Un cobro diario es único por inscripción + día (periodo, ej "2026-07-31").
            models.UniqueConstraint(
                fields=['inscripcion', 'tipo', 'periodo'],
                condition=models.Q(tipo='diario'),
                name='uniq_cobro_diario_por_dia',
            ),
            # tipo=extra queda deliberadamente fuera: un cobro extra (ej. un
            # paseo, material) sí puede repetirse el mismo día sin ser un bug.
        ]

    def __str__(self):
        return f'{self.inscripcion.nino} — {self.get_tipo_display()} {self.periodo} ({self.get_estado_display()})'

    @property
    def monto_pagado(self):
        """Suma de todos los pagos/cuotas registrados, menos lo devuelto."""
        total_pagos = self.pagos.aggregate(models.Sum('monto'))['monto__sum'] or 0
        total_devuelto = self.devoluciones.aggregate(models.Sum('monto'))['monto__sum'] or 0
        return total_pagos - total_devuelto

    @property
    def saldo_pendiente(self):
        """Lo que falta por cubrir, considerando pagos y montos condonados."""
        saldo = self.monto_final - self.monto_pagado - self.monto_condonado
        return saldo if saldo > 0 else 0

    def recalcular_estado(self):
        """
        Recalcula el estado según lo pagado + lo condonado frente al monto final.
        No cambia estados finales manuales como 'anulado'.
        """
        if self.estado == Cobro.ESTADO_ANULADO:
            return
        # Un cobro cerrado con "Cerrar con lo pagado" (tiene foto de condonación
        # inicial) es una decisión ya tomada: siempre debe quedar exactamente
        # cubierto = pagado neto + condonado. Si por devoluciones, ajustes o
        # datos previos el condonado quedó desfasado, se reconcilia aquí para
        # que el mes no vuelva a quedar "parcial" pidiendo un cierre que ya se hizo.
        if self.monto_condonado_inicial is not None:
            condonado_correcto = max(self.monto_final - self.monto_pagado, 0)
            if condonado_correcto != self.monto_condonado:
                self.monto_condonado = condonado_correcto
                self.save(update_fields=['monto_condonado'])
        cubierto = self.monto_pagado + self.monto_condonado
        if cubierto <= 0:
            nuevo_estado = Cobro.ESTADO_PENDIENTE
        elif cubierto < self.monto_final:
            nuevo_estado = Cobro.ESTADO_PARCIAL
        else:
            nuevo_estado = Cobro.ESTADO_PAGADO
        if nuevo_estado != Cobro.ESTADO_PAGADO and self.fecha_vencimiento and self.fecha_vencimiento < date.today():
            # Sigue sin cubrirse por completo y ya venció
            if nuevo_estado == Cobro.ESTADO_PENDIENTE:
                nuevo_estado = Cobro.ESTADO_VENCIDO
        self.estado = nuevo_estado
        self.save(update_fields=['estado'])


class Pago(ModeloBase):
    """
    Un abono/cuota concreto aplicado a un Cobro. Un mismo Cobro (ej. una
    mensualidad de 650 Bs.) puede recibir varios Pagos (ej. 200 + 200) hasta
    cubrir el monto_final, o quedar cerrado antes por condonación.
    """
    cobro          = models.ForeignKey(Cobro, on_delete=models.CASCADE, related_name='pagos')
    monto          = models.DecimalField(max_digits=8, decimal_places=2)
    fecha_pago     = models.DateField(default=date.today)
    metodo_pago    = models.CharField(max_length=20, choices=Cobro.METODOS_PAGO, default=Cobro.METODO_EFECTIVO)
    comprobante    = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    registrado_por = models.ForeignKey(
        'accounts.Usuario', on_delete=models.SET_NULL, null=True, blank=True
    )
    observacion    = models.TextField(blank=True)
    # Número correlativo para el recibo imprimible (se asigna solo, al guardar
    # el pago por primera vez — ver services.asignar_numero_recibo).
    numero_recibo  = models.PositiveIntegerField(unique=True, null=True, blank=True)
    # Si este Pago no es dinero recibido sino la APLICACIÓN de un abono
    # adelantado a un cobro (modalidad por día), apunta al abono. Esos pagos
    # no llevan recibo propio (el recibo es el del abono) y NO suman a la caja
    # (el dinero ya entró a caja el día del abono). Ver services.aplicar_saldo.
    abono_origen   = models.ForeignKey(
        'AbonoDiario', on_delete=models.CASCADE, null=True, blank=True, related_name='aplicaciones'
    )

    class Meta:
        verbose_name        = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering            = ['-fecha_pago', '-created_at']

    def __str__(self):
        return f'Pago {self.monto} Bs. — {self.cobro}'


class Devolucion(ModeloBase):
    """
    Devolución de dinero sobre un Cobro que ya recibió uno o más Pagos.
    Ej: se cobró de más, la familia se da de baja y se le devuelve el saldo
    a favor, un error de cobro, etc.

    Resta de `Cobro.monto_pagado`, así que si el cobro estaba "pagado" por
    pago real (sin condonación) y se devuelve una parte, `recalcular_estado()`
    lo vuelve a abrir solo — consistente con la regla de "cerrar en orden":
    ese mes bloqueará de nuevo a los siguientes hasta que se resuelva otra vez.

    Excepción: si el cobro fue cerrado con condonación (`monto_condonado > 0`,
    vía la acción "Cerrar con lo pagado"), la devolución NO reabre el mes.
    En ese caso `registrar_devolucion` (ver views.py) incrementa
    `monto_condonado` en el mismo monto devuelto, para que el mes siga
    "pagado" — la decisión de dar el mes por saldado ya se tomó, y una
    devolución posterior no debe resucitar un cobro que se había perdonado.
    """
    # O cuelga de un cobro (devolución de un pago), o de la inscripción cuando
    # se devuelve en efectivo el SALDO A FAVOR de la cuenta del niño (dinero
    # que no se aplicó a ningún cobro). Exactamente uno de los dos (ver Meta).
    cobro          = models.ForeignKey(Cobro, on_delete=models.CASCADE, related_name='devoluciones',
                                       null=True, blank=True)
    inscripcion    = models.ForeignKey(Inscripcion, on_delete=models.CASCADE, related_name='devoluciones_saldo',
                                       null=True, blank=True)
    monto          = models.DecimalField(max_digits=8, decimal_places=2)
    fecha          = models.DateField(default=date.today)
    metodo_pago    = models.CharField(max_length=20, choices=Cobro.METODOS_PAGO, default=Cobro.METODO_EFECTIVO)
    motivo         = models.TextField()
    registrado_por = models.ForeignKey(
        'accounts.Usuario', on_delete=models.SET_NULL, null=True, blank=True
    )
    numero_recibo  = models.PositiveIntegerField(unique=True, null=True, blank=True)
    # True = el dinero NO sale de caja: pasa a la cuenta (saldo a favor) del
    # niño, p. ej. al cambiar a un turno más barato con el mes ya pagado. No
    # lleva recibo ni cuenta como egreso (su contraparte es un AbonoDiario
    # con es_traspaso=True, que tampoco cuenta como ingreso).
    a_cuenta       = models.BooleanField(default=False)

    class Meta:
        verbose_name        = 'Devolución'
        verbose_name_plural = 'Devoluciones'
        ordering            = ['-fecha', '-created_at']
        constraints = [
            models.CheckConstraint(
                name='devolucion_de_un_cobro_o_de_una_cuenta',
                condition=(models.Q(cobro__isnull=False, inscripcion__isnull=True)
                           | models.Q(cobro__isnull=True, inscripcion__isnull=False)),
            ),
        ]

    def __str__(self):
        destino = self.cobro if self.cobro_id else f'saldo de {self.inscripcion}'
        return f'Devolución {self.monto} Bs. — {destino}'


class AbonoDiario(ModeloBase):
    """
    Dinero a favor de la cuenta de una inscripción. Nace de dos maneras:
      - Un abono real: el tutor de un niño "por día" entrega dinero por
        adelantado o después, sin estar atado a un día concreto (entra a
        caja y lleva recibo).
      - Un traspaso (es_traspaso=True): sobró dinero de un cobro ya pagado
        (p. ej. cambio a un turno más barato) y pasa a la cuenta del niño.

    Funciona como saldo a favor: los cobros nuevos (días de asistencia o el
    siguiente ciclo mensual) se van cubriendo con él en orden cronológico
    (ver services.aplicar_saldo), creando `Pago` con `abono_origen`.
    Es el abono (no sus aplicaciones) lo que entra a caja y lleva recibo.
    """
    inscripcion    = models.ForeignKey(Inscripcion, on_delete=models.CASCADE, related_name='abonos')
    monto          = models.DecimalField(max_digits=8, decimal_places=2)
    fecha_pago     = models.DateField(default=date.today)
    metodo_pago    = models.CharField(max_length=20, choices=Cobro.METODOS_PAGO, default=Cobro.METODO_EFECTIVO)
    comprobante    = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    registrado_por = models.ForeignKey(
        'accounts.Usuario', on_delete=models.SET_NULL, null=True, blank=True
    )
    observacion    = models.TextField(blank=True)
    numero_recibo  = models.PositiveIntegerField(unique=True, null=True, blank=True)
    # True = no es dinero nuevo sino un saldo que viene de un ajuste interno
    # (p. ej. la diferencia por un cambio de turno). No entra a caja ni lleva
    # recibo: el dinero ya entró cuando se pagó el cobro original.
    es_traspaso    = models.BooleanField(default=False)
    # Parte de este abono que ya se devolvió en efectivo (ver services.devolver_saldo).
    devuelto       = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        verbose_name        = 'Abono (por día)'
        verbose_name_plural = 'Abonos (por día)'
        ordering            = ['fecha_pago', 'created_at']

    def __str__(self):
        return f'Abono {self.monto} Bs. — {self.inscripcion}'

    @property
    def monto_aplicado(self):
        return self.aplicaciones.aggregate(models.Sum('monto'))['monto__sum'] or 0

    @property
    def monto_disponible(self):
        return self.monto - self.monto_aplicado - self.devuelto


class DiasContratados(ModeloBase):
    """
    Historial de los días que el tutor acordó con el centro para una
    inscripción por día: "empezó con 5 días, luego se ampliaron a 10".
    Es un control informativo (el cobro real sigue dependiendo de la
    asistencia): permite ver cuántos días se acordaron, cuántos se han
    consumido y avisar cuando se pasa de lo acordado.
    El total contratado = iniciales + ampliaciones − reducciones.
    """
    TIPO_INICIAL    = 'inicial'
    TIPO_AMPLIACION = 'ampliacion'
    TIPO_REDUCCION  = 'reduccion'
    TIPOS = [
        (TIPO_INICIAL,    'Días iniciales'),
        (TIPO_AMPLIACION, 'Ampliación'),
        (TIPO_REDUCCION,  'Reducción'),
    ]

    inscripcion    = models.ForeignKey(Inscripcion, on_delete=models.CASCADE, related_name='dias_contratados')
    tipo           = models.CharField(max_length=12, choices=TIPOS)
    cantidad       = models.PositiveSmallIntegerField()
    fecha          = models.DateField(default=date.today)
    nota           = models.TextField(blank=True)
    registrado_por = models.ForeignKey(
        'accounts.Usuario', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name        = 'Días contratados'
        verbose_name_plural = 'Días contratados'
        ordering            = ['fecha', 'created_at']

    def __str__(self):
        signo = '−' if self.tipo == self.TIPO_REDUCCION else '+'
        return f'{self.inscripcion}: {signo}{self.cantidad} días ({self.get_tipo_display()})'
