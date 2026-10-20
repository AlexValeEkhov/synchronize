import keyring
from keyring.errors import KeyringError

import localization as loc
from colors import BLUE, GREEN, ORANGE, RED, YELLOW
from logger import log

SERVICE_NAME = "YAndexDiskSync"
TOKEN_USERNAME = "user_access_token"


def save_token(token: str) -> None:
    """Сохранить пользовательский токен."""
    if not isinstance(token, str) or not token.strip():
        raise ValueError(f"{YELLOW}{loc.tr('token_empty')}")

    try:
        keyring.set_password(
            SERVICE_NAME,
            TOKEN_USERNAME,
            token,
        )
    except KeyringError as exc:
        raise RuntimeError(f"{RED}{loc.tr('token_save_error')}") from exc


def load_token() -> str | None:
    """Получить токен или None, если он отсутствует."""
    try:
        return keyring.get_password(
            SERVICE_NAME,
            TOKEN_USERNAME,
        )
    except KeyringError as exc:
        raise RuntimeError(f"{RED}{loc.tr('token_read_error')}") from exc


def delete_token() -> None:
    """Удалить сохранённый токен."""
    try:
        keyring.delete_password(
            SERVICE_NAME,
            TOKEN_USERNAME,
        )
    except keyring.errors.PasswordDeleteError:
        pass
    except KeyringError as exc:
        raise RuntimeError(f"{RED}{loc.tr('token_delete_error')}") from exc


def change_token():
    token = input(f"{ORANGE}{loc.tr('input_token')}: {BLUE}")
    save_token(token)
    log(f"{GREEN}{loc.tr('token_changed')}")
    return token


def read_token():
    token = load_token()
    if not token:
        token = change_token()
    return token
