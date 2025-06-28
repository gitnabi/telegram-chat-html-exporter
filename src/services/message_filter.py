"""
Сервис для фильтрации сообщений по подстрокам.
"""

from typing import Set

from telethon.tl.types import Message

from ..config.models import ExportConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)


class MessageFilter:
    """Фильтр сообщений по содержимому."""

    def __init__(self, config: ExportConfig):
        self.config = config
        self.include_substrings = config.filter_include_substrings
        self.exclude_substrings = config.filter_exclude_substrings
        self.case_sensitive = config.filter_case_sensitive
        
        # Логируем настройки фильтрации
        if self.include_substrings:
            logger.info(f"Фильтр включения активен: {list(self.include_substrings)}")
        if self.exclude_substrings:
            logger.info(f"Фильтр исключения активен: {list(self.exclude_substrings)}")
        if self.include_substrings and self.exclude_substrings:
            logger.info("Используется комбинированная фильтрация (exclude имеет приоритет)")
        if self.include_substrings or self.exclude_substrings:
            logger.info(f"Учет регистра: {'включен' if self.case_sensitive else 'выключен'}")


    def _contains_any_substring(self, text: str, substrings: Set[str]) -> bool:
        """
        Проверяет, содержит ли текст любую из указанных подстрок.
        
        Args:
            text: Текст для проверки
            substrings: Множество подстрок для поиска
            
        Returns:
            True, если найдена хотя бы одна подстрока
        """
        if not text or not substrings:
            return False
            
        # Приводим к нужному регистру если необходимо
        search_text = text if self.case_sensitive else text.lower()
        
        for substring in substrings:
            search_substring = substring if self.case_sensitive else substring.lower()
            if search_substring in search_text:
                return True
                
        return False


    def get_filter_summary(self) -> str:
        """
        Возвращает краткое описание активных фильтров.
        
        Returns:
            Строка с описанием фильтров
        """
        if not self.include_substrings and not self.exclude_substrings:
            return "Фильтрация отключена"
            
        parts = []
        
        if self.include_substrings:
            parts.append(f"Включение: {', '.join(sorted(self.include_substrings))}")
            
        if self.exclude_substrings:
            parts.append(f"Исключение: {', '.join(sorted(self.exclude_substrings))}")
            
        case_info = "с учетом регистра" if self.case_sensitive else "без учета регистра"
        
        return f"{' | '.join(parts)} ({case_info}) - служебные сообщения всегда включены"

    def should_include_raw_message(self, message: Message) -> bool:
        """
        Определяет, должно ли сырое сообщение от Telegram API быть включено в экспорт.
        Служебные сообщения всегда включаются, фильтрация применяется только к обычным сообщениям пользователей.
        
        Логика фильтрации:
        1. Если задан include фильтр - сообщение должно содержать хотя бы одну подстроку из списка
        2. Если задан exclude фильтр - сообщение НЕ должно содержать ни одной подстроки из списка
        3. Exclude фильтр имеет приоритет над include фильтром
        
        Args:
            message: Сырое сообщение от Telegram API
            
        Returns:
            True, если сообщение должно быть включено, False - если исключено
        """
        # Служебные сообщения всегда пропускаем (не фильтруем)
        if hasattr(message, 'action') and message.action:
            return True
            
        # Если нет фильтров, включаем все обычные сообщения
        if not self.include_substrings and not self.exclude_substrings:
            return True
            
        # Получаем текст сообщения напрямую
        message_text = message.message
        
        # Если нет текста в обычном сообщении, применяем логику по умолчанию
        if not message_text:
            # Если есть фильтр включения - исключаем сообщения без текста
            # Если есть только фильтр исключения - включаем сообщения без текста
            return not bool(self.include_substrings)
        
        # Сначала проверяем include фильтр (если задан)
        if self.include_substrings:
            if not self._contains_any_substring(message_text, self.include_substrings):
                return False  # Не прошло include фильтр

        # Затем проверяем exclude фильтр (если задан) - он имеет приоритет
        if self.exclude_substrings:
            if self._contains_any_substring(message_text, self.exclude_substrings):
                return False  # Исключено exclude фильтром
                
        return True  # Прошло все фильтры
