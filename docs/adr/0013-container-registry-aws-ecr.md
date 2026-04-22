# ADR-0013: Container registry privado en AWS ECR

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica exige publicar las imágenes Docker en un **registry privado**
como parte del pipeline de CI/CD, y que el despliegue a dev/staging/prod
(ADR-0008, ADR-0010) arranque containers a partir de esas imágenes. Hay que
decidir dónde vivirán esas imágenes, qué visibilidad tendrán y cómo autentica
el pipeline contra el registry.

Esta decisión interactúa con:

- **ADR-0010**, que fija AWS EC2 como infraestructura.
- **ADR-0011**, que define los workflows de GitHub Actions.
- **ADR-0019**, que pone todo bajo Terraform incluyendo IAM.

## Drivers de la decisión

- **Alineación con AWS.** Dado que EC2 está en AWS (ADR-0010) y que vamos a
  usar IAM para el rol de la instancia y S3 para el state de Terraform
  (ADR-0019), centralizar el registry en AWS reduce superficie y permisos.
- **Costo.** El TP cuenta con créditos educativos AWS. ECR cobra
  almacenamiento + egress, cubierto por los créditos durante el TP.
- **Privacidad del código.** El contenido de las imágenes incluye lógica
  propietaria del cliente (aunque simulado en el TP) y no debe ser público.
- **Autenticación del pipeline.** Preferimos autenticación federada (OIDC)
  desde GitHub Actions hacia AWS, para no pegar credenciales de larga vida en
  secrets. ECR integra directamente con IAM.
- **Consistencia de herramientas.** Usar un solo plano de control
  (Terraform + AWS) facilita la adopción y el debugging.

## Opciones consideradas

1. **AWS ECR privado.**
2. **GitHub Container Registry (`ghcr.io`) privado.**
3. **Docker Hub privado (plan Pro).**

## Decisión

Usamos **AWS ECR privado** como único registry de Predictiva. Todas las
imágenes (backend, mock API, workers cuando existan) se publican allí con el
formato:

```text
<acct>.dkr.ecr.us-east-1.amazonaws.com/predictiva/<componente>:<tag>
```

Los `tag` siguen el esquema:

- `dev-pr-<número>` → entornos efímeros por PR.
- `staging-<sha_corto>` → cada merge a `main`.
- `v<semver>` → cada tag anotado en `main` (disparo de producción).
- `latest` → **no se usa** (prohibido en Terraform del entorno prod).

La autenticación desde GitHub Actions usa **OIDC**, asumiendo un rol IAM con
permisos acotados a `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`,
`ecr:PutImage`, `ecr:InitiateLayerUpload` y `ecr:UploadLayerPart`. La EC2
tiene un rol IAM distinto con permisos de solo lectura (`ecr:BatchGetImage`,
`ecr:GetDownloadUrlForLayer`).

Habilitamos **image scanning "scan on push"** en modo básico (gratuito) para
alertar sobre CVEs conocidas.

Las imágenes son **privadas**.

## Consecuencias

### Positivas

- Integración nativa con IAM: no hay que gestionar usuarios y passwords de
  registry; OIDC + roles cumplen con buenas prácticas modernas.
- `scan on push` da una primera línea de defensa contra CVEs sin costo extra.
- Terraform (ADR-0019) puede crear y versionar los repos de ECR, lifecycle
  policies y permisos en un solo lugar.
- El egress entre ECR y la EC2 dentro de la misma región es gratuito.

### Negativas

- Dependencia dura de AWS: si quisiéramos migrar el cómputo a otra nube en
  Fase 3, el registry viene con nosotros o lo reemplazamos.
- El `docker pull` desde máquinas locales de desarrolladores exige `aws
ecr get-login-password`, que no es complicado pero sí un paso más que
  `docker pull` anónimo.
- La autenticación OIDC requiere configurar un proveedor OIDC en IAM (costo
  único, gestionado por Terraform).

### Neutras

- Lifecycle policies: mantenemos las últimas 10 imágenes de `dev-pr-*` y las
  últimas 20 de `staging-*`; las `v*` (producción) se conservan
  indefinidamente hasta que se decida lo contrario.

## Pros y contras de las opciones

### Opción 1 — AWS ECR privado

- **Pros:**
  - Integración IAM/OIDC nativa.
  - Alineado con el resto del stack en AWS.
  - Gestionable vía Terraform.
  - Scan on push gratuito.
  - Egress gratis intra-región.
- **Contras:**
  - Acoplamiento a AWS.
  - URLs largas; requiere `aws ecr` CLI para login local.

### Opción 2 — `ghcr.io` privado

- **Pros:**
  - Gratuito para repositorios privados (sujeto a cuotas del plan GitHub).
  - Autenticación trivial desde GitHub Actions con `GITHUB_TOKEN`.
  - URLs más amigables.
- **Contras:**
  - Requiere sincronizar permisos entre GitHub y AWS (dos planos de control).
  - Egress hacia EC2 pasa por Internet público; añade latencia y consumo de
    créditos AWS en tráfico de entrada (entrante a EC2 sí es gratis, pero la
    velocidad depende del ancho de banda de GitHub).
  - Menos integrado con herramientas AWS como `Inspector`.

### Opción 3 — Docker Hub privado

- **Pros:**
  - Marca conocida.
- **Contras:**
  - Plan privado es pago; los rate limits del free tier son un riesgo
    operacional concreto (pulls anónimos limitados por IP).
  - Sin ventaja frente a ECR o ghcr.io.

## Referencias

- ADR-0008 — Modelo de entornos dev/staging/prod.
- ADR-0010 — AWS EC2 + Docker Compose + Traefik.
- ADR-0011 — GitHub Actions workflows.
- ADR-0014 — Estructura de imágenes Docker.
- ADR-0019 — Terraform gestiona ECR, IAM y OIDC.
- AWS ECR docs — private repositories, lifecycle policies, image scanning.
- GitHub Actions — OIDC with AWS.
