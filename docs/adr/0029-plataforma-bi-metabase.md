# ADR-0029: Plataforma de BI con Metabase OSS

- **Estado:** Aceptado
- **Fecha:** 2026-06-12
- **Autores:** Joaquin Leon Alderete
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda de Fase 2 (RF3) exige que **usuarios no técnicos** puedan explorar
la producción de pozos sobre el modelo dimensional `gold`: producción por
pozo/mes, evolución histórica y top de pozos por volumen, con filtros por
pozo, fecha y tipo de fluido. El consumidor objetivo es el rol de negocio
(Data Consumer / Data Owner), no un analista que escribe SQL.

El stack ya tiene una herramienta de dashboards: **Grafana**, adoptada para
observabilidad operativa en Fase 1 ([ADR-0017](0017-observabilidad-cloudwatch-dashboard-local.md),
[ADR-0021](0021-observabilidad-local-fase1.md)) y dirigida al rol Admin.
La primera pregunta es entonces si reutilizamos Grafana para BI de negocio o
sumamos una plataforma dedicada; la segunda, cuál.

La decisión está condicionada por el entorno de despliegue que fija
[ADR-0027](0027-topologia-despliegue-fase2.md): EC2 chicas con Docker
Compose/Swarm donde ya conviven PostgreSQL, Dagster y (on-demand) DataHub.
Cada contenedor y cada GB de RAM cuentan. El addendum P2 ya había
preseleccionado Metabase; este ADR formaliza esa decisión con la comparación
de alternativas que exige la adenda.

## Drivers de la decisión

- **Audiencia no técnica (RF3).** Explorar datos y armar preguntas sin
  escribir SQL; filtros simples sobre dashboards prearmados.
- **Footprint operativo mínimo.** La plataforma corre en la misma EC2 que el
  DW y el orquestador (ADR-0027); una herramienta de BI que exija su propio
  cluster de servicios queda descartada de entrada.
- **Separación de audiencias.** Grafana es del rol Admin (métricas y
  alertas); el BI de negocio tiene otros usuarios, otras fuentes (solo
  `gold`) y otro modelo de permisos. Mezclarlos confunde gobierno y accesos.
- **Open source self-hosted, sin tier pago** para las features que Fase 2
  necesita — mismo criterio que ADR-0028 y ADR-0023.
- **Plazo y curva de aprendizaje.** Entrega el 2026-06-15; el setup debe
  medirse en horas y el equipo no tiene un experto en BI dedicado.
- **Conector PostgreSQL de primera clase**, apuntando al schema `gold`
  ([ADR-0024](0024-modelo-dimensional-star-schema.md)).

## Opciones consideradas

1. **Metabase OSS** — BI orientado a negocio, contenedor único (JVM).
2. **Apache Superset** — plataforma BI completa orientada a analistas.
3. **Redash** — herramienta query-first de visualización SQL.
4. **Grafana (reutilizar)** — extender la instancia operativa existente con
   dashboards de negocio sobre PostgreSQL.

## Decisión

Elegimos **Metabase OSS** como plataforma de BI de Fase 2, desplegada como
contenedor único en el **puerto 3001** (evita la colisión con Grafana en
`:3000`), conectada con un usuario de **solo lectura** al schema `gold`.
Grafana sigue siendo la herramienta operativa del rol Admin; las audiencias
quedan separadas por herramienta.

Metabase es la única de las cuatro opciones que cumple los dos drivers
excluyentes a la vez: usuarios no técnicos autónomos (su query builder de
"questions" permite explorar `gold` sin SQL) y footprint de un solo
contenedor. Superset es más potente pero paga ese poder con un stack de
servicios desproporcionado para nuestra EC2 y con una curva orientada a
analistas. Redash exige SQL para cada visualización, lo que contradice RF3.
Reutilizar Grafana ahorra infraestructura pero ofrece una experiencia de
exploración pobre para negocio y mezcla audiencias y permisos que la adenda
pide mantener separados.

Los detalles de implementación (compose, dashboards concretos, filtros) se
resuelven en [F2-20](../backlog/issues-fase-2.md); las vistas del semantic
layer liviano (F2-28) se consumirán desde Metabase sin cambiar esta decisión.

## Consecuencias

**Positivas:**

- Usuarios de negocio exploran producción por pozo/mes, histórico y top de
  pozos sin escribir SQL ni pedir dashboards a un técnico (RF3 directo).
- Un solo contenedor adicional en la EC2; compatible con la topología y el
  presupuesto de memoria de ADR-0027.
- Setup en horas vía Compose; demo local reproducible con el resto del stack.
- Separación limpia: Grafana = operación (Admin), Metabase = negocio
  (consumidores de datos), cada uno con sus permisos.
- El usuario read-only sobre `gold` impide que el BI escriba o lea capas
  crudas (`bronze`/`silver`).

**Negativas / trade-offs asumidos:**

