# Backend — Искандер

FastAPI предоставляет HTTP API и WebSocket телеметрию. RosRuntime получает
публичные ROS-потоки, вызывает сервисы агента и владеет одним дочерним launch.
Reset пересоздаёт собственный мир/агента/mock-судью. Изменяющие запросы
сериализованы; произвольные shell-команды и Docker socket через API недоступны.

Контракты: [API](../../docs/api.md), Python MissionControl в did_core/ports.py.
Запуск: [QUICK_START](../../docs/QUICK_START.md). Без ROS доступны health и
диагностическое состояние, операции миссии возвращают явную ошибку.
Навигация и LLM выполняются агентом; backend не получает приватные цели судьи.
Владельцы модулей: [team](../../docs/team.md).
