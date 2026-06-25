# Backlog de Fase 3 — Issues

- **Objetivo:** conjunto **completo, ordenado e incremental** de issues para
  resolver la adenda técnica de Fase 3 sobre **Machine Learning / modelo
  predictivo**, manteniendo las convenciones de Fase 1 y Fase 2.
- **Fecha de entrega:** 11 de julio de 2026. El PDF dice "11 de Julio"; se
  interpreta como 2026 por el calendario actual del proyecto.
- **Origen:** transcripción versionable en
  [`docs/assignment/adenda-fase-3.md`](../assignment/adenda-fase-3.md), extraída
  del PDF versionado
  [`docs/assignment/adenda-fase-3.pdf`](../assignment/adenda-fase-3.pdf).
- **Alcance:** no se exige servicio live en producción. Sí se exige demostrar en
  video la integración ML Engineering: tracking de experimentos, métricas de
  runs, API de predicciones y trigger de retrain.

## Cómo leer este backlog

- Cada issue indica **Owner**, **tipo de commit** (ADR-0005), **labels**,
  **dependencias** (`Depende de`), rama sugerida, contexto y criterios de
  aceptación.
- Idioma español en issues/docs (ADR-0002); código, ramas y commits en inglés.
- Los issues están **ordenados por milestone** y diseñados para no pisarse:
  cada integrante conserva una vertical coherente.
- Los ADRs de Fase 3 son obligatorios para decisiones clave. Como aclara la
  adenda, **un ADR que no compare alternativas es inválido**.
- Las ramas sugeridas siguen ADR-0004 y ADR-0006:
  `<tipo>/f3-nn-slug-en-kebab-case`.
- Los títulos de PR deben seguir Conventional Commits (ADR-0005) y cerrar el
  issue correspondiente con `Closes #<número>`.

## Requerimientos de la adenda

### Funcionales

- Usuarios de API deben poder consumir una API REST para usar el servicio.
- Devs / ML Engineers deben poder acceder a una plataforma de tracking de
  experimentos de machine learning.
- El servicio debe exponer una API.
- Debe existir una plataforma para tracking del entrenamiento de modelos, de
  modo que el entrenamiento sea reproducible.

### No funcionales

- El procesamiento y generación de features debe quedar persistido en un feature
  store utilizado durante la inferencia.
- La arquitectura completa debe estar descripta en el `README.md`.
- Debe utilizarse una herramienta de orquestación que permita repetir el proceso
  de entrenamiento para un día dado.
- El entrenamiento y despliegue de modelos debe realizarse de manera recurrente
  y automática.
- Los pipelines de procesamiento deben desplegarse mediante CI/CD.
- Debe incluirse un video de 5 a 10 minutos con arquitectura, herramientas,
  rationale, valor agregado y demo funcional.

## Stack base disponible al iniciar Fase 3

| Capa | Estado heredado de Fase 2 |
| ---- | ------------------------- |
| Orquestación | Dagster ya corre assets de datos y particiones mensuales |
| Ingesta | dlt carga fuentes oficiales a `bronze` |
| Transformación | dbt construye `silver` y `gold` |
| Warehouse | PostgreSQL 16 con schemas `bronze` / `silver` / `gold` |
| Datos para ML | `gold.fact_production` y vistas semánticas en `gold` |
| API | FastAPI ya expone `/api/v1/forecast`, hoy basado en históricos Gold |
| CI/CD | GitHub Actions valida API, data pipeline, dbt y build de imagen data |
| Staging | Compose/Swarm ya publica API, Dagster, Metabase y DataHub |

## Stack objetivo de Fase 3

Las herramientas concretas quedan fijadas por los ADRs de Fase 3, pero el
backlog asume estas responsabilidades:

| Capa | Responsabilidad |
| ---- | --------------- |
| Feature store | Persistir features offline/online para entrenamiento e inferencia |
| Tracking | Registrar params, métricas, artefactos y runs reproducibles |
| Entrenamiento | Entrenar baseline predictivo y guardar artefactos/versiones |
| Evaluación | Medir calidad del modelo y bloquear promociones malas |
| Orquestación | Repetir entrenamiento para un día dado y automatizar retraining |
| Serving | Exponer predicciones por API REST usando modelo + features |
| CI/CD ML | Validar, construir y desplegar pipelines/model artifacts |
| Demo | Evidenciar runs, métricas, llamadas API y trigger de retrain |

## Orden de ejecución (milestones)

- **M1 — Decisiones / ADRs:** #01–#06.
- **M2 — Fundación ML:** #07–#10.
- **M3 — Features, entrenamiento y registry:** #11–#16.
- **M4 — Serving e integración API:** #17–#20.
- **M5 — Automatización, CI/CD y evidencia:** #21–#23.
- **M6 — Documentación, demo y cierre:** #24.

**Camino crítico:** `#01/#02/#03/#04/#05/#06 → #07 → #09 → #11/#12 → #13 → #15/#16 → #18 → #20 → #23 → #24`.

**Paralelización recomendada:**

- #01–#06 pueden arrancar en paralelo.
- #08 puede avanzar en paralelo con #09/#10 después de #03.
- #11 y #12 se pueden dividir: Ignacio define features; Santino las orquesta.
- #17 puede avanzar con mocks apenas #05 esté decidido.
- #21/#22 pueden preparar evidencia mientras #18/#20 se integran.

## Distribución por integrante (8 / 8 / 8)

### Santino Domato — Plataforma ML, orquestación y CI/CD

`#04` · `#06` · `#07` · `#12` · `#16` · `#19` · `#21` · `#23`

### Ignacio Vargas — Features, modelo y evaluación

`#01` · `#02` · `#09` · `#10` · `#11` · `#13` · `#15` · `#22`

### Joaquin Leon Alderete — Tracking, API, consumo y demo

`#03` · `#05` · `#08` · `#14` · `#17` · `#18` · `#20` · `#24`

## Balance de dificultad y extensión

Escala usada para repartir carga:

- **M (2 pts):** ADR, documentación técnica o cambio acotado.
- **L (3 pts):** implementación con tests y una integración principal.
- **XL (4 pts):** integración transversal con CI/CD, deploy o varios sistemas.

| Owner | Issues | Esfuerzo estimado |
| ----- | ------ | ----------------- |
| Santino | #04(M), #06(M), #07(M), #12(L), #16(L), #19(L), #21(M), #23(XL) | **21 pts** |
| Ignacio | #01(M), #02(M), #09(L), #10(M), #11(L), #13(L), #15(L), #22(M) | **20 pts** |
| Joaquin | #03(M), #05(M), #08(L), #14(L), #17(M), #18(L), #20(L), #24(M) | **20 pts** |

La diferencia máxima queda en **1 punto**. Santino conserva más trabajo de
plataforma, Ignacio concentra el núcleo ML, y Joaquin toma tracking + serving
para que el esfuerzo no quede cargado solo en Santino.

---

## M1 — Decisiones / ADRs

### 01 — ADR: objetivo predictivo, horizonte y métricas de evaluación

- **Owner:** Ignacio · **Tipo:** `docs(adr)` · **Labels:** `adr`, `ml`,
  `modelado` · **Depende de:** —
