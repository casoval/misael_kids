"""
asistencia/tests.py
Pruebas de la mejora de asistencia: permiso NoEsTutor, validación de horas,
generación automática de cobros, y los endpoints historial/resumen-mensual.
"""
from datetime import date, timedelta
from rest_framework.test import APITestCase
from rest_framework import status

from accounts.models import Usuario
from core.models import Sucursal, Sala, Turno
from ninos.models import Nino, Tutor, NinoTutor
from inscripciones.models import Inscripcion, Cobro
from .models import Asistencia


class AsistenciaTestBase(APITestCase):
    """Arma sucursal/sala/turno + un niño con inscripción mensual y otro
    con inscripción diaria, más un usuario staff y un usuario tutor."""

    def setUp(self):
        self.sucursal = Sucursal.objects.create(nombre='Misael Kids - Camacho', direccion='Av. Camacho 123')
        self.sala = Sala.objects.create(
            sucursal=self.sucursal, nombre='Sala Cuna',
            edad_min_meses=0, edad_max_meses=24, capacidad_maxima=10,
        )
        self.turno = Turno.objects.create(
            sala=self.sala, nombre='Turno mañana', tipo=Turno.TIPO_MANANA,
            hora_inicio='08:00', hora_fin='12:00',
            costo_mensual='650.00', costo_diario='40.00',
        )

        self.staff = Usuario.objects.create_user(
            email='directora@misaelkids.test', password='clave12345',
            nombres='Jackie', apellidos='Castro',
            rol=Usuario.ROL_DIRECTORA, is_staff=True,
        )

        # Niño A: modalidad mensual, con tutor propio (para probar permisos)
        self.nino_a = Nino.objects.create(
            nombres='Anthony', apellidos='Nogales', fecha_nacimiento=date(2025, 1, 1), genero='M',
        )
        self.usuario_tutor = Usuario.objects.create_user(
            username='mama_anthony', password='clave12345',
            nombres='Karina', apellidos='Castro', rol=Usuario.ROL_TUTOR,
        )
        self.tutor = Tutor.objects.create(
            usuario=self.usuario_tutor, nombres='Karina', apellidos='Castro',
            ci='1234567', telefono='70000000', parentesco=Tutor.PARENTESCO_MADRE,
        )
        NinoTutor.objects.create(nino=self.nino_a, tutor=self.tutor, es_principal=True)
        self.insc_mensual = Inscripcion.objects.create(
            nino=self.nino_a, sucursal=self.sucursal, sala=self.sala, turno=self.turno,
            modalidad_pago=Inscripcion.MODALIDAD_MENSUAL,
            fecha_inicio=date.today(), costo_mensual='650.00', costo_diario='40.00',
        )

        # Niño B: modalidad diaria, SIN relación con el tutor de arriba
        # (para probar que el tutor de A no puede ver ni tocar nada de B).
        self.nino_b = Nino.objects.create(
            nombres='Valentina', apellidos='Rojas', fecha_nacimiento=date(2024, 6, 1), genero='F',
        )
        self.insc_diaria = Inscripcion.objects.create(
            nino=self.nino_b, sucursal=self.sucursal, sala=self.sala, turno=self.turno,
            modalidad_pago=Inscripcion.MODALIDAD_DIARIA,
            fecha_inicio=date.today(), costo_mensual='650.00', costo_diario='40.00',
        )

    def url_lista(self):
        return '/api/asistencia/asistencia/'


class PermisoTutorTests(AsistenciaTestBase):
    """El hueco de seguridad que se corrigió: un tutor no debe poder crear,
    editar ni borrar asistencia — ni siquiera la de su propio hijo."""

    def test_tutor_no_puede_crear_asistencia_de_su_propio_hijo(self):
        self.client.force_authenticate(self.usuario_tutor)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_mensual.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_tutor_no_puede_crear_asistencia_de_otro_nino(self):
        """El caso más grave: antes del fix, un tutor podía marcar
        asistencia de un niño que NO es su hijo, incluso generando un
        cobro de mensualidad/diario para una familia ajena."""
        self.client.force_authenticate(self.usuario_tutor)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_diaria.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Cobro.objects.filter(inscripcion=self.insc_diaria).count(), 0)

    def test_tutor_solo_lee_la_asistencia_de_su_propio_hijo(self):
        Asistencia.objects.create(inscripcion=self.insc_mensual, fecha=date.today(), estado=Asistencia.ESTADO_PRESENTE)
        Asistencia.objects.create(inscripcion=self.insc_diaria, fecha=date.today(), estado=Asistencia.ESTADO_PRESENTE)
        self.client.force_authenticate(self.usuario_tutor)
        resp = self.client.get(self.url_lista())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        ids_vistos = {str(r['inscripcion']) for r in data}
        self.assertEqual(ids_vistos, {str(self.insc_mensual.id)})

    def test_staff_si_puede_crear_asistencia(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_mensual.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)


