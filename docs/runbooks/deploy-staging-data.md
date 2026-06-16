# Runbook deploy: stack de datos Phase-2 en staging

## Propósito y disparador

Este runbook guía a **Platform** al levantar el stack completo de datos Phase-2
en el nodo EC2 de staging para verificación E2E, corrección de bugs o
preparación de una demo. Cubre la creación de secretos, la publicación de la
imagen de datos, el aprovisionamiento de la infra con Terraform, la carga
inicial de datos y el ciclo de vida (bajar / levantar) del ambiente.

Se ejecuta ante alguno de estos disparadores:

- Primera puesta en marcha del stack Phase-2 en staging (fresh deploy).
- Re-deploy tras un `terraform destroy` previo, con o sin restauración del
  volumen de datos desde snapshot.
- Verificación E2E después de merges en las features F2-20 a F2-22
  (Metabase, DataHub, API gold).
- Preparación de una demo que exige datos reales en todas las capas
  (`bronze` → `silver` → `gold`) con linaje navegable.

El procedimiento no cubre reprocesamientos históricos puntuales (ver
[backfill histórico](backfill.md)) ni incidentes de calidad en datos ya
existentes (ver [Data Owner](data-owner.md)).

## Rol, dueño y prerrequisitos

- **Dueño:** Platform / Joaquin.
- **Escala a:** Data Engineer para cualquier incidente en el pipeline dbt/dlt;
  Infra para bloqueos de Terraform, IAM o red.

Antes de comenzar se necesita:

- **AWS CLI** configurado con un perfil que tenga permisos para: `ssm:*`,
  `ec2:*`, `terraform` (S3, DynamoDB, IAM read) y `ecr:GetAuthorizationToken`.
- **Terraform >= 1.15** instalado localmente.
- **Docker** disponible localmente (solo para generar `htpasswd` si no se
  cuenta con el binario de Apache).
- **`gh` CLI** autenticado, para disparar el workflow de build.
- **OIDC configurado** en la cuenta AWS: el rol `CI_ROLE_ARN` referenciado en
  los secrets de GitHub.
- **Acceso SSM al nodo:** no existe SSH abierto; toda sesión interactiva y
  todo comando remoto se ejecuta vía `aws ssm start-session` /
  `aws ssm send-command`.

Los insumos principales son los **secretos en SSM Parameter Store** que se
crean en el primer paso.

## Pasos

### Paso 1 — Crear los secretos en SSM Parameter Store

Todos los secretos se almacenan bajo el path `/petrocast/staging/data/` como
`SecureString`. La instancia EC2 (user-data) los lee al arrancar para generar
los `.env` de cada servicio.

```bash
# Ajustar la región si se usa un perfil nombrado
AWS_PROFILE=petrocast
REGION=us-east-2
PATH_PREFIX=/petrocast/staging/data

# Credenciales del data warehouse (PostgreSQL DW)
aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/dw_user" --value "<usuario-dw>"

aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/dw_password" --value "<contraseña-dw>"

aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/dw_database" --value "<nombre-bd>"

# URLs de datos.gob.ar (fuentes Bronze)
aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/source_production_url" \
  --value "<url-produccion-datos-gob-ar>"

aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/source_wells_url" \
  --value "<url-pozos-datos-gob-ar>"

# Webhook de notificaciones (Slack u otro receptor)
aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/notification_webhook_url" \
  --value "<webhook-url>"

# Contraseña de la base app de Metabase (user petrocast_bi en el DW)
aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/bi_db_password" --value "<contraseña-bi>"

# Cuenta admin de Metabase
aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/metabase_admin_email" \
  --value "<email-admin-metabase>"

aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/metabase_admin_password" \
  --value "<contraseña-admin-metabase>"

# Hash bcrypt para basic-auth de Traefik (generado con htpasswd)
# Generar el hash antes de cargar el parámetro:
#   htpasswd -nbB <usuario> <contraseña>
#   Ejemplo de salida: admin:$2y$05$...
aws ssm put-parameter --profile "$AWS_PROFILE" --region "$REGION" \
  --type SecureString --overwrite \
  --name "${PATH_PREFIX}/basic_auth_htpasswd" \
  --value "admin:\$2y\$05\$<hash-bcrypt>"
```

Notas sobre los parámetros:

- `source_production_url` y `source_wells_url` son las URLs directas del
  dataset CSV en datos.gob.ar. El data app las consume vía
  `PETROCAST_SOURCE_PRODUCTION_URL` y `PETROCAST_SOURCE_WELLS_URL`.
