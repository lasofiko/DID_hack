# ResearchPlanner и существующий DeepSeek в DID LAB

Соединены MissionManager Искандера и MAIProvider/ResearchPlanner Сони из dev
7a8edb3b92af139063bc2a1f97e5d3cc7246f333. Исходные ML-файлы клиента, настроек,
runtime и планировщика сохранены без переписывания. EnergyModel Марии не изменена.
Локальный HTTP-мок подтверждает цепочку, настоящий ROS/DeepSeek запуск ещё не проверен.

## Как подключается

Compose по умолчанию задаёт:
DID_PLANNER_FACTORY=did_ml.integration:create_llm_planner.

Эта factory возвращает существующий async context manager runtime.llm_planner.
AgentNode при старте миссии в режиме llm входит в него на том же asyncio loop,
где будет вызываться propose. PlannerRuntime сохраняет полученный ResearchPlanner.
MissionManager распознаёт его и использует ResearchBridge из этапа 1.

Провайдер не создаётся в режиме algorithmic. В режиме llm при отсутствии ключа,
ошибке настроек или загрузки factory используется Algorithmic fallback.
Factory и создание клиента не отправляют сетевой запрос: он возникает при propose,
если есть допустимая цель и решение не ограничено обязательным возвратом.

Client переиспользуется в течение жизни узла; новая миссия вызывает reset памяти
ResearchPlanner. При завершении узла сначала отменяется активная миссия/запрос,
затем закрывается async context/client, затем event loop.
Reset web-сессии пересоздаёт ROS-процесс и его клиент.

## Запуск пользователем на доступном Docker/ROS стенде

Из корня интеграционной рабочей копии можно использовать уже существующий .env,
не копируя его в Git. Для текущего компьютера PowerShell:

    docker compose --env-file "C:/Users/Соня/python/PycharmProjects/DID_hack/.env" up -d --build

Эта команда здесь не выполнялась: она собирает и запускает физический стенд.
После запуска открыть http://localhost:3000, дождаться ONLINE, выбрать LLM
и запустить миссию. Это уже может отправить настоящий платный/лимитируемый API-запрос.

Compose передаёт только согласованные DID_LLM_* переменные:
API_KEY, ENDPOINT, MODEL, TIMEOUT, MAX_TOKENS, JSON_MODE, THINKING.
Модель, адрес и авторизация берутся из существующего settings.py и пользовательского
окружения. Содержимое .env агентом не читалось и не копировалось.
Не публиковать полный вывод docker compose config с подставленными секретами.

Для явного offline ResearchPlanner задать перед запуском:
DID_PLANNER_FACTORY=did_ml.integration:create_planner.
Для полного отказа от вызовов модели достаточно режима algorithmic в UI.

Dockerfile устанавливает уже существующие ML-зависимости httpx/python-dotenv
в /opt/did-web и запускает colcon тем же Python, чтобы ROS console entry point
имел доступ к клиенту. Сборку Docker/colcon нужно подтвердить на стенде.

## Тайм-ауты и управление

В configs/agent.json общий planner_timeout увеличен до 12 секунд на одну попытку.
Значение по умолчанию AgentConfig для других пользователей остаётся прежним.
Контекст A* и все вызовы провайдера входят в общий deadline MissionManager.
ResearchBridge делит 80% оставшегося времени между provider_attempts, ограничивает
им исходный provider_timeout, затем восстанавливает настройки даже при отмене.
Это оставляет время на обработку результата и fallback.
Внешний MissionManager может сделать до двух попыток propose.

Робот остановлен во время ожидания. ROS watchdog и запрет движения по stop/pause
сохранены. Обычный stop немедленно запрещает движение; завершение уже ожидаемого
высокоуровневого запроса ограничено deadline. При shutdown запрос отменяется.

После ожидания MissionManager снова проверяет safety, актуальную батарею, collect
и маршрут. LLM управляет только подцелями, не скоростью.

## Контракты, энергия и источники

Observation и Subgoal не расширены. observe/reset/set_context/record_result,
whitelist публичных данных и подтверждение исполнения остаются из этапа 1.
Context содержит до восьми проверенных A*-кандидатов и raw стоимость движения
и поворотов туда/домой. Energy reserve/factor применяются один раз в ML;
backend независимо проверяет безопасность. Judge и скрытые позиции не передаются.
hypothesis_id пока допускается только null на backend.

LLM source публикуется только для принятого source=provider.
Без провайдера, после его ошибки или при принудительном возврате — Algorithmic.
Режим llm и источник конкретного решения — разные поля.

## Журнал

Compose задаёт DID_LLM_JOURNAL_DIR=/workspace/output/ml.
На хосте это experiments/runs/docker/ml/<uuid>.jsonl; каталог исключён из Git.
Существующий JsonlJournal сохраняет config, prompt, response, решение и результат,
с session_id для разных миссий и удалением ключа из записываемых строк.
Отдельный журнал MissionManager остаётся в agent-journal.jsonl.
Ошибки инициализации публикуют только класс исключения, без текста с секретами.

## Проверка этой интеграции

    python scripts/test_stage1.py
    python -m unittest tests.test_llm_mission_runtime -v
    python scripts/check_ros_package.py
    docker compose config --quiet

На Windows перед Python-тестами: $env:PYTHONUTF8="1".
Общий результат: 206 тестов, 200 PASS, 6 SKIP, 0 failures/errors.
Девять новых тестов проверяют существующий HTTP-клиент с MockTransport,
MissionManager, методы ROS-адаптера с fake объектами, повторную миссию,
cancel/cleanup, ошибки 401/429/503, отсутствие ключа и согласованный timeout.
Шесть полных кинематических mission-тестов намеренно пропущены.
Структура ROS-пакета и Compose config прошли проверку.

Настоящие API-запросы, Docker build, colcon build и Gazebo e2e не выполнялись.
Следующая проверка: собрать стенд, подтвердить загрузку клиента в ROS,
выполнить один разрешённый запрос и ограниченную миссию с проверкой stop/reset.
