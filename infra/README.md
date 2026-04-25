# Infra — Despliegue y CI/CD

## Overview

Tres ambientes en AWS, cada uno en una EC2 t3.small con Docker Swarm + Traefik:

| Ambiente                 | URL                                 | Trigger                      |
| ------------------------ | ----------------------------------- | ---------------------------- |
| Preview (efímero por PR) | `https://pr-<N>.dev.petrocast.shop` | Apertura/actualización de PR |
| Staging                  | `https://staging.petrocast.shop`    | Merge a `main`               |
| Production               | `https://api.petrocast.shop`        | Tag `v*` + approval manual   |

## Flujo CI/CD

```
PR abierta
    │
    ▼
ci.yml ──── lint (pre-commit) ──────────────────────────────┐
    │                                                        │
    ├──── test (pytest: unit + integration + contract) ─────┤
    │                                                        │
    └──── build (Docker → ECR) ─── Trivy scan ─────────────┤
              │                                              │
              ▼                                         report.yml
    deploy-preview.yml                          (solo en main: S3 upload)
         │
         ├── SSM deploy → EC2 preview
         ├── Smoke test
         └── Comentario en PR con URL

PR mergeada a main
    │
    ▼
deploy-staging.yml
    ├── Verifica imagen sha-<commit> en ECR
    ├── SSM deploy → EC2 staging (2 réplicas, rolling update)
    ├── Smoke test
    └── Rollback automático si smoke falla

Tag v* creado
    │
    ▼
deploy-production.yml
    ├── Verifica tag alcanzable desde main
    ├── Crea alias versión en ECR (sin rebuild)
    ├── GitHub Environment approval (reviewer requerido)
    ├── SSM deploy → EC2 prod (2 réplicas, rolling update)
    ├── Smoke test
    └── Rollback automático si smoke falla

PR toca infra/terraform/**
    │
    ▼
tf-plan.yml
    └── terraform plan (matriz: shared/preview/staging/prod)
        └── Comentario en PR con el plan

PR cerrada
    │
    ▼
deploy-preview-cleanup.yml
    ├── docker stack rm pr-<N>
    └── Purga tags ECR pr-<N>-*
```

## Arquitectura AWS

```
Route 53 (petrocast.shop)
    ├── *.dev.petrocast.shop → EIP EC2 preview
    ├── staging.petrocast.shop → EIP EC2 staging
    └── api.petrocast.shop → EIP EC2 prod

EC2 (preview / staging / prod)
    └── Docker Swarm (single-node manager)
          ├── traefik (stack: traefik)
          │     ├── Puerto 80/443 (host mode)
          │     ├── ACME DNS-01 con wildcard *.dev.* (preview)
          │     └── ACME HTTP-01 por host (staging/prod)
          └── mock-api (stack: pr-N / staging / prod)
                ├── Réplicas: 1 (preview) / 2 (staging/prod)
                ├── Rolling update: parallelism=1, order=start-first
                ├── failure_action=rollback, monitor=30s
                └── Logs → CloudWatch (/petrocast/<env>/app)

ECR
    └── petrocast/mock-api
          ├── sha-<7chars>   — tag canónico (build-once)
          ├── pr-<N>-sha-*   — alias por PR (expirado en 7 días)
          ├── staging-latest — alias mutable
          └── v<semver>      — alias inmutable para prod

S3
    ├── petrocast-pipeline-artifacts/
    │     ├── swarm/         — stack templates (Terraform los sube)
    │     └── scripts/       — deploy.sh, rollback.sh (Terraform los sube)
    └── petrocast-test-reports/
          └── <run_id>/      — coverage.xml, trivy-results.sarif
```

## Autenticación sin claves estáticas

GitHub Actions usa OIDC para asumir roles IAM:

- `ci-role` — cualquier ref del repo: push ECR + write S3.
- `deploy-role` — solo `main`, tags `v*`, environments o PRs: SSM SendCommand sobre EC2 con tag `Project=petrocast`.

Los EC2 usan instance profiles — sin credenciales hardcodeadas.

## Ver también

- [Terraform README](terraform/README.md) — secuencia de applies y secrets de GitHub
- [ADR-0008](../docs/adr/ADR-0008-plataforma-cloud.md) — decisión de plataforma AWS
- [ADR-0009](../docs/adr/ADR-0009-estrategia-de-deploy.md) — estrategia rolling update / rollback
