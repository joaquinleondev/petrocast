# ADR-0014: Estructura de imágenes Docker — `python:3.12-slim`, multi-stage, usuario no-root

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica pide que todo corra en contenedores Docker y exige
imágenes auditables, seguras y reproducibles. El backend es Python 3.12 +
FastAPI gestionado con `uv` (ADR-0012). Necesitamos fijar:

1. Qué **imagen base** se usa.
2. Si el Dockerfile es **single-stage o multi-stage**.
3. Con qué **usuario** corre el proceso dentro del container.

Estas decisiones impactan tamaño de la imagen, tiempos de build de CI,
superficie de ataque, tiempo de pull en despliegue y compatibilidad con las
rolling updates (ADR-0009) y los health checks.

## Drivers de la decisión

- **Tamaño y tiempo de pull.** Durante rolling updates (ADR-0009) la EC2 baja
  la imagen nueva antes de reemplazar la réplica vieja; una imagen más chica
  = rollouts más rápidos y menor riesgo de exceder timeouts del health check.
- **Seguridad por default.** Los scanners (ECR scan on push, ver ADR-0013)
  son más silenciosos sobre una imagen mínima; un usuario no-root limita el
  blast radius de una RCE.
- **Velocidad del build en CI.** Multi-stage permite cachear la capa de
  dependencias y reconstruir solo la capa de código en cada push.
- **Compatibilidad con bibliotecas de ML.** En Fase 3 vendrán scikit-learn,
  numpy, statsmodels. Estas dependen de bibliotecas del sistema (`libopenblas`,
  `libgomp`). Queremos una base donde eso se instale sin drama.
- **Reproducibilidad.** La imagen debe poder construirse idénticamente en
  CI y en la laptop de cualquier miembro del equipo.

## Opciones consideradas

### Imagen base

- **`python:3.12-slim` (Debian slim).**
- **`python:3.12-alpine`.**
- **`python:3.12` completa.**
- **`gcr.io/distroless/python3-debian12`.**

### Estrategia de build

- **Multi-stage: `builder` (compila deps) + `runtime` (mínimo).**
- **Single stage.**

### Usuario

- **No-root (UID fijo, p. ej. 10001).**
- **Root.**

## Decisión

- **Imagen base:** `python:3.12-slim-bookworm`.
- **Estrategia:** Dockerfile multi-stage con al menos dos stages (`builder`,
  `runtime`). El `builder` instala dependencias con `uv sync --frozen` y
  genera un venv en `/opt/venv`; el `runtime` copia solo el venv y el código.
- **Usuario:** `app` (UID `10001`, GID `10001`) creado en el Dockerfile. El
  filesystem de la app es propiedad del usuario `app`; el proceso arranca
  con `USER 10001`.

Fijamos además:

- `PYTHONDONTWRITEBYTECODE=1` y `PYTHONUNBUFFERED=1`.
- `PIP_NO_CACHE_DIR=1` y `UV_COMPILE_BYTECODE=1`.
- `HEALTHCHECK` **no se declara en el Dockerfile**: se declara a nivel de
  servicio Swarm/Compose para poder ajustar intervalos, timeouts y endpoints
  por ambiente sin reconstruir la imagen, manteniendo el contrato de
  liveness/readiness/deep definido en ADR-0009.
- `.dockerignore` exhaustivo (`.git`, `.venv`, `__pycache__`, `tests`,
  `docs`, `.env*`, `*.md` salvo los que la imagen necesite).
- Las imágenes se etiquetan con labels OCI estándar (`org.opencontainers.
image.source`, `revision`, `created`, `version`).

## Consecuencias

### Positivas

- La imagen `runtime` final queda bajo ~200 MB (orden de magnitud) vs.
  ~1 GB si usáramos la base completa.
- Un CVE en build-deps (gcc, headers) no afecta la imagen de producción: esas
  dependencias viven solo en el stage `builder`.
- Un proceso comprometido corre como UID no privilegiado y no puede escribir
  en `/usr` ni escalar fácilmente dentro del container.
- Compatibilidad comprobada con `numpy`, `scikit-learn` y `psycopg` en
  `slim-bookworm`; no hay sorpresas de `musl` vs `glibc` (problema típico de
  Alpine con ruedas precompiladas de ciencia de datos).
- Capa de dependencias cacheable: CI reconstruye solo si cambia
  `pyproject.toml` o `uv.lock`.

### Negativas

- El Dockerfile es más largo que un single-stage y exige disciplina para
  mantenerlo.
- Algunas bibliotecas que escriben en `/tmp` o `/app` necesitan permisos
  explícitos si se corre read-only; documentado en el Dockerfile.
- El UID fijo puede chocar con volúmenes bind-mounteados en desarrollo local
  si hay diferencias con el UID del host; se mitiga usando volúmenes
  nombrados o `userns-remap` cuando aplique.

### Neutras

- Distroless queda como alternativa futura para producción cuando el stack
  sea 100 % estable.
- Se evalúa activar filesystem read-only en los servicios Swarm de producción
  en una fase posterior.

## Pros y contras de las opciones

### Imagen base

#### `python:3.12-slim-bookworm`

- **Pros:** Balance tamaño/compatibilidad; `apt` disponible; `glibc`; ruedas
  manylinux2014 instalan sin recompilar.
- **Contras:** No es la más chica posible.

#### `python:3.12-alpine`

- **Pros:** Muy pequeña (~50 MB base).
- **Contras:** `musl` libc rompe o ralentiza ruedas precompiladas de
  `numpy`/`scipy`/`pandas`; frecuentemente toca compilar desde fuente.
  Mal trade-off para Fase 3.

#### `python:3.12` completa

- **Pros:** Todo out-of-the-box.
- **Contras:** ~1 GB; CVEs innecesarios; rolling updates más lentos.

#### Distroless

- **Pros:** Mínima superficie de ataque.
- **Contras:** Sin shell ni `apt`; debuggear en producción se vuelve
  complicado; complica el arranque de entry points con dependencias
  dinámicas. Demasiado agresivo para Fase 1.

### Estrategia de build

#### Multi-stage

- **Pros:** Imagen final mínima; build deps no se llevan a producción; capas
  cacheables.
- **Contras:** Dockerfile más largo; requiere entender el modelo de stages.

#### Single stage

- **Pros:** Dockerfile más simple.
- **Contras:** gcc, headers y toolchain persisten en producción; CVEs
  superfluos; imagen más pesada.

### Usuario

#### No-root

- **Pros:** Menor blast radius ante RCE; cumple checklists de hardening;
  compatible con Traefik y Docker Swarm.
- **Contras:** Requiere `chown` y planificar dónde escribe la app.

#### Root

- **Pros:** Cero configuración.
- **Contras:** Malas prácticas; visible en scanners; se corrige en algún
  momento, mejor ahora.

## Referencias

- ADR-0009 — Rolling updates y health checks.
- ADR-0010 — AWS EC2 + Docker Swarm + Traefik.
- ADR-0012 — Stack backend y uso de `uv`.
- ADR-0013 — Publicación de imágenes en ECR.
- Docker docs — multi-stage builds, `.dockerignore`, labels OCI.
- `uv` docs — `uv sync`, `UV_COMPILE_BYTECODE`.
- OWASP Docker Security Cheat Sheet.
