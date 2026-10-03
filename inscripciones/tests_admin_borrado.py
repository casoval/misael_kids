"""
Pruebas del bloqueo de borrado en el administrador: una inscripción (o cobro)
con pagos, abonos o devoluciones no se puede borrar; una vacía sí.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Usuario
from core.models import Sucursal, Sala, Turno
from ninos.models import Nino
from .models import Inscripcion, Cobro, Pago, AbonoDiario, Devolucion


class AdminBorradoTests(TestCase):

    def setUp(self):
        s = Sucursal.objects.create(nombre='Misael Kids - Camacho', direccion='Av. Camacho 123')
        sala = Sala.objects.create(sucursal=s, nombre='Sala Cuna', edad_min_meses=0,
                                   edad_max_meses=24, capacidad_maxima=10)
        turno = Turno.objects.create(sala=sala, nombre='Turno mañana', tipo=Turno.TIPO_MANANA,
                                     hora_inicio='08:00', hora_fin='12:00',
                                     costo_mensual='650.00', costo_diario='40.00')
        self.admin_user = Usuario.objects.create_user(
            email='root@misaelkids.test', password='clave12345', nombres='Root', apellidos='Admin',
            rol=Usuario.ROL_DIRECTORA, is_staff=True, is_superuser=True)
        self.client.force_login(self.admin_user)
        self.nino = Nino.objects.create(nombres='Valentina', apellidos='Rojas',
                                        fecha_nacimiento=date(2024, 6, 1), genero='F')
        self.insc = Inscripcion.objects.create(
            nino=self.nino, sucursal=s, sala=sala, turno=turno,
            modalidad_pago=Inscripcion.MODALIDAD_DIARIA, fecha_inicio=date.today(),
            costo_mensual='650.00', costo_diario='40.00')

    # ── helpers ──
    def _cobro(self, insc=None):
        return Cobro.objects.create(
            inscripcion=insc or self.insc, tipo=Cobro.TIPO_DIARIO, periodo=date.today().isoformat(),
            monto_base=Decimal('40'), monto_final=Decimal('40'), fecha_vencimiento=date.today())

    def _pago(self, cobro, monto='40', **kw):
        return Pago.objects.create(cobro=cobro, monto=Decimal(monto), fecha_pago=date.today(), **kw)

    def _abono(self, monto='100'):
        return AbonoDiario.objects.create(inscripcion=self.insc, monto=Decimal(monto), fecha_pago=date.today())

    def _url(self, modelo, accion, obj):
        return reverse(f'admin:inscripciones_{modelo}_{accion}', args=[obj.pk])

    def _borrar(self, modelo, obj):
        return self.client.post(self._url(modelo, 'delete', obj), {'post': 'yes'}, follow=True)

    # ── inscripción ──
    def test_inscripcion_vacia_se_puede_borrar(self):
        self._cobro()   # un cobro sin pagos no cuenta como dinero
        r = self._borrar('inscripcion', self.insc)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_inscripcion_con_pago_no_se_borra(self):
        c = self._cobro(); self._pago(c)
        r = self._borrar('inscripcion', self.insc)
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())
        self.assertTrue(Pago.objects.filter(cobro=c).exists())
        self.assertContains(r, '1 pago')

    def test_inscripcion_con_abono_no_se_borra(self):
        self._abono()
        r = self._borrar('inscripcion', self.insc)
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())
        self.assertTrue(AbonoDiario.objects.filter(inscripcion=self.insc).exists())
        self.assertContains(r, '1 abono')

    def test_inscripcion_con_devolucion_de_saldo_no_se_borra(self):
        Devolucion.objects.create(inscripcion=self.insc, monto=Decimal('10'), motivo='Saldo a favor')
        self._borrar('inscripcion', self.insc)
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())

    def test_ni_el_superusuario_puede_y_el_boton_eliminar_no_aparece(self):
        self._abono()
        r = self.client.get(self._url('inscripcion', 'change', self.insc))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, self._url('inscripcion', 'delete', self.insc))
        self.assertContains(r, 'No se puede borrar la inscripción')

    def test_accion_borrar_seleccionados_tambien_se_bloquea(self):
        self._abono()
        vacia = Inscripcion.objects.create(
            nino=Nino.objects.create(nombres='Mateo', apellidos='Quispe',
                                     fecha_nacimiento=date(2024, 3, 1), genero='M'),
            sucursal=self.insc.sucursal, sala=self.insc.sala, turno=self.insc.turno,
            fecha_inicio=date.today(), costo_mensual='650.00', costo_diario='40.00')
        data = {'action': 'delete_selected', 'post': 'yes',
                '_selected_action': [str(self.insc.pk), str(vacia.pk)]}
        self.client.post(reverse('admin:inscripciones_inscripcion_changelist'), data, follow=True)
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())
        self.assertTrue(Inscripcion.objects.filter(pk=vacia.pk).exists())   # nada se borra a medias

    def test_borrar_al_nino_con_dinero_no_arrastra_la_inscripcion(self):
        self._abono()
        self.client.post(reverse('admin:ninos_nino_delete', args=[self.nino.pk]), {'post': 'yes'}, follow=True)
        self.assertTrue(Nino.objects.filter(pk=self.nino.pk).exists())
        self.assertTrue(AbonoDiario.objects.filter(inscripcion=self.insc).exists())

    def test_borrar_al_nino_sin_dinero_si_se_puede(self):
        self.client.post(reverse('admin:ninos_nino_delete', args=[self.nino.pk]), {'post': 'yes'}, follow=True)
        self.assertFalse(Nino.objects.filter(pk=self.nino.pk).exists())

    # ── cobro / pago / abono ──
    def test_cobro_con_pago_no_se_borra_pero_sin_pago_si(self):
        con = self._cobro(); self._pago(con)
        sin = Cobro.objects.create(
            inscripcion=self.insc, tipo=Cobro.TIPO_DIARIO, periodo='2020-01-01',
            monto_base=Decimal('40'), monto_final=Decimal('40'), fecha_vencimiento=date.today())
        self._borrar('cobro', con)
        self._borrar('cobro', sin)
        self.assertTrue(Cobro.objects.filter(pk=con.pk).exists())
        self.assertFalse(Cobro.objects.filter(pk=sin.pk).exists())

    def test_pago_se_borra_y_el_cobro_vuelve_a_quedar_pendiente(self):
        c = self._cobro(); p = self._pago(c)
        c.recalcular_estado(); c.refresh_from_db()
        self.assertEqual(c.estado, Cobro.ESTADO_PAGADO)
        self._borrar('pago', p)
        c.refresh_from_db()
        self.assertFalse(Pago.objects.filter(pk=p.pk).exists())
        self.assertNotEqual(c.estado, Cobro.ESTADO_PAGADO)

    def test_abono_se_borra_con_sus_aplicaciones_y_recalcula_el_cobro(self):
        c = self._cobro(); a = self._abono('40')
        self._pago(c, '40', abono_origen=a)
        c.recalcular_estado(); c.refresh_from_db()
        self.assertEqual(c.estado, Cobro.ESTADO_PAGADO)
        self._borrar('abonodiario', a)
        c.refresh_from_db()
        self.assertFalse(AbonoDiario.objects.filter(pk=a.pk).exists())
        self.assertFalse(Pago.objects.filter(cobro=c).exists())
        self.assertNotEqual(c.estado, Cobro.ESTADO_PAGADO)

    def test_borrar_pagos_y_abonos_seleccionados_desde_la_lista(self):
        c = self._cobro(); p = self._pago(c); a = self._abono()
        self.client.post(reverse('admin:inscripciones_pago_changelist'),
                         {'action': 'delete_selected', 'post': 'yes', '_selected_action': [str(p.pk)]})
        self.client.post(reverse('admin:inscripciones_abonodiario_changelist'),
                         {'action': 'delete_selected', 'post': 'yes', '_selected_action': [str(a.pk)]})
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(AbonoDiario.objects.exists())

    def test_tras_borrar_pagos_y_abonos_la_inscripcion_ya_se_puede_borrar(self):
        c = self._cobro(); p = self._pago(c); a = self._abono()
        self._borrar('inscripcion', self.insc)
        self.assertTrue(Inscripcion.objects.filter(pk=self.insc.pk).exists())
        self._borrar('pago', p); self._borrar('abonodiario', a)
        self._borrar('inscripcion', self.insc)
        self.assertFalse(Inscripcion.objects.filter(pk=self.insc.pk).exists())
