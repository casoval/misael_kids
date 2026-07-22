"""
inscripciones/models.py
Inscripción del niño (sala+turno+sucursal) y gestión de cobros.
"""
from django.db import models
from django.core.exceptions import ValidationError
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
    fecha_inicio      = models.DateField()
    fecha_fin         = models.DateField(null=True, blank=True)

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
    ESTADO_PAGADO    = 'pagado'
    ESTADO_VENCIDO   = 'vencido'
    ESTADO_ANULADO   = 'anulado'
    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente'),
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
    periodo           = models.CharField(max_length=7, blank=True, help_text='Ej: 2025-06 para mensualidades')
    monto_base        = models.DecimalField(max_digits=8, decimal_places=2)
    monto_final       = models.DecimalField(max_digits=8, decimal_places=2)
    fecha_emision     = models.DateField(auto_now_add=True)
    fecha_vencimiento = models.DateField()
    estado            = models.CharField(max_length=15, choices=ESTADOS, default=ESTADO_PENDIENTE)
    fecha_pago        = models.DateField(null=True, blank=True)
    metodo_pago       = models.CharField(max_length=20, choices=METODOS_PAGO, blank=True)
    comprobante       = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    registrado_por    = models.ForeignKey(
        'accounts.Usuario', on_delete=models.SET_NULL, null=True, blank=True
    )
    observacion       = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Cobro'
        verbose_name_plural = 'Cobros'
        ordering            = ['-fecha_emision']

    def __str__(self):
        return f'{self.inscripcion.nino} — {self.get_tipo_display()} {self.periodo} ({self.get_estado_display()})'
