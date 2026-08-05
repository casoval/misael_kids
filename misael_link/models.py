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


class PlanTrabajoMisael(ModeloBase):
    """
    Plan de trabajo creado por un profesional del Centro Misael
    para ser ejecutado por la educadora del jardín.
    Se vincula a un PlanIndividual de la app agenda.

    Centro Misael no expone ninguna API para consultar esto en vivo (se
    revisó su repo: no hay endpoint de pacientes/evaluaciones/planes), así
    que esto sigue siendo un registro manual — pero con más contexto y
    con el informe adjunto, para no depender de tener que preguntarle al
    profesional cada dato por WhatsApp.
    """
    nino              = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='planes_misael')
    derivacion        = models.ForeignKey(Derivacion, on_delete=models.SET_NULL, null=True, blank=True)
    plan_individual   = models.OneToOneField(
        'agenda.PlanIndividual', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='plan_misael'
    )
    profesional_email    = models.EmailField(help_text='Email del profesional en el Centro Misael')
    profesional_nombre   = models.CharField(max_length=200)
    profesional_telefono = models.CharField(max_length=20, blank=True)
    area_intervencion    = models.CharField(
        max_length=150, blank=True,
        help_text='Ej: Lenguaje, Terapia ocupacional, Psicología...'
    )
    frecuencia_sesiones  = models.CharField(
        max_length=100, blank=True,
        help_text='Ej: 2 veces por semana'
    )
    descripcion       = models.TextField(help_text='Objetivos y lineamientos del plan')
    notas_seguimiento = models.TextField(
        blank=True,
        help_text='Avances, observaciones de la educadora, ajustes acordados con el profesional'
    )
    informe_pdf       = models.FileField(
        upload_to='planes_misael/', null=True, blank=True,
        help_text='Informe o plan de trabajo del Centro Misael, en PDF'
    )
    fecha_inicio      = models.DateField()
    fecha_fin         = models.DateField(null=True, blank=True)
    proxima_revision  = models.DateField(
        null=True, blank=True,
        help_text='Cuándo toca revisar/renovar el plan con el Centro Misael'
    )
    activo            = models.BooleanField(default=True)
    consentimiento_tutor = models.BooleanField(default=False,
        help_text='El tutor autorizó compartir información entre ambos centros')

    # ── Sincronización automática desde Centro Misael ──────────────
    # Si el plan/informe fue traído automáticamente desde la API de
    # Centro Misael (en vez de cargado a mano), guardamos el ID del
    # documento de origen para no volver a importarlo en cada sync.
    documento_centro_id = models.PositiveIntegerField(
        null=True, blank=True, unique=True,
        help_text='ID del DocumentoPaciente en Centro Misael, si fue traído automáticamente'
    )
    origen = models.CharField(
        max_length=20,
        choices=[('manual', 'Cargado manualmente'), ('sincronizado', 'Sincronizado desde Centro Misael')],
        default='manual',
    )

    class Meta:
        verbose_name = 'Plan de trabajo Centro Misael'
        ordering     = ['-fecha_inicio']

    def __str__(self):
        return f'Plan Misael — {self.nino} por {self.profesional_nombre}'
