# ADR-0008: Topología de ambientes (dev / staging / producción)

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 exige automatizar el despliegue a **tres
ambientes: desarrollo, staging y producción**. El PRD además exige
disponibilidad del 99.5% para la API de producción y verificación
automática de salud post-deployment.

Debemos definir:

- Dónde corre cada ambiente físicamente.
- Qué evento dispara un deploy a cada uno.
- Qué URL identifica a cada ambiente.
- Qué datos usa cada ambiente.
- Cómo se relaciona esta topología con la estrategia de branching
  definida en ADR-0004.

Esta decisión es **bloqueante** para escribir cualquier pipeline de
CI/CD: el pipeline concreto depende de esta topología.

## Drivers de la decisión

- El equipo cuenta con créditos AWS educativos, habilitando uso de EC2.
- Disponemos de un dominio propio, habilitando URLs limpias por ambiente.
- Equipo de 3 personas con proyecto de ~3 meses: la infraestructura debe
  poder administrarse sin operaciones complejas.
- La URL de producción es el entregable evaluable: debe ser estable y
  no reflejar código en desarrollo.
- El trunk-based definido en ADR-0004 se mantiene: una sola branch
  (`main`) alimenta los despliegues.
- Se deben poder revisar features en aislamiento antes de mergear
  (objetivo mencionado en conversación inicial del equipo).

## Opciones consideradas

1. **Un solo ambiente de producción**, sin staging ni dev deployados.
2. **Tres ambientes en una misma instancia EC2**, diferenciados por
   subdominio y red Docker.
3. **Tres instancias EC2 distintas**, una por ambiente.
4. **Servicios AWS managed** (ECS Fargate, App Runner) con tres servicios.

## Decisión

Adoptamos **Opción 2: tres ambientes en una misma instancia EC2**,
diferenciados por subdominio y manejados por un reverse proxy.

### Topología

| Ambiente          | URL                           | Disparador                    | Ciclo de vida                      | Base de datos                           |
| ----------------- | ----------------------------- | ----------------------------- | ---------------------------------- | --------------------------------------- |
| **Preview (dev)** | `pr-<N>.dev.<dominio>`        | Apertura o push a un PR       | Efímero (se destruye al cerrar PR) | Efímera por PR                          |
| **Staging**       | `staging.<dominio>`           | Merge a `main` (automático)   | Permanente                         | Persistente, dataset completo sintético |
| **Producción**    | `<dominio>` o `app.<dominio>` | Creación de tag `v*` (manual) | Permanente                         | Persistente, dataset completo sintético |

**Infraestructura física:**

- Una única instancia EC2 (tamaño `t3.small` o `t3.medium` según volumen,
  ajustable).
- Docker Engine + Docker Compose como runtime de containers.
- **Traefik** como reverse proxy con terminación TLS automática
  (Let's Encrypt) y enrutamiento por subdominio a containers.
- Una red Docker por ambiente (`predictiva-prod`, `predictiva-staging`,
  `predictiva-pr-<N>`) para aislamiento lógico.
- PostgreSQL en contenedor por ambiente (tres containers independientes
  para los ambientes permanentes, efímero por PR).

**DNS:**

- `A` record apuntando el dominio a la IP de la EC2.
- `CNAME` wildcards (`*.dev.<dominio>`) para preview environments.

### Relación con branching (ADR-0004)

La topología de deployment es **ortogonal** a la de branching. Mantenemos
una única branch permanente (`main`). Las reglas de promoción son:

```
Pull Request abierto      →  Preview env efímero en pr-<N>.dev.<dominio>
Merge a main              →  Deploy automático a staging.<dominio>
Tag v* creado en main     →  Deploy manual-confirmado a <dominio>
```

El deploy a producción **requiere crear un tag** (`git tag v1.0.0 && git
push --tags`). Esto previene deploys accidentales a la URL que ve el
evaluador.

### Datos por ambiente

- **Preview / Dev:** base de datos efímera, sembrada con un dataset
  sintético pequeño (~10 pozos, 2 años de histórico) al crearse.
- **Staging:** base de datos persistente con dataset sintético completo
  (~50 pozos, 10 años). Puede resetearse manualmente si se corrompe.
- **Producción:** mismo dataset que staging durante el TP. No hay
  datos sensibles reales en ninguna fase, por lo que no hay
  consideraciones adicionales de privacidad o enmascaramiento.

Cada ambiente tiene **variables de entorno propias** (`.env` cargado
por el pipeline según ambiente). Nunca se comparten credenciales entre
ambientes.

## Consecuencias

**Positivas:**

- Tres ambientes reales con URLs limpias y estables.
- Producción protegida de cambios accidentales (requiere tag).
- Staging captura regresiones antes de producción.
- Preview environments permiten review visual de cada PR.
- Una sola EC2 simplifica administración y reduce costo de créditos.
- Trunk-based se mantiene sin contradicciones.

**Negativas / trade-offs asumidos:**

- Los tres ambientes comparten hardware. Si la EC2 cae, caen los tres.
  Aceptable para un TP; en producción real se usaría multi-AZ.
- El aislamiento es lógico (redes Docker) y no físico. Un container que
  consume todos los recursos puede afectar a los otros. Mitigable con
  `docker run --memory --cpus` por ambiente.
- Los preview environments consumen recursos mientras el PR esté abierto.
  Si hay muchos PRs simultáneos en EC2 pequeña, puede saturarse.
  Mitigado con `t3.small` holgada y reglas de cleanup automático.

**Neutras:**

- La elección de una sola EC2 es reversible: si el proyecto crece, se
  migran staging y prod a instancias separadas sin cambiar la lógica de
  deployment.

## Pros y contras de cada opción

### Opción 1 — Un solo ambiente de producción

- ✅ Infraestructura mínima.
- ❌ No cumple requisito explícito de la adenda (tres ambientes).
- ❌ Sin staging, los bugs llegan al evaluador.
- ❌ Sin dev, no hay forma de probar features antes de mergear.

### Opción 2 — Tres ambientes en una misma EC2 (elegida)

- ✅ Cumple el requisito de tres ambientes.
- ✅ Una sola instancia que administrar.
- ✅ Usa créditos AWS eficientemente.
- ✅ Compatible con preview environments por PR.
- ❌ Aislamiento lógico, no físico.

### Opción 3 — Tres EC2 distintas

- ✅ Aislamiento físico total.
- ❌ Triplica costos (tres instancias corriendo siempre).
- ❌ Mayor complejidad de configuración (tres hosts, tres Traefik, etc.).
- ❌ Sobredimensionado para el propósito del TP.

### Opción 4 — ECS Fargate / App Runner

- ✅ Managed: menos ops.
- ✅ Escalado automático.
- ❌ Más caro por hora que EC2.
- ❌ Oculta conceptos de Docker, networking y deployment que la
  materia explícitamente cubre. El TP gana valor pedagógico con EC2.
- ❌ Curva de aprendizaje de servicios AWS específicos.

## Referencias

- ADR-0004 (Estrategia de branching) — trunk-based compatible.
- ADR-0009 (Estrategia de deployment) — define cómo se promueve entre
  ambientes.
- ADR-0010 (Plataforma de hosting) — justifica EC2 + Docker.
- ADR-0011 (Plataforma de CI/CD) — implementa los disparadores de deploy.
- [The Twelve-Factor App — Dev/prod parity](https://12factor.net/dev-prod-parity)
- Adenda técnica de Fase 1 (requisito de tres ambientes).
