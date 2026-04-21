# ADR-0002: Idioma a utilizar en documentación y código

- **Estado:** Aceptado
- **Fecha:** 2026-04-20
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

El proyecto involucra dos tipos de texto escrito:

1. **Documentación para humanos**: PRD, ADRs, README, historias de usuario,
   comentarios de PR.
2. **Código y artefactos técnicos**: nombres de variables, funciones,
   endpoints de API, mensajes de commit, nombres de branch, tablas y
   columnas de base de datos.

El equipo trabaja en español (materia dictada en UDESA, equipo
hispanohablante, PRD original redactado en español). Sin embargo, la
convención dominante en la industria del software es escribir código en
inglés, independientemente del idioma nativo del equipo.

Mezclar idiomas sin una regla explícita lleva a inconsistencias que
deterioran la legibilidad: funciones con nombres como `calcularForecast()`
o variables `wellPozo`.

## Drivers de la decisión

- El PRD y la comunicación con el "cliente" (profesores) son en español.
- El dominio (pronóstico de producción de hidrocarburos) tiene vocabulario
  técnico que convive entre inglés y español (ej: "well/pozo",
  "forecast/pronóstico", "declination/declinación").
- Las dependencias, frameworks, documentación técnica y mensajes de error
  de las herramientas están en inglés.
- Un mismo tipo de artefacto debe tener un idioma consistente; las
  excepciones deben ser justificables.

## Opciones consideradas

1. **Todo en español** (documentación y código).
2. **Todo en inglés** (documentación y código).
3. **Documentación en español, código en inglés** (convención mixta).

## Decisión

Adoptamos una **convención mixta** con las siguientes reglas:

**En español:**

- PRD y adendas técnicas.
- ADRs.
- README (sección principal; las secciones técnicas de instalación pueden
  incluir términos en inglés sin traducir).
- Historias de usuario y backlog.
- Descripciones de PRs e issues.
- Comentarios de código que explican decisiones de negocio o dominio.

**En inglés:**

- Todo identificador en el código: nombres de variables, funciones,
  clases, módulos, archivos de código.
- Endpoints de API y nombres de campos en responses JSON.
- Nombres de tablas y columnas de base de datos.
- Nombres de branches.
- Mensajes de commit (siguiendo Conventional Commits).
- Logs y mensajes técnicos emitidos por la aplicación.

**Términos del dominio sin traducción forzada:** algunos términos se usan
habitualmente en inglés en la industria argentina de oil & gas (ej:
"workover", "downtime", "turn-on date"). Cuando aparezcan en documentación
en español, se mantienen en inglés sin comillas ni cursiva, salvo la
primera aparición en un documento, que puede aclararse entre paréntesis.

## Consecuencias

**Positivas:**

- La documentación es accesible al evaluador (profesores) sin fricción.
- El código sigue la convención estándar de la industria, facilitando su
  lectura por cualquier ingeniero y su integración con librerías en inglés.
- Al momento de buscar ayuda sobre el código (Stack Overflow, docs),
  los términos coinciden con las fuentes.

**Negativas / trade-offs asumidos:**

- Requiere disciplina para no mezclar idiomas dentro de un mismo artefacto.
- En conversaciones sobre código, el equipo alternará idiomas
  naturalmente ("el método `calculateForecast` calcula el pronóstico").

**Neutras:**

- La convención es la más común en equipos hispanohablantes del sector
  tech; no representa una elección controversial.

## Pros y contras de cada opción

### Todo en español

- ✅ Coherencia absoluta de idioma.
- ❌ Rompe con la convención universal de código en inglés.
- ❌ Fricciona con librerías y frameworks (mezcla inevitable).
- ❌ Identificadores en español son menos portables.

### Todo en inglés

- ✅ Convención profesional uniforme.
- ❌ Agrega fricción para el equipo y para la comunicación con los
  profesores (el PRD original está en español).
- ❌ El equipo puede expresar razonamientos más precisos en su lengua
  nativa; forzar inglés empobrece los ADRs.

### Convención mixta (elegida)

- ✅ Documentación fluida en español; código universal en inglés.
- ✅ Refleja la práctica real de equipos hispanohablantes profesionales.
- ❌ Requiere criterio para saber qué va en cada idioma (mitigado con
  reglas explícitas en este ADR).

## Referencias

- ADR-0005 (Convenciones de commits) — especifica que los mensajes de
  commit van en inglés.
