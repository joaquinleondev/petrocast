# Architecture Decision Records

Este directorio contiene los Architecture Decision Records (ADRs) del
proyecto Predictiva.

## ¿Qué es un ADR?

Un ADR documenta una decisión arquitectónica relevante, incluyendo su
contexto, las opciones consideradas y la justificación de la decisión
tomada. Ver [ADR-0001](./0001-uso-de-adrs.md) para detalles del formato.

## ¿Cuándo escribir uno?

Cuando tomes una decisión que cumpla **todas** estas condiciones:

1. Tiene al menos dos alternativas razonables.
2. Cambiarla en el futuro implicaría retrabajo significativo.
3. Otro miembro del equipo podría razonablemente cuestionarla si no
   entiende el contexto.

Si la decisión es trivial o fácilmente reversible, **no** escribas un ADR.

## Cómo crear uno nuevo

1. Copiá [`template.md`](./template.md) con el siguiente nombre disponible:
   `NNNN-título-corto-en-kebab-case.md`.
2. Completalo respetando el formato.
3. Abrí un PR con el ADR en estado "Propuesto".
4. Tras la aprobación del equipo, cambiá el estado a "Aceptado" y mergeá.
5. Agregá una fila a la tabla de abajo.

## Índice

| Nº                                         | Título                        | Estado   | Fecha      |
| ------------------------------------------ | ----------------------------- | -------- | ---------- |
| [0001](./0001-uso-de-adrs.md)              | Adopción de ADRs              | Aceptado | 2026-04-20 |
| [0002](./0002-idioma-del-proyecto.md)      | Idioma del proyecto           | Aceptado | 2026-04-20 |
| [0003](./0003-estructura-monorepo.md)      | Estructura de monorepo        | Aceptado | 2026-04-20 |
| [0004](./0004-estrategia-branching.md)     | Estrategia de branching       | Aceptado | 2026-04-20 |
| [0005](./0005-convenciones-commits-prs.md) | Convenciones de commits y PRs | Aceptado | 2026-04-20 |
| [0006](./0006-conenciones-naming.md)       | Convenciones de naming        | Aceptado | 2026-04-20 |
