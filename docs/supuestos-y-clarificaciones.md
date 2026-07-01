# Supuestos y clarificaciones al PRD — Plataforma Predictiva

- **Versión:** v0.3
- **Fecha:** 2026-06-07
- **Autores:** Equipo Petrocast
- **Estado:** Vigente — preguntas abiertas pendientes de validación
- **Documento padre:** [PRD v0.1](./assignment/prd.md)

## Propósito

El PRD v0.1 dejó cuatro preguntas abiertas. La **Adenda Técnica de Fase 2**
resolvió la Pregunta 1 (fuentes y especificación de datos), por lo que su
propuesta original se retira y este documento se reencuadra como **catálogo de
ambigüedades y preguntas abiertas** pendientes:

1. Las preguntas del PRD que siguen sin resolver: horizontes (P2), seguridad
   de producción (P3, solo Fase 1 está cerrada) y baseline del KPI (P4).
2. Las **ambigüedades y preguntas abiertas que introduce la propia Adenda de
   Fase 2** (sección final).

Para cada punto se deja la lectura/propuesta tentativa del equipo y lo que, en
rigor, debería confirmarse con la cátedra/cliente antes de cerrarlo. Las
decisiones de diseño se profundizan en ADRs.

> **Estado:** ✅ resuelta · ⚠️ ambigüedad o decisión abierta.

---

## Pregunta 1 — Fuentes y especificación de datos · ✅ RESUELTA por la Adenda de Fase 2

> _¿Cuáles son las fuentes de datos específicas (sistemas, bases de datos)
> que se utilizarán para la ingesta de datos históricos de producción,
> pozos y variables operativas? Se requiere la especificación técnica de
> los esquemas de datos._

La Adenda Técnica de Fase 2 **cierra esta pregunta**: dejó de ser un supuesto
del equipo. Se retira la propuesta original (formato canónico inventado,
conector de _upload_ manual de CSV y dataset sintético como fuente), que quedó
obsoleta y, en unidades y granularidad, era incorrecta.

**Lo que fijó la cátedra** (`adenda-fase-2.md`):

- **Fuentes** (datos.gob.ar — Secretaría de Energía, "Capítulo IV", No Convencional):
  - Producción por pozo: `energia_b5b58cdc-9e07-41f9-b392-fb9ec68b0725`.
  - Listado de pozos por empresas operadoras (complementaria → tabla maestra de
    pozos): `energia_cbfa4d79-ffb3-4096-bab5-eb0dde9a8385`.
- Arquitectura **medallion**, **modelo estrella** en el DWH, orquestador con
  DAGs como código, gobierno con **DataHub** y chequeos de calidad persistidos.

**Esquema real** (verificado contra la fuente; reemplaza al esquema asumido):

| Aspecto         | Realidad de la fuente                                                              |
| --------------- | ---------------------------------------------------------------------------------  |
| Granularidad    | **Mensual** (una fila por pozo-mes), no diaria                                     |
| Unidades        | `prod_pet` [m³], `prod_gas` [miles de m³], `prod_agua` [m³] — sistema **métrico**  |
| Identificadores | `sigla` (string, boca de pozo) + `idpozo` (int, por formación productiva)          |
| Tiempo efectivo | `tef` (días con producción en el mes) → permite derivar caudal diario              |
| Cobertura       | 2006–2026; miles de pozos (no convencional)                                        |

Esto **resuelve además** la sub-pregunta #5 del documento original (formato de
identificadores de pozo): es `sigla`/`idpozo`, no UWI/API number.

