from src.repositories import well_repository
from src.schemas.well import WellInfo


def get_all_wells() -> list[WellInfo]:
    return well_repository.get_all()
