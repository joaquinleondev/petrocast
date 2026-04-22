# ADR-0017: Observabilidad — Prometheus + Grafana + Loki + structlog + alertas a Discord

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige un dashboard de monitoreo que cubra al
menos: latencia del API, disponibilidad del servicio, recursos (CPU, memoria,
disco) y frecuencia de uso del API. También se pide demostrar que el
despliegue es observable en tiempo real durante la defensa.

Tenemos que decidir:

1. Qué **stack de métricas y visualización** usamos.
2. Qué **formato de logs** produce la app y cómo los centralizamos.
3. Adónde van las **alertas** cuando algo se rompe.

Esto interactúa con ADR-0009 (health checks) y ADR-0010 (EC2 + Docker
Compose): todo el stack de observabilidad vive en la misma EC2 como
contenedores adicionales.

## Drivers de la decisión

- **Costo operacional.** Los créditos AWS cubren la infra de cómputo pero
  preferimos no depender de un SaaS pago. Un stack self-hosted en la misma
  EC2 es gratis.
- **Corresponde al temario.** La materia espera ver Prometheus + Grafana como
  soluciones de referencia; self-hostearlos es pedagógicamente valioso.
- **Propiedad de los datos.** Logs y métricas del sistema deben quedar en el
  perímetro del equipo, no en un SaaS de terceros con retención limitada.
- **Debug bajo presión.** Cuando algo falla en la defensa, necesitamos poder
  correlacionar métricas, logs y trazas sin abrir tres consolas distintas.
- **Footprint.** La EC2 es `t3.small` (2 GiB). El stack no puede consumir
  toda la memoria.

## Opciones consideradas

### Stack de observabilidad

- **Prometheus + Grafana self-hosted.**
- **Grafana Cloud free tier (SaaS).**
- **AWS CloudWatch.**
- **UptimeRobot + logs básicos.**

### Formato de logs

- **structlog JSON.**
- **`logging` nativo con formatter JSON.**
- **Plain text.**

### Centralización de logs

- **Loki (junto a Grafana).**
- **Solo `docker logs` + `grep`.**
- **AWS CloudWatch Logs.**

### Canal de alertas

- **Discord webhook.**
- **Slack webhook.**
- **Email.**
- **Sin alertas en Fase 1.**

## Decisión

- **Métricas:** Prometheus self-hosted. El backend expone
  `/metrics` vía `prometheus-client` con histogramas de latencia por endpoint
  y método, contador de requests por status code, y gauges de in-flight
  requests. `node_exporter` corre como sidecar para métricas de la EC2;
  `cadvisor` para métricas de contenedores; `traefik` expone sus propias
  métricas habilitando el endpoint `/metrics` en el servicio Traefik.
- **Visualización:** Grafana self-hosted. Dashboards versionados como código
  en `infra/grafana/dashboards/` y provisionados al arranque.
- **Logs estructurados:** `structlog` en JSON, con campos estándar
  (`timestamp`, `level`, `logger`, `event`, `request_id`, `user_id` si
  aplica, `trace_id` reservado). El backend inyecta `request_id` vía
  middleware de FastAPI y lo correlaciona con Traefik a través de header
  `X-Request-ID`.
- **Centralización:** Loki. Promtail corre en la EC2 para leer los archivos
  de `docker logs` rotados y enviarlos a Loki. Grafana consulta Loki como
  data source adicional.
- **Alertas:** Discord webhook. Prometheus Alertmanager dispara alertas por
  reglas (caída de `/health/ready`, 5xx > umbral, CPU > 85 % sostenido,
  disco > 85 %). Severidad mínima `warning` se silencia fuera de horario
  académico del equipo.

El conjunto corre en el `docker-compose.observability.yml` separado del
`docker-compose.app.yml`, para poder reiniciar la app sin tocar
observabilidad.

Retención:

- Prometheus: 15 días en disco local.
- Loki: 14 días.
- Las métricas de producción después de la demo se pueden archivar a S3 si
  hiciera falta.

## Consecuencias

### Positivas

- Dashboard en tiempo real con métricas, logs y estado de health; cumple el
  requisito de la adenda.
- Los logs estructurados son filtrables en Grafana con LogQL, y correlacionables
  con las métricas por `request_id`.
- Alertas llegan al Discord del equipo, sin añadir un canal de comunicación
  extra.
