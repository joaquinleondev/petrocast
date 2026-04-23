# ADR-0021: Subconjunto de observabilidad para entorno local — Fase 1

- **Estado:** Aceptado
- **Fecha:** 2026-04-23
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

ADR-0017 define el stack completo de observabilidad para producción:
Prometheus + Grafana + Loki + Promtail + Alertmanager + node_exporter +
cadvisor. Para la demo de Fase 1, el sistema corre localmente en Docker
sin un servidor EC2 todavía disponible.

Necesitamos decidir qué subconjunto del stack definido en ADR-0017
implementar en Fase 1 de manera que:

1. Cumpla los requisitos de la adenda (dashboard con las cuatro métricas).
2. Pueda levantarse en cualquier máquina del equipo con un solo comando.
3. No requiera infraestructura de servidor ni credenciales externas.

## Drivers de la decisión

- La adenda exige un dashboard funcional demostrable, no un stack de
  producción completo.
- El servidor EC2 todavía no está provisionado (se aborda en sprint de
  deployment).
- Loki, Promtail y Alertmanager tienen dependencias de configuración de
  red y persistencia que los hacen no triviales de correr localmente.
- El equipo dispone de Docker en sus máquinas.

## Opciones consideradas

1. **Implementar el stack completo de ADR-0017** (Prometheus + Grafana +
   Loki + Promtail + Alertmanager + node_exporter + cadvisor).
2. **Implementar solo Prometheus + Grafana** con métricas de la API.
3. **Usar Grafana Cloud free tier** para no correr nada localmente.

## Decisión

Adoptamos la **opción 2**: Prometheus + Grafana con métricas del API.

El API expone `/metrics` vía `prometheus-fastapi-instrumentator`, que
instrumenta automáticamente todos los endpoints con:

- Histogramas de latencia por endpoint y método HTTP.
- Contadores de requests por status code.
- Gauge de in-flight requests.

El stack de observabilidad corre en `infra/compose.observability.yml`
**separado** del `infra/compose.dev.yml` (per ADR-0017), permitiendo
reiniciar la app sin afectar el monitoreo.

Los componentes diferidos y su justificación:

| Componente      | Motivo para diferir                                                   |
| --------------- | --------------------------------------------------------------------- |
| Loki + Promtail | Requiere configuración de filesystem del host; útil con servidor real |
| Alertmanager    | Requiere un Discord webhook activo para ser útil                      |
| node_exporter   | Métricas de CPU/RAM del host; relevante en EC2, no en laptop          |
| cadvisor        | Métricas de containers del host; relevante en EC2                     |
| structlog       | Mejora de logs del API; no bloquea el dashboard de métricas           |

Todos estos componentes están documentados en ADR-0017 y se incorporan
al sprint de deployment cuando el servidor EC2 esté disponible.

## Consecuencias

**Positivas:**

- Dashboard funcional levantable con `docker compose up` en cualquier
  máquina del equipo.
- Cubre las cuatro métricas requeridas por la adenda: latencia,
  disponibilidad (error rate), frecuencia de uso, y recursos (in-flight).
- Dashboards versionados como código en `infra/monitoring/grafana/`.
- No requiere credenciales externas ni servidor.

**Negativas / trade-offs asumidos:**

- Sin métricas de CPU/RAM del host (node_exporter). La adenda pide "uso
  de recursos"; in-flight requests cubre parcialmente este requisito.
  Se completa cuando haya servidor.
- Sin centralización de logs. Los logs del API son accesibles vía
  `docker logs` mientras tanto.
- Sin alertas. Se agrega Alertmanager en el sprint de deployment.

**Neutras:**

- La arquitectura del compose sigue el patrón de ADR-0017; agregar los
  componentes faltantes es extender `compose.observability.yml` sin
  refactorizar lo existente.

## Referencias

- ADR-0017 — Stack completo de observabilidad (Prometheus/Grafana/Loki).
- ADR-0010 — Plataforma de hosting EC2 (donde el stack completo se deploya).
- Adenda técnica Fase 1 — requisitos del dashboard de monitoreo.
