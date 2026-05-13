"""event_key_publish_gate.py — pure decision library (no WP I/O).

Given a candidate article (title + publish-attribution time) and a list
of already-published articles in the relevant time window, decide
whether the candidate should be **published immediately** (it would be
the parent of a new event_key) or **held as draft** (a sibling parent
already exists for this event_key).

This file deliberately does **not** import the WP client or call any
side-effecting code. It is a pure library used by:

* the publish pipeline (when D-2 is enabled by user judgment), to gate
  status=publish vs status=draft, and
* tests / dry-run tooling, to verify the decision logic in isolation.

Wiring this gate into the publish pipeline is a production
side-effect change and must remain a user judgment item (§11). The
intent here is to have the decision function landed and tested so
flipping the wire is a small, observable change later.

CLI::

    python3 -m src.event_key_publish_gate \\
        --candidate-title "佐々木俊輔「最高です！」" \\
        --candidate-date 2026-05-12T22:00:00 \\
        --recent-json /path/to/recent_publishes.json

prints a JSON ``{"decision": "publish"|"hold", "reason": ..., ...}``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import event_key_ledger as ekl  # noqa: E402


# Subtypes that warrant publish-gating. Pre-game team-level events
# (lineup_pre / lineup_post) and orphans should *never* be held — they
# carry time-sensitive information and don't merge with a parent.
GATEABLE_SUBTYPES = {
    "walk_off",
    "homerun",
    "decisive_hit",
    "starting_pitcher",
    "relief",
    "home_visit",
    "debut_milestone",
    "record_milestone",
    "lineup_role",
    "generic",  # bare quotes that get absorbed into a primary event
}


@dataclass
class GateDecision:
    decision: str  # "publish" or "hold"
    reason: str
    event_key: str
    event_player: str
    event_subtype: str
    candidate_post_id: int | None = None
    existing_parent_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "event_key": self.event_key,
            "event_player": self.event_player,
            "event_subtype": self.event_subtype,
            "candidate_post_id": self.candidate_post_id,
            "existing_parent_id": self.existing_parent_id,
        }


def _compute_event_key_for_record(rec: ekl.PostRecord) -> tuple[str, str, str, str, str]:
    """Return ``(game_date, opponent, event_player, event_subtype, full_key)``
    for a candidate record. Mirrors the grouping rules in event_key_ledger
    but is single-record (no day-level context like inferred opponent or
    generic-merge primary subtype)."""
    if not ekl.has_giants_game_context(rec):
        return (rec.game_date or "undated", rec.opponent or "none", "", "orphan", "")
    if rec.event_type in ekl.LINEUP_EVENT_TYPES:
        ep = "team"
        sub = rec.event_type
    else:
        ep = ekl.derive_event_player(rec)
        sub = ekl.derive_event_subtype(rec.title)
    full = ekl._make_event_key(
        rec.game_date or "undated",
        rec.opponent or "none",
        ep,
        sub,
    )
    return (rec.game_date or "undated", rec.opponent or "none", ep, sub, full)


def decide_publish_or_hold(
    candidate: dict,
    *,
    recent_publishes: list[dict],
) -> GateDecision:
    """Decide whether ``candidate`` (a WP post-shaped dict with at least
    ``date`` and ``title``) should be published or held as draft.

    Algorithm
    ---------
    1. Build a ``PostRecord`` for the candidate; compute its event_key.
    2. If the candidate's subtype is *not* in :data:`GATEABLE_SUBTYPES`
       (lineup_pre / lineup_post / orphan / team events), always
       ``publish`` — these are time-sensitive and have no parent
       merging semantics.
    3. Build records for ``recent_publishes`` and compute the same
       event_key for each. If any recent-publish shares the candidate's
       event_key (or, for generic candidates, shares
       ``(game_date, opponent, event_player)``), the candidate is a
       child of an existing parent → ``hold``.
    4. Otherwise the candidate is the **first** record of its event_key
       and becomes the parent → ``publish``.

    The day-level "generic absorbs into the player's primary subtype"
    rule is approximated here by matching by ``(date, opponent, player)``
    when the candidate is generic — that way 「大城卓三「風に乗ってくれま
    した」」 (generic) is held as a child of an already-published
    「大城+homerun」 parent. We can't replay the full grouping pipeline
    inside a per-article gate, so this approximation is conservative
    (more likely to hold than to publish).
    """
    cand_rec = ekl.post_to_record(candidate)
    cand_date, cand_opp, cand_ep, cand_sub, cand_full = _compute_event_key_for_record(cand_rec)

    if cand_sub not in GATEABLE_SUBTYPES:
        return GateDecision(
            decision="publish",
            reason=f"non_gateable_subtype:{cand_sub}",
            event_key=cand_full,
            event_player=cand_ep,
            event_subtype=cand_sub,
            candidate_post_id=cand_rec.post_id or None,
        )

    if not cand_ep:
        return GateDecision(
            decision="publish",
            reason="no_event_player_detected",
            event_key=cand_full,
            event_player=cand_ep,
            event_subtype=cand_sub,
            candidate_post_id=cand_rec.post_id or None,
        )

    for existing in recent_publishes:
        ex_rec = ekl.post_to_record(existing)
        ex_date, ex_opp, ex_ep, ex_sub, ex_full = _compute_event_key_for_record(ex_rec)
        if ex_full == cand_full:
            return GateDecision(
                decision="hold",
                reason="parent_exists_same_event_key",
                event_key=cand_full,
                event_player=cand_ep,
                event_subtype=cand_sub,
                candidate_post_id=cand_rec.post_id or None,
                existing_parent_id=ex_rec.post_id or None,
            )
        # generic candidate → also held if any recent publish shares
        # (date, opponent, player) with a non-generic subtype (because
        # the day-level grouping would merge generic into that primary).
        if cand_sub == "generic" and ex_sub != "generic" and ex_sub in GATEABLE_SUBTYPES:
            if (ex_date, ex_opp, ex_ep) == (cand_date, cand_opp, cand_ep):
                return GateDecision(
                    decision="hold",
                    reason=f"generic_absorbs_into:{ex_sub}",
                    event_key=cand_full,
                    event_player=cand_ep,
                    event_subtype=cand_sub,
                    candidate_post_id=cand_rec.post_id or None,
                    existing_parent_id=ex_rec.post_id or None,
                )

    return GateDecision(
        decision="publish",
        reason="first_record_of_event_key",
        event_key=cand_full,
        event_player=cand_ep,
        event_subtype=cand_sub,
        candidate_post_id=cand_rec.post_id or None,
    )


# ─── CLI for ad-hoc decision lookups ────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="event_key publish-gate decision (pure, no WP I/O).")
    p.add_argument("--candidate-title", required=True)
    p.add_argument("--candidate-date", required=True, help="ISO datetime, e.g. 2026-05-12T22:00:00")
    p.add_argument("--candidate-post-id", type=int, default=0)
    p.add_argument(
        "--recent-json",
        required=True,
        help="Path to a JSON array of recent published-post dicts (id/date/title minimum).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    recent = json.loads(Path(args.recent_json).read_text(encoding="utf-8"))
    candidate = {
        "id": args.candidate_post_id,
        "date": args.candidate_date,
        "title": {"rendered": args.candidate_title},
        "categories": [],
        "link": "",
    }
    decision = decide_publish_or_hold(candidate, recent_publishes=recent)
    print(json.dumps(decision.to_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
