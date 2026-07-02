# ADR-0031: Estrategia de feature store

- **Estado:** Propuesto
- **Fecha:** 2026-07-02
- **Autores:** Ignacio Vargas Fernandez
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda de Fase 3 impone un requerimiento no funcional explícito: *el
procesamiento y generación de features debe quedar persistido en un feature
store utilizado durante la inferencia*. Es decir, las features no pueden
calcularse in-memory al vuelo — ni en training ni en serving — sino leerse de
un almacenamiento compartido por ambos caminos.

Este ADR decide **dónde y cómo persisten esas features**. Las restricciones
vienen dadas por decisiones ya tomadas:

- **Qué se computa** está fijado por ADR-0030: features de lags, rolling
  windows y tendencia sobre la producción mensual (`gold.fact_production`,
  m³), más atributos estáticos del pozo (`gold.dim_well`), a grano
  `well_id = idpozo` (texto).
- **Quién las consume:** el training (#13) las lee en batch para un
  `as_of_date` dado; la inferencia embebida en la API (ADR-0034, #18) las lee
  por `(well_id, as_of_date)` al responder una predicción. El grano es
  **mensual** y el serving es una consulta puntual — no hay requerimiento de
  latencia de milisegundos ni de streaming.
- **Con qué stack:** el warehouse es PostgreSQL 16 con arquitectura medallion
  operada por dbt (ADR-0023), modelo dimensional en `gold` (ADR-0024),
  orquestación Dagster con particiones mensuales (ADR-0028) y tests de
  calidad dbt con `store_failures` (ADR-0025).

El riesgo central que un feature store debe eliminar es doble:

1. **Leakage temporal:** una feature calculada para entrenar con corte en
   `as_of_date` no puede mirar datos posteriores a esa fecha (regla
   *point-in-time*, PIT). Con DDJJ rectificativas que reescriben meses
   pasados (ADR-0026), la disciplina PIT debe ser explícita.
2. **Training-serving skew:** si training e inferencia computan las features
   por caminos distintos (SQL en un lado, pandas en el otro), cualquier
   divergencia se convierte en error silencioso de predicción.

## Drivers de la decisión

- **Cumplir el RNF de la adenda:** features persistidas y usadas en
  inferencia; nada crítico calculado solo in-memory.
- **Eliminar el skew por construcción:** un único artefacto leído por
  training e inferencia, no dos implementaciones a sincronizar.
- **PIT verificable:** la regla "ninguna fila usa datos > `as_of_date`" debe
  poder testearse automáticamente (#11).
- **Cero infra nueva:** el equipo ya opera Postgres + dbt + Dagster; cada
  servicio adicional compite por las mismas 3 personas y el mismo
  presupuesto de cómputo (ADR-0027 acaba de *reducir* staging a t3.small).
- **Batch mensual, no online:** el grano es pozo-mes y la API responde
  consultas puntuales; no existe caso de uso de serving de baja latencia ni
  de features en tiempo real.
- **Reuso del patrón de calidad:** tests de unicidad/not-null y lineage
  (DataHub, dbt docs) ya funcionan sobre modelos dbt; las features deberían
  heredarlos gratis.
- **Trazabilidad:** cada run de training registra qué corte de features usó
  (`as_of_date` + metadata, ADR-0032); el store debe hacer ese vínculo
  trivial.

## Opciones consideradas

1. **Tablas propias en PostgreSQL generadas por dbt** (schema `features`,
   clave `(well_id, as_of_date)`, PIT por construcción).
2. **Feast** (feature store OSS dedicado, con registry, offline/online
   stores y SDK propio).
3. **DuckDB / archivos Parquet** (features materializadas a archivos
   columnar en disco o S3).
4. **Cálculo on-demand sin store** (training e inferencia computan features
   al vuelo desde `gold`).

## Decisión

Elegimos la **opción 1: tablas en un schema `features` de PostgreSQL,
generadas por dbt**, como feature store offline unificado. Especificación:

### Esquema y claves

- **Schema `features`** en el mismo Postgres del warehouse, creado por un
  init script `infra/data/postgres/init/004-create-features-schema.sql`
  (mismo patrón que `001-create-medallion-schemas.sql`). Queda separado de
  `gold`: `gold` es la capa de consumo BI/API con semántica dimensional;
  `features` es un contrato de ML con reglas propias (PIT, versionado por
  corte).
- **Modelos dbt** en `apps/data/dbt/models/features/` (sources sobre `gold`,
  `schema.yml` con tests y documentación por columna). El detalle de tablas
  y columnas se congela como **contrato A** en #09.
- **Clave primaria lógica: `(well_id, as_of_date)`**, con test dbt de
  unicidad. `well_id` es el de `gold.fact_production` (= `idpozo` en texto,
  ADR-0030). `as_of_date` es la **fecha de corte de conocimiento**: la fila
  contiene lo que se sabía del pozo a esa fecha.
- **El horizonte NO es parte de la clave.** Con la estrategia multi-step
  directa de ADR-0030 (un modelo global con `horizon` como input), el mismo
  vector de features sirve a todos los horizontes 1–12; incluirlo
  multiplicaría ×12 las filas sin información nueva. Si un futuro modelo
  necesitara features dependientes del horizonte, se agrega como columna de
  clave en una tabla nueva sin romper el contrato A.
- **Unidades en m³**, heredadas de silver/gold (A4 de
  `supuestos-y-clarificaciones.md`).

### Point-in-time correctness

- Cada modelo dbt de features acepta el corte como **partición**: computa
  lags/rolling/tendencia usando exclusivamente `production_month <
  as_of_date`. La regla queda **testeada** (#11): un test dbt/pytest
  verifica que ninguna feature de una fila con corte `d` cambia si se
  eliminan los datos posteriores a `d`.
- Las **DDJJ rectificativas** (ADR-0026) reescriben la historia en
  bronze/silver/gold; las filas de `features` ya materializadas para un
  `as_of_date` pasado **no se recalculan retroactivamente por defecto**: son
  la foto de lo conocido a ese corte, que es exactamente lo que un backtest
  honesto necesita. Un backfill explícito (re-materializar la partición vía
  Dagster, #12) queda disponible si se decide que una rectificación amerita
  rehacer un corte.

### Materialización y versionado

- **Dagster materializa** las particiones por `as_of_date` (asset de #12,
  reusando el patrón de particiones mensuales de Fase 2), con metadata de
  filas, rango de fechas y hash de configuración.
- **Versionado en dos ejes:**
  - *De los datos:* el `as_of_date` de la clave — cada corte es inmutable
    una vez materializado (salvo backfill explícito).
  - *De la definición:* el SQL de las features vive en dbt bajo git; un
    cambio de definición es un PR que altera `models/features/*.sql`, y los
    runs de MLflow registran el commit/imagen con que se materializó
    (ADR-0032). No se mantienen N versiones de definición conviviendo en el
    store: si la definición cambia de forma incompatible, se re-materializan
    los cortes necesarios y el registry vincula cada modelo a su corte.

### Cómo se evita el training-serving skew

- **Una sola escritura, dos lecturas.** Las features se computan **una vez**
  (dbt → tablas `features`) y tanto el training (#13) como el runtime de
  inferencia (#18, vía `feature_repository` en la API) **leen la misma
  tabla, por la misma clave `(well_id, as_of_date)`**. No existe un segundo
  camino de cómputo que pueda divergir: la inferencia no recalcula features
  in-memory (RNF de la adenda), y el training no arma datasets ad-hoc por
  fuera del store.
- La **signature del modelo** registrada en MLflow (contrato B, #16) fija el
  vector de features esperado = columnas del contrato A, con lo cual un
  drift de schema entre store y modelo falla ruidosamente al cargar, no en
  silencio.

## Consecuencias

**Positivas:**

- RNF de la adenda cumplido con **cero infraestructura nueva**: el feature
  store es Postgres + dbt + Dagster que ya operamos.
- Skew eliminado por construcción (misma tabla en train e inferencia) y PIT
  testeable automáticamente.
- Las features heredan gratis el stack de calidad y gobierno de Fase 2:
  tests dbt (`unique`, `not_null`, `store_failures`), lineage Gold →
  features en dbt docs/DataHub, y particiones/retries de Dagster.
- Backtesting honesto: los cortes históricos inmutables reproducen lo que
  se sabía en cada fecha.
- Documentación por columna en `schema.yml` — el contrato A es legible por
  cualquiera del equipo.

**Negativas / trade-offs asumidos:**

- **Sin online store:** una predicción para un pozo requiere que su
  partición de features esté materializada; un `as_of_date` no materializado
  responde error claro (#18) o dispara materialización. Aceptable: grano
  mensual, la materialización corre en el job de retrain (#19).
- **Sin registry de features dedicado** (catálogo, TTLs, owners por
  feature): se cubre con `schema.yml` + DataHub, suficiente para ~decenas de
  features y 3 personas.
- Postgres single-node limita el volumen; con ~48k filas-mes en
  `fact_production` hoy, el margen es de órdenes de magnitud.
- Filas de cortes mensuales acumulan storage (una foto por pozo por corte).
  Mitigable con retención/pruning de cortes viejos si llegara a doler.

**Neutras:**

- La decisión es ortogonal al tracking (ADR-0032): MLflow guarda *qué*
  corte usó cada run, no las features.
- Si en una fase futura apareciera serving online de baja latencia (grano
  diario/horario, SLA de ms), migrar a Feast puede **reusar estas mismas
  tablas como offline store** — la inversión en dbt no se tira.

## Pros y contras de cada opción

### Tablas PostgreSQL generadas por dbt (elegida)

- ✅ Cero infra nueva; reusa Postgres, dbt, Dagster y el stack de calidad.
- ✅ Misma tabla leída en train e inferencia ⇒ sin skew por construcción.
- ✅ PIT explícito y testeable; cortes inmutables para backtesting.
- ✅ Lineage y documentación gratis (dbt docs, DataHub, `schema.yml`).
- ❌ Sin online layer ni registry de features dedicado.
- ❌ Escala limitada a lo que aguante Postgres single-node (holgado hoy).

### Feast

- ✅ Feature store "de verdad": registry, offline/online stores, SDK de
  retrieval PIT ya resuelto.
- ✅ Estándar OSS conocido; buen camino si hubiera serving online.
- ❌ **Overkill sin caso de uso online:** nuestro serving es una consulta
  puntual sobre grano mensual; el online store (Redis/DynamoDB) y el feature
  server quedarían ociosos.
- ❌ Ops nuevas: registry, sync offline→online, SDK y conceptos propios
  (entities, feature views) para 3 personas y ~2 semanas — exactamente lo
  que "evita ops" desaconseja.
- ❌ Igual necesitaríamos dbt para transformar: Feast no computa features,
  solo las sirve — sumaría una capa sin quitar ninguna.

### DuckDB / Parquet

- ✅ Lectura columnar rapidísima para training batch; archivos versionables
  en S3.
- ❌ La API (ADR-0034) tendría que leer archivos en cada request o cachear —
  peor fit que un `SELECT` por PK en el Postgres ya conectado.
- ❌ Fuera del stack de calidad/lineage: sin tests dbt de unicidad, sin
  DataHub, sin rol read-only ya provisionado.
- ❌ Estado en archivos + estado en warehouse = dos fuentes de verdad que
  sincronizar.

### Cálculo on-demand sin store

- ✅ Sin storage extra ni materializaciones que orquestar; siempre "fresco".
- ❌ **Incumple el RNF de la adenda** (exige features persistidas usadas en
  inferencia) — descalificante por sí solo.
- ❌ Máximo riesgo de skew: training (SQL/pandas batch) e inferencia (query
  al vuelo) divergen con el primer refactor.
- ❌ PIT frágil: con DDJJ rectificativas, recomputar "lo que se sabía en
  marzo" desde un `gold` ya rectificado es imposible sin snapshots — que es
  justamente lo que el store materializa.
- ❌ Backtesting no reproducible (los datos de abajo cambian entre corridas).

## Referencias

- Adenda técnica Fase 3 — RNF: features persistidas en un feature store
  usado durante la inferencia.
- [Feast — Architecture](https://docs.feast.dev/getting-started/architecture) ·
  [Feast — Offline stores](https://docs.feast.dev/reference/offline-stores)
- [Kleppmann et al. — Hidden Technical Debt in ML Systems (NeurIPS 2015)](https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems)
  — training-serving skew.
- [dbt — Model contracts y tests](https://docs.getdbt.com/docs/collaborate/govern/model-contracts)
- `docs/supuestos-y-clarificaciones.md` — A4 (unidades m³).
- [ADR-0023](0023-arquitectura-medallion-dbt.md) — warehouse Postgres + dbt.
- [ADR-0024](0024-modelo-dimensional-star-schema.md) — grano de
  `gold.fact_production`.
- [ADR-0025](0025-calidad-datos-consecuencia.md) — tests y `store_failures`.
- [ADR-0026](0026-tipo-carga-medallion.md) — DDJJ rectificativas y upsert.
- [ADR-0028](0028-orquestacion-e-ingesta-dagster-dlt.md) — particiones
  Dagster.
- [ADR-0030](0030-objetivo-predictivo-horizonte-metricas.md) — target, grano
  `well_id`, horizonte.
- [ADR-0032](0032-tracking-experimentos-registry.md) — trazabilidad
  corte-de-features ↔ run.
- [ADR-0034](0034-serving-modelo-contrato-api.md) — lectura de features en
  inferencia.
- Backlog Fase 3 — [#02](../backlog/issues-fase-3.md) (este ADR), #09
  (contrato A), #11 (tests PIT), #12 (materialización), #18 (inferencia).
