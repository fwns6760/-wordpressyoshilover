"""One-shot roster expansion script.

NOMOTOKE-INTAKE-ROSTER-EXPAND-001
=================================

Fetches NPB.jp's Giants 1軍 + 2軍 batting + pitching stat tables and
merges every player name found into ``config/giants_roster.json``.
Existing entries are NEVER modified — only NEW names land as
``role=player`` with their position derived from the table source
(投手 / 打者 → 内野手・外野手・捕手 ambiguity is left as ``打者``).

Source-only contract: every name written to roster.json is a literal
substring of the NPB.jp HTML response. No LLM, no fabrication.

Usage:
    python3 -m src.tools.expand_roster_from_npb
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import urllib.request


JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent.parent
ROSTER_PATH = ROOT / "config" / "giants_roster.json"


def _fetch(url: str) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; yoshilover-roster-expand/1)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(800_000).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"fetch_failed url={url} err={exc}", file=sys.stderr)
        return ""


def _parse_names_from_html(html: str) -> list[tuple[str, str]]:
    """Return [(rendered_name, jersey_number)] from a parsed stats table.

    Reuses ``parse_npb_team_stats_html``. Jersey number is read from the
    ``背番号`` column when present; empty otherwise.
    """
    if not html:
        return []
    sys.path.insert(0, str(ROOT))
    from src.source_npb_team_stats_extractor import parse_npb_team_stats_html

    parsed = parse_npb_team_stats_html(html)
    if not parsed:
        return []
    out: list[tuple[str, str]] = []
    for normalized_name, record in parsed.items():
        rendered = record.get("__rendered_name__") or normalized_name
        jersey = (record.get("背番号") or "").strip()
        out.append((rendered.strip(), jersey))
    return out


def main() -> int:
    year = datetime.now(JST).year
    sources = [
        (f"https://npb.jp/bis/{year}/stats/idb1_g.html", "打者", "player"),
        (f"https://npb.jp/bis/{year}/stats/idp1_g.html", "投手", "player"),
        (f"https://npb.jp/bis/{year}/stats/idb2_g.html", "打者", "player"),
        (f"https://npb.jp/bis/{year}/stats/idp2_g.html", "投手", "player"),
    ]
    discovered: dict[str, dict[str, str]] = {}
    for url, position, role in sources:
        names = _parse_names_from_html(_fetch(url))
        for rendered, jersey in names:
            if not rendered:
                continue
            if rendered in discovered:
                # Prefer pitcher position when both batting and pitching
                # tables include the same name (rare for two-way players).
                if position == "投手":
                    discovered[rendered]["position"] = "投手"
                continue
            discovered[rendered] = {
                "position": position,
                "jersey_number": jersey,
                "role": role,
            }
    print(f"discovered_count={len(discovered)}")

    if not ROSTER_PATH.exists():
        print(f"roster file missing: {ROSTER_PATH}", file=sys.stderr)
        return 2
    existing = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    if not isinstance(existing, list):
        print("roster file is not a list", file=sys.stderr)
        return 2

    existing_names = {(e.get("name") or "").strip() for e in existing}
    added = 0
    for rendered, meta in discovered.items():
        if rendered in existing_names:
            continue
        existing.append(
            {
                "name": rendered,
                "aliases": [rendered],
                "role": meta["role"],
                "position": meta["position"],
                "jersey_number": meta["jersey_number"],
                "active": True,
            }
        )
        added += 1
    print(f"added_count={added}")
    if added:
        ROSTER_PATH.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
