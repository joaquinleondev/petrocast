# Runbook Data Owner: decisión de aptitud del dato ante bloqueo de calidad

## Propósito y disparador

Este runbook guía al **Data Owner** cuando un asset check bloqueante falla en el
pipeline medallion y la notificación de calidad llega al canal configurado en
`PETROCAST_NOTIFICATION_WEBHOOK_URL`.

El disparador concreto es F2-18: un test dbt de `severity: error` sobre
`silver/silver_production` falló, su check bloqueante de Dagster terminó en rojo
y el asset `gold_dbt_assets` fue saltado en ese run. Las tablas `gold` conservan
el último snapshot válido mientras dura el bloqueo, pero el dato de ese período
no se promovió.

Este runbook cubre **un solo rol y una sola decisión**: si el dato —con los fallos
que tiene— es apto o no apto para uso de negocio, y qué acciones se derivan de
esa decisión. La ejecución técnica del reproceso la delega al Data Engineer
(ver [data-engineer.md](data-engineer.md)).

## Rol, dueño y prerrequisitos

- **Dueño:** Data Owner de Petrocast.
- **Responsabilidad:** decidir si el dato es apto para uso de negocio; no
  ejecutar el pipeline ni modificar reglas de calidad sin acuerdo del Data
  Engineer.
- **Escala a:** Data Engineer para ejecución, backfill o corrección de umbral;
  Platform/Infra si el DW o DataHub no responden.

Antes de empezar, el Data Owner necesita:

- La notificación recibida (run id de Dagster, check fallido, partición afectada).
- Acceso de lectura al DW (`dbt_test__audit` y `gold`) para inspeccionar filas
  fallidas y estado de Gold.
- Acceso a la UI de DataHub (`http://localhost:9002`) para navegar el linaje
  aguas abajo de `silver_production`.
- Acceso a Metabase (`http://localhost:3001`) para confirmar qué dashboards
  consumen el dato bloqueado.
- Contacto con el Data Engineer (canal del incidente, issue o chat del equipo).

## Decisiones del rol

### Decisión funcional: umbral de aptitud para uso

El Data Owner debe declarar un dato **apto para uso de negocio** o **no apto**
antes de autorizar cualquier acción. El criterio concreto es: si las filas
fallidas en `dbt_test__audit` representan una **fracción menor al 1 % de las
filas de la partición afectada en `silver_production`** y corresponden
exclusivamente a la dimensión de validez de rangos (valores fuera de rango
aislados), el dato puede declararse apto con observación y el Data Engineer
puede reprocesar sin esperar corrección de fuente. Si las filas fallidas superan
ese umbral, o si fallan las dimensiones de completitud o unicidad, el dato se
declara no apto hasta que la fuente se corrija.

Este umbral existe porque el Data Owner es el rol que responde ante el negocio
por la confianza en el número que aparece en los dashboards de Metabase. Un
umbral explícito evita que la decisión sea arbitraria o varíe por incidente:
el negocio prefiere bloquear y comunicar antes que exponer una cifra de
producción incorrecta a operadores no técnicos que la tomarán como verdad.
Relajar el umbral sin registro equivale a trasladar el riesgo al usuario final,
que no tiene herramientas para auditarlo.

### Decisión no funcional: SLA de resolución

El Data Owner debe **triar la notificación en un máximo de 4 horas hábiles** y
**comunicar la decisión de aptitud** (apto con observación / no apto + motivo)
dentro del mismo bloque. Si la decisión de aptitud habilita el reproceso, el
Data Engineer debe completarlo y confirmar el cierre **dentro de las 24 horas
hábiles** del triaje.

Este SLA existe porque el Data Owner ownea la disponibilidad y confiabilidad del
dato para el negocio. Un bloqueo sin tiempo de respuesta definido degrada el
servicio de forma silenciosa: Gold se "congela" en el último snapshot válido, los
dashboards de Metabase dejan de actualizarse para el período bloqueado y los
operadores no tienen forma de saber si el dato ausente es por bloqueo planificado
o por incidente sin dueño. El SLA hace visible el estado del incidente y fija
expectativas para los consumidores.

