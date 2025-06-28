"""
HTML рендерер для генерации финального HTML файла.
"""

from pathlib import Path
from typing import Dict

from jinja2 import Environment, FileSystemLoader
from telethon import utils
from telethon.tl.types import TypePeer

from ..exceptions.rendering import TemplateRenderError
from ..models.data import TopicData
from ..utils.logging import get_logger

logger = get_logger(__name__)


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
            total_messages = sum(len(topic.messages) for topic in topics.values()) if topics else 0
            logger.info(f"Рендеринг HTML: {len(topics) if topics else 0} топиков, {total_messages} сообщений")

            # Сортируем топики по ID
            sorted_topics = []
            if topics:
                for topic_id in sorted(topics.keys()):
                    topic = topics[topic_id]
                    if topic.messages:  # Включаем только топики с сообщениями
                        # Сортируем сообщения по ID (новые первыми для лучшего UX)
                        topic.messages.sort(key=lambda x: x.id, reverse=True)
                        sorted_topics.append(topic)
                    else:
                        logger.debug(f"Пропускаем пустой топик: {topic.title} (ID: {topic_id})")

            # Рендерим HTML (даже если нет топиков - шаблон обработает это)
            html_content = self.template.render(
                title=f"Архив · {utils.get_display_name(entity)}", 
                topics=sorted_topics
            )

            logger.info("HTML успешно отрендерен")
            return html_content

        except Exception as e:
            logger.error(f"Неожиданная ошибка при рендеринге HTML: {e}")
            logger.debug("Детали ошибки:", exc_info=True)
            raise TemplateRenderError(f"Неожиданная ошибка рендеринга HTML: {type(e).__name__}: {e}")

    def render_empty(self, entity: TypePeer, message: str) -> str:
        """Рендеринг HTML для случая когда нет данных для отображения."""
        try:
            logger.info("Рендеринг пустого HTML файла")
            
            # Создаем пустой список топиков для шаблона
            empty_topics = []
            
            # Рендерим HTML с пустыми данными и сообщением
            html_content = self.template.render(
                title=f"Архив · {utils.get_display_name(entity)} (пустой)",
                topics=empty_topics,
                empty_message=message
            )
            
            logger.info("Пустой HTML успешно отрендерен")
            return html_content
            
        except Exception as e:
            logger.error(f"Ошибка при рендеринге пустого HTML: {e}")
            logger.debug("Детали ошибки:", exc_info=True)
            raise TemplateRenderError(f"Ошибка рендеринга пустого HTML: {type(e).__name__}: {e}")
