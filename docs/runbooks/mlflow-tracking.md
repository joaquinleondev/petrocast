# Runbook — Plataforma de tracking de experimentos (MLflow)

Cómo operar la plataforma de tracking/registry de Fase 3
([ADR-0032](../adr/0032-tracking-experimentos-registry.md), backlog F3-08).

## Arquitectura (resumen)

- **Backend store compartido:** PostgreSQL en la nube (Neon/Supabase free tier,
  alternativa RDS). Ahí viven runs, params, métricas y el model registry.
- **Artifact store:** bucket S3 (modelos serializados, plots, datasets de
  evaluación).
- **UI:** cada integrante levanta MLflow **local** con Docker Compose apuntando
  al backend compartido — todos ven los mismos runs y el mismo champion sin
  hostear un server 24/7. Queda **listo para deployar** en staging
  (`mlflow.staging.*`, ver `infra/compose.staging.yml`) pero **no se deploya**
  por presupuesto de cómputo.
- **Fallback local (offline):** base `mlflow` en el Postgres del data stack
  (init `003-create-mlflow-db.sql`) + volumen local de artefactos. Sirve para
  smokes y demos sin credenciales cloud.

## Contrato C — configuración de tracking (congelado)

Consumido por F3-14 (logging de runs), F3-15 (métricas de evaluación),
F3-16 (promoción del champion), F3-18 (loader en la API) y F3-19 (retraining).

| Ítem | Valor / variable |
| ---- | ---------------- |
| Tracking URI | `MLFLOW_TRACKING_URI` — URI Postgres del backend compartido (`postgresql://...:5432/mlflow?sslmode=require`); fallback local `postgresql://petrocast:<pass>@localhost:5432/mlflow` o `http://localhost:5000` |
| Artifact root | `PETROCAST_MLFLOW_ARTIFACT_ROOT` — `s3://<artifacts-bucket>/mlflow`; fallback local `/mlartifacts` (volumen) |
| Credenciales S3 | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` |
| Experimento | `MLFLOW_EXPERIMENT_NAME=petrocast-production-forecast` |
| Modelo registrado | `petrocast-production`; champion por **alias** `@champion` (`models:/petrocast-production@champion`) — nunca stages deprecados |
| Tags obligatorios por run | `as_of_date` (corte de features), `features_version`, `git_commit` (o tag de imagen) |

Los nombres están publicados (comentados) en `apps/api/.env.example` y
`apps/data/.env.example`; se descomentan cuando F3-14/F3-18 agreguen el bloque
reservado de settings (`extra="forbid"` rechaza claves desconocidas del
`.env` hasta entonces).

## Provisioning del backend compartido (una vez)

1. **Postgres cloud:** crear un proyecto free-tier en
   [Supabase](https://supabase.com) (o [Neon](https://neon.tech)). En Supabase
   usar el **Session pooler** (puerto 5432, host `...pooler.supabase.com`) sobre
   la base `postgres` que trae por defecto; en Neon se puede nombrar `mlflow`.
   Copiar la URI con `?sslmode=require` — es `MLFLOW_TRACKING_URI` /
   `PETROCAST_MLFLOW_BACKEND_URI`. En el primer arranque MLflow crea sus tablas.
   Compartir la credencial por el canal seguro del equipo (no por git).
2. **Bucket S3 + IAM user (Terraform):** el módulo
   `infra/terraform/modules/s3-mlflow` crea el bucket `petrocast-ml-artifacts`
   (sin expiración de objetos, a diferencia de `s3-artifacts`) y un IAM user
   acotado a ese bucket con su access key. Aplicar desde `envs/shared`:

   ```bash
   make -C infra/terraform apply-shared
   ```

   Obtener los valores (el secret es sensitive → hace falta `-raw`):

   ```bash
   cd infra/terraform/envs/shared
   terraform output -raw mlflow_artifact_root          # s3://petrocast-ml-artifacts/mlflow
   terraform output -raw mlflow_iam_access_key_id      # AWS_ACCESS_KEY_ID
   terraform output -raw mlflow_iam_secret_access_key  # AWS_SECRET_ACCESS_KEY
   ```

   El bucket vive en la región del env `shared` (`us-east-2`) → usar esa como
   `AWS_DEFAULT_REGION`. La access key queda en el state de Terraform (cifrado,
   no en git); compartirla por el canal seguro del equipo.
3. Exportar `PETROCAST_MLFLOW_BACKEND_URI`, `PETROCAST_MLFLOW_ARTIFACT_ROOT` y
   las credenciales AWS en el entorno local de cada integrante.

## Levantar la UI local

```bash
# Modo equipo (backend cloud + S3):
export PETROCAST_MLFLOW_BACKEND_URI='postgresql://postgres.<ref>:<pass>@aws-1-<region>.pooler.supabase.com:5432/postgres?sslmode=require'
export PETROCAST_MLFLOW_ARTIFACT_ROOT='s3://petrocast-ml-artifacts/mlflow'
export AWS_ACCESS_KEY_ID='<mlflow_iam_access_key_id>'
export AWS_SECRET_ACCESS_KEY='<mlflow_iam_secret_access_key>'
export AWS_DEFAULT_REGION='us-east-2'
docker compose -f infra/compose.mlflow.yml up -d --build

# Modo fallback local (sin credenciales cloud, junto al data stack):
docker compose -f infra/compose.data.yml -f infra/compose.mlflow.yml \
  --env-file apps/data/.env up -d --build data-postgres mlflow
```

UI en <http://localhost:5000> (cambiar puerto con `PETROCAST_MLFLOW_PORT`).

## Run de ejemplo (smoke)

Con la UI arriba (o directo contra el backend):

```bash
uv run --with mlflow python - <<'EOF'
import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("petrocast-production-forecast")
with mlflow.start_run(run_name="smoke", tags={"as_of_date": "2024-03-01"}):
    mlflow.log_param("model", "smoke")
    mlflow.log_metric("mase_median", 0.42)
EOF
```

El run debe aparecer en la UI con params, métricas y tags. Si dos integrantes
apuntan al mismo `MLFLOW_TRACKING_URI`, ambos ven el mismo run.

## Staging (listo, no deployado)

`infra/compose.staging.yml` define el servicio `mlflow` con router Traefik
(`mlflow.staging.<dominio>`, TLS + basic-auth) **doblemente gateado**: no está
en la lista de servicios de `deploy-data.sh` y además vive detrás del compose
profile `mlflow`. Para deployarlo en el futuro: publicar la imagen a ECR
(F3-23), cargar `mlflow_backend_uri`/artifact root en SSM → `stack.env`, y
correr `COMPOSE_PROFILES=mlflow dc up -d mlflow` en el nodo.

## Troubleshooting

- **`FATAL: database "mlflow" does not exist` (fallback local):** el volumen
  `data_postgres` es anterior al init 003. Crear a mano:
  `docker compose -f infra/compose.data.yml exec data-postgres psql -U petrocast -c 'CREATE DATABASE mlflow;'`.
- **Artefactos no suben a S3:** verificar `AWS_*` en el entorno del proceso
  que loguea (el cliente sube directo a S3; la UI no proxya artefactos).
- **Rollback del champion:** re-apuntar el alias —
  `mlflow registered-models alias set petrocast-production champion <version>`
  (manual/CLI, aceptable para la demo — ver ADR-0032).
