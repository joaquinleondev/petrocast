# ADR-0035: CI/CD de pipelines ML y promoción de artefactos

- **Estado:** Propuesto
- **Fecha:** 2026-07-02
- **Autores:** Santino Domato
- **Decisores:** Equipo Petrocast

## Contexto y problema

Fase 3 incorpora código para generar features, entrenar y evaluar un modelo,
registrar sus artefactos y servir el modelo aprobado desde FastAPI. Estos
componentes tienen ciclos de vida diferentes: el código y las imágenes Docker
se versionan en Git y ECR, mientras que cada entrenamiento genera una versión
de modelo independiente en MLflow.

El repositorio ya usa GitHub Actions como plataforma de CI/CD, OIDC para acceder
a AWS y ECR como registry de imágenes (ADR-0011 y ADR-0013). Además, ADR-0032
define MLflow como tracking y model registry, ADR-0033 asigna a Dagster la
orquestación del retraining y ADR-0034 establece que FastAPI carga el modelo
identificado por el alias `champion`.

La decisión pendiente es cómo validar cada cambio del pipeline ML, cómo publicar
el código ejecutable, cuándo promocionar un modelo candidato y cómo volver a una
versión anterior. También debemos definir qué parte del flujo se automatiza en
un proyecto sin producción permanentemente activa, evitando confundir CI con el
scheduler de entrenamiento o acoplar la promoción del modelo al despliegue de la
API.

## Drivers de la decisión

- **Separación de artefactos.** Una imagen contiene código y dependencias; una
  versión de MLflow contiene el modelo entrenado y su metadata.
- **Validación temprana.** Un PR debe detectar errores en features, training e
  inferencia antes de publicar imágenes o registrar candidatos compartidos.
- **Reproducibilidad.** Cada modelo debe poder vincularse al commit, imagen,
  corte de datos y versión de features que lo generaron.
- **Promoción segura.** Un merge no debe convertir automáticamente un modelo en
  `champion`; primero debe completar entrenamiento, evaluación y gates.
- **Rollback rápido.** Recuperar una versión aprobada anterior no debe requerir
  reconstruir imágenes ni redesplegar FastAPI.
- **Reuso del stack.** GitHub Actions, ECR, Dagster y MLflow ya cubren las
  responsabilidades necesarias.
- **Demostración sin prod live.** El flujo debe poder validarse localmente o en
  staging sin mantener infraestructura productiva encendida.
- **Costo operativo acotado.** El equipo es de tres personas y debe evitar un
  segundo sistema de CI/CD o herramientas específicas de MLOps administradas.

## Opciones consideradas

1. **GitHub Actions para CI/CD de código e imágenes, Dagster para ejecución y
   MLflow para promoción por alias.** Cada herramienta conserva una
   responsabilidad explícita y los artefactos se versionan de forma inmutable.
2. **Dagster también para build y deploy.** Los jobs de Dagster validan el
   código, construyen imágenes y promocionan modelos.
3. **Scripts locales y promoción manual.** El equipo ejecuta tests, builds y
   comandos de MLflow desde sus máquinas.
4. **Empaquetar el modelo dentro de la imagen de FastAPI.** Cada entrenamiento
   aprobado reconstruye y redespliega la API con el modelo incluido.

## Decisión

Elegimos **GitHub Actions para CI/CD de código e imágenes, Dagster para ejecutar
el pipeline y MLflow para promocionar modelos por alias**.

GitHub Actions será el plano de control de los cambios versionados en Git:
ejecutará los checks de PR, construirá la imagen del pipeline ML y publicará una
imagen inmutable en ECR después del merge. Dagster seguirá siendo el plano de
ejecución del pipeline `features → training → evaluation → promotion`. MLflow
almacenará los artefactos de cada entrenamiento y resolverá qué versión sirve la
API mediante el alias `champion`.

### Dos artefactos independientes

El flujo distingue dos tipos de artefactos:

1. **Imagen del pipeline ML.** Contiene código, lockfile y dependencias para
   materializar features, entrenar, evaluar y registrar modelos. Se publica como
   `petrocast/ml:sha-<commit-corto>` y se identifica también por digest.
