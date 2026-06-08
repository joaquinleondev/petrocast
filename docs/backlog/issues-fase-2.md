# Backlog de Fase 2 — Issues

- **Objetivo:** conjunto **completo, ordenado e incremental** de issues para
  resolver la [Adenda Técnica de Fase 2](../assignment/adenda-fase-2.md) con
  cobertura total de los requisitos (apuntado a nota máxima).
- **Fecha de entrega:** 15 de junio de 2026.
- **Origen:** consolida la **devolución de Fase 1** y las **decisiones de stack**
  del equipo (extraídas del `addendum-v0.3.md`, que se da de baja). Respecto de
  esa primera versión se incorporó: adopción de **`dlt`** para la capa de
  ingesta, **dbt Core v2 (motor Fusion)** para transformaciones, y cuatro
  concerns transversales que faltaban (CI del pipeline, secretos, despliegue y
  lint de SQL). **DataHub** se mantiene como plataforma de gobierno.

## Cómo leer este backlog

- Cada issue indica **Owner**, **tipo de commit** (ADR-0005), **labels**,
  **dependencias** (`Depende de`), decisión/contexto y criterios de aceptación.
- Idioma español en issues/docs (ADR-0002); código, ramas y commits en inglés.
- Los issues están **ordenados por milestone** y diseñados para **no pisarse**:
  cada integrante es dueño de una vertical coherente (archivos distintos).
- Recordatorio de la adenda: *un ADR que no compare alternativas es inválido*.
  Cada ADR de este backlog exige esa comparación en sus criterios.

## Stack final de Fase 2

| Capa | Herramienta | Nota 2026 |
| ---- | ----------- | --------- |
| Orquestación | Dagster 1.x | Asset-centric; mejor fit con medallion |
| Ingesta (EL) | **dlt (dlthub)** | Integración oficial con Dagster; estándar de ingesta |
| Transformación | **dbt Core v2 (Fusion)** | Runtime Rust, Apache 2.0 (jun-2026) |
| Data warehouse | PostgreSQL 16 | Schemas `bronze` / `silver` / `gold` |
| Modelo | Star: `fact_production` + `dim_well` / `dim_company` / `dim_date` | SK hash, SCD Tipo 1 |
| BI | Metabase OSS | Puerto 3001 |
| Gobierno | DataHub | On-demand |
| Calidad | dbt tests + `store_failures` + asset checks de Dagster | Bloqueo + notificación |
| Linaje | dbt docs + Dagster + DataHub | Nivel tabla |
| Semantic layer (bonus) | Vistas SQL en `gold` | — |

## Orden de ejecución (milestones)

- **M0 — Devolución Fase 1** (arranca ya, independiente): #01, #02
- **M1 — Decisiones / ADRs** (arranca ya, en paralelo): #03–#09
- **M2 — Fundación del stack**: #10 → #11, #12, #13
- **M3 — Pipeline medallion** (incremental): #14 → #15 → #16
- **M4 — Calidad, consecuencia y linaje**: #17 → #18, #19
- **M5 — Plataformas y consumo**: #20, #21, #22
- **M6 — Reproceso**: #23
- **M7 — Documentación y runbooks**: #24, #25, #26, #27
- **M8 — Bonus y cierre**: #28, #29, #30

