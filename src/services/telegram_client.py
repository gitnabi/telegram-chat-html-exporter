"""
Сервис клиента Telegram API.
"""

import logging
from typing import AsyncIterator, Dict, List, Tuple, Any, Optional

from telethon import TelegramClient, errors, utils
from telethon.tl.functions.channels import GetForumTopicsRequest
from telethon.tl.types import Message, TypePeer

from ..config import Constants, ExportConfig
from ..exceptions import TelegramAPIError, ChatResolutionError
from ..models import TopicData
from ..utils import retry_on_error

logger = logging.getLogger(__name__)


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
        """Разрешить чат по ID, имени или никнейму."""
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

        # Убираем @ если присутствует для поиска по никнейму
        username = search_term.lstrip("@")

        # Сначала пытаемся найти по никнейму
        try:
            entity = await self.client.get_entity(username)
            logger.info(
                f"Найден чат по никнейму: {utils.get_display_name(entity)} (@{username})"
            )
            return entity
        except Exception:
            logger.debug(f"Чат с никнеймом '@{username}' не найден, ищем по имени...")

        # Если не найден по никнейму, ищем по имени среди диалогов
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

        # Сортируем: сначала точные совпадения, затем частичные
        matching_chats.sort(key=lambda x: (x[2] != "exact", x[1].lower()))

        # Если найден только один чат, возвращаем его
        if len(matching_chats) == 1:
            entity, display_name, _ = matching_chats[0]
            logger.info(f"Найден чат: {display_name} (ID: {entity.id})")
            return entity

        # Если найдено несколько чатов, показываем список и просим пользователя выбрать
        return await self._handle_multiple_chats(matching_chats, search_term)

    async def _handle_multiple_chats(
        self, matching_chats: List[Tuple[Any, str, str]], search_term: str
    ) -> TypePeer:
        """Обработать случай с несколькими найденными чатами."""
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
                print("Пожалуйста, введите корректное число")
            except KeyboardInterrupt:
                raise ChatResolutionError("Выбор чата отменен пользователем")

    @retry_on_error()
    async def load_forum_topics(self, entity: TypePeer) -> Tuple[Dict[int, TopicData], bool]:
        """Загрузить топики форума если доступны. Возвращает (topics, is_forum)."""
        if not self.client:
            raise TelegramAPIError("Клиент не инициализирован")

        topics = {}
        is_forum = False
        excluded_count = 0
        
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

            is_forum = True
            logger.info("Чат является форумом")

            for topic in response.topics:
                # Проверяем фильтрацию топиков (белый и черный списки)
                if self._should_include_topic(topic.title):
                    topics[topic.id] = TopicData(id=topic.id, title=topic.title)
                else:
                    excluded_count += 1
                    logger.info(f"Топик '{topic.title}' (ID: {topic.id}) исключен из экспорта")

            logger.info(f"Загружено {len(topics)} топиков форума")
            if excluded_count > 0:
                logger.info(f"Исключено топиков: {excluded_count}")

        except errors.RPCError:
            logger.info("Чат не является форумом или нет доступа к топикам")
            # Создаем топик по умолчанию для обычных чатов
            topics[1] = TopicData(id=1, title="General")

        return topics, is_forum

    def _should_include_topic(self, topic_title: str) -> bool:
        """Проверить, следует ли включить топик в экспорт."""
        # Если указан белый список, проверяем включение
        if self.config.included_topics:
            for included_topic in self.config.included_topics:
                if topic_title.lower() == included_topic.lower():
                    break
            else:
                # Топик не найден в белом списке
                return False
        
        # Если указан черный список, проверяем исключение
        if self.config.excluded_topics:
            for excluded_topic in self.config.excluded_topics:
                if topic_title.lower() == excluded_topic.lower():
                    return False
        
        # По умолчанию включаем все топики
        return True

    def iter_messages(self, entity: TypePeer, topic_id: Optional[int] = None) -> AsyncIterator[Message]:
        """Итератор сообщений."""
        if not self.client:
            raise TelegramAPIError("Клиент не инициализирован")
        
        if topic_id is not None:
            # Итерируем по конкретному топику
            return self.client.iter_messages(entity, reverse=False, reply_to=topic_id)
        else:
            # Итерируем по всем сообщениям
            return self.client.iter_messages(entity, reverse=False)