Las decisiones que la adenda **delega** (grano, SCD, tipo de carga, BI, etc.) y
las **ambigüedades que deja abiertas** se tratan en
[Ambigüedades de la Adenda de Fase 2](#ambigüedades-y-preguntas-abiertas-de-la-adenda-de-fase-2).

---

## Pregunta 2 — Definición de horizonte de pronóstico

> _Se necesita confirmar la definición temporal exacta de los horizontes
> de pronóstico: ¿Cuál es el período para "corto plazo", "medio plazo" y
> "largo plazo"? (Esto impacta directamente en el KPI de Precisión del
> Pronóstico)._

### Contexto

Los horizontes de pronóstico en la industria upstream no son arbitrarios:
están atados a **procesos de negocio concretos** con distintas frecuencias
de ejecución. La definición "correcta" depende de qué proceso alimenta el
pronóstico.

Procesos típicos y sus horizontes asociados:

| Proceso de negocio                           | Horizonte típico | Frecuencia de update |
| -------------------------------------------- | ---------------- | -------------------- |
| Operaciones del día, despacho, logística     | 1–14 días        | Diario               |
| Commitments comerciales, nominations         | 1–3 meses        | Semanal/Mensual      |
| Presupuesto operativo, plan de workovers     | 3–18 meses       | Mensual              |
| Budget anual y forecast multi-anual          | 12–36 meses      | Trimestral           |
| Plan de desarrollo de campo, inversión CAPEX | 3–30 años        | Anual                |

La precisión alcanzable cae dramáticamente con el horizonte: pronósticos
a días pueden lograr MAPE < 5%; pronósticos a años pueden tener MAPE

> 30% incluso con modelos sofisticados.

### Propuesta

Adoptamos la siguiente segmentación, alineada a los ciclos de planning
más comunes en la industria:

| Horizonte       | Definición        | Use case primario                              | MAPE objetivo |
| --------------- | ----------------- | ---------------------------------------------- | ------------- |
| **Corto plazo** | 0–90 días         | Commitments comerciales, operación mensual     | ≤ 10%         |
| **Medio plazo** | 3–18 meses        | Presupuesto operativo anual, plan de workovers | ≤ 20%         |
| **Largo plazo** | 18 meses – 5 años | Budget plurianual, decisiones de inversión     | ≤ 30%         |

**Granularidad de salida del pronóstico:**

- Corto plazo: diaria.
- Medio plazo: mensual.
- Largo plazo: mensual o trimestral.

**Implicancia para el modelo:**
La plataforma debe poder generar pronósticos con granularidad diaria y
mensual. Pronósticos largos se computan mensualmente y, si se necesita
una vista diaria, se interpolan (sin aumentar precisión real).

### Asunciones

- El usuario primario del pronóstico es el área de planificación y
  presupuesto, cuyo ciclo principal es anual con revisiones trimestrales.
  Esto hace que el foco esté en medio plazo.
- La industria argentina sigue patrones similares a la global en ciclos
  de planning.
- La precisión alcanzable en largo plazo es inherentemente limitada; el
  valor del pronóstico largo es más como **guía de escenarios** que como
  número puntual.

### Puntos a validar con el cliente

1. ¿Cuál es el horizonte de planning más crítico para la toma de
   decisiones (donde más duele la imprecisión)?
2. ¿Existen compromisos comerciales o regulatorios que impongan
   horizontes específicos (ej: nominations de take-or-pay, DGO)?
3. ¿Los KPIs de MAPE objetivo son realistas respecto al baseline actual?
   Esto se profundiza en Pregunta 4.

### Referencias

- ADR pendiente: _Segmentación de horizontes de pronóstico y
  granularidad de salida_ (a escribir en Fase 3).
- KPI de Precisión del Pronóstico en el PRD original.

---

## Pregunta 3 — Requerimientos de seguridad de la API

> _¿Existen requerimientos no funcionales específicos de seguridad o
> autenticación (ej. OAuth, claves API, límites de tasa) para la API de
> Consulta (REST)?_

### Contexto

Los datos de producción de hidrocarburos son **altamente sensibles**:
tienen impacto directo en valuación de activos, cumplimiento regulatorio
(ante la Secretaría de Energía en Argentina, por ejemplo), decisiones de
inversión y compromisos comerciales. Una filtración de datos de
producción puede tener consecuencias económicas, regulatorias y
reputacionales serias.

Al mismo tiempo, la API debe ser **consumible por sistemas internos**
(caso de uso 3 del PRD), lo que impone la necesidad de autenticación
automatizable (no solo humana).

### Propuesta

Adoptamos un modelo de seguridad **por capas**, proporcional al riesgo:

**Capa 1 — Autenticación (quién consume):**

- **API Keys** por cliente/sistema consumidor para autenticación
  servidor-a-servidor. Cada sistema consumidor recibe una key única,
  rotable y revocable.
- **OAuth 2.0 con JWT** para usuarios humanos que acceden desde la UI.
  Tokens con expiración corta (1 hora) y refresh tokens con expiración
  más larga.
- Las API Keys y credenciales de usuarios **nunca se loguean** ni se
  exponen en mensajes de error.

**Capa 2 — Autorización (qué puede hacer):**

- Modelo RBAC (Role-Based Access Control) con los roles definidos en
  el PRD: Analista de Planificación, Ingeniero de Reservorios,
  Arquitecto/Especialista de Datos.
- Para el MVP, roles de solo-lectura son suficientes para la mayoría
  de los consumidores. Creación y modificación de escenarios requiere
  rol de Ingeniero de Reservorios o superior.

**Capa 3 — Protección de la API (cómo se usa):**

- **Rate limiting** por API Key: límite por defecto de 100 requests/
  minuto, configurable por cliente. Previene abuso y protege la
  infraestructura.
- **HTTPS obligatorio**, sin fallback a HTTP.
- **Headers de seguridad**: CORS configurado explícitamente,
  `Content-Security-Policy`, `X-Content-Type-Options`, etc.
- **Validación estricta de inputs** en todos los endpoints.

**Capa 4 — Trazabilidad:**

- **Audit log** de todos los accesos: qué key, qué endpoint, qué
  parámetros, qué respuesta (códigos, no bodies completos), qué
  timestamp.
- Este log es además evidencia para el KPI de gobernanza de datos
  (cobertura de trazabilidad) definido en el PRD.

**Fuera de alcance para el MVP (diferible):**

- Federación con identity providers corporativos (SAML, Azure AD).
- Cifrado de datos en reposo a nivel aplicación (se asume cifrado de
  la capa de infraestructura del proveedor cloud).
- Data masking por rol (ej: pozos en desarrollo visibles solo a ciertos
  roles).

### Decisión del cliente para Fase 1

La adenda técnica de Fase 1 emitida por la cátedra define una
implementación **simplificada** de seguridad, válida exclusivamente
para esta fase:

- **Mecanismo:** API key estática preconfigurada.
- **Valor:** `abcdef12345`.
- **Transporte:** header HTTP `X-API-Key`.
- **Validación:** se valida antes de responder cualquier request.
- **Respuesta en caso de fallo:** HTTP 403 (Forbidden).
- **Alcance:** aplica a todos los endpoints de la API
  (`/api/v1/forecast`, `/api/v1/wells`).

**Relación con la propuesta general:** esta decisión **no reemplaza**
la propuesta de seguridad por capas descrita más arriba, que debería
implementarse en fases posteriores o en un entorno productivo real.
Para Fase 1, el cliente priorizó la simplicidad del mock sobre la
robustez de seguridad, lo cual es razonable dado el propósito de esta
fase (demo del servicio, no exposición a sistemas productivos).

**Implicancias técnicas para el MVP:**

- La API key se lee desde una variable de entorno (`API_KEY`), no
  hardcodeada en el código, aunque su valor default coincida con el
  especificado. Esto facilita rotación en fases posteriores sin cambios
  de código.
- El audit log propuesto en la sección general **se mantiene** para
  Fase 1 aunque la autenticación sea trivial, porque es evidencia para
  el KPI de gobernanza de datos del PRD.
- El rate limiting propuesto se difiere a Fase 2+, salvo que durante
  Fase 1 se detecte abuso.

**Brecha respecto a la propuesta completa:**

| Capa de seguridad                 | Propuesta general                     | Fase 1 (adenda)                   |
| --------------------------------- | ------------------------------------- | --------------------------------- |
| Autenticación servicio-a-servicio | API Keys rotables por cliente         | API Key estática única            |
| Autenticación de usuarios         | OAuth 2.0 + JWT                       | No aplica (no hay UI autenticada) |
| Autorización (RBAC)               | Por rol (Analista / Ingeniero / Data) | No aplica                         |
| Rate limiting                     | 100 req/min por key                   | No requerido                      |
| Audit log                         | Completo                              | Completo                          |
| HTTPS obligatorio                 | Sí                                    | Recomendado                       |
| Headers de seguridad              | Sí                                    | Recomendado                       |

Las capas diferidas **se retomarán** en la planificación de Fase 2+
según decisión del equipo, o permanecerán como recomendaciones para
producción real.

### Asunciones

- La API se expondrá dentro de una red corporativa o VPN del cliente,
  no en internet pública abierta. Esto modera (pero no elimina) el
  riesgo de ataques externos.
- El volumen de consumidores de la API es bajo (decenas, no miles), lo
  que hace viable el modelo de API Keys sin necesidad de un sistema
  de gestión de identidades completo.
- Los profesores evaluarán la **presencia del diseño de seguridad**,
  no necesariamente su implementación completa en Fase 1. Iremos
  implementando capas progresivamente por fase.

### Puntos a validar con el cliente

1. ¿Existe un identity provider corporativo con el que la plataforma
   deba federarse? (Azure AD, Okta, etc.).
2. ¿La API debe exponerse solo a sistemas internos o también a
   terceros (socios comerciales, consultoras)?
3. ¿Existen requerimientos regulatorios específicos
   (compliance con normas de Secretaría de Energía, ISO 27001, etc.)?
4. ¿Hay políticas corporativas de rotación de credenciales, auditoría,
   o retención de logs que debamos respetar?

### Referencias

- ADR pendiente: _Arquitectura de seguridad y autenticación de la API_
  (a escribir en Fase 1 o inicio de Fase 2).
- [OWASP API Security Top 10](https://owasp.org/API-Security/).
- Requerimiento no funcional de disponibilidad del PRD (99.5%) — la
  seguridad no debe comprometerlo.

---

## Pregunta 4 — Definición de baseline para KPI

> _Confirmar el "baseline" (línea de base) actual para el cálculo del
> Error Medio Absoluto Porcentual (MAPE) y establecer el valor objetivo
> de reducción._

### Contexto

El PRD define el KPI primario como "reducción del MAPE respecto a un
baseline de mantener el último datapoint". Este baseline — conocido en
la literatura de forecasting como **naïve forecast** o _persistence
model_ — es intencionalmente débil. No es el baseline típico de la
industria.

Baselines alternativos, en orden creciente de sofisticación:

1. **Naïve (persistence):** el valor futuro = último valor observado.
2. **Naïve estacional:** el valor futuro = mismo mes del año anterior.
3. **Declinación exponencial** a tasa fija histórica del pozo.
4. **Arps Decline Curve Analysis** (exponencial, hiperbólica, armónica).
   Es el estándar de facto de la industria desde 1945.
5. **Modelos estadísticos** (ARIMA, Exponential Smoothing).
6. **Modelos de ML** (gradient boosting, redes neuronales, modelos
   fundacionales de series temporales).

El objetivo "superar el naïve" es un piso muy bajo. Superar Arps es un
desafío real y es donde ML aporta valor marginal genuino.

### Propuesta

Definimos un **esquema escalonado** de baselines y objetivos, alineado
al nivel de madurez esperable en cada fase:

**Baseline primario: Arps Decline Curve Analysis**

Usamos Arps como baseline de referencia porque:

- Es el **estándar de la industria** — cualquier ingeniero de
  reservorios lo reconoce y ya lo usa.
- Superar Arps con ML es un **resultado defendible** frente a
  stakeholders técnicos. Superar un naïve no lo es.
- Arps es **transparente y explicable**, lo que establece un piso
  razonable de confianza.

**Objetivos de MAPE por horizonte respecto a Arps:**

| Horizonte      | MAPE Arps típico (literatura) | Objetivo MVP      | Objetivo ideal     |
| -------------- | ----------------------------- | ----------------- | ------------------ |
| Corto (0–90d)  | 5–10%                         | ≤ MAPE Arps       | 20% mejor que Arps |
| Medio (3–18m)  | 10–20%                        | ≤ MAPE Arps + 2pp | 15% mejor que Arps |
| Largo (18m–5a) | 20–30%                        | ≤ MAPE Arps + 5pp | Igual o superior   |

**Interpretación:** en el MVP, el éxito es **no empeorar a Arps**
significativamente y ofrecer las ventajas adicionales de la plataforma
(escenarios what-if, visualización, trazabilidad, API). En el escenario
ideal, el modelo supera a Arps en corto y medio plazo.

**Baseline secundario (a reportar):** naïve persistence, para
completitud y para cumplir literalmente con lo que dice el PRD original.

**Metodología de cálculo del MAPE:**

- **Backtesting con split temporal**, nunca aleatorio: entrenar con
  datos hasta el mes M, predecir meses M+1 a M+k, comparar con
  realidad.
- Reportar MAPE por pozo y agregado, en forma de distribución
  (mediana, p75, p90) y no solo promedio — los promedios ocultan colas
  largas en datasets de pozos heterogéneos.
- Excluir pozos con menos de 12 meses de histórico de la evaluación
  (no es posible computar Arps confiable con menos).
- Reportar tanto MAPE como **MAE absoluto en m³**: el MAPE es
  engañoso para pozos con producción baja (la fuente es métrica, no bbl/d).
- **Métrica primaria escalada: MASE** (_Mean Absolute Scaled Error_). Escala
  el error contra el naive in-sample → un MASE < 1 significa literalmente
  "le ganamos a la persistencia naive" (el KPI del PRD), y a diferencia del
  MAPE **no explota con meses en cero** (pozos shut-in). Se fija en Fase 3
  (ADR-0030 / backlog #01).

### Asunciones

- El dataset disponible (sintético en Fase 1, posiblemente real en
  Fases posteriores) tiene suficientes pozos con suficiente histórico
  para entrenar y validar modelos no triviales.
- El equipo tiene o puede adquirir el conocimiento para implementar
  Arps correctamente (la librería de Python más común es
  [`petbox-dca`](https://github.com/petbox-dev/dca)).
- El profesor evalúa rigor metodológico por sobre resultados numéricos
  espectaculares. Reportar honestamente "nuestro modelo empata con
  Arps pero aporta X, Y, Z" es mejor que afirmar mejoras no verificables.

### Puntos a validar con el cliente

1. ¿Cuál es el MAPE actual que logran con su proceso manual de
   pronóstico? Este sería el baseline real a superar.
2. ¿Cómo se distribuye el portfolio de pozos (maduros vs nuevos, altos
   vs bajos productores)? Impacta qué modelos son apropiados.
3. ¿Existe una herramienta ya en uso (IHS Harmony, S&P Aries) contra
   la cual deberíamos compararnos?
4. ¿El cliente tiene un umbral de mejora mínimo que justifique el
   costo de adoptar la nueva plataforma?

### Referencias

- ADR pendiente: _Selección de baselines y metodología de evaluación
  de modelos_ (a escribir al inicio de Fase 3).
- Arps, J. J. (1945). _Analysis of Decline Curves._ Transactions of
  the AIME, 160(01), 228–247. — referencia fundacional.
- [Hyndman, R. J. — "Another look at forecast-accuracy metrics for
  intermittent demand"](https://robjhyndman.com/papers/foresight.pdf) —
  sobre las limitaciones del MAPE.

---

## Ambigüedades y preguntas abiertas de la Adenda de Fase 2

La Adenda de Fase 2 fija el **qué** (fuentes, medallion, modelo estrella,
DataHub) pero deja puntos sin cerrar. Se separan en (A) ambigüedades que
conviene **confirmar con la cátedra** y (B) decisiones que la adenda **delega
en el equipo** y deben cerrarse en ADRs.

### A. Ambigüedades a confirmar con la cátedra

**⚠️ A1 — Fecha de entrega contradictoria.** El PRD fija Fase 2 el
**2026-06-09** (Roadmap) y la adenda dice **15 de junio** (`adenda-fase-2.md:80`).
Asumimos que rige la adenda (15-jun) por ser posterior y específica; confirmar.

**⚠️ A2 — Alcance de la ingesta no acotado.** La fuente cubre **2006–2026** y
**miles de pozos** (todo el no convencional del país). La adenda no dice cuánto
histórico ni qué universo ingestar: ¿serie completa o una ventana? ¿todo el país
o una cuenca (p. ej. Neuquina)? Impacta volumetría, costo e infraestructura.
_Supuesto:_ serie completa del dataset no convencional; se acotará si el costo lo
exige.

**⚠️ A3 — Reconciliación con el contrato de API de Fase 1.** La API de Fase 1
expone `id_well` (string), fechas **diarias** (`YYYY-MM-DD`) y un escalar `prod`
sin unidad; la fuente real es **mensual**, **métrica** y multi-fluido. Queda sin
definir: `id_well` ¿es `sigla` o `idpozo`? (un pozo puede producir de varias
formaciones → distinto grano); `prod` ¿es petróleo, gas o equivalente, y en qué
unidad?; ¿cómo se sirve un dato mensual sobre un contrato de fechas diarias?
_Supuesto:_ `prod = prod_pet` en m³, devolviendo el valor del mes
correspondiente a cada fecha. **Resuelto parcialmente (Fase 3):**
`well_id = idpozo` casteado a texto, alineado al grano de
`gold.fact_production` — decidido en
[ADR-0030](adr/0030-objetivo-predictivo-horizonte-metricas.md); el supuesto
provisorio `id_well = sigla` queda **superado**. La traducción `sigla` →
`idpozo` en la capa de API, si se necesita, es responsabilidad del contrato D
(#17 / ADR-0034).

**⚠️ A4 — Unidad de las métricas de negocio.** La adenda no dice en qué unidad
exponer la producción en el semantic/BI layer: ¿m³ nativo, BOE, o bbl/Mscf para
alinear con el vocabulario de industria? _Supuesto:_ m³ nativo en silver/gold;
conversión solo en la capa de presentación si se pide.

**⚠️ A5 — "Ver los datos en el data warehouse" desde el gobierno.** La adenda
pide ver "los datos en el DWH" en la plataforma de gobierno
(`adenda-fase-2.md:27-30`), pero DataHub es un **catálogo de metadata y linaje**,
no un visor de filas. ¿Alcanza metadata + lineage + última actualización, o
esperan preview de datos? _Lectura:_ metadata, esquema, linaje y frescura en
DataHub; el preview de filas vive en la herramienta de BI. (Nota: en la adenda
esos ítems están mal anidados como bullets sueltos.)

**⚠️ A6 — Tercera dimensión de calidad de datos.** Se exigen "mínimo 3
dimensiones de las vistas en clase, como schema y linaje" (`adenda-fase-2.md:45`):
schema y linaje son dos; la tercera depende del material de clase. _Supuesto:_
sumamos **completitud** y **unicidad/validez** sobre claves de negocio.
Confirmar cuáles cuentan.

**⚠️ A7 — PII / privacidad en runbooks.** Los runbooks deben tratar
privacidad/PII (`adenda-fase-2.md:65`), pero la fuente es **dato público**.
_Lectura:_ documentamos "sin PII (dato público)" y enfocamos esa dimensión en
integridad y uso responsable. Confirmar que basta.

### B. Decisiones que la adenda delega en el equipo (cerrar en ADRs)

No son ambigüedades de la consigna sino elecciones nuestras, pedidas
explícitamente como ADR con comparación de alternativas:

- **Orquestador:** Airflow vs Prefect vs Dagster (`adenda-fase-2.md:31`).
- **Tipo de carga:** full / incremental append / merge / upsert
  (`adenda-fase-2.md:34`). La fuente publica **DDJJ rectificadas** (revisa meses
  pasados) → empuja a **merge/upsert** por clave natural; a justificar.
- **Grano de la fact y clave natural:** el grano nativo es **pozo-mes**; clave
  candidata `(idpozo, anio, mes)` (¿o `sigla`?). Define la idempotencia del
  reproceso (`adenda-fase-2.md:48-52`).
- **SCD de las dimensiones** (empresa/área/yacimiento pueden cambiar)
  (`adenda-fase-2.md:52`).
- **Herramienta de BI** (`adenda-fase-2.md:26`): Metabase / Superset / Power BI / otra.
- **Roles + runbooks:** elegir ≥2 roles (uno de negocio, uno técnico)
  (`adenda-fase-2.md:54`).

> **Impacto en P2 y P4:** la fuente **mensual en m³** vuelve tentativa la
> "salida diaria" propuesta en la Pregunta 2 (solo alcanzable por interpolación)
> y obliga a expresar el MAPE/MAE en **m³**, no en bbl/d, en la Pregunta 4.

---

## Síntesis

Tras la Adenda de Fase 2:

- **Resuelto:** fuentes y especificación de datos (P1) — la cátedra fijó
  datasets, medallion, modelo estrella y gobierno.
- **Sigue abierto (PRD):** horizontes (P2), seguridad de producción (P3, solo
  Fase 1 cerrada) y baseline del KPI (P4) — temas de Fase 3.
- **Nuevo (Adenda Fase 2):** ambigüedades A1–A7 y decisiones delegadas (B).

Puntos que, en un proyecto real, bloquearían el avance sin respuesta de la
cátedra/cliente:

1. Fecha de entrega efectiva de Fase 2 (A1).
2. Reconciliación de la API de Fase 1 con el dato real mensual/métrico (A3).
3. Horizonte de planning crítico para el negocio (P2).
4. MAPE actual del proceso manual / baseline real (P4).

Para el MVP del TP asumimos respuestas razonables y las documentamos
explícitamente.

## Cambios respecto al PRD original

Este Addendum **no modifica** el PRD v0.1. Agrega precisiones que deben
leerse junto con él. Si alguna respuesta del Addendum requiriera
modificar requerimientos del PRD, se emitiría un PRD v0.2 con el
delta explícito.

## Historial de versiones

| Versión | Fecha      | Cambios                                                                                             |
| ------- | ---------- | --------------------------------------------------------------------------------------------------- |
| v0.1    | 2026-04-20 | Versión inicial con respuestas a las 4 preguntas abiertas.                                          |
| v0.2    | 2026-04-21 | Actualizada Pregunta 3 con decisión de cliente para Fase 1 (API key estática según adenda técnica). |
| v0.3    | 2026-06-07 | La Adenda de Fase 2 resuelve la P1: se retira la propuesta original y el documento se reencuadra como catálogo de ambigüedades. Se agregan las ambigüedades A1–A7 y las decisiones delegadas (B) de la Fase 2. |
