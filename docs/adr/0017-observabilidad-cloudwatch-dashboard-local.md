# ADR-0017: Observabilidad con CloudWatch en AWS y dashboard local para Fase 1

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige un dashboard de monitoreo que cubra:

- Latencia del API.
- Disponibilidad / tasa de errores.
- Uso de recursos.
- Frecuencia de uso del API.

ADR-0008 y ADR-0010 separan los ambientes en tres EC2 con Docker Swarm:
preview/dev, staging y producción. El ADR original de observabilidad asumía
un stack completo Prometheus + Grafana + Loki self-hosted en la misma EC2.
Esa decisión deja de ser adecuada al separar ambientes: repetir todo el stack
en cada EC2 agrega overhead operativo innecesario para una mock API.

Necesitamos una estrategia que:

1. Cumpla la demo de Fase 1.
2. No mezcle observabilidad pesada con el runtime de cada ambiente.
3. Aproveche servicios básicos de AWS para logs y métricas.
4. Sea extensible si en Fase 2/3 se requiere más profundidad.

## Drivers de la decisión

- Cumplir la adenda con un dashboard demostrable.
- Mantener bajo consumo en EC2 pequeñas.
- Evitar operar Loki/Promtail/Alertmanager por ambiente en Fase 1.
- Centralizar logs básicos en AWS.
- Conservar `/metrics` en la API para Prometheus local y futura integración.
- Tener evidencia operacional suficiente para defender CI/CD y deploys.

## Opciones consideradas

### Stack de métricas y logs

1. **CloudWatch Logs + métricas básicas de AWS + dashboard local de Fase 1.**
2. **Prometheus + Grafana + Loki self-hosted en cada EC2.**
3. **Grafana Cloud free tier.**
4. **Solo `docker logs` y curls manuales.**

### Dashboard de Fase 1

1. **Prometheus + Grafana local** con `/metrics` de la API.
2. **CloudWatch Dashboard únicamente.**
3. **Dashboard manual o screenshots.**

## Decisión

Adoptamos una estrategia por capas:

### Capa 1 — Dashboard local de Fase 1

Para la demo inmediata, mantenemos **Prometheus + Grafana local** en Docker
Compose, documentado en ADR-0021.

La API expone `/metrics` con `prometheus-fastapi-instrumentator`, cubriendo:

- Histograma de latencia por endpoint y método.
- Contadores de requests por status code.
- Métricas de requests in-flight.
- Frecuencia de llamadas por endpoint.

Este stack se levanta localmente con:

```bash
docker compose -f infra/compose.observability.yml up
```

Esta decisión cumple el requisito de dashboard sin requerir servidor, DNS ni
credenciales AWS.

### Capa 2 — Observabilidad mínima en AWS

Para previews, staging y producción en AWS usamos **CloudWatch** como capa
operacional base:

- CloudWatch Logs para stdout/stderr de la aplicación.
- CloudWatch Logs para Traefik.
- CloudWatch Logs para scripts de deploy ejecutados por SSM/SSH.
- Métricas básicas de EC2.
- CloudWatch Agent si se requiere memoria/disco.
- Alarmas básicas por:
  - instancia sin heartbeat
  - CPU alta sostenida
  - disco alto
  - errores 5xx si se publican métricas custom

CloudWatch no reemplaza el dashboard local de Fase 1; complementa los
ambientes AWS con logs y métricas básicas sin operar un stack de observabilidad
completo por ambiente.

### Capa 3 — Evolución futura

Si Fase 2/3 requiere mayor capacidad de análisis, se evaluará:

- Un Prometheus + Grafana centralizado en una EC2 separada o servicio managed.
- Loki para logs estructurados.
- Alertmanager para alertas a Discord o email.
- OpenTelemetry para trazas.

Esa evolución debe documentarse con un nuevo ADR o una revisión explícita de
este ADR, porque implica más recursos y operación.

### Logging de aplicación

En Fase 1 se aceptan logs estándar de FastAPI/Uvicorn a stdout.

Para fases posteriores, se propone migrar a logs JSON estructurados con
campos:

- `timestamp`
- `level`
- `request_id`
- `method`
- `path`
- `status_code`
- `duration_ms`
- `environment`
- `version`

No se deben loguear API keys ni credenciales.

## Consecuencias

**Positivas:**

- Fase 1 tiene dashboard funcional y reproducible localmente.
- AWS tiene logs y métricas básicas sin sobrecargar cada EC2 con Grafana,
  Prometheus y Loki.
- La API conserva `/metrics`, por lo que una futura migración a Prometheus
  centralizado es directa.
- CloudWatch centraliza evidencia de deploys y runtime.
- El diseño es proporcional al tamaño de la mock API.

**Negativas / trade-offs asumidos:**

- CloudWatch básico no ofrece la misma ergonomía que Grafana para explorar
  métricas de aplicación.
- Sin Loki en Fase 1, los logs no tienen consultas avanzadas tipo LogQL.
- Sin Alertmanager, las alertas quedan limitadas a CloudWatch Alarms o a
  checks del pipeline.
- El dashboard local no observa automáticamente los ambientes AWS.

**Neutras:**

- Mantener `/metrics` desde el inicio reduce el costo de agregar Prometheus
  central más adelante.
- CloudWatch puede convivir con Grafana si se agrega como data source en una
  fase posterior.

## Pros y contras de cada opción

### CloudWatch + dashboard local (elegida)

- ✅ Bajo overhead en EC2.
- ✅ Cumple demo local con Prometheus/Grafana.
- ✅ Centraliza logs básicos en AWS.
- ✅ Alineado con el plan de AWS del proyecto.
- ❌ Menor profundidad que un stack completo self-hosted.

### Prometheus + Grafana + Loki en cada EC2

- ✅ Observabilidad potente por ambiente.
- ❌ Duplica/triplica recursos y configuración.
- ❌ Demasiado pesado para tres EC2 chicas y una mock API.
- ❌ Más piezas para mantener durante la entrega.

### Grafana Cloud

- ✅ Menos carga en EC2.
- ❌ Servicio externo adicional.
- ❌ Cuotas del free tier.
- ❌ Menor control de datos y credenciales.

### Solo `docker logs`

- ✅ Cero setup.
- ❌ No cumple dashboard.
- ❌ No permite análisis serio de latencia, error rate o frecuencia.

## Referencias

- ADR-0008 (Topología de ambientes).
- ADR-0010 (Hosting EC2 + Docker Swarm).
- ADR-0011 (GitHub Actions).
- ADR-0019 (Terraform gestiona CloudWatch log groups).
- ADR-0021 (Subconjunto local Prometheus + Grafana para Fase 1).
- AWS CloudWatch Logs.
- AWS CloudWatch Agent.
- prometheus-fastapi-instrumentator.
- Adenda técnica Fase 1.
