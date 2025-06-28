"""
Константы приложения.
"""


class Constants:
    """Константы приложения."""

    # API limits
    FORUM_TOPICS_LIMIT = 200
    MAX_CONCURRENT_DOWNLOADS = 5
    
    # File handling
    MAX_FILENAME_LENGTH = 255
    DEFAULT_MAX_FILE_SIZE_MB = 50
    
    # Progress and logging
    PROGRESS_LOG_INTERVAL = 100
    
    # Retry configuration
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 1.0
    
    # Default timezone
    DEFAULT_TIMEZONE = "Europe/Moscow"
    
    # Template files
    DEFAULT_TEMPLATE = "template.html"
    DEFAULT_STYLES = "styles.css"
    DEFAULT_SCRIPT = "script.js"
