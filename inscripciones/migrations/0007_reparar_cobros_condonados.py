# Repara cobros cerrados con "Cerrar con lo pagado" cuyo monto_condonado quedó
# desfasado tras devoluciones (pagado neto + condonado < monto_final), lo que
# los dejaba en "Parcial" y bloqueaba el mes siguiente.
from decimal import Decimal
from django.db import migrations
from django.db.models import Sum


def reparar(apps, schema_editor):
    Cobro = apps.get_model('inscripciones', 'Cobro')
    for cobro in Cobro.objects.filter(monto_condonado_inicial__isnull=False).exclude(estado='anulado'):
        pagos = cobro.pagos.aggregate(t=Sum('monto'))['t'] or Decimal('0')
        devs = cobro.devoluciones.aggregate(t=Sum('monto'))['t'] or Decimal('0')
        condonado = max(cobro.monto_final - (pagos - devs), Decimal('0'))
        cobro.monto_condonado = condonado
        cobro.estado = 'pagado'
        cobro.save(update_fields=['monto_condonado', 'estado'])


class Migration(migrations.Migration):

    dependencies = [
        ('inscripciones', '0006_cobro_monto_condonado_inicial'),
    ]

    operations = [
        migrations.RunPython(reparar, migrations.RunPython.noop),
    ]
