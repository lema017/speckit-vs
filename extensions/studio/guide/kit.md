# How to draw a screen

A screen of the mockup is one HTML page under `specs/_product/mockup/`. It has no logic and no real data. It uses the classes of the kit and a few `data-` attributes the Studio bar reads. The colors, the font and the corners come from the look the person chose, so **a page never sets a color or a font of its own**: no `style` with colors, no `<style>` block, no font names.

## The page

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Entrar a Oficio</title>
  <link rel="stylesheet" href="_studio/theme.css">
  <link rel="stylesheet" href="_studio/kit.css">
  <script src="_studio/product.js"></script>
  <script src="_studio/screens.js"></script>
  <script src="_studio/runtime.js"></script>
</head>
<body data-screen="SCR-login" data-area="acceso">
  <div class="app">
    …the screen…
  </div>
</body>
</html>
```

- `lang` is the language of the product. `data-screen` and `data-area` are the ones of the screen's file.
- The five files of `_studio/` are loaded exactly like that, and nothing else is loaded: no other script, no font, no image from a site. Where a picture goes, use a placeholder (`.ph`).
- Everything of the screen is inside one `<div class="app">`. One `<h1>` per page.
- Every field has a `<label for>`, every image an `alt`, every button a text or an `aria-label`.

## What makes it navigable

| You write | What happens in the mockup |
|---|---|
| `<a href="inicio.html">` | Goes to that screen. Link to the page (`File`) of the screen the element leads to |
| `<a href="inicio.html?sesion=1">` | Goes there and signs the person in. `?sesion=0` signs them out |
| `<a href="entrar.html?estado=error">` | Goes to that screen in that state |
| `<form data-goto="inicio.html?sesion=1">` | On submit, checks the required fields, shows the button busy and goes there |
| `<button type="button" data-goto="detalle.html">` | A button that goes to a screen |
| `<button type="button" data-set-state="confirmar">` | Changes the state of this screen without leaving it: open a dialog, show a result |
| `<a href="#pagos">` | Something that is not designed yet. The mockup says so when it is clicked, and `check` lists it |
| `data-state="vacio"` | The element shows only in that state. Several states: `data-state="normal cargando"`. Add `hidden` when it is not for `normal` |
| `data-persona="ACT-vecina"` | The element shows only for that person. Add `hidden` when it is not for the first actor |
| `data-sesion="1"` | The element shows only with a session (`0`: only without) |
| `data-ref="ST-1 R-login-lockout"` | The stories and the rules this element carries. The bar shows them, with the text of the rule |
| `<span data-bind="nombre">Ana</span>` | The name of the person chosen in the bar. Also `correo` and `rol` |
| `<input data-bind-value="correo">` | The same, as the value of a field |
| `class="sim"` | Something that in the real product happens outside the screen: an email, a payment page |
| `class="pending"` | Something that is not decided yet |

Rules of thumb:

- Every element of the screen's `## Elements` is on the page, with its label as written, and leads where it says. `check` notes a button, a link, a field or a tab the page does not show under its label.
- A snippet of this guide is an example. Leave out what the screen's file does not name: a picture goes on a page only when `## Elements` has an `image`.
- Every state of `States` is visible: wrap what changes in `data-state`. The states of the page are the ones of the screen's file, no other.
- Every rule of `- Rules:` is cited with `data-ref` on the element that applies it, and every story of `- Stories:` on the element where it happens.
- What one person sees and another does not goes in `data-persona`.
- Every page leads to another screen, and can be reached from a screen with `Entry: yes`.
- Sample data is made up, plausible and in the language of the product: names, dates, amounts. Three to five rows are enough.

Form fields: `required` makes the form check it. `data-msg-required="Escribe tu correo."` is the message. `type="email"` and `minlength` are checked too, with `data-msg-email` and `data-msg-min`. `data-match="password"` on a second password field checks both are equal. On the submit button, `data-loading-label="Entrando…"` is what it says while busy.

A field shown wrong in a state: `data-invalid-in="error" data-error-ref="id-of-the-message"`.

## Layouts

**A centered card**, for signing in, a confirmation, a single question:

```html
<div class="app">
  <div class="auth">
    <main class="card">
      <div class="brand"><span class="brand-mark" aria-hidden="true">O</span><span translate="no">Oficio</span></div>
      <h1>Entra a tu cuenta</h1>
      <p class="lead">Para apuntarte a un taller o dar uno.</p>
      …
    </main>
  </div>
</div>
```

**A bar on top**, for most screens. On a phone the links of the bar hide and the `tabbar` shows:

```html
<div class="app">
  <header class="topbar">
    <a class="brand" href="inicio.html"><span class="brand-mark" aria-hidden="true">O</span><span translate="no">Oficio</span></a>
    <ul class="nav">
      <li><a href="talleres.html" aria-current="page">Talleres</a></li>
      <li><a href="mis-talleres.html">Mis talleres</a></li>
    </ul>
    <a class="btn btn-ghost btn-small" href="entrar.html?sesion=0">Salir</a>
  </header>
  <main class="page">
    <div class="page-head">
      <div><h1>Talleres de esta semana</h1><p class="lead">12 talleres en tu barrio.</p></div>
      <a class="btn btn-primary" href="publicar.html">Publicar un taller</a>
    </div>
    …
  </main>
  <ul class="tabbar">
    <li><a href="talleres.html" aria-current="page"><span class="icon icon-home"></span>Talleres</a></li>
    <li><a href="mis-talleres.html"><span class="icon icon-calendar"></span>Míos</a></li>
    <li><a href="cuenta.html"><span class="icon icon-user"></span>Cuenta</a></li>
  </ul>
</div>
```

`page` is a column of text width. `page page-wide` is for tables and boards.

**A menu on the side**, for a product with many sections, used on a computer:

```html
<div class="app">
  <div class="shell">
    <nav class="sidebar">
      <a class="brand" href="inicio.html">…</a>
      <ul class="nav">
        <li><a href="pedidos.html" aria-current="page"><span class="icon icon-list"></span>Pedidos</a></li>
        <li><a href="clientes.html"><span class="icon icon-users"></span>Clientes</a></li>
      </ul>
    </nav>
    <div class="main">
      <header class="topbar"><h1>Pedidos</h1><span class="avatar avatar-small">A</span></header>
      <main class="page page-wide">…</main>
    </div>
  </div>
</div>
```

Side by side: `.row` (in a line, wraps), `.row.spread` (ends apart), `.stack` (one under another, close), `.stack-lg` (apart), `.split` (content and a side column), `.grow` (takes the room left), `.end` (goes to the far side of a `.row` or a `.topbar`).

## Components

**Text.** `h1`, `h2`, `h3`, `p`, `.lead` (under a title), `.muted`, `.small`, `.label` (a small heading over a group), `.num` (numbers in columns), `.foot` (the line under a card).

**Buttons.** `<a>` or `<button>` with `btn`. Add `btn-primary` (one per screen: the main action), `btn-danger`, `btn-ghost` (no border), `btn-small`, `btn-icon` (only an icon: give it `aria-label`), `btn-inline` (as wide as its text). In a `btn-row`, a `page-head`, a `topbar` or a `toolbar`, buttons are as wide as their text. Alone, a button fills the width.

```html
<div class="btn-row end">
  <button class="btn" type="button" data-set-state="normal">Cancelar</button>
  <button class="btn btn-danger" type="button" data-goto="talleres.html">Borrar taller</button>
</div>
```

**Fields.**

```html
<div class="field">
  <label for="titulo">Título</label>
  <input id="titulo" name="titulo" required data-msg-required="Escribe un título." value="Pan de masa madre">
  <p class="hint">Así lo verán los vecinos.</p>
</div>
<div class="field-row">
  <div class="field"><label for="dia">Día</label><input id="dia" type="date" value="2026-03-14"></div>
  <div class="field"><label for="cupo">Cupo</label><select id="cupo"><option>8 personas</option><option>12 personas</option></select></div>
</div>
<div class="field"><label for="nota">Descripción</label><textarea id="nota"></textarea></div>
<label class="check"><input type="checkbox" checked><span>Avisarme un día antes<span>Por correo</span></span></label>
<label class="switch">Lista de espera<input type="checkbox" checked></label>
<div class="search"><span class="icon icon-search"></span><input type="search" aria-label="Buscar talleres" placeholder="Buscar"></div>
```

A password field with its show button: `<div class="password"><input id="password" type="password"><button class="toggle" type="button" aria-controls="password" aria-label="Mostrar contraseña">Mostrar</button></div>`.

A row of filters: `<div class="toolbar">` with a `.search`, some `select` and buttons. Filter chips: `<ul class="chips"><li><button class="chip" type="button" aria-pressed="true">Todos</button></li>…</ul>`.

**Messages.**

```html
<div class="alert alert-danger" role="alert"><p><strong>El correo o la contraseña no coinciden.</strong></p><p>Te quedan 2 intentos.</p></div>
<div class="alert alert-success" role="status"><p><strong>Te apuntaste.</strong></p></div>
<div class="alert alert-info"><p>Quedan 2 lugares.</p></div>
<span class="badge">Borrador</span> <span class="badge badge-success">Confirmado</span> <span class="badge badge-danger">Cancelado</span> <span class="badge badge-primary">Nuevo</span>
<p class="toast" role="status">Taller publicado.</p>
```

Nothing to show yet, and loading:

```html
<div class="empty" data-state="vacio" hidden>
  <p>Todavía no te apuntaste a ningún taller.</p>
  <a class="btn btn-primary btn-inline" href="talleres.html">Ver los talleres</a>
</div>
<div data-state="cargando" role="status" aria-label="Cargando" hidden>
  <div class="skeleton"><i></i><i></i></div>
  <div class="skeleton"><i></i><i></i></div>
</div>
```

**Lists.** A simple list, each row a title, a second line and one link or badge:

```html
<ul class="list">
  <li><b>Pan de masa madre</b><span>Sábado a las 10:00, con Rosa</span><a href="taller.html">Ver taller</a></li>
</ul>
```

Rows with a picture or an avatar, each a link:

```html
<ul class="items">
  <li><a class="item" href="taller.html">
    <span class="avatar">R</span>
    <span class="item-body"><b>Pan de masa madre</b><span>Sábado a las 10:00</span></span>
    <span class="item-end"><span class="badge badge-success">2 lugares</span><span class="icon icon-chevron-right"></span></span>
  </a></li>
</ul>
```

**Cards**, for things with a picture, in a grid that adapts:

```html
<ul class="cards">
  <li><a class="tile" href="taller.html">
    <div class="ph">Foto del taller</div>
    <h3>Arreglo de bicis</h3>
    <p>Domingo a las 11:30, con Tomás</p>
    <div class="row spread"><span class="badge">6 de 8</span><span class="muted small">Gratis</span></div>
  </a></li>
</ul>
```

**Numbers at a glance:** `<ul class="stats"><li class="stat"><span>Inscritos</span><b>128</b><small>12 esta semana</small></li>…</ul>`.

**A table**, on a `page-wide`:

```html
<div class="table-wrap">
  <table class="table">
    <thead><tr><th>Taller</th><th>Día</th><th class="num">Inscritos</th><th class="actions"><span class="muted">Acciones</span></th></tr></thead>
    <tbody><tr><td>Pan de masa madre</td><td>Sáb 14 mar</td><td class="num">6 de 8</td><td class="actions"><a href="editar.html">Editar</a></td></tr></tbody>
  </table>
</div>
```

**Details of one thing:** `<dl class="kv"><dt>Lugar</dt><dd>Casa de la cultura</dd>…</dl>`. A block with a border: `<section class="panel"><h2>…</h2>…</section>`.

**Getting around.**

```html
<ul class="tabs"><li><a href="taller.html" aria-current="page">Detalle</a></li><li><a href="inscritos.html">Inscritos</a></li></ul>
<ol class="steps"><li class="is-done">Datos</li><li aria-current="step">Fecha</li><li>Publicar</li></ol>
<ol class="breadcrumb"><li><a href="talleres.html">Talleres</a></li><li>Pan de masa madre</li></ol>
<div class="pagination"><span>1 a 10 de 34</span><div class="btn-row"><a class="btn btn-small" href="#anterior">Anterior</a><a class="btn btn-small" href="#siguiente">Siguiente</a></div></div>
<div class="progress" role="img" aria-label="6 de 8 lugares"><i style="width: 75%"></i></div>
```

A width in `style` is fine. A color is not.

**Over the screen.** A dialog is a state of the screen. A button opens it with `data-set-state`, and the dialog sits last inside `.app`:

```html
<button class="btn btn-danger btn-inline" type="button" data-set-state="confirmar">Borrar taller</button>
…
<div class="modal-layer" data-state="confirmar" hidden>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="borrar-titulo">
    <h2 id="borrar-titulo">¿Borrar este taller?</h2>
    <p>Los 6 inscritos reciben un aviso. No se puede deshacer.</p>
    <div class="btn-row end">
      <button class="btn" type="button" data-set-state="normal">Cancelar</button>
      <a class="btn btn-danger" href="talleres.html">Borrar</a>
    </div>
  </div>
</div>
```

A menu that opens from a button works the same way: `<div class="menu-anchor">` holds the button and a `<ul class="menu" data-state="menu" hidden>`.

**Pictures and people.** `<div class="ph">Foto del taller</div>` (also `ph-square`, `ph-wide`, `ph-thumb`). `<span class="avatar">R</span>` (also `avatar-small`, `avatar-large`).

**Icons.** `<span class="icon icon-search" aria-hidden="true"></span>`, also `icon-small` and `icon-large`. An icon takes the color of the text around it. The ones there are:

`home` `search` `plus` `check` `x` `chevron-right` `chevron-left` `chevron-down` `arrow-left` `arrow-right` `user` `users` `bell` `calendar` `clock` `map-pin` `settings` `edit` `trash` `menu` `more` `filter` `mail` `lock` `info` `alert` `star` `heart` `upload` `download` `image` `file` `cart` `card` `chat` `phone` `eye` `logout` `share` `chart` `list` `grid` `tag` `link` `refresh` `help`

A big icon over a message: `<div class="status-icon is-success"><span class="icon icon-check"></span></div>` (`is-info`, or none for something that went wrong).

Signing in with another service: `<a class="btn sim" href="inicio.html?sesion=1"><span class="provider-icon google" aria-hidden="true">G</span>Continuar con Google</a>` (`google`, `facebook`, `github`).

## What a mockup never has

- Real data, real people, real prices of a real shop.
- A script of its own, a style of its own, a font or an image loaded from a site.
- A screen nobody described. If the screen is missing something, change its file in `screens/` first, with the person, and then the page.
