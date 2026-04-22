# ADR-0012: Stack tecnológico del backend — Python 3.12 + FastAPI + uv + PostgreSQL 16

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La Fase 1 exige un servicio HTTP que exponga el contrato OpenAPI descrito en
la adenda técnica y soporte un despliegue completo a dev/staging/prod. La
Fase 3 integrará un motor de ML (Arps Decline Curve Analysis como baseline +
modelos más elaborados). Entre ambas Fases el stack no debería cambiar, o la
deuda acumulada será enorme.

Necesitamos decidir, de una sola pasada, **lenguaje + framework + gestor de
dependencias + versión + motor de base de datos**, porque estas decisiones son
fuertemente interdependientes (por ejemplo, SQLAlchemy se beneficia de
tipados modernos de Python 3.12; `uv` requiere `pyproject.toml` y cambia el
Dockerfile completo).

## Drivers de la decisión

- **Continuidad con Fase 3.** El ecosistema de ML de Python (scikit-learn,
  statsmodels, pandas, PyTorch si hiciera falta) no tiene equivalente
  competitivo en otros lenguajes dentro del tiempo disponible.
- **Experiencia del equipo.** Al menos un miembro tiene experiencia concreta
  con FastAPI y ARQ; los otros dos tienen base en Python académico. Bajar el
  riesgo de curva de aprendizaje es prioritario.
- **Calidad del contrato OpenAPI.** FastAPI genera OpenAPI a partir del
  código, lo cual es el orden correcto para alinearse con el contrato de la
  adenda sin mantener dos fuentes de verdad.
- **Velocidad del ciclo de desarrollo.** Con un TP de 3 meses y 3 entregas,
  el tiempo de `pip install` durante CI importa.
- **Ergonomía de tipos.** mypy strict (ADR-0015) y Pydantic v2 dependen de
  features de tipos recientes.
- **Estabilidad operacional.** Necesitamos una versión de Python que tenga
  soporte de seguridad vigente durante todo el TP y bibliotecas maduras.

## Opciones consideradas

### Lenguaje y framework

- **Python + FastAPI.**
- **Python + Flask.**
- **Node.js + NestJS / Express.**
- **Go + Fiber / chi.**

### Gestor de dependencias de Python

- **`uv` (Astral).**
- **Poetry.**
- **`pip` + `pip-tools` + `requirements.txt`.**

### Versión de Python

- **Python 3.12.**
- **Python 3.11.**
- **Python 3.13.**

### Motor de base de datos

- **PostgreSQL 16.**
- **PostgreSQL 15 LTS.**
- **SQLite (solo Fase 1).**
- **Sin BD en Fase 1.**

## Decisión

- **Lenguaje y framework:** Python 3.12 + FastAPI.
- **Gestor de dependencias:** `uv`, con `pyproject.toml` como fuente única y
  `uv.lock` commiteado al repo.
- **Base de datos:** PostgreSQL 16.

FastAPI cumple con los drivers (OpenAPI nativo, tipado fuerte, rendimiento
adecuado, comunidad grande, integración natural con Pydantic v2 y
SQLAlchemy 2.x). `uv` acelera drásticamente instalación y resolución en CI y
encaja con el Dockerfile multi-stage (ADR-0014). Python 3.12 es estable,
tiene performance mejorada respecto a 3.11 y no carga con la inmadurez
relativa de 3.13 en bibliotecas de terceros. PostgreSQL 16 ofrece
mejoras de performance y logical replication útiles si Fase 2/3 necesitan
réplicas, y los drivers principales (`asyncpg`, `psycopg3`) lo soportan sin
problemas.

## Consecuencias

### Positivas

- OpenAPI generado por FastAPI contrastable automáticamente contra el
  contrato de la adenda (ver ADR-0007 y ADR-0016).
- `uv` reduce el tiempo de build de CI/CD notablemente (orden de magnitud
  respecto a `pip install`).
- Python 3.12 habilita `type` statements, mejoras de performance y `f-string`
  más potentes.
- PostgreSQL 16 ofrece compatibilidad completa con el ORM y herramientas de
  migración (Alembic).
- Bajo riesgo de rotación tecnológica entre Fase 1 y Fase 3: todo el stack
  persiste.

### Negativas

- `uv` es relativamente nuevo (aunque estable en 2026); si aparece un bug
  bloqueante tenemos que rollbackear a Poetry o `pip-tools`. Mitigado con
  `uv.lock` determinístico.
