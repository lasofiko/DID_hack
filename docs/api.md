# Контракт frontend ↔ backend (план реализации)

Сейчас работает **только GET /api/health**. Остальные маршруты ниже предстоит
написать; фронт может временно использовать локальные моки с этими форматами.
Python-форматы — packages/contracts/did_core/types.py.

| Метод / путь | Вход | Ответ |
|---|---|---|
| GET /api/health | — | 200: `{"status":"ok"}` |
| POST /api/missions | StartRequest | 201: MissionState |
| POST /api/missions/command | `{"command":"pause"}` | 200: MissionState |
| GET /api/state | — | 200: MissionState |
| GET /api/journal | — | 200: массив JournalEntry текущей миссии, от старых к новым |
| WS /api/telemetry | — | MissionState сразу при подключении, затем 4 раза/сек |

StartRequest:

```json
{"scenario":"easy","seed":1,"mode":"baseline"}
```

scenario: easy/medium/hard; mode: baseline/adaptive; seed: целое число
от 0 до 2147483647. Все три поля обязательны.

Начальное MissionState:

```json
{
  "run_id": null,
  "status": "idle",
  "observation": null,
  "goal": null,
  "collected": 0,
  "delivered": 0
}
```

Поля Observation, Subgoal и JournalEntry строго соответствуют types.py.
run_id после старта — непрозрачная строка; при новой миссии меняется.
Все JSON-числа конечны, NaN/Infinity запрещены. Скрытые цели и будущие
события не публикуются. Карта и траектория — отдельный будущий контракт,
сначала согласовать его с Искандером, не добавлять произвольные поля в Observation.

## Команды и ошибки

- start разрешён из idle/finished/stopped/failed. Одновременно одна миссия.
- pause: running/returning → paused, движение останавливается.
- resume: paused → прежнее состояние после повторной проверки безопасности.
- return: running/paused/returning → returning, перепланирование до базы.
- stop: running/paused/returning → stopped, движение останавливается.
- В остальных состояниях команда возвращает 409, формат
  `{"detail":"Команда недоступна в текущем состоянии"}`.
- 422 — неверные входные данные (стандартный detail FastAPI).
- 503 — исполнитель/ROS недоступен: `{"detail":"ROS недоступен"}`.

Повторный start активной миссии отклоняется, не сбрасывает её. Ответ команды
означает принятие команды, не завершение движения. Завершение отслеживать по
MissionState. При потере WS фронт помечает данные устаревшими и выключает
команды; после переподключения получает полный актуальный снимок.
Backend не должен блокировать HTTP на всё время Navigator.follow.
