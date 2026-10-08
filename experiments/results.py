"""Manual robot run records and summary. Standard library only."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
FIELDS = {
    "run_id", "scenario", "seed", "mode", "initial_position", "goal",
    "success", "duration_s", "error", "energy_used", "collected", "delivered",
    "recorded_at", "source",
}


def numeric(value, name, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: требуется число")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (nonnegative and value < 0):
        raise ValueError(f"{name}: число должно быть конечным" + (" и неотрицательным" if nonnegative else ""))


def validate(record):
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError("Запись имеет неверный набор полей")
    if not isinstance(record["run_id"], str) or not record["run_id"].strip():
        raise ValueError("run_id не может быть пустым")
    for name, choices in [("scenario", ("easy", "medium", "hard")), ("mode", ("baseline", "adaptive"))]:
        if record[name] is not None and record[name] not in choices:
            raise ValueError(f"Неверное значение {name}")
    for name in ("seed", "collected", "delivered"):
        value = record[name]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{name}: требуется неотрицательное целое")
    if record["seed"] is not None and record["seed"] > 2147483647:
        raise ValueError("seed превышает предел контракта")
    for name in ("initial_position", "goal"):
        point = record[name]
        if point is not None:
            if not isinstance(point, dict) or set(point) != {"x", "y"}:
                raise ValueError(f"{name}: требуются x и y")
            for coordinate in ("x", "y"):
                numeric(point[coordinate], f"{name}.{coordinate}")
    if record["success"] is not None and type(record["success"]) is not bool:
        raise ValueError("success: требуется true, false или null")
    for name in ("duration_s", "energy_used"):
        if record[name] is not None:
            numeric(record[name], name, nonnegative=True)
    if record["error"] is not None and not isinstance(record["error"], str):
        raise ValueError("error: требуется строка или null")
    if record["collected"] is not None and record["delivered"] is not None:
        if record["delivered"] > record["collected"]:
            raise ValueError("delivered не может превышать collected")
    if record["source"] != "manual" or not isinstance(record["recorded_at"], str):
        raise ValueError("Неверные метаданные записи")
    try:
        timestamp = datetime.fromisoformat(record["recorded_at"])
    except ValueError as error:
        raise ValueError("Неверное время записи") from error
    if timestamp.tzinfo is None:
        raise ValueError("Время записи должно содержать часовой пояс")


def read_store(path, kind):
    if not path.exists():
        return {"schema_version": 1, "dataset_kind": kind, "runs": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "dataset_kind", "runs"}:
        raise ValueError("Неверный формат файла результатов")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Неподдерживаемая версия файла")
    if data["dataset_kind"] != kind:
        raise ValueError("Нельзя смешивать тестовые и реальные записи: выберите другой файл")
    if not isinstance(data["runs"], list):
        raise ValueError("runs должен быть массивом")
    ids = set()
    for record in data["runs"]:
        validate(record)
        if record["run_id"] in ids:
            raise ValueError("В файле повторяются run_id")
        ids.add(record["run_id"])
    return data


def save_store(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def summary(runs):
    successful = [run for run in runs if run["success"] is True]
    failures = [run for run in runs if run["success"] is False]
    unknown = len(runs) - len(successful) - len(failures)
    known = len(successful) + len(failures)
    durations = [run["duration_s"] for run in successful if run["duration_s"] is not None]
    return {
        "runs_total": len(runs), "successful": len(successful),
        "failed": len(failures), "unknown_outcome": unknown,
        "success_rate_known_outcomes": len(successful) / known if known else None,
        "successful_duration_s": {
            "available": len(durations), "missing": len(successful) - len(durations),
            "mean": math.fsum(value / len(durations) for value in durations) if durations else None,
            "min": min(durations) if durations else None,
            "max": max(durations) if durations else None,
        },
        "failures": failures,
    }


def point(values):
    return {"x": values[0], "y": values[1]} if values is not None else None


def prompt(label, convert=str):
    while True:
        value = input(label + " (Enter = неизвестно): ").strip()
        if not value:
            return None
        try:
            return convert(value)
        except ValueError as error:
            print(f"Некорректный ввод: {error}")


def choice(options):
    def convert(value):
        if value not in options:
            raise ValueError("допустимо: " + ", ".join(options))
        return value
    return convert


def coordinates(value):
    parts = value.replace(",", " ").split()
    if len(parts) != 2:
        raise ValueError("введите два числа x y")
    values = [float(part) for part in parts]
    for item in values:
        numeric(item, "координата")
    return values


def nonnegative_float(value):
    result = float(value)
    numeric(result, "значение", nonnegative=True)
    return result


def nonnegative_int(value):
    result = int(value)
    if result < 0:
        raise ValueError("требуется неотрицательное целое")
    return result


def interactive(args):
    fields = [
        ("run_id", "ID запуска (Enter = создать автоматически)", str),
        ("scenario", "Сценарий easy/medium/hard", choice(("easy", "medium", "hard"))),
        ("seed", "Seed", nonnegative_int),
        ("mode", "Режим baseline/adaptive", choice(("baseline", "adaptive"))),
        ("initial_position", "Начальная позиция x y в map", coordinates),
        ("goal", "Заданная цель x y в map", coordinates),
        ("success", "Цель достигнута? yes/no/unknown", choice(("yes", "no", "unknown"))),
        ("duration_s", "Длительность, секунды", nonnegative_float),
        ("error", "Описание ошибки", str),
        ("energy_used", "Расход энергии", nonnegative_float),
        ("collected", "Собрано образцов", nonnegative_int),
        ("delivered", "Доставлено образцов", nonnegative_int),
    ]
    for name, label, convert in fields:
        if getattr(args, name) is None:
            setattr(args, name, prompt(label, convert))


def main():
    parser = argparse.ArgumentParser(description="Сохранение результатов робота и сводка")
    parser.add_argument("--file", type=Path, help="Свой JSON-файл результатов")
    parser.add_argument("--test-data", action="store_true", help="Только тестовые данные, отдельный файл")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="Добавить результат; без полей запускает опрос")
    add.add_argument("--interactive", action="store_true", help="Запросить отсутствующие поля")
    add.add_argument("--run-id")
    add.add_argument("--scenario", choices=("easy", "medium", "hard"))
    add.add_argument("--seed", type=int)
    add.add_argument("--mode", choices=("baseline", "adaptive"))
    add.add_argument("--initial-position", nargs=2, type=float, metavar=("X", "Y"))
    add.add_argument("--goal", nargs=2, type=float, metavar=("X", "Y"))
    add.add_argument("--success", choices=("yes", "no", "unknown"))
    add.add_argument("--duration-s", type=float)
    add.add_argument("--error")
    add.add_argument("--energy-used", type=float)
    add.add_argument("--collected", type=int)
    add.add_argument("--delivered", type=int)
    commands.add_parser("summary", help="Показать сводку JSON")
    args = parser.parse_args()
    kind = "test" if args.test_data else "real"
    path = args.file or ROOT / ("test_data" if args.test_data else "results") / "runs.json"
    try:
        data = read_store(path, kind)
        if args.command == "summary":
            print(json.dumps({"dataset_kind": kind, **summary(data["runs"])}, ensure_ascii=False, indent=2, allow_nan=False))
            return
        metadata = ("run_id", "scenario", "seed", "mode", "initial_position", "goal", "success", "duration_s", "error", "energy_used", "collected", "delivered")
        if args.interactive or all(getattr(args, field) is None for field in metadata):
            print("ТЕСТОВЫЕ ДАННЫЕ" if args.test_data else "РЕАЛЬНЫЕ РЕЗУЛЬТАТЫ: вводите только наблюдавшиеся значения")
            interactive(args)
        record = {field: getattr(args, field) for field in metadata}
        record.update(
            run_id=args.run_id if args.run_id is not None else str(uuid.uuid4()),
            initial_position=point(args.initial_position), goal=point(args.goal),
            success={"yes": True, "no": False}.get(args.success),
            error=args.error.strip() or None if args.error is not None else None,
            recorded_at=datetime.now(timezone.utc).isoformat(), source="manual",
        )
        validate(record)
        if any(run["run_id"] == record["run_id"] for run in data["runs"]):
            raise ValueError("run_id уже существует; запись не изменена")
        data["runs"].append(record)
        save_store(path, data)
        print(f"Сохранено ({kind}): {record['run_id']} → {path}")
    except (ValueError, OSError, EOFError) as error:
        parser.exit(2, f"Ошибка: {error}\n")


if __name__ == "__main__":
    main()
