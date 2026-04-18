#!/usr/bin/env python3
"""SessionStart hook: inject latest tickets + session log as additional context.

Yoshilover 監査役（Claude Code）起動時に
docs/handoff/tickets/OPEN.md と最新の session_logs を自動読み込みする。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TICKETS = REPO_ROOT / "docs" / "handoff" / "tickets" / "OPEN.md"
SESSION_LOGS = REPO_ROOT / "docs" / "handoff" / "session_logs"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"(not found: {path})"
    except Exception as exc:  # noqa: BLE001
        return f"(read error: {path}: {exc})"


def latest_session_log() -> Path | None:
    if not SESSION_LOGS.is_dir():
        return None
    logs = sorted(
        [p for p in SESSION_LOGS.iterdir() if p.is_file() and p.suffix == ".md"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return logs[0] if logs else None


def main() -> int:
    tickets_body = read_text(TICKETS)
    log_path = latest_session_log()
    if log_path is not None:
        log_body = read_text(log_path)
        log_name = log_path.name
    else:
        log_body = "(no session logs found)"
        log_name = "(none)"

    context = (
        "【監査役・起動時自動ロード】\n\n"
        "このリポジトリ（ヨシラバー）では Claude Code は**監査役**として動作する。\n"
        "必ず `CLAUDE.md` のルールに従う:\n"
        "- env変更・deploy・gcloud run services update はやらない（Codexの役割）\n"
        "- 監査発見は tickets/OPEN.md に追記\n"
        "- セッション終了前に session_logs/ を更新\n"
        "- Yoshihiroには選択肢を並べない、1つに絞って推奨（体力減らしモード）\n"
        "\n---\n\n"
        "## 未解決チケット（docs/handoff/tickets/OPEN.md）\n\n"
        f"{tickets_body}\n"
        "\n---\n\n"
        f"## 最新セッションログ（docs/handoff/session_logs/{log_name}）\n\n"
        f"{log_body}\n"
    )

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
