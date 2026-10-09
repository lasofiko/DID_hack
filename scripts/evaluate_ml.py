"""Offline acceptance by default; --live explicitly spends API quota on synthetic cases."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for package in ("contracts", "ml"):
    sys.path.insert(0, str(ROOT / "packages" / package))


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/runs/ml-acceptance.json")
    args = parser.parse_args()
    from did_ml import ResearchPlanner
    from did_ml.evaluation import cases, evaluate
    from did_ml.journal import JsonlJournal
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    trace = args.output.parent / f"ml-trace-{timestamp}.jsonl"
    if args.live:
        from dotenv import load_dotenv
        from did_ml.runtime import llm_planner
        load_dotenv(ROOT / ".env", override=False)
        async with llm_planner(journal_path=trace) as planner:
            results = [await evaluate(planner, case) for case in cases()]
    else:
        planner = ResearchPlanner(journal=JsonlJournal(trace))
        results = [await evaluate(planner, case) for case in cases()]
    report = {"kind": "synthetic_ml_acceptance_not_gazebo", "live_requested": args.live,
              "created_utc": timestamp, "trace": str(trace), "results": results,
              "passed": sum(item["passed"] for item in results), "total": len(results),
              "llm_decisions": sum(item["source"] == "provider" for item in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] == report["total"] and (not args.live or report["llm_decisions"] > 0) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
