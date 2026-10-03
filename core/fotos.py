"""
core/fotos.py
Utilidad para exponer la foto de un niño en las respuestas de la API.

Se usa en las vistas que arman diccionarios a mano (p. ej. el libro de caja).
Los serializers usan directamente `serializers.ImageField(source='...foto')`.
"""


def url_foto(request, foto):
    """URL (absoluta si hay request) de una ImageField, o None si no tiene foto
    o si el archivo no está disponible."""
    if not foto:
        return None
    try:
        url = foto.url
    except Exception:
        return None
    return request.build_absolute_uri(url) if request else url
