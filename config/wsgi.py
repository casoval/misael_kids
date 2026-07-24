"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
from pathlib import Path

from django.core.wsgi import get_wsgi_application

# Igual que en manage.py: cargamos el DJANGO_SETTINGS_MODULE del .env antes
# de aplicar el default, para que nunca dependa de que alguien lo exporte
# manualmente en el entorno que arranca el proceso.
try:
    import environ
    environ.Env.read_env(str(Path(__file__).resolve().parent.parent / '.env'))
except ImportError:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

application = get_wsgi_application()
