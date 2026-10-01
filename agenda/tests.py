"""
agenda/tests.py
Filtros por rango/turno/sucursal, permisos de tutor, validaciones y avance
automático del estado de un objetivo. Incluye la paginación global (page_size).
"""
from datetime import date, timedelta
from rest_framework.test import APITestCase
from rest_framework import status

from accounts.models import Usuario
from core.models import Sucursal, Sala, Turno
from ninos.models import Nino, Tutor, NinoTutor
from inscripciones.models import Inscripcion
from .models import PlanificacionGrupal, PlanIndividual, ObjetivoIndividual, RegistroObjetivo

URL_PLANIF = '/api/agenda/planificaciones/'
URL_PLANES = '/api/agenda/planes-individuales/'
URL_OBJ    = '/api/agenda/objetivos/'
URL_REG    = '/api/agenda/registros-objetivos/'


class AgendaBase(APITestCase):
    def setUp(self):
        self.suc = Sucursal.objects.create(nombre='Camacho', direccion='Av. 1')
        self.suc2 = Sucursal.objects.create(nombre='Sopocachi', direccion='Av. 2')

        def sala_turnos(suc, nombre):
            sala = Sala.objects.create(sucursal=suc, nombre=nombre, edad_min_meses=0,
                                       edad_max_meses=24, capacidad_maxima=10)
            man = Turno.objects.create(sala=sala, nombre='Turno mañana', tipo=Turno.TIPO_MANANA,
                                       hora_inicio='08:00', hora_fin='12:00',
                                       costo_mensual='650', costo_diario='40')
            tar = Turno.objects.create(sala=sala, nombre='Turno tarde', tipo=Turno.TIPO_TARDE,
                                       hora_inicio='14:00', hora_fin='18:00',
                                       costo_mensual='650', costo_diario='40')
            return sala, man, tar
        self.sala, self.man, self.tar = sala_turnos(self.suc, 'Sala Cuna')
        self.sala2, self.man2, _      = sala_turnos(self.suc2, 'Sala Sol')

        self.staff = Usuario.objects.create_user(
            email='dir@x.test', password='x12345678', nombres='Jackie', apellidos='Castro',
            rol=Usuario.ROL_DIRECTORA, is_staff=True)
        self.client.force_authenticate(self.staff)

        self.nino = Nino.objects.create(nombres='Anthony', apellidos='Nogales',
                                        fecha_nacimiento=date(2025, 1, 1), genero='M')
        self.nino2 = Nino.objects.create(nombres='Valentina', apellidos='Rojas',
                                         fecha_nacimiento=date(2025, 2, 1), genero='F')
        for nino, sala, turno, suc in [(self.nino, self.sala, self.man, self.suc),
                                       (self.nino2, self.sala2, self.man2, self.suc2)]:
            Inscripcion.objects.create(nino=nino, sucursal=suc, sala=sala, turno=turno,
                                       modalidad_pago='diaria', fecha_inicio=date.today(),
                                       costo_mensual='650', costo_diario='40')

        self.usuario_tutor = Usuario.objects.create_user(
            username='mama', password='x12345678', nombres='Karina', apellidos='C', rol=Usuario.ROL_TUTOR)
        tutor = Tutor.objects.create(usuario=self.usuario_tutor, nombres='Karina', apellidos='C',
                                     ci='1', telefono='7', parentesco='madre')
        NinoTutor.objects.create(nino=self.nino, tutor=tutor, es_principal=True)

    def planif(self, sala=None, turno=None, fecha=None, **kw):
        return PlanificacionGrupal.objects.create(
            sala=sala or self.sala, turno=turno or self.man,
            fecha=fecha or date(2026, 9, 29), actividades='Juego libre', **kw)


class PaginacionTests(AgendaBase):
    def test_page_size_se_respeta(self):
        # Antes ?page_size=200 se ignoraba y solo llegaban 25 registros.
        for i in range(40):
            self.planif(fecha=date(2026, 1, 1) + timedelta(days=i))
        r = self.client.get(URL_PLANIF + '?page_size=200')
        self.assertEqual(r.data['count'], 40)
        self.assertEqual(len(r.data['results']), 40)

    def test_sin_page_size_sigue_siendo_25(self):
        for i in range(30):
            self.planif(fecha=date(2026, 1, 1) + timedelta(days=i))
        self.assertEqual(len(self.client.get(URL_PLANIF).data['results']), 25)