- **Rama sugerida:** `docs/f3-01-adr-predictive-objective`
- **Decisión a documentar:** qué se predice, con qué horizonte temporal y con
  qué métricas se evalúa el modelo. Comparar al menos: regresión de producción
  futura por pozo, clasificación de caída/anomalía, forecast agregado por cuenca
  y baseline estadístico simple.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0030-*.md` con comparación de alternativas.
  - [ ] Define target, horizonte, granularidad y unidad de predicción.
  - [ ] Define métricas primarias/secundarias, por ejemplo MAE/RMSE/MAPE.
  - [ ] Explica por qué el objetivo elegido aporta valor al usuario de la API.
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda Fase 3; ADR-0001; ADR-0006.

### 02 — ADR: estrategia de feature store

- **Owner:** Ignacio · **Tipo:** `docs(adr)` · **Labels:** `adr`,
  `feature-store`, `ml` · **Depende de:** #01
- **Rama sugerida:** `docs/f3-02-adr-feature-store-strategy`
- **Decisión a documentar:** dónde y cómo persistir features para entrenamiento
  e inferencia. Comparar al menos: tablas PostgreSQL propias, Feast, DuckDB/Parquet
  y cálculo on-demand sin store.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0031-*.md` con comparación de alternativas.
  - [ ] Define esquema offline/online o justifica un store unificado.
  - [ ] Define claves (`well_id`, fecha de corte, horizonte) y versionado de
        features.
  - [ ] Explica cómo se evita training-serving skew.
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda RNF feature store; ADR-0023; ADR-0024.

### 03 — ADR: tracking de experimentos y registry de modelos

- **Owner:** Joaquin · **Tipo:** `docs(adr)` · **Labels:** `adr`,
  `tracking`, `mlops` · **Depende de:** #01
- **Rama sugerida:** `docs/f3-03-adr-experiment-tracking`
- **Decisión a documentar:** plataforma para tracking reproducible y registro
  de modelos. Comparar al menos: MLflow OSS, Weights & Biases, ClearML y tracking
  casero con archivos/DB.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0032-*.md` con comparación de alternativas.
  - [ ] Define dónde viven runs, métricas, params, artefactos y modelo champion.
  - [ ] Explica cómo un ML Engineer inspecciona distintos runs.
  - [ ] Evalúa costos/operación local, staging y demo sin servicio live.
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda RF tracking; ADR-0022; ADR-0027.

### 04 — ADR: orquestación de entrenamiento y retraining

- **Owner:** Santino · **Tipo:** `docs(adr)` · **Labels:** `adr`,
  `orquestacion`, `mlops` · **Depende de:** #01, #02
- **Rama sugerida:** `docs/f3-04-adr-training-orchestration`
- **Decisión a documentar:** cómo repetir entrenamiento para un día dado y cómo
  automatizar retraining recurrente. Comparar al menos: Dagster assets/jobs,
  GitHub Actions scheduled workflows, cron dentro de contenedor y Airflow/Prefect.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0033-*.md` con comparación de alternativas.
  - [ ] Define partición diaria o fecha de corte (`as_of_date`) para training.
  - [ ] Define schedule automático y trigger manual de retrain.
  - [ ] Explica retries, observabilidad y relación con assets de Fase 2.
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda RNF orquestación/retraining; ADR-0028.

### 05 — ADR: serving del modelo y contrato de API predictiva

- **Owner:** Joaquin · **Tipo:** `docs(adr)` · **Labels:** `adr`, `api`,
  `ml-serving` · **Depende de:** #01, #02, #03
- **Rama sugerida:** `docs/f3-05-adr-model-serving-api`
- **Decisión a documentar:** cómo la API REST sirve predicciones. Comparar al
  menos: modelo embebido en FastAPI, servicio separado de inferencia, batch
  predictions persistidas y serverless externo.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0034-*.md` con comparación de alternativas.
  - [ ] Define contrato de request/response, errores y versionado.
  - [ ] Define cómo se cargan modelo y features durante inferencia.
  - [ ] Justifica latencia, simplicidad y demo sin producción live.
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda RF API; ADR-0007; ADR-0012.

### 06 — ADR: CI/CD de pipelines ML y promoción de artefactos

- **Owner:** Santino · **Tipo:** `docs(adr)` · **Labels:** `adr`, `ci`,
  `mlops` · **Depende de:** #03, #04, #05
- **Rama sugerida:** `docs/f3-06-adr-ml-cicd`
- **Decisión a documentar:** cómo validar y desplegar pipelines de
  procesamiento, entrenamiento y artefactos de modelo. Comparar al menos:
  GitHub Actions con imágenes Docker, Dagster deploy manual, scripts locales y
  despliegue acoplado al API.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0035-*.md` con comparación de alternativas.
  - [ ] Define checks mínimos de PR para features/training/inference.
  - [ ] Define promoción de artefactos y rollback de modelo.
  - [ ] Define qué se automatiza aunque no haya servicio live en producción.
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda RNF CI/CD; ADR-0011; ADR-0013.

