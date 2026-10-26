import asyncio

import keyring
import pyperclip
from keyring.errors import KeyringError
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.processors import Processor, Transformation

import localization as loc
from colors import BLUE, GREEN, ORANGE, RED, YELLOW
from logger import log

SERVICE_NAME = "YAndexDiskSync"
TOKEN_USERNAME = "user_access_token"
show_text = False


class ToggleMaskProcessor(Processor):
    def apply_transformation(self, transformation_input):
        if show_text:
            return Transformation(
                fragments=transformation_input.fragments,
            )

        masked_fragments: StyleAndTextTuples = []
        for style, text, *rest in transformation_input.fragments:
            masked_fragments.append((style, "*" * len(text)))

        return Transformation(fragments=masked_fragments)


def save_token(token: str) -> None:
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
    try:
        return keyring.get_password(
            SERVICE_NAME,
            TOKEN_USERNAME,
        )
    except KeyringError as exc:
        raise RuntimeError(f"{RED}{loc.tr('token_read_error')}") from exc


def delete_token() -> None:
    try:
        keyring.delete_password(
            SERVICE_NAME,
            TOKEN_USERNAME,
        )
    except keyring.errors.PasswordDeleteError:
        pass
    except KeyringError as exc:
        raise RuntimeError(f"{RED}{loc.tr('token_delete_error')}") from exc


async def change_token() -> str | None:
    bindings = KeyBindings()

    @bindings.add("f2")
    def paste_from_clipboard(event) -> None:
        text = pyperclip.paste()
        if text:
            event.current_buffer.insert_text(text)

    @bindings.add("f1")
    def toggle_visibility(event) -> None:
        global show_text
        show_text = not show_text
        event.app.invalidate()

    print(
        f"{GREEN}F1 {BLUE}— {loc.tr('show_hide')}\n{GREEN}F2 {BLUE}— {loc.tr('paste_clipboard')}\n{GREEN}Enter {BLUE}— {loc.tr('confirm')}.\n"
    )

    session = PromptSession(
        key_bindings=bindings,
        input_processors=[ToggleMaskProcessor()],
    )
    message = ANSI(f"{ORANGE}{loc.tr('input_token')}: {BLUE}")
    token = await session.prompt_async(message)

    if not token:
        log(f"{YELLOW}{loc.tr('token_empty')}", 2)
        await asyncio.sleep(3)
        return None

    save_token(token)
    log(f"{GREEN}{loc.tr('token_changed')}")
    return token


async def read_token() -> str | None:
    token = load_token()
    if not token:
        token = await change_token()
    return token
