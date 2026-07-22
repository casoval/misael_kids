# 🌟 Misael Kids — Frontend Web

Interfaz HTML + JavaScript vanilla que consume la API REST del backend Django.
Estilo **"Jardín mágico"**: colorido, amigable, funcional.

---

## 📁 Estructura de archivos

```
misael_kids_frontend/
├── css/
│   ├── variables.css          ← Variables CSS (colores, tipografía, espaciado)
│   └── base.css               ← Componentes globales (sidebar, cards, tablas, modales...)
├── js/
│   └── api.js                 ← Cliente API, Auth JWT, helpers UI
├── pages/
│   ├── panel/                 ← Panel interno (directora, educadoras, admin)
│   │   ├── dashboard.html     ✅ Dashboard con stats y resúmenes
│   │   ├── asistencia.html    ✅ Registro diario por sala/turno, marcar masivo
│   │   ├── ninos.html         ✅ Listado, búsqueda, perfil lateral, registro
│   │   ├── cobros.html        ✅ Gestión de cobros, pagos, generación masiva
│   │   ├── inventario.html    ✅ Stock por sucursal, movimientos, alertas
│   │   ├── agenda.html        ✅ Calendario pedagógico, planificaciones, planes individuales
│   │   ├── sucursales.html    ✅ CRUD sucursales, salas y turnos
│   │   ├── reportes.html      ✅ Gráficos CSS, exportaciones CSV
│   │   ├── inscripciones.html ⚠️  Stub funcional (datos en bruto desde API)
│   │   ├── personal.html      ⚠️  Stub funcional
│   │   ├── salud.html         ⚠️  Stub funcional
│   │   ├── comunicacion.html  ⚠️  Stub funcional
│   │   └── evaluacion.html    ⚠️  Stub funcional
│   └── portal/                ← Portal de padres/tutores
│       └── inicio.html        ✅ Bitácora, asistencia, cobros, mensajes,
│                                  desarrollo, justificar ausencia
└── login.html                 ✅ Login compartido con detección de rol
```

---

## 🚀 Cómo usar

### Opción A — Abrir directamente en el navegador (sin servidor)

> ⚠️ Por seguridad, los navegadores modernos bloquean `fetch()` en archivos locales (`file://`).
> Necesitas un servidor HTTP local.

```bash
# Python (desde la carpeta misael_kids_frontend)
python -m http.server 3000

# O con Node.js (npx)
npx serve .

# O con VS Code: instala la extensión "Live Server" y haz clic en "Go Live"
```

Luego abre: **http://localhost:3000/login.html**

### Opción B — Servir desde Django

Copia la carpeta `misael_kids_frontend` dentro de `misael_kids/static/frontend/` y
configura Django para servir archivos estáticos. El acceso sería:
`http://localhost:8000/static/frontend/login.html`

---

## 🔗 Conexión con la API

Todas las páginas usan el archivo `js/api.js` que apunta a:
```javascript
const API_BASE = 'http://localhost:8000/api';
```

Si tu backend corre en otro puerto o dominio, cambia esa línea.
También asegúrate de que CORS esté configurado en Django para permitir
requests desde el origen del frontend (`http://localhost:3000`).

---

## 🔑 Credenciales de prueba

```
Email:    admin@misaelkids.com
Password: Admin1234!
Rol:      Administrador (acceso total al panel interno)
```

---

## 📱 Flujo de login

1. El usuario abre `login.html`
2. Selecciona su tab: **Personal** (directora/educadora) o **Padres**
3. Ingresa email y contraseña
4. El sistema llama a `/api/auth/login/` y obtiene el JWT
5. Según el rol del usuario, redirige automáticamente:
   - `admin`, `directora`, `educadora`, `ayudante`, `administrativo`, `cocina` → `pages/panel/dashboard.html`
   - `tutor` → `pages/portal/inicio.html`
6. El token se guarda en `localStorage` (`mk_token`, `mk_refresh`, `mk_usuario`)
7. Todas las requests llevan `Authorization: Bearer <token>`
8. Si el token expira, se refresca automáticamente con el refresh token
9. Si el refresh también expira, se redirige al login

---

## 🎨 Sistema de diseño

### Paleta de colores
| Variable         | Color     | Uso                              |
|------------------|-----------|----------------------------------|
| `--turquesa`     | `#2DD4BF` | Color principal, botones primarios |
| `--coral`        | `#FF6B6B` | Alertas, errores, ausencias       |
| `--amarillo`     | `#FFD93D` | Advertencias, pendientes          |
| `--verde`        | `#6BCB77` | Éxito, presentes, pagados         |
| `--violeta`      | `#A78BFA` | Planes individuales, Misael        |
| `--naranja`      | `#FB923C` | Alertas secundarias               |

