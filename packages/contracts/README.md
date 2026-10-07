# Contracts — общая договорённость команды

- did_core/types.py — форматы данных (TypedDict).
- did_core/ports.py — подписи будущих реализаций (Protocol).

Это не рабочая логика и не runtime-валидация. Импорт: from did_core.types import Observation.
Единицы, ошибки, владельцы: ../../docs/team.md. HTTP/WS: ../../docs/api.md.
Менять формат согласованно с владельцами затронутых модулей.
