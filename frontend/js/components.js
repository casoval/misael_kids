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

/* ── Vista: avatar del niño + selector Filas/Tarjetas ─────────
   Uso típico en una página:
     <div id="vt-algo"></div>                      ← aquí va el selector
     <div id="wrap-filas">…tabla…</div>
     <div id="wrap-tarjetas" class="grid-tarjetas" style="display:none"></div>

     Vista.montar('algo', { filas:'wrap-filas', tarjetas:'wrap-tarjetas',
                            selector:'vt-algo', alCambiar: v => pintar() });
     // al pintar los datos, rellenar las dos vistas (Vista.actual('algo')).
─────────────────────────────────────────────────────────────── */
const Vista = {
  _cfg: {},

  _esc(t) {
    return String(t ?? '').replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },

  /* Avatar: foto si existe, si no iniciales con color según género.
     `n` puede ser un registro de la API (nino_nombre / nino_foto /
     nino_genero) o un objeto {nombre, foto, genero}. */
  avatar(n, tam = 'md') {
    const nombre = n.nino_nombre ?? n.nombre_completo ?? n.nombre ?? '';
    const foto   = n.nino_foto   ?? n.foto   ?? null;
    const genero = n.nino_genero ?? n.genero ?? '';
    const ini = (typeof UI !== 'undefined' && UI.iniciales) ? UI.iniciales(nombre) : (nombre[0] || '?');
    const img = foto
      ? `<img src="${this._esc(foto)}" alt="" loading="lazy" onerror="this.remove()">`
      : '';
    return `<span class="av-nino av-${tam} ${genero === 'F' ? 'av-f' : ''}" title="${this._esc(nombre)}">${this._esc(ini) || '?'}${img}</span>`;
  },

  /* Celda de tabla: avatar + nombre (+ línea secundaria opcional). */
  celdaNino(n, sub = '', tam = 'sm') {
    const nombre = n.nino_nombre ?? n.nombre_completo ?? n.nombre ?? '—';
    return `<div class="celda-nino">${this.avatar(n, tam)}
      <div class="celda-nino-txt"><div class="celda-nino-nombre">${this._esc(nombre)}</div>
      ${sub ? `<div class="celda-nino-sub">${sub}</div>` : ''}</div></div>`;
  },

  /* Un dato "etiqueta / valor" para el cuerpo de una tarjeta. */
  dato(etiqueta, valorHTML, ancho = false) {
    return `<div class="tn-dato ${ancho ? 'tn-ancho' : ''}"><div class="tn-dato-lbl">${etiqueta}</div>
      <div class="tn-dato-val">${valorHTML}</div></div>`;
  },

  /* Tarjeta completa. opts: {clase, sub, badges, datos, acciones} (HTML ya armado). */
  tarjeta(n, opts = {}) {
    const nombre = n.nino_nombre ?? n.nombre_completo ?? n.nombre ?? '—';
    return `<div class="tarjeta-nino ${opts.clase || ''}">
      <div class="tn-cabecera">${this.avatar(n, 'md')}
        <div class="tn-titulo"><div class="tn-nombre">${this._esc(nombre)}</div>
        ${opts.sub ? `<div class="tn-sub">${opts.sub}</div>` : ''}</div></div>
      ${opts.badges ? `<div class="tn-badges">${opts.badges}</div>` : ''}
      ${opts.datos ? `<div class="tn-datos">${opts.datos}</div>` : ''}
      ${opts.acciones ? `<div class="tn-acciones">${opts.acciones}</div>` : ''}
    </div>`;
  },

  /* Vista elegida (se recuerda por pestaña/sección en este navegador). */
  actual(clave) {
    try {
      const v = localStorage.getItem('mk_vista_' + clave);
      if (v === 'filas' || v === 'tarjetas') return v;
    } catch (e) { /* sin almacenamiento: vale el valor por defecto */ }
    // Sin elección guardada: tarjetas en celular, filas en pantallas grandes.
    return (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) ? 'tarjetas' : 'filas';
  },

  /* Registra la sección y pinta el selector. */
  montar(clave, cfg) {
    this._cfg[clave] = cfg;
    const cont = document.getElementById(cfg.selector);
    if (cont) {
      cont.innerHTML = `<div class="vista-toggle" role="tablist" data-vista="${clave}">
        <button type="button" data-v="filas"    onclick="Vista.cambiar('${clave}','filas')">☰ Filas</button>
        <button type="button" data-v="tarjetas" onclick="Vista.cambiar('${clave}','tarjetas')">▦ Tarjetas</button>
      </div>`;
    }
    this.aplicar(clave);
  },

  /* Muestra/oculta los contenedores y marca el botón activo. */
  aplicar(clave) {
    const cfg = this._cfg[clave];
    if (!cfg) return;
    const v = this.actual(clave);
    const f = document.getElementById(cfg.filas);
    const t = document.getElementById(cfg.tarjetas);
    if (f) f.style.display = v === 'filas' ? '' : 'none';
    if (t) t.style.display = v === 'tarjetas' ? '' : 'none';
    document.querySelectorAll(`.vista-toggle[data-vista="${clave}"] button`).forEach(b =>
      b.classList.toggle('activo', b.dataset.v === v));
  },

  cambiar(clave, v) {
    try { localStorage.setItem('mk_vista_' + clave, v); } catch (e) { /* ignorar */ }
    this.aplicar(clave);
    const cfg = this._cfg[clave];
    if (cfg && cfg.alCambiar) cfg.alCambiar(v);
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

  // Cada item indica qué roles lo ven (sin `roles` = todos los del panel).
  // educadora/ayudante: solo trabajo de sala (nada de dinero ni inscripciones).
  // recepcionista: oficina (fichas, inscripciones, cobros, asistencia, avisos);
  // no ve la parte pedagógica (agenda, desarrollo) ni la gestión de personal.
  const OFICINA = ['admin', 'directora', 'recepcionista'];
  const SALA    = ['admin', 'directora', 'educadora', 'ayudante', 'cocina'];
  const todos = [
    { seccion: 'Principal' },
    { href: '/panel/dashboard/',    icon: '🏠', label: 'Inicio' },
    { href: '/panel/asistencia/',   icon: '📋', label: 'Asistencia' },
    { href: '/panel/agenda/',       icon: '📔', label: 'Agenda pedagógica',  roles: SALA },
    { seccion: 'Gestión' },
    { href: '/panel/ninos/',        icon: '👶', label: 'Niños' },
    { href: '/panel/inscripciones/',icon: '📝', label: 'Inscripciones',      roles: OFICINA },
    { href: '/panel/cobros/',       icon: '💰', label: 'Cobros',             roles: OFICINA },
    { seccion: 'Personal y Operación' },
    { href: '/panel/personal/',     icon: '👩‍🏫', label: 'Educadoras',         roles: ['admin', 'directora'] },
    { href: '/panel/salud/',        icon: '🏥', label: 'Salud' },
    { href: '/panel/comunicacion/', icon: '📨', label: 'Comunicación' },
    { href: '/panel/inventario/',   icon: '📦', label: 'Inventario' },
    { href: '/panel/evaluacion/',   icon: '🌱', label: 'Desarrollo',         roles: SALA },
    { href: '/panel/misael-link/',  icon: '🔗', label: 'Centro Misael' },
  ];
  const visibles = todos.filter(i => i.seccion || !i.roles || i.roles.includes(usr.rol));
  // Quita cabeceras de sección que quedaron sin ningún enlace debajo.
  const items = visibles.filter((it, idx) =>
    !it.seccion || (visibles[idx + 1] && !visibles[idx + 1].seccion));

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
  // Recepcionista: Reportes (mismo acceso que Cobros/caja)
  if (usr.rol === 'recepcionista') {
    items.push({ seccion: 'Administración' },
               { href: '/panel/reportes/', icon: '📊', label: 'Reportes' });
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
    return `<a class="nav-item ${activo}" href="${item.href}" title="${item.label}"${target} style="${extraStyle}">
      <div class="nav-icon">${item.icon}</div> ${item.label}${item.externo?' <span style="font-size:.6rem;opacity:.6">↗</span>':''}
    </a>`;
  }).join('');

  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  sidebar.innerHTML = `
    <div class="sidebar-logo">
      <div class="logo-icon" data-tema-logo>🌱</div>
      <div class="logo-texto"><h2>Misael Kids</h2><span>Panel interno</span></div>
    </div>
    <nav class="sidebar-nav">${html}</nav>
    <div class="sidebar-footer">
      <div id="tema-sidebar"></div>
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

  if (typeof Tema !== 'undefined') Tema.montar(document.getElementById('tema-sidebar'));
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

  // Botón ☰ flotante: en móvil el topbar no queda fijo (ocuparía hasta 3 filas),
  // así que cuando se sale de pantalla aparece este atajo para abrir el menú.
  if (topbar && !document.getElementById('btn-menu-flotante') && 'IntersectionObserver' in window) {
    const fab = document.createElement('button');
    fab.id = 'btn-menu-flotante';
    fab.className = 'btn-menu-flotante';
    fab.type = 'button';
    fab.setAttribute('aria-label', 'Abrir menú');
    fab.innerHTML = '☰';
    fab.onclick = toggleSidebarMovil;
    document.body.appendChild(fab);
    new IntersectionObserver(([e]) => fab.classList.toggle('visible', !e.isIntersecting))
      .observe(topbar);
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
    const s = this.lista.find(s => String(s.id) === String(id));
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
      // La sucursal guardada en el navegador puede ya no existir (base recreada,
      // sucursal desactivada, otro entorno con el mismo dominio…). Si se deja, el
      // selector queda en blanco y TODAS las pantallas filtran por un id fantasma
      // (reportes en 0, listas vacías) mientras la etiqueta dice "Todas".
      const guardado = this.getId();
      if (guardado && !this.lista.some(s => String(s.id) === String(guardado))) {
        localStorage.setItem(this.KEY, '');
      }
      // Si solo hay una sucursal y no hay selección, la seleccionamos por defecto
      if (!this.getId() && this.lista.length === 1) {
        localStorage.setItem(this.KEY, this.lista[0].id);
      }
    } catch {
      // Sin respuesta de la API no podemos validar nada: se conserva lo guardado.
      this.lista = [];
    }
  },

  renderSelector() {
    const topbar = document.querySelector('.topbar');
    if (!topbar || document.getElementById('selector-sucursal')) return;

    const wrap = document.createElement('div');
    wrap.className = 'selector-sucursal-wrap';   // estilos y responsive en base.css

    const sel = document.createElement('select');
    sel.id = 'selector-sucursal';
    sel.className = 'form-select';

    let opciones = '';
    if (this.lista.length > 1) {
      opciones += '<option value="">🏢 Todas las sucursales</option>';
    }
    this.lista.forEach(s => {
      opciones += `<option value="${escHtml(s.id)}">🏢 ${escHtml(s.nombre)}</option>`;
    });
    sel.innerHTML = opciones || '<option value="">Sin sucursales</option>';
    sel.value = this.getId();
    // Si el valor guardado no coincide con ninguna opción el <select> se ve vacío:
    // mejor mostrar la primera opción real que un recuadro en blanco.
    if (sel.selectedIndex < 0 || (this.getId() && sel.value !== this.getId())) sel.selectedIndex = 0;

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

/* ── Descargas de información (CSV, PDF…) ─────────────────────
   La recepcionista consulta en pantalla pero NO descarga nada: los botones
   marcados con data-descarga se quitan para ese rol. El servidor lo exige
   igual en los reportes; esto solo evita mostrar botones que no puede usar. */
function puedeDescargar() {
  const usr = Auth.getUsuario();
  return !!usr && usr.rol !== 'recepcionista';
}

/* ── Inicializar página del panel ─────────────────────────── */
function initPanel(paginaActiva, rolesPermitidos = ['admin','directora','educadora','ayudante','recepcionista','cocina']) {
  Auth.requerirAuth(rolesPermitidos);
  renderSidebar(paginaActiva);
  if (!puedeDescargar()) document.querySelectorAll('[data-descarga]').forEach(el => el.remove());
  // Sucursal.init() se llama por separado en cada página que lo necesite
  // para evitar condiciones de carrera con las cargas de datos
  Sucursal.init().catch(() => {}); // no bloquea si falla
}

/* ── Tablas responsive ────────────────────────────────────────
   En pantallas ≤ 600px el CSS convierte cada fila en una tarjeta
   (ver base.css). Para eso cada <td> necesita su etiqueta, que se
   toma del <th> de su columna. Se re-etiqueta solo cuando la página
   vuelve a pintar el <tbody> (listados cargados por API, filtros...).
   Para excluir una tabla: <div class="tabla-wrap" data-no-apilar>. */
function etiquetarTablas() {
  document.querySelectorAll('.tabla-wrap:not([data-no-apilar]) table').forEach(tabla => {
    const ths = tabla.querySelectorAll('thead th');
    if (!ths.length) return;
    if ([...ths].some(th => th.colSpan > 1 || th.rowSpan > 1)) return; // cabeceras complejas: se deja con scroll
    const etiquetas = [...ths].map(th => th.textContent.trim());
    tabla.classList.add('tabla-apilada');
    tabla.querySelectorAll('tbody tr').forEach(tr => {
      let col = 0;
      [...tr.children].forEach(td => {
        if (!td.hasAttribute('data-label')) td.setAttribute('data-label', td.colSpan > 1 ? '' : (etiquetas[col] || ''));
        col += td.colSpan || 1;
      });
    });
  });
}

(function iniciarTablasResponsive() {
  let pendiente = 0;
  const programar = () => {
    cancelAnimationFrame(pendiente);
    pendiente = requestAnimationFrame(etiquetarTablas);
  };
  const arrancar = () => {
    etiquetarTablas();
    new MutationObserver(programar).observe(document.body, { childList: true, subtree: true });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arrancar);
  else arrancar();
})();
