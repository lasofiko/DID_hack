# Проверки

Из корня в Python 3.12 окружении:

```sh
.venv/bin/python -m unittest discover -s tests -t . -v
.venv/bin/python scripts/check_ros_package.py
.venv/bin/python scripts/check_scenarios.py
.venv/bin/python scripts/audit_seeds.py
```

Unit-тесты проверяют A*, координаты, safety, энергию, поиск, команды, сервисные
отказы, planner validation/fallback, адаптацию и запрет скрытых данных.
Backend-тесты проверяют ASGI API/WS; без FastAPI они пропускаются, это не полная
проверка backend. check_ros_package проверяет структуру/синтаксис, не colcon.

check_scenarios запускает 18 кинематических сочетаний трёх сценариев, двух
режимов, seed1/2/7. audit_seeds проверяет seed1..10 на поставляемой карте.
JSON пишутся в experiments/runs, а не docs. Это **не ROS/Gazebo**: нет DDS,
физики колёс и скольжения.
audit_seeds — отдельная проверка качества доставки: известны seed7/8 с
безопасным возвратом без образца. Код 1 в таком случае ожидаемо сообщает
недостигнутый критерий; это ограничение текущего поиска, а не зелёный unit-тест.

Для работающего Docker web-стенда:

```sh
docker compose exec -T simulation bash docker/entrypoint.sh python3 -m unittest discover -s tests -t .
docker compose exec -T simulation bash docker/entrypoint.sh python3 scripts/web_check.py --seed 1 --controls --seconds 650 --output /workspace/output/web-easy-1.json
```

web_check **пересоздаёт сессию** и проверяет настоящие HTTP/WS → ROS → Gazebo,
мировую позу робота и устойчивые нули после finish. Не запускать одновременно
с ручным опытом/второй пробой. ros_smoke --move требует отдельный свежий мир
с start_agent=false: два источника скорости недопустимы.

Полная процедура, отрицательный clock-тест и критерии:
[validation](../docs/validation.md). Запуск: [QUICK_START](../docs/QUICK_START.md).

## Этап 1: локальная интеграция

python scripts/test_stage1.py объединяет наборы DID LAB, EnergyModel и ML,
добавляя tests/test_planner_integration.py (реальные классы + fake IO/provider).
Шесть тестов с полными кинематическими миссиями получают явный SKIP.
На Windows запускать с $env:PYTHONUTF8="1": CLI результатов печатает Unicode.
python scripts/test_ml.py отдельно запускает ML, включая HTTP MockTransport.
При ручном unittest discovery нужен -t ., чтобы tests.test_ml не конфликтовал
с scripts/test_ml.py. Пропуск отсутствующих зависимостей не является PASS.

Проверяются raw-энергобюджет и разворот, публичный whitelist, reset/result,
повторная safety/energy-проверка, pause/cancel и сохранение цели при REPLAN.
Все provider-тесты локальные. Итоговые числа и ограничения:
[STAGE1](../docs/integration/STAGE1.md).
