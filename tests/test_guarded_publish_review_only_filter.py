"""RELIABILITY-2026-05-08-Y2: guarded-publish が review-only prefix 付き draft を
auto-publish しないよう title prefix filter を追加した動作 test。

incident: 65046「【要review｜post_gen_validate】You「甲子園の魔物！過去イチ浜風！」」
が rss_fetcher の E2 path で force_status="draft" として作られたが、guarded-publish
が title prefix を無視して auto-publish (13:01:05) した事故。これを防ぐ早期 filter。
"""

import unittest

from src import guarded_publish_evaluator as evaluator


class IsReviewOnlyDraftTests(unittest.TestCase):
    def test_post_gen_validate_review_prefix_filtered(self):
        self.assertTrue(
            evaluator._is_review_only_draft(
                "【要review｜post_gen_validate】You「甲子園の魔物！過去イチ浜風！」"
            )
        )
        self.assertTrue(
            evaluator._is_review_only_draft(
                "【要review｜post_gen_validate】竹丸和幸「自分で終わりたかった」"
            )
        )

    def test_digest_prefix_filtered(self):
        self.assertTrue(
            evaluator._is_review_only_draft("【要review｜post_gen_validate digest｜2026-05-08")
        )

    def test_internal_skip_visible_prefix_filtered(self):
        self.assertTrue(
            evaluator._is_review_only_draft("【要review｜internal_skip_visible】test article")
        )

    def test_preflight_skip_prefix_filtered(self):
        self.assertTrue(
            evaluator._is_review_only_draft("【要review｜preflight_skip】test article")
        )

    def test_normal_titles_not_filtered(self):
        for title in (
            "巨人 3-2 阪神に競り勝ち連勝 9回サヨナラ本塁打",
            "【巨人】キャベッジ「状態も上向き」",
            "【要確認｜summary｜lineup】通常の publish-notice 件名",  # publish-notice 側 prefix、別物
            "5/8付 スポーツ報知 のファーム情報",
            "",
            "巨人ヤクルト戦",
        ):
            self.assertFalse(
                evaluator._is_review_only_draft(title),
                f"{title!r} should NOT be filtered (only 【要review｜...】 should be)",
            )

    def test_none_or_empty_safe(self):
        self.assertFalse(evaluator._is_review_only_draft(""))
        self.assertFalse(evaluator._is_review_only_draft(None))


class EvaluateRawPostsReviewOnlyFilterTests(unittest.TestCase):
    """evaluate_raw_posts が review-only draft を入力 list から除外するか検証。"""

    def _build_raw_post(self, *, post_id: int, title: str, modified: str = "2026-05-08T13:00:00") -> dict:
        return {
            "id": post_id,
            "title": {"rendered": title, "raw": title},
            "content": {"rendered": "<p>body</p>", "raw": "body"},
            "modified": modified,
            "modified_gmt": modified,
            "date": modified,
            "date_gmt": modified,
            "status": "draft",
            "link": f"https://yoshilover.com/{post_id}",
            "categories": [],
            "tags": [],
            "meta": {},
        }

    def test_review_only_draft_excluded_from_evaluation(self):
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        now = datetime(2026, 5, 8, 13, 30, 0, tzinfo=JST)

        review_post = self._build_raw_post(
            post_id=65046,
            title="【要review｜post_gen_validate】You「甲子園の魔物！過去イチ浜風！」",
        )
        normal_post = self._build_raw_post(
            post_id=65074,
            title="巨人 3-2 阪神に競り勝ち連勝 9回サヨナラ本塁打",
        )

        result = evaluator.evaluate_raw_posts(
            [review_post, normal_post],
            window_hours=24,
            max_pool=10,
            now=now,
        )
        # review_only draft は green/yellow/review/red のどこにも入らない
        for bucket_name in ("green", "yellow", "review", "red"):
            bucket = result.get(bucket_name, [])
            ids = {entry.get("post_id") for entry in bucket}
            self.assertNotIn(
                65046, ids,
                f"review-only draft 65046 must be excluded from {bucket_name} bucket",
            )

    def test_normal_draft_still_evaluated(self):
        # 通常の draft は今まで通り bucket 分け対象 (excluded されない)
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        now = datetime(2026, 5, 8, 13, 30, 0, tzinfo=JST)

        normal_post = self._build_raw_post(
            post_id=65074,
            title="巨人 3-2 阪神に競り勝ち連勝 9回サヨナラ本塁打",
        )
        result = evaluator.evaluate_raw_posts(
            [normal_post],
            window_hours=24,
            max_pool=10,
            now=now,
        )
        # 通常 draft はどこかの bucket には入る (具体 bucket は他の guard 判定次第)
        all_ids: set[int] = set()
        for bucket_name in ("green", "yellow", "review", "red"):
            for entry in result.get(bucket_name, []):
                pid = entry.get("post_id")
                if pid is not None:
                    all_ids.add(int(pid))
        self.assertIn(65074, all_ids, "normal draft should still be evaluated")


if __name__ == "__main__":
    unittest.main()
