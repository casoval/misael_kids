"""
misael_link/models.py
Conexión con el Centro de Neurodesarrollo Infantil Misael.
Derivaciones, planes compartidos e informes cruzados.
"""
from django.db import models
from core.models import ModeloBase


class Derivacion(ModeloBase):
    """
    Solicitud formal desde Misael Kids al Centro Misael
    para evaluación o tratamiento de un niño.
    """
    ESTADO_SOLICITADA = 'solicitada'
    ESTADO_ACEPTADA   = 'aceptada'
    ESTADO_EN_PROCESO = 'en_proceso'
    ESTADO_CERRADA    = 'cerrada'
    ESTADOS = [
        (ESTADO_SOLICITADA, 'Solicitada'),
        (ESTADO_ACEPTADA,   'Aceptada por el centro'),
        (ESTADO_EN_PROCESO, 'En proceso de atención'),
        (ESTADO_CERRADA,    'Cerrada'),
    ]

    nino             = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='derivaciones')
    solicitado_por   = models.ForeignKey('personal.Personal', on_delete=models.CASCADE)
    motivo           = models.TextField(help_text='Señales o comportamientos observados')
    area_derivacion  = models.CharField(max_length=200, help_text='Ej: Terapia del lenguaje, psicología')
    estado           = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_SOLICITADA)
    fecha_solicitud  = models.DateField(auto_now_add=True)
    fecha_respuesta  = models.DateField(null=True, blank=True)
    respuesta_centro = models.TextField(blank=True)
    consentimiento_tutor = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Derivación al Centro Misael'
        ordering     = ['-fecha_solicitud']

    def __str__(self):
        return f'Derivación {self.nino} — {self.area_derivacion} ({self.get_estado_display()})'


class PlanTrabajoMisael(ModeloBase):
    """
    Plan de trabajo creado por un profesional del Centro Misael
    para ser ejecutado por la educadora del jardín.
    Se vincula a un PlanIndividual de la app agenda.
    """
    nino              = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='planes_misael')
    derivacion        = models.ForeignKey(Derivacion, on_delete=models.SET_NULL, null=True, blank=True)
    plan_individual   = models.OneToOneField(
        'agenda.PlanIndividual', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='plan_misael'
    )
    profesional_email = models.EmailField(help_text='Email del profesional en el Centro Misael')
    profesional_nombre = models.CharField(max_length=200)
    descripcion       = models.TextField()
    fecha_inicio      = models.DateField()
    fecha_fin         = models.DateField(null=True, blank=True)
    activo            = models.BooleanField(default=True)
    consentimiento_tutor = models.BooleanField(default=False,
        help_text='El tutor autorizó compartir información entre ambos centros')

    class Meta:
        verbose_name = 'Plan de trabajo Centro Misael'
        ordering     = ['-fecha_inicio']

    def __str__(self):
        return f'Plan Misael — {self.nino} por {self.profesional_nombre}'
