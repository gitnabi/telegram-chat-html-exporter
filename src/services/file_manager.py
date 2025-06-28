"""
Сервис управления файлами.
"""

import logging
from pathlib import Path

from ..config import Constants, ExportConfig
from ..exceptions import ExportError
from ..utils import FileSystemService

logger = logging.getLogger(__name__)


class FileManager:
    """Сервис управления файлами."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self.fs_service = FileSystemService()

    def setup_directories(self) -> Path:
        """Настроить директории для экспорта."""
        # Создаем основную директорию
        self.fs_service.create_directory(self.config.output_path.parent)

        # Создаем директорию для медиа
        media_dir = self.config.output_path.with_name(
            self.config.output_path.stem + "_media"
        )
        self.fs_service.create_directory(media_dir)

        return media_dir

    def save_export(self, html_content: str) -> None:
        """Сохранить экспорт."""
        try:
            self.config.output_path.write_text(html_content, encoding="utf-8")
            logger.info(f"HTML экспортирован в: {self.config.output_path}")
        except Exception as e:
            raise ExportError(f"Не удалось сохранить HTML файл: {e}")

    def copy_required_files(self) -> None:
        """Скопировать необходимые файлы в выходную директорию."""
        output_dir = self.config.output_path.parent
        script_dir = Path(__file__).parent.parent.parent

        # Если директории одинаковые, копирование не требуется
        if output_dir.resolve() == script_dir.resolve():
            logger.debug(
                "Файлы уже находятся в выходной директории, копирование не требуется"
            )
            return

        # Список файлов для копирования
        required_files = [
            Constants.DEFAULT_STYLES,
            Constants.DEFAULT_SCRIPT,
        ]

        for filename in required_files:
            src_file = script_dir / filename
            dst_file = output_dir / filename

            if src_file.exists():
                self.fs_service.copy_file(src_file, dst_file)
            else:
                logger.warning(
                    f"Необходимый файл {filename} не найден в директории скрипта"
                )
