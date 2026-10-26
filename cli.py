from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import localization as loc
from colors import BLUE, GREEN, ORANGE, RED, RESET, WHITE, YELLOW, w, x
from logger import log
from settings import change_base_dir, change_language
from token_storage import change_token, delete_token
from yandex_client import get_root_folders

if TYPE_CHECKING:
    import aiohttp

    from main import AppState


def clear():
    subprocess.run(
        ["cmd", "/c", "cls"] if os.name == "nt" else ["clear"],
        check=False,
    )


def manage_invalid(invalid: dict):
    msg = f"{loc.tr('invalid_paths_found')}: {len(invalid)}"
    print(f"\n{x} {RED}{msg}")
    for (bad_part, reason), paths in invalid.items():
        print(f"{ORANGE}{paths[0]}")
        print(f"  └─ {RED}{bad_part}")
        print(f"  └─ {BLUE}{loc.tr('reason')}: {reason}")


async def yandex_root_menu(folders: list) -> str | None:
    while True:
        clear()
        print(f"\n{GREEN}{loc.tr('available_root_folders')}{RESET}")
        for i, folder in enumerate(folders, start=1):
            print(f"{RED}{i:>3} {w} {BLUE}{folder['name']}")
        print(f"\n{RED}  0 {w} {ORANGE}{loc.tr('return_to_menu')}")

        try:
            choice = int(input(f"{GREEN}{loc.tr('select_folder_number')}: {w}"))
            if choice == 0:
                return None
            if 1 <= choice <= len(folders):
                return folders[choice - 1]["name"]
        except ValueError:
            pass

        print(f"{RED}{loc.tr('enter_number_range')}: 0–{len(folders)}")


async def settings_menu(
    load_app_state: Callable[[aiohttp.ClientSession], Awaitable[AppState | None]],
    session: aiohttp.ClientSession,
) -> AppState | None:

    while True:
        clear()
        state = await load_app_state(session)
        if state is None:
            return None
        print(f"{BLUE}{loc.tr('user')}: {YELLOW}{state.user}")
        print(f"{GREEN}\n{loc.tr('program_settings')}:")
        print(f"{GREEN}  1 {w} {BLUE}{loc.tr('change_save_directory')}. {loc.tr('current')}: {YELLOW}{state.base_dir}")
        print(f"{GREEN}  2 {w} {BLUE}{loc.tr('change_interface_language')}. {loc.tr('current')}: {YELLOW}{state.lang}")
        print(f"{GREEN}  3 {w} {BLUE}{loc.tr('change_access_token')}")
        print(f"{GREEN}  4 {w} {BLUE}{loc.tr('delete_access_token')}")
        print(f" {'_' * 52}\n{RED} {loc.tr('any_key')} {w} {BLUE} {loc.tr('return_to_main_menu')}")

        choice = input(f"{w} ")
        if choice not in {"1", "2", "3", "4"}:
            break
        if choice == "1":
            change_base_dir()
        elif choice == "2":
            change_language()
        elif choice == "3":
            _ = change_token()
        elif choice == "4":
            delete_token()
            log(f"{YELLOW}{loc.tr('access_token_deleted_reenter_required')}")
    return state


async def main_menu(
    session: aiohttp.ClientSession,
    load_app_state: Callable[[aiohttp.ClientSession], Awaitable[AppState | None]],
    dir_list: list[str],
    state: AppState,
) -> tuple[list[str] | None, AppState | None]:

    while True:
        log(f"{BLUE}{loc.tr('user')}: {YELLOW}{state.user}")
        print(f"\n{GREEN}  1 {w} {BLUE}{loc.tr('sync_all_local_folders')}:\n\t{loc.tr('chosen')}{YELLOW}{dir_list}")
        print(f"{GREEN}  2 {w} {BLUE}{loc.tr('select_yandex_folder')} {WHITE}☁  {RED}{loc.tr('yandex_disk')}")
        print(f"{GREEN}  3 {w} {BLUE}{loc.tr('change_settings')}")
        print(f" {'_' * 52}\n{RED} {loc.tr('any_key')} {w} {BLUE} {loc.tr('exit_program')}")
        choice = input(f"{w} ")
        if choice not in {"1", "2", "3"}:
            return None, None
        if choice == "2":
            folders = await get_root_folders(session, state.headers)
            if not folders:
                continue

            name = await yandex_root_menu(folders)
            if not name:
                continue

            return [name], state
        if choice == "3":
            state = await settings_menu(load_app_state, session)
            if state is None:
                return None, None
            clear()
            continue
        if choice == "1":
            break

    return dir_list, state
