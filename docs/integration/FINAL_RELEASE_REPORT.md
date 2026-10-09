# Финальная интеграция DID LAB — 9 октября 2026

Итог: NOT READY. Интегрированный код проверен, но приёмка доставки не прошла
во всех обязательных случаях. Финальный merge в dev запрещён до устранения
провала audit_seeds и подтверждения критических gates. Все четыре EASY-опыта завершены.

## Источники и Git

Отдельный worktree: `/Users/kirito/.codex/worktrees/8130/DID_hack`.
Ветка: `integration/final-did-hack`. База: актуальный `origin/dev`
`2dc8827715be0524919d47c6d33d551b0f2e1c86`.

| Источник | SHA | Интеграция |
|---|---|---|
| Navigation, уже в dev | `2dc8827715be0524919d47c6d33d551b0f2e1c86` | Не применялся повторно |
| feature/mission-dashboard | `94afafef5520ce958bb4f9a8e55fb1255ae9c1f4` | Обычный merge с сохранением истории |
| feature/llm-validation | `77948c4e8991fcea51558b5b49acdac35f3a91be` | Обычный merge с сохранением истории |

SHA объединённого исполняемого кода: `5746274a00d456be799e61934482b62043bb3878`.
Конфликтов не было. Исправлены только trailing whitespace в двух frontend
critique-документах. Исходные ветки, main и PR #5 не изменялись.
Коммиты Сони `1124753` и `77948c4` оба являются предками интеграционной ветки.
Отдельных PR для двух новых веток при поиске не было; PR #4 уже содержался в dev.
PR #5 — dev → main, оставлен без изменений. Запуски GitHub Actions для новых
источников через доступный PR-workflow API не найдены; это не подтверждение CI.

## Автоматические проверки

Все команды запускались из корня worktree, кроме npm-команд.
`PY=/Users/kirito/Desktop/DID_hack/.venv/bin/python` — существующее Python 3.12
окружение; тесты через bootstrap импортируют текущий worktree.
Логи: `experiments/runs/final-integration/` (локальные, исключены из Git).

| Команда | PASS | FAIL | SKIP | Время | Статус / файл |
|---|---:|---:|---:|---:|---|
| `$PY -m unittest discover -s tests -t . -v` | 217 | 0 | 0 | 34.322 s | PASS, python-full.log |
| Docker Linux ARM64: `python3 -m unittest discover -s tests -t . -v` | 217 | 0 | 0 | 45.269 s | PASS, python-linux.log |
| `$PY -m unittest tests.test_navigation_reliability -v` | 6 | 0 | 0 | 1.364 s | PASS, navigation-tests.log |
| `$PY scripts/test_stage1.py` | 211 | 0 | 6 | 7.936 s | PASS с явными SKIPPED, test_stage1.log |
| `$PY scripts/test_ml.py` | 37 | 0 | 0 | 0.090 s | PASS, test_ml.log |
| `$PY scripts/check_ros_package.py` | — | — | — | 0.046 s | PASS, статическая проверка пакета |
| `$PY scripts/check_scenarios.py` | — | — | — | 140.383 s | Завершён, 18 кинематических строк; не ROS |
| `$PY scripts/audit_seeds.py` | 8 | 2 | 0 | 75.204 s | FAIL, seed 1 и 7 без доставки |
| Node 22: `npm ci && npm test && npm run build` | 22 | 0 | 0 | tests 0.183 s; build 1.49 s | PASS, frontend-docker.log |

Перекрывающиеся наборы не суммировать как число уникальных тестов.
Полный unittest включает A*, Navigation, Safety, Battery, Energy, Mission,
LLM lifecycle/validation/fallback, FastAPI/WebSocket, приватность и TIMEOUT.
Stage1 не заменял полный набор. `check_scenarios.py` только записывает результаты
и не делает assertions по итогам миссий; его exit 0 не равно всем успешным миссиям. Все 18 finished, коллизий 0;
доставка положительна в 16/18. HARD baseline seed 1 и adaptive seed 2 — delivered=0.
Точные команды, времена вспомогательных проверок — `checks.json`.

### Провал audit_seeds

Seed 1: finished, delivered=0, battery=30.7531, collisions=0.
Seed 7: finished, delivered=0, battery=44.6897, collisions=0.
Подробные повторные диагностики — `search-seed1.json`, `search-seed7.json`.
Завершение с пустой доставкой не считается успешной поисковой миссией.
Защитные энергетические коэффициенты не снижались; asserts не удалялись.

## Docker и ROS

