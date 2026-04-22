# Addendum v0.2 al PRD — Plataforma Predictiva

- **Versión:** v0.2
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Estado:** Propuesto — pendiente de validación con cliente
- **Documento padre:** [PRD v0.1](./prd-v0.1.md)

## Propósito

El PRD v0.1 deja explícitamente cuatro preguntas abiertas que requieren
respuesta antes de avanzar con la especificación técnica detallada de cada
fase. Este documento:

1. Propone respuestas fundamentadas a cada pregunta abierta.
2. Documenta las asunciones que soportan cada respuesta.
3. Identifica los puntos que, en un proyecto real, requerirían validación
   con el cliente antes de ser considerados definitivos.

Las decisiones que emergen de este Addendum se profundizan en ADRs
específicos referenciados al final de cada sección. El Addendum es el
resumen ejecutivo; los ADRs son el análisis completo.

## Cómo leer este documento

Cada sección sigue la misma estructura:

- **Pregunta original** tal como aparece en el PRD.
- **Contexto** que clarifica el alcance y las implicancias de la
  pregunta.
- **Propuesta** del equipo con justificación.
- **Asunciones** que soportan la propuesta.
- **Puntos a validar con el cliente** antes de cerrar la decisión.

---

## Pregunta 1 — Fuentes de datos y especificaciones

> _¿Cuáles son las fuentes de datos específicas (sistemas, bases de datos)
> que se utilizarán para la ingesta de datos históricos de producción,
> pozos y variables operativas? Se requiere la especificación técnica de
> los esquemas de datos._

### Contexto

Esta pregunta condiciona todo el diseño del módulo de ingesta (Fase 2). En
la industria de oil & gas (upstream), las fuentes típicas de datos de
producción son:

- **Sistemas SCADA** (Supervisory Control and Data Acquisition): capturan
  mediciones en tiempo real de sensores en pozos y facilities.
- **Historiadores de procesos** (típicamente OSIsoft PI System o Aveva
  PI): almacenan series temporales de alta frecuencia con retención larga.
- **Sistemas de allocation**: distribuyen la producción agregada medida en
  facilities entre los pozos individuales (la medición por pozo en tiempo
  real es cara, así que se estima por reglas).
- **Reportes diarios de producción (DPR)**: archivos o registros manuales
  con el volumen diario por pozo.
- **Sistemas de gestión de operaciones** (ej: IBM Maximo) para eventos de
  workover, downtime planificado, etc.
- **Data lakes corporativos** donde se consolidan las anteriores (patrón
  moderno en empresas con madurez de datos).

El formato típico de los datos es **series temporales** con granularidad
diaria o mensual para producción agregada, y granularidad mayor (minutos
u horas) para datos de SCADA.

### Propuesta

Para el alcance del trabajo integrador, proponemos un **enfoque por
capas de compatibilidad**:

**Capa 1 — Formato de intercambio estándar (obligatoria para todas las
fases):**

Definimos un formato CSV/Parquet canónico que representa el estado de la
verdad sobre los datos de producción. Este formato está desacoplado de la
fuente original y es el que consume el motor de pronóstico. Esquema
mínimo propuesto:

| Columna             | Tipo            | Descripción                              | Obligatoria |
| ------------------- | --------------- | ---------------------------------------- | ----------- |
| `well_id`           | string          | Identificador único del pozo             | Sí          |
| `date`              | date (ISO 8601) | Fecha de la medición                     | Sí          |
| `oil_rate_bbl_d`    | float           | Producción de petróleo en bbl/día        | Sí          |
| `gas_rate_mscf_d`   | float           | Producción de gas en Mscf/día            | Opcional    |
| `water_rate_bbl_d`  | float           | Producción de agua en bbl/día            | Opcional    |
| `downtime_hours`    | float           | Horas sin producción en el día           | Opcional    |
| `data_quality_flag` | enum            | `measured`, `allocated`, `estimated`     | Sí          |
| `source_system`     | string          | Nombre del sistema origen (trazabilidad) | Sí          |

**Capa 2 — Conectores específicos (agregables por fase):**

