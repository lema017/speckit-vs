# Navigation

## Areas

### acceso Acceso
- Covers: Entrar, crear una cuenta y recuperar la contraseña

### inicio Inicio
- Covers: Lo primero que ve una persona con sesión

## Flows

### FL-1 Entrar con correo
- Area: acceso
- Steps: SCR-login > SCR-home

### FL-2 Bloqueo por intentos fallidos
- Area: acceso
- Steps: SCR-login > SCR-login/error > SCR-login-locked

### FL-3 Crear cuenta
- Area: acceso
- Steps: SCR-login > SCR-signup > SCR-home/vacio

### FL-4 Recuperar la contraseña
- Area: acceso
- Steps: SCR-login > SCR-forgot > SCR-forgot/enviado > SCR-reset > SCR-home
