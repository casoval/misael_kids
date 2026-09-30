"""
reportes/tests.py
Resumen (asistencia, ocupación, cobros del mes, caja) y exportaciones CSV.
"""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Usuario
from asistencia.models import Asistencia
from core.models import Sala, Sucursal, Turno
from inscripciones.models import Cobro, Inscripcion, Pago, Devolucion
from inventario.models import ItemInventario
from ninos.models import Nino, NinoTutor, Tutor

URL_RESUMEN = '/api/reportes/resumen/'
URL_EXPORT  = '/api/reportes/exportar/'


def leer_csv(respuesta):
    texto = respuesta.content.decode('utf-8')
    assert texto.startswith('\ufeff'), 'el CSV debe llevar BOM para Excel'
    return list(csv.reader(io.StringIO(texto[1:])))


class ReportesBase(APITestCase):
    def setUp(self):
        self.hoy = date.today()
        self.mes = self.hoy.strftime('%Y-%m')
        self.mes_pasado = (self.hoy.replace(day=1) - timedelta(days=1))

        self.suc  = Sucursal.objects.create(nombre='Camacho', direccion='a')
        self.suc2 = Sucursal.objects.create(nombre='Sopocachi', direccion='b')

        def sala(suc, nombre, cap):
            sa = Sala.objects.create(sucursal=suc, nombre=nombre, edad_min_meses=0, edad_max_meses=24, capacidad_maxima=cap)
            tu = Turno.objects.create(sala=sa, nombre='Turno mañana', tipo=Turno.TIPO_MANANA, hora_inicio='08:00',
                                      hora_fin='12:00', costo_mensual='650', costo_diario='40')
            return sa, tu
        self.sala, self.turno   = sala(self.suc, 'Sala Cuna', 4)
        self.sala2, self.turno2 = sala(self.suc2, 'Sala Sol', 10)

        def usuario(email, rol, **kw):
            return Usuario.objects.create_user(email=email, password='x12345678', nombres='U', apellidos=rol, rol=rol, **kw)
        self.admin = usuario('admin@x.test', Usuario.ROL_ADMIN, is_staff=True)
        self.recepcionista = usuario('adm2@x.test', Usuario.ROL_RECEPCIONISTA)
        self.educadora = usuario('edu@x.test', Usuario.ROL_EDUCADORA)
        self.usuario_tutor = Usuario.objects.create_user(username='mama', password='x12345678', nombres='K', apellidos='C', rol=Usuario.ROL_TUTOR)

        def nino(nombres, apellidos, suc, sala, turno, **kw):
            n = Nino.objects.create(nombres=nombres, apellidos=apellidos, fecha_nacimiento=date(2025, 1, 1), genero='M', **kw)
            i = Inscripcion.objects.create(nino=n, sucursal=suc, sala=sala, turno=turno, modalidad_pago='diaria',
                                           fecha_inicio=self.hoy, costo_mensual='650', costo_diario='40')
            return n, i
        self.nino1, self.insc1 = nino('Anthony', 'Nogales', self.suc, self.sala, self.turno, alergias='Maní')
        self.nino2, self.insc2 = nino('Valentina', 'Rojas', self.suc, self.sala, self.turno)
        self.nino3, self.insc3 = nino('Lucas', 'Paz', self.suc2, self.sala2, self.turno2)

        tutor = Tutor.objects.create(nombres='Karina', apellidos='Castro', ci='1', telefono='70000000', parentesco='madre')
        NinoTutor.objects.create(nino=self.nino1, tutor=tutor, es_principal=True)

        # Asistencia: este mes (Camacho: 2 presentes, 1 ausente, 1 justificado; Sopocachi: 1 presente) + 1 del mes pasado
        d = self.hoy.replace(day=1)
        def asis(insc, estado, fecha=d): return Asistencia.objects.create(inscripcion=insc, fecha=fecha, estado=estado)
        asis(self.insc1, 'presente'); asis(self.insc2, 'presente')
        asis(self.insc1, 'ausente', d + timedelta(days=1)) if (d + timedelta(days=1)).month == d.month else None
        asis(self.insc2, 'ausente_justificado', d + timedelta(days=1)) if (d + timedelta(days=1)).month == d.month else None
        asis(self.insc3, 'presente')
        asis(self.insc1, 'presente', self.mes_pasado)

        self.client.force_authenticate(self.admin)

    def cobro(self, insc, monto, estado='pendiente', dias_venc=10, emision=None, **kw):
        c = Cobro.objects.create(inscripcion=insc, tipo=Cobro.TIPO_DIARIO,
                                 periodo=str(self.hoy + timedelta(days=len(Cobro.objects.all()))),
                                 monto_base=monto, monto_final=monto, estado=estado,
                                 fecha_vencimiento=self.hoy + timedelta(days=dias_venc), **kw)
        if emision:
            Cobro.objects.filter(id=c.id).update(fecha_emision=emision)
        c.refresh_from_db()            # los montos vuelven como Decimal, no como el texto con que se crearon
        return c