- `basic_auth_htpasswd` debe estar en el formato que acepta Traefik:
  `usuario:$2y$...`. El símbolo `$` debe escaparse al pasarlo por shell
  (`\$`), pero el valor almacenado en SSM no lleva escapes. Generarlo con
  `htpasswd -nbB <usuario> <contraseña>` (o con Docker:
  `docker run --rm httpd:alpine htpasswd -nbB <usuario> <contraseña>`).
- Verificar que los diez parámetros existan antes de continuar:

  ```bash
  aws ssm get-parameters-by-path --profile "$AWS_PROFILE" --region "$REGION" \
    --path "${PATH_PREFIX}" --with-decryption \
    --query "Parameters[].Name" --output text
  ```

### Paso 2 — Publicar la imagen de datos en ECR

La imagen `petrocast/data:staging-latest` se construye y publica por el workflow
`build-data.yml` cuando se mergea un cambio en `apps/data/**` a `main`. Para
forzar una publicación fuera de ciclo, disparar el workflow manualmente:

```bash
gh workflow run build-data.yml --ref main
```

Verificar que la imagen existe en ECR antes de avanzar:

```bash
aws ecr describe-images --profile "$AWS_PROFILE" --region "$REGION" \
  --repository-name petrocast/data \
  --image-ids imageTag=staging-latest \
  --query "imageDetails[0].imagePushedAt"
```

> La imagen de la API (`petrocast/mock-api`) se publica en `ci.yml` al
> mergear a `main`. Ambas imágenes deben existir en ECR antes del apply.

### Paso 3 — Levantar la infra con Terraform

Desde la raíz del repo:

```bash
cd infra/terraform/envs/staging
# El bucket/region del backend vienen de infra/terraform/backend.config;
# backend.tf de este env fija solo la key.
terraform init -backend-config=../../backend.config
```

**Primera vez (volumen de datos nuevo):** no pasar `data_snapshot_id`; Terraform
crea un volumen EBS vacío. El bootstrap lo formatea y lo monta en
`/var/lib/docker/volumes` (así todo el estado de los volúmenes Docker —
postgres, dagster, metabase, datahub — vive en el disco que se snapshotea).

```bash
terraform apply \
  -var "instance_type=t3.xlarge" \
  -var "traefik_acme_email=<email-letsencrypt>" \
  -var "state_bucket=<state-bucket>"
```

**Restore desde snapshot** (re-deploy con datos conservados): obtener el
`SnapshotId` del snapshot anterior (ver sección "Bajar y levantar la infra"),
luego:

```bash
terraform apply \
  -var "instance_type=t3.xlarge" \
  -var "traefik_acme_email=<email-letsencrypt>" \
  -var "state_bucket=<state-bucket>" \
  -var "data_snapshot_id=snap-XXXX"
```

El apply provisiona:

- La instancia EC2 **t3.xlarge** (us-east-2) con el user-data (bootstrap).
- El volumen EBS de datos (nuevo o restaurado desde snapshot), montado en
  `/var/lib/docker/volumes`.
- Los registros DNS Route53:
  `staging`, `api.staging`, `bi.staging`, `dagster.staging`,
  `datahub.staging` — todos apuntando a la IP pública de la instancia.
- El rol IAM de la instancia con permisos de lectura de SSM bajo
  `/petrocast/staging/data/*`.

El **user-data (bootstrap)** en `/var/log/bootstrap-swarm.log` realiza:

1. Instala Docker y AWS CLI; monta el volumen de datos en
   `/var/lib/docker/volumes` (lo formatea si es nuevo).
2. Inicia Swarm y despliega Traefik.
3. Corre `deploy-data.sh`, que lee los parámetros SSM, genera el `.env` del
   stack y el middleware basic-auth de Traefik, autentica en ECR y baja las
   imágenes.
4. Ejecuta `docker compose up` con los ~13 contenedores del stack.

Esperar ~10 minutos para que el bootstrap complete. Verificar desde la CLI:

```bash
INSTANCE_ID=$(terraform output -raw instance_id)

aws ssm send-command \
  --profile "$AWS_PROFILE" --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["tail -30 /var/log/bootstrap-swarm.log"]' \
  --output text \
  --query "Command.CommandId"
# Obtener el resultado con:
# aws ssm get-command-invocation --command-id <id> \
#   --instance-id $INSTANCE_ID --query "StandardOutputContent"
```

### Paso 4 — Seed E2E: cargar y materializar datos

Una vez que los contenedores están en pie, abrir una sesión SSM al nodo y
materializar el pipeline completo para un rango de meses representativo.

