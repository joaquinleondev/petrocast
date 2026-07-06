# F3-24 — README Fase 3, arquitectura completa y guion de video

- **Issue:** #127 · **Epic:** M6 (#103) · **Owner:** @joaquinleondev
- **Tipo:** `docs(readme)` · **Depende de:** F3-21 (#124), F3-22 (#125), F3-23 (#126) — todas CLOSED
- **Fecha:** 2026-07-06 · **Entrega Fase 3:** 2026-07-11

## Problema

Fase 3 (vertical ML de pronóstico) está implementada y cerrada issue por issue, pero
la documentación de cabecera no la refleja: el `README.md` raíz marca Fase 3 como
pendiente, no hay un README de Fase 3, y los diagramas de arquitectura no incluyen la
vertical ML. F3-24 es el capítulo de **cierre documental**: consolida arquitectura
F1+F2+F3, explica cómo operar la vertical ML, enlaza las decisiones (ADRs 0030–0035) y
deja el guion de video para la entrega.

No hay lógica nueva. Todo lo que se documenta ya existe como código y artefactos:
`docs/fase-3/{model-card,backtesting-report,demo-tracking-api}.md`,
`docs/runbooks/ml-promotion.md`, ADRs `0030`–`0035`, diagramas `docs/architecture/c4-*.md`.

## Decisiones tomadas

1. **Video:** se escribe el guion/checklist y se deja un placeholder (TBD) para el link
   de YouTube. No se graba en esta issue; el equipo agrega el link después.
2. **Diagramas:** se **extienden** los diagramas C4 existentes (`c4-context.md`,
   `c4-containers.md`) con la vertical ML. No se crea un diagrama dedicado nuevo.

## Alcance (footprint)

### 1. Crear `docs/fase-3/README.md` (hub de Fase 3)

Calcado del patrón de `docs/fase-2/README.md`. Secciones:

- **Arquitectura de la vertical ML.** Stack de herramientas (MLflow OSS + Postgres/Supabase
  para tracking + S3 para artefactos; dbt feature store en schema `features`, clave
  `(well_id, as_of_date)`, point-in-time; LightGBM global; Dagster para retraining; serving
  embebido en FastAPI). Flujo end-to-end: tracking → features → training → evaluación/gates
  → registry `@champion` → serving → retraining → CI/CD.
- **Decisiones (ADRs 0030–0035).** Una línea por ADR con link:
  0030 objetivo/horizonte/métricas · 0031 feature store · 0032 tracking/registry ·
  0033 orquestación/retraining · 0034 serving/contrato API · 0035 CI/CD y promoción.
- **Cómo correr.** Comandos reales para: tracking (`--track`), retrain (job/schedule
  Dagster), API de predicciones (`GET /api/v1/predictions`). Reusa/enlaza
  `demo-tracking-api.md` para no duplicar.
- **Guion/checklist de video.** Pasos: (1) mostrar runs de tracking con métricas distintas,
  (2) métricas/gates de calidad, (3) API de predicciones respondiendo, (4) retrain
  (job Dagster). + placeholder TBD para el link de YouTube.
- **Mapa de documentación de Fase 3.** Links a model-card, backtesting-report,
  demo-tracking-api, runbook `ml-promotion`, y los 6 ADRs.

### 2. Actualizar `README.md` raíz

- `## Descripción` (hoy vacía): un párrafo que incluya la capa de pronóstico ML.
- Tabla **Estado por fase**: Fase 3 `⏳ Pendiente` → `✅ Completa`, fecha 2026-07-11,
  demo con placeholder al video.
- Nueva sección **Video Entrega Adenda Fase 3** (placeholder TBD, mismo formato que F1/F2).
- **Documentación**: agregar link a `docs/fase-3/README.md`.
- **Cómo ejecutar** → ampliar "Paquete de machine learning" con tracking + retrain + API.

### 3. `docs/architecture/*`

Extender `c4-context.md` y `c4-containers.md` con la vertical ML (MLflow, feature store
schema `features`, serving embebido en FastAPI, retraining Dagster) — sumar la capa F3 a
los diagramas mermaid y a la prosa existentes.

### 4. `docs/fase-2/README.md`

Cross-link mínimo a `docs/fase-3/README.md` en su "Mapa de documentación".

## Fuera de alcance (YAGNI)

- Grabar el video (solo guion).
- Tocar código, tests o infra.
- Diagramas C4 nuevos desde cero.
- Reescribir los docs de Fase 3 ya entregados (se enlazan, no se duplican).

## Criterios de aceptación → mapeo

| Criterio de #127 | Dónde se cumple |
| --- | --- |
| README describe arquitectura F1+F2+F3 | README raíz + `docs/fase-3/README.md` + c4 extendidos |
| Herramientas, flujos y decisiones con links a ADRs 0030–0035 | sección Arquitectura + Decisiones de `docs/fase-3/README.md` |
| Cómo correr tracking, retrain y API | sección Cómo correr de `docs/fase-3/README.md` + README raíz |
| Guion/checklist de video | sección Guion de `docs/fase-3/README.md` |
| Actualiza docs de fase | `docs/fase-2/README.md` cross-link + `docs/fase-3/README.md` nuevo |

## Entrega

- Rama `docs/f3-24-readme-arquitectura`, PR con `Closes #127`.
- Milestone M6 (#103), labels `docs`/`demo`/`arquitectura`, assignee @joaquinleondev.
- Solo-docs → sin cambios de código; CI liviano.
