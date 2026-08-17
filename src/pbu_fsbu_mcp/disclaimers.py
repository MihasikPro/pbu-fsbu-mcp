"""User-facing warnings and standing disclaimers."""

from __future__ import annotations

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
