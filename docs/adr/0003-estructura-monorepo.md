# ADR-0003: Organización del proyecto como monorepo

- **Estado:** Aceptado
- **Fecha:** 2026-04-20
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

El proyecto Predictiva, según el PRD, tendrá al menos los siguientes
componentes a lo largo de las tres fases:

- Un módulo de ingesta y procesamiento de datos.
- Un motor de modelado predictivo (ML).
- Una API REST para exposición de resultados.
- Una interfaz de usuario / dashboard.
- Infraestructura de deployment.
- Documentación (PRD, ADRs, diagramas, backlog).

Estos componentes se pueden organizar de dos maneras principales:
**monorepo** (un solo repositorio con todos los componentes) o
**multi-repo** (un repositorio por componente).

Necesitamos decidir la estructura **antes de escribir código** para
evitar refactors estructurales costosos más adelante.

## Drivers de la decisión

- Equipo pequeño (3 personas) con comunicación directa.
- Proyecto de duración acotada (un cuatrimestre, tres fases).
- Entrega única evaluada como un todo integrado.
- Los componentes están fuertemente acoplados en su ciclo de vida
  (avanzan juntos por fase).
- Necesidad de trazabilidad entre decisiones, código y documentación.

## Opciones consideradas

1. **Monorepo** con estructura por carpetas (`apps/`, `packages/`,
   `infra/`, `docs/`).
2. **Multi-repo**: un repo por componente (uno para la API, uno para el
   dashboard, uno para los modelos, uno para docs).
3. **Monorepo con herramienta dedicada** (Nx, Turborepo, Bazel).

## Decisión

Adoptamos un **monorepo simple con estructura por carpetas**, sin
herramientas dedicadas de monorepo (Nx, Turborepo).

Estructura raíz:

```
predictiva/
├── README.md
├── LICENSE
├── .gitignore
├── .github/
│ ├── workflows/ # CI/CD
│ ├── PULL_REQUEST_TEMPLATE.md
│ └── ISSUE_TEMPLATE/
├── docs/
│ ├── prd/ # PRD y adendas
│ ├── adr/ # Architecture Decision Records
│ ├── architecture/ # Diagramas (C4, componentes)
│ ├── backlog/ # Historias de usuario
│ └── demo/ # Materiales de demo por fase
├── apps/ # Servicios ejecutables
├── packages/ # Librerías compartidas (si surgen)
└── infra/ # Infraestructura como código
```

**Reglas de estructura:**

- Los componentes concretos (API, dashboard, workers, etc.) se crean
  dentro de `apps/` cuando se implementen (Fase 1+). No se crean carpetas
  vacías anticipadamente.
- `packages/` se usa solo si surge código compartido entre dos o más
  apps. En Fase 1 probablemente no existirá.
- `infra/` contiene todo lo necesario para levantar el entorno de
  ejecución (docker-compose, configuraciones de Dokploy, scripts de
  deployment).
- `docs/` es parte del entregable, no un extra.

## Consecuencias

**Positivas:**

- Un solo lugar para issues, PRs, ADRs y CI.
- Cambios que tocan múltiples componentes se hacen en un solo PR atómico.
- El historial cuenta la evolución del proyecto completo.
- Trazabilidad natural: un ADR está al lado del código que describe.
- Setup para un colaborador nuevo: `git clone` y ya tiene todo.

**Negativas / trade-offs asumidos:**

- El repo crecerá en tamaño con el tiempo; no es un problema a la escala
  del TP.
- Un mal commit puede afectar múltiples componentes; se mitiga con
  review obligatorio por PR.

**Neutras:**

- No utilizamos herramientas como Nx/Turborepo porque agregan complejidad
  innecesaria para el tamaño del equipo y del proyecto. Si en algún
  momento se justifican, se escribirá un nuevo ADR.

## Pros y contras de cada opción

### Monorepo simple (elegida)

- ✅ Cero overhead de herramientas.
- ✅ Suficiente para el tamaño del equipo y del proyecto.
- ✅ Estructura estándar, fácilmente legible.
- ❌ No aporta optimizaciones de build caching o task orchestration.

### Multi-repo

- ✅ Cada componente puede evolucionar con su propio ciclo.
- ❌ Fricción para cambios que tocan múltiples componentes.
- ❌ ADRs y docs quedan dispersos.
- ❌ Overhead administrativo (tres repos, tres configuraciones de CI,
  tres sets de permisos).
- ❌ El estado del sistema en un momento dado no es capturable por un
  solo commit.

### Monorepo con Nx/Turborepo

- ✅ Aporta build caching, task runners, dependency graph.
- ❌ Complejidad de configuración desproporcionada para el proyecto.
- ❌ Curva de aprendizaje.
- ❌ Añade dependencias fuertes a un ecosistema (típicamente JS/TS).

## Referencias

- [Monorepo Explained](https://monorepo.tools/)
- Consigna del TP (requiere repositorio único por equipo).
- ADR-0001 (sobre ubicación de ADRs en `docs/adr/`).
