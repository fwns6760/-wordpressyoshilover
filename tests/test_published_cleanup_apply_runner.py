import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import published_cleanup_apply_runner as runner


FIXED_NOW = datetime.fromisoformat("2026-04-26T18:30:00+09:00")
LONG_EXTRA = (
    "試合全体の流れと継投の意味まで追える内容で、打線のつながりや守備面の整理もしやすかった。"
    "ファンが試合の核をつかみやすい情報量を保ち、終盤の判断材料も十分に残っていた。"
)


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    status: str = "publish",
    meta: dict | None = None,
) -> dict:
    return {
        "id": post_id,
        "title": {"raw": title, "rendered": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": "", "rendered": ""},
        "meta": meta or {"article_subtype": "postgame"},
        "modified": "2026-04-26T17:50:00+09:00",
        "date": "2026-04-26T17:40:00+09:00",
        "status": status,
        "link": f"https://yoshilover.com/{post_id}",
        "categories": [],
        "tags": [],
        "featured_media": 12,
    }


def _proposal(post_id: int, title: str, *flags: str) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "repairable_flags": list(flags),
        "proposed_cleanups": [{"flag": flag, "action": flag} for flag in flags],
    }


def _report(*proposals: dict) -> dict:
    return {
        "scan_meta": {"source": "unit-test", "ts": FIXED_NOW.isoformat()},
        "cleanup_proposals": list(proposals),
        "summary": {"with_proposals": len(proposals)},
    }


class FakeWPClient:
    def __init__(self, posts: dict[int, dict]):
        self.posts = {int(post_id): json.loads(json.dumps(post, ensure_ascii=False)) for post_id, post in posts.items()}
        self.get_post_calls: list[int] = []
        self.update_post_fields_calls: list[tuple[int, dict]] = []

    def get_post(self, post_id: int) -> dict:
        self.get_post_calls.append(int(post_id))
        return json.loads(json.dumps(self.posts[int(post_id)], ensure_ascii=False))

    def update_post_fields(self, post_id: int, **fields) -> None:
        self.update_post_fields_calls.append((int(post_id), dict(fields)))
        post = self.posts[int(post_id)]
        if "content" in fields:
            content = fields["content"]
            post["content"] = {"raw": content, "rendered": content}


