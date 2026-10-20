import logging
import re

from colors import x

logging.basicConfig(
    filename="_sync.log", filemode="w", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", encoding="utf-8"
)


# убирает из строки ANSI-коды
def prepare_message(text):
    replacements = {
        "✔️": "✅",
        f"{x}": "❌",
        # '{info}': 'ℹ️',
    }
    for key, val in replacements.items():
        text = text.replace(key, val)

    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


def log(msg: str, level: int = 1, print_msg: bool = True) -> None:
    if print_msg:
        print(msg)
    msg = prepare_message(msg)

    {
        1: logging.info,
        2: logging.warning,
        3: logging.error,
    }.get(level, logging.info)(msg)
