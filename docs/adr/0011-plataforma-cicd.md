# ADR-0011: Plataforma de CI/CD con GitHub Actions

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige un pipeline de CI/CD automatizado que:

- Ejecute tests automáticamente en cada PR.
- Haga análisis estático de código.
- Genere imágenes Docker inmutables.
- Deploye automáticamente a los ambientes definidos.
- Verifique salud post-deploy.
- Soporte recuperación automática ante fallos.

El código vive en GitHub (ADR-0003). La infraestructura es EC2
(ADR-0009). Los ambientes están definidos (ADR-0007) y la estrategia
de deploy también (ADR-0008).

Debemos decidir la plataforma que **orquesta** todo esto.

## Drivers de la decisión

- Integración nativa con el repositorio (preferencia por plataformas
  que vivan en GitHub).
- Capacidad de ejecutar acciones sobre la infraestructura remota (SSH a
  EC2, push a container registry).
- Soporte para secrets (API keys, SSH keys) sin exponerlos en código.
- Ecosistema de acciones reutilizables.
- Gratis o bajo costo para el volumen del TP.

## Opciones consideradas

1. **GitHub Actions** (nativo del repo).
2. **GitLab CI** (requiere migrar el repo).
3. **CircleCI / Travis / Drone** (terceros externos).
4. **Jenkins** self-hosted.
5. **AWS CodePipeline / CodeBuild** (nativo de AWS).

## Decisión

Adoptamos **GitHub Actions** como plataforma de CI/CD.

### Estructura de workflows

```
.github/workflows/
├── ci.yml                    # Tests, lint, build — en cada PR
├── deploy-preview.yml        # Deploy a preview env — en PR opened/updated
├── deploy-preview-cleanup.yml # Destruye preview env — en PR closed
├── deploy-staging.yml        # Deploy a staging — en merge a main
└── deploy-production.yml     # Deploy a producción — en tag v*
```

### Workflow `ci.yml` (se ejecuta en cada PR)

**Jobs (en paralelo donde sea posible):**

1. **Lint** — Ejecuta los linters definidos en ADR-0006
   (ruff, eslint, prettier, markdownlint). Falla el PR si hay errores.
2. **Type-check** — `mypy` para Python, `tsc --noEmit` para TypeScript.
3. **Unit tests** — Ejecuta tests unitarios en cada servicio.
4. **Integration tests** — Levanta stack mínimo con `docker compose` y
   corre tests de integración contra la API.
5. **Build images** — Construye imágenes Docker para cada servicio.
   Las etiqueta con el SHA del commit y las sube al container registry
   (ghcr.io, definido en ADR propio pendiente).
6. **Vulnerability scan** — Corre Trivy contra las imágenes
   construidas. Advierte sobre CVEs críticas sin fallar por default
   (configurable).
7. **OpenAPI contract validation** — Valida que los endpoints
   implementados cumplan la spec OpenAPI de la adenda.

Todos los jobs deben pasar para poder mergear (branch protection
rule de ADR-0004).

### Workflow `deploy-preview.yml`

Disparador: `pull_request` (opened, synchronize, reopened).

**Pasos:**

1. Construye o descarga las imágenes del PR (tag = SHA del commit).
2. SSH a la EC2 usando una clave guardada en GitHub Secrets.
3. Ejecuta `docker compose -f compose.preview.yml --project-name pr-<N> up -d`
   en la EC2, con variables de entorno específicas del PR.
4. Configura el subdominio `pr-<N>.dev.<dominio>` vía labels de Traefik.
5. Espera a que `/health/ready` responda OK.
6. Comenta en el PR con la URL del preview y un summary de health.

### Workflow `deploy-preview-cleanup.yml`

Disparador: `pull_request` closed.

**Pasos:**

1. SSH a la EC2.
2. Ejecuta `docker compose --project-name pr-<N> down -v` (elimina
   containers y volúmenes del PR).
3. Comenta en el PR confirmando el teardown.

### Workflow `deploy-staging.yml`

Disparador: `push` a `main`.

**Pasos:**

1. Construye imágenes con tag `staging-<SHA>` y `staging-latest`.
2. SSH a la EC2.
3. `docker compose pull` + `docker compose up -d` sobre el stack de
   staging, aplicando **rolling update** con `--no-stop-on-error`.
