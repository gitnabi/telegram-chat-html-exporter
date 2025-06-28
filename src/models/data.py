"""
Модели данных для структурированного представления данных чата.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


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
    grouped_message_ids: List[int] = field(default_factory=list)  # ID всех сообщений в группе


@dataclass
class TopicData:
    """Структурированное представление топика форума."""

    id: int
    title: str
    messages: List[MessageData] = field(default_factory=list)


@dataclass
class ExportResult:
    """Результат операции экспорта."""

    success: bool
    output_path: Path
    total_messages: int
    total_topics: int
    media_count: int
    error: Optional[str] = None
