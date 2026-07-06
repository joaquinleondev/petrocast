# Runbook — Promoción y rollback del modelo champion

Cómo registrar, promover, verificar y revertir la versión servida del modelo
predictivo ([ADR-0035](../adr/0035-cicd-pipelines-ml-promocion.md), backlog
F3-16/F3-23). El camino **normal** es automático: el `retraining_job` de
Dagster (F3-19) encadena features → training → evaluación → promoción y solo
mueve el alias si los gates de calidad pasan. Este runbook cubre la operación
**manual**: promover un candidato fuera de ciclo, verificar qué versión está
activa y, sobre todo, hacer rollback ante un incidente de calidad.

Disparadores típicos:

- Un run de entrenamiento válido no se promovió (falla transitoria de MLflow
  después de pasar gates) y hay que completar la promoción a mano.
- Las predicciones servidas muestran degradación y hay que volver a la versión
  anterior del champion **sin esperar un retrain**.
- Se necesita auditar qué versión está sirviendo la API y de qué run proviene.

> **Modelo ≠ imagen.** Según ADR-0035 son dos artefactos con ciclos de vida
> independientes: un incidente de **modelo** se resuelve re-apuntando el alias
> `champion` (este runbook); un incidente de **código/imagen** se resuelve
> re-deployando un digest anterior de la imagen (ver
> [deploy de staging](deploy-staging-data.md) y `infra/scripts/rollback.sh`).
> El rollback de modelo no reentrena, no reconstruye imágenes y no redeploya.

## Rol, dueño y prerrequisitos

- **Dueño:** MLOps / Santino.
- **Escala a:** Ignacio para dudas sobre métricas/gates (F3-15); Joaquin para
  el tracking server o la API de predicciones.

Antes de comenzar se necesita:

- `apps/ml` sincronizado: `cd apps/ml && uv sync --frozen`.
- `MLFLOW_TRACKING_URI` exportado apuntando al tracking server (contrato C, ver
  [runbook de MLflow](mlflow-tracking.md)). Los defaults del modelo registrado
  (`petrocast-production`) y del alias (`champion`) salen de
  `PETROCAST_MLFLOW_MODEL_NAME` / `PETROCAST_MLFLOW_MODEL_ALIAS`.
- Para verificar contra la API: una API key válida (auth `X-API-Key`,
  contrato D).

Todos los comandos de este runbook corren desde `apps/ml`. La referencia
completa del CLI vive en el [README de `apps/ml`](../../apps/ml/README.md)
(sección F3-16); acá se documenta el procedimiento operativo.

## Pasos

### Paso 1 — Registrar una versión candidata

Un entrenamiento ejecutado con `--track` deja en MLflow un run con métricas,
tags obligatorios (`as_of_date`, `features_version`, `git_commit`), el
resultado de los gates (`gates_passed`) y un Logged Model. Con su `run_id`:

```bash
uv run python -m petrocast_ml.registry register --run-id <run-id>
```

El comando crea una nueva versión del modelo registrado y hereda la
trazabilidad del run. Registrar **no** cambia qué modelo se sirve: el alias
`champion` no se mueve en este paso. El `retraining_job` de Dagster hace este
mismo paso automáticamente; solo hace falta a mano para runs fuera de ciclo.

### Paso 2 — Promover la versión a champion

```bash
uv run python -m petrocast_ml.registry promote --version <version>
```

La promoción es **explícita, idempotente y auditable** (ADR-0035): solo mueve
el alias `champion` a la versión indicada. Antes de moverlo verifica la
metadata del candidato y **rechaza** el cambio si:

- el run de origen no tiene `as_of_date`, métricas o el tag `gates_passed`
  (`CandidateMetadataError`) — típico de un run registrado sin evaluación;
- los gates de calidad no pasaron (`CandidateNotApprovedError`) — un run rojo
  no es promovible, sin excepciones manuales.

Los errores salen como JSON `{"error": ...}` con exit code 1.

### Paso 3 — Hacer efectivo el cambio en la API

La API carga el champion **una vez por proceso** y lo cachea
(`apps/api/src/core/serving.py`): mover el alias no afecta a un proceso que ya
tiene un modelo cargado. Para que la API tome la nueva versión, reiniciar el
servicio:

```bash
# Local (compose):
docker compose restart api

# Staging: re-deployar el servicio de la API (mismo digest de imagen; el
# reinicio del contenedor fuerza la recarga del champion).
```

Si MLflow no está disponible en el arranque, la API responde `503` en
`/api/v1/predictions` y reintenta la carga en el próximo request (no cachea
fallas), así que el servicio se recupera solo cuando MLflow vuelve.

### Paso 4 — Verificar qué versión está activa

Tres puntos de verificación, del registry hacia afuera:

1. **Registry:** el alias debe apuntar a la versión esperada.

   ```bash
   uv run python -m petrocast_ml.registry inspect
   uv run python -m petrocast_ml.registry inspect --version <version>
   ```

2. **UI de MLflow:** en `MLFLOW_TRACKING_URI`, el modelo registrado
   `petrocast-production` muestra el alias `@champion` sobre la versión y su
   run de origen (métricas `eval_*`, tag `gates_passed=true`).

3. **API:** la respuesta de predicciones declara la versión servida.

   ```bash
   curl -s -H "X-API-Key: <api-key>" \
     "http://localhost:8000/api/v1/predictions?id_well=<pozo>&as_of_date=<fecha>&horizon=3"
   # → "model_version" debe ser la versión recién promovida
   ```

Checklist de una promoción sana:

