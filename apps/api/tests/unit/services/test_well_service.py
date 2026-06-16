from src.services.well_service import get_all_wells
from tests.conftest import _FakeConnection


def test_get_all_wells_returns_non_empty_list(fake_conn: _FakeConnection) -> None:
    wells = get_all_wells(fake_conn)
    assert len(wells) > 0


def test_get_all_wells_items_have_id_well(fake_conn: _FakeConnection) -> None:
    wells = get_all_wells(fake_conn)
    for well in wells:
        assert well.id_well
