# ADR-0024: Modelo dimensional del gold — star schema

- **Estado:** Aceptado
- **Fecha:** 2026-06-08
- **Autores:** Ignacio Vargas Fernández
- **Decisores:** Equipo Petrocast

## Contexto y problema

La capa `gold` de la arquitectura medallion (ADR-0023) es la que consumen
Metabase (dashboards) y la API. Debe estar modelada para análisis: consultas
por pozo, por operadora, por período y por tipo de fluido (petróleo, gas,
agua), entendibles por usuarios no técnicos a través del Query Builder de
Metabase.

Necesitamos fijar el **modelo dimensional**: la forma de las tablas de hechos
y dimensiones, el **grano** de la fact, qué dimensiones existen, cómo se
generan las **surrogate keys** y qué estrategia de **historización (SCD)** se
aplica a las dimensiones. Estas decisiones condicionan los modelos dbt del gold
(F2-16) y el desempeño y claridad de los dashboards.

El warehouse es PostgreSQL (ADR-0012) y el motor dbt Core v2 (ADR-0023), que
ofrece `dbt_utils.generate_surrogate_key` para SK hash determinísticas.

## Drivers de la decisión

- **Consumo por no técnicos.** El modelo debe ser navegable en Metabase sin
  SQL: pocas tablas, joins obvios, nombres claros.
- **Simplicidad de mantenimiento.** Equipo de 3, plazo acotado; menos objetos y
  menos lógica de historización reduce riesgo.
- **Idempotencia y reproceso.** Las SK deben ser estables entre corridas para
  que upsert/backfill no dupliquen ni rompan referencias (alinea con ADR-0023 y
  el tipo de carga de F2-05).
- **Necesidad real de historia.** Hay que evaluar si los atributos de las
  dimensiones (p. ej. operadora de un pozo) requieren versionado histórico
  (SCD2) o basta con el último valor (SCD1) para las preguntas de la demo.
- **Cardinalidad y reutilización.** Operadora aparece en muchos pozos; conviene
  evaluar si es atributo de `dim_well` o una dimensión propia `dim_company`.

## Opciones consideradas

### Forma del esquema

1. **Star schema** (fact central + dimensiones desnormalizadas).
2. **Snowflake schema** (dimensiones normalizadas en sub-tablas).

### Operadora

1. **`dim_company` como dimensión propia** (fact → dim_well y fact → dim_company,
   o dim_well → dim_company).
2. **Operadora como atributo dentro de `dim_well`.**

### Surrogate keys

1. **Hash determinístico** (`dbt_utils.generate_surrogate_key` sobre la clave de
   negocio).
2. **Autoincremental** (secuencia / identity de PostgreSQL).

### Historización de dimensiones

1. **SCD Tipo 1** (overwrite; sólo último valor).
2. **SCD Tipo 2** (versionado con `valid_from`/`valid_to` y flag de actual).

## Decisión

- **Forma:** **star schema**.
  - **`fact_production`** — tabla de hechos. **Grano: una fila por pozo y
    período (mes)**, con medidas de producción de petróleo, gas y agua del
    período. Claves foráneas a las dimensiones vía surrogate keys.
  - **Dimensiones:** `dim_well` (pozo y sus atributos), **`dim_company`**
    (operadora, dimensión propia), `dim_date` (calendario por mes).
- **Surrogate keys:** **hash determinístico** con
  `dbt_utils.generate_surrogate_key` sobre la clave de negocio de cada entidad
  (p. ej. identificador de pozo; operadora; fecha).
- **Historización:** **SCD Tipo 1** en las dimensiones (overwrite del último
  valor).

Elegimos star sobre snowflake porque Metabase y los usuarios no técnicos
navegan mejor pocas tablas desnormalizadas con joins directos; la normalización
de snowflake agrega joins sin beneficio para este volumen. Elegimos
`dim_company` propia porque la operadora se repite en muchos pozos y se consulta
y filtra por sí misma (top operadoras, producción por operadora); una dimensión
propia evita redundancia y habilita ese análisis limpio. Elegimos SK hash
porque son estables y reproducibles entre corridas y particiones —clave para
upsert/backfill idempotente (ADR-0023)— sin coordinar secuencias. Elegimos SCD1
porque las preguntas de la Fase 2 necesitan el estado actual del pozo/operadora,
no su historia; SCD2 agregaría complejidad (versiones, `valid_from/to`,
resolución de la versión vigente en cada join) sin valor para el scope.

