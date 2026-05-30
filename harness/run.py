"""
Run baseline models against the v0.1 benchmark dataset.

Usage:
    python harness/run.py                        # uses config.yaml defaults
    python harness/run.py --model gpt-4o         # override model
    python harness/run.py --snapshot B           # override snapshot
    python harness/run.py --no-sample            # full 840-row run
"""
import argparse
import csv
import json
import pathlib
import sys
import yaml
from datetime import datetime, timezone

import check_version
import model as model_module

BENCHMARK_DIR = pathlib.Path(__file__).parent.parent
HARNESS_DIR = pathlib.Path(__file__).parent
RUNS_DIR = BENCHMARK_DIR / "runs"
SYSTEM_PROMPT_FILE = BENCHMARK_DIR / "eval_system_prompt.md"
SAMPLE_IDS_FILE = HARNESS_DIR / "sample_ids.txt"
CONFIG_FILE = HARNESS_DIR / "config.yaml"

SNAPSHOTS = {
    "A": "**Snapshot A — Evening at home:**\nTime: 20:30, Tuesday. Outdoor: 14°C, clear. Occupancy: both adults home, children in bedrooms. Recent events: dinner finished 30 minutes ago, TV on in living room.",
    "B": "**Snapshot B — Morning weekday:**\nTime: 07:15, Wednesday. Outdoor: 9°C, overcast. Occupancy: family home, adults preparing to leave. Recent events: kettle boiled, children's lights on.",
    "C": "**Snapshot C — Away:**\nTime: 14:00, Saturday. Outdoor: 18°C, sunny. Occupancy: nobody home. Recent events: last person left 2 hours ago, alarm armed in away mode.",
    "D": "**Snapshot D — Night:**\nTime: 23:15, Friday. Outdoor: 11°C, light rain. Occupancy: both adults home, children asleep. Recent events: TV off 20 minutes ago.",
}


def load_config(args) -> dict:
    cfg = yaml.safe_load(CONFIG_FILE.read_text())
    if args.model:
        cfg["model"] = args.model
    if args.snapshot:
        cfg["snapshot"] = args.snapshot
    if args.no_sample:
        cfg["sample_only"] = False
    return cfg


def build_system_prompt(snapshot_key: str) -> str:
    raw = SYSTEM_PROMPT_FILE.read_text()
    placeholder = "[INJECT AT EVAL TIME — replace with one of the standard snapshots below]"
    snapshot_text = SNAPSHOTS[snapshot_key]
    return raw.replace(placeholder, snapshot_text)


def load_rows(sample_only: bool) -> list[dict]:
    sample_ids = set()
    if sample_only:
        lines = SAMPLE_IDS_FILE.read_text().splitlines()
        sample_ids = {l.strip() for l in lines if l.strip() and not l.startswith("#")}

    rows = []
    for csv_file in sorted((BENCHMARK_DIR / "data").glob("v0.1_*.csv")):
        with open(csv_file) as fh:
            for row in csv.DictReader(fh):
                if sample_only and row["id"] not in sample_ids:
                    continue
                rows.append(row)

    return rows


def load_existing_ids(run_file: pathlib.Path) -> set[str]:
    if not run_file.exists():
        return set()
    ids = set()
    with open(run_file) as fh:
        for line in fh:
            line = line.strip()
            if line:
                record = json.loads(line)
                if not record.get("parse_error"):
                    ids.add(record["row_id"])
    return ids


def make_run_id(model: str, snapshot: str) -> str:
    model_slug = model.replace(":", "").replace(".", "").replace("-", "").replace("/", "_")
    version = ""
    for line in (BENCHMARK_DIR / "VERSION").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("cmds_hash"):
            version = line.replace(".", "")
            break
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{model_slug}_snapshot{snapshot.lower()}_{version}_{date}"


def parse_response(raw: str) -> tuple[dict | None, bool]:
    """Extract JSON from model response. Returns (parsed_dict, parse_error).

    Handles: plain JSON, JSON in code fences, JSON with explanation text before/after.
    Strategy: find the first '{' and last '}' and attempt to parse that substring.
    """
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, True
    candidate = raw[start : end + 1]
    try:
        return json.loads(candidate), False
    except json.JSONDecodeError:
        return None, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--snapshot")
    parser.add_argument("--no-sample", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args)
    model_name = cfg["model"]
    snapshot = cfg["snapshot"]
    sample_only = cfg["sample_only"]
    retries = cfg.get("retry_on_parse_error", 1)
    timeout = cfg.get("model_timeout_seconds", 60)

    # Version guard
    ok, version, _ = check_version.check()
    if not ok:
        print("ERROR: command column hash mismatch — bump VERSION before running.")
        sys.exit(1)

    system_prompt = build_system_prompt(snapshot)
    rows = load_rows(sample_only)

    if not rows:
        print("ERROR: No rows loaded. Check CSV files and sample_ids.txt.")
        sys.exit(1)

    RUNS_DIR.mkdir(exist_ok=True)
    run_id = make_run_id(model_name, snapshot)
    run_file = RUNS_DIR / f"{run_id}.jsonl"

    if run_file.exists():
        existing = load_existing_ids(run_file)
        if len(existing) >= len(rows):
            print(f"Run already complete: {run_file}")
            sys.exit(0)
        print(f"Resuming run — {len(existing)} rows already written, {len(rows) - len(existing)} remaining.")
    else:
        existing = set()
        print(f"Starting run: {run_id}")

    mode = "sample (42 rows)" if sample_only else f"full ({len(rows)} rows)"
    print(f"Model: {model_name}  |  Snapshot: {snapshot}  |  Data: {version}  |  Mode: {mode}\n")

    with open(run_file, "a") as out:
        for i, row in enumerate(rows):
            row_id = row["id"]
            if row_id in existing:
                continue

            utterance = row["command"]
            attempt = 0
            raw_response = ""
            parsed = None
            parse_error = False

            while attempt <= retries:
                try:
                    raw_response = model_module.call(model_name, system_prompt, utterance, timeout)
                    parsed, parse_error = parse_response(raw_response)
                    if not parse_error:
                        break
                except RuntimeError as e:
                    print(f"  [{row_id}] model error: {e}")
                    parse_error = True
                    break
                attempt += 1

            record = {
                "run_id": run_id,
                "row_id": row_id,
                "category": row["category"],
                "tier": int(row["tier"]),
                "interaction_type": row["interaction_type"],
                "expected_initiative": row["expected_initiative"],
                "expected_action": row["expected_action"],
                "utterance": utterance,
                "model": model_name,
                "snapshot": snapshot,
                "model_raw_response": raw_response,
                "parsed_initiative": parsed.get("initiative") if parsed else None,
                "parsed_action": parsed.get("action") if parsed else None,
                "parsed_clarification": parsed.get("clarification") if parsed else None,
                "parse_error": parse_error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            out.write(json.dumps(record) + "\n")
            out.flush()

            status = "ERR" if parse_error else "OK "
            initiative_match = (
                "✓" if parsed and parsed.get("initiative") == row["expected_initiative"] else "✗"
            ) if not parse_error else "-"
            print(f"  {status} [{row_id}] T{row['tier']} {row['interaction_type']:<10} initiative:{initiative_match}")

    print(f"\nDone. Output: {run_file}")


if __name__ == "__main__":
    main()