- Python 3.12 en imagen `slim` requiere instalar build deps en la stage de
  build del Dockerfile (gcc, libpq-dev). No es bloqueante pero sí paso
  obligado.
- PostgreSQL 16 agrega carga operacional vs. SQLite en Fase 1 (hay que
  gestionar un contenedor más). Se considera aceptable por los beneficios a
  largo plazo.

### Neutras

- La versión 3.12 quedará "vieja" eventualmente; se asume que Fase 2/3
  permanecerá en 3.12 salvo que haya una razón explícita para subir.
- Elegir FastAPI condiciona el estilo de la app (async-first, dependency
  injection vía `Depends`) que el equipo tendrá que aprender bien.

## Pros y contras de las opciones

### Lenguaje y framework

#### Python + FastAPI

- **Pros:** OpenAPI nativo, tipado, Pydantic, comunidad, continuidad con ML.
- **Contras:** Async exige disciplina; I/O bloqueante en handlers async es
  una trampa común.

#### Python + Flask

- **Pros:** Simplicidad y familiaridad.
- **Contras:** OpenAPI no es nativo; hay que sumar `flask-smorest` o similar;
  menos idiomático con Pydantic v2.

#### Node.js + NestJS

- **Pros:** Ecosistema JS, buena ergonomía con TypeScript.
- **Contras:** Romper continuidad con Fase 3 (ML); curva de TypeScript para
  quienes no vienen del frontend.

#### Go

- **Pros:** Binarios estáticos, performance, concurrencia.
- **Contras:** El equipo no lo domina; sin ecosistema ML comparable para
  Fase 3; mayor costo de aprendizaje en plazos ajustados.

### Gestor de dependencias

#### `uv`

- **Pros:** Muy rápido (Rust), resuelve lockfile determinístico, integra con
  `pyproject.toml`, soporta scripts.
- **Contras:** Proyecto relativamente joven; menor rodaje que Poetry aunque
  en 2025-2026 ya es estándar de facto emergente.

#### Poetry

- **Pros:** Maduro, amplio rodaje, lockfile confiable.
- **Contras:** Más lento que `uv`; su modelo de "virtual environments
  in-project" a veces complica Docker.

#### `pip` + `pip-tools`

- **Pros:** Conocido por cualquier dev Python.
- **Contras:** Resolución más lenta, sin lockfile nativo; scripts y tareas
  dependen de `Makefile` externo.

### Versión de Python

#### 3.12

- **Pros:** Estable, performance mejorada, soporte de seguridad durante todo
  el TP, bibliotecas maduras.
- **Contras:** No es la más reciente.

#### 3.11

- **Pros:** Aún más rodaje.
- **Contras:** Perderíamos mejoras de performance y tipo de 3.12.

#### 3.13

- **Pros:** Últimas features (GIL opcional).
- **Contras:** Algunas bibliotecas (por ejemplo ciertos stacks de data
  science) pueden no soportarlo aún sin parches.

### Base de datos

#### PostgreSQL 16

- **Pros:** Features modernas, drivers actualizados, suficiente cabeza para
  Fase 3 (JSONB, particionado, extensiones geo/serie temporal).
- **Contras:** Una versión más nueva implica ligeramente menos rodaje que 15
  LTS.

#### PostgreSQL 15 LTS

- **Pros:** Mayor base instalada, más guías y soluciones en foros.
- **Contras:** Ganancias marginales en estabilidad para un TP.

#### SQLite

- **Pros:** Cero ops, perfecto para Fase 1.
- **Contras:** Hay que migrar a PostgreSQL en algún momento; SQL dialects
  divergen; concurrencia limitada.

#### Sin BD

- **Pros:** Simplifica Fase 1 al máximo.
- **Contras:** Posterga deuda y dificulta una demo realista; ciertos mocks
  del API pueden requerir estado.

## Referencias

- ADR-0007 — Alineación con el contrato OpenAPI.
- ADR-0014 — Estructura de imágenes Docker.
- ADR-0015 — Análisis estático (Ruff + mypy).
- ADR-0016 — Estrategia de testing.
- ADR-0018 — Gestión de configuración (Pydantic Settings).
- ADR-0019 — Infraestructura con Terraform.
- FastAPI docs.
- Astral `uv` announcement & docs.
- PostgreSQL 16 release notes.
