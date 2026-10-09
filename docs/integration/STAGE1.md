# DID Hack — отчёт безопасной интеграции, этап 1

Дата: 8 октября 2026. Локальная интеграция для review; не подтверждение готовности
физического стенда или сквозного DeepSeek. Новая сеть к модели не использовалась.

## 1. Git и исходное состояние

Remote: https://github.com/lasofiko/DID_hack.git.
Первоначальная рабочая копия: C:/Users/Соня/python/PycharmProjects/DID_hack,
ветка dev с незакоммиченными ML-изменениями. Она сохранена; SHA-256 каждого
зафиксированного в исходном манифесте локального файла повторно проверен.

| Ссылка после безопасного fetch | SHA |
|---|---|
| dev и origin/dev | c251583ce4d4e8af54e298da0106ccb5bc9486fe |
| origin/night-mvp | 84f03cc94371086c119a2c8812ee75f93d6c6665 |
| origin/codex/maria-energy-integration | 63c72242977ea2075d833e164d7ea85a57257301 |
| main / origin/main | 54601e146bb4d260461cece99b538d7601c2b082 |
| merge-base dev / energy-integration | 54601e146bb4d260461cece99b538d7601c2b082 |

PR #3 проверен через GitHub: Draft, energy-integration → dev.
https://github.com/lasofiko/DID_hack/pull/3
Исторический SHA совпал с fetch, а не был принят на веру.
Проверены status, branches, граф истории, worktrees, diff и merge-base.
Признаков незавершённого merge/rebase/index.lock при аудите не найдено.
Чужие процессы на других компьютерах проверить невозможно.

Новая ветка: feature/system-integration, от актуального origin/dev.
Worktree:
C:/Users/Соня/.codex/visualizations/2026/10/07/01a11692-8146-7383-a698-f8484f66504a/system-integration

Перенос выполнен по проверенному списку отличий источника от merge-base,
с сохранением локального ML и отдельным разрешением пересечений. Git merge/rebase
не использовались. Ни main, dev, night-mvp, ни источник PR не передвигались.
Fetch обновил только remote-tracking metadata. Push и изменение PR не выполнялись.
Текущий HEAD: c251583ce4d4e8af54e298da0106ccb5bc9486fe.
Новых локальных коммитов нет: запрос на git commit был отклонён пользователем,
повтор не выполнялся. 126 файлов интеграции добавлены в индекс; последняя правка
этого отчёта о запрете коммита остаётся в рабочем дереве. Дерево намеренно не чистое.
Проверенные изменения доступны для review и последующего ручного коммита.

## 2. Пересечения и решения

Актуальные списки: overlap.json. Это пересечения изменений относительно общего
предка; merge с конфликтными маркерами не запускался.

| Файл | Что пересекалось | Решение и сохранённые стороны |
|---|---|---|
| README.md | Начальный dev/ML запуск против DID LAB/ROS запуска | Сохранены команды DID LAB и ограничения; добавлены ML-команды, интеграционный статус, актуальная factory и ссылка на отчёт. Удалены неверные утверждения об отсутствии клиента. |
| docs/architecture.md | Структура монорепо и ML против подробного ROS/UI контура | Сохранены безопасность, A*, ROS, карта и web; добавлены lifecycle ResearchBridge, бюджет, whitelist и роли папок. |
| docs/team.md | Распределение dev против инструкций измерения энергии/команды | Сохранены правила Марии и обязанности Сони/Искандера; уточнено текущее владение DID LAB/frontend, ML-контракт и ограничение hypothesis_id. |
| packages/ml/README.md | Готовый локальный ML против EnergyModel и «Planner ещё нет» | За основу ML взяты локальные подробные инструкции; добавлены оригинальная энергия и offline интеграция, устаревшее «не реализован» удалено. |
| tests/README.md | ML unit-проверки против ROS/energy/backend suites | Сохранены обе инструкции; отдельно описан ограниченный stage-1 runner, mock-провайдеры, discovery и физические ограничения. |
| experiments/README.md | Локальный ML handoff против CLI результатов/энергии | Сохранён CLI и правила реальных измерений; добавлено явное отделение синтетических ML-оценок от Gazebo-метрик. |
| pyproject.toml | Локальные ML extras против DID LAB dependencies | Сохранены mapping всех пяти Python-пакетов и web зависимости; добавлен extra ml. uv.lock обновлён реальным resolver. |

Точные исходные версии пересекавшихся dev/local файлов сохранены в preserved-dev.
Это архив для сравнения, не текущая инструкция: см. ARCHIVE.md.
Документ docs/LLM_INTEGRATION.md адресно обновлён: прежде он неверно объявлял,
что клиент Сони отсутствует, и предлагал несуществующую factory.

## 3. Интеграция и контракты

Основные интеграционные изменения относительно energy-источника:

- packages/agent/did_agent/planner_bridge.py — новый ограниченный адаптер.
- packages/agent/did_agent/mission.py — lifecycle, результат/отказ, snapshot после
  ожидания, проверка safety/энергии и достоверный planner_source.
