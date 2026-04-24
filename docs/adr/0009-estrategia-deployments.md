# ADR-0009: Estrategia de deployment, rolling updates y rollback con Docker Swarm

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige:

1. Estrategias de despliegue de bajo riesgo, como rolling updates o canary
   deployments.
2. Recuperación automática si el despliegue falla.
3. Verificación automática de salud tras el despliegue.

ADR-0008 define tres ambientes separados:

```text
PR abierta   -> preview/dev efimero
merge main   -> staging persistente
tag v*       -> produccion persistente
```

Cada ambiente corre sobre una EC2 con Docker Swarm single-node. Debemos
definir cómo se actualizan los servicios, cómo se verifica que el deploy
funcionó y cómo se vuelve a la versión anterior si algo falla.

## Drivers de la decisión

- Requisito explícito de rolling updates o estrategia equivalente.
- Requisito explícito de rollback automático.
- Requisito explícito de health checks post-deploy.
- El PRD exige disponibilidad de la API.
- El equipo necesita una solución operable sin Kubernetes.
- La estrategia debe funcionar igual en staging y producción.
- Los previews por PR deben ser baratos y simples de crear/destruir.

## Opciones consideradas

### Estrategia de rollout

1. **Recreate**: apagar servicio viejo y prender servicio nuevo.
2. **Rolling update con Docker Swarm**.
3. **Blue-green**: dos stacks completos y switch de tráfico.
4. **Canary**: enviar una porción del tráfico a la versión nueva.

### Health checks

1. **Single endpoint** (`/health`) para todo.
2. **Tres niveles** (`/health/live`, `/health/ready`, `/health/deep`).
3. **Deep checks solamente**.

### Rollback

1. **Manual** tras detectar un problema.
2. **Automático por Swarm** si el servicio falla durante el update.
3. **Automático por pipeline** si los smoke tests fallan.
4. **Automático por métricas degradadas** (latencia/error rate).

## Decisión

Adoptamos **Docker Swarm rolling updates + rollback automático**, reforzado
con smoke tests desde GitHub Actions.

### Rollout por ambiente

**Preview/dev:**

- Cada PR crea un stack Swarm propio (`pr-<N>`).
- El servicio corre con 1 réplica.
- El update puede usar recreate o rolling simplificado porque el tráfico es
  solo del equipo.
- Al cerrar o mergear el PR, el pipeline ejecuta `docker stack rm pr-<N>`.

**Staging y producción:**

- Cada ambiente corre como stack Swarm persistente (`staging`, `prod`).
- El servicio `mock-api` corre con 2 réplicas.
- El update se realiza con `update_config`:
  - `parallelism: 1`
  - `order: start-first`
  - `failure_action: rollback`
  - `monitor: 30s`
  - `max_failure_ratio: 0`
- El stack declara un `healthcheck` a nivel de servicio contra
  `/health/ready`. No se define en el Dockerfile para poder variar la
  política por ambiente sin reconstruir la imagen.
- Si una réplica nueva no arranca, se cae o no supera el período de
  monitoreo, Swarm revierte automáticamente.

Configuración base:

```yaml
services:
  mock-api:
    image: ${IMAGE_URI}
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')",
        ]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        delay: 10s
        order: start-first
        failure_action: rollback
        monitor: 30s
        max_failure_ratio: 0
      rollback_config:
        parallelism: 1
        delay: 5s
        order: start-first
        monitor: 30s
        max_failure_ratio: 0
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 60s
```

Canary y blue-green quedan fuera de Fase 1 por complejidad operativa. Swarm
rolling update cubre el requisito con menor overhead.

### Health checks

Implementamos tres endpoints:

**1. `GET /health/live` — Liveness**

- Pregunta: ¿el proceso HTTP está vivo?
- Responde 200 con `{ "status": "alive" }`.
- No valida dependencias.
- No requiere API key.

**2. `GET /health/ready` — Readiness**

- Pregunta: ¿el servicio puede atender tráfico?
- Responde 200 con `{ "status": "ready", "checks": { ... } }` si está listo.
- En Fase 1 no hay base de datos real; en Fase 2 debe validar dependencias
  críticas.
- No requiere API key para permitir health checks de infraestructura.

