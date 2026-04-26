import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import mail_delivery_bridge
from src import x_dry_run_mail_builder as builder
from src.tools import run_x_dry_run_mail as cli


FIXED_NOW = datetime.fromisoformat("2026-04-26T21:15:00+09:00")


def _post(
    post_id: int,
    title: str,
    body_html: str,
    *,
    category_ids: list[int],
    excerpt: str = "",
    status: str = "publish",
    featured_media: int = 10,
) -> dict:
    return {
        "id": post_id,
        "title": {"raw": title, "rendered": title},
        "excerpt": {"raw": excerpt, "rendered": excerpt},
        "content": {"raw": body_html, "rendered": body_html},
        "status": status,
        "date": "2026-04-26T20:00:00+09:00",
        "modified": "2026-04-26T20:05:00+09:00",
        "link": f"https://yoshilover.com/archives/{post_id}/",
        "featured_media": featured_media,
        "meta": {"article_subtype": "postgame"},
        "categories": category_ids,
        "tags": [],
    }


class FakeWPClient:
    def __init__(self, posts: list[dict], categories: list[dict] | None = None):
        self._posts = posts
        self._categories = categories or [
            {"id": 663, "name": "試合速報", "slug": "game"},
            {"id": 664, "name": "選手情報", "slug": "player"},
            {"id": 665, "name": "首脳陣", "slug": "manager"},
            {"id": 666, "name": "球団情報", "slug": "club"},
        ]
        self.list_posts_calls: list[dict] = []
        self.get_categories_calls = 0

    def list_posts(self, **kwargs):
        self.list_posts_calls.append(dict(kwargs))
        return self._posts

    def get_categories(self):
        self.get_categories_calls += 1
        return self._categories