**Camino crítico:** `#10 → #14 → #15 → #16` y a partir de Gold se abren en
paralelo calidad (#17→#18), linaje (#19), plataformas (#20/#21), API (#22) y
backfill (#23). Mientras corre el camino crítico, los ADRs (#03–#09), la
devolución de Fase 1 (#01/#02) y la preparación de infra de plataformas
(compose de Metabase/DataHub) pueden avanzar sin bloqueo.

## Distribución por integrante (10 / 10 / 10)

Owners sugeridos por área coherente (intercambiables si el equipo prefiere).

### Santino Domato — Plataforma, Orquestación e Ingesta

`#02` · `#03` · `#05` · `#09` · `#10` · `#11` · `#12` · `#14` · `#23` · `#26`

### Ignacio Vargas — Modelado, Transformación y Calidad

`#04` · `#06` · `#07` · `#13` · `#15` · `#16` · `#17` · `#18` · `#25` · `#28`

### Joaquin Leon Alderete — Gobierno, BI, Consumo y Documentación

`#01` · `#08` · `#19` · `#20` · `#21` · `#22` · `#24` · `#27` · `#29` · `#30`

---

## M0 — Devolución de Fase 1

### 01 — OpenAPI: agregar `securitySchemes` al contrato

- **Owner:** Joaquin · **Tipo:** `fix(api)` · **Labels:** `fase-1-feedback`,
  `api`, `seguridad` · **Depende de:** —
- **Contexto:** devolución de Fase 1. El OpenAPI generado por FastAPI no declara
  `components.securitySchemes` ni el `security` por operación, pese a existir
  auth (`apps/api/src/core/security.py`, `tests/integration/api/v1/test_auth.py`).
- **Criterios de aceptación:**
  - [ ] Esquema(s) de seguridad en FastAPI (HTTP Bearer o API Key) visibles en
        `components.securitySchemes` del OpenAPI.
  - [ ] Endpoints protegidos declaran su `security`.
  - [ ] `tests/contract/test_openapi_contract.py` verifica `securitySchemes`.
  - [ ] Swagger UI (`/docs`) muestra **Authorize**.
- **Referencias:** ADR-0007, ADR-0016.

### 02 — Dashboard: agregar uso de CPU y configurar una alerta

- **Owner:** Santino · **Tipo:** `feat(monitoring)` · **Labels:**
  `fase-1-feedback`, `observabilidad`, `infra` · **Depende de:** —
- **Contexto:** devolución de Fase 1. El dashboard Grafana
  (`infra/monitoring/grafana/dashboards/petrocast.json`) no tiene panel de CPU
  ni alertas. ADR-0021 difirió node_exporter/cadvisor y Alertmanager.
- **Criterios de aceptación:**
  - [ ] Exponer CPU (node_exporter/cadvisor en `infra/compose.observability.yml`
        o CPU de proceso del API) y scrapearla en `prometheus.yml`.
  - [ ] Panel de **uso de CPU** en `petrocast.json`.
  - [ ] **Al menos una alerta** versionada como código (provisioning de Grafana
        alerting).
  - [ ] Todo se levanta con `docker compose -f infra/compose.observability.yml up`.
- **Referencias:** ADR-0021, ADR-0017.

---

## M1 — Decisiones (ADRs con comparación de alternativas)

### 03 — ADR: orquestación e ingesta (Dagster + dlt)

- **Owner:** Santino · **Tipo:** `docs(adr)` · **Labels:** `adr`, `pipeline`,
  `ingesta` · **Depende de:** —
- **Decisión a documentar:** **Dagster 1.x** como orquestador y **`dlt`** como
  herramienta de ingesta (EL), integrados vía `dagster-dlt`. Comparar Dagster vs
  Airflow 3.x vs Prefect, y dlt vs Airbyte/Meltano vs extracción a mano.
- **Criterios de aceptación:**
  - [ ] Comparación de alternativas para orquestador **y** para ingesta.
  - [ ] Justifica el modelo de assets (afinidad medallion) y `dagster-dlt`.
  - [ ] Cubre DAGs-as-code, idempotencia, retries con backoff y observabilidad.
- **Referencias:** adenda (ADR obligatorio de orquestación, RF5/RF6).

### 04 — ADR: arquitectura medallion y transformaciones (dbt Core v2)

- **Owner:** Ignacio · **Tipo:** `docs(adr)` · **Labels:** `adr`, `pipeline`,
  `dbt` · **Depende de:** —
- **Decisión a documentar:** tres capas (`bronze`/`silver`/`gold`) en PostgreSQL;
  transformaciones en **dbt Core v2 (motor Fusion)**. Comparar contra ETL ad-hoc
  y contra alternativas de transformación (p. ej. SQLMesh) y de versión de dbt
  (v2/Fusion vs línea 1.x).
- **Criterios de aceptación:**
  - [ ] Comparación de alternativas.
  - [ ] Fija dbt Core v2 y el rol de cada capa.
- **Referencias:** adenda (ADR obligatorio de capas medallion, RF2), ADR-0012.

### 05 — ADR: tipo de carga (full / incremental / upsert)

- **Owner:** Santino · **Tipo:** `docs(adr)` · **Labels:** `adr`, `pipeline` ·
  **Depende de:** —
- **Decisión a documentar:** estrategia diferenciada por capa — Bronze full
  refresh del snapshot; Silver idempotente por partición de mes; Gold upsert por
  clave de negocio (`INSERT ... ON CONFLICT`) con SK hash. Comparar full vs
  incremental append vs upsert vs CDC.
- **Criterios de aceptación:**
  - [ ] Comparación de alternativas (la adenda lo exige explícitamente).
  - [ ] Justifica full en Bronze por la naturaleza snapshot del CSV fuente.
- **Referencias:** adenda (ADR obligatorio de tipo de carga, RF8).

### 06 — ADR: modelo dimensional (star schema)

- **Owner:** Ignacio · **Tipo:** `docs(adr)` · **Labels:** `adr`,
  `modelo-datos` · **Depende de:** —
- **Decisión a documentar:** star schema `fact_production` + `dim_well`,
  `dim_company`, `dim_date`; surrogate keys hash determinístico
  (`dbt_utils.generate_surrogate_key`); SCD Tipo 1. Comparar star vs snowflake,
  operadora como atributo vs `dim_company` propia, SK hash vs autoincremental,
  SCD1 vs SCD2.
- **Criterios de aceptación:**
  - [ ] Comparación de alternativas.
  - [ ] Documenta grano de la fact, dimensiones, surrogate keys y decisión SCD.
- **Referencias:** adenda (ADR obligatorio de modelo dimensional, RNF6/RNF11).

### 07 — ADR: calidad de datos y consecuencia operativa

- **Owner:** Ignacio · **Tipo:** `docs(adr)` · **Labels:** `adr`, `calidad` ·
  **Depende de:** —
- **Decisión a documentar:** 5 dimensiones (schema, completitud, unicidad,
  validez de rangos, frescura) con dbt tests y `store_failures = true`;
  consecuencia = **bloqueo de promoción** vía asset checks de Dagster +
  notificación. Comparar contra "marca visible" y "solo alerta".
- **Criterios de aceptación:**
  - [ ] Comparación de alternativas para dimensiones y consecuencia.
  - [ ] Justifica el bloqueo para proteger a usuarios no técnicos.
- **Referencias:** adenda (ADR obligatorio de calidad, RNF4/RNF5).

### 08 — ADR: gobierno de datos y linaje (DataHub)

- **Owner:** Joaquin · **Tipo:** `docs(adr)` · **Labels:** `adr`, `gobierno` ·
  **Depende de:** —
- **Decisión a documentar:** **DataHub** (herramienta nombrada por la adenda),
  on-demand; linaje por Dagster (flujo) + dbt (SQL) + DataHub (catálogo). Comparar
  DataHub vs OpenMetadata vs Atlas vs Marquez vs dbt docs.
- **Criterios de aceptación:**
  - [ ] Comparación de alternativas.
  - [ ] Documenta el trade-off de footprint (≈6 contenedores, ≈4 GB → on-demand).
  - [ ] Cubre navegación de lineage **a nivel tabla**.
- **Referencias:** adenda (ADR obligatorio de gobierno, RNF9/RNF10).

### 09 — ADR: topología de despliegue de Fase 2

- **Owner:** Santino · **Tipo:** `docs(adr)` · **Labels:** `adr`, `infra` ·
  **Depende de:** —
- **Contexto (gap):** definir dónde corre el stack de datos. DataHub no entra
  cómodo en la `t3.small` junto al resto. Comparar demo local con Compose vs EC2
  permanente vs híbrido (servicios base permanentes + DataHub on-demand).
- **Criterios de aceptación:**
  - [ ] Comparación de alternativas de despliegue.
  - [ ] Define cómo accede el Admin a la web de métricas (caso de uso de la adenda).
- **Referencias:** ADR-0010, ADR-0017; adenda (caso de uso Admin).

---

## M2 — Fundación del stack

### 10 — Scaffold del stack de datos

- **Owner:** Santino · **Tipo:** `feat(data)` · **Labels:** `pipeline`,
  `infra` · **Depende de:** #03, #04
- **Contexto:** esqueleto que habilita todo el pipeline. Es el principal
  desbloqueante del camino crítico.
- **Criterios de aceptación:**
  - [ ] PostgreSQL del DW con schemas `bronze`, `silver`, `gold`.
  - [ ] Proyecto Dagster corriendo con `dagster dev` (UI :3000).
  - [ ] Proyecto **dbt Core v2** integrado vía `dagster-dbt`.
  - [ ] **`dlt`** instalado e integrado vía `dagster-dlt` (asset de prueba ok).
  - [ ] `infra/compose.data.yml` levanta el stack con un comando.
- **Referencias:** addendum P1; ADR-0012; #03, #04.

### 11 — Gestión de secretos y configuración

- **Owner:** Santino · **Tipo:** `feat(data)` · **Labels:** `infra`,
  `seguridad` · **Depende de:** #10
- **Contexto (gap):** credenciales del DW, URLs de fuentes y webhook de
  notificación no deben vivir en el código.
- **Criterios de aceptación:**
  - [ ] Configuración vía variables de entorno / Pydantic Settings (alineado con
        ADR-0018) y `.env.example` documentado.
  - [ ] Secretos fuera del repo; Dagster/dlt/dbt los leen del entorno.
- **Referencias:** ADR-0018; usado por #14, #18, #21.

### 12 — CI del pipeline de datos en PRs

- **Owner:** Santino · **Tipo:** `ci` · **Labels:** `ci`, `pipeline` ·
  **Depende de:** #10
- **Contexto (gap):** requisito explícito de la adenda — los devs DEBEN recibir
  feedback sobre los tests en los PRs. Arranca apenas exista el proyecto dbt y se
  amplía a medida que se agregan modelos.
- **Criterios de aceptación:**
  - [ ] Workflow que en cada PR corre `dbt build`/tests sobre una DB efímera.
  - [ ] Valida los **asset checks** de Dagster y el código de ingesta (`dlt`).
  - [ ] El resultado aparece como check de estado del PR.
- **Referencias:** adenda (caso de uso Dev); ADR-0005; integra #13.

### 13 — Lint de SQL con sqlfluff

- **Owner:** Ignacio · **Tipo:** `chore` · **Labels:** `ci`, `dbt` ·
  **Depende de:** #10
- **Contexto (gap):** igualar la disciplina ruff/mypy de ADR-0015 en los modelos
  dbt.
- **Criterios de aceptación:**
  - [ ] `sqlfluff` configurado para el dialecto de PostgreSQL y dbt.
  - [ ] Hook en `.pre-commit-config.yaml` y en CI (#12).
- **Referencias:** ADR-0015.

---

## M3 — Pipeline medallion (incremental)

### 14 — Ingesta Bronze con `dlt` (dos fuentes de datos.gob.ar)

- **Owner:** Santino · **Tipo:** `feat(data)` · **Labels:** `ingesta`,
  `pipeline` · **Depende de:** #10, #11
- **Contexto:** las dos fuentes de la adenda: producción de pozos no
  convencionales y listado de pozos (complementaria).
- **Criterios de aceptación:**
  - [ ] Pipelines `dlt` que cargan ambas fuentes a `bronze` con **full refresh**,
        orquestados como assets de Dagster (`dagster-dlt`).
  - [ ] Assets **particionados por mes**; rematerializar una partición es
        idempotente.
  - [ ] `RetryPolicy` con **backoff exponencial**.
  - [ ] Logs y status accesibles en la UI de Dagster (observabilidad mínima).
- **Referencias:** adenda RF1, RF5, RF6, RNF8; #03, #05.

### 15 — Transformación Silver (dbt, idempotente por partición)

- **Owner:** Ignacio · **Tipo:** `feat(data)` · **Labels:** `dbt`,
  `pipeline` · **Depende de:** #14
- **Criterios de aceptación:**
  - [ ] Modelos dbt Bronze → Silver (tipado, normalización, nombres en inglés).
  - [ ] Cada partición de mes elimina y reinserta su rango (re-run → mismo
        resultado).
  - [ ] Habilita backfill por rango de particiones.
- **Referencias:** adenda RF2, RNF7, RNF8; #04, #05.

### 16 — Modelo Gold star schema (dbt, upsert + SK hash + SCD1)

- **Owner:** Ignacio · **Tipo:** `feat(data)` · **Labels:** `dbt`,
  `modelo-datos` · **Depende de:** #15
- **Criterios de aceptación:**
  - [ ] `fact_production` + `dim_well`, `dim_company`, `dim_date`.
  - [ ] Surrogate keys hash (`dbt_utils.generate_surrogate_key`).
  - [ ] Carga por **upsert** (`ON CONFLICT ... DO UPDATE`); SCD Tipo 1 en dims.
  - [ ] Reproceso de un período no duplica registros.
- **Referencias:** adenda RNF6; #06.

---

## M4 — Calidad, consecuencia y linaje

### 17 — Chequeos de calidad (5 dimensiones, persistidos)

- **Owner:** Ignacio · **Tipo:** `feat(data)` · **Labels:** `calidad`,
  `dbt` · **Depende de:** #15
- **Criterios de aceptación:**
  - [ ] dbt tests: schema, completitud (`not_null` > umbral), unicidad
        (`well_id, date`), validez de rangos (`oil_prod_m3 >= 0`,
        `gas_prod_mm3 >= 0`, rango de fechas) y frescura (mes M-1 para activos).
  - [ ] `store_failures = true`: filas fallidas persistidas en `dbt_test__audit`.
  - [ ] Checks en la transición Bronze → Silver.
- **Referencias:** adenda RNF4; #07.

### 18 — Consecuencia operativa: bloqueo + notificación

- **Owner:** Ignacio · **Tipo:** `feat(data)` · **Labels:** `calidad`,
  `pipeline` · **Depende de:** #17
- **Criterios de aceptación:**
  - [ ] dbt tests envueltos en **asset checks bloqueantes** de Dagster: si
        fallan, Gold no se materializa.
  - [ ] Estado visible en la UI de Dagster.
  - [ ] **Sensor** de Dagster que dispara notificación (Slack/email).
  - [ ] Metabase conserva el último Gold válido cuando hay bloqueo.
- **Referencias:** adenda RNF5; #07, #11.

### 19 — Linaje de datos navegable

- **Owner:** Joaquin · **Tipo:** `feat(data)` · **Labels:** `gobierno`,
  `linaje` · **Depende de:** #16
- **Criterios de aceptación:**
  - [ ] `dbt docs generate` produce el grafo Bronze → Silver → Gold.
  - [ ] El grafo de assets de Dagster (ingesta + dbt) es navegable.
  - [ ] Artefactos de linaje listos para importar a DataHub (#21).
- **Referencias:** adenda RNF9; #08.

---

## M5 — Plataformas y consumo

### 20 — BI: Metabase OSS (deploy + dashboards)

- **Owner:** Joaquin · **Tipo:** `feat(bi)` · **Labels:** `bi`, `infra` ·
  **Depende de:** #16
- **Criterios de aceptación:**
  - [ ] Metabase en **puerto 3001** (evita colisión con Grafana), conectado a
        `gold`.
  - [ ] Dashboards para no técnicos: producción por pozo/mes, evolución histórica
        y top pozos por volumen, con filtros (pozo, fecha, tipo de fluido).
- **Referencias:** adenda RF3; #08.

### 21 — Gobierno: DataHub (on-demand + ingesta)

- **Owner:** Joaquin · **Tipo:** `feat(gobierno)` · **Labels:** `gobierno`,
  `infra` · **Depende de:** #16, #19
- **Criterios de aceptación:**
  - [ ] DataHub levantable vía Compose **on-demand**.
  - [ ] Ingesta del catálogo de PostgreSQL y del linaje de dbt.
  - [ ] Expone workflows/ingestas, tablas del DW y **última actualización**
        (timestamp + row count).
  - [ ] Navegación de lineage **a nivel tabla**.
- **Referencias:** adenda RF4, RNF10; #08, #19.

### 22 — Conectar la API al esquema `gold`

- **Owner:** Joaquin · **Tipo:** `feat(api)` · **Labels:** `api`,
  `pipeline` · **Depende de:** #16
- **Contexto:** continuación de ADR-0020: el repository layer pasa de mocks a
  leer del DW.
- **Criterios de aceptación:**
  - [ ] `forecast_repository.py` y `well_repository.py` leen del schema `gold`.
  - [ ] Los tests de contrato siguen pasando (el contrato OpenAPI no cambia).
- **Referencias:** adenda (caso de uso API); ADR-0020.

---

## M6 — Reproceso

### 23 — Procedimiento de backfill documentado y verificable

- **Owner:** Santino · **Tipo:** `docs(data)` · **Labels:** `pipeline`,
  `runbook` · **Depende de:** #16, #18
- **Criterios de aceptación:**
  - [ ] Procedimiento para rematerializar un rango de particiones de mes en
        Dagster (UI y CLI `--partition-range`), reprocesando **desde Bronze**.
  - [ ] Pasos de validación (asset checks en verde, Gold actualizado).
  - [ ] Verificable de punta a punta; se enlaza desde el runbook DE (#26).
- **Referencias:** adenda RF7, RNF7.

---

## M7 — Documentación y runbooks

### 24 — README de Fase 2

- **Owner:** Joaquin · **Tipo:** `docs` · **Labels:** `docs` · **Depende de:**
  #20, #21
- **Criterios de aceptación:**
  - [ ] Instrucciones para actualizar/correr los workflows.
  - [ ] Instrucciones de acceso al BI (Metabase) y al gobierno (DataHub).
  - [ ] Descripción de la arquitectura de datos.
- **Referencias:** adenda RNF1, RNF2.

### 25 — Documentación del modelo de datos

- **Owner:** Ignacio · **Tipo:** `docs` · **Labels:** `docs`,
  `modelo-datos` · **Depende de:** #06, #16
- **Criterios de aceptación:**
  - [ ] Grano de la fact table, dimensiones, surrogate keys y decisión de SCD.
  - [ ] Diagrama del star schema.
- **Referencias:** adenda RNF3, RNF11.

### 26 — Runbook: Data Engineer (reprocesamiento / backfill)

- **Owner:** Santino · **Tipo:** `docs(runbook)` · **Labels:** `runbook`,
  `docs` · **Depende de:** #23
- **Criterios de aceptación:**
  - [ ] `docs/runbooks/data-engineer.md` con: propósito y disparador, rol/dueño y
        prerrequisitos, pasos numerados, validación, plan B/escalamiento y
        consideraciones no funcionales.
  - [ ] Justifica **una decisión funcional** y **una no funcional** desde los
        incentivos del rol (p. ej. reprocesar desde Bronze; correr fuera de
        horario para no contender con Metabase).
- **Referencias:** adenda (runbooks; rol de implementación).

### 27 — Runbook: Data Owner (incidente de calidad)

- **Owner:** Joaquin · **Tipo:** `docs(runbook)` · **Labels:** `runbook`,
  `docs` · **Depende de:** #18, #21
- **Criterios de aceptación:**
  - [ ] `docs/runbooks/data-owner.md` con las seis secciones requeridas, sobre la
        decisión de **aptitud del dato** ante un bloqueo de calidad.
  - [ ] Usa las filas fallidas (`store_failures`) y el linaje de DataHub para el
        análisis de impacto.
  - [ ] Justifica **una decisión funcional** (umbral de aptitud para uso) y **una
        no funcional** (SLA de resolución) desde los incentivos del rol.
- **Referencias:** adenda (runbooks; rol de negocio); #18, #21.

---

## M8 — Bonus y cierre

### 28 — (Bonus) Semantic layer liviano: vistas SQL en `gold`

- **Owner:** Ignacio · **Tipo:** `feat(data)` · **Labels:** `bonus`, `bi` ·
  **Depende de:** #16, #20
- **Decisión:** sin dbt Semantic Layer formal; vistas SQL que centralizan
  métricas (`gold.v_monthly_production_by_well`, `gold.v_top_wells_by_volume`).
- **Criterios de aceptación:**
  - [ ] Vistas creadas en `gold` y consumibles desde Metabase.
- **Nota:** bonus; no comprometer los obligatorios.
- **Referencias:** adenda RF9.

### 29 — (Recomendado) ADR: plataforma de BI (Metabase)

- **Owner:** Joaquin · **Tipo:** `docs(adr)` · **Labels:** `adr`, `bi` ·
  **Depende de:** —
- **Decisión a documentar:** Metabase OSS; convive con Grafana (operativo).
  Comparar Metabase vs Superset vs Redash vs Grafana.
- **Nota:** no es ADR obligatorio según la adenda, pero refuerza la defensa oral.
- **Referencias:** addendum P2.

### 30 — Verificación E2E + guion de demo de Fase 2

- **Owner:** Joaquin · **Tipo:** `docs` · **Labels:** `demo`, `docs` ·
  **Depende de:** #16, #18, #20, #21, #22, #23
- **Contexto:** asegurar una demo fluida (factor decisivo de nota).
- **Criterios de aceptación:**
  - [ ] Corrida E2E: ingesta → medallion → calidad → Gold → Metabase/DataHub →
        API.
  - [ ] Prueba del backfill y de un bloqueo de calidad (camino de falla).
  - [ ] `docs/demo/fase-2/guion.md` con el recorrido de la demo.
- **Referencias:** todas las anteriores.

---

## Matriz de cobertura (adenda → issues)

Demuestra que el backlog cubre el 100% de la adenda.

| Requisito de la adenda | Issues |
| ---------------------- | ------ |
| Caso de uso Dev (feedback de tests en PRs) | #12 |
| Caso de uso API (REST) | #22 |
| Caso de uso Admin (web de métricas) | #02, #09 |
| RF1 — Extracción de las 2 fuentes | #14 |
| RF2 — Arquitectura medallion | #14, #15, #16 |
| RF3 — BI para no técnicos | #20 |
| RF4 — Gobierno (workflows, datos DW, última actualización) | #21 |
| RF5 — Orquestación DAGs-as-code | #03, #10, #14 |
| RF6 — Idempotencia + retries backoff + observabilidad | #14 |
| RF7 — Backfill documentado y verificable | #23, #26 |
| RF8 — ADR de tipo de carga | #05 |
| RF9 — Semantic layer (bonus) | #28 |
| RNF1/RNF2 — README (workflows, BI/gobierno, arquitectura) | #24 |
| RNF3/RNF11 — Doc del modelo de datos (grano, dims, SK, SCD) | #25 |
| RNF4 — Calidad ≥ 3 dimensiones persistidas | #17 |
| RNF5 — Persistencia + consecuencia operativa | #17, #18 |
| RNF6 — DW modelo estrella | #16 |
| RNF7 — Reproceso por fecha | #15, #23 |
| RNF8 — Procesamiento idempotente | #14, #15, #16 |
| RNF9 — Funcionalidad de linaje | #19 |
| RNF10 — Gobierno con DataHub + lineage a nivel tabla | #21 |
| Roles + runbooks (negocio + implementación) | #26, #27 |
| ADRs obligatorios (orquestación, medallion, carga, dimensional, calidad, gobierno) | #03, #04, #05, #06, #07, #08 |
| Calidad de entrega para nota máxima (despliegue, CI, secretos, lint, BI ADR, demo) | #09, #11, #12, #13, #29, #30 |

## Trazabilidad: addendum → issues

| Decisión del equipo (addendum) | Issues |
| ------------------------------ | ------ |
| P1 — Orquestación: Dagster (+ dlt, dbt Core v2) | #03, #10, #14 |
| P2 — BI: Metabase OSS | #20, #29 |
| P3 — Gobierno: DataHub | #08, #21 |
| P4 — Linaje: Dagster + dbt + DataHub | #08, #19 |
| P5 — Tipo de carga por capa | #05, #14, #15, #16 |
| P6 — Calidad: 5 dimensiones + `store_failures` | #07, #17 |
| P7 — Consecuencia: bloqueo + notificación | #07, #18 |
| P8 — Runbooks: Data Engineer + Data Owner | #23, #26, #27 |
| P9 — Semantic layer (bonus): vistas SQL | #28 |
| Modelo dimensional (síntesis) | #06, #16, #25 |
| Conexión con Fase 1 (API → gold) | #22 |
