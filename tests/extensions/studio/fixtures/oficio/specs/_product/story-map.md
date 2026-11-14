# Stories

### ST-1 Entrar con correo
- Area: acceso
- Actor: ACT-vecina, ACT-tallerista
- Story: Como vecina, entro con mi correo y mi contraseña para apuntarme a un taller.
- Criteria: Con el correo y la contraseña correctos veo mi inicio. Con la contraseña mala veo un error.
- Rules: R-login-lockout, R-login-attempts-warning

### ST-2 Entrar con un proveedor
- Area: acceso
- Actor: ACT-vecina
- Story: Como vecina, entro con Google, Facebook o GitHub para no recordar otra contraseña.
- Criteria: Elijo un proveedor y llego a mi inicio.
- Rules: R-login-oauth

### ST-3 Crear una cuenta
- Area: acceso
- Actor: ACT-vecina
- Story: Como persona nueva, creo mi cuenta para apuntarme a talleres o dar uno.
- Criteria: Con un correo libre y una contraseña válida quedo dentro.
- Rules: R-signup-unique-email, R-password-length

### ST-4 Recuperar la contraseña
- Area: acceso
- Actor: ACT-vecina
- Story: Como vecina que olvidó su contraseña, la cambio con un enlace que llega a mi correo.
- Criteria: Pido el enlace, lo abro, pongo una contraseña nueva y entro con ella.
- Rules: R-reset-link

### ST-5 Ver mis talleres
- Area: inicio
- Actor: ACT-vecina, ACT-tallerista
- Story: Como vecina, al entrar veo los talleres a los que me apunté.
- Criteria: Veo la lista de mis talleres, o un aviso si todavía no tengo ninguno.
