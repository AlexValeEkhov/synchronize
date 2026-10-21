import json
from pathlib import Path
from tkinter import Tk, filedialog

import localization as loc
from colors import BLUE, GREEN, ORANGE, RED, YELLOW, w
from logger import log

PROJECT_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = PROJECT_DIR / "settings.json"
LOCALIZATION_DIR = PROJECT_DIR / "localization"

DEFAULT_SETTINGS = {
    "base_dir": "Yandex Disk",
    "language": "en",
}


def choose_path(initial_dir=None):
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        result = filedialog.askdirectory(
            initialdir=initial_dir,
            parent=root,
            title=loc.tr("choose_save_directory"),
        )
        return Path(result) if result else None
    finally:
        root.destroy()


def save_settings(settings, settings_path=SETTINGS_PATH):
    settings_path = Path(settings_path)
    temp_path = settings_path.with_suffix(".tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
            f.flush()

        temp_path.replace(settings_path)

    finally:
        if temp_path.exists():
            temp_path.unlink()


def load_settings(settings_path=SETTINGS_PATH):
    settings_path = Path(settings_path)

    with settings_path.open("r", encoding="utf-8") as f:
        settings = json.load(f)

    if not isinstance(settings, dict):
        raise ValueError(f"{RED}{loc.tr('settings_must_be_json_object')}")

    if not isinstance(settings.get("base_dir"), str):
        raise ValueError(f"{RED}{loc.tr('base_dir_must_be_string')}")

    if not isinstance(settings.get("language"), str):
        raise ValueError(f"{RED}{loc.tr('language_must_be_string')}")

    return settings


def define_settings(settings_path=SETTINGS_PATH):
    print(f"{ORANGE}{loc.tr('select_save_directory')}")

    selected_path = choose_path()

    if selected_path is None:
        raise RuntimeError(f"{RED}{loc.tr('directory_selection_cancelled')}")

    base_dir = selected_path / "Yandex Disk"
    language = change_language()

    settings = DEFAULT_SETTINGS.copy()
    settings["base_dir"] = str(base_dir)
    settings["language"] = language

    save_settings(settings, settings_path)
    print(f"{GREEN}{loc.tr('settings_saved')}")

    return settings


def change_setting(key, value, settings_path=SETTINGS_PATH):
    settings = load_settings(settings_path)

    if key not in DEFAULT_SETTINGS:
        raise KeyError(f"{RED}{loc.tr('unknown_setting')}: {key}")

    settings[key] = value
    save_settings(settings, settings_path)


def change_base_dir(settings_path=SETTINGS_PATH):
    selected_path = choose_path()

    if selected_path is None:
        return False

    change_setting(
        "base_dir",
        str(selected_path / "Yandex Disk"),
        settings_path,
    )
    return True


def get_localizations() -> dict:
    localizations = {
        num: loc
        for num, loc in enumerate(sorted(path.stem for path in LOCALIZATION_DIR.glob("*.json") if path.is_file()), start=1)
    }
    return localizations


def change_language(settings_path=SETTINGS_PATH):
    localizations = get_localizations()
    for num, language in localizations.items():
        print(f"{GREEN}  {num} {w} {YELLOW}{language}")
    try:
        choice = int(input(f"\n{ORANGE}{loc.tr('choose_app_language')} {w} {BLUE}").lower())
        language = localizations.get(choice, None)
    except (ValueError, UnboundLocalError):
        language = None

    if not language:
        log(f"{RED}{loc.tr('language_selection_error')}")
        language = "en"

    change_setting("language", language, settings_path)
    return language


def read_settings(settings_path=SETTINGS_PATH):
    settings_path = Path(settings_path)

    if not settings_path.exists():
        settings = define_settings(settings_path)
    else:
        try:
            settings = load_settings(settings_path)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"{RED}{loc.tr('settings_file_error')}: {e}")
            print(f"{loc.tr('program_reconfiguration_required')}")
            settings = define_settings(settings_path)

    base_dir = Path(settings["base_dir"])
    language = settings["language"]

    if not base_dir.is_dir():
        base_dir.mkdir(parents=True, exist_ok=True)

    return base_dir, language