class FiltrosPlanificacionTests(AgendaBase):
    def test_rango_desde_hasta_trae_solo_ese_mes(self):
        self.planif(fecha=date(2026, 8, 31))
        self.planif(fecha=date(2026, 9, 1))
        self.planif(fecha=date(2026, 9, 30))
        self.planif(fecha=date(2026, 10, 1))
        r = self.client.get(URL_PLANIF + '?desde=2026-09-01&hasta=2026-09-30&page_size=200')
        self.assertEqual(sorted(p['fecha'] for p in r.data['results']), ['2026-09-01', '2026-09-30'])

    def test_filtro_por_turno(self):
        self.planif(turno=self.man)
        self.planif(turno=self.tar)
        r = self.client.get(URL_PLANIF + f'?sala={self.sala.id}&turno={self.tar.id}')
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['turno_nombre'], 'Turno tarde')

    def test_filtro_por_sucursal(self):
        self.planif(sala=self.sala, turno=self.man)
        self.planif(sala=self.sala2, turno=self.man2)
        r = self.client.get(URL_PLANIF + f'?sucursal={self.suc2.id}')
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['sala_nombre'], 'Sala Sol')


class FiltrosPlanIndividualTests(AgendaBase):
    def setUp(self):
        super().setUp()
        self.plan1 = PlanIndividual.objects.create(nino=self.nino, descripcion='p1', fecha_inicio=date.today())
        self.plan2 = PlanIndividual.objects.create(nino=self.nino2, descripcion='p2', fecha_inicio=date.today())

    def test_filtra_por_sala_turno_y_sucursal_del_nino(self):
        ids = lambda q: {p['id'] for p in self.client.get(URL_PLANES + q).data['results']}
        self.assertEqual(ids(f'?sala={self.sala.id}'), {str(self.plan1.id)})
        self.assertEqual(ids(f'?sala={self.sala2.id}'), {str(self.plan2.id)})
        self.assertEqual(ids(f'?turno={self.man.id}'), {str(self.plan1.id)})
        self.assertEqual(ids(f'?sucursal={self.suc2.id}'), {str(self.plan2.id)})
        self.assertEqual(ids(f'?sucursal={self.suc.id}&turno={self.tar.id}'), set())

    def test_incluye_sala_y_turno_del_nino(self):
        r = self.client.get(URL_PLANES + f'?nino={self.nino.id}')
        self.assertEqual(r.data['results'][0]['nino_sala'], 'Sala Cuna · Turno mañana')

    def test_fecha_fin_anterior_al_inicio_se_rechaza(self):
        r = self.client.post(URL_PLANES, {
            'nino': str(self.nino.id), 'descripcion': 'x',
            'fecha_inicio': '2026-09-10', 'fecha_fin': '2026-09-01'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('fecha_fin', r.data)


class ValidacionesPlanificacionTests(AgendaBase):
    def test_turno_de_otra_sala_se_rechaza(self):
        r = self.client.post(URL_PLANIF, {
            'sala': str(self.sala.id), 'turno': str(self.man2.id),
            'fecha': '2026-09-29', 'actividades': 'x'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('turno', r.data)

    def test_duplicado_da_mensaje_claro(self):
        self.planif()
        r = self.client.post(URL_PLANIF, {
            'sala': str(self.sala.id), 'turno': str(self.man.id),
            'fecha': '2026-09-29', 'actividades': 'otra'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Ya existe una planificación', str(r.data))

    def test_editar_no_choca_consigo_misma(self):
        p = self.planif()
        r = self.client.patch(f'{URL_PLANIF}{p.id}/', {'actividades': 'Nuevo texto'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)


class PermisosTutorTests(AgendaBase):
    """Un tutor puede consultar (su sala/su hijo) pero NUNCA escribir en la agenda."""

    def setUp(self):
        super().setUp()
        self.plan = PlanIndividual.objects.create(nino=self.nino2, descripcion='ajeno', fecha_inicio=date.today())
        self.obj  = ObjetivoIndividual.objects.create(plan=self.plan, descripcion='o', area='social')
        self.client.force_authenticate(self.usuario_tutor)

    def test_tutor_no_puede_crear_planificacion(self):
        r = self.client.post(URL_PLANIF, {
            'sala': str(self.sala.id), 'turno': str(self.man.id),
            'fecha': '2026-09-29', 'actividades': 'hackeado'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_tutor_no_puede_crear_plan_ni_objetivo_ni_avance_de_otro_nino(self):
        self.assertEqual(self.client.post(URL_PLANES, {
            'nino': str(self.nino2.id), 'descripcion': 'x', 'fecha_inicio': '2026-09-29'},
            format='json').status_code, 403)
        self.assertEqual(self.client.post(URL_OBJ, {
            'plan': str(self.plan.id), 'descripcion': 'x', 'area': 'social'},
            format='json').status_code, 403)
        self.assertEqual(self.client.post(URL_REG, {
            'objetivo': str(self.obj.id), 'fecha': '2026-09-29', 'resultado': 'logrado'},
            format='json').status_code, 403)

    def test_tutor_sigue_pudiendo_leer_lo_suyo(self):
        visible = self.planif(visible_padres=True)
        interna = self.planif(turno=self.tar, visible_padres=False)
        r = self.client.get(URL_PLANIF)
        self.assertEqual(r.status_code, 200)
        ids = {p['id'] for p in r.data['results']}
        self.assertIn(str(visible.id), ids)
        self.assertNotIn(str(interna.id), ids)


class AvanceObjetivoTests(AgendaBase):
    def setUp(self):
        super().setUp()
        plan = PlanIndividual.objects.create(nino=self.nino, descripcion='p', fecha_inicio=date.today())
        self.obj = ObjetivoIndividual.objects.create(plan=plan, descripcion='Pinza fina', area='motricidad_fina')

    def _registrar(self, resultado, fecha='2026-09-29'):
        return self.client.post(URL_REG, {'objetivo': str(self.obj.id), 'fecha': fecha,
                                          'resultado': resultado}, format='json')

    def test_trabajado_pasa_pendiente_a_en_proceso(self):
        self.assertEqual(self._registrar('trabajado').status_code, 201)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.estado, ObjetivoIndividual.ESTADO_EN_PROCESO)

    def test_logrado_marca_el_objetivo_como_logrado(self):
        self._registrar('logrado')
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.estado, ObjetivoIndividual.ESTADO_LOGRADO)

    def test_no_trabajado_no_cambia_el_estado(self):
        self._registrar('no_trabajado')
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.estado, ObjetivoIndividual.ESTADO_PENDIENTE)

    def test_un_logrado_no_retrocede_con_avances_posteriores(self):
        self._registrar('logrado', '2026-09-28')
        self._registrar('trabajado', '2026-09-29')
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.estado, ObjetivoIndividual.ESTADO_LOGRADO)

    def test_corregir_un_avance_tambien_avanza_el_objetivo(self):
        r = self._registrar('no_trabajado')
        self.client.patch(f'{URL_REG}{r.data["id"]}/', {'resultado': 'logrado'}, format='json')
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.estado, ObjetivoIndividual.ESTADO_LOGRADO)

    def test_avance_duplicado_del_mismo_dia_da_mensaje_claro(self):
        self._registrar('trabajado')
        r = self._registrar('logrado')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Ya hay un avance', str(r.data))


class EliminarPlanIndividualTests(AgendaBase):
    def setUp(self):
        super().setUp()
        self.plan = PlanIndividual.objects.create(nino=self.nino, descripcion='p', fecha_inicio=date.today())
        obj = ObjetivoIndividual.objects.create(plan=self.plan, descripcion='o', area='social')
        RegistroObjetivo.objects.create(objetivo=obj, fecha=date.today(), resultado='trabajado')

    def test_eliminar_borra_plan_objetivos_y_avances(self):
        r = self.client.delete(f'{URL_PLANES}{self.plan.id}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PlanIndividual.objects.filter(id=self.plan.id).exists())
        self.assertEqual(ObjetivoIndividual.objects.count(), 0)
        self.assertEqual(RegistroObjetivo.objects.count(), 0)

    def test_tutor_no_puede_eliminar_un_plan(self):
        self.client.force_authenticate(self.usuario_tutor)
        r = self.client.delete(f'{URL_PLANES}{self.plan.id}/')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(PlanIndividual.objects.filter(id=self.plan.id).exists())

    def test_editar_un_plan_inactivo_no_lo_reactiva(self):
        PlanIndividual.objects.filter(id=self.plan.id).update(activo=False)
        r = self.client.patch(f'{URL_PLANES}{self.plan.id}/', {'descripcion': 'nueva'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.activo)

    def test_listar_sin_filtro_activo_incluye_inactivos(self):
        PlanIndividual.objects.filter(id=self.plan.id).update(activo=False)
        self.assertEqual(self.client.get(URL_PLANES + '?activo=true').data['count'], 0)
        self.assertEqual(self.client.get(URL_PLANES).data['count'], 1)


class ModificadoPorPlanificacionTests(AgendaBase):
    """Se guarda quién hizo la última modificación; la autora original no cambia."""

    def _educadora(self, email, nombres, ci, sala=None):
        from personal.models import Personal, AsignacionPersonal
        u = Usuario.objects.create_user(email=email, password='x12345678', nombres=nombres,
                                        apellidos='Test', rol=Usuario.ROL_EDUCADORA)
        p = Personal.objects.create(usuario=u, nombres=nombres, apellidos='Test', ci=ci,
                                    rol='educadora', fecha_ingreso=date(2025, 1, 1))
        sala = sala or self.sala
        AsignacionPersonal.objects.create(personal=p, sucursal=sala.sucursal, sala=sala,
                                          turno=sala.turnos.first(), fecha_inicio=date(2025, 1, 1))
        return u

    def test_al_crear_no_hay_modificador(self):
        self.client.force_authenticate(self._educadora('a@x.test', 'Ana', '111'))
        r = self.client.post(URL_PLANIF, {'sala': str(self.sala.id), 'turno': str(self.man.id),
                                          'fecha': '2026-09-29', 'actividades': 'Cuentos'})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['educadora_nombre'], 'Ana Test')
        self.assertIsNone(r.data['modificado_por'])

    def test_al_editar_se_guarda_quien_modifico_y_la_autora_no_cambia(self):
        ana  = self._educadora('a@x.test', 'Ana', '111')
        rosa = self._educadora('r@x.test', 'Rosa', '222')
        self.client.force_authenticate(ana)
        creada = self.client.post(URL_PLANIF, {'sala': str(self.sala.id), 'turno': str(self.man.id),
                                               'fecha': '2026-09-29', 'actividades': 'Cuentos'})
        pid = creada.data['id']
        self.client.force_authenticate(rosa)
        r = self.client.patch(f'{URL_PLANIF}{pid}/', {'actividades': 'Cuentos y pintura'})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['modificado_por_nombre'], 'Rosa Test')
        self.assertEqual(r.data['educadora_nombre'], 'Ana Test')       # la autora original sigue igual

    def test_la_directora_sin_ficha_tambien_queda_registrada(self):
        p = self.planif()
        r = self.client.patch(f'{URL_PLANIF}{p.id}/', {'observaciones': 'Revisada'})   # self.staff = directora
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['modificado_por_nombre'], 'Jackie Castro')

    def test_el_cliente_no_puede_falsear_el_modificador(self):
        p = self.planif()
        otro = Usuario.objects.create_user(email='o@x.test', password='x12345678',
                                           nombres='Otra', apellidos='Persona', rol=Usuario.ROL_DIRECTORA)
        r = self.client.patch(f'{URL_PLANIF}{p.id}/', {'observaciones': 'x', 'modificado_por': str(otro.id)})
        self.assertEqual(r.data['modificado_por_nombre'], 'Jackie Castro')

    def test_educadora_no_puede_mover_planificacion_a_sala_ajena(self):
        ana = self._educadora('a@x.test', 'Ana', '111')
        p = self.planif()
        self.client.force_authenticate(ana)
        r = self.client.patch(f'{URL_PLANIF}{p.id}/', {'sala': str(self.sala2.id), 'turno': str(self.man2.id)})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN, r.data)