- packages/ml/did_ml/integration.py — offline factory.
- tests/test_planner_integration.py — адресные проверки реальных классов с fake IO.
- tests/test_scenarios.py — исправлено ошибочное ожидание LLM от обычной заглушки.
- tests/__init__.py, scripts/test_stage1.py, scripts/test_ml.py — совместный discovery.
- pyproject.toml, uv.lock и перечисленные документы.

DID LAB frontend/backend/ROS, навигация, watchdog и EnergyObserver перенесены.
Поведение ResearchPlanner сохранено побайтово относительно локальной dev-копии.
Контракты did_core.types/ports сохранены с добавлениями energy-ветки для поворотов;
ради LLM Observation и Subgoal не расширены.

Найдены и исправлены:
нет PlanningContext, нет acknowledge результата, нет reset между миссиями,
нет регулярного observe, ложный LLM source, устаревающий за время propose snapshot.
Контекст содержит достижимые A*-кандидаты и raw стоимости маршрутов, включая
поворот для возврата. Reserve/factor не передаются как часть raw стоимости.
ML margins не слабее backend; финальная безопасность всё равно у MissionManager.

Вызов propose асинхронный с deadline. Контекст считается на публичной копии
в worker thread; робот остановлен на время планирования, stop/safety сохраняются.
При REPLAN цель остаётся pending до окончательного исхода. Pause/cancel/rejection
закрывают предложение отрицательным результатом; collect и finish — по ответу
сервиса. Внешний message сервиса не передаётся в историю ML.

Маркировка LLM требует принятого source=provider. Offline, ошибка, generic Planner
и принудительный возврат отображаются Algorithmic. Моки явно названы в тестах.
Настоящий модельный источник в данном этапе не проверялся.

Whitelist удаляет добавочные Observation/pose поля; ML получает только публичные
датчики, карту/достижимость, измеренные затраты и публичную историю. Адаптер
не обращается к judge или его сцене. Canary-тесты проверяют prompt и историю.

Оригиналы Марии совпадают с source побайтово:
- energy.py SHA-256: da4767c0f76d62394e2c68796530b7b56bbd90c8c1f6e6e3101eb3def23b3477
- factory.py SHA-256: dfae955cd4a0badf0bf7ee9959f606f900585a40afd5302dcbcb23c0026b1af8

## 4. Найденная локальная DeepSeek-интеграция

На момент аудита новые неотслеживаемые файлы в основной dev-копии:
packages/ml/did_ml/mai_provider.py, settings.py, runtime.py, journal.py,
research.py, evaluation.py; scripts/check_llm.py, evaluate_ml.py;
tests/test_ml_provider.py, test_ml_handoff.py, test_ml_diagnostics.py;
docs/ml-handoff.md. Planner/context/provider/validation, .env.example, pyproject
и часть документации были отслеживаемыми файлами с локальными изменениями.

MAIProvider.complete(prompt: str) -> str уже реализует TextProvider.
Новый клиент или интерфейс вместо него не создавался. settings.py использует
DID_LLM_*; runtime.llm_planner владеет httpx-клиентом как async context manager.
Зависимости: httpx==0.28.1, python-dotenv==1.2.1, extra ml.
Всё перенесено в интеграционную ветку; реальные .env не читались/не копировались.
mai_provider.py, settings.py, runtime.py, planner.py совпали с локальными оригиналами.

До реального запуска требуется согласовать event loop/cleanup ROS и клиента,
серверную передачу конфигурации, вложенные тайм-ауты и journaling/redaction.
Использовать существующие настройки маршрута/модели и поддерживаемые параметры;
не угадывать новые значения. check_llm.py в этом этапе не запускался.

## 5. Проверки

Python 3.13 на Windows; целевой ROS Jazzy/Python 3.12 отдельно не запускался.
Baseline получены из git archive в соседних baseline-dev/baseline-energy,
без переключения основной копии.

| Команда / область | Результат | PASS | SKIP / причины |
|---|---|---:|---|
| baseline-dev: python scripts/test_ml.py | PASS | 21 | 0 |
| baseline-energy: test_stage1.py --root ../baseline-energy | FAIL, затем локализован | 134 | 6 полных миссий; 3 CLI failures из-за Windows charmap |
| baseline-energy: PYTHONUTF8=1, unittest test_results.py | PASS | 6 | Все три упавших CLI-теста входят в этот повтор; исходный код не менялся |
| baseline-energy, совокупность проверенных допустимых тестов | PASS | 137 | 6 полных миссий |
| Интеграция: python scripts/test_stage1.py | PASS (197 total, 0 errors/failures) | 191 | 6 полных кинематических тестов исключены |
| Отдельная команда python scripts/test_ml.py | PASS | 37 | 0; provider-тесты mock/local |
| Новые ResearchPlanner/MissionManager проверки | PASS | 17 | fake robot/services/provider, реальный planner/manager/A*/energy adapter |
| Финальные адресные planner/mode/runtime проверки | PASS | 25 | 0 |
| python scripts/check_ros_package.py | PASS | 1 проверка | Синтаксис/manifest/resource/config/map; не colcon |
| npm ci --ignore-scripts, npm run build | PASS | 1 сборка | TypeScript + Vite; не browser/ROS e2e |
| uv lock | PASS | 19 пакетов | Resolver сохранил ML extras; это не Docker install |
| EnergyModel/factory byte comparison | PASS | 2 файла | Алгоритмы Марии не изменены |
| Реальный DeepSeek API | SKIP | 0 | Нет отдельного разрешения, этап 2 |
| Физические ROS/Gazebo и полные EASY/MEDIUM/HARD | SKIP | 0 в итоговом наборе | Ограничение этапа 1 |