class PermisosReportesTests(ReportesBase):
    def test_sin_login_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL_RESUMEN).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_educadora_y_tutor_no_pueden(self):
        for u in (self.educadora, self.usuario_tutor):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(URL_RESUMEN).status_code, 403, u.rol)
            self.assertEqual(self.client.get(URL_EXPORT + 'ninos/').status_code, 403, u.rol)

    def test_recepcionista_si_puede(self):
        self.client.force_authenticate(self.recepcionista)
        self.assertEqual(self.client.get(URL_RESUMEN).status_code, 200)

    def test_parametros_invalidos_dan_400(self):
        self.assertEqual(self.client.get(URL_RESUMEN + '?mes=2026-13').status_code, 400)
        self.assertEqual(self.client.get(URL_RESUMEN + '?mes=hola').status_code, 400)
        self.assertEqual(self.client.get(URL_RESUMEN + '?sucursal=no-es-uuid').status_code, 400)
        self.assertEqual(self.client.get(URL_EXPORT + 'ninos/?mes=xx').status_code, 400)

    def test_reporte_inexistente_404(self):
        self.assertEqual(self.client.get(URL_EXPORT + 'secretos/').status_code, 404)


class ResumenAsistenciaOcupacionTests(ReportesBase):
    def test_asistencia_total_y_por_sala(self):
        r = self.client.get(URL_RESUMEN + f'?mes={self.mes}').data['asistencia']
        por_sala = {s['sala_nombre']: s for s in r['por_sala']}
        self.assertEqual(set(por_sala), {'Sala Cuna', 'Sala Sol'})
        self.assertEqual(r['total'], sum(s['total'] for s in r['por_sala']))
        self.assertEqual(por_sala['Sala Sol']['presentes'], 1)
        self.assertEqual(por_sala['Sala Sol']['porcentaje'], 100.0)

    def test_filtro_de_sucursal_se_aplica(self):
        r = self.client.get(URL_RESUMEN + f'?mes={self.mes}&sucursal={self.suc2.id}').data
        self.assertEqual([s['sala_nombre'] for s in r['asistencia']['por_sala']], ['Sala Sol'])
        self.assertEqual([s['sala_nombre'] for s in r['ocupacion']['por_sala']], ['Sala Sol'])

    def test_mes_pasado_no_se_mezcla(self):
        mes_p = self.mes_pasado.strftime('%Y-%m')
        r = self.client.get(URL_RESUMEN + f'?mes={mes_p}').data['asistencia']
        self.assertEqual(r['total'], 1)
        self.assertEqual(r['presentes'], 1)

    def test_mes_sin_datos_no_divide_por_cero(self):
        r = self.client.get(URL_RESUMEN + '?mes=2020-01').data['asistencia']
        self.assertEqual((r['total'], r['porcentaje'], r['por_sala']), (0, None, []))

    def test_ocupacion_por_sala(self):
        r = self.client.get(URL_RESUMEN).data['ocupacion']
        sala = next(s for s in r['por_sala'] if s['sala_nombre'] == 'Sala Cuna')
        self.assertEqual((sala['inscritos'], sala['capacidad'], sala['porcentaje']), (2, 4, 50.0))
        self.assertEqual((r['inscritos'], r['capacidad']), (3, 14))

    def test_inscripcion_inactiva_no_ocupa_lugar(self):
        Inscripcion.objects.filter(id=self.insc2.id).update(activa=False)
        sala = next(s for s in self.client.get(URL_RESUMEN).data['ocupacion']['por_sala'] if s['sala_nombre'] == 'Sala Cuna')
        self.assertEqual(sala['inscritos'], 1)