class XDryRunMailBuilderTests(unittest.TestCase):
    def _eligible_post(self, post_id: int, title: str, *, category_id: int = 663) -> dict:
        excerpt = f"{title}。スポーツ報知の確認済み記事で、試合の流れと決定打を整理した。"
        body_html = (
            f"<p>{title}。スポーツ報知の確認済み記事で、試合の流れと決定打を整理した。</p>"
            "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T51111.html</p>"
        )
        return _post(post_id, title, body_html, category_ids=[category_id], excerpt=excerpt)

    def test_build_5_drafts_with_119_filter(self):
        posts = [
            self._eligible_post(701, "巨人が阪神に3-2で勝利 戸郷が7回2失点"),
            self._eligible_post(702, "阿部監督「最後まで粘れた」 巨人が接戦を制す", category_id=665),
            self._eligible_post(703, "巨人がヤクルトに4-2で勝利 打線が終盤に勝ち越し", category_id=664),
            self._eligible_post(704, "巨人がDeNAに6-3で勝利"),
            self._eligible_post(705, "巨人が広島に5-2で勝利 先発が試合をつくる"),
        ]
        wp = FakeWPClient(posts)

        payload = builder.build_x_dry_run_mail(wp, limit=5, now=FIXED_NOW)

        self.assertEqual(payload.requested_limit, 5)
        self.assertEqual(payload.fetched_posts, 5)
        self.assertEqual(payload.item_count, 5)
        self.assertEqual(len(payload.skipped_posts), 0)
        self.assertEqual(payload.subject, "[X-DRY-RUN] X 文案 5 件確認 (2026-04-26)")
        self.assertTrue(all(item.why_eligible == builder.WHY_ELIGIBLE_ALL_GREEN for item in payload.built_items))
        self.assertTrue(all(item.x_post_text.endswith(item.canonical_url) for item in payload.built_items))
        self.assertEqual(wp.list_posts_calls[0]["status"], "publish")
        self.assertEqual(wp.list_posts_calls[0]["orderby"], "date")
        self.assertEqual(wp.list_posts_calls[0]["order"], "desc")

    def test_skip_red_yellow_articles(self):
        green = self._eligible_post(711, "巨人が中日に4-1で勝利 先発が7回1失点")
        yellow = _post(
            712,
            "巨人がDeNAに勝利",
            (
                "<p>巨人がDeNAに勝利した。スポーツ報知の確認済み記事。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T52222.html</p>"
            ),
            category_ids=[663],
            featured_media=0,
        )
        red = _post(
            713,
            "巨人のポイントはどこ 阿部監督の試合前コメント",
            (
                "<p>巨人の試合前コメントを整理した。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260426-OHT1T53333.html</p>"
            ),
            category_ids=[665],
        )
        wp = FakeWPClient([green, yellow, red])

        payload = builder.build_x_dry_run_mail(wp, limit=3, now=FIXED_NOW)

        self.assertEqual([item.post_id for item in payload.built_items], [711])
        self.assertEqual(len(payload.skipped_posts), 2)
        skipped_by_post_id = {item.post_id: item for item in payload.skipped_posts}
        self.assertEqual(skipped_by_post_id[712].reason, builder.FILTER_REFUSED_REASON)
        self.assertIn("wp_gate_yellow_missing_featured_media", skipped_by_post_id[712].detail)
        self.assertEqual(skipped_by_post_id[713].reason, builder.FILTER_REFUSED_REASON)
        self.assertTrue(
            any(reason.startswith("wp_gate_yellow_") or reason.startswith("wp_gate_red_") for reason in skipped_by_post_id[713].detail)
        )

    def test_skip_non_target_categories(self):
        eligible_non_target = self._eligible_post(721, "巨人の新グッズ発売情報", category_id=666)
        eligible_target = self._eligible_post(722, "巨人がヤクルトに6-3で勝利 吉川が猛打賞", category_id=663)
        wp = FakeWPClient([eligible_non_target, eligible_target])

        payload = builder.build_x_dry_run_mail(wp, limit=2, now=FIXED_NOW)

        self.assertEqual([item.post_id for item in payload.built_items], [722])
        self.assertEqual(len(payload.skipped_posts), 1)
        self.assertEqual(payload.skipped_posts[0].post_id, 721)
        self.assertEqual(payload.skipped_posts[0].reason, builder.NON_TARGET_CATEGORY_REASON)
        self.assertEqual(payload.skipped_posts[0].category_names, ("球団情報",))

    def test_x_api_call_count_zero(self):
        source_paths = [Path(builder.__file__), Path(cli.__file__)]
        forbidden_tokens = ("create_tweet", "client.create_tweet")
        for path in source_paths:
            source = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                self.assertNotIn(token, source, msg=f"{path.name} must not use {token}")

        payload = builder.XDryRunMailBuild(
            requested_limit=5,
            fetched_posts=5,
            built_items=(
                builder.XDryRunMailItem(
                    post_id=701,
                    title="巨人が勝利",
                    category="試合速報",
                    canonical_url="https://yoshilover.com/archives/701/",
                    x_post_text="ひとことメモ。巨人が勝利\nhttps://yoshilover.com/archives/701/",
                    template_type="small_note",
                ),
            ),
            skipped_posts=(),
            subject="[X-DRY-RUN] X 文案 5 件確認 (2026-04-26)",
            body_text="sample body\n注意: X API call 0 件、live 投稿なし\n",
        )
        bridge_send = MagicMock()

        with patch.dict(os.environ, {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = builder.send_x_dry_run_mail(payload, dry_run=True, bridge_send=bridge_send)

        self.assertEqual(result.status, "dry_run")
        bridge_send.assert_not_called()

    def test_mail_body_includes_post_id_title_category_url_text(self):
        post = self._eligible_post(731, "巨人が広島に5-2で勝利 先発が試合をつくる")
        wp = FakeWPClient([post])

        payload = builder.build_x_dry_run_mail(wp, limit=1, now=FIXED_NOW)
        body_text = payload.body_text

        self.assertIn("post_id: 731", body_text)
        self.assertIn("title: 巨人が広島に5-2で勝利 先発が試合をつくる", body_text)
        self.assertIn("category: 試合速報", body_text)
        self.assertIn("url: https://yoshilover.com/archives/731/", body_text)
        self.assertIn("x_text:", body_text)
        self.assertIn("注意: X API call 0 件、live 投稿なし", body_text)

    def test_dry_run_default_no_live_mail(self):
        payload = builder.XDryRunMailBuild(
            requested_limit=5,
            fetched_posts=5,
            built_items=(
                builder.XDryRunMailItem(
                    post_id=741,
                    title="巨人が接戦を制した",
                    category="試合速報",
                    canonical_url="https://yoshilover.com/archives/741/",
                    x_post_text="ひとことメモ。接戦を制した\nhttps://yoshilover.com/archives/741/",
                    template_type="small_note",
                ),
            ),
            skipped_posts=(),
            subject="[X-DRY-RUN] X 文案 5 件確認 (2026-04-26)",
            body_text="body\n注意: X API call 0 件、live 投稿なし\n",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.object(cli, "build_x_dry_run_mail", return_value=payload) as build_mock, patch.object(
            cli, "send_x_dry_run_mail"
        ) as send_mock, patch.object(cli, "WPClient") as wp_client_mock:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("[subject] [X-DRY-RUN] X 文案 5 件確認 (2026-04-26)", stdout.getvalue())
        build_mock.assert_called_once()
        send_mock.assert_not_called()
        wp_client_mock.assert_called_once()

    def test_send_live_mail_uses_bridge_with_mail_request(self):
        payload = builder.XDryRunMailBuild(
            requested_limit=5,
            fetched_posts=5,
            built_items=(
                builder.XDryRunMailItem(
                    post_id=751,
                    title="巨人が快勝",
                    category="試合速報",
                    canonical_url="https://yoshilover.com/archives/751/",
                    x_post_text="ひとことメモ。快勝\nhttps://yoshilover.com/archives/751/",
                    template_type="small_note",
                ),
            ),
            skipped_posts=(),
            subject="[X-DRY-RUN] X 文案 5 件確認 (2026-04-26)",
            body_text="body\n注意: X API call 0 件、live 投稿なし\n",
        )
        bridge_result = mail_delivery_bridge.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[250, "ok"],
            reason=None,
        )
        bridge_send = MagicMock(return_value=bridge_result)

        with patch.dict(os.environ, {"PUBLISH_NOTICE_EMAIL_TO": "notice@example.com"}, clear=True):
            result = builder.send_x_dry_run_mail(payload, dry_run=False, bridge_send=bridge_send)

        self.assertEqual(result.status, "sent")
        bridge_send.assert_called_once()
        mail_request = bridge_send.call_args.args[0]
        self.assertIsInstance(mail_request, mail_delivery_bridge.MailRequest)
        self.assertEqual(mail_request.subject, payload.subject)
        self.assertEqual(mail_request.to, ["notice@example.com"])
        self.assertEqual(mail_request.metadata["notice_kind"], "x_dry_run")


if __name__ == "__main__":
    unittest.main()
