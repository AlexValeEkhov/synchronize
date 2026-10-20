import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import traceback
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import aiohttp
from tqdm import tqdm as bar

import localization as loc
from colors import (
    BLUE,
    GREEN,
    ORANGE,
    RED,
    RESET,
    WHITE,
    YELLOW,
    barcolor,
    l,
    o,
    r,
    v,
    w,
    x,
)
from logger import log
from settings import change_base_dir, change_language, read_settings
from token_storage import change_token, delete_token, read_token

VER = 1.19
BASE_URL = "https://cloud-api.yandex.net/v1/disk/resources"


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


def clear():
    subprocess.run(
        ["cmd", "/c", "cls"] if os.name == "nt" else ["clear"],
        check=False,
    )


async def get_user_info(session: aiohttp.ClientSession, headers: dict) -> dict:
    url = "https://login.yandex.ru/info"
    async with session.get(url, headers=headers, params={"format": "json"}) as response:
        response.raise_for_status()
        return await response.json()


async def get_root_folder(session, headers: dict) -> tuple[str, str] | tuple[None, None]:
    async with session.get(BASE_URL, headers=headers, params={"path": "/"}) as response:
        if response.status != 200:
            print(f"{RED}Ошибка: {response.status}\n{await response.text()}")
            return None, None

        data = await response.json()

    items = data.get("_embedded", {}).get("items", [])
    folders = [item for item in items if item["type"] == "dir"]

    if not folders:
        print(f"{RED}Нет доступных папок в корне")
        return None, None

    while True:
        print(f"\n{GREEN}Доступные папки в корне Яндекс.Диска:{RESET}")
        for i, folder in enumerate(folders, start=1):
            print(f"{RED}{i:>3} {w} {BLUE}{folder['name']}")
        print(f"\n{RED}  0 {w} {ORANGE}Вернуться в меню")

        try:
            choice = int(input(f"{GREEN}Выберите номер папки: {w}"))
            if choice == 0:
                return None, None
            if 1 <= choice <= len(folders):
                return folders[choice - 1]["path"], folders[choice - 1]["name"]
        except ValueError:
            pass

        print(f"{RED}Ошибка: введите число от 0 до {len(folders)}")


def get_free_space(folder_name: Path):
    return shutil.disk_usage(folder_name).free


def format_size(size_bytes: int):
    return f"{size_bytes / (1024**3):.2f} ГБ" if size_bytes >= 1024**3 else f"{size_bytes / (1024**2):.2f} МБ"


def read_md5_cache(base_dir):
    md5_path = base_dir / "md5_cache.json"
    if not (md5_path).exists():
        return {}
    with open(md5_path, "r", encoding="utf-8") as f:
        md5_cache = json.load(f)
    md5_cache = clean_md5_cache(md5_cache, base_dir)
    return md5_cache


def clean_md5_cache(md5_cache, base_dir):
    folders = [item.name for item in base_dir.iterdir() if item.is_dir()]
    for key in list(md5_cache.keys()):
        if key not in folders:
            del md5_cache[key]
    return md5_cache


def get_file_info(root_dir: Path, folder_name: str, md5_cache: dict):
    file_info, total_size, file_count = {}, 0, 0
    cache = md5_cache.setdefault(folder_name, {})  # если папки нет в кэше — создаём

    # --- обход папки ---
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

    # --- этап 1: определяем что нужно пересчитывать ---
    to_recalculate = []

    for rel_path, info in file_info.items():
        cache_entry = cache.get(rel_path)
        if cache_entry and info["last_edit"] == cache_entry.get("last_edit"):
            info["md5"] = cache_entry["md5"]
        else:
            to_recalculate.append((rel_path, info))

    # --- этап 2: считаем md5 только для нужных файлов ---
    total = len(to_recalculate)
    if total:
        for ind, (rel_path, info) in enumerate(to_recalculate, start=1):
            md5 = calculate_file_hash(root_dir / rel_path, ind=ind, total=total)
            info["md5"] = md5
            cache[rel_path] = {"md5": md5, "last_edit": info["last_edit"]}

    # --- очистка кэша от лишних записей---
    for rel_path in list(cache.keys()):
        if rel_path not in file_info:
            del cache[rel_path]

    log(
        f"\n{YELLOW}📂 {GREEN}Локально найдено файлов:{' ' * 8}{BLUE}{file_count}, "
        f"общий размер: {total_size:,} байт ({format_size(total_size)})"
    )
    return file_info


