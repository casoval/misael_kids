from django.db import migrations, models


def administrativo_a_recepcionista(apps, schema_editor):
    Personal = apps.get_model('personal', 'Personal')
    Personal.objects.filter(rol='administrativo').update(rol='recepcionista')


def recepcionista_a_administrativo(apps, schema_editor):
    Personal = apps.get_model('personal', 'Personal')
    Personal.objects.filter(rol='recepcionista').update(rol='administrativo')


class Migration(migrations.Migration):

    dependencies = [
        ('personal', '0003_personal_foto'),
    ]

    operations = [
        migrations.AlterField(
            model_name='personal',
            name='rol',
            field=models.CharField(
                choices=[
                    ('educadora', 'Educadora'), ('ayudante', 'Ayudante'),
                    ('directora', 'Directora'), ('recepcionista', 'Recepcionista'),
                    ('cocina', 'Cocina'),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(administrativo_a_recepcionista, recepcionista_a_administrativo),
    ]
