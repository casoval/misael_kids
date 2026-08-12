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
    solicitado_por   = models.ForeignKey(
        'personal.Personal', on_delete=models.SET_NULL, null=True, blank=True,
        help_text='Quién de Misael Kids solicitó la derivación. Puede quedar vacío '
                   'si el usuario no tiene una ficha de Personal asociada — la '
                   'derivación de todos modos puede crearla cualquier cuenta con permiso.',
    )
    motivo           = models.TextField(help_text='Señales o comportamientos observados')
    area_derivacion  = models.CharField(max_length=200, help_text='Ej: Terapia del lenguaje, psicología')
    estado           = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_SOLICITADA)
    fecha_solicitud  = models.DateField(auto_now_add=True)
    fecha_respuesta  = models.DateField(null=True, blank=True)
    respuesta_centro = models.TextField(blank=True)
    consentimiento_tutor = models.BooleanField(default=False)

    # ── Visto por Centro Misael ─────────────────────────────────────
    # Se marca cuando Centro Misael consulta esta derivación por primera
    # vez desde su página de vinculaciones, para poder pintar un aviso
    # de "nueva" del otro lado sin necesitar una tabla de alertas aparte.
    vista_por_centro = models.BooleanField(default=False)
    fecha_vista_por_centro = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Derivación al Centro Misael'
        ordering     = ['-fecha_solicitud']

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.nino_id and not hasattr(self.nino, 'vinculo_centro_misael'):
            raise ValidationError(
                'Este niño todavía no está vinculado con Centro Misael. '
                'Vincúlalo primero en la pestaña "Vincular con Centro Misael".'
            )

    def __str__(self):
        return f'Derivación {self.nino} — {self.area_derivacion} ({self.get_estado_display()})'


class VinculoCentroMisael(ModeloBase):
    """
    Vínculo entre un Nino de Misael Kids y un Paciente del Centro Misael
    (repo centro_terapias_v2, vía su API de integración).

    Un niño solo puede estar vinculado a un paciente. El vínculo se
    mantiene aunque el paciente pase a inactivo en Centro Misael: el
    jardín igual necesita seguir viendo sus planes de trabajo.
    """
    nino = models.OneToOneField(
        'ninos.Nino', on_delete=models.CASCADE, related_name='vinculo_centro_misael'
    )
    paciente_centro_id = models.PositiveIntegerField(
        help_text='ID del Paciente en Centro Misael (centro_terapias_v2)'
    )
    nombre_paciente_centro = models.CharField(
        max_length=200, blank=True,
        help_text='Nombre del paciente al momento de vincular, para referencia rápida'
    )
    estado_centro_cache = models.CharField(
        max_length=10, blank=True,
        help_text='Último estado (activo/inactivo) visto en Centro Misael. Informativo solamente.'
    )
    vinculado_por = models.ForeignKey(
        'personal.Personal', on_delete=models.SET_NULL, null=True, blank=True
    )
    fecha_vinculacion = models.DateTimeField(auto_now_add=True)
    ultima_sincronizacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Vínculo con Centro Misael'
        ordering = ['-fecha_vinculacion']

    def __str__(self):
        return f'{self.nino} ↔ paciente #{self.paciente_centro_id} en Centro Misael'

# NOTA: PlanTrabajoMisael se eliminó (ver migración 0004_delete_plantrabajomisael_and_more).
# Los planes de trabajo ahora los crea el profesional directamente en Centro
# Misael (modelo PlanTrabajo, repo centro_terapias_v2) y Misael Kids los
# consulta en vivo, de solo lectura, vía centro_misael_client.listar_planes_trabajo().
# Ya no hay copia local ni formulario manual del lado de Misael Kids.
