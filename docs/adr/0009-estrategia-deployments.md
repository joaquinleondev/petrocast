# ADR-0009: Estrategia de deployment, health checks y rollback

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige:

1. "Estrategias de despliegue de bajo riesgo (p. ej., **rolling updates o
   canary deployments**)".
2. "**Recuperación automática** en caso que el [despliegue] falle".
3. "**Verificación automática de la salud** tras el despliegue".

Definida ya la topología de ambientes (ADR-0007), resta decidir:

- Cómo se actualizan los containers al recibir una nueva versión.
- Cómo se verifica que un deployment fue exitoso.
- Qué ocurre si el deployment falla.

## Drivers de la decisión

- Requisito explícito de la adenda de deploy "de bajo riesgo".
- Requisito explícito de health checks post-deploy.
- Requisito explícito de recuperación automática.
- El PRD exige disponibilidad del 99.5% de la API.
- Equipo pequeño: la solución debe ser operable sin conocimiento
  profundo de orquestadores complejos.

## Opciones consideradas

### Estrategia de rollout

1. **Recreate** (apagar viejo → prender nuevo): causa downtime.
2. **Rolling update** (reemplazo gradual manteniendo réplicas activas).
3. **Blue-green** (dos ambientes idénticos, switch de tráfico).
4. **Canary** (subset de tráfico a la nueva versión).

### Health checks

1. **Single endpoint** (`/health` genérico).
2. **Kubernetes-style** (liveness + readiness + startup).
3. **Deep checks** (verificación de dependencias: DB, cache, etc.).

### Rollback

1. **Manual** tras detectar problema.
2. **Automático** por health check fallido.
3. **Automático** por métricas degradadas (error rate, latency).

## Decisión

### Rollout: Rolling update con dos réplicas

**Para staging y producción:**

- Cada servicio corre con **2 réplicas mínimo** en Docker Compose
  (`deploy.replicas: 2`).
- Al deployar una nueva versión, se actualizan las réplicas **de a una**,
  esperando a que la nueva pase health check antes de actualizar la
  siguiente.
- Traefik enruta tráfico solo a réplicas healthy, por lo que los usuarios
  nunca reciben respuestas de una réplica en actualización.
- Downtime teórico: **cero**.

**Para preview environments (dev):**

- Una sola réplica por PR es suficiente (tráfico solo del equipo).
- Estrategia simplificada: _recreate_ aceptable.

Canary y blue-green se **descartan para Fase 1** por complejidad
desproporcionada. Se mencionan como futuras mejoras si se justifica
más adelante.

### Health checks: tres niveles estilo Kubernetes

Implementamos **tres endpoints** con semántica diferenciada:

**1. `GET /health/live` — Liveness**

- Pregunta: ¿el proceso está corriendo?
- Implementación: responde 200 con `{ "status": "alive" }` siempre que
  el servidor pueda responder HTTP.
- No verifica dependencias.
- Uso: Traefik / Docker lo consulta cada pocos segundos. Si falla
  repetidamente, el container se reinicia automáticamente.

**2. `GET /health/ready` — Readiness**

- Pregunta: ¿el proceso puede atender tráfico?
- Implementación: verifica que dependencias críticas respondan
  (conexión a BD activa, caché accesible, etc.). Responde 200 con
  `{ "status": "ready", "checks": { "database": "ok", ... } }` si
  todo OK, o 503 con el detalle de qué falló.
- Uso: Traefik consulta al iniciar un container y durante su vida. Si
  falla, el container se marca como "not ready" y **no recibe tráfico**
  hasta que vuelva a estar OK. No se reinicia.

**3. `GET /health/deep` — Deep / informational**

> Nota: ADR-0020 fija el path como `/health/deep` por simetría de prefijo.
> Este ADR originalmente lo llamaba `/health`; la semántica no cambia.

- Pregunta: ¿cuál es el estado detallado del sistema?
- Implementación: devuelve un JSON rico con versión, uptime, estado de
  dependencias, latencia a cada una, timestamp del último deploy.
- Uso: monitoreo humano, dashboards, debugging. No usado por
  orquestadores.
- **Este endpoint se reporta como el "health check" genérico hacia
  afuera** (ej: para uptime monitors).

**Ejemplo de response de `/health`:**

