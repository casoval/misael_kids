"""
asistencia/models.py
Registro diario de asistencia del niño.
"""
from django.db import models
from core.models import ModeloBase


class Asistencia(ModeloBase):
    ESTADO_PRESENTE           = 'presente'
    ESTADO_AUSENTE_JUSTIFICADO = 'ausente_justificado'
    ESTADO_AUSENTE            = 'ausente'
    ESTADOS = [
        (ESTADO_PRESENTE,            'Presente'),
        (ESTADO_AUSENTE_JUSTIFICADO, 'Ausente justificado'),
        (ESTADO_AUSENTE,             'Ausente'),
    ]

    inscripcion       = models.ForeignKey('inscripciones.Inscripcion', on_delete=models.CASCADE, related_name='asistencias')
    fecha             = models.DateField()
    estado            = models.CharField(max_length=25, choices=ESTADOS, default=ESTADO_PRESENTE)
    hora_entrada      = models.TimeField(null=True, blank=True)
    hora_salida       = models.TimeField(null=True, blank=True)
    entregado_por     = models.CharField(max_length=200, blank=True)
    retirado_por      = models.CharField(max_length=200, blank=True)
    retiro_autorizado = models.BooleanField(default=True)
    obs_entrada       = models.TextField(blank=True)
    obs_salida        = models.TextField(blank=True)
    motivo_ausencia   = models.TextField(blank=True)
    registrado_por    = models.ForeignKey('accounts.Usuario', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name        = 'Asistencia'
        verbose_name_plural = 'Asistencias'
        ordering            = ['-fecha']
        unique_together     = [['inscripcion', 'fecha']]

    def __str__(self):
        return f'{self.inscripcion.nino} — {self.fecha} ({self.get_estado_display()})'
