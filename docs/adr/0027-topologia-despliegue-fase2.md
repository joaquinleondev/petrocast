# ADR-0027: Topología de despliegue de Fase 2

- **Estado:** Aceptado
- **Fecha:** 2026-06-10
- **Autores:** Santino Domato
- **Decisores:** Equipo Petrocast

## Contexto y problema

La Fase 2 agrega una plataforma de datos sobre la API ya desplegada en AWS:
warehouse PostgreSQL con capas `bronze`, `silver` y `gold`, orquestación con
Dagster, transformaciones dbt, ingesta con dlt, BI con Metabase, observabilidad
con Prometheus/Grafana y gobierno de datos con DataHub.

ADR-0008, ADR-0010 y ADR-0019 ya fijan una base de despliegue para Fase 1:
tres ambientes sobre EC2 con Docker Swarm single-node, Traefik, Route 53,
GitHub Actions y Terraform. Esa topología funciona bien para una API liviana,
pero Fase 2 suma servicios persistentes y herramientas pesadas. En particular,
DataHub consume varios contenedores y memoria suficiente como para competir con
PostgreSQL, Dagster y Metabase en una instancia chica.

La adenda también exige que usuarios no técnicos puedan acceder al BI, que haya
una web de métricas para el rol Admin y que la plataforma de gobierno permita
navegar linaje. Por lo tanto, no alcanza con definir "corre local": necesitamos
una topología operable para demo, revisión y uso del equipo sin sobredimensionar
infraestructura.

## Drivers de la decisión

- **Costo acotado:** evitar multiplicar instancias o servicios managed para un
  TP académico con volumen de datos bajo.
- **Operabilidad:** mantener el modelo conocido de Docker Compose/Swarm,
  Traefik, GitHub Actions y SSM/Terraform.
- **Disponibilidad de consumo:** API, warehouse, BI, Dagster y métricas deben
  poder estar disponibles de forma estable para demo y validación.
- **Footprint de DataHub:** el gobierno de datos debe existir, pero no necesita
  correr 24/7 en el path crítico.
- **Acceso claro para Admin:** la web de métricas debe tener una URL y una forma
  de autenticación definida.
- **Separación de ambientes:** no mezclar previews efímeros con staging/prod ni
  compartir datos persistentes entre ambientes.
- **Reproducibilidad local:** el equipo debe poder levantar el stack de datos
  completo o casi completo con Compose para desarrollo y evaluación.

## Opciones consideradas

1. **Demo local con Docker Compose únicamente.**
2. **EC2 permanente con todo el stack de Fase 2 corriendo 24/7.**
3. **Topología híbrida:** servicios base permanentes y DataHub on-demand.
4. **Servicios managed o plataforma dedicada para datos.**

## Decisión

Elegimos una **topología híbrida**:

- **Local/dev:** Compose como camino reproducible para desarrollo y demo técnica.
- **Staging/prod:** servicios base persistentes sobre las EC2 Swarm existentes.
- **DataHub:** despliegue on-demand para ingesta de metadatos y exploración de
  linaje, no servicio 24/7.

### Servicios base persistentes

En staging y producción mantenemos corriendo los componentes que sostienen el
producto y la demo operativa:

| Componente | Ciclo de vida | Motivo |
| ---------- | ------------- | ------ |
| API FastAPI | Persistente | Servicio público y contrato existente |
| PostgreSQL DW | Persistente | Estado analítico `bronze/silver/gold` |
| Dagster | Persistente en staging/prod | Orquestación, logs y estado de runs |
| Metabase | Persistente | BI para usuarios no técnicos |
| Prometheus/Grafana | Persistente o perfil observability | Métricas y alertas del rol Admin |
| DataHub | On-demand | Catálogo y linaje navegable, alto footprint |

La implementación puede empaquetarse en `infra/compose.data.yml` para local y
en stacks Swarm equivalentes para staging/prod. Los datos persistentes viven en
volúmenes por ambiente o bases separadas; nunca se comparten entre preview,
staging y producción.

### DataHub on-demand

DataHub se levanta sólo cuando el equipo necesita:

1. Ingerir metadata desde dbt y PostgreSQL.
2. Refrescar el grafo de linaje.
3. Navegar el catálogo y documentar evidencia para la entrega.

Al terminar, se baja para liberar memoria. Esta decisión hereda ADR-0022:
DataHub es obligatorio para gobierno y linaje, pero no está en el path crítico
de ingesta, transformación, BI ni API.

### Acceso del Admin a métricas

El Admin accede a Grafana así:

- **Local/dev:** `http://localhost:3001`, levantado con
  `docker compose -f infra/compose.observability.yml up` o el perfil
  equivalente del stack de datos.
- **Staging:** `https://metrics.staging.petrocast.shop`.
- **Producción/demo:** `https://metrics.petrocast.shop` o el hostname que se
  defina en Route 53 para la entrega.

