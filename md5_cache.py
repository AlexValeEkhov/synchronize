import hashlib
import json
from pathlib import Path

import localization as loc
from colors import RED, RESET
from logger import log


def calculate_file_hash(file_path: Path, hash_algorithm: str = "md5") -> str | None:
    try:
        h = hashlib.new(hash_algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None


def read_md5_cache(base_dir: Path) -> dict:
    md5_path = base_dir / "md5_cache.json"
    if not md5_path.exists():
        return {}
    with open(md5_path, "r", encoding="utf-8") as f:
        md5_cache = json.load(f)
    md5_cache = clean_md5_cache(md5_cache, base_dir)
    return md5_cache


def clean_md5_cache(md5_cache: dict, base_dir: Path) -> dict:
    folders = [item.name for item in base_dir.iterdir() if item.is_dir()]
    for key in list(md5_cache.keys()):
        if key not in folders:
            del md5_cache[key]
    return md5_cache


def save_md5_cache(md5_cache: dict, base_dir: Path):
    path = base_dir / "md5_cache.json"
    temp_path = base_dir / "md5_cache.tmp"

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(md5_cache, f, ensure_ascii=False, indent=4, default=str)

        temp_path.replace(path)

    except OSError as e:
        log(f"{RED}{loc.tr('cache_not_saved')}: {e}{RESET}", 3)

    finally:
        temp_path.unlink(missing_ok=True)
