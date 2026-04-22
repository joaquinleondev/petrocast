# ADR-0007: Alineación con el contrato OpenAPI de Fase 1 mediante `alias_generator` de Pydantic

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 fija un contrato OpenAPI de cara al cliente cuyos
campos están expresados en `snake_case` (por ejemplo `well_id`,
`forecast_horizon_days`, `produced_at`). Este contrato es **fuente de verdad**
para el evaluador: los mocks, los tests de contrato y los clientes externos
asumen esa forma exacta.

Al mismo tiempo, el ADR-0006 (naming conventions) establece que el código
interno en Python usa `snake_case` para variables y funciones, pero deja
explícitamente abierto cómo se expresan los DTOs y modelos de entrada/salida
de la API: si se mezclan dos convenciones distintas (interna vs. contrato) hay
que decidir **dónde vive el mapeo** y **quién lo controla**.

El problema concreto: necesitamos una forma reproducible, poco verbosa y
difícil de romper en PRs de no infringir el contrato OpenAPI cuando
evolucionemos los modelos internos entre Fase 1 y Fase 3.

## Drivers de la decisión

- **Fidelidad con el contrato.** El mock de Fase 1 y los tests de contrato
  (schemathesis, ver ADR-0016) validan contra el OpenAPI; cualquier divergencia
  rompe CI.
- **Baja fricción para el equipo.** Somos 3 personas con tiempo acotado. No
  queremos escribir mapeadores a mano para cada endpoint.
- **Evolución hacia Fase 3.** El motor de ML introducirá tipos internos
  (features, matrices, ventanas temporales) que no deberían estar tentados a
  filtrarse al contrato externo.
- **Type safety.** Queremos que mypy strict (ver ADR-0015) detecte rupturas
  antes de runtime.
- **Compatibilidad con FastAPI.** La generación automática de OpenAPI de
  FastAPI debe seguir reflejando el contrato acordado, no una versión
  "snake_case pura" del lado del servidor.

## Opciones consideradas

1. **Pydantic `alias_generator` con `populate_by_name=True`.** Los modelos
   viven en `snake_case` internamente y se exponen con alias (que casualmente
   también son `snake_case`, pero formalizado a través del generador).
2. **DTOs explícitos de entrada/salida separados del dominio.** Una capa
   `schemas/` con modelos `PredictionRequest`/`PredictionResponse` pegados al
   contrato y una capa `domain/` con tipos internos; conversión manual o con
   un mapper.
3. **`snake_case` interno acoplado al contrato.** No separar DTO y dominio:
   los modelos Pydantic son el contrato tal cual.

## Decisión

**Usamos Pydantic v2 con `alias_generator` + `populate_by_name=True`** en una
`BaseSchema` compartida de la cual heredan todos los modelos expuestos por la
API. Los atributos Python se escriben en `snake_case` (lo que coincide con la
forma del contrato), pero el generador de alias queda **fijado explícitamente**
en la base para que el día que el contrato externo cambie (por ejemplo si
Fase 2 introduce `camelCase` para algún cliente legacy o si aparece una
versión `v2` del API) el cambio sea **una sola línea** en la clase base y no
un refactor en N modelos.

Internamente, los modelos de dominio (dataclasses o Pydantic sin alias) viven
en `packages/core/` y los modelos de API en `apps/api/src/schemas/`. El router
de FastAPI acepta y devuelve **schemas**, y el servicio traduce a **dominio**
solo cuando hay lógica de negocio que lo justifique.

Esto se alinea con el ADR-0006, que ya dejaba abierta la excepción
explícita: "cuando el contrato OpenAPI lo impone, el alias manda".

## Consecuencias

### Positivas

- Un único punto de control para la forma serializada del API.
- `response_model_by_alias=True` en FastAPI garantiza que el OpenAPI generado
  coincide con el de la adenda.
- El refactor hacia `camelCase` u otra convención futura es trivial.
- mypy strict valida la forma interna sin interferir con el contrato.
- Los tests de contrato (schemathesis) ven exactamente lo que ve el cliente.

### Negativas

- Introduce un concepto (alias) que alguien nuevo en Pydantic tiene que
  aprender, aunque es parte del tutorial oficial.
- Si el equipo olvida `response_model_by_alias=True` en un endpoint, la salida
  puede diverger del contrato. Se mitiga con test de contrato en CI.
- El factor de "alias coincide con atributo" hoy parece redundante; su valor
  es latente, no inmediato.

### Neutras

- No cambia el rendimiento runtime de forma perceptible.
- No requiere dependencias adicionales más allá de las ya usadas.

## Pros y contras de las opciones

### Opción 1 — Pydantic `alias_generator`

- **Pros:**
  - Cero boilerplate por modelo.
  - Escala a docenas de endpoints sin refactor.
  - Compatible nativo con FastAPI.
  - El contrato queda centralizado en una `BaseSchema`.
- **Contras:**
  - Requiere disciplina en usar `by_alias=True` al serializar fuera de
    FastAPI.

### Opción 2 — DTOs explícitos + mapper

- **Pros:**
  - Separación limpísima entre dominio y API.
  - Ideal para sistemas grandes con múltiples consumidores.
- **Contras:**
  - 2x de código (schema + dominio + mapper) para 3 personas.
  - Cuando el dominio es casi idéntico al schema (Fase 1), el mapper es ruido.
  - Curva y mantenimiento desproporcionados para el alcance de Fase 1.

### Opción 3 — `snake_case` interno acoplado al contrato

- **Pros:**
  - Simplicidad máxima.
  - Sin conceptos adicionales.
- **Contras:**
  - Si el contrato externo cambia, hay que refactorear N modelos.
  - Mezcla responsabilidades: los modelos Pydantic son a la vez dominio,
    schema de validación y forma del contrato.
  - Impide una evolución limpia hacia Fase 3.

## Referencias

- ADR-0001 — Uso de ADRs con formato MADR.
- ADR-0006 — Naming conventions y su excepción para contratos externos.
- ADR-0012 — Stack del backend (Python + FastAPI + Pydantic v2).
- ADR-0016 — Estrategia de testing, incluido schemathesis para contract tests.
- Pydantic v2 docs — Model configuration & alias generators.
- FastAPI docs — Response model and `by_alias`.
- Addendum al PRD v0.2 — contrato OpenAPI de Fase 1.
