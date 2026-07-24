"""
Misael Kids — Configuración de producción
"""
from .base import *
import environ

env = environ.Env()

DEBUG = False

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Whitenoise para archivos estáticos
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# En Django 4.2+ el storage se configura con STORAGES (no con la antigua
# STATICFILES_STORAGE, que Django ya no lee — quedaba configurada pero
# sin efecto real, así que WhiteNoise nunca comprimía ni le ponía hash
# a los archivos, y por lo tanto no había cache-busting automático).
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
