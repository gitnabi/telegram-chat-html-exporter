#!/usr/bin/env python3
"""
Telegram Chat Exporter to Interactive HTML

Скрипт для экспорта Telegram чатов с поддержкой форумов в HTML формат.
"""

import argparse
import asyncio
import functools
import html
import logging
import os
import re
import shutil
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

from jinja2 import Environment, FileSystemLoader
from telethon import TelegramClient, errors, utils  # type: ignore[import-untyped]
from telethon.tl.functions.channels import GetForumTopicsRequest  # type: ignore[import-untyped]
from telethon.tl.types import (
    Message,
    MessageMediaDocument,  # type: ignore[import-untyped]
    MessageMediaPhoto,
    TypePeer,
)
from tqdm.asyncio import tqdm  # type: ignore[import-untyped]


# Константы
class Constants:
    """Константы приложения."""

    FORUM_TOPICS_LIMIT = 200
    PROGRESS_LOG_INTERVAL = 100
    MAX_FILENAME_LENGTH = 255
    MAX_CONCURRENT_DOWNLOADS = 5
    DEFAULT_MAX_FILE_SIZE_MB = 50
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 1.0


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Отключаем подробные логи Telethon
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("telethon.network").setLevel(logging.ERROR)
logging.getLogger("telethon.client").setLevel(logging.WARNING)


# Enum для типов медиа
class MediaType(Enum):
    """Типы медиа файлов."""

    PHOTO = "photo"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"
    VOICE = "voice"
    AUDIO = "audio"
    DOCUMENT = "document"
    GIF = "gif"


# Исключения
class ExportError(Exception):
    """Базовое исключение для операций экспорта."""

    pass


class TelegramAPIError(ExportError):
    """Ошибки связанные с Telegram API."""

    pass


class MediaDownloadError(ExportError):
    """Ошибки загрузки медиа."""

    pass


class TemplateRenderError(ExportError):
    """Ошибки рендеринга шаблонов."""

    pass


class ValidationError(ExportError):
    """Ошибки валидации."""

    pass


class ChatResolutionError(ExportError):
    """Ошибки разрешения чата."""

    pass