La arquitectura preverá que la fuente real pueda ser enchufable mediante
adaptadores (patrón de integración estándar). Para Fase 2 implementamos
un adaptador de referencia: **upload manual de CSV** vía interfaz web o
endpoint de API. Adaptadores adicionales (PI System, base de datos SQL,
S3, etc.) quedan fuera de alcance pero la arquitectura los permite.

**Capa 3 — Datos sintéticos para desarrollo y demo:**

Dado que no tenemos acceso a datos reales de un operador, generaremos un
**dataset sintético** con curvas de producción realistas (basadas en
modelos de Arps) para poblar el sistema durante desarrollo y demo. Este
dataset reside en `data/synthetic/` y es el que se carga en la demo de
Fase 1.

### Asunciones

- El "cliente" del sistema es un área de planificación que ya cuenta con
  sus datos de producción consolidados en algún sistema interno, y puede
  exportarlos a CSV o Parquet.
- Las variables de mayor valor para el pronóstico son oil rate, gas rate
  y downtime. Otras variables (presiones, temperaturas, GOR, BSW) pueden
  sumarse en iteraciones futuras.
- La granularidad diaria es suficiente para los horizontes de pronóstico
  de planning (ver Pregunta 2). Granularidad horaria o menor no aporta
  valor incremental para pronóstico de medio y largo plazo.
- El sistema puede ingestar datos históricos de hasta 10 años hacia
  atrás por pozo, con pozos activos del orden de decenas a centenas
  (no miles) para el MVP.

### Puntos a validar con el cliente

Antes de cerrar Fase 2, en un proyecto real se debería validar:

1. ¿Cuál es el sistema fuente real (PI, SAP, data lake)? Esto define el
   primer conector concreto a implementar.
2. ¿Cuál es la volumetría real? (cantidad de pozos, años de histórico,
   granularidad). Impacta dimensionamiento de infraestructura.
3. ¿Qué variables operativas adicionales (workover, inyección,
   ESP/PCP parameters) están disponibles y cuáles son prioritarias?
4. ¿Existen datos de reservorio (PVT, pruebas de presión, logs) que
   deban integrarse? Pueden mejorar significativamente los modelos.
5. ¿Cuál es el formato de los identificadores de pozo? (código interno,
   API number, UWI).

### Referencias

- ADR pendiente: _Formato de intercambio de datos y estrategia de
  adaptadores_ (a escribir en inicio de Fase 2).
- Adenda técnica de Fase 2 (detallará el esquema completo y los
  adaptadores concretos).

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
- Reportar tanto MAPE como **MAE absoluto en bbl/d**: el MAPE es
  engañoso para pozos con producción baja.

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

## Síntesis

Las respuestas propuestas en este Addendum se sostienen sobre un patrón
común: **diseñar para lo concreto que vamos a construir, pero dejar la
arquitectura abierta a lo que en un proyecto real se validaría con el
cliente**.

Puntos clave que quedan pendientes de validación con cliente (y que, en
un proyecto real, bloquearían el avance a la fase siguiente sin
respuesta):

1. Sistema(s) fuente real(es) de datos de producción.
2. Horizonte de planning crítico para el negocio.
3. Existencia y requerimientos de identity provider corporativo.
4. MAPE actual del proceso manual (baseline de negocio real).

Para el MVP del TP, asumimos respuestas razonables a estos puntos con
el fin de avanzar, y lo documentamos explícitamente.

## Cambios respecto al PRD original

Este Addendum **no modifica** el PRD v0.1. Agrega precisiones que deben
leerse junto con él. Si alguna respuesta del Addendum requiriera
modificar requerimientos del PRD, se emitiría un PRD v0.2 con el
delta explícito.

## Historial de versiones

| Versión | Fecha      | Cambios                                                                                             |
| ------- | ---------- | --------------------------------------------------------------------------------------------------- |
| v0.1    | 2026-04-20 | Versión inicial con respuestas a las 4 preguntas abiertas.                                          |
| v0.2    | 2026-04-XX | Actualizada Pregunta 3 con decisión de cliente para Fase 1 (API key estática según adenda técnica). |