---

## M2 — Fundación ML

### 07 — Scaffold del proyecto ML y configuración

- **Owner:** Santino · **Tipo:** `feat(ml)` · **Labels:** `ml`, `infra` ·
  **Depende de:** #01, #02, #03
- **Rama sugerida:** `feat/f3-07-ml-project-scaffold`
- **Contexto:** Fase 3 necesita un lugar claro para código de features,
  training, inference y tests, sin mezclar responsabilidades con API o dbt.
- **Criterios de aceptación:**
  - [ ] Estructura de proyecto ML creada según ADR-0006.
  - [ ] Dependencias mínimas de ML declaradas y lockfile actualizado.
  - [ ] Configuración por entorno alineada con ADR-0018.
  - [ ] Tests smoke verifican import/config del paquete ML.
  - [ ] README local del módulo explica comandos básicos.
- **Referencias:** #01, #02, #03; ADR-0018.

### 08 — Plataforma de tracking de experimentos

- **Owner:** Joaquin · **Tipo:** `feat(mlops)` · **Labels:** `tracking`,
  `infra`, `mlops` · **Depende de:** #03
- **Rama sugerida:** `feat/f3-08-experiment-tracking-platform`
- **Contexto:** los ML Engineers deben poder ver runs, métricas y artefactos en
  una plataforma reproducible. La herramienta concreta queda definida en #03.
- **Criterios de aceptación:**
  - [ ] Compose local/staging levanta la plataforma elegida.
  - [ ] Credenciales/paths/config se inyectan por variables de entorno.
  - [ ] Hay un run de ejemplo visible con params y métricas.
  - [ ] Documentación indica URL, usuario si aplica y comandos de uso.
  - [ ] CI valida al menos la configuración o el smoke del cliente.
- **Referencias:** adenda RF tracking; #03; ADR-0027.

### 09 — Schema y modelos base del feature store

- **Owner:** Ignacio · **Tipo:** `feat(data)` · **Labels:** `feature-store`,
  `dbt`, `ml` · **Depende de:** #02, #07
- **Rama sugerida:** `feat/f3-09-feature-store-schema`
- **Contexto:** la adenda exige persistir features y usarlas en inferencia. El
  store debe partir de `gold.fact_production` y conservar fecha de corte.
- **Criterios de aceptación:**
  - [ ] Schema/tablas de feature store creadas según #02.
  - [ ] Modelos dbt o scripts generan una tabla base con `well_id`,
        `as_of_date` y features iniciales.
  - [ ] Tests validan unicidad por clave de entidad + fecha de corte.
  - [ ] Documentación explica grano, claves y relación con Gold.
  - [ ] No se calcula feature crítica solo en memoria durante inferencia.
- **Referencias:** adenda RNF feature store; ADR-0023; ADR-0024.

### 10 — Fixtures y datasets de entrenamiento reproducibles

- **Owner:** Ignacio · **Tipo:** `test(ml)` · **Labels:** `ml`, `testing`,
  `datos` · **Depende de:** #01, #09
- **Rama sugerida:** `test/f3-10-training-fixtures`
- **Contexto:** CI no debe depender de internet ni de datasets pesados para
  validar training/inference. Se necesitan fixtures mínimos y representativos.
