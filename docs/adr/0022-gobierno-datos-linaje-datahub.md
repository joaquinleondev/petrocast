# ADR-0022: Gobierno de datos y linaje con DataHub

- **Estado:** Aceptado
- **Fecha:** 2026-06-08
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La Fase 2 introduce una plataforma de datos completa: ingesta de datasets
públicos de datos.gob.ar con **dlt**, orquestación asset-céntrica con
**Dagster**, transformaciones con **dbt Core v2** siguiendo el patrón
medallion **bronze → silver → gold**, un warehouse en **PostgreSQL 16**
(esquemas `bronze`, `silver`, `gold`, con `gold` modelado como star schema:
hechos + dimensiones, surrogate keys hash y SCD1) y BI sobre **Metabase**.

Con varias capas, decenas de tablas y un grafo de dependencias que cruza
orquestación, transformación y warehouse, surge el problema: **nadie puede
responder con confianza de dónde viene un dato ni a qué impacta cambiarlo.**
Un cambio en una tabla `bronze` puede romper un modelo `silver` y, aguas
abajo, un dashboard de Metabase, sin que haya forma sistemática de verlo
antes de que falle.

La adenda del curso aborda esto con dos requerimientos no funcionales de
gobierno que debemos satisfacer:

- **"Linaje de Datos":** el sistema DEBE proveer alguna manera de trazar el
  linaje de los datos.
- **"Herramienta de Gobierno":** la plataforma de gobierno DEBE implementarse
  con una herramienta vista en clase/tutoría (**DataHub**), y DEBE permitir
  **navegar el linaje a nivel de tabla**; se PUEDEN explorar alternativas si
  se justifican debidamente.

Además, la adenda establece que el gobierno de datos es una de las decisiones
clave de Fase 2 que requiere un ADR, y que **un ADR sin comparación de
alternativas se considera inválido.** Por eso este documento no solo registra
la elección, sino que la valida comparando cinco herramientas: la comparación
es lo que hace que este ADR cumpla el criterio de la adenda.

La decisión abarca:

1. Qué herramienta de catálogo, gobierno y linaje adoptamos.
2. Cómo conviven su footprint operativo con un host EC2 pequeño compartido
   por el resto del stack de Fase 2.
3. Cómo se construye y se navega el linaje a nivel de tabla.

## Drivers de la decisión

- **Cumplimiento de la adenda.** La herramienta de gobierno debe ser una
  vista en clase/tutoría; la adenda nombra explícitamente **DataHub**.
- **Linaje navegable a nivel tabla.** El RNF "Herramienta de Gobierno" exige
  poder navegar el linaje a nivel de tabla, no solo verlo en un reporte
  estático.
- **Catálogo + glosario + gobierno.** Necesitamos un catálogo navegable de
  datasets, no únicamente un grafo de linaje.
- **Ingesta nativa de nuestro stack.** La herramienta debe entender **dbt**
  (modelos, tests, `manifest.json`) y **PostgreSQL** sin integraciones a
  medida.
- **Footprint acotado.** El host de Fase 2 es un EC2 chico (ADR-0010); todo
  lo que corra de forma permanente compite por RAM con Dagster, Postgres y
  Metabase.
- **Validez del ADR.** Sin comparación de alternativas, la adenda invalida
  la decisión: la evaluación de las cinco opciones es obligatoria.

## Opciones consideradas

1. **DataHub** (LinkedIn) — catálogo + gobierno + linaje a nivel
   columna/tabla, con conectores de ingesta nativos para dbt y PostgreSQL.
2. **OpenMetadata** — catálogo + linaje comparables, footprint más liviano.
3. **Apache Atlas** — gobierno potente del ecosistema Hadoop (HBase/Solr).
4. **Marquez** (OpenLineage) — linaje liviano, sin catálogo ni gobierno.
5. **dbt docs** — sitio estático generado con linaje de modelos dbt.

### Comparación de alternativas

