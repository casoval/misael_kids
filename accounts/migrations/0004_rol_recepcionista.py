from django.db import migrations, models


def administrativo_a_recepcionista(apps, schema_editor):
    Usuario = apps.get_model('accounts', 'Usuario')
    Usuario.objects.filter(rol='administrativo').update(rol='recepcionista')


def recepcionista_a_administrativo(apps, schema_editor):
    Usuario = apps.get_model('accounts', 'Usuario')
    Usuario.objects.filter(rol='recepcionista').update(rol='administrativo')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_usuario_email'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='rol',
            field=models.CharField(
                choices=[
                    ('admin', 'Administrador'), ('directora', 'Directora'),
                    ('educadora', 'Educadora'), ('ayudante', 'Ayudante'),
                    ('tutor', 'Tutor / Padre'), ('profesional', 'Profesional Misael'),
                    ('cocina', 'Personal de cocina'), ('recepcionista', 'Recepcionista'),
                ],
                default='tutor', max_length=20,
            ),
        ),
        migrations.RunPython(administrativo_a_recepcionista, recepcionista_a_administrativo),
    ]
