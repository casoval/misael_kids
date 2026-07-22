"""
core/models.py
Modelos base: Sucursal, Sala, Turno
Son la raíz de todo el sistema multisucursal.
"""
import uuid
from django.db import models


class ModeloBase(models.Model):
    """
    Modelo abstracto base.
    Todos los modelos del sistema heredan de aquí.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Sucursal(ModeloBase):
    """
    Sede física de Misael Kids.
    Todo el sistema está anclado a una sucursal.
    """
    nombre      = models.CharField(max_length=100)
    direccion   = models.CharField(max_length=255)
    telefono    = models.CharField(max_length=20, blank=True)
    ciudad      = models.CharField(max_length=100, default='La Paz')
    descripcion = models.TextField(blank=True)
    directora   = models.ForeignKey(
        'accounts.Usuario',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sucursales_a_cargo',
        limit_choices_to={'rol__in': ['directora', 'admin']},
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Sucursal'
        verbose_name_plural = 'Sucursales'
        ordering            = ['nombre']

    def __str__(self):
        return self.nombre


class Sala(ModeloBase):
    """
    Sala dentro de una sucursal, agrupada por rango de edad.
    Ej: Sala cuna (0-24 meses), Sala medio (25-48 meses), Sala mayor (49-72 meses)
    """
    sucursal         = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='salas')
    nombre           = models.CharField(max_length=100)
    edad_min_meses   = models.PositiveSmallIntegerField(help_text='Edad mínima en meses')
    edad_max_meses   = models.PositiveSmallIntegerField(help_text='Edad máxima en meses')
    capacidad_maxima = models.PositiveSmallIntegerField()
    descripcion      = models.TextField(blank=True)
    activa           = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Sala'
        verbose_name_plural = 'Salas'
        ordering            = ['sucursal', 'edad_min_meses']
        unique_together     = [['sucursal', 'nombre']]

    def __str__(self):
        return f'{self.nombre} — {self.sucursal.nombre}'

    @property
    def rango_edad(self):
        return f'{self.edad_min_meses}–{self.edad_max_meses} meses'


class Turno(ModeloBase):
    """
    Turno disponible dentro de una sala.
    Cada turno tiene su propia tarifa base (mensual y diaria).
    Los costos individuales por niño se ajustan en Inscripcion.
    """
    TIPO_MANANA   = 'manana'
    TIPO_TARDE    = 'tarde'
    TIPO_COMPLETO = 'completo'
    TIPO_ESPECIAL = 'especial'

    TIPOS = [
        (TIPO_MANANA,   'Turno mañana'),
        (TIPO_TARDE,    'Turno tarde'),
        (TIPO_COMPLETO, 'Turno completo (mañana y tarde)'),
        (TIPO_ESPECIAL, 'Turno especial'),
    ]

    sala          = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name='turnos')
    nombre        = models.CharField(max_length=100)
    tipo          = models.CharField(max_length=20, choices=TIPOS)
    hora_inicio   = models.TimeField()
    hora_fin      = models.TimeField()
    costo_mensual = models.DecimalField(max_digits=8, decimal_places=2)
    costo_diario  = models.DecimalField(max_digits=7, decimal_places=2)
    descripcion   = models.TextField(blank=True)
    activo        = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Turno'
        verbose_name_plural = 'Turnos'
        ordering            = ['sala', 'hora_inicio']
        unique_together     = [['sala', 'nombre']]

    def __str__(self):
        return f'{self.nombre} · {self.sala.nombre} — {self.sala.sucursal.nombre}'
