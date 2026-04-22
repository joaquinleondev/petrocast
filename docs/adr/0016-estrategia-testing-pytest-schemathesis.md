# ADR-0016: Estrategia de testing — pytest con unit/integration/contract/smoke y coverage ≥70%

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige que el CI ejecute tests automatizados y
bloquee el despliegue si fallan. La materia (Ingeniería de Software I) cubre
explícitamente la pirámide de tests y conceptos de contract testing, smoke
testing y coverage. El proyecto debe, por lo tanto, tener una estrategia
explícita que cubra el temario **y** aporte valor real al producto.

La decisión abarca:

1. Qué **framework** de tests se usa.
2. Qué **tipos** de test se implementan en Fase 1.
3. Qué **coverage mínimo** exigimos y si bloquea el CI.
4. Cómo se hace **contract testing** contra el OpenAPI de la adenda.

## Drivers de la decisión

- **Cobertura pedagógica.** La materia pide demostrar los cuatro niveles
  (unit, integration, contract, smoke) y el TP es el espacio natural para
  hacerlo.
- **Valor real.** El contract testing, en particular, protege el contrato de
  la adenda contra regresiones silenciosas.
- **Velocidad del CI.** Los tests deben correr en minutos, no decenas de
  minutos, para no ralentizar los merges.
- **Reproducibilidad.** Los tests de integración deben levantar dependencias
  (Postgres, workers) de forma determinística, sin asumir estado en la
  máquina del dev.
- **Feedback en producción.** Los smoke tests corren post-deploy contra el
  entorno real (ADR-0009, readiness + deep) como prueba final de que la
  versión nueva está sana.

## Opciones consideradas

### Framework

- **pytest.**
- **unittest (stdlib).**

### Tipos de tests en Fase 1

- **Unit + Integration + Contract + Smoke.**
- **Unit + Integration.**
- **Solo Unit.**

### Coverage

- **≥70 % obligatorio (falla CI).**
- **≥80 % obligatorio (falla CI).**
- **Informativo (reporte pero no falla).**
- **Sin tracking.**

### Contract testing

- **schemathesis automatizado en CI.**
- **Manual con Postman / Bruno / Insomnia.**
- **Solo tests unitarios sobre los schemas.**

## Decisión

- **Framework:** `pytest`, con plugins `pytest-cov`, `pytest-asyncio`,
  `pytest-httpx` (o `respx`) para mockear llamadas HTTP salientes,
  `pytest-postgresql` o `testcontainers-python` para la BD de tests.
- **Tipos de tests:** Unit, Integration, Contract y Smoke (los cuatro).
- **Coverage:** mínimo **70 %** global sobre `apps/api/src` y
  `packages/core`, **bloqueante** en CI. Los `tests/`, `alembic/`, `migrations/`
  se excluyen. Configuración en `pyproject.toml`.
- **Contract testing:** `schemathesis run` contra el OpenAPI generado por la
  app, ejecutado como job de CI independiente. Adicionalmente, `pytest` con
  `schemathesis` como fixture permite integrar los contract tests en la suite
  principal cuando convenga.
- **Smoke tests:** son un set corto (~5-10 checks) que se ejecutan contra la
  URL real después del deploy, como parte del workflow (ADR-0011). Golpean
  `/health/live`, `/health/ready`, `/health/deep`, y dos endpoints
  representativos del contrato.

Estructura del repo:

```text
apps/api/tests/
  unit/              # funciones puras, validadores, utilidades
  integration/       # handlers FastAPI con TestClient y BD real
  contract/          # schemathesis
  smoke/             # corren contra URL remota, NO contra TestClient
```

## Consecuencias

### Positivas

- Los cuatro niveles están cubiertos, alineados con el temario de la materia.
- `schemathesis` detecta divergencias entre el OpenAPI declarado y el
  comportamiento real del servidor (valores fuera de rango, tipos mal,
  campos faltantes, status codes inesperados).
- El bloqueo por coverage obliga a no mergear código sin tests, sin ser tan
  agresivo como para paralizar al equipo.
- Los smoke tests post-deploy son la última línea de defensa antes de marcar
  el rollout como exitoso.

### Negativas

- `schemathesis` añade tiempo al CI (minutos) y puede generar flakiness si
  el OpenAPI tiene regex ambiguas; se mitiga con `--hypothesis-seed` fijo
  cuando sea necesario.
- El coverage ≥70 % bloqueante puede frenar PRs exploratorios; se acepta
  como trade-off consciente.
- Mantener fixtures consistentes entre unit e integration exige disciplina.

### Neutras

- Se evalúa subir a 80 % después de Fase 1 cuando la base de código sea
  más estable.
- `hypothesis` (property-based testing) está disponible a través de
  `schemathesis`; su uso explícito en unit tests queda como opcional.

## Pros y contras de las opciones

### Framework

#### pytest

- **Pros:** Estándar de facto; fixtures expresivas; plugins abundantes;
  excelente integración con `pytest-cov` y FastAPI.
- **Contras:** Magia implícita (collection, fixtures) puede sorprender a
  gente nueva.

#### unittest

- **Pros:** Incluido en la stdlib; sin dependencias.
- **Contras:** Boilerplate; sin fixtures parametrizadas cómodas; ecosistema
  de plugins minúsculo en comparación.

### Tipos de tests

#### Los cuatro

- **Pros:** Cubre pirámide completa; cubre la bibliografía de la materia;
  valor real en cada nivel.
- **Contras:** Más trabajo inicial; hay que justificar cada nivel.

#### Unit + Integration

- **Pros:** Más rápido de implementar.
- **Contras:** Pierde la garantía de contrato y la señal post-deploy.

#### Solo Unit

- **Pros:** Mínimo esfuerzo.
- **Contras:** No detecta problemas de wiring; falso sentido de seguridad.

### Coverage

#### ≥70 % bloqueante

- **Pros:** Exige tests sin ser punitivo; realista para 3 personas.
- **Contras:** Algún PR urgente podría verse obligado a sumar tests "de
  relleno".

#### ≥80 % bloqueante

- **Pros:** Mayor exigencia.
- **Contras:** A menudo se llena con tests de getters/setters sin valor.

#### Informativo

- **Pros:** Cero fricción.
- **Contras:** Sin consecuencia, la métrica se ignora.

#### Sin tracking

- **Pros:** Cero configuración.
- **Contras:** Imposible saber si los tests cubren algo nuevo.

### Contract testing

#### schemathesis automatizado

- **Pros:** Property-based sobre el OpenAPI real; encuentra casos que nadie
  imagina; gratis después de la configuración inicial.
- **Contras:** Latencia extra en CI; requiere seed fijo para ser
  determinístico.

#### Manual con Postman/Bruno

- **Pros:** Útil como parte de la demo.
- **Contras:** No es automatizado; no corre en CI; se desincroniza rápido
  con el código.

#### Solo tests unitarios sobre schemas

- **Pros:** Simple.
- **Contras:** No valida integraciones ni comportamiento real del servidor.

## Referencias

- ADR-0007 — Alineación con contrato OpenAPI.
- ADR-0009 — Health checks y readiness.
- ADR-0011 — Workflows de GitHub Actions.
- ADR-0012 — Stack backend.
- ADR-0015 — Análisis estático.
- pytest docs.
- schemathesis docs.
- FastAPI docs — TestClient and testing.
- testcontainers-python.
