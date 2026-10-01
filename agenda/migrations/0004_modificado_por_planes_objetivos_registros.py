import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _campo():
    return models.ForeignKey(
        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
        related_name='+', to=settings.AUTH_USER_MODEL,
        help_text='Última persona que modificó este registro')


class Migration(migrations.Migration):

    dependencies = [
        ('agenda', '0003_planificaciongrupal_modificado_por'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name='planindividual',     name='modificado_por', field=_campo()),
        migrations.AddField(model_name='objetivoindividual', name='modificado_por', field=_campo()),
        migrations.AddField(model_name='registroobjetivo',   name='modificado_por', field=_campo()),
    ]
