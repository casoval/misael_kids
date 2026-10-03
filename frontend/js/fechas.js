/* ── Fechas en español, semana desde el lunes, formato día/mes/año ──
   Reemplaza el calendario nativo del navegador (que sale en el idioma y
   el orden del sistema: inglés, mes/día/año, domingo primero) por
   flatpickr en español. NO cambia el resto del código:
     · input.value sigue siendo "AAAA-MM-DD" (o "AAAA-MM" en los de mes)
     · asignar input.value = '...' actualiza lo que se ve
     · input.min / input.max / input.disabled se respetan
     · el evento "change" se dispara igual que antes
   Se aplica solo a <input type="date"> y <input type="month">, también a
   los que se crean después (modales armados con JavaScript).
   Para dejar un campo con el selector nativo: data-nativo="1".          */
(function () {
  'use strict';
  if (!window.flatpickr) return;

  flatpickr.localize(flatpickr.l10ns.es);
  flatpickr.l10ns.default.firstDayOfWeek = 1;            // lunes

  const valorNativo = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

  function mejorar(el) {
    if (el._flatpickr || el.dataset.nativo || el.closest('.flatpickr-calendar')) return;
    const mes = el.type === 'month';
    const cfg = {
      locale: 'es',
      altInput: true,
      allowInput: true,
      disableMobile: true,                                // mismo calendario también en celular
      dateFormat: mes ? 'Y-m' : 'Y-m-d',
      altFormat:  mes ? 'F Y' : 'd/m/Y',
      minDate: el.min || null,
      maxDate: el.max || null,
      defaultDate: el.value || null,
      plugins: mes && window.monthSelectPlugin
        ? [new monthSelectPlugin({ shorthand: false, dateFormat: 'Y-m', altFormat: 'F Y' })] : [],
    };
    const fp = flatpickr(el, cfg);
    const alt = fp.altInput;
    if (!alt) return;

    alt.placeholder  = el.placeholder || (mes ? 'Mes y año' : 'dd/mm/aaaa');
    alt.autocomplete = 'off';
    alt.required     = el.required;
    alt.disabled     = el.disabled;
    alt.readOnly     = el.readOnly && !el.disabled ? true : alt.readOnly;
    if (el.style.cssText) alt.style.cssText = el.style.cssText;
    if (el.id) {
      alt.id = el.id + '-vista';
      document.querySelectorAll('label[for="' + el.id + '"]').forEach(l => l.setAttribute('for', alt.id));
    }

    // Asignar input.value desde el código también actualiza el campo visible.
    let ocupado = false;
    Object.defineProperty(el, 'value', {
      configurable: true,
      get() { return valorNativo.get.call(this); },
      set(v) {
        valorNativo.set.call(this, v);
        if (ocupado) return;
        ocupado = true;
        try { fp.setDate(v || null, false); } finally { ocupado = false; }
      },
    });
  }

  function sincronizar(el) {                               // min / max / disabled cambiados por código
    const fp = el._flatpickr;
    if (!fp) return;
    fp.set('minDate', el.min || null);
    fp.set('maxDate', el.max || null);
    if (fp.altInput) { fp.altInput.disabled = el.disabled; }
  }

  function revisar(raiz) {
    if (!raiz || raiz.nodeType !== 1) return;
    if (raiz.matches && raiz.matches('input[type="date"], input[type="month"]')) mejorar(raiz);
    if (raiz.querySelectorAll) raiz.querySelectorAll('input[type="date"], input[type="month"]').forEach(mejorar);
  }

  function limpiar(raiz) {                                 // evita calendarios huérfanos
    if (!raiz || raiz.nodeType !== 1 || !raiz.querySelectorAll) return;
    raiz.querySelectorAll('input').forEach(i => { if (i._flatpickr && !document.contains(i)) i._flatpickr.destroy(); });
  }

  function iniciar() {
    revisar(document.body);
    new MutationObserver(muts => {
      for (const m of muts) {
        if (m.type === 'attributes') { sincronizar(m.target); continue; }
        m.removedNodes.forEach(limpiar);
        m.addedNodes.forEach(revisar);
      }
    }).observe(document.body, {
      childList: true, subtree: true,
      attributes: true, attributeFilter: ['min', 'max', 'disabled'],
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
