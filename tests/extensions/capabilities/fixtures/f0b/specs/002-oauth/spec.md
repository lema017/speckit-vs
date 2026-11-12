# Feature Specification: Entrar con Google, Facebook o GitHub

**Feature Branch**: `002-oauth`
**Created**: 2026-11-11
**Status**: Draft
**Input**: D-02 de Studio: entrar con una cuenta de otro proveedor.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Entrar con otro proveedor (Priority: P1)

Luis no quiere otra contraseña y entra con su cuenta de GitHub.

**Acceptance Scenarios**:

1. **Given** la pantalla de entrada, **When** Luis elige GitHub, **Then** entra sin contraseña.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST ofrecer entrar con Google, Facebook o GitHub.
- **FR-002**: El sistema MUST rechazar cualquier otro proveedor.

## Product Reference

- Entregable: D-02
- SCR-login: sha256:0000000000000000 (de `handoff`, a mano en el ensayo)

## Capability Delta *(mandatory)*

<!-- capability-delta:v1 -->

### IMPLEMENTED R-login-oauth-providers
- Capability: login
- From: Se puede entrar con una cuenta de Google, Facebook o GitHub.
- To: Se puede entrar con una cuenta de Google, Facebook o GitHub.
- Links: FR-001, FR-002