Сборка: `UBUNTU_MIRROR=https://mirror.yandex.ru/ubuntu-ports docker compose -p did-final-integration build`.
Старт: `docker compose -p did-final-integration up -d`.
Docker build, React внутри образа и colcon did_robot: PASS (`docker-build.log`).
Linux ARM64, ROS 2 Jazzy, Gazebo Harmonic 8.15.0, TurtleBot3 Burger.
На старте Gazebo ожидал скачивание ground plane. Существующий Fuel-кеш скопирован
из тома `did_hack_gazebo-fuel` в отдельный `did-final-integration_gazebo-fuel`
без удаления/перезаписи исходного тома; интеграционный контейнер перезапущен.

Пассивный `scripts/ros_smoke.py`: PASS, `ros-smoke.log`.
Получено 22 odom / 3 scan / 435 clock; scan содержит 360 лучей, 327 конечных.
TF включает map → odom → base_footprint → base_link → base_scan.
Стартовая world/map ошибка 0.00844 m. `/cmd_vel` — TwistStamped;
единственный publisher did_agent (`cmd-owners.log`). Сервисы: `ros-services.log`.
Это стартовый probe без `--move`; движение оценивается отдельными миссиями.

## LLM и энергия

Включены исправления позднего ответа после Stop, запрета движения при отказе
ML-журнала и валидации зарегистрированных hypothesis_id. Новые и прежние тесты
прошли в полном наборе. LLM передаёт Subgoal, не публикует скорости.
Исторические два вызова MAI/DeepSeek описаны в [LLM_FINAL_VALIDATION.md](LLM_FINAL_VALIDATION.md)
и `llm-live-manager-evidence.json`: настоящая сеть, синтетическое наблюдение,
physical_execution=false. Эти два синтетических probe повторно не запускались.
При первоначальной проверке ключ отсутствовал в окружении интеграционного
стенда. Это ограничение конфигурации, не отсутствие реализации LLM. Затем
пользователь настроил `/Users/kirito/Desktop/DID_hack/.env`; явный `--env-file`
подтвердил наличие ключа в Compose и ожидаемые MAI/DeepSeek endpoint/model.
Значение ключа не выводилось и не копировалось. После завершения матрицы
контейнер пересоздан с явным --env-file без сборки. Настоящий физический
LLM-тест не прошёл: два Start через React дали HTTP 503 и безопасный stopped
до запроса к модели. Диагностический Start через backend прошёл, но реальные
provider_request завершились TimeoutError при лимите 5 s и source=offline.
Принятого provider-ответа и исполнения его подцели нет. Проверка обновлённой
API-конфигурации NOT VERIFIED после срочного изменения приоритета на Git.

BatteryManager.required применяет `(movement + turns) * return_factor + battery_reserve`;
фактические значения 1.5 и 8. Это условие принятия маршрута, не гарантия возврата.
Baseline обновляет наблюдаемую модель, оставляя исходные веса; adaptive применяет
оценки к планированию. Разделение и изменение маршрута проверяются автотестами.
Физические measurements/replans фиксируются в receipts и телеметрии.

## Frontend

Реальная страница localhost:3000 подключена к собранному ROS backend через WS.
RU/TT, сохранение TT после reload, татарские символы, Presentation Mode: PASS.
Карта, текущая поза/траектория, источник Algorithmic и журнал обновлялись
во время физической миссии. Состояние offline при перезапуске стенда видно.
Проверены CSS viewport 1920×1080, 1440×900, 1280×800, 390×844; горизонтального
переполнения нет. Скриншоты: `ru-css-*.jpg`, `tt-mobile.jpg`, `presentation-1440.jpg`.
Погрешность исходного масштаба браузера учтена; фактические размеры — `viewports.json`.
Проверка касается desktop-браузера с изменённым viewport, не физического телефона.
Татарский перевод не проверен носителем. Часть технического журнала остаётся EN
с явной пометкой оригинального сообщения. Полный WCAG-аудит не заявляется.

## Ограничения целостности

Нет конфликтных маркеров/удалённых исходников/новых файлов >1 MB.
Эвристическая проверка изменённых текстовых файлов не обнаружила шаблонов секретов
(`secret-scan.json`); это не формальная гарантия отсутствия секретов.
Сырые логи и новые скриншоты исключены из Git через experiments/runs.
Детектор frontend не сообщил находок (`ui-detector.json`).

## Физические миссии, Stop и release gate

Первый EASY baseline seed 1 завершён по внешнему лимиту 900.002 s:
collected=1, delivered=0, battery_used=28.4438, remaining=31.5562,
route_length=24.6240 m, replans=0, physical_base_distance=1.76523 m.
Статус stopped, причина External mission deadline, return_success=false.
Это FAIL приёмки доставки и прерванный возврат, не Return failed: TIMEOUT.
Независимые контакты не измеряются (collisions=null); reported_collision_events=0.
Receipt: `experiments/runs/docker/final-easy-baseline-1.json`.

