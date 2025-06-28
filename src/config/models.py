"""
Модели данных конфигурации.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Set
from zoneinfo import ZoneInfo

from .constants import Constants


@dataclass
class ExportConfig:
    """Конфигурация для процесса экспорта."""

    api_id: int
    api_hash: str
    session_name: str
    chat_identifier: str
    output_path: Path
    skip_media_types: Set[str] = field(default_factory=set)
    excluded_topics: Set[str] = field(default_factory=set)
    included_topics: Set[str] = field(default_factory=set)
    max_file_size_mb: int = Constants.DEFAULT_MAX_FILE_SIZE_MB
    date_format: str = "%Y-%m-%d %H:%M:%S"
    max_concurrent_downloads: int = Constants.MAX_CONCURRENT_DOWNLOADS
    progress_log_interval: int = Constants.PROGRESS_LOG_INTERVAL
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo(Constants.DEFAULT_TIMEZONE))
    filter_include_substrings: Set[str] = field(default_factory=set)
    filter_exclude_substrings: Set[str] = field(default_factory=set)
    filter_case_sensitive: bool = True


@dataclass
class MediaConfig:
    """Конфигурация для обработки медиа."""

    max_file_size_mb: int
    skip_media_types: Set[str]
    max_concurrent_downloads: int
