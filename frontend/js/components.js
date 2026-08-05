/* ═══════════════════════════════════════════════════════════════
   Misael Kids — Componentes reutilizables
   Formularios, validaciones, tablas y CRUD genérico
═══════════════════════════════════════════════════════════════ */

/* ── Validador de formularios ─────────────────────────────── */
const Validar = {
  requerido(val, nombre) {
    if (!val || val.toString().trim() === '')
      return `${nombre} es obligatorio`;
    return null;
  },
  email(val) {
    if (!val) return 'El email es obligatorio';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val))
      return 'El email no tiene un formato válido';
    return null;
  },
  minLength(val, min, nombre) {
    if (!val || val.length < min)
      return `${nombre} debe tener al menos ${min} caracteres`;
    return null;
  },
  numero(val, nombre) {
    if (val === '' || val === null || val === undefined)
      return `${nombre} es obligatorio`;
    if (isNaN(parseFloat(val)) || parseFloat(val) < 0)
      return `${nombre} debe ser un número válido mayor o igual a 0`;
    return null;
  },
  fecha(val, nombre) {
    if (!val) return `${nombre} es obligatoria`;
    return null;
  },
  formulario(reglas) {
    const errores = {};
    for (const [campo, checks] of Object.entries(reglas)) {
      for (const check of checks) {
        const err = check();
        if (err) { errores[campo] = err; break; }
      }
    }
    return errores;
  },
  mostrarErrores(errores, prefijo = '') {
    // Limpiar errores previos
    document.querySelectorAll(`${prefijo} .form-error`).forEach(el => el.textContent = '');
    document.querySelectorAll(`${prefijo} .form-input, ${prefijo} .form-select, ${prefijo} .form-textarea`)
      .forEach(el => el.classList.remove('input-error'));

    Object.entries(errores).forEach(([campo, msg]) => {
      const errorEl = document.querySelector(`${prefijo} [data-error="${campo}"]`);
      const inputEl = document.querySelector(`${prefijo} [name="${campo}"], ${prefijo} #${campo}`);
      if (errorEl) errorEl.textContent = msg;
      if (inputEl) inputEl.classList.add('input-error');
    });
    return Object.keys(errores).length === 0;
  },
};

