# ADR-0026: Tipo de carga por capa en la arquitectura medallion

- **Estado:** Propuesto
- **Fecha:** 2026-06-10
- **Autores:** Santino Domato
- **Decisores:** Equipo Petrocast

## Contexto y problema

La Fase 2 incorpora un pipeline analítico que ingiere dos fuentes de
datos.gob.ar: producción de pozos no convencionales y el listado
complementario de pozos cargados por empresas operadoras. La adenda exige
definir y justificar explícitamente el tipo de carga (`full`, incremental,
`merge` / `upsert`) en un ADR, además de garantizar idempotencia y un
procedimiento verificable de reprocesamiento histórico / backfill.

Las fuentes se consumen como archivos CSV publicados como snapshots completos.
No exponen un log de cambios, timestamps confiables de modificación por fila ni
eventos de altas, bajas y modificaciones. Además, los snapshots pueden corregir
períodos pasados: un mes ya procesado podría cambiar en una publicación futura.
Por eso una carga incremental append-only no alcanza para mantener consistencia
si se reprocesan meses históricos o si la fuente corrige datos.

ADR-0023 fija la arquitectura medallion (`bronze` → `silver` → `gold`) y dbt
como motor de transformación. ADR-0024 fija el modelo dimensional del `gold`
con star schema, surrogate keys hash determinísticas y SCD Tipo 1. Este ADR
define cómo se materializa cada capa para que ingesta, transformaciones y modelo
analítico sean idempotentes sin sobredimensionar la solución para el volumen y
plazo del TP.

## Drivers de la decisión

- **Idempotencia:** ejecutar dos veces la misma carga o el mismo backfill debe
  producir el mismo resultado, sin duplicar filas.
- **Correcciones históricas:** la estrategia debe capturar cambios en períodos
  pasados publicados en un nuevo snapshot fuente.
- **Backfill mensual:** debe ser posible reprocesar un mes o rango de meses sin
  reconstruir necesariamente todo el modelo analítico.
- **Trazabilidad medallion:** `bronze` debe conservar una copia fiel del
  snapshot fuente actual; `silver` debe representar datos limpios; `gold` debe
  exponer tablas estables para BI.
- **Simplicidad operativa:** el equipo es chico y el dataset es acotado, por lo
  que la estrategia no debe requerir infraestructura de streaming ni CDC si la
  fuente no lo ofrece.
- **Consumo BI estable:** Metabase debe ver claves y relaciones consistentes
  aunque se reprocesen particiones.
- **Compatibilidad con el stack:** la solución debe poder implementarse con
  `dlt`, Dagster, dbt y PostgreSQL.

## Opciones consideradas

1. **Full refresh end-to-end:** reemplazar todas las tablas en cada corrida.
2. **Incremental append-only:** agregar sólo filas nuevas sin actualizar ni
   borrar datos existentes.
3. **Merge / upsert por clave de negocio:** insertar nuevas filas y actualizar
   las existentes cuando la clave ya existe.
4. **CDC (Change Data Capture):** consumir eventos de cambios fila a fila desde
   la fuente.
5. **Estrategia diferenciada por capa:** `bronze` full refresh, `silver`
   idempotente por partición mensual y `gold` upsert por clave de negocio con
   surrogate keys hash.

## Decisión

Elegimos **estrategia diferenciada por capa**:

### Bronze: full refresh del snapshot fuente

La capa `bronze` se carga con **full refresh** de cada snapshot fuente. En cada
corrida, `dlt` reemplaza la tabla raw correspondiente
(`write_disposition="replace"` o equivalente) con la copia más fiel posible del
CSV publicado, agregando sólo metadatos técnicos mínimos del run cuando sean
necesarios (`loaded_at`, identificador de fuente, hash del archivo).

No intentamos inferir deltas en `bronze` porque la fuente publica snapshots
completos y no garantiza metadatos por fila para saber qué cambió. Full refresh
es más simple, reproducible y captura correcciones históricas sin lógica
especial: si el snapshot cambia una fila vieja, la nueva foto raw la contiene.

### Silver: reemplazo idempotente por partición mensual

La capa `silver` se materializa de forma **idempotente por partición de mes**.
Para cada mes reprocesado, el job elimina de `silver` las filas de esa partición
y las vuelve a insertar desde `bronze` ya tipadas, normalizadas, deduplicadas y
con nombres consistentes.

La unidad de partición es el mes de producción para los datos de producción.
Los datasets complementarios sin granularidad mensual se normalizan como
snapshot vigente y se usan al transformar las particiones afectadas. La regla
operativa es: rerun de la misma partición con el mismo `bronze` produce el mismo
`silver`; rerun con un snapshot nuevo refleja las correcciones publicadas.

### Gold: upsert por clave de negocio con SK hash

La capa `gold` usa **upsert por clave de negocio** sobre el star schema definido
en ADR-0024. Las dimensiones (`dim_well`, `dim_company`, `dim_date`) y la tabla
de hechos (`fact_production`) tienen claves únicas de negocio; las escrituras se
implementan con `INSERT ... ON CONFLICT ... DO UPDATE` o materialización
equivalente de dbt.

Las surrogate keys se generan como **hash determinístico** con
`dbt_utils.generate_surrogate_key` a partir de la clave de negocio. Esto evita
depender de secuencias autoincrementales y mantiene referencias estables entre
corridas, particiones y backfills. En dimensiones aplicamos SCD Tipo 1: si un
atributo cambia, el upsert sobrescribe el valor vigente.

