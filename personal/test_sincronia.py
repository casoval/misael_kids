"""
personal/test_sincronia.py
Usuario y ficha de Personal siempre sincronizados (como Tutor <-> Usuario):
alta atómica, vincular un usuario existente y rol alineado en ambos sentidos.
"""
from rest_framework.test import APITestCase

from accounts.models import Usuario
from personal.models import Personal

DATOS = dict(ci='123', rol='educadora', fecha_ingreso='2026-01-01')


class SincroniaPersonalUsuarioTests(APITestCase):
    def setUp(self):
        self.dir = Usuario.objects.create_user(
            email='dir@x.test', password='clave12345', nombres='D', apellidos='D', rol='directora')
        self.client.force_authenticate(self.dir)

    def _alta(self, **extra):
        body = dict(DATOS, nombres='Laura', apellidos='Pérez', username='laura',
                    password='MisaelKids2025!', telefono='7000')
        body.update(extra)
        return self.client.post('/api/personal/personal/', body, format='json')

    # ── Alta: un solo paso ─────────────────────────────────────────────
    def test_alta_crea_usuario_y_ficha_vinculados(self):
        r = self._alta()
        self.assertEqual(r.status_code, 201, r.data)
        ficha = Personal.objects.get(ci='123')
        self.assertEqual(ficha.usuario.username, 'laura')
        self.assertEqual(ficha.usuario.rol, 'educadora')
        self.assertTrue(ficha.usuario.check_password('MisaelKids2025!'))
        self.assertNotIn('password', r.data)

    def test_si_la_ficha_falla_no_queda_usuario_huerfano(self):
        self.assertEqual(self._alta().status_code, 201)
        r = self._alta(username='laura2')          # mismo CI -> falla
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Usuario.objects.filter(username='laura2').exists())
        # y se puede reintentar con el CI corregido sin "crear desde cero"
        self.assertEqual(self._alta(username='laura2', ci='999').status_code, 201)

    def test_usuario_repetido_no_crea_ficha(self):
        self.assertEqual(self._alta().status_code, 201)
        r = self._alta(ci='999')                   # mismo username
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Personal.objects.filter(ci='999').exists())

    def test_sin_nombres_ni_usuario_pide_los_datos(self):
        r = self.client.post('/api/personal/personal/', DATOS, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('nombres', r.data)

    # ── Acceso opcional, como en Tutor ("dar usuario") ─────────────────
    def test_ficha_sin_acceso_es_valida_y_no_crea_usuario(self):
        antes = Usuario.objects.count()
        r = self.client.post('/api/personal/personal/',
                             dict(DATOS, nombres='Sin', apellidos='Acceso'), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(r.data['tiene_acceso'])
        self.assertIsNone(r.data['usuario'])
        self.assertEqual(r.data['nombre_completo'], 'Sin Acceso')
        self.assertEqual(Usuario.objects.count(), antes)

    def test_dar_acceso_despues_al_editar(self):
        r = self.client.post('/api/personal/personal/',
                             dict(DATOS, nombres='Mar', apellidos='Gil', telefono='70'), format='json')
        pid = r.data['id']
        r = self.client.patch(f'/api/personal/personal/{pid}/',
                              {'username': 'mar', 'password': 'MisaelKids2025!'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['tiene_acceso'])
        u = Personal.objects.get(id=pid).usuario
        self.assertEqual((u.username, u.rol, u.nombres, u.apellidos), ('mar', 'educadora', 'Mar', 'Gil'))
        self.assertTrue(u.check_password('MisaelKids2025!'))

    def test_dar_acceso_exige_usuario_y_contrasena(self):
        pid = self.client.post('/api/personal/personal/',
                               dict(DATOS, nombres='A', apellidos='B'), format='json').data['id']
        r = self.client.patch(f'/api/personal/personal/{pid}/', {'username': 'solo'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', r.data)
        self.assertFalse(Usuario.objects.filter(username='solo').exists())

    def test_no_se_puede_dar_acceso_dos_veces(self):
        self._alta()
        pid = Personal.objects.get(ci='123').id
        r = self.client.patch(f'/api/personal/personal/{pid}/',
                              {'username': 'otro', 'password': 'MisaelKids2025!'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Usuario.objects.filter(username='otro').exists())

    def test_editar_nombre_en_usuarios_actualiza_la_ficha(self):
        self._alta()
        ficha = Personal.objects.get(ci='123')
        self.client.patch(f'/api/auth/usuarios/{ficha.usuario_id}/',
                          {'nombres': 'Lauris', 'apellidos': 'Paz'}, format='json')
        ficha.refresh_from_db()
        self.assertEqual(ficha.nombre_completo, 'Lauris Paz')

    def test_alta_desde_usuarios_envia_el_mismo_payload_y_crea_ambos(self):
        """Payload exacto de la pantalla Usuarios (con password2 sobrante)."""
        r = self.client.post('/api/personal/personal/', dict(
            nombres='Rosa', apellidos='Quispe', telefono='7', rol='recepcionista',
            password='MisaelKids2025!', password2='MisaelKids2025!', username='rosa',
            ci='777', fecha_ingreso='2026-02-01'), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        ficha = Personal.objects.get(ci='777')
        self.assertEqual((ficha.usuario.username, ficha.usuario.rol), ('rosa', 'recepcionista'))

    # ── Vincular un usuario que ya existía ─────────────────────────────
    def test_vincula_usuario_existente_sin_crear_otro(self):
        u = Usuario.objects.create_user(username='rosa', password='clave12345',
                                        nombres='Rosa', apellidos='Q', rol='educadora')
        antes = Usuario.objects.count()
        r = self.client.post('/api/personal/personal/', dict(DATOS, usuario=str(u.id)), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Usuario.objects.count(), antes)
        self.assertEqual(Personal.objects.get(ci='123').usuario_id, u.id)

    def test_vincular_ajusta_el_rol_del_usuario(self):
        u = Usuario.objects.create_user(username='ana', password='clave12345',
                                        nombres='Ana', apellidos='Q', rol='recepcionista')
        self.client.post('/api/personal/personal/', dict(DATOS, usuario=str(u.id)), format='json')
        u.refresh_from_db()
        self.assertEqual(u.rol, 'educadora')

    def test_no_vincula_un_tutor(self):
        u = Usuario.objects.create_user(username='mama', password='clave12345',
                                        nombres='M', apellidos='M', rol='tutor')
        r = self.client.post('/api/personal/personal/', dict(DATOS, usuario=str(u.id)), format='json')
        self.assertEqual(r.status_code, 400)
        u.refresh_from_db()
        self.assertEqual(u.rol, 'tutor')

    def test_no_vincula_dos_fichas_al_mismo_usuario(self):
        self.assertEqual(self._alta().status_code, 201)
        u = Personal.objects.get(ci='123').usuario
        r = self.client.post('/api/personal/personal/', dict(DATOS, ci='555', usuario=str(u.id)), format='json')
        self.assertEqual(r.status_code, 400)

    # ── Rol sincronizado en ambos sentidos ─────────────────────────────
    def test_cambiar_rol_en_la_ficha_cambia_el_del_usuario(self):
        self._alta()
        ficha = Personal.objects.get(ci='123')
        r = self.client.patch(f'/api/personal/personal/{ficha.id}/', {'rol': 'ayudante'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        ficha.usuario.refresh_from_db()
        self.assertEqual(ficha.usuario.rol, 'ayudante')

    def test_cambiar_rol_en_usuarios_cambia_el_de_la_ficha(self):
        self._alta()
        ficha = Personal.objects.get(ci='123')
        r = self.client.patch(f'/api/auth/usuarios/{ficha.usuario_id}/', {'rol': 'recepcionista'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        ficha.refresh_from_db()
        self.assertEqual(ficha.rol, 'recepcionista')

    def test_usuario_con_ficha_no_pasa_a_rol_tutor(self):
        self._alta()
        ficha = Personal.objects.get(ci='123')
        r = self.client.patch(f'/api/auth/usuarios/{ficha.usuario_id}/', {'rol': 'tutor'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_un_admin_no_se_degrada_por_tener_ficha(self):
        adm = Usuario.objects.create_user(username='root', password='clave12345',
                                          nombres='R', apellidos='R', rol='admin')
        Personal.objects.create(usuario=adm, ci='1', rol='directora', fecha_ingreso='2026-01-01')
        adm.refresh_from_db()
        self.assertEqual(adm.rol, 'admin')

    def test_editar_datos_en_la_ficha_actualiza_el_usuario(self):
        self._alta()
        ficha = Personal.objects.get(ci='123')
        self.client.patch(f'/api/personal/personal/{ficha.id}/',
                          {'nombres': 'Laurita', 'telefono': '7111'}, format='json')
        ficha.usuario.refresh_from_db()
        self.assertEqual((ficha.usuario.nombres, ficha.usuario.telefono), ('Laurita', '7111'))

    # ── Detectar usuarios de personal sin ficha ────────────────────────
    def test_lista_marca_usuarios_sin_ficha_y_se_pueden_filtrar(self):
        u = Usuario.objects.create_user(username='sinficha', password='clave12345',
                                        nombres='S', apellidos='F', rol='educadora')
        self._alta()                                   # este sí tiene ficha
        r = self.client.get('/api/auth/usuarios/?sin_ficha=true')
        datos = r.data['results'] if 'results' in r.data else r.data
        nombres = [x['username'] for x in datos]
        self.assertIn('sinficha', nombres)
        self.assertNotIn('laura', nombres)          # ya tiene ficha
        sf = next(x for x in datos if x['username'] == 'sinficha')
        self.assertTrue(sf['requiere_ficha'])
        self.assertIsNone(sf['ficha_personal'])
        todos = self.client.get('/api/auth/usuarios/?search=laura')
        dl = todos.data['results'] if 'results' in todos.data else todos.data
        self.assertFalse(dl[0]['requiere_ficha'])
        self.assertIsNotNone(dl[0]['ficha_personal'])
