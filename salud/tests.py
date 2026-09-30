from datetime import date

from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Usuario
from accounts.test_roles_sala import BaseSalas
from personal.models import Personal
from salud.models import IncidenteSalud


class RegistrarIncidenteTests(BaseSalas):
    """Antes el formulario enviaba reportado_por=null y TODO guardado fallaba."""

    def _payload(self, nino, **extra):
        d = {
            'nino': str(nino.pk), 'sucursal': str(self.suc.pk), 'tipo': 'accidente',
            'fecha': date.today().isoformat(), 'hora': '10:30',
            'descripcion': 'Se cayó en el patio', 'accion_tomada': 'Se limpió la herida',
            'notificado_tutor': False, 'hora_notificacion': None,
            'requirio_atencion_medica': False,
            'reportado_por': None,      # lo que enviaba el formulario
        }
        d.update(extra)
        return d

    def _cliente(self, usuario):
        c = APIClient(); c.force_authenticate(usuario); return c

    def test_educadora_registra_y_queda_como_reportante(self):
        r = self._cliente(self.educadora).post('/api/salud/incidentes/', self._payload(self.nino_a), format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.content)
        inc = IncidenteSalud.objects.get()
        self.assertEqual(inc.reportado_por, Personal.objects.get(usuario=self.educadora))
        self.assertTrue(r.data['reportado_por_nombre'])
        self.assertEqual(r.data['sucursal_nombre'], 'Kids Camacho')

    def test_admin_sin_ficha_puede_registrar(self):
        admin = Usuario.objects.create_superuser(email='adm@x.test', password='clave12345',
                                                 nombres='Admin', apellidos='Test')
        r = self._cliente(admin).post('/api/salud/incidentes/', self._payload(self.nino_a), format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.content)
        self.assertIsNone(IncidenteSalud.objects.get().reportado_por)
        self.assertIsNone(r.data['reportado_por_nombre'])

    def test_no_se_puede_falsear_el_reportante(self):
        otra = Personal.objects.get(usuario=self.ayudante)
        r = self._cliente(self.educadora).post(
            '/api/salud/incidentes/', self._payload(self.nino_a, reportado_por=str(otra.pk)), format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.content)
        self.assertEqual(IncidenteSalud.objects.get().reportado_por.usuario, self.educadora)

    def test_educadora_no_registra_en_nino_de_otra_sala(self):
        r = self._cliente(self.educadora).post('/api/salud/incidentes/', self._payload(self.nino_b), format='json')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_editar_no_cambia_el_reportante(self):
        c = self._cliente(self.educadora)
        inc_id = c.post('/api/salud/incidentes/', self._payload(self.nino_a), format='json').data['id']
        r = c.patch(f'/api/salud/incidentes/{inc_id}/', self._payload(self.nino_a, descripcion='Corregido'), format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.assertEqual(IncidenteSalud.objects.get().reportado_por.usuario, self.educadora)

    def test_tutor_no_puede_registrar_ni_eliminar_pero_si_ver_lo_de_su_hijo(self):
        r = self._cliente(self.tutor_user).post('/api/salud/incidentes/', self._payload(self.nino_a), format='json')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._cliente(self.tutor_user).get('/api/salud/incidentes/').status_code, 200)

    def test_eliminar_la_ficha_no_borra_el_incidente(self):
        c = self._cliente(self.educadora)
        c.post('/api/salud/incidentes/', self._payload(self.nino_a), format='json')
        Personal.objects.get(usuario=self.educadora).delete()
        self.assertEqual(IncidenteSalud.objects.count(), 1)
