# ADR-0004: Estrategia de branching basada en trunk

- **Estado:** Aceptado
- **Fecha:** 2026-04-20
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

Tres personas van a desarrollar código y documentación en paralelo a lo
largo de tres fases. Se necesita definir:

- Qué branches existen de manera permanente.
- Cómo se crean y nombran branches de trabajo.
- Cómo se integra el trabajo individual a la branch principal.
- Qué protecciones aplican a las branches importantes.

Sin una estrategia explícita, el riesgo es tener una historia de Git
desordenada, conflictos de merge frecuentes, y commits directos a `main`
que rompen la estabilidad.

## Drivers de la decisión

- Equipo pequeño con comunicación directa.
- No existe "producción" en el sentido tradicional: el entregable es una
  URL accesible al corrector durante las fechas de evaluación.
- No hay necesidad de liberar versiones paralelas ni de mantener ramas de
  compatibilidad.
- Se valora un historial de `main` limpio y narrativo.
- La materia lista "desarrollo colaborativo en Git" como contenido
  evaluable.

## Opciones consideradas

1. **Trunk-based simplificado**: una sola branch permanente (`main`) +
   feature branches cortas.
2. **Git Flow**: `main` + `develop` + branches `feature/*`, `release/*`,
   `hotfix/*`.
3. **GitHub Flow**: `main` + feature branches + deploys automáticos al
   mergear.

## Decisión

Adoptamos **trunk-based simplificado**, una variante de GitHub Flow:

- **Una única branch permanente: `main`.**
- **`main` está siempre deployable.** Si algo rompe `main`, arreglarlo es
  prioridad #1.
- **Todo cambio entra vía feature branch + Pull Request.** No existen
  commits directos a `main` (excepto el commit inicial del repo, antes de
  habilitar branch protection).
- **Feature branches son cortas**: idealmente < 3 días de trabajo, < 300
  líneas modificadas. Si crecen más, se dividen.
- **Las branches se eliminan al mergearse** (GitHub lo hace automáticamente
  si está configurado).

**Naming convention de branches:**

```
<tipo>/<descripción-corta-en-kebab-case>
```

Tipos permitidos:

- `feat/` — nueva funcionalidad.
- `fix/` — corrección de bug.
- `docs/` — solo cambios de documentación (incluye ADRs).
- `chore/` — tooling, configuración, dependencias.
- `refactor/` — cambio interno sin alterar comportamiento.
- `test/` — agregar o mejorar tests.

Ejemplos:

- `feat/forecast-endpoint`
- `docs/adr-0007-elección-stack-backend`
- `chore/github-pr-template`
- `fix/dashboard-date-parsing`

**Branch protection para `main`:**

- Require pull request before merging.
- Require 1 approval from another team member.
- Dismiss stale approvals when new commits are pushed.
- Require conversation resolution before merging.
- Require linear history (fuerza rebase o squash; prohíbe merge commits).
- Do not allow bypassing the above.

**Flujo típico de una feature:**

```bash
git checkout main
git pull
git checkout -b feat/mi-tarea
# ... trabajo ...
git fetch origin
git rebase origin/main
git push -u origin feat/mi-tarea
# abrir PR, recibir approval, merge con squash desde UI
```

**Probar varias features juntas antes de mergear:** si surge la
necesidad, se crea una **integration branch efímera**
(`integration/<nombre>`), se mergean las features ahí temporalmente para
probar, y si todo funciona se mergean a `main`. La integration branch se
borra. No existen branches de integración permanentes.

## Consecuencias

**Positivas:**

- Historial lineal y simple de seguir.
- `main` siempre refleja el estado más reciente y estable.
- Menor probabilidad de conflictos de merge grandes (branches cortas).
- Compatible con deploys continuos y preview environments por PR.
- Es el estándar moderno de la industria para equipos que hacen CI/CD.

**Negativas / trade-offs asumidos:**

- Requiere disciplina para no dejar crecer branches.
- No hay un entorno "staging" permanente; para probar integración se
  usan preview environments o integration branches efímeras.

**Neutras:**

- No aplica para proyectos con releases versionadas paralelas
  (ej: v1.x y v2.x); esto no es nuestro caso.

## Pros y contras de cada opción

### Trunk-based simplificado (elegida)

- ✅ Simple, una sola branch permanente.
- ✅ Historial limpio.
- ✅ Compatible con CI/CD continuo.
- ❌ Requiere disciplina de branches cortas.

### Git Flow

- ✅ Estructura muy clara para proyectos con releases versionadas.
- ❌ Over-engineering para un equipo de 3 y un proyecto de un cuatrimestre.
- ❌ Dos branches permanentes (`main` + `develop`) que requieren sincronización.
- ❌ El propio autor de Git Flow lo desaconseja para proyectos web modernos.

### GitHub Flow puro

- ✅ Muy similar a lo elegido.
- ✅ Aún más simple.
- ❌ Requiere deploys automáticos al mergear para funcionar bien; no
  aplica exactamente a nuestro flujo de entregas por fase.

## Referencias

- [Trunk Based Development](https://trunkbaseddevelopment.com/)
- [GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow)
- [Vincent Driessen — "Note on Git Flow"](https://nvie.com/posts/a-successful-git-branching-model/)
  (el propio autor desaconseja Git Flow para SaaS/web moderno)
- ADR-0005 (Convenciones de commits y estrategia de merge).