- **Criterios de aceptación:**
  - [ ] Fixtures pequeños cubren varios pozos, meses y casos faltantes.
  - [ ] Hay dataset esperado para training smoke y backtesting smoke.
  - [ ] Tests documentan supuestos de target/horizonte.
  - [ ] Los fixtures no contienen secretos ni archivos grandes.
  - [ ] CI puede ejecutar pruebas ML sin servicios externos.
- **Referencias:** #01; #09; ADR-0016.

---

## M3 — Features, entrenamiento y registry

### 11 — Feature engineering para producción histórica

- **Owner:** Ignacio · **Tipo:** `feat(ml)` · **Labels:** `features`, `dbt`,
  `ml` · **Depende de:** #09, #10
- **Rama sugerida:** `feat/f3-11-production-feature-engineering`
- **Contexto:** el modelo necesita features derivadas de la historia de
  producción, evitando leakage respecto de la fecha de corte.
- **Criterios de aceptación:**
  - [ ] Features de lags, rolling windows y tendencia quedan persistidas.
  - [ ] Tests validan que las features no miran datos posteriores a
        `as_of_date`.
  - [ ] Se documenta cada feature con descripción y tipo.
  - [ ] La salida es consumible por training e inference.
  - [ ] dbt/Dagster muestra lineage desde Gold hasta feature store.
- **Referencias:** adenda RNF feature store; #01; #02.

### 12 — Asset Dagster de materialización de features

- **Owner:** Santino · **Tipo:** `feat(data)` · **Labels:** `dagster`,
  `feature-store`, `mlops` · **Depende de:** #04, #09, #11
- **Rama sugerida:** `feat/f3-12-feature-materialization-asset`
- **Contexto:** la generación de features debe poder repetirse para un día dado
  y quedar visible en la orquestación.
- **Criterios de aceptación:**
  - [ ] Asset/job Dagster materializa features para `as_of_date`.
  - [ ] El asset expone metadata útil: filas, rango de fechas, hash/config.
  - [ ] Se puede ejecutar desde CLI y UI de Dagster.
  - [ ] Retries y logs siguen el patrón de Fase 2.
  - [ ] Tests o smoke local validan una materialización con fixtures.
- **Referencias:** adenda RNF orquestación; #04; ADR-0028.

### 13 — Pipeline de entrenamiento baseline

- **Owner:** Ignacio · **Tipo:** `feat(ml)` · **Labels:** `training`, `ml` ·
  **Depende de:** #01, #10, #11
- **Rama sugerida:** `feat/f3-13-baseline-training-pipeline`
- **Contexto:** se necesita un modelo predictivo inicial simple, reproducible y
  evaluable antes de optimizar.
- **Criterios de aceptación:**
  - [ ] Script/asset de training entrena un baseline con parámetros fijos.
  - [ ] Se guarda artefacto de modelo con metadata de dataset y código.
  - [ ] Se separan train/validation/test temporalmente.
  - [ ] Training smoke corre con fixtures en CI.
  - [ ] README del módulo explica cómo entrenar localmente.
- **Referencias:** adenda contexto modelo predictivo; #01; #10.

### 14 — Registro de runs, métricas y artefactos

- **Owner:** Joaquin · **Tipo:** `feat(mlops)` · **Labels:** `tracking`,
  `training`, `mlops` · **Depende de:** #03, #08, #13
- **Rama sugerida:** `feat/f3-14-training-run-tracking`
- **Contexto:** el video debe mostrar métricas de training en distintos runs.
  El tracking tiene que ser automático, no una captura manual.
- **Criterios de aceptación:**
  - [ ] Cada entrenamiento registra params, métricas, tags y artefactos.
  - [ ] Se pueden distinguir al menos dos runs en la UI de tracking.
  - [ ] El run guarda versión/corte de features y commit o imagen usada.
  - [ ] Tests mockean el cliente de tracking o validan el formato de logging.
  - [ ] Documentación explica cómo encontrar los runs para la demo.
