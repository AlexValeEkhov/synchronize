import shutil
from pathlib import Path

from tqdm import tqdm as bar

import localization as loc
from colors import BLUE, GREEN, RED, barcolor, r, v, w
from logger import log
from md5_cache import calculate_file_hash


def get_free_space(folder_name: Path):
    return shutil.disk_usage(folder_name).free


def get_local_files_info(root_dir: Path, folder_name: str, md5_cache: dict) -> {dict, int, int}:
    file_info, total_size, file_count = {}, 0, 0
    cache = md5_cache.setdefault(folder_name, {})

    for path in root_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            size = stat.st_size
            last_edit = stat.st_mtime
            rel_path = path.relative_to(root_dir).as_posix()

            file_info[rel_path] = {
                "size": size,
                "full_path": str(path),
                "last_edit": last_edit,
            }
            total_size += size
            file_count += 1
        except OSError:
            continue

    to_recalculate = []

    for rel_path, info in file_info.items():
        cache_entry = cache.get(rel_path)
        if cache_entry and info["last_edit"] == cache_entry.get("last_edit"):
            info["md5"] = cache_entry["md5"]
        else:
            to_recalculate.append((rel_path, info))

    total = len(to_recalculate)
    if total:
        for ind, (rel_path, info) in enumerate(to_recalculate, start=1):
            message = f"\r{r} {BLUE}{loc.tr('calculating_file_hash')} {ind} {loc.tr('of')} {total} "
            print(message, end="", flush=True)
            md5 = calculate_file_hash(root_dir / rel_path)
            info["md5"] = md5
            cache[rel_path] = {"md5": md5, "last_edit": info["last_edit"]}
        print()

    for rel_path in list(cache.keys()):
        if rel_path not in file_info:
            del cache[rel_path]

    return file_info, total_size, file_count


def copy_with_progress(src, dst, buffer_size=8 * 1024 * 1024):
    total_size = Path(src).stat().st_size
    with (
        open(src, "rb") as fsrc,
        open(dst, "wb") as fdst,
        bar(
            total=total_size,
            unit="B",
            unit_scale=True,
            desc=f"  {BLUE}💾 {loc.tr('copying')}",
            leave=False,
            ncols=100,
            colour=barcolor,
        ) as pbar,
    ):
        for buf in iter(lambda: fsrc.read(buffer_size), b""):
            fdst.write(buf)
            pbar.update(len(buf))


def clean_up(local: list[str], base_dir: Path):
    if local and input(f"{RED}{loc.tr('delete_local_files_prompt')}{w} ").lower() == "y":
        for file in local:
            try:
                Path(file).unlink()
                print(f"{v} {GREEN}{file} {loc.tr('deleted_from_local_disk')}\n")
            except FileNotFoundError:
                continue
    for dirpath in sorted(base_dir.rglob("*"), key=lambda p: -p.parts.__len__()):
        if dirpath.is_dir():
            try:
                dirpath.rmdir()
                log(f"{loc.tr('empty_folder_deleted')}: {dirpath.name}", print_msg=False)
            except OSError:
                continue
    print()
