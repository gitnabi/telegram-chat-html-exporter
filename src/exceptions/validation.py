"""
Исключения, связанные с валидацией.
"""

from .base import ExportError


class ValidationError(ExportError):
    """Ошибки валидации входных данных."""

    pass
