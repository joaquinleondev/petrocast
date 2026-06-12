from pathlib import Path

from petrocast_data.settings import DataSettings


def _parse_env_example(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key.lower())
    return keys


def test_env_example_keys_match_settings_fields():
    env_example = Path(__file__).parents[2] / ".env.example"
    example_keys = _parse_env_example(env_example)

    env_prefix = str(DataSettings.model_config.get("env_prefix", "")).lower()
    settings_keys = {f"{env_prefix}{field}" for field in DataSettings.model_fields}

    assert example_keys == settings_keys, (
        f"only in .env.example: {example_keys - settings_keys}; "
        f"only in DataSettings: {settings_keys - example_keys}"
    )
