import unittest
from unittest.mock import patch

from src.server import _parse_limit


class DummyHandler:
    def __init__(self, headers=None):
        self.headers = headers or {}


class ParseLimitTests(unittest.TestCase):
    def test_form_encoded_limit_10_is_not_misread_as_1(self):
        self.assertEqual(_parse_limit("limit=10", "application/x-www-form-urlencoded"), "10")

    def test_json_limit_is_supported(self):
        self.assertEqual(_parse_limit('{"limit": 3}', "application/json"), "3")

    def test_invalid_limit_falls_back_to_default(self):
        self.assertEqual(_parse_limit("limit=abc", "application/x-www-form-urlencoded"), "10")

    def test_non_positive_limit_is_clamped(self):
        self.assertEqual(_parse_limit("limit=0", "application/x-www-form-urlencoded"), "1")


class AuthModeTests(unittest.TestCase):
    def test_secret_mode_requires_matching_header(self):
        with patch.dict("os.environ", {"RUN_AUTH_MODE": "secret", "RUN_SECRET": "abc"}, clear=False):
            from importlib import reload
            import src.server as server

            reload(server)
            self.assertFalse(server._uses_cloud_run_auth())
            self.assertTrue(server._is_authorized(DummyHandler({"X-Secret": "abc"})))
            self.assertFalse(server._is_authorized(DummyHandler({"X-Secret": "zzz"})))

    def test_cloud_run_mode_skips_x_secret_check(self):
        with patch.dict("os.environ", {"RUN_AUTH_MODE": "cloud_run"}, clear=False):
            from importlib import reload
            import src.server as server

            reload(server)
            self.assertTrue(server._uses_cloud_run_auth())
            with patch.object(server, "_verify_oidc_token", return_value=False):
                self.assertFalse(server._is_authorized(DummyHandler({})))
            with patch.object(server, "_verify_oidc_token", return_value=True):
                self.assertTrue(server._is_authorized(DummyHandler({"Authorization": "Bearer token"})))

    def test_fact_check_notify_accepts_x_secret_even_in_cloud_run_mode(self):
        with patch.dict("os.environ", {"RUN_AUTH_MODE": "cloud_run", "RUN_SECRET": "abc"}, clear=False):
            from importlib import reload
            import src.server as server

            reload(server)
            with patch.object(server, "_verify_oidc_token", return_value=False):
                self.assertTrue(server._is_authorized_with_secret_fallback(DummyHandler({"X-Secret": "abc"})))
                self.assertFalse(server._is_authorized_with_secret_fallback(DummyHandler({"X-Secret": "zzz"})))


class RunFetcherTests(unittest.TestCase):
    def test_run_fetcher_success(self):
        from importlib import reload
        import src.server as server

        reload(server)
        with patch.object(server.subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            code, message = server._run_fetcher("3")
        self.assertEqual(code, 200)
        self.assertEqual(message, "completed")
        mock_run.assert_called_once_with(
            ["python3", "src/rss_fetcher.py", "--limit", "3"],
            cwd="/app",
            timeout=server.RUN_SUBPROCESS_TIMEOUT,
        )

    def test_run_fetcher_failure_returns_500(self):
        from importlib import reload
        import src.server as server

        reload(server)
        with patch.object(server.subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 2
            code, message = server._run_fetcher("3")
        self.assertEqual(code, 500)
        self.assertIn("exit code 2", message)

    def test_run_fetcher_timeout_returns_504(self):
        from importlib import reload
        import src.server as server

        reload(server)
        with patch.object(server.subprocess, "run", side_effect=server.subprocess.TimeoutExpired(cmd=["python3"], timeout=1)):
            code, message = server._run_fetcher("3")
        self.assertEqual(code, 504)
        self.assertIn("timed out", message)

    def test_run_fetcher_appends_draft_only_flag_when_enabled(self):
        with patch.dict("os.environ", {"RUN_DRAFT_ONLY": "1"}, clear=False):
            from importlib import reload
            import src.server as server

            reload(server)
            with patch.object(server.subprocess, "run") as mock_run:
                mock_run.return_value.returncode = 0
                code, message = server._run_fetcher("5")

        self.assertEqual(code, 200)
        self.assertEqual(message, "completed")
        mock_run.assert_called_once_with(
            ["python3", "src/rss_fetcher.py", "--limit", "5", "--draft-only"],
            cwd="/app",
            timeout=server.RUN_SUBPROCESS_TIMEOUT,
        )

    def test_run_fact_check_notify_success(self):
        from importlib import reload
        import src.server as server

        reload(server)
        with patch("src.fact_check_notifier.run_notification") as mock_run_notification:
            mock_run_notification.return_value = {
                "since": "yesterday",
                "checked_posts": 6,
                "red": 1,
                "yellow": 2,
                "green": 3,
                "subject": "subject",
                "sent": True,
            }
            code, body = server._run_fact_check_notify("yesterday", "20", category="postgame", send=True)

        self.assertEqual(code, 200)
        self.assertIn('"checked_posts": 6', body)
        self.assertIn('"sent": true', body)
        mock_run_notification.assert_called_once_with(
            since="yesterday",
            limit=20,
            category="postgame",
            send=True,
        )

    def test_run_fact_check_notify_failure_returns_500(self):
        from importlib import reload
        import src.server as server

        reload(server)
        with patch("src.fact_check_notifier.run_notification", side_effect=RuntimeError("smtp auth failed")):
            code, body = server._run_fact_check_notify("yesterday", "oops", category="", send=False)

        self.assertEqual(code, 500)
        self.assertIn('"status": "error"', body)
        self.assertIn('"limit": 20', body)
        self.assertIn("smtp auth failed", body)


class RunStartedLoggingTests(unittest.TestCase):
    def test_run_started_payload_reflects_current_runtime_guards(self):
        with patch.dict(
            "os.environ",
            {
                "RUN_DRAFT_ONLY": "1",
                "AUTO_TWEET_ENABLED": "0",
                "PUBLISH_REQUIRE_IMAGE": "1",
                "K_REVISION": "yoshilover-fetcher-00118-94p",
            },
            clear=False,
        ):
            from importlib import reload
            import src.server as server

            reload(server)
            payload = server._run_started_payload()

        self.assertEqual(
            payload,
            {
                "event": "run_started",
                "run_draft_only": True,
                "auto_tweet_enabled": False,
                "publish_require_image": True,
                "revision": "yoshilover-fetcher-00118-94p",
            },
        )

    def test_log_run_started_prints_json_payload(self):
        with patch.dict(
            "os.environ",
            {
                "RUN_DRAFT_ONLY": "1",
                "AUTO_TWEET_ENABLED": "0",
                "PUBLISH_REQUIRE_IMAGE": "1",
                "K_REVISION": "yoshilover-fetcher-00118-94p",
            },
            clear=False,
        ):
            from importlib import reload
            import src.server as server

            reload(server)
            with patch("builtins.print") as mock_print:
                server._log_run_started()

        mock_print.assert_called_once()
        logged_payload = mock_print.call_args.args[0]
        self.assertIn('"event": "run_started"', logged_payload)
        self.assertIn('"run_draft_only": true', logged_payload)
        self.assertIn('"auto_tweet_enabled": false', logged_payload)
        self.assertIn('"publish_require_image": true', logged_payload)
        self.assertIn('"revision": "yoshilover-fetcher-00118-94p"', logged_payload)


if __name__ == "__main__":
    unittest.main()
