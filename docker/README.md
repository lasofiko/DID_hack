# Контейнер ROS/Gazebo + web

Основной запуск и проверенные команды — [QUICK_START](../docs/QUICK_START.md).
Compose запускает FastAPI с React; backend владеет ровно одним дочерним
headless ROS/Gazebo launch. DDS находится внутри одного контейнера, поэтому
не требуется проброс ROS multicast между Mac и Linux. Docker socket не монтируется.
Порт привязан к 127.0.0.1:3000, сервис не публикуется в локальную сеть.

Dockerfile собирает React в отдельном Node 22 этапе. ROS/Gazebo/TurtleBot3
устанавливаются нативно; FastAPI/Uvicorn/WebSockets находятся в изолированном
venv с system-site-packages для ROS Python. Colcon устанавливает существующие
did_agent/did_core/did_environment в did_robot; никаких новых репозиториев.

Headless OGRE2/EGL использует Mesa llvmpipe. GPU-лидар требует рендеринг,
несмотря на отсутствие окна Gazebo. Fuel-модели остаются в named volume.
Поддержка Xvfb сохранена, но этот резервный режим не проверен в текущем этапе.

## Отдельный headless ROS без сайта

Сначала выключить web-стенд, затем запустить ровно один контейнер:

```sh
docker compose down
docker compose run --rm --no-deps simulation ros2 launch did_robot easy.launch.py headless:=true mock_judge:=true start_agent:=false
```

Мир/odom/scan/clock работают; агент отключён для независимой smoke-пробы.
Процесс остаётся в терминале, Ctrl+C завершает его. `run` не публикует web-порт.
Не запускать одновременно с web-стендом. Для автоматического управления
предпочтителен основной web запуск и его проверка координат перед start.

Сохраняется обычный launch с start_agent=true и координатным gate; для подключения
официального судьи mock_judge=false. Текущая web-сессия явно использует локальный
mock и не заявляется интеграцией с официальным судьёй.

ARM64 проверен на Mac; AMD64 предусмотрен нативной сборкой, runtime не испытан.
Проверки датчиков/TF/рендера, критерии миссии и известные ограничения:
[validation](../docs/validation.md).
