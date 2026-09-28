# Generated manually, siguiendo el mismo estilo que 0003_cobro_monto_condonado_...
# Agrega monto_condonado_inicial: la "foto" del monto condonado al momento
# del cierre ("Cerrar con lo pagado"), que ya no se vuelve a tocar. Permite
# a la interfaz mostrar cuando `monto_condonado` fue ajustado más tarde por
# una devolución sobre un mes ya cerrado.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inscripciones', '0005_recibos_y_devoluciones'),
    ]

    operations = [
        migrations.AddField(
            model_name='cobro',
            name='monto_condonado_inicial',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
    ]