2. **Versión de modelo.** Contiene el modelo serializado, su firma, métricas,
   parámetros y metadata. MLflow le asigna una versión inmutable dentro del
   modelo registrado `petrocast-production`.

Publicar una imagen prueba que el código puede ejecutarse, pero no demuestra que
un modelo nuevo sea mejor. Del mismo modo, promocionar un modelo no modifica la
imagen que ejecuta FastAPI. Esta separación permite reproducir qué código creó
cada versión sin forzar un deploy de aplicación por cada retraining.

### Checks mínimos de pull request

Todo PR que afecte `apps/ml`, los modelos dbt de features, el contrato de
inferencia o sus workflows ejecutará un check propio de pipeline ML. El check no
dependerá de internet, AWS ni de un servidor compartido de MLflow: usará
fixtures determinísticos, PostgreSQL efímero y un tracking store temporal.

Los checks mínimos serán:

1. **Calidad y reproducibilidad del entorno**
   - instalación desde el lockfile con `uv sync --frozen`;
   - Ruff, mypy y pytest sobre el código afectado;
   - verificación de que el entorno puede resolverse sin cambios del lockfile.
2. **Smoke de features**
   - `dbt parse` y construcción de los modelos necesarios sobre fixtures;
   - tests de schema y calidad definidos en dbt;
   - unicidad de `(well_id, as_of_date)`;
   - validación de point-in-time correctness: ninguna feature puede consumir
     información con fecha igual o posterior al corte.
3. **Smoke de training**
   - entrenamiento de un modelo pequeño con datos offline determinísticos;
   - métricas numéricas finitas y artefacto serializable;
   - registro local de parámetros, métricas, firma y tags obligatorios;
   - el smoke valida el camino técnico, no los umbrales productivos de calidad.
4. **Smoke de inferencia**
   - carga del artefacto producido por el smoke de training;
   - lectura de una fila válida del feature store de prueba;
   - predicción para un horizonte soportado;
   - validación del schema de salida, versión del modelo y ausencia de valores
     no finitos.
5. **Imagen y seguridad**
   - build multi-stage y ejecución no-root según ADR-0014;
   - escaneo de vulnerabilidades del filesystem y de la imagen;
   - bloqueo ante vulnerabilidades `HIGH` o `CRITICAL` corregibles.

Los tres smokes forman una cadena corta pero real: las features alimentan el
training y el modelo generado alimenta la inferencia. No se usarán mocks que
eliminen por completo esos límites de integración. Los datasets grandes,
backtests completos y comparaciones contra baselines quedan fuera del PR porque
harían al feedback lento y costoso; se ejecutan en el job de retraining.

### Publicación de la imagen ML

Al mergear a `main`, GitHub Actions repetirá los checks bloqueantes y construirá
una sola vez la imagen del pipeline. Si todos pasan:

- autenticará contra AWS mediante OIDC, sin credenciales persistentes;
- publicará `petrocast/ml:sha-<commit-corto>` en ECR;
- conservará el digest como identidad canónica del artefacto;
- podrá mover `staging-latest` al mismo digest para la demostración compartida;
- no publicará `latest` ni sobrescribirá tags inmutables;
- no moverá el alias `champion` como consecuencia del merge.

Los ambientes ejecutarán exactamente la imagen ya construida. Si se requiere
promover código entre staging y una futura producción, se moverá un alias o se
desplegará el mismo digest; no se reconstruirá el commit para cada ambiente.

### Entrenamiento, evaluación y promoción

Dagster lanzará `retraining_job` de forma programada o manual según ADR-0033.
El job consumirá una imagen ML identificable y generará un run candidato en
MLflow. Como mínimo, el run y la versión registrada incluirán:

- `git_commit` y digest de la imagen ejecutada;
- `as_of_date` y rango temporal de datos consumido;
- versión o hash de features;
- identificador del run de Dagster;
- parámetros, métricas y resultado de cada gate;
- versión previa del alias `champion`, cuando exista;
- origen del trigger: `schedule`, `manual` o `ci-smoke`.

La etapa de promoción sólo se ejecutará después de que la evaluación complete
los gates definidos en ADR-0030. Si un gate falla, el candidato y sus métricas
quedan registrados para auditoría, pero `champion` no cambia.