# Декоратор для повторных попыток
def retry_on_error(
    max_attempts: int = Constants.RETRY_ATTEMPTS, delay: float = Constants.RETRY_DELAY
):
    """Декоратор для повторных попыток при ошибках."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(
                        f"Попытка {attempt + 1} неудачна: {e}, повтор через {delay}с"
                    )
                    await asyncio.sleep(
                        delay * (2**attempt)
                    )  # Экспоненциальная задержка
            return None

        return wrapper

    return decorator


@dataclass
class ExportConfig:
    """Конфигурация процесса экспорта."""

    api_id: int
    api_hash: str
    session_name: str
    chat_identifier: str
    output_path: Path
    skip_media_types: Set[str] = field(default_factory=set)
    max_file_size_mb: int = Constants.DEFAULT_MAX_FILE_SIZE_MB
    date_format: str = "%Y-%m-%d %H:%M:%S"
    max_concurrent_downloads: int = Constants.MAX_CONCURRENT_DOWNLOADS
    progress_log_interval: int = Constants.PROGRESS_LOG_INTERVAL


@dataclass
class MediaConfig:
    """Конфигурация для обработки медиа."""

    max_file_size_mb: int
    skip_media_types: Set[str]
    max_concurrent_downloads: int


@dataclass
class ReactionData:
    """Структурированное представление реакции."""

    emoticon: str
    count: int


@dataclass
class MessageData:
    """Структурированное представление сообщения."""

    id: int
    date: str
    sender: str
    html_content: str
    topic_id: int
    is_service: bool = False
    service_description: str = ""
    is_reply: bool = False
    reply_to_msg_id: Optional[int] = None
    skip_reason: str = ""
    reactions: List[ReactionData] = field(default_factory=list)


@dataclass
class TopicData:
    """Структурированное представление топика форума."""

    id: int
    title: str
    messages: List[MessageData] = field(default_factory=list)


@dataclass
class ExportResult:
    """Результат экспорта."""

    success: bool
    output_path: Path
    total_messages: int
    total_topics: int
    media_count: int
    error: Optional[str] = None


class FileSystemService:
    """Сервис для работы с файловой системой."""

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


class MessageRenderer(ABC):
    """Абстрактный рендерер сообщений."""

    @abstractmethod
    async def render_message(self, msg: Message) -> str:
        """Рендеринг сообщения."""
        pass


class HTMLMessageRenderer(MessageRenderer):
    """HTML рендерер сообщений."""

    # Паттерн для ссылок Telegram
    TELEGRAM_LINK_PATTERN = re.compile(
        r'<a\s+href="https://t\.me/c/\d+/\d+/(\d+)"([^>]*)>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    async def render_message(self, msg: Message) -> str:
        """Рендеринг HTML содержимого сообщения."""
        content_parts = []

        # Добавляем отформатированный текст
        if msg.text:
            html_text = msg.text
            # Преобразуем ссылки Telegram в внутренние якорные ссылки
            html_text = self._transform_telegram_links(html_text)
            content_parts.append(html_text)

        return "<br>".join(filter(None, content_parts))

    def _transform_telegram_links(self, html_content: str) -> str:
        """
        Преобразование ссылок Telegram в внутренние якорные ссылки.

        Преобразует: <a href="https://t.me/c/2322718547/280/283">text</a>
        В: <a href="#msg-283" class="internal-link">text</a>
        """

        def replace_link(match):
            message_id = match.group(1)  # ID сообщения
            attributes = match.group(2)  # Другие атрибуты
            link_text = match.group(3)  # Текст ссылки

            # Добавляем класс internal-link к существующим атрибутам
            if "class=" in attributes:
                attributes = re.sub(
                    r'class="([^"]*)"', r'class="\1 internal-link"', attributes
                )
            else:
                attributes = f' class="internal-link"{attributes}'

            return f'<a href="#msg-{message_id}"{attributes}>{link_text}</a>'

        return self.TELEGRAM_LINK_PATTERN.sub(replace_link, html_content)


class MediaProcessor:
    """Обработчик медиа файлов."""

    def __init__(self, media_dir: Path, config: MediaConfig):
        self.media_dir = media_dir
        self.config = config
        self.downloaded_files: Set[str] = set()
        self.download_semaphore = asyncio.Semaphore(config.max_concurrent_downloads)

    def _get_media_type(self, msg: Message) -> Optional[MediaType]:
        """Определение типа медиа с использованием enum."""
        if not msg.media:
            return None

        if isinstance(msg.media, MessageMediaPhoto):
            return MediaType.PHOTO

        # Маппинг атрибутов сообщения к типам медиа
        type_mapping = {
            "video": MediaType.VIDEO,
            "video_note": MediaType.VIDEO_NOTE,
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
        """Проверка, нужно ли пропустить медиа."""
        if not msg.media:
            return True

        media_type = self._get_media_type(msg)

        # Проверяем тип медиа
        if media_type and media_type.value in self.config.skip_media_types:
            return True

        # Проверяем размер
        return self._exceeds_size_limit(msg)

    def _exceeds_size_limit(self, msg: Message) -> bool:
        """Проверка превышения лимита размера."""
        file_size = self._get_file_size(msg)
        max_size = self.config.max_file_size_mb * 1024 * 1024
        return file_size > max_size

    def _get_file_size(self, msg: Message) -> int:
        """Получение размера файла."""
        if hasattr(msg.media, "document") and msg.media.document:
            return msg.media.document.size

        # Для других типов медиа размер неизвестен
        return 0

    @retry_on_error()
    async def process_media(self, msg: Message) -> Optional[str]:
        """Загрузка и обработка медиа, возврат HTML представления."""
        if not msg.media or self.should_skip_media(msg):
            return None

        async with self.download_semaphore:
            return await self._download_media(msg)

    async def _download_media(self, msg: Message) -> Optional[str]:
        """Загрузка медиа файла."""
        try:
            # Генерируем безопасное имя файла
            file_key = f"{msg.id}_{msg.date.timestamp()}"
            if file_key in self.downloaded_files:
                return None

            media_filename = self._generate_safe_filename(msg)
            media_path = self.media_dir / media_filename

            downloaded_path = await msg.download_media(file=media_path)
            if not downloaded_path:
                return None

            self.downloaded_files.add(file_key)
            rel_path = os.path.relpath(downloaded_path, self.media_dir.parent)

            return self._generate_media_html(msg, rel_path)

        except Exception as e:
            logger.error(f"Ошибка обработки медиа для сообщения {msg.id}: {e}")
            raise MediaDownloadError(f"Не удалось загрузить медиа: {e}")

    def _generate_safe_filename(self, msg: Message) -> str:
        """Генерация безопасного имени файла для медиа."""
        base_name = f"msg_{msg.id}"

        if hasattr(msg.media, "document") and msg.media.document:
            # Используем оригинальное имя файла если доступно
            for attr in msg.media.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    safe_name = FileSystemService.sanitize_filename(attr.file_name)
                    if safe_name:
                        return safe_name

        return base_name

    def _generate_media_html(self, msg: Message, rel_path: str) -> str:
        """Генерация HTML для медиа контента."""
        if isinstance(msg.media, MessageMediaPhoto):
            return f'<img src="{rel_path}" loading="lazy" alt="Изображение">'

        elif isinstance(msg.media, MessageMediaDocument):
            if msg.gif:
                return f'<img src="{rel_path}" loading="lazy" alt="GIF">'
            elif msg.voice or msg.audio:
                return f'<audio controls src="{rel_path}">Ваш браузер не поддерживает аудио.</audio>'
            else:
                filename = Path(rel_path).name
                return f'<a href="{rel_path}" download>📄 {html.escape(filename)}</a>'

        return f'<a href="{rel_path}">📎 Медиа файл</a>'


class TelegramAPIClient:
    """Клиент для работы с Telegram API."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self.client: Optional[TelegramClient] = None

    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        self.client = TelegramClient(
            self.config.session_name, self.config.api_id, self.config.api_hash
        )
        await self.client.start()
        self.client.parse_mode = "html"
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход."""
        if self.client:
            await self.client.disconnect()

    @retry_on_error()
    async def resolve_chat(self, chat_identifier: str) -> TypePeer:
        """Разрешение чата по ID, имени или никнейму."""
        if not self.client:
            raise TelegramAPIError("Клиент не инициализирован")

        try:
            # Проверяем, является ли идентификатор числом (ID чата)
            if chat_identifier.lstrip("-").isdigit():
                chat_id = int(chat_identifier)
                entity = await self.client.get_entity(chat_id)
                logger.info(
                    f"Найден чат по ID: {utils.get_display_name(entity)} (ID: {chat_id})"
                )
                return entity

            # Если не число, ищем по имени или никнейму
            return await self._search_chat_by_name(chat_identifier)

        except Exception as e:
            raise ChatResolutionError(
                f"Не удалось разрешить чат '{chat_identifier}': {e}"
            )

    async def _search_chat_by_name(self, search_term: str) -> TypePeer:
        """Поиск чата по имени или никнейму."""
        if not self.client:
            raise TelegramAPIError("Клиент не инициализирован")

        logger.info(f"Поиск чата по имени/никнейму: '{search_term}'")

        # Убираем @ если есть для поиска по никнейму
        username = search_term.lstrip("@")

        # Сначала пробуем найти по никнейму
        try:
            entity = await self.client.get_entity(username)
            logger.info(
                f"Найден чат по никнейму: {utils.get_display_name(entity)} (@{username})"
            )
            return entity
        except Exception:
            logger.debug(f"Чат с никнеймом '@{username}' не найден, ищем по имени...")

        # Если по никнейму не найден, ищем по имени среди диалогов
        matching_chats: List[Tuple[Any, str, str]] = []

        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            display_name = utils.get_display_name(entity)

            # Проверяем точное совпадение имени
            if display_name.lower() == search_term.lower():
                matching_chats.append((entity, display_name, "exact"))
            # Проверяем частичное совпадение
            elif search_term.lower() in display_name.lower():
                matching_chats.append((entity, display_name, "partial"))

        if not matching_chats:
            raise ChatResolutionError(f"Чат с именем '{search_term}' не найден")

        # Сортируем: сначала точные совпадения, потом частичные
        matching_chats.sort(key=lambda x: (x[2] != "exact", x[1].lower()))

        # Если найден только один чат, возвращаем его
        if len(matching_chats) == 1:
            entity, display_name, _ = matching_chats[0]
            logger.info(f"Найден чат: {display_name} (ID: {entity.id})")
            return entity

        # Если найдено несколько чатов, показываем список и просим выбрать
        return await self._handle_multiple_chats(matching_chats, search_term)

    async def _handle_multiple_chats(
        self, matching_chats: List[Tuple[Any, str, str]], search_term: str
    ) -> TypePeer:
        """Обработка случая с несколькими найденными чатами."""
        logger.info(f"Найдено {len(matching_chats)} чатов с именем '{search_term}':")

        print(f"\nНайдено {len(matching_chats)} чатов с именем '{search_term}':")
        for i, (entity, display_name, match_type) in enumerate(matching_chats, 1):
            match_indicator = "🎯" if match_type == "exact" else "🔍"
            username_info = (
                f" (@{entity.username})"
                if hasattr(entity, "username") and entity.username
                else ""
            )
            print(
                f"{i}. {match_indicator} {display_name}{username_info} (ID: {entity.id})"
            )

        while True:
            try:
                choice = input(f"\nВыберите чат (1-{len(matching_chats)}): ").strip()
                if not choice:
                    continue

                index = int(choice) - 1
                if 0 <= index < len(matching_chats):
                    entity, display_name, _ = matching_chats[index]
                    logger.info(f"Выбран чат: {display_name} (ID: {entity.id})")
                    return entity
                else:
                    print(f"Пожалуйста, введите число от 1 до {len(matching_chats)}")
            except ValueError:
                print("Пожалуйста, введите корректный номер")
            except KeyboardInterrupt:
                raise ChatResolutionError("Выбор чата отменен пользователем")

    @retry_on_error()
    async def load_forum_topics(self, entity: TypePeer) -> Dict[int, TopicData]:
        """Загрузка топиков форума если доступны."""
        if not self.client:
            raise TelegramAPIError("Клиент не инициализирован")

        topics = {}
        try:
            response = await self.client(
                GetForumTopicsRequest(
                    entity,
                    offset_date=None,
                    offset_id=0,
                    offset_topic=0,
                    limit=Constants.FORUM_TOPICS_LIMIT,
                )
            )

            for topic in response.topics:
                topics[topic.id] = TopicData(id=topic.id, title=topic.title)

            logger.info(f"Загружено {len(topics)} топиков форума")

        except errors.RPCError:
            logger.info("Чат не является форумом или нет доступа к топикам")
            # Создаем топик по умолчанию для обычных чатов
            topics[1] = TopicData(id=1, title="Общий")

        return topics

    def iter_messages(self, entity: TypePeer) -> AsyncIterator[Message]:
        """Итератор сообщений."""
        if not self.client:
            raise TelegramAPIError("Клиент не инициализирован")
        return self.client.iter_messages(entity, reverse=False)


class MessageProcessor:
    """Процессор сообщений."""

    def __init__(
        self,
        config: ExportConfig,
        media_processor: MediaProcessor,
        message_renderer: MessageRenderer,
    ):
        self.config = config
        self.media_processor = media_processor
        self.message_renderer = message_renderer

    def _format_sender_name(self, sender) -> str:
        """Форматирование имени отправителя с юзернеймом или ID."""
        if not sender:
            return "Неизвестно"

        # Получаем основное имя
        display_name = utils.get_display_name(sender)

        # Добавляем юзернейм и ID
        if hasattr(sender, "username") and sender.username:
            return f"{display_name} (ID: {sender.id}, @{sender.username})"
        else:
            return f"{display_name} (ID: {sender.id})"

    def _analyze_service_message(self, msg: Message) -> Tuple[bool, str]:
        """Анализ служебного сообщения и возврат описания."""
        if not hasattr(msg, "action") or not msg.action:
            return False, ""

        action = msg.action
        action_type = type(action).__name__

        # Маппинг типов действий к описаниям
        service_descriptions = {
            "MessageActionChatAddUser": "Пользователь добавлен в чат",
            "MessageActionChatDeleteUser": "Пользователь покинул чат",
            "MessageActionChatJoinedByLink": "Пользователь присоединился по ссылке",
            "MessageActionChatEditTitle": "Изменено название чата",
            "MessageActionChatEditPhoto": "Изменена фотография чата",
            "MessageActionChatDeletePhoto": "Удалена фотография чата",
            "MessageActionChatCreate": "Чат создан",
            "MessageActionChannelCreate": "Канал создан",
            "MessageActionChatMigrateTo": "Чат преобразован в супергруппу",
            "MessageActionChannelMigrateFrom": "Супергруппа создана из чата",
            "MessageActionPinMessage": "Сообщение закреплено",
            "MessageActionHistoryClear": "История очищена",
            "MessageActionGameScore": "Результат игры",
            "MessageActionPaymentSent": "Платеж отправлен",
            "MessageActionPhoneCall": "Звонок",
            "MessageActionScreenshotTaken": "Сделан скриншот",
            "MessageActionCustomAction": "Пользовательское действие",
            "MessageActionBotAllowed": "Бот разрешен",
            "MessageActionSecureValuesSent": "Отправлены защищенные данные",
            "MessageActionContactSignUp": "Пользователь зарегистрировался",
            "MessageActionGeoProximityReached": "Достигнута близость местоположения",
            "MessageActionGroupCall": "Групповой звонок",
            "MessageActionInviteToGroupCall": "Приглашение в групповой звонок",
            "MessageActionSetMessagesTTL": "Установлен таймер самоуничтожения",
            "MessageActionGroupCallScheduled": "Запланирован групповой звонок",
            "MessageActionSetChatTheme": "Изменена тема чата",
            "MessageActionChatJoinedByRequest": "Пользователь принят в чат по заявке",
            "MessageActionWebViewDataSent": "Данные отправлены через веб-приложение",
            "MessageActionGiftPremium": "Подарена премиум-подписка",
            "MessageActionTopicCreate": "Создан топик форума",
            "MessageActionTopicEdit": "Изменен топик форума",
        }

        description = service_descriptions.get(
            action_type, f"Служебное сообщение: {action_type}"
        )

        # Добавляем дополнительную информацию для некоторых типов
        if action_type == "MessageActionChatEditTitle" and hasattr(action, "title"):
            description += f': "{action.title}"'
        elif action_type == "MessageActionCustomAction" and hasattr(action, "message"):
            description += f': "{action.message}"'

        return True, description

    def _get_skip_reason(self, msg: Message) -> str:
        """Определение причины пропуска сообщения."""
        if not msg.media:
            return ""

        media_type = self.media_processor._get_media_type(msg)

        # Проверяем тип медиа
        if (
            media_type
            and media_type.value in self.media_processor.config.skip_media_types
        ):
            return f"содержит {media_type.value}"

        # Проверяем размер файла
        if self.media_processor._exceeds_size_limit(msg):
            file_size_mb = self.media_processor._get_file_size(msg) / (1024 * 1024)
            return f"размер файла {file_size_mb:.1f}MB > {self.media_processor.config.max_file_size_mb}MB"

        return ""

    def _get_reply_info(self, msg: Message) -> Tuple[bool, Optional[int]]:
        """Получение информации о реплае."""
        reply_to = getattr(msg, "reply_to", None)
        if (
            reply_to
            and hasattr(reply_to, "reply_to_msg_id")
            and reply_to.reply_to_msg_id
        ):
            forum_topic = getattr(reply_to, "forum_topic", False)
            reply_to_top_id = getattr(reply_to, "reply_to_top_id", None)

            if forum_topic:
                # В форуме для реплая должны быть проставлены оба поля
                if reply_to_top_id is not None:
                    return True, reply_to.reply_to_msg_id
            else:
                # В обычном чате достаточно reply_to_msg_id
                return True, reply_to.reply_to_msg_id
        return False, None

    def _extract_reactions(self, msg: Message) -> List[ReactionData]:
        """Извлечение реакций из сообщения."""
        reactions: List[ReactionData] = []

        # Проверяем наличие реакций в сообщении
        if not hasattr(msg, "reactions") or not msg.reactions:
            logger.debug(f"Сообщение {msg.id}: нет реакций")
            return reactions

        # Получаем список результатов реакций
        results = getattr(msg.reactions, "results", None)
        if not results:
            logger.debug(f"Сообщение {msg.id}: нет результатов реакций")
            return reactions

        logger.debug(f"Сообщение {msg.id}: найдено {len(results)} реакций")

        # Обрабатываем каждую реакцию
        for i, result in enumerate(results):
            # Проверяем наличие необходимых полей вместо проверки типа
            if not hasattr(result, "count") or not hasattr(result, "reaction"):
                logger.debug(
                    f"Сообщение {msg.id}, реакция {i}: отсутствуют необходимые поля"
                )
                continue

            reaction = getattr(result, "reaction", None)
            if not reaction:
                logger.debug(f"Сообщение {msg.id}, реакция {i}: нет объекта reaction")
                continue

            # Проверяем наличие поля emoticon
            emoticon = getattr(reaction, "emoticon", None)
            count = getattr(result, "count", 0)

            if emoticon and count > 0:
                reactions.append(ReactionData(emoticon=emoticon, count=count))
                logger.debug(
                    f"Сообщение {msg.id}: добавлена реакция {emoticon} x{count}"
                )

        logger.debug(f"Сообщение {msg.id}: извлечено {len(reactions)} реакций")
        return reactions

    async def process_messages_streaming(
        self, messages_iter: AsyncIterator[Message], topics: Dict[int, TopicData]
    ) -> Dict[int, TopicData]:
        """Обработка сообщений потоком с прогресс-баром."""
        # Сначала подсчитаем общее количество сообщений
        logger.info("Подсчет общего количества сообщений...")
        total_messages = 0
        all_messages = []

        async for msg in messages_iter:
            all_messages.append(msg)
            total_messages += 1
            if total_messages % self.config.progress_log_interval == 0:
                logger.info(f"Собрано {total_messages} сообщений...")

        logger.info(f"Всего сообщений для обработки: {total_messages}")

        # Группируем сообщения
        grouped_messages, single_messages = self._group_messages(all_messages)

        # Создаем единый список для сортировки
        all_items = self._create_sorted_items(grouped_messages, single_messages)

        # Обрабатываем с прогресс-баром
        with tqdm(total=len(all_items), desc="Обработка сообщений") as pbar:
            for item_type, timestamp, data in all_items:
                if item_type == "group":
                    await self._process_message_group(data, topics)
                else:
                    await self._process_single_message(data, topics)
                pbar.update(1)

        logger.info(
            f"Обработано сообщений: {total_messages} "
            f"(групп: {len(grouped_messages)}, одиночных: {len(single_messages)})"
        )

        return topics

    def _group_messages(
        self, messages: List[Message]
    ) -> Tuple[Dict[int, List[Message]], List[Message]]:
        """Группировка сообщений по grouped_id."""
        grouped_messages: Dict[int, List[Message]] = {}
        single_messages = []

        for msg in messages:
            if msg.grouped_id:
                if msg.grouped_id not in grouped_messages:
                    grouped_messages[msg.grouped_id] = []
                grouped_messages[msg.grouped_id].append(msg)
            else:
                single_messages.append(msg)

        # Сортируем сообщения внутри групп
        for group_id in grouped_messages:
            grouped_messages[group_id].sort(key=lambda x: x.id)

        return grouped_messages, single_messages

    def _create_sorted_items(
        self, grouped_messages: Dict[int, List[Message]], single_messages: List[Message]
    ) -> List[Tuple[str, datetime, Any]]:
        """Создание отсортированного списка элементов."""
        all_items = []

        # Добавляем группированные сообщения
        for group_id, messages in grouped_messages.items():
            first_msg = messages[0]
            all_items.append(("group", first_msg.date, messages))

        # Добавляем одиночные сообщения
        for msg in single_messages:
            all_items.append(("single", msg.date, msg))

        # Сортируем по времени для сохранения хронологического порядка
        all_items.sort(key=lambda x: x[1])

        return all_items

    async def _process_message_group(
        self, message_group: List[Message], topics: Dict[int, TopicData]
    ):
        """Обработка группы сообщений (альбом)."""
        if not message_group:
            return

        first_msg = message_group[0]
        topic_id = self._get_topic_id(first_msg)

        # Убеждаемся что топик существует
        if topic_id not in topics:
            topics[topic_id] = TopicData(id=topic_id, title=f"Топик {topic_id}")

        # Объединяем контент всех сообщений группы
        combined_content = []
        for msg in message_group:
            content = await self._render_message_content(msg)
            if content:
                combined_content.append(content)

        # Анализируем первое сообщение группы для метаданных
        is_service, service_desc = self._analyze_service_message(first_msg)
        is_reply, reply_to_id = self._get_reply_info(first_msg)
        skip_reason = self._get_skip_reason(first_msg)
        reactions = self._extract_reactions(first_msg)

        # Создаем единое сообщение для всей группы
        message_data = MessageData(
            id=first_msg.id,
            date=first_msg.date.strftime(self.config.date_format),
            sender=self._format_sender_name(first_msg.sender),
            html_content="<br>".join(combined_content),
            topic_id=topic_id,
            is_service=is_service,
            service_description=service_desc,
            is_reply=is_reply,
            reply_to_msg_id=reply_to_id,
            skip_reason=skip_reason,
            reactions=reactions,
        )

        topics[topic_id].messages.append(message_data)

    async def _process_single_message(self, msg: Message, topics: Dict[int, TopicData]):
        """Обработка одиночного сообщения."""
        topic_id = self._get_topic_id(msg)

        # Убеждаемся что топик существует
        if topic_id not in topics:
            topics[topic_id] = TopicData(id=topic_id, title=f"Топик {topic_id}")

        content = await self._render_message_content(msg)

        # Анализируем сообщение для получения дополнительной информации
        is_service, service_desc = self._analyze_service_message(msg)
        is_reply, reply_to_id = self._get_reply_info(msg)
        skip_reason = self._get_skip_reason(msg)
        reactions = self._extract_reactions(msg)

        message_data = MessageData(
            id=msg.id,
            date=msg.date.strftime(self.config.date_format),
            sender=self._format_sender_name(msg.sender),
            html_content=content,
            topic_id=topic_id,
            is_service=is_service,
            service_description=service_desc,
            is_reply=is_reply,
            reply_to_msg_id=reply_to_id,
            skip_reason=skip_reason,
            reactions=reactions,
        )

        topics[topic_id].messages.append(message_data)

    async def _render_message_content(self, msg: Message) -> str:
        """Рендеринг полного содержимого сообщения включая текст и медиа."""
        content_parts = []

        # Добавляем отформатированный текст
        text_content = await self.message_renderer.render_message(msg)
        if text_content:
            content_parts.append(text_content)

        # Добавляем медиа контент
        media_html = await self.media_processor.process_media(msg)
        if media_html:
            content_parts.append(media_html)

        return "<br>".join(filter(None, content_parts))

    def _get_topic_id(self, msg: Message) -> int:
        """Извлечение ID топика из сообщения."""
        reply_to = getattr(msg, "reply_to", None)
        if reply_to and getattr(reply_to, "forum_topic", False):
            return (
                getattr(reply_to, "reply_to_top_id", None)
                or getattr(reply_to, "reply_to_msg_id", None)
                or 1
            )
        return 1


class HTMLRenderer:
    """Рендерер HTML."""

    def __init__(self, template_path: Path):
        self.template_path = template_path
        self._setup_template()

    def _setup_template(self):
        """Настройка шаблона."""
        try:
            template_dir = self.template_path.parent
            env = Environment(loader=FileSystemLoader(template_dir))
            self.template = env.get_template(self.template_path.name)
        except Exception as e:
            raise TemplateRenderError(f"Не удалось загрузить шаблон: {e}")

    def render(self, entity: TypePeer, topics: Dict[int, TopicData]) -> str:
        """Рендеринг HTML контента."""
        try:
            # Сортируем топики по ID
            sorted_topics = []
            for topic_id in sorted(topics.keys()):
                topic = topics[topic_id]
                # Сортируем сообщения по ID (новые первыми для лучшего UX)
                topic.messages.sort(key=lambda x: x.id, reverse=True)
                sorted_topics.append(topic)

            # Рендерим HTML
            html_content = self.template.render(
                title=f"Архив · {utils.get_display_name(entity)}", topics=sorted_topics
            )

            return html_content

        except Exception as e:
            raise TemplateRenderError(f"Ошибка рендеринга HTML: {e}")


class FileManager:
    """Менеджер файлов."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self.fs_service = FileSystemService()

    def setup_directories(self) -> Path:
        """Настройка директорий для экспорта."""
        # Создаем основную директорию
        self.fs_service.create_directory(self.config.output_path.parent)

        # Создаем директорию для медиа
        media_dir = self.config.output_path.with_name(
            self.config.output_path.stem + "_media"
        )
        self.fs_service.create_directory(media_dir)

        return media_dir

    def save_export(self, html_content: str) -> None:
        """Сохранение экспорта."""
        try:
            self.config.output_path.write_text(html_content, encoding="utf-8")
            logger.info(f"HTML экспортирован в: {self.config.output_path}")
        except Exception as e:
            raise ExportError(f"Не удалось сохранить HTML файл: {e}")

    def copy_required_files(self) -> None:
        """Копирование необходимых файлов в директорию вывода."""
        output_dir = self.config.output_path.parent
        script_dir = Path(__file__).parent

        # Если директории одинаковые, копирование не нужно
        if output_dir.resolve() == script_dir.resolve():
            logger.debug(
                "Файлы уже находятся в директории вывода, копирование не требуется"
            )
            return

        # Список файлов для копирования
        required_files = ["styles.css", "script.js"]

        for filename in required_files:
            src_file = script_dir / filename
            dst_file = output_dir / filename

            if src_file.exists():
                self.fs_service.copy_file(src_file, dst_file)
            else:
                logger.warning(
                    f"Необходимый файл {filename} не найден в директории скрипта"
                )


