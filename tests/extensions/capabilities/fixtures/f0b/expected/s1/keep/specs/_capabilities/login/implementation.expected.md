# login: implementation

## Rule Status

### R-login-lockout
- Observed: LockoutPolicy bloquea la cuenta 15 minutos al quinto fallo seguido, y un ingreso correcto reinicia el conteo.
- State: conforming
- Code: `src/auth/lockout.py::LockoutPolicy`
- Tests: `tests/test_lockout.py::test_fifth_failure_locks_for_15_minutes`, `tests/test_lockout.py::test_success_resets_count`

## Retirement Evidence

## Approach

El conteo vive en memoria, por cuenta. `LockoutPolicy` guarda el fin del bloqueo y lo compara con la hora que recibe.

## Decisions
| Decision | Why | Rejected alternative | Source |
|---|---|---|---|
| El bloqueo usa la hora que recibe | Las pruebas fijan la hora | Leer el reloj dentro de la clase | specs/001-acceso |

## Anchors
| Anchor | Kind | What it does |
|---|---|---|
| `src/auth/lockout.py::LockoutPolicy` | code | Cuenta los fallos y calcula el fin del bloqueo |
