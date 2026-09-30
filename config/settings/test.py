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