class ResumenCobrosTests(ReportesBase):
    def test_cobros_del_mes_por_estado_y_montos(self):
        pagado = self.cobro(self.insc1, '100.00')
        Pago.objects.create(cobro=pagado, monto='100.00', registrado_por=self.admin); pagado.recalcular_estado()
        parcial = self.cobro(self.insc2, '200.00')
        Pago.objects.create(cobro=parcial, monto='50.00', registrado_por=self.admin); parcial.recalcular_estado()
        self.cobro(self.insc3, '80.00')                                            # pendiente
        self.cobro(self.insc1, '999.00', estado='anulado')                         # anulado: no cuenta en montos
        r = self.client.get(URL_RESUMEN + f'?mes={self.mes}').data['cobros_mes']
        self.assertEqual(r['cantidad'], 4)
        self.assertEqual(r['por_estado']['pagado']['cantidad'], 1)
        self.assertEqual(r['por_estado']['parcial']['cantidad'], 1)
        self.assertEqual(r['por_estado']['anulado']['cantidad'], 1)
        self.assertEqual(Decimal(r['emitido']), Decimal('380.00'))     # 100+200+80, sin el anulado
        self.assertEqual(Decimal(r['cobrado']), Decimal('150.00'))
        self.assertEqual(Decimal(r['saldo']),   Decimal('230.00'))     # 150 (parcial) + 80
        self.assertEqual(r['porcentaje_cobrado'], round(150 * 100 / 380, 1))

    def test_emitido_es_cobrado_mas_condonado_mas_saldo(self):
        c = self.cobro(self.insc1, '100.00')
        Pago.objects.create(cobro=c, monto='30.00', registrado_por=self.admin)
        Cobro.objects.filter(id=c.id).update(monto_condonado='20.00')
        r = self.client.get(URL_RESUMEN + f'?mes={self.mes}').data['cobros_mes']
        self.assertEqual(Decimal(r['cobrado']) + Decimal(r['condonado']) + Decimal(r['saldo']), Decimal(r['emitido']))

    def test_devolucion_descuenta_lo_cobrado(self):
        c = self.cobro(self.insc1, '100.00')
        Pago.objects.create(cobro=c, monto='100.00', registrado_por=self.admin)
        Devolucion.objects.create(cobro=c, monto='40.00', registrado_por=self.admin, motivo='error')
        r = self.client.get(URL_RESUMEN + f'?mes={self.mes}').data['cobros_mes']
        self.assertEqual(Decimal(r['cobrado']), Decimal('60.00'))

    def test_cobro_de_otro_mes_no_entra(self):
        self.cobro(self.insc1, '100.00', emision=self.mes_pasado)
        self.assertEqual(self.client.get(URL_RESUMEN + f'?mes={self.mes}').data['cobros_mes']['cantidad'], 0)

    def test_filtro_de_sucursal_en_cobros(self):
        self.cobro(self.insc1, '100.00'); self.cobro(self.insc3, '55.00')
        r = self.client.get(URL_RESUMEN + f'?mes={self.mes}&sucursal={self.suc2.id}').data['cobros_mes']
        self.assertEqual(Decimal(r['emitido']), Decimal('55.00'))

    def test_caja_coincide_con_la_pantalla_de_cobros(self):
        """Reportes y Cobros deben mostrar EXACTAMENTE los mismos números de caja y cartera."""
        c = self.cobro(self.insc1, '100.00', dias_venc=-5)       # vencido
        Pago.objects.create(cobro=c, monto='25.00', registrado_por=self.admin); c.recalcular_estado()
        self.cobro(self.insc2, '60.00')
        rep  = self.client.get(URL_RESUMEN + f'?mes={self.mes}').data['caja']
        cob  = self.client.get(f'/api/inscripciones/cobros/resumen/?mes={self.mes}').data
        self.assertEqual(rep, cob)
        self.assertEqual(Decimal(rep['pendiente']['monto']), Decimal('135.00'))   # 75 + 60
        self.assertEqual(Decimal(rep['vencido']['monto']),   Decimal('75.00'))
        self.assertEqual(Decimal(rep['caja_mes']['ingresos']), Decimal('25.00'))


