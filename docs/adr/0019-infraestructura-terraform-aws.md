# ADR-0019: Infraestructura como código con Terraform sobre AWS para previews, staging y producción

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

ADR-0008 define tres ambientes separados y ADR-0010 fija AWS EC2 con Docker
Swarm como plataforma de hosting. Dado que la adenda técnica exige un
despliegue reproducible, auditable y versionado, necesitamos decidir:

1. Si usamos infraestructura como código (IaC) y con qué herramienta.
2. Dónde vive el state y cómo se evita corrupción por concurrencia.
3. Qué recursos gestiona IaC.
4. Cómo modelamos previews, staging y producción.
5. Dónde gestionamos DNS.
6. Qué rol cumplen S3, CloudWatch e IAM/OIDC.

## Drivers de la decisión

- Reproducibilidad: reconstruir la infraestructura desde el repo.
- Auditoría: cambios de infraestructura por Pull Request.
- Colaboración segura: tres personas pueden tocar infra.
- Separación de ambientes: preview/dev, staging y prod no deben compartir
  host.
- Integración con AWS: EC2, ECR, Route 53, S3, IAM y CloudWatch.
- Bajo costo con créditos educativos.
- Evitar operaciones manuales por consola que generen drift.

## Opciones consideradas

### Herramienta de IaC

- **Terraform.**
- **OpenTofu.**
- **Scripts bash.**
- **Pulumi.**
- **AWS CDK.**

### Terraform state

- **S3 + DynamoDB lock.**
- **S3 sin lock.**
- **State local commiteado o compartido manualmente.**
- **Terraform Cloud.**

### Scope de recursos

- **Todo bajo IaC**: red, EC2, IAM, ECR, S3, Route 53, CloudWatch.
- **Solo EC2 + Security Groups.**
- **Solo recursos críticos; resto manual.**

### Organización de ambientes

- **Tres root modules** (`envs/preview`, `envs/staging`, `envs/prod`).
- **Un root module con variables por ambiente.**
- **Un único ambiente compartido.**

## Decisión

Adoptamos **Terraform** como herramienta de IaC, con state remoto en
**S3 + DynamoDB lock**.

### Estructura

```text
infra/
├── modules/
│   ├── ec2-swarm-node/
│   ├── ecr/
│   ├── route53/
│   ├── s3-state/
│   ├── s3-artifacts/
│   ├── iam-github-oidc/
│   └── cloudwatch/
└── envs/
    ├── preview/
    ├── staging/
    └── prod/
```

Cada environment root usa los módulos compartidos y define sus diferencias:

- `preview`: EC2 para previews efímeros por PR y wildcard
  `*.dev.petrocast.shop`.
- `staging`: EC2 persistente para `staging.petrocast.shop`.
- `prod`: EC2 persistente para `api.petrocast.shop`.

### Backend del state

El state vive en S3:

```text
s3://<bucket-terraform-state>/petrocast/<env>/terraform.tfstate
```

La tabla DynamoDB provee locking para evitar `apply` concurrentes.

El bucket de state tiene:

- Versionado activado.
- Encriptación server-side.
- Bloqueo de acceso público.

El bucket y la tabla se bootstrappean una vez desde
`infra/modules/s3-state/` o un root bootstrap mínimo. Luego el resto de la
infra usa backend remoto.

### Recursos gestionados

Terraform gestiona:

- VPC, subnets, Internet Gateway y route tables.
- Security Groups.
- EC2 `swarm-preview-dev`, `swarm-staging`, `swarm-prod`.
- Elastic IPs.
- Key pairs si SSH se usa como fallback.
- IAM role para GitHub Actions vía OIDC.
- IAM instance profiles para EC2.
- ECR repository `petrocast/mock-api`.
- ECR lifecycle policies.
- Route 53 hosted zone y records:

```text
*.dev.petrocast.shop   -> EC2 preview
staging.petrocast.shop -> EC2 staging
api.petrocast.shop     -> EC2 prod
```

- S3 buckets:
  - `terraform-state`
  - `pipeline-artifacts`
  - `test-reports`
- CloudWatch log groups para:
  - logs de aplicación
  - logs de Traefik
  - logs de scripts de deploy
- Parámetros básicos para Systems Manager si se adopta SSM Run Command.

Quedan fuera de Terraform:

- Secrets de aplicación (`API_KEY`, etc.), que viven en GitHub Environments
  según ADR-0018.
- Datos de prueba cargados en la aplicación.

