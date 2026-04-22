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

| Nº                                                        | Título                                   | Estado   | Fecha      |
| --------------------------------------------------------- | ---------------------------------------- | -------- | ---------- |
| [0001](./0001-uso-de-adrs.md)                             | Adopción de ADRs                         | Aceptado | 2026-04-20 |
| [0002](./0002-idioma-del-proyecto.md)                     | Idioma del proyecto                      | Aceptado | 2026-04-20 |
| [0003](./0003-estructura-monorepo.md)                     | Estructura de monorepo                   | Aceptado | 2026-04-20 |
| [0004](./0004-estrategia-branching.md)                    | Estrategia de branching                  | Aceptado | 2026-04-20 |
| [0005](./0005-convenciones-commits-prs.md)                | Convenciones de commits y PRs            | Aceptado | 2026-04-20 |
| [0006](./0006-convenciones-naming.md)                     | Convenciones de naming                   | Aceptado | 2026-04-20 |
| [0007](./0007-alineacion-contrato-openapi-fase1.md)       | Alineación contrato OpenAPI Fase 1       | Aceptado | 2026-04-21 |
| [0008](./0008-topologia-de-ambientes.md)                  | Topología de ambientes                   | Aceptado | 2026-04-21 |
| [0009](./0009-estrategia-deployments.md)                  | Estrategia de deployments y rollback     | Aceptado | 2026-04-21 |
| [0010](./0010-plataforma-hosting.md)                      | Plataforma de hosting (AWS EC2)          | Aceptado | 2026-04-21 |
| [0011](./0011-plataforma-cicd.md)                         | Plataforma CI/CD (GitHub Actions)        | Aceptado | 2026-04-21 |
| [0012](./0012-stack-backend-python-fastapi-uv.md)         | Stack backend Python/FastAPI/uv          | Aceptado | 2026-04-21 |
| [0013](./0013-container-registry-aws-ecr.md)              | Container registry AWS ECR               | Aceptado | 2026-04-21 |
| [0014](./0014-imagenes-docker-slim-multistage-nonroot.md) | Imágenes Docker slim multi-stage no-root | Aceptado | 2026-04-21 |
| [0015](./0015-analisis-estatico-ruff-mypy-precommit.md)   | Análisis estático Ruff/mypy/pre-commit   | Aceptado | 2026-04-21 |
| [0016](./0016-estrategia-testing-pytest-schemathesis.md)  | Estrategia testing pytest/Schemathesis   | Aceptado | 2026-04-21 |
| [0017](./0017-observabilidad-prometheus-grafana-loki.md)  | Observabilidad Prometheus/Grafana/Loki   | Aceptado | 2026-04-21 |
| [0018](./0018-gestion-configuracion-pydantic-settings.md) | Gestión configuración Pydantic Settings  | Aceptado | 2026-04-21 |
| [0019](./0019-infraestructura-terraform-aws.md)           | Infraestructura Terraform AWS            | Aceptado | 2026-04-21 |
| [0020](./0020-estructura-directorios-backend.md)          | Estructura directorios backend           | Aceptado | 2026-04-22 |
