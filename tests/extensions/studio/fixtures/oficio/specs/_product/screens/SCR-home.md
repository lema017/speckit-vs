# SCR-home Inicio

- Area: inicio
- File: inicio.html
- Layout: app
- Session: required
- States: normal, vacio, cargando
- Stories: ST-5
- Rules: none

## Purpose

Mostrar a la persona sus talleres al entrar.

## Elements

- list "Mis talleres"
- button "Cerrar sesión" -> SCR-login

## States

- vacio: Todavía no hay talleres: invita a ver los de la semana.
- cargando: Dos filas en gris mientras llega la lista.