Mover el alias será una operación explícita, idempotente y auditable. Reintentar
la promoción del mismo run puede volver a apuntar `champion` a la versión ya
aprobada, pero nunca seleccionar una versión distinta ni omitir los gates. La
metadata de Dagster registrará la versión anterior y la nueva.

### Rollback del modelo

El rollback se realizará re-apuntando `champion` a una versión anterior que ya
haya sido aprobada. El operador seleccionará la versión, verificará su metadata
y ejecutará la misma operación de alias usada por la promoción. No se volverá a
entrenar, copiar ni modificar el artefacto.

FastAPI detectará el cambio mediante la estrategia de recarga definida en
ADR-0034 —TTL o endpoint de reload— y cargará la versión restaurada. Por lo
tanto, el rollback:

- no reconstruye la imagen de la API;
- no publica una nueva imagen ML;
- no requiere un deploy de infraestructura;
- conserva evidencia de quién movió el alias, cuándo y desde qué versión;
- puede revertirse volviendo a apuntar a otra versión aprobada.

Si el incidente pertenece al código del pipeline y no al modelo, se desplegará
un digest anterior de la imagen ML. Son dos operaciones distintas porque
resuelven fallas distintas.

### Automatización sin producción permanente

La ausencia de un ambiente productivo live no elimina el CI/CD; cambia dónde se
demuestra. El proyecto automatizará:

- checks de PR para features, training, inferencia, imagen y seguridad;
- publicación inmutable de la imagen ML después del merge;
- ejecución manual y programable del retraining con Dagster;
- registro de candidatos y evidencia en un MLflow local o compartido;
- evaluación y decisión automática de gates;
- promoción y rollback por alias en el ambiente de demostración.

No se exige mantener un endpoint productivo encendido. Una futura promoción al
ambiente `production` usará GitHub Environments con aprobación manual antes de
mover aliases o desplegar digests. La aprobación protege el límite de ambiente,
pero no reemplaza checks ni reevalúa el modelo manualmente.

La demo mínima debe mostrar: un PR verde, una imagen identificable por commit,
un candidato trazable, un gate que impide una promoción inválida, el movimiento
de `champion` para un candidato válido y un rollback a la versión anterior sin
rebuild ni redeploy.

### Permisos y secretos

GitHub Actions accederá a ECR mediante OIDC y permisos mínimos. Los jobs de PR
desde código no confiable no recibirán credenciales de AWS ni secretos del
registry compartido. Las URLs y credenciales de PostgreSQL, MLflow y S3 se
inyectarán por ambiente siguiendo ADR-0018.

El rol de CI podrá publicar imágenes, pero no promocionar modelos productivos.
El rol usado por Dagster podrá escribir runs, registrar versiones y mover el
alias del ambiente correspondiente. Separar permisos evita que modificar un
workflow de build otorgue por sí solo capacidad de cambiar el modelo servido.

## Consecuencias

**Positivas:**

- Cada PR valida de punta a punta el camino mínimo de features, training e
  inferencia sin depender de servicios externos.
- Código e imágenes se relacionan con modelos mediante metadata reproducible.
- Un merge publica código ejecutable, pero no salta los gates de calidad del
  modelo.
- Promoción y rollback son rápidos y no requieren rebuild ni redeploy de la API.
- GitHub Actions y Dagster no compiten como schedulers; cada uno mantiene una
  responsabilidad clara.
- El flujo completo puede demostrarse localmente o en staging sin prod live.

**Negativas / trade-offs asumidos:**

- CI gana tiempo y complejidad por integrar PostgreSQL, dbt, training e
  inferencia en un mismo smoke path.
- La trazabilidad requiere propagar commit, digest, corte y versión de features
  en todos los límites del pipeline.
- La recarga de FastAPI no es instantánea si se elige TTL; el tiempo máximo debe
  quedar documentado y monitoreado.
- Mantener imagen y modelo como artefactos separados exige distinguir qué tipo
  de rollback corresponde a cada incidente.
- Los smokes no prueban calidad estadística sobre el dataset completo; esa
  responsabilidad permanece en el retraining y sus gates.

**Neutras:**

