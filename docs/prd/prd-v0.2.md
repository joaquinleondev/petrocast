# Documento de Requerimientos: Plataforma de Ingesta, Procesamiento y Gobierno de Datos

| Propiedad | Valor |
| --------- | ----- |
| Versión   | No especificado en la adenda técnica |
| Fecha     | No especificado en la adenda técnica |
| Owner     | No especificado en la adenda técnica |

---

## Resumen Ejecutivo

Este documento describe los requerimientos de la Fase 2, cuyo objetivo es desarrollar la funcionalidad del sistema base junto con la base necesaria sobre la cual se llevará a cabo un desarrollo ágil.

La etapa se centra en la ingesta, procesamiento, calidad, almacenamiento, gobierno y visualización de datos mediante una arquitectura medallion. El sistema deberá permitir extraer datos desde fuentes públicas, procesarlos en capas Bronze, Silver y Gold, almacenarlos en un Data Warehouse, exponerlos mediante una plataforma de BI y permitir su seguimiento mediante una plataforma de gobierno de datos.

El sistema incluirá:

- Proceso de extracción de datos desde fuentes definidas.
- Arquitectura medallion para procesamiento de datos.
- Capas Bronze, Silver y Gold.
- Transformaciones de datos.
- Chequeos de calidad de datos.
- Data Warehouse.
- Plataforma de BI para usuarios no técnicos.
- Plataforma de gobierno de datos.
- Herramienta de orquestación con DAGs definidos como código.
- Procedimiento de reprocesamiento histórico / backfill.
- Documentación del modelo de datos.
- Runbooks por rol.
- ADRs para justificar decisiones técnicas clave.

### Notas

- En este documento se utiliza la convención del RFC 2119.
- Los ítems marcados como bonus no son obligatorios. Suman a la nota desde el aprobado hacia arriba, pero no compensan si la nota base no alcanza el umbral de aprobación.
- Los ADRs que no incluyan comparación de alternativas, o que únicamente describan el camino tomado, serán considerados inválidos y quedarán fuera de la evaluación del trabajo.

---

## Contexto / Problema

En esta etapa se busca desarrollar la funcionalidad del sistema base junto con la base necesaria sobre la cual se llevará a cabo un desarrollo ágil.

El sistema debe permitir implementar un flujo de datos completo que incluya extracción, procesamiento, calidad, almacenamiento, gobierno y visualización. Para esto se requiere una arquitectura de datos que organice los datos en capas medallion y permita que usuarios técnicos y no técnicos interactúen con el sistema.

El flujo general esperado es:

```text
Data Sources → Extracción de Datos → Bronze Layer → Silver Layer → Gold Layer → Data Warehouse → BI Platform / Data Governance Platform → Admins
````

Además, debe existir una herramienta de orquestación que controle los workflows de extracción, transformación, calidad y actualización de datos.

---

## Usuarios

A continuación se detallan los usuarios principales identificados en la adenda técnica de la Fase 2:

| Rol del Usuario    | Perfil/Equipo                             | Necesidad Clave                                                                                         |
| ------------------ | ----------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Desarrolladores    | Devs                                      | Al crear PRs, deben recibir feedback sobre los tests del código.                                        |
| Usuarios de la API | Usuarios técnicos o sistemas consumidores | Deben ser capaces de hacer uso del servicio mediante una API REST.                                      |
| Administradores    | Admins                                    | Deben poder acceder vía web a una interfaz que muestre métricas relevantes a la ejecución del servicio. |

---

## Casos de Uso

| Caso de Uso                             | Descripción                                                                                                                                                    |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Feedback de tests en PRs             | Los desarrolladores deben recibir feedback sobre los tests del código al crear pull requests.                                                                  |
| 2. Consumo del servicio vía API REST    | Los usuarios de la API deben poder hacer uso del servicio mediante una API REST.                                                                               |
| 3. Monitoreo web por administradores    | Los administradores deben poder acceder vía web a una interfaz que muestre métricas relevantes a la ejecución del servicio.                                    |
| 4. Revisión de datos mediante BI        | Usuarios no técnicos deben poder revisar los datos mediante una plataforma de BI.                                                                              |
| 5. Gobierno de datos                    | Los administradores o usuarios responsables deben poder visualizar workflows de extracción, datos en el Data Warehouse y la última actualización de los datos. |
| 6. Reprocesamiento histórico / backfill | El sistema debe permitir reprocesar datos históricos o datos de una fecha dada si existen cambios.                                                             |

---

## Objetivos Primarios

* Implementar un proceso de extracción de datos desde las fuentes definidas.
* Procesar los datos utilizando arquitectura medallion.
* Disponer de un Data Warehouse basado en modelo estrella.
* Permitir que usuarios no técnicos revisen los datos mediante una plataforma de BI.
* Implementar una plataforma de gobierno de datos.
* Orquestar workflows mediante DAGs definidos como código.
* Garantizar idempotencia, retries con backoff y observabilidad mínima.
* Documentar y permitir reprocesamiento histórico / backfill.

---

## Objetivos Secundarios

* Implementar chequeos de calidad de datos persistidos.
* Registrar linaje de datos.
* Documentar el modelo de datos utilizado.
* Definir y justificar decisiones técnicas mediante ADRs.
* Escribir runbooks específicos para al menos dos roles.
* Implementar, como bonus, un semantic layer para exponer métricas de negocio definidas una sola vez.

---

## Alcance

### Incluye

* Proceso de extracción de datos desde las fuentes especificadas.
* Uso de arquitectura medallion.
* Capas Bronze, Silver y Gold.
* Transformación de datos.
* Chequeos de calidad de datos.
* Persistencia de resultados de calidad.
* Data Warehouse con modelo estrella.
* Plataforma de BI.
* Plataforma de gobierno de datos.
* Orquestación con DAGs definidos como código.
* Idempotencia en los procesos.
* Retries con backoff.
* Logs y status accesibles.
* Reprocesamiento histórico / backfill.
* Definición y justificación del tipo de carga en un ADR.
* Documentación en README.md.
* Documentación del modelo de datos.
* Seguimiento de linaje.
* Runbooks por rol.
* ADRs sobre decisiones clave de la Fase 2.

### No Incluye

* No especificado en la adenda técnica.

---

## Stakeholders

| Stakeholder             | Descripción                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------- |
| Desarrolladores         | Responsables de crear PRs y recibir feedback sobre los tests del código.            |
| Usuarios de la API      | Usuarios que deben consumir el servicio mediante una API REST.                      |
| Administradores         | Usuarios que deben acceder vía web a métricas relevantes de ejecución del servicio. |
| Usuarios no técnicos    | Usuarios que deben revisar datos mediante la plataforma de BI.                      |
| Roles de negocio        | Al menos un rol cercano al negocio debe contar con un runbook específico.           |
| Roles de implementación | Al menos un rol cercano a la implementación debe contar con un runbook específico.  |

---

## Requerimientos Funcionales

* **Extracción de Datos**: DEBE haber un proceso de extracción de las fuentes de datos.

* **Fuente de Producción de Pozos**: El proceso de extracción DEBE incluir la fuente “Producción de Pozos de Gas y Petróleo No Convencional”:
  https://datos.gob.ar/dataset/energia-produccion-petroleo-gas-por-pozo-capitulo-iv/archivo/energia_b5b58cdc-9e07-41f9-b392-fb9ec68b0725

* **Fuente Complementaria de Pozos**: El proceso de extracción DEBE incluir el “Listado de pozos cargados por empresas operadoras” como información complementaria:
  https://datos.gob.ar/dataset/energia-produccion-petroleo-gas-por-pozo-capitulo-iv/archivo/energia_cbfa4d79-ffb3-4096-bab5-eb0dde9a8385

* **Arquitectura Medallion**: Se DEBE utilizar la arquitectura medallion para procesar los datos.

* **Plataforma de BI**: DEBE haber una plataforma de BI en la cual usuarios no técnicos puedan revisar los datos.

* **Plataforma de Gobierno de Datos**: DEBE haber una plataforma de gobierno de datos en la cual se puedan ver:

  * Los workflows de extracción de datos.
  * Los datos en el Data Warehouse.
  * La última vez que los datos fueron actualizados.

* **Orquestación**: DEBE haber una herramienta de orquestación con DAGs definidos como código, por ejemplo Airflow, Prefect, Dagster o equivalente.

* **Propiedades de los DAGs**: Los DAGs DEBEN tener:

  * Idempotencia.
  * Retries con backoff.
  * Observabilidad mínima, incluyendo logs y status accesibles.

* **Backfill**: DEBE existir un procedimiento documentado y verificable de reprocesamiento histórico / backfill.

* **Tipo de Carga**: DEBE definirse y justificarse explícitamente el tipo de carga en un ADR. Las alternativas mencionadas son:

  * Full.
  * Incremental append.
  * Merge.
  * Upsert.

* **Semantic Layer**: El sistema PUEDE implementar un semantic layer como dbt semantic layer, Cube.dev, vistas lógicas en el warehouse o similar, para exponer métricas de negocio definidas una sola vez. Este punto es bonus.

---

## Requerimientos No Funcionales

* **README.md**: El repositorio DEBE incluir un archivo README.md con instrucciones para:

  * Actualizar los workflows.
  * Acceder al sistema de BI.
  * Acceder al sistema de gobierno de datos.

* **Documentación de Arquitectura**: El README.md DEBE incluir una descripción de la arquitectura de datos desarrollada.

* **Documentación del Modelo de Datos**: DEBE haber documentación del modelo de datos utilizado.

* **Calidad de Datos**: DEBE haber chequeos de calidad de los datos que queden persistidos con mínimo 3 dimensiones vistas en clase, como schema y linaje.

* **Persistencia de Calidad**: Los resultados del chequeo de calidad DEBEN quedar persistidos, no solo como asserts en runtime.

* **Consecuencia Operativa ante Falla de Calidad**: Si falla un check, DEBE tener consecuencia operativa, por ejemplo:

  * Alerta.
  * Bloqueo de promoción aguas abajo.
  * Marca de calidad visible.

* **Modelo Estrella**: El Data Warehouse DEBE utilizar el modelo estrella.

* **Reprocesamiento por Fecha**: DEBE ser posible reprocesar los datos de una fecha dada en caso de que haya cambios.

* **Idempotencia**: El procesamiento de datos DEBE ser idempotente.

* **Linaje de Datos**: DEBE haber alguna funcionalidad para seguir el linaje de los datos.

* **Herramienta de Gobierno**: La plataforma de gobierno DEBE estar implementada con alguna herramienta vista en clase o tutoría, como DataHub. Se PUEDEN explorar alternativas si está debidamente justificado.

* **Documentación del Modelo Dimensional**: DEBE haber documentación del modelo de datos que incluya:

  * Grano de la fact table.
  * Dimensiones.
  * Surrogate keys donde aplique.
  * Decisión de SCD si las dimensiones cambian.

---

## Métricas de éxito / KPIs

No especificado en la adenda técnica.

---

## Dependencias y riesgos

### Dependencias

* Disponibilidad de las fuentes de datos especificadas.
* Selección e implementación de una herramienta de orquestación.
* Selección e implementación de una plataforma de BI.
* Selección e implementación de una plataforma de gobierno de datos.
* Definición de ADRs válidos con comparación de alternativas.
* Documentación del modelo de datos.
* Implementación de chequeos persistidos de calidad de datos.
* Definición de runbooks por rol.

### Riesgos

* Que los ADRs sean inválidos por no comparar alternativas o por solo describir el camino tomado.
* Que los chequeos de calidad queden únicamente como asserts en runtime y no queden persistidos.
* Que no exista una consecuencia operativa ante fallas de calidad.
* Que no se documente correctamente el procedimiento de backfill.
* Que el procesamiento no sea idempotente.
* Que no se pueda seguir el linaje de los datos.
* Que los runbooks sean genéricos y no describan procedimientos concretos propios del proyecto.

---

## Roadmap

### Fase 2

* **Objetivo**: Desarrollar la funcionalidad del sistema base junto con la base necesaria sobre la cual se llevará a cabo un desarrollo ágil.
* **Fecha estimada**: No especificado en la adenda técnica.
* **Entregables**:

  * Proceso de extracción de datos.
  * Arquitectura medallion.
  * Data Warehouse.
  * Plataforma de BI.
  * Plataforma de gobierno de datos.
  * Herramienta de orquestación con DAGs como código.
  * Procedimiento de backfill.
  * ADRs de decisiones clave.
  * README.md.
  * Documentación del modelo de datos.
  * Chequeos de calidad persistidos.
  * Funcionalidad de linaje.
  * Runbooks por rol.

---

## Preguntas abiertas

* ¿Qué herramienta de orquestación se utilizará: Airflow, Prefect, Dagster u otra equivalente?
* ¿Qué plataforma de BI se utilizará?
* ¿Qué plataforma de gobierno de datos se utilizará?
* ¿Qué herramienta se utilizará para seguir el linaje de los datos?
* ¿Qué tipo de carga se definirá en el ADR: full, incremental append, merge o upsert?
* ¿Qué dimensiones de calidad de datos, además de schema y linaje, serán implementadas?
* ¿Qué consecuencia operativa se aplicará ante fallas de calidad?
* ¿Qué roles serán elegidos para los runbooks?
* ¿Se implementará semantic layer como bonus?

---

## Arquitectura Propuesta

En base a la adenda técnica de Fase 2, la arquitectura esperada sigue el siguiente flujo:

```text
Data Sources
    ↓
