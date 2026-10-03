"""
Pruebas de: períodos por fechas, cierre de caja (efectivo / transferencia / QR),
deudas, descargas solo para admin y directora (la recepcionista no descarga)
y PDF de cada reporte.
"""
from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase  # noqa: F401  (ReportesBase ya lo usa)

from accounts.models import Usuario
from inscripciones.models import AbonoDiario, Cobro, Devolucion, Inscripcion, Pago
from . import services
from .tests import ReportesBase, URL_EXPORT, URL_RESUMEN, leer_csv

URL_CIERRE = '/api/reportes/cierre-caja/'
URL_PDF = '/api/reportes/pdf/'
TIPOS_PDF = ['informe-economico', 'cierre-caja', 'asistencia', 'cobros', 'deudas', 'ninos', 'inventario']


def D(x):
    return Decimal(str(x))


class CajaBase(ReportesBase):
    def setUp(self):
        super().setUp()
        self.directora = Usuario.objects.create_user(
            email='dir@x.test', password='x12345678', nombres='D', apellidos='Directora', rol=Usuario.ROL_DIRECTORA)
        self.d_hoy = self.hoy.isoformat()

    def pago(self, insc, monto, metodo='efectivo', fecha=None, usuario=None, **kw):
        c = Cobro.objects.create(
            inscripcion=insc, tipo=Cobro.TIPO_DIARIO, periodo=f'p{Cobro.objects.count()}', monto_base=monto,
            monto_final=monto, fecha_vencimiento=self.hoy)
        return Pago.objects.create(cobro=c, monto=monto, metodo_pago=metodo, fecha_pago=fecha or self.hoy,
                                   registrado_por=usuario or self.admin, **kw)

    def abono(self, insc, monto, metodo='efectivo', fecha=None, usuario=None, **kw):
        return AbonoDiario.objects.create(inscripcion=insc, monto=monto, metodo_pago=metodo,
                                          fecha_pago=fecha or self.hoy, registrado_por=usuario or self.admin, **kw)

    def cierre(self, **q):
        qs = '&'.join(f'{k}={v}' for k, v in q.items())
        r = self.client.get(f'{URL_CIERRE}?{qs}')
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    @staticmethod
    def neto(data, metodo):
        return D(next(m['neto'] for m in data['metodos'] if m['metodo'] == metodo))


class PeriodoPorFechasTests(CajaBase):
    def test_un_solo_dia_y_rango(self):
        ayer = self.hoy - timedelta(days=1)
        self.pago(self.insc1, 10, fecha=ayer)
        self.pago(self.insc1, 20)
        self.assertEqual(D(self.cierre(desde=self.d_hoy, hasta=self.d_hoy)['total']['neto']), D(20))
        self.assertEqual(D(self.cierre(desde=ayer.isoformat(), hasta=self.d_hoy)['total']['neto']), D(30))

    def test_el_mes_sigue_funcionando_y_da_lo_mismo_que_el_rango_completo(self):
        self.pago(self.insc1, 15)
        primero, ultimo = services.rango_mes(self.hoy.year, self.hoy.month)
        por_mes = self.client.get(URL_RESUMEN + f'?mes={self.mes}').data
        por_rango = self.client.get(URL_RESUMEN + f'?desde={primero}&hasta={ultimo}').data
        self.assertEqual(por_mes['caja'], por_rango['caja'])
        self.assertEqual(por_mes['cierre']['total'], por_rango['cierre']['total'])

    def test_resumen_por_rango_acota_la_asistencia(self):
        r = self.client.get(URL_RESUMEN + f'?desde={self.mes_pasado}&hasta={self.mes_pasado}').data
        self.assertEqual(r['asistencia']['total'], 1)

    def test_fechas_invalidas_dan_400(self):
        h = self.d_hoy
        for q in (f'desde={h}', f'hasta={h}', 'desde=hola&hasta=hola', f'desde={h}&hasta={self.hoy - timedelta(days=1)}',
                  f'desde={self.hoy - timedelta(days=400)}&hasta={h}'):
            self.assertEqual(self.client.get(f'{URL_CIERRE}?{q}').status_code, 400, q)
        self.assertEqual(self.client.get(f'{URL_CIERRE}?desde={h}&hasta={h}&metodo=bitcoin').status_code, 400)
        self.assertEqual(self.client.get(f'{URL_CIERRE}?usuario=no').status_code, 400)


