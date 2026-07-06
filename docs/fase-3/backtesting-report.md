# Reporte de backtesting — modelo de pronóstico de producción

- **Modelo evaluado:** `petrocast-production` v5 (champion) — baseline LightGBM
  de F3-13.
- **Corte de evaluación (champion):** `as_of = 2026-02-01`, horizontes 1–3
  meses.
- **Datos:** producción no convencional por pozo, capítulo IV
  (datos.gob.ar), ventana 2006-01 → 2026-05, 4.995 pozos, 410.945 filas
  pozo-mes.
- **Run de tracking:** MLflow run `d219bd649fef4adbaa92b22a4b167d08`
  (experimento `petrocast-production-forecast`, run `2026-02-01-h3`).
- **Anexo auditable:** [`assets/evaluation-2026-02-01.json`](assets/evaluation-2026-02-01.json).

## Resumen ejecutivo

El modelo **pasa los tres gates de calidad del ADR-0030** en el corte champion
(2026-02-01):

- Para el **pozo típico** (mediana), el error del modelo es **40% del error
  de la naive de persistencia** (MASE mediano 0,40 — cuanto menor que 1,
  mejor que repetir el último mes observado).
- En **volumen agregado**, el MAE del modelo es **13% menor** que el de la
  naive (98,5 vs 113,5 m³ por pozo-mes).
- Contra el ajuste físico de declinación (**Arps**), el modelo tiene una
  mediana de MAPE **18 puntos porcentuales mejor**.