def calculate_file_hash(file_path: Path, ind: int, total: int, hash_algorithm: str = "md5"):
    message = f"\r{r} {BLUE}Считаю хэш-сумму файла {ind} из {total}: \n"
    print(message, end="")
    try:
        h = hashlib.new(hash_algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None


async def get_yandex_file_info_async(base_path: str, headers: dict, session: aiohttp.ClientSession):
    file_info, total_size, file_count = {}, 0, 0

    async def list_folder(session, path):
        nonlocal total_size, file_count
        offset, limit = 0, 1000
        while True:
            params = {"path": path, "limit": limit, "offset": offset}
            async with session.get(BASE_URL, headers=headers, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
            items = data.get("_embedded", {}).get("items", [])
            if not items:
                break

            tasks = []
            for item in items:
                item_path = item["path"].replace("disk:", "").lstrip("/")
                if item["type"] == "dir":
                    tasks.append(list_folder(session, item["path"]))
                else:
                    rel_path = str(PurePosixPath(item_path).relative_to(base_path))
                    file_info[rel_path] = {"size": item["size"], "path": item["path"], "md5": item["md5"]}
                    total_size += item["size"]
                    file_count += 1

            if tasks:
                await asyncio.gather(*tasks)
            if len(items) < limit:
                break
            offset += limit

    await list_folder(session, f"disk:/{base_path.strip('/')}")

    log(
        f"{WHITE}☁  {GREEN}На {RED}Яндекс.Диске {GREEN}найдено файлов: "
        f"{BLUE}{file_count}, общий размер: {total_size:,} байт ({format_size(total_size)})"
    )
    return file_info


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
                reason = "запрещённые символы"
            elif part.endswith((" ", ".")):
                reason = "заканчивается на пробел или точку"
            elif part.upper() in RESERVED_NAMES:
                reason = "зарезервированное имя"

            if reason:
                grouped[(part, reason)].append(rel_path)
                break

    return grouped


def manage_invalid(invalid):
    msg = f"На Яндексе найдены проблемные пути: {len(invalid)}"
    print(f"\n{x} {RED}{msg}")
    for (bad_part, reason), paths in invalid.items():
        print(f"{ORANGE}{paths[0]}")
        print(f"  └─ {RED}{bad_part}")
        print(f"  └─ {BLUE}причина: {reason}")


def has_enough_space(free: int, size: int):
    return (free >= size, free - size if free >= size else free)


async def download_file_from_yandex(
    yandex_path: str,
    local_path: Path,
    headers: dict,
    session: aiohttp.ClientSession,
    size: int = 10_000_000,
) -> float | None:
    url = f"{BASE_URL}/download"

    # Этап 1. Получаем ссылку на скачивание через API Яндекс.Диска.
    async with session.get(
        url,
        headers=headers,
        params={"path": yandex_path},
    ) as response:
        if response.status != 200:
            log(
                f"  {RED}⛔ Ошибка получения ссылки: {response.status}\n{await response.text()}",
                3,
            )
            return None

        data = await response.json()
        download_url = data.get("href")

    if not download_url:
        log(
            f"  {RED}⛔ Не удалось получить ссылку на скачивание для {yandex_path}{RESET}",
            3,
        )
        return None

    # Этап 2. Скачиваем файл и записываем его на диск.
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)

        async with session.get(download_url) as response:
            response.raise_for_status()

            with (
                open(local_path, "wb") as f,
                bar(
                    total=size,
                    unit="B",
                    unit_scale=True,
                    desc=f"  {BLUE}💾 Скачиваю",
                    ncols=100,
                    leave=False,
                    colour=barcolor,
                ) as pbar,
            ):
                async for chunk in response.content.iter_chunked(8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        log(f"  {GREEN}💾 Скачано: {BLUE}{local_path}{RESET}")
        return local_path.stat().st_mtime

    except OSError as e:
        if e.errno == 28:
            log(
                f"  {RED}⛔ Недостаточно места на диске для {local_path}{RESET}",
                3,
            )
            return None

        raise


def copy_with_progress(src, dst, buffer_size=8 * 1024 * 1024):
    total_size = Path(src).stat().st_size
    with (
        open(src, "rb") as fsrc,
        open(dst, "wb") as fdst,
        bar(
            total=total_size, unit="B", unit_scale=True, desc=f"  {BLUE}💾 Копирую", leave=False, ncols=100, colour=barcolor
        ) as pbar,
    ):
        for buf in iter(lambda: fsrc.read(buffer_size), b""):
            fdst.write(buf)
            pbar.update(len(buf))


def resolve_missing(data1: dict, data2: dict, info2: dict, state: AppState, rel_path: str, folder_name: str, moved: list[str]):

    for path, info1 in data1.items():
        if info1["md5"] != info2["md5"]:
            continue

        new_path = state.base_dir / info2["path"].replace("disk:/", "")
        new_path.parent.mkdir(parents=True, exist_ok=True)

        if data2.get(path):  # копирование
            copy_with_progress(info1["full_path"], new_path)
            log(f"  {GREEN}Скопирован: {BLUE}{info1['full_path']} {w}{BLUE}{new_path}", 2)
            data1[str(rel_path)] = {"size": info2["size"], "full_path": str(new_path), "md5": info2["md5"]}
        else:  # перемещение
            try:
                Path(info1["full_path"]).rename(new_path)
            except OSError as e:
                if e.errno == 18:  # Invalid cross-device link
                    shutil.move(info1["full_path"], new_path)
                else:
                    raise
            moved.append(info1["full_path"])
            log(f"  {GREEN}Перемещен/Переименован: {BLUE}{info1['full_path']} {w}{BLUE}{new_path}", 2)

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

        sync_message = f"\r{r} {BLUE}Синхронизация {ind} из {len(all_paths)}: "
        print(sync_message, end="")

        lag = 0.002 if len(all_paths) > 1000 else 0.01
        await asyncio.sleep(lag)

        info1, info2 = data1.get(rel_path), data2.get(rel_path)
        local_path, download = folder / rel_path, False

        if not info1:
            found = resolve_missing(data1, data2, info2, state, rel_path, folder_name, moved)
            if found:
                continue
            log(f"\n  {x}{ORANGE}Только на Яндекс.Диске: {info2['path']}")
            download = True
        elif not info2:
            log(f"Только локально: {info1['full_path']}", print_msg=False)
            local.append(info1["full_path"])
            continue
        elif info1["md5"] != info2["md5"]:
            log(f"\n  {ORANGE}⚠️ Хэшсуммы не совпадают:\n    {info1['md5']} — Локально\n    {info2['md5']} — Яндекс.Диск")
            download = True
        else:
            log(f"Идентичны: {info1['full_path']} и {info2['path']}", print_msg=False)
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
                log(f"{RED}⛔ Недостаточно места для {local_path}{RESET}", 3)

    return local, moved


def clean_up(local: list[str], base_dir: Path):
    if local and input(f"{RED}Удалить локальные файлы? Y/N\n{w} ").lower() == "y":
        for file in local:
            try:
                Path(file).unlink()
                print(f"{v} {GREEN}{file} удален с локального диска.")
            except FileNotFoundError:
                continue
    for dirpath in sorted(base_dir.rglob("*"), key=lambda p: -p.parts.__len__()):
        if dirpath.is_dir():
            try:
                dirpath.rmdir()
                log(f"Удалена пустая папка: {dirpath.name}", print_msg=False)
            except OSError:
                continue
    print()


def save_md5_cache(md5_cache: dict, base_dir: Path):
    path = base_dir / "md5_cache.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(md5_cache, f, ensure_ascii=False, indent=4, default=str)


async def settings_menu(state: AppState, session: aiohttp.ClientSession):
    while True:
        clear()
        state = await load_app_state(session)
        print(f"{BLUE}Пользователь: {YELLOW}{state.user}")
        print(f"{GREEN}\nНастройки программы:")
        print(f"{GREEN}  1 {w} {BLUE}Изменить каталог сохранения. Текущий: {YELLOW}{state.base_dir}")
        print(f"{GREEN}  2 {w} {BLUE}Изменить язык интерфейса. Текущий: {YELLOW}{state.lang}")
        print(f"{GREEN}  3 {w} {BLUE}Изменить токен доступа")
        print(f"{GREEN}  4 {w} {BLUE}Удалить токен доступа")
        print(f" {'_' * 52}\n{RED} Any Key {w} {BLUE} Вернуться в главное меню")

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
            log(f"{YELLOW}Токен доступа удален. Необходимо ввести новый токен для продолжения работы.")
    return state


async def main_async():
    clear()
    async with aiohttp.ClientSession() as session:
        state = await load_app_state(session)
        while True:
            dir_list = [x for x in state.md5_cache.keys()]
            try:
                log(f"{BLUE}Пользователь: {YELLOW}{state.user}")
                print(f"\n{GREEN}  1 {w} {BLUE}Синхронизировать все папки на локальном диске:\n\t{YELLOW}{dir_list}")
                print(f"{GREEN}  2 {w} {BLUE}Выбрать папку для синхронизации на {RED}Яндекс.Диске")
                print(f"{GREEN}  3 {w} {BLUE}Изменить настройки")
                print(f" {'_' * 52}\n{RED} Any Key {w} {BLUE} Выйти из программы.")
                choice = input(f"{w} ")
                if choice not in {"1", "2", "3"}:
                    break
                if choice == "2":
                    _, name = await get_root_folder(session, state.headers)
                    if not name:
                        continue
                    dir_list = [name]
                if choice == "3":
                    state = await settings_menu(state, session)
                    clear()
                    continue
                clear()

                local, moved = [], []
                for folder_name in dir_list:
                    print(f"{YELLOW}📂 {BLUE}Обрабатываю папку {YELLOW}{folder_name}")
                    folder = state.base_dir / folder_name
                    folder.mkdir(parents=True, exist_ok=True)
                    data1 = get_file_info(folder, folder_name, state.md5_cache)
                    data2 = await get_yandex_file_info_async(folder_name, state.headers, session)
                    invalid = find_invalid_paths(data2)
                    if invalid:
                        manage_invalid(invalid)
                        break
                    local, moved = await synchronize(folder, folder_name, data1, data2, state, local, moved, session)
                else:
                    msg = "Синхронизация окончена"
                    print(f"\n{v} {GREEN}{msg}.")
                    local = [x for x in local if x not in moved]
                    if local:
                        print(f"\n{w}{ORANGE}Только локально:")
                        for path in local:
                            print("  " + str(path))

                    clean_up(local, state.base_dir)
                    clean_md5_cache(state.md5_cache, state.base_dir)
                    save_md5_cache(state.md5_cache, state.base_dir)
                    continue
                continue
            except Exception as e:
                err_text = f"Критическая ошибка: {e}\n{traceback.format_exc()}"
                log(err_text, 3)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
