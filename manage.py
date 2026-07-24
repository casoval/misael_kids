#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main():
    # Antes de decidir el default, cargamos el DJANGO_SETTINGS_MODULE que
    # indique el .env del proyecto (si existe). Esto evita que un comando
    # corrido a mano (p. ej. por SSH en el servidor) caiga silenciosamente
    # en 'development' solo porque la variable no estaba exportada en esa
    # sesión de shell, aunque el .env real diga 'production'. Una variable
    # ya exportada en el entorno (por systemd, docker, etc.) sigue ganando.
    try:
        import environ
        environ.Env.read_env(str(Path(__file__).resolve().parent / '.env'))
    except ImportError:
        pass

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Está instalado y activado el entorno virtual?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
