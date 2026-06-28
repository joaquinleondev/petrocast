# Backlog de Fase 3 — Issues

- **Objetivo:** conjunto **completo, ordenado e incremental** de issues para
  resolver la adenda técnica de Fase 3 sobre **Machine Learning / modelo
  predictivo**, manteniendo las convenciones de Fase 1 y Fase 2.
- **Fecha de entrega:** 11 de julio de 2026. El PDF dice "11 de Julio"; se
  interpreta como 2026 por el calendario actual del proyecto.
- **Origen:** transcripción versionable en
  [`docs/assignment/adenda-fase-3.md`](../assignment/adenda-fase-3.md), extraída
  del PDF original de la cátedra (figura en
  [`docs/assets/adenda-fase-3-fig-1.png`](../assets/adenda-fase-3-fig-1.png)).
- **Alcance:** no se exige servicio live en producción. Sí se exige demostrar en
  video la integración ML Engineering: tracking de experimentos, métricas de
  runs, API de predicciones y trigger de retrain.
- **Estado de este backlog:** refinado tras la validación del stack y tres
  auditorías (dependencias/temporalidad, colisiones de archivos "no pisarse" y
  distribución/esfuerzo). Las decisiones técnicas quedan fijadas en la sección
  [Stack objetivo refinado](#stack-objetivo-refinado-north-star).

## Cómo leer este backlog

- Cada issue indica **Owner**, **tipo de commit** (ADR-0005), **labels**,
  **dependencias** (`Depende de`), rama sugerida, contexto, **footprint de
  archivos** (crear/modificar), criterios de aceptación y, donde aplica, el
  **contrato de handoff** que debe congelarse antes de que el consumidor arranque.
- Idioma español en issues/docs (ADR-0002); código, ramas y commits en inglés.
- Los issues están **ordenados por milestone** y diseñados para no pisarse:
  cada integrante conserva una vertical coherente y el footprint de archivos está
  pensado para minimizar colisiones (ver [Protocolo "no pisarse"](#protocolo-no-pisarse)).
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

## Stack objetivo refinado (north star)

Las herramientas concretas se formalizan en los ADRs #01–#06 (con comparación de
alternativas, obligatoria). Estas son las **decisiones ya validadas** que el
backlog asume como norte; cada ADR debe hacer la comparación formal y aterrizar
la decisión, no inventarla de cero.

| Decisión (ADR) | Elección | Rationale corto |
| -------------- | -------- | --------------- |
| **Tracking + Registry (0032)** | **MLflow OSS**. Backend store en **Postgres en la nube** (Neon/Supabase free tier, o RDS) + artefactos en **S3**. Se corre **local para la demo** (listo-para-deployar, no se deploya por cómputo). | Único OSS self-hosted con tracking *y* registry. DB en la nube → runs/modelo compartidos por todo el equipo sin hostear server 24/7. |
| **Feature store (0031)** | **Tablas en un schema `features` de Postgres, generadas por dbt**. Clave `(well_id, as_of_date)`. **Point-in-time correct** (sin leakage). | Cero infra nueva, reusa el patrón medallion + tests de unicidad. Feast es overkill sin serving online de baja latencia (grano mensual, batch). |
| **Orquestación / retrain (0033)** | **Dagster**. `as_of_date` como **partición**; primer **`ScheduleDefinition`** del repo para retrain recurrente. | Ya corre Dagster; "repetir para un día dado" = partición. Evita fragmentar con Airflow/Prefect. |
| **Serving (0034)** | **Modelo embebido en FastAPI**, champion cargado del registry. "Despliegue recurrente" = **promoción de alias** (sin redeploy del contenedor). | Sin prod live, un solo modelo, latencia mínima. Lee features persistidas, no recalcula in-memory. |
| **Objetivo / métricas (0030)** | **Regresión de producción mensual por pozo** (`prod_pet`, m³). Horizonte **en meses**. Modelo: **un único LightGBM global**. Métricas: **MAE/RMSE + MASE** primarias (robustas a ceros), **MAPE-sobre-no-cero** secundaria. Baselines: **persistencia naive** (obligatorio por PRD) + **Arps** (best-effort, estándar de industria). | LightGBM global = estándar moderno para "muchas series relacionadas"; maneja cold-start vía features estáticas del pozo. **MASE** codifica directamente "le ganamos al naive" y no explota con meses en cero (shut-in). Ver `supuestos-y-clarificaciones.md` P4 (cita Hyndman). |
| **CI/CD ML (0035)** | **GitHub Actions** reusando OIDC→ECR→SSM; smokes de training/inference sobre fixtures offline. | Reusa el mecanismo actual; sin scripts manuales. |
| **Dónde vive el código ML** | **Paquete standalone `apps/ml/`** (`petrocast_ml`), con su `pyproject.toml`/`uv.lock`/`Dockerfile`, **importado por `apps/api` y `apps/data`** vía uv path-dependency. | Serving embebido obliga a que la API importe el runtime; si viviera en `apps/data` arrastraría dagster/dbt a la imagen de la API. Aísla el churn ML de ambos apps deployables. Ver [Dónde vive el código ML](#dónde-vive-el-código-ml). |

## Decisiones / contratos a congelar antes de codear (pre-work)

Antes de arrancar M2/M3, el equipo **congela** estos contratos. Son consumidos por
las tres personas y, si quedan abiertos, generan retrabajo y colisiones.

1. **`well_id` = `sigla` vs `idpozo`** (ambigüedad A3 de `supuestos-y-clarificaciones.md`).
   Un pozo puede producir de varias formaciones → distinto grano. El feature store,
   el grano del modelo y el `id_well` de la API deben usar **la misma clave que
   `gold.fact_production`**. Decisión por defecto: alinear con el grano de Gold
   (`well_id` derivado de `idpozo`); confirmar contra A3 y dejarlo escrito en #01/#09.
2. **Contrato A — tabla del feature store** (#09): schema `features`, nombre(s) de
   tabla, clave `(well_id, as_of_date)`, lista de columnas + tipos + orden,
   unidades en **m³**, manejo de nulos, y la **regla PIT** (ninguna fila usa datos
   posteriores a `as_of_date`).
3. **Contrato B — registry / alias champion** (#16→#18): nombre del modelo
   registrado, **alias `champion`** (MLflow alias, no `stage` deprecado), flavor
   (lightgbm/pyfunc), **signature** (vector de features = contrato A) y metadata
   expuesta (versión, `as_of_date` de training, métricas).
4. **Contrato C — config de tracking** (#08→#14/#15/#16/#19): `MLFLOW_TRACKING_URI`,
   artifact root (bucket/prefijo S3), credenciales por env, convención de nombres de
   experimento y tags de run obligatorios (versión de features/`as_of_date`,
   commit/imagen).
5. **Contrato D — OpenAPI de predicción** (#17→#18/#20/#21/#23/#24): request
   (campo de pozo + `as_of_date` + `horizon` **en meses**), response (predicciones
   por mes en **m³** + versión de modelo + `as_of_date` + horizonte), errores +
   status codes, auth `X-API-Key`.
6. **Contrato E — deps ML / imagen de la API** (#07/#23→#18/#20): qué importa la API
   (`petrocast_ml`: `load_champion()/predict()`), versiones pineadas de
   `lightgbm` + cliente `mlflow`, `COPY` en el `apps/api/Dockerfile`, tamaño de
   imagen aceptable.
7. **Contrato F — métricas/horizonte** (#01→#13/#15/#16/#17/#22): target, horizonte
   en meses, métricas primarias/secundarias, baselines, filtro de pozos ≥12 meses,
   split temporal, umbrales del gate.

El tablero de contratos completo está en
[Contratos de handoff](#contratos-de-handoff).

## Stack base disponible al iniciar Fase 3

| Capa | Estado heredado de Fase 2 |
| ---- | ------------------------- |
| Orquestación | Dagster ya corre assets de datos y particiones mensuales (sin `ScheduleDefinition` aún) |
| Ingesta | dlt carga fuentes oficiales a `bronze` |
| Transformación | dbt construye `silver` y `gold` |
| Warehouse | PostgreSQL 16 con schemas `bronze` / `silver` / `gold` |
| Datos para ML | `gold.fact_production` (grano pozo-mes; `oil_prod_m3`, `gas_prod_mm3`, `water_prod_m3`) y vistas semánticas en `gold` |
| API | FastAPI ya expone `/api/v1/forecast`, hoy basado en históricos Gold (mock) |
| CI/CD | GitHub Actions valida API, data pipeline, dbt y build de imagen data |
| Staging | Compose/Swarm ya publica API, Dagster, Metabase y DataHub |

## Stack objetivo de Fase 3

| Capa | Responsabilidad | Herramienta (north star) |
| ---- | --------------- | ------------------------ |
| Feature store | Persistir features para entrenamiento e inferencia | dbt → schema `features` en Postgres |
| Tracking | Registrar params, métricas, artefactos y runs reproducibles | MLflow (backend cloud Postgres + S3) |
| Entrenamiento | Entrenar baseline predictivo y guardar artefactos/versiones | `petrocast_ml` + LightGBM |
| Evaluación | Medir calidad y bloquear promociones malas | backtesting + gates (MASE vs naive/Arps) |
| Orquestación | Repetir entrenamiento para un día dado y automatizar retraining | Dagster (partición `as_of_date` + schedule) |
| Serving | Exponer predicciones por API REST usando modelo + features | FastAPI con modelo embebido |
| CI/CD ML | Validar, construir y desplegar pipelines/model artifacts | GitHub Actions (OIDC→ECR→SSM) |
| Demo | Evidenciar runs, métricas, llamadas API y trigger de retrain | scripts/guía de evidencia |

## Dónde vive el código ML

**Decisión:** nuevo paquete `apps/ml/` (`petrocast_ml`) con `pyproject.toml`,
`uv.lock`, `Dockerfile` y `tests/` propios, **dependido por `apps/api` y
`apps/data`** vía uv path-dependency (`tool.uv.sources`). Es la **primera
dependencia local cross-app** del monorepo (hoy los apps solo comparten DB +
convención de env-vars).

- **Por qué no dentro de `apps/data`:** el serving embebido obliga a `apps/api` a
  importar el runtime; si viviera en `apps/data`, la imagen de la API arrastraría
  `dagster`/`dbt`/`dlt`, rompiendo la imagen slim (ADR-0014). Además concentra todo
  el churn ML en un solo `pyproject.toml`/`uv.lock` → peor "no pisarse".
- **Por qué no dentro de `apps/api`:** invertiría la dirección de dependencia
  (los assets de training en Dagster importarían FastAPI) y metería el código de
  modelado de Ignacio dentro de la vertical de API de Joaquin.
- **`apps/ml/` (elegido):** deps mínimas (`lightgbm`, `mlflow`, `pandas`, `numpy`,
  `psycopg`; **sin dagster/dbt/fastapi**). Dirección limpia: `apps/data →
  petrocast_ml` (training/feature/retrain assets) y `apps/api → petrocast_ml`
  (inferencia). Aísla el churn ML de ambos apps deployables.
- **Alternativa a documentar en el ADR de #07:** `packages/petrocast-ml/` (el dir
  `packages/` está reservado para librerías compartidas por ADR-0003) es
  funcionalmente equivalente; `apps/ml/` gana solo por uniformidad con el patrón
  per-app de CI/Dockerfile. La decisión load-bearing es "paquete importable
  standalone que ambos apps dependen", no el dir exacto.

## Orden de ejecución (milestones)

- **M1 — Decisiones / ADRs:** #01–#06.
- **M2 — Fundación ML:** #07–#10.
- **M3 — Features, entrenamiento y registry:** #11–#16.
- **M4 — Serving e integración API:** #17–#20.
- **M5 — Automatización, CI/CD y evidencia:** #21–#23.
- **M6 — Documentación, demo y cierre:** #24.

### Camino crítico (corregido)

El camino crítico que figuraba antes ruteaba por `#20 → #23`, **arista
inexistente** (#23 depende de #06/#13/#18/#19, no de #20). El verdadero camino más
largo (14 nodos) termina por #21:

```
#01 → #03 → #07 → #09 → #10 → #11 → #13 → #14 → #15 → #16 → #18 → #20 → #21 → #24
```

**Rama co-crítica** (≈1 pt más corta, contiene el único XL #23 — tratar como
crítica para scheduling/riesgo):

```
#04/#06 → #12 → #19 → #23 → #24
```

> **Cuello de botella real:** la cadena `#09 → #10 → #11 → #13 → #15` es **toda de
> Ignacio** (≈14 pts seriales en una persona). El cuello no es un handoff, es su
> lane. Mitigación: #10 y #11 pueden solaparse; si la lane de Ignacio se atrasa,
> Santino (el más liviano) puede emparejar en los fixtures (#10) o en el harness
> de Arps.

### Validación de dependencias (auditoría)

- La numeración **es un orden topológico válido**: toda dependencia apunta a un
  número estrictamente menor. **No hay referencias hacia el futuro ni ciclos.**
- Correcciones aplicadas respecto del backlog previo:
  - **#08** `Depende de` `#03` → **`#03, #07`** (MLflow necesita el provisioning del
    backend cloud + la convención de config del paquete) y se reclasifica **L → XL**.
  - **#14** `Depende de` `#03, #08, #13` → **`#08, #13`** (#03 era redundante,
    transitivo vía #08).
  - **#15** `Depende de` `#13, #14` → **`#01, #13, #14`** (explicita que MASE,
    baselines y umbrales del gate se definen en #01).
  - **#18** `Depende de` `#02, #16, #17` → **`#09, #11, #16, #17`** (#02 es el ADR,
    no el store; la inferencia lee features **persistidas** → necesita #09 + #11).
  - **#21** `Depende de` `#08, #14, #20` → **`#08, #14, #19, #20`** (la demo muestra
    el **trigger de retrain**, que solo existe tras #19).

### Paralelización recomendada (lanes + sync points)

`S#` = punto de sincronización/handoff bloqueante.

```
SANTINO (plataforma/orq/CI)   IGNACIO (features/modelo/eval)  JOAQUIN (tracking/API/demo)
────────────────────────────  ─────────────────────────────  ────────────────────────────
                              #01  ◄── destraba a todos        (espera S1)
#04 (tras #02) ─┐            #02                              #03 (tras borrador #01)
#06 (tras#03/4/5)│                                            #05 (tras #01,#02,#03)
        ── S1: #01 listo ───────────────────────────────────────────────────────
#07 scaffold ───┼─► S2        (espera S2)                      #17 (tras #05, con mocks)
#07 + provisioning helper     #09 (tras #07) ──► S3            #08 (tras #07 + provisioning)─►S4
        ── S2: #07 listo → destraba #09 (Ig) y #08 (Jo) ──────────────────────────
#12 (tras #11)                #10 → #11 ──► S5                 #08 run de ejemplo (S4)
        ── S3: #09 schema → fixtures #10 ──────────────────────────────────────
        ── S5: #11 features → #12 (San) y #13 (Ig) ─────────────────────────────
#16 (tras #14,#15)            #13 ──► S6 → #15 ──► S7          #14 (tras #08,#13) ──► S6
        ── S6: #13 → #14 (Jo) y #15 (Ig) ──────────────────────────────────────
        ── S7: #14 + #15 → #16 (San) ──────────────────────────────────────────
#19 (tras #12,#13,#15,#16)    #22 (tras #15,#16)               #18 (tras #16,#09,#11,#17)
#23 (tras #06,#13,#18,#19)                                     #20 (tras #17,#18) ──► S8
#21 (tras #08,#14,#19,#20)                                     (#21 evidencia: Joaquin aporta)
        ── S8: #19 + #20 → #21 evidencia (San) ────────────────────────────────
                                                              #24 (tras #21,#22,#23) FINAL
```

**Sync points más anchos (proteger):** **S2 (#07 scaffold)** y **S5 (#11
features)** son los de mayor fan-out. **S7 (#16 champion)** libera toda la cola de
serving/retrain/CI.

### Calendario (2026-06-28 → 2026-07-11)

Fines de semana = push/buffer. Today = domingo 06-28; los ADRs arrancan async hoy
(el stack ya está decidido por el north star, así que los ADRs son rápidos).

| Fecha | Santino | Ignacio | Joaquin |
| ----- | ------- | ------- | ------- |
| **Dom 06-28** | (cola #04/#06) | **#01** borrador | **#03** (tras sketch de #01) |
| **Lun 06-29** | #04 (tras #02) | #01 final → **#02** | #03 → **#05** |
| **Mar 06-30** | #06; **#07** inicio + provisioning | #02 final | #05 final; **#17** (mocks) |
| **Mié 07-01** | #07 + **provisioning (Postgres+S3)** ◄S2 | **#09** inicio | **#08** inicio (MLflow + cloud DB) |
| **Jue 07-02** | base CI; cola #12 | #09 → **#10** | #08 (run de ejemplo) ◄S4; pulir #17 |
| **Vie 07-03** | **#12** (tras #11) | **#11** (lags/rolling/trend, sin leakage) ◄S5 | #14 prep; #18 loader skeleton |
| **Sáb 07-04** *(push)* | — | **#13** (LightGBM global) ◄S6 | **#14** (tras #08,#13) |
| **Dom 07-05** *(buffer)* | (cola #16/#19) | **#15** (vs naive+Arps, MASE) | #14 final |
| **Lun 07-06** | **#16** champion (@champion) | #15 → ◄S7; **#22** model card | **#18** runtime (tras #16) |
| **Mar 07-07** | **#19** (job + schedule) | #22 final | #18 → **#20** ◄S8 |
| **Mié 07-08** | **#23** (smokes + build) | (soporte) | #20 final; **#21** evidencia (con Santino) |
| **Jue 07-09** | #21 + #23 wrap | (soporte / pulido) | **#24** README inicio |
| **Vie 07-10** | dry-run E2E | dry-run E2E | #24 README + guion; grabar demo |
| **Sáb 07-11** *(entrega)* | buffer/fixes | buffer/fixes | grabación final + entrega |

#### Veredicto de realismo: AJUSTADO — entra con cortes + el push del finde

Con solo Lun–Vie (10 días hábiles) la cola `#16→#18→#20→#21` / `#19→#23→#24` cae
toda en los últimos 2–3 días sin slack y #23 es XL en rama casi-crítica. Es
factible solo si se usa el finde 07-04/05, la lane de Ignacio no se atrasa, y se
toman estos cortes (en orden de menor riesgo de nota; **ninguno** rompe RF/RNF de
la adenda):

1. **Foldear #12 dentro de #19** — una sola cadena de assets Dagster en vez de dos
   issues; elimina un handoff. ("Repetir para un día dado" lo cumple el `as_of_date`
   de #19.)
2. **Recortar #23 a smokes de PR + build de artefacto; diferir el job de "deploy".**
   No hay prod live; "deploy recurrente = promoción de alias" puede ser manual/CLI
   para la demo. Achica el XL más riesgoso.
3. **Adelgazar #21 a una guía de evidencia manual** (no script pulido) y **#22 al
   model card esencial** que alimenta el video.
4. **Diferir el rollback automático de #16 a manual** (re-apuntar `mlflow alias`);
   se mantiene promoción del champion + gate.

**No cortar (requisitos duros, en/cerca del camino crítico):** #01 (objetivo +
baseline naive + MASE), feature store #09/#11, tracking #08/#14, training #13,
eval-vs-naive #15, serving #17/#18/#20, trigger de retrain #19, README+video #24.
Los últimos dos días (07-10/11) quedan reservados para #24 + grabación + buffer.

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

Re-estimación tras los refinamientos (los issues que crecen: #08 por el cloud
backend; #18 por carga del modelo del registry + acople con `petrocast_ml`; #15
por MASE + Arps + doble baseline; #22 por la sección de métricas):

| Owner | Issues | Esfuerzo |
| ----- | ------ | -------- |
| Santino | #04(M), #06(M), #07(XL), #12(L), #16(L), #19(L), #21(M), #23(XL) | **21 pts** |
| Ignacio | #01(M), #02(M), #09(L), #10(M), #11(L), #13(L), #15(XL), #22(L) | **22 pts** |
| Joaquin | #03(M), #05(M), #08(XL), #14(L), #17(M), #18(XL), #20(L), #24(M) | **22 pts** |

> Nota: #07 sube a XL porque carga el scaffold + el wiring cross-app
> (path-deps en ambos `pyproject.toml` + lockfiles + `COPY` en el Dockerfile de la
> API) + el helper de provisioning. Diferencia máxima entre integrantes = **1 pt**.
> Se mantiene el 8/8/8 sin reasignar issues; los ajustes son a nivel sub-issue
> (ver criterios de #07/#08/#15).

## Protocolo "no pisarse"

Resultado de la auditoría de colisiones de archivos. La regla general: **landear
los seams primero (single-owner)** y para los archivos genuinamente compartidos,
usar **archivos nuevos** o un **protocolo append-only con un integrador**.

### Seams a landear primero (antes de que arranquen los dependientes)

1. **#07 `apps/ml/` (Santino) — la piedra angular.** Debe shipear como **contrato
   completo**, no esqueleto: declarar **todo el set de deps ML de una** en
   `apps/ml/pyproject.toml` (lightgbm, mlflow, scikit-learn, pandas, numpy,
   psycopg) y commitear `uv.lock` una vez → #13/#14/#15 agregan **solo código**.
   Shipear **stubs con firmas congeladas**: `inference.py::load_champion()/predict()`,
   lector de `features/`, `tracking.py`, `registry.py`. Landear el **wiring
   cross-app** (path-dep en `apps/api` y `apps/data`, regenerar ambos `uv.lock`,
   `COPY` en `apps/api/Dockerfile`).
2. **#09 contrato del feature store (Ignacio) — antes de #11/#12/#18.** Congelar la
   clave `(well_id, as_of_date)`, el schema `features`, los **nombres/tags** de los
   modelos dbt y el init SQL.
3. **#17 schema OpenAPI de predicción (Joaquin) — antes de #18/#20.** Landear
   `apps/api/src/schemas/prediction.py` (request/response/error) primero.
4. **Contrato C de conexión a MLflow (de #03/#08).** Publicar los nombres exactos de
   env-vars una vez; #14 (logging) y #18 (load) agregan claves idénticas a sus
   settings `extra="forbid"` sin churn.

### Archivos calientes y su protocolo

| Archivo | Issues (owner) | Protocolo |
| ------- | -------------- | --------- |
| `.github/workflows/ci.yml` | #07(S), #08(J), #10(I), #23(S) | **Integrador único: Santino (#23).** Cada agregado = **nuevo job top-level** (bloque YAML independiente → merge limpio). No editar los jobs `test`/`data-pipeline` existentes. Reservar nombres: `ml-tests`, `ml-training-smoke`, `ml-inference-smoke`. |
| `apps/ml/pyproject.toml` + `uv.lock` | #07(S), #13(I), #14(J), #15(I) | **Declarar todas las deps ML en #07** y commitear el lock una vez. Nunca mergear `uv.lock` a mano: tomar ambos `pyproject.toml`, re-correr `uv lock`, commitear. |
| `apps/data/src/petrocast_data/definitions.py` | #12(S), #19(S), recurso MLflow(J) | **Integrador: Santino** (ya posee #12 + #19). Poner el **recurso MLflow en `resources.py`**, no inline, para que #08/#14 (Joaquin) y #12/#19 (Santino) toquen archivos distintos. |
| `docs/adr/README.md` | #01,#02(I); #03,#05(J); #04,#06(S) | **Append-only, numeración reservada ya** (0030–0035). Cada PR de ADR agrega su fila al final; mergear los PRs de ADR **en orden numérico**. |
| `apps/api/src/core/config.py` + `apps/data/.../settings.py` | #08/#18(J), #19(S) | `extra="forbid"` → tratar las claves ML como **un bloque reservado** agregado una vez por app (en el wiring de #07/#08), para que #14/#18/#19 no re-editen settings. |
| `apps/api/pyproject.toml`/`uv.lock`/`Dockerfile` | #07(S), #18(J) | #07 landea path-dep + `COPY` primero; #18 solo agrega el import. |

### Archivos NUEVOS en vez de editar compartidos

- MLflow service → **`infra/compose.mlflow.yml`** (no `compose.data.yml`).
- Backend MLflow + schema features → **`infra/data/postgres/init/003-create-mlflow-db.sql`**
  y **`004-create-features-schema.sql`** (el dir corre en orden; nunca editar `001`).
- Build/deploy ML → **`.github/workflows/build-ml.yml`** (espejo de `build-data.yml`,
  `paths: apps/ml/**`), manteniendo mínimas las ediciones de `ci.yml`.

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
- **Norte (north star):** target = **producción mensual de petróleo por pozo**
  (`prod_pet`, m³); modelo = **un único LightGBM global**; horizonte **en meses**;
  métricas **MAE/RMSE + MASE** primarias, **MAPE-sobre-no-cero** secundaria;
  baselines = **persistencia naive** (obligatorio por PRD) + **Arps** (best-effort).
- **Footprint:** crear `docs/adr/0030-objetivo-predictivo-horizonte-metricas.md`;
  modificar `docs/adr/README.md` (1 fila, append-only).
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0030-*.md` con comparación de alternativas.
  - [ ] Define target, horizonte (en meses), granularidad y unidad de predicción (m³).
  - [ ] Define **`well_id` = `sigla` vs `idpozo`** alineado a `gold.fact_production`
        (resuelve A3 de `supuestos-y-clarificaciones.md`).
  - [ ] Define métricas primarias (**MAE/RMSE/MASE**) y secundaria (MAPE-no-cero),
        justificando MASE por robustez a ceros y por codificar "ganarle al naive".
  - [ ] Define baselines (naive obligatorio; Arps best-effort) y filtro de pozos
        ≥12 meses de histórico.
  - [ ] Define umbrales del gate (insumo de #15/#16).
  - [ ] Explica por qué el objetivo elegido aporta valor al usuario de la API.
  - [ ] Actualiza `docs/adr/README.md`.
- **Contrato que congela:** F (métricas/horizonte) — consumido por #13/#15/#16/#17/#22.
- **Referencias:** adenda Fase 3; `supuestos-y-clarificaciones.md` P2/P4; ADR-0001; ADR-0006.

### 02 — ADR: estrategia de feature store

- **Owner:** Ignacio · **Tipo:** `docs(adr)` · **Labels:** `adr`,
  `feature-store`, `ml` · **Depende de:** #01
- **Rama sugerida:** `docs/f3-02-adr-feature-store-strategy`
- **Decisión a documentar:** dónde y cómo persistir features para entrenamiento
  e inferencia. Comparar al menos: tablas PostgreSQL propias, Feast, DuckDB/Parquet
  y cálculo on-demand sin store.
- **Norte:** **tablas en schema `features` de Postgres generadas por dbt**; clave
  `(well_id, as_of_date)`; PIT. El ADR **debe justificar por qué no Feast** (sin
  serving online de baja latencia, evita ops) — eso satisface "comparar alternativas".
- **Footprint:** crear `docs/adr/0031-estrategia-feature-store.md`; modificar
  `docs/adr/README.md`.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0031-*.md` con comparación de alternativas.
  - [ ] Define esquema offline (justifica un store unificado sin online layer).
  - [ ] Define claves (`well_id`, `as_of_date`, horizonte) y versionado de features.
  - [ ] Explica cómo se evita training-serving skew (misma tabla leída en train e
        inferencia, keyed por `as_of_date`).
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda RNF feature store; ADR-0023; ADR-0024.

### 03 — ADR: tracking de experimentos y registry de modelos

- **Owner:** Joaquin · **Tipo:** `docs(adr)` · **Labels:** `adr`,
  `tracking`, `mlops` · **Depende de:** #01
- **Rama sugerida:** `docs/f3-03-adr-experiment-tracking`
- **Decisión a documentar:** plataforma para tracking reproducible y registro
  de modelos. Comparar al menos: MLflow OSS, Weights & Biases, ClearML y tracking
  casero con archivos/DB.
- **Norte:** **MLflow OSS**; backend store en **Postgres en la nube** (Neon/Supabase
  free, o RDS) + artefactos en **S3**; **aliases (`@champion`)** no stages
  deprecados; se corre **local para demo** (listo-para-deployar). Justificar el
  modelo "DB en la nube compartida + UI local" como forma de compartir runs/modelo
  sin server 24/7.
- **Footprint:** crear `docs/adr/0032-tracking-experimentos-registry.md`; modificar
  `docs/adr/README.md`.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0032-*.md` con comparación de alternativas.
  - [ ] Define dónde viven runs, métricas, params, artefactos y modelo champion
        (backend cloud Postgres + artifacts S3; alias `champion`).
  - [ ] Explica cómo un ML Engineer inspecciona distintos runs (UI local contra DB
        compartida).
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
- **Norte:** **Dagster**; `as_of_date` como **partición**; primer
  **`ScheduleDefinition`** del repo. "Despliegue recurrente" = promoción de alias
  (no redeploy del contenedor).
- **Footprint:** crear `docs/adr/0033-orquestacion-entrenamiento-retraining.md`;
  modificar `docs/adr/README.md`.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0033-*.md` con comparación de alternativas.
  - [ ] Define partición / fecha de corte (`as_of_date`) para training.
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
- **Norte:** **modelo embebido en FastAPI**, champion cargado del registry
  (alias); features leídas del store (no recalculo in-memory). Trade-off a
  documentar: la imagen de la API gana deps ML (`lightgbm`, cliente `mlflow`).
- **Footprint:** crear `docs/adr/0034-serving-modelo-contrato-api.md`; modificar
  `docs/adr/README.md`.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0034-*.md` con comparación de alternativas.
  - [ ] Define contrato de request/response, errores y versionado (consistente con #17).
  - [ ] Define cómo se cargan modelo y features durante inferencia.
  - [ ] Justifica latencia, simplicidad y demo sin producción live.
  - [ ] Actualiza `docs/adr/README.md`.
- **Referencias:** adenda RF API; ADR-0007; ADR-0012; ADR-0014.

### 06 — ADR: CI/CD de pipelines ML y promoción de artefactos

- **Owner:** Santino · **Tipo:** `docs(adr)` · **Labels:** `adr`, `ci`,
  `mlops` · **Depende de:** #03, #04, #05
- **Rama sugerida:** `docs/f3-06-adr-ml-cicd`
- **Decisión a documentar:** cómo validar y desplegar pipelines de
  procesamiento, entrenamiento y artefactos de modelo. Comparar al menos:
  GitHub Actions con imágenes Docker, Dagster deploy manual, scripts locales y
  despliegue acoplado al API.
- **Norte:** **GitHub Actions** reusando OIDC→ECR→SSM; `build-ml.yml` espejo de
  `build-data.yml`; smokes de training/inference sobre fixtures offline.
- **Footprint:** crear `docs/adr/0035-cicd-pipelines-ml-promocion.md`; modificar
  `docs/adr/README.md`.
- **Criterios de aceptación:**
  - [ ] ADR nuevo `docs/adr/0035-*.md` con comparación de alternativas.
  - [ ] Define checks mínimos de PR para features/training/inference.
  - [ ] Define promoción de artefactos y rollback de modelo (re-apuntar alias).
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
  training, inference y tests, sin mezclar responsabilidades con API o dbt. Es el
  **seam keystone**: debe shipear como contrato completo (deps + stubs + wiring),
  no como esqueleto. Ver [Dónde vive el código ML](#dónde-vive-el-código-ml).
- **Footprint:**
  - **Crear:** `apps/ml/pyproject.toml`, `apps/ml/uv.lock`, `apps/ml/README.md`,
    `apps/ml/src/petrocast_ml/{__init__,config,inference,tracking,registry}.py`
    (stubs con firmas congeladas), `apps/ml/src/petrocast_ml/features/__init__.py`,
    `apps/ml/src/petrocast_ml/py.typed`, `apps/ml/tests/smoke/test_import.py`,
    `apps/ml/Dockerfile` (o diferir a #23).
  - **Modificar (wiring cross-app):** `apps/api/pyproject.toml` + `apps/api/uv.lock`
    (path-dep `petrocast-ml`), `apps/data/pyproject.toml` + `apps/data/uv.lock`
    (path-dep), `apps/api/Dockerfile` (`COPY` del paquete), root `README.md` (mención).
- **Criterios de aceptación:**
  - [ ] Paquete `apps/ml/` (`petrocast_ml`) creado según ADR-0006, con
        `tool.uv.sources` path-dep desde `apps/api` y `apps/data`.
  - [ ] **Todas** las deps ML declaradas de una (lightgbm, mlflow, scikit-learn,
        pandas, numpy, psycopg) y `uv.lock` commiteado → dependientes agregan solo código.
  - [ ] Stubs con firmas públicas congeladas: `load_champion()`, `predict()`,
        `train()`, lector de features, cliente de tracking.
  - [ ] Configuración por entorno alineada con ADR-0018 (bloque reservado de claves ML).
  - [ ] Tests smoke verifican import/config del paquete ML.
  - [ ] README local explica comandos básicos.
  - [ ] (Sub-tarea infra) Helper de provisioning del backend cloud preparado en
        coordinación con #08 (no bloquea si #08 lo absorbe).
- **Contrato que congela:** E (deps ML / imagen API), interfaz pública de `petrocast_ml`.
- **Referencias:** #01, #02, #03; ADR-0003; ADR-0014; ADR-0018.

### 08 — Plataforma de tracking de experimentos

- **Owner:** Joaquin · **Tipo:** `feat(mlops)` · **Labels:** `tracking`,
  `infra`, `mlops` · **Depende de:** #03, #07 · **Esfuerzo:** XL
- **Rama sugerida:** `feat/f3-08-experiment-tracking-platform`
- **Contexto:** los ML Engineers deben poder ver runs, métricas y artefactos en
  una plataforma reproducible. Incluye **provisionar el backend compartido en la
  nube** (la decisión concreta sale de #03). Se deja **listo-para-deployar** y se
  corre **local para la demo**.
- **Footprint:**
  - **Crear:** `infra/compose.mlflow.yml`,
    `infra/data/postgres/init/003-create-mlflow-db.sql`, runbook en `docs/runbooks/`.
  - **Modificar:** `infra/compose.staging.yml` (router Traefik `mlflow.staging.*`,
    solo dejado listo), `apps/api/.env.example` + `apps/data/.env.example`
    (`MLFLOW_TRACKING_URI`, etc.), `.github/workflows/ci.yml` (smoke del cliente —
    vía #23 si es posible), opcional `infra/terraform/.../s3-artifacts` (bucket).
- **Criterios de aceptación:**
  - [ ] Provisionar **Postgres en la nube** (Neon/Supabase free, o RDS) como backend
        store + bucket **S3** para artefactos; MLflow apunta a ambos por env-vars.
  - [ ] Compose local levanta MLflow (UI) contra el backend cloud + S3.
  - [ ] `infra/compose.staging.yml` queda **preparado** (router/secrets) sin deployar.
  - [ ] Credenciales/paths/config se inyectan por variables de entorno.
  - [ ] Hay un run de ejemplo visible con params y métricas.
  - [ ] Documentación indica URL/comando, y cómo el equipo comparte runs vía la DB cloud.
  - [ ] CI valida al menos la configuración o el smoke del cliente.
- **Contrato que congela:** C (config de tracking) — consumido por #14/#15/#16/#19.
- **Referencias:** adenda RF tracking; #03; ADR-0027.

### 09 — Schema y modelos base del feature store

- **Owner:** Ignacio · **Tipo:** `feat(data)` · **Labels:** `feature-store`,
  `dbt`, `ml` · **Depende de:** #02, #07
- **Rama sugerida:** `feat/f3-09-feature-store-schema`
- **Contexto:** la adenda exige persistir features y usarlas en inferencia. El
  store debe partir de `gold.fact_production` y conservar fecha de corte
  (`as_of_date`). Congela el **contrato A** que consumen #11/#12/#18.
- **Footprint:**
  - **Crear:** `apps/data/dbt/models/features/` (`schema.yml`,
    `_features__sources.yml`, `feature_store_base.sql`),
    `infra/data/postgres/init/004-create-features-schema.sql`.
  - **Modificar:** `apps/data/dbt/dbt_project.yml` (bloque `features: +schema: features`).
- **Criterios de aceptación:**
  - [ ] Schema/tablas `features` creadas según #02; init SQL `004-*`.
  - [ ] Modelos dbt generan tabla base con `well_id`, `as_of_date` y features iniciales.
  - [ ] Tests validan unicidad por clave `(well_id, as_of_date)`.
  - [ ] Documentación explica grano, claves y relación con Gold; **unidades en m³**.
  - [ ] No se calcula feature crítica solo en memoria durante inferencia.
- **Contrato que congela:** A (tabla del feature store) — consumido por #11/#12/#18.
- **Referencias:** adenda RNF feature store; ADR-0023; ADR-0024.

### 10 — Fixtures y datasets de entrenamiento reproducibles

- **Owner:** Ignacio · **Tipo:** `test(ml)` · **Labels:** `ml`, `testing`,
  `datos` · **Depende de:** #01, #09
- **Rama sugerida:** `test/f3-10-training-fixtures`
- **Contexto:** CI no debe depender de internet ni de datasets pesados para
  validar training/inference. Se necesitan fixtures mínimos y representativos.
  *(Si la lane de Ignacio se atrasa, Santino puede emparejar acá — ver cuello de
  botella en el camino crítico.)*
- **Footprint:** crear `apps/ml/tests/fixtures/*.csv`, `apps/ml/tests/conftest.py`.
- **Criterios de aceptación:**
  - [ ] Fixtures pequeños cubren varios pozos, meses y casos faltantes (incl. meses
        en cero, para ejercitar MASE).
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
  producción, evitando leakage respecto de la fecha de corte. Es el **sync point
  S5** (fan-out a #12 y #13).
- **Footprint:**
  - **Crear:** `apps/data/dbt/models/features/*.sql` (lags/rolling/trend),
    `apps/ml/src/petrocast_ml/features/*.py`.
  - **Modificar:** `apps/data/dbt/models/features/schema.yml` (creado en #09).
- **Criterios de aceptación:**
  - [ ] Features de lags, rolling windows y tendencia quedan persistidas.
  - [ ] Tests validan que **ninguna feature mira datos posteriores a `as_of_date`**
        (regla PIT del contrato A).
  - [ ] Se documenta cada feature con descripción y tipo.
  - [ ] La salida es consumible por training (#13) e inference (#18).
  - [ ] dbt/Dagster muestra lineage desde Gold hasta feature store.
- **Referencias:** adenda RNF feature store; #01; #02; #09.

### 12 — Asset Dagster de materialización de features

- **Owner:** Santino · **Tipo:** `feat(data)` · **Labels:** `dagster`,
  `feature-store`, `mlops` · **Depende de:** #04, #09, #11
- **Rama sugerida:** `feat/f3-12-feature-materialization-asset`
- **Contexto:** la generación de features debe poder repetirse para un día dado
  y quedar visible en la orquestación. *(Candidato a foldear en #19 si el calendario
  aprieta — ver cortes.)*
- **Footprint:**
  - **Crear:** `apps/data/src/petrocast_data/assets/features.py`.
  - **Modificar:** `apps/data/src/petrocast_data/definitions.py` (registrar asset —
    **Santino integrador**), `apps/data/src/petrocast_data/assets/__init__.py`.
- **Criterios de aceptación:**
  - [ ] Asset/job Dagster materializa features para `as_of_date` (partición).
  - [ ] El asset expone metadata útil: filas, rango de fechas, hash/config.
  - [ ] Se puede ejecutar desde CLI y UI de Dagster.
  - [ ] Retries y logs siguen el patrón de Fase 2.
  - [ ] Tests o smoke local validan una materialización con fixtures.
- **Referencias:** adenda RNF orquestación; #04; #09; #11; ADR-0028.

### 13 — Pipeline de entrenamiento baseline

- **Owner:** Ignacio · **Tipo:** `feat(ml)` · **Labels:** `training`, `ml` ·
  **Depende de:** #01, #10, #11
- **Rama sugerida:** `feat/f3-13-baseline-training-pipeline`
- **Contexto:** se necesita un modelo predictivo inicial simple, reproducible y
  evaluable antes de optimizar. **Norte: un único LightGBM global** sobre todos los
  pozos con features de #11 + estáticas del pozo.
- **Footprint:**
  - **Crear:** `apps/ml/src/petrocast_ml/training/*.py`.
  - **Modificar:** `apps/ml/README.md` (deps ya están en #07 → no tocar el lock).
- **Criterios de aceptación:**
  - [ ] Script/asset de training entrena un **LightGBM global** con parámetros fijos.
  - [ ] Se guarda artefacto de modelo con metadata de dataset y código.
  - [ ] Se separan train/validation/test **temporalmente** (sin split aleatorio).
  - [ ] Se computa el **baseline naive** (persistencia) en el mismo split.
  - [ ] Training smoke corre con fixtures en CI.
  - [ ] README del módulo explica cómo entrenar localmente.
- **Referencias:** adenda contexto modelo predictivo; #01; #10; #11.

### 14 — Registro de runs, métricas y artefactos

- **Owner:** Joaquin · **Tipo:** `feat(mlops)` · **Labels:** `tracking`,
  `training`, `mlops` · **Depende de:** #08, #13
- **Rama sugerida:** `feat/f3-14-training-run-tracking`
- **Contexto:** el video debe mostrar métricas de training en distintos runs.
  El tracking tiene que ser automático, no una captura manual.
- **Footprint:**
  - **Crear:** `apps/ml/src/petrocast_ml/tracking.py` (rellena el stub de #07).
  - **Modificar:** `apps/ml/src/petrocast_ml/training/*.py` (instrumentar — mismos
    archivos que escribió Ignacio en #13; coordinar por el orden de dependencia),
    `apps/*/.env.example`.
- **Criterios de aceptación:**
  - [ ] Cada entrenamiento registra params, métricas, tags y artefactos en MLflow.
  - [ ] Se pueden distinguir al menos dos runs en la UI de tracking.
  - [ ] El run guarda versión/corte de features (`as_of_date`) y commit o imagen usada.
  - [ ] Tests mockean el cliente de tracking o validan el formato de logging.
  - [ ] Documentación explica cómo encontrar los runs para la demo.
- **Referencias:** adenda RF tracking y video; #03; #08; #13.

### 15 — Evaluación, backtesting y gates de calidad del modelo

- **Owner:** Ignacio · **Tipo:** `feat(ml)` · **Labels:** `evaluation`,
  `quality`, `ml` · **Depende de:** #01, #13, #14 · **Esfuerzo:** XL
- **Rama sugerida:** `feat/f3-15-model-evaluation-gates`
- **Contexto:** el modelo no debería promocionarse si empeora contra baseline
  o si sus métricas son inválidas. Crece a XL por **MASE + Arps + doble baseline +
  distribución**.
- **Footprint:** crear `apps/ml/src/petrocast_ml/evaluation/*.py` (incl. util MASE y
  baseline Arps); modificar el pipeline de training + `apps/ml/tests/`.
- **Criterios de aceptación:**
  - [ ] Backtesting temporal calcula las métricas de #01 (MAE/RMSE/**MASE** +
        MAPE-no-cero).
  - [ ] Compara contra **naive (obligatorio, baseline del gate)** y **Arps
        (best-effort, comparación primaria de industria)**.
  - [ ] Reporta distribución (mediana/p75/p90), no solo promedio; filtra pozos
        <12 meses.
  - [ ] **Gate automático** falla si las métricas superan los umbrales de #01.
  - [ ] Resultados quedan registrados en tracking (MLflow).
  - [ ] Tests cubren éxito y falla del gate.
  - [ ] *(Fallback)* si Arps resulta fiddly, el gate usa solo naive sin bloquear la entrega.
- **Referencias:** #01; #03; `supuestos-y-clarificaciones.md` P4; ADR-0016.

### 16 — Registro y promoción del modelo champion

- **Owner:** Santino · **Tipo:** `feat(mlops)` · **Labels:** `registry`,
  `deployment`, `mlops` · **Depende de:** #03, #14, #15
- **Rama sugerida:** `feat/f3-16-model-registry-promotion`
- **Contexto:** la API necesita saber cuál modelo usar. La promoción debe ser
  trazable y reversible. **Usar aliases (`@champion`), no `stage` deprecado.**
- **Footprint:** crear `apps/ml/src/petrocast_ml/registry.py` (rellena stub de #07);
  modificar integración de tracking/registry; posible asset en `definitions.py` si
  la promoción es un asset Dagster.
- **Criterios de aceptación:**
  - [ ] Existe el alias **`champion`** sobre el modelo registrado.
  - [ ] Solo se promociona si pasa los gates de #15.
  - [ ] Se persiste metadata de versión, `as_of_date` de training y métricas.
  - [ ] Mecanismo de **rollback** = re-apuntar el alias a la versión anterior
        (manual/CLI aceptable para la demo).
  - [ ] Documentación explica cómo inspeccionar/promover/rollback.
- **Contrato que congela:** B (registry / alias champion) — consumido por #18.
- **Referencias:** #03; #06; #15.

---

## M4 — Serving e integración API

### 17 — Contrato OpenAPI de predicciones

- **Owner:** Joaquin · **Tipo:** `feat(api)` · **Labels:** `api`,
  `contract`, `ml-serving` · **Depende de:** #05
- **Rama sugerida:** `feat/f3-17-prediction-api-contract`
- **Contexto:** los usuarios de API deben poder consumir el servicio predictivo
  con un contrato claro y validado. Seam a landear temprano (puede arrancar con
  mocks apenas #05 esté decidido).
- **Footprint:** crear `apps/api/src/schemas/prediction.py`; modificar
  `apps/api/tests/contract/test_openapi_contract.py`.
- **Criterios de aceptación:**
  - [ ] Request/response de predicción documentados en OpenAPI.
  - [ ] Incluye `horizon` **en meses**, pozo/entidad y `as_of_date`; predicciones en **m³**.
  - [ ] Errores esperados tienen schema y status code definidos; auth `X-API-Key`.
  - [ ] Contract tests verifican el OpenAPI (Schemathesis).
  - [ ] Ejemplos de requests quedan en README o colección de demo.
- **Contrato que congela:** D (OpenAPI de predicción) — consumido por #18/#20/#21/#23/#24.
- **Referencias:** adenda RF API; #05; ADR-0007.

### 18 — Runtime de inferencia con modelo y feature store

- **Owner:** Joaquin · **Tipo:** `feat(api)` · **Labels:** `inference`,
  `feature-store`, `ml-serving` · **Depende de:** #09, #11, #16, #17 · **Esfuerzo:** XL
- **Rama sugerida:** `feat/f3-18-inference-runtime`
- **Contexto:** inferencia debe usar features persistidas y el modelo champion,
  no recalcular todo ad hoc dentro del endpoint. Acopla la API al paquete
  `petrocast_ml` y al registry (contratos B y E).
- **Footprint:**
  - **Crear:** `apps/api/src/services/prediction_service.py`,
    `apps/api/src/repositories/feature_repository.py`,
    `apps/ml/src/petrocast_ml/inference.py` (loader del champion — rellena stub de #07).
  - **Modificar:** `apps/api/src/core/config.py` (claves MLflow/modelo, bloque
    reservado, `extra="forbid"`), `apps/api/Dockerfile` (si #07 no agregó el `COPY`).
- **Criterios de aceptación:**
  - [ ] Loader obtiene el champion vía `models:/<name>@champion`.
  - [ ] Inferencia lee features **persistidas** (schema `features`) para la
        entidad/`as_of_date` solicitada.
  - [ ] Maneja ausencia de features/modelo con errores claros.
  - [ ] Tests unitarios cubren predicción exitosa y casos de error.
  - [ ] Métricas/logs básicos permiten auditar la **versión de modelo** usada.
- **Referencias:** adenda RNF feature store; #05; #09; #11; #16; #17.

### 19 — Job y schedule de retraining

- **Owner:** Santino · **Tipo:** `feat(mlops)` · **Labels:** `dagster`,
  `retraining`, `mlops` · **Depende de:** #04, #12, #13, #15, #16
- **Rama sugerida:** `feat/f3-19-retraining-job-schedule`
- **Contexto:** la adenda exige entrenamiento/despliegue recurrente y
  automático, además de repetir training para un día dado.
- **Footprint:**
  - **Crear:** `apps/data/src/petrocast_data/assets/training.py` (cadena
    features→train→eval→promote), `apps/data/src/petrocast_data/schedules.py` (o inline).
  - **Modificar:** `apps/data/src/petrocast_data/definitions.py` (registrar job +
    **primer `schedules=[ScheduleDefinition(...)]`** — Santino integrador),
    `apps/data/src/petrocast_data/settings.py` (claves MLflow del proceso de training).
- **Criterios de aceptación:**
  - [ ] Job Dagster encadena features → training → evaluation → promotion.
  - [ ] Se puede ejecutar para un `as_of_date` específico (partición).
  - [ ] Schedule recurrente configurado y documentado.
  - [ ] Trigger manual queda demostrado por CLI o UI de Dagster.
  - [ ] Logs/metadata muestran fecha, modelo resultante y estado de promoción.
- **Referencias:** adenda RNF orquestación/retraining; #04; #12; #13; #15; #16.

### 20 — Endpoint REST de predicciones integrado

- **Owner:** Joaquin · **Tipo:** `feat(api)` · **Labels:** `api`,
  `prediction`, `ml-serving` · **Depende de:** #17, #18
- **Rama sugerida:** `feat/f3-20-prediction-endpoint`
- **Contexto:** la API existente debe devolver predicciones generadas por el
  modelo, manteniendo compatibilidad razonable con el contrato actual.
- **Footprint:**
  - **Crear:** `apps/api/src/api/v1/endpoints/prediction.py`,
    `apps/api/tests/integration/api/v1/test_prediction.py`.
  - **Modificar:** `apps/api/src/api/v1/router.py` (incluir router — Joaquin),
    `apps/api/README.md` (curl).
- **Criterios de aceptación:**
  - [ ] Endpoint REST devuelve predicciones usando el runtime de #18.
  - [ ] Tests de integración cubren llamadas reales con fixture/modelo smoke.
  - [ ] OpenAPI muestra ejemplos de predicción.
  - [ ] Respuesta incluye metadata mínima: **versión de modelo, `as_of_date` y
        horizonte** (en meses).
  - [ ] Se documentan comandos `curl` para la demo.
- **Referencias:** adenda RF API y video; #05; #17; #18.

---

## M5 — Automatización, CI/CD y evidencia

### 21 — Evidencia demo de tracking y API

- **Owner:** Santino · **Tipo:** `docs(demo)` · **Labels:** `demo`,
  `tracking`, `api` · **Depende de:** #08, #14, #19, #20
- **Rama sugerida:** `docs/f3-21-demo-evidence`
- **Contexto:** el video debe mostrar métricas en distintos runs, llamadas a la
  API bajo distintas condiciones y **trigger de retrain** (de ahí la dependencia
  agregada de #19).
- **Footprint:** crear `docs/fase-3/demo-*.md`, opcional `infra/scripts/demo/*.sh`
  (mayormente archivos nuevos).
- **Criterios de aceptación:**
  - [ ] Script o guía genera al menos dos runs con métricas distintas.
  - [ ] Script o guía ejecuta llamadas a la API con escenarios distintos.
  - [ ] Demuestra el **trigger de retrain** (#19) por CLI/UI de Dagster.
  - [ ] Se listan pantallas/evidencias necesarias para el video.
  - [ ] Los comandos funcionan sin servicio live en producción.
  - [ ] Se documentan datos de ejemplo y resultados esperados.
- **Referencias:** adenda video; #08; #14; #19; #20.

### 22 — Reporte de backtesting y model card

- **Owner:** Ignacio · **Tipo:** `docs(ml)` · **Labels:** `model-card`,
  `evaluation`, `ml` · **Depende de:** #15, #16
- **Rama sugerida:** `docs/f3-22-model-card-backtesting`
- **Contexto:** el equipo necesita explicar el valor agregado y los límites del
  modelo de forma entendible. Crece a L por la sección de métricas/baselines.
- **Footprint:** crear `docs/fase-3/model-card.md`, `docs/fase-3/backtesting-report.md`.
- **Criterios de aceptación:**
  - [ ] Model card documenta objetivo, datos, features, métricas y limitaciones.
  - [ ] Reporte resume backtesting con métricas en **m³** y comparación contra
        **naive y Arps** (distribución, no solo promedio).
  - [ ] Se incluyen riesgos: leakage, datos faltantes, drift y sesgos.
  - [ ] Se vincula el modelo champion con su run de tracking.
  - [ ] Sirve como insumo directo para el video.
- **Referencias:** adenda video/rationale; #01; #15; #16.

### 23 — CI/CD de pipelines ML y despliegue de artefactos

- **Owner:** Santino · **Tipo:** `ci(ml)` · **Labels:** `ci`, `deployment`,
  `mlops` · **Depende de:** #06, #13, #18, #19 · **Esfuerzo:** XL
- **Rama sugerida:** `ci/f3-23-ml-pipeline-cicd`
- **Contexto:** la adenda exige que los pipelines de procesamiento se desplieguen
  mediante CI/CD. No alcanza con scripts manuales. **Santino es el integrador único
  de `ci.yml`.**
- **Footprint:**
  - **Crear:** `.github/workflows/build-ml.yml` (espejo de `build-data.yml`,
    `paths: apps/ml/**`), `apps/ml/Dockerfile` (si no se creó en #07),
    `docs/runbooks/ml-promotion.md`, opcional `infra/scripts/deploy-ml.sh`.
  - **Modificar:** `.github/workflows/ci.yml` (**nuevos jobs** `ml-tests` /
    `ml-training-smoke` / `ml-inference-smoke` — bloques top-level independientes),
    posible `deploy-staging.yml`.
- **Criterios de aceptación:**
  - [ ] Workflow de PR ejecuta tests ML, training smoke e inference smoke (offline).
  - [ ] Workflow de build publica/empaqueta artefactos (imagen `petrocast/ml` a ECR).
  - [ ] Workflow de deploy actualiza pipelines/servicios definidos en #06.
  - [ ] Falla si el modelo no puede cargar o si el feature store no es usable.
  - [ ] README/runbook explica promoción y rollback.
  - [ ] *(Corte si aprieta)* el job de "deploy" puede diferirse; se mantiene
        smokes + build de artefacto.
- **Referencias:** adenda RNF CI/CD; #06; #13; #18; #19; ADR-0011; ADR-0013.

---

## M6 — Documentación, demo y cierre

### 24 — README Fase 3, arquitectura completa y guion de video

- **Owner:** Joaquin · **Tipo:** `docs(readme)` · **Labels:** `docs`,
  `demo`, `arquitectura` · **Depende de:** #21, #22, #23
- **Rama sugerida:** `docs/f3-24-readme-demo`
- **Contexto:** la adenda exige que la arquitectura completa esté descripta en
  el `README.md` y que el video explique diseño, herramientas, rationale, valor
  agregado y demo. **Funnel de toda la prosa de README** (los demás issues no editan
  `README.md`).
- **Footprint:** modificar root `README.md`, `docs/fase-2/README.md`,
  `docs/architecture/*` (c4-context/c4-containers están vacíos); crear
  `docs/fase-3/README.md`.
- **Criterios de aceptación:**
  - [ ] `README.md` describe arquitectura completa Fase 1 + Fase 2 + Fase 3.
  - [ ] Se documentan herramientas, flujos y decisiones clave con links a ADRs
        (0030–0035).
  - [ ] Se documenta cómo correr tracking, retrain y API de predicciones.
  - [ ] Guion/checklist del video cubre runs, métricas, API y retrain.
  - [ ] `docs/fase-2/README.md` o docs de fase se actualizan si corresponde.
- **Referencias:** adenda RNF README y video; #21; #22; #23.

---

## Contratos de handoff

Congelar el contrato **antes** de que el consumidor arranque. El productor lo
publica como parte de su issue; el consumidor lo asume estable.

| ID | Productor → Consumidor(es) | Contrato mínimo a congelar |
| -- | -------------------------- | -------------------------- |
| **A** | Ignacio #09(schema)+#11(features) → Santino #12 + Joaquin #18 | schema `features`; nombre(s) de tabla; clave `(well_id, as_of_date)` con **`well_id` = `sigla`/`idpozo` decidido**; columnas + dtypes + orden; unidades **m³**; manejo de nulos; **regla PIT**. |
| **B** | Santino #16 → Joaquin #18 | URI de registry; nombre del modelo; **alias `champion`** (no stage); flavor (lightgbm/pyfunc); **signature** (features = contrato A; salida = predicción por mes en m³); call `mlflow.pyfunc.load_model("models:/<name>@champion")`; metadata (versión, `as_of_date`, métricas). |
| **C** | Joaquin #08 → #14/#15/#16/#19 | `MLFLOW_TRACKING_URI`; artifact root (bucket/prefijo S3); creds por env; convención de nombres de experimento; tags de run obligatorios (versión de features/`as_of_date`, commit/imagen). |
| **D** | Joaquin #17 → #18/#20/#21/#23/#24 | request (campo de pozo + `as_of_date` + `horizon` **en meses**); response (predicciones por mes en **m³** + versión + `as_of_date` + horizonte); errores + status codes; auth **`X-API-Key`**. |
| **E** | Santino #07(deps)+#23(imagen) → Joaquin #18/#20 | qué importa la API (`petrocast_ml`: `load_champion()/predict()`); versiones pineadas de `lightgbm` + cliente `mlflow`; `COPY` en `apps/api/Dockerfile`; tamaño de imagen aceptable. |
| **F** | Ignacio #01 → #13/#15/#16/#17/#22 | target (`prod_pet`, m³); horizonte en meses; primarias **MAE/RMSE/MASE**, secundaria **MAPE-no-cero**; baselines **naive (oblig.) + Arps**; filtro ≥12 meses; split temporal; umbrales del gate. |

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
| #07 | `feat(ml): scaffold predictive modeling package` |
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
