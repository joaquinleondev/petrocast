# ADR-0006: Convenciones de naming de archivos, carpetas e identificadores

- **Estado:** Aceptado
- **Fecha:** 2026-04-20
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

A lo largo del proyecto se van a crear archivos, carpetas, variables,
funciones, clases, tablas de base de datos, endpoints de API, nombres
de ramas y artefactos de documentación. Cada uno de estos tiene
convenciones distintas en la industria — y mezclarlas dentro de un mismo
proyecto produce inconsistencias que deterioran la legibilidad y generan
fricción en reviews.

Ejemplos de lo que queremos evitar:

- `UserService.py` al lado de `data_loader.py` (dos convenciones en
  Python).
- `forecastChart.jsx` al lado de `WellSelector.jsx` (inconsistencia en
  componentes React).
- Rutas de API como `/api/getForecastByWell` al lado de `/api/wells/list`
  (mezcla verb-based con REST).
- ADRs con `ADR_0007.md`, `0008-stack.md`, `adr-0009-ci.MD`.

Sin reglas explícitas, cada persona aplica la convención con la que se
siente cómoda, y el proyecto termina siendo heterogéneo.

## Drivers de la decisión

- Consistencia visual e intelectual a lo largo del repositorio.
- Seguir, donde existan, las convenciones **idiomáticas de cada lenguaje
  o ecosistema** (no inventar estilos propios).
- Facilitar la navegación del repo por búsquedas (`grep`, IDE search).
- Evitar problemas de case-sensitivity entre sistemas operativos (macOS
  y Windows son case-insensitive por default, Linux no; un archivo
  `Forecast.py` y `forecast.py` pueden convivir en Git pero romper el
  build en Linux).
- Aplicar consistentemente las convenciones de idioma definidas en
  ADR-0002.

## Decisión

Adoptamos las siguientes convenciones, agrupadas por categoría.

---

### 1. Archivos y carpetas del repositorio

**Regla general:** `kebab-case` en minúsculas para archivos y carpetas,
**excepto** donde el ecosistema del lenguaje dicte otra convención.

| Tipo                           | Convención                        | Ejemplo                                          |
| ------------------------------ | --------------------------------- | ------------------------------------------------ |
| Carpetas generales             | `kebab-case`                      | `data-integration/`, `user-stories/`             |
| Archivos Markdown (docs, ADRs) | `kebab-case.md`                   | `0007-stack-backend.md`                          |
| Archivos de configuración      | nombre estándar de la herramienta | `package.json`, `pyproject.toml`, `.env.example` |
| Archivos en `.github/`         | siguen convención de GitHub       | `PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS`         |

**Regla específica de ADRs:** `NNNN-título-en-kebab-case.md`, con 4
dígitos y guiones. Ejemplo: `0012-eleccion-orquestador-ml.md`. Los
números son secuenciales sin saltos.

**No usar:**

- Espacios en nombres de archivos o carpetas (`User Stories/` → `user-stories/`).
- Mayúsculas en extensiones (`archivo.MD` → `archivo.md`).
- Acentos o caracteres especiales en nombres (incluso en español):
  `pronóstico.md` → `pronostico.md`.

---

### 2. Código Python

