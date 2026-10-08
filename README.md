# DID LAB — автономный исследователь

Один агент TurtleBot3 Burger: React/TypeScript → FastAPI → ROS 2 Jazzy →
Gazebo Harmonic. Headless Gazebo, настоящие odom/lidar/TF, команды TwistStamped;
сигнал образцов, батарея, сбор и finish — отдельный **локальный mock-судья**.
Системный ROS/Python macOS не нужны. Работа ведётся в существующей ветке night-mvp.

```sh
# Терминал на Mac, каталог DID_hack. Проверенное ARM64-зеркало Ubuntu:
UBUNTU_MIRROR=https://mirror.yandex.ru/ubuntu-ports docker compose up -d --build
```

Открыть **http://localhost:3000**. Дождаться ONLINE / IDLE, выбрать EASY и seed,
нажать Start mission. Start/Pause/Resume/Return/Stop вызывают реальные ROS services;
Reset пересоздаёт собственный Gazebo/ROS launch и mock-судью. Без Start робот
остаётся неподвижным. На карте показаны измеренная траектория, цель и маршрут;
в adaptive — наблюдаемые оценки затрат. Скрытых образцов/грунтов/будущих событий нет.

```sh
docker compose logs --tail 100
docker compose exec -T simulation bash docker/entrypoint.sh ros2 topic info /cmd_vel -v
docker compose exec -T simulation bash docker/entrypoint.sh python3 -m unittest discover -s tests
docker compose down
```

[Пошаговый запуск на русском](docs/QUICK_START.md),
[проверки и ограничения](docs/validation.md),
[архитектура](docs/architecture.md).

EASY содержит 3 образца/1 зону; MEDIUM — 5/3, без изменений;
HARD — 7/4 и приватные изменения стоимости, опасность и сбой сигнала.
Количество в интерфейсе — количество в среде, не обещание полной доставки.
Safety/батарея могут вызвать ранний возврат; HARD может закончиться безопасным
отказом при недостоверном датчике. Алгоритмическая и адаптивная стратегии работают
в одном агенте. Настоящий LLM пока не подключён: предусмотрен ограниченный fallback.

[Контракт API](docs/api.md), [подключение Сони](docs/LLM_INTEGRATION.md),
[подключение Марии](docs/ENERGY_INTEGRATION.md). Их модуль `packages/ml/did_ml`
не переписан; командные договорённости `docs/team.md` сохранены.

```sh
# Алгоритмические проверки в уже существующем Python 3.12 окружении:
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/check_scenarios.py
.venv/bin/python scripts/check_ros_package.py
```

Локальные результаты проверок сохраняются в `experiments/runs/` и исключены из Git.
Unit/кинематика и физические Gazebo-прогоны описаны отдельно в
[документации проверки](docs/validation.md). Запуск на Ubuntu x86-64 предусмотрен
нативной сборкой того же Dockerfile, но пока не проверен на сервере.