class GeneracionDeCobrosTests(AsistenciaTestBase):
    """La asistencia 'presente' sigue generando cobros automáticamente
    (comportamiento preexistente) — se confirma que el fix de permisos no
    lo rompió para el personal."""

    def test_presente_en_diaria_genera_cobro_del_dia(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_diaria.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertTrue(Cobro.objects.filter(
            inscripcion=self.insc_diaria, tipo=Cobro.TIPO_DIARIO,
            periodo=date.today().strftime('%Y-%m-%d'),
        ).exists())

    def test_presente_en_mensual_genera_ciclo_si_no_existe(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(Cobro.objects.filter(inscripcion=self.insc_mensual).count(), 0)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_mensual.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Cobro.objects.filter(inscripcion=self.insc_mensual, tipo=Cobro.TIPO_MENSUALIDAD).count(), 1)

    def test_ausente_no_genera_cobro(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_diaria.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_AUSENTE,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Cobro.objects.filter(inscripcion=self.insc_diaria).count(), 0)


class ValidacionHorasTests(AsistenciaTestBase):
    """La validación nueva: hora_salida debe ser posterior a hora_entrada."""

    def test_rechaza_salida_antes_de_entrada(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_mensual.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
            'hora_entrada': '09:00',
            'hora_salida': '08:00',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('hora_salida', resp.data)

    def test_rechaza_salida_igual_a_entrada(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_mensual.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
            'hora_entrada': '09:00',
            'hora_salida': '09:00',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_acepta_salida_posterior_a_entrada(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_mensual.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
            'hora_entrada': '08:00',
            'hora_salida': '12:00',
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_patch_parcial_compara_con_valor_ya_guardado(self):
        """Si solo se manda hora_salida en un PATCH, se debe comparar
        contra la hora_entrada que ya estaba guardada, no contra None."""
        self.client.force_authenticate(self.staff)
        creado = self.client.post(self.url_lista(), {
            'inscripcion': str(self.insc_mensual.id),
            'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE,
            'hora_entrada': '09:00',
        })
        self.assertEqual(creado.status_code, status.HTTP_201_CREATED, creado.data)
        asist_id = creado.data['id']
        resp = self.client.patch(f'{self.url_lista()}{asist_id}/', {'hora_salida': '08:00'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class HistorialYResumenTests(AsistenciaTestBase):
    """Los dos endpoints nuevos/conectados: historial (rango de fechas) y
    resumen-mensual (ya existía, ahora el frontend lo usa)."""

    def setUp(self):
        super().setUp()
        hoy = date.today()
        Asistencia.objects.create(inscripcion=self.insc_mensual, fecha=hoy, estado=Asistencia.ESTADO_PRESENTE)
        Asistencia.objects.create(inscripcion=self.insc_mensual, fecha=hoy - timedelta(days=5), estado=Asistencia.ESTADO_AUSENTE)
        Asistencia.objects.create(inscripcion=self.insc_mensual, fecha=hoy - timedelta(days=40), estado=Asistencia.ESTADO_AUSENTE_JUSTIFICADO)
        Asistencia.objects.create(inscripcion=self.insc_diaria, fecha=hoy, estado=Asistencia.ESTADO_PRESENTE)

    def test_historial_respeta_rango_de_fechas_por_defecto(self):
        """Por defecto son los últimos 30 días: el registro de hace 40
        días no debería aparecer."""
        self.client.force_authenticate(self.staff)
        resp = self.client.get(f'{self.url_lista()}historial/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        fechas = {r['fecha'] for r in resp.data}
        self.assertIn(date.today().isoformat(), fechas)
        self.assertNotIn((date.today() - timedelta(days=40)).isoformat(), fechas)

    def test_historial_con_rango_explicito_incluye_todo(self):
        self.client.force_authenticate(self.staff)
        desde = (date.today() - timedelta(days=45)).isoformat()
        resp = self.client.get(f'{self.url_lista()}historial/?desde={desde}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 4)

    def test_historial_filtra_por_nino_para_tutor(self):
        self.client.force_authenticate(self.usuario_tutor)
        resp = self.client.get(f'{self.url_lista()}historial/?desde=2000-01-01')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        inscripciones_vistas = {str(r['inscripcion']) for r in resp.data}
        self.assertEqual(inscripciones_vistas, {str(self.insc_mensual.id)})

    def test_resumen_mensual_cuenta_correctamente(self):
        self.client.force_authenticate(self.staff)
        hoy = date.today()
        resp = self.client.get(f'{self.url_lista()}resumen-mensual/?mes={hoy.month}&año={hoy.year}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Al menos el registro de hoy de insc_mensual e insc_diaria deben contar
        # (el de hace 5 días también, si cae en el mismo mes calendario).
        self.assertGreaterEqual(resp.data['total'], 2)
        self.assertGreaterEqual(resp.data['presentes'], 2)
