# ADR-0005: Convenciones de commits, PRs y estrategia de merge

- **Estado:** Aceptado
- **Fecha:** 2026-04-20
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

ADR-0004 establece el uso de feature branches + PRs. Queda por definir:

- **Formato de mensajes de commit**: sin convención, los mensajes tienden
  a ser inconsistentes ("wip", "cambios", "update") y el historial se
  vuelve ilegible.
- **Estrategia de merge**: GitHub ofrece tres opciones (merge commit,
  rebase, squash), con implicaciones distintas para el historial.
- **Estructura de PRs**: sin un template, los PRs entran con descripción
  mínima y el review se vuelve ineficiente.

## Drivers de la decisión

- Historial de `main` legible y que cuente la evolución del proyecto.
- Reviews eficientes que no requieran adivinar contexto.
- Evidencia clara de colaboración para la evaluación de la materia.
- Compatibilidad con herramientas de generación automática de changelog
  (futuro opcional).

## Opciones consideradas

### Mensajes de commit

1. **Conventional Commits** (`feat(scope): descripción`).
2. **Estilo libre** con algunas reglas básicas.
3. **Formato Gitmoji** (emojis prefijo por tipo de cambio).

### Estrategia de merge

1. **Squash and merge**: 1 PR = 1 commit en `main`.
2. **Rebase and merge**: preserva commits individuales linealmente.
3. **Merge commit**: preserva commits + commit de merge.

## Decisión

### Mensajes de commit: Conventional Commits

Formato:

```
<tipo>(<scope opcional>): <descripción en imperativo, minúsculas>
```

[body opcional explicando el por qué]
[footer opcional: refs, breaking changes]
**Tipos permitidos:**

| Tipo       | Uso                                                    |
| ---------- | ------------------------------------------------------ |
| `feat`     | Nueva funcionalidad para el usuario final              |
| `fix`      | Corrección de bug                                      |
| `docs`     | Solo cambios de documentación (incluye ADRs)           |
| `style`    | Formato, espacios, punto y coma (sin cambio de lógica) |
| `refactor` | Cambio interno sin alterar comportamiento externo      |
| `test`     | Agregar o ajustar tests                                |
| `chore`    | Tooling, dependencias, configuración                   |
| `ci`       | Cambios en pipelines de CI/CD                          |
| `perf`     | Mejora de performance                                  |

**Idioma:** los mensajes de commit se escriben **en inglés** (ver ADR-0002).

**Ejemplos válidos:**
feat(api): add GET /forecast/:well-id endpoint
fix(dashboard): correct date parsing on Safari
docs(adr): add ADR-0007 on backend stack selection
chore(ci): add lint workflow on pull requests
refactor(forecast): extract Arps model into separate module
**Ejemplos inválidos:**
update stuff # sin tipo, descripción vacía
WIP # no describe nada
Feat: Added new endpoint. # mayúsculas, punto final, pasado

### Estrategia de merge: Squash and merge

**En la configuración del repositorio:**

- ✅ Allow squash merging (**única habilitada**).
- ❌ Disable merge commits.
- ❌ Disable rebase merging.
- ✅ Automatically delete head branches.

**Consecuencia:** cada PR produce **exactamente un commit en `main`**. El
mensaje de ese commit es el título del PR, que debe respetar el formato
Conventional Commits. Los commits individuales dentro de la branch son
libres (pueden ser "wip", "fix typo", etc.); lo que cuenta es el commit
final squasheado.

### Template de Pull Request

Archivo `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Descripción

<!-- Qué hace este PR y por qué. 2-5 oraciones. -->

## Tipo de cambio

- [ ] feat — nueva funcionalidad
- [ ] fix — corrección de bug
- [ ] docs — documentación
- [ ] chore — tooling / configuración
- [ ] refactor — cambio interno sin alterar comportamiento
- [ ] test — tests

## Checklist

- [ ] El título del PR sigue el formato Conventional Commits.
- [ ] Actualicé la documentación relevante (README, ADRs).
- [ ] Si introduje una decisión no trivial, agregué un ADR.
- [ ] Los cambios son atómicos (un solo propósito por PR).
- [ ] Hice rebase con `main` antes de pedir review.

## Contexto adicional

<!-- Links a issues, ADRs relacionados, screenshots si aplica. -->
```

### Reglas de revisión

- Todo PR requiere **al menos 1 approval** de otro miembro del equipo.
- El autor del PR **no puede mergear sin approval**.
- Las conversaciones en el PR deben estar resueltas antes de mergear.
- Si el PR lleva más de 48h abierto sin review, el autor pinguea al equipo.

## Consecuencias

**Positivas:**

- El historial de `main` es una secuencia de commits atómicos y descriptivos.
- `git log --oneline` cuenta la historia del proyecto de un vistazo.
- Los PRs entran con contexto suficiente para ser revisados eficientemente.
- Facilita la generación automática de changelog si se decide adoptarla.
- Evidencia clara de colaboración para la evaluación.

**Negativas / trade-offs asumidos:**

- Curva de aprendizaje inicial para quien no usó Conventional Commits.
- Se pierden los commits individuales de la branch (quedan squasheados).
  Esto es aceptable: los commits intermedios de una branch suelen ser
  ruido ("wip", "fix typo"); lo que importa es el cambio agregado.

**Neutras:**

- El inglés en commits mientras se habla español en PRs y docs puede
  sentirse raro al principio; es la convención estándar.

## Pros y contras de cada opción

### Mensajes: Conventional Commits (elegida)

- ✅ Estándar de la industria.
- ✅ Fuerza a pensar qué se está cambiando.
- ✅ Habilita automatizaciones (changelog, versioning).
- ❌ Curva de aprendizaje mínima.

### Mensajes: Estilo libre

- ✅ Cero fricción.
- ❌ Historial inconsistente, difícil de navegar.
- ❌ No comunica la naturaleza del cambio sin leer el diff.

### Merge: Squash (elegida)

- ✅ Historial de `main` limpio: 1 PR = 1 commit.
- ✅ Revertir un PR es revertir un commit.
- ❌ Se pierden los commits intermedios de la branch.

### Merge: Rebase

- ✅ Preserva todos los commits linealmente.
- ❌ Requiere disciplina para que los commits individuales sean de calidad.
- ❌ El historial puede ser ruidoso con commits "wip" intermedios.

### Merge: Merge commit

- ❌ Crea commits de merge que agregan ruido al historial.
- ❌ Historial no lineal (grafo de branches).
- ❌ Incompatible con el requisito de "linear history" de ADR-0004.

## Referencias

- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/)
- [GitHub Docs — About merge methods on GitHub](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges)
- ADR-0002 (Idioma): commits en inglés.
- ADR-0004 (Branching): estructura de branches que alimenta estos PRs.
