# ADR-0030: Objetivo predictivo, horizonte y métricas de evaluación

- **Estado:** Aceptado
- **Fecha:** 2026-07-01
- **Autores:** Ignacio Vargas Fernandez
- **Decisores:** Equipo Petrocast

## Contexto y problema

Fase 3 incorpora un modelo predictivo servido por la API (ADR-0034), con
tracking reproducible (ADR-0032), feature store (ADR-0031) y retraining
orquestado (ADR-0033). Antes de escribir un solo pipeline hay que fijar la
decisión que condiciona a todas las demás: **qué se predice, con qué horizonte
y cómo se mide si el modelo es bueno**. Esta decisión congela el **contrato F**
del backlog (métricas/horizonte), consumido por training (#13), evaluación y
gates (#15), promoción del champion (#16), contrato OpenAPI (#17) y model card
(#22).

La realidad del dato acota el espacio de decisión:

- `gold.fact_production` tiene grano **pozo-mes**: clave `(well_id,
  production_month)` con `well_id = cast(idpozo as text)` (ver
  `silver_production.sql`). La fuente oficial es **mensual** y **métrica**
  (petróleo en m³, gas en Mm³); no existe dato diario.
- Un mismo pozo (boca, `sigla`) puede producir de **varias formaciones**, cada
  una con su `idpozo` — la ambigüedad **A3** de
  `supuestos-y-clarificaciones.md`, que este ADR debe resolver.
- Las series tienen **meses en cero** (pozos shut-in) y colas largas: hay
  pozos maduros con 20 años de histórico y pozos nuevos con pocos meses
  (cold-start). Cualquier métrica porcentual pura (MAPE) explota con ceros.
- El **KPI del PRD** pide **reducción del MAPE a corto plazo** contra el
  baseline "mantener el último datapoint" (persistencia naive); el estándar
  de industria para declino de pozos es **Arps** (P4 de
  `supuestos-y-clarificaciones.md`).

Además, la API de Fase 1 expone un forecast **por pozo** (`id_well`), por lo
que el objetivo elegido debe poder servirse a través de ese contrato
(reconciliación en ADR-0034 / backlog #17).

## Drivers de la decisión

- **Valor directo para el usuario de la API.** El contrato de Fase 1 promete
  pronóstico por pozo; el objetivo debe alimentar ese caso de uso sin capas de
  traducción artificiales.
- **Respetar el grano del dato.** Mensual, m³, por `idpozo`. Prometer salida
  diaria sería interpolación sin precisión real (P2).
- **Robustez a ceros e intermitencia.** Meses shut-in son normales; la métrica
  primaria no puede indefinirse ni explotar con `y = 0`.
- **KPI verificable.** El PRD exige ganarle al naive; la credibilidad de
  industria exige compararse con Arps (P4).
- **Cold-start.** Pozos nuevos con poco histórico deben recibir predicción
  razonable; empuja a un modelo global con features estáticas del pozo por
  sobre un modelo por serie.
- **Esfuerzo acotado.** Equipo de 3, entrega 11-jul: un solo modelo, un solo
  target, un pipeline de evaluación.
- **Reproducibilidad.** Split temporal determinístico y backtesting repetible
  para un `as_of_date` dado (ADR-0033).

## Opciones consideradas

1. **Regresión de producción futura mensual por pozo** (`prod_pet` en m³, un
   único LightGBM global sobre todos los pozos).
2. **Clasificación de caída / anomalía** (predecir si un pozo va a declinar
   más que un umbral, o flaggear producción anómala).
3. **Forecast agregado por cuenca/área** (predecir la producción total de la
   cuenca Neuquina, no por pozo).
4. **Baseline estadístico simple sin ML** (servir naive/Arps por pozo como
   "modelo", sin capa de aprendizaje).

## Decisión

Elegimos la **opción 1: regresión de la producción mensual de petróleo por
pozo**, con esta especificación (contrato F):

### Target, grano y unidad

- **Target:** producción mensual de petróleo `prod_pet` (columna
  `oil_prod_m3` de `gold.fact_production`), en **m³/mes**. Gas y agua quedan
  fuera del target (pueden entrar como features).
- **Entidad:** `well_id` = **`idpozo` casteado a texto**, exactamente el grano
  de `gold.fact_production` y del feature store (contrato A, #09). Esto
  **resuelve A3**: un `idpozo` identifica pozo+formación productiva, que es el
  grano al que existe la serie histórica. `sigla` queda como atributo
  descriptivo (`well_alias` en silver / `dim_well`); si la API necesita operar
  por `sigla`, la traducción es responsabilidad del contrato D (#17,
  ADR-0034), no del modelo.
- **Granularidad de salida:** mensual. No se promete salida diaria (la fuente
  es mensual; interpolar no agrega precisión — P2).

### Horizonte

- **Horizonte en meses**, parámetro `horizon` del request (contrato D):
  `1 ≤ horizon ≤ 12`.
- El foco es el **medio plazo** (presupuesto operativo, plan de workovers — el
  ciclo de planning que P2 identifica como crítico). Horizontes mayores a 12
  meses quedan fuera del alcance de Fase 3.
- **Estrategia multi-step:** un único modelo global con `horizon` como
  feature (estrategia directa). Evita entrenar 12 modelos o encadenar errores
  recursivamente; el detalle de implementación se cierra en #13.

### Modelo

- **Un único LightGBM global** (regresión) entrenado sobre todos los pozos,
  con features de lags/rolling/tendencia (contrato A, #11) más features
  estáticas del pozo (cuenca, área, tipo de recurso, edad). Es el estándar
  moderno para "muchas series relacionadas" (evidencia M5) y maneja cold-start
  vía las features estáticas, donde un modelo por serie no puede.

### Métricas

- **Primarias: MAE, RMSE y MASE**, todas calculadas sobre backtesting con
  split temporal.
  - **MAE/RMSE en m³**: interpretables en la unidad del negocio y sin
    divisiones por cero.
  - **MASE** (Hyndman): escala el MAE del modelo contra un naive de
    referencia. **Definición exacta (contrato F):** para cada pozo, MASE =
    MAE del modelo en test (pooled sobre `h = 1…horizon`) ÷ MAE in-sample
    del naive de un paso (promedio de `|Y_t − Y_{t−1}|` sobre el train hasta
    `as_of_date`) — la definición estándar de Hyndman. **MASE < 1** significa
    que el error de pronóstico es menor que la variación mes-a-mes histórica
    del pozo, y no se indefine con meses en cero, a diferencia del MAPE.
    Ganarle a la **persistencia naive en el horizonte pedido** (el espíritu
    del KPI del PRD) no lo garantiza MASE < 1 por sí solo: lo impone
    directamente el gate 2.
- **Secundaria: MAPE-sobre-no-cero** (MAPE calculado excluyendo meses con
  producción real 0). Se reporta porque es el vocabulario del PRD y de los
  stakeholders, pero no gobierna gates por su fragilidad con valores chicos.
- **Reporte en distribución, no solo promedio:** mediana, p75 y p90 por pozo.
  Los promedios ocultan colas largas en un portfolio heterogéneo (P4).

### Baselines y elegibilidad

- **Naive (persistencia): obligatorio.** Valor futuro = último valor
  observado antes de `as_of_date`, sostenido sobre todo el horizonte. Es el
  baseline del PRD y el comparador out-of-sample del gate 2. No es el
  denominador del MASE (ese es el naive de un paso in-sample — ver
  Métricas).
- **Arps (decline curve): best-effort.** Ajuste exponencial/hiperbólico por
  pozo (`petbox-dca` o ajuste propio). Es la **comparación primaria** frente
  a stakeholders técnicos — ganarle al naive es un piso muy bajo; empatar o
  superar a Arps es el resultado defendible (P4). Si el ajuste resulta
  inestable en el plazo de Fase 3, se degrada a reporte informativo sin
  bloquear el gate (fallback previsto en #15).
- **Filtro de elegibilidad:** la evaluación excluye pozos con **menos de 12
  meses de histórico** antes de `as_of_date` (no hay Arps confiable ni
  estacionalidad observable con menos). Esos pozos igual reciben predicción
  del modelo global (cold-start), pero no participan de métricas ni gates.

### Protocolo de evaluación y umbrales del gate

- **Backtesting temporal** (nunca aleatorio): entrenar con datos hasta el mes
  `M`, predecir `M+1 … M+h`, comparar contra lo observado. Splits
  train/validation/test estrictamente cronológicos (#13).
- **Agregación (contrato F):** la evaluación de los gates es
  **single-origin**: un único `as_of_date` de evaluación, prediciendo
  `h = 1…horizon` desde ese origen. Las métricas por pozo se calculan
  **pooled sobre todos los horizontes** de la ventana de test; los gates
  agregan luego sobre los pozos elegibles (mediana en el gate 1, suma de
  errores absolutos en el gate 2). La evaluación rolling entre distintos
  `as_of_date` la cubre el retraining recurrente (ADR-0033), no el gate.
- **Gates de promoción del champion** (insumo de #15/#16). Un candidato solo
  se promociona si, sobre la ventana de test del backtesting y los pozos
  elegibles:
  1. **MASE mediana por pozo < 1.0** — en al menos la mitad del portfolio,
     el error del modelo es menor que la variación mensual histórica del
     pozo (gate obligatorio; definición exacta de MASE en Métricas).
  2. **MAE agregado ≤ MAE agregado del naive** — no empeora el error total
     en m³ contra la persistencia evaluada out-of-sample sobre la misma
     ventana y horizontes; es el gate que codifica "ganarle al naive"
     (gate obligatorio).
  3. **Contra Arps (best-effort, no bloqueante):** se reporta la distribución
     de MASE/MAE relativa a Arps; objetivo MVP: MAPE-no-cero ≤ Arps + 2 pp en
     el horizonte medio (alineado a la tabla de P4).
- Los umbrales son **por `as_of_date` de evaluación** y quedan registrados en
  el run de MLflow (ADR-0032) junto con las métricas que los sustentan.

### Valor para el usuario de la API

El usuario de la API (planificación/presupuesto) obtiene, para un pozo y una
fecha de corte, la **producción esperada de los próximos `horizon` meses en
m³** — el insumo directo de su ciclo de planning mensual/anual (P2) — con la
garantía medible de que el modelo servido superó al proceso trivial de
"repetir el último mes" (gates 1 y 2) y se compara honestamente contra el
estándar de industria (Arps). La versión de modelo y el `as_of_date` viajan
en la respuesta (contrato D), así que cada número es trazable a un run
reproducible.

## Consecuencias

**Positivas:**

- Contrato F congelado: target, grano, horizonte, métricas, baselines, filtro
  y gates quedan fijos para #13/#15/#16/#17/#22 sin re-discusión.
- A3 resuelta: `well_id = idpozo` (texto), alineado 1:1 con
  `gold.fact_production` y el feature store — cero joins ambiguos entre
  training, store e inferencia.
- MASE + gate 2 operacionalizan el KPI del PRD (ganarle al baseline naive;
  formulado allí como reducción de MAPE a corto plazo) sobre el horizonte de
  1–12 meses de Fase 3, con métricas robustas a pozos shut-in.
- Un solo modelo global simplifica training, registry (un solo champion) y
  serving embebido (ADR-0034).
- Cold-start cubierto por diseño (features estáticas), sin pipeline aparte.

**Negativas / trade-offs asumidos:**

- Predecir a grano `idpozo` (pozo+formación) implica que una consulta por
  `sigla` (boca de pozo) puede requerir agregar varias series; esa
  reconciliación se difiere al contrato de API (#17) y contradice el supuesto
  provisorio de Fase 1 (`id_well = sigla`), que se documenta como superado.
- Un LightGBM global puede rendir peor que modelos por pozo en pozos maduros
  muy estables; se acepta a cambio de cold-start y de un único pipeline.
- Arps como comparación primaria es best-effort: si el ajuste es inestable,
  la entrega se defiende solo contra naive (gate 1 y 2), perdiendo fuerza
  narrativa frente a stakeholders técnicos.
- Horizonte acotado a 12 meses: no se cubre el largo plazo (18m–5a) descripto
  en P2; queda explícitamente fuera de Fase 3.

**Neutras:**

- La decisión es ortogonal a *dónde* viven las features (ADR-0031), *cómo* se
  trackea (ADR-0032), *cuándo* se re-entrena (ADR-0033) y *cómo* se sirve
  (ADR-0034); esos ADRs consumen este contrato.
- Los umbrales del gate pueden endurecerse en el futuro re-apuntando la
  config de #15 sin re-abrir este ADR, siempre que no cambien target ni
  métricas.

## Pros y contras de cada opción

### Regresión mensual por pozo con LightGBM global (elegida)

- ✅ Alimenta directamente el contrato de la API de Fase 1 (forecast por pozo).
- ✅ Respeta el grano nativo del dato (pozo-mes, m³): sin interpolaciones.
- ✅ Global + features estáticas ⇒ maneja cold-start y "muchas series
  relacionadas" con un solo artefacto.
- ✅ Evaluable contra naive y Arps con backtesting temporal estándar.
- ❌ Puede perder contra modelos por serie en pozos maduros estables.
- ❌ Grano `idpozo` obliga a reconciliar `sigla` en la capa de API.

### Clasificación de caída / anomalía

- ✅ Problema más simple (binario), métricas conocidas (precision/recall).
- ❌ No responde lo que la API promete: un **valor** de producción futura.
- ❌ Requiere definir umbrales de "caída" arbitrarios ⇒ target frágil.
- ❌ El KPI del PRD está formulado en error de pronóstico (MAPE/MAE), no en
  detección; no habría forma directa de verificarlo.

### Forecast agregado por cuenca/área

- ✅ Serie agregada más estable y fácil de modelar (los errores por pozo se
  cancelan).
- ❌ Pierde el grano pozo: la API de Fase 1 y el caso de uso de planning son
  por pozo.
- ❌ El feature store por `(well_id, as_of_date)` (contrato A) quedaría
  desacoplado del modelo.
- ❌ Aporta poco valor marginal: sumar Arps por pozo ya da un agregado
  razonable.

### Baseline estadístico simple sin ML (naive/Arps como "modelo")

- ✅ Mínimo esfuerzo; Arps es transparente y estándar de industria.
- ✅ Serviría el mismo contrato de API.
- ❌ No cumple la adenda de Fase 3: exige integración de **ML Engineering**
  (training, tracking, retraining); sin modelo aprendido no hay nada que
  trackear ni promover.
- ❌ Sin capacidad de mejorar con más datos ni de usar features exógenas.
- ❌ El naive/Arps ya están en la decisión elegida — como **baselines**, que
  es su rol correcto.

## Referencias

- [Hyndman, R. J. — "Another look at forecast-accuracy metrics for
  intermittent demand"](https://robjhyndman.com/papers/foresight.pdf) —
  limitaciones del MAPE y definición de MASE.
- Arps, J. J. (1945). *Analysis of Decline Curves.* Transactions of the AIME,
  160(01), 228–247.
- [petbox-dca](https://github.com/petbox-dev/dca) — librería de decline curve
  analysis para el baseline Arps.
- [Makridakis et al. — M5 accuracy competition](https://www.sciencedirect.com/science/article/pii/S0169207021001874)
  — gradient boosting global como estado del arte en series relacionadas.
- `docs/supuestos-y-clarificaciones.md` — P2 (horizontes), P4 (baselines y
  MASE), A3 (`sigla` vs `idpozo`).
- Adenda técnica Fase 3 — requerimientos funcionales y no funcionales.
- [ADR-0023](0023-arquitectura-medallion-dbt.md) — warehouse medallion.
- [ADR-0024](0024-modelo-dimensional-star-schema.md) — grano de
  `gold.fact_production`.
- [ADR-0032](0032-tracking-experimentos-registry.md) — tracking y registry.
- [ADR-0034](0034-serving-modelo-contrato-api.md) — serving y contrato de API.
- ADR-0031 (en redacción) — feature store; ADR-0033 (en redacción) —
  orquestación del retraining.
- Backlog Fase 3 — [#01](../backlog/issues-fase-3.md) (este ADR), #13, #15,
  #16, #17, #22 (consumidores del contrato F).
