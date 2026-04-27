# ADR-0011: Plataforma de CI/CD con GitHub Actions, OIDC y despliegue a Docker Swarm

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige un pipeline de CI/CD automatizado que:

- Ejecute tests automáticamente en cada PR.
- Haga análisis estático de código.
- Genere imágenes Docker inmutables.
- Publique las imágenes en un registry privado.
- Deploye a previews/dev, staging y producción.
- Verifique salud post-deploy.
- Soporte rollback automático ante fallos.

El código vive en GitHub (ADR-0003), los ambientes corren en EC2 con Docker
Swarm (ADR-0008 y ADR-0010), las imágenes se guardan en ECR (ADR-0013) y el
rollout usa Swarm (ADR-0009). Debemos decidir quién orquesta ese flujo y cómo
se autentica contra AWS.

## Drivers de la decisión

- Integración nativa con Pull Requests, pushes y tags de GitHub.
- Autenticación contra AWS sin access keys permanentes.
- Capacidad de publicar imágenes en ECR.
- Capacidad de ejecutar despliegues remotos sobre EC2/Swarm.
- Soporte de secrets y reglas por ambiente.
- Bajo costo para el volumen del TP.
- Evidencia clara del proceso en logs de pipeline.

## Opciones consideradas

1. **GitHub Actions + OIDC hacia AWS.**
2. **GitLab CI** (requiere migrar el repo).
3. **CircleCI / Travis / Drone**.
4. **Jenkins self-hosted.**
5. **AWS CodePipeline / CodeBuild.**

## Decisión

Adoptamos **GitHub Actions** como plataforma de CI/CD, autenticada contra AWS
mediante **OIDC** y roles IAM de corta duración.

No guardamos access keys permanentes de AWS como secrets. GitHub Actions
asume un rol IAM autorizado para:

- Publicar y leer imágenes en ECR.
- Subir artefactos a S3.
- Ejecutar despliegues remotos vía AWS Systems Manager Run Command, o SSH
  restringido como fallback inicial.
- Leer/escribir información mínima necesaria para Terraform según el workflow.

### Principio de imágenes

Adoptamos el patrón:

```text
build once -> promote same artifact
```

Para cada commit deployable se construye una imagen canónica:

```text
mock-api:sha-<sha_corto>
```

Los tags por ambiente son alias útiles, no builds distintos:

```text
PR:      mock-api:pr-123-<sha_corto>
main:    mock-api:sha-<sha_corto>, mock-api:staging-latest
release: mock-api:v1.0.0
```

Producción toma el digest ya validado en staging y lo etiqueta como `v*`.
Esto evita que "lo que se probó" y "lo que se deployó" sean artefactos
distintos.

### Estructura de workflows

```text
.github/workflows/
├── ci.yml
├── deploy-preview.yml
├── deploy-preview-cleanup.yml
├── deploy-staging.yml
└── deploy-production.yml
```

### Workflow `ci.yml`

Disparador: `pull_request` y `push` a `main`.

Jobs:

1. **Static analysis:** `pre-commit run --all-files`, Ruff, mypy,
   markdownlint y yamllint.
2. **Tests:** unit, integration y contract tests con coverage mínimo.
3. **Build:** construir imagen Docker.
4. **Security scan:** escaneo de vulnerabilidades de la imagen.
5. **Artifacts:** subir reportes de tests, coverage y scan a S3
   (`test-reports` / `pipeline-artifacts`) cuando aplique.

En PRs, si CI pasa, el workflow de preview puede publicar la imagen en ECR y
desplegar el stack efímero.

### Workflow `deploy-preview.yml`

Disparador: `pull_request` opened, synchronize, reopened.

Flujo:

```text
1. Ejecutar CI.
2. Construir imagen mock-api:sha-<sha> y alias pr-<N>-<sha>.
3. Publicar imagen en ECR.
4. Ejecutar docker stack deploy pr-<N> en EC2 swarm-preview-dev.
5. Traefik enruta pr-<N>.dev.<dominio> al servicio del PR.
6. Ejecutar smoke tests contra la URL del preview.
7. Comentar en el PR con la URL y resultado del health check.
```

### Workflow `deploy-preview-cleanup.yml`

Disparador: `pull_request` closed.

Flujo:

```text
1. Ejecutar docker stack rm pr-<N> en EC2 swarm-preview-dev.
2. Eliminar recursos efímeros asociados al PR si existen.
3. Comentar en el PR confirmando el teardown.
```

### Workflow `deploy-staging.yml`

Disparador: `push` a `main`.

Flujo:

```text
1. Ejecutar CI sobre el commit de main.
2. Construir/publicar mock-api:sha-<sha>.
3. Actualizar alias staging-latest al mismo digest.
4. Ejecutar docker stack deploy staging en EC2 swarm-staging.
5. Esperar rolling update de Swarm.
6. Consultar /health/ready.
7. Ejecutar smoke tests contra staging.<dominio>.
8. Si falla health o smoke, ejecutar docker service rollback staging_mock-api.
```

Staging no requiere aprobación manual: debe moverse rápido y representar el
estado integrado de `main`.

### Workflow `deploy-production.yml`

Disparador: tag `v*` apuntando a un commit alcanzable desde `main`.

Flujo:

```text
1. Verificar que el tag apunta a main.
2. Resolver el digest mock-api:sha-<sha> ya construido.
3. Etiquetar ese digest como mock-api:v<semver>.
4. Requerir aprobación manual vía GitHub Environment production.
5. Ejecutar docker stack deploy prod en EC2 swarm-prod.
6. Esperar rolling update de Swarm.
7. Ejecutar smoke tests contra api.<dominio>.
8. Si falla, ejecutar docker service rollback prod_mock-api.
```

Producción usa GitHub Environment `production` con required reviewers y
secrets propios.

### Despliegue remoto

Opción preferida:

- **AWS Systems Manager Run Command** para ejecutar comandos en EC2 sin abrir
  SSH público.

Fallback aceptado para primera iteración:

- SSH restringido desde GitHub Actions al usuario de deploy.
- Security Group limitado.
- Clave guardada como GitHub Secret hasta migrar a SSM.

El ADR favorece SSM como estado objetivo por seguridad, pero permite SSH si
el tiempo de Fase 1 exige reducir setup inicial.

### Gestión de secrets

**GitHub Environments:**

- `preview`
- `staging`
- `production`

Secrets por ambiente:

- `API_KEY`.
- Variables de smoke tests.
- Parámetros de despliegue no sensibles.

Credenciales AWS:

- No se guardan access keys permanentes.
- GitHub Actions usa OIDC para asumir roles IAM con permisos mínimos.

## Consecuencias

**Positivas:**

- Integración directa con PRs, `main` y tags.
- OIDC elimina credenciales AWS long-lived.
- GitHub Environments dan approvals y secrets por ambiente.
- Los previews se crean y destruyen automáticamente.
- Staging y producción usan el mismo artefacto validado.
- Rollback queda cubierto por Swarm y por smoke tests del pipeline.

**Negativas / trade-offs asumidos:**

- OIDC + IAM requiere configuración inicial más cuidadosa.
- SSM Run Command agrega permisos y setup de agente; SSH puede ser necesario
  como primer paso.
- Build once requiere disciplina: no reconstruir silenciosamente en
  producción.
- Los workflows son más largos que un deploy simple por SSH.

**Neutras:**

- Si en Fase 2 se adopta ECS/Kubernetes, GitHub Actions y OIDC siguen
  vigentes; cambiaría el job de deploy, no el modelo completo.

## Pros y contras de cada opción

### GitHub Actions + OIDC (elegida)

- ✅ Nativo del repo.
- ✅ Sin credenciales AWS permanentes.
- ✅ Environments con approvals y secrets.
- ✅ Buen ecosistema para Docker, ECR, S3 y AWS.
- ❌ Vendor lock-in suave con GitHub.

### GitLab CI

- ✅ CI/CD maduro.
- ❌ Requiere migrar el repo o duplicar integración.

### CircleCI / Travis / Drone

- ✅ Plataformas conocidas.
- ❌ Cuenta y configuración adicional.
- ❌ Menor integración con PRs y environments de GitHub.

### Jenkins

- ✅ Control total.
- ❌ Overhead operativo desproporcionado para el TP.

### AWS CodePipeline / CodeBuild

- ✅ Integración profunda con AWS.
- ❌ Peor experiencia para PRs y reviews.
- ❌ Más configuración que GitHub Actions para este caso.

## Referencias

- ADR-0003 (Monorepo).
- ADR-0004 (Branching).
- ADR-0008 (Topología de ambientes).
- ADR-0009 (Rolling updates y rollback).
- ADR-0010 (Hosting en EC2 con Docker Swarm).
- ADR-0013 (ECR).
- ADR-0018 (Gestión de configuración).
- ADR-0019 (Terraform e IAM OIDC).
- GitHub Actions — OIDC with AWS.
- GitHub Actions — Environments.
- AWS Systems Manager Run Command.
- Docker Swarm — `docker stack deploy` y `docker service rollback`.
