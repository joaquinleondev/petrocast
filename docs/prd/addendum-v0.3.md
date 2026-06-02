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

Adoptamos **Prefect 3.x** como herramienta de orquestación, complementado con **dbt Core** para las transformaciones SQL entre capas.

**Justificación:**

Prefect es la opción con menor sobrecarga operativa para los tres entornos que corren en EC2 `t3.small`. Airflow requiere al menos scheduler, webserver y una base de datos propia, lo que compite en recursos con el resto del stack de Fase 2 (PostgreSQL, Metabase, OpenMetadata). Dagster es técnicamente superior para arquitecturas medallion, pero tiene una curva de aprendizaje mayor dado que su modelo de assets es más distinto al paradigma de scripts secuenciales.

El modelo de flows de Prefect es idiomático Python: un flujo de ingesta se expresa como una función decorada con `@flow`, sus pasos como funciones con `@task`. Los retries con backoff exponencial son un atributo del decorador: `@task(retries=3, retry_delay_seconds=exponential(base=10, multiplier=1))`. Esto reduce la curva de aprendizaje para un equipo de tres personas en un plazo acotado.

El procedimiento de backfill se implementa como un flow parametrizado: `extract_flow(date_start="2020-01-01", date_end="2024-12-31")` puede invocarse desde la UI de Prefect o por CLI para reprocesar cualquier rango histórico, cubriendo el requisito explícito de la adenda.

**Relación con Airflow:**

Airflow es el estándar de la industria y sería la elección natural en un entorno productivo con infraestructura dedicada. Para este proyecto, el overhead operativo de Airflow supera el beneficio dado el tamaño del equipo y la restricción de infra. El ADR de orquestación documenta esta comparación con detalle y puede usarse en la defensa oral.

**Rol de dbt en el stack:**

Las transformaciones Bronze→Silver→Gold se implementan como modelos dbt, que Prefect invoca mediante el integrador `prefect-dbt`. Esto separa responsabilidades: Prefect maneja el scheduling, retries y observabilidad del flujo; dbt maneja las transformaciones SQL, los tests de calidad y genera el grafo de lineage automáticamente.

### Asunciones

- El servidor Prefect corre en el mismo EC2 que el resto del stack (no se usa Prefect Cloud).
- Las transformaciones son SQL-first (dbt), no PySpark ni operaciones de alta cardinalidad que requieran un motor distribuido.
- El volumen de datos de las fuentes definidas (dos CSVs de datos.gob.ar) es manejable en un solo nodo PostgreSQL: el dataset de producción de pozos no convencionales tiene del orden de millones de filas históricas, volumen trivial para PostgreSQL en una t3.small.

### Puntos a validar con el cliente

1. ¿Existe una herramienta de orquestación ya en uso en la organización que sea preferible adoptar (Airflow, Databricks Workflows, AWS Glue)?
2. ¿El flujo de extracción debe soportar fuentes adicionales en Fase 3 (SCADA, PI System, SAP)? Esto podría favorecer Airflow o Dagster por su ecosistema de conectores.
3. ¿Se requiere scheduling con frecuencia sub-horaria o near-realtime? Prefect lo soporta, pero Airflow tiene más operadores especializados para esos casos.

### Referencias

