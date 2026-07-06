# F3-22 — Reporte de backtesting y model card (diseño)

- **Issue:** [#125](https://github.com/joaquinleondev/petrocast/issues/125)
- **Fecha:** 2026-07-06
- **Estado:** aprobado

## Objetivo

Explicar el valor agregado y los límites del modelo champion de forma
entendible, con números reales de backtesting, como insumo directo para el
video de la entrega. Dos documentos nuevos: `docs/fase-3/model-card.md` y
`docs/fase-3/backtesting-report.md`.

## Contexto

- F3-15 (#118) dejó `petrocast_ml.evaluation`: `evaluate()` produce un
  `EvaluationReport` con distribuciones per-well, gates ADR-0030 y conteos de
  cobertura, persistido como `evaluation.json` y espejado como métricas
  `eval_*` en MLflow.
- F3-16 (#119, PR #148) dejó el registry con promoción reversible por alias
  (`register_candidate` / `promote_champion`).
- F3-19 (#149) dejó los assets Dagster `ml/training_candidate` →
  `ml/model_evaluation` → `ml/champion_promotion`, que leen del feature store
  postgres y ejecutan la cadena completa entrenar → evaluar → promover.
- Los fixtures de tests son diminutos (el baseline pierde contra la naive con
  MASE ~42); los números del reporte deben salir de una corrida sobre datos
  reales de datos.gob.ar (capítulo IV, producción por pozo).

## Decisión de enfoque

**Dagster end-to-end sobre datos reales, en infraestructura local efímera.**
Alternativas consideradas: (B) exportar CSVs del feature store y correr el
training CLI + registry CLI a mano — menos piezas pero champion promovido
fuera del asset oficial; (C) fixtures del repo — inmediato pero números sin
valor para el video. Se eligió A porque ejercita el código mergeado de los
PRs #148 y #149 y produce un champion real con run de tracking vinculable.

## Corrida real (infra local, no entra al repo)

1. Postgres efímero (docker, init scripts de `infra/data/postgres/init`).
2. MLflow server local con backend `sqlite:///` (MLflow 3.14 rechaza file
   store); `MLFLOW_TRACKING_URI` apuntando ahí.
3. Bronze con las URLs reales de `apps/data/.env.example`
   (`PETROCAST_SOURCE_*`); una partición mensual = un snapshot completo del
   recurso.
4. dbt silver/gold con `--indirect-selection cautious`; features
   materializadas para ~24 particiones `as_of` (la elegibilidad del backtest
   exige ≥ 12 meses de historia y el test cubre horizontes 1–3).
5. Materializar `ml/training_candidate`, `ml/model_evaluation`,
   `ml/champion_promotion` → `evaluation.json`, `run_id` MLflow, versión y
   alias del champion.

**Riesgo dimensionado antes de correr:** el CSV de capítulo IV es nacional
(millones de filas). Primero se mide el tamaño del recurso; si la ingesta
completa es inviable localmente, se recorta a un subconjunto (por ejemplo una
cuenca) y el reporte declara ese alcance de forma explícita.

## `docs/fase-3/backtesting-report.md`

- **Metodología:** contrato F (split single-origin, horizontes 1–3, convención
  target `as_of + (h − 1)`), elegibilidad ≥ 12 meses observados, convención
  MASE congelada (denominador = diffs entre filas observadas sucesivas).
- **Resultados:** tabla de gates (nombre, umbral, valor, veredicto, si
  bloquea), MAE agregado en m³ modelo vs naive, y tablas de distribución
  per-well (cuantiles) para `mase`, `model_mae_m3`, `naive_mae_m3`,
  `mape_nonzero_pct` y `arps_mape_nonzero_pct` — distribución, no solo
  promedio.
- **Baselines:** naive de persistencia y Arps (fit propio con scipy; share de
  fits exitosos/fallidos y bandera de degradación).
- **Cobertura:** pozos en test / elegibles / excluidos por historia corta /
  MASE indefinido.
- **Reproducibilidad:** sección con los comandos exactos de la corrida.
- **Anexo:** copia del `evaluation.json` en `docs/fase-3/assets/` (auditable
  sin MLflow).

## `docs/fase-3/model-card.md`

Formato model card estándar (Mitchell et al.) adaptado:

- Objetivo y uso previsto; usos fuera de alcance.
- Datos: fuente (datos.gob.ar capítulo IV), ventana temporal, granularidad
  mensual por pozo.
- Features: contrato A (`features.well_features`, ADR-0031).
- Modelo: LightGBM baseline con hiperparámetros fijos (F3-13).
- Métricas y gates: resumen con link al reporte de backtesting.
- Riesgos y limitaciones: leakage (mitigación: test PIT de F3-11), datos
  faltantes (`zero_months_12m`, meses sin reporte), drift (mitigación:
  retraining F3-19), sesgos de cobertura (cuenca / tipo de recurso).
- Champion: nombre registrado, versión, alias, `run_id` y cómo resolverlo por
  alias (ADR-0032).

## Alcance y forma

- Docs en español, consistentes con el resto de `docs/`.
- Sin script generador de reportes (YAGNI): los números se transcriben de la
  corrida real y la sección de reproducibilidad cubre la regeneración.
- Branch `docs/f3-22-model-card-backtesting`; PR
  `docs(ml): add model card and backtesting report`, `Closes #125`.
- Verificación: markdownlint y cotejo de números contra `evaluation.json`.

## Criterios de aceptación (del issue)

- [ ] Model card documenta objetivo, datos, features, métricas y limitaciones.
- [ ] Reporte resume backtesting con métricas en m³ y comparación contra naive
      y Arps (distribución, no solo promedio).
- [ ] Se incluyen riesgos: leakage, datos faltantes, drift y sesgos.
- [ ] Se vincula el modelo champion con su run de tracking.
- [ ] Sirve como insumo directo para el video.
