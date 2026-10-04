"""
core/validators.py
Validación de archivos subidos (fotos, documentos, comprobantes).

Sin esto, una foto de 15 MB llega hasta Cloudinary, que la rechaza por tamaño
y la API responde 500 en vez de un 400 con un mensaje entendible. También evita
que se suban formatos que ni el storage ni nadie espera (.exe, .html, .svg...).

Límites ajustables por entorno: MAX_FOTO_MB (8) y MAX_DOC_MB (10).
(El plan gratuito de Cloudinary admite hasta 10 MB por archivo.)
"""
import os

from django.conf import settings
from rest_framework import serializers

EXT_FOTO = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
EXT_DOCUMENTO = EXT_FOTO | {'.pdf'}


def _validar(archivo, extensiones, limite_mb, que):
    if not archivo:
        return archivo
    ext = os.path.splitext(getattr(archivo, 'name', '') or '')[1].lower()
    if ext not in extensiones:
        permitidas = ', '.join(sorted(e.lstrip('.') for e in extensiones))
        raise serializers.ValidationError(
            f'Formato no permitido para {que}. Usa: {permitidas}.')
    tamano = getattr(archivo, 'size', None)
    if tamano is not None and tamano > limite_mb * 1024 * 1024:
        raise serializers.ValidationError(
            f'{que.capitalize()} pesa más de {limite_mb:g} MB. Reduce su tamaño e inténtalo de nuevo.')
    return archivo


def validar_foto(archivo):
    return _validar(archivo, EXT_FOTO, getattr(settings, 'MAX_FOTO_MB', 8), 'la foto')


def validar_documento(archivo):
    return _validar(archivo, EXT_DOCUMENTO, getattr(settings, 'MAX_DOC_MB', 10), 'el archivo')


class ValidaArchivosMixin:
    """Mezclar en un ModelSerializer: DRF llama a validate_<campo> automáticamente."""

    def validate_foto(self, valor):
        return validar_foto(valor)

    def validate_archivo(self, valor):
        return validar_documento(valor)

    def validate_comprobante(self, valor):
        return validar_documento(valor)
