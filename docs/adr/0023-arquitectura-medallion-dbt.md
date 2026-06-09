# ADR-0023: Arquitectura medallion (bronze/silver/gold) y motor de transformación (dbt Core v2)

- **Estado:** Propuesto
- **Fecha:** 2026-06-08
- **Autores:** Ignacio Vargas Fernández
- **Decisores:** Equipo Petrocast

## Contexto y problema

La Fase 2 incorpora un pipeline de datos que ingiere dos fuentes de
datos.gob.ar, las transforma y las publica para consumo analítico (Metabase)
y gobierno (DataHub). La adenda exige (RF2) una arquitectura de capas
**medallion** y deja como ADR obligatorio fijar tanto el layering como el
**motor de transformación**.

Necesitamos decidir dos cosas acopladas:

1. **Cómo estructurar el almacenamiento intermedio**: una sola capa de tablas
   transformadas vs. el patrón de tres capas bronze/silver/gold.
2. **Con qué herramienta transformar**: SQL ad-hoc orquestado a mano vs. un
   framework de transformación declarativo (dbt, SQLMesh) y, dentro de dbt,
   qué línea de versión (la nueva **dbt Core v2 / motor Fusion** vs. la línea
   estable **1.x**).

Las decisiones están acopladas porque la elección del motor condiciona cómo
se materializan y testean las capas. El warehouse ya está fijado: PostgreSQL
(ADR-0012), con esquemas `bronze`, `silver` y `gold`. La orquestación ya está
fijada en la adenda: Dagster invocando dbt vía `dagster-dbt`. Este ADR no
revisa esas decisiones; las toma como dadas y formaliza la capa de
transformación que vive entre ellas.

## Drivers de la decisión

- **Trazabilidad y reproceso.** El dataset fuente es un snapshot full que
  puede incluir correcciones a períodos pasados. Necesitamos poder rematerializar
  desde el dato crudo sin haberlo perdido, lo que exige conservar el crudo
  intacto (capa bronze) separado de lo transformado.
- **Calidad como ciudadano de primera clase.** La adenda exige chequeos de
  calidad persistidos con consecuencia operativa (bloqueo). El motor debe
  soportar tests declarativos junto al modelo, no scripts de validación sueltos.
- **Linaje automático.** La adenda exige linaje navegable Bronze→Silver→Gold.
  El motor debería generar el grafo de dependencias por sí mismo, no a mano.
- **Afinidad con Dagster.** Ya se eligió `dagster-dbt`; el motor debe integrarse
  nativamente con el orquestador para no agregar pegamento.
- **Curva de aprendizaje y plazo.** TP con tiempo acotado y equipo de 3. La
  herramienta debe ser aprendible y tener documentación y rodaje suficientes.
- **Madurez vs. novedad.** "dbt Core v2 (Fusion)" es el motor nuevo (Rust);
  promete velocidad y validación estática, pero tiene menos rodaje que la línea
  1.x. Hay que pesar el riesgo de adoptar algo reciente en un entregable con
  nota.
- **Costo y licencia.** Preferimos open source self-hosted, sin dependencia de
  dbt Cloud ni costos recurrentes.

## Opciones consideradas

### Estructura de capas

1. **Medallion de tres capas (bronze/silver/gold).**
2. **Dos capas (raw + mart), sin silver intermedia.**
3. **Transformación directa fuente→tabla analítica (sin staging).**

### Motor de transformación

1. **dbt Core v2 (motor Fusion).**
2. **dbt Core línea 1.x.**
3. **SQLMesh.**
4. **ETL ad-hoc (SQL/Python orquestado a mano en Dagster).**

## Decisión

- **Estructura:** arquitectura **medallion de tres capas** en PostgreSQL:
  - **`bronze`** — copia fiel del snapshot fuente, sin transformar (carga full,
    idempotente por reemplazo). Es la fuente de verdad para reproceso.
  - **`silver`** — datos limpios, tipados, normalizados y deduplicados;
    idempotente por partición de mes; donde corren los chequeos de calidad.
  - **`gold`** — modelo dimensional (star schema, ver ADR-0024) listo para
    consumo de Metabase; upsert por clave de negocio.
- **Motor:** **dbt Core v2 (motor Fusion)**, self-hosted, invocado por Dagster
  vía `dagster-dbt`. Las transformaciones Bronze→Silver→Gold se expresan como
  modelos dbt; los chequeos de calidad como dbt tests (ver ADR-0025).

Elegimos dbt sobre ETL ad-hoc porque resuelve de fábrica tres requisitos de la
adenda —tests de calidad declarativos, linaje automático (`dbt docs generate`)
e integración nativa con Dagster— que con SQL a mano exigirían construir y
mantener nosotros. Elegimos dbt sobre SQLMesh porque, siendo SQLMesh
técnicamente sólido, dbt tiene mayor rodaje, más documentación y mejor soporte
del integrador `dagster-dbt` que el equipo ya planificó. Dentro de dbt elegimos
la línea v2/Fusion por su validación estática de SQL y velocidad, asumiendo el
riesgo de madurez descrito abajo y dejando como mitigación el fallback a la
línea 1.x si Fusion presenta un bloqueante.

