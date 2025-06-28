"""
Сервис рендеринга сообщений.
"""

import re
from abc import ABC, abstractmethod
from typing import Optional

from telethon.tl.types import Message


class MessageRenderer(ABC):
    """Абстрактный рендерер сообщений."""

    @abstractmethod
    async def render_message(self, msg: Message) -> str:
        """Рендеринг сообщения."""
        pass


class HTMLMessageRenderer(MessageRenderer):
    """HTML рендерер сообщений."""

    def __init__(self, current_chat_id: Optional[int] = None, is_forum: bool = False):
        """
        Инициализация рендерера.
        
        Args:
            current_chat_id: ID текущего обрабатываемого чата
            is_forum: Является ли чат форумом
        """
        self.current_chat_id = current_chat_id
        self.is_forum = is_forum

    # Паттерн для ссылок на сообщения в форуме: /c/CHAT_ID/TOPIC_ID/MESSAGE_ID (3 числа)
    FORUM_MESSAGE_LINK_PATTERN = re.compile(
        r'<a\s+href="https://t\.me/c/(\d+)/(\d+)/(\d+)(?:\?[^"]*)??"([^>]*)>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    # Паттерн для ссылок на топики форума: /c/CHAT_ID/TOPIC_ID (2 числа, но не сообщение)
    # Используем negative lookahead чтобы убедиться, что нет третьего числа после второго
    FORUM_TOPIC_LINK_PATTERN = re.compile(
        r'<a\s+href="https://t\.me/c/(\d+)/(\d+)(?!/\d+)(?:\?[^"]*)??"([^>]*)>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    # Паттерн для ссылок на сообщения в обычном чате: /c/CHAT_ID/MESSAGE_ID (2 числа, но не форум)
    # Этот паттерн будет использоваться только в обычных чатах
    REGULAR_MESSAGE_LINK_PATTERN = re.compile(
        r'<a\s+href="https://t\.me/c/(\d+)/(\d+)(?:\?[^"]*)??"([^>]*)>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    async def render_message(self, msg: Message) -> str:
        """Рендеринг HTML контента сообщения."""
        content_parts = []

        # Добавляем отформатированный текст
        if msg.text:
            html_text = msg.text
            # Преобразуем Telegram ссылки во внутренние anchor ссылки
            html_text = self._transform_telegram_links(html_text)
            content_parts.append(html_text)

        return "<br>".join(filter(None, content_parts))

    def _transform_telegram_links(self, html_content: str) -> str:
        """
        Преобразование Telegram ссылок во внутренние anchor ссылки.
        
        Обрабатывает три типа ссылок:
        1. https://t.me/c/CHAT_ID/TOPIC_ID/MESSAGE_ID - ссылка на сообщение в форуме
        2. https://t.me/c/CHAT_ID/MESSAGE_ID - ссылка на сообщение в обычном чате  
        3. https://t.me/c/CHAT_ID/TOPIC_ID - ссылка на топик в форуме
        
        Ссылки на другие чаты (с другим chat_id) остаются внешними.
        """
        if self.is_forum:
            # В форуме сначала обрабатываем ссылки на сообщения (с MESSAGE_ID)
            # затем ссылки на топики (без MESSAGE_ID)
            html_content = self.FORUM_MESSAGE_LINK_PATTERN.sub(self._replace_forum_message_link, html_content)
            html_content = self.FORUM_TOPIC_LINK_PATTERN.sub(self._replace_forum_topic_link, html_content)
            return html_content
        else:
            # В обычном чате обрабатываем только ссылки на сообщения
            return self.REGULAR_MESSAGE_LINK_PATTERN.sub(self._replace_regular_message_link, html_content)

    def _replace_forum_message_link(self, match):
        """Обработка ссылок на сообщения в форуме."""
        chat_id = int(match.group(1))      # CHAT_ID
        topic_id = match.group(2)          # TOPIC_ID
        message_id = match.group(3)        # MESSAGE_ID
        attributes = match.group(4)        # Атрибуты
        link_text = match.group(5)         # Текст ссылки
        
        # Проверяем, относится ли ссылка к текущему чату
        if self.current_chat_id and chat_id != self.current_chat_id:
            # Оставляем как внешнюю ссылку
            return match.group(0)
        
        # Добавляем класс internal-link к существующим атрибутам
        if "class=" in attributes:
            attributes = re.sub(
                r'class="([^"]*)"', r'class="\1 internal-link"', attributes
            )
        else:
            attributes = f' class="internal-link"{attributes}'
        
        # Ссылка на сообщение в форуме: /c/CHAT_ID/TOPIC_ID/MESSAGE_ID
        attributes += f' data-msg-id="{message_id}" data-topic-id="{topic_id}"'
        return f'<a href="#msg-{message_id}"{attributes}>{link_text}</a>'

    def _replace_forum_topic_link(self, match):
        """Обработка ссылок на топики форума."""
        chat_id = int(match.group(1))      # CHAT_ID
        topic_id = match.group(2)          # TOPIC_ID
        attributes = match.group(3)        # Атрибуты
        link_text = match.group(4)         # Текст ссылки
        
        # Проверяем, относится ли ссылка к текущему чату
        if self.current_chat_id and chat_id != self.current_chat_id:
            # Оставляем как внешнюю ссылку
            return match.group(0)
        
        # Добавляем класс internal-link к существующим атрибутам
        if "class=" in attributes:
            attributes = re.sub(
                r'class="([^"]*)"', r'class="\1 internal-link"', attributes
            )
        else:
            attributes = f' class="internal-link"{attributes}'
        
        # Ссылка на топик форума: /c/CHAT_ID/TOPIC_ID
        attributes += f' data-topic-id="{topic_id}"'
        return f'<a href="#topic-{topic_id}"{attributes}>{link_text}</a>'

    def _replace_regular_message_link(self, match):
        """Обработка ссылок на сообщения в обычном чате."""
        chat_id = int(match.group(1))      # CHAT_ID
        message_id = match.group(2)        # MESSAGE_ID
        attributes = match.group(3)        # Атрибуты
        link_text = match.group(4)         # Текст ссылки
        
        # Проверяем, относится ли ссылка к текущему чату
        if self.current_chat_id and chat_id != self.current_chat_id:
            # Оставляем как внешнюю ссылку
            return match.group(0)
        
        # Добавляем класс internal-link к существующим атрибутам
        if "class=" in attributes:
            attributes = re.sub(
                r'class="([^"]*)"', r'class="\1 internal-link"', attributes
            )
        else:
            attributes = f' class="internal-link"{attributes}'
        
        # Добавляем data-msg-id для обработки JavaScript
        attributes += f' data-msg-id="{message_id}"'
        
        # Ссылка на сообщение в обычном чате: /c/CHAT_ID/MESSAGE_ID
        return f'<a href="#msg-{message_id}"{attributes}>{link_text}</a>'
