# login: implementation

## Rule Status

### R-login-lockout
- Observed: LockoutPolicy bloquea la cuenta 15 minutos al quinto fallo seguido, y un ingreso correcto reinicia el conteo.
- State: conforming
- Code: `src/auth/lockout.py::LockoutPolicy`
- Tests: `tests/test_lockout.py::test_fifth_failure_locks_for_15_minutes`, `tests/test_lockout.py::test_success_resets_count`

### R-login-oauth-providers
- Observed: OAuthLogin acepta google, facebook y github, y rechaza cualquier otro proveedor.
- State: conforming
- Code: `src/auth/oauth.py::OAuthLogin`
- Tests: `tests/test_oauth.py::test_supports_google_facebook_github`, `tests/test_oauth.py::test_rejects_other_providers`

## Retirement Evidence

## Approach

El conteo vive en memoria, por cuenta. `LockoutPolicy` guarda el fin del bloqueo y lo compara con la hora que recibe.

La lista de proveedores es fija en `OAuthLogin.PROVIDERS`. El flujo con cada proveedor queda simulado.

## Decisions
| Decision | Why | Rejected alternative | Source |
|---|---|---|---|
| El bloqueo usa la hora que recibe | Las pruebas fijan la hora | Leer el reloj dentro de la clase | specs/001-acceso |
| Lista fija de proveedores | La regla nombra tres | Configurarlos por entorno | specs/002-oauth |

## Anchors
| Anchor | Kind | What it does |
|---|---|---|
| `src/auth/lockout.py::LockoutPolicy` | code | Cuenta los fallos y calcula el fin del bloqueo |
| `src/auth/oauth.py::OAuthLogin` | code | Dice qué proveedores se aceptan |
