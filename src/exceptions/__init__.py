"""
Пользовательские исключения для Telegram Chat Exporter.
"""

from .base import ExportError
from .api import TelegramAPIError, ChatResolutionError
from .media import MediaDownloadError
from .rendering import TemplateRenderError
from .validation import ValidationError

__all__ = [
    "ExportError",
    "TelegramAPIError", 
    "ChatResolutionError",
    "MediaDownloadError",
    "TemplateRenderError",
    "ValidationError",
]