## Pasos

1. **Recibir y registrar la alerta.** Al llegar la notificación por webhook,
   anotar: run id de Dagster, nombre del check fallido, partición afectada
   (mes en formato `YYYY-MM-01`) y timestamp del fallo.

2. **Leer las filas fallidas en `dbt_test__audit`.** Conectarse al DW y
   consultar la tabla de fallos correspondiente al check que disparó la alerta.
   El nombre de la tabla sigue el patrón del test dbt; para ver todas las tablas
   de fallos presentes:

   ```sql
   select table_name
   from information_schema.tables
   where table_schema = 'dbt_test__audit'
   order by table_name;
   ```

   Para inspeccionar los registros fallidos de un check de rango en la partición
   bloqueada (ajustar el nombre de tabla y el mes según la alerta):

   ```sql
   select *
   from dbt_test__audit.accepted_range_silver_production_oil_prod_m3__0__False
   where production_month = date '2016-01-01'
   order by well_id
   limit 50;
   ```

   Para medir la proporción de filas fallidas respecto del total de la partición:

   ```sql
   select
       f.production_month,
       count(*)                                   as filas_fallidas,
       s.total                                    as total_particion,
       round(count(*) * 100.0 / nullif(s.total, 0), 2) as pct_fallidas
   from dbt_test__audit.accepted_range_silver_production_oil_prod_m3__0__False f
   join (
       select production_month, count(*) as total
       from silver.silver_production
       group by production_month
   ) s using (production_month)
   where f.production_month = date '2016-01-01'
   group by f.production_month, s.total;
   ```

3. **Analizar el impacto aguas abajo con linaje DataHub.**
   a. Abrir DataHub UI en `http://localhost:9002` (si el stack no está
      levantado, solicitarlo al Data Engineer siguiendo
      `infra/datahub/README.md`).
   b. En **Browse > Datasets > postgres > petrocast > silver**, abrir
      `silver_production`.
   c. Ir a la pestaña **Lineage** y expandir **downstream**: aparecen
      `gold/fact_production` y, desde allí, las dimensiones (`dim_well`,
      `dim_company`, `dim_date`) y la API (F2-22).
   d. Confirmar qué tablas gold quedaron sin actualizar en la partición
      bloqueada y qué dashboards de Metabase las consumen (los tres
      dashboards de producción de F2-20).
   e. Documentar el impacto: qué tablas gold afectadas, qué dashboards
      congelados y si la API de producción expone el período bloqueado.

4. **Verificar el estado actual de Gold.** Confirmar que Gold conserva el
   último snapshot válido (las tablas no están vacías, solo desactualizadas
   para el período bloqueado):

   ```sql
   select
       production_month,
       count(*)         as filas,
       sum(oil_prod_m3) as oil_prod_m3
   from gold.fact_production
   where production_month >= date '2016-01-01'
     and production_month < date '2016-04-01'
   group by production_month
   order by production_month;
   ```

5. **Decidir la aptitud del dato.** Con la proporción de filas fallidas y el
   análisis de impacto, aplicar el criterio del umbral definido en "Decisiones
   del rol":
   - **Apto con observación:** documentar el motivo, autorizar el reproceso y
     comunicar a los consumidores el período afectado y el tiempo estimado de
     resolución.
   - **No apto:** comunicar a los consumidores que el dato del período no está
     disponible, documentar la causa y pedir al Data Engineer que identifique
     y corrija la fuente antes del reproceso.

6. **Comunicar la decisión.** Notificar en el canal del incidente (issue, PR o
   chat del equipo): período afectado, decisión (apto/no apto), motivo,
   impacto en dashboards/API y próximo dueño de acción.

