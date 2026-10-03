/* ═══════════════════════════════════════════════════════════════
   Misael Kids — Temas (aplicación, persistencia y selector)
   ───────────────────────────────────────────────────────────────
   · Se carga en el <head>, SIN defer, para aplicar el tema antes de
     que el navegador pinte y evitar el parpadeo del tema equivocado.
   · El tema es PERSONAL: se guarda por usuario en localStorage
     ('mk_tema_u_<id>') y en su perfil del servidor (campo Usuario.tema),
     así que lo que elige el admin no cambia lo que ve la recepcionista,
     la educadora, etc., ni al revés, aunque compartan el mismo navegador.
   · Mientras nadie ha iniciado sesión (pantalla de login) se usa una
     clave aparte, 'mk_tema_login', que se borra al cerrar sesión.
   · Se sincroniza entre pestañas abiertas del mismo usuario.
   · Los valores de cada tema viven en css/themes.css.

   API:
     Tema.actual()                    → id del tema activo
     Tema.aplicar('espacio')          → cambia y guarda el tema
     Tema.montar(elemento, {variante}) → dibuja el selector dentro de elemento
                                        variante: 'flotante' | 'sobre-color'
     Tema.alIniciarSesion(usuario)    → lo llama Auth.guardar() tras el login

   <html> recibe data-tema="id" y data-modo="claro|oscuro".
═══════════════════════════════════════════════════════════════ */
const Tema = (() => {
  const PREFIJO_USUARIO = 'mk_tema_u_';   // + id del usuario
  const CLAVE_LOGIN     = 'mk_tema_login'; // pantalla de login (nadie identificado)
  const CLAVE_ANTIGUA   = 'mk_tema';       // versión previa: una sola para todo el navegador
  const POR_DEFECTO = 'jardin';

  /* Para agregar un tema: registrarlo acá y crear su bloque en themes.css */
  /* grupo: cómo se agrupan en el menú · oscuro: activa el bloque data-modo="oscuro" */
  const TEMAS = [
    { id: 'jardin',    grupo: 'Alegres',       nombre: 'Jardín mágico',   desc: 'Colorido y alegre',      logo: '🌱', deco: ['🌸','🦋','🌟'],
      muestra: ['#2DD4BF', '#FF6B6B', '#FFD93D'], barra: '#2DD4BF' },
    { id: 'oceano',    grupo: 'Alegres',       nombre: 'Océano',          desc: 'Azules y aguamarina',    logo: '🐠', deco: ['🌊','🐬','🐚'],
      muestra: ['#0EA5E9', '#6366F1', '#BAE6FD'], barra: '#0EA5E9' },
    { id: 'atardecer', grupo: 'Alegres',       nombre: 'Dulce atardecer', desc: 'Fucsia y durazno',       logo: '🌅', deco: ['🦄','🎈','🌈'],
      muestra: ['#D946EF', '#FB923C', '#FDE68A'], barra: '#D946EF' },
    { id: 'selva',     grupo: 'Alegres',       nombre: 'Selva',           desc: 'Verde musgo y río',      logo: '🌳', deco: ['🌿','🦜','🍃'],
      muestra: ['#4D7C0F', '#0E7490', '#65A30D'], barra: '#4D7C0F' },
    { id: 'altiplano', grupo: 'Alegres',       nombre: 'Altiplano',       desc: 'Terracota y azul lago',  logo: '🦙', deco: ['🦙','⛰️','🌄'],
      muestra: ['#B45309', '#0369A1', '#F59E0B'], barra: '#B45309' },
    { id: 'papel',     grupo: 'Sobrios',       nombre: 'Papel',           desc: 'Sobrio y limpio',        logo: '📒', deco: ['✏️','📌','📚'],
      muestra: ['#2563EB', '#94A3B8', '#1E293B'], barra: '#2563EB',
      fuente: 'family=Inter:wght@400;500;600;700;800&family=DM+Serif+Display' },
    { id: 'espacio',   grupo: 'Oscuros',       nombre: 'Espacio',         desc: 'Oscuro con estrellas',   logo: '🚀', deco: ['🪐','🌟','🛸'],
      muestra: ['#8B5CF6', '#22D3EE', '#1A1A3A'], barra: '#1A1A3A', oscuro: true,
      fuente: 'family=Righteous' },
    { id: 'noche',     grupo: 'Oscuros',       nombre: 'Noche suave',     desc: 'Oscuro y tranquilo',     logo: '🌙', deco: ['🌙','⭐','☁️'],
      muestra: ['#0F766E', '#4F46E5', '#1E293B'], barra: '#0F172A', oscuro: true },
    { id: 'altocontraste', grupo: 'Accesibilidad', nombre: 'Alto contraste', desc: 'Máxima legibilidad', logo: '👁️', deco: ['⭐','✅','🔔'],
      muestra: ['#0B3BCC', '#FFD000', '#000000'], barra: '#0B3BCC',
      fuente: 'family=Atkinson+Hyperlegible:wght@400;700' },
  ];

  const porId = id => TEMAS.find(t => t.id === id);

  /* Usuario con sesión abierta (mk_usuario lo escribe Auth.guardar al hacer login).
     Se lee directo: este script carga antes que api.js. */
  function usuarioActual() {
    try {
      if (!localStorage.getItem('mk_token')) return null;
      const u = JSON.parse(localStorage.getItem('mk_usuario') || 'null');
      return u && u.id ? u : null;
    } catch (_) { return null; }
  }

  /* Clave donde vive la preferencia de QUIEN está usando la app ahora */
  function claveActual() {
    const u = usuarioActual();
    return u ? PREFIJO_USUARIO + u.id : CLAVE_LOGIN;
  }

  function leer() {
    try {
      const propio = localStorage.getItem(claveActual());
      if (porId(propio)) return propio;
      const delServidor = usuarioActual()?.tema;   // viene en el login
      if (porId(delServidor)) return delServidor;
    } catch (_) { /* modo privado / storage bloqueado */ }
    return POR_DEFECTO;
  }

  /* Guarda en el perfil del servidor para que siga a la persona entre dispositivos.
     Falla en silencio: el tema ya quedó aplicado y guardado en este navegador. */
  function enviarAlServidor(id) {
    if (!usuarioActual() || typeof API === 'undefined') return;
    API.patch('/auth/usuarios/yo/tema/', { tema: id }).catch(() => {});
  }

  function guardar(id) {
    try { localStorage.setItem(claveActual(), id); } catch (_) { /* se aplica igual, solo no persiste */ }
    const u = usuarioActual();
    if (u) {
      try {  // mantener al día la copia local del perfil
        u.tema = id;
        localStorage.setItem('mk_usuario', JSON.stringify(u));
      } catch (_) {}
      enviarAlServidor(id);
    }
  }

  /* Tras el login: el tema guardado en el perfil manda sobre lo que hubiera en
     este navegador. Si la persona aún no tiene tema propio, conserva el que eligió
     en la pantalla de login (si eligió alguno); si no, queda el de por defecto. */
  function alIniciarSesion(usuario) {
    if (!usuario || !usuario.id) return;
    const clave = PREFIJO_USUARIO + usuario.id;
    try {
      if (porId(usuario.tema)) {
        localStorage.setItem(clave, usuario.tema);
      } else {
        const elegidoEnLogin = localStorage.getItem(CLAVE_LOGIN);
        if (porId(elegidoEnLogin) && !porId(localStorage.getItem(clave))) {
          localStorage.setItem(clave, elegidoEnLogin);
          usuario.tema = elegidoEnLogin;
          localStorage.setItem('mk_usuario', JSON.stringify(usuario));
          enviarAlServidor(elegidoEnLogin);
        }
      }
      localStorage.removeItem(CLAVE_LOGIN);
    } catch (_) {}
  }

  /* Los temas con tipografía propia la piden a Google Fonts solo cuando se usan */
  function cargarFuente(tema) {
    if (!tema.fuente) return;
    const idLink = 'mk-fuente-' + tema.id;
    if (document.getElementById(idLink)) return;
    const link = document.createElement('link');
    link.id = idLink;
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?' + tema.fuente + '&display=swap';
    document.head.appendChild(link);
  }

  /* Color de la barra del navegador en móvil */
  function pintarBarraNavegador(tema) {
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      document.head.appendChild(meta);
    }
    meta.content = tema.barra;
  }

  /* data-tema-logo → emoji del tema · data-tema-deco → emojis decorativos del tema */
  function actualizarLogos(tema) {
    document.querySelectorAll('[data-tema-logo]').forEach(el => { el.textContent = tema.logo; });
    /* adornos: data-tema-deco="0|1|2" elige uno de los 3 emojis decorativos del tema */
    document.querySelectorAll('[data-tema-deco]').forEach(el => {
      el.textContent = tema.deco[Number(el.dataset.temaDeco)] || '';
    });
  }

  function marcarSelectores(id) {
    document.querySelectorAll('.tema-selector').forEach(sel => {
      const t = porId(id);
      const nombre = sel.querySelector('.tema-btn .tema-nombre');
      const puntos = sel.querySelector('.tema-btn .tema-puntos');
      if (nombre) nombre.textContent = t.nombre;
      if (puntos) puntos.innerHTML = t.muestra.map(c => `<i style="background:${c}"></i>`).join('');
      sel.querySelectorAll('.tema-op').forEach(op =>
        op.setAttribute('aria-checked', String(op.dataset.id === id)));
    });
  }

  function aplicar(id, { guardarEleccion = true } = {}) {
    const tema = porId(id) || porId(POR_DEFECTO);
    document.documentElement.setAttribute('data-tema', tema.id);
    document.documentElement.setAttribute('data-modo', tema.oscuro ? 'oscuro' : 'claro');
    cargarFuente(tema);
    pintarBarraNavegador(tema);
    actualizarLogos(tema);
    marcarSelectores(tema.id);
    if (guardarEleccion) guardar(tema.id);
    document.dispatchEvent(new CustomEvent('mk:tema', { detail: { id: tema.id } }));
  }

  function actual() {
    return document.documentElement.getAttribute('data-tema') || POR_DEFECTO;
  }

  /* ── Selector ─────────────────────────────────────────────── */
  function cerrarTodos() {
    document.querySelectorAll('.tema-selector.abierto').forEach(sel => {
      sel.classList.remove('abierto');
      sel.querySelector('.tema-btn')?.setAttribute('aria-expanded', 'false');
    });
  }

  function montar(contenedor, { variante = '' } = {}) {
    if (!contenedor) return;
    const t = porId(actual());
    contenedor.innerHTML = `
      <div class="tema-selector" ${variante ? `data-variante="${variante}"` : ''}>
        <button type="button" class="tema-btn" aria-haspopup="true" aria-expanded="false"
                title="Cambiar el aspecto de la app">
          <span>🎨</span>
          <span class="tema-puntos"></span>
          <span class="tema-nombre"></span>
          <span class="tema-flecha" aria-hidden="true">▲</span>
        </button>
        <div class="tema-menu" role="radiogroup" aria-label="Tema de la aplicación">
          ${TEMAS.map((x, n) => (n === 0 || TEMAS[n - 1].grupo !== x.grupo
              ? `<div class="tema-menu-titulo" role="presentation">${x.grupo}</div>` : '') + `
            <button type="button" class="tema-op" role="radio" data-id="${x.id}" aria-checked="false">
              <span class="tema-muestra"
                    style="background:linear-gradient(135deg,${x.muestra[0]} 50%,${x.muestra[1]} 50%)">${x.logo}</span>
              <span class="tema-txt">${x.nombre}<small>${x.desc}</small></span>
              <span class="tema-check" aria-hidden="true">✓</span>
            </button>`).join('')}
        </div>
      </div>`;

    const sel = contenedor.querySelector('.tema-selector');
    const btn = sel.querySelector('.tema-btn');

    btn.addEventListener('click', e => {
      e.stopPropagation();
      const abrir = !sel.classList.contains('abierto');
      cerrarTodos();
      sel.classList.toggle('abierto', abrir);
      btn.setAttribute('aria-expanded', String(abrir));
      if (abrir) sel.querySelector('.tema-op[aria-checked="true"]')?.focus();
    });

    sel.querySelectorAll('.tema-op').forEach(op => {
      op.addEventListener('click', () => {
        aplicar(op.dataset.id);
        cerrarTodos();
        btn.focus();
      });
    });

    marcarSelectores(t.id);
    actualizarLogos(t);
  }

  /* cerrar al hacer clic fuera o con Escape */
  document.addEventListener('click', e => { if (!e.target.closest('.tema-selector')) cerrarTodos(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarTodos(); });

  /* sincronizar con otras pestañas abiertas */
  window.addEventListener('storage', e => {
    if (e.key === claveActual() && porId(e.newValue)) aplicar(e.newValue, { guardarEleccion: false });
  });

  /* La clave única de la versión anterior era compartida por todo el navegador:
     se descarta para que el tema de una persona no "herede" a la siguiente. */
  try { localStorage.removeItem(CLAVE_ANTIGUA); } catch (_) {}

  /* Aplicación inmediata (este script va en el <head>) */
  aplicar(leer(), { guardarEleccion: false });

  return { TEMAS, actual, aplicar, montar, alIniciarSesion };
})();
