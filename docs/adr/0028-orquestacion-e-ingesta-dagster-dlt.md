# ADR-0028: Orquestación con Dagster e ingesta con dlt

- **Estado:** Aceptado
- **Fecha:** 2026-06-08
- **Autores:** Santino Domato
- **Decisores:** Equipo Petrocast

## Contexto y problema

Fase 2 introduce un pipeline de datos completo sobre una arquitectura
medallion (`bronze` → `silver` → `gold`) en PostgreSQL, con dos fuentes
oficiales de [datos.gob.ar](https://datos.gob.ar) (producción de pozos no
convencionales y listado de pozos). La adenda técnica de Fase 2 exige:

- DAGs-as-code (RF5).
- Idempotencia en cada paso (RNF8).
- Retries con backoff exponencial (RF6).
- Observabilidad mínima del workflow (RF6).
- Procesos reprocesables por rango de fechas (RF7).
- Un ADR explícito que documente la decisión de orquestación.

Antes de modelar transformaciones (eso lo cubre el ADR de medallion, #04)
necesitamos resolver dos preguntas separadas pero acopladas:

1. **¿Qué orquestador corre el pipeline?** Quién dispara los pasos, los
   programa, los reintenta, los expone en una UI y los conecta a alertas.
2. **¿Cómo extraemos y cargamos los datos a `bronze`?** Quién resuelve la
   parte EL (Extract + Load) del ELT — paginación de la API, manejo de
   esquema, normalización de tipos, idempotencia de la carga.

Las dos decisiones se acoplan porque el orquestador define el modelo de
ejecución (tareas vs assets vs flows) y la herramienta de ingesta tiene que
encajar en ese modelo sin que el equipo termine reimplementando la
integración a mano. La adenda recomienda decidirlas en conjunto.

## Drivers de la decisión

- **Afinidad medallion.** El pipeline tiene una estructura natural de capas
  (`bronze`, `silver`, `gold`) con dependencias direccionales. El modelo de
  ejecución debería reflejar eso, no esconderlo detrás de tareas opacas.
- **Idempotencia por partición de mes.** Rematerializar un mes específico
  tiene que ser una operación de primera clase, no un workaround.
- **Retries con backoff exponencial.** La API de datos.gob.ar puede fallar
  por límites de rate o por caídas momentáneas; el orquestador tiene que
  manejarlo declarativamente.
- **Observabilidad sin operar otro stack.** Necesitamos ver el estado del
  pipeline (qué corrió, qué falló, qué está pendiente) sin sumar un Grafana
  dedicado o un servicio externo.
- **Encaje con el equipo.** Tres personas, ~6 semanas hasta el 2026-06-15.
  La curva de aprendizaje cuenta tanto como el techo de capacidades.
- **Stack Python first.** El backend (Fase 1) ya está en Python con
  FastAPI + uv ([ADR-0012](0012-stack-backend-python-fastapi-uv.md)).
  Mantener un único lenguaje reduce el costo cognitivo y el setup.
- **Licencia open source no restrictiva.** Apache 2.0 o MIT, sin tier
  enterprise para features básicas.
- **Cero infraestructura proprietaria.** Tiene que correr en local
  (Docker Compose) y eventualmente en la misma EC2 que el resto del
  stack ([ADR-0010](0010-plataforma-hosting.md)), sin SaaS pago.

## Opciones consideradas

### Orquestación

1. **Dagster 1.x** — modelo asset-centric. Cada tabla/dataset es un *software-defined asset* con su definición, dependencias, particiones y materialización. La UI navega assets y su linaje. Integración nativa con dbt (`dagster-dbt`) y con dlt (`dagster-dlt`).
2. **Apache Airflow 3.x** — modelo operator-centric clásico (tasks dentro de DAGs). La línea 3.x (2025) introduce Assets v2, separación de scheduler y task execution, mejor manejo de logs. Ecosistema enorme de providers.
3. **Prefect 3.x** — modelo flow-centric, más dinámico. Decoradores `@flow` y `@task` sobre Python plano. Menos opinionado sobre lineage. Tier cloud pago para features de observabilidad enterprise; OSS suficiente para nuestra escala.

### Ingesta (Extract + Load a `bronze`)

1. **`dlt` (dlthub)** — librería Python pura para EL. Maneja paginación, schema inference y schema evolution, normalización (`json_normalize` automático), incremental loading, write-disposition por configuración (`replace` / `append` / `merge`). Apache 2.0. Integración oficial `dagster-dlt`.
2. **Airbyte OSS** — plataforma completa con UI y conectores enlatados. Requiere stack propio (~6 contenedores, BD interna). Conectores Java/Python heterogéneos.
3. **Meltano** — CLI sobre el ecosistema Singer (taps + targets). Pipeline definido en YAML. Reusa conectores Singer.
4. **Scripts custom en Python** — `httpx` + `psycopg` + pandas; sin dependencia nueva.

## Decisión

Adoptamos **Dagster 1.x como orquestador** y **`dlt` como herramienta de
ingesta**, integrados vía el módulo oficial **`dagster-dlt`**.

### Por qué Dagster

- Su modelo **asset-centric** mapea uno-a-uno con la arquitectura medallion.
  `bronze.production`, `silver.production`, `gold.fact_production` son
  assets con dependencias declaradas; el grafo de assets *es* el linaje a
  nivel tabla, sin trabajo adicional.
- **Particiones nativas por fecha.** El asset declara
  `MonthlyPartitionsDefinition`; rematerializar un mes específico es un
  clic en la UI o un comando `dagster asset materialize --partition-range`.
  No hay que inventar idempotencia — es de primera clase.
- **Asset checks** integran las validaciones de calidad (#07) y permiten
  que el bloqueo operativo de Gold (#18) sea declarativo, no un IF dentro
  de una tarea.
- **`dagster-dbt`** convierte cada modelo dbt en un asset; el linaje de
  Dagster + el grafo de dbt + DataHub (#08) componen la trazabilidad
  obligatoria por la adenda (RNF9/RNF10) sin pegamento custom.
- **UI rica embebida** (`dagster dev` levanta una UI en `:3000` con
  timeline, logs, estado por partición). Cubre la observabilidad mínima
  del workflow sin que necesitemos Grafana adicional para este caso.
- **Retries declarativos por asset** con `RetryPolicy(max_retries, delay,
  backoff="EXPONENTIAL")` cumplen RF6 directamente.

### Por qué dlt

- **Cero servidor.** Es una librería; corre dentro del mismo proceso
  Dagster. No suma contenedores (Airbyte/OSS son ≈6) ni una segunda
  base interna.
- **Idempotencia gratis** con `write_disposition="replace"` para Bronze
  (snapshot full refresh — coincide con el ADR de tipo de carga, #05).
- **Schema evolution automático.** Si datos.gob.ar agrega una columna,
  dlt la propaga; si elimina una, marca el cambio en `_dlt_loads`. Para
  Bronze (raw) esto es exactamente lo que queremos.
- **Normalización automática** de JSON anidado a tablas relacionales sin
  escribir transformaciones manuales en la capa de extracción.
- **Integración oficial `dagster-dlt`** convierte cada `pipeline.run()`
  en un asset de Dagster, con particiones, checks y reintentos del
  orquestador aplicados sin código extra.
- **Apache 2.0**, Python puro, instalable con `uv add dlt[postgres]`.

### Por qué la combinación es coherente

`dagster-dlt` (mantenido por Dagster Labs) expone los recursos de dlt como
assets nativos. Esto significa que **una sola decisión de orquestación
gobierna ingesta, transformaciones y calidad**: los retries de Dagster
aplican a la extracción de dlt y a las transformaciones de dbt; las
particiones de mes de Dagster particionan el load de dlt y los modelos de
dbt; los asset checks de Dagster bloquean Gold cuando los tests de dbt o
las validaciones de calidad fallan. No hay un "orquestador del orquestador".

## Consecuencias

**Positivas:**

- El grafo de assets *es* el linaje del pipeline a nivel tabla.
- Reprocesar un rango de fechas es de primera clase
  ([#23](../backlog/issues-fase-2.md) lo formaliza como runbook).
- Retries con backoff exponencial declarativos por asset (RF6).
- Observabilidad básica cubierta por la UI de `dagster dev`.
- Stack 100% Python, instalable con `uv`.
- `dagster-dbt` y `dagster-dlt` reducen el código de pegamento a cero.
- Schema evolution de dlt protege Bronze de cambios en la fuente sin
  cortar el pipeline.

**Negativas / trade-offs asumidos:**

- Dagster es menos conocido que Airflow; ningún miembro del equipo lo usó
  en producción antes de Fase 2. Se mitigará con una jornada inicial de
  setup guiado (#10) y referenciando la documentación oficial.
- `dlt` es una librería relativamente nueva (1.0 GA en 2024); si su
  comportamiento de schema evolution introduce sorpresas, el plan B es
  reemplazar la ingesta por scripts custom dejando el resto del pipeline
  intacto (la dependencia es solo en los assets Bronze).
- La UI de Dagster es local — no hay una UI corporativa hosteada. Para
  la demo del 2026-06-15 esto es suficiente; si Fase 3 requiere acceso
  remoto, se evalúa con un nuevo ADR.

**Neutras:**

- La decisión es ortogonal a la herramienta de transformación (#04 elige
  dbt Core v2) — Dagster integra ambas via `dagster-dbt`.
- La decisión es ortogonal a la plataforma de gobierno (#08 elige
  DataHub) — DataHub puede ingerir metadatos de Dagster y de dbt.

## Pros y contras de cada opción

### Dagster 1.x (elegida)

- ✅ Modelo asset-centric, alineado con medallion sin esfuerzo.
- ✅ Particiones, asset checks y retries declarativos de primera clase.
- ✅ `dagster-dbt` y `dagster-dlt` oficiales.
- ✅ UI embebida cubre observabilidad mínima.
- ❌ Menos ubicuo en el mercado que Airflow; comunidad más chica.
- ❌ El equipo no tiene experiencia previa con Dagster.

### Apache Airflow 3.x

- ✅ Estándar de facto, ecosistema enorme de providers.
- ✅ Assets v2 (2025) cierra parte de la brecha con Dagster.
- ❌ Operator-centric: el grafo describe tareas, no datos. Para
  representar medallion hay que mapear assets a tareas con convenciones.
- ❌ Stack más pesado (scheduler + executor + metastore + worker)
  que no se justifica para 3 EC2 chicas y un pipeline de mensual.
- ❌ Integración con dbt y dlt existe pero requiere más boilerplate
  que en Dagster.

### Prefect 3.x

- ✅ Muy ergonómico para Python (`@flow`/`@task`).
- ✅ Curva de aprendizaje más baja para principiantes que Airflow.
- ❌ Menos opinionado sobre lineage; representar medallion requiere
  convenciones manuales.
- ❌ Las features que serían más útiles para Fase 2 (UI rica,
  scheduling avanzado) están sobrerrepresentadas en el tier Cloud.
- ❌ No hay integración oficial `prefect-dlt` ni `prefect-dbt` al
  nivel de las de Dagster.

### dlt (elegida)

- ✅ Cero servidor; corre dentro de Dagster.
- ✅ Schema evolution e idempotencia gratis por configuración.
- ✅ Integración oficial `dagster-dlt`.
- ✅ Python puro, Apache 2.0.
- ❌ Librería joven; menos battle-tested que Airbyte.
- ❌ Comunidad de conectores prebuilt más chica.

### Airbyte OSS

- ✅ Cientos de conectores prebuilt.
- ✅ UI para gestionar conexiones.
- ❌ ~6 contenedores adicionales (incluye una BD interna);
  desproporcionado para 2 fuentes HTTP simples.
- ❌ Requiere operar su propio stack en paralelo a Dagster.

### Meltano

- ✅ Reutiliza el ecosistema Singer (taps + targets).
- ✅ Configuración en YAML, sin código Python para casos simples.
- ❌ El ecosistema Singer tiene calidad heterogénea entre conectores.
- ❌ Otra herramienta de orquestación implícita (Meltano scheduler) que
  compite con Dagster por el control del pipeline.

### Scripts custom en Python

- ✅ Cero dependencias nuevas.
- ✅ Control absoluto.
- ❌ Reimplementar paginación, schema evolution, normalización,
  idempotencia y retries es trabajo que dlt nos da gratis.
- ❌ Cada bug en estos scripts es deuda del equipo; con dlt es deuda
  upstream.

## Referencias

- [Dagster — Software-defined assets](https://docs.dagster.io/concepts/assets/software-defined-assets)
- [Dagster — Partitions](https://docs.dagster.io/concepts/partitions-schedules-sensors/partitions)
- [Dagster — Retries](https://docs.dagster.io/concepts/ops-jobs-graphs/op-retries)
- [Dagster — `dagster-dbt`](https://docs.dagster.io/integrations/dbt)
- [Dagster — `dagster-dlt`](https://docs.dagster.io/integrations/embedded-elt/dlt)
- [dlt (dlthub) — documentation](https://dlthub.com/docs/intro)
- [Airflow 3.0 release notes (2025)](https://airflow.apache.org/blog/airflow-3-0/)
- [Prefect 3 documentation](https://docs.prefect.io/3.0/)
- Adenda técnica Fase 2 — RF5 (DAGs-as-code), RF6 (idempotencia +
  retries + observabilidad), RF7 (reprocesamiento), RNF8 (idempotencia).
- [ADR-0012](0012-stack-backend-python-fastapi-uv.md) — stack Python.
- [ADR-0010](0010-plataforma-hosting.md) — hosting EC2.
- ADR de medallion (#04, en redacción) — transformaciones con dbt Core v2.
- ADR de tipo de carga (#05, en redacción) — estrategia full/incremental por capa.
- ADR de gobierno (#08, en redacción) — DataHub para catálogo y linaje.
