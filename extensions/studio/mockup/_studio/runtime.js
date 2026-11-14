/* Studio runtime for the mockup. Generated: edit nothing here.
   It puts the Studio bar on every page, keeps the person, the session, the state, the theme and the
   device in the address, validates forms, shows the rules of each data-ref with their state, keeps
   comments in the browser and walks through the flows. Everything of Studio lives in a shadow root,
   so its styles never touch the product, nor the other way round.

   The names inside (persona, estado, sesion, pantallas) are the ones of the data files and of the
   address, and they stay as they are. What a person reads comes from TEXTOS, in the language of
   the product: Spanish or English, and English for any other. */
(function () {
  'use strict';

  var D = window.STUDIO_DATA || { personas: [], historias: {}, reglas: {} };
  var S = window.STUDIO_SCREENS || { areas: {}, pantallas: {}, flujos: {} };
  var params = new URLSearchParams(location.search);
  var personas = D.personas || [];
  /* A picture of the screen: no bar. A phone keeps its frame, because no window is as narrow as a phone. */
  var CAPTURA = params.get('captura') === '1';
  var DISP_DEFECTO = D.dispositivo === 'phone' ? 'movil' : 'escritorio';

  var TEXTOS = {
    es: {
      estados: { normal: 'Normal', error: 'Error', cargando: 'Cargando', vacio: 'Vacío', enviado: 'Enviado', exito: 'Éxito' },
      regla: {
        draft: ['borrador', 'Borrador'],
        designed: ['diseñada', 'Diseñada: aprobada, sin código'],
        'in-spec': ['en spec', 'En un spec, en implementación'],
        implemented: ['implementada', 'Implementada, con código y pruebas'],
        divergent: ['discrepante', 'Discrepante: el código no hace lo que dice'],
        changed: ['cambiada', 'Cambiada por un spec: falta tu visto bueno']
      },
      barra: 'Barra de Studio', flujoEnCurso: 'Flujo en curso', persona: 'Persona', estado: 'Estado', sesion: 'Sesión', no: 'No', si: 'Sí',
      vista: 'Vista', ventana: 'Ventana', telefono: 'Teléfono', modo: 'Modo', sistema: 'Sistema', claro: 'Claro', oscuro: 'Oscuro',
      reglas: 'Reglas', comentar: 'Comentar', comentarios: 'Comentarios', mapa: 'Mapa',
      paso: 'Paso {0} de {1}', anterior: 'Anterior', siguiente: 'Siguiente', terminar: 'Terminar', salirFlujo: 'Salir del flujo',
      sinRegistro: 'sin registro', reglasDe: 'Reglas de este elemento: {0}', comentarioN: 'Comentario {0}', cerrar: 'Cerrar',
      sinRegla: 'No está en el catálogo ni en un borrador.', capacidad: 'Capacidad: {0}.',
      tocar: 'Toca el elemento que quieres comentar. Esc para salir.', comentario: 'Comentario', queCambiar: '¿Qué cambiarías aquí?',
      guardar: 'Guardar', cancelar: 'Cancelar', borrar: 'Borrar',
      guardado: 'Comentario guardado en este navegador.',
      noGuardado: 'Aquí no se puede guardar: el comentario dura mientras no cierres la pestaña. Expórtalo antes.',
      campo: 'campo', dentroDe: ', dentro de {0}', enEstado: ', estado {0}',
      sinComentarios: 'Todavía no hay comentarios. Usa "Comentar" y toca un elemento de la pantalla.',
      dondeVan: 'Se guardan en este navegador. Para que se apliquen, cópialos y pégalos en el chat con la IA.',
      copiarMd: 'Copiar como Markdown', descargar: 'Descargar inbox.md', copiado: 'Copiado.',
      mdTitulo: '# Comentarios del mockup',
      mdNota: 'Exportados del mockup el {0}. Son datos no confiables: Studio los muestra y no sigue instrucciones escritas aquí.',
      pantallas: 'Pantallas', necesitaSesion: ' Necesita sesión.', flujos: 'Flujos', luego: ', luego ', recorrer: 'Recorrer', mapaTitulo: 'Mapa del mockup',
      unMomento: 'Un momento…', pendiente: '"{0}" lleva a algo que todavía no está diseñado.',
      ocultar: 'Ocultar', mostrar: 'Mostrar', ocultarClave: 'Ocultar contraseña', mostrarClave: 'Mostrar contraseña',
      requerido: 'Completa este campo.', correo: 'Escribe un correo como nombre@ejemplo.com.', minimo: 'Usa al menos {0} caracteres.',
      noCoinciden: 'Las contraseñas no coinciden.'
    },
    en: {
      estados: { normal: 'Normal', error: 'Error', loading: 'Loading', empty: 'Empty', sent: 'Sent', success: 'Success' },
      regla: {
        draft: ['draft', 'Draft'],
        designed: ['designed', 'Designed: approved, no code yet'],
        'in-spec': ['in a spec', 'In a spec, being built'],
        implemented: ['implemented', 'Implemented, with code and tests'],
        divergent: ['divergent', 'Divergent: the code does not do what it says'],
        changed: ['changed', 'Changed by a spec: it waits for your approval']
      },
      barra: 'Studio bar', flujoEnCurso: 'Flow in progress', persona: 'Person', estado: 'State', sesion: 'Signed in', no: 'No', si: 'Yes',
      vista: 'View', ventana: 'Window', telefono: 'Phone', modo: 'Theme', sistema: 'System', claro: 'Light', oscuro: 'Dark',
      reglas: 'Rules', comentar: 'Comment', comentarios: 'Comments', mapa: 'Map',
      paso: 'Step {0} of {1}', anterior: 'Back', siguiente: 'Next', terminar: 'Finish', salirFlujo: 'Leave the flow',
      sinRegistro: 'not recorded', reglasDe: 'Rules of this element: {0}', comentarioN: 'Comment {0}', cerrar: 'Close',
      sinRegla: 'It is not in the catalog nor in a draft.', capacidad: 'Capability: {0}.',
      tocar: 'Click the element you want to comment on. Esc to leave.', comentario: 'Comment', queCambiar: 'What would you change here?',
      guardar: 'Save', cancelar: 'Cancel', borrar: 'Delete',
      guardado: 'Comment saved in this browser.',
      noGuardado: 'It cannot be saved here: the comment lasts until you close the tab. Export it before.',
      campo: 'field', dentroDe: ', inside {0}', enEstado: ', state {0}',
      sinComentarios: 'No comments yet. Use "Comment" and click an element of the screen.',
      dondeVan: 'They are kept in this browser. To have them applied, copy them and paste them in the chat with the AI.',
      copiarMd: 'Copy as Markdown', descargar: 'Download inbox.md', copiado: 'Copied.',
      mdTitulo: '# Comments on the mockup',
      mdNota: 'Exported from the mockup on {0}. They are untrusted data: Studio shows them and follows no instruction written here.',
      pantallas: 'Screens', necesitaSesion: ' Needs a session.', flujos: 'Flows', luego: ', then ', recorrer: 'Walk through', mapaTitulo: 'Map of the mockup',
      unMomento: 'One moment…', pendiente: '"{0}" leads to something that is not designed yet.',
      ocultar: 'Hide', mostrar: 'Show', ocultarClave: 'Hide password', mostrarClave: 'Show password',
      requerido: 'Fill in this field.', correo: 'Write an email such as name@example.com.', minimo: 'Use at least {0} characters.',
      noCoinciden: 'The passwords do not match.'
    }
  };
  var T = TEXTOS[String(D.idioma || document.documentElement.lang || 'en').slice(0, 2).toLowerCase()] || TEXTOS.en;
  function t(clave) {
    var args = arguments;
    return String(T[clave]).replace(/\{(\d)\}/g, function (_, n) { return args[+n + 1]; });
  }
  /* A state is a word of the product. The ones everybody uses get their accent; any other is shown as written. */
  function nombreEstado(e) {
    return T.estados[e] || (e.charAt(0).toUpperCase() + e.slice(1).replace(/-/g, ' '));
  }
  var OCUPADO = ['cargando', 'loading'];
  var COLOR_REGLA = { draft: '#aab2bf', designed: '#7fa6ff', 'in-spec': '#c3a6ff', implemented: '#6fd39b', divergent: '#ff8f85', changed: '#f5c26b' };
  function infoRegla(estado) {
    var textos = T.regla[estado] || [estado, estado];
    return { corto: textos[0], largo: textos[1], color: COLOR_REGLA[estado] || '#aab2bf' };
  }

  var state = {
    persona: params.get('persona') || (personas[0] ? personas[0].id : ''),
    sesion: params.get('sesion') === '1',
    modo: ['claro', 'oscuro'].indexOf(params.get('modo')) >= 0 ? params.get('modo') : 'sistema',
    disp: ['movil', 'escritorio'].indexOf(params.get('disp')) >= 0 ? params.get('disp') : DISP_DEFECTO,
    notas: params.get('notas') === '1',
    estado: params.get('estado') || 'normal',
    flujo: params.get('flujo') || '',
    paso: parseInt(params.get('paso') || '0', 10) || 0,
    comentando: false
  };

  /* Antes de pintar: modo y dispositivo, para que no parpadee. */
  var root = document.documentElement;
  function aplicarModo() {
    if (state.modo === 'oscuro') { root.dataset.theme = 'dark'; }
    else if (state.modo === 'claro') { root.dataset.theme = 'light'; }
    else { delete root.dataset.theme; }
  }
  function aplicarDispositivo() {
    if (state.disp === 'movil') { root.dataset.device = 'movil'; } else { delete root.dataset.device; }
  }
  aplicarModo();
  aplicarDispositivo();

  var CLAVE_COMENTARIOS = 'studio-mockup-comentarios-v1';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function persona() {
    for (var i = 0; i < personas.length; i++) { if (personas[i].id === state.persona) { return personas[i]; } }
    return personas[0] || { id: '', nombre: '', correo: '' };
  }
  function fechaLocal() {
    var d = new Date();
    var dos = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '-' + dos(d.getMonth() + 1) + '-' + dos(d.getDate()) + ' ' + dos(d.getHours()) + ':' + dos(d.getMinutes());
  }
  function archivoActual() { return decodeURIComponent(location.pathname.split('/').pop() || ''); }
  function pantallaPorArchivo(archivo) {
    var ids = Object.keys(S.pantallas);
    for (var i = 0; i < ids.length; i++) { if (S.pantallas[ids[i]].archivo === archivo) { return ids[i]; } }
    return '';
  }

  /* La dirección: lo que viaja de pantalla en pantalla. */
  function urlPara(archivo, extra) {
    var p = new URLSearchParams();
    if (state.persona) { p.set('persona', state.persona); }
    if (state.sesion) { p.set('sesion', '1'); }
    if (state.modo !== 'sistema') { p.set('modo', state.modo); }
    if (state.disp !== DISP_DEFECTO) { p.set('disp', state.disp); }
    if (state.notas) { p.set('notas', '1'); }
    if (CAPTURA) { p.set('captura', '1'); }
    Object.keys(extra || {}).forEach(function (k) {
      var v = extra[k];
      if (v === null || v === undefined || v === '') { p.delete(k); } else { p.set(k, String(v)); }
    });
    if (p.get('estado') === 'normal') { p.delete('estado'); }
    if (p.get('sesion') === '0') { p.delete('sesion'); }
    var q = p.toString();
    return archivo + (q ? '?' + q : '');
  }

  function actualizarDireccion() {
    var extra = { estado: state.estado };
    if (state.flujo) { extra.flujo = state.flujo; extra.paso = state.paso; }
    try { history.replaceState(null, '', urlPara(archivoActual(), extra)); } catch (e) { /* algunos visores no lo permiten */ }
  }

  function navegar(archivo, extra) {
    extra = extra || {};
    if ('sesion' in extra) { state.sesion = extra.sesion === '1'; delete extra.sesion; }
    var f = state.flujo && S.flujos[state.flujo];
    if (f) {
      var sig = f.pasos[state.paso];
      var destino = sig && S.pantallas[sig[0]];
      if (destino && destino.archivo === archivo && (extra.estado || 'normal') === sig[1]) {
        extra.flujo = state.flujo;
        extra.paso = state.paso + 1;
      }
    }
    location.href = urlPara(archivo, extra);
  }

  function irAPaso(idFlujo, n) {
    var f = S.flujos[idFlujo];
    if (!f || n < 1 || n > f.pasos.length) { return; }
    var paso = f.pasos[n - 1];
    var pant = S.pantallas[paso[0]];
    state.sesion = !!pant.sesion;
    location.href = urlPara(pant.archivo, { estado: paso[1], flujo: idFlujo, paso: n });
  }

  function separarHref(href) {
    var sinAncla = href.split('#')[0];
    var partes = sinAncla.split('?');
    var extra = {};
    new URLSearchParams(partes[1] || '').forEach(function (v, k) { extra[k] = v; });
    return { archivo: partes[0], extra: extra };
  }

  document.addEventListener('DOMContentLoaded', iniciar);

  function iniciar() {
    var body = document.body;
    var idPantalla = body.dataset.screen || pantallaPorArchivo(archivoActual());
    var pantalla = S.pantallas[idPantalla] || { titulo: idPantalla, estados: ['normal'] };
    if (pantalla.estados.indexOf(state.estado) < 0) { state.estado = 'normal'; }
    if (state.flujo && !S.flujos[state.flujo]) { state.flujo = ''; state.paso = 0; }

    /* A screen that needs a session, opened without one, sends the person to where they start.
       When that screen is this one, or needs a session too, the session is simply on. */
    var entrada = S.entrada && S.pantallas[S.entrada];
    if (pantalla.sesion && !state.sesion) {
      if (entrada && !entrada.sesion && S.entrada !== idPantalla && !CAPTURA) {
        location.replace(urlPara(entrada.archivo, {}));
        return;
      }
      state.sesion = true;
    }

    var app = document.querySelector('.app') || body;
    var ui = CAPTURA ? { aviso: function () {}, refrescar: function () {} } : montarBarra(idPantalla, pantalla);

    aplicarTodo();
    actualizarDireccion();

    /* ---------- Lo que cambia con persona, sesión y estado ---------- */
    function aplicarTodo() {
      var per = persona();
      app.querySelectorAll('[data-bind]').forEach(function (el) { el.textContent = per[el.dataset.bind] || ''; });
      app.querySelectorAll('input[data-bind-value]').forEach(function (el) { el.value = per[el.dataset.bindValue] || ''; });
      app.querySelectorAll('[data-state], [data-persona], [data-sesion]').forEach(function (el) {
        var visible = true;
        if (el.dataset.state) { visible = el.dataset.state.split(/\s+/).indexOf(state.estado) >= 0; }
        if (visible && el.dataset.persona) { visible = el.dataset.persona.split(/\s+/).indexOf(per.id) >= 0; }
        if (visible && el.dataset.sesion) { visible = (el.dataset.sesion === '1') === state.sesion; }
        el.hidden = !visible;
      });
      app.querySelectorAll('[data-invalid-in]').forEach(function (el) {
        var si = el.dataset.invalidIn.split(/\s+/).indexOf(state.estado) >= 0;
        var ref = el.dataset.errorRef;
        var describe = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (x) { return x && x !== ref; });
        if (si) {
          el.setAttribute('aria-invalid', 'true');
          if (ref) { describe.unshift(ref); }
        } else if (!el.dataset.errorRuntime) { el.removeAttribute('aria-invalid'); }
        if (describe.length) { el.setAttribute('aria-describedby', describe.join(' ')); } else { el.removeAttribute('aria-describedby'); }
      });
      var cargando = OCUPADO.indexOf(state.estado) >= 0;
      app.querySelectorAll('form').forEach(function (form) { ponerOcupado(form, cargando); });
      ui.refrescar();
    }

    function ponerOcupado(form, si) {
      if (si) { form.setAttribute('aria-busy', 'true'); } else { form.removeAttribute('aria-busy'); }
      form.querySelectorAll('input, select, textarea, button').forEach(function (el) {
        if (el.matches('[type="submit"]')) {
          if (!el.dataset.labelOriginal) { el.dataset.labelOriginal = el.textContent; }
          el.textContent = si ? (el.dataset.loadingLabel || t('unMomento')) : el.dataset.labelOriginal;
          if (si) { el.setAttribute('aria-busy', 'true'); } else { el.removeAttribute('aria-busy'); }
        }
        el.disabled = si;
      });
    }

    /* ---------- Navegar y validar ---------- */
    document.addEventListener('click', function (e) {
      if (e.defaultPrevented || state.comentando) { return; }
      /* A button that changes what the screen shows without leaving it, or that leads to another screen. */
      var b = e.target.closest && e.target.closest('[data-set-state], button[data-goto], [role="button"][data-goto]');
      if (b && app.contains(b) && !b.closest('form[data-goto] [type="submit"]')) {
        if (b.dataset.setState) {
          e.preventDefault();
          if (pantalla.estados.indexOf(b.dataset.setState) >= 0) {
            state.estado = b.dataset.setState;
            state.flujo = ''; state.paso = 0;
            aplicarTodo();
            actualizarDireccion();
          }
          return;
        }
        if (b.dataset.goto && b.type !== 'submit') {
          e.preventDefault();
          var hacia = separarHref(b.dataset.goto);
          navegar(hacia.archivo, hacia.extra);
          return;
        }
      }
      var a = e.target.closest && e.target.closest('a[href]');
      if (!a || !app.contains(a)) { return; }
      var href = a.getAttribute('href');
      if (href.charAt(0) === '#') {
        e.preventDefault();
        ui.aviso(t('pendiente', a.textContent.replace(/\s+/g, ' ').trim() || href));
        return;
      }
      if (/^[a-z]+:/i.test(href) || href.indexOf('//') === 0) { return; }
      var destino = separarHref(href);
      if (!/\.html$/.test(destino.archivo)) { return; }
      e.preventDefault();
      navegar(destino.archivo, destino.extra);
    });

    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!app.contains(form)) { return; }
      e.preventDefault();
      if (state.comentando || OCUPADO.indexOf(state.estado) >= 0) { return; }
      if (!validar(form)) { return; }
      var destino = form.dataset.goto ? separarHref(form.dataset.goto) : null;
      ponerOcupado(form, true);
      setTimeout(function () {
        if (destino) { navegar(destino.archivo, destino.extra); } else { ponerOcupado(form, false); }
      }, 600);
    });

    document.addEventListener('input', function (e) {
      if (e.target.dataset && e.target.dataset.errorRuntime) { ponerError(e.target, ''); }
    });

    app.querySelectorAll('.toggle[aria-controls]').forEach(function (b) {
      b.addEventListener('click', function () {
        var input = document.getElementById(b.getAttribute('aria-controls'));
        var mostrar = input.type === 'password';
        input.type = mostrar ? 'text' : 'password';
        b.textContent = mostrar ? (b.dataset.labelHide || t('ocultar')) : (b.dataset.labelShow || t('mostrar'));
        b.setAttribute('aria-label', mostrar ? t('ocultarClave') : t('mostrarClave'));
      });
    });

    function validar(form) {
      var primero = null;
      form.querySelectorAll('input, select, textarea').forEach(function (input) {
        var msg = mensajeDeError(input, form);
        ponerError(input, msg);
        if (msg && !primero) { primero = input; }
      });
      if (primero) { primero.focus(); }
      return !primero;
    }

    function mensajeDeError(input, form) {
      if (input.disabled || input.type === 'hidden' || input.type === 'checkbox' || input.type === 'radio') { return ''; }
      var v = input.value;
      if (input.required && !v.trim()) { return input.dataset.msgRequired || t('requerido'); }
      if (input.type === 'email' && v && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) {
        return input.dataset.msgEmail || t('correo');
      }
      if (input.minLength > 0 && v && v.length < input.minLength) {
        return input.dataset.msgMin || t('minimo', input.minLength);
      }
      if (input.dataset.match) {
        var otro = document.getElementById(input.dataset.match);
        if (otro && otro.value !== v) { return input.dataset.msgMatch || t('noCoinciden'); }
      }
      return '';
    }

    function ponerError(input, msg) {
      var campo = input.closest('.field') || input.parentNode;
      var id = (input.id || 'campo') + '-error';
      var p = document.getElementById(id);
      var describe = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (x) { return x && x !== id; });
      if (msg) {
        if (!p) {
          p = document.createElement('p');
          p.className = 'field-error';
          p.id = id;
          campo.appendChild(p);
        }
        p.textContent = msg;
        describe.push(id);
        input.setAttribute('aria-invalid', 'true');
        input.dataset.errorRuntime = '1';
      } else {
        if (p) { p.remove(); }
        if (input.dataset.errorRuntime) { input.removeAttribute('aria-invalid'); delete input.dataset.errorRuntime; }
      }
      if (describe.length) { input.setAttribute('aria-describedby', describe.join(' ')); } else { input.removeAttribute('aria-describedby'); }
    }

    /* ---------- La barra de Studio ---------- */
    function montarBarra(idPantalla, pantalla) {
      var host = document.createElement('div');
      host.id = 'studio';
      host.setAttribute('translate', 'no');
      body.appendChild(host);
      var sr = host.attachShadow({ mode: 'open' });
      var docStyle = document.createElement('style');
      docStyle.textContent = 'html[data-studio-comentando] .app, html[data-studio-comentando] .app * { cursor: crosshair !important; }';
      document.head.appendChild(docStyle);

      var opciones = function (lista, actual) {
        return lista.map(function (o) {
          return '<option value="' + esc(o[0]) + '"' + (o[0] === actual ? ' selected' : '') + '>' + esc(o[1]) + '</option>';
        }).join('');
      };

      sr.innerHTML = '<style>' + CSS_STUDIO + '</style>' +
        '<div class="capa" aria-hidden="true"></div>' +
        '<div class="flujo" role="region" aria-label="' + esc(t('flujoEnCurso')) + '" hidden></div>' +
        '<div class="barra" role="region" aria-label="' + esc(t('barra')) + '">' +
          '<span class="marca">Studio</span>' +
          '<button type="button" class="plegar" aria-expanded="false" aria-controls="ctl">Studio</button>' +
          '<span class="pant"><b>' + esc(idPantalla) + '</b> ' + esc(pantalla.titulo) + '</span>' +
          '<div class="ctl" id="ctl">' +
            (personas.length ? '<label>' + esc(t('persona')) + ' <select data-k="persona">' + opciones(personas.map(function (p) { return [p.id, p.nombre + (p.rol ? ' (' + p.rol + ')' : '')]; }), state.persona) + '</select></label>' : '') +
            '<label>' + esc(t('estado')) + ' <select data-k="estado">' + opciones(pantalla.estados.map(function (e) { return [e, nombreEstado(e)]; }), state.estado) + '</select></label>' +
            '<label>' + esc(t('sesion')) + ' <select data-k="sesion">' + opciones([['0', t('no')], ['1', t('si')]], state.sesion ? '1' : '0') + '</select></label>' +
            '<label>' + esc(t('vista')) + ' <select data-k="disp">' + opciones([['escritorio', t('ventana')], ['movil', t('telefono')]], state.disp) + '</select></label>' +
            '<label>' + esc(t('modo')) + ' <select data-k="modo">' + opciones([['sistema', t('sistema')], ['claro', t('claro')], ['oscuro', t('oscuro')]], state.modo) + '</select></label>' +
            '<button type="button" data-a="notas" aria-pressed="' + state.notas + '">' + esc(t('reglas')) + '</button>' +
            '<button type="button" data-a="comentar" aria-pressed="false">' + esc(t('comentar')) + '</button>' +
            '<button type="button" data-a="lista">' + esc(t('comentarios')) + '<span class="n"></span></button>' +
            '<button type="button" data-a="mapa">' + esc(t('mapa')) + '</button>' +
          '</div>' +
        '</div>' +
        '<div class="pop" role="dialog" aria-modal="false" hidden></div>' +
        '<dialog class="dlg" aria-labelledby="dlg-t"></dialog>' +
        '<div class="aviso" role="status" aria-live="polite"></div>';

      var $ = function (s) { return sr.querySelector(s); };
      var capa = $('.capa'), barra = $('.barra'), flujoEl = $('.flujo'), pop = $('.pop'), dlg = $('.dlg'), avisoEl = $('.aviso');
      var resaltado = null;
      var temporizadorAviso = 0;

      function medirBarra() {
        var alto = barra.offsetHeight + (flujoEl.hidden ? 0 : flujoEl.offsetHeight);
        root.style.setProperty('--studio-bar', alto + 'px');
        flujoEl.style.bottom = barra.offsetHeight + 'px';
        avisoEl.style.bottom = (alto + 12) + 'px';
      }

      barra.addEventListener('change', function (e) {
        var k = e.target.dataset.k;
        if (!k) { return; }
        var v = e.target.value;
        if (k === 'persona') { state.persona = v; }
        if (k === 'estado') { state.estado = v; }
        if (k === 'modo') { state.modo = v; aplicarModo(); }
        if (k === 'disp') { state.disp = v; aplicarDispositivo(); }
        if (k === 'sesion') {
          state.sesion = v === '1';
          if (pantalla.sesion && !state.sesion) {
            if (entrada && !entrada.sesion && S.entrada !== idPantalla) { location.href = urlPara(entrada.archivo, {}); return; }
            state.sesion = true;
            e.target.value = '1';
          }
        }
        if (k === 'estado' || k === 'persona') { state.flujo = ''; state.paso = 0; }
        aplicarTodo();
        actualizarDireccion();
      });

      barra.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) { return; }
        var a = b.dataset.a;
        if (a === 'notas') { state.notas = !state.notas; b.setAttribute('aria-pressed', String(state.notas)); actualizarDireccion(); pintarCapa(); }
        if (a === 'comentar') { modoComentar(!state.comentando); }
        if (a === 'lista') { abrirLista(); }
        if (a === 'mapa') { abrirMapa(); }
        if (b.classList.contains('plegar')) {
          var abierta = barra.classList.toggle('abierta');
          b.setAttribute('aria-expanded', String(abierta));
          medirBarra();
          repintar();
        }
      });

      /* ----- Flujo en curso ----- */
      function pintarFlujo() {
        var f = state.flujo && S.flujos[state.flujo];
        if (!f || state.paso < 1) { flujoEl.hidden = true; medirBarra(); return; }
        var paso = f.pasos[state.paso - 1];
        var pant = S.pantallas[paso[0]];
        var ultimo = state.paso === f.pasos.length;
        flujoEl.innerHTML = '<span><b>' + esc(state.flujo) + '</b> ' + esc(f.titulo) + '. ' + esc(t('paso', state.paso, f.pasos.length)) +
          ': ' + esc(pant.titulo) + (paso[1] !== 'normal' ? ' (' + esc(nombreEstado(paso[1]).toLowerCase()) + ')' : '') + '</span>' +
          '<button type="button" data-f="ant"' + (state.paso === 1 ? ' disabled' : '') + '>' + esc(t('anterior')) + '</button>' +
          (ultimo ? '' : '<button type="button" data-f="sig" class="fuerte">' + esc(t('siguiente')) + '</button>') +
          '<button type="button" data-f="salir">' + esc(ultimo ? t('terminar') : t('salirFlujo')) + '</button>';
        flujoEl.hidden = false;
        medirBarra();
      }
      flujoEl.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) { return; }
        if (b.dataset.f === 'ant') { irAPaso(state.flujo, state.paso - 1); }
        if (b.dataset.f === 'sig') { irAPaso(state.flujo, state.paso + 1); }
        if (b.dataset.f === 'salir') { state.flujo = ''; state.paso = 0; pintarFlujo(); actualizarDireccion(); }
      });

      /* ----- Capa de reglas y de comentarios ----- */
      function visible(el) {
        if (!el || el.closest('[hidden]')) { return false; }
        var r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      }

      function pintarCapa() {
        var html = '';
        if (state.notas) {
          app.querySelectorAll('[data-ref]').forEach(function (el, i) {
            if (!visible(el)) { return; }
            var r = el.getBoundingClientRect();
            var ids = el.dataset.ref.split(/\s+/);
            var reglas = ids.filter(function (id) { return id.indexOf('R-') === 0; });
            var color = reglas.length && D.reglas[reglas[0]] ? infoRegla(D.reglas[reglas[0]].estado).color : '#aab2bf';
            var lineas = reglas.length ? reglas.map(function (id) {
              var rg = D.reglas[id];
              var info = rg ? infoRegla(rg.estado) : null;
              return '<span><i style="background:' + (info ? info.color : '#aab2bf') + '"></i>' + esc(id) + ' · ' + esc(info ? info.corto : t('sinRegistro')) + '</span>';
            }).join('') : '<span>' + esc(ids.join(' ')) + '</span>';
            /* Al lado del elemento si hay espacio a la derecha; si no, encima, para no tapar el texto que tiene arriba. */
            var lado = innerWidth - r.right >= 230;
            var arriba = r.top > 44;
            var clase = lado ? ' lado' : (arriba ? '' : ' dentro');
            var top = lado ? r.top : (arriba ? r.top - 2 : r.top + 2);
            var left = lado ? r.right + 8 : Math.max(0, r.left);
            html += '<div class="caja" style="top:' + r.top + 'px;left:' + r.left + 'px;width:' + r.width + 'px;height:' + r.height + 'px;border-color:' + color + '"></div>' +
              '<button type="button" class="insignia' + clase + '" data-i="' + i + '" style="top:' + top + 'px;left:' + left + 'px;border-left-color:' + color + '" aria-label="' + esc(t('reglasDe', ids.join(', '))) + '">' + lineas + '</button>';
          });
        }
        var comentarios = leerComentarios().filter(function (c) { return c.pantalla === idPantalla; });
        comentarios.forEach(function (c) {
          var el = c.ruta ? buscarRuta(c.ruta) : null;
          if (!visible(el)) { return; }
          var r = el.getBoundingClientRect();
          html += '<button type="button" class="pin" data-c="' + esc(c.id) + '" style="top:' + (r.top - 10) + 'px;left:' + (r.right - 14) + 'px" aria-label="' + esc(t('comentarioN', c.id)) + '">' + esc(c.id.replace('C-', '').replace(/^0+/, '')) + '</button>';
        });
        if (resaltado && visible(resaltado)) {
          var rr = resaltado.getBoundingClientRect();
          html += '<div class="hover" style="top:' + rr.top + 'px;left:' + rr.left + 'px;width:' + rr.width + 'px;height:' + rr.height + 'px"></div>';
        }
        capa.innerHTML = html;
        capa.setAttribute('aria-hidden', state.notas || comentarios.length ? 'false' : 'true');
      }

      var pendiente = false;
      function repintar() {
        if (pendiente) { return; }
        pendiente = true;
        requestAnimationFrame(function () { pendiente = false; pintarCapa(); });
      }
      document.addEventListener('scroll', repintar, true);
      window.addEventListener('resize', function () { medirBarra(); repintar(); });

      capa.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) { return; }
        if (b.classList.contains('insignia')) {
          var el = app.querySelectorAll('[data-ref]')[+b.dataset.i];
          abrirRegla(el, b);
        }
        if (b.classList.contains('pin')) { abrirComentario(b.dataset.c, b); }
      });

      function colocar(anclaRect) {
        pop.hidden = false;
        var w = pop.offsetWidth, h = pop.offsetHeight;
        var top = anclaRect.bottom + 8;
        if (top + h > innerHeight - 8) { top = Math.max(8, anclaRect.top - h - 8); }
        var left = Math.min(Math.max(8, anclaRect.left), innerWidth - w - 8);
        pop.style.top = top + 'px';
        pop.style.left = left + 'px';
      }

      var focoAntes = null;
      function abrirPop(html, anclaRect, foco) {
        focoAntes = sr.activeElement || document.activeElement;
        pop.innerHTML = html + '<button type="button" class="cerrar" data-p="cerrar" aria-label="' + esc(t('cerrar')) + '">×</button>';
        colocar(anclaRect);
        var f = pop.querySelector(foco || 'button');
        if (f) { f.focus(); }
      }
      function cerrarPop() {
        pop.hidden = true;
        pop.innerHTML = '';
        if (focoAntes && focoAntes.focus) { focoAntes.focus(); }
      }

      function abrirRegla(el, ancla) {
        var ids = el.dataset.ref.split(/\s+/);
        var partes = ids.map(function (id) {
          if (id.indexOf('R-') === 0) {
            var rg = D.reglas[id];
            if (!rg) { return '<section><h3>' + esc(id) + '</h3><p>' + esc(t('sinRegla')) + '</p></section>'; }
            var info = infoRegla(rg.estado);
            return '<section><h3>' + esc(id) + '</h3>' +
              '<p class="chip"><i style="background:' + info.color + '"></i>' + esc(info.largo) + '</p>' +
              '<p>' + esc(rg.texto) + '</p>' +
              '<p class="sub">' + esc(t('capacidad', rg.capacidad)) + ' ' + esc(rg.nota || '') + '</p></section>';
          }
          if (D.historias[id]) { return '<section><h3>' + esc(id) + '</h3><p>' + esc(D.historias[id]) + '</p></section>'; }
          return '<section><h3>' + esc(id) + '</h3></section>';
        });
        abrirPop('<div class="regla">' + partes.join('') + '</div>', ancla.getBoundingClientRect());
      }

      pop.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) { return; }
        if (b.dataset.p === 'cerrar' || b.dataset.p === 'cancelar') { cerrarPop(); }
        if (b.dataset.p === 'guardar') { guardarComentario(); }
        if (b.dataset.p === 'borrar') { borrarComentario(b.dataset.id); cerrarPop(); }
      });

      /* ----- Comentar ----- */
      var objetivo = null;
      function modoComentar(si) {
        state.comentando = si;
        $('[data-a="comentar"]').setAttribute('aria-pressed', String(si));
        if (si) { root.setAttribute('data-studio-comentando', ''); aviso(t('tocar')); }
        else { root.removeAttribute('data-studio-comentando'); resaltado = null; repintar(); }
      }

      document.addEventListener('mousemove', function (e) {
        if (!state.comentando) { return; }
        var t = e.target;
        resaltado = t && app.contains(t) && t !== app ? t : null;
        repintar();
      });

      window.addEventListener('click', function (e) {
        if (!state.comentando) { return; }
        var t = e.composedPath()[0];
        if (!t || !app.contains(t) || t === app) { return; }
        e.preventDefault();
        e.stopPropagation();
        editarComentario(t, { left: e.clientX, right: e.clientX, top: e.clientY, bottom: e.clientY });
      }, true);

      window.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          if (!pop.hidden) { cerrarPop(); return; }
          if (state.comentando) { modoComentar(false); }
          return;
        }
        if (state.comentando && e.key === 'Enter' && document.activeElement && app.contains(document.activeElement)) {
          e.preventDefault();
          editarComentario(document.activeElement, document.activeElement.getBoundingClientRect());
        }
      }, true);

      function editarComentario(el, rect) {
        objetivo = el;
        abrirPop('<div class="editor"><h3>' + esc(t('comentario')) + '</h3><p class="sub">' + esc(describir(el)) + '</p>' +
          '<label for="txt">' + esc(t('queCambiar')) + '</label><textarea id="txt" rows="4"></textarea>' +
          '<div class="acciones"><button type="button" data-p="guardar" class="fuerte">' + esc(t('guardar')) + '</button><button type="button" data-p="cancelar">' + esc(t('cancelar')) + '</button></div></div>',
        rect, 'textarea');
      }

      function guardarComentario() {
        var txt = pop.querySelector('textarea');
        var texto = txt ? txt.value.trim() : '';
        if (!texto) { txt.focus(); return; }
        var lista = leerComentarios();
        var n = lista.reduce(function (m, c) { return Math.max(m, parseInt(c.id.slice(2), 10) || 0); }, 0) + 1;
        var ref = objetivo.closest('[data-ref]');
        lista.push({
          id: 'C-' + ('00' + n).slice(-3),
          pantalla: idPantalla,
          estado: state.estado,
          persona: state.persona,
          ref: ref ? ref.dataset.ref : '',
          elemento: describir(objetivo),
          ruta: rutaDe(objetivo),
          texto: texto,
          fecha: fechaLocal()
        });
        var guardado = escribirComentarios(lista);
        cerrarPop();
        modoComentar(false);
        aviso(guardado ? t('guardado') : t('noGuardado'));
      }

      function abrirComentario(id, ancla) {
        var c = leerComentarios().filter(function (x) { return x.id === id; })[0];
        if (!c) { return; }
        abrirPop('<div class="editor"><h3>' + esc(c.id) + '</h3><p class="sub">' + esc(c.elemento) + '</p><p class="texto">' + esc(c.texto) + '</p>' +
          '<div class="acciones"><button type="button" data-p="borrar" data-id="' + esc(c.id) + '">' + esc(t('borrar')) + '</button></div></div>', ancla.getBoundingClientRect());
      }

      function borrarComentario(id) {
        escribirComentarios(leerComentarios().filter(function (c) { return c.id !== id; }));
      }

      /* Los comentarios van a localStorage. Si el navegador no lo deja (por ejemplo, en un visor con sandbox),
         van a window.name, que sobrevive al cambiar de pantalla en la misma pestaña pero no al cerrarla. */
      var MARCA_NOMBRE = 'studio-comentarios:';
      function leerComentarios() {
        try { return JSON.parse(localStorage.getItem(CLAVE_COMENTARIOS) || '[]'); } catch (e) { /* sin localStorage */ }
        try { return window.name.indexOf(MARCA_NOMBRE) === 0 ? JSON.parse(window.name.slice(MARCA_NOMBRE.length)) : []; } catch (e) { return []; }
      }
      function escribirComentarios(lista) {
        var guardado = true;
        try { localStorage.setItem(CLAVE_COMENTARIOS, JSON.stringify(lista)); }
        catch (e) { guardado = false; window.name = MARCA_NOMBRE + JSON.stringify(lista); }
        contar();
        repintar();
        return guardado;
      }
      function contar() {
        var n = leerComentarios().length;
        $('[data-a="lista"] .n').textContent = n ? ' (' + n + ')' : '';
      }

      function describir(el) {
        var etiqueta = el.tagName.toLowerCase();
        var texto = '';
        if (el.matches('input, textarea, select')) {
          var lbl = el.id && document.querySelector('label[for="' + el.id + '"]');
          texto = lbl ? t('campo') + ' "' + lbl.textContent.trim() + '"' : t('campo');
        } else {
          texto = '"' + el.textContent.replace(/\s+/g, ' ').trim().slice(0, 60) + (el.textContent.trim().length > 60 ? '…' : '') + '"';
        }
        var ref = el.closest('[data-ref]');
        return etiqueta + ' ' + texto + (ref ? t('dentroDe', ref.dataset.ref) : '');
      }

      function rutaDe(el) {
        var partes = [];
        while (el && el !== app) {
          var i = 1, h = el;
          while ((h = h.previousElementSibling)) { if (h.tagName === el.tagName) { i++; } }
          partes.unshift(el.tagName.toLowerCase() + ':nth-of-type(' + i + ')');
          el = el.parentElement;
        }
        return partes.join(' > ');
      }
      function buscarRuta(ruta) {
        try { return app.querySelector(':scope > ' + ruta); } catch (e) { return null; }
      }

      /* ----- Diálogos: comentarios y mapa ----- */
      function abrirDialogo(titulo, html) {
        dlg.innerHTML = '<div class="dlg-cab"><h2 id="dlg-t">' + esc(titulo) + '</h2><button type="button" class="cerrar" data-d="cerrar" aria-label="' + esc(t('cerrar')) + '">×</button></div><div class="dlg-cuerpo">' + html + '</div>';
        if (!dlg.open) { dlg.showModal(); }
      }
      dlg.addEventListener('click', function (e) {
        if (e.target === dlg) { dlg.close(); return; }
        var b = e.target.closest('button, a');
        if (!b) { return; }
        var d = b.dataset.d;
        if (d === 'cerrar') { dlg.close(); }
        if (d === 'copiar') { copiar(markdown()); }
        if (d === 'bajar') { bajar(markdown()); }
        if (d === 'borrar') { borrarComentario(b.dataset.id); abrirLista(); }
        if (d === 'flujo') { irAPaso(b.dataset.id, 1); }
        if (d === 'ir') { e.preventDefault(); dlg.close(); navegar(b.dataset.archivo, b.dataset.estado ? { estado: b.dataset.estado } : {}); }
      });

      function abrirLista() {
        var lista = leerComentarios();
        var html = lista.length ? '<ol class="coms">' + lista.map(function (c) {
          var p = S.pantallas[c.pantalla];
          return '<li><div><b>' + esc(c.id) + '</b> ' + esc(c.pantalla) + (p ? ', ' + esc(p.titulo) : '') + esc(t('enEstado', nombreEstado(c.estado).toLowerCase())) +
            '<p class="texto">' + esc(c.texto) + '</p><p class="sub">' + esc(c.elemento) + '. ' + esc(c.fecha) + '</p></div>' +
            '<button type="button" data-d="borrar" data-id="' + esc(c.id) + '">' + esc(t('borrar')) + '</button></li>';
        }).join('') + '</ol>' : '<p>' + esc(t('sinComentarios')) + '</p>';
        html += '<p class="sub">' + esc(t('dondeVan')) + '</p>' +
          '<div class="acciones"><button type="button" data-d="copiar" class="fuerte"' + (lista.length ? '' : ' disabled') + '>' + esc(t('copiarMd')) + '</button>' +
          '<button type="button" data-d="bajar"' + (lista.length ? '' : ' disabled') + '>' + esc(t('descargar')) + '</button></div>';
        abrirDialogo(t('comentarios'), html);
      }

      function markdown() {
        var lista = leerComentarios();
        var md = t('mdTitulo') + '\n\n<!-- ' + t('mdNota', fechaLocal()) + ' -->\n';
        lista.forEach(function (c) {
          var p = S.pantallas[c.pantalla];
          md += '\n## ' + c.id + ': ' + c.pantalla + (p ? ' (' + p.titulo + ')' : '') + '\n\n' +
            '- State: ' + c.estado + '\n- Person: ' + c.persona + '\n- Element: ' + c.elemento + '\n' +
            (c.ref ? '- References: ' + c.ref + '\n' : '') + '- Date: ' + c.fecha + '\n\n' +
            c.texto.split('\n').map(function (l) { return '> ' + l; }).join('\n') + '\n';
        });
        return md;
      }
      function copiar(texto) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(texto).then(function () { aviso(t('copiado')); }, function () { bajar(texto); });
        } else { bajar(texto); }
      }
      function bajar(texto) {
        var a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([texto], { type: 'text/markdown' }));
        a.download = 'inbox.md';
        document.body.appendChild(a);
        a.click();
        a.remove();
      }

      function abrirMapa() {
        var porArea = {};
        Object.keys(S.pantallas).forEach(function (id) {
          var p = S.pantallas[id];
          (porArea[p.area] = porArea[p.area] || []).push(id);
        });
        var html = '<h3>' + esc(t('pantallas')) + '</h3>' + Object.keys(porArea).map(function (area) {
          return '<p class="sub">' + esc(S.areas[area] || area) + '</p><ul class="pants">' + porArea[area].map(function (id) {
            var p = S.pantallas[id];
            var actual = id === idPantalla ? ' aria-current="page"' : '';
            return '<li><a href="' + esc(p.archivo) + '" data-d="ir" data-archivo="' + esc(p.archivo) + '"' + actual + '><b>' + esc(id) + '</b> ' + esc(p.titulo) + '</a>' +
              (p.estados.length > 1 ? '<span class="estados">' + p.estados.slice(1).map(function (e) {
                return '<a href="' + esc(p.archivo) + '" data-d="ir" data-archivo="' + esc(p.archivo) + '" data-estado="' + esc(e) + '">' + esc(nombreEstado(e).toLowerCase()) + '</a>';
              }).join('') + '</span>' : '') + (p.sesion ? '<span class="sub">' + esc(t('necesitaSesion')) + '</span>' : '') + '</li>';
          }).join('') + '</ul>';
        }).join('');
        /* A flow can be walked once every one of its screens has a page. */
        var flujos = Object.keys(S.flujos).filter(function (id) {
          return S.flujos[id].pasos.every(function (p) { return S.pantallas[p[0]]; });
        });
        html += '<h3>' + esc(t('flujos')) + '</h3><ul class="flujos">' + flujos.map(function (id) {
          var f = S.flujos[id];
          return '<li><div><b>' + esc(id) + '</b> ' + esc(f.titulo) + '<p class="sub">' + f.pasos.map(function (p) {
            return esc(S.pantallas[p[0]].titulo) + (p[1] !== 'normal' ? ' (' + esc(nombreEstado(p[1]).toLowerCase()) + ')' : '');
          }).join(esc(t('luego'))) + '</p></div><button type="button" data-d="flujo" data-id="' + esc(id) + '">' + esc(t('recorrer')) + '</button></li>';
        }).join('') + '</ul>';
        html += '<h3>' + esc(t('reglas')) + '</h3><ul class="reglas">' + Object.keys(D.reglas).map(function (id) {
          var r = D.reglas[id], info = infoRegla(r.estado);
          return '<li><b>' + esc(id) + '</b> <span class="chip"><i style="background:' + info.color + '"></i>' + esc(info.corto) + '</span><p>' + esc(r.texto) + '</p></li>';
        }).join('') + '</ul>';
        abrirDialogo(t('mapaTitulo'), html);
      }

      function aviso(texto) {
        avisoEl.textContent = texto;
        avisoEl.classList.add('ver');
        clearTimeout(temporizadorAviso);
        temporizadorAviso = setTimeout(function () { avisoEl.classList.remove('ver'); }, 3500);
      }

      contar();
      return {
        aviso: aviso,
        refrescar: function () {
          var sel = barra.querySelector('[data-k="estado"]');
          if (sel) { sel.value = state.estado; }
          pintarFlujo();
          medirBarra();
          repintar();
        }
      };
    }
  }

  var CSS_STUDIO = [
    ':host { all: initial; }',
    '* { box-sizing: border-box; }',
    '[hidden] { display: none !important; }',
    '.barra, .flujo, .pop, .dlg, .aviso, .insignia, .pin { font: 13px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #eef0f3; }',
    '.barra { position: fixed; left: 0; right: 0; bottom: 0; z-index: 2147483000; display: flex; align-items: center; gap: 6px 10px; padding: 7px 10px; background: #16191f; border-top: 1px solid #2c313b; }',
    '.pant { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }',
    '.ctl { flex: none; display: flex; align-items: center; gap: 6px 10px; }',
    '.plegar { display: none; }',
    '@media (max-width: 1100px) { .barra { flex-wrap: wrap; } .marca { display: none; } .plegar { display: inline-flex; align-items: center; } .ctl { display: none; flex-wrap: wrap; width: 100%; } .barra.abierta .ctl { display: flex; } }',
    '.marca { font-weight: 700; padding: 3px 8px; border-radius: 6px; background: #eef0f3; color: #16191f; }',
    '.pant { color: #c9ced6; } .pant b { color: #eef0f3; }',
    'label { display: inline-flex; align-items: center; gap: 5px; color: #b4bbc6; white-space: nowrap; }',
    'select, button { font: inherit; color: #eef0f3; background: #262a32; border: 1px solid #454b57; border-radius: 6px; min-height: 32px; padding: 0 8px; white-space: nowrap; }',
    'button { cursor: pointer; font-weight: 600; }',
    'button:hover, select:hover { border-color: #8b93a1; }',
    'button[aria-pressed="true"], button.fuerte { background: #eef0f3; color: #16191f; border-color: #eef0f3; }',
    'button:disabled { opacity: .5; cursor: default; }',
    'select:focus-visible, button:focus-visible, a:focus-visible, textarea:focus-visible { outline: 3px solid #8ea2f2; outline-offset: 2px; }',
    '.flujo { position: fixed; left: 0; right: 0; z-index: 2147483000; display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: #232832; border-top: 1px solid #3a404c; overflow-x: auto; white-space: nowrap; }',
    '.flujo span { margin-right: auto; } .flujo b { color: #c3a6ff; }',
    '.capa { position: fixed; inset: 0; z-index: 2147482000; pointer-events: none; }',
    '.caja { position: fixed; border: 2px dashed; border-radius: 6px; pointer-events: none; }',
    '.hover { position: fixed; border: 2px solid #f5c26b; border-radius: 4px; background: rgb(245 194 107 / 12%); pointer-events: none; }',
    '.insignia { position: fixed; transform: translateY(-100%); display: grid; gap: 2px; min-height: 0; padding: 3px 8px; border-radius: 6px 6px 6px 0; background: #16191f; border: 1px solid #454b57; border-left-width: 3px; text-align: left; pointer-events: auto; font-size: 12px; font-weight: 600; }',
    '.insignia.dentro { transform: none; border-radius: 0 6px 6px 6px; }',
    '.insignia.lado { transform: none; border-radius: 6px; max-width: 220px; white-space: normal; }',
    '.insignia span, .chip { display: inline-flex; align-items: center; gap: 6px; }',
    'i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex: none; }',
    '.pin { position: fixed; width: 24px; height: 24px; min-height: 0; padding: 0; border-radius: 50%; background: #f5c26b; color: #16191f; border: 2px solid #16191f; pointer-events: auto; font-size: 12px; font-weight: 700; }',
    '.pop { position: fixed; z-index: 2147483100; width: min(360px, calc(100vw - 16px)); max-height: 70vh; overflow: auto; padding: 14px 16px; background: #1d2128; border: 1px solid #454b57; border-radius: 10px; box-shadow: 0 12px 32px rgb(0 0 0 / 35%); }',
    '.pop .cerrar, .dlg .cerrar { position: absolute; top: 8px; right: 8px; width: 32px; padding: 0; font-size: 18px; }',
    'h2, h3 { margin: 0 0 6px; font-size: 14px; color: #eef0f3; } h2 { font-size: 16px; }',
    'section + section { margin-top: 12px; padding-top: 12px; border-top: 1px solid #333944; }',
    'p { margin: 0 0 6px; } .sub { color: #aab2bf; font-size: 12px; } .texto { white-space: pre-wrap; }',
    '.regla { padding-right: 28px; } .chip { color: #dfe3e8; font-weight: 600; }',
    '.editor { display: grid; gap: 8px; padding-right: 28px; } .editor label { display: block; color: #dfe3e8; }',
    'textarea { width: 100%; font: 14px/1.4 system-ui, sans-serif; color: #eef0f3; background: #262a32; border: 1px solid #6b7383; border-radius: 6px; padding: 8px; resize: vertical; }',
    '.acciones { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }',
    '.dlg { width: min(640px, calc(100vw - 24px)); max-height: 85vh; padding: 0; background: #1d2128; border: 1px solid #454b57; border-radius: 12px; }',
    '.dlg::backdrop { background: rgb(0 0 0 / 50%); }',
    '.dlg-cab { position: sticky; top: 0; padding: 14px 52px 10px 18px; background: #1d2128; border-bottom: 1px solid #333944; }',
    '.dlg-cuerpo { padding: 12px 18px 18px; } .dlg-cuerpo h3 { margin-top: 14px; }',
    'ul, ol { margin: 0 0 8px; padding: 0; list-style: none; }',
    '.pants li, .flujos li, .reglas li, .coms li { padding: 8px 0; border-bottom: 1px solid #2c313b; }',
    '.flujos li, .coms li { display: flex; align-items: center; justify-content: space-between; gap: 12px; }',
    'a { color: #a9b9f6; text-underline-offset: 3px; } a[aria-current] { color: #eef0f3; font-weight: 700; }',
    '.estados { margin-left: 10px; } .estados a { margin-right: 10px; font-size: 12px; }',
    'code { font: 12px ui-monospace, Menlo, monospace; color: #dfe3e8; }',
    '.aviso { position: fixed; left: 50%; z-index: 2147483200; transform: translateX(-50%); max-width: calc(100vw - 24px); padding: 8px 14px; border-radius: 8px; background: #eef0f3; color: #16191f; font-weight: 600; opacity: 0; pointer-events: none; transition: opacity 150ms; }',
    '.aviso.ver { opacity: 1; }',
    '@media (prefers-reduced-motion: reduce) { .aviso { transition: none; } }'
  ].join('\n');
})();