Seguimos [**PEP 8**](https://peps.python.org/pep-0008/) estrictamente.

| Elemento          | Convención         | Ejemplo                                    |
| ----------------- | ------------------ | ------------------------------------------ |
| Archivo / módulo  | `snake_case.py`    | `forecast_engine.py`                       |
| Carpeta / paquete | `snake_case/`      | `data_ingestion/`                          |
| Clase             | `PascalCase`       | `ForecastModel`, `WellRepository`          |
| Función / método  | `snake_case`       | `calculate_forecast()`, `load_well_data()` |
| Variable          | `snake_case`       | `well_id`, `forecast_horizon`              |
| Constante         | `UPPER_SNAKE_CASE` | `DEFAULT_HORIZON_DAYS`, `API_VERSION`      |
| Atributo privado  | `_snake_case`      | `_internal_cache`                          |
| Test file         | `test_<módulo>.py` | `test_forecast_engine.py`                  |

**Imports:** siempre absolutos (`from predictiva.forecast import ...`),
nunca relativos (`from ..forecast import ...`). Los absolutos son más
explícitos y sobreviven mejor a refactors.

---

### 3. Código TypeScript / React

Seguimos las convenciones dominantes del ecosistema (compatibles con
Next.js, Remix, etc.).

| Elemento                      | Convención                   | Ejemplo                                 |
| ----------------------------- | ---------------------------- | --------------------------------------- |
| Componente React              | `PascalCase.tsx`             | `ForecastChart.tsx`, `WellSelector.tsx` |
| Hook custom                   | `useCamelCase.ts`            | `useForecast.ts`, `useWellData.ts`      |
| Archivo de utilidades         | `kebab-case.ts`              | `date-utils.ts`, `api-client.ts`        |
| Archivo de tipos              | `kebab-case.ts` o `types.ts` | `forecast-types.ts`                     |
| Carpeta                       | `kebab-case/`                | `components/`, `forecast-charts/`       |
| Archivo de test               | `<nombre>.test.ts[x]`        | `ForecastChart.test.tsx`                |
| Nombre de clase/tipo/interfaz | `PascalCase`                 | `type Forecast`, `interface WellData`   |
| Función / variable            | `camelCase`                  | `calculateForecast()`, `wellId`         |
| Constante top-level           | `UPPER_SNAKE_CASE`           | `DEFAULT_HORIZON_DAYS`                  |
| Componente interno            | `PascalCase`                 | `const ForecastChart = () => ...`       |

**Nota sobre componentes:** el **archivo** que contiene un componente
React tiene el mismo nombre que el componente (`ForecastChart.tsx`
exporta `ForecastChart`). Esto desvía de la regla general de
`kebab-case` pero es la convención universal en el ecosistema React.

**Evitar `default export` para componentes**, salvo cuando el framework
lo exige (páginas de Next.js). Preferir named exports (`export const
ForecastChart = ...`) para facilitar refactors y búsquedas.

---

### 4. API REST

Seguimos convenciones REST estándar, con endpoints en inglés (ver
ADR-0002).

| Elemento                         | Convención                            | Ejemplo                                        |
| -------------------------------- | ------------------------------------- | ---------------------------------------------- |
| Path de recurso                  | `kebab-case` en plural                | `/wells`, `/forecasts`, `/production-data`     |
| Path con parámetro               | `kebab-case` con `:param` o `{param}` | `/wells/:wellId/forecast`                      |
| Query params                     | `camelCase`                           | `?horizonDays=90&modelVersion=v2`              |
| Campos de JSON (body y response) | `camelCase`                           | `{ "wellId": "...", "forecastValues": [...] }` |
| Códigos de estado HTTP           | estándar RFC                          | 200, 201, 400, 404, 500                        |

**Verbos HTTP:** siguen semántica REST (GET = leer, POST = crear,
PUT = reemplazar, PATCH = actualizar parcial, DELETE = eliminar). No
usar verbos en el path: `/calculateForecast` → `POST /forecasts`.

**Versionado:** las rutas se versionan con prefijo `/v1/`, `/v2/`.
Ejemplo: `/v1/wells/:wellId/forecast`.

---

### 5. Base de datos

| Elemento               | Convención                          | Ejemplo                                        |
| ---------------------- | ----------------------------------- | ---------------------------------------------- |
| Tabla                  | `snake_case` en plural              | `wells`, `forecast_runs`, `production_records` |
| Columna                | `snake_case`                        | `well_id`, `created_at`, `forecast_value`      |
| Primary key            | `id` (simple) o `<recurso>_id` (FK) | `id`, `well_id`                                |
| Índice                 | `idx_<tabla>_<columnas>`            | `idx_production_records_well_id`               |
| Foreign key constraint | `fk_<tabla>_<columna>`              | `fk_forecasts_well_id`                         |

**Timestamps:** toda tabla tiene `created_at` y `updated_at` (convención
de Rails/Django), salvo que haya razón para omitirlos. Tipo `timestamp
with time zone` (`TIMESTAMPTZ` en Postgres).

---

### 6. Branches

Ya definido en ADR-0004. Para referencia rápida:
<tipo>/<descripción-kebab-case>
Tipos: `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`, `test/`.

**No usar acentos, mayúsculas, ni espacios** en nombres de branch.

---

### 7. Mensajes de commit

Ya definido en ADR-0005: Conventional Commits en inglés. Para referencia:

```
<tipo>(<scope opcional>): <descripción en inglés, minúsculas, imperativo>
```

---

### 8. Variables de entorno

| Elemento            | Convención         | Ejemplo                                     |
| ------------------- | ------------------ | ------------------------------------------- |
| Variable de entorno | `UPPER_SNAKE_CASE` | `DATABASE_URL`, `API_KEY`                   |
| Prefijo por app     | `<APP>_<VAR>`      | `FORECAST_API_PORT`, `INGESTION_BATCH_SIZE` |

Siempre existe un `.env.example` versionado en el repo con todas las
variables documentadas (valores vacíos o placeholders). El `.env` real
**nunca** se commitea (está en `.gitignore`).

---

### 9. Nombres que requieren criterio

Algunas decisiones de naming no se resuelven por regla sino por criterio.
Lineamientos:

**Longitud:** nombres descriptivos > nombres cortos y crípticos. Una
variable llamada `d` o `x` es mala; `daysUntilForecastEnd` es buena.
Excepciones aceptadas:

- Índices de loops: `i`, `j`.
- Variables dummy: `_` en Python.
- Nombres convencionales: `df` para DataFrame, `db` para conexión.

**Booleanos:** deben leerse como preguntas cuando se usan. Prefijos:
`is*`, `has*`, `should*`, `can*`, `did*`.

- Mal: `forecast`, `valid`, `active`.
- Bien: `isForecastReady`, `hasValidData`, `shouldRetrain`.

**Funciones:** nombre empieza con verbo. `calculateForecast()`,
`loadWellData()`, no `forecast()` ni `wellData()` (que suenan a nombres
de cosas).

**Plurales para colecciones:** `wells` (array) vs `well` (uno solo).
`forecastValues` (array de números) vs `forecastValue` (escalar).

**No abreviaturas inventadas:** `fcst` → `forecast`, `wl` → `well`,
`prod` → `production`. Excepción: abreviaturas estándar de la industria
o del dominio (`id`, `url`, `api`, `html`, `ml` si está en contexto claro).

---

## Consecuencias

**Positivas:**

- El repositorio se ve consistente independientemente de quién escriba.
- Los reviews de código no se pierden en discusiones de estilo.
- Herramientas automáticas (linters, formatters) pueden aplicar parte
  de estas reglas.
- Nuevos miembros (o el evaluador) pueden predecir dónde encontrar cosas.

**Negativas / trade-offs asumidos:**

- Overhead mental inicial mientras las reglas se internalizan.
- Algunas reglas pueden sentirse arbitrarias (¿por qué kebab-case para
  archivos generales pero PascalCase para componentes React?) — son
  convenciones heredadas del ecosistema, no invenciones nuestras.

**Neutras:**

- La mayoría de las reglas coinciden con las defaults de herramientas
  como Ruff (Python), ESLint + Prettier (TS), por lo que adoptarlas
  no requiere esfuerzo adicional si se configuran los linters.

## Aplicación y enforcement

- **Linters y formatters** (a configurar en Fase 1):
  - Python: [`ruff`](https://docs.astral.sh/ruff/) con reglas PEP 8.
  - TypeScript: `eslint` + `prettier` con preset estándar.
  - Markdown: `markdownlint` para ADRs y docs.
- **CI**: el pipeline de CI correrá los linters en cada PR. Un PR con
  errores de lint no puede mergearse.
- **Pre-commit hooks** (recomendado pero opcional): `pre-commit` con
  los mismos checks, para evitar pushear código que va a fallar en CI.

Las reglas que no puedan enforzarse automáticamente (ej: longitud de
nombres, booleanos como preguntas) quedan como responsabilidad del
revisor de PRs.

## Referencias

- [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html)
- [REST API Design Best Practices — Microsoft](https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design)
- ADR-0002 (Idioma del proyecto).
- ADR-0004 (Estrategia de branching).
- ADR-0005 (Convenciones de commits y PRs).
