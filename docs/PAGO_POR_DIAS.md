# Modalidad "por día": cómo funciona

> La modalidad **mensual** no cambió. Todo lo de abajo aplica solo a inscripciones con `modalidad_pago='diaria'`.

## Inscripción
- `fecha_inicio` = **primer día de asistencia**. No hay `fecha_fin` al inscribir (puede continuar, volver otro día o pasar a mensual).
- `dias_semana` (opcional, `[0..6]`, 0 = lunes). Vacío = todos los días. Con valores, el niño solo aparece en la
  planilla esos días y una falta sin aviso solo se cobra esos días. Un "presente" en otro día igual se cobra.
- Aparece en la planilla de asistencia desde `fecha_inicio` (la mensual se lista igual que siempre).

## Regla de cobro (según la asistencia del día)
| Asistencia | Cobro |
|---|---|
| Presente | Se cobra |
| Ausente (sin aviso) | Se cobra, si era un día esperado |
| Ausente justificado | No se cobra (falta avisada) |

Cambiar la asistencia después anula o reactiva el cobro del día (misma mecánica de antes). Borrar el registro
de asistencia de un día cobrado también anula ese cobro (si no tiene pagos reales).

## Dinero: abonos y saldo a favor
- `POST /inscripciones/{id}/registrar-abono/` registra dinero entregado por el tutor (por adelantado o después). Lleva recibo propio.
- El abono es un **saldo a favor**. Al generarse cobros diarios, se cubren solos del más antiguo al más nuevo
  (`services.aplicar_saldo`). Cada cobro cubierto recibe un `Pago` con `abono_origen` (sin recibo propio).
- **Caja**: entra el abono (el día que se recibió). Los pagos con `abono_origen` **no** se suman (no hay doble conteo).
- Si un día ya cubierto pasa a "justificado", su dinero vuelve al saldo y cubre otros días abiertos.
- Un pago real, devolución o condonación sobre el cobro sigue bloqueando la anulación automática.

## Control de días acordados
`DiasContratados` guarda el historial (inicial / ampliación / reducción): "empezó con 5 días, luego 10".
Es informativo: `GET /inscripciones/{id}/resumen-diario/` devuelve saldo, deuda, días acordados vs cobrados,
conteo de asistencia, abonos y alertas (`excedido`, `completo`, `deuda`, `saldo_agotado`).
`POST .../contratar-dias/` ajusta días; `registrar-abono` con `dias` los suma a los acordados.

## Cambio de modalidad
`POST /inscripciones/{id}/cambiar-modalidad/` (por día ⇄ mensual). Cierra la inscripción actual
(`activa=False`, `fecha_fin`) y crea una nueva enlazada (`inscripcion_origen`); el historial no se toca.
Hereda ajuste/beca y precios negociados. Al pasar a mensual, el saldo a favor se aplica a la primera mensualidad;
los días adeudados quedan en la inscripción cerrada (no bloquean la mensualidad) y se informan en la respuesta.
`transferir` también conserva saldo, días acordados y `dias_semana` de una inscripción por día.

## Corrección incluida
`transferir` hacia una mensualidad fallaba (`TypeError`, 500) porque la fecha quedaba como texto. Ahora se convierte a `date`.

---

# Cambio de turno / sala / sucursal en mensualidad, baja y saldo a cuenta

## Transferir una mensualidad (mensual → mensual) con un ciclo en curso
El mes en curso **no se duplica**: pasa a la inscripción nueva (que se ancla al inicio de ese ciclo, así los meses
siguientes siguen alineados) y solo se compensa la diferencia de precio contra lo ya pagado.

| Caso | Qué pasa |
|---|---|
| El turno nuevo cuesta igual | Nada cambia: solo cambia de sala/turno/sucursal. Se conserva un precio negociado. |
| Cuesta menos y sobra dinero | El sobrante pasa a la **cuenta** del niño (saldo a favor) y descuenta su próxima mensualidad. |
| Cuesta más | El mes queda con lo que falta por cobrar (parcial). |
| Pagó menos y ya no completa el mes | `cerrar_con_lo_pagado: true` + `motivo_cierre` → se condona lo que falta (igual que "Cerrar con lo pagado"). |

- `POST /inscripciones/{id}/transferir/` con `simular: true` devuelve el plan sin cambiar nada (la pantalla lo usa como vista previa).
- Si no hay ciclo en curso, o la modalidad cambia, se comporta como antes (se genera un ciclo nuevo).
- Los ciclos anteriores sin pagar se quedan en la inscripción cerrada como deuda y se avisa.
- Precio: si el turno nuevo tiene el mismo precio de lista que el actual, se conserva el precio de la inscripción;
  si no, rige el del turno nuevo. Un `costo_mensual`/`costo_diario` explícito manda sobre ambos.

