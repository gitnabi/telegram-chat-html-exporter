"""
Утилиты конфигурации логирования.
"""

import logging


def setup_logging(verbose: bool = False) -> None:
    """Настройка логирования приложения."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Disable verbose logs from Telethon
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("telethon.network").setLevel(logging.ERROR)
    logging.getLogger("telethon.client").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Получить логгер с указанным именем."""
    return logging.getLogger(name)
