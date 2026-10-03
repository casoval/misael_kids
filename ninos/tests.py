from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Usuario
from ninos.models import Tutor


class SincroniaTelefonoTutorTests(TestCase):
    def _usuario(self, **kw):
        return Usuario.objects.create_user(
            username=kw.pop('username', 'papa1'), password='Clave12345!',
            nombres='Ana', apellidos='Pérez', rol='tutor', **kw)

    def _tutor(self, usuario=None, telefono='76543210'):
        return Tutor.objects.create(
            usuario=usuario, nombres='Ana', apellidos='Pérez', ci='123',
            telefono=telefono, parentesco='madre')

    def test_telefono_de_la_ficha_llega_al_usuario(self):
        u = self._usuario()                       # usuario creado SIN teléfono
        self.assertEqual(u.telefono, '')
        self._tutor(usuario=u)
        u.refresh_from_db()
        self.assertEqual(u.telefono, '76543210')

    def test_editar_telefono_del_tutor_actualiza_usuario(self):
        u = self._usuario()
        t = self._tutor(usuario=u)
        t.telefono = '71111111'; t.save()
        u.refresh_from_db()
        self.assertEqual(u.telefono, '71111111')

    def test_editar_telefono_del_usuario_actualiza_tutor(self):
        admin = Usuario.objects.create_superuser(
            email='a@a.com', password='Clave12345!', nombres='A', apellidos='B')
        u = self._usuario()
        t = self._tutor(usuario=u)
        c = APIClient(); c.force_authenticate(admin)
        r = c.patch(f'/api/auth/usuarios/{u.id}/', {'telefono': '72222222'}, format='json')
        self.assertIn(r.status_code, (200, 204), r.content)
        t.refresh_from_db()
        self.assertEqual(t.telefono, '72222222')

    def test_tutor_sin_usuario_no_falla(self):
        self._tutor(usuario=None)


class DistintivoCentroMisaelTests(TestCase):
    """La lista y la ficha del niño dicen si está vinculado de verdad con Centro Misael."""

    def setUp(self):
        from datetime import date
        from ninos.models import Nino
        from misael_link.models import VinculoCentroMisael
        self.admin = Usuario.objects.create_superuser(
            email='adm@a.com', password='Clave12345!', nombres='A', apellidos='B')
        self.c = APIClient(); self.c.force_authenticate(self.admin)
        self.con = Nino.objects.create(nombres='Vinculado', apellidos='Uno', fecha_nacimiento=date(2023, 1, 1), genero='M')
        self.sin = Nino.objects.create(nombres='Sin', apellidos='Vinculo', fecha_nacimiento=date(2023, 2, 1), genero='F',
                                       tiene_plan_misael=True)       # casilla manual marcada, pero SIN vínculo real
        VinculoCentroMisael.objects.create(nino=self.con, paciente_centro_id=42,
                                           nombre_paciente_centro='Vinculado Uno', estado_centro_cache='activo')

    def test_lista_marca_solo_al_vinculado_de_verdad(self):
        r = self.c.get('/api/ninos/ninos/', {'page_size': 50})
        self.assertEqual(r.status_code, 200, r.content)
        por_id = {x['id']: x for x in r.data['results']}
        self.assertTrue(por_id[str(self.con.id)]['vinculado_centro_misael'])
        self.assertFalse(por_id[str(self.sin.id)]['vinculado_centro_misael'])
        self.assertTrue(por_id[str(self.sin.id)]['tiene_plan_misael'])   # la casilla manual no cuenta como vínculo

    def test_detalle_trae_los_datos_del_vinculo(self):
        d = self.c.get(f'/api/ninos/ninos/{self.con.id}/').data
        self.assertTrue(d['vinculado_centro_misael'])
        self.assertEqual(d['centro_misael']['paciente_centro_id'], 42)
        self.assertEqual(d['centro_misael']['nombre_paciente'], 'Vinculado Uno')
        sin = self.c.get(f'/api/ninos/ninos/{self.sin.id}/').data
        self.assertFalse(sin['vinculado_centro_misael'])
        self.assertIsNone(sin['centro_misael'])

    def test_la_lista_no_hace_una_consulta_por_nino(self):
        from datetime import date
        from ninos.models import Nino
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as pocas:
            self.c.get('/api/ninos/ninos/', {'page_size': 50})
        for i in range(8):
            Nino.objects.create(nombres=f'N{i}', apellidos='X', fecha_nacimiento=date(2023, 3, 1), genero='M')
        with CaptureQueriesContext(connection) as muchas:
            self.c.get('/api/ninos/ninos/', {'page_size': 50})
        self.assertEqual(len(pocas), len(muchas))
