# Petrocast — Plataforma de Pronóstico de Producción de Hidrocarburos

> Trabajo Integrador — Ingeniería de Software I — UDESA — 2026

## Descripción

## Video Entrega Adenda Fase 1

Demo del proyecto disponible en [YouTube](https://youtu.be/ymsLBhMp4wo?si=FLE44OcpUzbenkfb).

## Equipo

- Santino Domato — sdomato@udesa.edu.ar / [sdomato](https://github.com/sdomato)
- Ignacio Vargas — ivargasfernandez@udesa.edu.ar / [ignacio279](https://github.com/ignacio279)
- Joaquin Leon Alderete — jleonalderete@udesa.edu.ar / [joaquinleondev](https://github.com/joaquinleondev)

## Documentación

- [Consigna de la materia (PRD y adendas)](docs/assignment/)
- [PRD — Fase 2](docs/prd/prd-v0.2.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Arquitectura](docs/architecture/c4-context.md)
- [Backlog de Fase 2](docs/backlog/issues-fase-2.md)
- [Runbooks operativos](docs/runbooks/)
- [Supuestos y clarificaciones](docs/supuestos-y-clarificaciones.md)

## Estado por fase

| Fase   | Fecha      | Estado           | Demo                               |
| ------ | ---------- | ---------------- | ---------------------------------- |
| Fase 1 | 2026-04-28 | ✅ Completa      | [link](https://api.petrocast.shop) |
| Fase 2 | 2026-06-09 | ⏳ En desarrollo | —                                  |
| Fase 3 | 2026-06-30 | ⏳ Pendiente     | —                                  |

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

## Despliegue

El pipeline CI/CD es completamente automatizado vía GitHub Actions:

| Evento                 | Resultado                                                             |
| ---------------------- | --------------------------------------------------------------------- |
| PR abierta/actualizada | Build + Trivy scan + preview efímero en `pr-<N>.dev.petrocast.shop`   |
| Merge a `main`         | Rollout a staging (`staging.petrocast.shop`) con rollback automático  |
| Tag `v*`               | Despliegue a producción (`api.petrocast.shop`) con approval requerido |
| PR cerrada             | Teardown automático del preview + limpieza ECR                        |

Ver [infra/README.md](infra/README.md) para el diagrama de flujo completo y [infra/terraform/README.md](infra/terraform/README.md) para la secuencia de provisioning de la infraestructura AWS.
