# Agent

Реализованы RobotState, MissionManager (MissionControl), NavigationPlanner (A*),
MotionController, SafetyManager, SampleSearch, BatteryManager и ReturnToBase.
WaypointNavigator исполняет путь асинхронно через внедрённую публикацию скоростей.
Форматы данных сохраняются из did_core; ROS-зависимостей в ядре нет.

Алгоритмический EASY/baseline работает без LLM. Planner можно внедрить в
MissionManager: timeout, две попытки, валидация и fallback уже предусмотрены.
Скрытые координаты запрещены на входе агента. Проверки: из корня
`python -m unittest discover -s tests -v` и `python scripts/demo_easy.py`.
Подробности: [архитектура](../../docs/architecture.md) и
[проверки/ограничения](../../docs/validation.md).

В текущем этапе добавлены adaptive EnergyObserver и команды трёх сценариев.
A* обновляется по измеренному расходу, Model не получает истинный грунт.
Planner mode algorithmic/llm — внутри того же MissionManager; внешний Planner
валидируется, две попытки с timeout и Algorithmic fallback.
Порты команды сохранены: [LLM](../../docs/LLM_INTEGRATION.md),
[EnergyModel](../../docs/ENERGY_INTEGRATION.md).
Результаты доставки различаются между seed/режимами; безопасность возврата
приоритетнее сбора всех образцов. Сбой сигнала HARD приводит к безопасному отказу.
