# ADR-0020: Estructura de Directorios del Backend

- **Estado:** Aceptado
- **Fecha:** 2026-04-22
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Drivers de la decisión

- Escalabilidad estructural hacia Fase 2 (ORM + migraciones) y Fase 3 (motor predictivo) sin refactoring destructivo.
- Testabilidad aislada: poder probar la lógica de negocio (services, domain) sin levantar HTTP ni mocks de base de datos.
- Separación de contratos HTTP (schemas Pydantic) del modelo de datos persistente (ORM SQLAlchemy), que divergirán en Fase 2.
- Versionado de API: soporte para `/api/v1/` y eventual `/api/v2/` sin duplicar lógica de negocio.
- Alineación con ADR-0009 (health checks), ADR-0016 (pirámide de tests: unit + integration), ADR-0018 (Pydantic Settings).

## Opciones consideradas

1. **Estructura plana extendida** — agregar archivos al `app/` actual (`app/wells.py`, `app/forecast.py`, etc.).
2. **Estructura por feature** — un paquete por dominio (`app/wells/`, `app/forecast/`) con todo dentro.
3. **Estructura por capa (layered)** — paquetes separados para `api/`, `services/`, `repositories/`, `schemas/`, `core/`.

## Decisión

Elegimos **Estructura por capa (Opción 3)** porque alinea los límites de responsabilidad con los saltos de complejidad de cada fase: en Fase 2 solo cambia `repositories/` (de mock a SQLAlchemy); en Fase 3 solo cambia `services/` y se agrega `domain/`. El resto del código no se toca.

La estructura adoptada es:

```
apps/api/
├── src/
│   ├── main.py                        # Crear FastAPI, montar routers
│   ├── core/
│   │   ├── config.py                  # Pydantic Settings (ADR-0018)
│   │   └── security.py                # verify_api_key
│   ├── api/
│   │   ├── deps.py                    # Dependencias compartidas (auth, db, paginación)
│   │   └── v1/
│   │       ├── router.py              # APIRouter raíz con prefijo /api/v1
│   │       └── endpoints/
│   │           ├── wells.py
│   │           ├── forecast.py
│   │           └── health.py          # /health/{live,ready,deep}
│   ├── schemas/
│   │   ├── base.py                    # BaseSchema con alias_generator (ADR-0007)
│   │   ├── well.py                    # DTOs HTTP de pozos
│   │   └── forecast.py                # DTOs HTTP de pronóstico
│   ├── repositories/
│   │   ├── well_repository.py         # Fase 1: datos en memoria; Fase 2: SQLAlchemy
│   │   └── forecast_repository.py     # Fase 1: cálculo Arps mock; Fase 3: motor real
│   └── services/
│       ├── well_service.py            # Orquesta repositorio de pozos
│       └── forecast_service.py        # Orquesta repositorio + dominio (Fase 3)
└── tests/
    ├── conftest.py                    # Fixtures compartidos: client, auth_headers
    ├── unit/
    │   └── services/                  # Tests de servicios sin HTTP
    ├── integration/
    │   └── api/v1/                    # Tests de endpoints con TestClient
    ├── contract/                      # schemathesis vs OpenAPI (ADR-0016)
    └── smoke/                         # Checks post-deploy contra URL real
```

**Flujo de una request:**

```
HTTP request
  → api/v1/endpoints/{recurso}.py   (validación HTTP, códigos de error)
    → services/{recurso}_service.py  (lógica de negocio, orquestación)
      → repositories/{recurso}_repository.py  (acceso a datos)
        → schemas/{recurso}.py       (DTOs de retorno)
```

**Capas que se agregan por fase:**

| Fase | Capa nueva                                               | Capa que cambia                              |
| ---- | -------------------------------------------------------- | -------------------------------------------- |
| 2    | `models/` (SQLAlchemy ORM), `db/` (session + migrations) | `repositories/` (mock → DB query)            |
| 3    | `domain/` (Arps, Forecaster ABC)                         | `services/forecast_service.py` (llama motor) |

**Health endpoints (convención Fase 1):** `/health/{live,ready,deep}` — reemplaza la terna `{live,ready,<root>}` descrita en ADR-0009. La semántica se mantiene (liveness sin deps, readiness con deps, deep con JSON rico + API key), solo cambia el path del último a `/health/deep` por simetría de prefijo.

## Consecuencias

**Positivas:**

- `repositories/` actúa como seam: swap mock → PostgreSQL sin tocar endpoints ni services.
- Tests unitarios de `services/` y `domain/` no requieren HTTP ni fixtures de base de datos.
- Endpoints flacos (solo HTTP concerns): validación de parámetros, códigos de estado, serialización.
- `api/v1/` permite agregar `api/v2/` con routing independiente sin duplicar lógica.
- `core/` centraliza configuración y seguridad; `deps.py` centraliza dependencias FastAPI inyectables.
- Health endpoints `/health/{live,ready,deep}` integrados desde Fase 1 (requerimiento ADR-0009).

**Negativas / trade-offs asumidos:**

- Más archivos y directorios para un mock de dos endpoints. Overhead justificado por las fases siguientes.
- Para features simples, el desarrollador debe navegar 4 capas en lugar de editar un solo archivo.

**Neutras:**

- `schemas/` y `models/` (ORM) son paquetes distintos desde el inicio, aunque en Fase 1 no hay ORM. Prepara la separación sin imponer trabajo prematuro.
- `python-dotenv` reemplazado por `pydantic-settings` en `core/config.py`, alineando con ADR-0018.

## Pros y contras de cada opción

### Opción 1 — Estructura plana extendida

- ✅ Mínimo overhead inmediato.
- ❌ Sin seam entre HTTP y datos: en Fase 2, agregar DB requiere modificar los mismos archivos de endpoints.
- ❌ Imposible testear lógica de negocio sin levantar HTTP.
- ❌ Schemas HTTP y modelos ORM colisionan en el mismo espacio de nombres.

### Opción 2 — Estructura por feature

- ✅ Alta cohesión dentro de cada feature.
- ❌ Lógica transversal (auth, config, DB session) se duplica o requiere un paquete `shared/` extra.
- ❌ En oil & gas con pocas entidades pero lógica predictiva compleja, la separación por feature no sigue los límites de cambio reales (el motor Arps afecta a todos los pozos).

### Opción 3 — Estructura por capa ✅ Elegida

- ✅ Los límites de capa coinciden con los límites de cambio por fase.
- ✅ Patrón estándar en proyectos FastAPI de producción; curva de aprendizaje baja.
- ✅ `conftest.py` compartido reduce duplicación en fixtures de tests.
- ❌ Más boilerplate inicial para un MVP de dos endpoints.

## Referencias

- [FastAPI — Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html) — Martin Fowler
- ADR-0009: Estrategia de deployments (health checks)
- ADR-0012: Stack backend Python + FastAPI + uv
- ADR-0016: Estrategia de testing pytest + schemathesis
- ADR-0018: Gestión de configuración con Pydantic Settings
