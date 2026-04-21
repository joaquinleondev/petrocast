# ADR-0007: Alineación con el contrato OpenAPI de Fase 1

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

ADR-0006 establece que los campos de los responses JSON de la API deben
usar `camelCase` (`wellId`, `dateStart`, `forecastValues`). Sin embargo,
la adenda técnica de Fase 1 emitida por la cátedra define un contrato
OpenAPI específico con campos en `snake_case`:

- `id_well`, `date_start`, `date_end` (parámetros de query)
- `id_well`, `date`, `prod` (campos del response JSON)

Este contrato es la fuente de verdad que el evaluador usará para
validar el funcionamiento del servicio. Desviarse de él implica que la
validación automática falle, independientemente de la calidad interna
del código.

ADR-0006 sección 4 anticipa exactamente esta situación bajo el título
"Excepción: contratos de API impuestos externamente", y delega la
formalización al ADR del contrato concreto. Este es ese ADR.

## Drivers de la decisión

- El contrato OpenAPI de Fase 1 es definido externamente por la cátedra
  y no es negociable para esta fase.
- La validación del entregable se realizará contra ese contrato; una
  discrepancia de naming genera fallos de integración.
- El código interno puede seguir sus propias convenciones; el mapping
  ocurre en la capa de serialización (Pydantic).
- La excepción ya está prevista y documentada en ADR-0006, por lo que
  no contradice las convenciones del proyecto.

## Opciones consideradas

1. **Respetar el contrato externo tal cual** (`snake_case` en campos
   públicos de la API).
2. **Implementar `camelCase` interno y agregar una capa de mapeo** que
   traduzca antes de serializar el response.
3. **Proponer al cliente (cátedra) que cambie el contrato a `camelCase`.**

## Decisión

Adoptamos la **opción 1**: los endpoints `GET /api/v1/forecast` y
`GET /api/v1/wells` exponen exactamente los campos y nombres definidos
en el contrato OpenAPI de la adenda técnica.

Los modelos Pydantic que representan estos responses usan los nombres
del contrato directamente (`id_well`, `prod`, `date`). No se agrega
una capa de mapeo porque:

- El mock de Fase 1 no tiene lógica de dominio interna que requiera
  nombres distintos a los del contrato.
- Una capa de mapeo agrega complejidad innecesaria para un mock.

Si en fases posteriores el código interno necesita nombres distintos
a los del contrato, se introduce el mapeo en ese momento.

## Consecuencias

**Positivas:**

- La validación automática del evaluador pasa sin fricción.
- El código es directamente legible contra la spec OpenAPI.
- Sin overhead de mapeo en el mock.

**Negativas / trade-offs asumidos:**

- Los modelos Pydantic del response usan `snake_case` en vez del
  `camelCase` que usaría una API REST sin contrato externo impuesto.
  Esto es una excepción explícita y localizada.

**Neutras:**

- Si el contrato cambia en fases posteriores, los modelos deben
  actualizarse. Eso es esperado para cualquier cambio de contrato.

## Pros y contras de cada opción

### Respetar el contrato externo (elegida)

- ✅ Pasa la validación del evaluador sin adaptaciones.
- ✅ Máxima fidelidad al spec; cero riesgo de discrepancias.
- ✅ Sin complejidad adicional en el mock.
- ❌ Los campos del response no siguen `camelCase` de ADR-0006 (excepción justificada).

### camelCase interno + capa de mapeo

- ✅ El código interno sigue ADR-0006 estrictamente.
- ❌ Agrega una capa de transformación innecesaria para un mock.
- ❌ Mayor superficie de bugs (errores de mapeo pueden romper la validación).

### Proponer cambio del contrato a camelCase

- ✅ Alinearía el contrato con las convenciones internas.
- ❌ El contrato es emitido por la cátedra; no está en nuestro control.
- ❌ Fuera de alcance y tiempo para Fase 1.

## Referencias

- ADR-0006 sección 4 — "Excepción: contratos de API impuestos externamente".
- Adenda técnica Fase 1 (`docs/prd/adenda-fase-1.md`) — especificación
  OpenAPI completa con los campos del contrato.
