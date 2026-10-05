"""
Misael Kids — Configuración para tests (SQLite en memoria, sin PostgreSQL).
Uso:  python manage.py test --settings=config.settings.test
"""
import os
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key')
os.environ.setdefault('DJANGO_DEBUG', 'False')
os.environ.setdefault('DB_NAME', 'x')
os.environ.setdefault('DB_USER', 'x')
os.environ.setdefault('DB_PASSWORD', 'x')

from .base import *  # noqa

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Los tests NUNCA deben subir nada a Cloudinary. base.py lee el archivo .env, y
# si ahí hay credenciales reales (p. ej. en el servidor), el storage por defecto
# sería Cloudinary y los tests que suben una foto la enviarían a la cuenta real.
STORAGES = {
    'default':     {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
