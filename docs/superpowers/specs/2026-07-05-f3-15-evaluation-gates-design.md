# Diseño F3-15 — Evaluación, backtesting y gates de calidad

- **Issue:** [#118](https://github.com/joaquinleondev/petrocast/issues/118) · **Rama:** `feat/f3-15-model-evaluation-gates`
- **Contratos consumidos:** F (ADR-0030: métricas, gates, filtro, agregación single-origin), A (features), C (tracking MLflow, ADR-0032)
- **Decisiones de sesión:** Arps con ajuste propio (`scipy.optimize.curve_fit`, sin `petbox-dca`); gate obligatorio fallido ⇒ registrar todo y `exit code 1`.

## Alcance

Agregar evaluación completa post-entrenamiento al pipeline offline: métricas del contrato F por pozo y en distribución, doble baseline (naive obligatorio, Arps best-effort), gates automáticos de promoción y registro en MLflow. `train()` (F3-13) no cambia.

Fuera de alcance: promoción del champion (#16), orquestación Dagster (#19), reporte/model card (#125), evaluación rolling multi-origen (ADR-0033).

## Arquitectura

Nuevo paquete `apps/ml/src/petrocast_ml/evaluation/`, funciones puras sin I/O ni MLflow:

| Módulo | Responsabilidad |
|---|---|
| `metrics.py` | métricas por pozo (MAE/RMSE/MASE/MAPE-no-cero, pooled sobre horizontes) y distribuciones p50/p75/p90 |
| `arps.py` | ajuste de declino por pozo y forecast a los meses de test |
| `gates.py` | `GateThresholds` + evaluación de veredictos |
| `report.py` | `EvaluationReport` (dataclass) → dict serializable / métricas MLflow planas |
| `__init__.py` | `evaluate(model, dataset, production, request, thresholds=None) -> EvaluationReport` |

Flujo en `training/__main__.py` (única orquestación con I/O):

```
build_training_dataset → train() → evaluate()
  → evaluation.json en artifact dir
  → record_training_run(..., evaluation=report)   # si --track
  → print(resumen JSON) → sys.exit(1) si falla gate obligatorio
```

`evaluate()` recomputa `temporal_split(dataset, request)` (determinístico) y recibe la serie
`production` cruda — necesaria para elegibilidad, denominador MASE y fit Arps.

## Semántica (contrato F, ADR-0030)

**Elegibilidad.** Pozo elegible si `production` tiene ≥ 12 meses observados (`oil_prod_m3`
no nulo, ceros cuentan) con `production_month < as_of_date`. No elegibles quedan fuera de
métricas y gates; se reporta el conteo.

**Métricas por pozo** — sobre las filas de test del pozo (single origin, pooled `h = 1…H`),
restringidas al subconjunto evaluable (`naive_forecast_m3` no nulo, invariante del dataset):

- `model_mae`, `model_rmse`, `naive_mae` en m³.
- `MASE = model_mae / d`, con `d` = promedio de `|Y_t − Y_{t−1}|` sobre **meses observados
  sucesivos** del train en orden cronológico (`production_month < as_of_date`; los gaps de
  calendario colapsan — convención congelada por el fixture `expected_naive_backtest.csv`
  de F3-10, columna `naive_insample_mae_m3`). `d = 0` o < 2 observaciones ⇒ MASE
  indefinido: el pozo sale de la distribución MASE y del gate 1; se reporta
  `wells_mase_undefined`.
- `MAPE-no-cero` = promedio de `|Y − ŷ| / Y` sobre filas test con `Y > 0`; sin filas
  positivas ⇒ indefinido para ese pozo.

**Distribuciones.** p50/p75/p90 sobre pozos elegibles con métrica definida: MASE,
`model_mae`, `naive_mae`, MAPE-no-cero del modelo y de Arps.

**Arps (best-effort).** Por pozo elegible, sobre meses de train con `q > 0` (los ceros
shut-in no entran al fit, estándar DCA), con `t` = meses desde el primer mes observado:

- Hiperbólica `q(t) = qi / (1 + b·Di·t)^(1/b)` vía `curve_fit`, bounds `qi > 0`, `Di > 0`,
  `0 ≤ b ≤ 1` (`b → 0` ≈ exponencial), `p0` razonable (qi = máximo reciente, Di = 0.1,
  b = 0.5), `maxfev` acotado.
- Requiere ≥ 6 puntos positivos; falta de puntos o no-convergencia ⇒ `arps_failed` para el
  pozo (nunca excepción hacia afuera).
- Forecast `q(t)` en los meses target del test ⇒ MAPE-no-cero de Arps con las mismas reglas.
- Si los fits exitosos cubren < 50 % de los pozos elegibles ⇒ estado `degraded`: la
  comparación Arps se reporta como `not_evaluated` (fallback del issue).

**Gates.**

| # | Regla | Umbral default | Bloqueante |
|---|---|---|---|
| 1 | mediana de MASE por pozo | `< 1.0` | sí |
| 2 | `Σ\|err_modelo\| ≤ Σ\|err_naive\|` sobre filas test evaluables de pozos elegibles (MAE agregado) | ratio `≤ 1.0` | sí |
| 3 | mediana MAPE-no-cero modelo ≤ mediana Arps + margen | `+2 pp` | no (informativo) |

`GateThresholds(mase_median_max=1.0, naive_mae_ratio_max=1.0, arps_mape_margin_pp=2.0)` —
defaults del ADR-0030, inyectable por constructor (endurecer umbrales no reabre el ADR).

## Reporte y registro

`EvaluationReport`: `as_of_date`, horizontes, thresholds, conteos (pozos en test, elegibles,
excluidos por historia, MASE indefinido, Arps fitted/failed/degraded), distribuciones,
agregados (MAE modelo/naive en m³), lista de gates (`name`, `value`, `threshold`, `passed`,
`blocking`) y `gates_passed` (AND de los bloqueantes).

- **Artifact:** `evaluation.json` junto a `model.txt`/`metadata.json`.
- **MLflow:** métricas planas con prefijo `eval_` (distribuciones, agregados, conteos y
  `eval_gate_*_passed` como 0/1) + tag `gates_passed`. Se extiende
  `record_training_run(..., evaluation: EvaluationReport | None = None)` — mismo run que
  el training.
- **CLI:** el JSON final de stdout suma `evaluation` (resumen) y `gates_passed`; exit 1 si
  `gates_passed` es falso (persistencia y tracking ocurren antes).

## Manejo de errores

- Cero pozos elegibles, o ningún pozo con MASE definido ⇒ `ValueError` (evaluación
  inválida; no hay veredicto silencioso).
- Fallos de Arps: contados por pozo, jamás propagan (gate 3 no bloquea).
- Filas de test sin naive: ya excluidas por el invariante del dataset (F3-13); la
  evaluación reutiliza el mismo filtro.

## Testing

- `unit/test_evaluation_metrics.py`: MASE calculado a mano; pares consecutivos con gaps;
  `d = 0` ⇒ indefinido; MAPE-no-cero excluye ceros; cuantiles.
- `unit/test_arps.py`: recupera parámetros de series sintéticas exponencial e hiperbólica;
  < 6 puntos ⇒ failed; serie sin estructura ⇒ failed sin excepción.
- `unit/test_gates.py`: pasa/falla por cada gate obligatorio; Arps nunca bloquea;
  thresholds custom.
- `unit/test_evaluation.py`: `evaluate()` end-to-end con modelo dummy (Protocol
  `TrainableModel` con `predict` controlado): caso gates-pass, caso gates-fail,
  elegibilidad filtra pozos cortos, reporte JSON-serializable.
- `unit/test_tracking.py`: extensión — métricas `eval_` y tag con el double in-memory.
- `smoke/test_training_smoke.py`: CLI con fixtures ⇒ `evaluation.json` existe; exit code
  refleja el gate (caso éxito y caso falla vía CSVs armados para que gane el naive).

Toolchain: `scipy>=1.13,<2.0` explícito en `pyproject.toml` (hoy transitiva vía
scikit-learn) + override mypy `ignore_missing_imports` para `scipy.*`. `ruff` y `mypy
--strict` como el resto del paquete.