### Región y tamaño

- **Región:** `us-east-1`.
- **Instancias iniciales:** `t3.small` para preview, staging y producción.

Justificación:

- `us-east-1` tiene menor costo, buena disponibilidad de servicios y soporte
  amplio para créditos educativos.
- `t3.small` mantiene margen para Docker, Traefik, dos réplicas en staging y
  producción, y múltiples previews pequeños.
- Si el presupuesto aprieta, preview puede bajarse a `t3.micro` como cambio
  de variable. Si Fase 2/3 crecen, staging/prod pueden subir a `t3.medium`.

### S3 para artefactos

S3 no sirve la API. Se usa como almacenamiento durable para:

1. State remoto de Terraform.
2. Artefactos del pipeline.
3. Reportes de tests, coverage y security scan.

Esto evita cargar el repositorio con reportes generados y deja evidencia de
CI/CD por ejecución.

### IAM/OIDC

Terraform crea el proveedor OIDC de GitHub y roles con permisos mínimos:

- Rol de CI para publicar imágenes en ECR y subir reportes a S3.
- Rol de deploy para ejecutar SSM Run Command o acciones equivalentes.
- Instance profile de EC2 con permisos de solo lectura sobre ECR y escritura
  limitada de logs a CloudWatch.

## Consecuencias

**Positivas:**

- Toda la infraestructura crítica queda versionada y revisable.
- El state remoto con lock evita corrupción por concurrencia.
- Los ambientes quedan modelados explícitamente y separados.
- Route 53, ECR, IAM y S3 comparten un único plano de control.
- OIDC elimina credenciales AWS long-lived en GitHub.
- S3 centraliza state y artefactos sin mezclarlo con la aplicación.

**Negativas / trade-offs asumidos:**

- Terraform suma curva de aprendizaje.
- El bootstrap de S3/DynamoDB requiere un paso inicial.
- Tres EC2 elevan costo frente a una única instancia.
- Gestionar tres root modules exige disciplina para no duplicar lógica.

**Neutras:**

- OpenTofu queda como alternativa compatible si el equipo decide evitar
  Terraform en el futuro.
- La estructura modular permite migrar prod a dos nodos Swarm sin rediseñar
  preview y staging.

## Pros y contras de cada opción

### Terraform (elegida)

- ✅ Estándar de facto.
- ✅ Provider AWS maduro.
- ✅ State remoto y locking bien entendidos.
- ✅ Fácil de revisar por PR.
- ❌ HCL y state management agregan curva.

### OpenTofu

- ✅ Compatible conceptualmente con Terraform.
- ✅ Alternativa open source.
- ❌ Menor adopción en cursos/documentación general.

### Scripts bash

- ✅ Simples al principio.
- ❌ No idempotentes.
- ❌ Sin plan previo.
- ❌ Drift casi garantizado.

### Pulumi / AWS CDK

- ✅ IaC en lenguajes conocidos.
- ❌ Más abstracción y curva para el TP.
- ❌ CDK acopla fuerte a CloudFormation.

### S3 + DynamoDB para state (elegida)

- ✅ Patrón estándar en AWS.
- ✅ Barato.
- ✅ Locking real.
- ✅ Versionado del state.
- ❌ Bootstrap inicial.

### State local

- ✅ Cero infraestructura inicial.
- ❌ Riesgo de pérdida o corrupción.
- ❌ Puede contener datos sensibles.
- ❌ No escala a tres personas.

### Tres root modules (elegida)

- ✅ Separa cambios por ambiente.
- ✅ Reduce riesgo de aplicar prod accidentalmente.
- ✅ Permite variables y policies específicas.
- ❌ Algo más de estructura inicial.

### Un único root module

- ✅ Menos archivos.
- ❌ Más riesgo de confundir workspaces o variables.
- ❌ Menos explícito para el evaluador.

## Referencias

- ADR-0008 (Topología de ambientes).
- ADR-0009 (Deployments y rollback).
- ADR-0010 (Hosting EC2 + Swarm).
- ADR-0011 (GitHub Actions + OIDC).
- ADR-0013 (ECR).
- ADR-0017 (Observabilidad y CloudWatch).
- ADR-0018 (Secrets en GitHub, no en Terraform).
- Terraform AWS Provider docs.
- AWS S3 backend para Terraform.
- AWS DynamoDB state locking.
- AWS Route 53 wildcard records.
- GitHub Actions OIDC with AWS.
- AWS Systems Manager Run Command.
