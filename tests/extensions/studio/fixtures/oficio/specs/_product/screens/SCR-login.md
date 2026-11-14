# SCR-login Entrar

- Area: acceso
- File: entrar.html
- Layout: auth
- Session: none
- States: normal, error, cargando
- Stories: ST-1, ST-2
- Rules: R-login-lockout, R-login-oauth, R-login-attempts-warning
- Entry: yes

## Purpose

Entrar a la cuenta con correo y contraseña, o con un proveedor.

## Elements

- field "Correo"
- field "Contraseña"
- button "Entrar" -> SCR-home
- button "Continuar con Google" -> SCR-home
- button "Continuar con Facebook" -> SCR-home
- button "Continuar con GitHub" -> SCR-home
- link "¿Olvidaste tu contraseña?" -> SCR-forgot
- link "Crea tu cuenta" -> SCR-signup

## States

- error: El correo o la contraseña no coinciden. Avisa cuántos intentos quedan.
- cargando: El botón dice "Entrando…".