- Este ADR no redefine features, métricas ni umbrales de aceptación.
- Tampoco cambia el scheduler mensual ni el contrato público de FastAPI.
- Una futura producción puede agregar aprobaciones y ambientes sin modificar la
  separación entre CI, ejecución y registry.

## Implementación incremental

1. Crear un workflow `build-ml.yml` con instalación frozen, checks, smokes,
   build y escaneo de la imagen.
2. Incorporar fixtures determinísticos que permitan recorrer features,
   training e inferencia sin red.
3. Publicar la imagen `sha-<commit-corto>` en ECR después del merge a `main` y
   registrar su digest.
4. Propagar commit, digest, `as_of_date` y versión de features a Dagster y
   MLflow.
5. Implementar la promoción idempotente del alias después de los gates y
   registrar versión previa y nueva.
6. Agregar una operación manual de rollback por alias y verificar la recarga de
   FastAPI sin redeploy.
7. Ejecutar la demostración completa primero con PostgreSQL y MLflow locales;
   habilitar staging compartido cuando sus recursos estén disponibles.

## Pros y contras de cada opción

### GitHub Actions + Dagster + MLflow por alias (elegida)

- ✅ Reusa el stack y separa CI, runtime y model registry.
- ✅ Ofrece checks bloqueantes, artefactos inmutables y trazabilidad completa.
- ✅ Permite promoción y rollback sin reconstruir ni redesplegar FastAPI.
- ✅ Funciona localmente y escala a staging o producción con el mismo contrato.
- ❌ Requiere propagar metadata coherente entre tres sistemas.
- ❌ Los tests de integración hacen que CI sea más pesado que un lint unitario.

### Dagster también para build y deploy

- ✅ Centraliza visualmente casi todo el ciclo ML.
- ✅ Puede expresar dependencias y retries como assets u ops.
- ❌ Mezcla ejecución de datos con validación de PRs y publicación de imágenes.
- ❌ Dagster necesitaría permisos de repositorio y registry que no requiere para
  orquestar retraining.
- ❌ Duplica capacidades maduras de GitHub Actions.

### Scripts locales y promoción manual

- ✅ Tiene una implementación inicial simple.
- ✅ No necesita runners ni workflows adicionales.
- ❌ Los resultados dependen de la máquina y disciplina de cada integrante.
- ❌ No ofrece checks bloqueantes, evidencia uniforme ni permisos centralizados.
- ❌ Aumenta el riesgo de publicar una imagen o promocionar un modelo no probado.

### Modelo empaquetado dentro de FastAPI

- ✅ La imagen contiene todo lo necesario para servir una versión conocida.
- ✅ El rollback de aplicación y modelo usa un único digest.
- ❌ Cada retraining exige rebuild y redeploy aunque el código no haya cambiado.
- ❌ Acopla innecesariamente el ciclo del modelo al de la API.
- ❌ Contradice la promoción por alias definida en ADR-0032 y ADR-0034.

## Referencias

- [GitHub Actions — OpenID Connect en AWS](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [MLflow — Model Registry workflows](https://mlflow.org/docs/latest/ml/model-registry/workflow/)
- [MLflow — Model aliases](https://mlflow.org/docs/latest/ml/model-registry/workflow/#model-version-aliases)
- [ADR-0011](0011-plataforma-cicd.md) — CI/CD con GitHub Actions y OIDC.
- [ADR-0013](0013-container-registry-aws-ecr.md) — imágenes inmutables y ECR.
- [ADR-0014](0014-imagenes-docker-slim-multistage-nonroot.md) — build y runtime de imágenes.
- [ADR-0018](0018-gestion-configuracion-pydantic-settings.md) — configuración y secretos.
- [ADR-0030](0030-objetivo-predictivo-horizonte-metricas.md) — métricas y gates.
- [ADR-0031](0031-estrategia-feature-store.md) — feature store y point-in-time correctness.
- [ADR-0032](0032-tracking-experimentos-registry.md) — tracking y registry MLflow.
- [ADR-0033](0033-orquestacion-entrenamiento-retraining.md) — job recurrente en Dagster.
- [ADR-0034](0034-serving-modelo-contrato-api.md) — serving y recarga del champion.
- Backlog Fase 3 — #06 como decisión y #21/#22 como implementación.
