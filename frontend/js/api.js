/* ═══════════════════════════════════════════════════════════════
   Misael Kids — API client y utilidades globales
   Todas las páginas importan este archivo primero
═══════════════════════════════════════════════════════════════ */

const API_BASE = '/api';  // Relativo — funciona en cualquier puerto

/* ══════════════════════════════════════
   AUTH — Manejo de sesión JWT
══════════════════════════════════════ */

const Auth = {
  getToken()    { return localStorage.getItem('mk_token'); },
  getRefresh()  { return localStorage.getItem('mk_refresh'); },
  getUsuario()  { return JSON.parse(localStorage.getItem('mk_usuario') || 'null'); },

  guardar(data) {
    localStorage.setItem('mk_token',   data.access);
    localStorage.setItem('mk_refresh', data.refresh);
    localStorage.setItem('mk_usuario', JSON.stringify(data.usuario));
  },

  cerrar() {
    localStorage.removeItem('mk_token');
    localStorage.removeItem('mk_refresh');
    localStorage.removeItem('mk_usuario');
    window.location.href = '/';
  },

  estaLogueado() { return !!this.getToken(); },

  getRol()       { return this.getUsuario()?.rol || null; },

  // Roles del panel interno
  esPersonalInterno() {
    const rol = this.getRol();
    return ['admin','directora','educadora','ayudante','administrativo','cocina','profesional'].includes(rol);
  },

  // Padres/tutores van al portal
  esTutor() { return this.getRol() === 'tutor'; },

  // Redirige si no está logueado o si el rol no corresponde a la página
  requerirAuth(soloRoles = null) {
    if (!this.estaLogueado()) {
      window.location.href = '/';
      return false;
    }
    if (soloRoles && !soloRoles.includes(this.getRol())) {
      this.redirigirSegunRol();
      return false;
    }
    return true;
  },

  redirigirSegunRol() {
    if (this.esTutor()) {
      window.location.href = '/portal/';
    } else if (this.esPersonalInterno()) {
      window.location.href = '/panel/dashboard/';
    } else {
      this.cerrar();
    }
  },

  async refrescarToken() {
    try {
      const res = await fetch(`${API_BASE}/auth/login/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: this.getRefresh() }),
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('mk_token', data.access);
        return data.access;
      }
    } catch {}
    this.cerrar();
    return null;
  },
};

/* ══════════════════════════════════════
   FETCH con autenticación automática
══════════════════════════════════════ */

async function apiFetch(endpoint, opciones = {}) {
  const token = Auth.getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opciones.headers,
  };

  let res = await fetch(`${API_BASE}${endpoint}`, { ...opciones, headers });

  // Si el token expiró, intentar refrescar una vez
  if (res.status === 401) {
    const nuevoToken = await Auth.refrescarToken();
    if (nuevoToken) {
      headers.Authorization = `Bearer ${nuevoToken}`;
      res = await fetch(`${API_BASE}${endpoint}`, { ...opciones, headers });
    }
  }

  if (!res.ok) {
    let errorMsg = `Error ${res.status}`;
    try {
      const err = await res.json();
      errorMsg = Object.values(err).flat().join(' ') || errorMsg;
    } catch {}
    throw new Error(errorMsg);
  }

  // 204 No Content no tiene body
  if (res.status === 204) return null;
  return res.json();
}

// Métodos convenientes
const API = {
  get:    (url)        => apiFetch(url),
  post:   (url, data)  => apiFetch(url, { method: 'POST',   body: JSON.stringify(data) }),
  put:    (url, data)  => apiFetch(url, { method: 'PUT',    body: JSON.stringify(data) }),
  patch:  (url, data)  => apiFetch(url, { method: 'PATCH',  body: JSON.stringify(data) }),
  delete: (url)        => apiFetch(url, { method: 'DELETE' }),
};

/* ══════════════════════════════════════
   UI HELPERS
══════════════════════════════════════ */

const UI = {
  // Toast de notificación flotante
  toast(mensaje, tipo = 'info', duracion = 3500) {
    const colores = {
      exito:   { bg: 'var(--verde-l)',    color: 'var(--verde-d)',    icono: '✅' },
      error:   { bg: 'var(--coral-l)',    color: 'var(--coral-d)',    icono: '❌' },
      info:    { bg: 'var(--turquesa-l)', color: 'var(--turquesa-d)', icono: 'ℹ️' },
      warn:    { bg: 'var(--amarillo-l)', color: '#92400E',           icono: '⚠️' },
    };
    const c = colores[tipo] || colores.info;

    const t = document.createElement('div');
    t.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:9999;
      background:${c.bg}; color:${c.color};
      padding:12px 18px; border-radius:14px;
      font-family:var(--font-body); font-weight:700; font-size:.875rem;
      box-shadow:0 8px 24px rgba(0,0,0,.12);
      display:flex; align-items:center; gap:8px;
      transform:translateY(60px); opacity:0;
      transition:all 300ms ease; max-width:360px;
      border:1.5px solid ${c.color}30;
    `;
    t.innerHTML = `<span>${c.icono}</span><span>${mensaje}</span>`;
    document.body.appendChild(t);
    requestAnimationFrame(() => {
      t.style.transform = 'translateY(0)';
      t.style.opacity   = '1';
    });
    setTimeout(() => {
      t.style.transform = 'translateY(60px)';
      t.style.opacity   = '0';
      setTimeout(() => t.remove(), 300);
    }, duracion);
  },

  // Abrir / cerrar modal
  abrirModal(id) {
    document.getElementById(id)?.classList.add('abierto');
    document.body.style.overflow = 'hidden';
  },
  cerrarModal(id) {
    document.getElementById(id)?.classList.remove('abierto');
    document.body.style.overflow = '';
  },

  // Loader dentro de un contenedor
  mostrarLoader(contenedor, msg = 'Cargando...') {
    contenedor.innerHTML = `
      <div class="loader">
        <div class="spinner"></div>
        <p style="color:var(--texto-suave);font-weight:600">${msg}</p>
      </div>`;
  },

  // Estado vacío
  vacio(contenedor, msg = 'No hay datos', icono = '📭') {
    contenedor.innerHTML = `
      <div class="loader">
        <div style="font-size:3rem">${icono}</div>
        <p style="color:var(--texto-suave);font-weight:600">${msg}</p>
      </div>`;
  },

  // Llenar un <select> con opciones
  llenarSelect(selectEl, opciones, valorKey = 'id', textoKey = 'nombre', placeholder = 'Seleccionar...') {
    selectEl.innerHTML = `<option value="">${placeholder}</option>`;
    opciones.forEach(op => {
      const opt = document.createElement('option');
      opt.value       = op[valorKey];
      opt.textContent = typeof textoKey === 'function' ? textoKey(op) : op[textoKey];
      selectEl.appendChild(opt);
    });
  },

  // Iniciales de un nombre
  iniciales(nombre = '') {
    return nombre.split(' ').slice(0,2).map(p => p[0]?.toUpperCase() || '').join('');
  },

  // Fecha de HOY como "YYYY-MM-DD" en hora LOCAL (no usar `new Date().toISOString()`
  // para esto: convierte a UTC, y en Bolivia (UTC-4) eso muestra la fecha de MAÑANA
  // en cualquier momento después de las 20:00 hora local).
  fechaHoyISO(d = new Date()) {
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const dia = String(d.getDate()).padStart(2,'0');
    return `${y}-${m}-${dia}`;
  },

  // Formatear fecha
  fecha(iso) {
    if (!iso) return '—';
    return new Date(iso + 'T00:00:00').toLocaleDateString('es-BO', {
      day: '2-digit', month: 'short', year: 'numeric'
    });
  },

  // Formatear moneda boliviana
  moneda(valor) {
    if (valor == null) return '—';
    return `Bs. ${parseFloat(valor).toFixed(2)}`;
  },

  // Chip de estado para cobros
  chipEstadoCobro(estado) {
    const mapa = {
      pendiente: '<span class="chip chip-amarillo">⏳ Pendiente</span>',
      pagado:    '<span class="chip chip-verde">✅ Pagado</span>',
      vencido:   '<span class="chip chip-coral">🔴 Vencido</span>',
      anulado:   '<span class="chip chip-gris">🚫 Anulado</span>',
    };
    return mapa[estado] || `<span class="chip chip-gris">${estado}</span>`;
  },

  // Chip de asistencia
  chipAsistencia(estado) {
    const mapa = {
      presente:            '<span class="chip chip-verde">✅ Presente</span>',
      ausente:             '<span class="chip chip-coral">❌ Ausente</span>',
      ausente_justificado: '<span class="chip chip-amarillo">📄 Justificado</span>',
    };
    return mapa[estado] || `<span class="chip chip-gris">${estado}</span>`;
  },
};

/* ══════════════════════════════════════
   Cerrar modales al click fuera
══════════════════════════════════════ */

document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('abierto');
    document.body.style.overflow = '';
  }
  if (e.target.classList.contains('modal-cerrar')) {
    const overlay = e.target.closest('.modal-overlay');
    overlay?.classList.remove('abierto');
    document.body.style.overflow = '';
  }
});

/* ══════════════════════════════════════
   Sidebar mobile toggle
══════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('sidebar-toggle');
  const sidebar   = document.querySelector('.sidebar');
  toggleBtn?.addEventListener('click', () => sidebar?.classList.toggle('abierto'));
});
