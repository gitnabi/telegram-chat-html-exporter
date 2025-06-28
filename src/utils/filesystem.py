"""
Утилиты файловой системы.
"""

import os
import re
import shutil
import logging
from pathlib import Path
from typing import Optional

from ..config import Constants
from ..exceptions import ExportError

logger = logging.getLogger(__name__)


class FileSystemService:
    """Сервис для операций с файловой системой."""

    @staticmethod
    def create_directory(path: Path) -> None:
        """Создание директории."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Создана директория: {path}")
        except Exception as e:
            raise ExportError(f"Не удалось создать директорию {path}: {e}")

    @staticmethod
    def copy_file(src: Path, dst: Path) -> None:
        """Копирование файла."""
        try:
            shutil.copy2(src, dst)
            logger.debug(f"Скопирован файл: {src} -> {dst}")
        except Exception as e:
            logger.warning(f"Не удалось скопировать файл {src}: {e}")

    @staticmethod
    def sanitize_filename(filename: str) -> Optional[str]:
        """Очистка имени файла для предотвращения path traversal."""
        # Удаляем разделители путей и опасные символы
        filename = os.path.basename(filename)
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        filename = filename.strip(". ")

        # Ограничиваем длину
        if len(filename) > Constants.MAX_FILENAME_LENGTH:
            name, ext = os.path.splitext(filename)
            filename = name[:250] + ext

        return filename if filename else None
