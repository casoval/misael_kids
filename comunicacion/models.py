"""
comunicacion/models.py
Mensajes individuales y avisos masivos a padres.
"""
from django.db import models
from core.models import ModeloBase


class Mensaje(ModeloBase):
    """Mensaje directo entre educadora/directora y tutor, vinculado a un niño."""
    remitente    = models.ForeignKey('accounts.Usuario', on_delete=models.CASCADE, related_name='mensajes_enviados')
    destinatario = models.ForeignKey('accounts.Usuario', on_delete=models.CASCADE, related_name='mensajes_recibidos')
    nino         = models.ForeignKey('ninos.Nino', on_delete=models.CASCADE, related_name='mensajes', null=True, blank=True)
    asunto       = models.CharField(max_length=200)
    cuerpo       = models.TextField()
    leido        = models.BooleanField(default=False)
    leido_en     = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Mensaje'
        ordering     = ['-created_at']

    def __str__(self):
        return f'{self.remitente} → {self.destinatario}: {self.asunto[:50]}'


class Aviso(ModeloBase):
    """Aviso masivo (circular) a padres de una sala, turno o sucursal completa."""
    autor        = models.ForeignKey('accounts.Usuario', on_delete=models.CASCADE)
    sucursal     = models.ForeignKey('core.Sucursal', on_delete=models.CASCADE, null=True, blank=True,
                                     help_text='Nulo = todas las sucursales')
    sala         = models.ForeignKey('core.Sala', on_delete=models.CASCADE, null=True, blank=True,
                                     help_text='Nulo = todas las salas de la sucursal')
    turno        = models.ForeignKey('core.Turno', on_delete=models.CASCADE, null=True, blank=True)
    titulo       = models.CharField(max_length=200)
    cuerpo       = models.TextField()
    importante   = models.BooleanField(default=False)
    publicado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Aviso'
        ordering     = ['-publicado_en']

    def __str__(self):
        return self.titulo