class PublishedCleanupApplyRunnerTests(unittest.TestCase):
    def _write_input(self, tmpdir: str, payload: dict) -> Path:
        path = Path(tmpdir) / "cleanup_proposals.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _ledger_rows(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_dry_run_no_wp_put(self):
        post = _post(
            401,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。戸郷が7回2失点で試合をつくり、岡本和真が終盤に決勝打を放った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                '<div class="yoshilover-related-posts"><p>関連記事</p></div>'
                "<p>出典: https://example.com/source</p>"
            ),
        )
        wp = FakeWPClient({401: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            result = runner.run_published_cleanup_apply(
                self._write_input(tmpdir, _report(_proposal(401, post["title"]["raw"], "site_component_mixed_into_body"))),
                wp_client=wp,
                ledger_path=ledger_path,
                backup_dir=Path(tmpdir) / "backup",
                now=FIXED_NOW,
            )
            rows = self._ledger_rows(ledger_path)

        self.assertEqual(result["summary"]["dry_run"], 1)
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(rows[0]["status"], "dry_run")

    def test_live_applies_cleanup_to_published_post(self):
        post = _post(
            402,
            "巨人がヤクルトに2-1で勝利",
            (
                "<p>巨人がヤクルトに2-1で勝利した。序盤から丁寧に試合を運び、先発もリズムよく投げ込んだ。</p>"
                f"<p>{LONG_EXTRA}</p>"
                '<div class="yoshilover-related-posts"><p>関連記事</p></div>'
                "<p>出典: https://example.com/source</p>"
            ),
        )
        wp = FakeWPClient({402: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir) / "backup"
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            result = runner.run_published_cleanup_apply(
                self._write_input(tmpdir, _report(_proposal(402, post["title"]["raw"], "site_component_mixed_into_body"))),
                wp_client=wp,
                live=True,
                ledger_path=ledger_path,
                backup_dir=backup_dir,
                now=FIXED_NOW,
            )
            backups = list(backup_dir.glob("*.json"))
            backup_payload = json.loads(backups[0].read_text(encoding="utf-8"))
            rows = self._ledger_rows(ledger_path)

        self.assertEqual(result["summary"]["applied"], 1)
        self.assertEqual(len(wp.update_post_fields_calls), 1)
        update_post_id, fields = wp.update_post_fields_calls[0]
        self.assertEqual(update_post_id, 402)
        self.assertEqual(set(fields.keys()), {"content"})
        self.assertNotIn("yoshilover-related-posts", fields["content"])
        self.assertEqual(len(backups), 1)
        self.assertEqual(backup_payload["id"], 402)
        self.assertIn("meta", backup_payload)
        self.assertEqual(rows[0]["status"], "applied")

    def test_backup_required_before_apply(self):
        post = _post(
            403,
            "巨人が広島に4-2で勝利",
            (
                "<p>巨人が広島に4-2で勝利した。序盤に主導権を握り、終盤まで試合の軸を保った。</p>"
                f"<p>{LONG_EXTRA}</p>"
                '<div class="yoshilover-related-posts"><p>関連記事</p></div>'
                "<p>出典: https://example.com/source</p>"
            ),
        )
        wp = FakeWPClient({403: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            with patch.object(
                runner.cleanup_runner,
                "create_publish_backup",
                side_effect=runner.cleanup_runner.BackupError("boom"),
            ) as backup_mock:
                result = runner.run_published_cleanup_apply(
                    self._write_input(tmpdir, _report(_proposal(403, post["title"]["raw"], "site_component_mixed_into_body"))),
                    wp_client=wp,
                    live=True,
                    ledger_path=ledger_path,
                    backup_dir=Path(tmpdir) / "backup",
                    now=FIXED_NOW,
                )
            rows = self._ledger_rows(ledger_path)

        self.assertEqual(backup_mock.call_count, 1)
        self.assertEqual(result["summary"]["held"], 1)
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(rows[0]["error"], "backup_failed")

    def test_verify_failed_holds_no_wp_put(self):
        post = _post(
            404,
            "巨人が中日に1-0で勝利",
            '<div class="yoshilover-related-posts"><p>関連記事</p></div><p>出典: https://example.com/source</p>',
        )
        wp = FakeWPClient({404: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            result = runner.run_published_cleanup_apply(
                self._write_input(tmpdir, _report(_proposal(404, post["title"]["raw"], "site_component_mixed_into_body"))),
                wp_client=wp,
                live=True,
                ledger_path=ledger_path,
                backup_dir=Path(tmpdir) / "backup",
                now=FIXED_NOW,
            )
            rows = self._ledger_rows(ledger_path)

        self.assertEqual(result["summary"]["held"], 1)
        self.assertEqual(wp.update_post_fields_calls, [])
        self.assertEqual(result["executed"][0]["verify_result"], "prose_lt_100")
        self.assertEqual(rows[0]["status"], "held")

    def test_max_burst_enforced(self):
        posts = {}
        proposals = []
        for index in range(12):
            post_id = 500 + index
            title = f"巨人が第{index + 1}戦に勝利"
            posts[post_id] = _post(
                post_id,
                title,
                (
                    f"<p>{title}。攻守ともに流れが整理され、勝敗を分けた場面も明確だった。</p>"
                    f"<p>{LONG_EXTRA}</p>"
                    '<div class="yoshilover-related-posts"><p>関連記事</p></div>'
                    "<p>出典: https://example.com/source</p>"
                ),
            )
            proposals.append(_proposal(post_id, title, "site_component_mixed_into_body"))
        wp = FakeWPClient(posts)

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            result = runner.run_published_cleanup_apply(
                self._write_input(tmpdir, _report(*proposals)),
                wp_client=wp,
                ledger_path=ledger_path,
                backup_dir=Path(tmpdir) / "backup",
                max_burst=10,
                now=FIXED_NOW,
            )
            rows = self._ledger_rows(ledger_path)

        self.assertEqual(result["summary"]["dry_run"], 10)
        self.assertEqual(result["summary"]["skipped"], 2)
        self.assertEqual([item["error"] for item in result["executed"][-2:]], ["burst_cap", "burst_cap"])
        self.assertEqual(len(rows), 12)

    def test_ledger_records_each_attempt(self):
        site_component_post = _post(
            601,
            "巨人がDeNAに5-3で勝利",
            (
                "<p>巨人がDeNAに5-3で勝利した。中盤に流れを引き戻し、終盤の継投も整理されていた。</p>"
                f"<p>{LONG_EXTRA}</p>"
                '<div class="yoshilover-related-posts"><p>関連記事</p></div>'
                "<p>出典: https://example.com/source</p>"
            ),
        )
        already_clean_post = _post(
            602,
            "巨人が楽天に3-1で勝利",
            (
                "<p>巨人が楽天に3-1で勝利した。試合の核が最初から見え、攻守ともに流れを追いやすかった。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>出典: https://example.com/source</p>"
            ),
        )
        wp = FakeWPClient({601: site_component_post, 602: already_clean_post})

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            runner.run_published_cleanup_apply(
                self._write_input(
                    tmpdir,
                    _report(
                        _proposal(601, site_component_post["title"]["raw"], "site_component_mixed_into_body"),
                        _proposal(602, already_clean_post["title"]["raw"], "site_component_mixed_into_body"),
                    ),
                ),
                wp_client=wp,
                ledger_path=ledger_path,
                backup_dir=Path(tmpdir) / "backup",
                now=FIXED_NOW,
            )
            rows = self._ledger_rows(ledger_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["post_id"] for row in rows], [601, 602])
        self.assertEqual([row["status"] for row in rows], ["dry_run", "skipped"])

    def test_proposals_skip_post_without_changes(self):
        post = _post(
            603,
            "巨人が西武に4-0で勝利",
            (
                "<p>巨人が西武に4-0で勝利した。先発が序盤から流れをつくり、打線も好機を逃さなかった。</p>"
                f"<p>{LONG_EXTRA}</p>"
                "<p>出典: https://example.com/source</p>"
            ),
        )
        wp = FakeWPClient({603: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            with patch.object(runner.cleanup_runner, "create_publish_backup") as backup_mock:
                result = runner.run_published_cleanup_apply(
                    self._write_input(tmpdir, _report(_proposal(603, post["title"]["raw"], "site_component_mixed_into_body"))),
                    wp_client=wp,
                    live=True,
                    ledger_path=ledger_path,
                    backup_dir=Path(tmpdir) / "backup",
                    now=FIXED_NOW,
                )

        self.assertFalse(backup_mock.called)
        self.assertEqual(result["summary"]["skipped"], 1)
        self.assertEqual(result["executed"][0]["error"], "no_content_changes")
        self.assertEqual(wp.update_post_fields_calls, [])

    def test_re_apply_dedup_skips_already_cleaned(self):
        post = _post(
            604,
            "巨人がオリックスに6-2で勝利",
            (
                "<p>巨人がオリックスに6-2で勝利した。打線が中盤に畳みかけ、守備も最後まで安定していた。</p>"
                f"<p>{LONG_EXTRA}</p>"
                '<div class="yoshilover-related-posts"><p>関連記事</p></div>'
                "<p>出典: https://example.com/source</p>"
            ),
        )
        wp = FakeWPClient({604: post})

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "ledger.jsonl"
            ledger_path.write_text(
                json.dumps(
                    {
                        "post_id": 604,
                        "ts": "2026-04-26T17:00:00+09:00",
                        "status": "applied",
                        "live": True,
                        "cleanup_flags": ["site_component_mixed_into_body"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = runner.run_published_cleanup_apply(
                self._write_input(tmpdir, _report(_proposal(604, post["title"]["raw"], "site_component_mixed_into_body"))),
                wp_client=wp,
                live=True,
                ledger_path=ledger_path,
                backup_dir=Path(tmpdir) / "backup",
                now=FIXED_NOW,
            )

        self.assertEqual(result["summary"]["skipped"], 1)
        self.assertEqual(result["executed"][0]["error"], "already_applied")
        self.assertEqual(wp.get_post_calls, [])
        self.assertEqual(wp.update_post_fields_calls, [])


if __name__ == "__main__":
    unittest.main()
