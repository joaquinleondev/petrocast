# ADR-0019: Infraestructura como código con Terraform sobre AWS — state en S3+DynamoDB, DNS en Route 53, EC2 `t3.small` en `us-east-1`

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

El ADR-0010 fijó AWS EC2 + Docker Compose + Traefik como plataforma de
deployment. Ese ADR es agnóstico respecto a **cómo** se crea esa
infraestructura. Dado que la adenda técnica exige que todo el despliegue sea
reproducible, auditable y versionado, necesitamos decidir:

1. Si usamos **infraestructura como código (IaC)** y con qué herramienta.
2. Dónde vive el **state** y cómo se evita que dos personas corran `apply` a
   la vez.
3. Qué recursos gestiona IaC y cuáles quedan fuera.
4. Dónde gestionamos **DNS**, dado que tenemos un dominio propio para los
   tres ambientes.
5. Parámetros concretos de la flota: **región** y **tamaño de instancia**.

## Drivers de la decisión

- **Reproducibilidad.** El evaluador debe poder reconstruir la
  infraestructura desde el repo sin conocimiento tribal.
- **Auditoría.** Los PRs que cambian infra deben pasar por el mismo
  workflow que el código (review + CI).
- **Colaboración segura.** Tres personas pueden tocar infra
  concurrentemente; hace falta locking del state.
- **Costo.** Créditos AWS educativos finitos; preferimos recursos baratos y
  una región donde los precios sean predecibles.
- **Curva del equipo.** Al menos un miembro ya ha usado Terraform; los demás
  pueden aprenderlo razonablemente en Fase 1.
- **Integración con el resto de ADRs.** ECR (ADR-0013), IAM OIDC para CI
  (ADR-0013, ADR-0011) y Route 53 son todos candidatos naturales a vivir
  bajo Terraform para mantener un único plano de control.

## Opciones consideradas

### Herramienta de IaC

- **Terraform.**
- **Manual con scripts bash.**
- **Pulumi.**
- **AWS CDK.**

### Terraform state

- **S3 + DynamoDB (lock).**
- **S3 sin lock.**
- **Local (`terraform.tfstate` en un repo privado).**
- **Terraform Cloud free tier.**

### Scope de lo gestionado

- **Todo (VPC, EC2, SG, S3, IAM, DNS, ECR).**
- **Solo EC2 + Security Groups.**
- **Solo recursos críticos; el resto manual.**

### DNS

- **AWS Route 53.**
- **Cloudflare (DNS + CDN gratis).**
- **En el registrar actual, manualmente.**

### Región y tamaño

- **`us-east-1`.**
- **`sa-east-1` (São Paulo).**
- **`us-east-2` (Ohio).**
- **EC2 `t3.small` (2 vCPU, 2 GiB).**
- **EC2 `t3.medium`.**
- **EC2 `t3.micro`.**

## Decisión

- **Herramienta:** Terraform (versión fijada en `~> 1.9`).
- **Estructura:** `infra/terraform/` con módulos por responsabilidad
  (`modules/network`, `modules/compute`, `modules/ecr`, `modules/dns`,
  `modules/observability`) y entornos como directorios raíz con `backend`
  propio (`envs/dev`, `envs/staging`, `envs/prod`). Los tres comparten la
  misma EC2 con Traefik enruteando por host, coherente con ADR-0008 y
  ADR-0010.
- **Backend del state:** S3 con versionado activado + tabla DynamoDB para
  lock. Encriptación server-side con SSE-S3 (suficiente para el TP).
  Bucket y tabla se bootstrappean una única vez con un script
  `infra/terraform/bootstrap/` y luego el state vive ahí.
- **Scope:** Todo. VPC, subnets, Internet Gateway, Security Groups, EC2,
  EBS, key pair, rol IAM de la instancia, proveedor OIDC para GitHub
  Actions, roles IAM para los workflows, repos ECR, lifecycle policies,
  Route 53 hosted zone y records, y los buckets S3 auxiliares. Lo único
  explícitamente fuera de Terraform son los secrets de aplicación (viven
  en GitHub Secrets, ver ADR-0018).
- **DNS:** AWS Route 53 con una hosted zone por el dominio del proyecto.
  Los NS del dominio apuntan a Route 53. Los records son:
  - `dev-*.<dominio>` → wildcard al Elastic IP de la EC2 (subdominios
    efímeros por PR).
  - `staging.<dominio>` → mismo IP.
  - `<dominio>` y `www.<dominio>` → mismo IP (prod).
- **Región:** `us-east-1`. Es la región más barata, la de mayor
  disponibilidad de servicios y la que los créditos AWS educativos suelen
  cubrir sin caveats. La latencia desde Argentina es aceptable para un TP
  (~150 ms); no hay requisito del PRD que la prohíba.
- **Tamaño de instancia:** `t3.small` (2 vCPU, 2 GiB). Cubre el stack de
  observabilidad de ADR-0017 junto al backend y el mock sin ahogar la
  memoria. `t3.micro` (1 GiB) es insuficiente para Grafana + Prometheus +
  Loki. Si Fase 2 o 3 demandan más, subir a `t3.medium` (4 GiB) es un
  cambio de una variable en Terraform.

## Consecuencias

### Positivas

- Un `terraform apply` reconstruye todo el entorno de cero.
- Los cambios de infra pasan por PR review, igual que el código.
- El state con lock evita corrupciones cuando dos miembros corren `apply`.
- DNS en Route 53 permite gestionar TLS vía Traefik + Let's Encrypt
  (ADR-0010) con DNS-01 challenge si el tiempo alcanza; HTTP-01 funciona
  en cualquier caso.
