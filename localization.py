import json
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "localization"

_current_locale = {}


def load_locale(language: str) -> None:
    global _current_locale

    path = LOCALES_DIR / f"{language}.json"

    with path.open("r", encoding="utf-8") as file:
        _current_locale = json.load(file)


def tr(key: str) -> str:
    return _current_locale.get(key, key)
