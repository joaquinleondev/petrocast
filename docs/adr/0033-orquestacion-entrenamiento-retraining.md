# ADR-0033: Orquestación del entrenamiento y retraining con Dagster

- **Estado:** Aceptado
- **Fecha:** 2026-07-02
- **Autores:** Santino Domato
- **Decisores:** Equipo Petrocast

## Contexto y problema

Fase 3 incorpora un pipeline de ML que materializa features persistidas,
entrena un modelo global de producción mensual, evalúa el candidato y, si
supera los gates de calidad, lo publica en el registry. La adenda exige que
este proceso pueda repetirse para una fecha dada y que el entrenamiento y el
despliegue del modelo se ejecuten de forma recurrente y automática.

El stack heredado de Fase 2 ya usa Dagster como orquestador asset-céntrico de
la ingesta y las transformaciones `bronze` → `silver` → `gold` (ADR-0028). Sus
assets tienen particiones mensuales por período de producción, retries
declarativos, asset checks y observabilidad en la UI. Fase 3 debe extender ese
grafo sin sumar un segundo plano de control ni duplicar scheduling, logs y
estado en otra herramienta.

ADR-0030 define un único modelo LightGBM global que predice producción de
petróleo por pozo y mes. ADR-0031 define el feature store en PostgreSQL con
clave `(well_id, as_of_date)` y exige point-in-time correctness: una fila de
features para un corte sólo puede usar datos con `production_month <
as_of_date`. ADR-0032 fija MLflow para tracking y registry, y ADR-0034 establece
que el despliegue recurrente consiste en mover el alias `champion`, no en
reconstruir o redesplegar el contenedor de la API.

La decisión pendiente es cómo representar el corte de entrenamiento, cómo
encadenar la materialización de features, training, evaluación y promoción,
y cómo ofrecer tanto un trigger automático como uno manual con la misma
semántica reproducible.

## Drivers de la decisión

- **Reproducibilidad por fecha de corte.** Repetir un entrenamiento para el
  mismo `as_of_date` debe seleccionar el mismo universo temporal de features.
- **Point-in-time correctness.** El orquestador debe preservar la regla de no
  usar datos posteriores al corte definida en ADR-0031.
- **Automatización recurrente.** Debe existir un schedule versionado como
  código, con una ejecución mensual y un mecanismo seguro contra ticks
  duplicados.
- **Trigger manual equivalente.** La UI y la CLI deben poder lanzar exactamente
  el mismo job para una partición elegida, sin un script alternativo.
- **Reuso del stack.** Dagster, PostgreSQL, dbt y los assets medallion ya están
  desplegados; no se justifica operar otro scheduler para un solo pipeline ML.
- **Retries selectivos.** Los errores transitorios deben reintentarse con
  backoff, pero los fallos determinísticos de datos o calidad no deben ocultarse
  detrás de reintentos automáticos.
- **Observabilidad y trazabilidad.** Cada run debe exponer corte, versión de
  features, modelo resultante, métricas y estado de promoción.
- **Simplicidad operativa.** El equipo es de tres personas, no hay servicio live
  obligatorio y el flujo debe poder demostrarse localmente.

## Opciones consideradas

1. **Dagster assets/jobs con `ScheduleDefinition`.** Extender el grafo actual
   con assets ML particionados por `as_of_date`, un job de retraining y un
   schedule mensual.
2. **GitHub Actions con workflow programado.** Ejecutar training desde un
   `schedule` de Actions y aceptar `workflow_dispatch` para corridas manuales.
3. **Cron dentro del contenedor.** Mantener un proceso cron que invoque scripts
   de features, training, evaluación y promoción.
4. **Airflow o Prefect para ML.** Incorporar un segundo orquestador dedicado al
   pipeline de entrenamiento.

## Decisión

Elegimos **Dagster assets/jobs con `ScheduleDefinition`**. La cadena de
retraining se modelará como assets particionados y se expondrá mediante un único
job, usado tanto por el schedule automático como por los triggers manuales.

### Grafo de retraining

El job `retraining_job` encadena estas responsabilidades:

1. **Features:** materializa el corte solicitado en el schema `features` desde
   los assets `gold` ya validados.
