# Guía maestra del video de Fase 3 — punta a punta

Guía completa para grabar el video de entrega de Fase 3: setup del entorno,
coreografía de la demo, guiones palabra por palabra (español rioplatense),
reparto equitativo entre los 3 integrantes, y publicación final.

## Ficha del video

| Ítem               | Valor                                                                 |
| ------------------ | --------------------------------------------------------------------- |
| Duración           | **5 a 10 minutos** (objetivo: ~9:30)                                  |
| Requisito (adenda) | Explicar arquitectura, herramientas, rationale y valor agregado       |
| Requisito (adenda) | Demostrar métricas de training en distintos runs                      |
| Requisito (adenda) | Demostrar llamadas a la API con predicciones en distintas condiciones |
| Requisito (adenda) | Demostrar el trigger de un retrain                                    |
| Reparto            | Joaquin ~3:30 · Ignacio ~3:00 · Santino ~3:00                         |
| Entrega            | 2026-07-11 — subir a YouTube y pegar el link en los 2 `TBD`           |

### Reparto por bloque

| Bloque | Minutos   | Habla       | Tema                                                            |
| ------ | --------- | ----------- | --------------------------------------------------------------- |
| 1      | 0:00–0:50 | **Joaquin** | Apertura + arquitectura end-to-end                              |
| 2      | 0:50–3:50 | **Ignacio** | Datos, features point-in-time, modelo, evaluación y gates       |
| 3      | 3:50–6:50 | **Santino** | Orquestación Dagster, retrain en vivo (gates bloquean), CI/CD   |
| 4      | 6:50–9:30 | **Joaquin** | Tracking MLflow, registry, API en vivo, valor agregado y cierre |

### Qué corre dónde (mapa de servicios y bases)

Todo es **local**, sin AWS ni Supabase (fallback local del compose):

| Servicio                                             | Dónde corre                                 | URL / conexión                                     |
| ---------------------------------------------------- | ------------------------------------------- | -------------------------------------------------- |
| PostgreSQL warehouse (`bronze/silver/gold/features`) | Docker (`data-postgres`)                    | `localhost:5432`, user `petrocast`, db `petrocast` |
| Backend de MLflow                                    | Base `mlflow` del mismo Postgres            | (interno)                                          |
| Artefactos de MLflow                                 | Volumen Docker `mlflow_artifacts`           | vía `--serve-artifacts` (HTTP)                     |
| MLflow UI + registry                                 | Docker (`mlflow`)                           | `http://localhost:5000`                            |
| Dagster UI                                           | Docker (`dagster`)                          | `http://localhost:3000`                            |
| API FastAPI                                          | **Host** (terminal propia, `uv`)            | `http://localhost:8000`                            |
| Datos fuente                                         | datos.gob.ar (producción por pozo, cap. IV) | descarga vía asset bronze                          |

---

## Parte 1 — Preparación del entorno (hacer el día ANTES de grabar)

> Tiempo estimado: 1 a 2 horas (la ingesta y las corridas de retraining tardan).
> Responsable sugerido: Joaquin (host de la demo), con Santino de apoyo.

### 1.1 Requisitos previos

- Docker + Docker Compose funcionando (`docker ps` no da error).
- `uv` instalado (`uv --version`).
- Repo clonado y actualizado: `git checkout main && git pull`.
- Conexión a internet (la ingesta descarga ~410.000 filas de datos.gob.ar).

Todos los comandos se corren **desde la raíz del repo** salvo que se indique lo
contrario.

### 1.2 Configurar variables de entorno

```bash
cp apps/data/.env.example apps/data/.env
```

Editar `apps/data/.env` y cambiar **una sola línea** (para que coincida con la
config por defecto de la API):

```bash
PETROCAST_DW_PASSWORD=petrocast
```

El resto queda como está. En particular `PETROCAST_MLFLOW_TRACKING_URI=http://mlflow:5000`
es correcto: es la URL **dentro** de la red de Docker (la usa Dagster).

Después, la config de la API:

```bash
cp apps/api/.env.example apps/api/.env
```

No hace falta tocar nada: ya trae `API_KEY=abcdef12345`, warehouse en
`localhost:5432` con password `petrocast`, y `MLFLOW_TRACKING_URI=http://localhost:5000`.

> Si el stack ya se levantó antes con otra password, resetear todo con
> `docker compose --env-file apps/data/.env -f infra/compose.data.yml -f infra/compose.mlflow.yml down -v`
> (el `-v` borra los volúmenes) y empezar de cero.

