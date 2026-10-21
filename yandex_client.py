import asyncio
from pathlib import Path, PurePosixPath

import aiohttp
from tqdm import tqdm as bar

import localization as loc
from colors import BLUE, GREEN, ORANGE, RED, RESET, WHITE, barcolor, w
from logger import log

BASE_URL = "https://cloud-api.yandex.net/v1/disk/resources"


async def get_user_info(session: aiohttp.ClientSession, headers: dict) -> dict:
    url = "https://login.yandex.ru/info"
    async with session.get(url, headers=headers, params={"format": "json"}) as response:
        response.raise_for_status()
        return await response.json()


async def get_root_folder(session, headers: dict) -> tuple[str, str] | tuple[None, None]:
    async with session.get(BASE_URL, headers=headers, params={"path": "/"}) as response:
        if response.status != 200:
            print(f"{RED}{loc.tr('http_error')}: {response.status}\n{await response.text()}")
            return None, None

        data = await response.json()

    items = data.get("_embedded", {}).get("items", [])
    folders = [item for item in items if item["type"] == "dir"]

    if not folders:
        print(f"{RED}{loc.tr('no_root_folders')}")
        return None, None

    while True:
        print(f"\n{GREEN}{loc.tr('available_root_folders')}{RESET}")
        for i, folder in enumerate(folders, start=1):
            print(f"{RED}{i:>3} {w} {BLUE}{folder['name']}")
        print(f"\n{RED}  0 {w} {ORANGE}{loc.tr('return_to_menu')}")

        try:
            choice = int(input(f"{GREEN}{loc.tr('select_folder_number')}: {w}"))
            if choice == 0:
                return None, None
            if 1 <= choice <= len(folders):
                return folders[choice - 1]["path"], folders[choice - 1]["name"]
        except ValueError:
            pass

        print(f"{RED}{loc.tr('enter_number_range')}: 0–{len(folders)}")


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

    return file_info, total_size, file_count


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
                f"  {RED}⛔ {loc.tr('download_link_error')}: {response.status}\n{await response.text()}",
                3,
            )
            return None

        data = await response.json()
        download_url = data.get("href")

    if not download_url:
        log(
            f"  {RED}⛔ {loc.tr('download_link_missing')} {yandex_path}{RESET}",
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
                    desc=f"  {BLUE}💾 {loc.tr('downloading')}",
                    ncols=100,
                    leave=False,
                    colour=barcolor,
                ) as pbar,
            ):
                async for chunk in response.content.iter_chunked(8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        log(f"  {GREEN}💾 {loc.tr('downloaded')}: {BLUE}{local_path}{RESET}")
        return local_path.stat().st_mtime

    except OSError as e:
        if e.errno == 28:
            log(
                f"  {RED}⛔ {loc.tr('insufficient_disk_space_for')} {local_path}{RESET}",
                3,
            )
            return None

        raise