## Consecuencias

### Positivas

- Bronze captura cualquier corrección histórica publicada en el snapshot sin
  lógica incremental frágil.
- Silver permite backfill por mes y reruns seguros: borrar e insertar la
  partición evita duplicados y estados parciales.
- Gold mantiene tablas estables para BI, con claves únicas y surrogate keys
  reproducibles entre corridas.
- La estrategia se alinea con la arquitectura medallion: raw simple, limpieza
  particionada y modelo analítico idempotente.
- No requiere CDC, streaming ni infraestructura adicional que la fuente no
  soporta.

### Negativas / trade-offs asumidos

- Bronze guarda sólo el snapshot raw vigente si se usa reemplazo simple; no
  conserva historia de snapshots anteriores. Si auditoría histórica de snapshots
  se vuelve requisito, habrá que versionar `bronze` por `snapshot_date` o por
  hash de archivo.
- Silver necesita que el rango mensual se elimine e inserte de forma atómica
  para evitar particiones incompletas si falla un job.
- Gold requiere definir y mantener claves de negocio únicas y constraints
  `ON CONFLICT`; una clave mal elegida puede ocultar duplicados reales o generar
  sobrescrituras incorrectas.
- SCD Tipo 1 simplifica el modelo pero no permite reconstruir atributos
  dimensionales históricos, trade-off ya asumido en ADR-0024.

### Neutras

- El volumen actual permite full refresh en `bronze` sin impacto relevante; si
  el dataset creciera mucho, podría evaluarse particionar o versionar raw sin
  cambiar la semántica de `silver` y `gold`.
- La implementación exacta puede usar dbt incremental models, SQL transaccional
  o macros propias, siempre que respete delete+insert por partición en `silver`
  y upsert por clave de negocio en `gold`.
- Los chequeos de calidad de ADR-0025 corren antes de promocionar a `gold`; si
  fallan, la partición no debe actualizar el modelo analítico.

## Pros y contras de cada opción

### Estrategia diferenciada por capa (elegida)

- ✅ Usa el tipo de carga que mejor encaja con el rol de cada capa: snapshot raw,
  limpieza particionada y modelo analítico upsertable.
- ✅ Cumple idempotencia y backfill sin depender de metadatos de cambio que la
  fuente no provee.
- ✅ Captura correcciones históricas y evita duplicados en reprocesos.
- ❌ Requiere implementar tres patrones de carga en vez de uno solo.

### Full refresh end-to-end

- ✅ Muy simple de razonar e implementar.
- ✅ Captura correcciones históricas porque reconstruye todo.
- ❌ Reprocesar un mes obliga a reconstruir también capas derivadas completas.
- ❌ Puede generar más downtime o churn en tablas consumidas por Metabase.
- ❌ No aprovecha particiones mensuales ni keys estables del modelo gold.

### Incremental append-only

- ✅ Eficiente cuando la fuente emite eventos inmutables o datos estrictamente
  nuevos.
- ✅ Implementación simple para logs o series que nunca corrigen historia.
- ❌ No maneja actualizaciones ni eliminaciones.
- ❌ Reprocesar una partición duplicaría filas salvo que haya deduplicación
  posterior.
- ❌ No captura correcciones históricas en snapshots completos.

### Merge / upsert por clave de negocio en todas las capas

- ✅ Maneja altas y modificaciones sin reconstruir tablas completas.
- ✅ Encaja bien en `gold`, donde las claves de negocio ya están normalizadas.
- ❌ En `bronze` obliga a decidir claves y semántica de actualización antes de
  limpiar y deduplicar los datos.
- ❌ Agrega complejidad innecesaria para snapshots chicos publicados completos.
- ❌ No resuelve por sí solo bajas o filas removidas del snapshot si no se
  compara contra la foto completa.

### CDC

- ✅ Es la opción más precisa cuando existe un stream o log transaccional de
  cambios con inserts, updates y deletes.
- ✅ Reduce el volumen movido si la fuente publica deltas confiables.
- ❌ datos.gob.ar entrega CSV snapshots, no un change log ni offsets de CDC.
- ❌ Requiere infraestructura y operación adicional fuera del alcance del TP.
- ❌ Sería una simulación de CDC basada en diffs de snapshots, más compleja que
  full refresh + particiones sin aportar valor proporcional.

## Referencias

- Adenda Fase 2 (`docs/assignment/adenda-fase-2.md`) — RF de tipo de carga,
  idempotencia y backfill.
- Backlog Fase 2 (`docs/backlog/issues-fase-2.md`) — F2-05, F2-14, F2-15 y
  F2-16.
- ADR-0023 — Arquitectura medallion y motor dbt Core v2
  (`docs/adr/0023-arquitectura-medallion-dbt.md`).
- ADR-0024 — Modelo dimensional del gold — star schema
  (`docs/adr/0024-modelo-dimensional-star-schema.md`).
- ADR-0025 — Calidad de datos y consecuencia operativa
  (`docs/adr/0025-calidad-datos-consecuencia.md`).
- ADR-0023 — Orquestación e ingesta con Dagster y dlt
  (`docs/adr/0023-orquestacion-e-ingesta-dagster-dlt.md`).
- PostgreSQL — `INSERT ... ON CONFLICT`:
  https://www.postgresql.org/docs/current/sql-insert.html
- dbt Docs — Incremental models:
  https://docs.getdbt.com/docs/build/incremental-models
