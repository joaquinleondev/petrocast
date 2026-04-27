# ADR-0008: Topología de ambientes con previews efímeros, staging y producción separados

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige automatizar despliegues a ambientes de
desarrollo, staging y producción. Además, el PRD pide disponibilidad de la
API, verificación automática de salud post-deployment y una separación clara
entre código en desarrollo y el servicio que verá el evaluador.

Necesitamos definir:

- Qué significa "dev" en un flujo con Pull Requests.
- Dónde corre físicamente cada ambiente.
- Qué evento dispara un deploy a cada ambiente.
- Qué URL identifica a cada ambiente.
- Cómo se evita mezclar previews, staging y producción en la misma unidad
  operativa.
- Cómo se relaciona esta topología con la estrategia de branching definida
  en ADR-0004.

Esta decisión es bloqueante para CI/CD, DNS, Terraform, registry y estrategia
de rollback.

## Drivers de la decisión

- El equipo cuenta con créditos AWS educativos, por lo que EC2 es viable.
- Disponemos de un dominio propio para URLs limpias por ambiente.
- La URL de producción debe ser estable y no reflejar código en desarrollo.
- Staging debe representar el estado integrado de `main`.
- Las Pull Requests deben poder revisarse en un ambiente aislado antes de
  mergear.
- Se busca profesionalismo sin introducir Kubernetes, ECS o una plataforma
  managed con mayor complejidad operativa.
- La separación de ambientes debe ser defendible: no queremos todos los
  workloads críticos mezclados en una única EC2.

## Opciones consideradas

1. **Un solo ambiente de producción**, sin staging ni dev deployados.
2. **Tres ambientes en una misma EC2**, diferenciados por subdominio y red
   Docker.
3. **Tres EC2 separadas**, una para previews/dev, una para staging y una para
   producción, cada una con Docker Swarm single-node.
4. **Servicios AWS managed** (ECS Fargate, App Runner) con tres servicios.

## Decisión

Adoptamos **tres EC2 separadas**, cada una operando como un **single-node
Docker Swarm**:

```text
PR abierta      -> preview/dev efimero: pr-123.dev.petrocast.shop
merge a main    -> staging persistente: staging.petrocast.shop
tag v*          -> produccion: api.petrocast.shop
```

### Topología

| Ambiente        | URL                         | Disparador                   | Ciclo de vida                     | Host físico             |
| --------------- | --------------------------- | ---------------------------- | --------------------------------- | ----------------------- |
| **Preview/dev** | `pr-<N>.dev.petrocast.shop` | PR opened/synchronize/reopen | Efímero, se destruye al cerrar PR | EC2 `swarm-preview-dev` |
| **Staging**     | `staging.petrocast.shop`    | Merge a `main`               | Persistente                       | EC2 `swarm-staging`     |
| **Producción**  | `api.petrocast.shop`        | Tag `v*` con approval manual | Persistente                       | EC2 `swarm-prod`        |

Cada EC2 tiene:

- Docker Engine.
- Docker Swarm inicializado en modo single-node.
- Traefik como reverse proxy.
- Acceso a ECR para descargar imágenes.
- Logs enviados a CloudWatch.

Producción puede escalar a dos nodos Swarm si se busca mayor robustez, pero
para una mock API académica no es obligatorio. El diseño deja esa evolución
como cambio incremental, no como rediseño.

### DNS

Route 53 gestiona los records:

```text
*.dev.petrocast.shop      -> EC2 preview/dev
staging.petrocast.shop    -> EC2 staging
api.petrocast.shop        -> EC2 producción
```

El wildcard `*.dev.petrocast.shop` permite que cada PR tenga su propio hostname
sin crear records DNS individuales. Traefik enruta internamente por hostname
al stack correspondiente.

### Relación con branching (ADR-0004)

La topología de deployment es ortogonal a la estrategia de branching. Se
mantiene una única branch permanente (`main`) y las promociones ocurren por
eventos:

```text
Pull Request abierto      -> preview env efimero pr-<N>.dev.petrocast.shop
Merge a main              -> deploy automatico a staging.petrocast.shop
Tag v* creado en main     -> deploy a api.petrocast.shop con approval manual
```

El deploy a producción requiere crear un tag versionado (`v1.0.0`,
`v1.0.1`, etc.) y pasar por GitHub Environment `production` con aprobación
manual. Esto evita que un merge accidental a `main` afecte la URL productiva.

### Datos por ambiente

- **Preview/dev:** estado efímero por PR, sembrado con dataset sintético
  pequeño. Se elimina al cerrar o mergear el PR.
- **Staging:** dataset sintético persistente y completo para validar el
  sistema integrado.
- **Producción:** dataset sintético persistente usado para la entrega y demo
  formal.

No hay datos reales sensibles en Fase 1. Si en Fase 2 se incorporaran datos
reales, se deberá agregar un ADR específico sobre segregación, backups,
retención y enmascaramiento.

## Consecuencias

**Positivas:**

- Dev queda representado por previews efímeros reales, no por una branch
  permanente.
- Staging y producción quedan físicamente separados, lo que reduce el riesgo
  de interferencia entre workloads.
- La URL productiva solo cambia ante releases explícitos.
- La separación por EC2 es simple de explicar y operar, pero más defendible
  que una sola máquina con todo mezclado.
- Docker Swarm permite rolling updates y rollback sin Kubernetes.
- El wildcard DNS simplifica previews por PR.

**Negativas / trade-offs asumidos:**

- Tres EC2 cuestan más que una única instancia.
- Hay tres hosts que parchear, monitorear y provisionar.
- El aislamiento sigue sin ser alta disponibilidad real: cada ambiente tiene
  un único nodo. Para el TP es aceptable.
- Docker Swarm single-node no resuelve fallas físicas del host; solo gestiona
  el ciclo de vida de servicios dentro del nodo.

**Neutras:**

- La decisión es reversible: si el proyecto crece, staging y producción
  pueden migrarse a Swarm multi-node, ECS o Kubernetes sin cambiar el flujo
  de promoción PR -> staging -> prod.

## Pros y contras de cada opción

### Opción 1 — Un solo ambiente de producción

- ✅ Infraestructura mínima.
- ❌ No cumple bien el requisito de separar ambientes.
- ❌ Sin staging, los bugs llegan directamente al evaluador.
- ❌ Sin previews, no hay forma de probar PRs en aislamiento.

### Opción 2 — Tres ambientes en una misma EC2

- ✅ Bajo costo.
- ✅ Un solo host que administrar.
- ❌ Mezcla workloads de distinta criticidad.
- ❌ Una caída de la EC2 tira previews, staging y producción.
- ❌ Menos defendible como separación real de environments.

### Opción 3 — Tres EC2 con Swarm single-node (elegida)

- ✅ Separación física por ambiente.
- ✅ Cumple previews, staging y producción sin sobreingeniería.
- ✅ Permite rolling updates y rollback vía Docker Swarm.
- ✅ Mantiene bajo overhead operativo frente a Kubernetes o ECS.
- ❌ Mayor costo que una EC2 única.
- ❌ No ofrece HA multi-nodo por default.

### Opción 4 — ECS Fargate / App Runner

- ✅ Managed: menos administración de servidores.
- ✅ Escalado y health management nativos.
- ❌ Mayor curva de aprendizaje para el equipo.
- ❌ Más difícil de explicar en detalle si el foco del TP es demostrar
  fundamentos de Docker, networking y despliegue.
- ❌ Potencialmente más caro para tres ambientes.

## Referencias

- ADR-0004 (Estrategia de branching).
- ADR-0009 (Estrategia de deployment, rolling updates y rollback).
- ADR-0010 (Plataforma de hosting).
- ADR-0011 (Plataforma de CI/CD).
- ADR-0013 (Container registry en ECR).
- ADR-0019 (Infraestructura como código con Terraform).
- AWS Route 53 — wildcards en records DNS.
- GitHub Actions — environments y deployment protection rules.
- Adenda técnica de Fase 1 (requisito de ambientes y CI/CD).
