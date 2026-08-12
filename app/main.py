from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

for path in [SCRIPT_DIR, PROJECT_ROOT]:
    if path in sys.path:
        sys.path.remove(path)

sys.path.insert(0, PROJECT_ROOT)

from app.config import settings
from app.logging import get_logger
from app.bot.telegram_bot import run_bot


def main() -> None:
    logger = get_logger("app.main")
    logger.info("Iniciando %s", settings.PROJECT_NAME)
    logger.info("Modo debug: %s", settings.DEBUG)
    run_bot()


if __name__ == "__main__":
    main()
