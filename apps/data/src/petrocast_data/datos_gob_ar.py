import csv
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from io import TextIOWrapper
from pathlib import Path
from typing import Any, TextIO, cast
from urllib.parse import unquote, urlparse
from urllib.request import Request, url2pathname, urlopen

DATASET_API_URL = (
    "https://datos.gob.ar/api/3/action/package_show"
    "?id=energia-produccion-petroleo-gas-por-pozo-capitulo-iv"
)
USER_AGENT = "petrocast-data/0.1"


def resolve_csv_location(location: str) -> str:
    source_location = location.strip()
    if not source_location:
        raise ValueError("CSV source location cannot be empty")

    parsed_location = urlparse(source_location)
    if parsed_location.scheme not in {"http", "https"}:
        return source_location
    if "/archivo/" not in parsed_location.path:
        return source_location

    resource_id_candidates = _resource_id_candidates(parsed_location.path)
    for resource in _fetch_dataset_resources():
        resource_id = str(resource.get("id", ""))
        resource_url = str(resource.get("url") or resource.get("download_url") or "")
        if resource_url and (
            resource_id in resource_id_candidates
            or any(candidate in resource_url for candidate in resource_id_candidates)
        ):
            return resource_url

    raise ValueError(f"Could not resolve datos.gob.ar archive page to a CSV URL: {location}")


def read_csv_rows(
    location: str,
    *,
    source_name: str,
    partition_key: str,
) -> Iterator[dict[str, object]]:
    csv_location = resolve_csv_location(location)
    with _open_text_location(csv_location) as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            yield _row_with_metadata(row, source_name=source_name, partition_key=partition_key)


def _resource_id_candidates(path: str) -> set[str]:
    resource_token = unquote(path.rstrip("/").rsplit("/", maxsplit=1)[-1])
    candidates = {resource_token}
    if resource_token.startswith("energia_"):
        candidates.add(resource_token.removeprefix("energia_"))
    return candidates


def _fetch_dataset_resources() -> list[dict[str, Any]]:
    request = Request(DATASET_API_URL, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = cast(dict[str, Any], json.load(response))

    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("datos.gob.ar dataset response does not include a result object")

    resources = result.get("resources")
    if not isinstance(resources, list):
        raise ValueError("datos.gob.ar dataset response does not include resources")

    return [resource for resource in resources if isinstance(resource, dict)]


@contextmanager
def _open_text_location(location: str) -> Iterator[TextIO]:
    parsed_location = urlparse(location)
    if parsed_location.scheme in {"http", "https"}:
        request = Request(location, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urlopen(request, timeout=60) as response:  # noqa: S310
            csv_file = TextIOWrapper(response, encoding="utf-8-sig", newline="")
            yield csv_file
        return

    path = _local_path(location)
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        yield csv_file


def _local_path(location: str) -> Path:
    parsed_location = urlparse(location)
    if parsed_location.scheme == "file":
        return Path(url2pathname(parsed_location.path))
    return Path(location)


def _row_with_metadata(
    row: Mapping[str | None, str | None],
    *,
    source_name: str,
    partition_key: str,
) -> dict[str, object]:
    cleaned_row: dict[str, object] = {
        key.strip(): value if value is not None else ""
        for key, value in row.items()
        if key and key.strip()
    }
    cleaned_row["_petrocast_source"] = source_name
    cleaned_row["_petrocast_partition_key"] = partition_key
    return cleaned_row
