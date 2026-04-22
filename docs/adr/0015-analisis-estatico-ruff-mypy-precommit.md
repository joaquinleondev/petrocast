# ADR-0015: Análisis estático de código — Ruff, mypy strict, markdownlint, yamllint y pre-commit

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica exige análisis estático como gate del pipeline de CI.
Necesitamos definir qué herramientas corren, con qué severidad, dónde corren
(local / CI / ambos) y qué pasa si fallan. Esta decisión cruza con
ADR-0005 (squash merge + Conventional Commits), ADR-0011 (workflows) y
ADR-0016 (testing).

El objetivo no es simplemente "tener linter", sino **evitar que bugs
triviales, bugs de tipos y documentación malformada lleguen a `main`**, sin
ralentizar excesivamente al equipo.

## Drivers de la decisión

- **Calidad sin fricción.** Con 3 personas y tiempo acotado, la barrera para
  "pasar el linter" debe ser baja localmente (pre-commit) para que no se
  acumulen errores hasta el CI.
- **Homogeneidad de estilo.** Evitar discusiones sobre formato; el formatter
  decide.
- **Type safety real.** Pydantic v2 y FastAPI ganan mucho con mypy strict;
  además mypy es el único que detecta categorías enteras de bugs que los
  tests no cubren siempre.
- **Documentación confiable.** Los ADRs y README son parte del entregable.
  Un markdownlint evita tablas rotas, links muertos por sintaxis y encabezados
  duplicados.
- **YAML de CI y Compose.** Son críticos; un error de indentación en
  `.github/workflows/*.yml` rompe todos los pipelines. yamllint ataja eso.
- **Velocidad.** El linter no puede costar más que los tests.

## Opciones consideradas

### Linter/formatter para Python

- **Ruff unificado (linter + formatter).**
- **Ruff (linter) + Black (formatter).**
- **Black + Flake8 + isort.**
- **Pylint + Black.**

### Type checking

- **mypy strict.**
- **mypy básico (solo errores, sin strict).**
- **Sin mypy.**

### Linting no-Python

- **markdownlint-cli2 + yamllint.**
- **Solo markdownlint.**
- **Ninguno.**

### Pre-commit hooks

- **Pre-commit hooks locales + CI.**
- **Solo en CI.**

## Decisión

- **Ruff unificado** para linting y formatting de Python. Configurado en
  `pyproject.toml`. Reglas seleccionadas incluyen al menos: `E`, `F`, `I`
  (imports), `N`, `UP`, `B`, `SIM`, `S` (security subset), `RUF`. Se permiten
  supresiones con comentario justificado.
- **mypy strict** sobre `apps/` y `packages/`. Los test fixtures y conftest
  pueden relajarse puntualmente vía `overrides` en `pyproject.toml`, no por
  archivo.
- **markdownlint-cli2** sobre `**/*.md` (incluido `docs/adr/`) y **yamllint**
  sobre `**/*.yml`/`**/*.yaml` (incluye `.github/workflows/`).
- **pre-commit** gestiona todos los hooks. El repo tiene un
  `.pre-commit-config.yaml` versionado. Los miembros del equipo **deben**
  instalar `pre-commit install` (documentado en el README).
- El **CI ejecuta los mismos hooks** vía `pre-commit run --all-files` como
  job obligatorio previo a los tests. Si el CI falla y local no, es señal de
  que alguien no instaló el hook o hizo `--no-verify`.

## Consecuencias

### Positivas

- Un único comando (`pre-commit run --all-files`) reproduce el análisis
  estático completo.
- Feedback inmediato al desarrollador (hook local) que reduce round-trips de
  PR → CI → fix.
- Ruff ofrece autocorrección en la mayoría de reglas; conflictos de estilo
  son cero.
- mypy strict cubre Pydantic v2 y FastAPI adecuadamente; las fallas tempranas
  se sienten como "el compilador te avisó".
- La configuración vive en `pyproject.toml` (Python) y archivos de
  configuración pequeños, reproducibles.

### Negativas

- mypy strict exige anotar todo; en Fase 1 hay un costo inicial de poner
  tipos en los mocks.
- Si alguien usa `git commit --no-verify` el valor de los hooks locales se
  pierde; se mitiga con el CI que igual corre todo.
- Ruff y mypy tienen updates frecuentes; hay que fijarlos en `pyproject.toml`
  y en `.pre-commit-config.yaml` con versiones concretas.

### Neutras

- `bandit` se evalúa no incluir porque Ruff ya cubre un subset relevante
  (`S`). Se reconsidera en Fase 2 si el contexto de seguridad lo exige.
- `hadolint` para Dockerfiles no se incluye en Fase 1 por costo/beneficio;
  pendiente de evaluación.

## Pros y contras de las opciones

### Linter/formatter Python

#### Ruff unificado

- **Pros:** Extremadamente rápido (Rust), reemplaza Flake8 + isort + varios
  plugins + Black; autofix; configuración única en `pyproject.toml`.
- **Contras:** Reglas aún en evolución; algún plugin de nicho puede faltar.

#### Ruff + Black

- **Pros:** Separación clásica entre linter y formatter; ambos son estándares.
- **Contras:** Duplicación sin beneficio real dado que Ruff formatea
  correctamente; dos herramientas que fijar en versiones.

#### Black + Flake8 + isort

- **Pros:** Ecosistema legendario.
- **Contras:** 3x más lento en CI que Ruff unificado; 3 configuraciones
  separadas.

#### Pylint

- **Pros:** Reglas muy profundas.
- **Contras:** Extremadamente lento; falsos positivos frecuentes; curva alta.

### Type checking

#### mypy strict

- **Pros:** Detecta bugs reales; valida que los tipos de Pydantic y los
  endpoints estén bien conectados; escala a Fase 3.
- **Contras:** Requiere anotar todo, incluyendo factories de tests.

#### mypy básico

- **Pros:** Poco costo.
- **Contras:** Deja pasar la mayoría de problemas (genéricos sin parámetros,
  `Any` implícitos).

#### Sin mypy

- **Pros:** Cero fricción.
- **Contras:** Pierde una capa importante de calidad; hace que mypy más
  tarde sea dolorosísimo de introducir.

### Lint no-Python

#### markdownlint + yamllint

- **Pros:** Previene errores en docs y en configs críticas de CI.
- **Contras:** Dos herramientas extra.

#### Solo markdownlint

- **Pros:** Menos ruido.
- **Contras:** Un typo en `.github/workflows/*.yml` rompe todo silenciosamente.

#### Ninguno

- **Pros:** Cero configuración.
- **Contras:** Deuda obvia.

### Pre-commit

#### Local + CI

- **Pros:** Feedback inmediato y garantía de CI.
- **Contras:** Los miembros del equipo deben recordar `pre-commit install`
  una vez.

#### Solo CI

- **Pros:** Setup cero.
- **Contras:** Round-trip mucho más lento; se commitea basura y se descubre
  en CI; gasto innecesario de minutos de GitHub Actions.

## Referencias

- ADR-0005 — Conventional Commits + squash merge.
- ADR-0011 — Workflows de GitHub Actions.
- ADR-0012 — Stack backend y `pyproject.toml`.
- ADR-0016 — Estrategia de testing.
- Ruff docs.
- mypy docs — strict mode.
- pre-commit framework.
- markdownlint-cli2.
- yamllint.
