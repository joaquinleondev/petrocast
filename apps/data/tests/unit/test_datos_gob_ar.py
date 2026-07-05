from pathlib import Path

import petrocast_data.datos_gob_ar as datos_gob_ar


def test_archive_page_resolves_to_dataset_resource_url(monkeypatch):
    monkeypatch.setattr(
        datos_gob_ar,
        "_fetch_dataset_resources",
        lambda: [
            {
                "id": "b5b58cdc-9e07-41f9-b392-fb9ec68b0725",
                "url": "https://example.test/production.csv",
            }
        ],
    )

    assert (
        datos_gob_ar.resolve_csv_location(
            "https://datos.gob.ar/dataset/example/archivo/"
            "energia_b5b58cdc-9e07-41f9-b392-fb9ec68b0725"
        )
        == "https://example.test/production.csv"
    )


def test_direct_csv_url_is_used_without_resolution():
    assert (
        datos_gob_ar.resolve_csv_location("https://example.test/source.csv")
        == "https://example.test/source.csv"
    )


def test_local_csv_rows_keep_raw_values_and_add_metadata():
    fixture = Path(__file__).parents[1] / "fixtures" / "production_by_well.csv"

    rows = list(
        datos_gob_ar.read_csv_rows(
            str(fixture),
            source_name="production_by_well",
            partition_key="2026-06-01",
        )
    )

    # The fixture is a multi-month series (F3-11: gives the point-in-time test
    # real power); the canonical 2016-01 row stays first, byte-identical, so this
    # keeps asserting the reader's raw passthrough + metadata on the anchor row.
    assert len(rows) == 25
    assert rows[0] == {
        "idempresa": "YSUR",
        "anio": "2016",
        "mes": "1",
        "idpozo": "135204",
        "prod_pet": "0.000",
        "prod_gas": "59.940",
        "prod_agua": "28.350",
        "iny_agua": "0.000",
        "iny_gas": "0.000",
        "iny_co2": "0.000",
        "iny_otro": "0.000",
        "tef": "30.810",
        "vida_util": "",
        "tipoextraccion": "Plunger Lift",
        "tipoestado": "Extracción Efectiva",
        "tipopozo": "Gasífero",
        "observaciones": "",
        "fechaingreso": "2016-02-17 10:50:46.929347",
        "rectificado": "f",
        "habilitado": "t",
        "idusuario": "5",
        "empresa": "YSUR ENERGÍA ARGENTINA S.R.L.",
        "sigla": "APA.Nq.ACO-13(d)",
        "formprod": "PREC",
        "profundidad": "3500",
        "formacion": "precuyo",
        "idareapermisoconcesion": "ANC",
        "areapermisoconcesion": "ANTICLINAL CAMPAMENTO",
        "idareayacimiento": "ACO",
        "areayacimiento": "ANTICLINAL CAMPAMENTO OESTE",
        "cuenca": "NEUQUINA",
        "provincia": "Neuquén",
        "coordenadax": "-69.79352366",
        "coordenaday": "-38.9690076",
        "tipo_de_recurso": "NO CONVENCIONAL",
        "proyecto": "GAS PLUS",
        "clasificacion": "EXPLOTACION",
        "subclasificacion": "DESARROLLO",
        "sub_tipo_recurso": "TIGHT",
        "fecha_data": "2016-01-31",
        "_petrocast_source": "production_by_well",
        "_petrocast_partition_key": "2026-06-01",
    }
