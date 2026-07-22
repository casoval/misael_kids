"""
evaluacion/models.py
Hitos del desarrollo infantil y evaluación por niño.
"""
from django.db import models
from core.models import ModeloBase


class HitoDesarrollo(ModeloBase):
    """
    Catálogo de hitos esperados por rango de edad.
    Se pre-carga con datos estándar del desarrollo infantil 0-72 meses.
    """
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

    nombre           = models.CharField(max_length=300)
    area             = models.CharField(max_length=25, choices=AREAS)
    edad_min_meses   = models.PositiveSmallIntegerField()
    edad_max_meses   = models.PositiveSmallIntegerField()
    descripcion      = models.TextField(blank=True)
    activo           = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Hito de desarrollo'
        ordering     = ['edad_min_meses', 'area']

    def __str__(self):
        return f'{self.nombre} ({self.edad_min_meses}-{self.edad_max_meses} meses)'


class EvaluacionNino(ModeloBase):
    """Evaluación de un hito específico para un niño."""
    ESTADO_LOGRADO    = 'logrado'
    ESTADO_EN_PROCESO = 'en_proceso'
    ESTADO_NO_LOGRADO = 'no_logrado'
    ESTADOS = [
        (ESTADO_LOGRADO,    'Logrado'),
        (ESTADO_EN_PROCESO, 'En proceso'),
        (ESTADO_NO_LOGRADO, 'No logrado aún'),
    ]

    nino          = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='evaluaciones')
    educadora     = models.ForeignKey('personal.Personal', on_delete=models.CASCADE)
    hito          = models.ForeignKey(HitoDesarrollo, on_delete=models.CASCADE)
    fecha         = models.DateField()
    estado        = models.CharField(max_length=15, choices=ESTADOS)
    observacion   = models.TextField(blank=True)
    alerta_rezago = models.BooleanField(default=False)

    class Meta:
        verbose_name    = 'Evaluación de desarrollo'
        unique_together = [['nino', 'hito', 'fecha']]
        ordering        = ['-fecha']

    def __str__(self):
        return f'{self.nino} — {self.hito.nombre}: {self.get_estado_display()}'