### 1.3 Levantar el stack (terminal 1 — dejarla abierta)

```bash
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml \
  -f infra/compose.mlflow.yml \
  up --build data-postgres mlflow dagster
```

Esperar a que los logs se calmen y verificar:

- Dagster UI: <http://localhost:3000> carga.
- MLflow UI: <http://localhost:5000> carga (experimentos vacíos, está bien).

#### 1.3.1 Si el stack corre en otra máquina (Tailscale) — opcional

Solo aplica si el stack no corre en la misma máquina desde la que grabás (caso
de Joaquin: server Linux por SSH, grabación desde la Mac, misma tailnet). Dos
escollos, ambos ya contemplados en el compose:

- **MLflow responde `400 Invalid Host header`.** MLflow valida el header `Host`
  contra DNS rebinding, y por `tailscale serve` llega el DNS de la tailnet, no
  `localhost`. Agregar el host propio en `apps/data/.env`:

  ```bash
  PETROCAST_MLFLOW_ALLOWED_HOSTS=localhost,127.0.0.1,mlflow,<host>.ts.net,<host>.ts.net:*
  ```

- **La UI de MLflow carga pero no muestra runs ni modelos**, y en los logs del
  compose aparece `Blocked cross-origin request from https://<host>.ts.net:5000`.
  Es la protección CORS del server (default: solo orígenes `localhost`), aparte
  de la validación de Host. Permitir el origen de la tailnet:

  ```bash
  PETROCAST_MLFLOW_ALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000,https://<host>.ts.net:5000
  ```

- **Dagster o MLflow no levantan: `bind 0.0.0.0:3000/5000: address already in
  use`.** `tailscale serve` ya escucha esos puertos en la IP de la tailnet, y
  `0.0.0.0` la incluye. Publicar ambos solo en loopback y dejar que Tailscale
  proxee:

  ```bash
  PETROCAST_DAGSTER_BIND=127.0.0.1
  PETROCAST_MLFLOW_BIND=127.0.0.1
  ```

Dagster no valida el `Host`, así que no necesita nada más. La API del bloque 4
corre en el host del stack: los `curl` con `localhost:8000` funcionan por SSH.
Si querés mostrarlos desde una terminal de la Mac, hay que servir también el
8000 por Tailscale.

### 1.4 Cargar el warehouse con datos reales (una sola vez)

> ⚠️ **Bronze, silver y gold están los tres particionados por mes**, y la
> partición significa cosas distintas en cada capa. Leer §1.4.1 antes de
> materializar: elegir mal la partición deja el warehouse **vacío** con todos
> los assets en verde.

