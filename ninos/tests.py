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
