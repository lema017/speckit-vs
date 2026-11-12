# Feature Specification: Acceso con bloqueo por intentos fallidos

**Feature Branch**: `001-acceso`
**Created**: 2026-11-11
**Status**: Draft
**Input**: D-01 de Studio: entrar con correo y bloqueo por intentos fallidos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bloqueo tras intentos fallidos (Priority: P1)

Ana entra con su correo. Si alguien falla la contraseña muchas veces seguidas, la cuenta se bloquea un rato.

**Acceptance Scenarios**:

1. **Given** una cuenta sin fallos, **When** se falla 5 veces seguidas, **Then** la cuenta queda bloqueada 15 minutos.
2. **Given** una cuenta con 4 fallos, **When** se entra bien, **Then** el conteo vuelve a cero.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST contar los intentos fallidos seguidos de cada cuenta.
- **FR-002**: El sistema MUST bloquear la cuenta 15 minutos al quinto intento fallido seguido.
- **FR-003**: Un ingreso correcto MUST reiniciar el conteo.

## Product Reference

- Entregable: D-01
- SCR-login: sha256:0000000000000000 (de `handoff`, a mano en el ensayo)

## Capability Delta *(mandatory)*

<!-- capability-delta:v1 -->

### IMPLEMENTED R-login-lockout
- Capability: login
- From: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.
- To: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.
- Links: FR-002, US1/AC1