Iniciar sesión interactiva:

```bash
aws ssm start-session \
  --profile "$AWS_PROFILE" --region "$REGION" \
  --target "$INSTANCE_ID"
```

Dentro de la sesión, ejecutar como `root` (o con `sudo`). El rango de meses a
sembrar es configurable con `SEED_RANGE` (default `2023-01-01...2023-07-01`):

```bash
# 1. Materializar bronze → silver → gold para el rango E2E.
#    deploy-data.sh seed corre la materialización de Dagster + dbt build.
SEED_RANGE="2016-01-01...2024-12-01" bash /opt/petrocast/deploy-data.sh seed

# 2. Provisionar Metabase (datasource gold read-only + dashboards). El script es
#    stdlib y corre en el host; Metabase escucha en localhost:3001.
set -a; . /var/lib/petrocast/stack.env; set +a
MB_URL=http://localhost:3001 \
PETROCAST_METABASE_ADMIN_EMAIL="$(aws ssm get-parameter --with-decryption \
  --name /petrocast/staging/data/metabase_admin_email --query Parameter.Value --output text)" \
PETROCAST_METABASE_ADMIN_PASSWORD="$(aws ssm get-parameter --with-decryption \
  --name /petrocast/staging/data/metabase_admin_password --query Parameter.Value --output text)" \
  python3 /opt/petrocast/metabase/provision_metabase.py

# 3. Generar artefactos dbt e ingestar el linaje en DataHub (GMS en localhost:8080).
docker compose -p petrocast \
  -f /opt/petrocast/compose.data.yml -f /opt/petrocast/compose.datahub.yml \
  -f /opt/petrocast/compose.dev.yml -f /opt/petrocast/compose.staging.yml \
  exec -T dagster uv run dbt docs generate --project-dir dbt --profiles-dir dbt
PETROCAST_DATAHUB_GMS=http://localhost:8080 bash /opt/petrocast/datahub/datahub.sh ingest
```

> `deploy-data.sh seed` usa los selectores reales (`bronze/production_by_well`,
> `bronze/wells_registry`, `tag:silver`, `tag:gold`). Alternativamente, la
> materialización se dispara desde la **UI de Dagster** en
> `https://dagster.staging.petrocast.shop` (basic-auth) con el menú de backfill.
>
> Para rangos históricos grandes, preferir ventanas de 12 meses y evitar
> ejecutar durante uso activo de Metabase. Ver
> [backfill histórico](backfill.md) para el procedimiento detallado por CLI.

## Validación

Una vez completado el seed, verificar el stack completo:

| Endpoint | Credenciales | Resultado esperado |
|---|---|---|
| `https://staging.petrocast.shop/health/ready` | ninguna | `200 OK` — API Fase 1 intacta |
| `https://api.staging.petrocast.shop/api/v1/wells` | ninguna | JSON con pozos de `gold` |
| `https://api.staging.petrocast.shop/api/v1/forecast` | ninguna | JSON con forecast desde `gold` |
| `https://bi.staging.petrocast.shop` | basic-auth | Metabase con dashboards de producción |
| `https://dagster.staging.petrocast.shop` | basic-auth | Assets bronze → silver → gold verdes; checks sin fallos |
| `https://datahub.staging.petrocast.shop` | basic-auth | Linaje `silver_production` → `fact_production` navegable |

Checklist E2E:

- [ ] `staging.petrocast.shop/health/ready` responde `200` (API Fase 1).
- [ ] `/api/v1/wells` devuelve filas con `well_id` y nombre de empresa.
- [ ] `/api/v1/forecast` devuelve datos con al menos un punto por pozo.
- [ ] Dagster UI muestra el último run verde para los assets `silver` y `gold`.
- [ ] Los asset checks de `silver/silver_production` aparecen verdes (sin
  checks bloqueantes fallidos).
- [ ] Metabase carga sin error y los tres dashboards muestran datos del
  último mes materializado.
- [ ] DataHub muestra el grafo de linaje desde `silver_production` hacia
  `gold/fact_production` y las dimensiones.
- [ ] El volumen de datos está montado y tiene espacio disponible:
  `df -h /var/lib/docker/volumes` (verificar vía SSM).

## Si algo falla: rollback, plan B y escalamiento

**El `terraform apply` falla:**

- Revisar el plan previo con `terraform plan` y confirmar que el rol IAM de
  la instancia tiene permisos `ssm:GetParametersByPath` bajo
  `/petrocast/staging/data/*`.
- Si el fallo es de S3 o DynamoDB (backend de estado), verificar el bucket
  y la tabla de locks especificados en `backend.tf`.
