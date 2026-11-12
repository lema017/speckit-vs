# Diseño: login

Aprobado por: Ana Pérez (PO) el 2026-11-11

## Capability Delta
<!-- capability-delta:v1 -->

### NEW-CAPABILITY login
- Covers: Entrar a la cuenta con correo o con Google, Facebook o GitHub

### DESIGNED R-login-lockout
- Capability: login
- From: (none)
- To: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.
- Links: none

### DESIGNED R-login-oauth-providers
- Capability: login
- From: (none)
- To: Se puede entrar con una cuenta de Google, Facebook o GitHub.
- Links: none

### DESIGNED R-login-one-account-per-email
- Capability: login
- From: (none)
- To: Un correo registra una sola cuenta.
- Links: none

### DESIGNED R-login-reset-expiry
- Capability: login
- From: (none)
- To: El enlace para recuperar la contraseña vence a los 30 minutos.
- Links: none
