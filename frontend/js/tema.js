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

   Animaciones (capas de movimiento, ver css/base.css y css/themes.css):
   · <html data-anim="on|off"> las enciende o apaga. Hay un interruptor en el
     selector de tema; la elección se guarda por dispositivo ('mk_anim'),
     porque depende de qué tan potente es la tablet, no de quién la use.
   · Si el sistema pide "reducir movimiento", quedan apagadas y no se pueden encender.
   · <html data-oculto> se pone mientras la pestaña no se ve: el CSS pausa todo.

   API:
     Tema.actual()                    → id del tema activo
     Tema.animaciones()               → true si las animaciones están activas
     Tema.fijarAnimaciones(true|false)
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
  const CLAVE_ANIM    = 'mk_anim';       // 'on' | 'off' · por dispositivo

  /* ── Animaciones: interruptor global ─────────────────────────── */
  const mqReducir = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const sistemaReduceMovimiento = () => !!(mqReducir && mqReducir.matches);

  function animacionesActivas() {
    if (sistemaReduceMovimiento()) return false;
    try { return localStorage.getItem(CLAVE_ANIM) !== 'off'; } catch (_) { return true; }
  }

  function pintarAnimaciones() {
    const activas = animacionesActivas();
    document.documentElement.setAttribute('data-anim', activas ? 'on' : 'off');
    document.querySelectorAll('.tema-anim').forEach(b => {
      b.setAttribute('aria-checked', String(activas));
      b.toggleAttribute('disabled', sistemaReduceMovimiento());
      const nota = b.querySelector('small');
      if (nota) nota.textContent = sistemaReduceMovimiento()
        ? 'Tu dispositivo pidió menos movimiento' : 'Ambiente y movimiento';
    });
  }

  function fijarAnimaciones(activas) {
    try { localStorage.setItem(CLAVE_ANIM, activas ? 'on' : 'off'); } catch (_) {}
    pintarAnimaciones();
  }

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

  /* Cambio de tema con transición: reveal circular desde el botón (View Transitions);
     si el navegador no lo soporta, un fundido corto de colores. */
  function cambiarConEfecto(id, origen) {
    if (!animacionesActivas() || id === actual()) { aplicar(id); return; }
    if (origen && typeof document.startViewTransition === 'function') {
      const r = origen.getBoundingClientRect();
      const x = r.left + r.width / 2, y = r.top + r.height / 2;
      const radio = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
      const vt = document.startViewTransition(() => aplicar(id));
      vt.ready.then(() => document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radio}px at ${x}px ${y}px)`] },
        { duration: 600, easing: 'ease-in-out', pseudoElement: '::view-transition-new(root)' }
      )).catch(() => {});
      return;
    }
    const html = document.documentElement;
    html.classList.add('tema-fundiendo');
    aplicar(id);
    setTimeout(() => html.classList.remove('tema-fundiendo'), 500);
  }

  /* ── Números que suben desde 0 ────────────────────────────────
     Las tarjetas de estadísticas (.stat-info .valor) cuentan hacia su valor
     cada vez que la página les escribe un número. No toca el valor real:
     al terminar deja exactamente el texto que puso la página. */
  const ultimoEscrito = new WeakMap();   // texto que escribió el propio contador
  const rafContador   = new WeakMap();

  function formatearNumero(v, dec, sepMil, sepDec) {
    const [ent, frac] = v.toFixed(dec).split('.');
    const miles = sepMil ? ent.replace(/\B(?=(\d{3})+(?!\d))/g, sepMil) : ent;
    return frac ? miles + sepDec + frac : miles;
  }

  function contarHasta(el) {
    const texto = el.textContent;
    if (ultimoEscrito.get(el) === texto) return;          // lo escribió el contador
    cancelAnimationFrame(rafContador.get(el));
    if (!animacionesActivas() || document.hidden) return;
    const m = texto.trim().match(/^([^\d-]*)(\d[\d.,]*)(.*)$/);
    if (!m) return;                                        // "—", "Cargando…", etc.
    const [, pre, num, post] = m;
    const d = num.match(/([.,])(\d{1,2})$/);
    const dec = d ? d[2].length : 0;
    const sepDec = d ? d[1] : '';
    const parteEntera = d ? num.slice(0, -(dec + 1)) : num;
    const sepMil = (parteEntera.match(/[.,]/) || [''])[0];
    const destino = parseFloat(parteEntera.replace(/[.,]/g, '') + (dec ? '.' + d[2] : ''));
    if (!isFinite(destino) || destino <= 0) return;

    const t0 = performance.now(), dur = 800;
    const escribir = valor => { ultimoEscrito.set(el, valor); el.textContent = valor; };
    const paso = ahora => {
      const k = Math.min(1, (ahora - t0) / dur);
      if (k >= 1) { escribir(texto); return; }             // el texto original, intacto
      const suave = 1 - Math.pow(1 - k, 3);                // frena al llegar
      escribir(pre + formatearNumero(destino * suave, dec, sepMil, sepDec) + post);
      rafContador.set(el, requestAnimationFrame(paso));
    };
    escribir(pre + formatearNumero(0, dec, sepMil, sepDec) + post);
    rafContador.set(el, requestAnimationFrame(paso));
  }

  if (typeof MutationObserver !== 'undefined') {
    new MutationObserver(muts => {
      const vistos = new Set();
      for (const mu of muts) {
        const nodo = mu.target.nodeType === 1 ? mu.target : mu.target.parentElement;
        const el = nodo && nodo.closest && nodo.closest('.stat-info .valor');
        if (el && !vistos.has(el)) { vistos.add(el); contarHasta(el); }
      }
    }).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
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
        <div class="tema-menu">
          <div role="radiogroup" aria-label="Tema de la aplicación">
          ${TEMAS.map((x, n) => (n === 0 || TEMAS[n - 1].grupo !== x.grupo
              ? `<div class="tema-menu-titulo" role="presentation">${x.grupo}</div>` : '') + `
            <button type="button" class="tema-op" role="radio" data-id="${x.id}" aria-checked="false">
              <span class="tema-muestra"
                    style="background:linear-gradient(135deg,${x.muestra[0]} 50%,${x.muestra[1]} 50%)">${x.logo}</span>
              <span class="tema-txt">${x.nombre}<small>${x.desc}</small></span>
              <span class="tema-check" aria-hidden="true">✓</span>
            </button>`).join('')}
          </div>
          <div class="tema-menu-titulo" role="presentation">Movimiento</div>
          <button type="button" class="tema-anim" role="switch" aria-checked="true">
            <span class="tema-muestra tema-muestra-anim" aria-hidden="true">✨</span>
            <span class="tema-txt">Animaciones<small>Ambiente y movimiento</small></span>
            <span class="tema-switch" aria-hidden="true"><i></i></span>
          </button>
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
        cambiarConEfecto(op.dataset.id, btn);
        cerrarTodos();
        btn.focus();
      });
    });

    /* el interruptor no cierra el menú: así se ve el efecto al probarlo */
    sel.querySelector('.tema-anim').addEventListener('click', () => fijarAnimaciones(!animacionesActivas()));

    marcarSelectores(t.id);
    actualizarLogos(t);
    pintarAnimaciones();
  }

  /* cerrar al hacer clic fuera o con Escape */
  document.addEventListener('click', e => { if (!e.target.closest('.tema-selector')) cerrarTodos(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarTodos(); });

  /* sincronizar con otras pestañas abiertas */
  window.addEventListener('storage', e => {
    if (e.key === claveActual() && porId(e.newValue)) aplicar(e.newValue, { guardarEleccion: false });
    if (e.key === CLAVE_ANIM) pintarAnimaciones();
  });

  /* pestaña no visible → el CSS pausa las animaciones (ahorra batería en las tablets) */
  document.addEventListener('visibilitychange', () => {
    document.documentElement.toggleAttribute('data-oculto', document.hidden);
  });
  if (mqReducir && mqReducir.addEventListener) mqReducir.addEventListener('change', pintarAnimaciones);

  /* La clave única de la versión anterior era compartida por todo el navegador:
     se descarta para que el tema de una persona no "herede" a la siguiente. */
  try { localStorage.removeItem(CLAVE_ANTIGUA); } catch (_) {}

  /* Aplicación inmediata (este script va en el <head>) */
  pintarAnimaciones();
  aplicar(leer(), { guardarEleccion: false });

  return { TEMAS, actual, aplicar, montar, alIniciarSesion,
           animaciones: animacionesActivas, fijarAnimaciones };
})();
