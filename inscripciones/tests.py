"""
inscripciones/tests.py

Pruebas de la modalidad "por día":
  - días de la semana opcionales (planilla y regla de cobro de faltas),
  - abonos (saldo a favor) que se aplican solos a los cobros diarios,
  - caja sin doble conteo,
  - control de días contratados con alertas,
  - cambio de modalidad (por día ⇄ mensual) y transferencia conservando la cuenta.
La mensualidad se prueba solo en lo que debe seguir igual.
"""
from datetime import date, timedelta
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Usuario
from asistencia.models import Asistencia
from core.models import Sucursal, Sala, Turno
from ninos.models import Nino
from .models import Inscripcion, Cobro, Pago, AbonoDiario, DiasContratados
from .models import Devolucion
from django.db import IntegrityError, transaction
from .services import saldo_a_favor, resumen_financiero, resumen_diario, generar_ciclo_mensual, estado_pago
from .services import deuda_abierta

URL_INSC = '/api/inscripciones/inscripciones/'
URL_ASIST = '/api/asistencia/asistencia/'
URL_COBROS = '/api/inscripciones/cobros/'


def dec(x):
    return Decimal(str(x))


class PorDiaBase(APITestCase):
    """Sucursal/sala/turno (costo diario 40, mensual 650), un niño por día
    que empezó hace 10 días y un usuario de finanzas."""

    def setUp(self):
        self.hoy = date.today()
        self.sucursal = Sucursal.objects.create(nombre='Misael Kids - Camacho', direccion='Av. Camacho 123')
        self.sala = Sala.objects.create(
            sucursal=self.sucursal, nombre='Sala Cuna',
            edad_min_meses=0, edad_max_meses=24, capacidad_maxima=10,
        )
        self.turno = Turno.objects.create(
            sala=self.sala, nombre='Turno mañana', tipo=Turno.TIPO_MANANA,
            hora_inicio='08:00', hora_fin='12:00', costo_mensual='650.00', costo_diario='40.00',
        )
        self.staff = Usuario.objects.create_user(
            email='directora@misaelkids.test', password='clave12345',
            nombres='Jackie', apellidos='Castro', rol=Usuario.ROL_DIRECTORA, is_staff=True,
        )
        self.usuario_tutor = Usuario.objects.create_user(
            username='mama', password='clave12345', nombres='Karina', apellidos='Castro', rol=Usuario.ROL_TUTOR,
        )
        self.nino = Nino.objects.create(
            nombres='Valentina', apellidos='Rojas', fecha_nacimiento=date(2024, 6, 1), genero='F')
        self.inicio = self.hoy - timedelta(days=10)
        self.insc = self._inscribir(self.nino, fecha_inicio=self.inicio)
        self.client.force_authenticate(self.staff)

    def _inscribir(self, nino, modalidad=Inscripcion.MODALIDAD_DIARIA, fecha_inicio=None, **kw):
        insc = Inscripcion.objects.create(
            nino=nino, sucursal=self.sucursal, sala=self.sala, turno=self.turno,
            modalidad_pago=modalidad, fecha_inicio=fecha_inicio or self.hoy,
            costo_mensual='650.00', costo_diario='40.00', **kw)
        insc.refresh_from_db()      # los montos pasan de texto a Decimal, como en producción
        return insc

    def _otro_nino(self, nombre='Mateo', apellido='Quispe'):
        return Nino.objects.create(nombres=nombre, apellidos=apellido, fecha_nacimiento=date(2024, 3, 1), genero='M')

    # ── helpers ──
    def marcar(self, insc, fecha, estado):
        r = self.client.post(URL_ASIST, {
            'inscripcion': str(insc.id), 'fecha': fecha.isoformat(), 'estado': estado}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        return r.data['id']

    def cambiar(self, asist_id, estado):
        return self.client.patch(f'{URL_ASIST}{asist_id}/', {'estado': estado}, format='json')

    def cobro_de(self, insc, fecha):
        return Cobro.objects.filter(
            inscripcion=insc, tipo=Cobro.TIPO_DIARIO, periodo=fecha.isoformat()).first()

    def abonar(self, insc, monto, **extra):
        r = self.client.post(f'{URL_INSC}{insc.id}/registrar-abono/', {'monto': str(monto), **extra}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        return r

    def dia(self, n):
        """Un día pasado dentro del período de la inscripción: hoy - n."""
        return self.hoy - timedelta(days=n)


# ═══════════════════════════════════════════════════════════════════
class DiasDeLaSemanaTests(PorDiaBase):

    def test_es_dia_esperado_sin_dias_es_todos_desde_el_inicio(self):
        self.assertFalse(self.insc.es_dia_esperado(self.inicio - timedelta(days=1)))
        self.assertTrue(self.insc.es_dia_esperado(self.inicio))
        self.assertTrue(self.insc.es_dia_esperado(self.hoy))

    def test_es_dia_esperado_respeta_dias_semana_y_fecha_fin(self):
        lunes = self.hoy - timedelta(days=self.hoy.weekday())          # lunes de esta semana
        self.insc.dias_semana = [0, 2]                                 # lunes y miércoles
        self.insc.fecha_fin = lunes + timedelta(days=2)                # hasta el miércoles
        self.assertTrue(self.insc.es_dia_esperado(lunes))
        self.assertFalse(self.insc.es_dia_esperado(lunes + timedelta(days=1)))
        self.assertTrue(self.insc.es_dia_esperado(lunes + timedelta(days=2)))
        self.assertFalse(self.insc.es_dia_esperado(lunes + timedelta(days=7)))   # pasó fecha_fin

    def test_crear_inscripcion_diaria_con_dias_semana_los_ordena_y_valida(self):
        otro = self._otro_nino()
        r = self.client.post(URL_INSC, {
            'nino': str(otro.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
            'modalidad_pago': 'diaria', 'fecha_inicio': self.hoy.isoformat(),
            'costo_mensual': '650.00', 'costo_diario': '40.00', 'dias_semana': [4, 0, 2, 2],
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['dias_semana'], [0, 2, 4])
        self.assertEqual(r.data['dias_semana_display'], 'Lun, Mié, Vie')
        self.assertEqual(Cobro.objects.filter(inscripcion_id=r.data['id']).count(), 0)   # diaria: nada que cobrar aún

    def test_dias_semana_invalidos_se_rechazan(self):
        for malo in ([7], [-1], ['x'], 'lunes'):
            r = self.client.patch(f'{URL_INSC}{self.insc.id}/', {'dias_semana': malo}, format='json')
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, malo)

    def test_en_mensual_los_dias_semana_se_ignoran(self):
        otro = self._otro_nino()
        r = self.client.post(URL_INSC, {
            'nino': str(otro.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
            'modalidad_pago': 'mensual', 'fecha_inicio': self.hoy.isoformat(),
            'costo_mensual': '650.00', 'costo_diario': '40.00', 'dias_semana': [0, 1],
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['dias_semana'], [])
        # y la mensualidad sigue generando su primer ciclo como siempre
        self.assertEqual(Cobro.objects.filter(inscripcion_id=r.data['id'], tipo=Cobro.TIPO_MENSUALIDAD).count(), 1)

    def test_ausente_sin_aviso_en_dia_que_no_le_toca_no_cobra(self):
        self.insc.dias_semana = [(self.hoy.weekday() + 1) % 7]          # hoy NO le toca
        self.insc.save()
        self.marcar(self.insc, self.hoy, 'ausente')
        self.assertIsNone(self.cobro_de(self.insc, self.hoy))

    def test_presente_en_dia_que_no_le_toca_si_cobra(self):
        self.insc.dias_semana = [(self.hoy.weekday() + 1) % 7]
        self.insc.save()
        self.marcar(self.insc, self.hoy, 'presente')
        self.assertIsNotNone(self.cobro_de(self.insc, self.hoy))

    def test_ausente_antes_de_la_fecha_de_inicio_no_cobra(self):
        antes = self.inicio - timedelta(days=3)
        self.marcar(self.insc, antes, 'ausente')
        self.assertIsNone(self.cobro_de(self.insc, antes))


# ═══════════════════════════════════════════════════════════════════
class PlanillaDiariaTests(PorDiaBase):

    def planilla(self, fecha):
        r = self.client.get(f'{URL_ASIST}planilla/?fecha={fecha.isoformat()}&sala={self.sala.id}')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        return [n['inscripcion'] for n in r.data['ninos']], r.data['ninos']

    def test_aparece_desde_su_fecha_de_inicio_y_no_antes(self):
        futuro = self._inscribir(self._otro_nino('Luz', 'Mamani'), fecha_inicio=self.hoy + timedelta(days=1))
        ids_hoy, _ = self.planilla(self.hoy)
        self.assertNotIn(futuro.id, ids_hoy)
        ids_manana, _ = self.planilla(self.hoy + timedelta(days=1))
        self.assertIn(futuro.id, ids_manana)

    def test_solo_aparece_los_dias_de_la_semana_que_le_tocan(self):
        self.insc.dias_semana = [self.hoy.weekday()]
        self.insc.save()
        ids, ninos = self.planilla(self.hoy)
        self.assertIn(self.insc.id, ids)
        fila = next(n for n in ninos if n['inscripcion'] == self.insc.id)
        self.assertEqual(fila['modalidad_pago'], 'diaria')
        ids, _ = self.planilla(self.hoy + timedelta(days=1))
        self.assertNotIn(self.insc.id, ids)

    def test_si_ya_tiene_registro_ese_dia_aparece_aunque_no_le_toque(self):
        self.insc.dias_semana = [(self.hoy.weekday() + 1) % 7]
        self.insc.save()
        self.marcar(self.insc, self.hoy, 'presente')
        ids, _ = self.planilla(self.hoy)
        self.assertIn(self.insc.id, ids)

    def test_mensual_se_lista_igual_que_siempre(self):
        m = self._inscribir(self._otro_nino('Ana', 'Choque'),
                            modalidad=Inscripcion.MODALIDAD_MENSUAL, fecha_inicio=self.hoy + timedelta(days=5))
        ids, _ = self.planilla(self.hoy)
        self.assertIn(m.id, ids)

    def test_con_fecha_fin_deja_de_aparecer_despues(self):
        self.insc.fecha_fin = self.hoy - timedelta(days=2)
        self.insc.save()
        ids, _ = self.planilla(self.hoy)
        self.assertNotIn(self.insc.id, ids)


# ═══════════════════════════════════════════════════════════════════
class AbonosYSaldoTests(PorDiaBase):

    def test_abono_adelantado_queda_como_saldo_y_cubre_el_dia_al_asistir(self):
        r = self.abonar(self.insc, 100)
        self.assertIsNotNone(r.data['abono']['numero_recibo'])
        self.assertEqual(dec(r.data['resumen']['saldo_a_favor']), dec(100))
        self.assertEqual(Cobro.objects.filter(inscripcion=self.insc).count(), 0)

        self.marcar(self.insc, self.hoy, 'presente')
        cobro = self.cobro_de(self.insc, self.hoy)
        self.assertEqual(cobro.estado, Cobro.ESTADO_PAGADO)
        self.assertEqual(saldo_a_favor(self.insc), dec(60))                 # 100 - 40
        aplic = cobro.pagos.get()
        self.assertIsNotNone(aplic.abono_origen)
        self.assertIsNone(aplic.numero_recibo)                              # sin recibo propio

    def test_falta_sin_aviso_tambien_descuenta_del_saldo(self):
        self.abonar(self.insc, 100)
        self.marcar(self.insc, self.hoy, 'ausente')
        self.assertEqual(self.cobro_de(self.insc, self.hoy).estado, Cobro.ESTADO_PAGADO)
        self.assertEqual(saldo_a_favor(self.insc), dec(60))

    def test_falta_justificada_no_descuenta(self):
        self.abonar(self.insc, 100)
        self.marcar(self.insc, self.hoy, 'ausente_justificado')
        self.assertIsNone(self.cobro_de(self.insc, self.hoy))
        self.assertEqual(saldo_a_favor(self.insc), dec(100))

    def test_abono_menor_al_dia_deja_pago_parcial_y_otro_abono_lo_completa(self):
        self.abonar(self.insc, 30)
        self.marcar(self.insc, self.hoy, 'presente')
        cobro = self.cobro_de(self.insc, self.hoy)
        self.assertEqual(cobro.estado, Cobro.ESTADO_PARCIAL)
        self.assertEqual(cobro.saldo_pendiente, dec(10))
        self.abonar(self.insc, 10)
        cobro.refresh_from_db()
        self.assertEqual(cobro.estado, Cobro.ESTADO_PAGADO)
        self.assertEqual(saldo_a_favor(self.insc), dec(0))

    def test_pagar_despues_cubre_los_dias_adeudados_del_mas_antiguo_al_mas_nuevo(self):
        for n in (3, 2, 1):
            self.marcar(self.insc, self.dia(n), 'presente')       # 3 días de 40 = 120 de deuda
        self.assertEqual(dec(resumen_diario(self.insc)['deuda']), dec(120))
        self.abonar(self.insc, 100)                                # cubre 2 días y 20 del tercero
        estados = [self.cobro_de(self.insc, self.dia(n)).estado for n in (3, 2, 1)]
        self.assertEqual(estados, [Cobro.ESTADO_PAGADO, Cobro.ESTADO_PAGADO, Cobro.ESTADO_PARCIAL])
        self.assertEqual(dec(resumen_diario(self.insc)['deuda']), dec(20))
        self.assertEqual(saldo_a_favor(self.insc), dec(0))

    def test_justificar_un_dia_ya_cubierto_devuelve_el_saldo_y_cubre_otro_abierto(self):
        self.marcar(self.insc, self.dia(2), 'presente')            # queda debiendo 40
        self.abonar(self.insc, 40)                                 # lo cubre
        self.assertEqual(self.cobro_de(self.insc, self.dia(2)).estado, Cobro.ESTADO_PAGADO)
        self.marcar(self.insc, self.dia(1), 'presente')            # sin saldo: queda abierto
        self.assertIn(self.cobro_de(self.insc, self.dia(1)).estado, (Cobro.ESTADO_PENDIENTE, Cobro.ESTADO_VENCIDO))

        # La falta del día -2 resulta ser avisada: se anula y su plata cubre el día -1
        a2 = Asistencia.objects.get(inscripcion=self.insc, fecha=self.dia(2))
        r = self.cambiar(a2.id, 'ausente_justificado')
        self.assertEqual(r.data['cobro_info']['accion'], 'anulado')
        self.assertEqual(self.cobro_de(self.insc, self.dia(2)).estado, Cobro.ESTADO_ANULADO)
        self.assertEqual(self.cobro_de(self.insc, self.dia(1)).estado, Cobro.ESTADO_PAGADO)
        self.assertEqual(saldo_a_favor(self.insc), dec(0))

    def test_pago_real_sigue_bloqueando_la_anulacion(self):
        aid = self.marcar(self.insc, self.hoy, 'presente')
        cobro = self.cobro_de(self.insc, self.hoy)
        Pago.objects.create(cobro=cobro, monto='10.00', registrado_por=self.staff)
        cobro.recalcular_estado()
        r = self.cambiar(aid, 'ausente_justificado')
        self.assertEqual(r.data['cobro_info']['accion'], 'no_anulado')

    def test_borrar_la_asistencia_anula_el_dia_y_libera_el_saldo(self):
        self.abonar(self.insc, 40)
        aid = self.marcar(self.insc, self.hoy, 'presente')
        self.assertEqual(saldo_a_favor(self.insc), dec(0))
        r = self.client.delete(f'{URL_ASIST}{aid}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.cobro_de(self.insc, self.hoy).estado, Cobro.ESTADO_ANULADO)
        self.assertEqual(saldo_a_favor(self.insc), dec(40))

    def test_cobro_con_descuento_usa_el_costo_diario_final(self):
        self.insc.tipo_ajuste = Inscripcion.AJUSTE_DESCUENTO_PCT
        self.insc.porcentaje_ajuste = dec(25)                      # 40 -> 30
        self.insc.save()
        self.abonar(self.insc, 100)
        self.marcar(self.insc, self.hoy, 'presente')
        self.assertEqual(self.cobro_de(self.insc, self.hoy).monto_final, dec(30))
        self.assertEqual(saldo_a_favor(self.insc), dec(70))

    def test_abonos_validaciones_y_permisos(self):
        url = f'{URL_INSC}{self.insc.id}/registrar-abono/'
        for malo in ({}, {'monto': 'abc'}, {'monto': '0'}, {'monto': '-5'}, {'monto': '10', 'metodo_pago': 'bitcoin'},
                     {'monto': '10', 'fecha_pago': '31-12-2026'}, {'monto': '10', 'dias': 'x'}):
            self.assertEqual(self.client.post(url, malo, format='json').status_code,
                             status.HTTP_400_BAD_REQUEST, malo)
        # un tutor no puede registrar abonos
        self.client.force_authenticate(self.usuario_tutor)
        self.assertEqual(self.client.post(url, {'monto': '10'}, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(AbonoDiario.objects.count(), 0)

    def test_abono_en_inscripcion_mensual_se_rechaza(self):
        m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        r = self.client.post(f'{URL_INSC}{m.id}/registrar-abono/', {'monto': '50'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_numeros_de_recibo_de_abonos_son_correlativos(self):
        a = self.abonar(self.insc, 10).data['abono']['numero_recibo']
        b = self.abonar(self.insc, 10).data['abono']['numero_recibo']
        self.assertEqual(b, a + 1)

    def test_recibo_pdf_del_abono(self):
        abono_id = self.abonar(self.insc, 50).data['abono']['id']
        r = self.client.get(f'/api/inscripciones/recibos/abono/{abono_id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_calendario_incluye_resumen_y_estado_de_cada_dia(self):
        self.abonar(self.insc, 40)
        self.marcar(self.insc, self.hoy, 'presente')
        r = self.client.get(f'{URL_INSC}{self.insc.id}/calendario-pagos/?anio={self.hoy.year}&mes={self.hoy.month}')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['modalidad'], 'diaria')
        self.assertIn('resumen', r.data)
        fila = next(d for d in r.data['calendario']['dias'] if d['fecha'] == self.hoy.isoformat())
        self.assertEqual(fila['asistencia'], 'presente')
        self.assertEqual(fila['cobro']['estado'], 'pagado')
        self.assertTrue(fila['esperado'])


# ═══════════════════════════════════════════════════════════════════
class CajaSinDobleConteoTests(PorDiaBase):

    def test_el_abono_entra_a_caja_una_sola_vez_y_sus_aplicaciones_no(self):
        self.abonar(self.insc, 100)
        self.marcar(self.insc, self.hoy, 'presente')              # aplica 40 del abono
        self.marcar(self.insc, self.dia(1), 'presente')           # aplica otros 40
        caja = resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']
        self.assertEqual(caja['ingresos'], dec(100))              # no 180
        self.assertEqual(caja['cantidad_pagos'], 1)

    def test_pendiente_no_incluye_dias_ya_cubiertos_por_abono(self):
        self.abonar(self.insc, 40)
        self.marcar(self.insc, self.dia(1), 'presente')           # cubierto por el abono
        self.marcar(self.insc, self.hoy, 'presente')              # sin cubrir: 40
        r = resumen_financiero(self.hoy.year, self.hoy.month)
        self.assertEqual(r['pendiente']['monto'], dec(40))
        self.assertEqual(r['pendiente']['cantidad'], 1)

    def test_endpoint_movimientos_lista_el_abono_con_su_recibo_y_totales_correctos(self):
        self.abonar(self.insc, 100)
        self.marcar(self.insc, self.hoy, 'presente')
        r = self.client.get(f'{URL_COBROS}movimientos/')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['count'], 1)
        fila = r.data['results'][0]
        self.assertTrue(fila['es_abono'])
        self.assertEqual(fila['tipo'], 'pago')
        self.assertIsNotNone(fila['numero_recibo'])
        self.assertEqual(dec(r.data['totales']['ingresos']), dec(100))
        self.assertEqual(dec(r.data['totales']['por_metodo']['efectivo']['ingresos']), dec(100))
        # filtrar por "devolucion" no debe traer abonos
        self.assertEqual(self.client.get(f'{URL_COBROS}movimientos/?tipo=devolucion').data['count'], 0)
        # búsqueda por nombre del niño llega al abono
        self.assertEqual(self.client.get(f'{URL_COBROS}movimientos/?search=Valentina').data['count'], 1)

    def test_pago_directo_a_un_cobro_diario_sigue_funcionando_como_antes(self):
        self.marcar(self.insc, self.hoy, 'presente')
        cobro = self.cobro_de(self.insc, self.hoy)
        r = self.client.post(f'{URL_COBROS}{cobro.id}/registrar-pago/', {'monto': '40'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        caja = resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']
        self.assertEqual(caja['ingresos'], dec(40))


# ═══════════════════════════════════════════════════════════════════
class DiasContratadosTests(PorDiaBase):

    def test_primer_abono_con_dias_es_inicial_y_el_siguiente_es_ampliacion(self):
        self.abonar(self.insc, 200, dias=5)
        self.abonar(self.insc, 200, dias=5)
        tipos = list(self.insc.dias_contratados.values_list('tipo', flat=True))
        self.assertEqual(tipos, [DiasContratados.TIPO_INICIAL, DiasContratados.TIPO_AMPLIACION])
        r = resumen_diario(self.insc)
        self.assertEqual(r['dias_contratados']['total'], 10)
        self.assertEqual(len(r['dias_contratados']['historial']), 2)

    def test_abono_sin_dias_no_toca_los_dias_contratados(self):
        self.abonar(self.insc, 100)
        self.assertEqual(self.insc.dias_contratados.count(), 0)

    def test_dias_acordados_al_inscribir(self):
        otro = self._otro_nino()
        r = self.client.post(URL_INSC, {
            'nino': str(otro.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
            'modalidad_pago': 'diaria', 'fecha_inicio': self.hoy.isoformat(),
            'costo_mensual': '650.00', 'costo_diario': '40.00', 'dias_contratados': 5,
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        insc = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(resumen_diario(insc)['dias_contratados']['total'], 5)

    def test_alerta_al_completar_y_al_excederse_de_lo_acordado(self):
        self.client.post(f'{URL_INSC}{self.insc.id}/contratar-dias/', {'cantidad': 2, 'tipo': 'inicial'}, format='json')
        self.marcar(self.insc, self.dia(2), 'presente')
        self.marcar(self.insc, self.dia(1), 'presente')
        codigos = [a['codigo'] for a in resumen_diario(self.insc)['alertas']]
        self.assertIn('completo', codigos)
        self.marcar(self.insc, self.hoy, 'ausente')               # el tercero cobrado excede lo acordado
        codigos = [a['codigo'] for a in resumen_diario(self.insc)['alertas']]
        self.assertIn('excedido', codigos)
        self.assertIn('deuda', codigos)

    def test_ampliar_de_5_a_10_y_reducir(self):
        url = f'{URL_INSC}{self.insc.id}/contratar-dias/'
        self.client.post(url, {'cantidad': 5, 'tipo': 'inicial'}, format='json')
        r = self.client.post(url, {'cantidad': 5, 'tipo': 'ampliacion', 'nota': 'La mamá pidió más días'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data['dias_contratados']['total'], 10)
        self.assertEqual(r.data['dias_contratados']['historial'][-1]['nota'], 'La mamá pidió más días')
        r = self.client.post(url, {'cantidad': 3, 'tipo': 'reduccion'}, format='json')
        self.assertEqual(r.data['dias_contratados']['total'], 7)
        # no se puede reducir más de lo contratado
        self.assertEqual(self.client.post(url, {'cantidad': 99, 'tipo': 'reduccion'}, format='json').status_code,
                         status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(url, {'cantidad': 0}, format='json').status_code, status.HTTP_400_BAD_REQUEST)

    def test_conteos_de_asistencia_en_el_resumen(self):
        self.marcar(self.insc, self.dia(3), 'presente')
        self.marcar(self.insc, self.dia(2), 'ausente')
        self.marcar(self.insc, self.dia(1), 'ausente_justificado')
        a = resumen_diario(self.insc)['asistencia']
        self.assertEqual((a['presentes'], a['ausentes_cobrados'], a['justificados']), (1, 1, 1))
        self.assertEqual(resumen_diario(self.insc)['dias_contratados']['cobrados'], 2)

    def test_endpoint_resumen_diario_solo_para_diaria(self):
        self.assertEqual(self.client.get(f'{URL_INSC}{self.insc.id}/resumen-diario/').status_code, status.HTTP_200_OK)
        m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        self.assertEqual(self.client.get(f'{URL_INSC}{m.id}/resumen-diario/').status_code, status.HTTP_400_BAD_REQUEST)


# ═══════════════════════════════════════════════════════════════════
class CambioDeModalidadTests(PorDiaBase):

    def url(self, insc=None):
        return f'{URL_INSC}{(insc or self.insc).id}/cambiar-modalidad/'

    def test_diaria_a_mensual_cierra_la_anterior_y_conserva_su_historial(self):
        self.abonar(self.insc, 40)                      # debe estar al día para poder cambiar
        self.marcar(self.insc, self.dia(2), 'presente')
        cobro_viejo = self.cobro_de(self.insc, self.dia(2))
        r = self.client.post(self.url(), {'fecha_inicio': self.hoy.isoformat()}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

        self.insc.refresh_from_db()
        self.assertFalse(self.insc.activa)
        self.assertEqual(self.insc.fecha_fin, self.hoy - timedelta(days=1))
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        self.assertEqual(nueva.modalidad_pago, 'mensual')
        self.assertEqual(nueva.inscripcion_origen_id, self.insc.id)
        self.assertEqual(nueva.fecha_inicio, self.hoy)
        self.assertEqual(Cobro.objects.filter(inscripcion=nueva, tipo=Cobro.TIPO_MENSUALIDAD).count(), 1)
        # el cobro diario viejo sigue intacto en su inscripción
        cobro_viejo.refresh_from_db()
        self.assertEqual(cobro_viejo.inscripcion_id, self.insc.id)
        self.assertEqual(cobro_viejo.monto_final, dec(40))
        # y el niño tiene una sola inscripción activa
        self.assertEqual(Inscripcion.objects.filter(nino=self.nino, activa=True).count(), 1)

    def test_hereda_ajuste_y_precio_negociado(self):
        self.insc.tipo_ajuste = Inscripcion.AJUSTE_DESCUENTO_MONTO
        self.insc.monto_ajuste = dec(50)
        self.insc.costo_mensual = dec(600)
        self.insc.motivo_ajuste = 'Hermanos'
        self.insc.save()
        r = self.client.post(self.url(), {}, format='json')
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        self.assertEqual(nueva.tipo_ajuste, Inscripcion.AJUSTE_DESCUENTO_MONTO)
        self.assertEqual(nueva.costo_mensual, dec(600))
        self.assertEqual(nueva.costo_mensual_final, dec(550))
        self.assertIn('Hermanos', nueva.motivo_ajuste)
        cobro = Cobro.objects.get(inscripcion=nueva, tipo=Cobro.TIPO_MENSUALIDAD)
        self.assertEqual(cobro.monto_final, dec(550))

    def test_el_saldo_a_favor_se_aplica_a_la_primera_mensualidad_sin_duplicar_caja(self):
        self.abonar(self.insc, 200)
        caja_antes = resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']['ingresos']
        r = self.client.post(self.url(), {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(dec(r.data['traspaso']['saldo_aplicado']), dec(200))
        self.assertEqual(dec(r.data['traspaso']['saldo_restante']), dec(0))
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        mens = Cobro.objects.get(inscripcion=nueva, tipo=Cobro.TIPO_MENSUALIDAD)
        self.assertEqual(mens.monto_pagado, dec(200))
        self.assertEqual(mens.estado, Cobro.ESTADO_PARCIAL)
        self.assertEqual(mens.saldo_pendiente, dec(450))
        # la caja no cambia: el dinero ya había entrado con el abono
        self.assertEqual(resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']['ingresos'], caja_antes)

    def test_si_el_saldo_supera_la_mensualidad_lo_que_sobra_se_informa(self):
        self.abonar(self.insc, 700)
        r = self.client.post(self.url(), {}, format='json')
        self.assertEqual(dec(r.data['traspaso']['saldo_aplicado']), dec(650))
        self.assertEqual(dec(r.data['traspaso']['saldo_restante']), dec(50))
        self.assertTrue(any('saldo a favor' in a for a in r.data['advertencias']))
        # lo que sobró queda en la cuenta de la mensualidad nueva y cubre su siguiente ciclo
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        self.assertEqual(saldo_a_favor(nueva), dec(50))
        self.assertEqual(saldo_a_favor(self.insc), dec(0))
        siguiente = generar_ciclo_mensual(nueva, ciclo_num=1)
        self.assertEqual(siguiente.monto_pagado, dec(50))
        self.assertEqual(saldo_a_favor(nueva), dec(0))

    def test_con_deuda_por_dias_no_se_puede_pasar_a_mensual_hasta_pagar(self):
        self.marcar(self.insc, self.dia(2), 'presente')
        self.marcar(self.insc, self.dia(1), 'ausente')            # 2 días cobrados sin pagar = 80
        r = self.client.post(self.url(), {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['codigo'], 'deuda_pendiente')
        self.assertEqual(dec(r.data['deuda']), dec(80))
        self.assertIn('al día', r.data['error'])
        # no se cambió nada
        self.assertTrue(Inscripcion.objects.get(pk=self.insc.pk).activa)
        self.assertEqual(Inscripcion.objects.filter(nino=self.insc.nino).count(), 1)
        # al pagar lo que debe, ya puede pasar a mensual
        self.abonar(self.insc, 80)
        r = self.client.post(self.url(), {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(dec(r.data['traspaso']['deuda_dias_pendientes']), dec(0))

    def test_con_deuda_en_la_mensualidad_no_se_puede_pasar_a_por_dia(self):
        m = self._inscribir(self._otro_nino('Deuda', 'Mensual'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        generar_ciclo_mensual(m, ciclo_num=0)
        # la mensualidad generada aún no está pagada
        r = self.client.post(self.url(m), {'dias_semana': [1, 3]}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['codigo'], 'deuda_pendiente')
        self.assertTrue(Inscripcion.objects.get(pk=m.pk).activa)
        # pagada completa → ya puede cambiar
        c = Cobro.objects.get(inscripcion=m, tipo=Cobro.TIPO_MENSUALIDAD)
        pago = self.client.post(f'{URL_COBROS}{c.id}/registrar-pago/', {'monto': str(c.monto_final)}, format='json')
        self.assertEqual(pago.status_code, status.HTTP_200_OK, pago.data)
        r = self.client.post(self.url(m), {'dias_semana': [1, 3]}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

    def test_con_la_mensualidad_pagada_a_medias_tambien_se_bloquea(self):
        m = self._inscribir(self._otro_nino('Parcial', 'Mensual'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        generar_ciclo_mensual(m, ciclo_num=0)
        c = Cobro.objects.get(inscripcion=m, tipo=Cobro.TIPO_MENSUALIDAD)
        self.client.post(f'{URL_COBROS}{c.id}/registrar-pago/', {'monto': '100'}, format='json')
        r = self.client.post(self.url(m), {'dias_semana': [1, 3]}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(dec(r.data['deuda']), c.monto_final - dec(100))

    def test_la_deuda_de_una_inscripcion_anterior_tambien_bloquea_el_cambio(self):
        # Primero se paga y pasa a mensual; luego se reabre una deuda en la inscripción cerrada.
        self.abonar(self.insc, 40)
        self.marcar(self.insc, self.dia(1), 'presente')
        r = self.client.post(self.url(), {'fecha_inicio': self.hoy.isoformat()}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        c = Cobro.objects.get(inscripcion=nueva, tipo=Cobro.TIPO_MENSUALIDAD)
        self.client.post(f'{URL_COBROS}{c.id}/registrar-pago/', {'monto': str(c.monto_final)}, format='json')
        viejo = Cobro.objects.get(inscripcion=self.insc, tipo=Cobro.TIPO_DIARIO)
        viejo.pagos.all().delete()
        viejo.estado = Cobro.ESTADO_PENDIENTE
        viejo.save()
        r = self.client.post(self.url(nueva), {'dias_semana': [1, 3]}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('inscripción anterior', r.data['error'])

    def test_advierte_si_el_dia_de_inicio_ya_estaba_cobrado_por_dia(self):
        self.abonar(self.insc, 40)
        self.marcar(self.insc, self.hoy, 'presente')
        r = self.client.post(self.url(), {'fecha_inicio': self.hoy.isoformat()}, format='json')
        self.assertTrue(any('dos veces' in a for a in r.data['advertencias']))

    def test_transferir_cambiando_de_modalidad_tambien_exige_estar_al_dia(self):
        self.marcar(self.insc, self.dia(1), 'presente')            # 40 sin pagar
        tarde = Turno.objects.create(
            sala=self.sala, nombre='Turno tarde', tipo=Turno.TIPO_TARDE,
            hora_inicio='14:00', hora_fin='18:00', costo_mensual='650.00', costo_diario='40.00')
        r = self.client.post(f'{URL_INSC}{self.insc.id}/transferir/', {
            'sala': self.sala.id, 'turno': tarde.id, 'modalidad_pago': 'mensual'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data['codigo'], 'deuda_pendiente')
        self.assertTrue(Inscripcion.objects.get(pk=self.insc.pk).activa)

    def test_al_pasar_a_mensual_se_puede_indicar_otro_precio(self):
        r = self.client.post(self.url(), {'costo_mensual': '500.00'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        self.assertEqual(nueva.costo_mensual, dec('500.00'))
        self.assertEqual(nueva.costo_diario, dec('40.00'))                       # el otro precio no se toca
        self.assertEqual(Cobro.objects.get(inscripcion=nueva, tipo=Cobro.TIPO_MENSUALIDAD).monto_final, dec('500.00'))
        self.assertIn('Precio mensualidad acordado: Bs. 500.00', nueva.motivo_ajuste)

    def test_al_pasar_a_por_dia_se_puede_indicar_otro_precio_y_se_mantiene_el_descuento(self):
        m = self._inscribir(self._otro_nino('Rosa', 'Precio'), modalidad=Inscripcion.MODALIDAD_MENSUAL,
                            tipo_ajuste=Inscripcion.AJUSTE_DESCUENTO_PCT, porcentaje_ajuste='10')
        generar_ciclo_mensual(m, ciclo_num=0)
        c = Cobro.objects.get(inscripcion=m, tipo=Cobro.TIPO_MENSUALIDAD)
        self.client.post(f'{URL_COBROS}{c.id}/registrar-pago/', {'monto': str(c.monto_final)}, format='json')
        r = self.client.post(self.url(m), {'dias_semana': [1, 3], 'costo_diario': '50'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        self.assertEqual(nueva.costo_diario, dec('50.00'))
        self.assertEqual(nueva.costo_diario_final, dec('45.00'))                  # 10 % de descuento heredado

    def test_sin_indicar_precio_se_conserva_el_de_la_inscripcion(self):
        self.insc.costo_mensual = dec('600')                                      # precio negociado
        self.insc.save()
        r = self.client.post(self.url(), {}, format='json')
        self.assertEqual(Inscripcion.objects.get(pk=r.data['inscripcion']['id']).costo_mensual, dec('600.00'))

    def test_un_precio_no_valido_se_rechaza_sin_cambiar_nada(self):
        for malo in ('abc', '0', '-50', '999999'):
            r = self.client.post(self.url(), {'costo_mensual': malo}, format='json')
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, malo)
        self.assertTrue(Inscripcion.objects.get(pk=self.insc.pk).activa)
        self.assertEqual(Inscripcion.objects.filter(nino=self.insc.nino).count(), 1)

    def test_mensual_a_diaria_con_dias_de_la_semana(self):
        m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        r = self.client.post(self.url(m), {'dias_semana': [1, 3]}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        self.assertEqual((nueva.modalidad_pago, nueva.dias_semana), ('diaria', [1, 3]))
        self.assertEqual(Cobro.objects.filter(inscripcion=nueva).count(), 0)

    def test_validaciones(self):
        self.assertEqual(self.client.post(self.url(), {'modalidad': 'diaria'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(self.url(), {'modalidad': 'semanal'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(
            self.url(), {'fecha_inicio': (self.inicio - timedelta(days=1)).isoformat()}, format='json').status_code, 400)
        self.assertEqual(self.client.post(self.url(), {'fecha_inicio': '01/10/2026'}, format='json').status_code, 400)
        # tutor sin permiso
        self.client.force_authenticate(self.usuario_tutor)
        self.assertEqual(self.client.post(self.url(), {}, format='json').status_code, 403)
        # nada se cambió por los intentos fallidos
        self.insc.refresh_from_db()
        self.assertTrue(self.insc.activa)
        # una inscripción ya cerrada no se puede cambiar otra vez
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(self.url(), {}, format='json').status_code, 201)
        self.assertEqual(self.client.post(self.url(), {}, format='json').status_code, 400)


# ═══════════════════════════════════════════════════════════════════
class TransferirDiariaTests(PorDiaBase):

    def setUp(self):
        super().setUp()
        self.sala2 = Sala.objects.create(
            sucursal=self.sucursal, nombre='Sala Gateo',
            edad_min_meses=12, edad_max_meses=36, capacidad_maxima=10,
        )
        self.turno2 = Turno.objects.create(
            sala=self.sala2, nombre='Turno tarde', tipo=Turno.TIPO_TARDE,
            hora_inicio='14:00', hora_fin='18:00', costo_mensual='700.00', costo_diario='45.00',
        )

    def test_transferir_diaria_a_diaria_lleva_el_saldo_los_dias_y_los_dias_de_la_semana(self):
        self.insc.dias_semana = [0, 2]
        self.insc.save()
        self.abonar(self.insc, 200, dias=5)
        self.marcar(self.insc, self.dia(1), 'presente')           # consume 1 día: restan 4 acordados
        r = self.client.post(f'{URL_INSC}{self.insc.id}/transferir/', {
            'sala': self.sala2.id, 'turno': self.turno2.id,
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(nueva.modalidad_pago, 'diaria')
        self.assertEqual(nueva.dias_semana, [0, 2])
        self.assertEqual(saldo_a_favor(nueva), dec(160))          # 200 - 40 ya consumidos
        self.assertEqual(resumen_diario(nueva)['dias_contratados']['total'], 4)
        self.assertEqual(r.data['traspaso']['dias_trasladados'], 4)
        # el cobro ya pagado en la inscripción vieja sigue ahí
        self.assertEqual(self.cobro_de(self.insc, self.dia(1)).estado, Cobro.ESTADO_PAGADO)

    def test_transferir_una_mensual_no_agrega_nada_de_la_cuenta_diaria(self):
        m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        r = self.client.post(f'{URL_INSC}{m.id}/transferir/', {
            'sala': self.sala2.id, 'turno': self.turno2.id}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertNotIn('traspaso', r.data)
        self.assertEqual(r.data['dias_semana'], [])


# ═══════════════════════════════════════════════════════════════════
class MensualidadSigueIgualTests(PorDiaBase):
    """La mensualidad no debe haber cambiado."""

    def setUp(self):
        super().setUp()
        self.m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL)

    def test_la_falta_sin_aviso_no_genera_ni_anula_nada_en_mensual(self):
        self.marcar(self.m, self.hoy, 'ausente')
        self.assertEqual(Cobro.objects.filter(inscripcion=self.m).count(), 0)

    def test_presente_genera_el_ciclo_y_el_calendario_mensual_no_trae_resumen_diario(self):
        self.marcar(self.m, self.hoy, 'presente')
        self.assertEqual(Cobro.objects.filter(inscripcion=self.m, tipo=Cobro.TIPO_MENSUALIDAD).count(), 1)
        r = self.client.get(f'{URL_INSC}{self.m.id}/calendario-pagos/')
        self.assertEqual(r.data['modalidad'], 'mensual')
        self.assertNotIn('resumen', r.data)

    def test_pago_parcial_y_cierre_de_mensualidad_funcionan_igual(self):
        self.client.post(f'{URL_INSC}{self.m.id}/generar-cobro-mensual/', {'ciclo': 0}, format='json')
        cobro = Cobro.objects.get(inscripcion=self.m, tipo=Cobro.TIPO_MENSUALIDAD)
        r = self.client.post(f'{URL_COBROS}{cobro.id}/registrar-pago/', {'monto': '200'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['estado'], 'parcial')
        r = self.client.post(f'{URL_COBROS}{cobro.id}/cerrar-con-lo-pagado/', {'motivo': 'Acuerdo'}, format='json')
        self.assertEqual(r.data['estado'], 'pagado')
        self.assertEqual(Pago.objects.filter(cobro=cobro, abono_origen__isnull=False).count(), 0)


# ═══════════════════════════════════════════════════════════════════
class TransferirMensualTests(PorDiaBase):
    """
    Mensual → mensual (cambio de turno, sala o sucursal) con el ciclo en curso:
    el ciclo no se duplica y solo se compensa la diferencia de precio.
    """

    def setUp(self):
        super().setUp()
        self.sala2 = Sala.objects.create(
            sucursal=self.sucursal, nombre='Sala Gateo', edad_min_meses=12, edad_max_meses=36, capacidad_maxima=10)
        mk = lambda nombre, mensual, tipo: Turno.objects.create(
            sala=self.sala2, nombre=nombre, tipo=tipo, hora_inicio='14:00', hora_fin='18:00',
            costo_mensual=mensual, costo_diario='40.00')
        self.t_igual  = mk('Tarde igual',  '650.00', Turno.TIPO_TARDE)
        self.t_caro   = mk('Tarde cara',   '700.00', Turno.TIPO_MANANA)
        self.t_barato = mk('Tarde barata', '600.00', Turno.TIPO_COMPLETO)
        self.ana = self._otro_nino('Ana', 'Choque')
        self.m = self._inscribir(self.ana, modalidad=Inscripcion.MODALIDAD_MENSUAL, fecha_inicio=self.hoy - timedelta(days=10))
        self.ciclo = generar_ciclo_mensual(self.m, ciclo_num=0)      # [hoy-10, hoy+20)

    def pagar(self, cobro, monto):
        r = self.client.post(f'{URL_COBROS}{cobro.id}/registrar-pago/', {'monto': str(monto)}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)

    def transferir(self, turno, **extra):
        return self.client.post(f'{URL_INSC}{self.m.id}/transferir/',
                                {'sala': self.sala2.id, 'turno': turno.id, **extra}, format='json')

    # ── mismo precio ──
    def test_mismo_precio_el_ciclo_en_curso_continua_sin_duplicarse(self):
        self.pagar(self.ciclo, 650)
        r = self.transferir(self.t_igual)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.assertTrue(r.data['transferencia']['continua_ciclo'])
        self.assertEqual(r.data['transferencia']['ciclo']['motivo'], 'mismo_precio')

        self.ciclo.refresh_from_db()
        self.assertEqual(self.ciclo.inscripcion_id, nueva.id)                  # el mismo cobro, ahora en la nueva
        self.assertEqual(self.ciclo.estado, Cobro.ESTADO_PAGADO)
        self.assertEqual(Cobro.objects.filter(inscripcion=nueva).count(), 1)   # no se generó otro mes
        self.assertEqual(Cobro.objects.filter(inscripcion=self.m).count(), 0)
        self.assertEqual(Devolucion.objects.count(), 0)
        self.assertEqual(saldo_a_favor(nueva), dec(0))
        self.m.refresh_from_db()
        self.assertFalse(self.m.activa)

    def test_los_ciclos_siguientes_quedan_alineados_con_el_original(self):
        r = self.transferir(self.t_igual)
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(nueva.fecha_inicio, self.ciclo.periodo_inicio)        # ancla en el ciclo, no en hoy
        siguiente = generar_ciclo_mensual(nueva)
        self.assertEqual(siguiente.periodo_inicio, self.ciclo.periodo_fin)

    def test_precio_negociado_se_conserva_si_el_turno_cuesta_igual(self):
        self.m.costo_mensual = dec(600)               # precio negociado distinto del de lista (650)
        self.m.save()
        r = self.transferir(self.t_igual)             # mismo precio de lista que el turno actual
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(nueva.costo_mensual, dec(600))

    def test_si_el_turno_cuesta_distinto_rige_el_precio_del_turno_nuevo(self):
        r = self.transferir(self.t_caro)
        self.assertEqual(Inscripcion.objects.get(pk=r.data['id']).costo_mensual, dec(700))

    # ── cuesta más ──
    def test_turno_mas_caro_deja_por_cobrar_la_diferencia(self):
        self.pagar(self.ciclo, 650)
        r = self.transferir(self.t_caro)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(dec(r.data['transferencia']['ciclo']['por_cobrar']), dec(50))
        self.ciclo.refresh_from_db()
        self.assertEqual(self.ciclo.monto_final, dec(700))
        self.assertEqual(self.ciclo.estado, Cobro.ESTADO_PARCIAL)
        self.assertEqual(self.ciclo.saldo_pendiente, dec(50))
        self.pagar(self.ciclo, 50)
        self.ciclo.refresh_from_db()
        self.assertEqual(self.ciclo.estado, Cobro.ESTADO_PAGADO)

    # ── cuesta menos: lo que sobra va a su cuenta ──
    def test_turno_mas_barato_el_sobrante_pasa_a_la_cuenta_sin_tocar_la_caja(self):
        self.pagar(self.ciclo, 650)
        caja_antes = resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']
        r = self.transferir(self.t_barato)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(dec(r.data['transferencia']['ciclo']['a_favor']), dec(50))

        self.ciclo.refresh_from_db()
        self.assertEqual((self.ciclo.monto_final, self.ciclo.monto_pagado, self.ciclo.estado),
                         (dec(600), dec(600), Cobro.ESTADO_PAGADO))
        self.assertEqual(saldo_a_favor(nueva), dec(50))
        dev = Devolucion.objects.get()
        self.assertTrue(dev.a_cuenta)
        self.assertIsNone(dev.numero_recibo)
        # ni ingreso ni egreso nuevos en caja: el dinero ya había entrado con el pago original
        caja = resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']
        self.assertEqual(caja['ingresos'], caja_antes['ingresos'])
        self.assertEqual(caja['devoluciones'], dec(0))
        # y no aparecen como movimientos de caja
        mov = self.client.get(f'{URL_COBROS}movimientos/')
        self.assertEqual(mov.data['count'], 1)

    def test_el_sobrante_cubre_solo_la_siguiente_mensualidad(self):
        self.pagar(self.ciclo, 650)
        nueva = Inscripcion.objects.get(pk=self.transferir(self.t_barato).data['id'])
        siguiente = generar_ciclo_mensual(nueva)
        self.assertEqual(siguiente.monto_final, dec(600))
        self.assertEqual(siguiente.monto_pagado, dec(50))
        self.assertEqual(siguiente.saldo_pendiente, dec(550))
        self.assertEqual(saldo_a_favor(nueva), dec(0))

    # ── pagó menos: cerrar con lo pagado ──
    def test_pago_menor_se_puede_cerrar_el_ciclo_con_lo_pagado(self):
        self.pagar(self.ciclo, 300)
        r = self.transferir(self.t_caro, cerrar_con_lo_pagado=True, motivo_cierre='Se acordó con la directora')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.ciclo.refresh_from_db()
        self.assertEqual(self.ciclo.estado, Cobro.ESTADO_PAGADO)
        self.assertEqual(self.ciclo.monto_condonado, dec(400))                 # 700 - 300
        self.assertEqual(self.ciclo.motivo_condonacion, 'Se acordó con la directora')

    def test_cerrar_con_lo_pagado_tambien_a_igual_precio(self):
        self.pagar(self.ciclo, 300)
        r = self.transferir(self.t_igual, cerrar_con_lo_pagado=True, motivo_cierre='Ya no completa el mes')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.ciclo.refresh_from_db()
        self.assertEqual((self.ciclo.estado, self.ciclo.monto_condonado), (Cobro.ESTADO_PAGADO, dec(350)))

    def test_cerrar_con_lo_pagado_exige_motivo_y_no_cambia_nada_si_falta(self):
        self.pagar(self.ciclo, 300)
        r = self.transferir(self.t_caro, cerrar_con_lo_pagado=True)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.m.refresh_from_db()
        self.ciclo.refresh_from_db()
        self.assertTrue(self.m.activa)
        self.assertEqual(self.ciclo.inscripcion_id, self.m.id)
        self.assertEqual(Inscripcion.objects.filter(nino=self.ana).count(), 1)

    # ── simulación ──
    def test_simular_muestra_el_plan_sin_cambiar_nada(self):
        self.pagar(self.ciclo, 650)
        r = self.transferir(self.t_barato, simular=True)
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertTrue(r.data['simulacion'])
        self.assertTrue(r.data['continua_ciclo'])
        self.assertEqual(dec(r.data['ciclo']['a_favor']), dec(50))
        self.assertEqual(dec(r.data['costo_mensual_nuevo']), dec(600))
        self.m.refresh_from_db()
        self.ciclo.refresh_from_db()
        self.assertTrue(self.m.activa)
        self.assertEqual((self.ciclo.inscripcion_id, self.ciclo.monto_final), (self.m.id, dec(650)))
        self.assertEqual(Inscripcion.objects.filter(nino=self.ana).count(), 1)
        self.assertEqual(AbonoDiario.objects.count(), 0)
        self.assertEqual(Devolucion.objects.count(), 0)

    # ── casos borde ──
    def test_ciclos_anteriores_sin_pagar_quedan_en_la_inscripcion_cerrada_y_se_avisa(self):
        self.m.fecha_inicio = self.hoy - timedelta(days=40)
        self.m.save()
        Cobro.objects.filter(pk=self.ciclo.pk).delete()
        anterior = generar_ciclo_mensual(self.m, ciclo_num=0)                  # [hoy-40, hoy-10): sin pagar
        vigente  = generar_ciclo_mensual(self.m, ciclo_num=1)                  # [hoy-10, hoy+20)
        r = self.transferir(self.t_igual)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        anterior.refresh_from_db()
        vigente.refresh_from_db()
        self.assertEqual(anterior.inscripcion_id, self.m.id)
        self.assertEqual(str(vigente.inscripcion_id), r.data['id'])
        self.assertTrue(any('anteriores sin pagar' in a for a in r.data['advertencias']))

    def test_un_ciclo_ya_cerrado_con_lo_pagado_no_se_reajusta(self):
        self.pagar(self.ciclo, 300)
        self.client.post(f'{URL_COBROS}{self.ciclo.id}/cerrar-con-lo-pagado/', {'motivo': 'Acuerdo'}, format='json')
        r = self.transferir(self.t_caro)
        self.assertEqual(r.data['transferencia']['ciclo']['motivo'], 'cerrado_con_lo_pagado')
        self.ciclo.refresh_from_db()
        self.assertEqual((self.ciclo.monto_final, self.ciclo.estado), (dec(650), Cobro.ESTADO_PAGADO))

    def test_sin_ciclo_en_curso_se_genera_uno_nuevo_como_siempre(self):
        Cobro.objects.filter(pk=self.ciclo.pk).delete()
        r = self.transferir(self.t_igual)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertNotIn('transferencia', r.data)
        self.assertEqual(Cobro.objects.filter(inscripcion_id=r.data['id'], tipo=Cobro.TIPO_MENSUALIDAD).count(), 1)

    def test_el_saldo_a_favor_previo_acompana_al_niño(self):
        self.pagar(self.ciclo, 650)                     # nada abierto: el saldo queda disponible
        AbonoDiario.objects.create(inscripcion=self.m, monto=dec(50), es_traspaso=True)
        r = self.transferir(self.t_igual)
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(saldo_a_favor(nueva), dec(50))
        self.assertEqual(saldo_a_favor(self.m), dec(0))

    def test_el_saldo_previo_cubre_lo_que_haya_quedado_abierto_al_transferir(self):
        AbonoDiario.objects.create(inscripcion=self.m, monto=dec(50), es_traspaso=True)
        r = self.transferir(self.t_igual)               # el ciclo en curso seguía sin pagar
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.ciclo.refresh_from_db()
        self.assertEqual(self.ciclo.monto_pagado, dec(50))
        self.assertEqual(saldo_a_favor(nueva), dec(0))

    def test_fecha_de_transferencia_invalida_se_rechaza(self):
        self.assertEqual(self.transferir(self.t_igual, fecha_transferencia='01/10/2026').status_code, 400)
        self.m.refresh_from_db()
        self.assertTrue(self.m.activa)


# ═══════════════════════════════════════════════════════════════════
class CerrarInscripcionTests(PorDiaBase):
    """Baja del niño y regreso posterior con una inscripción nueva."""

    def setUp(self):
        super().setUp()
        self.ana = self._otro_nino('Ana', 'Choque')
        self.m = self._inscribir(self.ana, modalidad=Inscripcion.MODALIDAD_MENSUAL, fecha_inicio=self.hoy - timedelta(days=10))
        self.ciclo = generar_ciclo_mensual(self.m, ciclo_num=0)
        self.url = f'{URL_INSC}{self.m.id}/cerrar/'

    def pagar(self, cobro, monto):
        self.client.post(f'{URL_COBROS}{cobro.id}/registrar-pago/', {'monto': str(monto)}, format='json')

    def test_baja_cierra_la_inscripcion_y_deja_el_ciclo_como_estaba(self):
        self.pagar(self.ciclo, 300)
        r = self.client.post(self.url, {'motivo': 'Se mudaron'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.m.refresh_from_db()
        self.assertFalse(self.m.activa)
        self.assertEqual(self.m.fecha_fin, self.hoy)
        self.assertIn('Se mudaron', self.m.motivo_ajuste)
        self.ciclo.refresh_from_db()
        self.assertEqual(self.ciclo.estado, Cobro.ESTADO_PARCIAL)              # no se tocó
        self.assertEqual(dec(r.data['deuda_pendiente']), dec(350))
        self.assertTrue(any('sin pagar' in a for a in r.data['advertencias']))

    def test_cerrar_con_lo_pagado_en_la_baja(self):
        self.pagar(self.ciclo, 300)
        r = self.client.post(self.url, {'cerrar_con_lo_pagado': True, 'motivo_cierre': 'Ya no viene'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(dec(r.data['monto_condonado']), dec(350))
        self.assertEqual(dec(r.data['deuda_pendiente']), dec(0))
        self.ciclo.refresh_from_db()
        self.assertEqual(self.ciclo.estado, Cobro.ESTADO_PAGADO)

    def test_cerrar_con_lo_pagado_exige_motivo(self):
        r = self.client.post(self.url, {'cerrar_con_lo_pagado': True}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.m.refresh_from_db()
        self.assertTrue(self.m.activa)

    def test_ciclos_futuros_sin_pagos_se_anulan_y_con_pagos_solo_se_avisa(self):
        futuro_libre = generar_ciclo_mensual(self.m, ciclo_num=1)
        futuro_pagado = generar_ciclo_mensual(self.m, ciclo_num=2)
        Pago.objects.create(cobro=futuro_pagado, monto='100.00', registrado_por=self.staff)   # alguien pagó por adelantado
        futuro_pagado.recalcular_estado()
        r = self.client.post(self.url, {'fecha_fin': self.hoy.isoformat()}, format='json')
        self.assertEqual(r.data['ciclos_anulados'], 1)
        futuro_libre.refresh_from_db()
        futuro_pagado.refresh_from_db()
        self.assertEqual(futuro_libre.estado, Cobro.ESTADO_ANULADO)
        self.assertEqual(futuro_pagado.estado, Cobro.ESTADO_PARCIAL)
        self.assertTrue(any('ya tiene pagos' in a for a in r.data['advertencias']))

    def test_validaciones(self):
        self.assertEqual(self.client.post(self.url, {'fecha_fin': 'ayer'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(
            self.url, {'fecha_fin': (self.m.fecha_inicio - timedelta(days=1)).isoformat()}, format='json').status_code, 400)
        self.client.force_authenticate(self.usuario_tutor)
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 200)
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 400)    # ya cerrada

    def test_baja_de_inscripcion_por_dia_informa_deuda_y_saldo(self):
        self.marcar(self.insc, self.dia(2), 'presente')
        self.abonar(self.insc, 100)                      # cubre el día (40): quedan 60 a favor
        self.marcar(self.insc, self.dia(1), 'presente')  # cubierto también: quedan 20
        self.marcar(self.insc, self.hoy, 'presente')     # cubierto 20, debe 20
        r = self.client.post(f'{URL_INSC}{self.insc.id}/cerrar/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(dec(r.data['deuda_pendiente']), dec(20))
        self.assertEqual(dec(r.data['saldo_a_favor']), dec(0))

    def test_si_regresa_se_crea_una_inscripcion_nueva_y_su_saldo_la_acompana(self):
        self.abonar(self.insc, 100)                       # saldo a favor en una inscripción por día
        self.client.post(f'{URL_INSC}{self.insc.id}/cerrar/', {}, format='json')
        self.assertEqual(saldo_a_favor(self.insc), dec(100))
        r = self.client.post(URL_INSC, {
            'nino': str(self.nino.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
            'modalidad_pago': 'mensual', 'fecha_inicio': self.hoy.isoformat(),
            'costo_mensual': '650.00', 'costo_diario': '40.00',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)                 # ya no hay otra activa
        nueva = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(saldo_a_favor(self.insc), dec(0))
        primer = Cobro.objects.get(inscripcion=nueva, tipo=Cobro.TIPO_MENSUALIDAD)
        self.assertEqual(primer.monto_pagado, dec(100))                                  # el saldo cubrió parte del primer mes
        self.assertEqual(Inscripcion.objects.filter(nino=self.nino, activa=True).count(), 1)

    def test_no_se_puede_inscribir_de_nuevo_mientras_siga_activa(self):
        r = self.client.post(URL_INSC, {
            'nino': str(self.ana.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
            'modalidad_pago': 'mensual', 'fecha_inicio': self.hoy.isoformat(),
            'costo_mensual': '650.00', 'costo_diario': '40.00',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ═══════════════════════════════════════════════════════════════════
class DevolverSaldoTests(PorDiaBase):
    """Devolución en efectivo del saldo a favor: la misma Devolucion, colgada de la inscripción."""

    def url(self, insc=None):
        return f'{URL_INSC}{(insc or self.insc).id}/devolver-saldo/'

    def devolver(self, monto, insc=None, **extra):
        return self.client.post(self.url(insc), {'monto': str(monto), 'motivo': 'La familia lo pidió', **extra}, format='json')

    def test_devolver_parte_descuenta_el_saldo_y_genera_recibo(self):
        self.abonar(self.insc, 100)
        r = self.devolver(60)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(dec(r.data['saldo_a_favor']), dec(40))
        dev = Devolucion.objects.get()
        self.assertIsNone(dev.cobro_id)
        self.assertEqual(dev.inscripcion_id, self.insc.id)
        self.assertFalse(dev.a_cuenta)
        self.assertIsNotNone(dev.numero_recibo)
        self.assertEqual(AbonoDiario.objects.get().devuelto, dec(60))
        self.assertEqual(saldo_a_favor(self.insc), dec(40))

    def test_devolver_todo_deja_la_cuenta_en_cero(self):
        self.abonar(self.insc, 100)
        self.assertEqual(self.devolver(100).status_code, status.HTTP_201_CREATED)
        self.assertEqual(saldo_a_favor(self.insc), dec(0))
        self.assertEqual(self.devolver(1).status_code, status.HTTP_400_BAD_REQUEST)         # ya no hay nada

    def test_el_dinero_devuelto_no_se_aplica_despues_a_ningun_cobro(self):
        self.abonar(self.insc, 100)
        self.devolver(60)                                          # quedan 40: alcanza para un solo día
        self.marcar(self.insc, self.dia(1), 'presente')
        self.marcar(self.insc, self.hoy, 'presente')
        self.assertEqual(self.cobro_de(self.insc, self.dia(1)).estado, Cobro.ESTADO_PAGADO)
        self.assertIn(self.cobro_de(self.insc, self.hoy).estado, (Cobro.ESTADO_PENDIENTE, Cobro.ESTADO_VENCIDO))
        self.assertEqual(saldo_a_favor(self.insc), dec(0))

    def test_validaciones_y_permisos(self):
        self.abonar(self.insc, 100)
        for malo in ({'monto': '101'}, {'monto': '0'}, {'monto': '-5'}, {'monto': 'abc'}, {},
                     {'monto': '10', 'metodo_pago': 'bitcoin'}, {'monto': '10', 'fecha': '31-12-2026'}):
            r = self.client.post(self.url(), {'motivo': 'x', **malo}, format='json')
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, malo)
        self.assertEqual(self.client.post(self.url(), {'monto': '10'}, format='json').status_code, 400)   # sin motivo
        self.client.force_authenticate(self.usuario_tutor)
        self.assertEqual(self.devolver(10).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Devolucion.objects.count(), 0)
        self.assertEqual(saldo_a_favor(self.insc), dec(100))

    def test_en_caja_es_un_egreso_real(self):
        self.abonar(self.insc, 100)
        self.devolver(60)
        caja = resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']
        self.assertEqual((caja['ingresos'], caja['devoluciones'], caja['neto']), (dec(100), dec(60), dec(40)))
        # filtrando por la sucursal de la inscripción también cuenta
        caja_suc = resumen_financiero(self.hoy.year, self.hoy.month, sucursal=self.sucursal.id)['caja_mes']
        self.assertEqual(caja_suc['devoluciones'], dec(60))

    def test_aparece_en_movimientos_como_devolucion_con_su_recibo(self):
        self.abonar(self.insc, 100)
        self.devolver(60)
        r = self.client.get(f'{URL_COBROS}movimientos/')
        self.assertEqual(r.data['count'], 2)                                    # el abono y la devolución
        fila = next(f for f in r.data['results'] if f['tipo'] == 'devolucion')
        self.assertEqual(fila['concepto'], 'Devolución del saldo a favor')
        self.assertEqual(fila['nino_nombre'], self.nino.nombre_completo)
        self.assertIsNotNone(fila['numero_recibo'])
        self.assertEqual(dec(r.data['totales']['devoluciones']), dec(60))
        self.assertEqual(dec(r.data['totales']['neto']), dec(40))
        self.assertEqual(self.client.get(f'{URL_COBROS}movimientos/?tipo=pago').data['count'], 1)
        self.assertEqual(self.client.get(f'{URL_COBROS}movimientos/?tipo=devolucion').data['count'], 1)
        self.assertEqual(self.client.get(f'{URL_COBROS}movimientos/?search=Valentina&tipo=devolucion').data['count'], 1)
        self.assertEqual(self.client.get(f'{URL_COBROS}movimientos/?sucursal={self.sucursal.id}&tipo=devolucion').data['count'], 1)

    def test_recibo_pdf_de_la_devolucion_del_saldo(self):
        self.abonar(self.insc, 100)
        dev_id = self.devolver(60).data['devolucion']['id']
        r = self.client.get(f'/api/inscripciones/recibos/devolucion/{dev_id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_funciona_en_una_inscripcion_ya_cerrada(self):
        self.abonar(self.insc, 100)
        self.client.post(f'{URL_INSC}{self.insc.id}/cerrar/', {}, format='json')
        self.assertEqual(self.devolver(100).status_code, status.HTTP_201_CREATED)
        self.assertEqual(saldo_a_favor(self.insc), dec(0))

    def test_baja_con_devolucion_del_saldo_en_el_mismo_paso(self):
        self.abonar(self.insc, 100)
        r = self.client.post(f'{URL_INSC}{self.insc.id}/cerrar/',
                             {'devolver_saldo': True, 'metodo_pago': 'transferencia'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(dec(r.data['saldo_a_favor']), dec(0))
        self.assertEqual(dec(r.data['devolucion']['monto']), dec(100))
        self.assertEqual(r.data['devolucion']['metodo_pago'], 'transferencia')
        self.assertFalse(any('saldo a favor' in a for a in r.data['advertencias']))
        self.assertEqual(Devolucion.objects.count(), 1)

    def test_baja_sin_pedir_la_devolucion_deja_el_saldo_y_avisa(self):
        self.abonar(self.insc, 100)
        r = self.client.post(f'{URL_INSC}{self.insc.id}/cerrar/', {}, format='json')
        self.assertEqual(dec(r.data['saldo_a_favor']), dec(100))
        self.assertIsNone(r.data['devolucion'])
        self.assertTrue(any('Devolver saldo' in a for a in r.data['advertencias']))

    def test_si_vuelve_solo_pasa_a_la_inscripcion_nueva_lo_que_no_se_devolvio(self):
        self.abonar(self.insc, 100)
        self.devolver(60)
        self.client.post(f'{URL_INSC}{self.insc.id}/cerrar/', {}, format='json')
        r = self.client.post(URL_INSC, {
            'nino': str(self.nino.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
            'modalidad_pago': 'diaria', 'fecha_inicio': self.hoy.isoformat(),
            'costo_mensual': '650.00', 'costo_diario': '40.00',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(saldo_a_favor(Inscripcion.objects.get(pk=r.data['id'])), dec(40))

    def test_sobrante_de_un_cambio_de_turno_en_mensualidad_tambien_se_puede_devolver(self):
        sala2 = Sala.objects.create(sucursal=self.sucursal, nombre='Sala Gateo', edad_min_meses=12,
                                    edad_max_meses=36, capacidad_maxima=10)
        barato = Turno.objects.create(sala=sala2, nombre='Barata', tipo=Turno.TIPO_TARDE, hora_inicio='14:00',
                                      hora_fin='18:00', costo_mensual='600.00', costo_diario='40.00')
        m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL,
                            fecha_inicio=self.hoy - timedelta(days=10))
        ciclo = generar_ciclo_mensual(m, ciclo_num=0)
        self.client.post(f'{URL_COBROS}{ciclo.id}/registrar-pago/', {'monto': '650'}, format='json')
        nueva = Inscripcion.objects.get(pk=self.client.post(
            f'{URL_INSC}{m.id}/transferir/', {'sala': sala2.id, 'turno': barato.id}, format='json').data['id'])
        self.assertEqual(saldo_a_favor(nueva), dec(50))
        r = self.devolver(50, insc=nueva)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        caja = resumen_financiero(self.hoy.year, self.hoy.month)['caja_mes']
        # entró 650 (el pago real) y salió 50 en efectivo; el traspaso interno no cuenta en ningún sentido
        self.assertEqual((caja['ingresos'], caja['devoluciones'], caja['neto']), (dec(650), dec(50), dec(600)))

    def test_resumen_diario_muestra_lo_devuelto_por_abono(self):
        self.abonar(self.insc, 100)
        self.devolver(30)
        a = resumen_diario(self.insc)['abonos'][0]
        self.assertEqual((a['devuelto'], a['disponible']), (dec(30), dec(70)))

    def test_la_devolucion_de_un_pago_a_un_cobro_sigue_funcionando(self):
        self.marcar(self.insc, self.hoy, 'presente')
        cobro = self.cobro_de(self.insc, self.hoy)
        self.client.post(f'{URL_COBROS}{cobro.id}/registrar-pago/', {'monto': '40'}, format='json')
        r = self.client.post(f'{URL_COBROS}{cobro.id}/registrar-devolucion/',
                             {'monto': '10', 'motivo': 'Error de cobro'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        dev = Devolucion.objects.get()
        self.assertEqual((dev.cobro_id, dev.inscripcion_id), (cobro.id, None))

    def test_una_devolucion_no_puede_quedar_sin_cobro_ni_inscripcion(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Devolucion.objects.create(monto=dec(5), motivo='x')


# ═══════════════════════════════════════════════════════════════════
class CalendarioDeDiasTests(PorDiaBase):
    """Pago por día: los días se eligen en un calendario (fechas exactas)."""

    def d(self, n):
        """Un día futuro: hoy + n."""
        return self.hoy + timedelta(days=n)

    def iso(self, *fechas):
        return [f.isoformat() for f in fechas]

    def crear(self, dias, **extra):
        otro = self._otro_nino('Luz', 'Mamani')
        body = {
            'nino': str(otro.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
            'modalidad_pago': 'diaria', 'costo_mensual': '650.00', 'costo_diario': '40.00',
            'dias_programados': dias, **extra,
        }
        return self.client.post(URL_INSC, body, format='json')

    def planilla_ids(self, fecha):
        r = self.client.get(f'{URL_ASIST}planilla/?fecha={fecha.isoformat()}&sala={self.sala.id}')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        return [n['inscripcion'] for n in r.data['ninos']]

    # ── crear ──
    def test_crear_ordena_deduplica_y_toma_el_primer_dia_como_inicio(self):
        r = self.crear(self.iso(self.d(5), self.d(2), self.d(2), self.d(9)))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['dias_programados'], self.iso(self.d(2), self.d(5), self.d(9)))
        self.assertEqual(r.data['fecha_inicio'], self.d(2).isoformat())      # no hizo falta mandarlo
        self.assertEqual(r.data['dias_semana_display'], '3 días elegidos')
        self.assertEqual(Cobro.objects.filter(inscripcion_id=r.data['id']).count(), 0)

    def test_crear_anota_los_dias_acordados_desde_el_calendario(self):
        r = self.crear(self.iso(self.d(1), self.d(2), self.d(3)))
        insc = Inscripcion.objects.get(pk=r.data['id'])
        self.assertEqual(resumen_diario(insc)['dias_contratados']['total'], 3)
        self.assertEqual(insc.dias_contratados.get().tipo, DiasContratados.TIPO_INICIAL)

    def test_fechas_invalidas_se_rechazan(self):
        for malo in (['2026-13-40'], ['hola'], 'lunes', [5]):
            r = self.crear(malo)
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, malo)

    def test_diaria_sin_calendario_ni_fecha_inicio_se_rechaza(self):
        r = self.crear([])
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('fecha_inicio', r.data)

    def test_inscripcion_antigua_sin_calendario_sigue_funcionando(self):
        r = self.crear([], fecha_inicio=self.hoy.isoformat(), dias_semana=[0, 2])
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['dias_programados'], [])
        self.assertEqual(r.data['dias_semana_display'], 'Lun, Mié')

    def test_mensual_ignora_el_calendario(self):
        r = self.crear(self.iso(self.d(1)), modalidad_pago='mensual', fecha_inicio=self.hoy.isoformat())
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['dias_programados'], [])

    def test_editar_la_inscripcion_no_cambia_el_calendario(self):
        r = self.crear(self.iso(self.d(1), self.d(2)))
        r2 = self.client.patch(f'{URL_INSC}{r.data["id"]}/', {'dias_programados': self.iso(self.d(8))}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_200_OK, r2.data)
        self.assertEqual(r2.data['dias_programados'], self.iso(self.d(1), self.d(2)))

    # ── planilla y cobro ──
    def test_solo_aparece_en_la_planilla_los_dias_elegidos(self):
        r = self.crear(self.iso(self.hoy, self.d(3)))
        nuevo = r.data['id']
        self.assertIn(nuevo, [str(i) for i in self.planilla_ids(self.hoy)])
        self.assertNotIn(nuevo, [str(i) for i in self.planilla_ids(self.d(1))])
        self.assertIn(nuevo, [str(i) for i in self.planilla_ids(self.d(3))])

    def test_falta_sin_aviso_solo_cobra_en_dia_elegido(self):
        r = self.crear(self.iso(self.hoy))
        insc = Inscripcion.objects.get(pk=r.data['id'])
        self.marcar(insc, self.hoy, 'ausente')
        self.assertIsNotNone(self.cobro_de(insc, self.hoy))
        fuera = self.hoy - timedelta(days=1)
        insc.fecha_inicio = fuera
        insc.save()
        self.marcar(insc, fuera, 'ausente')              # un día que NO eligió
        self.assertIsNone(self.cobro_de(insc, fuera))

    def test_presente_en_dia_no_elegido_si_cobra(self):
        r = self.crear(self.iso(self.d(4)))
        insc = Inscripcion.objects.get(pk=r.data['id'])
        insc.fecha_inicio = self.hoy
        insc.save()
        self.marcar(insc, self.hoy, 'presente')
        self.assertIsNotNone(self.cobro_de(insc, self.hoy))

    def test_calendario_respeta_fecha_fin_al_cerrar(self):
        r = self.crear(self.iso(self.d(1), self.d(6)))
        insc = Inscripcion.objects.get(pk=r.data['id'])
        insc.fecha_fin = self.d(3)
        self.assertTrue(insc.es_dia_esperado(self.d(1)))
        self.assertFalse(insc.es_dia_esperado(self.d(6)))

    # ── aumentar / disminuir ──
    def url_dias(self, insc):
        return f'{URL_INSC}{insc.id}/actualizar-dias/'

    def nuevo(self, *dias):
        r = self.crear(self.iso(*dias))
        return Inscripcion.objects.get(pk=r.data['id'])

    def test_aumentar_dias_registra_ampliacion(self):
        insc = self.nuevo(self.d(1), self.d(2))
        r = self.client.post(self.url_dias(insc), {
            'dias': self.iso(self.d(1), self.d(2), self.d(5), self.d(6), self.d(7))}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['agregadas'], self.iso(self.d(5), self.d(6), self.d(7)))
        self.assertEqual(r.data['quitadas'], [])
        hist = r.data['resumen']['dias_contratados']
        self.assertEqual(hist['total'], 5)
        self.assertEqual([(h['tipo'], h['cantidad']) for h in hist['historial']],
                         [('inicial', 2), ('ampliacion', 3)])

    def test_disminuir_dias_registra_reduccion(self):
        insc = self.nuevo(self.d(1), self.d(2), self.d(3), self.d(4))
        r = self.client.post(self.url_dias(insc), {'dias': self.iso(self.d(1), self.d(2))}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['quitadas'], self.iso(self.d(3), self.d(4)))
        hist = r.data['resumen']['dias_contratados']
        self.assertEqual(hist['total'], 2)
        self.assertEqual(hist['historial'][-1]['tipo'], 'reduccion')
        self.assertEqual(hist['historial'][-1]['cantidad'], 2)

    def test_cambio_mixto_registra_solo_la_diferencia(self):
        insc = self.nuevo(self.d(1), self.d(2), self.d(3))
        # quita 1 y agrega 3 → +2 netos
        r = self.client.post(self.url_dias(insc), {
            'dias': self.iso(self.d(2), self.d(3), self.d(8), self.d(9), self.d(10))}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['resumen']['dias_contratados']['total'], 5)
        insc.refresh_from_db()
        self.assertEqual(insc.fecha_inicio, self.d(2))                 # el primer día se recalcula

    def test_sin_cambios_no_ensucia_el_historial(self):
        insc = self.nuevo(self.d(1), self.d(2))
        r = self.client.post(self.url_dias(insc), {'dias': self.iso(self.d(2), self.d(1))}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(insc.dias_contratados.count(), 1)

    def test_no_se_puede_quitar_un_dia_con_asistencia_o_cobro(self):
        insc = self.nuevo(self.hoy, self.d(2))
        self.marcar(insc, self.hoy, 'presente')
        r = self.client.post(self.url_dias(insc), {'dias': self.iso(self.d(2))}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('asistencia o cobro', r.data['error'])
        insc.refresh_from_db()
        self.assertEqual(insc.dias_programados, self.iso(self.hoy, self.d(2)))

    def test_el_resumen_marca_los_dias_bloqueados(self):
        insc = self.nuevo(self.hoy, self.d(2))
        self.marcar(insc, self.hoy, 'presente')
        res = resumen_diario(insc)
        self.assertEqual(res['dias_programados'], self.iso(self.hoy, self.d(2)))
        self.assertEqual(res['dias_bloqueados'], self.iso(self.hoy))

    def test_calendario_vacio_se_rechaza(self):
        insc = self.nuevo(self.d(1))
        r = self.client.post(self.url_dias(insc), {'dias': []}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fecha_invalida_en_actualizar_dias(self):
        insc = self.nuevo(self.d(1))
        r = self.client.post(self.url_dias(insc), {'dias': ['mañana']}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mensual_no_tiene_calendario(self):
        m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        r = self.client.post(self.url_dias(m), {'dias': self.iso(self.d(1))}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inscripcion_antigua_concilia_con_lo_ya_acordado(self):
        # Tenía 5 días acordados (a mano) y sin calendario; al elegir 7 fechas, +2.
        self.client.post(f'{URL_INSC}{self.insc.id}/contratar-dias/', {'cantidad': 5, 'tipo': 'inicial'}, format='json')
        r = self.client.post(self.url_dias(self.insc), {
            'dias': self.iso(*[self.d(i) for i in range(1, 8)])}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['resumen']['dias_contratados']['total'], 7)

    # ── transferir / cambiar modalidad ──
    def test_transferir_conserva_las_fechas_que_quedan_por_delante(self):
        insc = self.nuevo(self.hoy - timedelta(days=0), self.d(3), self.d(4))
        sala2 = Sala.objects.create(sucursal=self.sucursal, nombre='Sala 2',
                                    edad_min_meses=0, edad_max_meses=36, capacidad_maxima=10)
        turno2 = Turno.objects.create(sala=sala2, nombre='Tarde', tipo=Turno.TIPO_TARDE,
                                      hora_inicio='14:00', hora_fin='18:00',
                                      costo_mensual='650.00', costo_diario='40.00')
        r = self.client.post(f'{URL_INSC}{insc.id}/transferir/', {
            'sucursal': self.sucursal.id, 'sala': sala2.id, 'turno': turno2.id,
            'fecha_transferencia': self.d(2).isoformat()}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['dias_programados'], self.iso(self.d(3), self.d(4)))

    def test_cambiar_de_mensual_a_diaria_con_calendario(self):
        m = self._inscribir(self._otro_nino('Ana', 'Choque'), modalidad=Inscripcion.MODALIDAD_MENSUAL,
                            fecha_inicio=self.hoy - timedelta(days=3))
        r = self.client.post(f'{URL_INSC}{m.id}/cambiar-modalidad/', {
            'dias_programados': self.iso(self.d(2), self.d(1), self.d(5))}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(pk=r.data['inscripcion']['id'])
        self.assertEqual(nueva.dias_programados, self.iso(self.d(1), self.d(2), self.d(5)))
        self.assertEqual(nueva.fecha_inicio, self.d(1))
        self.assertEqual(resumen_diario(nueva)['dias_contratados']['total'], 3)


# ═══════════════════════════════════════════════════════════════════
# Estado de pago (política: se paga por adelantado) y días acordados
# ═══════════════════════════════════════════════════════════════════
class EstadoDePagoTests(PorDiaBase):
    """El estado de cuenta debe decir cuánto es, cuánto se pagó y cuánto falta,
    y los días acordados deben seguir al calendario (no a abonos anteriores)."""

    def d(self, n):
        return self.hoy + timedelta(days=n)

    def iso(self, *fechas):
        return [f.isoformat() for f in fechas]

    def diaria_con_calendario(self, n_dias=5):
        insc = self._inscribir(self._otro_nino('Franquito', 'Castro'),
                               dias_programados=self.iso(*[self.d(i) for i in range(n_dias)]))
        DiasContratados.objects.create(inscripcion=insc, tipo='inicial', cantidad=n_dias)
        return insc

    def cuenta(self, insc):
        return self.client.get(f'{URL_INSC}{insc.id}/calendario-pagos/').data['resumen']['cuenta']

    def test_diaria_sin_pagar_es_deuda_por_adelantado(self):
        insc = self.diaria_con_calendario(5)
        c = self.cuenta(insc)
        self.assertEqual(c['nivel'], 'deuda')
        self.assertEqual(c['dias_acordados'], 5)
        self.assertEqual(c['monto_acordado'], dec('200.00'))
        self.assertEqual(c['pagado_total'], dec('0'))
        self.assertEqual(c['falta_pagar'], dec('200.00'))
        self.assertEqual(c['dias_sin_pagar'], 5)

    def test_diaria_pagada_por_adelantado_esta_al_dia(self):
        insc = self.diaria_con_calendario(5)
        self.abonar(insc, 200)
        c = self.cuenta(insc)
        self.assertEqual(c['nivel'], 'al_dia')
        self.assertEqual(c['falta_pagar'], dec('0'))
        self.assertEqual(c['dias_pagados'], 5)

    def test_pago_parcial_muestra_cuanto_falta(self):
        insc = self.diaria_con_calendario(5)
        self.abonar(insc, 120)
        c = self.cuenta(insc)
        self.assertEqual(c['nivel'], 'deuda')
        self.assertEqual(c['falta_pagar'], dec('80.00'))
        self.assertEqual(c['dias_pagados'], 3)
        self.assertEqual(c['dias_sin_pagar'], 2)

    def test_el_pago_sigue_contando_cuando_el_dia_ya_se_cobro_por_asistencia(self):
        # El monto pagado no cambia al consumirse el saldo: sigue al día.
        insc = self.diaria_con_calendario(5)
        self.abonar(insc, 200)
        self.marcar(insc, self.d(0), 'presente')
        c = self.cuenta(insc)
        self.assertEqual(c['nivel'], 'al_dia')
        self.assertEqual(c['pagado_total'], dec('200.00'))
        self.assertEqual(c['dias_cobrados'], 1)
        self.assertEqual(c['saldo_a_favor'], dec('160.00'))

    def test_pagar_de_mas_se_informa_como_saldo(self):
        insc = self.diaria_con_calendario(2)
        self.abonar(insc, 200)
        c = self.cuenta(insc)
        self.assertEqual(c['nivel'], 'al_dia')
        self.assertEqual(c['pagado_de_mas'], dec('120.00'))

    def test_devolver_saldo_reabre_la_deuda(self):
        insc = self.diaria_con_calendario(5)
        self.abonar(insc, 200)
        self.client.post(f'{URL_INSC}{insc.id}/devolver-saldo/', {
            'monto': '80', 'metodo_pago': 'efectivo', 'motivo': 'Pidió devolución'}, format='json')
        c = self.cuenta(insc)
        self.assertEqual(c['nivel'], 'deuda')
        self.assertEqual(c['falta_pagar'], dec('80.00'))

    # ── días acordados vs calendario (el bug del "2 de 9") ──
    def test_abono_con_dias_no_se_suma_a_los_acordados_del_calendario(self):
        insc = self.diaria_con_calendario(5)
        self.abonar(insc, 200, dias=4)       # antes sumaba 4 y el contador quedaba en 9
        r = self.client.get(f'{URL_INSC}{insc.id}/calendario-pagos/')
        self.assertEqual(r.data['resumen']['dias_contratados']['total'], 5)

    def test_cambiar_el_calendario_actualiza_los_dias_acordados(self):
        insc = self.diaria_con_calendario(5)
        r = self.client.post(f'{URL_INSC}{insc.id}/actualizar-dias/', {
            'dias': self.iso(*[self.d(i) for i in range(8)])}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['resumen']['dias_contratados']['total'], 8)
        self.assertEqual(r.data['resumen']['cuenta']['monto_acordado'], dec('320.00'))
        r = self.client.post(f'{URL_INSC}{insc.id}/actualizar-dias/', {
            'dias': self.iso(*[self.d(i) for i in range(3)])}, format='json')
        self.assertEqual(r.data['resumen']['dias_contratados']['total'], 3)
        self.assertEqual(r.data['resumen']['cuenta']['monto_acordado'], dec('120.00'))

    # ── lista de inscripciones ──
    def test_la_lista_trae_el_estado_de_pago(self):
        deudor = self.diaria_con_calendario(5)
        pagado = self._inscribir(self._otro_nino('Ana', 'Choque'),
                                 dias_programados=self.iso(self.d(1), self.d(2)))
        self.abonar(pagado, 80)
        r = self.client.get(URL_INSC + '?page_size=100&activa=true')
        filas = {f['id']: f for f in (r.data.get('results') or r.data)}
        self.assertEqual(filas[str(deudor.id)]['estado_pago']['nivel'], 'deuda')
        self.assertEqual(filas[str(pagado.id)]['estado_pago']['nivel'], 'al_dia')

    def test_mensualidad_sin_pagar_es_deuda_y_pagada_esta_al_dia(self):
        m = self._inscribir(self._otro_nino('Luz', 'Mamani'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        cobro = generar_ciclo_mensual(m, ciclo_num=0)
        lista = {f['id']: f for f in (self.client.get(URL_INSC + '?page_size=100').data.get('results'))}
        e = lista[str(m.id)]['estado_pago']
        self.assertEqual(e['nivel'], 'deuda')
        self.assertEqual(e['falta_pagar'], dec('650.00'))
        Pago.objects.create(cobro=cobro, monto='650.00')
        cobro.recalcular_estado()
        lista = {f['id']: f for f in (self.client.get(URL_INSC + '?page_size=100').data.get('results'))}
        e = lista[str(m.id)]['estado_pago']
        self.assertEqual(e['nivel'], 'al_dia')
        self.assertEqual(e['pagado_total'], dec('650.00'))

    def test_inscripcion_inactiva_no_muestra_estado(self):
        insc = self.diaria_con_calendario(2)
        insc.activa = False
        insc.save()
        r = self.client.get(URL_INSC + '?page_size=100&activa=false')
        fila = [f for f in (r.data.get('results') or r.data) if f['id'] == str(insc.id)][0]
        self.assertIsNone(fila['estado_pago'])


class FiltroEstadoPagoTests(PorDiaBase):
    """?estado_pago= en la lista: al_dia, deuda, sin_registro (solo inscripciones activas)."""

    def d(self, n):
        return self.hoy + timedelta(days=n)

    def setUp(self):
        super().setUp()
        iso = lambda *ns: [self.d(n).isoformat() for n in ns]
        self.deudor = self._inscribir(self._otro_nino('Ana', 'Deuda'), dias_programados=iso(1, 2))
        self.al_dia = self._inscribir(self._otro_nino('Beto', 'Pagado'), dias_programados=iso(1, 2))
        self.abonar(self.al_dia, 80)
        self.baja = self._inscribir(self._otro_nino('Caro', 'Baja'), dias_programados=iso(1, 2))
        self.baja.activa = False
        self.baja.save()

    def ids(self, query):
        r = self.client.get(URL_INSC + '?page_size=100' + query)
        self.assertEqual(r.status_code, status.HTTP_200_OK, getattr(r, 'data', None))
        filas = r.data['results'] if isinstance(r.data, dict) else r.data
        return {f['id'] for f in filas}

    def test_filtra_con_deuda(self):
        ids = self.ids('&estado_pago=deuda')
        self.assertIn(str(self.deudor.id), ids)
        self.assertNotIn(str(self.al_dia.id), ids)
        self.assertNotIn(str(self.baja.id), ids)

    def test_filtra_al_dia(self):
        self.assertEqual(self.ids('&estado_pago=al_dia'), {str(self.al_dia.id)})

    def test_filtra_sin_registro(self):
        sin = self._inscribir(self._otro_nino('Dani', 'Nuevo'))   # por día, sin calendario ni días acordados
        ids = self.ids('&estado_pago=sin_registro')
        self.assertIn(str(sin.id), ids)
        self.assertNotIn(str(self.deudor.id), ids)
        self.assertNotIn(str(self.al_dia.id), ids)

    def test_las_dadas_de_baja_no_entran_en_ningun_estado_de_pago(self):
        for v in ('deuda', 'al_dia', 'sin_registro'):
            self.assertNotIn(str(self.baja.id), self.ids(f'&estado_pago={v}'))

    def test_combina_con_otros_filtros(self):
        self.assertEqual(self.ids('&estado_pago=deuda&modalidad_pago=mensual'), set())
        self.assertIn(str(self.deudor.id), self.ids('&estado_pago=deuda&modalidad_pago=diaria'))

    def test_valor_invalido_da_error(self):
        r = self.client.get(URL_INSC + '?estado_pago=cualquiera')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sin_filtro_trae_todas(self):
        ids = self.ids('')
        self.assertTrue({str(self.deudor.id), str(self.al_dia.id)} <= ids)


class DiasAFavorTests(PorDiaBase):
    """Días pagados que no se usan (p. ej. una falta avisada) deben alertar al personal."""

    def d(self, n):
        return self.hoy + timedelta(days=n)

    def setUp(self):
        super().setUp()
        self.insc5 = self._inscribir(
            self._otro_nino('Franquito', 'Castro'),
            dias_programados=[self.d(i).isoformat() for i in range(1, 6)])
        self.abonar(self.insc5, 200)

    def cuenta(self, insc=None):
        insc = insc or self.insc5
        return self.client.get(f'{URL_INSC}{insc.id}/calendario-pagos/').data['resumen']

    def test_pagado_y_todos_los_dias_por_venir_no_hay_dias_a_favor(self):
        c = self.cuenta()['cuenta']
        self.assertEqual(c['dias_a_favor'], 0)

    def test_falta_avisada_deja_un_dia_a_favor_y_alerta(self):
        self.marcar(self.insc5, self.d(1), 'ausente_justificado')
        r = self.cuenta()
        c = r['cuenta']
        self.assertEqual(c['dias_a_favor'], 1)
        self.assertEqual(c['dias_a_favor_permiso'], 1)
        self.assertEqual(c['monto_a_favor'], dec('40.00'))
        self.assertEqual(c['nivel'], 'al_dia')
        self.assertIn('dias_a_favor', [a['codigo'] for a in r['alertas']])

    def test_asistir_a_un_dia_acordado_no_genera_dias_a_favor(self):
        insc = self._inscribir(self._otro_nino('Pablo', 'Rios'),
                               dias_programados=[self.dia(2).isoformat(), self.dia(1).isoformat()])
        self.abonar(insc, 80)
        self.marcar(insc, self.dia(2), 'presente')
        self.marcar(insc, self.dia(1), 'ausente')          # falta sin aviso: se cobra
        self.assertEqual(self.cuenta(insc)['cuenta']['dias_a_favor'], 0)

    def test_pagar_de_mas_se_marca_como_a_favor_sin_permiso(self):
        self.abonar(self.insc5, 80)
        c = self.cuenta()['cuenta']
        self.assertEqual(c['dias_a_favor'], 2)
        self.assertEqual(c['dias_a_favor_permiso'], 0)

    def test_la_lista_trae_dias_a_favor_y_se_puede_filtrar(self):
        self.marcar(self.insc5, self.d(1), 'ausente_justificado')
        r = self.client.get(URL_INSC + '?page_size=100&activa=true')
        fila = [f for f in r.data['results'] if f['id'] == str(self.insc5.id)][0]
        self.assertEqual(fila['estado_pago']['dias_a_favor'], 1)
        r = self.client.get(URL_INSC + '?page_size=100&estado_pago=a_favor')
        self.assertEqual({f['id'] for f in r.data['results']}, {str(self.insc5.id)})

    def test_el_dia_a_favor_se_recupera_reprogramando(self):
        self.marcar(self.insc5, self.d(1), 'ausente_justificado')
        dias = [self.d(i).isoformat() for i in range(1, 6)] + [self.d(8).isoformat()]
        r = self.client.post(f'{URL_INSC}{self.insc5.id}/actualizar-dias/', {'dias': dias}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['resumen']['cuenta']['dias_a_favor'], 0)

    def test_reprogramar_un_dia_lo_absorbe_el_saldo_y_no_figura_deuda(self):
        self.marcar(self.insc5, self.d(1), 'ausente_justificado')
        dias = [self.d(i).isoformat() for i in range(1, 6)] + [self.d(8).isoformat()]
        r = self.client.post(f'{URL_INSC}{self.insc5.id}/actualizar-dias/', {'dias': dias}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        c = self.cuenta()['cuenta']
        self.assertEqual(c['nivel'], 'al_dia')
        self.assertEqual(c['falta_pagar'], dec('0'))
        self.assertEqual(c['dias_a_pagar'], 5)
        self.assertEqual(c['dias_permiso_sin_cobro'], 1)
        self.assertFalse(c['sobre_acordado'])
        # El dinero cubre el día nuevo y no el día con permiso.
        self.assertIn(self.d(8).isoformat(), c['dias_cubiertos'])
        self.assertNotIn(self.d(1).isoformat(), c['dias_cubiertos'])
        # La lista tampoco lo marca con deuda.
        r = self.client.get(URL_INSC + '?page_size=100&estado_pago=deuda')
        self.assertNotIn(str(self.insc5.id), {f['id'] for f in r.data['results']})

    def test_con_saldo_a_favor_la_cuenta_queda_por_encima_de_lo_acordado(self):
        self.marcar(self.insc5, self.d(1), 'ausente_justificado')
        c = self.cuenta()['cuenta']
        self.assertTrue(c['sobre_acordado'])
        self.assertEqual(c['pagado_de_mas'], dec('40.00'))
        self.assertEqual(c['dias_sobre_acordado'], 1)
        self.assertGreater(c['pct_pagado'], 100)
        self.assertIn('por encima de lo acordado', c['mensaje'])

    def _devolver(self, monto):
        return self.client.post(f'{URL_INSC}{self.insc5.id}/devolver-saldo/', {
            'monto': monto, 'metodo_pago': 'efectivo', 'motivo': 'Devolución por permiso'}, format='json')

    def test_devolver_el_saldo_del_permiso_deja_la_cuenta_al_dia_sin_alertas(self):
        self.marcar(self.insc5, self.d(1), 'ausente_justificado')
        r = self._devolver('40')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        c = self.cuenta()['cuenta']
        self.assertEqual(c['nivel'], 'al_dia')
        self.assertEqual(c['dias_a_favor'], 0)
        self.assertFalse(c['sobre_acordado'])
        self.assertEqual(c['pagado_total'], dec('160.00'))
        self.assertEqual(c['falta_pagar'], dec('0'))

    def test_devolver_el_saldo_que_cubria_un_dia_nuevo_vuelve_a_marcar_deuda(self):
        self.marcar(self.insc5, self.d(1), 'ausente_justificado')
        dias = [self.d(i).isoformat() for i in range(1, 6)] + [self.d(8).isoformat()]
        self.client.post(f'{URL_INSC}{self.insc5.id}/actualizar-dias/', {'dias': dias}, format='json')
        self._devolver('40')
        c = self.cuenta()['cuenta']
        self.assertEqual(c['nivel'], 'deuda')
        self.assertEqual(c['falta_pagar'], dec('40.00'))
        self.assertNotIn(self.d(8).isoformat(), c['dias_cubiertos'])


class MensualidadPorIniciarTests(PorDiaBase):
    """Pasar de por día a mensual con inicio futuro: no debe decir 'sin mensualidad generada'."""

    def _pasar(self, insc, dias_adelante):
        inicio = (self.hoy + timedelta(days=dias_adelante)).isoformat()
        r = self.client.post(f'{URL_INSC}{insc.id}/cambiar-modalidad/',
                             {'modalidad': 'mensual', 'fecha_inicio': inicio}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        return Inscripcion.objects.get(nino=insc.nino, activa=True)

    def test_inicio_futuro_sin_pagar_es_por_iniciar_y_no_deuda(self):
        nueva = self._pasar(self._inscribir(self._otro_nino('Franquito', 'Castro')), 10)
        e = estado_pago(nueva)
        self.assertEqual(e['nivel'], 'por_iniciar')
        self.assertEqual(e['falta_pagar'], dec('0'))
        self.assertGreater(e['por_pagar_proximo'], 0)
        self.assertEqual(e['pagado_total'], dec('0'))
        self.assertGreater(e['monto_acordado'], 0)
        self.assertIn('empieza el', e['mensaje'])

    def test_se_puede_filtrar_por_iniciar_y_no_sale_en_deuda(self):
        nueva = self._pasar(self._inscribir(self._otro_nino('Franquito', 'Castro')), 10)
        r = self.client.get(URL_INSC + '?page_size=100&estado_pago=por_iniciar')
        self.assertEqual({f['id'] for f in r.data['results']}, {str(nueva.id)})
        r = self.client.get(URL_INSC + '?page_size=100&estado_pago=deuda')
        self.assertNotIn(str(nueva.id), {f['id'] for f in r.data['results']})

    def test_inicio_hoy_sin_pagar_si_es_deuda(self):
        nueva = self._pasar(self._inscribir(self._otro_nino('Franquito', 'Castro')), 0)
        self.assertEqual(estado_pago(nueva)['nivel'], 'deuda')


class HistorialCuentaTests(PorDiaBase):
    """El historial del niño debe verse completo aunque cambie de modalidad."""

    def setUp(self):
        super().setUp()
        self.insc = self._inscribir(
            self._otro_nino('Franquito', 'Castro'),
            dias_programados=[(self.hoy + timedelta(days=i)).isoformat() for i in range(1, 4)])
        self.abonar(self.insc, 120)
        self.marcar(self.insc, self.hoy + timedelta(days=1), 'presente')

    def _historial(self, insc):
        r = self.client.get(f'{URL_INSC}{insc.id}/historial-cuenta/')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        return r.data

    def test_historial_incluye_abonos_cobros_y_dias(self):
        h = self._historial(self.insc)
        tipos = {m['tipo'] for m in h['movimientos']}
        self.assertTrue({'inscripcion', 'abono', 'cobro', 'aplicacion'} <= tipos, tipos)
        self.assertEqual(h['totales']['recibido'], dec('120.00'))
        self.assertEqual(h['nino'], 'Franquito Castro')

    def test_al_pasar_a_mensual_el_historial_de_dia_no_desaparece(self):
        r = self.client.post(f'{URL_INSC}{self.insc.id}/cambiar-modalidad/', {
            'modalidad': 'mensual', 'fecha_inicio': (self.hoy + timedelta(days=10)).isoformat()}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        nueva = Inscripcion.objects.get(nino=self.insc.nino, activa=True)
        h = self._historial(nueva)
        self.assertEqual(len(h['inscripciones']), 2)
        self.assertEqual({i['modalidad'] for i in h['inscripciones']}, {'diaria', 'mensual'})
        movs = h['movimientos']
        # Sigue el abono y el cobro por día de la inscripción cerrada...
        self.assertIn('abono', {m['tipo'] for m in movs if m['modalidad'] == 'diaria'})
        self.assertIn('cobro', {m['tipo'] for m in movs if m['modalidad'] == 'diaria'})
        # ...y se ve el cambio y la mensualidad nueva.
        self.assertTrue(any(m['tipo'] == 'inscripcion' and 'Cambio:' in m['titulo'] for m in movs))
        self.assertTrue(any(m['tipo'] == 'cobro' and m['modalidad'] == 'mensual' for m in movs))
        self.assertEqual(h['totales']['recibido'], dec('120.00'))

    def test_el_historial_se_puede_pedir_desde_la_inscripcion_cerrada(self):
        self.client.post(f'{URL_INSC}{self.insc.id}/cambiar-modalidad/', {
            'modalidad': 'mensual', 'fecha_inicio': (self.hoy + timedelta(days=5)).isoformat()}, format='json')
        h = self._historial(Inscripcion.objects.get(pk=self.insc.pk))
        self.assertEqual(len(h['inscripciones']), 2)

    def test_la_devolucion_aparece_como_salida_con_recibo(self):
        self.client.post(f'{URL_INSC}{self.insc.id}/devolver-saldo/', {
            'monto': '40', 'metodo_pago': 'efectivo', 'motivo': 'Prueba'}, format='json')
        dev = [m for m in self._historial(self.insc)['movimientos'] if m['tipo'] == 'devolucion']
        self.assertEqual(len(dev), 1)
        self.assertEqual(dev[0]['efecto'], 'sale')
        self.assertEqual(dev[0]['recibo']['tipo'], 'devolucion')


class CambioDeModalidadCasosTests(PorDiaBase):
    """Qué pasa al pasar de por día a mensual con saldo, deuda o fechas que chocan."""

    def _pasar(self, insc, fecha):
        return self.client.post(f'{URL_INSC}{insc.id}/cambiar-modalidad/',
                                {'modalidad': 'mensual', 'fecha_inicio': fecha.isoformat()}, format='json')

    def _con_dias_pasados(self, nombre, dias_atras=(5, 4, 2, 1), abono=None):
        insc = self._inscribir(self._otro_nino(nombre, 'Caso'), fecha_inicio=self.hoy - timedelta(days=6))
        if abono:
            self.abonar(insc, abono)
        for k in dias_atras:
            self.marcar(insc, self.hoy - timedelta(days=k), 'presente')
        return insc

    def test_el_saldo_a_favor_se_aplica_a_la_primera_mensualidad(self):
        insc = self._con_dias_pasados('Saldo', abono=400)          # 4 días × 40 = 160 usados, 240 de saldo
        r = self._pasar(insc, self.hoy)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['traspaso']['saldo_aplicado'], dec('240.00'))
        nueva = Inscripcion.objects.get(nino=insc.nino, activa=True)
        c = Cobro.objects.get(inscripcion=nueva)
        self.assertEqual(c.monto_pagado, dec('240.00'))
        self.assertEqual(estado_pago(nueva)['falta_pagar'], dec('410.00'))

    def test_el_saldo_mayor_a_la_mensualidad_deja_el_resto_a_favor(self):
        insc = self._con_dias_pasados('Mucho', abono=1000)         # 840 de saldo > 650
        r = self._pasar(insc, self.hoy)
        self.assertEqual(r.data['traspaso']['saldo_aplicado'], dec('650.00'))
        nueva = Inscripcion.objects.get(nino=insc.nino, activa=True)
        self.assertEqual(saldo_a_favor(nueva), dec('190.00'))
        self.assertEqual(estado_pago(nueva)['nivel'], 'al_dia')

    def _con_deuda_anterior(self, nombre):
        """Pasa a mensual estando al día y luego reabre una deuda en la inscripción por día cerrada
        (p. ej. un cobro corregido después). Devuelve (inscripción cerrada, mensual nueva)."""
        insc = self._con_dias_pasados(nombre, dias_atras=(2, 1), abono=80)
        self.assertEqual(self._pasar(insc, self.hoy).status_code, status.HTTP_201_CREATED)
        nueva = Inscripcion.objects.get(nino=insc.nino, activa=True)
        c = Cobro.objects.get(inscripcion=nueva)
        self.client.post(f'{URL_COBROS}{c.id}/registrar-pago/', {'monto': '650'}, format='json')
        for viejo in Cobro.objects.filter(inscripcion=insc, tipo=Cobro.TIPO_DIARIO):
            viejo.pagos.all().delete()
            viejo.estado = Cobro.ESTADO_PENDIENTE
            viejo.save()
        return insc, nueva

    def test_la_deuda_de_dias_cobrados_sigue_visible_tras_pasar_a_mensual(self):
        insc, nueva = self._con_deuda_anterior('Debe')
        e = estado_pago(nueva)
        self.assertEqual(e['nivel'], 'deuda')
        self.assertEqual(e['deuda_anterior'], dec('80.00'))
        self.assertEqual(e['deuda_total'], dec('80.00'))
        self.assertIn('inscripción anterior', e['mensaje'])
        r = self.client.get(URL_INSC + '?page_size=100&estado_pago=deuda')
        self.assertIn(str(nueva.id), {f['id'] for f in r.data['results']})

    def test_pagar_la_deuda_anterior_quita_la_alerta(self):
        insc, nueva = self._con_deuda_anterior('Paga')
        for c in Cobro.objects.filter(inscripcion=insc, tipo=Cobro.TIPO_DIARIO):
            r = self.client.post(f'{URL_COBROS}{c.id}/registrar-pago/', {'monto': '40'}, format='json')
            self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        e = estado_pago(nueva)
        self.assertEqual(e['nivel'], 'al_dia')
        self.assertEqual(e['deuda_anterior'], dec('0'))

    def test_no_se_puede_empezar_la_mensualidad_encima_de_dias_ya_cobrados(self):
        insc = self._con_dias_pasados('Choque', abono=400)         # asistió hace 5, 4, 2 y 1 días
        r = self._pasar(insc, self.hoy - timedelta(days=3))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('dos veces', r.data['error'])
        self.assertIn((self.hoy).strftime('%d/%m/%Y'), r.data['error'])      # sugiere hoy (día siguiente al último)
        self.assertTrue(Inscripcion.objects.get(pk=insc.pk).activa)           # no se cambió nada
        self.assertEqual(Inscripcion.objects.filter(nino=insc.nino).count(), 1)

    def test_empezar_el_dia_siguiente_al_ultimo_asistido_si_se_puede(self):
        insc = self._con_dias_pasados('Ok', abono=400)
        self.assertEqual(self._pasar(insc, self.hoy).status_code, status.HTTP_201_CREATED)


# ═══════════════════════════════════════════════════════════════════
class ReinscripcionConDeudaTests(PorDiaBase):
    """Se puede dar de baja con deuda, pero no volver a inscribir hasta pagarla (aun con saldo a favor)."""

    def _baja(self, insc):
        return self.client.post(f'{URL_INSC}{insc.id}/cerrar/', {}, format='json')

    def _nueva(self, nino, modalidad='mensual'):
        datos = {'nino': str(nino.id), 'sucursal': self.sucursal.id, 'sala': self.sala.id, 'turno': self.turno.id,
                 'modalidad_pago': modalidad, 'costo_mensual': '650.00', 'costo_diario': '40.00'}
        if modalidad == 'mensual':
            datos['fecha_inicio'] = self.hoy.isoformat()
        else:
            datos['dias_programados'] = [self.hoy.isoformat()]
        return self.client.post(URL_INSC, datos, format='json')

    def _mensual_con_deuda_dada_de_baja(self, nombre='Deudor'):
        m = self._inscribir(self._otro_nino(nombre, 'Baja'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        generar_ciclo_mensual(m, ciclo_num=0)                 # 650 sin pagar
        self.assertEqual(self._baja(m).status_code, status.HTTP_200_OK)
        return m

    def test_se_puede_dar_de_baja_con_deuda(self):
        m = self._mensual_con_deuda_dada_de_baja()
        m.refresh_from_db()
        self.assertFalse(m.activa)
        self.assertEqual(deuda_abierta(m), dec(650))

    def test_con_deuda_en_la_inscripcion_cerrada_no_se_puede_crear_una_mensualidad_nueva(self):
        m = self._mensual_con_deuda_dada_de_baja()
        r = self._nueva(m.nino)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('650', str(r.data))
        self.assertEqual(Inscripcion.objects.filter(nino=m.nino, activa=True).count(), 0)

    def test_tambien_se_bloquea_la_inscripcion_por_dia(self):
        m = self._mensual_con_deuda_dada_de_baja('PorDia')
        self.assertEqual(self._nueva(m.nino, 'diaria').status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_saldo_a_favor_no_compensa_la_deuda(self):
        # Por día: asistió 2 días sin pagar (80) pero también tiene un abono de 500 en la misma cuenta.
        n = self._otro_nino('Saldo', 'Favor')
        d = self._inscribir(n, fecha_inicio=self.hoy - timedelta(days=5))
        self.marcar(d, self.dia(2), 'presente')
        self.marcar(d, self.dia(1), 'presente')               # 80 de deuda
        self.assertEqual(self._baja(d).status_code, status.HTTP_200_OK)
        d.refresh_from_db()
        # Saldo a favor "suelto" en la inscripción cerrada (p. ej. un abono que no se aplicó)
        AbonoDiario.objects.create(inscripcion=d, monto=dec(500), fecha_pago=self.hoy, metodo_pago='efectivo',
                                   registrado_por=self.staff)
        self.assertGreater(saldo_a_favor(d), 0)
        self.assertGreater(deuda_abierta(d), 0)
        r = self._nueva(n)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.data)
        self.assertIn('saldo a favor', str(r.data))

    def test_al_pagar_la_deuda_ya_se_puede_inscribir_de_nuevo(self):
        m = self._mensual_con_deuda_dada_de_baja('Paga')
        c = Cobro.objects.get(inscripcion=m, tipo=Cobro.TIPO_MENSUALIDAD)
        pago = self.client.post(f'{URL_COBROS}{c.id}/registrar-pago/', {'monto': '650'}, format='json')
        self.assertEqual(pago.status_code, status.HTTP_200_OK, pago.data)
        r = self._nueva(m.nino)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

    def test_sin_deuda_la_baja_y_el_regreso_funcionan_como_siempre(self):
        m = self._inscribir(self._otro_nino('Limpio', 'Baja'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        self.assertEqual(self._baja(m).status_code, status.HTTP_200_OK)
        self.assertEqual(self._nueva(m.nino).status_code, status.HTTP_201_CREATED)

    def test_una_inscripcion_dada_de_baja_no_se_puede_reactivar(self):
        # sin deuda también: la baja es definitiva y el regreso se hace con una inscripción nueva
        m = self._inscribir(self._otro_nino('Alta', 'Nueva'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        self._baja(m)
        r = self.client.patch(f'{URL_INSC}{m.id}/', {'activa': True}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, r.data)
        self.assertIn('inscripción nueva', str(r.data))
        m.refresh_from_db()
        self.assertFalse(m.activa)
        # y volver con una inscripción nueva sí funciona
        self.assertEqual(self._nueva(m.nino).status_code, status.HTTP_201_CREATED)

    def test_editar_una_inscripcion_dada_de_baja_sin_tocar_activa_sigue_cerrada(self):
        m = self._inscribir(self._otro_nino('Edita', 'Cerrada'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        self._baja(m)
        r = self.client.patch(f'{URL_INSC}{m.id}/', {'motivo_ajuste': 'Corrección'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        m.refresh_from_db()
        self.assertFalse(m.activa)

    def test_la_lista_muestra_la_deuda_de_una_inscripcion_dada_de_baja(self):
        m = self._mensual_con_deuda_dada_de_baja('Lista')
        r = self.client.get(URL_INSC + '?page_size=100&activa=false')
        fila = next(f for f in r.data['results'] if f['id'] == str(m.id))
        self.assertEqual(dec(fila['deuda_cerrada']), dec(650))
        self.assertIsNone(fila['estado_pago'])
        # sin deuda → 0; y en las activas siempre 0
        limpia = self._inscribir(self._otro_nino('Sin', 'Deuda'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        self._baja(limpia)
        r = self.client.get(URL_INSC + '?page_size=100&activa=')
        filas = {f['id']: f for f in r.data['results']}
        self.assertEqual(dec(filas[str(limpia.id)]['deuda_cerrada']), dec(0))
        self.assertEqual(dec(filas[str(self.insc.id)]['deuda_cerrada']), dec(0))

    def test_el_mensaje_de_bloqueo_indica_donde_cobrar(self):
        m = self._mensual_con_deuda_dada_de_baja('Mensaje')
        r = self._nueva(m.nino)
        self.assertIn('Dadas de baja', str(r.data))

    def test_las_inscripciones_no_se_eliminan_por_la_api(self):
        m = self._inscribir(self._otro_nino('No', 'Borrar'), modalidad=Inscripcion.MODALIDAD_MENSUAL)
        self._baja(m)
        r = self.client.delete(f'{URL_INSC}{m.id}/')
        self.assertEqual(r.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertIn('administrador de Django', str(r.data))
        self.assertTrue(Inscripcion.objects.filter(pk=m.pk).exists())



# ═══════════════════════════════════════════════════════════════════
class EditarPrecioMensualTests(PorDiaBase):
    """Editar el precio de una inscripción mensual no puede dejar su cobro abierto con el precio viejo."""

    def _mensual(self):
        r = self.client.post(URL_INSC, {
            'nino': str(self._otro_nino().id), 'sucursal': str(self.sucursal.id), 'sala': str(self.sala.id),
            'turno': str(self.turno.id), 'modalidad_pago': 'mensual', 'fecha_inicio': self.hoy.isoformat(),
            'costo_mensual': '650.00', 'costo_diario': '40.00', 'tipo_ajuste': 'ninguno', 'activa': True,
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        return Inscripcion.objects.get(pk=r.data['id'])

    def test_cobro_sin_pagos_sigue_el_precio_editado(self):
        insc = self._mensual()
        cobro = Cobro.objects.get(inscripcion=insc)
        self.assertEqual(cobro.monto_final, dec(650))
        r = self.client.patch(f'{URL_INSC}{insc.id}/', {'costo_mensual': '700.00'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        cobro.refresh_from_db()
        self.assertEqual((cobro.monto_base, cobro.monto_final), (dec(700), dec(700)))

    def test_cobro_con_pagos_no_se_toca(self):
        insc = self._mensual()
        cobro = Cobro.objects.get(inscripcion=insc)
        Pago.objects.create(cobro=cobro, monto=dec(650), metodo_pago='efectivo',
                            fecha_pago=self.hoy, registrado_por=self.staff)
        cobro.refresh_from_db()
        cobro.recalcular_estado()      # la API lo hace al registrar el pago; aquí se crea directo
        self.assertEqual(cobro.estado, Cobro.ESTADO_PAGADO)
        self.client.patch(f'{URL_INSC}{insc.id}/', {'costo_mensual': '750.00'}, format='json')
        cobro.refresh_from_db()
        self.assertEqual(cobro.monto_final, dec(650))
        self.assertEqual(cobro.estado, Cobro.ESTADO_PAGADO)

    def test_editar_otro_campo_no_cambia_cobros(self):
        insc = self._mensual()
        cobro = Cobro.objects.get(inscripcion=insc)
        self.client.patch(f'{URL_INSC}{insc.id}/', {'motivo_ajuste': 'nota'}, format='json')
        cobro.refresh_from_db()
        self.assertEqual(cobro.monto_final, dec(650))

    def test_lista_trae_precio_de_la_inscripcion_y_del_turno(self):
        insc = self._mensual()
        Inscripcion.objects.filter(pk=insc.pk).update(costo_mensual=dec(750))
        r = self.client.get(URL_INSC, {'page_size': 50})
        fila = next(x for x in r.data['results'] if x['id'] == str(insc.id))
        self.assertEqual(dec(fila['costo_mensual']), dec(750))
        self.assertEqual(dec(fila['turno_costo_mensual']), dec(650))
