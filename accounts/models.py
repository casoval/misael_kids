"""
accounts/models.py
Usuario personalizado y roles del sistema Misael Kids
"""
import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra_fields):
        username = extra_fields.get('username')
        if not email and not username:
            raise ValueError('Debes indicar un email o un nombre de usuario.')
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email or None, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', Usuario.ROL_ADMIN)
        return self.create_user(email, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """
    Usuario base del sistema.
    El rol define qué puede ver y hacer en cada módulo.
    """
    ROL_ADMIN         = 'admin'
    ROL_DIRECTORA     = 'directora'
    ROL_EDUCADORA     = 'educadora'
    ROL_AYUDANTE      = 'ayudante'
    ROL_TUTOR         = 'tutor'          # Padre / madre / tutor del niño
    ROL_PROFESIONAL   = 'profesional'    # Del Centro Misael
    ROL_COCINA        = 'cocina'
    ROL_ADMINISTRATIVO = 'administrativo'

    ROLES = [
        (ROL_ADMIN,          'Administrador'),
        (ROL_DIRECTORA,      'Directora'),
        (ROL_EDUCADORA,      'Educadora'),
        (ROL_AYUDANTE,       'Ayudante'),
        (ROL_TUTOR,          'Tutor / Padre'),
        (ROL_PROFESIONAL,    'Profesional Misael'),
        (ROL_COCINA,         'Personal de cocina'),
        (ROL_ADMINISTRATIVO, 'Administrativo'),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email      = models.EmailField(unique=True, null=True, blank=True)
    username   = models.CharField(max_length=50, unique=True, null=True, blank=True,
                     help_text='Nombre de usuario alternativo para personas sin email (tutores, profesionales, etc.)')
    nombres    = models.CharField(max_length=100)
    apellidos  = models.CharField(max_length=100)
    telefono   = models.CharField(max_length=20, blank=True)
    rol        = models.CharField(max_length=20, choices=ROLES, default=ROL_TUTOR)
    foto       = models.ImageField(upload_to='usuarios/', null=True, blank=True)
    activo     = models.BooleanField(default=True)

    is_staff   = models.BooleanField(default=False)
    is_active  = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UsuarioManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['nombres', 'apellidos']

    class Meta:
        verbose_name        = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering            = ['apellidos', 'nombres']

    def __str__(self):
        return f'{self.nombres} {self.apellidos} ({self.get_rol_display()})'

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'

    @property
    def identificador(self):
        """Email o nombre de usuario, lo que esté disponible."""
        return self.email or self.username
