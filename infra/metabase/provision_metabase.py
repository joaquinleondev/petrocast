#!/usr/bin/env python3
"""provision_metabase.py — idempotent Metabase provisioning for Petrocast.

Automates via the Metabase REST API (stdlib only: urllib.request + json):
  1. Wait for Metabase to be healthy.
  2. Complete first-time setup (admin user) OR log in if already set up.
  3. Ensure the gold PostgreSQL database connection exists (petrocast_bi / gold schema).
  4. Create or update 3 native SQL questions (cards) — idempotent by name:
       a) Producción por pozo/mes   (table)
       b) Evolución histórica mensual (line)
       c) Top pozos por volumen      (bar)
     All cards unpivot oil/gas/water into (fluid_type, volume) rows via UNION ALL
     so that the {{fluid_type}} filter can slice by fluid type.
  5. Create or update dashboard "Producción Petrocast" with the 3 cards arranged in
     a 2-column grid.  All three filter parameters are fully wired to card
     template-tag variables via parameter_mappings — no manual UI steps required:
       * "Pozo"         → {{well_name}}   on cards (a) and (c)
       * "Fecha"        → {{date_filter}} on cards (a) and (b)
       * "Tipo fluido"  → {{fluid_type}}  on all three cards

Usage:
  python3 infra/metabase/provision_metabase.py

Required env vars:
  PETROCAST_METABASE_ADMIN_EMAIL    admin e-mail for first-time setup / login
  PETROCAST_METABASE_ADMIN_PASSWORD admin password
  PETROCAST_BI_DB_PASSWORD          password for the petrocast_bi Postgres role

Optional env vars:
  MB_URL            Metabase base URL (default: http://localhost:3001)
  MB_DW_HOST        Postgres host visible from Metabase container (default: data-postgres)
  MB_DW_PORT        Postgres port (default: 5432)
  MB_DW_DBNAME      Postgres database name (default: petrocast)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
MB_URL = os.environ.get("MB_URL", "http://localhost:3001").rstrip("/")
ADMIN_EMAIL = os.environ["PETROCAST_METABASE_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["PETROCAST_METABASE_ADMIN_PASSWORD"]
BI_DB_PASSWORD = os.environ["PETROCAST_BI_DB_PASSWORD"]

DW_HOST = os.environ.get("MB_DW_HOST", "data-postgres")
DW_PORT = int(os.environ.get("MB_DW_PORT", "5432"))
DW_DBNAME = os.environ.get("MB_DW_DBNAME", "petrocast")

DB_CONNECTION_NAME = "Petrocast Gold (read-only)"
DASHBOARD_NAME = "Producción Petrocast"

# ---------------------------------------------------------------------------
# Card specifications
# Each card unpivots oil/gas/water via UNION ALL so {{fluid_type}} can filter.
# Filters are optional: tag IS NULL OR <condition>.
# ---------------------------------------------------------------------------
CARD_SPECS: list[dict[str, Any]] = [
    {
        "name": "Producción por pozo/mes",
        "display": "table",
        "description": (
            "Producción mensual desagregada por pozo y tipo de fluido (filas). "
            "Filtros: {{well_name}}, {{date_filter}}, {{fluid_type}}."
        ),
        "query": """\
SELECT
    dw.well_alias,
    dc.company_name,
    dd.production_month,
    fluid.fluid_type,
    fluid.volume
FROM gold.fact_production fp
JOIN gold.dim_well    dw ON fp.well_key    = dw.well_key
JOIN gold.dim_company dc ON fp.company_key = dc.company_key
JOIN gold.dim_date    dd ON fp.date_key    = dd.date_key
JOIN LATERAL (VALUES
    ('Petróleo', fp.oil_prod_m3),
    ('Gas',      fp.gas_prod_mm3),
    ('Agua',     fp.water_prod_m3)
) AS fluid(fluid_type, volume) ON TRUE
WHERE 1=1
    [[AND dw.well_alias ILIKE '%' || {{well_name}} || '%']]
    [[AND dd.production_month = {{date_filter}}::date]]
    [[AND fluid.fluid_type = {{fluid_type}}]]
ORDER BY dd.production_month DESC, dw.well_alias, fluid.fluid_type
""",
        "template_tags": {
            "well_name": {
                "id": "tt_well_name_1",
                "name": "well_name",
                "display-name": "Pozo",
                "type": "text",
                "required": False,
            },
            "date_filter": {
                "id": "tt_date_filter_1",
                "name": "date_filter",
                "display-name": "Fecha",
                "type": "date",
                "required": False,
            },
            "fluid_type": {
                "id": "tt_fluid_type_1",
                "name": "fluid_type",
                "display-name": "Tipo de fluido",
                "type": "text",
                "required": False,
            },
        },
        # Which dashboard params map to which tags in this card
        "_param_tags": {
            "filter_pozo": "well_name",
            "filter_fecha": "date_filter",
            "filter_fluido": "fluid_type",
        },
    },
    {
        "name": "Evolución histórica mensual",
        "display": "line",
        "description": (
            "Producción agregada por mes y tipo de fluido. "
            "Ideal para ver tendencias. Filtros: {{date_filter}}, {{fluid_type}}."
        ),
        "query": """\
