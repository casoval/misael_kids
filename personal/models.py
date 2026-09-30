"""
personal/models.py
Perfil del personal educativo, asignaciones multisucursal y RRHH básico.
"""
from django.db import models
from core.models import ModeloBase


class Personal(ModeloBase):
    """
    Perfil del personal del jardín (educadoras, ayudantes, etc.)
    El acceso al sistema (Usuario) es OPCIONAL, igual que en Tutor: la ficha
    existe por sí sola y luego se le "da acceso" con usuario y contraseña.
    """
    ROL_EDUCADORA   = 'educadora'
    ROL_AYUDANTE    = 'ayudante'
    ROL_DIRECTORA   = 'directora'
    ROL_RECEPCIONISTA = 'recepcionista'
    ROL_COCINA      = 'cocina'

    ROLES = [
        (ROL_EDUCADORA,      'Educadora'),
        (ROL_AYUDANTE,       'Ayudante'),
        (ROL_DIRECTORA,      'Directora'),
        (ROL_RECEPCIONISTA, 'Recepcionista'),
        (ROL_COCINA,         'Cocina'),
    ]

    usuario       = models.OneToOneField(
        'accounts.Usuario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='perfil_personal'
    )
    nombres       = models.CharField(max_length=100)
    apellidos     = models.CharField(max_length=100)
    ci            = models.CharField(max_length=20, unique=True, verbose_name='CI')
    telefono      = models.CharField(max_length=20, blank=True)
    rol           = models.CharField(max_length=20, choices=ROLES)
    especialidad  = models.CharField(max_length=200, blank=True)
    foto          = models.ImageField(upload_to='personal/', null=True, blank=True)
    fecha_ingreso = models.DateField()
    activo        = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Personal'
        verbose_name_plural = 'Personal'
        ordering            = ['apellidos', 'nombres']

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'.strip()

    def save(self, *args, **kwargs):
        u = self.usuario
        # Fichas nuevas ligadas a un usuario sin nombres propios: se copian de él.
        if u and not (self.nombres and self.apellidos):
            self.nombres   = self.nombres   or u.nombres
            self.apellidos = self.apellidos or u.apellidos
        super().save(*args, **kwargs)
        if not u:
            return
        # Ficha y usuario siempre coinciden en nombre y rol (los permisos usan el
        # rol del USUARIO). Un admin nunca se degrada por tener ficha.
        campos = []
        if u.nombres != self.nombres:
            u.nombres = self.nombres; campos.append('nombres')
        if u.apellidos != self.apellidos:
            u.apellidos = self.apellidos; campos.append('apellidos')
        if self.telefono and u.telefono != self.telefono:
            u.telefono = self.telefono; campos.append('telefono')
        if u.rol != self.rol and u.rol != 'admin':
            u.rol = self.rol; campos.append('rol')
        if campos:
            u.save(update_fields=campos)

    def __str__(self):
        return f'{self.nombre_completo} — {self.get_rol_display()}'


class AsignacionPersonal(ModeloBase):
    """
    Asigna a un miembro del personal a una sucursal + sala + turno.
    Una educadora puede tener múltiples asignaciones activas simultáneas
    (ej: sala cuna mañana en sucursal A y sala medio tarde en sucursal B).
    """
    personal      = models.ForeignKey(Personal, on_delete=models.CASCADE, related_name='asignaciones')
    sucursal      = models.ForeignKey('core.Sucursal', on_delete=models.CASCADE)
    sala          = models.ForeignKey('core.Sala', on_delete=models.CASCADE)
    turno         = models.ForeignKey('core.Turno', on_delete=models.CASCADE)
    fecha_inicio  = models.DateField()
    fecha_fin     = models.DateField(null=True, blank=True, help_text='Nulo = asignación vigente')
    es_titular    = models.BooleanField(default=True, help_text='Titular o sustituta')
    activa        = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Asignación de personal'
        verbose_name_plural = 'Asignaciones de personal'
        ordering            = ['-fecha_inicio']

    def __str__(self):
        return f'{self.personal} → {self.sala} {self.turno}'


class AsistenciaPersonal(ModeloBase):
    """
    Registro diario de asistencia del personal (RRHH básico).
    """
    ESTADO_PRESENTE  = 'presente'
    ESTADO_AUSENTE   = 'ausente'
    ESTADO_PERMISO   = 'permiso'
    ESTADO_VACACION  = 'vacacion'
    ESTADO_ENFERMEDAD = 'enfermedad'

    ESTADOS = [
        (ESTADO_PRESENTE,   'Presente'),
        (ESTADO_AUSENTE,    'Ausente'),
        (ESTADO_PERMISO,    'Con permiso'),
        (ESTADO_VACACION,   'Vacaciones'),
        (ESTADO_ENFERMEDAD, 'Baja por enfermedad'),
    ]

    personal      = models.ForeignKey(Personal, on_delete=models.CASCADE, related_name='asistencias')
    sucursal      = models.ForeignKey('core.Sucursal', on_delete=models.CASCADE)
    fecha         = models.DateField()
    hora_entrada  = models.TimeField(null=True, blank=True)
    hora_salida   = models.TimeField(null=True, blank=True)
    estado        = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_PRESENTE)
    observacion   = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Asistencia del personal'
        verbose_name_plural = 'Asistencias del personal'
        ordering            = ['-fecha']
        unique_together     = [['personal', 'fecha', 'sucursal']]

    def __str__(self):
        return f'{self.personal} — {self.fecha} ({self.get_estado_display()})'