## Cuenta del niño (saldo a favor) en mensualidad
- La diferencia a favor se registra con dos movimientos **internos** que no tocan la caja:
  `Devolucion(a_cuenta=True)` sobre el cobro y `AbonoDiario(es_traspaso=True)` en la inscripción nueva.
- `generar_ciclo_mensual` aplica el saldo a favor al ciclo nuevo automáticamente (sin saldo no hace nada).
- La caja y los movimientos excluyen `a_cuenta` y `es_traspaso`: el dinero cuenta una sola vez, cuando se pagó.

## Baja y regreso
- `POST /inscripciones/{id}/cerrar/` da de baja (`activa=False`, `fecha_fin`). Los ciclos mensuales futuros sin pagos se anulan;
  con pagos solo se avisa. `cerrar_con_lo_pagado` + `motivo_cierre` salda el ciclo en curso. Informa deuda pendiente y saldo a favor.
- Si el niño regresa se crea una **inscripción nueva** (la regla de "una sola activa por niño" no cambia) y su saldo a favor pasa
  a ella automáticamente; en mensual cubre su primer ciclo.
- Al pasar de por día a mensual, el saldo que sobre ya no se queda en la inscripción cerrada: pasa a la mensual.

## Devolver el saldo a favor
Es la **misma `Devolucion`** de siempre (mismo recibo, método y motivo; sale de caja como egreso), solo que en vez de
colgar de un cobro cuelga de la **inscripción** (`Devolucion.inscripcion`, con una restricción: o cobro o inscripción, nunca ambos).
- `POST /inscripciones/{id}/devolver-saldo/` con `monto` (hasta el saldo disponible), `motivo` (obligatorio), `metodo_pago`, `fecha`.
  Funciona también en inscripciones cerradas, que es el caso típico.
- Descuenta el saldo y lo que se devuelve se resta de los abonos (`AbonoDiario.devuelto`), del más antiguo al más nuevo, así ese
  dinero no se vuelve a aplicar a ningún cobro. Si el niño regresa, solo pasa a la inscripción nueva lo que no se devolvió.
- En la baja: `devolver_saldo: true` (+ `metodo_pago`) devuelve todo el saldo en el mismo paso y deja el recibo.
- En la pantalla: botón "Devolver saldo" en el panel de pagos (mensual y por día) y casilla en "Dar de baja".
- Las devoluciones `a_cuenta` (movimiento interno al cambiar de turno) siguen sin tocar la caja; esta sí.

## Estado de pago y días acordados (política: pago por adelantado)

- **Días acordados** = los días elegidos en el calendario de la inscripción. Ya no se suman por separado
  los "días que cubre" de un abono: aumentar o disminuir días en el calendario actualiza el contador al instante.
  (Solo las inscripciones antiguas, sin calendario, siguen usando el historial de ajustes.)
- **Monto a pagar** = días acordados × costo por día. **Pagado** = lo abonado + lo pagado en cobros, menos devoluciones.
  **Falta pagar** = monto − pagado. Si falta algo, la inscripción queda con *Deuda pendiente*.
- `GET /inscripciones/inscripciones/` devuelve `estado_pago` (por día y mensual) y la lista lo muestra
  como columna "Estado de pago", con una alerta arriba que enumera a quienes tienen deuda.
- `resumen_diario` expone `cuenta` con el desglose (`monto_acordado`, `pagado_total`, `falta_pagar`, `dias_pagados`...).
- En el calendario del modal de Pagos, los días acordados se pintan como *pagados por adelantado* (azul) o
  *sin pagar* (rojo), según cuántos días cubre el dinero ya recibido, en orden cronológico.

### Días a favor (permisos y pagos de más)
Con calendario, el saldo a favor se reparte entre los días acordados que aún no se consumieron. Los días
pagados que sobran son **días a favor** (`cuenta.dias_a_favor`, `monto_a_favor`); `dias_a_favor_permiso` indica
cuántos vienen de una falta avisada (no se cobra). La lista los muestra en azul bajo "Estado de pago", el modal
de Pagos agrega una alerta, y se puede filtrar con `?estado_pago=a_favor`. Se resuelven reprogramando el día en
"Ajustar días" o devolviendo el saldo.
