from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.viral_topic_detector import (  # noqa: E402
    JST,
    build_topic_candidate,
    classify_expected_subtype,
    cross_reference_official_sources,
    fetch_yahoo_news_baseball_ranking,
    fetch_yahoo_realtime_search_giants,
    has_spam_marker,
    is_giants_related_signal,
    load_fetcher_history,
)


DEFAULT_OUT_DIR = ROOT / "logs" / "viral_topics_dry_run"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 src/tools/run_viral_topic_dry_run.py",
        description="Dry-run Yahoo-based giants topic detection without publish side effects.",
    )
    parser.add_argument("--max-candidates", type=int, default=10, help="Maximum number of candidates to write.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="JSONL output directory.")
    parser.add_argument(
        "--history-window-hours",
        type=int,
        default=24,
        help="Fetcher history window used for source confirmation.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    fetcher_history = load_fetcher_history()

    candidates = _collect_candidates(
        max_candidates=max(int(args.max_candidates or 0), 0),
        fetcher_history=fetcher_history,
        history_window_hours=max(int(args.history_window_hours or 0), 0),
    )

    output_path = out_dir / f"{_today_key()}.jsonl"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as handle:
            for candidate in candidates:
                handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    sys.stdout.write(
        json.dumps(
            {
                "output_path": str(output_path),
                "written": len(candidates),
                "publish_blocked": True,
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


def _collect_candidates(
    *,
    max_candidates: int,
    fetcher_history: dict[str, Any] | None,
    history_window_hours: int,
) -> list[dict[str, Any]]:
    if max_candidates <= 0:
        return []

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_rows = (
        ("yahoo_realtime_search", fetch_yahoo_realtime_search_giants()),
        ("yahoo_news_ranking", fetch_yahoo_news_baseball_ranking()),
    )

    for source, rows in source_rows:
        for raw_signal in rows:
            if len(collected) >= max_candidates:
                return collected
            signature = _candidate_signature(source, raw_signal)
            if signature in seen:
                continue
            seen.add(signature)
            if has_spam_marker(_signal_text(raw_signal)):
                continue

            candidate = build_topic_candidate(raw_signal, source)
            if not is_giants_related_signal(raw_signal, source):
                candidate["skip_reason"] = "not_giants_related"
                candidate["next_action"] = "discard"
                collected.append(candidate)
                continue

            subtype, confidence = classify_expected_subtype(
                str(raw_signal.get("keyword") or ""),
                title=str(raw_signal.get("title") or ""),
            )
            candidate["expected_subtype"] = subtype
            candidate["subtype_confidence"] = confidence
            candidate["source_confirmation"] = cross_reference_official_sources(
                str(raw_signal.get("keyword") or raw_signal.get("title") or ""),
                fetcher_history,
                history_window_hours=history_window_hours,
            )

            if subtype is None or confidence == "unresolved":
                candidate["skip_reason"] = "subtype_unresolved"
                candidate["next_action"] = "default_review"
            elif not bool(candidate["source_confirmation"].get("confirmed")):
                candidate["next_action"] = "default_review"
            else:
                candidate["next_action"] = "candidate_for_existing_subtype"

            collected.append(candidate)

    return collected


def _candidate_signature(source: str, raw_signal: dict[str, Any]) -> str:
    return "|".join(
        [
            source,
            str(raw_signal.get("keyword") or ""),
            str(raw_signal.get("title") or ""),
            str(raw_signal.get("url") or ""),
        ]
    )


def _signal_text(raw_signal: dict[str, Any]) -> str:
    return " ".join(
        str(raw_signal.get(field) or "")
        for field in ("keyword", "title", "context_excerpt", "url")
    )


def _today_key() -> str:
    from datetime import datetime

    return datetime.now(JST).strftime("%Y-%m-%d")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
