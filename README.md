# Petrocast — Plataforma de Pronóstico de Producción de Hidrocarburos

> Trabajo Integrador — Ingeniería de Software I — UDESA — 2026

## Descripción

## Equipo

- Santino Domato — email/github
- Ignacio Vargas — email/github
- Joaquin Leon Alderete — jleonalderete@udesa.edu.ar/joaquinleondev

## Documentación

- [PRD](docs/prd/prd-v0.1.md)
- [Addendum del PRD (decisiones sobre preguntas abiertas)](docs/prd/addendum-v0.2.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Arquitectura](docs/architecture/c4-context.md)
- [Backlog](docs/backlog/user-stories.md)

## Estado por fase

| Fase   | Fecha      | Estado           | Demo |
| ------ | ---------- | ---------------- | ---- |
| Fase 1 | 2026-04-28 | 🚧 En desarrollo | —    |
| Fase 2 | 2026-06-09 | ⏳ Pendiente     | —    |
| Fase 3 | 2026-06-30 | ⏳ Pendiente     | —    |

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
