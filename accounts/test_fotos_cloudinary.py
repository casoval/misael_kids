"""
Fotos: salen hacia Cloudinary (no a disco) y se validan tipo y tamaño.

Cloudinary se SIMULA (mock de cloudinary.uploader.upload): no hay credenciales
ni red en los tests. Lo que se prueba es nuestro cableado: que el storage por
defecto sea el de Cloudinary, que la API suba por ahí, que se guarde el
public_id devuelto y que la URL pública apunte a res.cloudinary.com.
"""
import io
import tempfile
from pathlib import Path
from unittest import mock

import cloudinary
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import Usuario
from ninos.serializers import DocumentoSerializer

STORAGES_CLOUDINARY = {
    'default':     {'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


def imagen(nombre='foto.png', formato='PNG', lado=20):
    buf = io.BytesIO()
    Image.new('RGB', (lado, lado), (200, 30, 30)).save(buf, formato)
    return SimpleUploadedFile(nombre, buf.getvalue(), content_type=f'image/{formato.lower()}')


class SubidaACloudinaryTests(TestCase):
    def setUp(self):
        self.u = Usuario.objects.create_user(email='e@x.test', password='1234',
                                             nombres='E', apellidos='T', rol='educadora')
        self.c = APIClient()
        self.c.force_authenticate(self.u)
        # La librería llama a cloudinary.config() al importarse por primera vez;
        # se importa ANTES de configurar para que no pise las credenciales de prueba.
        import cloudinary_storage.storage  # noqa: F401
        cloudinary.config(cloud_name='demo', api_key='1', api_secret='2', secure=True)

    def test_la_foto_se_sube_a_cloudinary_y_no_a_disco(self):
        with tempfile.TemporaryDirectory() as media, \
             override_settings(STORAGES=STORAGES_CLOUDINARY, MEDIA_ROOT=media), \
             mock.patch('cloudinary.uploader.upload',
                        return_value={'public_id': 'media/usuarios/foto_abc123'}) as subir:
            r = self.c.patch(f'/api/auth/usuarios/{self.u.id}/',
                             {'nombres': 'Con foto', 'foto': imagen()}, format='multipart')
            self.assertEqual(r.status_code, 200, r.data)

            # 1) Se llamó a Cloudinary como imagen. La librería antepone el prefijo
            #    'media/' (MEDIA_URL), así que en Cloudinary queda en media/usuarios/.
            self.assertEqual(subir.call_count, 1)
            opciones = subir.call_args.kwargs
            self.assertEqual(opciones['folder'], 'media/usuarios')
            self.assertEqual(opciones['resource_type'], 'image')

            # 2) En la BD queda el public_id y la URL pública es de Cloudinary
            self.u.refresh_from_db()
            self.assertEqual(self.u.foto.name, 'media/usuarios/foto_abc123')
            self.assertTrue(r.data['foto'].startswith('https://res.cloudinary.com/demo/'), r.data['foto'])
            self.assertTrue(r.data['foto'].endswith('/media/usuarios/foto_abc123'), r.data['foto'])
            self.assertNotIn('testserver', r.data['foto'])   # no es una URL local

            # 3) Nada se escribió en el disco del servidor
            self.assertEqual(list(Path(media).rglob('*.*')), [])


@override_settings(MAX_FOTO_MB=0.0005)   # ~524 bytes: una foto real lo supera
class ValidacionFotoTests(TestCase):
    def setUp(self):
        self.u = Usuario.objects.create_user(email='e@x.test', password='1234',
                                             nombres='E', apellidos='T', rol='educadora')
        self.c = APIClient()
        self.c.force_authenticate(self.u)

    def test_foto_demasiado_pesada_da_400_no_500(self):
        r = self.c.patch(f'/api/auth/usuarios/{self.u.id}/',
                         {'foto': imagen(lado=200)}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertIn('foto', r.data)
        self.assertIn('pesa más de', str(r.data['foto']))

    @override_settings(MAX_FOTO_MB=8)
    def test_foto_de_tamano_normal_se_acepta(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            r = self.c.patch(f'/api/auth/usuarios/{self.u.id}/', {'foto': imagen()}, format='multipart')
        self.assertEqual(r.status_code, 200, r.data)

    @override_settings(MAX_FOTO_MB=8)
    def test_formato_no_permitido_se_rechaza(self):
        falso = SimpleUploadedFile('virus.exe', b'MZ\x90\x00', content_type='image/png')
        r = self.c.patch(f'/api/auth/usuarios/{self.u.id}/', {'foto': falso}, format='multipart')
        self.assertEqual(r.status_code, 400)


class ValidacionDocumentoTests(TestCase):
    def _errores(self, archivo):
        s = DocumentoSerializer(data={'tipo': 'otro', 'nombre': 'x', 'archivo': archivo})
        s.is_valid()
        return s.errors.get('archivo')

    def test_pdf_e_imagenes_se_aceptan(self):
        for nombre in ('a.pdf', 'a.jpg', 'a.PNG', 'a.webp'):
            f = SimpleUploadedFile(nombre, b'%PDF-1.4 x', content_type='application/octet-stream')
            self.assertIsNone(self._errores(f), nombre)

    def test_formatos_peligrosos_o_raros_se_rechazan(self):
        for nombre in ('a.exe', 'a.html', 'a.svg', 'a.js', 'a.docx', 'sinextension'):
            f = SimpleUploadedFile(nombre, b'x')
            self.assertIsNotNone(self._errores(f), nombre)

    @override_settings(MAX_DOC_MB=0.0001)
    def test_documento_demasiado_pesado_se_rechaza(self):
        f = SimpleUploadedFile('a.pdf', b'%PDF' + b'0' * 500)
        self.assertIn('pesa más de', str(self._errores(f)))
