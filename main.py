#!/usr/bin/env python3
"""
Telegram Chat Exporter to Interactive HTML

Главная точка входа для экспорта Telegram чатов в HTML формат.
"""

import sys

from src.cli import cli_main
from src.utils.logging import setup_logging

# Настройка логирования по умолчанию
setup_logging()

if __name__ == "__main__":
    sys.exit(cli_main())