class CierreDeCajaTests(CajaBase):
    def test_cuanto_dejar_en_efectivo_transferencia_y_qr(self):
        self.pago(self.insc1, 100, 'efectivo')
        self.pago(self.insc2, 50, 'efectivo')
        self.abono(self.insc1, 80, 'transferencia')
        self.pago(self.insc2, 30, 'qr')
        c = self.cierre(desde=self.d_hoy, hasta=self.d_hoy)
        self.assertEqual(self.neto(c, 'efectivo'), D(150))
        self.assertEqual(self.neto(c, 'transferencia'), D(80))
        self.assertEqual(self.neto(c, 'qr'), D(30))
        self.assertEqual(D(c['total']['neto']), D(260))
        self.assertEqual(len(c['movimientos']), 4)

    def test_devolucion_en_efectivo_resta_solo_del_efectivo(self):
        p = self.pago(self.insc1, 100, 'efectivo')
        self.pago(self.insc2, 40, 'qr')
        Devolucion.objects.create(cobro=p.cobro, monto=30, metodo_pago='efectivo', motivo='Cobró de más',
                                  fecha=self.hoy, registrado_por=self.admin)
        c = self.cierre(desde=self.d_hoy, hasta=self.d_hoy)
        self.assertEqual(self.neto(c, 'efectivo'), D(70))
        self.assertEqual(self.neto(c, 'qr'), D(40))
        self.assertEqual(D(c['total']['devoluciones']), D(30))

    def test_aplicar_un_abono_a_un_dia_no_cuenta_dos_veces(self):
        a = self.abono(self.insc1, 100, 'efectivo')
        cobro = Cobro.objects.create(inscripcion=self.insc1, tipo=Cobro.TIPO_DIARIO, periodo='x',
                                     monto_base=40, monto_final=40, fecha_vencimiento=self.hoy)
        Pago.objects.create(cobro=cobro, monto=40, metodo_pago='efectivo', fecha_pago=self.hoy, abono_origen=a)
        c = self.cierre(desde=self.d_hoy, hasta=self.d_hoy)
        self.assertEqual(self.neto(c, 'efectivo'), D(100))
        self.assertEqual(len(c['movimientos']), 1)

    def test_traspasos_entre_cuentas_no_mueven_la_caja(self):
        p = self.pago(self.insc1, 100, 'efectivo')
        Devolucion.objects.create(cobro=p.cobro, monto=20, a_cuenta=True, metodo_pago='efectivo',
                                  motivo='Cambio de turno', fecha=self.hoy)
        self.abono(self.insc1, 20, 'efectivo', es_traspaso=True)
        c = self.cierre(desde=self.d_hoy, hasta=self.d_hoy)
        self.assertEqual(self.neto(c, 'efectivo'), D(100))
        self.assertEqual(len(c['movimientos']), 1)

    def test_coincide_con_la_caja_de_cobros(self):
        self.pago(self.insc1, 100, 'efectivo')
        self.abono(self.insc2, 55, 'qr')
        primero, ultimo = services.rango_mes(self.hoy.year, self.hoy.month)
        c = self.cierre(desde=primero, hasta=ultimo)
        cobros = self.client.get(f'/api/inscripciones/cobros/resumen/?mes={self.mes}').data
        self.assertEqual(D(c['total']['neto']), D(cobros['caja_mes']['neto']))

    def test_por_dia_y_por_persona(self):
        ayer = self.hoy - timedelta(days=1)
        self.pago(self.insc1, 100, 'efectivo', fecha=ayer, usuario=self.recepcionista)
        self.pago(self.insc2, 60, 'qr', usuario=self.admin)
        c = self.cierre(desde=ayer.isoformat(), hasta=self.d_hoy)
        self.assertEqual([d['fecha'] for d in c['por_dia']], [ayer.isoformat(), self.d_hoy])
        self.assertEqual(D(c['por_dia'][0]['metodos']['efectivo']), D(100))
        personas = {u['usuario']: D(u['total']['neto']) for u in c['por_usuario']}
        self.assertEqual(personas[self.recepcionista.nombre_completo], D(100))
        self.assertEqual(personas[self.admin.nombre_completo], D(60))

    def test_filtros_de_usuario_metodo_y_sucursal(self):
        self.pago(self.insc1, 100, 'efectivo', usuario=self.recepcionista)
        self.pago(self.insc2, 60, 'qr', usuario=self.admin)
        self.pago(self.insc3, 25, 'efectivo', usuario=self.admin)               # otra sucursal
        q = dict(desde=self.d_hoy, hasta=self.d_hoy)
        self.assertEqual(D(self.cierre(**q, usuario=self.recepcionista.id)['total']['neto']), D(100))
        self.assertEqual(D(self.cierre(**q, metodo='qr')['total']['neto']), D(60))
        self.assertEqual(D(self.cierre(**q, sucursal=self.suc.id)['total']['neto']), D(160))
        self.assertEqual(D(self.cierre(**q, sucursal=self.suc2.id)['total']['neto']), D(25))

    def test_dia_sin_movimientos_da_ceros(self):
        c = self.cierre(desde=self.d_hoy, hasta=self.d_hoy)
        self.assertEqual(D(c['total']['neto']), D(0))
        self.assertEqual(c['movimientos'], [])

    def test_recepcionista_puede_ver_el_cierre_pero_educadora_y_tutor_no(self):
        self.pago(self.insc1, 10)
        self.client.force_authenticate(self.recepcionista)
        self.assertEqual(self.client.get(f'{URL_CIERRE}?desde={self.d_hoy}&hasta={self.d_hoy}').status_code, 200)
        for u in (self.educadora, self.usuario_tutor):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(URL_CIERRE).status_code, 403)

    def test_cierre_en_csv(self):
        self.pago(self.insc1, 100, 'efectivo')
        r = self.client.get(f'{URL_EXPORT}cierre-caja/?desde={self.d_hoy}&hasta={self.d_hoy}')
        filas = leer_csv(r)
        self.assertEqual(filas[0][:3], ['Fecha', 'Hora', 'Tipo'])
        self.assertEqual(len(filas), 2)
        self.assertIn('cierre_caja_', r['Content-Disposition'])