7. **Delegar al Data Engineer.** Si el dato es apto o la fuente fue corregida,
   pedir al Data Engineer que ejecute el reproceso y backfill siguiendo
   [data-engineer.md](data-engineer.md) y
   [backfill.md](backfill.md#procedimiento-por-cli). El Data Engineer confirma
   cierre con run id y evidencia de validación.

8. **Registrar el cierre.** Una vez que el Data Engineer confirma el reproceso
   exitoso, registrar en el issue/incidente: decisión tomada, evidencia de
   validación recibida, dashboards verificados y timestamp de cierre.

## Validación

El incidente se considera cerrado cuando:

- El Data Engineer confirma que el run de Dagster del reproceso terminó en verde
  y los asset checks de `silver/silver_production` están sin fallos nuevos para
  el período reprocesado.
- La tabla `dbt_test__audit` correspondiente al check fallido no contiene nuevas
  filas para ese período.
- `gold.fact_production` tiene filas actualizadas para la partición bloqueada
  (confirmar con la query del paso 4).
- Los dashboards de Metabase muestran datos consistentes para el período que
  estaba bloqueado.
- La decisión y la evidencia quedaron registradas en el issue o canal del
  incidente.

Si el dato se declaró **no apto** y no se reprocesó, el cierre equivale a que
el bloqueo quedó documentado con un dueño de acción explícito y un plazo para
la corrección de la fuente.

## Si algo falla: rollback, plan B y escalamiento

- **No puedo leer `dbt_test__audit`:** solicitar al Data Engineer acceso de
  solo lectura o que comparta la salida de la query de filas fallidas. No
  decidir sin ver la evidencia.
- **DataHub no está disponible:** solicitar al Data Engineer que levante el
  stack on-demand (`infra/datahub/datahub.sh up` + `ingest`) antes del paso 3.
  Como alternativa de emergencia, pedir al Data Engineer el grafo de linaje dbt
  en texto o la visualización de `dbt docs serve`.
- **No puedo determinar el impacto aguas abajo:** declarar el dato no apto de
  forma conservadora y escalar al Data Engineer para el análisis de impacto
  técnico.
- **El Data Engineer no puede reprocesar en el SLA:** comunicar a los
  consumidores el estado del bloqueo, mantener Gold en el último snapshot válido
  y registrar la excepción con nuevo plazo acordado.
- **El check sigue fallando tras el reproceso:** no forzar la promoción a Gold.
  Escalar al Data Engineer para revisar si el umbral del test es correcto o si
  la fuente tiene un problema estructural. Si el umbral requiere cambio, ese
  cambio necesita acuerdo explícito del Data Owner antes de mergearse.
- **Impacto en demo o entrega:** comunicar al equipo con el run id, el período
  afectado, la decisión de aptitud y el plazo de resolución.

## Consideraciones no funcionales

- **Calidad:** el Data Owner ownea la definición de "apto para negocio"; el
  umbral de aptitud es una regla de negocio, no técnica, y solo cambia con su
  aprobación.
- **Frescura:** un bloqueo congela Gold en el último snapshot válido; el Data
  Owner es responsable de comunicar a los consumidores el período sin
  actualizar y el SLA de resolución.
- **SLA de resolución:** triaje en 4 horas hábiles; reproceso confirmado en
  24 horas hábiles. Sin SLA, los consumidores no pueden distinguir un bloqueo
  activo de un incidente sin dueño.
- **Gobernanza:** toda decisión de aptitud queda registrada con motivo,
  evidencia y dueño de acción. El registro es el trazado de auditoría que
  permite explicar por qué un período de Gold quedó desactualizado.
- **Privacidad:** no copiar filas fallidas fuera del DW; la inspección se hace
  con queries de control dentro del warehouse.
- **Disponibilidad del consumo BI:** Gold conserva el último snapshot válido
  durante el bloqueo (F2-18); los dashboards de Metabase siguen disponibles con
  datos históricos mientras se resuelve el incidente.

## Referencias

- [Procedimiento de backfill histórico](backfill.md).
- [Runbook Data Engineer](data-engineer.md).
- ADR-0025: calidad de datos y consecuencia operativa.
- ADR-0023: arquitectura medallion y dbt.
- F2-17: chequeos de calidad (cinco dimensiones, `store_failures`).
- F2-18: consecuencia operativa (bloqueo + notificación).
- F2-19: linaje Dagster bronze → silver → gold.
- F2-21: DataHub — catálogo y linaje navegable.
- F2-20: Metabase — dashboards de consumo gold.
- F2-27: Runbook Data Owner.