La evaluación es honesta por diseño: el mismo pipeline, corrido con corte
2026-03-01 (el mes más reciente evaluable), **falla el gate agregado**
(ratio 1,037 > 1,0) y el sistema **bloquea la promoción** automáticamente.
Ver [Robustez temporal](#robustez-temporal-gates-en-cinco-cortes).

## Metodología

- **Contrato F (ADR-0030):** split *single-origin*. Se entrena con todo lo
  observable antes del corte `as_of` y se evalúa sobre los meses target
  `as_of + (h − 1)` para `h ∈ {1, 2, 3}` (para 2026-02-01: feb, mar y abr
  2026). Sin ventanas deslizantes: un origen, tres horizontes.
- **Elegibilidad:** solo pozos con **≥ 12 meses observados** antes del corte
  entran al veredicto (contrato de cobertura; el resto se reporta como
  excluido).
- **MASE:** denominador = MAE de la naive un-paso sobre la historia
  pre-corte del pozo, con diffs entre **filas observadas sucesivas**
  (convención congelada por el fixture de F3-10; los meses faltantes no se
  imputan). Pozos con historia plana (denominador 0) quedan con MASE
  indefinido y se reportan aparte.
- **Baselines:**
  - *Naive de persistencia:* repetir el último valor observado antes del
    corte.
  - *Arps:* ajuste de declinación hiperbólica por pozo (implementación
    propia con `scipy.optimize`, F3-15) sobre la historia pre-corte;
    comparación por MAPE sobre targets positivos.
- **Unidades:** todo en **m³** de petróleo por pozo-mes.
- La materialización del feature store es *point-in-time* (contrato A,
  ADR-0031): cada corte usa exclusivamente meses anteriores a `as_of`; el
  test singular anti-leakage corrió y pasó en los 24 cortes materializados.

## Cobertura (corte 2026-02-01)

| Métrica | Valor |
| --- | ---: |
| Pozos en el split de test | 4.773 |
| Pozos elegibles (≥ 12 meses de historia) | 4.320 |
| Pozos excluidos por historia corta | 453 |
| Pozos elegibles con MASE indefinido (historia plana) | 575 |
| Pozos con ajuste Arps exitoso | 3.622 |
| Pozos con ajuste Arps fallido | 698 |
| Comparación Arps degradada | No |
| Filas de entrenamiento | 284.923 |
| Filas de test | 14.314 |

## Gates de calidad (ADR-0030)

| Gate | Umbral | Valor | Veredicto | ¿Bloqueante? |
| --- | ---: | ---: | :---: | :---: |
| MASE mediano per-well | < 1,0 | 0,403 | ✅ pasa | Sí |
| MAE agregado vs naive (ratio) | ≤ 1,0 | 0,868 | ✅ pasa | Sí |
| MAPE mediano vs Arps (gap, pp) | ≤ +2,0 | −18,1 | ✅ pasa | No (informativo) |

Un gate bloqueante fallido registra la corrida igual (métricas `eval_*` y tag
`gates_passed=false` en MLflow) pero **impide la promoción a champion** —
comportamiento verificado en la corrida 2026-03-01.

## Modelo vs naive (m³)

| Métrica agregada | Modelo | Naive | Ratio |
| --- | ---: | ---: | ---: |
| MAE (m³/pozo-mes) | 98,52 | 113,52 | 0,868 |

Lectura: el grueso de la mejora del modelo está en el pozo típico (ver
distribuciones); en volumen agregado —dominado por los pozos de mayor
producción— la ventaja es del 13%.

## Modelo vs Arps

- Ajuste hiperbólico exitoso en 3.622 de 4.320 pozos elegibles (84%); 698
  pozos sin convergencia (historia corta, intermitente o no declinante).
- MAPE mediano (targets positivos): **modelo 29,9%** vs **Arps 48,0%** —
  gap de −18,1 pp a favor del modelo.

## Distribuciones per-well

Distribución sobre pozos elegibles (percentiles 50/75/90). La cola alta
(p90) muestra dónde el modelo todavía falla: pozos intermitentes o con
quiebres de régimen.

| Métrica per-well | p50 | p75 | p90 |
| --- | ---: | ---: | ---: |
| MASE | 0,403 | 0,946 | 2,272 |
| MAE modelo (m³) | 6,46 | 92,99 | 303,22 |
| MAE naive (m³) | 2,36 | 93,88 | 331,90 |
| MAPE modelo (%, targets > 0) | 29,9 | 86,4 | 414,4 |
| MAPE Arps (%, targets > 0) | 48,0 | 98,2 | 343,4 |

Notas de lectura:

- El MASE < 1 en más de la mitad de los pozos y ~0,95 en p75: el modelo es
  mejor o igual que la naive para ~3 de cada 4 pozos elegibles.
- En p50 de MAE absoluto la naive luce menor (2,4 vs 6,5 m³): la mediana de
  MAE cae en pozos chicos casi constantes, donde repetir el último mes es
  casi perfecto. El MASE (que normaliza por pozo) y el agregado capturan
  mejor la ganancia real.
- El p90 de MAPE del modelo (414%) viene de pozos con producción cercana a
  cero donde el error relativo explota; en MAE esos mismos pozos pesan poco.

## Robustez temporal: gates en cinco cortes

El mismo pipeline (datos → features PIT → entrenamiento → evaluación →
promoción) corrió para cinco cortes. Champion = último candidato que pasó
los gates (2026-02-01).

| Corte | MASE mediano | Ratio MAE vs naive | Gap Arps (pp) | Gates |
| --- | ---: | ---: | ---: | :---: |
| 2025-09-01 | 0,431 | 0,876 | −20,9 | ✅ |
| 2025-12-01 | 0,397 | 0,905 | −18,0 | ✅ |
| 2026-01-01 | 0,394 | 0,885 | −19,0 | ✅ |
| 2026-02-01 | 0,403 | 0,868 | −18,1 | ✅ (champion) |
| 2026-03-01 | 0,463 | 1,037 | −17,7 | ❌ bloqueado |

El corte 2026-03-01 falla el gate agregado: sus targets (mar–may 2026) son
los meses más recientes del dataset, donde las declaraciones juradas todavía
se rectifican y la cola de pozos grandes es más ruidosa. El sistema hizo lo
correcto: registró la corrida y bloqueó la promoción.

## Calidad de datos observada

Sobre los datos reales ingeridos (no sobre fixtures):

- **3 filas con producción negativa** en 410.945 (2 de gas en 2020-05, 1 de
  petróleo con −0,001 m³ en 2008-12). Los tests `accepted_range` de la capa
  silver las detectan; hoy pasan a gold sin filtrar (impacto despreciable en
  esta evaluación, pero es un caso a resolver en la capa de datos).
- **575 pozos elegibles con historia plana** (MASE indefinido): pozos que
  reportan valores idénticos mes a mes — probable relleno administrativo.
- El test de *recency* de silver avisa (WARN) que el último mes disponible
  (2026-05) está a ~2 meses del presente: rezago normal de publicación de
  capítulo IV.

## Cómo reproducir

Infraestructura local efímera (nada de esto persiste en el repo):

```bash
# 1. Warehouse efímero + MLflow local (backend sqlite)
docker run -d --name f3-22-pg \
  -e POSTGRES_USER=petrocast -e POSTGRES_PASSWORD=petrocast -e POSTGRES_DB=petrocast \
  -p 5432:5432 -v $REPO/infra/data/postgres/init:/docker-entrypoint-initdb.d:ro postgres:16
uv run --project apps/ml mlflow server \
  --backend-store-uri sqlite:////tmp/mlflow/mlflow.db \
  --default-artifact-root /tmp/mlflow/artifacts --host 127.0.0.1 --port 5000

# 2. Descargar los CSV de capítulo IV (el server corta conexiones largas:
#    usar --compressed) y apuntar las fuentes a los archivos locales
export PETROCAST_SOURCE_PRODUCTION_URL=/ruta/production-noconv.csv
export PETROCAST_SOURCE_WELLS_URL=/ruta/wells-registry.csv
export PETROCAST_DW_HOST=localhost PETROCAST_DW_USER=petrocast \
  PETROCAST_DW_PASSWORD=petrocast PETROCAST_DW_DATABASE=petrocast \
  PETROCAST_MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  PETROCAST_ML_ARTIFACT_DIR=/tmp/ml-artifacts DBT_PROFILES_DIR=$PWD/dbt

# 3. Pipeline de datos (desde apps/data)
uv run dagster asset materialize -m petrocast_data.definitions --select warehouse_schemas_ready
uv run dagster asset materialize -m petrocast_data.definitions \
  --select "bronze/production_by_well,bronze/wells_registry" --partition 2026-05-01
uv run dbt build --project-dir dbt --select tag:silver
uv run dbt build --project-dir dbt --select tag:gold --indirect-selection cautious
for m in 2024-04-01 ... 2026-03-01; do   # 24 cortes mensuales
  uv run dbt build --project-dir dbt --select tag:features \
    --vars "{\"as_of_date\": \"$m\"}" --indirect-selection cautious
done

# 4. Cadena ML por corte (entrena, evalúa gates, promueve si pasan)
uv run dagster asset materialize -m petrocast_data.definitions \
  --select "ml/training_candidate,ml/model_evaluation,ml/champion_promotion" \
  --partition 2026-02-01
```

El `evaluation.json` queda junto al artefacto del modelo y espejado como
métricas `eval_*` en el run MLflow.

## Anexo

- [`assets/evaluation-2026-02-01.json`](assets/evaluation-2026-02-01.json):
  salida íntegra de `evaluate()` para el corte champion.
- Run MLflow del champion: `d219bd649fef4adbaa92b22a4b167d08`
  (`petrocast-production` v5, alias `champion`, git `ddbcae8`).
- Ver también la [model card](model-card.md).
