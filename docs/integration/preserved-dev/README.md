# DID Hack — скелет проекта

Структура и минимальный запуск приложения. ML-планировщик реализован отдельно
без LLM; логика робота, интеграция с бэкендом и симуляция пока не реализованы.

```text
apps/
  backend/        FastAPI: точка входа и GET /api/health
  frontend/       React + TypeScript: стартовая страница
packages/
  contracts/      общие типы и интерфейсы, без реализации
  agent/          логика агента и планирование (TODO)
  ml/             офлайн-планировщик, проверки и интерфейс будущей LLM
  environment/    сценарии и судья (TODO)
ros2/             ROS-узлы и launch (TODO)
configs/          настройки (TODO)
tests/            тесты (TODO)
experiments/      результаты запусков (TODO)
docs/             описание архитектуры
scripts/          запуск
```

## Первый запуск

Нужны Python 3.12+ и Node.js 22.12+.

```sh
python -m venv .venv
```

Активация Windows: `.venv\Scripts\Activate.ps1`.
Linux: `source .venv/bin/activate`.

```sh
python -m pip install -e .
npm ci --prefix apps/frontend
npm run build
npm run dev
```

Открыть http://127.0.0.1:8000. Страница показывает статус подключения к бэкенду.
После установки и сборки достаточно `npm run dev`.

Для разработки фронта с hot reload запустить во втором терминале:

```sh
npm run dev --prefix apps/frontend
```

Vite проксирует `/api` на бэкенд порта 8000.
Назначение модулей: [архитектура](docs/architecture.md).

## Команде: с чего начать

1. [Кто что пишет и как соединять модули](docs/team.md).
2. [Форматы данных](packages/contracts/did_core/types.py) и [подписи интерфейсов](packages/contracts/did_core/ports.py).
3. [Контракт API для фронта и бэка](docs/api.md).

Типы и Protocol — договорённости, не готовые алгоритмы. Реализацию каждый
пишет в своём модуле. Дополнительные API пока существуют только в документации.

## Реализованная ML-часть (без LLM)

`packages/ml/did_ml` теперь содержит офлайн-планировщик и интерфейс будущего
LLM-провайдера. Остальные части остаются скелетом. Интеграция и ограничения:
[ML README](packages/ml/README.md).

```sh
python scripts/demo_ml.py
python scripts/test_ml.py
```

## DeepSeek через API МАИ

Добавлен асинхронный адаптер `deepseek-v4.1-flash`. Установка:
`python -m pip install -e ".[ml]"`. Настройки и новый ключ — в локальном `.env`
по `.env.example`. Проверочный запрос: `python scripts/check_llm.py`.
Подробности и непроверенные параметры шлюза: [ML README](packages/ml/README.md).
Проверочный живой запрос с локальными настройками прошёл (source=llm). Автотесты используют подставной HTTP.


## Передача ML команде

[Инструкция для Искандера и Марии](docs/ml-handoff.md): API модуля, журнал,
гипотезы, replay и границы ответственности. Приёмка: `python scripts/evaluate_ml.py`.
Реальные запросы включаются отдельно флагом `--live`.