4. Espera `/health/ready` en ambas réplicas.
5. Consulta `/health` y verifica que la versión sea la esperada.
6. **Si algún check falla**, ejecuta rollback:
   - `docker compose` con el tag de la versión previa.
   - Verifica que la versión previa vuelva a estar healthy.
   - Marca el job como fallido.
7. Notifica al equipo.

### Workflow `deploy-production.yml`

Disparador: `push` de un tag que matchea `v*`.

**Pasos:**

1. Verifica que el tag apunta a un commit en `main` (evita tags en
   branches sueltas).
2. Requiere aprobación manual de un segundo miembro del equipo
   (GitHub Environments con protection rules). Esto sustituye al
   "botón de promote".
3. Mismo flujo que staging, pero apuntando al stack de producción.
4. Health checks más estrictos: si algo falla, rollback automático
   inmediato.
5. Notificación al equipo con la URL de producción confirmando el
   deploy.

### Gestión de secrets

**Almacenados en GitHub Secrets, no en el repo:**

- `EC2_SSH_PRIVATE_KEY` — clave SSH para el usuario de deploy.
- `EC2_HOST` — DNS o IP de la instancia.
- `CONTAINER_REGISTRY_TOKEN` — si se usa registry con auth.
- `API_KEY_PROD`, `API_KEY_STAGING` — API keys de la aplicación
  (aunque para Fase 1 sea `abcdef12345`, se mantiene en secret para
  prácticas correctas).
- `DATABASE_URL_PROD`, `DATABASE_URL_STAGING`.

**Environments de GitHub:**

Configuramos tres environments (`preview`, `staging`, `production`)
con sus propias variables y reglas:

- `production` requiere approval de un segundo miembro para deploy.
- `staging` y `preview` deployan sin approval.

## Consecuencias

**Positivas:**

- Integración cero-fricción con el repo (push, PR events, tags).
- Ecosistema amplio de actions (docker/build-push-action, ssh-action,
  etc.) que cubren 90% del trabajo sin escribir shell.
- Secrets management integrado.
- Environments de GitHub dan "approval gates" sin necesidad de
  herramientas adicionales.
- Gratuito para repos públicos; límite generoso para privados.
- Logs de cada run quedan visibles en la UI de GitHub para auditoría.

**Negativas / trade-offs asumidos:**

- GitHub Actions como vendor lock-in suave. Migración a otra plataforma
  requiere reescribir workflows. Mitigable: los pasos internos son
  comandos de shell reusables.
- Los jobs corren en runners efímeros de GitHub: cold start en cada
  corrida. Para el volumen del TP, irrelevante.
- SSH desde GitHub Actions a EC2 expone la clave si no se gestiona
  correctamente. Mitigado con GitHub Secrets y un usuario SSH
  dedicado con permisos mínimos.

**Neutras:**

- Para Fase 1 no usamos self-hosted runners. Se evalúa en Fase 2+ si
  hay workloads pesadas (ej: entrenar modelos).

## Pros y contras de cada opción

### GitHub Actions (elegida)

- ✅ Nativo del repo.
- ✅ Gratis para el volumen del TP.
- ✅ Environments con approval gates.
- ❌ Vendor lock-in suave.

### GitLab CI

- ✅ Excelente CI/CD, muy maduro.
- ❌ Requiere migrar el repo a GitLab.

### CircleCI / Travis

- ✅ Independiente del hosting del repo.
- ❌ Requiere cuenta separada, configuración de webhooks.
- ❌ Ecosistema menor que GitHub Actions.

### Jenkins self-hosted

- ✅ Control total.
- ❌ Overhead operativo enorme para un TP.
- ❌ Es la plataforma menos querida por los desarrolladores.

### AWS CodePipeline

- ✅ Nativo de AWS, integración profunda con servicios AWS.
- ❌ DX significativamente peor que GitHub Actions.
- ❌ Configuración más compleja para casos simples.

## Referencias

- ADR-0003 (Monorepo — repo en GitHub).
- ADR-0004 (Branching — PR-centric).
- ADR-0008 (Topología de ambientes).
- ADR-0009 (Estrategia de deployment).
- ADR-0010 (Hosting en EC2).
- [GitHub Actions — Docs](https://docs.github.com/en/actions)
- [GitHub Environments and deployment protection rules](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- Adenda técnica de Fase 1 (requisitos citados).
