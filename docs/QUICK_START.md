# Как запустить DID LAB

Проверенный стенд: Mac Apple Silicon ARM64, Docker Desktop, ROS Jazzy,
Gazebo Harmonic с программным EGL/llvmpipe. Все команды выполнять в обычном
терминале macOS из существующего каталога `DID_hack`.
ROS/Gazebo на Mac непосредственно не устанавливаются.

## Первый запуск

```sh
UBUNTU_MIRROR=https://mirror.yandex.ru/ubuntu-ports docker compose up -d --build
```

Сборка занимает больше времени при первом скачивании пакетов. Зеркало применяется
к Ubuntu ARM64; apt-подписи не отключаются. Docker выбирает родную архитектуру.
Контейнер ограничен 8 CPU/7 ГБ, shared memory 512 МБ.

Откройте http://localhost:3000. Интерфейс сначала CONNECTING, затем ONLINE;
статус миссии IDLE, энергия 60. Мир и агент уже работают, движение запрещено
до Start. В EASY выбрать seed (целое 0..2147483647), Baseline или Adaptive,
Planner Algorithmic и нажать Start mission. Сначала backend проверяет реальную
позу робота/odom/base, затем вызывает ROS start. Батарея/координаты/журнал должны
изменяться при физическом движении. Карта доступна без GUI Gazebo.

Pause останавливает миссию, но не время мира. Resume продолжает после проверки
safety. Return to base меняет приоритет на возврат; окончание — только после
подтверждения finish судьёй. Stop прекращает движение. Reset simulator & judge
завершает принадлежащую приложению process group, пересоздаёт мир и судью,
возвращает робот на (-2,-0.5), очищает журнал/траекторию/модель, восстанавливает 60.
Это настоящий reset, а не очистка React state. Для следующего опыта меняйте
сценарий/seed и нажимайте Reset либо Start после терминального результата.

MEDIUM: 5 образцов и 3 зоны затрат. HARD: 7/4 и скрытые изменения;
сбой сенсора может привести к FAILED и нулевым командам. FINISHED означает
безопасный finish, а не обязательный сбор всех образцов: смотрите Delivered.
LLM без factory Сони честно работает как Algorithmic fallback.

## Если сайт/робот не работают

```sh
docker compose logs --tail 100
docker compose exec -T simulation tail -50 /workspace/output/web-runtime.log
docker compose exec -T simulation bash docker/entrypoint.sh ros2 topic list
docker compose exec -T simulation bash docker/entrypoint.sh ros2 topic info /cmd_vel -v
```

В `/cmd_vel` должно быть geometry_msgs/msg/TwistStamped, один publisher did_agent
и subscriber ros_gz_bridge. Нужны потоки `/odom`, `/scan`, `/clock`, `/map`,
`/did/battery`, `/did/sample_sensor`, `/did/agent/state`. Наличие имени topic само
по себе не подтверждает данные; реальный smoke/миссионные пробы делают эту проверку.
При CONNECTING подождать готовности EGL-лидара; при ERROR читать сообщение и
журналы, затем Reset. Не отключайте safety и координатный gate ради старта.
При разрыве связи карта сохраняет последнее измерение и перестаёт двигаться.

## Проверки

```sh
docker compose exec -T simulation bash docker/entrypoint.sh python3 -m unittest discover -s tests
docker compose exec -T simulation bash docker/entrypoint.sh python3 scripts/web_check.py --seed 1 --controls --seconds 650 --output /workspace/output/web-easy-1.json
docker compose exec -T simulation bash docker/entrypoint.sh python3 scripts/web_check.py --seed 2 --seconds 650 --output /workspace/output/web-easy-2.json
```

Пробы **сами пересоздают текущую сессию**; не запускайте их во время ручного
опыта и не запускайте две одновременно. Проверяются HTTP/WS, реальная карта,
сбор/finish, мировая поза только робота, нулевые TwistStamped после завершения.
JSON находится на Mac в `experiments/runs/docker`, этот каталог исключён из Git.
Приватный файл `private-judge-events.jsonl` — только для проверки судьи;
он не доступен из web/API и не передаётся агенту.

```sh
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/check_scenarios.py
.venv/bin/python scripts/check_ros_package.py
```

Эти локальные проверки — unit/ASGI/кинематика, не ROS/Gazebo. Backend-тесты
пропускаются, если FastAPI не установлен в отдельном окружении.

## Выключение

```sh
docker compose down
```

Останавливаются только сервисы данного Compose; Fuel-том и результаты сохраняются.
Нет push, очистки чужих контейнеров или установки системного ROS.

## Ubuntu x86-64 и отдельный ROS запуск

Тот же Dockerfile использует архитектуру будущего сервера. ARM64 ubuntu-ports
зеркало на AMD64 не задавать; режим EGL предусмотрен и там. Runtime Ubuntu AMD64
пока не проверен: это ограничение, а не подтверждённая инструкция эксплуатации.
Отдельный headless ROS launch сохраняется; проверенный вариант указан
в [docker/README.md](../docker/README.md). Не запускайте два Gazebo/судьи рядом
в одном ROS_DOMAIN_ID. GUI Gazebo и режим Xvfb этой web-проверкой не проверялись.
