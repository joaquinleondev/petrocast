# ADR-0025: Estrategia de calidad de datos y consecuencia operativa

- **Estado:** Aceptado
- **Fecha:** 2026-06-08
- **Autores:** Ignacio Vargas Fernández
- **Decisores:** Equipo Petrocast

## Contexto y problema

El gold de la arquitectura medallion (ADR-0023, ADR-0024) lo consumen usuarios
no técnicos vía Metabase, que toman decisiones sobre esos datos sin capacidad de
auditar el SQL subyacente. Si un dato sucio (un valor fuera de rango, un duplicado,
un faltante) llega al gold, el usuario lo verá como verdad sin saber que está mal.

La adenda exige (RNF4/RNF5) una estrategia de calidad de datos con **consecuencia
operativa**: no alcanza con medir calidad, hay que decidir **qué pasa cuando un
chequeo falla**. Necesitamos fijar:

1. **Qué dimensiones de calidad** chequeamos y con qué herramienta.
2. **Dónde** corren los chequeos dentro del pipeline.
3. **Qué consecuencia** tiene un fallo: ¿se bloquea la promoción del dato,
   se marca como sospechoso pero se publica, o sólo se alerta?
4. **Persistencia**: ¿se guardan las filas que fallaron para diagnóstico?

El motor es dbt Core v2 (ADR-0023), que ofrece dbt tests con `store_failures`;
la orquestación es Dagster, cuyos **asset checks** pueden bloquear la
materialización de assets aguas abajo.

## Drivers de la decisión

- **Proteger a usuarios no técnicos.** El consumidor final no puede juzgar si
  el dato está mal; el sistema debe impedir que el dato sucio lo alcance.
- **Diagnóstico y reproceso.** Cuando algo falla, el Data Owner y el Data
  Engineer necesitan ver *qué filas* fallaron, no sólo que "falló" (alinea con
  los runbooks F2-26/F2-27).
- **Continuidad del servicio.** Bloquear la promoción no debe dejar a Metabase
  vacío: el último gold bueno debe seguir disponible.
- **Cobertura suficiente, no exhaustiva.** Cinco dimensiones bien elegidas
  cubren los riesgos reales del dataset sin sobre-ingeniería para el plazo.
- **Afinidad con el stack.** Aprovechar dbt tests + asset checks de Dagster en
  lugar de construir un framework de validación propio.

## Opciones consideradas

### Dimensiones de calidad

1. **Cinco dimensiones**: schema, completitud, unicidad, validez de rangos,
   frescura — como dbt tests con `store_failures = true`.
2. **Sólo tests de schema/unicidad** (los que trae dbt de fábrica), sin validez
   de rangos ni frescura.
3. **Framework de validación propio** (Python ad-hoc) en vez de dbt tests.

### Consecuencia ante un fallo

1. **Bloqueo de promoción** vía asset checks de Dagster + notificación.
2. **Marca visible** (publicar el dato pero etiquetarlo como sospechoso).
3. **Solo alerta** (publicar el dato y notificar, sin frenar nada).

### Persistencia de fallos

1. **`store_failures = true`** (las filas que fallan quedan en una tabla).
2. **Sin persistencia** (el test sólo devuelve pass/fail).

## Decisión

- **Dimensiones:** chequeamos **cinco dimensiones** como **dbt tests con
  `store_failures = true`**, en la transición **Bronze→Silver** (donde el riesgo
  de dato sucio es mayor), antes de materializar el gold:
  1. **Schema** — tipos y columnas esperadas.
  2. **Completitud** — ausencia de nulos en campos obligatorios.
  3. **Unicidad** — no hay dos filas con la misma clave de negocio
     (`(well_id, date)`).
  4. **Validez de rangos** — valores dentro de rangos plausibles (p. ej.
     producción ≥ 0).
  5. **Frescura** — los datos corresponden al período esperado.
- **Consecuencia:** **bloqueo de promoción**. Los dbt tests se envuelven en
  **asset checks bloqueantes de Dagster**: si un check falla, Dagster **detiene
  la materialización de los assets aguas abajo** (el gold no se actualiza) y
  marca el asset check como fallido. Un **sensor de Dagster** dispara la
  **notificación automática** (Slack/email).
- **Persistencia:** `store_failures = true` → las filas que fallan quedan en una
  tabla consultable para diagnóstico del Data Owner / Data Engineer.

