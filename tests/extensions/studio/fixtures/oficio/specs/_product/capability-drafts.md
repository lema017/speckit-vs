# Capability drafts

## login

- Covers: Entrar a la cuenta con correo o con Google, Facebook o GitHub

### R-login-lockout
- Text: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.
- Example: Ana falla 5 veces a las 10:00 y puede volver a intentar a las 10:15.

### R-login-oauth
- Text: Se puede entrar con una cuenta de Google, Facebook o GitHub.
- Example: Ana elige Google y llega a su inicio sin escribir una contraseña.

### R-login-attempts-warning
- Text: Desde el tercer intento fallido, se avisa cuántos intentos quedan antes del bloqueo.
- Example: Al tercer fallo Ana lee "Te quedan 2 intentos".

## signup

- Covers: Crear una cuenta con correo y contraseña

### R-signup-unique-email
- Text: Un correo registra una sola cuenta.
- Example: Ana ya tiene cuenta con ana@ejemplo.com y no puede crear otra con ese correo.

### R-password-length
- Text: La contraseña tiene al menos 8 caracteres.
- Example: "secreto" se rechaza y "secreto1" se acepta.

## password-reset

- Covers: Cambiar la contraseña con un enlace que llega al correo

### R-reset-link
- Text: El enlace para cambiar la contraseña vence a los 60 minutos y sirve una sola vez.
- Example: Ana pide el enlace a las 9:00 y a las 10:01 ya no sirve.
