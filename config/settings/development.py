"""
Misael Kids — Configuración de desarrollo
"""
from .base import *

DEBUG = True

INSTALLED_APPS += ['django_extensions']

# Mostrar emails en consola durante desarrollo
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Barra de debug (opcional, instalar si se necesita)
INTERNAL_IPS = ['127.0.0.1']

# Más permisivo en desarrollo
CORS_ALLOW_ALL_ORIGINS = True
