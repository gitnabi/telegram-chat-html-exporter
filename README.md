> [!WARNING]
> **ВАЙБ-ОРИЕНТИРОВАННАЯ РАЗРАБОТКА**

# Telegram Chat HTML Exporter

CLI-утилита для экспорта Telegram чатов с поддержкой форумов в интерактивный HTML формат.

## Установка зависимостей

Создание виртуального окружения
```bash
python3 -m venv venv
```
Активация окружения
```bash
source venv/bin/activate
```
Установка зависимостей
```bash
pip install -r requirements.txt
```

## Быстрый старт

### 1. Получение API ключей
1. Перейдите на https://my.telegram.org/apps (Перед этим выключайте VPN/proxy)
2. Создайте новое приложение
3. Сохраните `api_id` и `api_hash`

### 2. Экспорт чата

```bash
# По ID чата
python main.py --chat -1001234567890 --api-id 12345 --api-hash "your_api_hash" --output my_chat.html

# По имени чата
python main.py --chat "Название чата" --api-id 12345 --api-hash "your_api_hash" --output my_chat.html

# По username
python main.py --chat @mychat --api-id 12345 --api-hash "your_api_hash" --output my_chat.html
```

## Параметры

- `--chat` - ID, имя или username чата (обязательно)
- `--api-id` - Telegram API ID (обязательно)
- `--api-hash` - Telegram API hash (обязательно)
- `--session` - Имя сессии для Telegram клиента (по умолчанию: telegram_export_session)
- `--output` - Путь к выходному HTML файлу (по умолчанию: telegram_export.html)
- `--max-file-size` - Максимальный размер файла в МБ (по умолчанию: 50)
- `--max-downloads` - Максимальное количество параллельных загрузок (по умолчанию: 5)
- `--skip-media` - Пропустить все медиа файлы (флаг)
- `--skip-media-types` - Типы медиа для пропуска (по умолчанию: []) - доступные типы: photo, video, video_note, voice, audio, document, gif
- `--exclude-topics` - Названия топиков для исключения из экспорта (например: --exclude-topics "Спам" "Реклама"). Нельзя использовать одновременно с --include-topics
- `--include-topics` - Названия топиков для включения в экспорт (только указанные топики будут экспортированы). Нельзя использовать одновременно с --exclude-topics
- `--timezone`, `-tz` - Таймзона для отображения времени сообщений (по умолчанию: Europe/Moscow). Примеры: Europe/Moscow, UTC, America/New_York, Asia/Tokyo
- `--filter-include` - Фильтр включения: показывать только сообщения, содержащие хотя бы одну из указанных подстрок (например: --filter-include "python" "код" "bug"). Можно комбинировать с --filter-exclude (exclude имеет приоритет). Служебные сообщения всегда включаются независимо от фильтров
- `--filter-exclude` - Фильтр исключения: скрывать сообщения, содержащие любую из указанных подстрок (например: --filter-exclude "спам" "реклама" "бот"). Можно комбинировать с --filter-include (exclude имеет приоритет). Служебные сообщения всегда включаются независимо от фильтров
- `--filter-ignore-case` - Игнорировать регистр при фильтрации сообщений (по умолчанию регистр учитывается) (флаг)
- `--verbose`, `-v` - Включить подробное логирование (флаг)
