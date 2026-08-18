"""User-facing warnings and standing disclaimers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

STALE_AFTER_DAYS = 90

MAPPING_DISCLAIMER = (
    "Проекция на 1С:Бухгалтерия предприятия 3.0 - экспертная интерпретация "
    "разработчиков сервера, а не норма стандарта. Проверяйте по тексту пункта."
)

NO_MAPPING_MESSAGE = (
    "Проекция на конфигурацию 1С для этого стандарта пока не заполнена. "
    "Отсутствие записей не означает, что стандарт не реализован в конфигурации."
)

# Says something different from MAPPING_DISCLAIMER, on purpose: MAPPING_DISCLAIMER
# says "this is an interpretation, not the norm itself"; this one says "and nobody
# has checked whether the interpretation is even correct yet". Both travel together -
# neither replaces the other.
UNVERIFIED_MAPPING_WARNING = (
    "Хотя бы одна из показанных строк не проверена человеком-экспертом и "
    "приведена как черновик. Не полагайтесь на нее без проверки по тексту "
    "пункта и по конфигурации."
)


def verification_warning(rows: Iterable[bool]) -> list[str]:
    """Return a one-item warning list when any `rows` entry (a row's `verified`) is False.

    Empty when every row is verified, and empty when `rows` is empty - an empty
    result set makes no claim about a projection, so there is nothing to warn about.
    """
    if any(not verified for verified in rows):
        return [UNVERIFIED_MAPPING_WARNING]
    return []


def corpus_warnings(built_at: date, today: date) -> list[str]:
    """Return warnings to attach to every response for a stale corpus."""
    age_days = (today - built_at).days
    if age_days <= STALE_AFTER_DAYS:
        return []
    return [
        (
            f"Корпус собран {built_at.strftime('%d.%m.%Y')} ({age_days} дн. назад). "
            "Возможно, появились новые приказы Минфина. Требуется пересборка корпуса."
        )
    ]