| Herramienta  | Catálogo + gobierno | Linaje a nivel tabla | Footprint (contenedores / RAM) | Ingesta dbt + Postgres | Madurez / UI         | Veredicto                           |
| ------------ | ------------------- | -------------------- | ------------------------------ | ---------------------- | -------------------- | ----------------------------------- |
| **DataHub**  | Sí (completo)       | Sí, navegable        | Pesado (~6 / ~4 GB)            | Nativa                 | Alta, UI rica        | **Elegida** — mandada por la adenda |
| OpenMetadata | Sí (completo)       | Sí, navegable        | Medio (~3 / ~2 GB)             | Nativa                 | Alta, UI moderna     | Runner-up; la adenda nombra DataHub |
| Apache Atlas | Sí (potente)        | Sí                   | Pesado (Hadoop/HBase/Solr)     | Indirecta              | Madura pero compleja | Descartada — demasiado pesada       |
| Marquez      | No                  | Solo linaje          | Liviano (~2)                   | Parcial (OpenLineage)  | Foco en linaje       | Descartada — sin catálogo/gobierno  |
| dbt docs     | No                  | Solo dbt (estático)  | Mínimo (~1 proceso)            | Solo dbt               | Sitio estático       | Descartada — sin cross-tool/UI viva |

## Decisión

Elegimos **DataHub** como plataforma de catálogo, gobierno y linaje de datos,
desplegado **bajo demanda** (on-demand): se levanta solo cuando hay que
catalogar/ingestar metadatos o explorar el linaje, y se baja al terminar.

DataHub es la herramienta **nombrada y mandada por la adenda** del curso, y
es la única de las cinco opciones que cubre simultáneamente los tres ejes que
necesitamos —catálogo navegable, gobierno/glosario y **linaje navegable a
nivel de tabla**— con conectores de ingesta nativos para **dbt** y
**PostgreSQL**.

### Despliegue bajo demanda

El stack de DataHub vía `docker compose` levanta del orden de **~6
contenedores** (GMS, consumers MAE/MCE, Elasticsearch, Kafka, MySQL y el
frontend) y consume **~4 GB de RAM**. Ese footprint **no entra corriendo
24/7** junto al resto del stack de Fase 2 en el EC2 chico del proyecto
(ADR-0008, ADR-0010, ADR-0019). En lugar de cambiar de herramienta —lo que
contradiría la adenda— mitigamos el costo con el ciclo de vida operativo:

```text
docker compose up   ->  ingesta de metadatos (dbt + Postgres)
                    ->  refresco del linaje
                    ->  exploración / navegación del grafo
docker compose down ->  se libera RAM para Dagster, Postgres y Metabase
```

El catálogo y el linaje son **artefactos de inspección**, no parte del path
crítico de runtime: ni la ingesta de dlt, ni la orquestación de Dagster, ni
los dashboards de Metabase dependen de que DataHub esté arriba. Por eso
levantarlo a demanda es una mitigación pragmática y suficiente, no una
degradación del servicio.

### Arquitectura de linaje a nivel tabla

El linaje navegable a nivel de tabla se arma combinando **tres fuentes
complementarias** que DataHub unifica:

1. **Dagster → linaje de flujos/assets.** Dagster aporta el grafo de
   orquestación (qué asset produce/consume qué) a nivel de flujo y asset.
2. **dbt → linaje de modelos/SQL.** `dbt docs generate` produce el
   `manifest.json` con el grafo de dependencias entre modelos y el SQL
   compilado; la fuente dbt de DataHub lo ingiere.
3. **DataHub → grafo unificado a nivel tabla.** DataHub ingiere los metadatos
   de **dbt** y de **PostgreSQL** y los presenta como un único grafo de
   linaje **a nivel de tabla**, navegable y clickeable, recorriendo
   **bronze → silver → gold** con navegación upstream/downstream.

Así, ante un cambio en una tabla `bronze`, el equipo navega el grafo en
DataHub y ve qué modelos `silver`/`gold` y qué tablas downstream se ven
afectados antes de aplicarlo —exactamente lo que pide el RNF
"Herramienta de Gobierno".

## Consecuencias

**Positivas:**

- Cumplimos los RNF "Linaje de Datos" y "Herramienta de Gobierno" con la
  herramienta que la adenda nombra explícitamente.
- Un único lugar para catálogo, glosario, gobierno y linaje a nivel tabla.
- Ingesta nativa de dbt y PostgreSQL: sin glue code para poblar el catálogo.
- El linaje cruza orquestación (Dagster), transformación (dbt) y warehouse
  (Postgres) en un grafo navegable bronze → silver → gold.
- El ciclo up/down mantiene libre la RAM del EC2 para el stack que sí corre
  de forma permanente.

**Negativas / trade-offs asumidos:**

- Footprint pesado: ~6 contenedores y ~4 GB de RAM cuando está arriba.
- No corre 24/7; el catálogo y el linaje son válidos a la fecha de la última
  ingesta, no en tiempo real.
- Operar el ciclo up/ingesta/down agrega un paso manual (mitigable con un
  script o una receta documentada).