class ExportOrchestrator:
    """Координатор процесса экспорта."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self._validate_config()

        # Инициализация компонентов
        self.file_manager = FileManager(config)
        self.telegram_client = TelegramAPIClient(config)

        # Настройка рендерера
        template_path = Path(__file__).parent / "template.html"
        self.html_renderer = HTMLRenderer(template_path)
        self.message_renderer = HTMLMessageRenderer()

    def _validate_config(self) -> None:
        """Валидация конфигурации."""
        if self.config.api_id <= 0:
            raise ValidationError("api_id должен быть положительным")

        if not self.config.api_hash:
            raise ValidationError("api_hash не может быть пустым")

        if self.config.max_file_size_mb <= 0:
            raise ValidationError("max_file_size_mb должен быть положительным")

    @retry_on_error()
    async def export_chat(self) -> ExportResult:
        """Экспорт чата с правильной обработкой ошибок и логикой повторов."""
        try:
            logger.info("Начинаем экспорт Telegram чата...")
            logger.info(f"Идентификатор чата: {self.config.chat_identifier}")
            logger.info(f"Вывод: {self.config.output_path}")

            # Настройка директорий
            media_dir = self.file_manager.setup_directories()

            # Создание медиа процессора после создания директории
            media_config = MediaConfig(
                max_file_size_mb=self.config.max_file_size_mb,
                skip_media_types=self.config.skip_media_types,
                max_concurrent_downloads=self.config.max_concurrent_downloads,
            )
            media_processor = MediaProcessor(media_dir, media_config)

            # Создание процессора сообщений
            message_processor = MessageProcessor(
                self.config, media_processor, self.message_renderer
            )

            async with self.telegram_client as client:
                # Разрешение чата по ID, имени или никнейму
                entity = await client.resolve_chat(self.config.chat_identifier)

                # Загрузка топиков форума
                topics = await client.load_forum_topics(entity)

                # Обработка сообщений
                topics = await message_processor.process_messages_streaming(
                    client.iter_messages(entity), topics
                )

                # Рендеринг HTML
                html_content = self.html_renderer.render(entity, topics)

                # Сохранение результата
                self.file_manager.save_export(html_content)
                self.file_manager.copy_required_files()

                # Подсчет результатов
                total_messages = sum(len(topic.messages) for topic in topics.values())
                media_count = len(media_processor.downloaded_files)

                result = ExportResult(
                    success=True,
                    output_path=self.config.output_path,
                    total_messages=total_messages,
                    total_topics=len(topics),
                    media_count=media_count,
                )

                logger.info("Экспорт завершен успешно")
                logger.info(f"✓ HTML экспортирован в: {self.config.output_path}")
                logger.info(f"✓ Топиков: {len(topics)}")
                logger.info(f"✓ Сообщений: {total_messages}")
                logger.info(f"✓ Медиа файлов: {media_count}")

                return result

        except ChatResolutionError as e:
            logger.error(f"Ошибка разрешения чата: {e}")
            return ExportResult(
                success=False,
                output_path=self.config.output_path,
                total_messages=0,
                total_topics=0,
                media_count=0,
                error=str(e),
            )
        except TelegramAPIError as e:
            logger.error(f"Ошибка Telegram API: {e}")
            return ExportResult(
                success=False,
                output_path=self.config.output_path,
                total_messages=0,
                total_topics=0,
                media_count=0,
                error=str(e),
            )
        except Exception as e:
            logger.error(f"Неожиданная ошибка во время экспорта: {e}")
            return ExportResult(
                success=False,
                output_path=self.config.output_path,
                total_messages=0,
                total_topics=0,
                media_count=0,
                error=str(e),
            )


def create_argument_parser() -> argparse.ArgumentParser:
    """Создание и настройка парсера аргументов."""
    parser = argparse.ArgumentParser(
        description="Экспорт Telegram чата в интерактивный HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Пример:
  %(prog)s --chat -1001234567890 --api-id 12345 --api-hash abc123 --output my_chat.html
        """,
    )

    parser.add_argument(
        "--chat",
        type=str,
        required=True,
        help='ID, имя или никнейм Telegram чата (например: -1001234567890, "Мой чат", @mychat)',
    )

    parser.add_argument("--api-id", type=int, required=True, help="Telegram API ID")

    parser.add_argument("--api-hash", required=True, help="Telegram API hash")

    parser.add_argument(
        "--session",
        default="telegram_export_session",
        help="Имя сессии для Telegram клиента (по умолчанию: telegram_export_session)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("telegram_export.html"),
        help="Путь к выходному HTML файлу (по умолчанию: telegram_export.html)",
    )

    parser.add_argument(
        "--max-file-size",
        type=int,
        default=Constants.DEFAULT_MAX_FILE_SIZE_MB,
        help=f"Максимальный размер файла для загрузки в МБ (по умолчанию: {Constants.DEFAULT_MAX_FILE_SIZE_MB})",
    )

    parser.add_argument(
        "--max-downloads",
        type=int,
        default=Constants.MAX_CONCURRENT_DOWNLOADS,
        help=f"Максимальное количество параллельных загрузок (по умолчанию: {Constants.MAX_CONCURRENT_DOWNLOADS})",
    )

    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="Пропустить загрузку всех медиа файлов",
    )

    parser.add_argument(
        "--skip-media-types",
        nargs="*",
        choices=["photo", "video", "video_note", "voice", "audio", "document", "gif"],
        default=[],
        help="Типы медиа для пропуска (photo, video, video_note, voice, audio, document, gif)",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Включить подробное логирование"
    )

    return parser


