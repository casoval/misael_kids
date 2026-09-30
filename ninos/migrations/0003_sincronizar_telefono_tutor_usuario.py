"""
Corrige datos existentes: tutores con cuenta de portal cuyo Usuario quedó sin
teléfono (o con uno distinto) porque el formulario nunca lo enviaba.
El teléfono de la ficha del tutor (el de la tarjeta del niño) es la fuente.
"""
from django.db import migrations


def sincronizar(apps, schema_editor):
    Tutor = apps.get_model('ninos', 'Tutor')
    for t in Tutor.objects.exclude(usuario__isnull=True).exclude(telefono='').select_related('usuario'):
        u = t.usuario
        if u.telefono != t.telefono:
            u.telefono = t.telefono
            u.save(update_fields=['telefono'])


class Migration(migrations.Migration):

    dependencies = [
        ('ninos', '0002_alter_tutor_ci'),
        ('accounts', '0004_rol_recepcionista'),
    ]

    operations = [
        migrations.RunPython(sincronizar, migrations.RunPython.noop),
    ]
