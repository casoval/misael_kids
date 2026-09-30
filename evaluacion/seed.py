"""
evaluacion/seed.py
Carga idempotente del catálogo de hitos. Lo comparten la migración de datos y
el comando `manage.py cargar_hitos`.

Reglas (para poder ejecutarlo las veces que sea sin efectos secundarios):
  - Un hito se considera "el mismo" si coincide su id o su par (nombre, área).
  - Si ya existe NO se toca (respeta lo que la directora haya editado).
  - Si falta (nunca cargado o borrado) se crea.
  - `actualizar=True` (solo desde el comando) sobrescribe edades y descripción
    de los que ya existen con los valores del catálogo.
"""
from .catalogo_hitos import HITOS


def cargar_catalogo(HitoModel, actualizar=False):
    creados = actualizados = omitidos = 0
    for h in HITOS:
        campos = {
            'edad_min_meses': h['edad_min_meses'],
            'edad_max_meses': h['edad_max_meses'],
            'descripcion':    h['descripcion'],
        }
        existente = (HitoModel.objects.filter(pk=h['id']).first()
                     or HitoModel.objects.filter(nombre=h['nombre'], area=h['area']).first())
        if existente is None:
            HitoModel.objects.create(id=h['id'], nombre=h['nombre'], area=h['area'],
                                     activo=True, **campos)
            creados += 1
        elif actualizar:
            for k, v in campos.items():
                setattr(existente, k, v)
            existente.save(update_fields=list(campos) + ['updated_at'])
            actualizados += 1
        else:
            omitidos += 1
    return creados, actualizados, omitidos
