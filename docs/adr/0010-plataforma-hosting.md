# ADR-0010: Plataforma de hosting sobre AWS EC2 con Docker Swarm y Traefik

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

ADR-0008 define tres ambientes:

```text
preview/dev efimero -> pr-<N>.dev.petrocast.shop
staging persistente -> staging.petrocast.shop
produccion          -> api.petrocast.shop
```

Debemos decidir dónde corren esos ambientes, con qué runtime de containers y
cómo se exponen a internet.

Condicionantes conocidos:

- El equipo cuenta con créditos AWS educativos.
- Se dispone de un dominio propio para configurar URLs por ambiente.
- La materia cubre cloud, DevOps, containers, networking y despliegues.
- La solución debe ser suficientemente profesional para defender separación
  de ambientes, sin caer en sobreingeniería.

## Drivers de la decisión

- Aprovechar créditos AWS disponibles.
- Separar físicamente previews, staging y producción.
- Mostrar fundamentos de Docker, networking, reverse proxy, TLS y rollout.
- Mantener bajo overhead operativo para un equipo de 3 personas.
- Evitar Kubernetes/ECS en Fase 1.
- Permitir rolling updates y rollback automático.
- Mantener infraestructura reproducible vía Terraform (ADR-0019).

## Opciones consideradas

1. **Tres EC2 con Docker Swarm single-node + Traefik.**
2. **Una única EC2 con Docker Compose y redes separadas.**
3. **ECS Fargate.**
4. **AWS App Runner.**
5. **Elastic Beanstalk.**
6. **Proveedor distinto a AWS** (Railway, Fly.io, Render).

## Decisión

Adoptamos **tres EC2 en AWS**, una por ambiente lógico, cada una con
**Docker Swarm single-node** y **Traefik** como reverse proxy:

```text
EC2 swarm-preview-dev -> previews por PR
EC2 swarm-staging     -> staging persistente
EC2 swarm-prod        -> produccion persistente
```

### Componentes por EC2

**Cómputo:**

- Ubuntu LTS.
- Docker Engine.
- Docker Swarm inicializado localmente (`docker swarm init`).
- Usuario de deploy con permisos mínimos para operar Docker.

**Runtime:**

- Stacks desplegados con `docker stack deploy`.
- Servicios declarados con `deploy.update_config` y `deploy.rollback_config`
  (ADR-0009).
- Staging y producción usan 2 réplicas del servicio API.
- Preview/dev usa 1 réplica por PR.

**Reverse proxy:**

- Traefik en cada EC2.
- Descubrimiento de servicios vía labels Docker.
- Terminación TLS con Let's Encrypt.
- Routing por hostname:

```text
pr-123.dev.petrocast.shop -> stack pr-123 en EC2 preview
staging.petrocast.shop    -> stack staging en EC2 staging
api.petrocast.shop        -> stack prod en EC2 prod
```

**Networking:**

- Security Groups por ambiente.
- Ingress público en 80/443.
- SSH restringido o reemplazado por AWS Systems Manager Run Command.
- Egress hacia ECR para descargar imágenes.

**Persistencia:**

- Fase 1 no requiere base de datos real.
- Cuando se incorpore PostgreSQL (stack definido en ADR-0012), cada
  ambiente tendrá su propia base de datos o volumen persistente, nunca
  compartido entre ambientes.

### DNS

Route 53 apunta cada hostname al ambiente correcto:

```text
*.dev.petrocast.shop   -> Elastic IP de swarm-preview-dev
staging.petrocast.shop -> Elastic IP de swarm-staging
api.petrocast.shop     -> Elastic IP de swarm-prod
```

El wildcard de previews evita modificar DNS por cada PR. Traefik decide el
servicio destino usando el hostname.

### Despliegue remoto

La primera iteración puede usar SSH restringido desde GitHub Actions hacia
cada EC2 para ejecutar:

```bash
docker login
docker stack deploy
docker service ls
curl /health
```

Como mejora de seguridad, la arquitectura propone migrar a **AWS Systems
Manager Run Command**, que permite ejecutar comandos remotos sin exponer el
puerto SSH. La decisión de CI/CD queda detallada en ADR-0011.

### Infraestructura como código

Toda la infraestructura se gestiona con Terraform (ADR-0019):

- EC2 preview, staging y prod.
- Security Groups.
- Elastic IPs.
- IAM roles.
- ECR.
- Route 53.
- S3 para state y artefactos.
- CloudWatch log groups.

## Consecuencias

**Positivas:**

- Separación física de ambientes sin complejidad de orquestadores managed.
- Docker Swarm permite rolling updates y rollback con configuración simple.
- Traefik simplifica routing dinámico para previews por PR.
- Las URLs son estables y limpias para demo y evaluación.
- El equipo demuestra fundamentos de containers, DNS, TLS, networking y
  deployment.
- Migrar a Swarm multi-node, ECS o Kubernetes en el futuro es posible sin
  cambiar el flujo de promoción.

**Negativas / trade-offs asumidos:**

- Tres EC2 tienen más costo y mantenimiento que una.
- Swarm single-node no da alta disponibilidad ante caída de la instancia.
- Hay que mantener Docker y Traefik en tres hosts.
- SSM es más seguro que SSH, pero requiere configuración adicional de IAM y
  agente en la instancia.

**Neutras:**

- Producción con un solo nodo es suficiente para la mock API académica. Dos
  nodos en producción quedan como mejora opcional si se busca mayor robustez.

## Pros y contras de cada opción

### Tres EC2 + Docker Swarm + Traefik (elegida)

- ✅ Separación clara de ambientes.
- ✅ Rolling updates y rollback nativos.
- ✅ Bajo overhead frente a Kubernetes/ECS.
- ✅ Excelente para previews por PR con wildcard DNS.
- ❌ Más hosts que administrar.
- ❌ Sin HA multi-nodo por default.

### Una EC2 + Docker Compose

- ✅ Costo mínimo.
- ✅ Setup simple.
- ❌ Mezcla previews, staging y producción en el mismo host.
- ❌ Una falla de la EC2 tira todos los ambientes.
- ❌ Compose no ofrece el mismo modelo declarativo de rolling/rollback que
  Swarm.

### ECS Fargate

- ✅ Managed y escalable.
- ✅ Health checks y rollouts robustos.
- ❌ Más curva de aprendizaje y más piezas AWS.
- ❌ Menos transparente para defender fundamentos de Docker y networking.
- ❌ Mayor costo para tres ambientes.

### AWS App Runner

- ✅ Muy simple para exponer servicios web.
- ❌ Menos control sobre networking, Traefik y previews dinámicos.
- ❌ Oculta demasiado del stack que queremos demostrar.

### Elastic Beanstalk

- ✅ PaaS clásico con despliegues integrados.
- ❌ Menos alineado con prácticas modernas de containers.
- ❌ Menor valor pedagógico que operar Docker/Traefik directamente.

### Proveedor alternativo

- ✅ Mejor DX inicial en algunos casos.
- ❌ No aprovecha créditos AWS.
- ❌ Pierde coherencia con ECR, Route 53, IAM/OIDC, S3 y CloudWatch.

## Referencias

- ADR-0008 (Topología de ambientes).
- ADR-0009 (Rolling updates y rollback).
- ADR-0011 (GitHub Actions).
- ADR-0013 (ECR).
- ADR-0019 (Terraform).
- Docker Swarm docs.
- Traefik Proxy docs.
- AWS Systems Manager Run Command.
- AWS EC2 docs.
