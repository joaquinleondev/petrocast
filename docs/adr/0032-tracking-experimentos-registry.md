# ADR-0032: Tracking de experimentos y registry de modelos con MLflow

- **Estado:** Propuesto
- **Fecha:** 2026-06-28
- **Autores:** Joaquin Leon Alderete
- **Decisores:** Equipo Petrocast

## Contexto y problema

Fase 3 incorpora un modelo predictivo de producción mensual por pozo
(ver ADR-0030, objetivo y métricas). La adenda técnica exige dos cosas que
recaen sobre esta decisión:

- **RF (funcional):** los devs / ML Engineers DEBEN poder acceder a una
  **plataforma de tracking de experimentos** de machine learning.
- **RNF (no funcional):** el entrenamiento DEBE ser **reproducible**.

"Reproducible" y "plataforma de tracking" implican registrar, para cada
entrenamiento, sus parámetros, métricas, el artefacto de modelo resultante y la
referencia exacta a los datos y al código que lo produjeron (versión/corte de
features `as_of_date`, commit o imagen). Además, la API de predicciones
(ADR-0034) necesita una fuente de verdad de **qué modelo está vigente** — un
*model registry* con un concepto de modelo *champion* y un mecanismo de
promoción/rollback trazable.

Hay dos sub-problemas acoplados que esta decisión resuelve en conjunto:

1. **¿Dónde se trackean los experimentos?** Quién guarda runs, params, métricas
   y artefactos, y cómo un ML Engineer los compara entre sí.
2. **¿Dónde vive el registry de modelos?** Quién versiona los modelos, marca el
   *champion* y permite rollback.

El proyecto **no entrega servicio live en producción** (la adenda lo aclara): la
demo se hace mostrando métricas de distintos runs, llamadas a la API y el
trigger de retrain. Por eso la plataforma debe poder **correrse localmente para
la demo**, pero quedar **lista para deployar**, y — idealmente — permitir que
los tres integrantes **compartan los mismos runs y el mismo modelo champion**
sin tener que hostear un servidor 24/7.

## Drivers de la decisión

- **Tracking + registry en una sola herramienta.** Evitar pegar dos sistemas
  distintos para runs y para versionado de modelos.
- **Reproducibilidad.** Cada run debe quedar atado a params, métricas,
  artefacto, `as_of_date` de features y commit/imagen.
- **Acceso del ML Engineer a una plataforma** (RF de la adenda), con UI para
  comparar runs.
- **Compartido por el equipo sin servidor 24/7.** Idealmente, un backend en la
  nube (DB + object storage) contra el que cada uno corre la UI local.
- **Costo cero y OSS self-hosted.** Sin SaaS pago para features básicas, sin
  tier enterprise para registry o self-host.
- **Encaje con el stack existente.** Python en todo el repo (ADR-0012),
  PostgreSQL 16 ya operativo (ADR-0023), buckets S3 ya provisionados por
  Terraform (`modules/s3-artifacts`, ADR-0019), despliegue por Compose/Swarm
  (ADR-0027). La herramienta no debería sumar un stack propietario.
- **Integración con el código.** El training (`apps/ml`) debe loguear con pocas
  líneas; el serving (`apps/api`, ADR-0034) debe poder cargar el champion por un
  identificador estable.
- **Aliases, no stages.** El mecanismo de "champion" debe usar la API vigente de
  la herramienta, no features deprecadas.

## Opciones consideradas

1. **MLflow OSS (self-hosted).** Tracking + Model Registry en un solo proyecto
   Apache 2.0. *Backend store* en una base SQL (params, métricas, runs, registry)
   y *artifact store* en object storage (S3) — dos stores separados. UI web para
   comparar runs. SDK Python nativo (`mlflow.log_*`, autolog para
   scikit-learn/LightGBM). Registry con **aliases** (`@champion`) y tags desde
   MLflow 2.9 (los *stages* quedaron deprecados).
2. **Weights & Biases (W&B).** Plataforma SaaS líder en tracking, con UI de
   comparación y colaboración excelentes. *Free tier* para uso personal/académico,
   pero los proyectos privados de equipo y el self-host (**W&B Server**) caen en
   planes pagos/enterprise. Hosteada en la nube de un tercero.
3. **ClearML.** Plataforma MLOps completa (tracking + orquestación + gestión de
   datos + serving). Self-host OSS posible, pero el server son **varios servicios**
   (API server, web, file server, MongoDB, Redis, Elasticsearch).