### Tipografía
- **Fredoka One** — Títulos, números grandes (`font-family: var(--font-display)`)
- **Nunito** — Texto, etiquetas, botones (`font-family: var(--font-body)`)

### Componentes disponibles (en `base.css`)
- `.card` + `.card-header` + `.card-titulo` — Tarjeta estándar
- `.stat-card` + `.stat-icon` + `.stat-info` — Tarjeta de estadística
- `.btn`, `.btn-primary`, `.btn-coral`, `.btn-amarillo`, `.btn-outline` — Botones
- `.chip-verde`, `.chip-coral`, `.chip-turquesa`, etc. — Chips/badges
- `.form-grupo` + `.form-input` + `.form-select` + `.form-textarea` — Formularios
- `.tabla-wrap` + `table` + `thead th` + `tbody td` — Tablas
- `.modal-overlay` + `.modal` — Modales con animación
- `.alerta-exito`, `.alerta-peligro`, `.alerta-info`, `.alerta-warn` — Alertas
- `.loader` + `.spinner` — Estados de carga
- `.grid-2`, `.grid-3`, `.grid-4`, `.grid-stats` — Grids responsivos

### Helpers de JS (en `api.js`)
```javascript
UI.toast('Mensaje', 'exito|error|info|warn')   // Notificación flotante
UI.abrirModal('id-del-modal')                   // Abrir modal
UI.cerrarModal('id-del-modal')                  // Cerrar modal
UI.mostrarLoader(contenedor, 'mensaje')          // Loader en contenedor
UI.vacio(contenedor, 'mensaje', '🎨')           // Estado vacío
UI.llenarSelect(selectEl, lista, 'id', 'nombre') // Llenar <select>
UI.iniciales('Juan Pérez')                       // → 'JP'
UI.fecha('2025-06-15')                           // → '15 jun 2025'
UI.moneda(700.50)                                // → 'Bs. 700.50'
UI.chipEstadoCobro('pendiente')                  // → HTML chip
UI.chipAsistencia('presente')                    // → HTML chip
```

---

## 📄 Páginas completamente implementadas

### Panel interno
| Página | Descripción | Características destacadas |
|--------|-------------|---------------------------|
| `login.html` | Login compartido | Tabs por rol, JWT automático, redirige según rol |
| `dashboard.html` | Inicio del panel | Stats en tiempo real, asistencia de hoy, alertas, avisos |
| `asistencia.html` | Asistencia diaria | Grid de tarjetas por niño, marcar masivo, cobro diario automático, exportar CSV |
| `ninos.html` | Gestión de niños | Búsqueda en tiempo real, paginación, panel lateral de perfil, alergias destacadas |
| `cobros.html` | Gestión de cobros | Stats financieras, registrar pagos, generación masiva de mensualidades, exportar CSV |
| `inventario.html` | Inventario | Grid visual con barra de stock, movimientos, alertas automáticas |
| `agenda.html` | Agenda pedagógica | Calendario mensual, planificaciones grupales, planes individuales con objetivos |
| `sucursales.html` | Admin sucursales | CRUD sucursales, salas y turnos inline |
| `reportes.html` | Reportes | Gráficos de barras CSS, 4 exportaciones CSV con BOM para Excel |

### Portal de padres
| Página | Secciones |
|--------|-----------|
| `inicio.html` | Bitácora del jardín, asistencia mensual con resumen, cobros pendientes, mensajería, evaluación del desarrollo, justificar ausencias |

---

## ⚠️ Páginas en stub (muestran datos crudos de la API)

Estas páginas cargan y muestran los datos correctamente pero tienen UI básica:
- `inscripciones.html` — Inscripciones y cobros por niño
- `personal.html` — Gestión del personal
- `salud.html` — Incidentes de salud
- `comunicacion.html` — Mensajes y avisos
- `evaluacion.html` — Evaluación del desarrollo

Se pueden desarrollar siguiendo el mismo patrón de las páginas completadas.

---

## 🔧 Próximos pasos sugeridos

1. **Completar los stubs** de inscripciones, personal, salud, comunicación y evaluación
2. **Conectar CORS en Django** para el origen del frontend
3. **Agregar un servidor de archivos** o integrar en Django como app estática
4. **Notificaciones push** (en Fase 2) usando Service Workers
5. **App móvil** (en Fase 2) con React Native o PWA usando el mismo API
6. **Modo offline** con Service Workers para educadoras en salas sin buena señal

---

*Frontend para Misael Kids — La Paz, Bolivia · 2026*
