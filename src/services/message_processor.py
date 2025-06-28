"""
Процессор сообщений для обработки и группировки сообщений Telegram.
"""

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Tuple

from telethon import utils
from telethon.tl.types import Message
from tqdm.asyncio import tqdm

from ..config.models import ExportConfig
from ..models.data import MessageData, ReactionData, TopicData
from ..renderers.message_renderer import MessageRenderer
from .media_processor import MediaProcessor
from .message_filter import MessageFilter
from ..utils.logging import get_logger

logger = get_logger(__name__)


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
        self.message_filter = MessageFilter(config)
        
        # Логируем информацию о фильтрации
        filter_summary = self.message_filter.get_filter_summary()
        logger.info(f"Настройки фильтрации: {filter_summary}")

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

    def _format_message_date(self, msg_date: datetime) -> str:
        """Форматирование времени сообщения с учетом таймзоны."""
        # Конвертируем UTC время в указанную таймзону
        from zoneinfo import ZoneInfo
        localized_date = msg_date.replace(tzinfo=ZoneInfo("UTC")).astimezone(self.config.timezone)
        return localized_date.strftime(self.config.date_format)

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

    def _get_reply_info(self, msg: Message) -> Tuple[bool, int]:
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
        self, messages_iter: AsyncIterator[Message], topics: Dict[int, TopicData], topic_id: int, telegram_client=None
    ) -> Dict[int, TopicData]:
        """Обработка сообщений потоком с прогресс-баром и фильтрацией во время обработки."""
        # Сначала собираем все сообщения
        logger.info("Сбор сообщений...")
        total_messages = 0
        all_messages = []

        async for msg in messages_iter:
            total_messages += 1
            all_messages.append(msg)
                
            if total_messages % self.config.progress_log_interval == 0:
                logger.info(f"Собрано {total_messages} сообщений...")

        logger.info(f"Всего собрано сообщений: {total_messages}")

        # Группируем ВСЕ сообщения перед фильтрацией
        grouped_messages, single_messages = self._group_messages(all_messages)

        # Применяем фильтрацию с учетом групп
        logger.info("Фильтрация сообщений с учетом групп...")
        filtered_grouped, filtered_single, excluded_count = self._filter_grouped_messages(grouped_messages, single_messages)
        
        # Подсчитываем количество сообщений после фильтрации
        filtered_message_count = sum(len(group) for group in filtered_grouped.values()) + len(filtered_single)
        
        logger.info(f"После фильтрации: {filtered_message_count} сообщений, исключено: {excluded_count}")

        # Если все сообщения отфильтрованы, возвращаем пустые топики
        if filtered_message_count == 0:
            logger.info("Все сообщения отфильтрованы, создание пустых топиков...")
            if topic_id not in topics:
                topics[topic_id] = TopicData(id=topic_id, title=f"Топик {topic_id}")
            return topics

        # Создаем список отфильтрованных сообщений для дальнейшей обработки
        filtered_messages = []
        for group in filtered_grouped.values():
            filtered_messages.extend(group)
        filtered_messages.extend(filtered_single)

        # Создаем единый список для сортировки из отфильтрованных сообщений
        all_items = self._create_sorted_items(filtered_grouped, filtered_single)

        # ЭТАП 1: Обрабатываем текст сообщений (без медиа)
        logger.info("Этап 1: Обработка текста сообщений...")
        with tqdm(total=len(all_items), desc="Обработка текста") as pbar:
            for item_type, timestamp, data in all_items:
                if item_type == "group":
                    await self._process_message_group_text_only(data, topics, topic_id)
                else:
                    await self._process_single_message_text_only(data, topics, topic_id)
                pbar.update(1)

        # ЭТАП 2: Параллельная загрузка всех медиа файлов
        logger.info("Этап 2: Параллельная загрузка медиа...")
        await self._process_all_media_parallel(filtered_messages, topics, topic_id)

        logger.info(
            f"Обработано сообщений: {len(filtered_messages)} "
            f"(групп: {len(filtered_grouped)}, одиночных: {len(filtered_single)})"
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

    def _filter_grouped_messages(
        self, grouped_messages: Dict[int, List[Message]], single_messages: List[Message]
    ) -> Tuple[Dict[int, List[Message]], List[Message], int]:
        """
        Фильтрация сообщений с учетом групп.
        Если хотя бы одно сообщение в группе проходит фильтр - включаем всю группу.
        
        Args:
            grouped_messages: Словарь групп сообщений
            single_messages: Список одиночных сообщений
            
        Returns:
            Кортеж: (отфильтрованные_группы, отфильтрованные_одиночные, количество_исключенных)
        """
        filtered_grouped: Dict[int, List[Message]] = {}
        filtered_single: List[Message] = []
        excluded_count = 0
        
        # Фильтруем групповые сообщения
        for group_id, messages in grouped_messages.items():
            # Проверяем, проходит ли хотя бы одно сообщение в группе фильтр
            group_passes_filter = False
            for msg in messages:
                if self.message_filter.should_include_raw_message(msg):
                    group_passes_filter = True
                    break
            
            if group_passes_filter:
                # Включаем всю группу
                filtered_grouped[group_id] = messages
                logger.debug(f"Группа {group_id} включена (содержит {len(messages)} сообщений)")
            else:
                # Исключаем всю группу
                excluded_count += len(messages)
                logger.debug(f"Группа {group_id} исключена (содержит {len(messages)} сообщений)")
        
        # Фильтруем одиночные сообщения как обычно
        for msg in single_messages:
            if self.message_filter.should_include_raw_message(msg):
                filtered_single.append(msg)
            else:
                excluded_count += 1
        
        return filtered_grouped, filtered_single, excluded_count

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

    async def _process_message_group_text_only(
        self, message_group: List[Message], topics: Dict[int, TopicData], topic_id: int
    ):
        """Обработка группы сообщений (только текст, без медиа)."""
        if not message_group:
            return

        first_msg = message_group[0]

        # Убеждаемся что топик существует
        if topic_id not in topics:
            topics[topic_id] = TopicData(id=topic_id, title=f"Топик {topic_id}")

        # Объединяем только текстовый контент всех сообщений группы
        combined_content = []
        for msg in message_group:
            text_content = await self.message_renderer.render_message(msg)
            if text_content:
                combined_content.append(text_content)

        # Анализируем первое сообщение группы для метаданных
        is_service, service_desc = self._analyze_service_message(first_msg)
        is_reply, reply_to_id = self._get_reply_info(first_msg)
        skip_reason = self._get_skip_reason(first_msg)
        reactions = self._extract_reactions(first_msg)

        # Собираем все ID сообщений в группе
        grouped_message_ids = [msg.id for msg in message_group]
        logger.debug(f"Создание группы сообщений с ID: {grouped_message_ids}")

        # Создаем единое сообщение для всей группы (пока без медиа)
        message_data = MessageData(
            id=first_msg.id,
            date=self._format_message_date(first_msg.date),
            sender=self._format_sender_name(first_msg.sender),
            html_content="<br>".join(combined_content),
            topic_id=topic_id,
            is_service=is_service,
            service_description=service_desc,
            is_reply=is_reply,
            reply_to_msg_id=reply_to_id,
            skip_reason=skip_reason,
            reactions=reactions,
            grouped_message_ids=grouped_message_ids,
        )

        topics[topic_id].messages.append(message_data)

    async def _process_single_message_text_only(self, msg: Message, topics: Dict[int, TopicData], topic_id: int):
        """Обработка одиночного сообщения (только текст, без медиа)."""
        # Убеждаемся что топик существует
        if topic_id not in topics:
            topics[topic_id] = TopicData(id=topic_id, title=f"Топик {topic_id}")

        # Рендерим только текстовый контент
        text_content = await self.message_renderer.render_message(msg)

        # Анализируем сообщение для получения дополнительной информации
        is_service, service_desc = self._analyze_service_message(msg)
        is_reply, reply_to_id = self._get_reply_info(msg)
        skip_reason = self._get_skip_reason(msg)
        reactions = self._extract_reactions(msg)

        message_data = MessageData(
            id=msg.id,
            date=self._format_message_date(msg.date),
            sender=self._format_sender_name(msg.sender),
            html_content=text_content or "",
            topic_id=topic_id,
            is_service=is_service,
            service_description=service_desc,
            is_reply=is_reply,
            reply_to_msg_id=reply_to_id,
            skip_reason=skip_reason,
            reactions=reactions,
        )

        topics[topic_id].messages.append(message_data)

    async def _process_all_media_parallel(
        self, messages: List[Message], topics: Dict[int, TopicData], topic_id: int
    ):
        """Параллельная обработка всех медиа файлов."""
        # Собираем все сообщения с медиа
        media_messages = []
        for msg in messages:
            if msg.media and not self.media_processor.should_skip_media(msg):
                media_messages.append(msg)

        if not media_messages:
            logger.info("Нет медиа файлов для загрузки")
            return

        logger.info(f"Найдено {len(media_messages)} медиа файлов для загрузки")

        # Ограничиваем количество параллельных загрузок
        max_concurrent = self.config.max_concurrent_downloads
        logger.info(f"Максимальное количество параллельных загрузок: {max_concurrent}")

        # Обрабатываем медиа батчами
        completed_count = 0
        total_count = len(media_messages)
        
        with tqdm(total=total_count, desc="Загрузка медиа") as pbar:
            # Разбиваем на батчи по max_concurrent
            for i in range(0, total_count, max_concurrent):
                batch = media_messages[i:i + max_concurrent]
                
                # Создаем задачи для текущего батча
                batch_tasks = []
                for msg in batch:
                    task = asyncio.create_task(
                        self.media_processor.process_media(msg),
                        name=f"media_{msg.id}"
                    )
                    batch_tasks.append((msg.id, task))

                # Ждем завершения всех задач в батче
                batch_results = await asyncio.gather(*[task for _, task in batch_tasks], return_exceptions=True)
                
                # Обрабатываем результаты
                for (msg_id, _), result in zip(batch_tasks, batch_results):
                    try:
                        if isinstance(result, Exception):
                            logger.error(f"Ошибка загрузки медиа для сообщения {msg_id}: {result}")
                        elif result:
                            # Находим соответствующее сообщение и добавляем медиа
                            self._add_media_to_message(topics, topic_id, msg_id, result)
                        
                        completed_count += 1
                        pbar.update(1)
                    except Exception as e:
                        logger.error(f"Ошибка обработки результата для сообщения {msg_id}: {e}")
                        completed_count += 1
                        pbar.update(1)

        logger.info(f"Загрузка медиа завершена: {completed_count}/{total_count}")

    def _add_media_to_message(
        self, topics: Dict[int, TopicData], topic_id: int, msg_id: int, media_html: str
    ):
        """Добавление медиа к уже обработанному сообщению."""
        if topic_id not in topics:
            logger.debug(f"Топик {topic_id} не найден для добавления медиа сообщения {msg_id}")
            return

        # Ищем сообщение по основному ID или по ID в группе
        for message in topics[topic_id].messages:
            # Проверяем основной ID сообщения
            if message.id == msg_id:
                logger.debug(f"Добавление медиа к сообщению {msg_id} (основной ID)")
                self._append_media_to_content(message, media_html)
                return
            
            # Проверяем ID в группе сообщений
            if msg_id in message.grouped_message_ids:
                logger.debug(f"Добавление медиа к сообщению {message.id} (медиа из группы, ID: {msg_id})")
                self._append_media_to_content(message, media_html)
                return

        logger.warning(f"Сообщение с ID {msg_id} не найдено в топике {topic_id} для добавления медиа")

    def _append_media_to_content(self, message: MessageData, media_html: str):
        """Добавление медиа к контенту сообщения."""
        if message.html_content:
            message.html_content += "<br>" + media_html
        else:
            message.html_content = media_html
