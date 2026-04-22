# ADR-0018: Gestión de configuración — Pydantic Settings + GitHub Secrets + `.env.example` versionado

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

El sistema tiene tres ambientes (dev, staging, prod) sobre una misma EC2
(ADR-0008, ADR-0010), cada uno con credenciales y parámetros distintos:
cadena de conexión a Postgres, API key interna, claves de servicios
externos en Fases 2/3, endpoints de observabilidad, etc. Necesitamos un
esquema consistente para:

1. Cómo la aplicación **lee** su configuración en runtime.
2. Dónde **viven los secrets** (fuente de verdad) y cómo llegan al
   contenedor.
3. Cómo un nuevo miembro del equipo **replica** el entorno local con rapidez.

## Drivers de la decisión

- **Type safety.** Queremos que un secret faltante o malformado falle en
  boot, no en producción después de la primera request.
- **Separación runtime/build.** Las imágenes Docker no deben contener
  secrets (ADR-0014); la configuración se inyecta en runtime.
- **Reproducibilidad local.** Un dev tiene que poder correr la app con
  `docker compose up` siguiendo el README en menos de 10 minutos.
- **Mínima superficie de riesgo.** Los secrets reales nunca van al repo ni
  a imágenes. Las claves pasan por canales auditables.
- **Costo.** No vamos a sumar un servicio gestionado de secrets si no hace
  falta; AWS Secrets Manager es útil, pero cobra por secret/mes.

## Opciones consideradas

### Cómo carga la app su configuración

- **Pydantic Settings (v2).**
- **`python-dotenv` + dataclass propia.**
- **`os.environ` directo.**

### Dónde viven los secrets

- **GitHub Secrets + `.env` materializado en la EC2 en runtime.**
- **AWS Secrets Manager.**
- **Env vars hardcoded en `docker-compose.yml` por ambiente.**

### `.env.example`

- **Versionado en el repo.**
- **No versionado; solo documentación en README.**

## Decisión

- **La app carga configuración con Pydantic Settings v2.** Una clase
  `Settings` en `apps/api/src/config.py` hereda de `BaseSettings`, con
  campos tipados, validators y `SettingsConfigDict(env_file=".env",
env_file_encoding="utf-8", extra="forbid", case_sensitive=False)`.
- **Origen de los secrets:** GitHub Secrets (a nivel de Environment para
  staging y prod, a nivel de repo para el resto). El workflow de deploy
  (ADR-0011) genera un `.env` en la EC2 con `envsubst` a partir de un
  template, y lo monta como archivo (no como variable de entorno) en el
  contenedor del backend, con permisos `600` y ownership `app:app`. Esto
  evita que el `.env` aparezca en `docker inspect` como variable.
- **`.env.example` versionado.** Contiene todas las variables esperadas, con
  valores de ejemplo (nunca reales) y un comentario por variable. Un test
  de CI verifica que todas las keys de `.env.example` existen en la clase
  `Settings` y viceversa.

Jerarquía de resolución (primer origen que exista gana):

1. Variables de entorno del proceso.
2. `/app/.env` montado desde el host.
3. Defaults en la clase `Settings` (solo valores no sensibles, por ej.
   `LOG_LEVEL=INFO`).

Las claves por ambiente siguen el patrón:

```text
# En GitHub Environments → staging
DATABASE_URL=postgresql+asyncpg://...
API_KEY=...
# En GitHub Environments → production
DATABASE_URL=postgresql+asyncpg://...
API_KEY=...
```

El contrato de API de Fase 1 usa una API key estática (`abcdef12345`)
documentada en el Addendum al PRD v0.2; en staging y prod esa key vive en
GitHub Secrets y se lee como `API_KEY_INTERNAL` en `Settings`.

## Consecuencias

### Positivas

- Una sola clase `Settings` es fuente de verdad del contrato de
  configuración: autodocumentada, tipada, validada al arranque.
- Los secrets nunca se embeben en la imagen Docker ni aparecen en `git
log`.
- El onboarding local es `cp .env.example .env` y pegar valores de dev.
- El CI valida la sincronización de `.env.example` y `Settings` en cada PR.
- La rotación de una credencial es un cambio en GitHub Secrets + redeploy.

### Negativas

- Hay que mantener cuidadosamente `.env.example` y la clase `Settings` en
  sincronía; mitigado con el test de CI.
- Los secrets en GitHub Secrets son **opacos para auditoría detallada**
  (quién los vio y cuándo); AWS Secrets Manager sí ofrece ese audit log.
  Para el TP es aceptable; para producción real se reevalúa.
- `envsubst` en el workflow puede fallar silenciosamente si falta una
  variable; mitigado con `set -euo pipefail` y `envsubst '$VAR1 $VAR2'`
  explícito (whitelist).

### Neutras

- Si en Fase 3 crece la cantidad de secrets o se suman integraciones
  sensibles, la migración a AWS Secrets Manager es directa (cambiar la
  fuente en el workflow sin tocar la app si el `.env` sigue siendo la
  interfaz).
- El backend puede leer también `settings` específicas de workers ARQ
  (heredando `Settings` y sumando campos) sin romper el diseño.

## Pros y contras de las opciones

### Carga de configuración

#### Pydantic Settings v2

- **Pros:** Tipado, validators, carga desde env y `.env`, integrado con el
  resto de Pydantic (que ya usamos por FastAPI); falla temprano.
- **Contras:** Dependencia adicional (ya la tenemos indirectamente).

#### `python-dotenv` + dataclass

- **Pros:** Simple.
- **Contras:** Sin validación real; `.env` se vuelve un formato frágil; hay
  que escribir el cast de tipos a mano.

#### `os.environ` directo

- **Pros:** Cero dependencias.
- **Contras:** KeyError tardío; nada de tipos; cero ergonomía.

### Fuente de secrets

#### GitHub Secrets + `.env` runtime

- **Pros:** Gratis, integrado con Actions; la materialización en archivo
  (no variable) evita filtraciones vía `docker inspect`.
- **Contras:** Audit logging limitado; límite de tamaño de secret (48 KB,
  no es un problema).

#### AWS Secrets Manager

- **Pros:** Audit log detallado, rotación automática, integración IAM.
- **Contras:** Costo por secret/mes; requiere SDK o sidecar en runtime;
  sobredimensionado para Fase 1.

#### Env vars hardcoded en `docker-compose.yml`

- **Pros:** Simplicidad máxima.
- **Contras:** Los secrets van al repo; inaceptable.

### `.env.example`

#### Versionado

- **Pros:** Onboarding rápido; fuente de verdad del contrato; validable en
  CI.
- **Contras:** Hay que recordar actualizarlo al agregar variables (mitigado
  con test de CI).

#### No versionado

- **Pros:** Menos archivos.
- **Contras:** Todos los devs reinventan su `.env`; errores silenciosos
  por variables faltantes.

## Referencias

- ADR-0008 — Entornos dev/staging/prod.
- ADR-0010 — EC2 + Docker Compose + Traefik.
- ADR-0011 — Workflows de GitHub Actions.
- ADR-0014 — Las imágenes no contienen secrets.
- ADR-0019 — Infraestructura con Terraform (no reemplaza secrets de
  aplicación, los complementa).
- Pydantic Settings docs.
- GitHub Environments & Secrets docs.
- Addendum al PRD v0.2 — API key estática de Fase 1.