SELECT
    dd.production_month,
    fluid.fluid_type,
    SUM(fluid.volume) AS total_volume
FROM gold.fact_production fp
JOIN gold.dim_date dd ON fp.date_key = dd.date_key
JOIN LATERAL (VALUES
    ('Petróleo', fp.oil_prod_m3),
    ('Gas',      fp.gas_prod_mm3),
    ('Agua',     fp.water_prod_m3)
) AS fluid(fluid_type, volume) ON TRUE
WHERE 1=1
    [[AND dd.production_month >= {{date_filter}}::date]]
    [[AND fluid.fluid_type = {{fluid_type}}]]
GROUP BY dd.production_month, fluid.fluid_type
ORDER BY dd.production_month, fluid.fluid_type
""",
        "template_tags": {
            "date_filter": {
                "id": "tt_date_filter_2",
                "name": "date_filter",
                "display-name": "Fecha desde",
                "type": "date",
                "required": False,
            },
            "fluid_type": {
                "id": "tt_fluid_type_2",
                "name": "fluid_type",
                "display-name": "Tipo de fluido",
                "type": "text",
                "required": False,
            },
        },
        "_param_tags": {
            "filter_fecha": "date_filter",
            "filter_fluido": "fluid_type",
        },
    },
    {
        "name": "Top pozos por volumen",
        "display": "bar",
        "description": (
            "Ranking de pozos por volumen total. "
            "Filtros: {{well_name}}, {{fluid_type}}."
        ),
        "query": """\
SELECT
    dw.well_alias,
    fluid.fluid_type,
    SUM(fluid.volume) AS total_volume
FROM gold.fact_production fp
JOIN gold.dim_well dw ON fp.well_key = dw.well_key
JOIN LATERAL (VALUES
    ('Petróleo', fp.oil_prod_m3),
    ('Gas',      fp.gas_prod_mm3),
    ('Agua',     fp.water_prod_m3)
) AS fluid(fluid_type, volume) ON TRUE
WHERE 1=1
    [[AND dw.well_alias ILIKE '%' || {{well_name}} || '%']]
    [[AND fluid.fluid_type = {{fluid_type}}]]