Состав исходного успешного общего прогона: 196 tests, 190 PASS, 6 SKIP,
0 failures/errors. После него добавлен тест маркировки принудительного возврата;
окончательный повтор: 197 tests, 191 PASS, 6 SKIP, 0 failures/errors;
машинная сводка хранится в integration-results.json.
ML: 21 основных + 2 diagnostics + 5 handoff + 9 provider/settings = 37.
Последние девять включают HTTP MockTransport и настройки, не реальную сеть.
Новые integration tests не имитируют успешную физическую миссию.

Отклонения при проверке, не скрытые за итоговым PASS:
первый общий baseline discovery успел захватить кинематические mission-тесты,
включая длительный тест на официальной карте, и ошибки временных файлов.
Это вышло за ограничение этапа; запуск остановлен и не используется как доказательство.
Далее использован явный список шести SKIP. Ни Gazebo, ни реальные модельные
запросы не запускались. Разрешённый повтор вне sandbox устранил filesystem errors.
UTF-8 устранил три исходных CLI failures. Ничего не исправлялось в физике/судье.
Первый интеграционный discovery обнаружил реальную коллизию имён scripts/test_ml.py
и tests/test_ml.py; введён квалифицированный tests.* discovery с -t .
Первый frontend build блокировался sandbox (esbuild spawn EPERM);
разрешённый повтор вне sandbox прошёл. Неуспешные подготовительные запуски
не включены в число успешно пройденных тестов.

## 6. Остаточные риски

| Приоритет | Файлы | Влияние / дальнейшая проверка |
|---|---|---|
| P1 | did_ml/runtime.py, ros2/.../agent_node.py, compose.yaml | Async client lifecycle не подключён к синхронной ROS factory; offline работает, настоящий DeepSeek e2e ещё нет. |
| P1 | did_ml/settings.py, did_agent/config.py | Provider timeout по умолчанию 5 с, manager deadline 3 с; согласовать общий бюджет/повторы до реальных запросов. |
| P1 | ROS/Gazebo/Docker окружение | Нет colcon/физической проверки в текущем Windows-сеансе. Нужен отдельный контролируемый стенд. |
| P2 | did_agent/planner_bridge.py | Ограничение восемью кандидатами может дать ранний возврат при недостижимых ближайших точках; полнота/качество покрытия не заявлены. Копирование карты требует измерить нагрузку на целевом стенде. |
| P2 | did_agent/planner_bridge.py, navigation.py | Отмена ожидания не прерывает уже начатый A*: worker завершает текущий расчёт на своей копии. На больших картах проверить задержки и CPU. |
| P2 | did_agent/state.py, did_ml/validation.py | ROS допускает skew до 0.1 с, ML не допускает будущего sensor timestamp. В таких пакетах используется fallback без подделки времени. |
| P2 | did_agent/mission.py, did_ml/research.py | hypothesis_id пока только null на backend, хотя ML умеет registry. Отдельно согласовать журнал/идентификаторы. |
| P2 | scripts/test_stage1.py, experiments/results.py | Windows CLI требует UTF-8; шесть полных тестов и физические проверки явно не подтверждены итоговым suite. |

## 7. Следующее задание

Довести именно существующий MAIProvider → ResearchPlanner → MissionManager:
проверить владение async клиентом в AgentNode, создание/закрытие при reset/shutdown,
согласовать общий deadline, retries и cancellation; передать серверные DID_LLM_*
без утечек в UI/prompt; проверить mock ошибки/auth/rate-limit/bad JSON и fallback.
Затем с отдельным разрешением выполнить один реальный check_llm и ограниченный
сквозной тест на доступном стенде. Не переписывать клиент и не менять EnergyModel.

## 8. Рекомендация команде

Ветка пригодна для review offline-интеграции. Это не финальная готовность DeepSeek
или соревновательных физических миссий. После review Сони, Искандера и Марии,
проверки этапа 2 и стенда команда может рассмотреть последующее объединение с dev
и судьбу Draft PR #3. Merge/push/удаление веток сейчас не выполнялись.
