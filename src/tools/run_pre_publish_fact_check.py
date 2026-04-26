"""Run the pre-publish fact-check lane.

Modes:
  extract  -> WordPress draft(s) to contract input JSON.
  detect   -> dry-run stub findings, or Gemini-backed live detection with
              graceful stub fallback when ``--live`` is supplied.
  approve  -> detector JSON to local approval YAML.
  apply    -> approval YAML to proposed diff or live WordPress patch.

``--live`` mode-specific meaning (SAFE BY DEFAULT; omit for dry-run):
  - extract --live: no effect (always read-only WP GET).
  - detect  --live: invokes the Gemini Flash adapter. The adapter enforces
                    ``--max-llm-calls`` per invocation, uses a local cache,
                    and falls back to the dry stub on API/JSON errors.
  - approve --live: no effect (always local YAML I/O).
  - apply   --live: ENABLES WP write. Without this flag, apply only prints the
                    proposed diff and exits. Apply also requires
                    ``--approve-yaml``, valid backup creation, ``approve:true``
                    findings, exact ``find_text`` match, and content-hash match.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.pre_publish_fact_check import approver, detector, extractor
from src.pre_publish_fact_check.applier import ApplyRefusedError, apply_approved_fixes
from src.pre_publish_fact_check.approver import load_yaml
from src.wp_client import WPClient


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP_DIR = ROOT / "backups" / "pre_publish_fact_check"
LIVE_HELP = """Mode-specific live-effect flag. SAFE BY DEFAULT (omit = dry-run).
        - extract --live: no effect (always read-only WP GET).
        - detect  --live: invokes the Gemini Flash adapter with local cache, graceful stub fallback,
                          and per-invocation cap controlled by --max-llm-calls.
        - approve --live: no effect (always local YAML I/O).
        - apply   --live: ENABLES WP write. Without this flag, apply only prints proposed diff and exits.
                          Apply also requires --approve-yaml, valid backup creation, approve:true findings,
                          find_text exact match, and content hash match. ANY refuse condition aborts."""


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _make_wp_client() -> WPClient:
    _load_dotenv_if_available()
    return WPClient()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_pre_publish_fact_check",
        description="Pre-publish fact-check lane with dry stub detection and optional Gemini-backed live detection.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--post-id", type=int, help="Target WordPress post ID.")
    parser.add_argument("--latest-drafts", type=int, help="Fetch latest N drafts ordered by modified desc.")
    parser.add_argument(
        "--mode",
        required=True,
        choices=("extract", "detect", "approve", "apply"),
        help="Lane mode to execute.",
    )
    parser.add_argument("--live", action="store_true", help=LIVE_HELP)
    parser.add_argument(
        "--max-llm-calls",
        type=int,
        default=5,
        help="Maximum Gemini adapter calls per detect invocation when --live is used. Default: 5",
    )
    parser.add_argument("--input-from", help="Path to previous phase output.")
    parser.add_argument("--output", help="Write output to this path instead of stdout.")
    parser.add_argument("--approve-yaml", help="Approval YAML path. Required for apply.")
    parser.add_argument(
        "--backup-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help=f"Backup directory for live apply. Default: {DEFAULT_BACKUP_DIR}",
    )
    return parser.parse_args(argv)


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit_output(text: str, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


def _run_extract(args: argparse.Namespace) -> str:
    if (args.post_id is None) == (args.latest_drafts is None):
        raise ValueError("extract requires exactly one of --post-id or --latest-drafts")
    wp_client = _make_wp_client()
    records = extractor.extract_posts(
        wp_client,
        post_id=args.post_id,
        latest_drafts=args.latest_drafts,
    )
    return json.dumps(records, ensure_ascii=False, indent=2)


def _run_detect(args: argparse.Namespace) -> str:
    if not args.input_from:
        raise ValueError("detect requires --input-from")
    _load_dotenv_if_available()
    extracted_posts = _read_json(args.input_from)
    if not isinstance(extracted_posts, list):
        raise ValueError("detect input must be a JSON list")
    results = detector.detect_posts(
        extracted_posts,
        live=args.live,
        max_llm_calls=args.max_llm_calls,
    )
    return json.dumps(results, ensure_ascii=False, indent=2)


def _run_approve(args: argparse.Namespace) -> str:
    if not args.input_from:
        raise ValueError("approve requires --input-from")
    detector_results = _read_json(args.input_from)
    if not isinstance(detector_results, list):
        raise ValueError("approve input must be a JSON list")
    records = approver.build_approval_records(detector_results)
    return approver.dump_yaml(records)


def _run_apply(args: argparse.Namespace) -> str:
    if args.post_id is None:
        raise ValueError("apply requires --post-id")
    if not args.approve_yaml:
        raise ValueError("apply requires --approve-yaml")
    approval_records = load_yaml(args.approve_yaml)
    wp_client = _make_wp_client()
    result = apply_approved_fixes(
        wp_client=wp_client,
        post_id=args.post_id,
        approval_records=approval_records,
        backup_dir=args.backup_dir,
        live=args.live,
        stderr=sys.stderr,
    )
    if result.diff:
        print(result.diff, file=sys.stderr)
    return json.dumps(result.summary, ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.mode == "extract":
            payload = _run_extract(args)
        elif args.mode == "detect":
            payload = _run_detect(args)
        elif args.mode == "approve":
            payload = _run_approve(args)
        else:
            payload = _run_apply(args)
    except (ApplyRefusedError, NotImplementedError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _emit_output(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