GROUP BY dw.well_alias, fluid.fluid_type
ORDER BY total_volume DESC
LIMIT 20
""",
        "template_tags": {
            "well_name": {
                "id": "tt_well_name_3",
                "name": "well_name",
                "display-name": "Pozo",
                "type": "text",
                "required": False,
            },
            "fluid_type": {
                "id": "tt_fluid_type_3",
                "name": "fluid_type",
                "display-name": "Tipo de fluido",
                "type": "text",
                "required": False,
            },
        },
        "_param_tags": {
            "filter_pozo": "well_name",
            "filter_fluido": "fluid_type",
        },
    },
]

# Dashboard filter parameters — declared once, wired via parameter_mappings below.
DASHBOARD_PARAMETERS: list[dict[str, Any]] = [
    {
        "id": "filter_pozo",
        "name": "Pozo",
        "slug": "pozo",
        "type": "string/contains",
        "sectionId": "string",
    },
    {
        "id": "filter_fecha",
        "name": "Fecha",
        "slug": "fecha",
        "type": "date/single",
        "sectionId": "date",
    },
    {
        "id": "filter_fluido",
        "name": "Tipo de fluido",
        "slug": "tipo_fluido",
        "type": "string/=",
        "sectionId": "string",
        "values_source_type": "static-list",
        "values_source_config": {
            "values": [["Petróleo"], ["Gas"], ["Agua"]],
        },
    },
]

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_session_token: str | None = None


def _headers(auth: bool = True) -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if auth and _session_token:
        h["X-Metabase-Session"] = _session_token
    return h


def api_get(path: str, *, auth: bool = True) -> Any:
    req = urllib.request.Request(
        f"{MB_URL}{path}",
        headers=_headers(auth),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_post(path: str, body: Any, *, auth: bool = True) -> Any:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{MB_URL}{path}",
        data=data,
        headers=_headers(auth),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_put(path: str, body: Any) -> Any:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{MB_URL}{path}",
        data=data,
        headers=_headers(),
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Step 1: Wait for health
# ---------------------------------------------------------------------------
def wait_for_health(retries: int = 30, delay: float = 10.0) -> None:
    print(f"[1/5] Waiting for Metabase at {MB_URL}/api/health …")
    for attempt in range(1, retries + 1):
        try:
            data = api_get("/api/health", auth=False)
            if data.get("status") == "ok":
                print("      Metabase is healthy.")
                return
        except Exception as exc:  # noqa: BLE001
            print(f"      Attempt {attempt}/{retries}: {exc}")
        time.sleep(delay)
    sys.exit("ERROR: Metabase did not become healthy in time.")


# ---------------------------------------------------------------------------
# Step 2: Setup or login
# ---------------------------------------------------------------------------
def setup_or_login() -> None:
    global _session_token  # noqa: PLW0603

    print("[2/5] Checking Metabase setup state …")
    props = api_get("/api/session/properties", auth=False)
    has_setup = props.get("has-user-setup", False)

    if not has_setup:
        print("      First-time setup — creating admin user via /api/setup …")
        setup_token = props.get("setup-token") or props.get("token-features", {})
        # setup-token lives at top level in older versions; try both keys
        if isinstance(setup_token, dict):
            setup_token = props.get("setup-token")
        if not setup_token:
            sys.exit(
                "ERROR: could not find setup-token in /api/session/properties. "
                "Metabase may already be configured — re-run after it finishes starting."
            )
        result = api_post(
            "/api/setup",
            {
                "token": setup_token,
                "user": {
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD,
                    "first_name": "Petrocast",
                    "last_name": "Admin",
                    "site_name": "Petrocast BI",
                },
                "prefs": {
                    "site_name": "Petrocast BI",
                    "allow_tracking": False,
                },
            },
            auth=False,
        )
        _session_token = result.get("id")
        print("      Admin created. Session token acquired.")
    else:
        print("      Already set up — logging in …")
        result = api_post(
            "/api/session",
            {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            auth=False,
        )
        _session_token = result.get("id")
        print("      Logged in.")

    if not _session_token:
        sys.exit("ERROR: no session token returned — check credentials.")


# ---------------------------------------------------------------------------
# Step 3: Ensure gold DB connection
# ---------------------------------------------------------------------------
def ensure_database() -> int:
    """Return the Metabase database id for the gold connection, creating if absent."""
    print("[3/5] Ensuring gold database connection …")
    dbs = api_get("/api/database")
    db_list: list[Any] = dbs.get("data") if isinstance(dbs, dict) else (dbs if isinstance(dbs, list) else [])
    existing = [d for d in db_list if d.get("name") == DB_CONNECTION_NAME]
    if existing:
        db_id = existing[0]["id"]
        print(f"      Database '{DB_CONNECTION_NAME}' already exists (id={db_id}).")
        return db_id

    print(f"      Creating database connection '{DB_CONNECTION_NAME}' …")
    db = api_post(
        "/api/database",
        {
            "name": DB_CONNECTION_NAME,
            "engine": "postgres",
            "details": {
                "host": DW_HOST,
                "port": DW_PORT,
                "dbname": DW_DBNAME,
                "user": "petrocast_bi",
                "password": BI_DB_PASSWORD,
                "schema-filters-type": "inclusion",
                "schema-filters-patterns": "gold",
                "ssl": False,
            },
            "auto_run_queries": True,
            "is_full_sync": True,
        },
    )
    db_id = db["id"]
    print(f"      Created (id={db_id}). Triggering sync …")
    try:
        api_post(f"/api/database/{db_id}/sync_schema", {})
    except urllib.error.HTTPError:
        pass  # sync may 204 or vary by version
    return db_id


# ---------------------------------------------------------------------------
# Step 4: Create or update native SQL questions (cards)
# ---------------------------------------------------------------------------
def _card_body(spec: dict[str, Any], db_id: int) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "display": spec.get("display", "table"),
        "description": spec.get("description", ""),
        "dataset_query": {
            "type": "native",
            "database": db_id,
            "native": {
                "query": spec["query"],
                "template-tags": spec.get("template_tags", {}),
            },
        },
        "result_metadata": [],
        "visualization_settings": {},
    }


def ensure_cards(db_id: int) -> list[int]:
    """Create or update cards. Returns list of card ids in CARD_SPECS order."""
    print("[4/5] Ensuring SQL question cards …")
    existing_cards_resp = api_get("/api/card")
    existing_by_name: dict[str, int] = {}
    cards_list = existing_cards_resp if isinstance(existing_cards_resp, list) else []
    for c in cards_list:
        existing_by_name[c.get("name", "")] = c["id"]

    card_ids: list[int] = []
    for spec in CARD_SPECS:
        name = spec["name"]
        body = _card_body(spec, db_id)
        if name in existing_by_name:
            cid = existing_by_name[name]
            print(f"      Card '{name}' exists (id={cid}) — updating …")
            api_put(f"/api/card/{cid}", body)
            card_ids.append(cid)
        else:
            print(f"      Creating card '{name}' …")
            card = api_post("/api/card", body)
            cid = card["id"]
            print(f"      Created (id={cid}).")
            card_ids.append(cid)

    return card_ids


# ---------------------------------------------------------------------------
# Step 5: Create or update dashboard with dashcards and parameter_mappings
# ---------------------------------------------------------------------------
def _build_dashcards(card_ids: list[int]) -> list[dict[str, Any]]:
    """Build the dashcards array for PUT /api/dashboard/{id}.

    Uses negative ids for new dashcards (Metabase v0.62 convention).
    Each dashcard's parameter_mappings wire every dashboard filter param to the
    corresponding template-tag variable in the card's native SQL.
    """
    # Layout: 2-column grid, each card is 12 wide × 8 tall (full row)
    dashcards = []
    for i, (spec, card_id) in enumerate(zip(CARD_SPECS, card_ids)):
        param_tags: dict[str, str] = spec.get("_param_tags", {})
        parameter_mappings = [
            {
                "parameter_id": param_id,
                "card_id": card_id,
                "target": ["variable", ["template-tag", tag_name]],
            }
            for param_id, tag_name in param_tags.items()
        ]
        dashcards.append(
            {
                "id": -(i + 1),  # negative id = new dashcard
                "card_id": card_id,
                "row": i * 9,
                "col": 0,
                "size_x": 24,
                "size_y": 8,
                "parameter_mappings": parameter_mappings,
                "visualization_settings": {},
            }
        )
    return dashcards


def ensure_dashboard(card_ids: list[int]) -> int:
    """Create or update the Producción Petrocast dashboard. Returns dashboard id."""
    print("[5/5] Ensuring dashboard …")
    existing_resp = api_get("/api/dashboard")
    dashboards = existing_resp if isinstance(existing_resp, list) else []
    existing = [d for d in dashboards if d.get("name") == DASHBOARD_NAME]

    dashcards = _build_dashcards(card_ids)

    if existing:
        dash_id = existing[0]["id"]
        print(f"      Dashboard '{DASHBOARD_NAME}' exists (id={dash_id}) — updating …")
        # To replace dashcards we submit the full set with negative ids; Metabase
        # will delete old dashcards not present and create the new ones.
        api_put(
            f"/api/dashboard/{dash_id}",
            {
                "name": DASHBOARD_NAME,
                "description": (
                    "Producción de petróleo, gas y agua por pozo — Petrocast. "
                    "Fuente: gold.fact_production (lectura solo). Ref: ADR-0029."
                ),
                "parameters": DASHBOARD_PARAMETERS,
                "dashcards": dashcards,
            },
        )
        print(f"      Updated (id={dash_id}).")
        return dash_id

    print(f"      Creating dashboard '{DASHBOARD_NAME}' …")
    dash = api_post(
        "/api/dashboard",
        {
            "name": DASHBOARD_NAME,
            "description": (
                "Producción de petróleo, gas y agua por pozo — Petrocast. "
                "Fuente: gold.fact_production (lectura solo). Ref: ADR-0029."
            ),
            "parameters": DASHBOARD_PARAMETERS,
        },
    )
    dash_id = dash["id"]
    print(f"      Created (id={dash_id}). Adding dashcards …")

    # PUT with dashcards array wires cards + parameter_mappings in one call.
    # POST /api/dashboard/{id}/cards returns 404 in Metabase v0.62.
    api_put(
        f"/api/dashboard/{dash_id}",
        {
            "name": DASHBOARD_NAME,
            "parameters": DASHBOARD_PARAMETERS,
            "dashcards": dashcards,
        },
    )
    print(f"      Dashcards wired ({len(dashcards)} cards, all filters mapped).")
    return dash_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    wait_for_health()
    setup_or_login()
    db_id = ensure_database()
    card_ids = ensure_cards(db_id)
    dash_id = ensure_dashboard(card_ids)

    print()
    print("=" * 60)
    print("Provisioning complete.")
    print(f"  Dashboard id : {dash_id}")
    print(f"  Card ids     : {card_ids}")
    print(f"  DB id        : {db_id}")
    print(f"  Metabase URL : {MB_URL}")
    print()
    print("All filters are provisioned and wired automatically:")
    print("  'Pozo'         → {{well_name}}   (cards 1 & 3)")
    print("  'Fecha'        → {{date_filter}} (cards 1 & 2)")
    print("  'Tipo fluido'  → {{fluid_type}}  (all 3 cards)")
    print("=" * 60)


if __name__ == "__main__":
    main()