Extracción de Datos
    ↓
Bronze Layer
    ↓
Silver Layer
    ↓
Gold Layer
    ↓
Data Warehouse
    ↓
BI Platform / Data Governance Platform
    ↓
Admins
```

La arquitectura también contempla una herramienta de orquestación que interactúa con:

* Extracción de datos.
* Transformación de datos.
* Calidad de datos.
* Plataforma de gobierno de datos.

La arquitectura debe implementar el patrón medallion con capas Bronze, Silver y Gold, junto con procesos de transformación y calidad de datos antes de disponibilizar la información en el Data Warehouse.

---

## Runbooks

El equipo DEBE elegir al menos 2 roles distintos de los vistos en clase, donde:

* Al menos uno sea de perfil más cercano al negocio, como:

  * Data PM.
  * Data Analyst.
  * Data Owner.
  * Usuario de BI.

* Al menos uno sea más cercano a la implementación, como:

  * Data Engineer.
  * Analytics Engineer.
  * Data Steward.

Para cada uno de esos roles, el equipo DEBE escribir un runbook dirigido a ese tipo de usuario en:

```text
docs/runbooks/
```

Ejemplos:

```text
docs/runbooks/data-engineer.md
docs/runbooks/bi-user.md
```

Cada runbook DEBE describir un procedimiento concreto y propio de ese rol dentro de este proyecto. No debe ser genérico.

Cada runbook DEBE incluir como mínimo:

* Propósito y disparador: para qué sirve y cuándo se ejecuta.
* Rol/dueño y prerrequisitos: quién lo corre, qué accesos, insumos o herramientas necesita.
* Pasos: el procedimiento numerado, ejecutable de punta a punta.
* Validación: cómo sabe el rol que salió bien, incluyendo checks, queries de control o métrica esperada.
* Si algo falla: rollback, plan B y a quién o qué se escala.
* Consideraciones no funcionales: límites y garantías que ese rol ownea o le importan, por ejemplo:

  * Latencia.
  * Frescura.
  * Costo.
  * Seguridad / privacidad.
  * PII.
  * Calidad de dato.
  * SLAs.
  * Gobernanza.

El runbook DEBE dejar explícitas y justificadas, con al menos un párrafo, dos decisiones del proyecto:

1. **Una decisión funcional**: decisión sobre qué hace el procedimiento o el sistema, por ejemplo:

   * Qué se transforma.
   * Qué métrica se define.
   * Qué se expone.
   * Qué se valida.

2. **Una decisión no funcional**: decisión sobre cómo debe comportarse el sistema, por ejemplo:

   * Cada cuánto corre.
   * Cuánto puede costar.
   * Qué nivel de privacidad o seguridad aplica.
   * Qué umbral de calidad, disponibilidad o disponibilidad se considera aceptable.

La justificación DEBE fundamentar por qué esa decisión tiene sentido desde la perspectiva e incentivos del rol. No alcanza con justificarla diciendo que es una buena práctica.

---

## ADRs

Los ADRs DEBEN cubrir las decisiones clave de la Fase 2:

* Orquestación.
* Capas medallion.
* Tipo de carga: full vs incremental.
* Modelo dimensional.
* Calidad de datos.
* Gobierno de datos.

Los ADRs que no lleven a cabo una comparación de alternativas, o que únicamente describan el camino tomado, serán considerados inválidos y estarán fuera de la evaluación del trabajo.

