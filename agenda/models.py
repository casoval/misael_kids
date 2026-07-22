"""
agenda/models.py
Planificación pedagógica grupal e individual.
"""
from django.db import models
from core.models import ModeloBase


class PlanificacionGrupal(ModeloBase):
    """Registro diario de actividades para toda la sala/turno."""
    sala           = models.ForeignKey('core.Sala', on_delete=models.CASCADE)
    turno          = models.ForeignKey('core.Turno', on_delete=models.CASCADE)
    educadora      = models.ForeignKey('personal.Personal', on_delete=models.CASCADE)
    fecha          = models.DateField()
    actividades    = models.TextField()
    areas_trabajadas = models.CharField(max_length=500, blank=True, help_text='Áreas de desarrollo abordadas')
    observaciones  = models.TextField(blank=True)
    visible_padres = models.BooleanField(default=True)

    class Meta:
        verbose_name    = 'Planificación grupal'
        unique_together = [['sala', 'turno', 'fecha']]
        ordering        = ['-fecha']

    def __str__(self):
        return f'Planif. {self.sala} {self.turno} — {self.fecha}'


class PlanIndividual(ModeloBase):
    """Plan de trabajo para un niño con necesidades específicas."""
    ORIGEN_EDUCADORA = 'educadora'
    ORIGEN_MISAEL    = 'centro_misael'
    ORIGENES = [
        (ORIGEN_EDUCADORA, 'Creado por educadora'),
        (ORIGEN_MISAEL,    'Plan del Centro Misael'),
    ]

    nino         = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='planes_individuales')
    creado_por   = models.ForeignKey('personal.Personal', on_delete=models.CASCADE)
    origen       = models.CharField(max_length=20, choices=ORIGENES, default=ORIGEN_EDUCADORA)
    descripcion  = models.TextField()
    fecha_inicio = models.DateField()
    fecha_fin    = models.DateField(null=True, blank=True)
    activo       = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Plan individual'
        ordering     = ['-fecha_inicio']

    def __str__(self):
        return f'Plan {self.nino} ({self.get_origen_display()})'


class ObjetivoIndividual(ModeloBase):
    """Objetivo específico dentro de un plan individual."""
    AREA_MOTRICIDAD_FINA   = 'motricidad_fina'
    AREA_MOTRICIDAD_GRUESA = 'motricidad_gruesa'
    AREA_LENGUAJE          = 'lenguaje'
    AREA_SOCIAL            = 'social'
    AREA_COGNITIVO         = 'cognitivo'
    AREA_AUTONOMIA         = 'autonomia'
    AREAS = [
        (AREA_MOTRICIDAD_FINA,   'Motricidad fina'),
        (AREA_MOTRICIDAD_GRUESA, 'Motricidad gruesa'),
        (AREA_LENGUAJE,          'Lenguaje y comunicación'),
        (AREA_SOCIAL,            'Desarrollo social'),
        (AREA_COGNITIVO,         'Desarrollo cognitivo'),
        (AREA_AUTONOMIA,         'Autonomía'),
    ]
    ESTADO_PENDIENTE  = 'pendiente'
    ESTADO_EN_PROCESO = 'en_proceso'
    ESTADO_LOGRADO    = 'logrado'
    ESTADOS = [
        (ESTADO_PENDIENTE,  'Pendiente'),
        (ESTADO_EN_PROCESO, 'En proceso'),
        (ESTADO_LOGRADO,    'Logrado'),
    ]

    plan         = models.ForeignKey(PlanIndividual, on_delete=models.CASCADE, related_name='objetivos')
    descripcion  = models.TextField()
    area         = models.CharField(max_length=25, choices=AREAS)
    estado       = models.CharField(max_length=15, choices=ESTADOS, default=ESTADO_PENDIENTE)
    orden        = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = 'Objetivo individual'
        ordering     = ['orden']

    def __str__(self):
        return f'{self.descripcion[:60]} ({self.get_estado_display()})'


class RegistroObjetivo(ModeloBase):
    """Avance diario registrado por la educadora sobre un objetivo."""
    RESULTADO_TRABAJADO = 'trabajado'
    RESULTADO_LOGRADO   = 'logrado'
    RESULTADO_NO_TRABAJADO = 'no_trabajado'
    RESULTADOS = [
        (RESULTADO_TRABAJADO,    'Trabajado'),
        (RESULTADO_LOGRADO,      'Logrado hoy'),
        (RESULTADO_NO_TRABAJADO, 'No trabajado'),
    ]

    objetivo     = models.ForeignKey(ObjetivoIndividual, on_delete=models.CASCADE, related_name='registros')
    educadora    = models.ForeignKey('personal.Personal', on_delete=models.CASCADE)
    fecha        = models.DateField()
    resultado    = models.CharField(max_length=20, choices=RESULTADOS)
    observacion  = models.TextField(blank=True)

    class Meta:
        verbose_name    = 'Registro de objetivo'
        unique_together = [['objetivo', 'fecha']]
        ordering        = ['-fecha']

    def __str__(self):
        return f'{self.objetivo} — {self.fecha}: {self.get_resultado_display()}'
