# Telegram Chat HTML Exporter

Навайбкоженный скрипт для экспорта Telegram чатов с поддержкой форумов в интерактивный HTML формат.

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
1. Перейдите на https://my.telegram.org/apps
2. Создайте новое приложение
3. Сохраните `api_id` и `api_hash`

### 2. Экспорт чата

```bash
# По ID чата
python script.py --chat -1001234567890 --api-id 12345 --api-hash "your_api_hash" --output my_chat.html

# По имени чата
python script.py --chat "Название чата" --api-id 12345 --api-hash "your_api_hash" --output my_chat.html

# По username
python script.py --chat @mychat --api-id 12345 --api-hash "your_api_hash" --output my_chat.html
```

## Основные параметры

- `--chat` - ID, имя или username чата (обязательно)
- `--api-id` - Telegram API ID (обязательно)
- `--api-hash` - Telegram API hash (обязательно)
- `--output` - Путь к выходному HTML файлу
- `--skip-media` - Пропустить все медиа файлы
- `--max-file-size` - Максимальный размер файла в МБ (по умолчанию: 50)
- `--skip-media-types` - Типы медиа для пропуска (photo, video, video_note, voice, audio, document, gif)
