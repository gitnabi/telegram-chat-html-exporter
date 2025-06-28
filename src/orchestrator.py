"""
Координатор процесса экспорта Telegram чатов.
"""

from pathlib import Path

from .config.models import ExportConfig, MediaConfig
from .exceptions.validation import ValidationError
from .models.data import ExportResult
from .renderers.html_renderer import HTMLRenderer
from .renderers.message_renderer import HTMLMessageRenderer
from .services.file_manager import FileManager
from .services.media_processor import MediaProcessor
from .services.message_processor import MessageProcessor
from .services.telegram_client import TelegramAPIClient
from .utils.decorators import retry_on_error
from .utils.logging import get_logger

logger = get_logger(__name__)


class ExportOrchestrator:
    """Координатор процесса экспорта."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self._validate_config()

        # Инициализация компонентов
        self.file_manager = FileManager(config)
        self.telegram_client = TelegramAPIClient(config)

        # Настройка рендерера
        template_path = Path(__file__).parent.parent / "template.html"
        self.html_renderer = HTMLRenderer(template_path)
        # message_renderer будет создан в export_chat после получения информации о чате
        self.message_renderer = None

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

            async with self.telegram_client as client:
                # Разрешение чата по ID, имени или никнейму
                entity = await client.resolve_chat(self.config.chat_identifier)

                # Загрузка топиков форума
                topics, is_forum = await client.load_forum_topics(entity)

                # Создание рендерера сообщений с правильными параметрами
                self.message_renderer = HTMLMessageRenderer(
                    current_chat_id=entity.id, 
                    is_forum=is_forum
                )

                # Создание процессора сообщений
                message_processor = MessageProcessor(
                    self.config, media_processor, self.message_renderer
                )

                # Обработка сообщений
                if is_forum:
                    # Если чат является форумом, итерируемся отдельно по каждому топику
                    logger.info("Обработка форума: итерация по топикам")
                    
                    processed_topics = {}
                    for topic_id, topic_data in topics.items():
                        logger.info(f"🔄 ═══ Обработка топика: {topic_data.title} (ID: {topic_id}) ═══")
                        topic_messages_iter = client.iter_messages(entity, topic_id)
                        # Создаем временный словарь для обработки этого топика
                        from .models.data import TopicData
                        temp_topics = {topic_id: TopicData(id=topic_id, title=topic_data.title)}
                        processed_temp_topics = await message_processor.process_messages_streaming(
                            topic_messages_iter, temp_topics, topic_id, client
                        )
                        # Копируем результат в основной словарь
                        processed_topics[topic_id] = processed_temp_topics[topic_id]
                    topics = processed_topics
                else:
                    # Если чат обычный, итерируемся по всем сообщениям
                    logger.info("Обработка обычного чата: итерация по всем сообщениям")
                    topics = await message_processor.process_messages_streaming(
                        client.iter_messages(entity), topics, topic_id=1, telegram_client=client
                    )

                # Проверяем, остались ли данные после фильтрации
                total_messages = sum(len(topic.messages) for topic in topics.values())
                
                if not topics or total_messages == 0:
                    logger.info("После фильтрации не осталось сообщений для экспорта")
                    logger.info("Создается пустой HTML файл...")

                logger.info(f"Данные для рендеринга: {len(topics)} топиков, {total_messages} сообщений")

                # Рендеринг HTML (работает как с данными, так и без них)
                if not topics or total_messages == 0:
                    # Создаем пустой HTML с объяснением
                    empty_message = "Все сообщения были отфильтрованы. Проверьте настройки фильтров."
                    html_content = self.html_renderer.render_empty(entity, empty_message)
                else:
                    html_content = self.html_renderer.render(entity, topics)

                # Сохранение результата
                self.file_manager.save_export(html_content)
                self.file_manager.copy_required_files()

                # Подсчет результатов
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

        except Exception as e:
            from .exceptions.api import ChatResolutionError, TelegramAPIError
            
            if isinstance(e, ChatResolutionError):
                logger.error(f"Ошибка разрешения чата: {e}")
            elif isinstance(e, TelegramAPIError):
                logger.error(f"Ошибка Telegram API: {e}")
            else:
                logger.error(f"Неожиданная ошибка во время экспорта: {e}")
            
            return ExportResult(
                success=False,
                output_path=self.config.output_path,
                total_messages=0,
                total_topics=0,
                media_count=0,
                error=str(e),
            )