- OIDC + roles acotados (ADR-0013) también quedan versionados y revisables.

### Negativas

- Curva inicial: dos de los tres miembros tienen que aprender Terraform.
- El bootstrap del bucket S3 y tabla DynamoDB es un "huevo y gallina"
  (Terraform necesita donde guardar el state antes de poder crearlo); se
  resuelve con un `bootstrap/` separado aplicado una vez manualmente.
- La latencia desde Argentina a `us-east-1` es mayor que a `sa-east-1`; no
  es crítica pero se percibe.
- `t3.small` con 2 GiB deja poca holgura; requiere monitorear memoria
  durante las demos.

### Neutras

- Terraform Cloud queda disponible como fallback si S3 + DynamoDB dan
  problemas inesperados.
- La decisión de región es reversible: migrar entre regiones implica
  reprovisionar, pero no reescribir código.

## Pros y contras de las opciones

### Herramienta de IaC

#### Terraform

- **Pros:** Estándar de facto; proveedor AWS muy maduro; comunidad enorme;
  conceptos (state, plan, apply, modules) son transferibles.
- **Contras:** HCL es un idioma más para aprender; gestión de state es una
  fuente clásica de accidentes.

#### Scripts bash

- **Pros:** Aparente simplicidad.
- **Contras:** No idempotente; sin plan previo; auditoría pobre; no escala
  a 3 ambientes.

#### Pulumi

- **Pros:** IaC en TypeScript/Python.
- **Contras:** El equipo no lo usa; ecosistema menor para AWS; la curva
  cancela el beneficio de "lenguaje conocido".

#### AWS CDK

- **Pros:** IaC en TypeScript/Python; genera CloudFormation.
- **Contras:** Acopla a CloudFormation (sus limitaciones), opaco para
  debugging; no aplica fuera de AWS si Fase 3 quisiera multi-cloud.

### Terraform state

#### S3 + DynamoDB lock

- **Pros:** Estándar, barato, integrado con AWS, seguro con versionado
  activo.
- **Contras:** Bootstrap de una vez.

#### S3 sin lock

- **Pros:** Un recurso menos.
- **Contras:** Riesgo real de corrupción si dos miembros hacen `apply` a
  la vez.

#### Local en repo privado

- **Pros:** Cero infra.
- **Contras:** State con secrets en git; inaceptable.

#### Terraform Cloud free tier

- **Pros:** UI, runs remotos, sin bootstrap.
- **Contras:** Servicio extra; 5 usuarios máx en free tier; pérdida de
  control del pipeline.

### Scope de IaC

#### Todo

- **Pros:** Un solo plano de control; onboarding y documentación unificada;
  reconstruible de cero.
- **Contras:** Superficie más grande de aprendizaje inicial.

#### Solo EC2 + SG

- **Pros:** Menor volumen de código IaC.
- **Contras:** Recursos críticos (IAM, ECR, DNS) quedan manuales y con
  drift garantizado.

#### Solo críticos

- **Pros:** Compromiso intermedio.
- **Contras:** La línea se vuelve subjetiva; inevitablemente alguien mueve
  un recurso por consola y se rompe la reproducibilidad.

### DNS

#### Route 53

- **Pros:** Integrado con Terraform y con Let's Encrypt DNS-01; latencia
  baja; maneja wildcards y bonitos health checks.
- **Contras:** Costo por hosted zone ($0,50/mes) + queries (trivial, pero
  existe).

#### Cloudflare

- **Pros:** Free tier generoso; CDN.
- **Contras:** Plano de control separado; sincronizar con IaC exige un
  segundo proveedor de Terraform y un segundo flujo de credenciales.

#### Registrar actual, manual

- **Pros:** Cero servicios.
- **Contras:** Sin IaC; no escala a subdominios efímeros por PR.

### Región

#### `us-east-1`

- **Pros:** Más barata; todos los servicios disponibles al instante; mayor
  inventario de guías y AMIs.
- **Contras:** Latencia más alta hacia Argentina.

#### `sa-east-1`

- **Pros:** Menor latencia regional.
- **Contras:** Precios ~25 % más altos; a veces servicios nuevos llegan más
  tarde; créditos educativos a veces tienen sorpresas con regiones no-US.

#### `us-east-2`

- **Pros:** Balance costo-latencia.
- **Contras:** No hay razón fuerte para preferirla sobre `us-east-1` dado
  que la diferencia de latencia con Argentina es despreciable.

### Tamaño

#### `t3.small`

- **Pros:** Suficiente para backend + Prom/Grafana/Loki + mock; barato.
- **Contras:** Poca holgura de memoria; exige monitoreo.

#### `t3.medium`

- **Pros:** Holgura cómoda.
- **Contras:** ~2x el costo; innecesario para Fase 1.

#### `t3.micro`

- **Pros:** Free tier.
- **Contras:** 1 GiB no alcanza para correr Postgres + stack de
  observabilidad + backend sin thrashing.

## Referencias

- ADR-0008 — Tres ambientes sobre una EC2.
- ADR-0009 — Rolling updates y health checks.
- ADR-0010 — AWS EC2 + Docker Compose + Traefik.
- ADR-0011 — Workflows de GitHub Actions.
- ADR-0013 — Container registry en ECR.
- ADR-0017 — Stack de observabilidad (consume memoria de la EC2).
- ADR-0018 — Secrets en GitHub, no en Terraform.
- Terraform AWS Provider docs.
- AWS pricing — EC2 / Route 53 / S3 / DynamoDB.
- Let's Encrypt — DNS-01 challenge.
