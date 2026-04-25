# Terraform — Infraestructura AWS

## Prerequisitos manuales

1. **Dominio**: Registrar/delegar `petrocast.shop` a Route 53. Terraform crea la hosted zone y expone los NS como output. Tras `apply-shared`, copiar los 4 NS records al registrador.
2. **Bootstrap IAM**: Usuario IAM local con permisos admin solo para el primer `apply-bootstrap`. Tras eso, todos los applies usan OIDC.
3. **Herramientas**: `terraform >= 1.9`, `aws-cli >= 2`, `make`.

---

## Secuencia de applies

### 1. Bootstrap del state backend (una sola vez)

```bash
cd infra/terraform
make bootstrap
```

Crea:

- S3 bucket `petrocast-tf-state-<random>` (versioning + encryption)
- DynamoDB table `petrocast-tf-locks`

Guarda el output del bucket/table — se necesitan para crear `backend.config`.

Crear `infra/terraform/backend.config` (gitignoreado):

```hcl
bucket         = "<bucket-name-del-output>"
dynamodb_table = "petrocast-tf-locks"
region         = "us-east-1"
```

### 2. Shared (ECR, VPC, Route53, IAM OIDC, S3, CloudWatch)

```bash
make apply-shared
```

**Después de este apply:**

- Copiar los 4 NS records del output `route53_nameservers` al registrador del dominio.
- Esperar propagación DNS (~15–60 min).

### 3. Environments (EC2 + DNS records)

```bash
make apply-preview
make apply-staging
make apply-prod
```

Cada env crea: EC2 t3.small + EIP + Security Group + instancia profile IAM + record DNS (A record apuntando a la EIP).

### 4. Configurar GitHub Secrets

Tras los applies, obtener los valores con:

```bash
make output-shared
make output-preview
make output-staging
make output-prod
```

**Secrets a nivel repo (`Settings → Secrets → Actions`):**

| Secret            | Valor                                                             |
| ----------------- | ----------------------------------------------------------------- |
| `AWS_REGION`      | `us-east-1`                                                       |
| `ECR_REGISTRY`    | output `ecr_repository_url` de shared (sin `/petrocast/mock-api`) |
| `CI_ROLE_ARN`     | output `ci_role_arn` de shared                                    |
| `TF_ROLE_ARN`     | output `ci_role_arn` de shared (mismo rol)                        |
| `TF_STATE_BUCKET` | nombre del bucket del bootstrap                                   |
| `TF_LOCK_TABLE`   | `petrocast-tf-locks`                                              |
| `DOMAIN`          | `petrocast.shop`                                                  |
| `REPORTS_BUCKET`  | output `reports_bucket` de shared                                 |

**Secrets por environment (`Settings → Environments`):**

Environment `preview`:

| Secret                | Valor                              |
| --------------------- | ---------------------------------- |
| `DEPLOY_ROLE_ARN`     | output `deploy_role_arn` de shared |
| `PREVIEW_INSTANCE_ID` | output `instance_id` de preview    |
| `API_KEY`             | clave API del servicio             |

Environment `staging`:

| Secret                | Valor                              |
| --------------------- | ---------------------------------- |
| `DEPLOY_ROLE_ARN`     | output `deploy_role_arn` de shared |
| `STAGING_INSTANCE_ID` | output `instance_id` de staging    |
| `API_KEY`             | clave API del servicio             |

Environment `production`:

| Secret             | Valor                              |
| ------------------ | ---------------------------------- |
| `DEPLOY_ROLE_ARN`  | output `deploy_role_arn` de shared |
| `PROD_INSTANCE_ID` | output `instance_id` de prod       |
| `API_KEY`          | clave API del servicio             |

**Configurar environment `production` con required reviewers** (`Settings → Environments → production → Required reviewers`).

---

## Estructura de módulos

```
modules/
├── vpc/              — VPC /16, 2 subnets públicas, IGW
├── ec2-swarm-node/   — EC2 Ubuntu 22.04, EIP, SG (80/443), SSM-only
├── ecr/              — Repo ECR con lifecycle policies y scan on push
├── route53/          — Hosted zone + records DNS por env
├── s3-artifacts/     — Buckets artifacts y reports
├── iam-github-oidc/  — OIDC provider + ci-role + deploy-role
└── cloudwatch/       — Log groups por env, retención 14/30 días
```

## Makefile targets

```bash
make bootstrap         # one-shot: crea S3 state + DynamoDB
make plan-shared       # terraform plan para envs/shared
make apply-shared      # terraform apply para envs/shared
make plan-preview      # terraform plan para envs/preview
make apply-preview     # ...
make apply-staging
make apply-prod
make output-shared     # terraform output para envs/shared
make output-preview
make output-staging
make output-prod
make fmt               # terraform fmt -recursive
make validate-shared   # terraform validate para envs/shared
make destroy-preview   # terraform destroy (peligroso — confirmar)
```
