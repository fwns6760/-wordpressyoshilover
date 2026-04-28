"""Local cost report helper for llm_cost structured logs.

Production source of truth is Cloud Logging / BigQuery. This helper is mainly
for dev/test and for summarizing log exports.

Examples:
  python3 -m src.tools.run_llm_cost_report --since 24h --by lane
  python3 -m src.tools.run_llm_cost_report --since 1h --by call_site,model
  python3 -m src.tools.run_llm_cost_report --input /tmp/llm_cost.json --by lane
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_INPUT = Path("logs/llm_cost_local.jsonl")
DEFAULT_GROUP_KEYS = ("lane",)


@dataclass(frozen=True)
class ReportRow:
    group: tuple[str, ...]
    calls: int
    total_cost_jpy: float
    avg_input_chars: float
    avg_output_chars: float


def parse_since_window(value: str) -> timedelta:
    text = value.strip().lower()
    unit = text[-1:]
    amount = int(text[:-1])
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise ValueError(f"unsupported --since value: {value}")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if len(normalized) >= 5 and normalized[-5] in {"+", "-"} and normalized[-3] != ":":
        normalized = normalized[:-2] + ":" + normalized[-2:]
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_json_records(path: Path) -> list[Any]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []

    records: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _coerce_event(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None

    if record.get("event") == "llm_cost":
        return record

    payload = record.get("jsonPayload")
    if not isinstance(payload, dict) or payload.get("event") != "llm_cost":
        return None

    merged = dict(payload)
    if "timestamp" not in merged and isinstance(record.get("timestamp"), str):
        merged["timestamp"] = record["timestamp"]
    return merged


def load_llm_cost_events(path: str | Path) -> list[dict[str, Any]]:
    records = _read_json_records(Path(path))
    events: list[dict[str, Any]] = []
    for record in records:
        event = _coerce_event(record)
        if event is not None:
            events.append(event)
    return events


def filter_events_since(
    events: Iterable[dict[str, Any]],
    since: timedelta | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if since is None:
        return list(events)

    current = now or datetime.now(timezone.utc)
    threshold = current - since
    filtered: list[dict[str, Any]] = []
    for event in events:
        parsed = _parse_timestamp(event.get("timestamp"))
        if parsed is None:
            continue
        if parsed.astimezone(timezone.utc) >= threshold.astimezone(timezone.utc):
            filtered.append(event)
    return filtered


def aggregate_events(
    events: Iterable[dict[str, Any]],
    group_keys: tuple[str, ...],
) -> list[ReportRow]:
    buckets: dict[tuple[str, ...], dict[str, float]] = {}
    for event in events:
        key = tuple(str(event.get(group_key) or "") for group_key in group_keys)
        bucket = buckets.setdefault(
            key,
            {
                "calls": 0.0,
                "total_cost_jpy": 0.0,
                "input_chars": 0.0,
                "output_chars": 0.0,
            },
        )
        bucket["calls"] += 1
        bucket["total_cost_jpy"] += float(event.get("estimated_cost_jpy") or 0.0)
        bucket["input_chars"] += float(event.get("input_chars") or 0.0)
        bucket["output_chars"] += float(event.get("output_chars") or 0.0)

    rows: list[ReportRow] = []
    for key, bucket in sorted(buckets.items()):
        calls = int(bucket["calls"])
        avg_input = bucket["input_chars"] / calls if calls else 0.0
        avg_output = bucket["output_chars"] / calls if calls else 0.0
        rows.append(
            ReportRow(
                group=key,
                calls=calls,
                total_cost_jpy=round(bucket["total_cost_jpy"], 4),
                avg_input_chars=round(avg_input, 2),
                avg_output_chars=round(avg_output, 2),
            )
        )
    return rows


def format_tsv(rows: Iterable[ReportRow], group_keys: tuple[str, ...]) -> str:
    header = [
        *group_keys,
        "calls",
        "total_cost_jpy",
        "avg_input_chars",
        "avg_output_chars",
    ]
    lines = ["\t".join(header)]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    *row.group,
                    str(row.calls),
                    f"{row.total_cost_jpy:.4f}",
                    f"{row.avg_input_chars:.2f}",
                    f"{row.avg_output_chars:.2f}",
                ]
            )
        )
    return "\n".join(lines)


def _parse_group_keys(value: str) -> tuple[str, ...]:
    keys = tuple(part.strip() for part in value.split(",") if part.strip())
    if not keys:
        raise ValueError("--by must contain at least one field")
    return keys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_llm_cost_report")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--since", default=None)
    parser.add_argument("--by", default="lane")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    group_keys = _parse_group_keys(args.by)
    since = parse_since_window(args.since) if args.since else None
    events = load_llm_cost_events(args.input)
    filtered = filter_events_since(events, since)
    rows = aggregate_events(filtered, group_keys)
    print(format_tsv(rows, group_keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Production usage:
#   gcloud logging read 'jsonPayload.event="llm_cost"' --format=json > /tmp/llm_cost.json
#   python3 -m src.tools.run_llm_cost_report --input /tmp/llm_cost.json --by lane
# Future preferred path:
#   export llm_cost logs to BigQuery and aggregate with SQL.
