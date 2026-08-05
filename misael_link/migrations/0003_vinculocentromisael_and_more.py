import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('misael_link', '0002_plantrabajomisael_area_intervencion_and_more'),
        ('ninos', '0001_initial'),
        ('personal', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='plantrabajomisael',
            name='documento_centro_id',
            field=models.PositiveIntegerField(
                blank=True, null=True, unique=True,
                help_text='ID del DocumentoPaciente en Centro Misael, si fue traído automáticamente',
            ),
        ),
        migrations.AddField(
            model_name='plantrabajomisael',
            name='origen',
            field=models.CharField(
                choices=[('manual', 'Cargado manualmente'), ('sincronizado', 'Sincronizado desde Centro Misael')],
                default='manual', max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='VinculoCentroMisael',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('paciente_centro_id', models.PositiveIntegerField(help_text='ID del Paciente en Centro Misael (centro_terapias_v2)')),
                ('nombre_paciente_centro', models.CharField(blank=True, max_length=200, help_text='Nombre del paciente al momento de vincular, para referencia rápida')),
                ('estado_centro_cache', models.CharField(blank=True, max_length=10, help_text='Último estado (activo/inactivo) visto en Centro Misael. Informativo solamente.')),
                ('fecha_vinculacion', models.DateTimeField(auto_now_add=True)),
                ('ultima_sincronizacion', models.DateTimeField(blank=True, null=True)),
                ('nino', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vinculo_centro_misael', to='ninos.nino')),
                ('vinculado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='personal.personal')),
            ],
            options={
                'verbose_name': 'Vínculo con Centro Misael',
                'ordering': ['-fecha_vinculacion'],
            },
        ),
    ]
