import unittest

from src.rss_fetcher import finalize_post_publication


class _StubWP:
    def __init__(self):
        self.publish_post_calls = []
        self.update_post_status_calls = []

    def publish_post(self, post_id: int, **kwargs) -> None:
        self.publish_post_calls.append((post_id, kwargs))

    def update_post_status(self, post_id: int, status: str) -> None:
        self.update_post_status_calls.append((post_id, status))


class _StubLogger:
    def __init__(self):
        self.messages = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class FinalizePostPublicationTests(unittest.TestCase):
    def test_finalize_post_publication_routes_publish_through_helper(self):
        wp = _StubWP()
        logger = _StubLogger()
        history = {}

        published = finalize_post_publication(
            wp,
            64416,
            "https://yoshilover.com/64416",
            history,
            "巨人戦試合前情報",
            logger,
            draft_only=False,
        )

        self.assertTrue(published)
        self.assertEqual(wp.update_post_status_calls, [])
        self.assertEqual(
            wp.publish_post_calls,
            [
                (
                    64416,
                    {
                        "caller": "rss_fetcher.finalize_post_publication",
                        "source_lane": "rss_fetcher",
                        "status_before": "draft",
                    },
                )
            ],
        )
        self.assertIn("https://yoshilover.com/64416", history)

    def test_finalize_post_publication_keeps_draft_only_behavior(self):
        wp = _StubWP()
        logger = _StubLogger()
        history = {}

        published = finalize_post_publication(
            wp,
            64416,
            "https://yoshilover.com/64416",
            history,
            "巨人戦試合前情報",
            logger,
            draft_only=True,
        )

        self.assertFalse(published)
        self.assertEqual(wp.publish_post_calls, [])
        self.assertEqual(wp.update_post_status_calls, [])
