# ADR-0021: Subconjunto de observabilidad para entorno local — Fase 1

- **Estado:** Aceptado
- **Fecha:** 2026-04-23
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

ADR-0017 define una estrategia de observabilidad por capas: CloudWatch como
capa operacional base para AWS y Prometheus + Grafana como dashboard local de
Fase 1. Para la demo de Fase 1, el sistema corre localmente en Docker sin
depender de servidores EC2 ni credenciales externas.

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
- Loki, Promtail y Alertmanager se consideran mejoras futuras si la
  observabilidad de aplicación crece; no son necesarios para demostrar el
  dashboard requerido en Fase 1.
- El equipo dispone de Docker en sus máquinas.

## Opciones consideradas

1. **Implementar un stack completo de observabilidad local** (Prometheus +
   Grafana + Loki + Promtail + Alertmanager + node_exporter + cadvisor).
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

Los componentes no incluidos en el stack local y su justificación:

| Componente      | Motivo para diferir                                                   |
| --------------- | --------------------------------------------------------------------- |
| Loki + Promtail | Aporta búsqueda avanzada de logs, no requerida para Fase 1            |
| Alertmanager    | Requiere canales de alerta activos y reglas maduras                   |
| node_exporter   | Métricas de CPU/RAM del host; en AWS se cubren con CloudWatch         |
| cadvisor        | Métricas de containers del host; no bloquea la demo local             |
| structlog       | Mejora de logs del API; no bloquea el dashboard de métricas           |

Estos componentes podrán incorporarse en Fase 2/3 si el equipo necesita
observabilidad más profunda que CloudWatch + `/metrics`.

## Consecuencias

**Positivas:**

- Dashboard funcional levantable con `docker compose up` en cualquier
  máquina del equipo.
- Cubre las cuatro métricas requeridas por la adenda: latencia,
  disponibilidad (error rate), frecuencia de uso, y recursos (in-flight).
- Dashboards versionados como código en `infra/monitoring/grafana/`.
- No requiere credenciales externas ni servidor.

**Negativas / trade-offs asumidos:**

- Sin métricas de CPU/RAM del host en el compose local (node_exporter). En
  AWS, ese punto se cubre con CloudWatch/CloudWatch Agent según ADR-0017.
- Sin centralización de logs. Los logs del API son accesibles vía
  `docker logs` mientras tanto.
- Sin alertas locales. En AWS, las alertas básicas pueden resolverse con
  CloudWatch Alarms.

**Neutras:**

- La arquitectura local conserva `/metrics`, por lo que agregar Prometheus
  centralizado o Grafana con CloudWatch como data source no requiere
  refactorizar la API.

## Referencias

- ADR-0017 — Observabilidad con CloudWatch en AWS y dashboard local.
- ADR-0010 — Plataforma de hosting EC2 con Docker Swarm.
- Adenda técnica Fase 1 — requisitos del dashboard de monitoreo.
