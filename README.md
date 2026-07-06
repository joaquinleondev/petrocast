# Petrocast — Plataforma de Pronóstico de Producción de Hidrocarburos

> Trabajo Integrador — Ingeniería de Software I — UDESA — 2026

## Descripción

Petrocast es una plataforma de datos y pronóstico de producción de hidrocarburos
construida sobre datos públicos de `datos.gob.ar`. Integra una API REST (Fase 1),
una plataforma de datos medallion con dbt + Dagster (Fase 2) y una vertical de
machine learning que entrena, evalúa, promueve y sirve un modelo de pronóstico de
producción vía `GET /api/v1/predictions` (Fase 3).

## Video Entrega Adenda Fase 1

Demo del proyecto disponible en [YouTube](https://youtu.be/ymsLBhMp4wo?si=FLE44OcpUzbenkfb).

## Video Entrega Adenda Fase 2

Demo del proyecto disponible en [YouTube](https://youtu.be/4pZgppJV6uo).

## Video Entrega Adenda Fase 3

Demo del proyecto disponible en YouTube: **TBD** (pendiente de grabación).

## Equipo

- Santino Domato — sdomato@udesa.edu.ar / [sdomato](https://github.com/sdomato)
- Ignacio Vargas — ivargasfernandez@udesa.edu.ar / [ignacio279](https://github.com/ignacio279)
- Joaquin Leon Alderete — jleonalderete@udesa.edu.ar / [joaquinleondev](https://github.com/joaquinleondev)

## Documentación

- [Consigna de la materia (PRD y adendas)](docs/assignment/)
- [PRD — Fase 2](docs/assignment/adenda-fase-2.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Arquitectura](docs/architecture/c4-context.md)
- [README de Fase 2](docs/fase-2/README.md)
- [README de Fase 3 — vertical ML](docs/fase-3/README.md)
- [Modelo de datos — star schema Gold](docs/architecture/modelo-datos.md)
- [Backlog de Fase 2](docs/backlog/issues-fase-2.md)
- [Runbooks operativos](docs/runbooks/)
- [Supuestos y clarificaciones](docs/supuestos-y-clarificaciones.md)

## Estado por fase

| Fase   | Fecha      | Estado           | Demo                               |
| ------ | ---------- | ---------------- | ---------------------------------- |
| Fase 1 | 2026-04-28 | ✅ Completa      | [link](https://api.petrocast.shop) |
| Fase 2 | 2026-06-09 | ✅ Completa      | [link](https://youtu.be/4pZgppJV6uo)                                  |
| Fase 3 | 2026-07-11 | ✅ Completa      | [guion](docs/fase-3/README.md#guion--checklist-de-video) |

## Cómo ejecutar

### Prerequisito

```bash
docker network create petrocast
```

### API

```bash
docker compose -f infra/compose.dev.yml up --build
```

Disponible en <http://localhost:8000>. Documentación OpenAPI en <http://localhost:8000/docs>.

### Stack de observabilidad

```bash
docker compose -f infra/compose.observability.yml up
```

- Grafana: <http://localhost:3000> (sin login, dashboard cargado automáticamente)
- Prometheus: <http://localhost:9090>

### Stack de datos

```bash
docker compose -f infra/compose.data.yml up --build
```

- Dagster UI: <http://localhost:3000>
- PostgreSQL DW: `localhost:5432` con schemas `bronze`, `silver` y `gold`

> Los puertos del host son configurables para convivir con los otros stacks
> (Grafana también usa el 3000; el Postgres de dev, el 5432):
> `PETROCAST_DAGSTER_PORT=3001 PETROCAST_DW_PUBLISHED_PORT=5433 docker compose -f infra/compose.data.yml up`

### Paquete de machine learning

El paquete compartido `apps/ml` concentra los contratos de features,
entrenamiento, tracking, registry e inferencia usados por Data y API. La guía de
configuración y los comandos locales están en [apps/ml/README.md](apps/ml/README.md).

Operación de la vertical ML (detalle en [docs/fase-3/README.md](docs/fase-3/README.md)):

```bash
# Tracking + retraining (MLflow en :5000, Dagster en :3000)
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml -f infra/compose.mlflow.yml \
  up --build data-postgres mlflow dagster

# Retraining por CLI (features → training → evaluación → promoción)
PARTITION=2026-01-01 infra/scripts/demo/f3-21-demo-evidence.sh retrain-cli

# API de predicciones (con la API levantada)
curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=POZO-001&as_of_date=2024-03-15&horizon=3"
```

## Despliegue

El pipeline CI/CD es completamente automatizado vía GitHub Actions:

| Evento                 | Resultado                                                             |
| ---------------------- | --------------------------------------------------------------------- |
| PR abierta/actualizada | Build + Trivy scan + preview efímero en `pr-<N>.dev.petrocast.shop`   |
| Merge a `main`         | Rollout a staging (`staging.petrocast.shop`) con rollback automático  |
| Tag `v*`               | Despliegue a producción (`api.petrocast.shop`) con approval requerido |
| PR cerrada             | Teardown automático del preview + limpieza ECR                        |

Ver [infra/README.md](infra/README.md) para el diagrama de flujo completo y [infra/terraform/README.md](infra/terraform/README.md) para la secuencia de provisioning de la infraestructura AWS.
