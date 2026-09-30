from django.db import migrations, models
import django.db.models.deletion


def copiar_nombres(apps, schema_editor):
    """Las fichas existentes toman nombres/apellidos de su usuario."""
    Personal = apps.get_model('personal', 'Personal')
    for p in Personal.objects.select_related('usuario').all():
        if p.usuario_id:
            p.nombres, p.apellidos = p.usuario.nombres, p.usuario.apellidos
            p.save(update_fields=['nombres', 'apellidos'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_rol_recepcionista'),
        ('personal', '0004_rol_recepcionista'),
    ]

    operations = [
        migrations.AddField(
            model_name='personal', name='nombres',
            field=models.CharField(max_length=100, default=''), preserve_default=False,
        ),
        migrations.AddField(
            model_name='personal', name='apellidos',
            field=models.CharField(max_length=100, default=''), preserve_default=False,
        ),
        migrations.RunPython(copiar_nombres, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='personal', name='usuario',
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='perfil_personal', to='accounts.usuario'),
        ),
        migrations.AlterModelOptions(
            name='personal',
            options={'ordering': ['apellidos', 'nombres'],
                     'verbose_name': 'Personal', 'verbose_name_plural': 'Personal'},
        ),
    ]
