# ADR-0034: Serving del modelo embebido en FastAPI y contrato de API predictiva

- **Estado:** Propuesto
- **Fecha:** 2026-06-28
- **Autores:** Joaquin Leon Alderete
- **Decisores:** Equipo Petrocast

## Contexto y problema

Fase 3 debe **exponer predicciones por una API REST** (RF de la adenda). El
backend ya existe: `apps/api` es un FastAPI que hoy sirve `/api/v1/forecast`
como **mock**, leyendo históricos de `gold.fact_production` y devolviéndolos como
si fueran el pronóstico (ADR-0007, ADR-0020). Fase 3 reemplaza ese mock por
predicciones de un **modelo real** (un único LightGBM global, ADR-0030) que se
carga del **model registry** (ADR-0032) y consume **features persistidas** del
feature store (ADR-0031).

La pregunta de arquitectura es **dónde corre la inferencia** y cómo se la expone:
¿el modelo vive dentro del proceso FastAPI, en un servicio separado, se precomputa
en batch, o se hostea en un endpoint gestionado? La decisión condiciona la
latencia, la cantidad de infraestructura nueva, el acople entre el ciclo de vida
del modelo y el de la API, y cómo se cumple el RNF de **"entrenamiento y
despliegue recurrente y automático"** sin servicio live en producción.

Restricciones del contexto:

- **Sin prod live.** La entrega se demuestra localmente; no hay que escalar a
  miles de RPS.
- **Un solo modelo, chico.** Un LightGBM global serializa a pocos MB.
- **Grano mensual, batch-ish.** Las predicciones son por pozo y por mes; no hay
  requerimiento de inferencia online de baja latencia (sub-100 ms).
- **NFR de latencia del PRD:** una respuesta de pronóstico nuevo en **< 5 s**.
- **Imágenes slim** (ADR-0014): la imagen de la API hoy copia solo `src/` y un
  venv liviano, sin `dagster`/`dbt`.
- **Equipo de 3, ~2 semanas.** Minimizar piezas móviles.

## Drivers de la decisión

- **Simplicidad operativa.** Cuantas menos piezas nuevas que desplegar y
  monitorear, mejor; 3 EC2 chicas, sin prod live.
- **Latencia.** Cumplir el < 5 s del PRD con margen.
- **Reuso del contrato y del pipeline de deploy existentes.** La API ya tiene
  contrato (ADR-0007), auth `X-API-Key`, tests de contrato (ADR-0016) y un
  pipeline CI/CD que la buildea y despliega.
- **Carga del champion desde el registry** (ADR-0032) y **lectura de features
  persistidas** (ADR-0031), sin recalcular features críticas en memoria.
- **"Despliegue recurrente y automático"** del modelo sin acoplar el ciclo de la
  imagen de la API.
- **Separación de tipos** (ADR-0020): los tipos internos de ML (features,
  matrices) no deben filtrarse al contrato externo; viven en `domain/`.

## Opciones consideradas

1. **Modelo embebido en FastAPI.** El proceso de la API carga el champion
   (`mlflow.pyfunc`/LightGBM) desde el registry/S3 y predice **in-process**. Lee
   las features persistidas del schema `features`. Una sola unidad desplegable.
2. **Servicio de inferencia separado.** Un contenedor dedicado (MLflow Models
   serving, BentoML, KServe, o un FastAPI-ML propio) expone el modelo por HTTP; la
   API de negocio lo consume como cliente.
3. **Batch predictions persistidas.** Un job de Dagster precomputa las
   predicciones por `(well_id, as_of_date, horizon)` y las guarda en una tabla; la
   API solo **lee** esa tabla.
4. **Serverless / endpoint gestionado externo.** Hostear el modelo en un
   SageMaker Endpoint, Vertex AI o AWS Lambda; la API lo invoca.

## Decisión