2. **Training:** entrena el candidato global con las features del corte y
   registra parámetros, artefactos y tags en MLflow.
3. **Evaluación:** ejecuta el backtesting y los gates definidos en ADR-0030
   contra los baselines naive y Arps.
4. **Promoción:** registra la versión del modelo y mueve el alias `champion`
   únicamente cuando todos los gates bloqueantes pasan.

Cada límite será un asset explícito para que Dagster pueda mostrar linaje,
metadata y estado individual, y para que una recuperación continúe desde el
paso fallido sin repetir trabajo upstream exitoso. La promoción no se mezcla
con el entrenamiento: un candidato fallido queda trazable en MLflow, pero no
altera el modelo servido.

### `as_of_date` como partición

Todos los assets del job comparten una `MonthlyPartitionsDefinition`. La clave
de partición usa formato `YYYY-MM-01` y representa el primer día del mes que se
quiere pronosticar. Por ejemplo, la partición `2026-07-01`:

- materializa features usando únicamente datos con `production_month <
  2026-07-01`;
- entrena y evalúa el modelo con ese mismo corte;
- produce pronósticos cuyo primer período posible es julio de 2026;
- registra `as_of_date=2026-07-01` como tag obligatorio del run y metadata del
  modelo.

La granularidad mensual coincide con el dato fuente y con el feature store. No
se crean particiones diarias vacías para una serie que sólo cambia por mes. Si
el usuario pide repetir el proceso para un día intermedio, el contrato
normaliza el corte al primer día del mes correspondiente y lo muestra antes de
lanzar el run; no se aceptan dos claves distintas para el mismo estado de datos.

Rematerializar una partición no sobrescribe artefactos de MLflow: genera un
nuevo run y, si corresponde, una nueva versión de modelo vinculada al mismo
`as_of_date`. Las tablas de features siguen siendo idempotentes por partición;
el alias `champion` sólo cambia después de una evaluación aprobada.

### Schedule automático

Se agregará el primer `ScheduleDefinition` del repositorio para
`retraining_job`, con frecuencia mensual. El valor inicial será
`0 6 5 * *` en UTC: el día 5 de cada mes a las 06:00, el schedule solicita la
partición cuyo `as_of_date` es el primer día de ese mes. El margen de cinco días
reduce el riesgo de entrenar mientras todavía se actualiza el snapshot mensual
de la fuente.

Cada tick emitirá un `RunRequest` con:

- la clave de partición calculada;
- un `run_key` estable con formato `retraining:<as_of_date>`, para que Dagster
  no lance dos veces el mismo tick;
- tags con `as_of_date`, origen `schedule` y versión del código desplegado.

El cron y la zona horaria quedan versionados en código. Cambiar la frecuencia
requiere un PR porque modifica la política operativa. Si los assets `gold` o sus
checks de calidad no están listos para el corte, el job falla antes del
training y no promueve ningún modelo. Un operador puede relanzar la partición
cuando el dato quede disponible.

### Trigger manual

El mismo `retraining_job` se podrá ejecutar desde la UI de Dagster o desde la
CLI seleccionando una partición `as_of_date`. No habrá un script de training
paralelo con reglas distintas. El operador podrá:

- materializar un corte histórico para backtesting o auditoría;
- repetir el corte vigente después de una corrección de datos;
- recuperar un run fallido desde el asset pendiente;
- generar un nuevo candidato sin mover `champion` si los gates no pasan.

Los triggers manuales usan los mismos recursos, configuración, validaciones y
tags que el schedule; sólo cambia el tag de origen a `manual`.

### Relación con los assets de Fase 2

Los assets ML extienden el linaje existente en lugar de duplicarlo:

`bronze` → `silver` → `gold` → `features` → `training` → `evaluation` →
`promotion`.

Las particiones tienen significados distintos y no se fuerzan a una relación
uno-a-uno:

- Fase 2 particiona `silver` y `gold` por **mes de producción**.
- Fase 3 particiona features y training por **fecha de corte de conocimiento**.
- Una partición de training consume todas las particiones de producción
  anteriores a `as_of_date`, no sólo la que comparte su mes calendario.

