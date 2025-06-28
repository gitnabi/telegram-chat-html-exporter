"""
Исключения, связанные с рендерингом шаблонов.
"""

from .base import ExportError


class TemplateRenderError(ExportError):
    """Ошибки рендеринга шаблонов."""

    pass