Остановка после внешнего лимита: PASS. В receipt 40 устойчивых нулевых команд;
независимый `final-stop-proof.json` получил 63 нулевые TwistStamped и физическое
смещение 0.0 m за 3 s. Это проверка фактического неподвижного тела Gazebo.
`physical-midpoint.json` подтверждает положение тела [0.707827, 1.624910] m
во время миссии относительно старта около [-2.00844, -0.5] m.

Возобновление после прерывания не перезапускало текущую миссию, сборки или тесты.
Ожидающий runner следующих опытов остановлен до проверки Stop, затем возобновлён.
Повторный SSH fetch после прерывания завершился сетевым timeout. Затем GitHub API
подтвердил неизменность SHA dev, frontend и LLM. Хеши runtime.py, mission.py
и planner.py в Docker совпали с текущим worktree (image-source-hashes.txt).
До завершения критических gate merge в dev запрещён.

Инструкция демонстрации: [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md).

## Завершённая физическая матрица

Все строки: EASY, Algorithmic, SHA `5746274`, лимит 900 s, последовательное
выполнение в одном интеграционном стенде. Никакая миссия не запускалась параллельно.

| Seed | Стратегия | Статус | Собрано / доставлено | Время, s | Использовано / осталось | Путь, m | До базы, m | Replans | Возврат | Нулевых cmd |
|---|---|---|---|---:|---|---:|---:|---:|---|---:|
| 1 | Baseline | FAIL, external timeout | 1 / 0 | 900.002 | 28.444 / 31.556 | 24.624 | 1.765 | 0 | Нет | 40 |
| 1 | Adaptive | PASS, finished | 1 / 1 | 495.504 | 18.880 / 41.120 | 17.085 | 0.142 | 34 | Да | 59 |
| 2 | Baseline | PASS, finished | 1 / 1 | 473.747 | 18.414 / 41.586 | 14.976 | 0.177 | 0 | Да | 61 |
| 2 | Adaptive | PASS, finished | 1 / 1 | 536.510 | 18.454 / 41.546 | 16.528 | 0.164 | 33 | Да | 59 |

Receipts: `experiments/runs/docker/final-easy-{baseline,adaptive}-{1,2}.json`.
Сводка: `experiments/runs/final-integration/physical-summary.json`.
Полный журнал: `experiments/runs/docker/agent-journal.jsonl`.
Replans подсчитаны по полному журналу run_id, поскольку receipt сохраняет только
ограниченный хвост событий. Физические расстояния до базы берутся из Gazebo,
путь — из odom. Полное число обнаруженных образцов не подтверждено.
Reported collision events = 0 во всех четырёх строках; независимые контакты
NOT VERIFIED. Нет основания приравнивать отсутствие событий к отсутствию контактов.

### Baseline vs Adaptive

Seed 1: Adaptive завершил доставку и возврат; Baseline не уложился в лимит.
Сравнение энергии на доставленный образец для Baseline seed 1 не определено.
Seed 2: оба доставили один образец; Adaptive использовал на 0.041 энергии больше,
прошёл на 1.552 m больше и занял на 62.763 s больше. Превосходство Adaptive
не подтверждено этими двумя парами. Оценки энергии и перепланирование работают,
но эффективности и надёжности требуется отдельная оценка на большем наборе.
MEDIUM/HARD физические миссии: SKIPPED по приоритету пользователя экономить лимит
и не проводить дополнительных длительных экспериментов; кинематические результаты
не заменяют их. Доставка всех 3/5/7 образцов NOT VERIFIED.

## Управление настоящим backend

В React последовательно выполнены Reset, Start, Pause, Resume, Return и Stop.
Телеметрия: finished → idle → running → paused → running → returning → stopped.
Результат и сырые измерения: `experiments/runs/docker/final-controls-proof.json`;
сводка: `experiments/runs/final-integration/control-summary.json`.
Start/Resume сопровождались ненулевыми ROS-командами, всего в probe 693 таких команды.
Pause: 359 нулевых команд во внутреннем интервале, отступ 2 s от границ
опроса состояния с частотой 1 Hz; физическое смещение за наблюдение Pause 0.001776 m.
На границе Resume ненулевые команды появились раньше следующего HTTP-опроса;
поэтому весь интервал между снимками paused/running нельзя называть строго нулевым.
Stop: 888 нулевых команд после задержки 0.5 s; физическое смещение 0.0 m.
UI показал подтверждение stopped свежей телеметрией (`ui-stopped.jpg`).
Return подтвердил переход returning и движение, а полное завершение возврата
подтверждается тремя отдельными строками матрицы. Reset проверен после finished,
а не после stopped. Ограничения velocity, watchdog и SafetyManager не изменялись.