**3. `GET /health/deep` — Deep / diagnóstico**

- Pregunta: ¿qué versión está corriendo y con qué estado interno?
- Devuelve versión, commit, uptime y checks informativos.
- Requiere API key porque puede exponer detalles operativos.

### Verificación post-deploy

Después de `docker stack deploy`, GitHub Actions ejecuta:

1. Esperar a que Swarm reporte el servicio actualizado.
2. Consultar `/health/ready` hasta obtener 200 OK.
3. Ejecutar smoke tests contra la URL pública del ambiente.
4. Verificar que la respuesta de `/health/deep` corresponda al commit o tag
   esperado.

Ejemplo conceptual:

```bash
curl -f https://staging.<dominio>/health/ready
curl -f -H "X-API-Key: $API_KEY" https://staging.<dominio>/health/deep
pytest tests/smoke
```

### Rollback automático en dos capas

**Capa 1 — Docker Swarm**

Swarm revierte automáticamente si el contenedor falla durante el rolling
update, no arranca o incumple la política de update.

**Capa 2 — Pipeline**

Si el servicio arranca pero falla un endpoint crítico, el workflow ejecuta:

```bash
docker service rollback <stack>_mock-api
```

Luego vuelve a consultar `/health/ready`. Si la versión anterior tampoco
queda healthy, el job falla y deja evidencia en GitHub Actions.

### Qué no cubre Fase 1

No hacemos rollback automático por métricas degradadas de producción (por
ejemplo, latencia p95 alta durante varios minutos). Eso requiere integrar
alertas y métricas con decisiones automáticas del pipeline, lo cual excede
Fase 1. Queda como mejora futura.

## Consecuencias

**Positivas:**

- Cumple rolling updates, health checks y rollback automático sin Kubernetes.
- Staging y producción tienen updates de bajo riesgo con dos réplicas.
- Los smoke tests cubren casos donde el proceso arranca pero la API no
  responde correctamente.
- El mismo patrón sirve para staging y producción.
- La estrategia es demostrable con comandos y configuración versionada.

**Negativas / trade-offs asumidos:**

- Dos réplicas duplican el consumo de recursos en staging y producción.
- Swarm single-node no protege contra caída física de la EC2.
- El rollback de pipeline requiere que GitHub Actions tenga permisos para
  ejecutar comandos remotos en la instancia.
- Los previews tienen menor robustez que staging/prod, pero es intencional:
  son efímeros y de bajo tráfico.

**Neutras:**

- El diseño puede evolucionar a Swarm multi-node, ECS o Kubernetes si el
  proyecto crece. Los conceptos de health, rolling update y smoke tests se
  mantienen.

## Pros y contras de cada opción

### Recreate

- ✅ Simple.
- ❌ Causa downtime.
- ❌ No cumple bien el requisito de bajo riesgo.

### Rolling update con Docker Swarm (elegida)

- ✅ Soporta rolling update y rollback nativos.
- ✅ Menor complejidad que Kubernetes.
- ✅ Compatible con Traefik y ECR.
- ✅ Configurable declarativamente en el stack.
- ❌ Menos popular que Kubernetes en producción moderna.

### Blue-green

- ✅ Rollback rápido por switch de tráfico.
- ❌ Duplica recursos por ambiente.
- ❌ Agrega complejidad de routing y naming.

### Canary

- ✅ Reduce blast radius ante bugs.
- ❌ Requiere métricas y decisión automatizada para saber si la canary va
  bien.
- ❌ Overkill para una mock API académica.

### Health checks de tres niveles (elegida)

- ✅ Semántica clara: vivo, listo, diagnóstico.
- ✅ Portable a Kubernetes si se migra.
- ✅ Evita reiniciar procesos por fallas transitorias de dependencias.
- ❌ Más endpoints que un mock mínimo.

## Referencias

- ADR-0008 (Topología de ambientes).
- ADR-0010 (Hosting en EC2 con Docker Swarm).
- ADR-0011 (GitHub Actions y despliegue remoto).
- ADR-0016 (Smoke tests).
- Docker Compose Deploy Specification — `update_config` y `rollback_config`.
- Docker Swarm — rolling updates.
- Adenda técnica de Fase 1.
