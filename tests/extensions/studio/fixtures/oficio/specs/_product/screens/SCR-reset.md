# SCR-reset Nueva contraseña

- Area: acceso
- File: nueva-contrasena.html
- Layout: auth
- Session: none
- States: normal, error, cargando
- Stories: ST-4
- Rules: R-password-length, R-reset-link

## Purpose

Poner una contraseña nueva desde el enlace del correo.

## Elements

- field "Contraseña nueva"
- button "Guardar contraseña" -> SCR-home

## States

- error: La contraseña es corta o el enlace venció.
- cargando: El botón dice "Guardando…".