class DeudasTests(CajaBase):
    def test_mensualidad_iniciada_sin_pagar_es_deuda_y_pagada_no(self):
        n = self._mensual('Sofía', 'Mamani')
        insc = Inscripcion.objects.get(nino=n)
        ini = self.hoy - timedelta(days=5)
        Cobro.objects.create(inscripcion=insc, tipo=Cobro.TIPO_MENSUALIDAD, periodo='m', monto_base=650, monto_final=650,
                             fecha_vencimiento=ini + timedelta(days=5), periodo_inicio=ini, periodo_fin=ini + timedelta(days=30))
        d = services.listar_deudas(self.suc.id)
        fila = next(f for f in d['filas'] if f['nino'].startswith('Sofía'))
        self.assertEqual(fila['debe'], D(650))
        # al pagarla ya no figura
        c = Cobro.objects.get(inscripcion=insc)
        Pago.objects.create(cobro=c, monto=650, registrado_por=self.admin)
        c.recalcular_estado()
        self.assertFalse([f for f in services.listar_deudas(self.suc.id)['filas'] if f['nino'].startswith('Sofía')])

    def _mensual(self, nombres, apellidos):
        from ninos.models import Nino
        n = Nino.objects.create(nombres=nombres, apellidos=apellidos, fecha_nacimiento=date(2025, 1, 1), genero='F')
        Inscripcion.objects.create(nino=n, sucursal=self.suc, sala=self.sala, turno=self.turno,
                                   modalidad_pago='mensual', fecha_inicio=self.hoy - timedelta(days=5),
                                   costo_mensual='650', costo_diario='40')
        return n

    def test_el_resumen_trae_las_deudas(self):
        r = self.client.get(URL_RESUMEN + f'?mes={self.mes}').data
        self.assertIn('deudas', r)
        self.assertIn('cantidad', r['deudas'])