Elegimos **bloqueo** sobre "marca visible" y "solo alerta" porque el consumidor
es no técnico y no puede protegerse solo: si el dato sucio llega al gold, lo
toma como válido. La alerta sin bloqueo es insuficiente —si nadie actúa a
tiempo, el dato sucio llega igual—. El bloqueo, combinado con mantener el último
gold bueno disponible en Metabase, protege al usuario sin cortar el servicio.
Elegimos dbt tests sobre un framework propio porque ya tenemos dbt (ADR-0023) y
sus tests se integran con el linaje y con los asset checks de Dagster sin código
extra. `store_failures` convierte cada fallo en evidencia accionable para los
runbooks.

## Consecuencias

### Positivas

- El dato sucio **no llega** al consumidor no técnico: el gold sólo se actualiza
  si pasa calidad.
- Las filas fallidas quedan persistidas (`store_failures`) → diagnóstico directo
  para el Data Owner (F2-27) y reproceso para el Data Engineer (F2-26).
- Continuidad: el último gold bueno permanece en Metabase mientras se resuelve.
- Estado visible en la UI de Dagster ("asset bloqueado por check fallido desde
  [fecha]") y exportable a DataHub.
- Cobertura con cinco dimensiones sin construir framework propio.

### Negativas / trade-offs asumidos

- **Un fallo frena el pipeline.** Requiere intervención humana (Data Owner
  decide; Data Engineer reprocesa) para desbloquear; sin eso, el gold se
  "congela" en el último run bueno. Es el costo deliberado de proteger al
  usuario, y por eso existen los dos runbooks.
- Definir bien rangos y umbrales (validez, completitud) exige conocimiento del
  dominio; un umbral mal puesto puede bloquear de más (falsos positivos) o de
  menos. Mitigado dejando el umbral de "aptitud para uso" como decisión del
  Data Owner (regla de negocio, ver F2-27).
- `store_failures` agrega tablas de fallos al warehouse (storage menor,
  aceptable).

### Neutras

- El canal de notificación concreto (Slack vs email) y el umbral exacto de cada
  dimensión se afinan en la implementación (F2-17/F2-18), no en este ADR.
- Los chequeos corren en Bronze→Silver; chequeos adicionales en gold quedan
  abiertos a una fase posterior si hiciera falta.

## Pros y contras de las opciones

### Dimensiones de calidad

#### Cinco dimensiones (dbt tests + store_failures)

- ✅ Cubre los riesgos reales (schema, nulos, duplicados, rangos, frescura);
  declarativo junto al modelo; persiste evidencia.
- ❌ Hay que definir rangos/umbrales del dominio.

#### Solo schema/unicidad

- ✅ Mínimo esfuerzo; tests nativos de dbt.
- ❌ No detecta valores absurdos ni datos desactualizados; insuficiente para
  proteger al consumidor.

#### Framework propio (Python)

- ✅ Control total de la lógica.
- ❌ Hay que construir y mantener tests, persistencia e integración con linaje y
  Dagster; reinventa lo que dbt ya da.

### Consecuencia ante un fallo

#### Bloqueo de promoción

- ✅ Garantiza que el dato sucio no llega al usuario; estado explícito; fuerza
  resolución.
- ❌ Frena el pipeline; necesita intervención humana para desbloquear.

#### Marca visible

- ✅ No corta el flujo; el dato se publica con advertencia.
- ❌ El usuario no técnico puede ignorar o no entender la marca y usar el dato
  igual.

#### Solo alerta

- ✅ Cero fricción operativa.
- ❌ El dato sucio llega al gold de todos modos; si nadie reacciona a tiempo, el
  daño ya está hecho.

### Persistencia de fallos

#### `store_failures = true`

- ✅ Evidencia accionable (qué filas, por qué) para runbooks y diagnóstico.
- ❌ Tablas de fallos extra en el warehouse.

#### Sin persistencia

- ✅ Cero storage extra.
- ❌ Sólo se sabe que falló, no qué ni por qué; diagnóstico a ciegas.

## Referencias

- ADR-0023 — Arquitectura medallion y motor dbt Core v2 (dónde corren los tests).
- ADR-0024 — Modelo dimensional del gold (clave de negocio `(well_id, date)`).
- Adenda técnica Fase 2 (`docs/prd/addendum-v0.3.md`) — RNF4/RNF5, cinco
  dimensiones, asset checks bloqueantes, sensor de notificación, `store_failures`.
- Runbook Data Owner (F2-27) y Data Engineer (F2-26) — consumen este bloqueo.
- dbt tests / `store_failures` y Dagster asset checks — documentación oficial.
- Issue [#19](https://github.com/joaquinleondev/petrocast/issues/19) — F2-07.
