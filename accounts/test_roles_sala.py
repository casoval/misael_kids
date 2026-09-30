"""
accounts/test_roles_sala.py
Reglas de acceso de la EDUCADORA / AYUDANTE (solo sus salas asignadas) y de la
RECEPCIONISTA (oficina: fichas, inscripciones, cobros, asistencia, avisos).
"""
from datetime import date, timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Usuario
from core.models import Sucursal, Sala, Turno
from inscripciones.models import Inscripcion
from ninos.models import Nino
from personal.models import Personal, AsignacionPersonal
from asistencia.models import Asistencia


def _usuario(email, rol):
    return Usuario.objects.create_user(
        email=email, password='clave12345', nombres=rol.title(), apellidos='Test', rol=rol,
    )


class BaseSalas(APITestCase):
    def setUp(self):
        self.suc = Sucursal.objects.create(nombre='Kids Camacho', direccion='Av. Camacho 1')
        self.sala_a = Sala.objects.create(sucursal=self.suc, nombre='Sala A', edad_min_meses=0,
                                          edad_max_meses=24, capacidad_maxima=10)
        self.sala_b = Sala.objects.create(sucursal=self.suc, nombre='Sala B', edad_min_meses=25,
                                          edad_max_meses=48, capacidad_maxima=10)
        self.turno_a = self._turno(self.sala_a)
        self.turno_b = self._turno(self.sala_b)
        self.nino_a = self._nino('Ana', self.sala_a, self.turno_a)
        self.nino_b = self._nino('Beto', self.sala_b, self.turno_b)
        self.insc_a = self.nino_a.inscripciones.first()
        self.insc_b = self.nino_b.inscripciones.first()

        self.educadora = self._personal('edu@x.test', Usuario.ROL_EDUCADORA, '111')
        self.ayudante = self._personal('ayu@x.test', Usuario.ROL_AYUDANTE, '222')
        self.asig_edu = self._asignar(self.educadora, self.sala_a, self.turno_a)
        self._asignar(self.ayudante, self.sala_a, self.turno_a)
        self.recep = _usuario('rec@x.test', Usuario.ROL_RECEPCIONISTA)
        self.tutor_user = _usuario('tut@x.test', Usuario.ROL_TUTOR)

    def _turno(self, sala):
        return Turno.objects.create(sala=sala, nombre='Mañana', tipo=Turno.TIPO_MANANA,
                                    hora_inicio='08:00', hora_fin='12:00',
                                    costo_mensual='650.00', costo_diario='40.00')

    def _nino(self, nombre, sala, turno):
        n = Nino.objects.create(nombres=nombre, apellidos='Prueba',
                                fecha_nacimiento=date(2024, 1, 1), genero='M')
        Inscripcion.objects.create(nino=n, sucursal=self.suc, sala=sala, turno=turno,
                                   modalidad_pago=Inscripcion.MODALIDAD_DIARIA,
                                   fecha_inicio=date.today(),
                                   costo_mensual='650.00', costo_diario='40.00')
        return n

    def _personal(self, email, rol, ci):
        u = _usuario(email, rol)
        Personal.objects.create(usuario=u, ci=ci, rol=rol, fecha_ingreso=date(2024, 1, 1))
        return u

    def _asignar(self, usuario, sala, turno, **kw):
        return AsignacionPersonal.objects.create(
            personal=Personal.objects.get(usuario=usuario), sucursal=self.suc, sala=sala, turno=turno,
            fecha_inicio=date(2024, 1, 1), **kw)

    def ids(self, resp):
        data = resp.data['results'] if isinstance(resp.data, dict) and 'results' in resp.data else resp.data
        return {str(x['id']) for x in data}


