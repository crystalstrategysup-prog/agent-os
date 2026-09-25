"""Deterministic applicability selection; no checklist requires every format."""

from __future__ import annotations

from .safeio import GateError

TYPES = (
    "general",
    "backend",
    "frontend",
    "mobile",
    "data-ml",
    "platform",
    "embedded",
    "legacy",
)
FEATURES = (
    "http-api",
    "events",
    "database",
    "pii",
    "public",
    "deployment",
    "ui",
    "ml",
    "external-send",
    "safety-critical",
)
# Document ID -> (title, required headings). Alternative tools/formats are in catalog.json.
DOCS = {
    "dossier": (
        "Досье проекта",
        ("Назначение", "Текущее состояние", "Границы", "Ограничения"),
    ),
    "roadmap": ("Дорожная карта", ("Этапы", "Зависимости", "Следующий этап")),
    "stage": (
        "Контракт текущего этапа",
        ("Цель", "Область изменений", "Приёмка", "Откат"),
    ),
    "quality": ("Стратегия проверок", ("Проверки", "Доказательства", "Ограничения")),
    "architecture": (
        "Архитектура",
        ("Контекст", "Компоненты", "Границы доверия", "Решения"),
    ),
    "requirements": (
        "Требования",
        ("Функции", "Нефункциональные требования", "Правила"),
    ),
    "contracts": (
        "Интерфейсы и контракты",
        ("Интерфейсы", "Схемы", "Совместимость", "Ошибки"),
    ),
    "http-api": ("HTTP API", ("Операции", "Авторизация", "OpenAPI", "Версионирование")),
    "events": (
        "Событийные контракты",
        ("Каналы", "Схемы", "Доставка", "Совместимость"),
    ),
    "data": ("Модель данных", ("Сущности", "Хранение", "Миграции", "Удаление")),
    "security": ("Безопасность", ("Активы", "Угрозы", "Полномочия", "Секреты")),
    "privacy": ("Персональные данные", ("Категории", "Основания", "Сроки", "Доступ")),
    "operations": (
        "Эксплуатация",
        ("Установка", "Проверка", "Обновление", "Откат", "Восстановление"),
    ),
    "release": ("Выпуск", ("Версии", "Состав", "Проверки", "Публикация")),
    "onboarding": (
        "Онбординг разработчика",
        ("Начало", "Навигация", "Команды", "Неисправности"),
    ),
    "ux": (
        "Пользовательские сценарии",
        ("Пользователи", "Сценарии", "Доступность", "Приёмка"),
    ),
    "model-card": (
        "Модель и данные ML",
        ("Назначение", "Данные", "Оценка", "Ограничения"),
    ),
    "safety": (
        "Анализ безопасности эксплуатации",
        ("Опасности", "Контроли", "Проверка", "Ответственность"),
    ),
    "incident": ("Разбор инцидента", ("Влияние", "Хронология", "Причина", "Меры")),
}
BASE = {"dossier", "roadmap", "stage", "quality"}
TYPE_DOCS = {
    "general": set(),
    "backend": {"architecture", "contracts", "security"},
    "frontend": {"requirements", "architecture", "ux"},
    "mobile": {"requirements", "architecture", "ux", "release"},
    "data-ml": {"requirements", "data", "model-card"},
    "platform": {"architecture", "contracts", "security", "operations", "onboarding"},
    "embedded": {"requirements", "architecture", "contracts", "operations"},
    "legacy": {
        "requirements",
        "architecture",
        "contracts",
        "data",
        "operations",
        "onboarding",
    },
}
FEATURE_DOCS = {
    "http-api": {"http-api", "contracts", "security"},
    "events": {"events", "contracts"},
    "database": {"data"},
    "pii": {"privacy", "security", "data"},
    "public": {"release", "security", "onboarding"},
    "deployment": {"operations", "release"},
    "ui": {"ux"},
    "ml": {"model-card", "data"},
    "external-send": {"security", "contracts"},
    "safety-critical": {"safety", "security"},
}


def select(
    types: list[str], features: list[str], change_kind: str = "implementation"
) -> dict:
    if not types or any(t not in TYPES for t in types):
        raise GateError("unknown_project_type")
    if any(f not in FEATURES for f in features):
        raise GateError("unknown_project_feature")
    reasons = {d: ["every_project"] for d in BASE}
    for typ in types:
        for d in TYPE_DOCS[typ]:
            reasons.setdefault(d, []).append("type:" + typ)
    for feature in features:
        for d in FEATURE_DOCS[feature]:
            reasons.setdefault(d, []).append("feature:" + feature)
    if change_kind == "incident":
        reasons["incident"] = ["change:incident"]
    return {
        "schema": "agentos.docs-selection/v1",
        "required": sorted(reasons),
        "reasons": reasons,
        "not_applicable": sorted(set(DOCS) - set(reasons)),
    }
