"""
salud/models.py
Incidentes de salud y medicamentos autorizados.
"""
from django.db import models
from core.models import ModeloBase


class IncidenteSalud(ModeloBase):
    TIPO_ACCIDENTE  = 'accidente'
    TIPO_ENFERMEDAD = 'enfermedad'
    TIPO_SINTOMA    = 'sintoma'
    TIPO_MEDICACION = 'medicacion'
    TIPOS = [
        (TIPO_ACCIDENTE,  'Accidente'),
        (TIPO_ENFERMEDAD, 'Enfermedad'),
        (TIPO_SINTOMA,    'Síntoma observado'),
        (TIPO_MEDICACION, 'Medicación aplicada'),
    ]

    nino              = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='incidentes_salud')
    # Quién lo registró: lo completa el servidor con la ficha de Personal del usuario
    # logueado. Puede quedar vacío (p. ej. un admin sin ficha) y, si se elimina esa
    # ficha, el incidente se conserva en vez de borrarse en cascada.
    reportado_por     = models.ForeignKey('personal.Personal', on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name='incidentes_reportados')
    sucursal          = models.ForeignKey('core.Sucursal', on_delete=models.CASCADE)
    fecha             = models.DateField()
    hora              = models.TimeField()
    tipo              = models.CharField(max_length=15, choices=TIPOS)
    descripcion       = models.TextField()
    accion_tomada     = models.TextField()
    notificado_tutor  = models.BooleanField(default=False)
    hora_notificacion = models.TimeField(null=True, blank=True)
    requirio_atencion_medica = models.BooleanField(default=False)

    class Meta:
        verbose_name        = 'Incidente de salud'
        verbose_name_plural = 'Incidentes de salud'
        ordering            = ['-fecha', '-hora']

    def __str__(self):
        return f'{self.nino} — {self.get_tipo_display()} {self.fecha}'