- Todo el stack se configura como código (Prometheus rules, Grafana
  dashboards, Promtail pipelines) y vive en el repo.
- Cero costo monetario adicional (cubierto por créditos AWS).

### Negativas

- Consumo de RAM de Grafana + Prometheus + Loki + Promtail + node_exporter +
  cadvisor puede ser el ~30-40 % de la RAM disponible en `t3.small`. Hay que
  vigilar; si se vuelve un cuello de botella, subir a `t3.medium` es trivial
  (ADR-0019).
- Operar este stack no es gratis en esfuerzo: hay que mantener versiones de
  imágenes, dashboards y reglas.
- Sin trazas distribuidas en Fase 1. Si Fase 3 requiere OpenTelemetry, se
  agrega Tempo como nuevo data source; la arquitectura lo permite sin
  refactor.

### Neutras

- Las alertas por email quedan disponibles vía Alertmanager si hiciera falta
  un canal adicional.
- Grafana se expone detrás de Traefik con autenticación básica en dev y OIDC
  en prod si el tiempo lo permite (por ahora, basic auth).

## Pros y contras de las opciones

### Stack de observabilidad

#### Prometheus + Grafana self-hosted

- **Pros:** Estándar, gratis, potente, dashboards como código, cubre
  métricas + logs + alertas.
- **Contras:** Consumo de recursos notable en una EC2 chica; requiere
  aprender PromQL/LogQL.

#### Grafana Cloud free tier

- **Pros:** Sin overhead en la EC2.
- **Contras:** Free tier con cuotas (10k series activas, 50 GB logs/mes);
  data fuera del perímetro; curva igual de alta que self-hosted.

#### AWS CloudWatch

- **Pros:** Integrado en AWS; cero setup inicial.
- **Contras:** Costo por métrica custom y por GB de logs sale caro rápido;
  dashboards muy limitados; deja afuera la experiencia pedagógica con Prom/
  Grafana.

#### UptimeRobot + logs básicos

- **Pros:** Super simple.
- **Contras:** No cubre latencia por endpoint, ni recursos, ni frecuencia de
  uso del API. Incumple la adenda.

### Formato de logs

#### structlog JSON

- **Pros:** Campos estructurados, contexto automático (bind), rinde bien,
  indexa muy bien en Loki.
- **Contras:** API ligeramente distinta a `logging` nativo; curva corta.

#### logging nativo + formatter JSON

- **Pros:** Sin dependencia adicional.
- **Contras:** Bind de contexto más verboso; handling de excepciones más
  manual.

#### Plain text

- **Pros:** Fácil de leer en terminal.
- **Contras:** Pésimo para Loki y para correlaciones; se parsea con regex y
  se desprolija.

### Centralización

#### Loki

- **Pros:** Integrado con Grafana, barato en disco, consultas rápidas con
  LogQL; no indexa el contenido sino las labels, lo que lo hace eficiente.
- **Contras:** Requiere Promtail; labels mal diseñadas explotan cardinalidad.

#### Solo `docker logs`

- **Pros:** Cero setup.
- **Contras:** No es un dashboard; no es persistente ante rotación; no
  integra con métricas.

#### CloudWatch Logs

- **Pros:** Integrado en AWS.
- **Contras:** Costo; UI limitada; otra vez saca al equipo del ecosistema
  Grafana.

### Alertas

#### Discord webhook

- **Pros:** El equipo ya usa Discord; setup trivial; soporta mensajes ricos.
- **Contras:** No hay SLAs de entrega formales.

#### Slack webhook

- **Pros:** Integraciones maduras.
- **Contras:** El equipo no está en Slack para este TP; crear un workspace
  solo para alertas es desproporcionado.

#### Email

- **Pros:** Universal.
- **Contras:** Alto riesgo de terminar ignorado; filtros de spam.

#### Sin alertas

- **Pros:** Nada que configurar.
- **Contras:** Incumple el espíritu del requisito (monitoreo útil, no solo
  decorativo).

## Referencias

- ADR-0009 — Health checks y rolling updates.
- ADR-0010 — EC2 + Docker Compose + Traefik.
- ADR-0011 — Workflows de CI/CD.
- ADR-0019 — Tamaño de EC2 y posible escalado.
- Prometheus docs — `prometheus-client` for Python, best practices.
- Grafana Loki docs.
- structlog docs.
- Alertmanager — Discord receiver.