- **Referencias:** adenda RF tracking y video; #03; #08.

### 15 — Evaluación, backtesting y gates de calidad del modelo

- **Owner:** Ignacio · **Tipo:** `feat(ml)` · **Labels:** `evaluation`,
  `quality`, `ml` · **Depende de:** #13, #14
- **Rama sugerida:** `feat/f3-15-model-evaluation-gates`
- **Contexto:** el modelo no debería promocionarse si empeora contra baseline
  o si sus métricas son inválidas.
- **Criterios de aceptación:**
  - [ ] Backtesting temporal calcula métricas definidas en #01.
  - [ ] Se compara contra baseline naive documentado.
  - [ ] Gate automático falla si métricas superan umbrales definidos.
  - [ ] Resultados quedan registrados en tracking.
  - [ ] Tests cubren éxito y falla del gate.
- **Referencias:** #01; #03; ADR-0016.

### 16 — Registro y promoción del modelo champion

- **Owner:** Santino · **Tipo:** `feat(mlops)` · **Labels:** `registry`,
  `deployment`, `mlops` · **Depende de:** #03, #14, #15
- **Rama sugerida:** `feat/f3-16-model-registry-promotion`
- **Contexto:** la API necesita saber cuál modelo usar. La promoción debe ser
  trazable y reversible.
- **Criterios de aceptación:**
  - [ ] Existe concepto de modelo `champion` o equivalente.
  - [ ] Solo se promociona si pasa gates de #15.
  - [ ] Se persiste metadata de versión, fecha de entrenamiento y métricas.
  - [ ] Hay mecanismo de rollback a modelo anterior.
  - [ ] Documentación explica cómo inspeccionar/promover/rollback.
- **Referencias:** #03; #06; #15.

---

## M4 — Serving e integración API

### 17 — Contrato OpenAPI de predicciones

- **Owner:** Joaquin · **Tipo:** `feat(api)` · **Labels:** `api`,
  `contract`, `ml-serving` · **Depende de:** #05
- **Rama sugerida:** `feat/f3-17-prediction-api-contract`
- **Contexto:** los usuarios de API deben poder consumir el servicio predictivo
  con un contrato claro y validado.
- **Criterios de aceptación:**
  - [ ] Request/response de predicción documentados en OpenAPI.
  - [ ] Incluye campos de horizonte, pozo/entidad y fecha de corte si aplica.
  - [ ] Errores esperados tienen schema y status code definidos.
  - [ ] Contract tests verifican el OpenAPI.
  - [ ] Ejemplos de requests quedan en README o colección de demo.
- **Referencias:** adenda RF API; #05; ADR-0007.

### 18 — Runtime de inferencia con modelo y feature store

- **Owner:** Joaquin · **Tipo:** `feat(api)` · **Labels:** `inference`,
  `feature-store`, `ml-serving` · **Depende de:** #02, #16, #17
- **Rama sugerida:** `feat/f3-18-inference-runtime`
- **Contexto:** inferencia debe usar features persistidas y el modelo champion,
  no recalcular todo ad hoc dentro del endpoint.
- **Criterios de aceptación:**
  - [ ] Loader obtiene el modelo champion desde el registry/artefacto definido.
  - [ ] Inferencia lee features persistidas para la entidad/fecha solicitada.
  - [ ] Maneja ausencia de features/modelo con errores claros.
  - [ ] Tests unitarios cubren predicción exitosa y casos de error.
  - [ ] Métricas/logs básicos permiten auditar versión de modelo usada.
- **Referencias:** adenda RNF feature store; #05; #16; #17.

### 19 — Job y schedule de retraining

- **Owner:** Santino · **Tipo:** `feat(mlops)` · **Labels:** `dagster`,
  `retraining`, `mlops` · **Depende de:** #04, #12, #13, #15, #16
- **Rama sugerida:** `feat/f3-19-retraining-job-schedule`
- **Contexto:** la adenda exige entrenamiento/despliegue recurrente y
  automático, además de repetir training para un día dado.
