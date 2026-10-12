"""Настройки приложения.

Значения берутся из переменных окружения или из файла .env рядом с программой
(пример смотри в .env.example). Пароль от базы больше не хранится в коде.
"""
import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    """Мини-загрузчик .env без внешних библиотек."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(Path(__file__).resolve().parent / ".env")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "photo_bd"),
}

# Названия ролей в таблице «роль»
ROLE_ADMIN = "админ"
ROLE_CLIENT = "клиент"
ROLE_PHOTOGRAPHER = "фотограф"

# Статусы фотосессий. Значение «проведена» было в исходном коде,
# остальные два подправь под свою базу, если в ней другие слова.
STATUS_PLANNED = "запланирована"
STATUS_DONE = "проведена"
STATUS_CANCELLED = "отменена"
