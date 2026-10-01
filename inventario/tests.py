"""
inventario/tests.py
Permisos por rol, validación de movimientos (sin stock negativo ni cantidades inválidas),
historial de solo lectura, stock solo editable vía movimientos, borrado lógico y filtros.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Usuario
from core.models import Sucursal
from .models import ItemInventario, MovimientoInventario

URL_ITEMS = '/api/inventario/items/'
URL_MOVS  = '/api/inventario/movimientos/'


def usuario(rol, email):
    return Usuario.objects.create_user(email=email, password='x12345678', nombres='Pepe',
                                       apellidos=rol.title(), rol=rol)


class InventarioBase(APITestCase):
    def setUp(self):
        self.suc  = Sucursal.objects.create(nombre='Camacho', direccion='a')
        self.suc2 = Sucursal.objects.create(nombre='Sopocachi', direccion='b')
        self.directora = usuario(Usuario.ROL_DIRECTORA, 'd@x.test')
        self.client.force_authenticate(self.directora)
        self.item = ItemInventario.objects.create(sucursal=self.suc, nombre='Crayones', categoria='didactico',
                                                  unidad='cajas', stock_actual=10, stock_minimo=3)

    def mov(self, tipo, cantidad, motivo='Prueba', **extra):
        return self.client.post(f'{URL_ITEMS}{self.item.id}/registrar-movimiento/',
                                {'tipo': tipo, 'cantidad': cantidad, 'motivo': motivo, **extra})


class PermisosInventarioTests(InventarioBase):
    def test_tutor_no_puede_ver_ni_escribir(self):
        self.client.force_authenticate(usuario(Usuario.ROL_TUTOR, 't@x.test'))
        self.assertEqual(self.client.get(URL_ITEMS).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(URL_ITEMS + 'alertas-stock/').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.mov('entrada', 5).status_code, status.HTTP_403_FORBIDDEN)
        r = self.client.post(URL_ITEMS, {'sucursal': str(self.suc.id), 'nombre': 'X', 'categoria': 'otro', 'unidad': 'u'})
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f'{URL_ITEMS}{self.item.id}/').status_code, status.HTTP_403_FORBIDDEN)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)

    def test_sin_login_no_entra(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL_ITEMS).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_el_profesional_puede_leer_alertas_para_el_dashboard_pero_no_escribir(self):
        self.client.force_authenticate(usuario(Usuario.ROL_PROFESIONAL, 'p@x.test'))
        self.assertEqual(self.client.get(URL_ITEMS + 'alertas-stock/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.mov('entrada', 1).status_code, status.HTTP_403_FORBIDDEN)

    def test_cocina_educadora_y_ayudante_registran_movimientos(self):
        for rol in (Usuario.ROL_COCINA, Usuario.ROL_EDUCADORA, Usuario.ROL_AYUDANTE):
            self.client.force_authenticate(usuario(rol, f'{rol}@x.test'))
            self.assertEqual(self.mov('entrada', 1).status_code, status.HTTP_201_CREATED, rol)

    def test_solo_oficina_desactiva_items(self):
        self.client.force_authenticate(usuario(Usuario.ROL_EDUCADORA, 'e@x.test'))
        self.assertEqual(self.client.delete(f'{URL_ITEMS}{self.item.id}/').status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.directora)
        self.assertEqual(self.client.delete(f'{URL_ITEMS}{self.item.id}/').status_code, status.HTTP_204_NO_CONTENT)


class MovimientosTests(InventarioBase):
    def test_entrada_salida_y_ajuste_actualizan_stock_y_guardan_historial(self):
        r = self.mov('entrada', 5)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual((r.data['stock_anterior'], r.data['stock_resultante'], r.data['stock_actual']), (10, 15, 15))
        self.assertEqual(self.mov('salida', 4).data['stock_resultante'], 11)
        r = self.mov('ajuste', 7, 'Inventario físico')
        self.assertEqual((r.data['stock_anterior'], r.data['stock_resultante']), (11, 7))
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 7)
        self.assertEqual(self.item.movimientos.count(), 3)
        self.assertEqual(self.item.movimientos.first().registrado_por, self.directora)

    def test_salida_mayor_al_stock_se_rechaza_y_no_cambia_nada(self):
        r = self.mov('salida', 11)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cantidad', r.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)
        self.assertEqual(self.item.movimientos.count(), 0)

    def test_ajuste_a_cero_es_valido(self):
        self.assertEqual(self.mov('ajuste', 0, 'Se terminó').status_code, status.HTTP_201_CREATED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 0)

    def test_datos_invalidos_dan_400_y_no_500(self):
        for datos in [
            {'tipo': 'robo', 'cantidad': 1, 'motivo': 'x'},        # tipo inexistente
            {'tipo': 'entrada', 'cantidad': 'abc', 'motivo': 'x'},  # no numérico (antes: error 500)
            {'tipo': 'entrada', 'cantidad': None, 'motivo': 'x'},
            {'tipo': 'entrada', 'cantidad': 0, 'motivo': 'x'},      # entrada de 0
            {'tipo': 'salida',  'cantidad': -3, 'motivo': 'x'},     # negativo
            {'tipo': 'ajuste',  'cantidad': -1, 'motivo': 'x'},
            {'tipo': 'entrada', 'cantidad': 1, 'motivo': '   '},    # motivo vacío
            {'tipo': 'entrada', 'cantidad': 1, 'motivo': 'x' * 301},
            {'tipo': 'entrada', 'cantidad': 1, 'motivo': 'x', 'fecha': 'ayer'},
        ]:
            r = self.client.post(f'{URL_ITEMS}{self.item.id}/registrar-movimiento/', datos, format='json')
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, datos)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_la_fecha_elegida_se_respeta_y_la_futura_se_rechaza(self):
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        r = self.mov('entrada', 1, fecha=ayer)
        self.assertEqual(r.data['fecha'], ayer)                    # antes se ignoraba y se guardaba "hoy"
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertEqual(self.mov('entrada', 1, fecha=manana).status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_se_mueve_stock_de_un_item_desactivado(self):
        self.item.activo = False
        self.item.save()
        # oficina puede localizarlo con ?activo=false; el movimiento se rechaza
        self.assertEqual(self.mov('entrada', 1).status_code, status.HTTP_400_BAD_REQUEST)

    def test_el_historial_es_de_solo_lectura(self):
        self.mov('entrada', 2)
        m = self.item.movimientos.first()
        self.assertEqual(self.client.get(URL_MOVS + f'?item={self.item.id}').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(URL_MOVS, {'item': str(self.item.id), 'fecha': '2026-10-01',
                                                      'tipo': 'entrada', 'cantidad': 999, 'motivo': 'x'}).status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.patch(f'{URL_MOVS}{m.id}/', {'cantidad': 1}).status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(f'{URL_MOVS}{m.id}/').status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ItemsTests(InventarioBase):
    def datos(self, **extra):
        return {'sucursal': str(self.suc.id), 'nombre': 'Bloques', 'categoria': 'juguetes',
                'unidad': 'unidades', 'stock_actual': 6, 'stock_minimo': 2, **extra}

    def test_crear_con_stock_inicial_registra_el_movimiento(self):
        r = self.client.post(URL_ITEMS, self.datos())
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        item = ItemInventario.objects.get(pk=r.data['id'])
        m = item.movimientos.get()
        self.assertEqual((m.tipo, m.cantidad, m.motivo, m.stock_resultante), ('entrada', 6, 'Stock inicial', 6))

    def test_crear_sin_stock_no_genera_movimiento(self):
        r = self.client.post(URL_ITEMS, self.datos(stock_actual=0))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_stock_minimo_cero_es_valido(self):
        r = self.client.post(URL_ITEMS, self.datos(stock_minimo=0))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(r.data['stock_minimo'], 0)

    def test_el_stock_no_se_edita_directamente(self):
        r = self.client.patch(f'{URL_ITEMS}{self.item.id}/', {'stock_actual': 500})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('stock_actual', r.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)

    def test_se_puede_editar_nombre_minimo_y_unidad(self):
        r = self.client.patch(f'{URL_ITEMS}{self.item.id}/', {'nombre': 'Crayones gruesos', 'stock_minimo': 5})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual((r.data['nombre'], r.data['stock_minimo'], r.data['stock_actual']), ('Crayones gruesos', 5, 10))

    def test_nombre_repetido_en_la_misma_sucursal_se_rechaza_pero_no_en_otra(self):
        r = self.client.post(URL_ITEMS, self.datos(nombre='  CRAYONES '))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('nombre', r.data)
        r = self.client.post(URL_ITEMS, self.datos(nombre='Crayones', sucursal=str(self.suc2.id)))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

    def test_desactivar_es_borrado_logico_y_conserva_el_historial(self):
        self.mov('entrada', 1)
        self.assertEqual(self.client.delete(f'{URL_ITEMS}{self.item.id}/').status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(ItemInventario.objects.filter(pk=self.item.pk, activo=False).exists())
        self.assertEqual(MovimientoInventario.objects.filter(item=self.item).count(), 1)
        ids = {i['id'] for i in self.client.get(URL_ITEMS).data['results']}
        self.assertNotIn(str(self.item.id), ids)                      # el listado normal ya no lo muestra
        ids = {i['id'] for i in self.client.get(URL_ITEMS + '?activo=false').data['results']}
        self.assertIn(str(self.item.id), ids)                         # oficina puede verlo y reactivarlo

    def test_el_listado_no_arrastra_todos_los_movimientos(self):
        self.mov('entrada', 1)
        fila = self.client.get(URL_ITEMS).data['results'][0]
        self.assertNotIn('movimientos', fila)

    def test_alertas_y_filtro_bajo_stock_incluyen_el_valor_minimo(self):
        ItemInventario.objects.create(sucursal=self.suc2, nombre='Jabón', categoria='limpieza',
                                      unidad='litros', stock_actual=2, stock_minimo=2)   # igual al mínimo
        alertas = self.client.get(URL_ITEMS + 'alertas-stock/').data
        self.assertEqual([a['nombre'] for a in alertas], ['Jabón'])
        # alertas y listado respetan la sucursal elegida
        self.assertEqual(self.client.get(URL_ITEMS + f'alertas-stock/?sucursal={self.suc.id}').data, [])
        r = self.client.get(URL_ITEMS + '?bajo_stock=true')
        self.assertEqual([i['nombre'] for i in r.data['results']], ['Jabón'])
        r = self.client.get(URL_ITEMS + '?bajo_stock=false')
        self.assertEqual([i['nombre'] for i in r.data['results']], ['Crayones'])
