"""
misael_link/centro_misael_client.py

Cliente delgado hacia la API de integración expuesta por Centro Misael
(app integracion_misael_kids del repo centro_terapias_v2).

Requiere en el .env de Misael Kids:
    CENTRO_MISAEL_API_URL=https://tu-centro-misael.com
    CENTRO_MISAEL_API_KEY=<misma clave que MISAEL_KIDS_API_KEY en Centro Misael>
"""
import requests
from django.conf import settings


class CentroMisaelNoConfigurado(Exception):
    """La URL o la API key de Centro Misael no están configuradas."""


class CentroMisaelError(Exception):
    """Error de red o respuesta inesperada de Centro Misael."""


def _base_url():
    if not settings.CENTRO_MISAEL_API_URL or not settings.CENTRO_MISAEL_API_KEY:
        raise CentroMisaelNoConfigurado(
            'CENTRO_MISAEL_API_URL / CENTRO_MISAEL_API_KEY no están configurados en el .env.'
        )
    return settings.CENTRO_MISAEL_API_URL.rstrip('/') + '/api/integracion/misael-kids'


def _headers():
    return {'Authorization': f'ApiKey {settings.CENTRO_MISAEL_API_KEY}'}


def _get(path, params=None, timeout=10):
    url = f'{_base_url()}{path}'
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise CentroMisaelError(f'No se pudo conectar con Centro Misael: {exc}') from exc

    if resp.status_code == 401:
        raise CentroMisaelError('API key rechazada por Centro Misael.')
    if resp.status_code == 404:
        return None
    if not resp.ok:
        raise CentroMisaelError(f'Centro Misael respondió {resp.status_code}: {resp.text[:300]}')
    return resp.json()


def buscar_pacientes(query):
    """Devuelve lista de pacientes (activos e inactivos) que calzan con `query`."""
    data = _get('/pacientes/buscar/', params={'q': query})
    return data or []


def obtener_paciente(paciente_id):
    """Detalle completo de un paciente, para copiar datos. None si no existe."""
    return _get(f'/pacientes/{paciente_id}/')


def listar_documentos_compartidos(paciente_id):
    """Documentos marcados por el profesional como 'Compartir con Misael Kids'."""
    data = _get(f'/pacientes/{paciente_id}/documentos/')
    return data or []


def descargar_archivo(url, timeout=30):
    """
    Descarga el archivo de un documento compartido.
    Sin headers de auth: `archivo_url` ya viene lista para descarga directa
    desde el storage (Cloudflare R2 / disco), no pasa por nuestra API key.
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise CentroMisaelError(f'No se pudo descargar el archivo: {exc}') from exc
    return resp.content
