# Naming Cheatsheet

Consulta rápida. Detalles completos en [ADR-0006](./0006-naming-conventions.md).

## Archivos & carpetas generales

- `kebab-case.md`, `kebab-case/`
- ADRs: `NNNN-titulo-kebab-case.md`

## Python

- Archivos: `snake_case.py`
- Clases: `PascalCase`
- Funciones/vars: `snake_case`
- Constantes: `UPPER_SNAKE_CASE`
- Tests: `test_<modulo>.py`

## TypeScript / React

- Componentes: `PascalCase.tsx` → exporta `PascalCase`
- Hooks: `useCamelCase.ts`
- Utils/tipos: `kebab-case.ts`
- Funciones/vars: `camelCase`
- Tipos/interfaces: `PascalCase`
- Constantes: `UPPER_SNAKE_CASE`
- Tests: `<Nombre>.test.tsx`

## API REST

- Paths: `/kebab-case` en plural → `/wells`, `/forecasts`
- JSON fields: `camelCase` → `{ "wellId": "..." }`
- Query params: `camelCase` → `?horizonDays=90`
- Verbos HTTP, no en el path

## Base de datos

- Tablas: `snake_case` plural → `wells`, `forecast_runs`
- Columnas: `snake_case` → `well_id`, `created_at`
- FK: `<recurso>_id`
- Siempre: `created_at`, `updated_at`

## Branches

- `feat/descripcion-kebab`, `fix/...`, `docs/...`, `chore/...`

## Commits (inglés, imperativo)

- `feat(api): add forecast endpoint`
- `fix(dashboard): correct date parsing`
- `docs(adr): add ADR-0008 on deployment strategy`

## Env vars

- `UPPER_SNAKE_CASE` con prefijo de app
- `FORECAST_API_PORT`, `DATABASE_URL`
- Nunca commitear `.env`, siempre mantener `.env.example`

## Booleanos

- Leen como preguntas: `isReady`, `hasData`, `shouldRetrain`

## Evitar

- Espacios, acentos, mayúsculas inconsistentes en archivos
- Abreviaturas inventadas: `fcst` → `forecast`
- Verbos en paths REST: `/getForecast` → `GET /forecasts`
- Nombres de funciones sin verbo: `forecast()` → `calculateForecast()`