class EducadoraNinosTests(BaseSalas):
    def test_lista_solo_ninos_de_su_sala(self):
        self.client.force_authenticate(self.educadora)
        resp = self.client.get('/api/ninos/ninos/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.ids(resp), {str(self.nino_a.id)})

    def test_detalle_de_nino_ajeno_da_404(self):
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.get(f'/api/ninos/ninos/{self.nino_b.id}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/ninos/ninos/{self.nino_a.id}/').status_code, 200)

    def test_puede_editar_su_nino_pero_no_el_ajeno(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.patch(f'/api/ninos/ninos/{self.nino_a.id}/', {'observaciones': 'ok'})
        self.assertNotIn(r.status_code, (403, 404))
        self.assertEqual(self.client.patch(f'/api/ninos/ninos/{self.nino_b.id}/', {'nombres': 'X'}).status_code, 404)

    def test_no_puede_crear_ni_borrar_ninos(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.post('/api/ninos/ninos/', {'nombres': 'N', 'apellidos': 'N',
                             'fecha_nacimiento': '2024-01-01', 'genero': 'M'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.delete(f'/api/ninos/ninos/{self.nino_a.id}/').status_code, 403)

    def test_no_puede_modificar_autorizados_a_retirar(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.post('/api/ninos/autorizados/', {
            'nino': str(self.nino_a.id), 'nombres': 'P', 'apellidos': 'Q', 'ci': '1',
            'telefono': '1', 'parentesco': 'tio', 'vigencia_desde': '2026-01-01'})
        self.assertEqual(r.status_code, 403)

    def test_ayudante_solo_lee(self):
        self.client.force_authenticate(self.ayudante)
        self.assertEqual(self.client.get('/api/ninos/ninos/').status_code, 200)
        r = self.client.patch(f'/api/ninos/ninos/{self.nino_a.id}/', {'observaciones': 'x'})
        self.assertEqual(r.status_code, 403)


class AsignacionVigenciaTests(BaseSalas):
    def test_asignacion_vencida_pierde_acceso(self):
        self.asig_edu.fecha_fin = date.today() - timedelta(days=1)
        self.asig_edu.save()
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.ids(self.client.get('/api/ninos/ninos/')), set())

    def test_asignacion_inactiva_pierde_acceso(self):
        self.asig_edu.activa = False
        self.asig_edu.save()
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.ids(self.client.get('/api/ninos/ninos/')), set())

    def test_personal_inactivo_pierde_acceso(self):
        Personal.objects.filter(usuario=self.educadora).update(activo=False)
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.ids(self.client.get('/api/ninos/ninos/')), set())

    def test_segunda_sala_asignada_se_suma(self):
        self._asignar(self.educadora, self.sala_b, self.turno_b)
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.ids(self.client.get('/api/ninos/ninos/')),
                         {str(self.nino_a.id), str(self.nino_b.id)})


