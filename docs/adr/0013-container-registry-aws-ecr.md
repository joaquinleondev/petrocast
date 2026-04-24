# ADR-0013: Container registry privado en AWS ECR y promoción del mismo artefacto

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica exige generar artefactos inmutables (imágenes Docker) como
parte del pipeline de CI/CD y publicarlos en un registry privado. ADR-0008 y
ADR-0010 definen que previews, staging y producción corren en EC2 con Docker
Swarm, por lo que los nodos necesitan descargar imágenes desde un registry.

También debemos decidir cómo versionar esas imágenes para evitar un problema
común: reconstruir una imagen distinta por ambiente y perder la garantía de
que producción ejecuta exactamente lo validado en staging.

## Drivers de la decisión

- Alineación con AWS: usamos EC2, Route 53, IAM/OIDC, S3 y CloudWatch.
- Privacidad: las imágenes no deben ser públicas.
- Autenticación moderna: GitHub Actions debe publicar en el registry sin
  access keys permanentes.
- Trazabilidad: cada deploy debe apuntar a un commit, digest y tag claros.
- Bajo costo: los créditos AWS cubren ECR durante el TP.
- Limpieza automática: los tags efímeros de PR no deben acumularse
  indefinidamente.

## Opciones consideradas

1. **AWS ECR privado.**
2. **GitHub Container Registry (`ghcr.io`) privado.**
3. **Docker Hub privado.**

## Decisión

Usamos **AWS ECR privado** como registry único para Petrocast.

Formato de repositorio:

```text
<account>.dkr.ecr.<region>.amazonaws.com/petrocast/mock-api:<tag>
```

### Estrategia de tags

La imagen canónica de un commit es:

```text
mock-api:sha-<sha_corto>
```

Los tags por flujo apuntan al mismo digest:

```text
Preview PR:
  mock-api:pr-123-<sha_corto>

Main / staging:
  mock-api:sha-<sha_corto>
  mock-api:staging-latest

Release / producción:
  mock-api:v1.0.0
```

Regla central:

```text
build once -> promote same artifact
```

Producción no reconstruye la imagen. El workflow resuelve el digest de
`sha-<sha_corto>` ya validado y lo etiqueta como `v*`. De esta forma, si
staging pasó smoke tests con un digest, producción usa ese mismo digest.

### Tags prohibidos o restringidos

- `latest` queda prohibido para despliegues.
- `staging-latest` se permite solo como alias operativo de staging, nunca
  como referencia para producción.
- Producción solo puede usar tags `v*` o digests explícitos.

### Autenticación

GitHub Actions autentica contra AWS usando OIDC y asume un rol IAM con
permisos mínimos para publicar imágenes:

- `ecr:GetAuthorizationToken`
- `ecr:BatchCheckLayerAvailability`
- `ecr:InitiateLayerUpload`
- `ecr:UploadLayerPart`
- `ecr:CompleteLayerUpload`
- `ecr:PutImage`

Las EC2 tienen un rol IAM de solo lectura para descargar imágenes:

- `ecr:BatchGetImage`
- `ecr:GetDownloadUrlForLayer`
- `ecr:GetAuthorizationToken`

### Scanning y lifecycle

Habilitamos scan on push en ECR para detectar CVEs conocidas.

Lifecycle policies:

- Expirar tags `pr-*` después de 7 días o mantener solo los últimos N por
  repositorio.
- Mantener los últimos 20 tags `sha-*`.
- Mantener tags `v*` indefinidamente hasta que el equipo decida una política
  de retención de releases.
- Mantener `staging-latest` como alias mutable.

## Consecuencias

**Positivas:**

- ECR se integra naturalmente con IAM, OIDC y EC2.
- No hay credenciales long-lived para publicar imágenes.
- La trazabilidad por digest evita dudas sobre qué corrió en cada ambiente.
- `build once -> promote same artifact` reduce riesgo de diferencias entre
  staging y producción.
- Lifecycle policies controlan el crecimiento de imágenes de PR.

**Negativas / trade-offs asumidos:**

- Acoplamiento a AWS.
- Los developers necesitan `aws ecr get-login-password` para hacer pulls
  locales.
- OIDC e IAM requieren configuración inicial vía Terraform.
- ECR tiene URLs más largas que GHCR.

**Neutras:**

- Si en el futuro se migra el runtime a otra nube, las imágenes pueden
  republicarse en otro registry sin cambiar el Dockerfile.

## Pros y contras de las opciones

### AWS ECR privado (elegida)

- ✅ Integración con IAM/OIDC.
- ✅ Alineado con EC2, Terraform y AWS.
- ✅ Lifecycle policies y scan on push.
- ✅ Egress dentro de AWS simple de operar.
- ❌ Acoplamiento a AWS.

### GHCR privado

- ✅ Integración trivial con GitHub Actions.
- ✅ URLs más amigables.
- ❌ Segundo plano de permisos separado de AWS.
- ❌ EC2 debe autenticar contra GitHub en runtime.

### Docker Hub privado

- ✅ Muy conocido.
- ❌ Plan privado pago.
- ❌ Rate limits y menor integración con AWS.
- ❌ Sin ventaja concreta sobre ECR en este proyecto.

## Referencias

- ADR-0008 (Topología de ambientes).
- ADR-0009 (Deployments y rollback).
- ADR-0010 (EC2 + Docker Swarm).
- ADR-0011 (GitHub Actions + OIDC).
- ADR-0014 (Imágenes Docker).
- ADR-0019 (Terraform gestiona ECR e IAM).
- AWS ECR — private repositories.
- AWS ECR — lifecycle policies.
- GitHub Actions — OIDC with AWS.
