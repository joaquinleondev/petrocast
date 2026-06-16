# Runbook Data Engineer: reprocesamiento y backfill

## Propósito y disparador

Este runbook guía al **Data Engineer** cuando necesita reprocesar datos históricos
del pipeline medallion (`bronze` → `silver` → `gold`) sin romper el consumo de BI
ni perder trazabilidad.

Se ejecuta ante alguno de estos disparadores:

- Corrección o actualización histórica en las fuentes de datos.gob.ar.
- Fallo de calidad que bloqueó la promoción a Gold.
- Pedido del Data Owner para reconstruir un rango de meses.
- Incidente operativo donde `gold.fact_production` quedó incompleto o desfasado.
- Preparación de una demo/verificación E2E que requiere evidencia reproducible.

El procedimiento operativo detallado vive en
[backfill histórico](backfill.md). Este runbook define cómo decide, ejecuta,
valida y comunica el Data Engineer ese reproceso.

## Rol, dueño y prerrequisitos

- **Dueño:** Data Engineer de Petrocast.
- **Responsabilidad:** mantener el pipeline reproducible, idempotente y
  observable; no decidir si un dato es apto para negocio.
- **Escala a:** Data Owner si hay dudas de aptitud del dato; Platform/Infra si
  falla Docker, Postgres, credenciales o conectividad.

Antes de empezar, el Data Engineer necesita:

- Acceso al repo y branch actualizada con `main`.
- Dagster UI disponible en <http://localhost:3000> o CLI local desde `apps/data`.
- PostgreSQL DW accesible con schemas `bronze`, `silver`, `gold` y
  `dbt_test__audit`.
- Variables `PETROCAST_DW_*`, `PETROCAST_SOURCE_PRODUCTION_URL` y
  `PETROCAST_SOURCE_WELLS_URL` configuradas fuera del repo.
- Rango de meses a reprocesar en formato `YYYY-MM-01`.
- Motivo del reproceso y evidencia inicial: issue, alerta, run fallido o pedido
  del Data Owner.

## Decisiones del rol

### Decisión funcional: reprocesar siempre desde Bronze

El Data Engineer debe reprocesar desde `bronze` y no corregir manualmente tablas
`silver` o `gold`. Esta decisión prioriza una fuente de verdad cruda y
reproducible: si la corrección se aplica solo en una capa derivada, el próximo
run la puede pisar y la explicación del resultado queda fuera de Dagster/dbt. El
incentivo del Data Engineer es que cualquier integrante pueda repetir el mismo
rango, ver los mismos asset checks y llegar al mismo Gold; por eso el runbook
fuerza el camino Bronze → Silver → Gold.

### Decisión no funcional: correr rangos controlados fuera de horas de consumo

El Data Engineer debe preferir ventanas chicas y, si el rango es grande, correr
el backfill fuera del horario de uso de Metabase/DataHub. Esta decisión no busca
"optimizar por prolijidad", sino proteger el servicio que otros roles consumen:
un backfill grande compite por CPU, conexiones y locks del DW, mientras que el
Data Engineer es el rol que puede elegir cuándo pagar ese costo. El incentivo es
mantener disponibilidad y tiempos razonables para usuarios no técnicos, sin
renunciar a una reconstrucción completa cuando haga falta.

## Pasos

1. **Registrar el incidente o pedido.** Anotar rango, motivo, fuente del pedido,
   run de Dagster asociado y tabla afectada.
2. **Definir el alcance.** Confirmar el rango mensual exacto, por ejemplo
   `2016-01-01...2016-03-01`, y si el backfill requiere refrescar Bronze desde
   fuente oficial o desde fixtures/local CSV.
3. **Avisar antes de ejecutar.** Si el rango es grande o afecta una demo,
   informar al Data Owner y al equipo que Gold puede tardar en actualizarse.
4. **Preparar el entorno.** Desde `apps/data`, asegurar dependencias y manifest:

   ```bash
   export PYTHONPATH="$PWD/src"
   uv run dbt deps --project-dir dbt
   uv run dbt parse --project-dir dbt --profiles-dir dbt
   ```

