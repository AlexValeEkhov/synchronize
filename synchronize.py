from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiohttp

    from main import AppState

import asyncio
import re
import shutil
from collections import defaultdict
from pathlib import Path, PurePosixPath

import aiohttp

import localization as loc
from colors import BLUE, GREEN, ORANGE, RED, RESET, r, w, x
from local_disk import copy_with_progress, get_free_space
from logger import log
from yandex_client import download_file_from_yandex


def format_size(size_bytes: int):
    return (
        f"{size_bytes / (1024**3):.2f} {loc.tr('size_gb')}"
        if size_bytes >= 1024**3
        else f"{size_bytes / (1024**2):.2f} {loc.tr('size_mb')}"
    )


def find_invalid_paths(file_info: dict):
    INVALID_CHARS = r'[<>:"/\\|?*]'
    RESERVED_NAMES = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    grouped = defaultdict(list)

    for rel_path in file_info.keys():
        parts = PurePosixPath(rel_path).parts

        for part in parts:
            reason = None

            if re.search(INVALID_CHARS, part):
                reason = loc.tr("invalid_characters")
            elif part.endswith((" ", ".")):
                reason = loc.tr("ends_with_space_or_dot")
            elif part.upper() in RESERVED_NAMES:
                reason = loc.tr("reserved_name")

            if reason:
                grouped[(part, reason)].append(rel_path)
                break

    return grouped


def has_enough_space(free: int, size: int):
    return (free >= size, free - size if free >= size else free)


def resolve_missing(data1: dict, data2: dict, info2: dict, state: AppState, rel_path: str, folder_name: str, moved: list[str]):

    for path, info1 in data1.items():
        if info1["md5"] != info2["md5"]:
            continue

        new_path = state.base_dir / info2["path"].replace("disk:/", "")
        new_path.parent.mkdir(parents=True, exist_ok=True)

        if data2.get(path):  # copy
            copy_with_progress(info1["full_path"], new_path)
            log(f"  {GREEN}{loc.tr('copied')}: {BLUE}{info1['full_path']} {w}{BLUE}{new_path}", 2)
            data1[str(rel_path)] = {"size": info2["size"], "full_path": str(new_path), "md5": info2["md5"]}
        else:  # move
            try:
                Path(info1["full_path"]).rename(new_path)
            except OSError as e:
                if e.errno == 18:  # Invalid cross-device link
                    shutil.move(info1["full_path"], new_path)
                else:
                    raise
            moved.append(info1["full_path"])
            log(f"  {GREEN}{loc.tr('moved_or_renamed')}: {BLUE}{info1['full_path']} {w}{BLUE}{new_path}", 2)

        last_edit = new_path.stat().st_mtime
        if last_edit:
            state.md5_cache[folder_name][rel_path] = {"md5": info2["md5"], "last_edit": last_edit}

        return True

    return False


async def synchronize(
    folder: Path,
    folder_name: str,
    data1: dict,
    data2: dict,
    state: AppState,
    local: list,
    moved: list,
    session: aiohttp.ClientSession,
):
    all_paths, free = sorted(set(data1) | set(data2)), get_free_space(folder)

    for ind, rel_path in enumerate(all_paths, start=1):
        if ind % 100 == 0:
            free = get_free_space(folder)

        sync_message = f"\r{r} {BLUE}{loc.tr('synchronizing')} {ind} {loc.tr('of')} {len(all_paths)}: "
        print(sync_message, end="")
        # output delay for visual progress monitoring, could be removed for maximum speed
        lag = 0.002 if len(all_paths) > 1000 else 0.01
        await asyncio.sleep(lag)

        info1, info2 = data1.get(rel_path), data2.get(rel_path)
        local_path, download = folder / rel_path, False

        if not info1:
            found = resolve_missing(data1, data2, info2, state, rel_path, folder_name, moved)
            if found:
                continue
            log(f"\n  {x}{ORANGE}{loc.tr('only_on_yandex_disk')}: {info2['path']}")
            download = True
        elif not info2:
            log(f"{loc.tr('only_local')}: {info1['full_path']}", print_msg=False)
            local.append(info1["full_path"])
            continue
        elif info1["md5"] != info2["md5"]:
            log(
                f"\n  {ORANGE}⚠️ {loc.tr('hashes_do_not_match')}:\n"
                f"    {info1['md5']} — {loc.tr('locally')}\n"
                f"    {info2['md5']} — {loc.tr('yandex_disk')}"
            )
            download = True
        else:
            log(f"{loc.tr('identical')}: {info1['full_path']} {loc.tr('and')} {info2['path']}", print_msg=False)
            continue

        if download and info2:
            ok, free = has_enough_space(free, info2["size"])
            if ok:
                last_edit = await download_file_from_yandex(
                    info2["path"],
                    local_path,
                    state.headers,
                    session,
                    info2["size"],
                )
                if last_edit:
                    state.md5_cache[folder_name][rel_path] = {"md5": info2["md5"], "last_edit": last_edit}
            else:
                log(f"{RED}⛔ {loc.tr('insufficient_space_for')} {local_path}{RESET}", 3)

    return local, moved