Fallback проверен отдельно в контейнере без ключа: выбрано LLM, но backend сообщил
`Planner unavailable; Algorithmic fallback: ValueError`; источник Algorithmic
виден в UI как «Алгоритмический резерв» (`llm-fallback.jpg`). Это PASS честного
отображения fallback, но не доказательство настоящего LLM.

## Срочная публикация интеграции

По последнему распоряжению пользователя новые физические эксперименты не
запускаются. Приоритет — сохранение кода и публикация PR в dev.
Быстрая повторная проверка:
`python -m unittest tests.test_backend tests.test_llm_mission_runtime tests.test_llm_final_validation tests.test_planner_integration -v`:
41 PASS, 0 FAIL, 0 SKIP, 1.645 s. Лог: `experiments/runs/final-integration/git-priority-tests.log`.
Проверены совместимость API/WS, lifecycle LLM, ResearchBridge и валидация.
Frontend tests/build не повторялись: 22 PASS и production build уже подтверждены
на том же SHA кода. После этого менялись только документы.

| Release gate | Статус | Доказательство |
|---|---|---|
| 1: три компонента | PASS | Navigation, оба feature head и оба коммита Сони — предки HEAD |
| 2: конфликты | PASS | Нет unmerged index; обычные merge; whitespace исправлен |
| 3: автоматические проверки | FAIL для полного release | 217 unittest и быстрые 41 PASS; audit_seeds 8/10 |
| 4: frontend build / UI | PASS с отдельным блокером LLM Start | 22 tests, tsc/Vite, RU/TT, Algorithmic controls |
| 5: Docker / ROS | PASS ранее проверенного стенда | Build, Jazzy/Harmonic, odom/scan/clock/TF |
| 6: движение Gazebo | PASS | Четыре реальные физические миссии |
| 7: Safety / Stop | PASS в указанном объёме | Автотесты, UI controls, нулевые команды и неподвижность |
| 8: настоящий LLM / fallback | FAIL / NOT VERIFIED | Fallback виден; два Start HTTP 503; provider → исполнение не подтверждено |
| 9: приватность | PASS в проверенном объёме | Whitelist и тесты; ключ не выводился; raw logs ignored |
| 10: отчёт | PASS | Фактические результаты и ограничения сохранены |

Публикуется Draft PR без merge в dev из-за незакрытого runtime-блокера LLM Start.
Причина HTTP 503 не установлена: гипотеза холодной инициализации не доказана.
Успешный диагностический Start не опровергает два отказа UI. Timeout provider —
отдельное ограничение конфигурации/сети, а не отсутствие реализации LLM.
Провал audit_seeds относится также к Navigation-коду, уже находящемуся в dev;
это ограничение доставки, не доказанная регрессия frontend merge.

Сохранены `experiments/runs/docker/final-real-llm-first-start-failure.json`,
`final-real-llm-second-start-failure.json`, `final-llm-timeout-diagnostic.json`,
`experiments/runs/final-integration/real-llm-api-diagnostic.log` и ML JSONL.
При остановке диагностического observer SIGTERM завершил контекст rclpy до
сериализации receipt: сырой журнал сохранён, backend подтвердил stopped.
Этот observer не считается успешным LLM/физическим Stop-доказательством.
Все экспериментальные harness и логи остаются ignored. Main и PR #5 не меняются.

## Обновление Git после нового распоряжения, 9 октября 2026

Пользователь изменил порядок приёмки и явно потребовал fast-forward dev после
критических Python/frontend-проверок. Dev обновлена обычным fast-forward/push
до d14c685; Navigation, EnergyModel, финальная LLM, Frontend и DEMO-профиль
сохранены. Дополнительно публикуется коммит плана экспериментов и этой записи.
Критические проверки: 100/100 Python PASS, 22/22 frontend PASS, без skip/fail.
Ошибок Git merge и diff --check нет. Эти результаты не закрывают описанные выше
физические/LLM release gates: готовность полного релиза остаётся NOT READY.
Ранее запланированный Draft PR не был создан коннектором (HTTP403); дальнейшее
обновление dev выполнено напрямую по новому явному указанию, без merge в main.

Удалены только remote-ветки feature/maria, feature/llm-integration,
feature/llm-validation, feature/mission-dashboard, night-mvp и
integration/final-did-hack после проверки ancestry и актуальных remote SHA.
Локальные ветки/worktree сохранены. Незакоммиченный map.yaml основной копии
оставлен побайтно неизменным и сохранён отдельным patch; неправильный ключ
«вщслукimage» вместо image остаётся локальной проблемой, в dev он не включён.
Полная матрица НЕ запускалась; план — FULL_EXPERIMENT_PLAN.md и
experiments/plans/final-matrix.json. Перед тестированием необходим научный образ
на актуальном source SHA: нынешний DEMO-overlay не заменяет его проверку.