class EducadoraAsistenciaTests(BaseSalas):
    def _marcar(self, insc):
        return self.client.post('/api/asistencia/asistencia/', {
            'inscripcion': str(insc.id), 'fecha': date.today().isoformat(),
            'estado': Asistencia.ESTADO_PRESENTE})

    def test_marca_asistencia_en_su_sala(self):
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self._marcar(self.insc_a).status_code, 201)

    def test_no_marca_asistencia_en_sala_ajena(self):
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self._marcar(self.insc_b).status_code, 403)
        self.assertEqual(Asistencia.objects.count(), 0)

    def test_ayudante_marca_asistencia_en_su_sala_pero_no_en_otra(self):
        self.client.force_authenticate(self.ayudante)
        self.assertEqual(self._marcar(self.insc_a).status_code, 201)
        self.assertEqual(self._marcar(self.insc_b).status_code, 403)

    def test_planilla_ignora_sala_ajena(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.get(f'/api/asistencia/asistencia/planilla/?sala={self.sala_b.id}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['ninos'], [])
        r = self.client.get('/api/asistencia/asistencia/planilla/')
        self.assertEqual([n['nino'] for n in r.data['ninos']], [self.nino_a.id])

    def test_planilla_muestra_educadora_sin_usuario(self):
        """Una ficha sin acceso al sistema igual aparece asignada a su sala."""
        ficha = Personal.objects.create(nombres='Sin', apellidos='Login', ci='900',
                                        rol='educadora', fecha_ingreso=date(2024, 1, 1))
        AsignacionPersonal.objects.create(personal=ficha, sucursal=self.suc, sala=self.sala_a,
                                          turno=self.turno_a, fecha_inicio=date(2024, 1, 1))
        self.client.force_authenticate(self.recep)
        r = self.client.get(f'/api/asistencia/asistencia/planilla/?sala={self.sala_a.id}')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Sin Login', [e['nombre'] for e in r.data['educadoras']])

    def test_listado_solo_asistencia_de_su_sala(self):
        Asistencia.objects.create(inscripcion=self.insc_a, fecha=date.today(),
                                  estado=Asistencia.ESTADO_PRESENTE)
        Asistencia.objects.create(inscripcion=self.insc_b, fecha=date.today(),
                                  estado=Asistencia.ESTADO_PRESENTE)
        self.client.force_authenticate(self.educadora)
        r = self.client.get('/api/asistencia/asistencia/')
        self.assertEqual(len(self.ids(r)), 1)


class EducadoraOtrosModulosTests(BaseSalas):
    def test_no_ve_cobros_ni_inscripciones(self):
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.get('/api/inscripciones/cobros/').status_code, 403)
        self.assertEqual(self.client.get('/api/inscripciones/inscripciones/').status_code, 403)

    def _incidente(self, nino):
        return self.client.post('/api/salud/incidentes/', {
            'nino': str(nino.id), 'sucursal': str(self.suc.id),
            'reportado_por': str(Personal.objects.get(usuario=self.educadora).id),
            'fecha': date.today().isoformat(), 'hora': '09:00',
            'tipo': 'accidente', 'descripcion': 'golpe', 'accion_tomada': 'hielo'})

    def test_registra_incidente_de_su_nino_pero_no_de_uno_ajeno(self):
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self._incidente(self.nino_a).status_code, 201)
        self.assertEqual(self._incidente(self.nino_b).status_code, 403)


class RecepcionistaTests(BaseSalas):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.recep)

    def test_ve_todos_los_ninos_y_puede_crear_ficha(self):
        self.assertEqual(self.ids(self.client.get('/api/ninos/ninos/')),
                         {str(self.nino_a.id), str(self.nino_b.id)})
        r = self.client.post('/api/ninos/ninos/', {'nombres': 'Nuevo', 'apellidos': 'Niño',
                             'fecha_nacimiento': '2024-05-01', 'genero': 'F'})
        self.assertEqual(r.status_code, 201, r.data)

    def test_gestiona_tutores_y_autorizados(self):
        r = self.client.post('/api/ninos/autorizados/', {
            'nino': str(self.nino_a.id), 'nombres': 'P', 'apellidos': 'Q', 'ci': '1',
            'telefono': '1', 'parentesco': 'tio', 'vigencia_desde': '2026-01-01'})
        self.assertEqual(r.status_code, 201, r.data)

    def test_ve_cobros_e_inscripciones(self):
        self.assertEqual(self.client.get('/api/inscripciones/cobros/').status_code, 200)
        self.assertEqual(self.client.get('/api/inscripciones/inscripciones/').status_code, 200)

    def test_marca_asistencia_en_cualquier_sala(self):
        for insc in (self.insc_a, self.insc_b):
            r = self.client.post('/api/asistencia/asistencia/', {
                'inscripcion': str(insc.id), 'fecha': date.today().isoformat(),
                'estado': Asistencia.ESTADO_PRESENTE})
            self.assertEqual(r.status_code, 201, r.data)

    def test_migracion_de_rol_existe_el_nuevo_valor(self):
        self.assertEqual(Usuario.ROL_RECEPCIONISTA, 'recepcionista')
        self.assertNotIn('administrativo', dict(Usuario.ROLES))
