import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src import long_body_compression_audit as audit
from src.tools import run_long_body_audit as cli
from src.tools.draft_body_editor import _extract_prose_text


FIXED_NOW = datetime.fromisoformat("2026-04-26T09:00:00+09:00")


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    modified: str = "2026-04-26T08:00:00+09:00",
    date: str = "2026-04-26T07:00:00+09:00",
    meta: dict | None = None,
) -> dict:
    payload = {
        "id": post_id,
        "title": {"raw": title, "rendered": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": "", "rendered": ""},
        "status": "draft",
        "date": date,
        "modified": modified,
        "link": f"https://yoshilover.com/{post_id}",
        "featured_media": 10,
        "categories": [],
        "tags": [],
    }
    if meta is not None:
        payload["meta"] = meta
    return payload


def _paragraphs(text: str, count: int) -> str:
    return "".join(f"<p>{text}</p>" for _ in range(count))


def _lineup_body() -> str:
    core = _paragraphs(
        "巨人の先発オーダーは守備位置と打順の並びが確認でき、試合前に押さえるべき情報が一つずつ整理されている。",
        63,
    )
    lineup_once = "".join(f"<p>{idx}番 選手{idx} 守備位置{idx}</p>" for idx in range(1, 10))
    lineup_twice = "".join(f"<p>{idx}番 選手{idx} 守備位置{idx}</p>" for idx in range(1, 10))
    ai_tone = "<p>💬 このニュース、どう見る？</p><p>初回の入りが鍵になりそうです。</p>"
    generality = "<p>元記事で確認できる範囲をそのまま押さえておきたいところです。</p>"
    related = (
        '<div class="yoshilover-related-posts">'
        "<p>【関連記事】</p>"
        "<p>巨人の前日スタメン振り返り</p>"
        "<p>巨人の打順比較メモ</p>"
        "</div>"
    )
    twitter = (
        "<p>https://x.com/example/status/1911111111111111111</p>"
        "<p>https://twitter.com/example/status/1911111111111111112</p>"
    )
    source = "<p>参照元: スポーツ報知 https://example.com/source-lineup</p>"
    return core + lineup_once + lineup_twice + ai_tone + generality + related + twitter + source


def _comment_body() -> str:
    quote = "阿部監督は打線のつながりと継投の細部まで丁寧に振り返り、交代の意図と終盤の判断を詳しく説明した。"
    source = "<p>参照元: スポーツ報知 https://example.com/source-comment</p>"
    return _paragraphs(quote, 44) + source


def _postgame_body() -> str:
    line = "巨人が阪神に3-2で勝利し、終盤の追加点と継投の順番まで振り返れる試合内容だった。"
    source = "<p>参照元: スポーツ報知 https://example.com/source-postgame</p>"
    return _paragraphs(line, 24) + source


def _notice_body() -> str:
    line = "浅野翔吾の一軍合流は守備位置と役割の確認を中心にまとまっており、告知として十分に簡潔だった。"
    source = "<p>参照元: スポーツ報知 https://example.com/source-notice</p>"
    return _paragraphs(line, 12) + source


def _program_body() -> str:
    line = "GIANTS TVの放送情報は日時と出演者がすぐ分かる簡潔な構成だった。"
    source = "<p>参照元: スポーツ報知 https://example.com/source-program</p>"
    return _paragraphs(line, 3) + source


def _probable_starter_body() -> str:
    line = "予告先発は登板間隔と相手打線の相性まで整理され、翌日の見どころが短くまとまっていた。"
    source = "<p>参照元: スポーツ報知 https://example.com/source-probable</p>"
    return _paragraphs(line, 12) + source


def _injury_body() -> str:
    line = "主力の故障離脱について現状確認と復帰時期の見通しを簡潔に整理している。"
    source = "<p>参照元: スポーツ報知 https://example.com/source-injury</p>"
    return _paragraphs(line, 5) + source


class StrictReadOnlyWPClient:
    def __init__(self, pages: dict[int, list[dict]]):
        self.pages = pages
        self.list_posts_calls: list[dict] = []
        self.get_post_calls: list[int] = []
        self.write_attempted = False

    def list_posts(self, **kwargs):
        self.list_posts_calls.append(dict(kwargs))
        page = int(kwargs.get("page", 1))
        return json.loads(json.dumps(self.pages.get(page, []), ensure_ascii=False))

    def get_post(self, post_id: int):
        self.get_post_calls.append(int(post_id))
        raise AssertionError("get_post should not be needed for this audit")

    def update_post_fields(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")

    def update_post_status(self, *args, **kwargs):
        self.write_attempted = True
        raise AssertionError("write path must not be called")


class LongBodyCompressionAuditTests(unittest.TestCase):
    def setUp(self):
        self.program = _post(801, "GIANTS TVで試合前特番を放送", _program_body())
        self.notice = _post(802, "浅野翔吾が一軍合流へ", _notice_body())
        self.probable = _post(803, "巨人の予告先発は山崎伊織", _probable_starter_body())
        self.postgame = _post(804, "巨人が阪神に3-2で勝利", _postgame_body())
        self.comment = _post(805, '阿部監督「打線がつながった」 試合後の振り返り', _comment_body())
        self.lineup = _post(806, "巨人スタメン 4月26日阪神戦 先発オーダー", _lineup_body())
        self.injury = _post(807, "主力が故障で離脱", _injury_body())

    def test_audit_raw_posts_builds_distribution_axes_and_classification(self):
        posts = [
            self.program,
            self.notice,
            self.probable,
            self.postgame,
            self.comment,
            self.lineup,
            self.injury,
        ]

        report = audit.audit_raw_posts(posts, window_hours=72, max_pool=20, now=FIXED_NOW)

        expected_distribution = audit._empty_distribution()
        for post in posts:
            prose_len = len(_extract_prose_text(post["content"]["raw"]))
            expected_distribution[audit._bucket_label(prose_len)] += 1

        self.assertEqual(report["scan_meta"]["scanned"], 7)
        self.assertEqual(report["prose_length_distribution"], expected_distribution)
        self.assertEqual(report["by_subtype"]["lineup"], {"count": 1, "over_limit": 1, "compressible": 1, "exclude": 0})
        self.assertEqual(report["by_subtype"]["comment"], {"count": 1, "over_limit": 1, "compressible": 0, "exclude": 1})
        self.assertEqual(report["by_subtype"]["injury"]["count"], 1)
        self.assertEqual(report["summary"]["over_limit_total"], 2)
        self.assertEqual(report["summary"]["compressible_total"], 1)
        self.assertEqual(report["summary"]["exclude_total"], 1)
        self.assertEqual(report["summary"]["injury_hold_count"], 1)

        compressible = report["compressible_candidates"][0]
        self.assertEqual(compressible["post_id"], 806)
        self.assertGreater(compressible["prose_len"], compressible["limit"])
        self.assertLessEqual(compressible["estimated_after_compress"], compressible["limit"])
        self.assertEqual(
            set(compressible["compress_targets"]),
            {"ai_tone", "related_articles", "twitter_url", "lineup_duplication", "generality"},
        )

        excluded = report["exclude_candidates"][0]
        self.assertEqual(excluded["post_id"], 805)
        self.assertEqual(excluded["reason"], "no_safe_compression_target")

        axis_counts = report["summary"]["structure_axes"]
        for axis in ("ai_tone", "related_articles", "twitter_url", "lineup_duplication", "generality"):
            self.assertEqual(axis_counts[axis]["posts"], 1)
            self.assertGreater(axis_counts[axis]["hits"], 0)
            self.assertGreater(axis_counts[axis]["chars"], 0)

    def test_scan_wp_drafts_paginates_and_uses_get_only(self):
        body = _notice_body()
        page_one = [_post(9000 + index, f"下書き {index} 合流", body) for index in range(100)]
        page_two = [_post(9101, "追加の下書き 合流", body)]
        wp = StrictReadOnlyWPClient({1: page_one, 2: page_two})

        report = audit.scan_wp_drafts(
            wp,
            window_hours=72,
            max_pool=101,
            now=FIXED_NOW,
        )

        self.assertEqual(report["scan_meta"]["fetched"], 101)
        self.assertEqual(report["scan_meta"]["scanned"], 101)
        self.assertEqual([call["page"] for call in wp.list_posts_calls], [1, 2])
        self.assertEqual([call["per_page"] for call in wp.list_posts_calls], [100, 1])
        self.assertTrue(all(call["status"] == "draft" for call in wp.list_posts_calls))
        self.assertEqual(wp.get_post_calls, [])
        self.assertFalse(wp.write_attempted)

    def test_render_human_report_shows_distribution_policy_and_candidates(self):
        report = audit.audit_raw_posts(
            [self.program, self.notice, self.probable, self.postgame, self.comment, self.lineup, self.injury],
            now=FIXED_NOW,
        )

        rendered = audit.render_human_report(report)

        self.assertIn("Long Body Compression Audit", rendered)
        self.assertIn("Prose Length Distribution", rendered)
        self.assertIn("Structure Axes (over-limit drafts only)", rendered)
        self.assertIn("Subtype Policy", rendered)
        self.assertIn("Compressible Candidates", rendered)
        self.assertIn("806 | lineup |", rendered)
        self.assertIn("injury_hold_count", rendered)

    def test_cli_main_writes_json_output_without_wp_write(self):
        report = audit.audit_raw_posts([self.lineup, self.comment], now=FIXED_NOW)
        fake_wp = StrictReadOnlyWPClient({})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "audit.json"
            with patch.object(cli, "_make_wp_client", return_value=fake_wp), patch.object(
                cli, "scan_wp_drafts", return_value=report
            ):
                exit_code = cli.main(
                    [
                        "--window-hours",
                        "72",
                        "--max-pool",
                        "200",
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    ]
                )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["compressible_total"], 1)
        self.assertEqual(payload["summary"]["exclude_total"], 1)
        self.assertFalse(fake_wp.write_attempted)

    def test_cli_main_prints_human_output_to_stdout(self):
        report = audit.audit_raw_posts([self.lineup], now=FIXED_NOW)
        stdout = io.StringIO()

        with patch.object(cli, "_make_wp_client"), patch.object(cli, "scan_wp_drafts", return_value=report), patch(
            "sys.stdout", stdout
        ):
            exit_code = cli.main(["--window-hours", "72", "--max-pool", "200", "--format", "human"])

        self.assertEqual(exit_code, 0)
        rendered = stdout.getvalue()
        self.assertIn("Long Body Compression Audit", rendered)
        self.assertIn("Compressible Candidates", rendered)


if __name__ == "__main__":
    unittest.main()
