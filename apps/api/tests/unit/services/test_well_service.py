from src.services.well_service import get_all_wells


def test_get_all_wells_returns_non_empty_list():
    wells = get_all_wells()
    assert len(wells) > 0


def test_get_all_wells_items_have_id_well():
    wells = get_all_wells()
    for well in wells:
        assert well.id_well