- ADR pendiente: _Selección de herramienta de orquestación_ (Prefect vs Airflow vs Dagster, a escribir al inicio de Fase 2).
- [Prefect 3.x Docs](https://docs.prefect.io/) — deploy guide, retry decorators, parametrización.
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

Adoptamos **OpenMetadata** como plataforma de gobierno de datos, complementada con el lineage nativo de dbt.

**Justificación frente a DataHub:**

DataHub es la herramienta de referencia mencionada en clase y es el estándar en la industria para data governance empresarial. Sin embargo, DataHub requiere Kafka, Elasticsearch y MySQL como dependencias propias — en total ~6 contenedores y ~4 GB RAM, lo que excede la capacidad de la EC2 t3.small cuando corre junto a PostgreSQL, Prefect, Metabase y la API. OpenMetadata logra las mismas tres capacidades requeridas con un footprint significativamente menor (~2 GB RAM, sin Kafka).

OpenMetadata cubre los tres requisitos de la adenda:

1. **Workflows**: tiene una sección "Ingestion Pipelines" que muestra el estado y última ejecución del conector de PostgreSQL. Se puede configurar el conector para que catalogue automáticamente las tablas del esquema Gold.
2. **Datos en el DW**: el catálogo expone todas las tablas con descripciones de columnas, tipos y estadísticas básicas. Las tablas del star schema son navegables por un usuario no técnico.
3. **Última actualización**: la metadata de cada tabla incluye el timestamp de la última ingesta y el número de filas.

El lineage SQL detallado (qué columna de Bronze alimenta qué columna de Gold) se obtiene del grafo de dbt (`dbt docs generate`) y se importa a OpenMetadata via el conector dbt nativo.

**Nota sobre la elección frente a la recomendación de la cátedra:**

DataHub es válido y sería la elección en un entorno con infraestructura dedicada. La elección de OpenMetadata como alternativa cumple los mismos requisitos funcionales y está debidamente justificada en el ADR de gobierno, lo que tiene más valor pedagógico que adoptar DataHub sin análisis.

### Asunciones

- OpenMetadata se levanta en Docker Compose junto al resto del stack de datos.
- El lineage de flujos de Prefect se anota manualmente en la metadata de cada tabla (qué flow la generó y cuándo), o mediante el emisor de eventos de Prefect si se implementa la integración.
- El lineage SQL detallado se obtiene de dbt y se importa a OpenMetadata vía el conector dbt.

### Puntos a validar con el cliente

1. ¿La cátedra evalúa con DataHub específicamente, o acepta cualquier plataforma de gobierno si está debidamente justificada?
2. ¿Se requiere integración con herramientas de governance corporativas existentes (Collibra, Alation, Informatica)?
3. ¿El lineage columnar (no solo a nivel tabla) es un requisito para esta fase?

### Referencias

- ADR pendiente: _Selección de plataforma de gobierno de datos_ (OpenMetadata vs DataHub, a escribir al inicio de Fase 2).
- [OpenMetadata Docs — Docker Compose quickstart](https://docs.open-metadata.org/quick-start/local-docker-deployment).
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
| Linaje de flujo | **Prefect** | Cada flow run registra qué tablas se cargaron, en qué rango de fechas, y con qué resultado |
| Linaje SQL (modelo) | **dbt** | `dbt docs generate` produce el grafo de dependencias entre modelos Bronze/Silver/Gold; visible en `dbt docs serve` |
| Catálogo + linaje integrado | **OpenMetadata** | Ingesta el grafo de dbt via conector; lo presenta en una UI navegable junto al catálogo de tablas |

No se añade una herramienta separada para linaje porque la combinación Prefect + dbt + OpenMetadata cubre el requisito sin componentes adicionales. Herramientas especializadas como Marquez o OpenLineage agregarían complejidad sin beneficio incremental dado el volumen y número de fuentes de Fase 2.

### Asunciones

- El linaje columnar exhaustivo (rastrear una columna individual de la fact table hasta el CSV fuente) se considera nice-to-have para esta fase, no obligatorio. El linaje a nivel de modelo (Bronze → Silver → Gold) es el mínimo exigido.
- Si en Fase 3 se agregan múltiples fuentes heterogéneas, se evalúa incorporar OpenLineage como capa estándar entre Prefect y OpenMetadata.

### Puntos a validar con el cliente

1. ¿El requisito de linaje de la adenda implica rastreo columnar, o es suficiente el rastreo a nivel de tabla/modelo?
2. ¿Debe el lineage ser accesible para auditores externos, o es suficiente con que sea visible internamente?

### Referencias

- ADR pendiente: _Estrategia de linaje y gobierno de datos_ (a escribir al inicio de Fase 2, puede unificarse con el ADR de gobierno).
- [OpenMetadata — dbt connector](https://docs.open-metadata.org/connectors/pipeline/dbt).

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

Cada ejecución procesa el rango de meses indicado por parámetro (`date_start`, `date_end`), elimina los registros Silver existentes para ese rango, y los reinserta transformados desde Bronze. Un re-run del mismo período produce el mismo resultado, lo que satisface el requisito de idempotencia. Este mecanismo también permite el backfill: invocar el flow con un rango histórico reprocesa sólo ese rango.

**Gold — upsert por clave de negocio:**

La fact table se actualiza con `INSERT ... ON CONFLICT (well_id, date) DO UPDATE`. Las tablas de dimensiones (`dim_well`, `dim_date`) usan upsert por surrogate key. Esto soporta correcciones históricas sin duplicar registros y mantiene el estado del DW consistente entre ejecuciones.

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

- dbt Core está disponible en el entorno de ejecución de los flows de Prefect.
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
Metabase / OpenMetadata
```

Cuando un check falla, Prefect marca el flow como `FAILED`. El estado visible en la UI de Prefect y en OpenMetadata es "pipeline con error desde [fecha]". El equipo recibe una notificación automática vía webhook de Prefect.

**Justificación frente a alternatives:**

La _marca de calidad visible_ (publicar datos pero con un badge de advertencia) es menos severa pero introduce el riesgo de que usuarios no técnicos en Metabase consuman datos sucios sin percatarse. El _bloqueo de promoción_ garantiza que Metabase siempre muestra el último dataset válido conocido, aunque sea un poco más antiguo que el esperado. Esto es preferible en un contexto donde la audiencia incluye usuarios no técnicos (planificadores) que toman decisiones sobre los datos.

La _alerta solamente_ sin bloqueo es insuficiente: si nadie actúa en tiempo, los datos sucios llegan al Gold de todas formas.

### Asunciones

- Prefect puede enviar notificaciones via webhook o integración de Slack en el plan open source (self-hosted).
- El equipo tiene configurado un canal de Slack o email donde recibir las alertas de pipeline fallido.
- Los datos previos en el Gold (del último run exitoso) permanecen disponibles en Metabase mientras se resuelve la falla.

### Puntos a validar con el cliente

1. ¿Deben las alertas de calidad llegar a un canal de Slack específico, o es suficiente con email?
2. ¿Hay un SLA de resolución para pipelines fallidos (ej: "resolver en menos de 4 horas en horario de negocio")?
3. ¿Deben los usuarios de Metabase recibir algún aviso visible cuando los datos no son del día esperado?

### Referencias

- ADR pendiente: _Estrategia de calidad de datos en la capa medallion_ (mismo ADR que Pregunta 6).
- [Prefect Docs — Notifications y Automations](https://docs.prefect.io/3.x/automate/events/automations-triggers/).

---

## Pregunta 8 — Roles para los runbooks

> _¿Qué roles serán elegidos para los runbooks?_

### Contexto

La adenda requiere runbooks para al menos dos roles distintos: uno cercano al negocio (Data PM, Data Analyst, Data Owner, Usuario de BI) y uno cercano a la implementación (Data Engineer, Analytics Engineer, Data Steward). Los runbooks deben describir procedimientos concretos del proyecto, no genéricos, e incluir dos decisiones justificadas por rol.

### Propuesta

Escribimos dos runbooks:

**Runbook 1 — Data Engineer: Reprocesamiento histórico (backfill)**

Procedimiento para reprocesar datos de un rango de fechas específico cuando el dataset fuente fue corregido o el pipeline falló en una ejecución pasada. Pasos: verificar el fallo en la UI de Prefect, identificar el rango afectado, invocar el backfill flow con los parámetros correctos, verificar que los checks de calidad pasan y que el Gold fue actualizado, notificar al equipo.

Decisiones a justificar:

- _Funcional:_ por qué el backfill reprocesa desde Bronze (no desde Silver), garantizando que ningún dato corrupto de ejecuciones previas contamine el reprocesamiento.
- _No funcional:_ por qué el backfill corre fuera del horario de negocio para evitar contención de queries en el mismo PostgreSQL que sirve a Metabase.

**Runbook 2 — Analista de BI / Data Analyst: Construcción de un nuevo dashboard en Metabase**

Procedimiento para que un analista no técnico acceda a Metabase, explore el modelo estrella del Gold layer, y publique un dashboard de seguimiento de producción por cuenca. Pasos: acceder a Metabase en la URL del entorno, seleccionar la tabla `fact_production` del esquema `gold`, construir una pregunta con el Query Builder visual, crear un dashboard y compartirlo.

Decisiones a justificar:

- _Funcional:_ por qué el modelo estrella expuesto tiene `dim_well` como única dimensión no temporal en Fase 2 (en lugar de dimensiones de operadora y cuenca separadas), y qué impacto tiene en la granularidad de los filtros disponibles.
- _No funcional:_ por qué el usuario de Metabase tiene permisos de sólo lectura sobre el esquema `gold` y no sobre `bronze` ni `silver`, protegiendo los datos intermedios de modificaciones accidentales.

Los runbooks se escriben en `docs/runbooks/data-engineer.md` y `docs/runbooks/bi-analyst.md` una vez que el pipeline esté implementado, para que reflejen la realidad del sistema.

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

El scope de Fase 2 ya incluye extracción, pipeline medallion completo, DW con star schema, Metabase, OpenMetadata, chequeos de calidad con persistencia, linaje, dos runbooks y seis ADRs. Agregar dbt Semantic Layer incrementa el riesgo de no terminar los ítems obligatorios. Además, dbt Semantic Layer con MetricFlow requiere dbt Cloud o una integración no trivial; no es un agregado gratuito sobre dbt Core.

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
Prefect flow — extracción, scheduling, retries con backoff
    ↓
schema: bronze (PostgreSQL, full refresh por ejecución)
    ↓ dbt tests: schema
schema: silver (PostgreSQL, idempotente por partición de mes)
    ↓ dbt tests: completitud + unicidad + validez + frescura
schema: gold (PostgreSQL, star schema: fact_production, dim_well, dim_date)
    ├── Metabase OSS (BI para usuarios no técnicos — puerto 3001)
    └── OpenMetadata (catálogo + linaje dbt + estado de workflows)
         ↑
    Prefect UI (estado de flows, logs, historial — puerto 4200)

apps/api (FastAPI) — repositories/ se conecta al esquema gold en Fase 2
```

Resumen de decisiones:

| Decisión | Elección | Motivación principal |
| -------- | -------- | -------------------- |
| Orquestación | Prefect 3.x | Menor overhead operativo que Airflow; setup de un proceso |
| Transformaciones | dbt Core | Linaje SQL automático; tests persistidos con `store_failures` |
| Data Warehouse | PostgreSQL 16 (schemas bronze/silver/gold) | Ya definido en ADR-0012; sin componente nuevo |
| BI | Metabase OSS | UI sin SQL; una imagen Docker; ideal para no-técnicos |
| Gobierno de datos | OpenMetadata | Catálogo + linaje + freshness; menor footprint que DataHub |
| Carga Bronze | Full refresh | Idempotente; simple; validado por naturaleza del CSV fuente |
| Carga Silver/Gold | Idempotente por partición + upsert | Soporta correcciones históricas |
| Calidad | 5 dimensiones, `store_failures = true` | Resultados persistidos; bloqueo de promoción ante falla |
| Consecuencia calidad | Bloqueo de promoción + notificación | Protege a usuarios no técnicos de datos sucios en Metabase |
| Runbooks | Data Engineer + Analista de BI | Cubre un rol técnico y uno de negocio |
| Semantic layer | No en Fase 2 (vistas SQL como alternativa liviana) | Reduce riesgo de no entregar obligatorios |

## Conexión con la arquitectura de Fase 1

El repositorio layer de la API (`apps/api/src/repositories/`) que en Fase 1 retorna datos mock está diseñado explícitamente para ser reemplazado en Fase 2 por conexiones al DW real, según lo anticipó ADR-0020. En Fase 2, `forecast_repository.py` y `well_repository.py` se conectan al esquema `gold` de PostgreSQL. Esto no es un cambio de arquitectura sino la continuación del diseño original.

## Cambios respecto al PRD v0.2

Este Addendum **no modifica** el PRD v0.2. Agrega precisiones que deben leerse junto con él. Si alguna respuesta del Addendum requiriera modificar requerimientos del PRD, se emitiría un PRD v0.3 con el delta explícito.

## Historial de versiones

| Versión | Fecha | Cambios |
| ------- | ----- | ------- |
| v0.3 | 2026-06-01 | Versión inicial con respuestas a las 9 preguntas abiertas de la adenda técnica de Fase 2. |