def validate_and_create_config(args: argparse.Namespace) -> ExportConfig:
    """Валидация аргументов и создание конфигурации."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    output_path = args.output.expanduser().resolve()

    # Формируем список типов медиа для пропуска
    skip_media_types = set(args.skip_media_types) if args.skip_media_types else set()

    # Если указан флаг --skip-media, пропускаем все типы медиа
    if args.skip_media:
        skip_media_types.update(
            {"photo", "video", "video_note", "voice", "audio", "document", "gif"}
        )

    return ExportConfig(
        api_id=args.api_id,
        api_hash=args.api_hash,
        session_name=args.session,
        chat_identifier=args.chat,
        output_path=output_path,
        skip_media_types=skip_media_types,
        max_file_size_mb=args.max_file_size,
        max_concurrent_downloads=args.max_downloads,
    )


async def main() -> int:
    """Главная асинхронная точка входа."""
    parser = create_argument_parser()
    args = parser.parse_args()

    try:
        config = validate_and_create_config(args)
        orchestrator = ExportOrchestrator(config)

        result = await orchestrator.export_chat()

        if result.success:
            return 0
        else:
            logger.error(f"Экспорт не удался: {result.error}")
            return 1

    except ValidationError as e:
        logger.error(f"Ошибка конфигурации: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Экспорт отменен пользователем")
        return 1
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        logger.debug("Полный traceback:", exc_info=True)
        return 1


def cli_main() -> int:
    """CLI точка входа для синхронного выполнения."""
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        print("\nЭкспорт отменен пользователем")
        return 1


if __name__ == "__main__":
    sys.exit(cli_main())
