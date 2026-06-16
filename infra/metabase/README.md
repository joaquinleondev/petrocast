# Metabase BI — Operator Runbook

> Reference: ADR-0029 · Feature: F2-20

Metabase OSS proporciona dashboards de producción para usuarios no técnicos,
conectado de solo lectura al schema `gold` del data warehouse.

---

## Arquitectura

```
Metabase OSS :3001 (host)
  └─ container :3000
       ├─ App DB: H2 embebido en volumen `metabase_data` (dev/staging)
       └─ DW: petrocast_bi → data-postgres:5432 / gold schema (solo lectura)
```

- **Imagen:** `metabase/metabase:v0.62.1.8` (OSS, sin sufijo `-ee`).
- **Puerto host:** `3001` por defecto (`PETROCAST_METABASE_PORT`). El 3001 evita
  colisión con Dagster y Grafana, ambos en `:3000`.
- **Persistencia:** volumen Docker `metabase_data`. Para producción sustituir H2 por
  una instancia Postgres dedicada (ver "Producción" más abajo).

---

## Bring-up

```bash
# 1. Asegurar variables de entorno en apps/data/.env
cp apps/data/.env.example apps/data/.env
# Editar: PETROCAST_BI_DB_PASSWORD, PETROCAST_METABASE_ADMIN_EMAIL/PASSWORD

# 2. Levantar el stack completo (incluye Metabase)
docker compose --env-file apps/data/.env -f infra/compose.data.yml up -d

# 3. Esperar que Metabase esté healthy (puede tardar ~60 s en el primer arranque)
docker compose --env-file apps/data/.env -f infra/compose.data.yml \
  exec metabase curl -sf http://localhost:3000/api/health

# 4. Provisionar conexión + dashboards (ejecutar una sola vez; es re-runnable)
PETROCAST_METABASE_ADMIN_EMAIL=admin@example.com \
PETROCAST_METABASE_ADMIN_PASSWORD=secreto \
PETROCAST_BI_DB_PASSWORD=change-me \
python3 infra/metabase/provision_metabase.py
```

Metabase UI: <http://localhost:3001>

---

## Variables de entorno

| Variable | Requerida | Default | Descripción |
|---|---|---|---|
| `PETROCAST_METABASE_PORT` | No | `3001` | Puerto host para la UI de Metabase |
| `PETROCAST_BI_DB_PASSWORD` | **Sí** | — | Password del usuario Postgres `petrocast_bi` |
| `PETROCAST_METABASE_ADMIN_EMAIL` | **Sí (script)** | — | E-mail del admin de Metabase |
| `PETROCAST_METABASE_ADMIN_PASSWORD` | **Sí (script)** | — | Password del admin de Metabase |
| `MB_URL` | No (script) | `http://localhost:3001` | URL base de Metabase para el script |
| `MB_DW_HOST` | No (script) | `data-postgres` | Host del DW visto desde Metabase |
| `MB_DW_PORT` | No (script) | `5432` | Puerto del DW |
| `MB_DW_DBNAME` | No (script) | `petrocast` | Nombre de la base del DW |

---

## Rol de solo lectura (`petrocast_bi`)

El script de init `infra/data/postgres/init/002-create-bi-readonly-role.sh`
crea el rol en el primer arranque del volumen Postgres:

```sql
-- Solo tiene acceso al schema gold
GRANT USAGE ON SCHEMA gold TO petrocast_bi;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO petrocast_bi;
ALTER DEFAULT PRIVILEGES FOR ROLE "petrocast" IN SCHEMA gold
    GRANT SELECT ON TABLES TO petrocast_bi;
-- Sin acceso a bronze/silver (REVOKE explícito)
```

Si se regenera el volumen de Postgres (`down -v`) el rol se recrea automáticamente.

---

## Dashboards provisonados

El script `infra/metabase/provision_metabase.py` crea y mantiene de forma idempotente:

| Tarjeta (card) | Tipo | Template variables |
|---|---|---|
| Producción por pozo/mes | Tabla | `{{well_name}}`, `{{date_filter}}`, `{{fluid_type}}` |
| Evolución histórica mensual | Línea | `{{date_filter}}`, `{{fluid_type}}` |
| Top pozos por volumen | Barras | `{{well_name}}`, `{{fluid_type}}` |

Cada tarjeta unpivotea petróleo / gas / agua en filas `(fluid_type, volume)` mediante
`UNION ALL`, lo que permite filtrar por tipo de fluido de forma nativa.

Dashboard: **"Producción Petrocast"** con filtros completamente cableados (automático):

| Filtro | Tipo | Tarjetas conectadas | Tag |
|---|---|---|---|
| **Pozo** (`string/contains`) | texto libre | Producción por pozo/mes, Top pozos | `{{well_name}}` |
| **Fecha** (`date/single`) | fecha | Producción por pozo/mes, Evolución histórica | `{{date_filter}}` |
| **Tipo de fluido** (`string/=`) | lista estática: Petróleo / Gas / Agua | las tres tarjetas | `{{fluid_type}}` |

No hay pasos manuales — el script aprovisiona el mapeo filtro→variable mediante
`PUT /api/dashboard/{id}` con `parameter_mappings` en cada dashcard.

> **Nota de implementación (Metabase v0.62):** `POST /api/dashboard/{id}/cards` devuelve
> 404 en esta versión. Los dashcards se agregan vía `PUT /api/dashboard/{id}` con el
> array `dashcards` (ids negativos para dashcards nuevos). Los filtros opcionales usan
> la sintaxis `[[AND columna = {{tag}}]]` en el SQL nativo.

---

## Producción (reemplazar H2 por Postgres)

H2 es adecuado para desarrollo. En producción usar una instancia Postgres
dedicada para la app DB de Metabase:

```yaml
# En infra/compose.data.yml, reemplazar las env de metabase:
MB_DB_TYPE: postgres
MB_DB_HOST: <host-postgres-dedicado>
MB_DB_PORT: "5432"
MB_DB_DBNAME: metabase
MB_DB_USER: metabase
MB_DB_PASS: ${PETROCAST_METABASE_DB_PASSWORD:?}
# Y eliminar MB_DB_FILE + el volumen metabase_data
```

---

## Operaciones comunes

```bash
# Ver logs de Metabase
docker compose --env-file apps/data/.env -f infra/compose.data.yml logs -f metabase

# Reiniciar solo Metabase (sin bajar DW ni Dagster)
docker compose --env-file apps/data/.env -f infra/compose.data.yml restart metabase

# Borrar el estado de Metabase (perderás toda la configuración UI — usar con cuidado)
docker compose --env-file apps/data/.env -f infra/compose.data.yml down
docker volume rm petrocast_metabase_data   # nombre real: <project>_metabase_data
docker compose --env-file apps/data/.env -f infra/compose.data.yml up -d metabase
# Re-provisionar después
python3 infra/metabase/provision_metabase.py

# Re-sync de tablas gold en Metabase (después de un backfill / nuevas tablas)
# Desde la UI: Settings → Databases → Petrocast Gold → Sync database schema now
# O vía API:
ADMIN_SESSION=$(curl -sf -X POST http://localhost:3001/api/session \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin@example.com","password":"secreto"}' | jq -r .id)
DB_ID=$(curl -sf http://localhost:3001/api/database \
  -H "X-Metabase-Session: $ADMIN_SESSION" | jq '.data[] | select(.name=="Petrocast Gold (read-only)") | .id')
curl -sf -X POST "http://localhost:3001/api/database/$DB_ID/sync_schema" \
  -H "X-Metabase-Session: $ADMIN_SESSION"
```