- En caso de estado corrompido, hacer `terraform state list` y coordinar con
  Infra antes de cualquier `terraform state rm`.

**Traefik no obtiene certificado TLS (Let's Encrypt):**

- Verificar que los registros DNS propagaron: `dig api.staging.petrocast.shop`.
  La propagación puede tardar hasta 5 minutos después del apply.
- Revisar los logs de Traefik:

  ```bash
  aws ssm send-command --profile "$AWS_PROFILE" --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["docker service logs traefik_traefik --tail 50"]'
  ```

- Si el problema es rate-limit de Let's Encrypt, esperar 1 hora (el límite
  es 5 certificados fallidos por dominio por hora) o usar el staging ACME
  de Let's Encrypt para pruebas.

**Memoria insuficiente en t3.xlarge (~16 GB RAM):**

- DataHub (GMS + MySQL + OpenSearch) consume ~6-8 GB. Si el nodo se queda
  sin memoria, bajar DataHub temporalmente:

  ```bash
  docker compose -f /opt/petrocast/compose.datahub.yml down
  ```

- Como plan B, hacer `terraform apply -var "instance_type=t3.2xlarge"` para
  subir a 32 GB RAM. El cambio requiere un `terraform apply` que reemplaza la
  instancia (downtime de ~3 min).

**El bootstrap no montó el volumen de datos:**

- Verificar en `/var/log/bootstrap-swarm.log` que el paso de montaje de EBS
  no lanzó un error.
- Desde SSM, confirmar el estado del volumen:

  ```bash
  lsblk
  df -h /var/lib/docker/volumes
  ```

- Si el volumen no aparece adjunto, verificar en la consola AWS EC2 que el
  volumen EBS está en estado `in-use` y adjunto a la instancia correcta.
- Como plan B: adjuntar el volumen manualmente desde la consola y montar (Docker
  debe estar detenido al montar sobre su directorio de volúmenes):

  ```bash
  systemctl stop docker
  mount /dev/<device> /var/lib/docker/volumes
  systemctl start docker
  ```

**Faltan secretos en SSM:**

- El bootstrap loguea en `/var/log/bootstrap-swarm.log` cualquier parámetro
  SSM no encontrado.
- Re-crear el parámetro faltante (Paso 1) y volver a correr el deploy del stack
  (re-lee SSM y re-aplica `compose up`, sin recrear la instancia):

  ```bash
  aws ssm send-command --profile "$AWS_PROFILE" --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["bash /opt/petrocast/deploy-data.sh up"]'
  ```

**Logs principales:**

| Fuente | Cómo acceder |
|---|---|
| Bootstrap | `tail -f /var/log/bootstrap-swarm.log` vía SSM |
| Un servicio | `docker logs --tail 50 petrocast-<servicio>-1` vía SSM (p. ej. `petrocast-dagster-1`) |
| deploy-data | `tail -f /var/log/petrocast-deploy-data.log` vía SSM |
| CloudWatch | Grupo `/petrocast/staging/*` en la consola de AWS |

**Escalar a:** Data Engineer si falla dbt/dlt/Dagster tras el bootstrap;
Platform/Infra si falla la instancia, el volumen EBS, la red o los permisos IAM.

## Bajar y levantar la infra (lifecycle)

El nodo de staging es el mismo que corre la **API mock de Fase 1**. Un
`terraform destroy` baja ambos stacks. La API mock se vuelve a desplegar en el
próximo merge a `main` (workflow `deploy-staging.yml`) o haciendo un nuevo
`terraform apply`.

### Bajar la infra

1. Obtener el `volume-id` del volumen de datos:

   ```bash
   cd infra/terraform/envs/staging
   terraform output -raw data_volume_id
   # Alternativamente, por tag Name:
   aws ec2 describe-volumes --profile "$AWS_PROFILE" --region "$REGION" \
     --filters "Name=tag:Name,Values=petrocast-swarm-staging-data" \
     --query "Volumes[0].VolumeId" --output text
   ```

2. Crear un snapshot antes de destruir (el snapshot conserva todos los datos
   persistentes: Postgres DW, Dagster home, Metabase, DataHub):

   ```bash
   aws ec2 create-snapshot \
     --profile "$AWS_PROFILE" --region "$REGION" \
     --volume-id <volume-id> \
     --description "petrocast staging-data $(date -u +%Y-%m-%d)" \
     --tag-specifications 'ResourceType=snapshot,Tags=[{Key=Name,Value=petrocast-staging-data},{Key=Env,Value=staging}]'
   ```

   Anotar el `SnapshotId` devuelto (p. ej. `snap-0abc1234def567890`).
   Esperar a que el snapshot pase a estado `completed`:

   ```bash
   aws ec2 wait snapshot-completed \
     --profile "$AWS_PROFILE" --region "$REGION" \
     --snapshot-ids snap-XXXX
   ```