- **Criterios de aceptación:**
  - [ ] Job Dagster encadena features → training → evaluation → promotion.
  - [ ] Se puede ejecutar para un `as_of_date` específico.
  - [ ] Schedule recurrente configurado y documentado.
  - [ ] Trigger manual queda demostrado por CLI o UI de Dagster.
  - [ ] Logs/metadata muestran fecha, modelo resultante y estado de promoción.
- **Referencias:** adenda RNF orquestación/retraining; #04.

### 20 — Endpoint REST de predicciones integrado

- **Owner:** Joaquin · **Tipo:** `feat(api)` · **Labels:** `api`,
  `prediction`, `ml-serving` · **Depende de:** #17, #18
- **Rama sugerida:** `feat/f3-20-prediction-endpoint`
- **Contexto:** la API existente debe devolver predicciones generadas por el
  modelo, manteniendo compatibilidad razonable con el contrato actual.
- **Criterios de aceptación:**
  - [ ] Endpoint REST devuelve predicciones usando el runtime de #18.
  - [ ] Tests de integración cubren llamadas reales con fixture/modelo smoke.
  - [ ] OpenAPI muestra ejemplos de predicción.
  - [ ] Respuesta incluye metadata mínima: versión de modelo, fecha de corte y
        horizonte.
  - [ ] Se documentan comandos `curl` para la demo.
- **Referencias:** adenda RF API y video; #05; #17; #18.

---

## M5 — Automatización, CI/CD y evidencia

### 21 — Evidencia demo de tracking y API

- **Owner:** Santino · **Tipo:** `docs(demo)` · **Labels:** `demo`,
  `tracking`, `api` · **Depende de:** #08, #14, #20
- **Rama sugerida:** `docs/f3-21-demo-evidence`
- **Contexto:** el video debe mostrar métricas en distintos runs, llamadas a la
  API bajo distintas condiciones y trigger de retrain.
- **Criterios de aceptación:**
  - [ ] Script o guía genera al menos dos runs con métricas distintas.
  - [ ] Script o guía ejecuta llamadas a la API con escenarios distintos.
  - [ ] Se listan pantallas/evidencias necesarias para el video.
  - [ ] Los comandos funcionan sin servicio live en producción.
  - [ ] Se documentan datos de ejemplo y resultados esperados.
- **Referencias:** adenda video; #14; #20.

### 22 — Reporte de backtesting y model card

- **Owner:** Ignacio · **Tipo:** `docs(ml)` · **Labels:** `model-card`,
  `evaluation`, `ml` · **Depende de:** #15, #16
- **Rama sugerida:** `docs/f3-22-model-card-backtesting`
- **Contexto:** el equipo necesita explicar el valor agregado y los límites del
  modelo de forma entendible.
- **Criterios de aceptación:**
  - [ ] Model card documenta objetivo, datos, features, métricas y limitaciones.
  - [ ] Reporte resume backtesting y comparación contra baseline.
  - [ ] Se incluyen riesgos: leakage, datos faltantes, drift y sesgos.
  - [ ] Se vincula el modelo champion con su run de tracking.
  - [ ] Sirve como insumo directo para el video.
- **Referencias:** adenda video/rationale; #01; #15.

### 23 — CI/CD de pipelines ML y despliegue de artefactos

- **Owner:** Santino · **Tipo:** `ci(ml)` · **Labels:** `ci`, `deployment`,
  `mlops` · **Depende de:** #06, #13, #18, #19
- **Rama sugerida:** `ci/f3-23-ml-pipeline-cicd`
- **Contexto:** la adenda exige que los pipelines de procesamiento se desplieguen
  mediante CI/CD. No alcanza con scripts manuales.
