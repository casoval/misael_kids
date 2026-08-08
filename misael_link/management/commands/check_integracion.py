"""
Diagnóstico de un solo comando para la integración con Centro Misael.

Uso en el servidor:
    cd /var/www/misael_kids
    ./venv/bin/python manage.py check_integracion

Hace una llamada real de red al endpoint /ping/ de Centro Misael para
confirmar que la URL, la API key y la conectividad funcionan de punta
a punta — no solo que las variables existan.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.migrations.executor import MigrationExecutor
from django.db import connections

from misael_link import centro_misael_client as cm


def _ok(msg):
    return f'  ✅ {msg}'


def _fail(msg):
    return f'  ❌ {msg}'


class Command(BaseCommand):
    help = 'Diagnostica la integración con Centro Misael: variables, migraciones y conexión real.'

    def handle(self, *args, **options):
        problemas = []

        # ── 1. Variables de entorno ──────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('1. Variables de entorno'))
        url = getattr(settings, 'CENTRO_MISAEL_API_URL', '')
        key = getattr(settings, 'CENTRO_MISAEL_API_KEY', '')
        if not url:
            self.stdout.write(self.style.ERROR(_fail('CENTRO_MISAEL_API_URL no está configurada en el .env.')))
            problemas.append('CENTRO_MISAEL_API_URL vacía')
        else:
            self.stdout.write(self.style.SUCCESS(_ok(f'CENTRO_MISAEL_API_URL = {url}')))
        if not key:
            self.stdout.write(self.style.ERROR(_fail('CENTRO_MISAEL_API_KEY no está configurada en el .env.')))
            problemas.append('CENTRO_MISAEL_API_KEY vacía')
        else:
            self.stdout.write(self.style.SUCCESS(_ok(
                f'CENTRO_MISAEL_API_KEY configurada (empieza con "{key[:4]}...", {len(key)} caracteres). '
                'Confirma que sea EXACTAMENTE la misma que MISAEL_KIDS_API_KEY en el .env de Centro Misael.'
            )))

        # ── 2. Migraciones pendientes de misael_link ────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n2. Migraciones'))
        conn = connections['default']
        executor = MigrationExecutor(conn)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        relevantes = [(m, b) for m, b in plan if m.app_label == 'misael_link']
        if relevantes:
            self.stdout.write(self.style.ERROR(_fail(f'Hay {len(relevantes)} migración(es) de misael_link SIN aplicar:')))
            for m, _ in relevantes:
                self.stdout.write(f'      - {m.app_label}.{m.name}')
            self.stdout.write('    → corre: ./venv/bin/python manage.py migrate')
            problemas.append('migraciones de misael_link pendientes')
        else:
            self.stdout.write(self.style.SUCCESS(_ok('misael_link está al día con las migraciones.')))

        # ── 3. Conexión real con Centro Misael ───────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n3. Conexión real a Centro Misael'))
        if not url or not key:
            self.stdout.write(self.style.WARNING('  ⚠️  Se omite la prueba de conexión: faltan variables arriba.'))
        else:
            try:
                # Reutiliza el mismo cliente que usa la vista real, con query
                # vacío — es exactamente lo que dispara la pestaña de
                # vinculación al abrirse (lista los primeros pacientes).
                # Reutiliza el mismo cliente que usa la vista real, para que
                # el resultado sea representativo del comportamiento real.
                resultados = cm.buscar_pacientes('a')
                self.stdout.write(self.style.SUCCESS(_ok(
                    f'Conexión exitosa. Centro Misael respondió con {len(resultados)} paciente(s) '
                    f'para una búsqueda de prueba ("a").'
                )))
            except cm.CentroMisaelNoConfigurado as exc:
                self.stdout.write(self.style.ERROR(_fail(str(exc))))
                problemas.append('cliente reporta no configurado')
            except cm.CentroMisaelError as exc:
                self.stdout.write(self.style.ERROR(_fail(f'Falló la conexión real: {exc}')))
                self.stdout.write(
                    '    → si dice "API key rechazada": las claves no coinciden entre ambos .env.\n'
                    '    → si dice "No se pudo conectar": revisa DNS/firewall entre ambos servidores '
                    '(¿CENTRO_MISAEL_API_URL es alcanzable por HTTPS desde este servidor?).\n'
                    '    → si dice "respondió 500": hay un error del lado de Centro Misael, revisa su log.'
                )
                problemas.append('conexión real fallida')

        # ── Resumen ───────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n── Resumen ──'))
        if problemas:
            self.stdout.write(self.style.ERROR(f'Se encontraron {len(problemas)} problema(s): ' + ', '.join(problemas)))
        else:
            self.stdout.write(self.style.SUCCESS('Todo en orden: la integración con Centro Misael debería funcionar.'))
