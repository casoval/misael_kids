"""
Tests de regresión de la auditoría de seguridad.

Cada clase reproduce un hallazgo: ANTES del arreglo el test fallaba
(el ataque funcionaba); AHORA debe pasar.
"""
import json
import os
import subprocess
import sys
import warnings
from datetime import date
from pathlib import Path

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Usuario
from comunicacion.models import Mensaje
from core.models import Sucursal
from personal.models import Personal

FRONTEND = Path(__file__).resolve().parent.parent / 'frontend'
CLAVE_FUERTE = 'Zorro-Azul-7391'


def crear(rol, nombre):
    return Usuario.objects.create_user(
        email=f'{nombre}@x.test', password='clave-Inicial-5521',
        nombres=nombre.title(), apellidos='Test', rol=rol)


def cliente(usuario):
    c = APIClient()
    c.force_authenticate(usuario)
    return c


class ResetPasswordTests(TestCase):
    """Una directora NO puede tomar la cuenta de un admin reseteándole la clave."""

    def setUp(self):
        self.admin = crear('admin', 'admin')
        self.directora = crear('directora', 'directora')
        self.educadora = crear('educadora', 'educadora')

    def _reset(self, quien, objetivo, password=CLAVE_FUERTE):
        return cliente(quien).post(
            f'/api/auth/usuarios/{objetivo.id}/resetear-password/',
            {'password': password}, format='json')

    def test_directora_no_puede_resetear_a_un_admin(self):
        r = self._reset(self.directora, self.admin)
        self.assertEqual(r.status_code, 403)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.check_password(CLAVE_FUERTE))
        self.assertTrue(self.admin.check_password('clave-Inicial-5521'))

    def test_admin_si_puede_resetear_a_una_directora(self):
        self.assertEqual(self._reset(self.admin, self.directora).status_code, 200)
        self.directora.refresh_from_db()
        self.assertTrue(self.directora.check_password(CLAVE_FUERTE))

    def test_directora_puede_resetear_a_una_educadora(self):
        self.assertEqual(self._reset(self.directora, self.educadora).status_code, 200)

    def test_educadora_no_puede_resetear_a_nadie(self):
        # Para un rol sin permisos, get_queryset solo le muestra su propio usuario;
        # sobre otro devuelve 404 y sobre sí misma 403. Nunca 200.
        self.assertIn(self._reset(self.educadora, self.directora).status_code, (403, 404))
        self.assertEqual(self._reset(self.educadora, self.educadora).status_code, 403)

    def test_reset_con_menos_de_4_caracteres_es_rechazado(self):
        r = self._reset(self.admin, self.educadora, password='abc')
        self.assertEqual(r.status_code, 400)
        self.educadora.refresh_from_db()
        self.assertFalse(self.educadora.check_password('abc'))

    def test_reset_acepta_cualquier_clave_de_4_o_mas(self):
        for clave in ('1234', '12345678', 'password', 'aaaa'):
            self.assertEqual(self._reset(self.admin, self.educadora, password=clave).status_code,
                             200, clave)
            self.educadora.refresh_from_db()
            self.assertTrue(self.educadora.check_password(clave), clave)

    def test_reset_sin_clave_genera_una_aleatoria(self):
        r = cliente(self.admin).post(
            f'/api/auth/usuarios/{self.educadora.id}/resetear-password/', {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.educadora.refresh_from_db()
        self.assertTrue(self.educadora.check_password(r.data['password']))


class ValidadoresContrasenaTests(TestCase):
    """Regla única: 4 o más caracteres, sin ninguna otra exigencia."""
    def setUp(self):
        self.admin = crear('admin', 'admin')

    def _crear(self, password):
        return cliente(self.admin).post('/api/auth/usuarios/', {
            'username': 'nuevo', 'nombres': 'N', 'apellidos': 'U', 'rol': 'educadora',
            'password': password, 'password2': password}, format='json')

    def test_crear_usuario_rechaza_menos_de_4_caracteres(self):
        for corta in ('123', 'abc', 'a'):
            r = self._crear(corta)
            self.assertEqual(r.status_code, 400, corta)
            self.assertIn('password', r.data)
        self.assertFalse(Usuario.objects.filter(username='nuevo').exists())

    def test_crear_usuario_acepta_cualquier_clave_de_4_o_mas(self):
        # Sin exigir complejidad: numéricas, comunes y repetidas son válidas.
        for i, clave in enumerate(('1234', '12345678', 'password', 'aaaa', CLAVE_FUERTE)):
            r = cliente(self.admin).post('/api/auth/usuarios/', {
                'username': f'nuevo{i}', 'nombres': 'N', 'apellidos': 'U', 'rol': 'educadora',
                'password': clave, 'password2': clave}, format='json')
            self.assertEqual(r.status_code, 201, clave)

    def test_cambiar_password_rechaza_menos_de_4(self):
        r = cliente(self.admin).post('/api/auth/usuarios/cambiar-password/', {
            'password_actual': 'clave-Inicial-5521',
            'password_nuevo': '123', 'password_nuevo2': '123'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('clave-Inicial-5521'))

    def test_cambiar_password_acepta_4_caracteres_numericos(self):
        r = cliente(self.admin).post('/api/auth/usuarios/cambiar-password/', {
            'password_actual': 'clave-Inicial-5521',
            'password_nuevo': '1234', 'password_nuevo2': '1234'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('1234'))


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()   # el contador de throttling vive en la caché
        self.addCleanup(cache.clear)
        self.usuario = crear('directora', 'dir')

    def test_fuerza_bruta_es_bloqueada_con_429(self):
        c = APIClient()
        codigos = [c.post('/api/auth/login/', {'email': 'dir@x.test', 'password': f'mal{i}'},
                          format='json').status_code for i in range(25)]
        self.assertEqual(codigos[0], 400)
        self.assertIn(429, codigos)
        # Una vez bloqueado, ni siquiera la clave CORRECTA entra (hasta que pase la ventana).
        r = c.post('/api/auth/login/', {'email': 'dir@x.test', 'password': 'clave-Inicial-5521'},
                   format='json')
        self.assertEqual(r.status_code, 429)

    def test_login_normal_sigue_funcionando(self):
        r = APIClient().post('/api/auth/login/', {'email': 'dir@x.test',
                             'password': 'clave-Inicial-5521'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)

    def test_usuario_inexistente_y_clave_mala_dan_el_mismo_mensaje(self):
        c = APIClient()
        a = c.post('/api/auth/login/', {'email': 'no@existe.test', 'password': 'x'}, format='json')
        b = c.post('/api/auth/login/', {'email': 'dir@x.test', 'password': 'x'}, format='json')
        self.assertEqual((a.status_code, a.data), (b.status_code, b.data))


class AsistenciaPersonalPermisosTests(TestCase):
    """Un tutor (u otro rol no directivo) NO puede ver ni tocar la asistencia del personal."""
    URL = '/api/personal/asistencia-personal/'

    def setUp(self):
        self.admin = crear('admin', 'admin')
        self.directora = crear('directora', 'directora')
        self.tutor = crear('tutor', 'tutor')
        self.educadora = crear('educadora', 'educadora')
        self.recep = crear('recepcionista', 'recep')
        self.suc = Sucursal.objects.create(nombre='S', direccion='d')
        self.personal = Personal.objects.create(
            usuario=self.educadora, nombres='E', apellidos='T', ci='1',
            rol='educadora', fecha_ingreso=date.today())
        self.cuerpo = {'personal': str(self.personal.id), 'sucursal': str(self.suc.id),
                       'fecha': '2026-10-01', 'estado': 'ausente'}

    def test_roles_no_directivos_reciben_403(self):
        for u in (self.tutor, self.educadora, self.recep):
            c = cliente(u)
            self.assertEqual(c.get(self.URL).status_code, 403, u.rol)
            self.assertEqual(c.post(self.URL, self.cuerpo, format='json').status_code, 403, u.rol)

    def test_admin_y_directora_pueden_gestionarla(self):
        for u in (self.admin, self.directora):
            c = cliente(u)
            self.assertEqual(c.get(self.URL).status_code, 200)
        r = cliente(self.directora).post(self.URL, self.cuerpo, format='json')
        self.assertEqual(r.status_code, 201)

    def test_tutor_no_puede_borrar_ni_editar_un_registro(self):
        r = cliente(self.directora).post(self.URL, self.cuerpo, format='json')
        url = f'{self.URL}{r.data["id"]}/'
        c = cliente(self.tutor)
        self.assertEqual(c.patch(url, {'estado': 'presente'}, format='json').status_code, 403)
        self.assertEqual(c.delete(url).status_code, 403)


class EdicionPropiaMultipartTests(TestCase):
    """PATCH del propio perfil con multipart (subida de foto) daba HTTP 500."""

    def setUp(self):
        self.edu = crear('educadora', 'edu')

    def test_multipart_no_explota_y_actualiza(self):
        r = cliente(self.edu).patch(f'/api/auth/usuarios/{self.edu.id}/',
                                    {'nombres': 'Nuevo', 'telefono': '7000'}, format='multipart')
        self.assertEqual(r.status_code, 200)
        self.edu.refresh_from_db()
        self.assertEqual(self.edu.nombres, 'Nuevo')

    def test_multipart_con_archivo_no_explota(self):
        # Imagen PNG válida mínima (1x1)
        png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06'
               b'\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe'
               b'\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82')
        from django.test import override_settings
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            r = cliente(self.edu).patch(
                f'/api/auth/usuarios/{self.edu.id}/',
                {'nombres': 'Con foto', 'foto': SimpleUploadedFile('a.png', png, 'image/png')},
                format='multipart')
        self.assertNotEqual(r.status_code, 500)

    def test_no_puede_auto_ascenderse_ni_por_multipart_ni_por_json(self):
        c = cliente(self.edu)
        for fmt in ('multipart', 'json'):
            r = c.patch(f'/api/auth/usuarios/{self.edu.id}/', {'rol': 'admin', 'nombres': 'X'}, format=fmt)
            self.assertEqual(r.status_code, 200, fmt)
            self.edu.refresh_from_db()
            self.assertEqual(self.edu.rol, 'educadora', fmt)

    def test_no_puede_cambiarse_el_estado_activo(self):
        cliente(self.edu).patch(f'/api/auth/usuarios/{self.edu.id}/', {'activo': False}, format='json')
        self.edu.refresh_from_db()
        self.assertTrue(self.edu.activo)


class MensajesTests(TestCase):
    def setUp(self):
        self.admin = crear('admin', 'admin')
        self.tutor = crear('tutor', 'tutor')

    def test_remitente_lo_fija_el_servidor_y_no_hace_falta_enviarlo(self):
        # El panel NO envía `remitente`: antes devolvía 400.
        r = cliente(self.tutor).post('/api/comunicacion/mensajes/', {
            'destinatario': str(self.admin.id), 'asunto': 'Hola', 'cuerpo': 'x'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(str(r.data['remitente']), str(self.tutor.id))

    def test_no_se_puede_suplantar_al_remitente(self):
        r = cliente(self.tutor).post('/api/comunicacion/mensajes/', {
            'remitente': str(self.admin.id), 'destinatario': str(self.admin.id),
            'asunto': 'Hola', 'cuerpo': 'x'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Mensaje.objects.get().remitente_id, self.tutor.id)

    def test_marcar_leido_usa_hora_con_zona_horaria(self):
        m = Mensaje.objects.create(remitente=self.admin, destinatario=self.tutor, asunto='a', cuerpo='b')
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter('always')
            r = cliente(self.tutor).post(f'/api/comunicacion/mensajes/{m.id}/marcar-leido/')
        self.assertEqual(r.status_code, 200)
        m.refresh_from_db()
        self.assertTrue(m.leido)
        self.assertTrue(timezone.is_aware(m.leido_en))
        self.assertFalse([a for a in avisos if 'naive datetime' in str(a.message)])


class StorageCloudinaryTests(SimpleTestCase):
    """
    Django 5.1 ignora DEFAULT_FILE_STORAGE: Cloudinary nunca se activaba.
    Se comprueba en un subproceso porque los settings se evalúan al importar.
    """

    def _storage(self, settings_module, con_cloudinary):
        env = {k: v for k, v in os.environ.items() if not k.startswith('CLOUDINARY_')}
        env.update(DJANGO_SETTINGS_MODULE=settings_module, DJANGO_SECRET_KEY='x' * 60,
                   DJANGO_DEBUG='False', DB_NAME='x', DB_USER='x', DB_PASSWORD='x')
        if con_cloudinary:
            env.update(CLOUDINARY_CLOUD_NAME='demo', CLOUDINARY_API_KEY='1', CLOUDINARY_API_SECRET='2')
        codigo = ("import django; django.setup();"
                  "from django.core.files.storage import storages;"
                  "s=storages['default']; print(type(s).__module__+'.'+type(s).__name__)")
        out = subprocess.run([sys.executable, '-c', codigo], env=env, capture_output=True,
                             text=True, cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        return out.stdout.strip()

    def test_con_credenciales_usa_cloudinary_en_test_y_en_produccion(self):
        for modulo in ('config.settings.test', 'config.settings.production'):
            self.assertEqual(self._storage(modulo, True),
                             'cloudinary_storage.storage.MediaCloudinaryStorage', modulo)

    def test_sin_credenciales_cae_a_disco_local(self):
        for modulo in ('config.settings.test', 'config.settings.production'):
            self.assertEqual(self._storage(modulo, False),
                             'django.core.files.storage.filesystem.FileSystemStorage', modulo)


class FrontendEscapeTests(SimpleTestCase):
    """
    Regresión estática del XSS almacenado: el texto libre que viene de la API
    no puede interpolarse crudo en las páginas que se renderizan con innerHTML.
    (No sustituye una prueba en navegador, pero impide que vuelvan estas líneas.)
    """
    CRUDOS = {
        'pages/panel/comunicacion.html': [
            '${av.titulo}', '${av.cuerpo}', '${m.asunto}', '${mensajeAbierto.cuerpo}',
            '${m.cuerpo?.slice', '${av.autor_nombre}', "av.titulo}')",
        ],
        'pages/panel/salud.html': [
            '${inc.descripcion}', '${inc.accion_tomada}', '${inc.nino_nombre}',
            "${inc.nino_nombre}')",
        ],
        'pages/portal/inicio.html': [
            '${m.asunto}', '${m.cuerpo}', '${m.remitente_nombre}', '${p.observaciones}',
            '${p.actividades}', '${plan.descripcion}', '${obj.descripcion}', '${h.nombre_completo}',
        ],
    }

    def test_no_hay_interpolaciones_crudas_de_texto_libre(self):
        for ruta, patrones in self.CRUDOS.items():
            html = (FRONTEND / ruta).read_text(encoding='utf-8')
            for p in patrones:
                self.assertNotIn(p, html, f'{ruta}: interpolación sin escapar {p!r}')

    def test_helper_escHtml_existe_y_las_paginas_lo_usan(self):
        self.assertIn('function escHtml', (FRONTEND / 'js/api.js').read_text(encoding='utf-8'))
        for ruta in self.CRUDOS:
            self.assertIn('escHtml(', (FRONTEND / ruta).read_text(encoding='utf-8'), ruta)

    def test_ids_y_textos_no_se_inyectan_en_onclick(self):
        com = (FRONTEND / 'pages/panel/comunicacion.html').read_text(encoding='utf-8')
        sal = (FRONTEND / 'pages/panel/salud.html').read_text(encoding='utf-8')
        self.assertNotIn("eliminarAviso('${av.id}','", com)
        self.assertNotIn("incidente de ${inc.nino_nombre}", sal)
