import asyncio
from pathlib import Path, PurePosixPath

import aiohttp

import localization as loc
from colors import RED, RESET
from logger import log

BASE_URL = "https://cloud-api.yandex.net/v1/disk/resources"


async def get_user_info(session: aiohttp.ClientSession, headers: dict) -> dict:
    url = "https://login.yandex.ru/info"
    async with session.get(url, headers=headers, params={"format": "json"}) as response:
        response.raise_for_status()
        return await response.json()


async def get_root_folders(session: aiohttp.ClientSession, headers: dict) -> list[dict] | None:
    async with session.get(BASE_URL, headers=headers, params={"path": "/"}) as response:
        if response.status != 200:
            print(f"{RED}{loc.tr('http_error')}: {response.status}\n{await response.text()}")
            return None

        data = await response.json()

    items = data.get("_embedded", {}).get("items", [])
    folders = [item for item in items if item["type"] == "dir"]

    if not folders:
        print(f"{RED}{loc.tr('no_root_folders')}")
        return None

    return folders


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


async def get_download_url(
    yandex_path: str,
    headers: dict,
    session: aiohttp.ClientSession,
) -> str | None:

    url = f"{BASE_URL}/download"
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
    return download_url
