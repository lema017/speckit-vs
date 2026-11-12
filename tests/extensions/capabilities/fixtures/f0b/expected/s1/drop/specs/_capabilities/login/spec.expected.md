# login

## Overview
Entrar a la cuenta con correo o con Google, Facebook o GitHub

## Rules

- **R-login-lockout** [designed]: Tras 3 intentos fallidos seguidos, la cuenta se bloquea 30 minutos. (specs/_capabilities/_changes/20261112-redesign-login)

- **R-login-oauth-providers** [designed]: Se puede entrar con una cuenta de Google, Facebook o GitHub. (specs/_capabilities/_changes/20261111-design-login)

- **R-login-one-account-per-email** [designed]: Un correo registra una sola cuenta. (specs/_capabilities/_changes/20261111-design-login)

- **R-login-reset-expiry** [designed]: El enlace para recuperar la contraseña vence a los 30 minutos. (specs/_capabilities/_changes/20261111-design-login)

## Related Capabilities