- [ ] `inspect` muestra el alias `champion` en la versión esperada.
- [ ] El run de origen tiene `gates_passed=true` y métricas `eval_*`.
- [ ] La API responde `200` y `model_version` coincide tras el reinicio.
- [ ] Queda registrado quién promovió, cuándo y desde qué versión (ver
      Consideraciones no funcionales).

## Rollback del champion

El rollback usa el **mismo mecanismo** que la promoción: re-apuntar el alias a
una versión anterior ya aprobada. Identificar la versión destino con
`inspect` (buscar la última versión con `gates_passed=true` anterior a la
actual) y ejecutar:

```bash
uv run python -m petrocast_ml.registry rollback --to-version <version-anterior>
```

Después, repetir el **Paso 3** (reinicio de la API) y el **Paso 4**
(verificación). El rollback re-valida los gates de la versión destino: solo se
puede volver a una versión que fue aprobada en su momento — si hace falta
servir algo que nunca pasó gates, eso es una decisión de equipo que requiere
cambiar umbrales por PR, no un bypass operativo.

Anotar en el canal del equipo: versión anterior, versión restaurada, motivo y
hora. El alias en MLflow queda como estado final, pero el "por qué" vive fuera
del registry.

## Si algo falla

**Los gates bloquean una promoción (`CandidateNotApprovedError`):**

- Es el comportamiento correcto: el champion anterior sigue sirviendo y no hay
  nada que revertir.
- Diagnóstico: revisar `evaluation.json` en el artifact del run (o las métricas
  `eval_*` en MLflow) para ver qué gate falló — mediana de MASE `< 1.0` o MAE
  del modelo `≤` MAE de la naive (umbrales de ADR-0030).
- Si el modelo es genuinamente malo: no promover; iterar features/training.
- Si el equipo concluye que el umbral es demasiado estricto: ajustar
  `GateThresholds` por PR + actualización del ADR, nunca promover a mano un
  run rojo.

**`CandidateMetadataError` al promover:**

- El run se registró sin evaluación (falta el tag `gates_passed` o métricas).
- Volver a correr el entrenamiento por el camino completo (CLI con evaluación
  o `retraining_job`), registrar el run nuevo y promover ese. No parchear tags
  a mano en runs de verdad: rompe la trazabilidad que ADR-0035 exige.

**MLflow no responde:**

- `register`/`promote`/`rollback` fallan con error de conexión: reintentar
  cuando vuelva; ninguna operación queda a medias (el alias se mueve en una
  sola llamada).
- La API sigue sirviendo el champion que ya tiene cargado en memoria; los
  procesos que arrancan sin poder cargar responden `503` hasta que MLflow
  vuelva.
- Server local caído → relevantarlo con compose; backend cloud caído → modo
  fallback local. Ambos procedimientos en el
  [runbook de MLflow](mlflow-tracking.md).

**ECR no responde o falta la imagen `petrocast/ml`:**

- No bloquea promociones ni rollbacks de modelo (el alias vive en MLflow); solo
  afecta el ciclo de **imagen**.
- Verificar que el repo `petrocast/ml` exista (Terraform `envs/shared`,
  `module "ecr_ml"`) y que el build de la imagen esté verde.
- Para un incidente de código en staging: re-deployar el último digest sano
  (`sha-<commit>`), ver [deploy de staging](deploy-staging-data.md).

**La API no toma la nueva versión tras promover:**

- Casi siempre falta el **Paso 3**: el proceso viejo sigue vivo con el modelo
  anterior cacheado. Reiniciar el servicio y re-verificar `model_version`.
- Si tras el reinicio responde `503`, el proceso no pudo cargar el champion:
  revisar `MLFLOW_TRACKING_URI`/credenciales del entorno de la API y que el
  alias apunte a una versión con artifacts accesibles.

## Consideraciones no funcionales

**Trazabilidad:**

- Cada versión registrada conserva `run_id`, `as_of_date`, métricas y veredicto
  de gates; la promoción/rollback solo mueve el alias, así que la historia de
  versiones queda intacta y auditable en MLflow.
- Registrar los movimientos manuales (quién/cuándo/por qué) en el canal del
  equipo; el registry guarda el "qué", no el "por qué".

**Seguridad:**

- El tracking server compartido exige las credenciales del contrato C; no
  commitear URIs con contraseña. En CI los smokes usan un MLflow efímero local
  (SQLite), nunca el registry compartido.
- La promoción en CI está fuera de alcance por diseño: el rol de CI publica
  imágenes pero no mueve el alias de producción (ADR-0035).

**Costo/disponibilidad:**

- Promoción y rollback son operaciones de metadata: sin retrain, sin rebuild,
  sin redeploy de imagen — segundos, no horas. El único downtime es el
  reinicio de la API (Paso 3).

## Referencias

- ADR-0030: objetivo predictivo, métricas y umbrales de los gates.
- ADR-0032: tracking de experimentos y registry (aliases, no stages).
- ADR-0034: serving del modelo y carga del champion en la API.
- ADR-0035: CI/CD de pipelines ML, promoción y rollback de artefactos.
- [Runbook de MLflow](mlflow-tracking.md): levantar la plataforma, contrato C,
  troubleshooting del server.
- [README de `apps/ml`](../../apps/ml/README.md): referencia del CLI de
  registry y comandos de entrenamiento/verificación.
- [Deploy de staging](deploy-staging-data.md): ciclo de vida de imágenes y
  rollback de código.
- F3-16 (promoción del champion), F3-19 (retraining job), F3-23 (CI/CD ML).
