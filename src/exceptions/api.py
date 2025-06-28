"""
Исключения, связанные с Telegram API.
"""

from .base import ExportError


class TelegramAPIError(ExportError):
    """Ошибки, связанные с Telegram API."""

    pass


class ChatResolutionError(ExportError):
    """Ошибки разрешения чата."""

    pass
