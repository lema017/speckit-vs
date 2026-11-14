# SCR-login-locked Cuenta bloqueada

- Area: acceso
- File: bloqueada.html
- Layout: auth
- Session: none
- States: normal
- Stories: ST-1
- Rules: R-login-lockout

## Purpose

Decir que la cuenta quedó bloqueada y cuándo se puede volver a intentar.

## Elements

- text "Hubo 5 intentos fallidos seguidos"
- link "Restablecer contraseña" -> SCR-forgot
- link "Volver a la entrada" -> SCR-login
