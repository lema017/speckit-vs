# login: implementation

## Rule Status

### R-login-oauth-providers
- Observed: OAuthLogin acepta google, facebook y github, y rechaza cualquier otro proveedor.
- State: conforming
- Code: `src/auth/oauth.py::OAuthLogin`
- Tests: `tests/test_oauth.py::test_supports_google_facebook_github`, `tests/test_oauth.py::test_rejects_other_providers`

## Retirement Evidence

## Approach

La lista de proveedores es fija en `OAuthLogin.PROVIDERS`. El flujo con cada proveedor queda simulado.

## Decisions
| Decision | Why | Rejected alternative | Source |
|---|---|---|---|
| Lista fija de proveedores | La regla nombra tres | Configurarlos por entorno | specs/002-oauth |

## Anchors
| Anchor | Kind | What it does |
|---|---|---|
| `src/auth/oauth.py::OAuthLogin` | code | Dice qué proveedores se aceptan |
