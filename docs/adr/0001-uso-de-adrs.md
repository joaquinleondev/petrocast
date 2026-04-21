# ADR-0001: Adopción de ADRs para documentar decisiones arquitectónicas

- **Estado:** Aceptado
- **Fecha:** 2026-04-20
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

Durante el desarrollo de un proyecto de software se toman decisiones que
afectan la arquitectura, el stack tecnológico, los procesos de trabajo y
la organización del código. Estas decisiones suelen implicar trade-offs
no triviales entre opciones válidas, y su contexto se pierde con el tiempo
si no se documenta explícitamente.

En nuestro caso, el proyecto Petrocast se desarrolla en tres fases a lo
largo del cuatrimestre, con tres personas trabajando en paralelo. Sin un
mecanismo formal para documentar decisiones:

- Los miembros del equipo podrían cuestionar en Fase 2 decisiones tomadas
  en Fase 1 sin recordar por qué se tomaron así.
- Las decisiones quedarían implícitas en commits o conversaciones de
  mensajería, dificultando su revisión.
- La evaluación del TP explícitamente requiere documentar los análisis
  realizados durante el desarrollo.

Necesitamos un mecanismo ligero, versionado junto con el código, que
capture **el contexto, las opciones consideradas y la justificación** de
cada decisión relevante.

## Drivers de la decisión

- Requerimiento explícito de la consigna del TP: documentar el razonamiento
  detrás de las decisiones de diseño.
- Necesidad de que decisiones tomadas por una persona sean comprensibles
  para las otras dos sin necesidad de conversación sincrónica.
- Preferencia por herramientas livianas que no agreguen overhead al flujo
  de trabajo.
- Las decisiones deben vivir junto al código y versionarse con él.

## Opciones consideradas

1. **ADRs en Markdown dentro del repo** (formato MADR).
2. **Documentación centralizada en Notion o Confluence.**
3. **No documentar formalmente; confiar en comentarios de código y commits.**

## Decisión

Adoptamos **ADRs en Markdown dentro del repositorio**, siguiendo una
variante simplificada del formato [MADR (Markdown Any Decision Records)](https://adr.github.io/madr/).

Los ADRs se ubican en `docs/adr/` y se numeran secuencialmente
(`0001-*.md`, `0002-*.md`, ...). Un índice en `docs/adr/README.md` lista
todos los ADRs existentes con su estado.

**Criterio para escribir un ADR:** cualquier decisión que tenga al menos
dos alternativas razonables y cuyo cambio futuro implique retrabajo
significativo. No se escribe un ADR para decisiones triviales o reversibles.

**Estados válidos:** Propuesto, Aceptado, Deprecado, Reemplazado por
ADR-XXXX. Los ADRs nunca se borran ni se editan después de ser aceptados:
si una decisión cambia, se escribe un nuevo ADR que reemplaza al anterior
y se actualiza el estado del viejo.

## Consecuencias

**Positivas:**

- Las decisiones quedan versionadas con el código y accesibles en el mismo
  repo.
- El historial de ADRs cuenta la evolución arquitectónica del proyecto.
- Satisface el requisito de evaluación de explicitar análisis realizados.
- Induce disciplina: escribir un ADR obliga a considerar alternativas.

**Negativas / trade-offs asumidos:**

- Overhead de escritura para cada decisión no trivial.
- Riesgo de "fatiga de ADR" si se escriben para decisiones triviales.

**Neutras:**

- La calidad de los ADRs depende del rigor de quien los escribe; se
  mitigará con revisión cruzada vía PR.

## Pros y contras de cada opción

### ADRs en Markdown en el repo

- ✅ Versionados junto con el código que describen.
- ✅ Revisables vía PR, lo que permite feedback antes de aceptar una decisión.
- ✅ Formato estándar en la industria, fácilmente legibles.
- ❌ Menos visuales que una wiki con búsqueda integrada.

### Notion / Confluence

- ✅ Búsqueda y jerarquía visual más ricas.
- ❌ Desacoplados del código; pueden quedar desactualizados.
- ❌ Dependencia de una herramienta externa.
- ❌ No se versionan junto al estado del repo en un momento dado.

### No documentar formalmente

- ✅ Cero overhead.
- ❌ Las decisiones se pierden; los nuevos miembros no tienen contexto.
- ❌ Incumple el requisito de evaluación del TP.

## Referencias

- [Michael Nygard — "Documenting Architecture Decisions" (2011)](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [MADR — Markdown Any Decision Records](https://adr.github.io/madr/)
- Consigna del TP (sección "Entregables"): ADRs como componente evaluable.
