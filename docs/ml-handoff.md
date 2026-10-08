# ML: передача команде

Ответственная: Соня. Модуль `packages/ml/did_ml`. Работает без ROS, умеет
использовать DeepSeek через МАИ. Не управляет роботом и не знает скрытых целей.

## Готово

- ResearchPlanner, публичный контекст, проверка JSON, энергии и свежести.
- Офлайн-выбор, память посещений/отказов, фильтрация сигнала перед collect.
- API-адаптер, тайм-ауты, до двух попыток и fallback.
- После исчерпания попыток — пауза API на 30 секунд реального времени
  (provider_cooldown); в это время действует офлайн-планировщик.
- Реестр гипотез: только явно зарегистрированные id, без выдуманных выводов.
- JSONL: настройки, входы, промпты, финальные ответы, задержки и результаты.
- ReplayProvider и 9 синтетических приёмочных ситуаций.

## Искандеру: цикл интеграции

```python
from pathlib import Path
from did_ml import PlanningContext
from did_ml.runtime import llm_planner

async with llm_planner(journal_path=Path('experiments/runs/mission-001.jsonl')) as planner:
    planner.observe(observation)
    planner.set_context(PlanningContext(
        sim_time=observation['sim_time'],
        pose_x=observation['pose']['x'],
        pose_y=observation['pose']['y'],
        home_energy=home_energy,
        candidates=tuple(candidates),
    ))
    goal = await planner.propose(observation)
    # Проверить на НОВЫХ данных, исполнить либо отклонить.
    planner.record_result(goal, result, completion_time)
```

Переменные observation/candidates/home_energy/result предоставляет backend.
Исполняемый пример без API: `python scripts/demo_ml.py`.
Один planner и HTTP-клиент живут всю миссию, не пересоздаются для каждого решения.
Backend заранее загружает окружение; автоматической загрузки .env в библиотеке нет.

Перед propose:

1. Кандидаты достижимы на публичной карте в map. Candidate содержит id, x, y,
   outbound_energy, return_energy, information_gain (по умолчанию 1).
2. id стабильны. Стоимости — единицы батареи, не расстояния. Учесть правила
   расхода движения/поворотов/простоя. home_energy — возврат с текущей позиции.
3. Context точно соответствует времени и позиции Observation. Время — /clock.
4. Свежие наблюдения подавать в observe между решениями, иначе не накопится
   окно сигнала. Во время запроса LLM держать новые данные в агрегаторе backend.

После propose:

- Снова проверить сенсоры, путь и бюджет: состояние меняется за время API.
- Обязателен record_result для той же подцели, включая отказ валидатора.
  Неудача — success=False, причина в message и в feedback следующего propose.
- UnsafeObservation/PlanningUnavailable — остановка и восстановление,
  не разрешение ехать домой. RuntimeError журнала — также стоп; восстановить
  запись и пересоздать миссию, не продолжать исполнение без журнала.
- observe/set_context/propose/record_result сериализованы. ROS-watchdog
  работает независимо от ML. Успех collect/finish подтверждает только судья.
- reset очищает pending, память, гипотезы и паузу API. Вызывать только для
  новой миссии/сброса часов, не после каждого решения.

## Марии: гипотезы и стоимость

EnergyModel и научные критерии остаются вашей частью. Backend передаёт начальные
стоимости для baseline и обновляемые для adaptive. LLM/промпт/пороги в паре одинаковы.

Гипотеза регистрируется ДО эксперимента, без pending-подцели:

```python
planner.observe(observation)
planner.register_hypothesis(
    'H1', 'Стоимость движения на участке выросла',
    'Повторный расход выше исходной оценки', observation['sim_time'],
)
```

Модель может связать действие с H1, если оно проверяет предположение, либо
вернуть null. Офлайн-планировщик оставляет null. После результата и свежего observe:

```python
planner.conclude_hypothesis('H1', evidence, conclusion, observation['sim_time'])
```

evidence/conclusion основаны на ваших измерениях. Реестр проверяет порядок и
формат, но не доказывает истинность вывода. Несостоявшаяся проба — неопределённый
результат. Идентификаторы не переиспользуются в миссии.
События kind=research соответствуют JournalEntry: hypothesis/observation/conclusion.

## Журнал и replay

Запись включается параметром journal_path у llm_planner. Для офлайна:
ResearchPlanner(journal=JsonlJournal(path)). Файлы experiments/runs игнорируются Git.
Ключ редактируется журналом runtime, заголовки не записываются. Другие секреты
не помещать в контекст. Файлы автоматически никуда не отправляются.

```python
from did_ml import ResearchPlanner
from did_ml.journal import ReplayProvider
planner = ResearchPlanner(provider=ReplayProvider(path, session_id=saved_session_id))
```

Повторить те же наблюдения, контекст, гипотезы, feedback и результаты в том же
порядке. Хеш промпта должен совпасть. Replay повторяет успешные HTTP-ответы,
включая отклонённые подцели, но не сетевые сбои, задержки и физику Gazebo.
Он не восстанавливает весь процесс из checkpoint. Каждый reset создаёт новый session_id.

## Приёмка

```sh
python -m pip install -e ".[ml]"
python scripts/test_ml.py
python scripts/evaluate_ml.py
```

Для живого API (расходует квоту, до 6 попыток для текущего набора):

```sh
python scripts/evaluate_ml.py --live --output experiments/runs/ml-live-acceptance.json
```

Каждая ситуация изолирована reset. Отчёт разделяет provider/offline/safety;
fallback не считается ответом модели. Это приёмка ML-модуля, не эксперименты Gazebo.

## Осталось у команды

Искандер: Observation/TF/карта, кандидаты и пути, MissionControl, ROS/safety,
судья, HTTP/WS, отображение журнала. Мария: EnergyModel, методика научных проб,
калибровка порогов, hard-события, парные эксперименты. Фронт: реальные миссии.

ML сам не строит маршрут и не оценивает грунты. Без кандидатов вернёт подцель
возврата. Локальный поиск градиента сигнала и выявление отказа датчика ещё не
реализованы. Реестр гипотез не заменяет научную методику. Полную миссию в ROS
нужно проверить совместно после интеграции.

## Проверено 8 октября 2026

- 37 автотестов прошли, включая HTTP-ошибки, отмену, журнал, replay и реестр.
- Офлайн-приёмка: 9/9 синтетических ситуаций.
- Живая приёмка после уточнения промпта: 9/9, из них 3 решения DeepSeek,
  остальные — правила возврата/остановки. Эти 3 ответа заняли примерно 3.1–4.0 с.
- Первый живой прогон дал 8/9: модель исследовала вместо сбора при устойчивом
  сигнале. Уточнён приоритет collect; повторный прогон прошёл. Это один повтор,
  не статистическая оценка надёжности и не эксперимент в Gazebo.
- Локальный отчёт: experiments/runs/ml-live-acceptance-v2.json; путь к trace
  записан внутри. Логи игнорируются Git, не публикуются автоматически.
