from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class FeatureReader(Protocol):
    """Port implemented by consumers that read the persisted feature store."""

    def read(self, *, well_id: str, as_of_date: date) -> pd.DataFrame:
        """Return one persisted feature vector for a well and cutoff date."""
        ...


def read_features(
    reader: FeatureReader,
    *,
    well_id: str,
    as_of_date: date,
) -> pd.DataFrame:
    """Read features through the shared feature-store port."""
    return reader.read(well_id=well_id, as_of_date=as_of_date)


__all__ = ["FeatureReader", "read_features"]