3. Destruir la infra:

   ```bash
   cd infra/terraform/envs/staging
   terraform destroy \
     -var "instance_type=t3.xlarge" \
     -var "traefik_acme_email=<email-letsencrypt>" \
     -var "state_bucket=<state-bucket>"
   ```

Costo en estado de reposo: solo el snapshot EBS (~$0.05/GB/mes ≈ $1-3/mes
para volúmenes de 20-60 GB). Los registros Route53 se eliminan con el destroy.

### Levantar la infra (restore)

Repetir el Paso 3 pasando el `SnapshotId` obtenido al bajar:

```bash
cd infra/terraform/envs/staging
terraform apply \
  -var "instance_type=t3.xlarge" \
  -var "traefik_acme_email=<email-letsencrypt>" \
  -var "state_bucket=<state-bucket>" \
  -var "data_snapshot_id=snap-XXXX"
```

El bootstrap restaura el volumen desde el snapshot, lo monta en
`/var/lib/docker/volumes` con todos los datos intactos y ejecuta
`docker compose up`. El stack queda operativo en ~10 minutos. Repetir la checklist de **Validación** completa antes de dar por
levantado el ambiente.

> Si la imagen `petrocast/data:staging-latest` fue actualizada desde el último
> deploy, el bootstrap descarga la nueva imagen automáticamente al hacer el
> `docker compose up`. No es necesario volver a ejecutar el Paso 2
> manualmente.

## Consideraciones no funcionales

**Costo:**

- EC2 t3.xlarge en us-east-2: ~$0.166/h ≈ $120/mes si se deja 24/7.
- EBS data volume (p. ej. 40 GB gp3): ~$3/mes mientras la instancia está en
  pie.
- Snapshot EBS (estado de reposo): ~$0.05/GB/mes ≈ $1-3/mes.
- Estrategia recomendada: hacer `terraform destroy` entre sesiones de trabajo;
  el costo idle queda en $1-3/mes de snapshot.

**Seguridad:**

- Todos los endpoints están detrás de TLS (Let's Encrypt) + basic-auth
  (Traefik). No existe ningún puerto abierto directamente; el acceso al nodo
  es exclusivamente vía SSM (no hay SSH público).
- Los secretos viven en SSM Parameter Store como `SecureString`; nunca deben
  commitearse en el repo.
- El rol IAM de la instancia está scoped a `ssm:GetParametersByPath` bajo
  `/petrocast/staging/data/*`; no tiene acceso a parámetros de producción.
- Bajar la infra entre sesiones reduce la superficie de ataque y el costo.

**Disponibilidad:**

- El ambiente de staging no tiene SLA. Los incidentes del pipeline dbt/dlt
  en staging no requieren triaje de 4 horas (ese SLA es de producción).
- DataHub consume ~6-8 GB de RAM; en caso de presión de memoria es el primer
  servicio a bajar para liberar recursos.

**Datos y backup:**

- El volumen de datos (montado en `/var/lib/docker/volumes`) es el único estado
  persistente. El snapshot es el backup. Sin snapshot, un `terraform destroy`
  elimina todos los datos de staging de forma irrecuperable.
- Los datos de staging provienen de fuentes públicas (datos.gob.ar) y pueden
  recargarse desde cero con un fresh deploy + seed E2E completo; aun así, el
  snapshot ahorra ~1-2 horas de materialización.

## Referencias

- ADR-0027: topología de despliegue Fase 2 (staging + producción).
- ADR-0013: registro ECR y ciclo de vida de imágenes.
- `infra/metabase/README.md`: variables de entorno, provisioning y roles de
  Metabase.
- `infra/datahub/README.md`: arquitectura de linaje, ingesta dbt y Postgres.
- `docs/fase-2/README.md`: visión general del stack Phase-2.
- [Backfill histórico](backfill.md): materializar rangos históricos en Bronze,
  Silver y Gold.
- [Data Engineer](data-engineer.md): reprocesamiento y validación de datos.
- [Data Owner](data-owner.md): decisión de aptitud del dato ante bloqueos de
  calidad.
- F2-20: Metabase — dashboards de producción.
- F2-21: DataHub — catálogo y linaje navegable.
- F2-22: API gold — endpoints conectados a `gold.fact_production`.