4. **Tracking casero (archivos + DB).** Loguear params/métricas a tablas
   PostgreSQL o JSON y subir artefactos a S3 con `boto3`, sin dependencia nueva.

## Decisión

Adoptamos **MLflow OSS** como plataforma única de **tracking de experimentos y
model registry**, con esta topología:

- **Backend store:** **PostgreSQL en la nube compartida** (Neon o Supabase, free
  tier; alternativa AWS RDS si el equipo prefiere mantenerlo dentro de la cuenta).
  Guarda runs, params, métricas y el registry.
- **Artifact store:** **S3** (un bucket reutilizando `modules/s3-artifacts`,
  ADR-0019).
- **UI:** se levanta con **Docker Compose local** apuntando al backend cloud + S3
  (`infra/compose.mlflow.yml`, backlog #08). Se deja **lista para deployar** en
  staging detrás de Traefik (router `mlflow.staging.petrocast.shop`, mismo patrón
  que Dagster/Metabase/DataHub en ADR-0027), pero **no se deploya** para la
  entrega por presupuesto de cómputo.
- **Champion:** se modela con un **alias de registry `champion`**
  (`models:/petrocast-production@champion`), no con stages deprecados. El rollback
  es re-apuntar el alias a la versión anterior (ADR-0034 y backlog #16).

### Por qué MLflow

- **Tracking y registry en una sola herramienta OSS**, sin pegar dos sistemas.
- **La separación backend store / artifact store es justo lo que habilita el
  modelo "DB en la nube + UI local".** Apuntando el `--backend-store-uri` a una
  Postgres compartida y el `--default-artifact-root` a S3, **cada integrante corre
  la UI local pero lee/escribe los mismos runs, métricas y el mismo champion** —
  sin necesidad de hostear un servidor 24/7. Cubre la demo y el trabajo en equipo
  con la misma topología.
- **SDK Python nativo.** `mlflow.start_run()`, `log_param/metric/artifact` y
  `mlflow.lightgbm.autolog()` instrumentan el training de `apps/ml` con pocas
  líneas (backlog #13/#14); el serving carga el champion con
  `mlflow.pyfunc.load_model("models:/...@champion")` (ADR-0034).
- **Aliases vigentes** (no stages deprecados): el champion es un alias movible,
  con rollback trivial y trazable.
- **Costo cero, Apache 2.0**, sin tier enterprise para registry ni self-host.
- **Encaje con el stack:** reusa PostgreSQL y S3 que ya tenemos; la UI es un
  contenedor más en Compose; es Python, igual que el resto del repo.

### Por qué no las otras

- **W&B** tiene mejor UI/colaboración, pero el **self-host es enterprise/pago** y
  el SaaS implica datos en la nube de un tercero y límites de equipo en el free
  tier. Choca con "OSS self-hosted, costo cero, compartido por el equipo".
- **ClearML** hace mucho más de lo que necesitamos: la **orquestación ya la cubre
  Dagster** (ADR-0033) y no queremos un segundo orquestador. Su self-host son
  ~6 servicios, desproporcionado para 3 EC2 chicas y una demo local.
- **Tracking casero** obliga a reimplementar comparación de runs, versionado de
  modelos, registry y UI — exactamente lo que MLflow regala — y difícilmente
  calificaría como la "plataforma de tracking" que pide la adenda.

## Consecuencias

**Positivas:**

- Tracking + registry unificados, reproducibles y con UI de comparación.
- **Runs y champion compartidos por todo el equipo** vía backend cloud + S3, sin
  servidor 24/7 (encaja con la entrega sin prod live).
- Champion por **alias** con rollback trazable (insumo de ADR-0034 y #16).
- Instrumentación mínima desde `apps/ml`; carga directa desde `apps/api`.
- Reusa PostgreSQL y S3 existentes; cero costo de licencias.
- Lista para deployar en staging con el patrón Traefik de ADR-0027 si Fase 4 lo
  requiere.

**Negativas / trade-offs asumidos:**

- Sumamos un servicio (UI MLflow) y una dependencia cliente (`mlflow`) a
  `apps/ml` y a la imagen de `apps/api` (esta última se cuantifica en ADR-0034).
- El backend store es una **dependencia externa nueva** (Postgres en la nube). Se
  mitiga eligiendo un free tier (Neon/Supabase) y porque su contenido es
  regenerable re-corriendo los entrenamientos; los secretos van por variables de
  entorno (ADR-0018) y SSM en staging.
- Corrida local para la demo ⇒ **no hay URL persistente 24/7**. Aceptable: la
  adenda no exige servicio live y la demo se hace localmente.

**Neutras:**

- Es ortogonal a la **orquestación** (Dagster, ADR-0033): los assets de Dagster
  loguean a MLflow.
- Es ortogonal al **feature store** (ADR-0031): MLflow registra *qué* `as_of_date`
  de features usó cada run, pero no almacena las features.
- El contrato de configuración (`MLFLOW_TRACKING_URI`, artifact root, credenciales)
  se congela en backlog #08 (contrato C) y lo consumen #14/#15/#16/#19.

## Pros y contras de cada opción

### MLflow OSS (elegida)

- ✅ Tracking + model registry en una sola herramienta Apache 2.0.
- ✅ Backend store SQL + artifact store S3 separados ⇒ DB cloud compartida + UI
  local sin servidor 24/7.
- ✅ SDK Python nativo + autolog para LightGBM/scikit-learn.
- ✅ Aliases (`@champion`) vigentes; rollback trivial.
- ✅ Reusa PostgreSQL y S3 del stack; cero costo.
- ❌ Suma un servicio (UI) y deps de cliente a `apps/ml` y a la imagen de la API.
- ❌ La UI no es multi-tenant ni tiene control de acceso fino en OSS (irrelevante
  para 3 personas).

### Weights & Biases

- ✅ UI de comparación y colaboración de primer nivel.
- ✅ Free tier generoso para uso individual/académico.
- ❌ Self-host (W&B Server) es enterprise/pago.
- ❌ SaaS: datos en la nube de un tercero; límites de equipo en el free tier;
  depende de cuenta e internet.
- ❌ Choca con "OSS self-hosted, costo cero" del proyecto.

### ClearML

- ✅ Plataforma MLOps completa (tracking + registry + orquestación + serving).
- ✅ Self-host OSS posible.
- ❌ Duplica responsabilidades que ya cubre Dagster (orquestación) ⇒ dos
  orquestadores compitiendo.
- ❌ Self-host = ~6 servicios (Mongo, Redis, Elasticsearch, etc.),
  desproporcionado para 3 EC2 y una demo local.

### Tracking casero (archivos + DB)

- ✅ Cero dependencias nuevas; control total.
- ✅ Reusa Postgres y S3 directamente.
- ❌ Hay que reimplementar comparación de runs, versionado, registry, aliases y
  UI — todo lo que MLflow da gratis.
- ❌ Difícilmente califica como la "plataforma de tracking" que pide la adenda.
- ❌ Cada bug es deuda del equipo; con MLflow es deuda upstream.

## Referencias

- [MLflow — Tracking](https://mlflow.org/docs/latest/tracking.html)
- [MLflow — Model Registry](https://mlflow.org/docs/latest/model-registry.html)
- [MLflow — Model Registry aliases (reemplazan stages)](https://mlflow.org/docs/latest/model-registry.html#deprecated-using-model-stages)
- [MLflow — Backend & artifact stores](https://mlflow.org/docs/latest/tracking/backend-stores.html)
- [Weights & Biases](https://docs.wandb.ai/) · [ClearML](https://clear.ml/docs/)
- [Neon (Postgres serverless)](https://neon.tech/) · [Supabase](https://supabase.com/)
- Adenda técnica Fase 3 — RF tracking de experimentos, RNF reproducibilidad.
- [ADR-0012](0012-stack-backend-python-fastapi-uv.md) — stack Python/FastAPI.
- [ADR-0018](0018-gestion-configuracion-pydantic-settings.md) — configuración por entorno.
- [ADR-0019](0019-infraestructura-terraform-aws.md) — S3 vía Terraform.
- [ADR-0023](0023-arquitectura-medallion-dbt.md) — PostgreSQL del warehouse.
- [ADR-0027](0027-topologia-despliegue-fase2.md) — patrón de servicios en staging.
- ADR-0033 (en redacción) — orquestación con Dagster.
- ADR-0034 (en redacción) — serving del modelo y contrato de API.
- Backlog Fase 3 — [#03](../backlog/issues-fase-3.md), #08 (plataforma), #14 (logging), #16 (champion).
