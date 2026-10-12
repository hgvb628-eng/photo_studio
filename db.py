"""Работа с MySQL: все запросы идут с параметрами (защита от SQL-инъекций)."""
from contextlib import contextmanager

import mysql.connector

from config import DB_CONFIG


class DatabaseError(Exception):
    """Ошибка базы данных с понятным текстом для пользователя."""


@contextmanager
def connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as exc:
        raise DatabaseError(f"Не удалось подключиться к БД: {exc}") from exc
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(sql, params=None):
    """SELECT: вернуть все строки. Если передаёшь params, символ % в SQL пиши как %%."""
    try:
        with connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                return cursor.fetchall()
            finally:
                cursor.close()
    except mysql.connector.Error as exc:
        raise DatabaseError(f"Ошибка запроса: {exc}") from exc


def fetch_one(sql, params=None):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    """INSERT/UPDATE/DELETE с коммитом. Возвращает id последней вставленной записи."""
    try:
        with connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                conn.commit()
                return cursor.lastrowid
            except mysql.connector.Error:
                conn.rollback()
                raise
            finally:
                cursor.close()
    except mysql.connector.Error as exc:
        raise DatabaseError(f"Не удалось выполнить операцию: {exc}") from exc