```json
{
  "status": "ok",
  "service": "predictiva-api",
  "version": "1.2.3",
  "commit": "a3f9b1c",
  "deployed_at": "2026-04-28T14:32:10Z",
  "uptime_seconds": 3600,
  "checks": {
    "database": { "status": "ok", "latency_ms": 4 },
    "forecast_engine": { "status": "ok", "version": "0.1.0-mock" }
  }
}
```

**Autenticación de health endpoints:** `/health/live` y `/health/ready`
**no requieren API key** (monitoreo interno). `/health/deep` **sí requiere
API key** (puede exponer información de infraestructura).

### Verificación post-deploy

El pipeline de CI/CD, tras pushear nuevos containers:

1. Espera a que los nuevos containers inicien (timeout configurable,
   default 60s).
2. Consulta `/health/ready` hasta obtener 200 OK, con timeout máximo de
   2 minutos.
3. Consulta `/health/deep` y verifica que `version` coincida con la versión
   esperada (evita servir containers cacheados o mal deployados).
4. Si cualquier paso falla, se dispara rollback automático.

### Rollback automático

**Para staging y producción:**

- El pipeline conserva la imagen Docker de la versión anterior hasta
  que la nueva pase todos los health checks.
- Si los health checks fallan, el pipeline:
  1. Restaura la imagen anterior en los containers.
  2. Verifica que la versión vieja vuelva a estar healthy.
  3. Falla el job con un mensaje explícito.
  4. Notifica al equipo (comentario en el PR, o Slack/Discord si se
     configura).

**El rollback automático se dispara por:**

- Health check fallido post-deploy.
- Containers que no logran arrancar (exit code != 0).

**No se dispara automáticamente por:**

- Métricas de producción degradadas post-deploy (error rate, latency).
  Esto requiere observabilidad integrada con el pipeline, fuera de
  alcance de Fase 1. Queda como rollback manual.

## Consecuencias

**Positivas:**

- Cumple los tres requisitos de la adenda (rolling, health, recuperación).
- Downtime efectivo cero en updates normales.
- Detección temprana de deploys rotos sin intervención humana.
- Patrón de health checks estándar de industria (Kubernetes-style),
  reutilizable en fases futuras si se migra a K8s.
- Trazabilidad: `/health` expone versión y commit exacto corriendo.

**Negativas / trade-offs asumidos:**

- Dos réplicas por servicio duplican consumo de recursos. En EC2
  pequeña, puede requerir upgrade de tipo de instancia.
- Implementar bien readiness (con dependencias reales) requiere
  disciplina de código: cada servicio debe saber verificar sus
  dependencias sin falsos positivos.
- Rollback por métricas queda fuera de alcance; un deploy que "parece
  healthy" pero degrada la experiencia no rollbackea solo.

**Neutras:**

- Los tres niveles de health pueden parecer overkill para una API
  simple. Son el estándar moderno y su implementación es trivial
  (~50 líneas de código). Vale la pena adoptarlos desde el día 1.

## Pros y contras de cada opción

### Rollout: Rolling update (elegida)

- ✅ Cero downtime con 2+ réplicas.
- ✅ Soportado nativo en Docker Swarm, Kubernetes, Traefik.
- ✅ Simple de razonar.
- ❌ Duplica recursos durante la transición.

### Rollout: Recreate

- ✅ Simple.
- ❌ Causa downtime. Incompatible con SLA de 99.5%.

### Rollout: Blue-green

- ✅ Rollback instantáneo (switch de vuelta).
- ❌ Duplica recursos permanentemente.
- ❌ Complejidad de routing.

### Rollout: Canary

- ✅ Mínimo blast radius ante un bug.
- ❌ Requiere observabilidad para decidir "¿la canary va bien?".
- ❌ Overkill para el volumen del TP.

### Health: Kubernetes-style (elegida)

- ✅ Semántica clara (liveness vs readiness vs deep).
- ✅ Permite a Traefik actuar correctamente (reiniciar vs no rutear).
- ✅ Portable a K8s sin cambios.

### Health: Single endpoint

- ✅ Más simple de implementar.
- ❌ Mezcla "¿estoy vivo?" con "¿puedo atender tráfico?". Lleva a
  loops de reinicio cuando la BD está lenta.

## Referencias

- ADR-0008 (Topología de ambientes).
- ADR-0010 (Plataforma de hosting — justifica Docker Compose).
- ADR-0011 (Plataforma de CI/CD — implementa las verificaciones).
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Traefik — Health Checks](https://doc.traefik.io/traefik/routing/services/#health-check)
- Adenda técnica de Fase 1 (requisitos citados).
