"""
CLI интерфейс для экспорта Telegram чатов.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from .config.constants import Constants
from .config.models import ExportConfig
from .exceptions.validation import ValidationError
from .orchestrator import ExportOrchestrator
from .utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


def create_argument_parser() -> argparse.ArgumentParser:
    """Создание и настройка парсера аргументов."""
    parser = argparse.ArgumentParser(
        description="Экспорт Telegram чата в интерактивный HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Пример:
  %(prog)s --chat -1001234567890 --api-id 12345 --api-hash abc123 --output my_chat.html
        """,
    )

    parser.add_argument(
        "--chat",
        type=str,
        required=True,
        help='ID, имя или никнейм Telegram чата (например: -1001234567890, "Мой чат", @mychat)',
    )

    parser.add_argument("--api-id", type=int, required=True, help="Telegram API ID")

    parser.add_argument("--api-hash", required=True, help="Telegram API hash")

    parser.add_argument(
        "--session",
        default="telegram_export_session",
        help="Имя сессии для Telegram клиента (по умолчанию: telegram_export_session)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("telegram_export.html"),
        help="Путь к выходному HTML файлу (по умолчанию: telegram_export.html)",
    )

    parser.add_argument(
        "--max-file-size",
        type=int,
        default=Constants.DEFAULT_MAX_FILE_SIZE_MB,
        help=f"Максимальный размер файла для загрузки в МБ (по умолчанию: {Constants.DEFAULT_MAX_FILE_SIZE_MB})",
    )

    parser.add_argument(
        "--max-downloads",
        type=int,
        default=Constants.MAX_CONCURRENT_DOWNLOADS,
        help=f"Максимальное количество параллельных загрузок (по умолчанию: {Constants.MAX_CONCURRENT_DOWNLOADS})",
    )

    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="Пропустить загрузку всех медиа файлов",
    )

    parser.add_argument(
        "--skip-media-types",
        nargs="*",
        choices=["photo", "video", "video_note", "voice", "audio", "document", "gif"],
        default=[],
        help="Типы медиа для пропуска (photo, video, video_note, voice, audio, document, gif)",
    )

    parser.add_argument(
        "--exclude-topics",
        nargs="*",
        default=[],
        help="Названия топиков для исключения из экспорта (например: --exclude-topics \"Спам\" \"Реклама\"). "
             "Нельзя использовать одновременно с --include-topics",
    )

    parser.add_argument(
        "--include-topics",
        nargs="*",
        default=[],
        help="Названия топиков для включения в экспорт (только указанные топики будут экспортированы). "
             "Нельзя использовать одновременно с --exclude-topics",
    )

    parser.add_argument(
        "--timezone", "-tz",
        type=str,
        default="Europe/Moscow",
        help="Таймзона для отображения времени сообщений (по умолчанию: Europe/Moscow). "
             "Примеры: Europe/Moscow, UTC, America/New_York, Asia/Tokyo"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Включить подробное логирование"
    )

    parser.add_argument(
        "--filter-include",
        nargs="*",
        default=[],
        help="Фильтр включения: показывать только сообщения, содержащие хотя бы одну из указанных подстрок "
             "(например: --filter-include \"python\" \"код\" \"bug\"). "
             "Можно комбинировать с --filter-exclude (exclude имеет приоритет)",
    )

    parser.add_argument(
        "--filter-exclude",
        nargs="*",
        default=[],
        help="Фильтр исключения: скрывать сообщения, содержащие любую из указанных подстрок "
             "(например: --filter-exclude \"спам\" \"реклама\" \"бот\"). "
             "Можно комбинировать с --filter-include (exclude имеет приоритет)",
    )

    parser.add_argument(
        "--filter-ignore-case",
        action="store_true",
        help="Игнорировать регистр при фильтрации сообщений (по умолчанию регистр учитывается)",
    )

    return parser


def validate_and_create_config(args: argparse.Namespace) -> ExportConfig:
    """Валидация аргументов и создание конфигурации."""
    if args.verbose:
        setup_logging(verbose=True)

    # Проверяем, что не заданы одновременно exclude-topics и include-topics
    if args.exclude_topics and args.include_topics:
        raise ValidationError(
            "Нельзя одновременно использовать --exclude-topics и --include-topics. "
            "Используйте либо белый список (--include-topics), либо черный список (--exclude-topics)."
        )


    # Валидация таймзоны
    try:
        timezone = ZoneInfo(args.timezone)
        logger.info(f"Используется таймзона: {args.timezone}")
    except Exception as e:
        raise ValidationError(f"Неверная таймзона '{args.timezone}': {e}")

    output_path = args.output.expanduser().resolve()

    # Формируем список типов медиа для пропуска
    skip_media_types = set(args.skip_media_types) if args.skip_media_types else set()

    # Если указан флаг --skip-media, пропускаем все типы медиа
    if args.skip_media:
        skip_media_types.update(
            {"photo", "video", "video_note", "voice", "audio", "document", "gif"}
        )

    return ExportConfig(
        api_id=args.api_id,
        api_hash=args.api_hash,
        session_name=args.session,
        chat_identifier=args.chat,
        output_path=output_path,
        skip_media_types=skip_media_types,
        excluded_topics=set(args.exclude_topics) if args.exclude_topics else set(),
        included_topics=set(args.include_topics) if args.include_topics else set(),
        max_file_size_mb=args.max_file_size,
        max_concurrent_downloads=args.max_downloads,
        timezone=timezone,
        filter_include_substrings=set(args.filter_include) if args.filter_include else set(),
        filter_exclude_substrings=set(args.filter_exclude) if args.filter_exclude else set(),
        filter_case_sensitive=not args.filter_ignore_case,
    )


async def main() -> int:
    """Главная асинхронная точка входа."""
    parser = create_argument_parser()
    args = parser.parse_args()

    try:
        config = validate_and_create_config(args)
        orchestrator = ExportOrchestrator(config)

        result = await orchestrator.export_chat()

        if result.success:
            return 0
        else:
            logger.error(f"Экспорт не удался: {result.error}")
            return 1

    except ValidationError as e:
        logger.error(f"Ошибка конфигурации: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Экспорт отменен пользователем")
        return 1
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        logger.debug("Полный traceback:", exc_info=True)
        return 1


def cli_main() -> int:
    """CLI точка входа для синхронного выполнения."""
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        print("\nЭкспорт отменен пользователем")
        return 1
