# Addendum v0.3 al PRD — Plataforma de Ingesta, Procesamiento y Gobierno de Datos

- **Versión:** v0.3
- **Fecha:** 2026-06-01
- **Autores:** Equipo Petrocast
- **Estado:** Propuesto — pendiente de validación con cliente
- **Documento padre:** [PRD v0.2 — Fase 2](./prd-v0.2.md)

## Propósito

La adenda técnica de Fase 2 define los requisitos del sistema de ingesta, procesamiento y gobierno de datos, pero deja abiertas nueve decisiones de diseño que condicionan la arquitectura a implementar. Este documento:

1. Propone una respuesta fundamentada a cada pregunta abierta.
2. Documenta las asunciones que soportan cada respuesta.
3. Identifica los puntos que, en un proyecto real, requerirían validación con el cliente.

Las decisiones de mayor envergadura se profundizan en ADRs específicos, referenciados al final de cada sección. Este Addendum es el resumen ejecutivo; los ADRs son el análisis completo con comparación de alternativas.

## Cómo leer este documento

Cada sección sigue la misma estructura:

- **Pregunta original** tal como aparece en el PRD de Fase 2.
- **Contexto** que clarifica el alcance e implicancias de la pregunta.
- **Propuesta** del equipo con justificación.
- **Asunciones** que soportan la propuesta.
- **Puntos a validar con el cliente** antes de cerrar la decisión.

---

## Pregunta 1 — Herramienta de orquestación

> _¿Qué herramienta de orquestación se utilizará: Airflow, Prefect, Dagster u otra equivalente?_

### Contexto

La herramienta de orquestación debe cumplir los tres requisitos técnicos de la adenda:

1. DAGs definidos como código.
2. Idempotencia y retries con backoff.
3. Observabilidad mínima: logs y estado de ejecución accesibles.

Las tres opciones mencionadas difieren en modelo de programación, complejidad operativa y afinidad con la arquitectura medallion adoptada en el proyecto.

| Dimensión | Apache Airflow 2.x | Prefect 3.x | Dagster 1.x |
| --------- | ------------------ | ----------- | ----------- |
| Modelo de abstracción | DAG de tareas (grafo de dependencias) | Flows y tasks (funciones Python decoradas) | Software-defined assets (outputs, no pasos) |
| Setup local mínimo | `docker compose` (6+ contenedores: scheduler, webserver, worker, Redis, PostgreSQL, Flower) | `prefect server start` (1 proceso local) | `dagster dev` (1 proceso local) |
| Retries con backoff | `retries` + `retry_delay` en BaseOperator | `@task(retries=3, retry_delay_seconds=exponential(10))` | `@op(retry_policy=RetryPolicy(...))` |
| Observabilidad integrada | Webserver con Gantt, logs por tarea, Tree view | UI en localhost:4200 con logs por task run e historial | UI en localhost:3000 con asset catalog y partitions |
| Afinidad con arquitectura medallion | Media (tareas que transforman, sin modelo de assets) | Media (flows con steps secuenciales) | Alta (assets Bronze/Silver/Gold son ciudadanos de primera clase) |
| Recursos en EC2 t3.small | Alto (~2+ GB RAM solo para servicios base) | Bajo (~300 MB) | Bajo-medio (~400 MB) |
| Backfill nativo | Sí (catchup + Tree view) | Sí (re-run parametrizado por fecha desde UI/CLI) | Sí (backfill by partition) |
| Integración con dbt | Via `apache-airflow-providers-dbt-cloud` | Via `prefect-dbt` | Nativa (`dagster-dbt`, mejor de clase) |

### Propuesta

Adoptamos **Dagster 1.x** como herramienta de orquestación, complementado con **dbt Core** para las transformaciones SQL entre capas.

**Justificación:**

Dagster es la opción con mejor afinidad con la arquitectura medallion de este proyecto. Su modelo de _software-defined assets_ expresa cada tabla (Bronze, Silver, Gold) como un asset cuyo grafo de dependencias Dagster infiere automáticamente, en lugar de tareas conectadas a mano. Esto alinea el orquestador con el modelo de datos, no con una secuencia de pasos opacos, y hace que las tres capas medallion sean ciudadanos de primera clase de la herramienta.

La integración con dbt vía `dagster-dbt` es la mejor de su categoría: cada modelo dbt aparece como un asset nativo dentro de Dagster, unificando extracción y transformación en un único grafo observable. Airflow y Prefect integran dbt como un paso opaco; Dagster lo integra como assets navegables, lo que potencia el linaje (Pregunta 4) sin componentes extra.

Los retries con backoff son un atributo de la definición del asset (`RetryPolicy(max_retries=3, backoff=Backoff.EXPONENTIAL)`). La idempotencia se obtiene de forma nativa mediante **particiones**: cada asset se particiona por mes y rematerializar una partición la reemplaza de forma determinística.