## Consecuencias

### Positivas

- Modelo simple y navegable en Metabase sin SQL; joins obvios fact→dim.
- SK hash determinísticas → upsert/backfill idempotente y referencias estables
  entre particiones.
- `dim_company` habilita análisis por operadora de primera clase.
- Menos objetos y cero lógica de versionado → menos superficie de error en el
  plazo del TP.

### Negativas / trade-offs asumidos

- **SCD1 pierde historia.** Si un pozo cambia de operadora, el dato anterior se
  sobrescribe; no se puede reconstruir "quién operaba en tal mes". Aceptado:
  fuera de scope de Fase 2; si se necesitara, se migra esa dimensión a SCD2 en
  una fase posterior.
- Star desnormaliza atributos en las dimensiones → leve redundancia de datos
  frente a snowflake. Irrelevante a este volumen (< 500 MB).
- SK hash exige claves de negocio bien definidas y estables; un cambio en la
  definición de la clave reescribe las SK. Mitigado documentando la clave de
  negocio de cada entidad.

### Neutras

- El detalle de columnas y tipos de cada tabla se especifica en la
  implementación dbt del gold (F2-16), no en este ADR.
- La materialización (upsert por clave de negocio en gold) se decide en el ADR
  de tipo de carga (F2-05); este ADR fija sólo la forma dimensional.

## Pros y contras de las opciones

### Forma del esquema

#### Star schema

- ✅ Pocas tablas, joins directos, óptimo para BI self-service (Metabase).
- ❌ Redundancia controlada en dimensiones.

#### Snowflake schema

- ✅ Dimensiones normalizadas, menos redundancia.
- ❌ Más joins y más tablas; peor experiencia en Query Builder; sin beneficio a
  este volumen.

### Operadora

#### `dim_company` propia

- ✅ Sin redundancia de atributos de operadora por pozo; análisis por operadora
  directo; reutilizable.
- ❌ Una dimensión y un join más.

#### Operadora como atributo de `dim_well`

- ✅ Una tabla menos.
- ❌ Repite los datos de la operadora en cada pozo; análisis por operadora
  requiere `GROUP BY` sobre texto repetido, propenso a inconsistencias.

### Surrogate keys

#### Hash determinístico

- ✅ Estable y reproducible entre corridas/particiones; no requiere secuencia
  central; ideal para upsert idempotente.
- ❌ Claves más anchas (hash) que un entero; dependen de una clave de negocio
  estable.

#### Autoincremental

- ✅ Compactas; patrón clásico de DW.
- ❌ No determinísticas: un reproceso puede reasignar IDs y romper referencias;
  difícil de coordinar entre particiones y backfills.

### Historización

#### SCD Tipo 1

- ✅ Simple; refleja el estado actual; sin lógica de versiones.
- ❌ Sin historia de cambios de atributos.

#### SCD Tipo 2

- ✅ Historia completa de cambios (auditable en el tiempo).
- ❌ Complejidad alta: versionado, `valid_from/to`, resolución de versión vigente
  en cada join; innecesario para las preguntas de Fase 2.

## Referencias

- ADR-0023 — Arquitectura medallion y motor dbt Core v2 (capa gold).
- ADR-0025 — Estrategia de calidad de datos en la capa medallion *(F2-07, pendiente)*.
- Adenda técnica Fase 2 (`docs/prd/addendum-v0.3.md`) — RNF6/RNF11, consumo
  Metabase del esquema gold.
- `dbt_utils.generate_surrogate_key` — documentación dbt-utils.
- Kimball — dimensional modeling (star schema, grano, SCD).
- Issue [#18](https://github.com/joaquinleondev/petrocast/issues/18) — F2-06.