El schedule de retraining no vuelve a descargar automáticamente todos los
snapshots ni reconstruye el warehouse completo. Consume `gold` como upstream y
verifica que sus materializaciones y asset checks estén disponibles. Para una
recuperación end-to-end, el operador puede materializar primero el rango
necesario de Fase 2 y luego lanzar la partición de retraining. Esta separación
evita convertir cada entrenamiento en un full refresh costoso y conserva la
capacidad de backfill ya definida en ADR-0026 y ADR-0028.

### Retries y recuperación

Se mantiene el patrón de Fase 2 para fallos transitorios:

- `RetryPolicy(max_retries=3, delay=30,
  backoff=Backoff.EXPONENTIAL)` en operaciones de I/O y llamadas externas,
  como lectura del warehouse, escritura de artefactos y comunicación con
  MLflow/S3;
- reejecución desde el asset fallido cuando los upstream de la misma partición
  ya están materializados;
- promoción idempotente: reintentar la operación sólo puede apuntar `champion`
  a la versión aprobada por ese run, nunca crear una aprobación nueva.

No se reintentan automáticamente errores determinísticos: violaciones de
point-in-time correctness, datasets vacíos, tests dbt fallidos, métricas por
debajo de los gates o configuración inválida. Esos casos terminan el run como
fallido y requieren corrección o decisión humana.

### Observabilidad

Dagster será la vista operativa del workflow y MLflow la vista experimental.
Cada materialización publicará, según corresponda:

- `as_of_date`, origen del trigger y `dagster_run_id`;
- cantidad de pozos y filas de features;
- rango mínimo y máximo de `production_month` consumido;
- versión/hash de features y commit o imagen ejecutada;
- identificador del run de MLflow y versión del modelo candidato;
- métricas principales, resultado de cada gate y estado de promoción;
- versión anterior y nueva del alias `champion` cuando haya promoción.

La UI de Dagster muestra timeline, logs, estado por partición y el asset exacto
que falló. MLflow conserva parámetros, métricas y artefactos para comparar
candidatos. Los fallos bloqueantes reutilizarán el mecanismo de notificación
del pipeline de datos cuando exista un webhook configurado; sin webhook, el
estado seguirá visible en Dagster sin impedir la ejecución local.

## Consecuencias

**Positivas:**

- Se cumple el requisito de repetir training para una fecha mediante una
  partición explícita y reproducible.
- Schedule y trigger manual usan el mismo job; no existen dos caminos con
  comportamiento divergente.
- El grafo de Fase 2 se extiende hasta modelo y promoción con linaje visible de
  punta a punta.
- Retries, logs, particiones y recuperación reutilizan capacidades ya operadas
  por el equipo.
- Un fallo de evaluación deja evidencia del candidato sin afectar al champion.
- El despliegue recurrente del modelo ocurre al mover el alias del registry, sin
  rebuild ni redeploy de FastAPI.

**Negativas / trade-offs asumidos:**

- Dagster pasa a coordinar también ML y aumenta la importancia operativa de su
  instancia y base de estado.
- Una partición mensual no distingue dos cortes diarios dentro del mismo mes;
  es deliberado porque la fuente y el target son mensuales.
- El schedule depende de que `gold` esté actualizado y validado. Si la fuente se
  publica tarde, el run falla y debe relanzarse; no se adivina disponibilidad
  mediante esperas silenciosas.
- Rematerializar el mismo `as_of_date` crea nuevos runs y versiones de modelo;
  MLflow debe conservar tags suficientes para distinguirlos.
- El cron del día 5 es una política inicial. Si cambia la cadencia de la fuente,
  habrá que modificarla y volver a validar el tiempo de disponibilidad.

**Neutras:**

- Este ADR no define features, algoritmo ni umbrales; los toma de ADR-0030 y
  ADR-0031.
- Tampoco define el backend de tracking ni el serving; usa MLflow y el alias
  `champion` según ADR-0032 y ADR-0034.
- GitHub Actions sigue siendo responsable de validar, construir y desplegar el
  código del pipeline. No se convierte en el scheduler de retraining.

## Migración e implementación incremental