class ExportacionesTests(ReportesBase):
    def test_asistencia_csv_solo_del_mes_y_legible(self):
        r = self.client.get(URL_EXPORT + f'asistencia/?mes={self.mes}')
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r['Content-Type'])
        self.assertIn(f'asistencia_{self.mes}.csv', r['Content-Disposition'])
        self.assertEqual(r['Cache-Control'], 'no-store')
        filas = leer_csv(r)
        self.assertEqual(int(r['X-Filas']), len(filas) - 1)
        self.assertEqual(filas[0][:6], ['Fecha', 'Niño', 'Sucursal', 'Sala', 'Turno', 'Estado'])
        cuerpo = filas[1:]
        self.assertEqual(len(cuerpo), Asistencia.objects.filter(fecha__year=self.hoy.year, fecha__month=self.hoy.month).count())
        self.assertTrue(all(f[0].startswith(self.mes) for f in cuerpo), 'no debe traer registros de otros meses')
        self.assertIn('Presente', {f[5] for f in cuerpo})           # estado legible, no 'ausente_justificado'
        self.assertFalse(any('_' in f[5] for f in cuerpo))

    def test_mes_sin_datos_devuelve_cero_filas(self):
        r = self.client.get(URL_EXPORT + 'asistencia/?mes=2020-01')
        self.assertEqual(r['X-Filas'], '0')
        self.assertEqual(len(leer_csv(r)), 1)          # solo la cabecera

    def test_asistencia_csv_filtra_por_sucursal(self):
        filas = leer_csv(self.client.get(URL_EXPORT + f'asistencia/?mes={self.mes}&sucursal={self.suc2.id}'))[1:]
        self.assertEqual({f[2] for f in filas}, {'Sopocachi'})

    def test_nombres_con_comillas_y_comas_no_rompen_la_fila(self):
        Nino.objects.filter(id=self.nino1.id).update(nombres='Ana "Nani", María', apellidos="O'Brien")
        filas = leer_csv(self.client.get(URL_EXPORT + f'asistencia/?mes={self.mes}'))
        nombres = {f[1] for f in filas[1:]}
        self.assertIn('Ana "Nani", María O\'Brien', nombres)
        self.assertTrue(all(len(f) == len(filas[0]) for f in filas), 'todas las filas con el mismo número de columnas')

    def test_inyeccion_de_formulas_se_neutraliza(self):
        Nino.objects.filter(id=self.nino1.id).update(nombres='=HYPERLINK("http://malo")', apellidos='X', alergias='@cmd|calc')
        filas = leer_csv(self.client.get(URL_EXPORT + 'ninos/'))
        cabecera, cuerpo = filas[0], filas[1:]
        fila = next(f for f in cuerpo if f[1] == 'X')
        self.assertEqual(fila[0], '\'=HYPERLINK("http://malo")')
        self.assertEqual(fila[cabecera.index('Alergias')], "'@cmd|calc")

    def test_montos_negativos_siguen_siendo_numeros(self):
        from reportes.services import celda
        self.assertEqual(celda(Decimal('-5.00')), Decimal('-5.00'))
        self.assertEqual(celda('-5'), "'-5")
        self.assertEqual(celda(None), '')
        self.assertEqual(celda(True), 'Sí')

    def test_cobros_csv_respeta_el_mes_y_calcula_saldo(self):
        c = self.cobro(self.insc1, '100.00')
        Pago.objects.create(cobro=c, monto='30.00', registrado_por=self.admin)
        self.cobro(self.insc2, '70.00', emision=self.mes_pasado)                 # otro mes: no debe salir
        filas = leer_csv(self.client.get(URL_EXPORT + f'cobros/?mes={self.mes}'))
        cab, cuerpo = filas[0], filas[1:]
        self.assertEqual(len(cuerpo), 1)
        f = cuerpo[0]
        self.assertEqual(Decimal(f[cab.index('Pagado (neto)')]), Decimal('30.00'))
        self.assertEqual(Decimal(f[cab.index('Saldo')]), Decimal('70.00'))
        self.assertEqual(f[cab.index('Tipo')], 'Cobro por día')

    def test_ninos_csv_incluye_sala_turno_y_tutores(self):
        filas = leer_csv(self.client.get(URL_EXPORT + 'ninos/'))
        cab, cuerpo = filas[0], filas[1:]
        self.assertEqual(len(cuerpo), 3)
        a = next(f for f in cuerpo if f[0] == 'Anthony')
        self.assertEqual(a[cab.index('Sala')], 'Sala Cuna')
        self.assertEqual(a[cab.index('Turno')], 'Turno mañana')
        self.assertEqual(a[cab.index('Alergias')], 'Maní')
        self.assertIn('Karina Castro', a[-1]); self.assertIn('70000000', a[-1])
        solo = leer_csv(self.client.get(URL_EXPORT + f'ninos/?sucursal={self.suc2.id}'))[1:]
        self.assertEqual([f[0] for f in solo], ['Lucas'])

    def test_inventario_csv_y_filtro_de_sucursal(self):
        ItemInventario.objects.create(sucursal=self.suc, nombre='Pañales', categoria='higiene', unidad='paquetes', stock_actual=1, stock_minimo=5)
        ItemInventario.objects.create(sucursal=self.suc2, nombre='Jabón', categoria='higiene', unidad='unidades', stock_actual=9, stock_minimo=2)
        filas = leer_csv(self.client.get(URL_EXPORT + 'inventario/'))
        cab, cuerpo = filas[0], filas[1:]
        self.assertEqual({f[1] for f in cuerpo}, {'Pañales', 'Jabón'})
        self.assertEqual(next(f for f in cuerpo if f[1] == 'Pañales')[cab.index('Stock bajo')], 'Sí')
        self.assertEqual({f[1] for f in leer_csv(self.client.get(URL_EXPORT + f'inventario/?sucursal={self.suc2.id}'))[1:]}, {'Jabón'})
