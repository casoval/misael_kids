"""
Precarga el catálogo de hitos del desarrollo (0-72 meses).

Antes el catálogo dependía de un `loaddata` manual que casi nunca se ejecutaba
(p. ej. en un despliegue solo con `migrate`), por eso la pantalla
"Catálogo de hitos" aparecía vacía. Ahora se carga solo con `migrate`.
Es idempotente: no duplica ni pisa hitos que ya existan.
"""
from django.db import migrations


def cargar(apps, schema_editor):
    from evaluacion.seed import cargar_catalogo
    cargar_catalogo(apps.get_model('evaluacion', 'HitoDesarrollo'))


class Migration(migrations.Migration):

    dependencies = [
        ('evaluacion', '0002_educadora_opcional'),
    ]

    operations = [
        # Reversa vacía: borrar el catálogo arrastraría las evaluaciones de los niños.
        migrations.RunPython(cargar, migrations.RunPython.noop),
    ]
