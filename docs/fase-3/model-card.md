# Model card — `petrocast-production`

Pronóstico mensual de producción de petróleo por pozo (no convencional,
Argentina). Formato adaptado de *Model Cards for Model Reporting*
(Mitchell et al., 2019).

## Detalles del modelo

| Campo | Valor |
| --- | --- |
| Nombre registrado | `petrocast-production` (MLflow Model Registry) |
| Versión champion | **v5** (alias `champion`) |
| Run de tracking | `d219bd649fef4adbaa92b22a4b167d08` (run `2026-02-01-h3`) |
| Corte de entrenamiento | `as_of = 2026-02-01` |
| Algoritmo | LightGBM `LGBMRegressor`, estrategia *direct multi-step* (horizonte como feature) |
| Hiperparámetros | Fijos por contrato (F3-13, sin tuning): `n_estimators=300`, `learning_rate=0.05`, `num_leaves=31`, `min_child_samples=20`, `random_state=42`, `deterministic=true` |
| Commit | `ddbcae8` |
| Resolución programática | `models:/petrocast-production@champion` (ADR-0032) |

Un solo modelo global entrenado sobre todos los pozos, con los estáticos de
`dim_well` como categóricas nativas de LightGBM — eso da una predicción
razonable también para pozos con poca historia (*cold start*).

## Objetivo y uso previsto

- **Objetivo (ADR-0030):** predecir la producción de petróleo (`oil_prod_m3`,
  en m³) de cada pozo para los próximos 1, 2 y 3 meses.
- **Usuarios previstos:** la API de serving de Petrocast (F3-18) y los
  tableros/demos del proyecto.
- **Decisiones que soporta:** priorización operativa y análisis de tendencia
  por pozo/cuenca; siempre con supervisión humana.

**Fuera de alcance:** pronóstico de gas o agua; pozos convencionales (el
dataset ingerido cubre no convencional); horizontes > 3 meses; uso
regulatorio o contable; decisiones automatizadas sin revisión.

## Datos

- **Fuente:** producción de pozos de gas y petróleo no convencional,
  capítulo IV, Secretaría de Energía (datos.gob.ar), más el listado de pozos
  de las empresas operadoras.
- **Ventana ingerida:** 2006-01 → 2026-05; 4.995 pozos; 410.945 filas
  pozo-mes.
- **Granularidad:** pozo-mes, volúmenes en m³.
- **Pipeline:** dlt → bronze → silver → gold (`fact_production`) → feature
  store `features.well_features` (dbt, ADR-0031), todo con tests de calidad
  por capa.

## Features (contrato A, ADR-0031)

Todas calculadas *point-in-time*: solo con meses estrictamente anteriores al
corte `as_of` (test singular anti-leakage en cada materialización).

- **Lags calendario:** producción 1/2/3/6/12 meses atrás.
- **Rolling:** media 3/6/12m y desvío 6/12m sobre meses observados (sin
  imputar faltantes como cero).
- **Tendencia:** pendiente lineal 6/12m (m³/mes).
- **Recencia e intermitencia:** meses desde la última observación, meses en
  cero en la ventana de 12.
- **Historia:** meses con historia, edad del pozo.
- **Estáticas:** cuenca, yacimiento, tipo de recurso (categóricas).

## Métricas y evaluación

Backtest *single-origin* (contrato F): entrenar antes del corte, evaluar los
3 meses siguientes. Detalle completo en el
[reporte de backtesting](backtesting-report.md).

| Gate (ADR-0030) | Umbral | Champion (2026-02-01) | Veredicto |
| --- | ---: | ---: | :---: |
| MASE mediano per-well | < 1,0 | 0,403 | ✅ |
| MAE agregado vs naive | ≤ 1,0 | 0,868 | ✅ |
| MAPE vs Arps (gap, pp) | ≤ +2,0 | −18,1 | ✅ |

En cinco cortes evaluados (2025-09 → 2026-03) el modelo pasó los gates en
cuatro; el corte 2026-03 fue **bloqueado automáticamente** por el gate
agregado (ratio 1,037) — la promoción a champion solo ocurre con gates en
verde.

## Limitaciones y riesgos

- **Leakage.** Riesgo estructural en features temporales. Mitigación: regla
  point-in-time del feature store + test singular que recomputa la tabla
  desde gold y falla ante divergencias (corrió en los 24 cortes usados).
- **Datos faltantes y calidad.** Los datos reales traen huecos de reporte,
  3 filas con producción negativa (detectadas por los tests de silver) y
  ~575 pozos con historia plana (posible relleno administrativo). Los meses
  recientes se rectifican con rezago: el corte 2026-03 falló gates por esa
  inestabilidad.
- **Drift.** La mezcla de pozos cambia (entrada de pozos nuevos en Vaca
  Muerta, cambios de régimen). Mitigación: job de reentrenamiento mensual
  con gates (F3-19) — un candidato que degrada no se promueve; el champion
  anterior sigue sirviendo.
- **Sesgos de cobertura.** El dataset ingerido es 100% no convencional y
  la cuenca Neuquina domina la muestra; el desempeño en otras cuencas o en
  pozos convencionales no está garantizado. Pozos con < 12 meses de
  historia quedan fuera del veredicto de calidad (453 en el corte champion).
- **Cola de error.** El p90 de MASE es 2,27: en ~10% de los pozos el modelo
  es claramente peor que la naive (intermitentes, quiebres de régimen). El
  MAPE explota en pozos de producción cercana a cero.

## Champion y trazabilidad

- El alias `champion` del registry apunta siempre a la última versión que
  pasó los gates; la promoción es atómica y reversible (F3-16).
- Resolución en runtime: `models:/petrocast-production@champion`.
- Cada versión registrada lleva tags de contrato C (`as_of_date`,
  `features_version`, `git_commit`, `gates_passed`) y su run de tracking
  con parámetros, métricas `eval_*` y artefactos (modelo + `evaluation.json`).
- Champion actual: **v5** ← run `d219bd649fef4adbaa92b22a4b167d08`
  (`as_of=2026-02-01`, `git_commit=ddbcae8`, `gates_passed=true`).
