# SCR-forgot Recuperar contraseña

- Area: acceso
- File: recuperar.html
- Layout: auth
- Session: none
- States: normal, enviado, cargando
- Stories: ST-4
- Rules: R-reset-link

## Purpose

Pedir el enlace para cambiar la contraseña.

## Elements

- field "Correo"
- button "Mandar enlace"
- link "Volver a la entrada" -> SCR-login

## States

- enviado: Dice que el enlace va en camino y cuánto dura.
- cargando: El botón dice "Enviando…".