- Kafka, Elasticsearch y MySQL elevan la complejidad operativa frente a
  alternativas más simples.

**Neutras:**

- **OpenMetadata** queda registrado como el runner-up más fuerte: cubre lo
  mismo con un footprint menor (~3 contenedores, ~2 GB) y podría justificarse
  como alternativa si en el futuro el costo de DataHub se volviera
  prohibitivo, dado que la adenda permite explorar alternativas justificadas.
- El metadato ingestado (manifest de dbt, esquema de Postgres) es portable:
  migrar a otra herramienta no implica rehacer el modelado de datos.
- La frecuencia de refresco del linaje queda como decisión operativa, no
  arquitectónica.

## Pros y contras de cada opción

### DataHub (elegida)

- ✅ Mandada explícitamente por la adenda del curso.
- ✅ Catálogo + gobierno + glosario + linaje a nivel columna/tabla.
- ✅ Conectores de ingesta nativos para dbt y PostgreSQL, más metadatos de
  orquestación.
- ✅ UI rica con grafo de linaje navegable upstream/downstream.
- ❌ Footprint pesado: ~6 contenedores (GMS, MAE/MCE, Elasticsearch, Kafka,
  MySQL, frontend), ~4 GB de RAM.
- ❌ No entra corriendo 24/7 en el EC2 chico; obliga al despliegue
  bajo demanda.

### OpenMetadata

- ✅ Catálogo + linaje comparables a DataHub.
- ✅ Más liviano: ~3 contenedores, ~2 GB de RAM.
- ✅ Ingesta de dbt y bases SQL.
- ❌ La adenda nombra DataHub, no OpenMetadata: sería el runner-up más fuerte
  pero requeriría justificar el desvío.

### Apache Atlas

- ✅ Gobierno y linaje potentes, con modelo de metadatos extensible.
- ❌ Atado al ecosistema Hadoop (HBase, Solr): operacionalmente pesado.
- ❌ Complejo de levantar y mantener para la escala de este proyecto.
- ❌ Integración con dbt/PostgreSQL menos directa que en DataHub.

### Marquez (OpenLineage)

- ✅ Liviano: ~2 contenedores.
- ✅ Buen modelo de linaje basado en el estándar OpenLineage.
- ❌ Solo linaje: sin catálogo de datos, sin glosario, sin UI de gobierno.
- ❌ No cubre el RNF "Herramienta de Gobierno" más allá del linaje.

### dbt docs

- ✅ Footprint mínimo: ~1 proceso, sitio estático generado.
- ✅ Da linaje de modelos/SQL para dbt directamente desde el proyecto.
- ❌ Solo cubre dbt: no incluye el linaje cross-tool con Dagster ni Postgres.
- ❌ Sin catálogo ni UI de gobierno; no es un grafo vivo navegable.
- ❌ Sitio estático: hay que regenerarlo y republicarlo en cada cambio.

## Referencias

- Adenda del curso — gobierno de datos como decisión de Fase 2 que requiere
  ADR; un ADR sin comparación de alternativas se considera inválido.
- Adenda del curso — RNF "Linaje de Datos" (trazabilidad del linaje) y RNF
  "Herramienta de Gobierno" (herramienta vista en clase/tutoría, DataHub,
  con navegación de linaje a nivel tabla; alternativas justificadas
  permitidas).
- ADR-0002 — Idioma del proyecto (ADRs en español).
- ADR-0008 — Topología de ambientes (host por ambiente).
- ADR-0010 — Hosting AWS EC2 (host chico, argumento del footprint).
- ADR-0019 — Infraestructura Terraform sobre AWS (tamaño de instancia).
- ADR de orquestación de Fase 2 (Dagster + dlt) — fuente del linaje de
  flujos/assets (número pendiente, aún no mergeado).
- ADR de transformaciones medallion (dbt Core v2, bronze → silver → gold) —
  fuente del linaje de modelos/SQL vía `manifest.json` (número pendiente).
- ADR del modelado dimensional (star schema en `gold`) — objeto catalogado
  aguas abajo (número pendiente).
- ADR de calidad de datos de Fase 2 — complementa gobierno con validaciones
  (número pendiente).
- ADR de topología de despliegue de Fase 2 — contexto del host compartido
  (número pendiente).
- DataHub — documentación de ingestion sources (dbt, PostgreSQL).
- DataHub — Lineage (table-level y column-level).
- OpenMetadata, Apache Atlas, Marquez (OpenLineage), dbt docs — documentación
  oficial de cada alternativa.