- **Licencia AGPLv3** en la edición OSS (vs. Apache 2.0 de Superset).
  Aceptable: uso interno self-hosted, sin redistribución ni SaaS derivado.
- **JVM con apetito de RAM** (~1–2 GB en reposo). ADR-0027 ya dimensiona la
  instancia contemplando Metabase persistente; se monitorea con las métricas
  del Admin.
- Features avanzadas (SSO, sandboxing por fila, caching granular) están en
  el tier pago. Fase 2 no las necesita; si Fase 3 las exige, se revisa con
  un nuevo ADR.
- Menos profundidad de visualización que Superset para análisis complejos.
  El alcance de RF3 (tres dashboards con filtros) está cómodamente dentro de
  lo que cubre Metabase.

**Neutras:**

- La metadata de Metabase (usuarios, dashboards) vive en su propia base de
  aplicación; el detalle (Postgres dedicado vs. base separada en el mismo
  servidor) se define en F2-20.
- La decisión es ortogonal al gobierno: DataHub cataloga `gold`
  independientemente de qué herramienta lo visualice
  ([ADR-0022](0022-gobierno-datos-linaje-datahub.md)).

## Pros y contras de cada opción

### Metabase OSS (elegida)

- ✅ Query builder visual usable por no técnicos; dashboards con filtros
  (pozo, fecha, tipo de fluido) sin SQL.
- ✅ Contenedor único; el footprint más chico de las opciones BI dedicadas.
- ✅ Conector PostgreSQL nativo y maduro; apunta a `gold` sin fricción.
- ✅ Curva de aprendizaje baja; setup en horas.
- ❌ AGPLv3 (sin impacto para uso interno, pero más restrictiva que Apache 2.0).
- ❌ SSO, permisos por fila y caching avanzado solo en tier pago.
- ❌ Visualizaciones menos potentes que Superset para análisis exploratorio
  profundo.

### Apache Superset

- ✅ Licencia Apache 2.0.
- ✅ Visualizaciones muy ricas, SQL Lab, ecosistema de plugins; escala a
  organizaciones grandes.
- ❌ Arquitectura pesada: webserver + workers (Celery) + Redis + base de
  metadata — varios contenedores en una EC2 que ya corre el DW, Dagster y
  DataHub on-demand.
- ❌ Orientado a analistas de datos; la exploración para usuarios de negocio
  sin SQL es notablemente menos amigable que en Metabase.
- ❌ Setup y operación (upgrades, workers, cache) desproporcionados para
  tres dashboards y un equipo de 3 con entrega en días.

### Redash

- ✅ Liviano y simple de operar; queries SQL compartibles con parámetros.
- ✅ Licencia BSD-2.
- ❌ **Query-first**: cada visualización nace de una consulta SQL escrita a
  mano — incumple el requisito central de RF3 (usuarios no técnicos
  autónomos).
- ❌ Desarrollo de la edición OSS estancado desde la adquisición por
  Databricks; comunidad y releases en declive — riesgo de mantenimiento a
  futuro.
- ❌ Sin query builder visual comparable al de Metabase.

### Grafana (reutilizar la instancia operativa)

- ✅ Cero infraestructura nueva; el equipo ya lo opera desde Fase 1.
- ✅ Soporta PostgreSQL como datasource.
- ❌ Diseñado para series de tiempo y monitoreo; el BI tabular de negocio
  (rankings, drill-down por dimensiones, filtros cruzados) es incómodo y
  limitado.
- ❌ Sin exploración ad-hoc para no técnicos: cada panel lo arma alguien que
  escribe SQL; el usuario de negocio solo mira.
- ❌ Mezcla audiencias y permisos: el Admin (métricas de infraestructura) y
  el Data Consumer (producción de pozos) compartirían herramienta, carpetas
  y modelo de acceso, complicando el gobierno que la adenda pide.

## Referencias

- Adenda técnica Fase 2 — RF3 (dashboards para usuarios no técnicos);
  addendum P2 (preselección de Metabase).
- [ADR-0017](0017-observabilidad-cloudwatch-dashboard-local.md) /
  [ADR-0021](0021-observabilidad-local-fase1.md) — Grafana operativo (Admin).
- [ADR-0024](0024-modelo-dimensional-star-schema.md) — star schema `gold`
  que consume el BI.
- [ADR-0027](0027-topologia-despliegue-fase2.md) — topología de despliegue;
  Metabase como servicio persistente.
- [ADR-0022](0022-gobierno-datos-linaje-datahub.md) — gobierno y linaje
  (ortogonal al BI).
- [Metabase — documentación](https://www.metabase.com/docs/latest/)
- [Apache Superset — documentación](https://superset.apache.org/docs/intro)
- [Redash — documentación](https://redash.io/help/)
- [Grafana — PostgreSQL data source](https://grafana.com/docs/grafana/latest/datasources/postgres/)
- [F2-20](../backlog/issues-fase-2.md) — implementación (deploy + dashboards);
  [F2-28](../backlog/issues-fase-2.md) — semantic layer liviano en `gold`.