5. **Ejecutar el procedimiento formal.** Seguir
   [backfill histórico](backfill.md#procedimiento-por-cli) o la sección de UI en
   Dagster. Para CLI, el paso central es:

   ```bash
   uv run dagster asset materialize \
     --module-name petrocast_data.definitions \
     --select "tag:silver,tag:gold" \
     --partition-range 2016-01-01...2016-03-01
   ```

6. **Revisar asset checks.** En Dagster, abrir el run y confirmar que los checks
   bloqueantes de `silver/silver_production` quedaron verdes. El check de
   frescura puede quedar en warning si el rango es histórico.
7. **Validar Gold.** Ejecutar las queries de control del
   [procedimiento de backfill](backfill.md#validación) para confirmar filas del
   rango y ausencia de duplicados en `gold.fact_production`.
8. **Guardar evidencia.** Registrar run id, rango, resultado de checks, conteos
   de Gold y cualquier warning relevante.
9. **Comunicar cierre.** Avisar al solicitante que el rango quedó reprocesado o,
   si hubo bloqueo, compartir las filas fallidas y el próximo dueño de acción.

## Validación

El reproceso se considera exitoso cuando:

- El run de Dagster termina en verde.
- `silver/silver_production` no tiene checks bloqueantes fallidos.
- `gold_dbt_assets` se ejecutó después de Silver.
- `gold.fact_production` contiene filas para el rango reprocesado.
- No existen duplicados por `(well_id, production_month)` en Gold.
- La evidencia queda registrada junto al issue, PR o canal del incidente.

Si el objetivo era resolver un bloqueo de calidad, además debe verificarse que la
tabla correspondiente en `dbt_test__audit` ya no contiene nuevas filas fallidas
para el rango reprocesado.

## Si algo falla: plan B y escalamiento

- **Falla conexión al DW:** revisar `PETROCAST_DW_*`, salud de `data-postgres` y
  que el `.env` coincida con el volumen local. Si hubo cambio de password local,
  recrear el volumen solo si no hay datos que conservar.
- **Falla Bronze:** validar URLs oficiales, permisos de red y formato CSV. Como
  plan B, usar un CSV local verificado para aislar si el problema es la fuente o
  el pipeline.
- **Falla un asset check bloqueante:** no forzar Gold. Revisar filas en
  `dbt_test__audit`, compartir evidencia con Data Owner y repetir el backfill
  solo después de corregir fuente, mapeo o regla de calidad.
- **Gold no se actualiza:** confirmar que el rango usa particiones válidas y que
  `gold_dbt_assets` no fue saltado por dependencia fallida de Silver.
- **El run tarda demasiado:** cancelar, dividir el rango en bloques más chicos y
  reprogramar fuera de horario.
- **Impacto en demo o entrega:** escalar al equipo con run id, rango afectado,
  causa probable y decisión pendiente.

## Consideraciones no funcionales

- **Idempotencia:** repetir el mismo rango debe dejar el mismo resultado; si no
  ocurre, tratarlo como incidente.
- **Calidad:** los checks bloqueantes son la barrera de promoción; el Data
  Engineer opera el mecanismo, pero no relaja umbrales sin acuerdo del Data
  Owner.
- **Disponibilidad:** evitar backfills largos durante uso de BI/gobierno porque
  compiten por recursos del DW.
- **Seguridad:** no commitear `.env`, credenciales ni extractos sensibles de CSV
  en issues o PRs.
- **Trazabilidad:** toda ejecución relevante debe tener run id, rango y resultado
  de validación.
- **Gobernanza:** si el cambio altera linaje, grano o semántica del modelo, no es
  un simple backfill; requiere PR/ADR o documentación del modelo.

## Referencias

- [Procedimiento de backfill histórico](backfill.md).
- ADR-0023: arquitectura medallion y dbt.
- ADR-0025: calidad de datos y consecuencia operativa.
- ADR-0026: tipo de carga por capa.
- ADR-0028: orquestación e ingesta con Dagster y dlt.
- F2-26: Runbook Data Engineer.
