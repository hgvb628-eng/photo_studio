"""Авторизация и хранение паролей.

Пароли хешируются через PBKDF2-HMAC-SHA256 с индивидуальной солью.
Старые хеши (обычный SHA-256, 64 символа) продолжают работать и при первом входе
автоматически заменяются на новые, если колонка «пароль» достаточно длинная
(нужно выполнить: ALTER TABLE пользователь MODIFY пароль VARCHAR(255);).
"""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Optional

import db
from config import DB_CONFIG

PREFIX = "pbkdf2_sha256"
ITERATIONS = 600_000


@dataclass
class User:
    id: int
    role: str
    name: str
    client_id: Optional[int]
    photographer_id: Optional[int]


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return f"{PREFIX}${ITERATIONS}${salt}${digest}"


def _is_legacy(stored: str) -> bool:
    return len(stored) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored)


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if _is_legacy(stored):
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, stored.lower())
    try:
        prefix, iterations, salt, digest = stored.split("$")
        if prefix != PREFIX:
            return False
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
    except ValueError:
        return False
    return hmac.compare_digest(calc, digest)


def _password_column_fits(length: int) -> bool:
    row = db.fetch_one(
        "SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'пользователь' AND COLUMN_NAME = 'пароль'",
        (DB_CONFIG["database"],),
    )
    return bool(row and row[0] and row[0] >= length)


def _upgrade_hash(user_id: int, password: str) -> None:
    """Заменить старый SHA-256 на PBKDF2, если колонка позволяет. Ошибки не мешают входу."""
    try:
        new_hash = hash_password(password)
        if _password_column_fits(len(new_hash)):
            db.execute(
                "UPDATE пользователь SET пароль = %s WHERE id_пользователя = %s",
                (new_hash, user_id),
            )
    except db.DatabaseError:
        pass


def authenticate(login: str, password: str) -> Optional[User]:
    row = db.fetch_one(
        """
        SELECT п.id_пользователя, р.название, п.id_клиента, п.id_фотографа,
               CASE
                   WHEN п.id_клиента IS NOT NULL THEN к.ФИО
                   WHEN п.id_фотографа IS NOT NULL THEN ф.ФИО
                   ELSE п.логин
               END AS имя,
               п.пароль
        FROM пользователь п
        JOIN роль р ON п.id_роли = р.id_роли
        LEFT JOIN клиент к ON п.id_клиента = к.id_клиента
        LEFT JOIN фотограф ф ON п.id_фотографа = ф.id_фотографа
        WHERE п.логин = %s AND п.активен = 1
        """,
        (login,),
    )
    if not row:
        return None
    user_id, role, client_id, photographer_id, name, stored = row
    if not verify_password(password, stored or ""):
        return None
    if _is_legacy(stored):
        _upgrade_hash(user_id, password)
    return User(user_id, role, name, client_id, photographer_id)