class DescargasSoloAdminYDirectoraTests(CajaBase):
    def test_la_recepcionista_no_descarga_nada(self):
        self.client.force_authenticate(self.recepcionista)
        for tipo in ('asistencia', 'cobros', 'ninos', 'inventario', 'deudas', 'cierre-caja'):
            self.assertEqual(self.client.get(f'{URL_EXPORT}{tipo}/').status_code, 403, f'csv {tipo}')
        for tipo in TIPOS_PDF:
            self.assertEqual(self.client.get(f'{URL_PDF}{tipo}/').status_code, 403, f'pdf {tipo}')

    def test_admin_y_directora_si_descargan(self):
        for u in (self.admin, self.directora):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(f'{URL_EXPORT}ninos/').status_code, 200, u.rol)
            self.assertEqual(self.client.get(f'{URL_PDF}ninos/').status_code, 200, u.rol)

    def test_educadora_y_tutor_tampoco(self):
        for u in (self.educadora, self.usuario_tutor):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(f'{URL_PDF}ninos/').status_code, 403)

    def test_sin_login_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'{URL_PDF}ninos/').status_code, 401)


class PdfTests(CajaBase):
    def setUp(self):
        super().setUp()
        self.pago(self.insc1, 100, 'efectivo')
        self.abono(self.insc2, 80, 'qr', usuario=self.recepcionista)
        ItemInventario = __import__('inventario.models', fromlist=['ItemInventario']).ItemInventario
        ItemInventario.objects.create(sucursal=self.suc, nombre='Pañales', categoria=ItemInventario.CATEGORIAS[0][0],
                                      unidad='paquetes', stock_actual=1, stock_minimo=3)

    def test_cada_reporte_genera_un_pdf_valido(self):
        for tipo in TIPOS_PDF:
            r = self.client.get(f'{URL_PDF}{tipo}/?desde={self.d_hoy}&hasta={self.d_hoy}')
            self.assertEqual(r.status_code, 200, tipo)
            self.assertEqual(r['Content-Type'], 'application/pdf', tipo)
            self.assertTrue(r.content.startswith(b'%PDF'), tipo)
            self.assertIn('.pdf', r['Content-Disposition'], tipo)
            self.assertEqual(r['Cache-Control'], 'no-store', tipo)

    def test_filtros_se_aceptan_en_el_pdf(self):
        q = f'?desde={self.d_hoy}&hasta={self.d_hoy}&sucursal={self.suc.id}&sala={self.sala.id}'
        self.assertEqual(self.client.get(f'{URL_PDF}asistencia/{q}&estado=ausente').status_code, 200)
        self.assertEqual(self.client.get(f'{URL_PDF}cobros/{q}&estado=pendiente&tipo=diario').status_code, 200)
        self.assertEqual(self.client.get(f'{URL_PDF}cierre-caja/{q}&metodo=qr&usuario={self.admin.id}').status_code, 200)

    def test_pdf_sin_datos_no_se_rompe(self):
        lejos = self.hoy - timedelta(days=200)
        for tipo in TIPOS_PDF:
            r = self.client.get(f'{URL_PDF}{tipo}/?desde={lejos}&hasta={lejos}')
            self.assertEqual(r.status_code, 200, tipo)

    def test_pdf_inexistente_404_y_filtros_malos_400(self):
        self.assertEqual(self.client.get(f'{URL_PDF}secretos/').status_code, 404)
        self.assertEqual(self.client.get(f'{URL_PDF}cobros/?estado=raro').status_code, 400)
        self.assertEqual(self.client.get(f'{URL_PDF}asistencia/?estado=pendiente').status_code, 400)
        self.assertEqual(self.client.get(f'{URL_PDF}cobros/?tipo=raro').status_code, 400)

    def test_nombres_con_caracteres_raros_no_rompen_el_pdf(self):
        self.nino1.nombres = 'Ana <b>&</b> "Luz"'
        self.nino1.save()
        self.assertEqual(self.client.get(f'{URL_PDF}ninos/').status_code, 200)
        self.assertEqual(self.client.get(f'{URL_PDF}cierre-caja/?desde={self.d_hoy}&hasta={self.d_hoy}').status_code, 200)

    def test_csv_con_rango_de_fechas_y_nombre_de_archivo(self):
        r = self.client.get(f'{URL_EXPORT}asistencia/?desde={self.hoy.replace(day=1)}&hasta={self.hoy}')
        self.assertEqual(r.status_code, 200)
        r2 = self.client.get(f'{URL_EXPORT}cobros/?mes={self.mes}')
        self.assertIn(f'cobros_{self.mes}.csv', r2['Content-Disposition'])