## Consecuencias

### Positivas

- El crudo (bronze) queda intacto y permite backfill reprocesando desde el
  origen, sin depender de capas derivadas (alinea con el runbook de reproceso,
  F2-23/F2-26).
- Los chequeos de calidad viven junto al modelo (dbt tests) y se ejecutan en la
  transición Bronze→Silver, donde el riesgo de dato sucio es mayor.
- El linaje a nivel de modelo se genera solo (`dbt docs generate`) y se importa
  a DataHub vía su source dbt nativo (alinea con F2-19/F2-21).
- Separación de responsabilidades clara: Dagster orquesta (scheduling, retries,
  particiones, asset checks); dbt transforma y testea.
- Stack open source self-hosted; sin costo de licencia ni dependencia de dbt
  Cloud.

### Negativas / trade-offs asumidos

- **dbt Core v2 / Fusion es nuevo.** Menos rodaje que 1.x; riesgo de bugs o de
  features/adapters que aún no cubran PostgreSQL al 100%. Mitigación: pinnear la
  versión, y mantener el modelo escrito en SQL estándar de dbt para poder
  rollbackear a 1.x sin reescritura significativa.
- Tres capas implican más tablas y más almacenamiento que una transformación
  directa. Aceptable dado el tamaño del dataset (< 500 MB).
- Curva de aprendizaje de dbt (modelos, `ref()`, materializaciones, tests) para
  quienes no lo conocen. Acotada por el tamaño chico del pipeline (dos fuentes).

### Neutras

- El detalle de la materialización por capa (full en bronze, incremental por
  partición en silver, upsert en gold) se decide en el ADR de tipo de carga
  (F2-05). Este ADR sólo fija el rol de cada capa.
- El modelo dimensional concreto del gold (hechos/dimensiones) se define en el
  ADR de modelo dimensional (ADR-0024).

## Pros y contras de las opciones

### Estructura de capas

#### Medallion de tres capas

- ✅ Crudo preservado para reproceso; silver como punto único de limpieza y
  calidad; gold optimizado para consumo. Patrón estándar y entendible.
- ❌ Más tablas y storage; más modelos que mantener.

#### Dos capas (raw + mart)

- ✅ Menos objetos; más simple.
- ❌ Mezcla limpieza y modelado dimensional en un solo paso; los chequeos de
  calidad pierden un punto natural donde correr; reproceso más enredado.

#### Transformación directa (sin staging)

- ✅ Mínimo de objetos; máxima simplicidad inicial.
- ❌ Sin crudo preservado no hay backfill confiable; toda corrección obliga a
  re-descargar; imposible auditar qué entró vs. qué se transformó.

### Motor de transformación

#### dbt Core v2 (Fusion)

- ✅ Tests y linaje nativos; integración `dagster-dbt`; SQL declarativo con
  `ref()`; validación estática y velocidad del motor Fusion; open source.
- ❌ Motor nuevo, menos rodaje; posible inmadurez de adapters; riesgo de
  bloqueante que obligue a fallback a 1.x.

#### dbt Core 1.x

- ✅ Misma propuesta de valor (tests, linaje, `dagster-dbt`) con máximo rodaje
  y documentación; battle-tested en PostgreSQL.
- ❌ Sin la validación estática ni la velocidad de Fusion; es la dirección que
  el ecosistema está dejando atrás a mediano plazo.

#### SQLMesh

- ✅ Column-level lineage nativo, entornos virtuales (virtual data environments),
  y manejo de cambios incremental potente; técnicamente muy sólido.
- ❌ Menor rodaje y comunidad que dbt; integración con Dagster menos estándar
  que `dagster-dbt`; el equipo ya planificó el camino dbt en la adenda;
  re-decidir agrega costo de aprendizaje sin beneficio decisivo para este scope.

#### ETL ad-hoc (SQL/Python a mano)

- ✅ Cero dependencias nuevas; control total.
- ❌ Hay que construir y mantener nosotros los tests de calidad, el grafo de
  linaje y la idempotencia; más código propenso a error; no genera docs ni
  lineage para DataHub; peor relación esfuerzo/resultado para el plazo.

## Referencias

- ADR-0012 — Stack backend Python/FastAPI/uv + PostgreSQL 16 (warehouse).
- ADR-0024 — Modelo dimensional (star schema) del gold *(F2-06, pendiente)*.
- ADR-0025 — Estrategia de calidad de datos en la capa medallion *(F2-07, pendiente)*.
- Adenda técnica Fase 2 (`docs/prd/addendum-v0.3.md`) — RF2 (medallion),
  orquestación Dagster + `dagster-dbt`, calidad, linaje.
- dbt Core / dbt Fusion engine — documentación oficial.
- SQLMesh — documentación oficial.
- Issue [#16](https://github.com/joaquinleondev/petrocast/issues/16) — F2-04.
