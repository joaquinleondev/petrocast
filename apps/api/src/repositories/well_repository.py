from src.schemas.well import WellInfo

_WELLS: list[WellInfo] = [
    WellInfo(id_well="POZO-001"),
    WellInfo(id_well="POZO-002"),
    WellInfo(id_well="POZO-003"),
]


def get_all() -> list[WellInfo]:
    return _WELLS