El procedimiento de backfill se cubre con el soporte **nativo de particiones** de Dagster: desde la UI o por CLI se puede rematerializar cualquier rango de meses (`--partition-range`), con un calendario visual que muestra qué particiones están materializadas y cuáles no. Esto es más robusto y verificable que un flow parametrizado manual, y cubre el requisito explícito de backfill de la adenda.

**Relación con Prefect y Airflow:**

Prefect es la alternativa de menor curva de aprendizaje (Python idiomático con `@flow`/`@task`) y Airflow es el estándar de la industria; ambas son válidas. Se elige Dagster porque su modelo de assets y su integración nativa con dbt reducen el pegamento necesario para cubrir tres requisitos de la adenda —medallion, linaje y calidad— que de otro modo requerirían más componentes o código manual. La mayor curva de aprendizaje del modelo de assets es el costo asumido, acotado por el tamaño chico del pipeline (dos fuentes). El consumo de recursos en EC2 `t3.small` es bajo (~400 MB), comparable a Prefect y muy por debajo de Airflow. El ADR de orquestación documenta esta comparación con detalle para la defensa oral.

**Rol de dbt en el stack:**

Las transformaciones Bronze→Silver→Gold se implementan como modelos dbt, que Dagster invoca mediante el integrador `dagster-dbt`. Esto separa responsabilidades: Dagster maneja el scheduling, retries, particiones y observabilidad del grafo; dbt maneja las transformaciones SQL, los tests de calidad y genera el grafo de lineage automáticamente.

### Asunciones

- El servidor de Dagster (`dagster webserver` + `dagster daemon`) corre en el mismo EC2 que el resto del stack (no se usa Dagster+ / Cloud).
- Las transformaciones son SQL-first (dbt), no PySpark ni operaciones de alta cardinalidad que requieran un motor distribuido.
- El volumen de datos de las fuentes definidas (dos CSVs de datos.gob.ar) es manejable en un solo nodo PostgreSQL: el dataset de producción de pozos no convencionales tiene del orden de millones de filas históricas, volumen trivial para PostgreSQL en una t3.small.

### Puntos a validar con el cliente

1. ¿Existe una herramienta de orquestación ya en uso en la organización que sea preferible adoptar (Airflow, Databricks Workflows, AWS Glue)?
2. ¿El flujo de extracción debe soportar fuentes adicionales en Fase 3 (SCADA, PI System, SAP)? Esto podría favorecer Airflow o Dagster por su ecosistema de conectores.
3. ¿Se requiere scheduling con frecuencia sub-horaria o near-realtime? Dagster lo soporta vía schedules/sensors; un volumen near-realtime podría requerir revisar la estrategia de particiones.

### Referencias