/* ── CRUD genérico ────────────────────────────────────────── */
const CRUD = {
  async cargarTabla({ endpoint, tbody, columnas, acciones, filtros = {} }) {
    let url = endpoint + '?page_size=100';
    Object.entries(filtros).forEach(([k, v]) => { if (v) url += `&${k}=${encodeURIComponent(v)}`; });
    tbody.innerHTML = `<tr><td colspan="${columnas.length + 1}">
      <div class="loader"><div class="spinner"></div></div></td></tr>`;
    try {
      const data  = await API.get(url);
      const lista = data.results || data;
      if (!lista.length) {
        tbody.innerHTML = `<tr><td colspan="${columnas.length + 1}" style="text-align:center;
          padding:2rem;color:var(--texto-suave);font-weight:600">Sin registros</td></tr>`;
        return [];
      }
      tbody.innerHTML = lista.map(item => `
        <tr>
          ${columnas.map(col => `<td>${col.render ? col.render(item) :
            (item[col.key] ?? '—')}</td>`).join('')}
          <td>
            <div style="display:flex;gap:6px">
              ${acciones.editar ? `<button class="btn btn-outline btn-sm"
                onclick="${acciones.editar}('${item.id}')">✏️ Editar</button>` : ''}
              ${acciones.eliminar ? `<button class="btn btn-sm"
                style="background:var(--coral-l);color:var(--coral-d);border:1.5px solid var(--coral)"
                onclick="${acciones.eliminar}('${item.id}','${item[acciones.nombreCampo]||''}')">
                🗑️ Eliminar</button>` : ''}
              ${acciones.extra ? acciones.extra(item) : ''}
            </div>
          </td>
        </tr>`).join('');
      return lista;
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="${columnas.length + 1}">
        <div class="alerta alerta-peligro">Error: ${err.message}</div></td></tr>`;
      return [];
    }
  },

  async eliminar(id, endpoint, nombre, callback) {
    if (!confirm(`¿Eliminar "${nombre}"?\n\nEsta acción no se puede deshacer.`)) return;
    try {
      await API.delete(`${endpoint}${id}/`);
      UI.toast(`✅ "${nombre}" eliminado correctamente`, 'exito');
      if (callback) callback();
    } catch (err) {
      UI.toast(`No se puede eliminar: ${err.message}`, 'error');
    }
  },

  async cargarEnModal(id, endpoint, rellenar) {
    try {
      const data = await API.get(`${endpoint}${id}/`);
      rellenar(data);
    } catch (err) {
      UI.toast('Error cargando datos: ' + err.message, 'error');
    }
  },

  async guardar({ id, endpoint, datos, modalId, callback }) {
    try {
      if (id) {
        await API.patch(`${endpoint}${id}/`, datos);
        UI.toast('✅ Actualizado correctamente', 'exito');
      } else {
        await API.post(endpoint, datos);
        UI.toast('✅ Creado correctamente', 'exito');
      }
      if (modalId) UI.cerrarModal(modalId);
      if (callback) callback();
    } catch (err) {
      UI.toast('Error al guardar: ' + err.message, 'error');
      throw err;
    }
  },
};

/* ── Sidebar dinámico ─────────────────────────────────────── */
function renderSidebar(paginaActiva) {
  const usr = Auth.getUsuario();
  if (!usr) return;

  // El rol 'profesional' (Centro Misael) solo trabaja con derivaciones y
  // planes de trabajo: antes veía el menú completo con enlaces a páginas
  // a las que no tenía acceso (y lo rebotaban).
  if (usr.rol === 'profesional') {
    const itemsProfesional = [
      { seccion: 'Principal' },
      { href: '/panel/dashboard/',   icon: '🏠', label: 'Inicio' },
      { href: '/panel/misael-link/', icon: '🔗', label: 'Centro Misael' },
    ];
    return _pintarSidebar(itemsProfesional, paginaActiva, usr);
  }

  const items = [
    { seccion: 'Principal' },
    { href: '/panel/dashboard/',    icon: '🏠', label: 'Inicio' },
    { href: '/panel/asistencia/',   icon: '📋', label: 'Asistencia' },
    { href: '/panel/agenda/',       icon: '📔', label: 'Agenda pedagógica' },
    { seccion: 'Gestión' },
    { href: '/panel/ninos/',        icon: '👶', label: 'Niños' },
    { href: '/panel/inscripciones/',icon: '📝', label: 'Inscripciones' },
    { href: '/panel/cobros/',       icon: '💰', label: 'Cobros' },
    { seccion: 'Personal y Operación' },
    { href: '/panel/personal/',     icon: '👩‍🏫', label: 'Educadoras' },
    { href: '/panel/salud/',        icon: '🏥', label: 'Salud' },
    { href: '/panel/comunicacion/', icon: '📨', label: 'Comunicación' },
    { href: '/panel/inventario/',   icon: '📦', label: 'Inventario' },
    { href: '/panel/evaluacion/',   icon: '🌱', label: 'Desarrollo' },
    { href: '/panel/misael-link/',  icon: '🔗', label: 'Centro Misael' },
  ];

  // Sección admin solo para admin/directora
  if (['admin', 'directora'].includes(usr.rol)) {
    items.push(
      { seccion: 'Administración' },
      { href: '/panel/sucursales/', icon: '🏢', label: 'Sucursales y salas' },
      { href: '/panel/turnos/',     icon: '⏰', label: 'Turnos' },
      { href: '/panel/usuarios/',   icon: '🔐', label: 'Usuarios' },
      { href: '/panel/reportes/',   icon: '📊', label: 'Reportes' },
    );
  }
  // Enlace al admin Django solo para superusuarios (rol admin)
  if (usr.rol === 'admin') {
    items.push({ href: '/admin/', icon: '⚙️', label: 'Admin Django', externo: true });
  }

  return _pintarSidebar(items, paginaActiva, usr);
}

/* Pinta el HTML del sidebar a partir de una lista de items ya filtrada por rol. */
function _pintarSidebar(items, paginaActiva, usr) {
  const html = items.map(item => {
    if (item.seccion) return `<div class="nav-seccion">${item.seccion}</div>`;
    const activo = paginaActiva && item.href.includes(paginaActiva) ? 'activo' : '';
    const target = item.externo ? ' target="_blank" rel="noopener"' : '';
    const extraStyle = item.externo ? 'opacity:.75;border-top:1px dashed var(--gris-200);margin-top:4px;padding-top:var(--gap-sm)' : '';
    return `<a class="nav-item ${activo}" href="${item.href}"${target} style="${extraStyle}">
      <div class="nav-icon">${item.icon}</div> ${item.label}${item.externo?' <span style="font-size:.6rem;opacity:.6">↗</span>':''}
    </a>`;
  }).join('');

  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  sidebar.innerHTML = `
    <div class="sidebar-logo">
      <div class="logo-icon">🌱</div>
      <div class="logo-texto"><h2>Misael Kids</h2><span>Panel interno</span></div>
    </div>
    <nav class="sidebar-nav">${html}</nav>
    <div class="sidebar-footer">
      <div class="usuario-card">
        <div class="usuario-avatar">${UI.iniciales(usr.nombres + ' ' + usr.apellidos)}</div>
        <div class="usuario-info">
          <div class="nombre">${usr.nombres} ${usr.apellidos}</div>
          <div class="rol">${usr.rol_display || usr.rol}</div>
        </div>
        <button onclick="Auth.cerrar()" title="Cerrar sesión"
          style="margin-left:auto;background:none;border:none;cursor:pointer;font-size:1.1rem;opacity:.6">🚪</button>
      </div>
    </div>`;

  insertarMenuMovil();
}

/* ── Menú móvil: botón hamburguesa en el topbar + fondo oscuro ────────
   Se inyecta desde acá (no en cada página) para que funcione igual en
   todo el panel sin tener que tocar los ~15 archivos HTML uno por uno. */
function insertarMenuMovil() {
  const topbar = document.querySelector('.topbar');
  if (topbar && !document.getElementById('btn-menu-movil')) {
    const btn = document.createElement('button');
    btn.id = 'btn-menu-movil';
    btn.className = 'btn-menu-movil';
    btn.setAttribute('aria-label', 'Abrir menú');
    btn.textContent = '☰';
    btn.onclick = toggleSidebarMovil;
    topbar.insertBefore(btn, topbar.firstChild);
  }
  if (!document.getElementById('sidebar-backdrop')) {
    const backdrop = document.createElement('div');
    backdrop.id = 'sidebar-backdrop';
    backdrop.className = 'sidebar-backdrop';
    backdrop.onclick = cerrarSidebarMovil;
    document.body.appendChild(backdrop);
  }
}

function toggleSidebarMovil() {
  document.getElementById('sidebar')?.classList.toggle('abierto');
  document.getElementById('sidebar-backdrop')?.classList.toggle('visible');
}

function cerrarSidebarMovil() {
  document.getElementById('sidebar')?.classList.remove('abierto');
  document.getElementById('sidebar-backdrop')?.classList.remove('visible');
}

/* ── Selector global de sucursal (persistente en topbar) ──── */
const Sucursal = {
  KEY: 'mk_sucursal_actual',
  lista: [],

  getId() {
    return localStorage.getItem(this.KEY) || '';
  },
  setId(id) {
    localStorage.setItem(this.KEY, id || '');
    window.dispatchEvent(new CustomEvent('sucursalChanged', { detail: { id } }));
  },
  getNombre() {
    const id = this.getId();
    const s = this.lista.find(s => s.id === id);
    return s ? s.nombre : 'Todas las sucursales';
  },
  // true si hay una sucursal específica seleccionada (no "todas")
  activo() {
    return !!this.getId();
  },

  async cargar() {
    try {
      const data = await API.get('/core/sucursales/?activa=true&page_size=50');
      this.lista = data.results || data;
      // Si solo hay una sucursal y no hay selección, la seleccionamos por defecto
      if (!this.getId() && this.lista.length === 1) {
        localStorage.setItem(this.KEY, this.lista[0].id);
      }
    } catch { this.lista = []; }
  },

  renderSelector() {
    const topbar = document.querySelector('.topbar');
    if (!topbar || document.getElementById('selector-sucursal')) return;

    const wrap = document.createElement('div');
    wrap.style.display = 'flex';
    wrap.style.alignItems = 'center';
    wrap.style.gap = '8px';
    wrap.style.marginLeft = 'var(--gap-lg)';

    const sel = document.createElement('select');
    sel.id = 'selector-sucursal';
    sel.className = 'form-select';
    sel.style.maxWidth = '230px';
    sel.style.fontWeight = '700';

    let opciones = '';
    if (this.lista.length > 1) {
      opciones += '<option value="">🏢 Todas las sucursales</option>';
    }
    this.lista.forEach(s => {
      opciones += `<option value="${s.id}">🏢 ${s.nombre}</option>`;
    });
    sel.innerHTML = opciones || '<option value="">Sin sucursales</option>';
    sel.value = this.getId();

    if (this.lista.length <= 1) sel.disabled = true; // listo para el futuro, sin uso aún

    sel.addEventListener('change', () => this.setId(sel.value));
    wrap.appendChild(sel);

    const titulo = topbar.querySelector('.topbar-titulo');
    if (titulo) titulo.insertAdjacentElement('afterend', wrap);
    else topbar.insertBefore(wrap, topbar.firstChild);
  },

  // Devuelve el set de IDs de niño que pertenecen a la sucursal seleccionada
  // (vía inscripciones activas). Si no hay sucursal seleccionada, devuelve null (sin filtro).
  async ninosIds() {
    if (!this.activo()) return null;
    try {
      const data = await API.get('/inscripciones/inscripciones/?sucursal=' + this.getId() + '&activa=true&page_size=1000');
      return new Set((data.results || data).map(i => i.nino));
    } catch { return null; }
  },

  // Devuelve el set de IDs de personal asignado a la sucursal seleccionada.
  async personalIds() {
    if (!this.activo()) return null;
    try {
      const data = await API.get('/personal/asignaciones/?sucursal=' + this.getId() + '&activa=true&page_size=1000');
      return new Set((data.results || data).map(a => a.personal));
    } catch { return null; }
  },

  async init() {
    await this.cargar();
    this.renderSelector();
  }
};

/* ── Inicializar página del panel ─────────────────────────── */
function initPanel(paginaActiva, rolesPermitidos = ['admin','directora','educadora','ayudante','administrativo','cocina']) {
  Auth.requerirAuth(rolesPermitidos);
  renderSidebar(paginaActiva);
  // Sucursal.init() se llama por separado en cada página que lo necesite
  // para evitar condiciones de carrera con las cargas de datos
  Sucursal.init().catch(() => {}); // no bloquea si falla
}