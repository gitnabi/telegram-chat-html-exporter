"""
Сервис обработки медиа.
"""

import asyncio
import html
import logging
import os
from pathlib import Path
from typing import Optional, Set

from telethon.tl.types import Message, MessageMediaDocument, MessageMediaPhoto

from ..config import MediaConfig
from ..exceptions import MediaDownloadError
from ..models import MediaType
from ..utils import FileSystemService, retry_on_error

logger = logging.getLogger(__name__)


class MediaProcessor:
    """Класс для обработки медиафайлов"""

    def __init__(self, media_dir: Path, config: MediaConfig):
        self.media_dir = media_dir
        self.config = config
        self.downloaded_files: Set[str] = set()
        self.download_semaphore = asyncio.Semaphore(config.max_concurrent_downloads)
        self._global_media_counter = 0  # Глобальный счетчик для уникальных ID
        logger.info(f"Инициализирован MediaProcessor с max_concurrent_downloads={config.max_concurrent_downloads}")

    def _get_next_global_index(self) -> int:
        """Получить следующий глобальный индекс для медиа."""
        self._global_media_counter += 1
        return self._global_media_counter

    def _get_file_extension(self, msg: Message) -> str:
        """Определить правильное расширение файла по типу медиа."""
        # Сначала пытаемся получить расширение из оригинального имени файла
        if hasattr(msg.media, "document") and msg.media.document:
            for attr in msg.media.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    original_path = Path(attr.file_name)
                    if original_path.suffix:
                        return original_path.suffix.lower()

        # Определяем расширение по типу медиа
        media_type = self._get_media_type(msg)
        
        if media_type == MediaType.PHOTO:
            return ".jpg"
        elif media_type == MediaType.VIDEO:
            return ".mp4"
        elif media_type == MediaType.VIDEO_NOTE:
            return ".mp4"
        elif media_type == MediaType.VOICE:
            return ".ogg"
        elif media_type == MediaType.AUDIO:
            return ".mp3"
        elif media_type == MediaType.GIF:
            return ".gif"
        elif media_type == MediaType.DOCUMENT:
            # Для документов пытаемся определить по MIME-типу
            if hasattr(msg.media, "document") and msg.media.document:
                mime_type = getattr(msg.media.document, "mime_type", "")
                if "pdf" in mime_type:
                    return ".pdf"
                elif "image" in mime_type:
                    if "webp" in mime_type:
                        return ".webp"
                    elif "png" in mime_type:
                        return ".png"
                    elif "gif" in mime_type:
                        return ".gif"
                    else:
                        return ".jpg"
                elif "video" in mime_type:
                    return ".mp4"
                elif "audio" in mime_type:
                    return ".mp3"
                elif "text" in mime_type:
                    return ".txt"
                elif "zip" in mime_type or "archive" in mime_type:
                    return ".zip"
            return ".bin"  # fallback для неизвестных документов
        
        # fallback для неизвестных типов
        return ".bin"

    def _get_media_base_name(self, msg: Message) -> str:
        """Построить базовое имя файла медиа, объединяя тип медиа и оригинальное имя."""
        # Определяем тип медиа
        media_type = self._get_media_type(msg)
        media_type_str = media_type.value if media_type else "unknown"
        
        # Пытаемся получить оригинальное имя файла
        safe_name = None
        if hasattr(msg.media, "document") and msg.media.document:
            for attr in msg.media.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    original_path = Path(attr.file_name)
                    safe_name = FileSystemService.sanitize_filename(original_path.stem)
                    if safe_name:
                        break
        
        # Формируем итоговое имя
        if safe_name:
            return f"{media_type_str}_{safe_name}"
        else:
            return media_type_str


    def _generate_unique_filename(self, msg: Message) -> str:
        """Генерировать уникальное имя файла.
    
        Формат:
        - С оригинальным именем: msg_{msg_id}_{global_index}_{media_type}_{original_name}.{extension}
        - Без оригинального имени: msg_{msg_id}_{global_index}_{media_type}.{extension}
        """
        global_index = self._get_next_global_index()
        base_name = self._get_media_base_name(msg)
        extension = self._get_file_extension(msg)
        
        # Формируем финальное имя файла
        filename = f"msg_{msg.id}_{global_index}_{base_name}{extension}"
        
        logger.debug(f"Сгенерировано уникальное имя файла: {filename}")
        return filename

    def _get_media_type(self, msg: Message) -> Optional[MediaType]:
        """Определить тип медиа с использованием enum."""
        if not msg.media:
            return None

        if isinstance(msg.media, MessageMediaPhoto):
            return MediaType.PHOTO

        # Соответствие атрибутов сообщения типам медиа
        type_mapping = {
            "video_note": MediaType.VIDEO_NOTE,
            "video": MediaType.VIDEO,
            "voice": MediaType.VOICE,
            "audio": MediaType.AUDIO,
            "gif": MediaType.GIF,
        }

        # Проверяем атрибуты сообщения
        for attr, media_type in type_mapping.items():
            if getattr(msg, attr, False):
                return media_type

        # Если это документ, но не специальный тип
        if isinstance(msg.media, MessageMediaDocument):
            return MediaType.DOCUMENT

        return None

    def should_skip_media(self, msg: Message) -> bool:
        """Проверить, следует ли пропустить медиа."""
        if not msg.media:
            return True

        media_type = self._get_media_type(msg)

        # Проверяем тип медиа
        if media_type and media_type.value in self.config.skip_media_types:
            return True

        # Проверяем размер
        return self._exceeds_size_limit(msg)

    def _exceeds_size_limit(self, msg: Message) -> bool:
        """Проверить, превышает ли размер файла лимит."""
        file_size = self._get_file_size(msg)
        max_size = self.config.max_file_size_mb * 1024 * 1024
        return file_size > max_size

    def _get_file_size(self, msg: Message) -> int:
        """Получить размер файла."""
        if hasattr(msg.media, "document") and msg.media.document:
            return msg.media.document.size

        # Для других типов медиа размер неизвестен
        return 0

    @retry_on_error()
    async def process_media(self, msg: Message) -> Optional[str]:
        """Загрузить и обработать медиа, вернуть HTML представление."""
        if not msg.media or self.should_skip_media(msg):
            return None

        # Логируем ожидание семафора
        logger.debug(f"Сообщение {msg.id}: ожидание слота для загрузки (активных: {self.config.max_concurrent_downloads - self.download_semaphore._value})")
        
        async with self.download_semaphore:
            logger.debug(f"Сообщение {msg.id}: начало загрузки медиа (активных загрузок: {self.config.max_concurrent_downloads - self.download_semaphore._value})")
            try:
                result = await self._download_media(msg)
                logger.debug(f"Сообщение {msg.id}: завершена загрузка медиа")
                return result
            except Exception as e:
                logger.error(f"Ошибка загрузки медиа для сообщения {msg.id}: {e}")
                return None

    async def _download_media(self, msg: Message) -> Optional[str]:
        """Загрузить медиа файл."""
        try:
            # Генерируем уникальное имя файла
            media_filename = self._generate_unique_filename(msg)
            
            # Используем уникальное имя как ключ для предотвращения дублирования
            if media_filename in self.downloaded_files:
                logger.debug(f"Файл {media_filename} уже был загружен, пропускаем")
                return None

            media_path = self.media_dir / media_filename

            downloaded_path = await msg.download_media(file=media_path)
            if not downloaded_path:
                return None

            self.downloaded_files.add(media_filename)
            rel_path = os.path.relpath(downloaded_path, self.media_dir.parent)

            return self._generate_media_html(msg, rel_path)

        except Exception as e:
            logger.error(f"Ошибка обработки медиа для сообщения {msg.id}: {e}")
            raise MediaDownloadError(f"Не удалось загрузить медиа: {e}")


    def _generate_media_html(self, msg: Message, rel_path: str) -> str:
        """Сгенерировать HTML для медиа контента."""
        if isinstance(msg.media, MessageMediaPhoto):
            return f'<img src="{rel_path}" loading="lazy" alt="Image">'

        elif isinstance(msg.media, MessageMediaDocument):
            if msg.gif:
                return f'<img src="{rel_path}" loading="lazy" alt="GIF">'
            elif msg.voice or msg.audio:
                return f'<audio controls src="{rel_path}">Your browser does not support audio.</audio>'
            else:
                filename = Path(rel_path).name
                return f'<a href="{rel_path}" download>📄 {html.escape(filename)}</a>'

        return f'<a href="{rel_path}">📎 Media file</a>'