1. Registrar el asset de features con la partición mensual `as_of_date` y
   metadata de corte, filas y versión.
2. Agregar assets separados para training, evaluación y promoción, todos sobre
   la misma definición de particiones.
3. Definir `retraining_job` con la selección completa y registrar el primer
   `ScheduleDefinition` en `Definitions`.
4. Validar primero un trigger manual con fixtures y un backend de MLflow local;
   verificar que un gate fallido no mueva `champion`.
5. Habilitar el schedule en el ambiente de demostración y confirmar deduplicado
   por `run_key`, retries y metadata en la UI.
6. Validar promoción y rollback re-apuntando el alias a una versión anterior,
   sin redesplegar la API.

La migración es aditiva: no modifica las particiones ni la semántica de los
assets de Fase 2. Si el schedule se deshabilita, el job manual continúa
disponible y no afecta el pipeline de datos existente.

## Pros y contras de cada opción

### Dagster assets/jobs con `ScheduleDefinition` (elegida)

- ✅ Reusa el orquestador, la UI y el modelo asset-céntrico existentes.
- ✅ Particiones, retries, backfills, metadata y linaje son de primera clase.
- ✅ Schedule y ejecución manual comparten exactamente el mismo job.
- ✅ Conecta naturalmente `gold` → features → modelo → promoción.
- ❌ Aumenta el alcance y criticidad de la instancia de Dagster.
- ❌ Requiere modelar con cuidado la diferencia entre `production_month` y
  `as_of_date`.

### GitHub Actions con workflow programado

- ✅ Scheduling y `workflow_dispatch` ya están disponibles sin un servicio
  adicional.
- ✅ Logs y permisos quedan integrados con el repositorio.
- ❌ Duplica la orquestación fuera de Dagster y fragmenta el linaje y el estado.
- ❌ Repetir una fecha exige inputs, scripts y manejo de retries propios.
- ❌ Los runners y secretos de CI pasan a ser una dependencia del runtime ML.

### Cron dentro del contenedor

- ✅ Es simple de iniciar y no requiere una plataforma externa.
- ✅ Puede invocar directamente el código Python existente.
- ❌ No ofrece historial durable, particiones, deduplicado ni recuperación por
  asset sin implementarlos a mano.
- ❌ Mezcla lifecycle del scheduler con el contenedor de ejecución.
- ❌ La ejecución manual tendería a usar otro camino distinto al cron.

### Airflow o Prefect para ML

- ✅ Son orquestadores maduros con scheduling, retries y ejecución manual.
- ✅ Podrían aislar el dominio ML del pipeline de datos.
- ❌ Introducen un segundo plano de control, otra UI y otro estado operativo.
- ❌ Duplican capacidades ya cubiertas por Dagster y rompen el linaje unificado.
- ❌ El costo de despliegue y aprendizaje no se justifica para un pipeline y un
  equipo de tres personas.

## Referencias

- Adenda técnica Fase 3 — orquestación repetible, retraining recurrente y
  automático.
- [Dagster — Schedules](https://docs.dagster.io/guides/automate/schedules/)
- [Dagster — Partitions](https://docs.dagster.io/guides/build/partitions-and-backfills/partitioning-assets)
- [Dagster — Asset jobs](https://docs.dagster.io/guides/build/jobs/asset-jobs)
- [ADR-0025](0025-calidad-datos-consecuencia.md) — calidad y bloqueo operativo.
- [ADR-0026](0026-tipo-carga-medallion.md) — carga idempotente y backfills.
- [ADR-0028](0028-orquestacion-e-ingesta-dagster-dlt.md) — Dagster y dlt en
  Fase 2.
- [ADR-0030](0030-objetivo-predictivo-horizonte-metricas.md) — objetivo,
  métricas y gates.
- [ADR-0031](0031-estrategia-feature-store.md) — feature store y
  point-in-time correctness.
- [ADR-0032](0032-tracking-experimentos-registry.md) — tracking y registry con
  MLflow.
- [ADR-0034](0034-serving-modelo-contrato-api.md) — serving y promoción por
  alias.
- Backlog Fase 3 — [#04](../backlog/issues-fase-3.md) y #12/#19 como
  implementación de esta decisión.
