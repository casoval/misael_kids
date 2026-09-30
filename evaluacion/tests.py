"""
evaluacion/tests.py
Catálogo de hitos (precargado por migración), permisos por rol, creación y
edición de evaluaciones, filtros y alertas de rezago.
"""
from datetime import date, timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Usuario
from core.models import Sucursal, Sala, Turno
from inscripciones.models import Inscripcion
from ninos.models import Nino, Tutor, NinoTutor
from personal.models import Personal, AsignacionPersonal
from .models import HitoDesarrollo, EvaluacionNino

URL_HITOS = '/api/evaluacion/hitos/'
URL_EVALS = '/api/evaluacion/evaluaciones/'
URL_ALERTAS = URL_EVALS + 'alertas-rezago/'


def meses_atras(meses):
    """Fecha de nacimiento (día 1) para que el niño tenga `meses` meses cumplidos."""
    hoy = date.today()
    total = hoy.year * 12 + (hoy.month - 1) - meses
    return date(total // 12, total % 12 + 1, 1)


class Base(APITestCase):
    def setUp(self):
        self.suc = Sucursal.objects.create(nombre='Camacho', direccion='Av. 1')
        self.sala = Sala.objects.create(sucursal=self.suc, nombre='Sala Cuna', edad_min_meses=0,
                                        edad_max_meses=72, capacidad_maxima=10)
        self.sala_otra = Sala.objects.create(sucursal=self.suc, nombre='Sala Sol', edad_min_meses=0,
                                             edad_max_meses=72, capacidad_maxima=10)
        self.turno = Turno.objects.create(sala=self.sala, nombre='Mañana', tipo=Turno.TIPO_MANANA,
                                          hora_inicio='08:00', hora_fin='12:00',
                                          costo_mensual='650', costo_diario='40')
        self.turno_otro = Turno.objects.create(sala=self.sala_otra, nombre='Mañana', tipo=Turno.TIPO_MANANA,
                                               hora_inicio='08:00', hora_fin='12:00',
                                               costo_mensual='650', costo_diario='40')

        def usuario(email, rol):
            return Usuario.objects.create_user(email=email, password='x12345678',
                                               nombres=rol.title(), apellidos='Test', rol=rol)
        self.admin = usuario('admin@x.test', Usuario.ROL_ADMIN)
        self.directora = usuario('dir@x.test', Usuario.ROL_DIRECTORA)
        self.educadora = usuario('edu@x.test', Usuario.ROL_EDUCADORA)
        self.ayudante = usuario('ayu@x.test', Usuario.ROL_AYUDANTE)
        self.recepcion = usuario('rec@x.test', Usuario.ROL_RECEPCIONISTA)
        self.cocina = usuario('coc@x.test', Usuario.ROL_COCINA)
        self.tutor_user = usuario('tut@x.test', Usuario.ROL_TUTOR)

        self.personal = Personal.objects.create(
            usuario=self.educadora, nombres='Edu', apellidos='Test', ci='111',
            rol=Personal.ROL_EDUCADORA, fecha_ingreso=date(2024, 1, 1))
        AsignacionPersonal.objects.create(personal=self.personal, sucursal=self.suc, sala=self.sala,
                                          turno=self.turno, fecha_inicio=date(2024, 1, 1))

        self.nino = Nino.objects.create(nombres='Ana', apellidos='Mamani',
                                        fecha_nacimiento=meses_atras(14), genero='F')
        self.nino_otro = Nino.objects.create(nombres='Luis', apellidos='Perez',
                                             fecha_nacimiento=meses_atras(30), genero='M')
        Inscripcion.objects.create(nino=self.nino, sucursal=self.suc, sala=self.sala, turno=self.turno,
                                   modalidad_pago='diaria', fecha_inicio=timezone.localdate(),
                                   costo_mensual='650', costo_diario='40')
        Inscripcion.objects.create(nino=self.nino_otro, sucursal=self.suc, sala=self.sala_otra,
                                   turno=self.turno_otro, modalidad_pago='diaria',
                                   fecha_inicio=timezone.localdate(), costo_mensual='650', costo_diario='40')
        tutor = Tutor.objects.create(usuario=self.tutor_user, nombres='Mama', apellidos='Mamani',
                                     ci='9', telefono='7', parentesco='madre')
        NinoTutor.objects.create(nino=self.nino, tutor=tutor, es_principal=True)

        self.hito = HitoDesarrollo.objects.filter(area='motricidad_gruesa',
                                                  edad_min_meses__lte=14, edad_max_meses__gte=14).first()
        self.hito2 = HitoDesarrollo.objects.filter(area='lenguaje',
                                                   edad_min_meses__lte=14, edad_max_meses__gte=14).first()

    def payload(self, **kw):
        datos = {'nino': str(self.nino.id), 'hito': str(self.hito.id),
                 'fecha': timezone.localdate().isoformat(), 'estado': 'en_proceso', 'observacion': ''}
        datos.update(kw)
        return datos

    def eval(self, **kw):
        datos = dict(nino=self.nino, hito=self.hito, fecha=timezone.localdate(), estado='en_proceso')
        datos.update(kw)
        return EvaluacionNino.objects.create(**datos)


# ─────────────────────────────────────────────────────────────────────────
class CatalogoTests(Base):
    """El catálogo debe venir cargado solo con `migrate` (antes estaba vacío)."""

    def test_catalogo_precargado_por_migracion(self):
        self.assertGreaterEqual(HitoDesarrollo.objects.count(), 200)

    def test_las_seis_areas_tienen_hitos(self):
        for codigo, _ in HitoDesarrollo.AREAS:
            self.assertGreaterEqual(HitoDesarrollo.objects.filter(area=codigo).count(), 30, codigo)

    def test_todas_las_edades_0_72_cubiertas_en_cada_area(self):
        for codigo, _ in HitoDesarrollo.AREAS:
            for mes in range(0, 73):
                ok = HitoDesarrollo.objects.filter(area=codigo, edad_min_meses__lte=mes,
                                                   edad_max_meses__gte=mes).exists()
                self.assertTrue(ok, f'{codigo}: sin hitos para {mes} meses')

    def test_integridad_de_datos(self):
        vistos = set()
        for h in HitoDesarrollo.objects.all():
            self.assertLessEqual(h.edad_min_meses, h.edad_max_meses, h.nombre)
            self.assertLessEqual(h.edad_max_meses, 72, h.nombre)
            self.assertTrue(h.descripcion.strip(), f'{h.nombre} sin descripción')
            clave = (h.nombre, h.area)
            self.assertNotIn(clave, vistos, f'duplicado {clave}')
            vistos.add(clave)

    def test_hitos_originales_conservan_su_id(self):
        # Las evaluaciones ya guardadas apuntan a estos ids: no pueden cambiar.
        h = HitoDesarrollo.objects.get(pk='a1000001-0000-0000-0000-000000000013')
        self.assertEqual(h.nombre, 'Camina solo')

    def test_comando_cargar_hitos_es_idempotente(self):
        from django.core.management import call_command
        antes = HitoDesarrollo.objects.count()
        call_command('cargar_hitos', verbosity=0)
        call_command('cargar_hitos', verbosity=0)
        self.assertEqual(HitoDesarrollo.objects.count(), antes)

    def test_comando_repone_hitos_borrados_sin_tocar_los_editados(self):
        from django.core.management import call_command
        h = HitoDesarrollo.objects.get(pk='a1000001-0000-0000-0000-000000000013')
        h.descripcion = 'Texto editado por la directora'
        h.save()
        HitoDesarrollo.objects.get(pk='a1000001-0000-0000-0000-000000000012').delete()
        call_command('cargar_hitos', verbosity=0)
        self.assertTrue(HitoDesarrollo.objects.filter(pk='a1000001-0000-0000-0000-000000000012').exists())
        h.refresh_from_db()
        self.assertEqual(h.descripcion, 'Texto editado por la directora')

    def test_fixture_coincide_con_el_catalogo(self):
        import json
        from pathlib import Path
        from .catalogo_hitos import HITOS
        ruta = Path(__file__).parent / 'fixtures' / 'hitos_desarrollo.json'
        ids_fixture = {o['pk'] for o in json.loads(ruta.read_text(encoding='utf-8'))}
        self.assertEqual(ids_fixture, {h['id'] for h in HITOS})


# ─────────────────────────────────────────────────────────────────────────
class HitosApiTests(Base):
    def test_listado_y_filtro_por_area(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.get(URL_HITOS + '?area=lenguaje&page_size=500')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['results'])
        self.assertTrue(all(h['area'] == 'lenguaje' for h in r.data['results']))

    def test_filtro_por_edad_en_meses(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.get(URL_HITOS + '?edad=14&page_size=500')
        self.assertTrue(r.data['results'])
        for h in r.data['results']:
            self.assertLessEqual(h['edad_min_meses'], 14)
            self.assertGreaterEqual(h['edad_max_meses'], 14)

    def test_orden_por_edad_funciona(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.get(URL_HITOS + '?ordering=-edad_min_meses&page_size=500')
        edades = [h['edad_min_meses'] for h in r.data['results']]
        self.assertEqual(edades, sorted(edades, reverse=True))

    def test_por_edad(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.get(URL_HITOS + 'por-edad/?meses=20')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data)
        self.assertTrue(all(h['edad_min_meses'] <= 20 <= h['edad_max_meses'] for h in r.data))

    def test_por_edad_invalida_es_400_no_500(self):
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.get(URL_HITOS + 'por-edad/?meses=abc').status_code, 400)
        self.assertEqual(self.client.get(URL_HITOS + 'por-edad/').status_code, 400)

    def test_solo_admin_o_directora_editan_el_catalogo(self):
        nuevo = {'nombre': 'Hito nuevo', 'area': 'social', 'edad_min_meses': 10, 'edad_max_meses': 20}
        for u in (self.tutor_user, self.educadora, self.ayudante, self.cocina):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.post(URL_HITOS, nuevo).status_code, 403, u.rol)
        self.client.force_authenticate(self.directora)
        self.assertEqual(self.client.post(URL_HITOS, nuevo).status_code, 201)

    def test_rango_de_edad_invertido_se_rechaza(self):
        self.client.force_authenticate(self.directora)
        r = self.client.post(URL_HITOS, {'nombre': 'X', 'area': 'social',
                                         'edad_min_meses': 30, 'edad_max_meses': 10})
        self.assertEqual(r.status_code, 400)

    def test_borrar_hito_lo_desactiva_y_conserva_evaluaciones(self):
        ev = self.eval()
        self.client.force_authenticate(self.directora)
        r = self.client.delete(f'{URL_HITOS}{self.hito.id}/')
        self.assertEqual(r.status_code, 204)
        self.hito.refresh_from_db()
        self.assertFalse(self.hito.activo)
        self.assertTrue(EvaluacionNino.objects.filter(pk=ev.pk).exists())
        ids = [str(h['id']) for h in self.client.get(URL_HITOS + '?page_size=500').data['results']]
        self.assertTrue(ids)
        self.assertNotIn(str(self.hito.id), ids)

    def test_recepcionista_no_accede_al_desarrollo(self):
        self.client.force_authenticate(self.recepcion)
        self.assertEqual(self.client.get(URL_HITOS).status_code, 403)
        self.assertEqual(self.client.get(URL_EVALS).status_code, 403)


# ─────────────────────────────────────────────────────────────────────────
class CrearEvaluacionTests(Base):
    def test_educadora_crea_evaluacion_y_queda_como_autora(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.post(URL_EVALS, self.payload(), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        ev = EvaluacionNino.objects.get(pk=r.data['id'])
        self.assertEqual(ev.educadora, self.personal)

    def test_frontend_envia_educadora_null_y_no_debe_fallar(self):
        # Antes: el formulario mandaba educadora:null y la API respondía 400.
        self.client.force_authenticate(self.educadora)
        r = self.client.post(URL_EVALS, self.payload(educadora=None), format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def test_cliente_no_puede_falsear_la_educadora(self):
        otra = Personal.objects.create(nombres='Otra', apellidos='X', ci='222',
                                       rol=Personal.ROL_EDUCADORA, fecha_ingreso=date(2024, 1, 1))
        self.client.force_authenticate(self.educadora)
        r = self.client.post(URL_EVALS, self.payload(educadora=str(otra.id)), format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(EvaluacionNino.objects.get(pk=r.data['id']).educadora, self.personal)

    def test_directora_sin_ficha_de_personal_puede_evaluar(self):
        self.client.force_authenticate(self.directora)
        r = self.client.post(URL_EVALS, self.payload(), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(EvaluacionNino.objects.get(pk=r.data['id']).educadora)

    def test_ayudante_sin_asignacion_no_puede_evaluar(self):
        self.client.force_authenticate(self.ayudante)
        self.assertEqual(self.client.post(URL_EVALS, self.payload(), format='json').status_code, 403)

    def test_educadora_no_evalua_ninos_de_otra_sala(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.post(URL_EVALS, self.payload(nino=str(self.nino_otro.id)), format='json')
        self.assertEqual(r.status_code, 403)

    def test_educadora_no_puede_mover_evaluacion_a_nino_ajeno(self):
        ev = self.eval()
        self.client.force_authenticate(self.educadora)
        r = self.client.patch(f'{URL_EVALS}{ev.id}/', {'nino': str(self.nino_otro.id)}, format='json')
        self.assertEqual(r.status_code, 403)
        ev.refresh_from_db()
        self.assertEqual(ev.nino, self.nino)

    def test_tutor_y_cocina_no_pueden_escribir(self):
        for u in (self.tutor_user, self.cocina):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.post(URL_EVALS, self.payload(), format='json').status_code,
                             403, u.rol)

    def test_duplicado_mismo_dia_se_rechaza(self):
        self.eval()
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.post(URL_EVALS, self.payload(), format='json').status_code, 400)

    def test_misma_evaluacion_en_otra_fecha_se_permite(self):
        self.eval(fecha=timezone.localdate() - timedelta(days=30))
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.post(URL_EVALS, self.payload(), format='json').status_code, 201)

    def test_fecha_futura_se_rechaza(self):
        self.client.force_authenticate(self.educadora)
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post(URL_EVALS, self.payload(fecha=manana), format='json').status_code, 400)

    def test_hito_inactivo_se_rechaza(self):
        self.hito.activo = False
        self.hito.save()
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.post(URL_EVALS, self.payload(), format='json').status_code, 400)

    def test_estado_invalido_se_rechaza(self):
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.post(URL_EVALS, self.payload(estado='xx'), format='json').status_code, 400)

    def test_logrado_no_puede_quedar_con_alerta_de_rezago(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.post(URL_EVALS, self.payload(estado='logrado', alerta_rezago=True), format='json')
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.data['alerta_rezago'])

    def test_editar_a_logrado_limpia_la_alerta(self):
        ev = self.eval(estado='no_logrado', alerta_rezago=True)
        self.client.force_authenticate(self.educadora)
        r = self.client.patch(f'{URL_EVALS}{ev.id}/', {'estado': 'logrado'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        ev.refresh_from_db()
        self.assertFalse(ev.alerta_rezago)

    def test_editar_solo_observacion_funciona(self):
        ev = self.eval()
        self.client.force_authenticate(self.educadora)
        r = self.client.patch(f'{URL_EVALS}{ev.id}/', {'observacion': 'Avanza bien'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        ev.refresh_from_db()
        self.assertEqual(ev.observacion, 'Avanza bien')

    def test_respuesta_trae_campos_para_el_frontend(self):
        self.client.force_authenticate(self.educadora)
        r = self.client.post(URL_EVALS, self.payload(), format='json')
        for campo in ('hito_nombre', 'hito_area', 'hito_area_codigo', 'estado_display', 'educadora_nombre'):
            self.assertIn(campo, r.data)
        self.assertEqual(r.data['hito_area_codigo'], 'motricidad_gruesa')


# ─────────────────────────────────────────────────────────────────────────
class ConsultaEvaluacionTests(Base):
    def test_tutor_ve_solo_evaluaciones_de_su_hijo(self):
        self.eval()
        self.eval(nino=self.nino_otro)
        self.client.force_authenticate(self.tutor_user)
        r = self.client.get(URL_EVALS + '?page_size=100')
        self.assertEqual(r.status_code, 200)
        self.assertEqual({str(e['nino']) for e in r.data['results']}, {str(self.nino.id)})

    def test_educadora_ve_solo_sus_salas(self):
        self.eval()
        self.eval(nino=self.nino_otro)
        self.client.force_authenticate(self.educadora)
        r = self.client.get(URL_EVALS + '?page_size=100')
        self.assertEqual({str(e['nino']) for e in r.data['results']}, {str(self.nino.id)})

    def test_filtro_por_area_del_hito(self):
        self.eval()
        self.eval(hito=self.hito2)
        self.client.force_authenticate(self.directora)
        r = self.client.get(URL_EVALS + '?nino=%s&hito__area=lenguaje&page_size=100' % self.nino.id)
        self.assertEqual(len(r.data['results']), 1)
        self.assertEqual(r.data['results'][0]['hito_area_codigo'], 'lenguaje')

    def test_alertas_rezago_devuelve_lista_simple(self):
        self.eval(estado='no_logrado', alerta_rezago=True)
        self.client.force_authenticate(self.directora)
        r = self.client.get(URL_ALERTAS)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.data, list)   # el dashboard hace .slice() sobre esto
        self.assertEqual(len(r.data), 1)

    def test_alerta_superada_por_evaluacion_posterior_no_se_muestra(self):
        self.eval(fecha=timezone.localdate() - timedelta(days=60), estado='no_logrado', alerta_rezago=True)
        self.eval(fecha=timezone.localdate(), estado='logrado')
        self.client.force_authenticate(self.directora)
        self.assertEqual(self.client.get(URL_ALERTAS).data, [])

    def test_alertas_respetan_alcance_de_la_educadora(self):
        self.eval(estado='no_logrado', alerta_rezago=True, nino=self.nino_otro)
        self.client.force_authenticate(self.educadora)
        self.assertEqual(self.client.get(URL_ALERTAS).data, [])


class EdadEnMesesTests(Base):
    def test_no_cuenta_el_mes_si_aun_no_cumple_el_dia(self):
        hoy = date.today()
        if hoy.day < 28:
            nacio = date(hoy.year - 1, hoy.month, hoy.day + 1)
            n = Nino(nombres='T', apellidos='T', fecha_nacimiento=nacio, genero='M')
            self.assertEqual(n.edad_en_meses, 11)
        n = Nino(nombres='T', apellidos='T', fecha_nacimiento=date(hoy.year - 2, hoy.month, 1), genero='M')
        self.assertEqual(n.edad_en_meses, 24)
