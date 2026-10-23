import asyncio
import traceback
from dataclasses import dataclass
from pathlib import Path

import aiohttp

import localization as loc
from cli import clear, main_menu, manage_invalid
from colors import BLUE, GREEN, ORANGE, RED, WHITE, YELLOW, v, w
from local_disk import clean_up, get_local_files_info
from logger import log
from md5_cache import (
    clean_md5_cache,
    read_md5_cache,
    save_md5_cache,
)
from settings import read_settings
from synchronize import find_invalid_paths, format_size, synchronize
from token_storage import read_token
from yandex_client import get_user_info, get_yandex_file_info_async

VER = 1.19


@dataclass
class AppState:
    base_dir: Path
    lang: str
    token: str
    headers: dict
    user: str
    md5_cache: dict


async def load_app_state(session):
    base_dir, lang = read_settings()
    loc.load_locale(lang)

    token = read_token()
    headers = {"Authorization": f"OAuth {token}"}
    user = await get_user_info(session, headers)
    md5_cache = read_md5_cache(base_dir)

    return AppState(
        base_dir=base_dir,
        lang=lang,
        token=token,
        headers=headers,
        user=user.get("login"),
        md5_cache=md5_cache,
    )


async def main_async():
    clear()
    async with aiohttp.ClientSession() as session:
        state = await load_app_state(session)
        while True:
            dir_list = [x for x in state.md5_cache.keys()]
            dir_list, state = await main_menu(session, load_app_state, dir_list, state)
            clear()
            try:
                local, moved = [], []
                for folder_name in dir_list:
                    print(f"{YELLOW}📂 {BLUE}{loc.tr('processing_folder')} {YELLOW}{folder_name}")
                    folder = state.base_dir / folder_name
                    folder.mkdir(parents=True, exist_ok=True)
                    data1, total_size, file_count = get_local_files_info(folder, folder_name, state.md5_cache)
                    log(
                        f"\n{YELLOW}📂 {GREEN}{loc.tr('local_files_found')}:{' ' * 8}{BLUE}{file_count}, "
                        f"{loc.tr('total_size')}: {total_size:,} {loc.tr('size_bytes')} ({format_size(total_size)})"
                    )
                    data2, total_size, file_count = await get_yandex_file_info_async(folder_name, state.headers, session)
                    log(
                        f"{WHITE}☁  {GREEN}{loc.tr('files_found_on')} {RED}{loc.tr('yandex_disk')} {GREEN}{loc.tr('files_count')}: "
                        f"{BLUE}{file_count}, {loc.tr('total_size')}: {total_size:,} {loc.tr('size_bytes')} ({format_size(total_size)})"
                    )
                    invalid = find_invalid_paths(data2)
                    if invalid:
                        manage_invalid(invalid)
                        break
                    local, moved = await synchronize(folder, folder_name, data1, data2, state, local, moved, session)
                else:
                    msg = loc.tr("sync_finished")
                    print(f"\n{v} {GREEN}{msg}.")
                    local = [x for x in local if x not in moved]
                    if local:
                        print(f"\n{w}{ORANGE}{loc.tr('only_local')}:")
                        for path in local:
                            print("  " + str(path))

                    clean_up(local, state.base_dir)
                    clean_md5_cache(state.md5_cache, state.base_dir)
                    save_md5_cache(state.md5_cache, state.base_dir)
                    continue
                continue
            except Exception as e:
                err_text = f"{loc.tr('critical_error')}: {e}\n{traceback.format_exc()}"
                log(err_text, 3)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
