# ADR-00010: Plataforma de hosting sobre AWS EC2

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

Debemos decidir dónde corren los ambientes definidos en ADR-0007, con
qué runtime, y cómo se exponen a internet.

Condicionantes conocidos:

- El equipo cuenta con **créditos AWS educativos**, disponibles durante
  la duración del TP.
- Se dispone de un **dominio propio** para configurar URLs por ambiente.
- La materia cubre en su temario conceptos de cloud, DevOps, y
  arquitecturas de software. La infraestructura elegida debe permitir
  demostrar esos conceptos.

## Drivers de la decisión

- Aprovechar los créditos AWS disponibles.
- Mostrar conocimiento de fundamentos (Docker, networking, reverse proxy,
  TLS) en vez de abstracciones managed.
- Infraestructura reproducible y versionable.
- Costo bajo (los créditos no son infinitos).
- Simplicidad operativa para un equipo de 3.

## Opciones consideradas

1. **EC2 con Docker Compose + reverse proxy**.
2. **ECS Fargate** (containers managed).
3. **AWS App Runner** (deploy directo desde repo).
4. **Elastic Beanstalk** (PaaS clásico de AWS).
5. **Proveedor distinto a AWS** (Railway, Fly.io, Render).

## Decisión

Adoptamos **EC2 con Docker Compose y Traefik como reverse proxy**.

### Componentes

**Cómputo:**

- Una instancia EC2 (Ubuntu LTS, `t3.small` inicialmente, escalable).
- Docker Engine + Docker Compose.
- Usuario no-root con permisos mínimos para administración.

**Networking:**

- Security Group con ingress permitido solo en puertos 80, 443, y 22
  (SSH restringido a IPs del equipo).
- Elastic IP asociada a la instancia (evita que cambie al reiniciar).

**Reverse proxy:**

- **Traefik v3** en container, montado sobre el socket Docker.
- Descubrimiento automático de servicios vía labels en los containers.
- **Terminación TLS** con certificados de Let's Encrypt vía ACME
  (automático, renovación automática).
- Enrutamiento por subdominio a los containers correspondientes
  (`staging.<dominio>` → containers de staging, etc.).

**Base de datos:**

- **PostgreSQL** en container, con volumen persistente por ambiente.
- Un container de DB por ambiente permanente (staging, producción).
- Backups: snapshot diario de los volúmenes de EBS (configurable en
  AWS Backup). Para Fase 1, backup manual o snapshot semanal.

**DNS:**

- Registros apuntando al Elastic IP:
  - `A <dominio>` → IP (producción).
  - `A staging.<dominio>` → IP.
  - `A *.dev.<dominio>` → IP (wildcard para preview environments).

**Infraestructura como código:**

- Definiciones de Docker Compose versionadas en `infra/compose/`.
- Scripts de provisioning inicial de la EC2 versionados en
  `infra/provision/` (bash o Ansible, decisión diferida a la
  implementación).
- **Terraform se considera para Fase 2+** si la infraestructura crece.
  Para Fase 1, con una sola instancia, el overhead de Terraform no se
  justifica.

### Estructura de `infra/`

```
infra/
├── compose/
│   ├── base.yml                  # Servicios comunes (Traefik, etc.)
│   ├── docker-compose.staging.yml
│   ├── docker-compose.prod.yml
│   └── docker-compose.preview.yml
├── provision/
│   ├── bootstrap.sh              # Setup inicial de la EC2
│   └── README.md
├── traefik/
│   ├── traefik.yml               # Config estática
│   └── dynamic.yml               # Config dinámica
└── README.md                     # Cómo operar la infra
```

### Operación

- **Acceso SSH**: solo los 3 del equipo, con claves públicas registradas.
- **Deployment**: vía CI/CD (ADR-0011), no SSH manual.
- **Logs**: Traefik y containers envían a `stdout`; agregados por
  Docker Compose. Acceso vía `docker compose logs`.
- **Monitoreo**: el dashboard de monitoreo exigido por la adenda se
  resolverá en un ADR propio (observabilidad, pendiente).

## Consecuencias

**Positivas:**

- Costo bajo: una sola EC2 `t3.small` puede sostener los tres ambientes
  del TP con holgura.
- Control total sobre el stack: útil pedagógicamente.
- Patrones reutilizables (Traefik + Docker + Let's Encrypt) son
  industria-estándar para proyectos pequeños-medianos.
- Elastic IP + DNS propio dan URLs limpias y estables para el
  evaluador.
- Migración futura a K8s es incremental: los containers y compose
  files son la mitad del camino.

**Negativas / trade-offs asumidos:**

- Hay una sola máquina: si se cae, todo se cae. Riesgo aceptable para
  el TP.
- Requiere configuración inicial de ~1 día (SSH, Docker, Traefik,
  certificados, DNS).
- No hay auto-scaling. Para el volumen del TP no es necesario.
- No hay alta disponibilidad multi-AZ. El SLA del 99.5% del PRD se
  cumple de facto en un TP de bajo volumen; no se garantiza con
  infraestructura de un solo nodo.

**Neutras:**

- La instalación manual es reversible: si se pierde la EC2, los scripts
  de provisioning permiten recrearla.

## Pros y contras de cada opción

### EC2 + Docker Compose + Traefik (elegida)

- ✅ Control total.
- ✅ Costo mínimo.
- ✅ Demuestra fundamentos.
- ❌ Configuración manual inicial.
- ❌ Sin HA nativa.

### ECS Fargate

- ✅ Managed: sin EC2 que administrar.
- ✅ Escalado automático.
- ❌ Más caro por hora equivalente de cómputo.
- ❌ Curva de aprendizaje de ECS, task definitions, service discovery.
- ❌ Oculta conceptos de Docker y networking que el TP puede demostrar.

### AWS App Runner

- ✅ Deploy directo desde repo, sin configuración de infra.
- ❌ Muy caro para tres ambientes (pricing por servicio).
- ❌ Oculta casi todo el stack.
- ❌ Integración limitada con redes privadas, BD propia, etc.

### Elastic Beanstalk

- ✅ PaaS con algo de control.
- ❌ Legacy dentro del portfolio AWS, sucesor es App Runner / ECS.
- ❌ Ambiguo respecto a buenas prácticas modernas.

### Proveedor alternativo (Railway, Fly.io, Render)

- ✅ Excelente DX, preview environments nativos.
- ❌ No aprovecha los créditos AWS disponibles.
- ❌ Obligaría a gestionar crédito/gasto real.

## Referencias

- ADR-0008 (Topología de ambientes).
- ADR-0009 (Estrategia de deployment).
- ADR-0011 (Plataforma de CI/CD).
- [Traefik Proxy — Documentation](https://doc.traefik.io/traefik/)
- [Docker Compose — Reference](https://docs.docker.com/compose/)
- [AWS EC2 — Free tier / Educate credits](https://aws.amazon.com/free/)
