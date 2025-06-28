"""
Типы перечислений для приложения.
"""

from enum import Enum


class MediaType(Enum):
    """Типы медиа файлов."""

    PHOTO = "photo"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"
    VOICE = "voice"
    AUDIO = "audio"
    DOCUMENT = "document"
    GIF = "gif"
