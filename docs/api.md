# Контракт frontend ↔ backend

FastAPI обслуживает React и ROS-мост из одного контейнера. Старые форматы
Observation/Subgoal/MissionState сохранены. Дополнительная телеметрия описана
в `packages/contracts/did_core/web.py`.

Внутренний контракт энергии расширен для угла поворотов: EnergyMeasurement.angle_rad,
TurnEnergyMeasurement и TurnCostEstimate. Это не поля HTTP/WS или Observation.
Адаптер должен разделять прямое движение и повороты на месте, получать угол
из реальной ориентации робота. Инструкция: docs/energy.md.

| Метод / путь | Вход | Ответ |
|---|---|---|
| GET /api/health | — | 200: `{"status":"ok"}`, независимо от ROS |
| POST /api/missions | StartRequest | 201: MissionState |
| POST /api/missions/command | `{"command":"pause"}` | 200: MissionState |
| POST /api/command | тот же запрос | совместимый краткий путь |
| POST /api/missions/reset | StartRequest | 200: idle MissionState после нового ROS/Gazebo/судьи |
| GET /api/state | — | MissionState, observation=null при отсутствии данных |
| GET /api/journal | — | публичные записи текущей миссии, старые → новые |
| GET /api/scenarios | — | только количество образцов/зон и наличие изменений |
| GET /api/map | — | публичная OccupancyGrid, 503 если ещё нет |
| GET /api/trajectory | — | реально наблюдавшиеся точки map/метры |
| WS /api/telemetry | — | полный публичный снимок сразу, затем 4 Гц |

```json
{"scenario":"easy","seed":1,"mode":"adaptive","planner_mode":"algorithmic"}
```

scenario/mode/seed обязательны; seed — строго целое 0..2147483647, bool не
принимается. scenario easy/medium/hard, mode baseline/adaptive.
Дополнительный planner_mode algorithmic/llm по умолчанию algorithmic.
Лишние поля отклоняются. Ни команды shell, ни Docker-параметры не принимаются.

WS сохраняет поля MissionState на верхнем уровне для старого клиента и также
передаёт state, session, connection, robot_pose, robot_yaw, trajectory,
planned_path, knowledge, journal, events, planner_source, collected_positions,
score, map_revision, error. connection: online/connecting/error; browser также
показывает offline при разрыве WS или >2с без сообщения. online требует свежих
odom, scan, advancing clock, state и карты. robot_yaw в радианах, точки в
map/метрах. Растр карты не дублируется четыре раза в секунду.

MapData: width/height/resolution/origin/origin_yaw/data/revision. data — ROS
row-major, строка 0 соответствует нижней части карты; frontend переворачивает
растр при рисовании и применяет поворот origin. Occupancy/trajectory — публичные
данные; knowledge — измеренные оценки плиток 0.5м, uncertainty=null для неизвестной
уверенности. Позиции collected_positions — положение робота при подтверждённом
сборе, **не истинные координаты скрытого образца**. events содержат только уже
произошедшие sample_collected/false_collect/hazard_hit/collision без скрытой
геометрии. Score фильтруется по whitelist. Приватный журнал судьи не обслуживается
HTTP и не публикуется ROS.

start разрешён из idle/finished/stopped/failed; после терминального состояния или
изменения сценария сначала пересоздаётся собственный дочерний launch. Backend
проверяет мировую позу только робота через Gazebo transport, сравнивает её с map/odom
и базой, открывает coordinates_verified, вызывает agent/start и запускает эпоху
mock/start только после принятия старта. Ошибка старта останавливает агент и
требует новой сессии при следующей попытке. Изменяющие запросы API сериализованы.
Миссия не стартует автоматически при запуске сайта.

pause: running/returning → paused; resume: paused → прежний статус с safety;
return: running/paused/returning → returning; stop: эти же статусы → stopped.
409 — команда недоступна/миссия активна; 422 — неверный запрос;
503 — ROS/sensors/service/gate недоступны; 504 — timeout операции.
Ответ означает принятие команды, завершение движения отслеживается телеметрией.
Reset завершает только принадлежащую backend process group и запускает новую;
Docker socket и произвольные subprocess-команды через API отсутствуют.

Движение всегда контролирует агент и steady-clock watchdog. Потеря телеметрии
не создаёт движение в UI: последнее измеренное положение сохраняется.
Статусы finished с нулевой/неполной доставкой не означают сбор всех образцов.