En la **UI de Dagster** (<http://localhost:3000>):

1. Ir a **Assets** (menú lateral) → vista de grafo (**Global asset lineage**).
2. Materializar `warehouse_schemas_ready` (grupo `warehouse`, sin particiones).
   Esperar el verde.
3. Seleccionar **los 10 assets particionados** de bronze + silver + gold:

   ```text
   bronze/production_by_well          gold/dim_company
   bronze/wells_registry              gold/dim_date
   silver/silver_production           gold/dim_well
   silver/silver_wells                gold/fact_production
                                      gold/v_monthly_production_by_well
                                      gold/v_top_wells_by_volume
   ```

4. **Materialize** → elegir el **rango completo de particiones**
   (`2006-01-01` … la última) → Launch.

Los tres assets comparten `BackfillPolicy.single_run()`, así que el rango
entero se resuelve en **un único run**: bronze descarga el CSV una sola vez y
dbt corre una sola vez. ⏱️ Tarda ~**4 a 5 minutos** (casi todo es la descarga
de datos.gob.ar; dbt son segundos).

Equivalente por CLI, si preferís no pelearte con el selector en vivo:

```bash
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml -f infra/compose.mlflow.yml \
  exec dagster dagster asset materialize \
  --select "bronze/production_by_well,bronze/wells_registry,silver/silver_production,silver/silver_wells,gold/dim_company,gold/dim_date,gold/dim_well,gold/fact_production,gold/v_monthly_production_by_well,gold/v_top_wells_by_volume" \
  --partition-range 2006-01-01...2026-06-01 \
  -m petrocast_data.definitions
```

Verificación (terminal 2) — **este paso no es opcional**:

```bash
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml -f infra/compose.mlflow.yml \
  exec data-postgres psql -U petrocast -d petrocast \
  -c "SELECT count(*), min(production_month), max(production_month) FROM gold.fact_production;"
```

Debe dar ~**410.000 filas**, de `2006-01-01` a `2026-05-01`. Si da **0**, no
falló nada: materializaste una partición sin datos (ver §1.4.1).

Silver termina con **1 warning** (`PASS=15 WARN=1 ERROR=0`) y eso está bien: el
único check no bloqueante es el de _recency_ (frescura), por contrato F2-18. Un
warning de dbt **no** deja el asset en rojo.

#### 1.4.1 Qué significa la partición en cada capa (leer antes de materializar)

La misma palabra quiere decir dos cosas distintas en capas contiguas:

| Capa              | Qué significa la partición           | Efecto real en los datos                                                      |
| ----------------- | ------------------------------------ | ----------------------------------------------------------------------------- |
| **bronze**        | Sello operacional: cuándo se ingirió | **Ninguno.** Siempre baja el dataset completo y **reemplaza** la tabla entera |
| **silver / gold** | Ventana temporal: `min`/`max_month`  | **Filtra de verdad.** Construye solo los meses del rango (delete+insert)      |

Dos consecuencias prácticas:

- En **bronze** da igual qué partición elijas: `read_csv_rows` no filtra (solo
  estampa `_petrocast_partition_key` en cada fila) y el resource usa
  `write_disposition="replace"`. Una sola partición ya te trae los 20 años.
  Por eso **no** conviene materializar bronze en un rango de a una partición
  por vez: cada una re-descargaría todo. Con `single_run()` el rango es un solo
  run, así que es seguro.
- En **silver/gold** la partición **es** el filtro. La última partición
  disponible es `2026-06`, pero **los datos llegan hasta `2026-05`**: si
  materializás solo esa última, la ventana no tiene datos, silver construye
  **cero filas**, gold hereda el vacío... y todo queda **verde**, porque los
  tests pasan trivialmente sobre tablas vacías. Es la trampa más fácil de
  pisar en todo el setup. Siempre **rango completo**.

### 1.5 Poblar MLflow y dejar el champion listo (corridas históricas)

Esto genera los "distintos runs con métricas distintas" que pide la adenda y
deja un champion promovido para que la API funcione.

#### 1.5.0 Backfill del histórico de features (primero, una sola vez)

El training carga **todos** los cortes persistidos anteriores al de la
partición para armar train/validation; el `retraining_job` solo materializa
el corte propio. En un warehouse recién cargado no hay histórico y el training
falla con `ValueError: no training cutoffs older than <partición>
(validation_cutoffs=0)`. Hay que backfillear los mismos cortes que usó el
[reporte de backtesting](backtesting-report.md): `2024-04-01 … 2025-11-01`
(los 4 restantes hasta `2026-03-01` los agregan los propios retraining runs).

En la UI de Dagster: asset `features/well_features` → **Materialize** → rango
`2024-04-01 … 2025-11-01` → Launch backfill. La política de backfill de
features es `multi_run(max 1)`, así que son **20 runs** de ~15-30 s cada uno
(⏱️ ~5-10 min en total). Equivalente por CLI:

```bash
for m in 2024-{04..12}-01 2025-{01..11}-01; do
  docker compose --env-file apps/data/.env \
    -f infra/compose.data.yml -f infra/compose.mlflow.yml \
    exec dagster dagster asset materialize \
    --select "features/well_features" --partition "$m" \
    -m petrocast_data.definitions
done
```

Verificar (debe dar 20 cortes, `2024-04-01` a `2025-11-01`):

```bash
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml -f infra/compose.mlflow.yml \
  exec data-postgres psql -U petrocast -d petrocast \
  -c "SELECT count(DISTINCT as_of_date), min(as_of_date), max(as_of_date) FROM features.well_features;"
```

#### 1.5.1 Corridas históricas del retraining

Se hace **desde la UI de Dagster** (así el video en vivo repite exactamente el
mismo flujo):

1. Ir a **Jobs** → **`retraining_job`**.
2. Click en **Materialize all** → elegir la partición **`2025-12-01`** → Launch.
3. Esperar a que termine en verde (features → training → evaluación →
   promoción). ⏱️ Cronometrar cuánto tarda: ese dato define la coreografía del
   bloque 3 (ver §3).
4. Repetir con la partición **`2026-01-01`**.
5. Repetir con la partición **`2026-02-01`**.

Según el [reporte de backtesting](backtesting-report.md), esos tres cortes
**pasan los gates** (MASE mediano ≈ 0,40, ratio < 1). El champion queda
apuntando al candidato de `2026-02-01`.

> ⚠️ **NO correr la partición `2026-03-01` todavía.** Esa es la que **falla los
> gates** (ratio 1,037 > 1,0) y es la estrella del bloque 3: se dispara EN VIVO
> durante la grabación para mostrar el bloqueo automático de la promoción.
>
> 🔎 **Confirmar que `2026-03-01` sigue fallando los gates.** El
> [reporte de backtesting](backtesting-report.md) se armó con un snapshot más
> viejo del dataset; hoy la serie llega hasta `2026-05`, así que el corte de
> marzo ya tiene meses objetivo con datos consolidados y **puede pasar los
> gates**. En el ensayo general, correr `2026-03-01` una vez y mirar el
> veredicto: si **falla**, borrar ese run de MLflow y dejarla para el vivo. Si
> **pasa**, elegir para el bloque 3 el corte más reciente que sí falle
> (probar `2026-04-01` / `2026-05-01`) y actualizar el guion de Santino con esa
> fecha. Sin un corte que falle, el bloque 3 se queda sin su punto central.

Verificar en MLflow (<http://localhost:5000>):

- Experimento `petrocast-production-forecast` con **3 runs** de métricas
  distintas (`2025-12-01-h3`, `2026-01-01-h3`, `2026-02-01-h3`).
- En **Models** → `petrocast-production`: el alias **`@champion`** apunta a la
  versión del run de `2026-02-01`. **Anotar ese número de versión** (aparece
  en el video como `model_version`).

Alternativa por CLI (mismo efecto; ojo con el override de la URI porque desde
el host MLflow es `localhost`, no `mlflow`):

```bash
PETROCAST_MLFLOW_TRACKING_URI=http://localhost:5000 \
PARTITION=2025-12-01 \
  infra/scripts/demo/f3-21-demo-evidence.sh retrain-cli
```

### 1.6 Levantar la API (terminal 3 — dejarla abierta)

```bash
cd apps/api
uv sync --frozen
uv run fastapi dev src/main.py
```

La API queda en `http://localhost:8000`. Se corre en el **host** (no Docker)
para que resuelva Postgres y MLflow por `localhost` sin problemas de red.

### 1.7 Elegir el pozo de la demo

Buscar pozos con features materializadas en el corte del champion y
**producción alta**: para pozos marginales o planos el modelo predice el mismo
valor en los 3 meses (los árboles no splitean por `horizon` en esos caminos) y
el forecast queda plano en cámara. Con un pozo grande se ve la curva de
declinación:

```bash
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml -f infra/compose.mlflow.yml \
  exec data-postgres psql -U petrocast -d petrocast \
  -c "SELECT well_id, oil_prod_m3_lag_1m FROM features.well_features WHERE as_of_date = '2026-02-01' ORDER BY oil_prod_m3_lag_1m DESC NULLS LAST LIMIT 5;"
```

Elegir uno (son ids numéricos tipo `135204`) y **anotarlo**: es `<POZO_DEMO>`
en todos los curls de abajo. Probar el happy path ya mismo:

```bash
curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=<POZO_DEMO>&as_of_date=2026-01-15&horizon=3"
```

> **Por qué `as_of_date=2026-01-15`:** el contrato dice "as_of = último mes
> observado"; el service lee el vector de features del mes siguiente
> (`2026-02-01`), que es justo el corte materializado. Los tres meses predichos
> salen como `2026-02-01`, `2026-03-01` y `2026-04-01`.

Respuesta esperada (valores ilustrativos):

```json
{
  "id_well": "<POZO_DEMO>",
  "as_of_date": "2026-01-15",
  "horizon": 3,
  "model_version": "5",
  "predictions": [
    { "month": "2026-02-01", "oil_prod_m3": 1234.5 },
    { "month": "2026-03-01", "oil_prod_m3": 1180.2 },
    { "month": "2026-04-01", "oil_prod_m3": 1125.9 }
  ]
}
```

### 1.8 Checklist de verificación pre-grabación

Correr TODO esto la noche anterior. Si algo falla, no grabar hasta arreglarlo.

- [ ] `http://localhost:3000` (Dagster) y `http://localhost:5000` (MLflow) cargan.
- [ ] **`gold.fact_production` tiene ~410.000 filas, de `2006-01-01` a `2026-05-01`** (§1.4). Verde en Dagster **no** alcanza: si quedó en 0, el resto del setup miente.
- [ ] `features.well_features` tiene el histórico backfilleado: ≥ 20 cortes desde `2024-04-01` (§1.5.0). Sin esto, el primer retraining falla con `no training cutoffs older than ...`.
- [ ] La partición `2026-03-01` de `retraining_job` **falla** los gates en el ensayo (§1.5). Si pasa, cambiar el corte del bloque 3.
- [ ] MLflow: experimento `petrocast-production-forecast` con ≥ 3 runs de métricas distintas.
- [ ] MLflow → Models → `petrocast-production`: alias `@champion` en la versión de `2026-02-01`.
- [ ] La partición `2026-03-01` de `retraining_job` **NO** se corrió (queda para el vivo).
- [ ] Curl happy path (§1.7) devuelve `200` con `model_version`.
- [ ] Curl con `as_of_date=2024-03-15` devuelve `404` (`no persisted features` — corte sin materializar).
- [ ] Curl con `horizon=13` devuelve `422`.
- [ ] `curl -H "X-API-Key: abcdef12345" http://localhost:8000/health/deep` muestra `model_serving` con `status: loaded` y el `model_version` del champion (si dice `not_loaded`, pegarle primero al happy path: la carga es lazy).
- [ ] Cronometrado cuánto tarda una corrida de `retraining_job` (§1.5 paso 3).
- [ ] Ensayo general completo del guion, cronometrado ≤ 9:45.

---

## Parte 2 — Estructura del video (mapa de pantallas)

| Min  | Pantalla                                                                              | Quién   |
| ---- | ------------------------------------------------------------------------------------- | ------- |
| 0:00 | Título / cara + `docs/fase-3/README.md` con el diagrama de flujo                      | Joaquin |
| 0:50 | `docs/fase-3/backtesting-report.md` (datos) + código/schema de `well_features`        | Ignacio |
| 1:50 | [`model-card.md`](model-card.md) + tabla de gates del backtesting report              | Ignacio |
| 2:50 | MLflow UI: comparación de 2 runs (métricas distintas)                                 | Ignacio |
| 3:50 | Dagster UI: asset graph + `retraining_job`                                            | Santino |
| 4:30 | **EN VIVO**: launch de la partición `2026-03-01` → falla gates → champion intacto     | Santino |
| 5:50 | GitHub Actions: CI verde (`ml checks`, `data pipeline checks`) + schedule mensual     | Santino |
| 6:50 | MLflow: detalle de un run (params, métricas, tags, artefactos) + registry `@champion` | Joaquin |
| 7:40 | Terminal: curls en vivo (`200`, `404`, `422`) + `/health/deep`                        | Joaquin |
| 8:50 | Diagrama de flujo de nuevo + cierre                                                   | Joaquin |

Cobertura del checklist oficial ([`README.md` de Fase 3](README.md#guion--checklist-de-video)):
runs distintos ✅ (2:50) · detalle de run ✅ (6:50) · predicción con `model_version` ✅ (7:40) ·
error controlado ✅ (7:40) · trigger manual ✅ (4:30) · retrain fallido no pisa champion ✅ (4:30–5:50).

---

## Parte 3 — Guiones al pie de la letra

Convenciones: **[PANTALLA]** = qué se ve; **[ACCIÓN]** = qué hace el que graba;
el texto plano es lo que se dice, palabra por palabra. Hablar a ritmo normal
(~140 palabras/minuto). Si un bloque queda largo, cortar en edición, no apurar
la voz.

### Bloque 1 — Joaquin: apertura y arquitectura (0:00–0:50)

**[PANTALLA]** Slide o pantalla con el nombre del proyecto; a los 15 segundos,
`docs/fase-3/README.md` en GitHub, con el diagrama de flujo Mermaid visible.

> Hola, somos el equipo de Petrocast: Santino, Ignacio y Joaquin. En las fases
> anteriores construimos la API y la plataforma de datos; en esta Fase 3 le
> agregamos la vertical de machine learning: un modelo que pronostica la
> producción mensual de petróleo por pozo, y que se sirve por la misma API REST.
>
> El flujo completo es este que ven acá: un feature store point-in-time armado
> con dbt sobre Postgres; un modelo LightGBM global; tracking de experimentos y
> registry de modelos con MLflow; evaluación con gates de calidad automáticos;
> y Dagster orquestando el reentrenamiento mensual. La regla de oro del diseño
> es esta: si un reentrenamiento no pasa los gates de calidad, el modelo
> productivo —el champion— no se toca. Ignacio arranca por los datos y el
> modelo.

### Bloque 2 — Ignacio: datos, features, modelo y gates (0:50–3:50)

**[PANTALLA]** `docs/fase-3/backtesting-report.md`, sección de datos.

> Gracias, Joaquin. Los datos son públicos: producción de petróleo y gas por
> pozo del capítulo cuatro de datos punto gob punto ar. Son unas cuatrocientas
> diez mil filas pozo-mes, casi cinco mil pozos, desde dos mil seis hasta hoy.
> Pasan por una arquitectura medallion —bronze, silver, gold— que ya teníamos
> de la Fase 2, y de gold sale el feature store.

**[PANTALLA]** `apps/data/dbt/models/features/well_features.sql` en el editor,
o el `schema.yml` del mismo directorio.

> El feature store es una tabla dbt en el schema features, con clave pozo y
> fecha de corte. Para cada corte calculamos lags de producción de uno a doce
> meses, medias y desvíos móviles, tendencia e intermitencia. Y acá está el
> punto conceptual más importante: las features son point-in-time. Para el
> corte de febrero solo se usan datos estrictamente anteriores a febrero. Eso
> evita el leakage temporal, que es la forma más fácil de mentirse con un
> modelo de series de tiempo: evaluarlo con información del futuro. No lo
> dejamos librado a la disciplina: hay un test automático anti-leakage que
> corre en el CI contra un Postgres real en cada pull request.

**[PANTALLA]** `docs/fase-3/model-card.md`.

> El modelo es un LightGBM global: uno solo para todos los pozos, no uno por
> pozo. ¿Por qué? Porque la mayoría de los pozos tiene poca historia, y un
> modelo global aprende patrones de declinación compartidos entre pozos. Los
> hiperparámetros están congelados y el entrenamiento es determinístico, así
> cualquier corrida es reproducible.

**[PANTALLA]** `docs/fase-3/backtesting-report.md`, tabla "Gates de calidad".

> Para evaluarlo no nos alcanza con el error absoluto: lo comparamos contra
> dos baselines. La naive de persistencia —repetir el último mes— y la curva
> de declinación de Arps, que es el baseline clásico de la ingeniería en
> petróleo. La métrica estrella es el MASE: cuánto error tiene el modelo
> relativo a la naive. Y sobre eso definimos tres gates de calidad en el
> ADR treinta: MASE mediano menor a uno, error agregado menor o igual al de
> la naive, y la comparación contra Arps como control informativo. En el
> corte champion el MASE mediano dio cero coma cuarenta: para el pozo típico,
> el modelo tiene el cuarenta por ciento del error de la naive.

**[PANTALLA]** MLflow UI (`http://localhost:5000`), experimento
`petrocast-production-forecast`: tildar dos runs (`2026-01-01-h3` y
`2026-02-01-h3`) → **Compare**.

> Todo esto queda trazado en MLflow. Acá tienen dos corridas con cortes
> distintos y métricas distintas: se ve el error del modelo y el de la naive
> lado a lado, para cada corte. El backtesting completo corrió sobre cinco
> cortes: cuatro pasaron los gates... y uno no. Qué pasa cuando no pasa, lo
> muestra Santino en vivo.

### Bloque 3 — Santino: orquestación, retrain en vivo y CI/CD (3:50–6:50)

**[PANTALLA]** Dagster UI (`http://localhost:3000`) → **Jobs** →
`retraining_job` → grafo de assets.

> Gracias, Ignacio. Acá estamos en Dagster, nuestro orquestador. Este es el
> retraining job: una cadena de cuatro assets. Materializa las features del
> corte, entrena el candidato, lo evalúa con backtesting y gates, y recién si
> los gates pasan, lo registra y lo promueve a champion. El job está
> particionado por fecha de corte, una partición por mes, y tiene un schedule
> mensual: el día cinco de cada mes se reentrena solo, con la partición del
> mes. Con eso el entrenamiento y el despliegue del modelo son recurrentes y
> automáticos, como pide la consigna, pero con un guardrail de calidad en el
> medio.

**[ACCIÓN]** Click en **Materialize all** → elegir partición **`2026-03-01`**
→ **Launch run**. Mientras corre, seguir hablando. Si en el ensayo la corrida
tardó más de ~2 minutos, cortar la espera en edición y retomar cuando el step
de evaluación está por terminar.

> Lo lanzo a mano para que lo vean: partición dos mil veintiséis, marzo. Este
> corte lo elegimos a propósito: sabemos por el backtesting que falla el gate
> agregado, porque sus meses objetivo son los más recientes del dataset, donde
> las declaraciones juradas todavía se rectifican. Miren lo que pasa: las
> features se materializan, el candidato entrena, la evaluación corre... y el
> step de promoción falla. No es un bug: es el sistema haciendo exactamente lo
> que debe. El run quedó registrado en MLflow con su veredicto, gates
> underscore passed en falso, y el estado de promoción dice bloqueado por
> gates de calidad.

**[PANTALLA]** MLflow UI → **Models** → `petrocast-production`: el alias
`@champion` sigue en la versión de `2026-02-01`.

> Y acá está la prueba del guardrail: el registry. El alias champion sigue
> apuntando a la misma versión de antes, la del corte de febrero que sí pasó
> los gates. Un reentrenamiento malo nunca pisa al modelo que está sirviendo
> predicciones. Y si un día hiciera falta volver atrás, hay un runbook de
> promoción y rollback: mover el alias es una operación de un comando.

**[PANTALLA]** GitHub → pestaña **Actions** del repo, un run de `ci` verde en
`main`; abrir los jobs `ml checks` y `data pipeline checks`.

> Todo esto viaja por CI/CD. Cada pull request corre lint, tipos, los tests de
> la API, los del paquete de ML con smokes de entrenamiento e inferencia
> offline, y el pipeline de datos completo contra un Postgres real, incluido
> el test anti-leakage que mencionó Ignacio. Las imágenes Docker se buildean,
> se escanean y se publican en ECR, cada PR levanta un preview efímero, y el
> merge a main despliega a staging con rollback automático. Joaquin cierra
> con la parte que ve el usuario: la API.

### Bloque 4 — Joaquin: tracking, API en vivo y cierre (6:50–9:30)

**[PANTALLA]** MLflow UI → run `2026-02-01-h3` → vista de detalle.

> Gracias, Santino. Antes de la API, miren la trazabilidad de un run: los
> parámetros del modelo, las métricas contra la naive, y tres tags de contrato
> que identifican unívocamente cada corrida: la fecha de corte, la versión de
> las features y el commit de git. Más los artefactos: el modelo serializado,
> la metadata y el reporte de evaluación en JSON. Cualquier predicción que
> sirva la API se puede rastrear hasta acá: qué modelo, entrenado con qué
> datos, con qué código.

**[PANTALLA]** Terminal (fuente grande). Correr los curls uno a uno, dejando
ver cada respuesta. `<POZO_DEMO>` es el pozo anotado en §1.7.

**[ACCIÓN]** Curl 1 — happy path:

```bash
curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=<POZO_DEMO>&as_of_date=2026-01-15&horizon=3"
```

> La API embebe el modelo: al primer pedido carga el champion desde el
> registry por su alias, y lo cachea. Le pido tres meses de pronóstico para
> este pozo, con corte en enero. Ahí está: los tres meses siguientes con la
> producción esperada en metros cúbicos, y un campo model version que dice
> exactamente qué versión del champion respondió: la misma que vimos recién
> en el registry.

**[ACCIÓN]** Curl 2 — error de negocio (404):

```bash
curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=<POZO_DEMO>&as_of_date=2024-03-15&horizon=3"
```

> Distintas condiciones, distintas respuestas. Si pido un corte que no tiene
> features materializadas, no inventa nada: cuatrocientos cuatro, con un
> mensaje claro. El modelo solo predice desde el feature store persistido,
> nunca calcula features al vuelo: es la misma garantía point-in-time de
> entrenamiento, ahora en serving.

**[ACCIÓN]** Curl 3 — error de validación (422):

```bash
curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=<POZO_DEMO>&as_of_date=2026-01-15&horizon=13"
```

> Y si pido un horizonte fuera del contrato, doce meses es el máximo,
> cuatrocientos veintidós de validación antes de tocar el modelo.

**[ACCIÓN]** Curl 4 — observabilidad:

```bash
curl -H "X-API-Key: abcdef12345" "http://localhost:8000/health/deep"
```

> El health check profundo también reporta el estado del serving: modelo
> cargado, y qué versión. Observabilidad de punta a punta.

**[PANTALLA]** Volver a `docs/fase-3/README.md` con el diagrama de flujo.

> Cerramos con el valor de todo esto. Petrocast pasó de ser una plataforma de
> datos a un sistema de decisión: pronósticos de producción por pozo,
> consumibles por API, con un modelo que se reentrena solo todos los meses y
> que tiene prohibido degradarse, porque los gates de calidad comparan cada
> candidato contra baselines reales antes de promoverlo. Cada número que
> devuelve la API es trazable al run, a los datos y al commit que lo
> generaron. Eso es ingeniería de machine learning: no solo un modelo que
> predice, sino un sistema que se puede operar, auditar y mejorar con
> confianza. Gracias por vernos.

---

## Parte 4 — Grabación y edición

- **Herramienta**: OBS Studio (gratis) o Loom. Grabar pantalla a 1080p.
- **Cada uno graba su bloque** por separado (pantalla + voz); Joaquin edita y
  une. Alternativa: una sola sesión por llamada compartiendo pantalla y se
  turnan; menos edición, más ensayo.
- **Zoom**: navegador al 125–150%, terminal con fuente ≥ 16pt. Regla: si no se
  lee en un celular, está chico.
- **Cortes**: la espera del retraining del bloque 3 se corta en edición (dejar
  el launch, cortar, retomar en el step de evaluación terminando).
- **Audio**: micrófono cerca, ambiente silencioso, y un ensayo de niveles antes
  de la toma buena.
- **Antes de grabar cada bloque**: cerrar pestañas ajenas, ocultar bookmarks,
  modo no molestar (que no salte una notificación en plena toma).
- **Ensayo general obligatorio**: correr el guion completo una vez, cronometrar.
  Si pasa de 9:45, recortar del bloque propio, no acelerar la voz.

## Parte 5 — Publicación y cierre del repo

1. Exportar el video (1080p, mp4) y subirlo a YouTube como **No listado**.
2. Reemplazar los dos placeholders con el link:
   - `README.md` raíz, sección "Video Entrega Adenda Fase 3" (línea del `TBD`).
   - `docs/fase-3/README.md`, línea "Video de la entrega: **TBD**".
3. Marcar los 6 ítems del checklist en `docs/fase-3/README.md`.
4. Abrir una PR `docs: link del video de Fase 3` con esos cambios (milestone
   `Fase 3 — Adenda 3`), review de un compañero, squash a `main`.
5. Verificar que el link funciona en incógnito (sin sesión de Google).

## Plan B (si algo falla el día de la grabación)

- **datos.gob.ar caído / sin internet**: si el warehouse ya se cargó en §1.4,
  no afecta (todo lo demás es local). Si no se llegó a cargar, usar el camino
  de fixtures: `MLFLOW_TRACKING_URI=http://localhost:5000
infra/scripts/demo/f3-21-demo-evidence.sh tracking-runs` genera los 2 runs
  con métricas distintas, y `infra/scripts/demo/f3-21-demo-evidence.sh
api-offline` demuestra los escenarios de la API vía TestClient. El bloque 3
  se cubre mostrando el run verde de `retraining_job` de un ensayo previo
  (grabar SIEMPRE el ensayo general por si acaso).
- **La corrida en vivo de `2026-03-01` tarda demasiado**: usar la grabación
  del ensayo para ese tramo (por eso el ensayo se graba).
- **La API devuelve 503 en el happy path**: el champion no está o MLflow está
  caído. Verificar `docker compose ... ps`, el alias en MLflow Models, y
  reintentar; la carga es lazy y reintenta en el próximo request.

## Apéndice — Mapa requisito de la adenda → minuto del video

| Requisito (adenda Fase 3)                    | Dónde queda cubierto                                                         |
| -------------------------------------------- | ---------------------------------------------------------------------------- |
| Diseño de arquitectura                       | Bloque 1 (0:00) + diagrama en cierre (8:50)                                  |
| Herramientas usadas                          | Bloques 1–4 (dbt, LightGBM, MLflow, Dagster, FastAPI, Actions)               |
| Rationale de puntos clave                    | PIT/leakage y modelo global (B2), champion/gates (B3), serving embebido (B4) |
| Valor agregado del sistema                   | Cierre (8:50)                                                                |
| Métricas de training en distintos runs       | MLflow Compare (2:50) + detalle de run (6:50)                                |
| Llamadas a la API en distintas condiciones   | Curls 200/404/422 + health (7:40)                                            |
| Trigger de un retrain                        | Launch en vivo de `2026-03-01` (4:30)                                        |
| Entrenamiento/deploy recurrente y automático | Schedule mensual (B3)                                                        |
| Pipelines desplegados por CI/CD              | GitHub Actions (5:50)                                                        |