Traefik publica Grafana por hostname y exige autenticación. Las credenciales se
leen de secretos/variables de entorno, nunca del repo. Como mínimo se usa la
autenticación propia de Grafana con contraseña inicial rotada por ambiente; si
se expone públicamente, se agrega middleware de Basic Auth o allowlist de IPs en
Traefik/Security Groups.

### Previews de PR

Los previews por PR siguen siendo efímeros y livianos. No levantan todo el stack
de datos por defecto, porque PostgreSQL + Dagster + Metabase + DataHub por PR
sería costoso y lento. Para cambios de datos, la validación en PR ocurre en CI
con una base efímera y `dbt build`/tests; el stack completo se valida en staging
después del merge.

## Consecuencias

### Positivas

- Reutiliza la infraestructura existente de EC2, Swarm, Traefik, Route 53 y
  GitHub Actions sin rediseñar la plataforma.
- Mantiene disponibles los servicios que sí necesitan continuidad: API, DW,
  Dagster, Metabase y métricas.
- Reduce costo y presión de memoria al no correr DataHub 24/7.
- El Admin tiene una URL explícita para métricas y un modelo de autenticación.
- El equipo conserva una demo local reproducible con Compose.
- Los previews siguen rápidos y baratos; el feedback fuerte de datos queda en
  CI y staging.

### Negativas / trade-offs asumidos

- DataHub on-demand implica una operación manual o semiautomatizada para
  refrescar linaje antes de una demo o auditoría.
- Staging/prod concentran varios servicios en EC2 single-node; no hay alta
  disponibilidad real.
- Grafana expuesto por hostname requiere cuidar autenticación, secretos y reglas
  de red.
- La validación completa del stack de datos no ocurre en cada preview de PR,
  sino en CI con DB efímera y luego en staging.

### Neutras

- Si el volumen o la criticidad crecen, PostgreSQL puede migrarse a RDS y
  Grafana/DataHub a servicios dedicados sin cambiar la separación lógica de
  ambientes.
- DataHub puede levantarse localmente o en staging según el momento de la demo;
  lo importante es que su ciclo sea explícitamente on-demand.
- La topología no cambia la estrategia de carga, calidad ni modelo dimensional;
  sólo define dónde y cómo se operan esos componentes.

## Pros y contras de cada opción

### Demo local con Docker Compose únicamente

- ✅ Es la opción más barata y reproducible.
- ✅ No requiere DNS, TLS, credenciales AWS ni operación remota.
- ✅ Sirve para desarrollo y para una demo controlada en una notebook.
- ❌ No deja servicios disponibles para revisión asincrónica del equipo.
- ❌ No modela bien el acceso real del Admin a métricas ni del usuario a BI.
- ❌ No aprovecha la topología AWS ya definida en ADR-0008/0010.

### EC2 permanente con todo el stack 24/7

- ✅ Modelo simple: todo está siempre arriba en una URL remota.
- ✅ Facilita demos y revisión sin pasos manuales previos.
- ✅ DataHub queda siempre disponible para linaje.
- ❌ DataHub compite por memoria con PostgreSQL, Dagster y Metabase.
- ❌ Aumenta costo o fuerza a subir tamaño de instancia.
- ❌ Opera servicios pesados aunque sólo se usen para inspección ocasional.

### Topología híbrida (elegida)

- ✅ Mantiene permanentes los servicios críticos para consumo y operación.
- ✅ Ejecuta DataHub sólo cuando aporta valor: catalogar, refrescar y navegar
  linaje.
- ✅ Balancea costo, memoria y demostrabilidad.
- ✅ Es compatible con Compose local y con Swarm/Traefik en AWS.
- ❌ Requiere documentar y recordar el procedimiento para levantar/bajar
  DataHub.
- ❌ El linaje puede quedar desactualizado si nadie ejecuta el refresh antes de
  revisar el catálogo.

### Servicios managed o plataforma dedicada para datos

- ✅ RDS, ECS/Fargate, Grafana Cloud o similares reducirían operación manual y
  mejorarían aislamiento.
- ✅ Escalan mejor si el proyecto se vuelve productivo.
- ❌ Agregan costo, complejidad de Terraform y superficie de configuración.
- ❌ Cambian demasiado la plataforma para el plazo de Fase 2.
- ❌ No son necesarios para el volumen bajo y el contexto académico actual.

## Referencias

- Adenda Fase 2 (`docs/assignment/adenda-fase-2.md`) — BI, gobierno, métricas,
  DAGs como código, backfill y runbooks.
- Backlog Fase 2 (`docs/backlog/issues-fase-2.md`) — F2-09, F2-10, F2-20,
  F2-21 y F2-30.
- ADR-0008 — Topología de ambientes con previews, staging y producción.
- ADR-0010 — Hosting AWS EC2 con Docker Swarm y Traefik.
- ADR-0017 — Observabilidad con CloudWatch y dashboard local.
- ADR-0019 — Infraestructura Terraform AWS por ambiente.
- ADR-0022 — Gobierno de datos y linaje con DataHub.
- ADR-0023 — Orquestación con Dagster e ingesta con dlt.
