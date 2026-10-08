# Проверка стенда и известные ограничения

Процедуры приёмки и границы совместимости DID LAB. Подробные локальные журналы
не входят в Git. Команды выполнять из корня проекта; запуск:
[QUICK_START](QUICK_START.md).

## Совместимость

Контрольная версия проверена 8 октября 2026 в Docker Desktop Linux ARM64
на Apple Silicon: ROS 2 Jazzy, Gazebo Harmonic 8.15.0, TurtleBot3 Gazebo 2.3.7,
Python 3.12, OGRE2/EGL/Mesa llvmpipe. did_robot собирается colcon, frontend —
Node 22. Системные ROS/Gazebo на Mac не требуются. Ubuntu AMD64 предусмотрен
нативным Dockerfile, но runtime x86-64 не проверен. GUI/Xvfb не входит в
подтверждённый headless-режим.

GPU-лидар требует рендеринг даже без GUI. Если нет scan, проверяйте EGL/OGRE2
в логах, не отключайте freshness. При недоступном ports.ubuntu.com на ARM64
использовалось https://mirror.yandex.ru/ubuntu-ports с проверкой apt-подписей.
На AMD64 ubuntu-ports зеркало не задавать.

## Уровни проверки

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_ros_package.py
.venv/bin/python scripts/check_scenarios.py
.venv/bin/python scripts/audit_seeds.py
```

Unit/ASGI проверяют алгоритмы, safety, API/WS и privacy. Кинематика имитирует
входы агента, не подтверждает физическую навигацию/DDS. JSON генераторов
записывается в experiments/runs. Backend-тесты выполнять с FastAPI:
без него они пропускаются. Проектное окружение требует Python 3.12+.

```sh
docker compose exec -T simulation bash docker/entrypoint.sh python3 -m unittest discover -s tests
docker compose exec -T simulation bash docker/entrypoint.sh python3 scripts/web_check.py --seed 1 --controls --seconds 650 --output /workspace/output/web-easy-1.json
docker compose exec -T simulation bash docker/entrypoint.sh python3 scripts/web_check.py --seed 2 --seconds 650 --output /workspace/output/web-easy-2.json
docker compose exec -T simulation bash docker/entrypoint.sh python3 scripts/web_check.py --scenario medium --seed 1 --mode adaptive --seconds 650 --output /workspace/output/web-medium-1.json
docker compose exec -T simulation bash docker/entrypoint.sh python3 scripts/web_check.py --scenario hard --seed 2 --mode adaptive --seconds 130 --expect-safe-failure --output /workspace/output/web-hard-2.json
```

Пробы **пересоздают сессию**. Запускать по одной, без ручного опыта одновременно.
Доставка требует finished, delivered>0, физической базы <0.18 м и устойчивых
нулей TwistStamped. HARD expect-safe-failure проверяет отказ, а не доставку.
Private журнал судьи нужен только для проверки среды, через API недоступен.

## Независимая проверка движения и TF

Выключить web-стенд и оставить один свежий мир без управляющего агента:

```sh
docker compose down
docker compose run --rm --no-deps --name did-hack-smoke simulation ros2 launch did_robot easy.launch.py headless:=true mock_judge:=true start_agent:=false
```

Во втором терминале:

```sh
docker exec -i did-hack-smoke bash docker/entrypoint.sh python3 scripts/ros_smoke.py --move
```

Требуются реальные /odom, /scan, /clock, geometry_msgs/msg/TwistStamped,
map→odom→base_footprint→base_link→base_scan и составной tf lookup. Имени топика
недостаточно. dynamic_pose используется диагностикой/стартовым gate только
для позы **робота**, не как вход агента. Scene/info кеширует исходную сцену.
Нельзя одновременно управлять роботом из smoke и автономным агентом.

Для отрицательной clock-пробы нужен другой свежий standalone launch с
start_agent=true, autostart=false, coordinates_verified=false. Скрипт
ros_clock_safety.py проверяет стартовые координаты, запускает миссию,
замораживает физику и требует нулей steady watchdog, затем снимает паузу.
Не запускать против web-сессии или рядом со вторым судьёй/публикатором скорости.
После диагностики завершить launch через Ctrl+C и восстановить Compose.

TF static subscriber должен иметь transient history и ждать всю цепь/lookup,
а не завершаться по первым sensor packets. Offset проверять неподвижно:
CLI на движущемся роботе смешивает моменты времени.

## Измерения контрольной версии

Исторические результаты этой реализации, не гарантия любого seed:

| Проверка | Полученный результат |
|---|---|
| Unit/ASGI на Mac и Linux ARM64 | 81 тест прошёл в каждом окружении |
| Кинематика | 18 сочетаний 3 сценария × 2 режима × seed1/2/7; отказы HARD отдельно |
| EASY audit_seeds на поставляемой карте, seed1..10 | 8/10 доставили образец; seed7/8 finished с delivered=0, battery=43.5667/43.6537, collisions=0; скрипт правильно завершился с кодом 1 |
| Независимый smoke | 360 лучей; физическое движение 0.2374963 м, odom 0.23727 м; стартовый world/map error 0.0142317 м; TF lookup успешен |
| EASY baseline seed1 | finished, delivered=2/3, battery=37.18979, физическая база 0.070061 м; Pause/Resume проверены |
| EASY baseline seed2 | finished, delivered=1/3, battery=40.05676, физическая база 0.117234 м |
| MEDIUM adaptive seed1, два прогона | finished, 2/5 в обоих; батарея 42.95209/42.71129, физическая база 0.113315/0.137208 м |
| Финальная адаптация MEDIUM | 14 плиток, оценки 1..3.33363; восемь интервалов hypothesis/experiment до observation; A* replan; 61 нулевая команда после finish |
| HARD adaptive seed2 | collected=1, delivered=0, failed/STALE_DATA, battery=54.17863; устойчивые нули, **не успех миссии** |
| Браузер | Реальные Start/Pause/Resume/Return/Stop/Reset; offline замораживает позу; WS около 3.98 Гц; LLM без factory даёт Algorithmic fallback |
| Выключение во время движения | Пять финальных нулевых TwistStamped; физическое торможение после уничтожения мира не измерялось |

Ранние goal_samples=1 прогоны относятся к другой конфигурации, не доказывают
сбор 3/5/7. Дополнительный физический EASY seed1 остановился BLOCKED без доставки;
повторяемость ограничена, такой прогон не засчитывается успешным.
Дополнительный audit_seeds при ревизии документации не прошёл критерий
доставки для seed7/8. Это отдельная алгоритмическая приёмка, а не падение
81 unit/ASGI-тестов; её не следует объявлять полностью успешной или ослаблять
assertion ради зелёного результата. Подробные результаты остаются локальными.

## Safety и диагностика отказов

- Freshness использует sim stamp и monotonic wall receipt. Независимые DDS
  потоки допускают до 100 мс опережения stamp; большие future stamps, старые
  пакеты и frozen clock блокируют движение.
- Frames: odom/base_footprint и base_scan. Неверные frames, NaN/unknown lidar
  и quaternion снимают старое наблюдение. Скорости приводятся к float;
  невалидные/просроченные команды заменяются нулём.
- Emergency не очищается Start. Collision/hazard_hit защёлкивают остановку:
  устранить причину, затем Reset. Sensor failure даёт консервативный отказ.
- Navigator проверяет фактический отрезок и уточняет waypoint до 0.2×resolution,
  если обычный допуск пропускает безопасный поворот; A* не срезает углы.
- BatteryManager копит смещение до измеримого интервала и проверяет запас
  до движения и по пути. Неопределённый collect/finish после timeout нельзя
  повторять: запрос мог выполниться; требуется новая сессия.
- Backend сохраняет сигналы Uvicorn, завершает только собственный launch,
  сериализует Start/Reset. Ошибка старта требует reset; эпоха HARD начинается
  после принятого старта агента.
- Публичные score/event/knowledge фильтруются по типам/whitelist. Внешний
  planner exception публикуется как класс ошибки, без потенциальных секретов.

## Ограничения

Нет SLAM/коррекции odometry drift. Стартовый map→odom offset не исправляет
скольжение колёс. Измеренный drift около 0.11 м потребовал clearance=0.35 м;
поздняя движущаяся диагностика дала расхождение 0.2713 м, которое без синхронизации
не является чистой метрикой локализации. Не ослаблять safety/gate ради демо.
Mock generator имеет независимый clearance=0.20 м.

Препятствия без bearing не наносятся в карту; гарантированного динамического
объезда нет. Mock-судья использует самостоятельный odom→map, не независимый
physical ground truth/официальный скоринг. Зоны/hazard и сбой сигнала — правила
mock, а не изменение трения Gazebo. Пороги interest=0.25/collect=0.78 откалиброваны
на этом сигнале, официальный датчик потребует отдельной проверки.

Полный сбор 3/5/7 и успешная HARD-доставка не подтверждены. Оценки энергии
предварительные; смешанный грунт не разделяется точно одним измерением;
преимущество adaptive над baseline не доказано. Реальные клиенты Сони/Марии
и официальный судья отсутствуют: [Planner](LLM_INTEGRATION.md),
[EnergyModel](ENERGY_INTEGRATION.md). Повторяйте процедуры для новой версии,
сохраняйте локальные receipts с scenario/seed/config.
