from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('misael_link', '0003_vinculocentromisael_and_more'),
        ('agenda', '0001_initial'),
    ]

    operations = [
        # Los planes de trabajo ahora los crea el profesional directamente
        # en Centro Misael (modelo PlanTrabajo, repo centro_terapias_v2) y
        # se consultan en vivo, de solo lectura, sin copia local.
        migrations.DeleteModel(
            name='PlanTrabajoMisael',
        ),
        migrations.AddField(
            model_name='derivacion',
            name='vista_por_centro',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='derivacion',
            name='fecha_vista_por_centro',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