- **Criterios de aceptación:**
  - [ ] Workflow de PR ejecuta tests ML, training smoke e inference smoke.
  - [ ] Workflow de build publica o empaqueta artefactos necesarios.
  - [ ] Workflow de deploy actualiza pipelines/servicios definidos en #06.
  - [ ] Falla si el modelo no puede cargar o si el feature store no es usable.
  - [ ] README/runbook explica promoción y rollback.
- **Referencias:** adenda RNF CI/CD; #06; ADR-0011.

---

## M6 — Documentación, demo y cierre

### 24 — README Fase 3, arquitectura completa y guion de video

- **Owner:** Joaquin · **Tipo:** `docs(readme)` · **Labels:** `docs`,
  `demo`, `arquitectura` · **Depende de:** #21, #22, #23
- **Rama sugerida:** `docs/f3-24-readme-demo`
- **Contexto:** la adenda exige que la arquitectura completa esté descripta en
  el `README.md` y que el video explique diseño, herramientas, rationale, valor
  agregado y demo.
- **Criterios de aceptación:**
  - [ ] `README.md` describe arquitectura completa Fase 1 + Fase 2 + Fase 3.
  - [ ] Se documentan herramientas, flujos y decisiones clave con links a ADRs.
  - [ ] Se documenta cómo correr tracking, retrain y API de predicciones.
  - [ ] Guion/checklist del video cubre runs, métricas, API y retrain.
  - [ ] `docs/fase-2/README.md` o docs de fase se actualizan si corresponde.
- **Referencias:** adenda RNF README y video; #21; #22; #23.

---

## Matriz de cobertura de requerimientos

| Requerimiento Fase 3 | Issues principales |
| -------------------- | ------------------ |
| API REST de predicciones | #05, #17, #18, #20 |
| Tracking reproducible de entrenamientos | #03, #08, #14, #21 |
| Feature store persistido para inferencia | #02, #09, #11, #12, #18 |
| Arquitectura completa en README | #01–#06, #22, #24 |
| Orquestar entrenamiento para un día dado | #04, #12, #19 |
| Entrenamiento/despliegue recurrente y automático | #04, #16, #19, #23 |
| Pipelines desplegados por CI/CD | #06, #23 |
| ADRs con comparación de alternativas | #01, #02, #03, #04, #05, #06 |
| Video demo 5–10 minutos | #14, #19, #20, #21, #22, #24 |

## Títulos de PR sugeridos

| Issue | Título sugerido |
| ----- | --------------- |
| #01 | `docs(adr): add ADR on predictive objective and metrics` |
| #02 | `docs(adr): add ADR on feature store strategy` |
| #03 | `docs(adr): add ADR on experiment tracking and model registry` |
| #04 | `docs(adr): add ADR on training orchestration and retraining` |
| #05 | `docs(adr): add ADR on model serving API architecture` |
| #06 | `docs(adr): add ADR on ML CI/CD and artifact promotion` |
| #07 | `feat(ml): scaffold predictive modeling project` |
| #08 | `feat(mlops): add experiment tracking platform` |
| #09 | `feat(data): add feature store schema and base models` |
| #10 | `test(ml): add reproducible training fixtures` |
| #11 | `feat(ml): add production feature engineering` |
| #12 | `feat(data): add feature materialization asset` |
| #13 | `feat(ml): add baseline training pipeline` |
| #14 | `feat(mlops): log training runs and artifacts` |
| #15 | `feat(ml): add model evaluation gates` |
| #16 | `feat(mlops): add champion model promotion` |
| #17 | `feat(api): add prediction API contract` |
| #18 | `feat(api): add inference runtime` |
| #19 | `feat(mlops): add retraining job and schedule` |
| #20 | `feat(api): expose model predictions endpoint` |
| #21 | `docs(demo): add tracking and API demo evidence` |
| #22 | `docs(ml): add model card and backtesting report` |
| #23 | `ci(ml): add ML pipeline checks and deployment` |
| #24 | `docs(readme): document Phase 3 architecture and demo` |
