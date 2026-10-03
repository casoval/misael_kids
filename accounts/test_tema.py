"""
accounts/test_tema.py
El tema visual es personal: cada usuario cambia solo el suyo.
"""
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Usuario


def _usuario(email, rol):
    return Usuario.objects.create_user(
        email=email, password='clave12345', nombres=rol.title(), apellidos='Test', rol=rol,
    )


class TemaPersonalTests(APITestCase):
    URL = '/api/auth/usuarios/yo/tema/'

    def setUp(self):
        self.admin = _usuario('admin@x.test', Usuario.ROL_ADMIN)
        self.recep = _usuario('recep@x.test', Usuario.ROL_RECEPCIONISTA)

    def test_por_defecto_vacio(self):
        self.assertEqual(self.admin.tema, '')

    def test_admin_cambia_su_tema_y_no_afecta_a_recepcionista(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(self.URL, {'tema': 'espacio'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.admin.refresh_from_db(); self.recep.refresh_from_db()
        self.assertEqual(self.admin.tema, 'espacio')
        self.assertEqual(self.recep.tema, '')

    def test_recepcionista_cambia_su_tema_y_no_afecta_a_admin(self):
        self.client.force_authenticate(self.admin)
        self.client.patch(self.URL, {'tema': 'espacio'}, format='json')
        self.client.force_authenticate(self.recep)
        self.client.patch(self.URL, {'tema': 'papel'}, format='json')
        self.admin.refresh_from_db(); self.recep.refresh_from_db()
        self.assertEqual(self.admin.tema, 'espacio')
        self.assertEqual(self.recep.tema, 'papel')

    def test_formato_invalido(self):
        self.client.force_authenticate(self.admin)
        for malo in ('<script>', 'con espacio', 'x' * 31, 'MAYUS'):
            r = self.client.patch(self.URL, {'tema': malo}, format='json')
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, malo)

    def test_requiere_login(self):
        r = self.client.patch(self.URL, {'tema': 'papel'}, format='json')
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_edicion_general_no_permite_cambiar_tema_de_otro(self):
        """El admin edita a la recepcionista por el CRUD: 'tema' se ignora."""
        self.client.force_authenticate(self.admin)
        r = self.client.patch(f'/api/auth/usuarios/{self.recep.id}/',
                              {'telefono': '777', 'tema': 'espacio'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.recep.refresh_from_db()
        self.assertEqual(self.recep.telefono, '777')
        self.assertEqual(self.recep.tema, '')

    def test_login_devuelve_el_tema_propio(self):
        self.recep.tema = 'papel'; self.recep.save()
        r = self.client.post('/api/auth/login/',
                             {'email': 'recep@x.test', 'password': 'clave12345'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['usuario']['tema'], 'papel')

    def test_yo_incluye_tema(self):
        self.admin.tema = 'noche'; self.admin.save()
        self.client.force_authenticate(self.admin)
        r = self.client.get('/api/auth/usuarios/yo/')
        self.assertEqual(r.data['tema'], 'noche')
