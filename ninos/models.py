"""
ninos/models.py
Ficha del niño, tutores, personas autorizadas y documentos.
"""
from django.db import models
from core.models import ModeloBase


class Nino(ModeloBase):
    """
    Ficha única del niño. Se crea una sola vez.
    Las inscripciones (sala/turno/sucursal) se gestionan en la app inscripciones.
    """
    GENERO_MASCULINO = 'M'
    GENERO_FEMENINO  = 'F'
    GENERO_OTRO      = 'O'
    GENEROS = [
        (GENERO_MASCULINO, 'Masculino'),
        (GENERO_FEMENINO,  'Femenino'),
        (GENERO_OTRO,      'Otro'),
    ]

    nombres              = models.CharField(max_length=100)
    apellidos            = models.CharField(max_length=100)
    fecha_nacimiento     = models.DateField()
    genero               = models.CharField(max_length=1, choices=GENEROS)
    foto                 = models.ImageField(upload_to='ninos/', null=True, blank=True)
    alergias             = models.TextField(blank=True, help_text='Alergias alimentarias o medicamentosas')
    condiciones_medicas  = models.TextField(blank=True, help_text='Condiciones de salud relevantes')
    medicacion_habitual  = models.TextField(blank=True)
    tiene_plan_misael    = models.BooleanField(default=False, help_text='Tiene plan de trabajo del Centro Misael')
    observaciones        = models.TextField(blank=True)
    activo               = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Niño'
        verbose_name_plural = 'Niños'
        ordering            = ['apellidos', 'nombres']

    def __str__(self):
        return f'{self.nombres} {self.apellidos}'

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'

    @property
    def edad_en_meses(self):
        from datetime import date
        hoy = date.today()
        return (hoy.year - self.fecha_nacimiento.year) * 12 + (hoy.month - self.fecha_nacimiento.month)


class Tutor(ModeloBase):
    """
    Padre, madre o tutor legal del niño.
    Puede tener cuenta de acceso al portal de padres.
    """
    PARENTESCO_PADRE  = 'padre'
    PARENTESCO_MADRE  = 'madre'
    PARENTESCO_ABUELO = 'abuelo'
    PARENTESCO_TUTOR  = 'tutor_legal'
    PARENTESCO_OTRO   = 'otro'

    PARENTESCOS = [
        (PARENTESCO_PADRE,  'Padre'),
        (PARENTESCO_MADRE,  'Madre'),
        (PARENTESCO_ABUELO, 'Abuelo/a'),
        (PARENTESCO_TUTOR,  'Tutor legal'),
        (PARENTESCO_OTRO,   'Otro'),
    ]

    usuario     = models.OneToOneField(
        'accounts.Usuario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='perfil_tutor'
    )
    nombres     = models.CharField(max_length=100)
    apellidos   = models.CharField(max_length=100)
    ci          = models.CharField(max_length=20, verbose_name='CI/DNI')
    telefono    = models.CharField(max_length=20)
    telefono_alt = models.CharField(max_length=20, blank=True)
    email       = models.EmailField(blank=True)
    parentesco  = models.CharField(max_length=20, choices=PARENTESCOS)
    activo      = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Tutor'
        verbose_name_plural = 'Tutores'
        ordering            = ['apellidos', 'nombres']

    def __str__(self):
        return f'{self.nombres} {self.apellidos} ({self.get_parentesco_display()})'


class NinoTutor(ModeloBase):
    """
    Relación niño ↔ tutor. Un niño puede tener varios tutores.
    Solo un tutor puede ser el principal (recibe notificaciones por defecto).
    """
    nino        = models.ForeignKey(Nino, on_delete=models.CASCADE, related_name='tutores')
    tutor       = models.ForeignKey(Tutor, on_delete=models.CASCADE, related_name='ninos')
    es_principal = models.BooleanField(default=False)
    puede_retirar = models.BooleanField(default=True)

    class Meta:
        verbose_name      = 'Relación niño-tutor'
        unique_together   = [['nino', 'tutor']]

    def __str__(self):
        return f'{self.nino} ← {self.tutor}'


class PersonaAutorizada(ModeloBase):
    """
    Personas autorizadas a retirar al niño además de los tutores.
    Tiene vigencia de fecha y puede ser temporal.
    """
    nino          = models.ForeignKey(Nino, on_delete=models.CASCADE, related_name='autorizados')
    nombres       = models.CharField(max_length=100)
    apellidos     = models.CharField(max_length=100)
    ci            = models.CharField(max_length=20)
    telefono      = models.CharField(max_length=20)
    parentesco    = models.CharField(max_length=100)
    foto          = models.ImageField(upload_to='autorizados/', null=True, blank=True)
    vigencia_desde = models.DateField()
    vigencia_hasta = models.DateField(null=True, blank=True, help_text='Nulo = indefinida')
    activa        = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Persona autorizada'
        verbose_name_plural = 'Personas autorizadas'

    def __str__(self):
        return f'{self.nombres} {self.apellidos} → autorizado para {self.nino}'


class Documento(ModeloBase):
    """
    Documentos digitalizados del niño (contrato, partida, vacunas, etc.)
    """
    TIPO_CONTRATO   = 'contrato'
    TIPO_PARTIDA    = 'partida_nacimiento'
    TIPO_VACUNAS    = 'carnet_vacunas'
    TIPO_MEDICO     = 'informe_medico'
    TIPO_FOTO       = 'foto'
    TIPO_OTRO       = 'otro'

    TIPOS = [
        (TIPO_CONTRATO, 'Contrato de inscripción'),
        (TIPO_PARTIDA,  'Partida de nacimiento'),
        (TIPO_VACUNAS,  'Carnet de vacunas'),
        (TIPO_MEDICO,   'Informe médico'),
        (TIPO_FOTO,     'Foto'),
        (TIPO_OTRO,     'Otro'),
    ]

    nino          = models.ForeignKey(Nino, on_delete=models.CASCADE, related_name='documentos')
    tipo          = models.CharField(max_length=30, choices=TIPOS)
    nombre        = models.CharField(max_length=200)
    archivo       = models.FileField(upload_to='documentos/')
    fecha_subida  = models.DateField(auto_now_add=True)
    verificado    = models.BooleanField(default=False)
    observacion   = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Documento'
        verbose_name_plural = 'Documentos'
        ordering            = ['-fecha_subida']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.nino}'
