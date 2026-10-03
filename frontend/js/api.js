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
    // El tema es personal: se carga el del perfil de quien acaba de entrar
    if (typeof Tema !== 'undefined') Tema.alIniciarSesion(data.usuario);
  },

  cerrar() {
    localStorage.removeItem('mk_token');
    localStorage.removeItem('mk_refresh');
    localStorage.removeItem('mk_usuario');
    // La pantalla de login vuelve al tema por defecto: no hereda el de quien salió
    localStorage.removeItem('mk_tema_login');
    window.location.href = '/';
  },

  estaLogueado() { return !!this.getToken(); },

  getRol()       { return this.getUsuario()?.rol || null; },

  // Roles del panel interno
  esPersonalInterno() {
    const rol = this.getRol();
    return ['admin','directora','educadora','ayudante','recepcionista','cocina','profesional'].includes(rol);
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
  // Para endpoints que reciben un archivo (foto, PDF...): FormData en vez de
  // JSON. OJO: nunca fijar 'Content-Type' a mano acá — el navegador arma
  // el header multipart con el boundary correcto solo si lo dejamos vacío.
  postForm:  (url, formData) => apiFetchForm(url, formData, 'POST'),
  patchForm: (url, formData) => apiFetchForm(url, formData, 'PATCH'),
  // Descarga un archivo (CSV, etc.) de un endpoint que exige login. Un <a href> normal
  // no envía el token, por eso se pide con fetch y se entrega como Blob.
  // Devuelve { nombre, filas } (filas = cabecera X-Filas, si el servidor la manda).
  // Con { omitirSiVacio: true } no descarga nada si el servidor informa 0 filas.
  // Con { abrir: true } el archivo (p. ej. un PDF) se abre en una pestaña nueva del
  // navegador en vez de guardarse; si el navegador bloquea la pestaña, se descarga.
  descargar: (endpoint, opciones) => apiDescargar(endpoint, opciones),
};

async function apiDescargar(endpoint, { nombre = 'descarga', omitirSiVacio = false, abrir = false } = {}) {
  // La pestaña se abre ANTES de pedir el archivo: dentro del clic el navegador lo permite,
  // después de un await lo bloquearía como ventana emergente.
  let ventana = null;
  if (abrir) {
    ventana = window.open('', '_blank');
    if (ventana) ventana.document.write('<title>Preparando informe…</title><p style="font-family:sans-serif;padding:2rem">Preparando el informe…</p>');
  }
  try {
    return await _apiDescargar(endpoint, { nombre, omitirSiVacio, ventana });
  } catch (err) {
    if (ventana) ventana.close();
    throw err;
  }
}

async function _apiDescargar(endpoint, { nombre, omitirSiVacio, ventana }) {
  const pedir = () => fetch(`${API_BASE}${endpoint}`, { headers: { Authorization: `Bearer ${Auth.getToken()}` } });
  let res = await pedir();
  if (res.status === 401 && await Auth.refrescarToken()) res = await pedir();
  if (!res.ok) {
    let msg = `Error ${res.status}`;
    try { const e = await res.json(); msg = Object.values(e).flat().join(' ') || msg; } catch {}
    throw new Error(msg);
  }
  const cd    = res.headers.get('Content-Disposition') || '';
  const dado  = /filename="?([^";]+)"?/.exec(cd);
  const filas = res.headers.has('X-Filas') ? parseInt(res.headers.get('X-Filas'), 10) : null;
  const archivo = dado ? dado[1] : nombre;
  if (omitirSiVacio && filas === 0) { if (ventana) ventana.close(); return { nombre: archivo, filas, descargado: false }; }
  const blob = await res.blob();
  if (ventana) {
    // Se fuerza el tipo PDF para que el navegador lo muestre en su visor en lugar de guardarlo.
    const tipo = blob.type || (/\.pdf$/i.test(archivo) ? 'application/pdf' : '');
    const urlVer = URL.createObjectURL(tipo ? new Blob([blob], { type: tipo }) : blob);
    ventana.location.replace(urlVer);
    setTimeout(() => URL.revokeObjectURL(urlVer), 5 * 60 * 1000);   // la pestaña necesita la URL viva mientras se lee
    return { nombre: archivo, filas, descargado: true, abierto: true };
  }
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: archivo });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);   // revocarla al instante puede cancelar la descarga en algunos navegadores
  return { nombre: archivo, filas, descargado: true };
}

async function apiFetchForm(endpoint, formData, method) {
  const token = Auth.getToken();
  const headers = { ...(token ? { Authorization: `Bearer ${token}` } : {}) };

  let res = await fetch(`${API_BASE}${endpoint}`, { method, headers, body: formData });

  if (res.status === 401) {
    const nuevoToken = await Auth.refrescarToken();
    if (nuevoToken) {
      headers.Authorization = `Bearer ${nuevoToken}`;
      res = await fetch(`${API_BASE}${endpoint}`, { method, headers, body: formData });
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
  if (res.status === 204) return null;
  return res.json();
}

/* ══════════════════════════════════════
   ESCAPE HTML — usar SIEMPRE que se interpole texto que viene de la
   API (nombres, asuntos, cuerpos, observaciones...) dentro de un
   template que termina en innerHTML. Evita XSS almacenado.
══════════════════════════════════════ */
function escHtml(t) {
  return String(t ?? '').replace(/[&<>"'`]/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c]));
}

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
      warn:    { bg: 'var(--amarillo-l)', color: 'var(--amarillo-txt)',           icono: '⚠️' },
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
      transition:transform 420ms cubic-bezier(.34,1.56,.64,1), opacity 250ms ease; max-width:360px;
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

  // Edad en meses con su equivalente en años entre paréntesis.
  //   UI.edad(14)       -> "14 meses (1 año y 2 meses)"
  //   UI.edad(14, true) -> "14m (1a 2m)"        (versión corta para chips y listas)
  //   UI.edad(8)        -> "8 meses (menos de 1 año)"
  edad(meses, corta = false) {
    const m = parseInt(meses, 10);
    if (isNaN(m) || m < 0) return '—';
    const a = Math.floor(m / 12), r = m % 12;
    if (corta) return `${m}m (${a ? a + 'a' + (r ? ' ' + r + 'm' : '') : '<1a'})`;
    const anios = a === 1 ? '1 año' : `${a} años`;
    const resto = r === 1 ? '1 mes' : `${r} meses`;
    const enAnios = a === 0 ? 'menos de 1 año' : (r ? `${anios} y ${resto}` : anios);
    return `${m} ${m === 1 ? 'mes' : 'meses'} (${enAnios})`;
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
      parcial:   '<span class="chip chip-violeta">🟡 Pago parcial</span>',
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
