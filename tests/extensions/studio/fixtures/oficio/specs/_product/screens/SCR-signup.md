# SCR-signup Crear cuenta

- Area: acceso
- File: registro.html
- Layout: auth
- Session: none
- States: normal, error, cargando
- Stories: ST-2, ST-3
- Rules: R-signup-unique-email, R-password-length, R-login-oauth

## Purpose

Crear una cuenta nueva con correo y contraseña, o con un proveedor.

## Elements

- field "Nombre"
- field "Correo"
- field "Contraseña"
- button "Crear cuenta" -> SCR-home/vacio
- link "Entra" -> SCR-login

## States

- error: El correo ya tiene cuenta, o la contraseña es corta.
- cargando: El botón dice "Creando…".
