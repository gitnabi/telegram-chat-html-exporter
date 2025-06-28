"""
Исключения, связанные с обработкой медиа.
"""

from .base import ExportError


class MediaDownloadError(ExportError):
    """Ошибки загрузки медиа."""

    pass