- ADR pendiente: _Selección de herramienta de orquestación_ (Dagster vs Prefect vs Airflow, a escribir al inicio de Fase 2).
- [Dagster Docs](https://docs.dagster.io/) — software-defined assets, particiones, backfill, retry policies.
- [dagster-dbt](https://docs.dagster.io/integrations/dbt) — integración nativa con dbt.
- ADR-0012: Elección de stack backend Python + PostgreSQL, que define el motor de base de datos compartido entre la API y el DW.

---

## Pregunta 2 — Plataforma de BI

> _¿Qué plataforma de BI se utilizará?_

### Contexto

La adenda requiere una plataforma de BI accesible para **usuarios no técnicos** que permita revisar los datos en el Data Warehouse. Los criterios de selección son: conexión nativa a PostgreSQL, UI explorable sin conocimiento de SQL, self-hosted y open source, bajo overhead operativo, y capacidad de crear dashboards con filtros interactivos.

| Criterio | Metabase OSS | Apache Superset | Redash | Grafana |
| -------- | ------------ | --------------- | ------ | ------- |
| Orientado a no-técnicos | Alta (Query Builder visual) | Media (requiere SQL básico) | Baja (SQL obligatorio) | No (foco en métricas operativas) |
| Self-hosted / open source | Sí | Sí | Sí | Sí (ya lo tenemos) |
| Setup Docker | `docker run` (1 imagen) | `docker compose` (3+ contenedores) | `docker compose` (3 contenedores) | `docker run` (1 imagen) |
| Exploración sin SQL | Sí | Parcial | No | No |
| Dashboards con filtros | Sí | Sí | Sí | Parcial |
| Conexión a PostgreSQL | Sí | Sí | Sí | Sí |
| Curva de aprendizaje | Baja | Media-Alta | Media | Baja (para ops) |

### Propuesta

Adoptamos **Metabase OSS** como plataforma de BI.

**Justificación:**

El requisito explícito de la adenda es que usuarios no técnicos puedan revisar los datos. Metabase es el líder claro en este segmento: su Query Builder visual permite explorar el modelo estrella del esquema Gold sin escribir SQL. El setup es `docker run -p 3001:3000 metabase/metabase` — una imagen, sin dependencias adicionales. Se integra al `compose.data.yml` sin fricción.

Metabase se conecta directamente al esquema `gold` de PostgreSQL y puede generar dashboards con filtros por pozo, fecha y tipo de fluido (petróleo, gas, agua) sin configuración adicional.

**Relación con Grafana:**

Grafana continúa como plataforma de monitoreo operativo (métricas de la API, latencia, error rate), según lo definido en Fase 1 (ADR-0021). Metabase cubre el caso de uso de BI de negocio sobre los datos del DW. Son herramientas con audiencias distintas y no se solapan. El puerto por defecto de Metabase (3000) colisiona con Grafana, por lo que Metabase se expone en el 3001.

### Asunciones

- Los usuarios no técnicos acceden a Metabase vía navegador en la misma red que el servidor.
- No se requiere SSO ni autenticación federada para Metabase en esta fase; se usa la autenticación básica de Metabase con usuario/contraseña.
- Los dashboards necesarios para la demo son un subconjunto acotado: producción por pozo por mes, evolución histórica y top pozos por volumen.

### Puntos a validar con el cliente

1. ¿Metabase OSS es suficiente o se requieren features de Metabase Pro (SSO, alertas avanzadas, embedding)?
2. ¿Existen dashboards o reportes específicos que el equipo de planificación ya usa hoy que deberíamos replicar en Metabase?
3. ¿Se requiere acceso externo a internet para Metabase, o sólo acceso intra-red?

### Referencias

- ADR pendiente: _Selección de plataforma de BI_ (a escribir al inicio de Fase 2).
- [Metabase Docs — Running with Docker](https://www.metabase.com/docs/latest/installation-and-operation/running-metabase-on-docker).

---

## Pregunta 3 — Plataforma de gobierno de datos

> _¿Qué plataforma de gobierno de datos se utilizará?_

### Contexto

La adenda requiere una plataforma de gobierno que exponga:

1. Los **workflows de extracción de datos** (qué flow corrió, cuándo, con qué resultado).
2. Los **datos en el Data Warehouse** (qué tablas existen, qué columnas, qué significa cada campo).
3. La **última vez que los datos fueron actualizados**.

Además, la adenda exige que la herramienta sea de las "vistas en clase o tutoría, como DataHub". Opciones evaluadas:

| Plataforma | Catálogo | Linaje | Calidad | Setup |
| ---------- | -------- | ------ | ------- | ----- |
| **DataHub** (LinkedIn) | Sí, completo | Sí, columnar | Sí | `docker compose` (~6 contenedores: GMS, MCE consumer, Elasticsearch, Kafka, MySQL, frontend). ~4 GB RAM |
| **OpenMetadata** | Sí, completo | Sí, a nivel tabla | Sí | `docker compose` (~3 contenedores: API, UI, PostgreSQL). ~2 GB RAM |
| **Apache Atlas** | Sí | Sí (foco Hadoop) | No | Ecosistema Hadoop, muy complejo |
| **Marquez** (Astronomer) | No | Sí (OpenLineage) | No | 2 contenedores, pero no tiene catálogo |
| **dbt docs** | Parcial (modelos dbt) | Sí (grafo SQL) | Sí (resultados de tests) | `dbt docs serve`, 1 proceso |

### Propuesta

Adoptamos **DataHub** como plataforma de gobierno de datos, complementada con el lineage nativo de dbt.

**Justificación:**

DataHub es la herramienta **nombrada explícitamente por la adenda** ("alguna herramienta vista en clase o tutoría (DataHub)"). Aunque la adenda permite alternativas justificadas, se opta por DataHub para **eliminar el riesgo de evaluación** de usar una herramienta no solicitada: el beneficio de footprint de una alternativa no compensa el riesgo de que la cátedra espere ver DataHub específicamente.

DataHub cubre los tres requisitos de la adenda:

1. **Workflows**: las _ingestion sources_ muestran el estado y última ejecución de los conectores (PostgreSQL, dbt, Dagster). El estado de los assets/particiones de Dagster es visible además en la propia UI de Dagster.
2. **Datos en el DW**: el catálogo expone todas las tablas con descripciones de columnas, tipos y estadísticas. Las tablas del star schema son navegables por un usuario no técnico.
3. **Última actualización**: la metadata de cada tabla incluye el timestamp de la última ingesta y el número de filas.

El lineage SQL detallado (qué columna de Bronze alimenta qué columna de Gold) se obtiene del grafo de dbt (`dbt docs generate`) y se importa a DataHub vía su _source_ dbt nativo.

**Footprint y operación:**

DataHub requiere Kafka, Elasticsearch y MySQL como dependencias (~6 contenedores, ~4 GB RAM), lo que es exigente para una EC2 `t3.small` corriendo junto al resto del stack. Se gestiona **levantando DataHub bajo demanda** (vía `docker compose`) para la demostración de gobierno y linaje, en lugar de mantenerlo encendido de forma permanente junto a Postgres, Dagster, Metabase y la API.

**Nota sobre alternativas:**

**OpenMetadata** sería una alternativa válida y de menor footprint (~2 GB, sin Kafka), que cumple los mismos tres requisitos. Se prioriza DataHub por ser la herramienta explícitamente requerida; la comparación completa queda registrada en el ADR de gobierno para cumplir el requisito de análisis de alternativas.

### Asunciones

- DataHub se levanta vía Docker Compose bajo demanda para la demostración de gobierno y linaje (no necesariamente de forma permanente junto al resto del stack).
- El linaje de la orquestación (qué asset/partición de Dagster generó cada tabla y cuándo) es visible en la UI de Dagster; el estado de ingesta se refleja en DataHub.
- El lineage SQL detallado se obtiene de dbt y se importa a DataHub vía su source dbt.

### Puntos a validar con el cliente

1. ¿La cátedra evalúa con DataHub específicamente, o acepta cualquier plataforma de gobierno si está debidamente justificada?
2. ¿Se requiere integración con herramientas de governance corporativas existentes (Collibra, Alation, Informatica)?
3. ¿El lineage columnar (no solo a nivel tabla) es un requisito para esta fase?

### Referencias

- ADR pendiente: _Selección de plataforma de gobierno de datos_ (DataHub vs OpenMetadata, a escribir al inicio de Fase 2).
- [DataHub Docs — Quickstart con Docker](https://datahubproject.io/docs/quickstart/).
- [DataHub — dbt integration](https://datahubproject.io/docs/generated/ingestion/sources/dbt/).
- [dbt Docs — Artifacts y lineage graph](https://docs.getdbt.com/reference/artifacts/dbt-artifacts).

---

## Pregunta 4 — Herramienta de linaje de datos

> _¿Qué herramienta se utilizará para seguir el linaje de los datos?_

### Contexto

El linaje de datos tiene dos niveles:

- **Linaje de flujo** (flow-level): qué proceso generó qué dataset, cuándo, con qué parámetros.
- **Linaje SQL** (column-level): qué columna de qué tabla Bronze alimenta qué columna de qué tabla Gold.

Una sola herramienta raramente cubre ambos niveles con igual profundidad. La pregunta es qué herramienta o combinación cubre el requisito de la adenda.

### Propuesta

Cubrimos el linaje con **dos herramientas complementarias ya elegidas en el stack**:

| Nivel | Herramienta | Cómo |
| ----- | ----------- | ---- |
| Linaje de flujo | **Dagster** | Cada materialización de asset registra qué se cargó, en qué partición de mes, y con qué resultado; el grafo de assets (extracción + dbt) es navegable en la UI |
| Linaje SQL (modelo) | **dbt** | `dbt docs generate` produce el grafo de dependencias entre modelos Bronze/Silver/Gold; visible en `dbt docs serve` |
| Catálogo + linaje integrado | **DataHub** | Ingesta el grafo de dbt vía su source; lo presenta en una UI navegable junto al catálogo de tablas |

No se añade una herramienta separada para linaje porque la combinación Dagster + dbt + DataHub cubre el requisito sin componentes adicionales. Herramientas especializadas como Marquez o OpenLineage agregarían complejidad sin beneficio incremental dado el volumen y número de fuentes de Fase 2.

### Asunciones

- El linaje columnar exhaustivo (rastrear una columna individual de la fact table hasta el CSV fuente) se considera nice-to-have para esta fase, no obligatorio. El linaje a nivel de modelo (Bronze → Silver → Gold) es el mínimo exigido.
- Si en Fase 3 se agregan múltiples fuentes heterogéneas, se evalúa incorporar OpenLineage como capa estándar entre Dagster y DataHub.

### Puntos a validar con el cliente

1. ¿El requisito de linaje de la adenda implica rastreo columnar, o es suficiente el rastreo a nivel de tabla/modelo?
2. ¿Debe el lineage ser accesible para auditores externos, o es suficiente con que sea visible internamente?

### Referencias

- ADR pendiente: _Estrategia de linaje y gobierno de datos_ (a escribir al inicio de Fase 2, puede unificarse con el ADR de gobierno).
- [DataHub — dbt source](https://datahubproject.io/docs/generated/ingestion/sources/dbt/).

---

## Pregunta 5 — Tipo de carga

> _¿Qué tipo de carga se definirá en el ADR: full, incremental append, merge o upsert?_

### Contexto

El tipo de carga define cómo se incorporan nuevas ejecuciones del pipeline al Data Warehouse. La elección impacta en idempotencia, complejidad de implementación y soporte de correcciones históricas.

Las fuentes de Fase 2 son dos datasets públicos de datos.gob.ar:

- **Producción de pozos no convencionales**: registros mensuales por pozo. El dataset se publica como archivo completo (snapshot), no como delta. Los datos históricos pueden recibir correcciones retroactivas.
- **Listado de pozos**: catálogo de pozos con atributos (operadora, estado, tipo) que pueden cambiar entre publicaciones.

| Tipo | Idempotente | Soporta correcciones | Complejidad |
| ---- | ----------- | -------------------- | ----------- |
| Full (todas las capas) | Sí | Sí | Baja |
| Incremental append | Sí (con watermark) | No | Media |
| Upsert por clave de negocio | Sí | Sí | Media |
| CDC | Depende | Sí | Alta |

### Propuesta

Adoptamos una **estrategia de carga diferenciada por capa**:

**Bronze — carga full del snapshot fuente:**

Cada ejecución descarga el CSV completo de datos.gob.ar y reemplaza la tabla Bronze con su contenido. El dataset fuente es un snapshot completo, no un delta: no existe mecanismo de changelog en la fuente. Descargar y reemplazar es la opción más simple, robusta e idempotente dado el tamaño del dataset (< 500 MB estimado).

**Silver — idempotente por partición de mes:**

Cada partición de mes procesa su propio rango, elimina los registros Silver existentes para ese mes, y los reinserta transformados desde Bronze. Un re-run de la misma partición produce el mismo resultado, lo que satisface el requisito de idempotencia. Este mecanismo también habilita el backfill: rematerializar un rango de particiones de mes en Dagster (`--partition-range`) reprocesa sólo esos meses, con seguimiento visual de qué particiones quedaron materializadas.

**Gold — upsert por clave de negocio:**

La fact table se actualiza con `INSERT ... ON CONFLICT (well_sk, date_sk) DO UPDATE`. Las tablas de dimensiones (`dim_well`, `dim_company`, `dim_date`) usan upsert por surrogate key. Las surrogate keys son un **hash determinístico** de la clave de negocio (`dbt_utils.generate_surrogate_key`), no un contador autoincremental: así el upsert encuentra siempre la misma fila entre ejecuciones y no duplica. Esto soporta correcciones históricas sin duplicar registros y mantiene el estado del DW consistente entre ejecuciones.

**Justificación de full para Bronze:**

Intentar inferir qué registros son nuevos desde un CSV completo agrega complejidad sin beneficio dado que (a) el tamaño del dataset lo permite sin problemas de rendimiento y (b) las correcciones retroactivas en la fuente invalidarían un watermark basado solo en la fecha de publicación.

### Asunciones

- Los archivos CSV de datos.gob.ar pueden descargarse completos sin restricciones de rate limit significativas.
- El volumen total del dataset es manejable para una carga full en Bronze: se estima < 500 MB en texto, < 100 MB comprimido.
- Los datos históricos en el CSV pueden incluir correcciones a períodos pasados, lo que valida la necesidad de upsert en Silver/Gold en lugar de incremental append puro.

### Puntos a validar con el cliente

1. ¿Con qué frecuencia se actualiza el dataset fuente en datos.gob.ar? Esto define el scheduling de los flows.
2. ¿Cuál es la latencia aceptable entre la publicación de nuevos datos y su disponibilidad en el DW?
3. ¿Existen restricciones de ancho de banda o almacenamiento que hagan inviable la carga full de Bronze?

### Referencias

- ADR pendiente: _Estrategia de tipo de carga y procesamiento incremental_ (a escribir al inicio de Fase 2).
- [dbt Docs — Incremental models](https://docs.getdbt.com/docs/build/incremental-models).

---

## Pregunta 6 — Dimensiones de calidad de datos adicionales

> _¿Qué dimensiones de calidad de datos, además de schema y linaje, serán implementadas?_

### Contexto

La adenda requiere chequeos de calidad con al menos **3 dimensiones** persistidas, con **consecuencia operativa** ante fallas. Las dimensiones de schema y linaje se mencionan como ejemplos. Las dimensiones estándar incluyen: schema, completitud, unicidad, validez (rangos y formatos), frescura y consistencia referencial.

### Propuesta

Implementamos cinco dimensiones, chequeadas en la transición Bronze→Silver donde el riesgo de datos sucios es mayor:

| Dimensión | Check concreto para Petrocast |
| --------- | ----------------------------- |
| **Schema** | Las columnas obligatorias (`idpozo`, `fecha`, `prod_pet`) existen en el CSV descargado y tienen el tipo esperado |
| **Completitud** | `well_id IS NOT NULL`, `date IS NOT NULL`, `oil_prod_m3 IS NOT NULL` en > 99% de los registros |
| **Unicidad** | No existen dos filas con el mismo `(well_id, date)` en la capa Silver |
| **Validez de rangos** | `oil_prod_m3 >= 0`, `gas_prod_mm3 >= 0`, `fecha BETWEEN '2010-01-01' AND CURRENT_DATE` |
| **Frescura** | Si el flow corre en el mes M, el DW debe contener al menos un registro del mes M-1 para los pozos activos |

**Herramienta:** dbt tests nativos (`not_null`, `unique`, `accepted_values`) para las dimensiones 1–4. Un test personalizado (`dbt-utils` o macro propia) para frescura.

**Persistencia:**

dbt tiene un mecanismo nativo de `store_failures = true` que persiste las filas fallidas en tablas `dbt_test__audit.test_<nombre>` dentro de PostgreSQL. Esto satisface el requisito de la adenda de que los resultados queden persistidos y no sean sólo asserts en runtime.

### Asunciones

- dbt Core está disponible en el entorno de ejecución de Dagster (vía `dagster-dbt`).
- El umbral de falla para completitud es > 1% de nulos (no cero), dado que el dataset fuente puede tener huecos menores aceptables en campos opcionales (producción de agua, downtime).
- Los tests corren sobre el esquema Silver antes de que dbt ejecute los modelos Gold.

### Puntos a validar con el cliente

1. ¿Cuál es el umbral aceptable de completitud? ¿Se puede publicar un Gold con 98% de completitud si los faltantes corresponden a pozos inactivos?
2. ¿Existen SLAs de frescura definidos (ej: "los datos del mes anterior deben estar disponibles antes del día 5 del mes siguiente")?

### Referencias

- ADR pendiente: _Estrategia de calidad de datos en la capa medallion_ (a escribir al inicio de Fase 2).
- [dbt Docs — Data tests](https://docs.getdbt.com/docs/build/data-tests).
- [dbt Docs — store_failures](https://docs.getdbt.com/reference/resource-configs/store_failures).

---

## Pregunta 7 — Consecuencia operativa ante falla de calidad

> _¿Qué consecuencia operativa se aplicará ante fallas de calidad?_

### Contexto

La adenda exige que si falla un check de calidad, haya una consecuencia operativa concreta: alerta, bloqueo de promoción aguas abajo, o marca de calidad visible. La elección impacta en la confiabilidad de los datos que llegan a Metabase y en la experiencia del equipo de datos cuando algo falla.

### Propuesta

Adoptamos **bloqueo de promoción aguas abajo** como consecuencia primaria, con notificación complementaria por Slack o email.

```
Bronze
  ↓ [check: schema]
Silver ──── si falla → pipeline se detiene; Gold no se actualiza
  ↓ [check: completitud + unicidad + validez + frescura]
Gold ──────  si falla → pipeline se detiene; Metabase muestra datos del run anterior
  ↓
Metabase / DataHub
```

Los checks de calidad se implementan como **dbt tests** envueltos en **asset checks bloqueantes de Dagster**: cuando un check falla, Dagster **detiene la materialización de los assets aguas abajo** (Gold no se actualiza) y marca el asset check como fallido. El estado es visible en la UI de Dagster ("asset bloqueado por check fallido desde [fecha]") y en DataHub. Un **sensor de Dagster** dispara la notificación automática (Slack/email).

**Justificación frente a alternatives:**

La _marca de calidad visible_ (publicar datos pero con un badge de advertencia) es menos severa pero introduce el riesgo de que usuarios no técnicos en Metabase consuman datos sucios sin percatarse. El _bloqueo de promoción_ garantiza que Metabase siempre muestra el último dataset válido conocido, aunque sea un poco más antiguo que el esperado. Esto es preferible en un contexto donde la audiencia incluye usuarios no técnicos (planificadores) que toman decisiones sobre los datos.

La _alerta solamente_ sin bloqueo es insuficiente: si nadie actúa en tiempo, los datos sucios llegan al Gold de todas formas.

### Asunciones

- Dagster puede enviar notificaciones via sensores e integraciones (Slack/email) en su versión open source self-hosted.
- El equipo tiene configurado un canal de Slack o email donde recibir las alertas de pipeline fallido.
- Los datos previos en el Gold (del último run exitoso) permanecen disponibles en Metabase mientras se resuelve la falla.

### Puntos a validar con el cliente

1. ¿Deben las alertas de calidad llegar a un canal de Slack específico, o es suficiente con email?
2. ¿Hay un SLA de resolución para pipelines fallidos (ej: "resolver en menos de 4 horas en horario de negocio")?
3. ¿Deben los usuarios de Metabase recibir algún aviso visible cuando los datos no son del día esperado?

### Referencias

- ADR pendiente: _Estrategia de calidad de datos en la capa medallion_ (mismo ADR que Pregunta 6).
- [Dagster Docs — Asset checks](https://docs.dagster.io/concepts/assets/asset-checks).
- [Dagster Docs — Sensors](https://docs.dagster.io/concepts/partitions-schedules-sensors/sensors).

---

## Pregunta 8 — Roles para los runbooks

> _¿Qué roles serán elegidos para los runbooks?_

### Contexto

La adenda requiere runbooks para al menos dos roles distintos: uno cercano al negocio (Data PM, Data Analyst, Data Owner, Usuario de BI) y uno cercano a la implementación (Data Engineer, Analytics Engineer, Data Steward). Los runbooks deben describir procedimientos concretos del proyecto, no genéricos, e incluir dos decisiones justificadas por rol.

### Propuesta

Escribimos dos runbooks:

**Runbook 1 — Data Engineer: Reprocesamiento histórico (backfill)**

Procedimiento para reprocesar datos de un rango de fechas específico cuando el dataset fuente fue corregido o el pipeline falló en una ejecución pasada. Pasos: verificar el fallo en la UI de Dagster, identificar el rango de particiones de mes afectado, lanzar el backfill de esas particiones desde Dagster (UI o CLI), verificar que los asset checks de calidad pasan y que el Gold fue actualizado, notificar al equipo.

Decisiones a justificar:

- _Funcional:_ por qué el backfill reprocesa desde Bronze (no desde Silver), garantizando que ningún dato corrupto de ejecuciones previas contamine el reprocesamiento.
- _No funcional:_ por qué el backfill corre fuera del horario de negocio para evitar contención de queries en el mismo PostgreSQL que sirve a Metabase.

**Runbook 2 — Data Owner: Resolución de incidente de calidad (decisión de aptitud del dato)**

Procedimiento para el responsable de negocio del dominio "producción de pozos" cuando un check de calidad **bloquea la promoción a Gold** (ver Pregunta 7), o un consumidor reporta un dato sospechoso. El Data Owner no implementa: **decide si el dato es apto para uso**. Pasos: recibir la alerta de pipeline bloqueado; en Dagster, identificar qué asset check falló y revisar la tabla de filas fallidas persistida (`store_failures`); en DataHub, usar el linaje para ver qué dashboards de Metabase y qué usuarios quedan afectados (análisis de impacto); decidir entre (a) mantener el bloqueo y pedir reproceso al Data Engineer, (b) aprobar una excepción documentada, o (c) marcar el dato como _deprecated_ en DataHub; comunicar la decisión a los consumidores; registrar la decisión (quién, cuándo, por qué).

Decisiones a justificar:

- _Funcional:_ por qué el Data Owner **define el umbral de "aptitud para uso"** (ej. permitir publicar Gold con 98% de completitud si los faltantes corresponden a pozos inactivos) — es una regla de negocio, no técnica, y la owna porque responde ante los usuarios no técnicos si el dato está mal.
- _No funcional:_ por qué el Data Owner **fija el SLA de resolución de incidentes** (ej. < 4 h hábiles) balanceando frescura vs confiabilidad — su incentivo es que los planificadores confíen en los dashboards, y un dato viejo pero confiable le cuesta menos que uno fresco pero sucio.

Los runbooks se escriben en `docs/runbooks/data-engineer.md` y `docs/runbooks/data-owner.md` una vez que el pipeline esté implementado, para que reflejen la realidad del sistema.

### Asunciones

- Los runbooks se revisan al final de Fase 2, no al inicio: deben describir procedimientos reales, con comandos concretos y URLs del entorno desplegado.
- El perfil de "Analytics Engineer" (quien escribe modelos dbt) no requiere un runbook propio en esta fase; su trabajo se documenta en el README del directorio dbt.

### Puntos a validar con el cliente

1. ¿Existe un perfil de Data Owner o Data Steward en la organización que deba tener su propio runbook en Fase 3?
2. ¿El equipo docente espera ver al menos un runbook de rol técnico y uno de rol de negocio, o puede haber dos técnicos?

### Referencias

- Estructura de runbooks definida en el PRD v0.2, sección "Runbooks".
- `docs/runbooks/` (a crear al inicio de Fase 2).

---

## Pregunta 9 — Semantic layer (bonus)

> _¿Se implementará semantic layer como bonus?_

### Contexto

El semantic layer es una capa de abstracción que expone métricas de negocio definidas una sola vez y reutilizables en múltiples herramientas. El objetivo es evitar que cada herramienta (Metabase, la API, notebooks) defina "producción mensual promedio por pozo" de forma diferente.

Opciones:

- **dbt Semantic Layer + MetricFlow**: define métricas como `avg_monthly_production` en el repo dbt; consumibles por herramientas compatibles.
- **Cube.dev**: servidor semántico standalone, más poderoso pero agrega otro componente operativo.
- **Vistas lógicas en PostgreSQL**: `CREATE VIEW gold.v_monthly_production AS ...`; simple pero no reutilizable entre herramientas externas.
- **No implementar**: Fase 2 ya tiene suficiente scope.

### Propuesta

No implementamos semantic layer formal en Fase 2. Como alternativa liviana, creamos **vistas SQL en el esquema `gold`** que centralizan la lógica de las métricas más consultadas.

**Justificación:**

El scope de Fase 2 ya incluye extracción, pipeline medallion completo, DW con star schema, Metabase, DataHub, chequeos de calidad con persistencia, linaje, dos runbooks y seis ADRs. Agregar dbt Semantic Layer incrementa el riesgo de no terminar los ítems obligatorios. Además, dbt Semantic Layer con MetricFlow requiere dbt Cloud o una integración no trivial; no es un agregado gratuito sobre dbt Core.

Las métricas necesarias para la demo de Fase 2 (producción mensual por pozo, evolución histórica, top pozos) se pueden definir directamente en Metabase o como vistas en Gold sin una capa semántica independiente.

Si en Fase 3 se implementa un motor de ML que consume features del DW, la introducción de un semantic layer cobra más sentido como capa de features consistente entre el pipeline de entrenamiento y la API de predicción.

### Asunciones

- El bonus no es necesario para aprobar, y el riesgo de comprometer los ítems obligatorios supera el beneficio de nota.
- Las vistas en `gold` (`gold.v_monthly_production_by_well`, `gold.v_top_wells_by_volume`) son un compromiso aceptable que cubre la intención del bonus sin la complejidad de dbt Semantic Layer.

### Puntos a validar con el cliente

1. ¿El equipo docente valora el semantic layer como diferenciador de nota, o es considerado un nice-to-have menor?
2. ¿En Fase 3, cuando se integre el modelo ML, sería el momento adecuado para introducir MetricFlow como capa de features?

---

## Síntesis

Las decisiones de este Addendum siguen un principio común: **minimizar la complejidad operativa preservando el rigor arquitectónico exigido por la adenda**.

El stack propuesto para Fase 2:

```
datos.gob.ar (CSV — producción de pozos + listado de pozos)
    ↓
Dagster — extracción (assets particionados por mes), scheduling, retries con backoff
    ↓
schema: bronze (PostgreSQL, full refresh por ejecución)
    ↓ dbt tests: schema
schema: silver (PostgreSQL, idempotente por partición de mes)
    ↓ dbt tests: completitud + unicidad + validez + frescura (asset checks bloqueantes)
schema: gold (PostgreSQL, star schema: fact_production, dim_well, dim_company, dim_date)
    ├── Metabase OSS (BI para usuarios no técnicos — puerto 3001)
    └── DataHub (catálogo + linaje dbt + estado de ingesta) — bajo demanda
         ↑
    Dagster UI (estado de assets/particiones, logs, historial — puerto 3000)

apps/api (FastAPI) — repositories/ se conecta al esquema gold en Fase 2
```

Resumen de decisiones:

| Decisión | Elección | Motivación principal |
| -------- | -------- | -------------------- |
| Orquestación | Dagster 1.x | Modelo de assets afín a medallion; integración nativa con dbt (`dagster-dbt`); backfill por particiones |
| Transformaciones | dbt Core | Linaje SQL automático; tests persistidos con `store_failures` |
| Data Warehouse | PostgreSQL 16 (schemas bronze/silver/gold) | Ya definido en ADR-0012; sin componente nuevo |
| Modelo dimensional | Star schema: `fact_production` + `dim_well`, `dim_company`, `dim_date`; SK hash determinístico; SCD Tipo 1 | Operadora como dimensión propia (filtro de negocio frecuente); SK hash compatible con upsert |
| BI | Metabase OSS | UI sin SQL; una imagen Docker; ideal para no-técnicos |
| Gobierno de datos | DataHub | Herramienta explícitamente requerida por la adenda; riesgo de evaluación cero |
| Carga Bronze | Full refresh | Idempotente; simple; validado por naturaleza del CSV fuente |
| Carga Silver/Gold | Idempotente por partición + upsert | Soporta correcciones históricas |
| Calidad | 5 dimensiones, `store_failures = true` | Resultados persistidos; bloqueo de promoción ante falla |
| Consecuencia calidad | Bloqueo de promoción (asset checks Dagster) + notificación | Protege a usuarios no técnicos de datos sucios en Metabase |
| Runbooks | Data Engineer + Data Owner | Cubre un rol técnico y uno de negocio |
| Semantic layer | No en Fase 2 (vistas SQL como alternativa liviana) | Reduce riesgo de no entregar obligatorios |

## Conexión con la arquitectura de Fase 1

El repositorio layer de la API (`apps/api/src/repositories/`) que en Fase 1 retorna datos mock está diseñado explícitamente para ser reemplazado en Fase 2 por conexiones al DW real, según lo anticipó ADR-0020. En Fase 2, `forecast_repository.py` y `well_repository.py` se conectan al esquema `gold` de PostgreSQL. Esto no es un cambio de arquitectura sino la continuación del diseño original.

## Cambios respecto al PRD v0.2

Este Addendum **no modifica** el PRD v0.2. Agrega precisiones que deben leerse junto con él. Si alguna respuesta del Addendum requiriera modificar requerimientos del PRD, se emitiría un PRD v0.3 con el delta explícito.

## Historial de versiones

| Versión | Fecha | Cambios |
| ------- | ----- | ------- |
| v0.3 | 2026-06-01 | Versión inicial con respuestas a las 9 preguntas abiertas de la adenda técnica de Fase 2. |
| v0.3.1 | 2026-06-03 | Revisión de stack: orquestación **Dagster** (era Prefect) por afinidad con medallion e integración nativa con dbt; gobierno **DataHub** (era OpenMetadata) por ser la herramienta requerida por la adenda; modelo dimensional explicitado con **`dim_company`** como dimensión propia y surrogate keys hash; backfill y bloqueo de calidad vía particiones y asset checks de Dagster; runbook de **Data Owner** (era Analista de BI). |
