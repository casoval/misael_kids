"""
core/pagination.py
Paginación estándar de la API.

El frontend pide listas grandes con `?page_size=200` (o 500, 1000) en casi
todas las pantallas, pero la clase por defecto de DRF (`PageNumberPagination`)
IGNORA ese parámetro salvo que se declare `page_size_query_param`. Resultado:
todas esas pantallas recibían solo los primeros 25 registros sin ningún aviso
(en la Agenda, por ejemplo, el calendario cargaba las 25 planificaciones más
antiguas de la historia y las del mes actual desaparecían al pasar de 25).
"""
from rest_framework.pagination import PageNumberPagination


class PaginacionEstandar(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 1000
