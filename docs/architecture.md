# Архитектура

Один агент. Основной исполняемый поток:

```text
/odom, /scan, /clock, /did/battery, /did/sample_sensor
  → RobotState → SafetyManager
  → MissionManager → SampleSearch или внешний Planner
  → валидация цели и энергии → NavigationPlanner (A*)
  → WaypointNavigator → MotionController → /cmd_vel (TwistStamped)
  → TurtleBot3 в Gazebo → новые наблюдения
```

MissionManager использует существующие Observation, Subgoal, Result и
MissionState из did_core; сохраняются статусы idle/running/paused/returning/
finished/stopped/failed. Внутренние действия различаются по goal.action.
ReturnToBase строит маршрут до базы, BatteryManager оценивает его стоимость с
резервом. SafetyManager и ROS watchdog останавливают движение независимо от LLM.
Часы свежести используют и sim_time источника, и монотонное время получения.

NavigationPlanner запрещает неизвестные/занятые клетки, расширяет препятствия
под габариты робота, не допускает срезания диагональных углов. Карта статическая;
измеренное препятствие останавливает движение. Без bearing оно не наносится
в карту; гарантированного объезда динамического препятствия пока нет.
Полноценные SLAM, Nav2 navigation stack и динамическая costmap не реализованы.
Используются только Nav2 map_server и lifecycle_manager для публикации /map.

SampleSearch получает только карту и публичный сигнал. Сглаживает несколько
измерений, оценивает локальный градиент по истории, исследует непосещённые точки.
Истинные координаты образцов живут только у mock-судьи. AgentNode не импортирует
MockJudge и не загружает сценарий с координатами.

MockJudge — отдельная opt-in среда с собственными правилами энергии/датчика/счёта.
ROS-судья самостоятельно читает odom и использует явно заданное преобразование;
это приближение истинной позы для mock, не независимый датчик ground truth Gazebo.
Безопасность отделена от высокого уровня: /clock может остановиться, а steady
watchdog всё равно обнулит устаревшую команду.

LLM подключается через Planner.propose: не более двух попыток с timeout,
валидация Subgoal, затем алгоритмический fallback. Algorithmic вообще не
вызывает внешний Planner; LLM отображается как источник только после принятого
ответа. Реального внешнего клиента пока нет. Adaptive EnergyObserver обновляет
наблюдаемые локальные стоимости и A*, не получает истинные параметры грунтов.
Консервативный BatteryManager независимо ограничивает риск расхода энергии.

Frontend → FastAPI HTTP/WS → ROS services и публичные topics. RosRuntime
владеет одним дочерним launch; lifecycle/reset описан ниже.
Владельцы модулей и общие единицы: [team](team.md).

В проверенном Docker headless-режиме TF связно: map → odom → base_footprint
→ base_link → base_scan. Начальное map→odom берётся из config_file; это
фиксированное преобразование, не SLAM. После измеренного дрейфа odom около
11 см запас планирования увеличен до 0.35 м. У угла Navigator уточняет waypoint
до 0.2 × resolution, если его обычный пропуск даёт небезопасный следующий отрезок.
Генерация mock-сцены использует независимый фиксированный clearance 0.20 м.
Критерии runtime-проверки и ограничения: [validation](validation.md).

## Web и сценарии

React/TypeScript рисует публичную OccupancyGrid, реальную odom-траекторию и
оценки EnergyObserver. FastAPI и ROS-мост работают в том же контейнере; DDS не
пробрасывается на Mac. PublicCache получает только агентские state/journal/knowledge,
публичные odom/map/clock/scan и whitelist счёта/уже произошедших событий судьи.
Нет прямого обращения backend к private scene generator.

Backend владеет только собственным `ros2 launch`: reset завершает его process group
и запускает новый headless мир/agent/judge с проверенными scenario/seed/mode.
API не принимает shell/Docker-команды, Docker socket не монтируется.
Миссия стартует только после проверки мировой позы робота и открытия координатного
gate. HTTP-команда не ждёт окончания Navigator.follow, WS выдаёт данные 4 Гц.

EASY 3/1, MEDIUM 5/3, HARD 7/4: изменения знает только отдельный судья.
Nan-сигнал и реальный hazard_hit проходят прежнюю safety-проверку и вызывают нули.
ObservedEnergyModel хранит измеренные затраты, обновляет веса A* и журнал
исследовательского цикла. Геометрия true грунтов в слой карты не передаётся.
LLM/EnergyModel команды подключаются factory из did_ml, модуль участников не менялся.
Публичные контракты: [API](api.md). Подключение команды:
[Planner](LLM_INTEGRATION.md), [EnergyModel](ENERGY_INTEGRATION.md).
Проверки и границы применимости: [validation](validation.md).
