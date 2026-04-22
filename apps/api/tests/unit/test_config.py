from pathlib import Path

from src.core.config import Settings


def _parse_env_example(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key.lower())
    return keys


def test_env_example_keys_match_settings_fields():
    env_example = Path(__file__).parent.parent.parent / ".env.example"
    example_keys = _parse_env_example(env_example)
    settings_fields = set(Settings.model_fields.keys())
    assert example_keys == settings_fields, (
        f"only in .env.example: {example_keys - settings_fields}; "
        f"only in Settings: {settings_fields - example_keys}"
    )