Adoptamos el **modelo embebido en FastAPI**: la API carga el modelo **champion**
desde el registry de MLflow por alias (`models:/petrocast-production@champion`,
ADR-0032), lee las **features persistidas** del feature store (ADR-0031) para la
entidad y `as_of_date` pedidas, y predice in-process. El "**despliegue recurrente
y automático**" se resuelve **promoviendo el alias `@champion`** en el registry
(tras pasar los gates de evaluación, backlog #15/#16): la API recarga el champion
**sin necesidad de re-buildear ni redeployar el contenedor**.

### Contrato de la API predictiva

Se mantiene la convención de Fase 1 (ADR-0007: snake_case, `X-API-Key`, esquemas
Pydantic con `alias_generator`). El contrato concreto se formaliza en backlog #17
(contrato D); en resumen:

- **Request:** identificador de pozo (`id_well`, mapeado a la clave de
  `gold.fact_production` decidida en ADR-0030), `as_of_date` (fecha de corte) y
  `horizon` **en meses**.
- **Response:** predicciones **por mes en m³**, más metadata: **versión del
  modelo**, `as_of_date` y `horizon`.
- **Errores:** 404 (pozo inexistente), 422 (validación), 503 (modelo o feature
  store no disponibles); auth `X-API-Key` → 403 si falla.
- Los tipos internos de ML viven en `src/domain/` (ADR-0020); el contrato externo
  en `src/schemas/` no los expone.

### Por qué embebido

- **Mínima infraestructura y latencia.** Un solo modelo chico ⇒ un contenedor,
  sin hop HTTP extra. Predecir in-process entra holgado en el < 5 s del PRD.
- **Reusa el pipeline de deploy de la API** (CI → staging/prod, ADR-0009/0011) sin
  cambios estructurales: el endpoint de predicción es una ruta más.
- **La API ya es Python/FastAPI** (ADR-0012): cargar `lightgbm` + cliente `mlflow`
  es directo; el loader expone la versión del modelo en la respuesta y en
  `/health/deep`.
- **Sin training-serving skew:** lee las **mismas features persistidas** que usó el
  training (ADR-0031), no recalcula in-memory.
- **Cumple "despliegue recurrente" sin redeploy.** Como la fuente de verdad del
  modelo vigente es el **alias del registry**, promover un nuevo champion (o hacer
  rollback re-apuntando el alias) cambia lo que sirve la API **sin tocar la imagen**
  — desacopla el ciclo del modelo del ciclo del contenedor.

### Trade-off principal y mitigación

Embeber el modelo hace que la imagen de `apps/api` **gane dependencias de ML**
(`lightgbm` + cliente `mlflow`). Se acota manteniendo en `apps/ml` solo el runtime
de inferencia (sin `dagster`/`dbt`/`fastapi`), de modo que la API arrastre un set
mínimo (contrato E, backlog #07/#23), y midiendo el tamaño de imagen resultante en
CI. La recarga del champion tras una promoción se resuelve con una estrategia
simple (recarga con TTL o un endpoint de *reload*), no con reinicio del contenedor.

## Consecuencias

**Positivas:**

- Mínima infra y latencia; una sola unidad desplegable.
- Reusa el contrato (ADR-0007), la auth y el pipeline de deploy de la API.
- Carga del champion por alias + lectura de features persistidas ⇒ sin skew y con
  metadata de versión auditable.
- **Despliegue recurrente del modelo por promoción de alias, sin redeploy** del
  contenedor (cumple el RNF).
- Fácil de demostrar localmente (la demo no requiere prod live).

**Negativas / trade-offs asumidos:**

- La imagen de la API crece por las deps de ML; se mide y se acota (contrato E).
- El ciclo de vida del modelo queda acoplado al proceso de la API (un modelo muy
  pesado competiría por memoria con el web server). Aceptable para un LightGBM
  chico; si Fase 4 sube el tamaño/throughput, se migra a un servicio separado
  **sin cambiar el contrato**.
- Reflejar una promoción de champion requiere una estrategia de recarga
  (TTL/endpoint de reload), no es automático "gratis".

**Neutras:**

- Ortogonal al tracking/registry (ADR-0032) y al feature store (ADR-0031): esta
  decisión sólo define *dónde corre* la inferencia.
- Reversible hacia un servicio separado (BentoML/KServe) si cambian los drivers;
  el contrato de la API queda igual.

## Pros y contras de cada opción

### Modelo embebido en FastAPI (elegida)

- ✅ Mínima infra: una sola unidad desplegable; sin hop HTTP.
- ✅ Latencia mínima; entra holgado en el < 5 s del PRD.
- ✅ Reusa contrato, auth y pipeline de deploy existentes.
- ✅ Despliegue del modelo por alias, sin redeploy del contenedor.
- ❌ La imagen de la API gana deps de ML (se mide y acota).
- ❌ Acopla el lifecycle del modelo al proceso de la API.

### Servicio de inferencia separado

- ✅ Desacopla modelo y API; escala y versiona independientemente.
- ✅ La imagen de la API queda liviana, sin deps de ML.
- ❌ Suma un contenedor a operar/monitorear y un hop HTTP (más latencia).
- ❌ Desproporcionado para un único modelo chico sin prod live ni demanda de escala.

### Batch predictions persistidas

- ✅ Serving trivial: la API sólo lee una tabla; latencia mínima.
- ✅ Encaja con Dagster, que ya precomputa por partición.
- ❌ No es *on-demand*: sólo responde para `(pozo, as_of_date, horizon)`
   precomputados; pedidos fuera de la grilla quedan sin respuesta o exigen recompute.
- ❌ Explosión combinatoria de filas si crece el espacio de horizontes/fechas.

### Serverless / endpoint gestionado externo

- ✅ Escala gestionada, sin operar el runtime.
- ✅ Aísla por completo el modelo de la API.
- ❌ Introduce un proveedor/servicio pago y dependencia de red.
- ❌ Sobredimensionado y contrario al espíritu "sin prod live, costo cero,
   self-hosted" del proyecto.

## Referencias

- [MLflow — Serving / `pyfunc.load_model`](https://mlflow.org/docs/latest/models.html)
- [BentoML](https://docs.bentoml.com/) · [KServe](https://kserve.github.io/website/)
- Adenda técnica Fase 3 — RF API de predicciones, RNF despliegue recurrente.
- PRD — NFR de latencia (< 5 s) para un pronóstico nuevo.
- [ADR-0007](0007-alineacion-contrato-openapi-fase1.md) — contrato OpenAPI Fase 1.
- [ADR-0012](0012-stack-backend-python-fastapi-uv.md) — FastAPI/uv.
- [ADR-0014](0014-imagenes-docker-slim-multistage-nonroot.md) — imágenes slim.
- [ADR-0020](0020-estructura-directorios-backend.md) — capa `domain/` para tipos ML.
- [ADR-0032](0032-tracking-experimentos-registry.md) — registry y champion por alias.
- ADR-0030 (en redacción) — objetivo/horizonte/métricas; ADR-0031 (en redacción) — feature store.
- Backlog Fase 3 — [#05](../backlog/issues-fase-3.md), #17 (contrato), #18 (runtime), #20 (endpoint).
