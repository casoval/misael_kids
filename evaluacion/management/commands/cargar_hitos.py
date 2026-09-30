"""
python manage.py cargar_hitos [--actualizar]

Carga (o repone) el catálogo de hitos del desarrollo. Seguro de ejecutar varias
veces. Por defecto solo crea los hitos que faltan y no toca los existentes;
con --actualizar restablece edades y descripción de TODOS los del catálogo.
"""
from django.core.management.base import BaseCommand

from evaluacion.models import HitoDesarrollo
from evaluacion.seed import cargar_catalogo


class Command(BaseCommand):
    help = 'Carga el catálogo de hitos del desarrollo infantil (0-72 meses).'

    def add_arguments(self, parser):
        parser.add_argument('--actualizar', action='store_true',
                            help='Sobrescribe edades y descripción de los hitos ya existentes.')

    def handle(self, *args, **opts):
        creados, actualizados, omitidos = cargar_catalogo(HitoDesarrollo, opts['actualizar'])
        if opts['verbosity'] >= 1:
            self.stdout.write(self.style.SUCCESS(
                f'Catálogo de hitos: {creados} creados, {actualizados} actualizados, '
                f'{omitidos} sin cambios (total {HitoDesarrollo.objects.count()}).'))
