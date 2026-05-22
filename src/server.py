"""
Cloud Run用HTTPサーバー
POST /run → rss_fetcher.pyを実行
GET  /health → ヘルスチェック
GET  /unpublish → mail 1-click 非公開 (post_id + token、2026-05-14 user request)
GET  /publish-and-tweet → mail 内「公開してX投稿画面へ」ボタンの confirmation page (379-OPS / GH #53)
POST /publish-and-tweet → token 検証 + draft→publish flip + X intent URL に 302 redirect
"""
import json
import logging
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TRUE_VALUES = {"1", "true", "yes", "on"}

SECRET = os.environ.get("RUN_SECRET", "").strip()
PORT   = int(os.environ.get("PORT", 8080))
ENABLE_TEST_GEMINI = os.environ.get("ENABLE_TEST_GEMINI", "").strip().lower() in TRUE_VALUES
CLOUD_RUN_AUTH_MODES = {"cloud_run", "iam", "oidc"}
OIDC_SERVICE_ACCOUNT = os.environ.get("RUN_OIDC_SERVICE_ACCOUNT", "").strip()
OIDC_AUDIENCE = os.environ.get("RUN_OIDC_AUDIENCE", "").strip()
RUN_SUBPROCESS_TIMEOUT = int(os.environ.get("RUN_SUBPROCESS_TIMEOUT", "840"))


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


RUN_DRAFT_ONLY = _env_flag("RUN_DRAFT_ONLY", False)


def _secret_is_configured() -> bool:
    return bool(SECRET)


def _auth_mode() -> str:
    return os.environ.get("RUN_AUTH_MODE", "secret").strip().lower() or "secret"


def _uses_cloud_run_auth() -> bool:
    return _auth_mode() in CLOUD_RUN_AUTH_MODES


def _extract_bearer_token(handler: BaseHTTPRequestHandler) -> str:
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return ""
    return auth[7:].strip()


def _verify_oidc_token(token: str) -> bool:
    if not token:
        return False
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(
            token,
            GoogleAuthRequest(),
            audience=OIDC_AUDIENCE or None,
        )
    except Exception:
        return False

    issuer = claims.get("iss", "")
    email = claims.get("email", "")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        return False
    if OIDC_SERVICE_ACCOUNT and email != OIDC_SERVICE_ACCOUNT:
        return False
    if claims.get("email_verified") is False:
        return False
    return True


def _is_authorized(handler: BaseHTTPRequestHandler) -> bool:
    if _uses_cloud_run_auth():
        return _verify_oidc_token(_extract_bearer_token(handler))
    return _secret_is_configured() and handler.headers.get("X-Secret", "") == SECRET


def _is_secret_authorized(handler: BaseHTTPRequestHandler) -> bool:
    return _secret_is_configured() and handler.headers.get("X-Secret", "") == SECRET


def _is_authorized_with_secret_fallback(handler: BaseHTTPRequestHandler) -> bool:
    if _is_secret_authorized(handler):
        return True
    return _is_authorized(handler)


def _parse_limit(body: str, content_type: str = "") -> str:
    limit = None

    if body:
        if "application/json" in content_type:
            try:
                payload = json.loads(body)
                limit = payload.get("limit")
            except json.JSONDecodeError:
                limit = None

        if limit is None:
            params = parse_qs(body, keep_blank_values=False)
            values = params.get("limit")
            if values:
                limit = values[0]

    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 10

    if parsed < 1:
        parsed = 1
    return str(parsed)


def _parse_query_value(path: str, key: str, default: str = "") -> str:
    parsed = urlparse(path)
    values = parse_qs(parsed.query, keep_blank_values=False).get(key)
    if not values:
        return default
    return values[0]


def _parse_mode(body: str, content_type: str = "") -> str:
    """DIGEST-DAILY-MORNING (2026-05-21) Phase 2: POST body / form / query
    から ``mode`` を抽出。 未指定 / "default" / "rss" / "" → "rss" (既存挙動)。
    """
    mode = ""
    if body:
        if "application/json" in content_type:
            try:
                payload = json.loads(body)
                mode = (payload.get("mode") or "").strip()
            except json.JSONDecodeError:
                mode = ""
        if not mode:
            params = parse_qs(body, keep_blank_values=False)
            values = params.get("mode")
            if values:
                mode = (values[0] or "").strip()
    mode = (mode or "").lower()
    if mode in ("", "default", "rss"):
        return "rss"
    return mode


def _run_digest_daily(force: bool = False) -> tuple[int, str]:
    """DIGEST-DAILY-MORNING (2026-05-21) Phase 2 handler。

    朝まとめ digest 1 記事を WP に作成する (冪等)。src/tools/digest_daily_morning
    の main path を直接呼ぶのではなく、必要 step を組み立てる:
    1. 当日分既存 check (slug query)
    2. なければ build_digest_body + WPClient.create_post
    3. draft 作成時は publish-notice HTML mail を送る
    """
    log = logging.getLogger("server.digest_daily")
    try:
        from src.tools.digest_daily_morning import (
            build_digest_body,
            build_digest_title,
            build_digest_slug,
            is_digest_already_published_today,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("digest_daily import failed err=%s", exc)
        return 500, json.dumps(
            {"status": "error", "error": f"import_failed:{type(exc).__name__}"},
            ensure_ascii=False,
        )
    try:
        from src.wp_client import WPClient
    except Exception as exc:  # noqa: BLE001
        log.warning("digest_daily wp_client import failed err=%s", exc)
        return 500, json.dumps(
            {"status": "error", "error": f"wp_client_import_failed:{type(exc).__name__}"},
            ensure_ascii=False,
        )
    wp = WPClient()
    slug = build_digest_slug()
    if not force and is_digest_already_published_today(wp):
        log.info("digest_daily skip reason=already_published_today slug=%s", slug)
        return 200, json.dumps(
            {"status": "skipped", "reason": "already_published_today", "slug": slug},
            ensure_ascii=False,
        )
    title = build_digest_title()
    body = build_digest_body()
    # Article creation is draft-first; publishing is handled only by the
    # mail/manual selection flow.
    requested_status = "draft"
    try:
        post_id = wp.create_post(
            title=title,
            content=body,
            status=requested_status,
            categories=[670],  # コラム category id (override via env if needed)
            caller="digest_daily_morning",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("digest_daily create_post failed err=%s", exc)
        return 500, json.dumps(
            {"status": "error", "error": f"create_post_failed:{type(exc).__name__}:{exc}"},
            ensure_ascii=False,
        )

    actual_status = requested_status
    try:
        post_data = wp.get_post(post_id)
        actual_status = str((post_data or {}).get("status") or requested_status).strip().lower()
    except Exception as exc:  # noqa: BLE001
        post_data = {}
        log.warning("digest_daily get_post failed post_id=%s err=%s", post_id, exc)

    notice_counts = {"sent": 0, "suppressed": 0, "errors": 0}
    if actual_status == "draft":
        notice_counts = _send_digest_daily_draft_notice(
            wp=wp,
            post_id=post_id,
            title=title,
            canonical_url=str((post_data or {}).get("link") or "").strip(),
            body_html=body,
            post_data=post_data,
            log=log,
        )
    response_status = "draft" if actual_status == "draft" else "published"
    log.info(
        "digest_daily %s post_id=%s slug=%s notice_sent=%s notice_suppressed=%s notice_errors=%s",
        response_status,
        post_id,
        slug,
        notice_counts.get("sent", 0),
        notice_counts.get("suppressed", 0),
        notice_counts.get("errors", 0),
    )
    return 200, json.dumps(
        {
            "status": response_status,
            "post_id": post_id,
            "title": title,
            "slug": slug,
            "notice": notice_counts,
        },
        ensure_ascii=False,
    )


def _send_digest_daily_draft_notice(
    *,
    wp,
    post_id: int,
    title: str,
    canonical_url: str,
    body_html: str,
    post_data: dict,
    log: logging.Logger,
) -> dict[str, int]:
    """Send the same draft-first HTML notice used by rss_fetcher.

    The user-facing contract is: article creation creates a draft, and draft
    creation sends a mail for manual selection. Reusing rss_fetcher's notice
    helper keeps the publish button, admin URL, body excerpt, and remote queue
    marker behavior identical.
    """
    try:
        from src.rss_fetcher import (
            _build_inline_draft_notice_request,
            _send_fetcher_inline_draft_notices,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("digest_daily draft notice import failed post_id=%s err=%s", post_id, exc)
        return {"sent": 0, "suppressed": 0, "errors": 1}

    try:
        if not post_data:
            post_data = wp.get_post(post_id)
        request = _build_inline_draft_notice_request(
            post_data=post_data,
            post_id=post_id,
            title=title,
            canonical_url=canonical_url,
            subtype="digest_daily",
            body_html=body_html,
        )
        return _send_fetcher_inline_draft_notices([request], logger=log)
    except Exception as exc:  # noqa: BLE001
        log.warning("digest_daily draft notice failed post_id=%s err=%s", post_id, exc)
        return {"sent": 0, "suppressed": 0, "errors": 1}


def _parse_bool_query(path: str, key: str, default: bool = False) -> bool:
    value = _parse_query_value(path, key, "")
    if not value:
        return default
    return value.strip().lower() in TRUE_VALUES


def _normalize_positive_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _run_started_payload() -> dict:
    return {
        "event": "run_started",
        "run_draft_only": RUN_DRAFT_ONLY,
        "auto_tweet_enabled": _env_flag("AUTO_TWEET_ENABLED", False),
        "publish_require_image": _env_flag("PUBLISH_REQUIRE_IMAGE", True),
        "revision": os.environ.get("K_REVISION", "").strip(),
    }


def _log_run_started() -> None:
    print(json.dumps(_run_started_payload(), ensure_ascii=False), flush=True)


def _run_fetcher(limit: str) -> tuple[int, str]:
    cmd = ["python3", "src/rss_fetcher.py", "--limit", limit]
    if RUN_DRAFT_ONLY:
        cmd.append("--draft-only")
    try:
        result = subprocess.run(
            cmd,
            cwd="/app",
            timeout=RUN_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return 504, f"rss_fetcher timed out after {RUN_SUBPROCESS_TIMEOUT}s"

    if result.returncode != 0:
        return 500, f"rss_fetcher failed with exit code {result.returncode}"
    return 200, "completed"


def _run_fact_check_notify(since: str, limit: str, category: str = "", send: bool = True) -> tuple[int, str]:
    normalized_limit = _normalize_positive_int(limit, 20)
    try:
        try:
            from src.fact_check_notifier import run_notification
        except ImportError:
            from fact_check_notifier import run_notification

        payload = run_notification(
            since=since or "yesterday",
            limit=normalized_limit,
            category=category,
            send=send,
        )
    except Exception as exc:
        return 500, json.dumps(
            {
                "status": "error",
                "error": str(exc),
                "since": since or "yesterday",
                "limit": normalized_limit,
                "category": category,
                "sent": False,
            },
            ensure_ascii=False,
        )

    response = {
        "status": "ok",
        "since": payload["since"],
        "checked_posts": payload["checked_posts"],
        "red": payload["red"],
        "yellow": payload["yellow"],
        "green": payload["green"],
        "subject": payload["subject"],
        "reason": payload.get("reason", ""),
        "posts_in_last_hour_count": payload.get("posts_in_last_hour_count", 0),
        "sent": payload["sent"],
        "delivery_mode": payload.get("delivery_mode", "none"),
    }
    return 200, json.dumps(response, ensure_ascii=False)


def _run_audit_notify(window_minutes: str, send: bool = True) -> tuple[int, str]:
    normalized_window_minutes = _normalize_positive_int(window_minutes, 60)
    try:
        try:
            from src.audit_notify import run_audit_notification
        except ImportError:
            from audit_notify import run_audit_notification

        payload = run_audit_notification(
            window_minutes=normalized_window_minutes,
            send=send,
        )
    except Exception as exc:
        return 500, json.dumps(
            {
                "status": "error",
                "error": str(exc),
                "window_minutes": normalized_window_minutes,
                "mail_sent": False,
            },
            ensure_ascii=False,
        )

    return 200, json.dumps(payload, ensure_ascii=False)


def _run_unpublish(post_id_raw: str, token: str) -> tuple[int, str]:
    """344-INGEST 2026-05-14 user request: mail 1-click 非公開 endpoint 本体。

    成功時: status="draft" に flip + 簡易 HTML response 返す
    認証失敗 / WP REST 失敗時: 4xx/5xx + 簡易 HTML
    """
    log = logging.getLogger("server.unpublish")

    if not post_id_raw or not post_id_raw.isdigit():
        log.info("unpublish_skip reason=invalid_post_id raw=%s", post_id_raw[:20])
        return 400, _unpublish_html("error", "post_id が不正です")
    if not token:
        log.info("unpublish_skip reason=missing_token post_id=%s", post_id_raw)
        return 400, _unpublish_html("error", "token が無いです")

    try:
        from src.unpublish_token import verify_unpublish_token
    except Exception as exc:  # noqa: BLE001
        log.warning("unpublish_helper_import_failed err=%s", exc)
        return 500, _unpublish_html("error", "内部エラー (helper import 失敗)")

    if not verify_unpublish_token(post_id_raw, token):
        log.info("unpublish_skip reason=token_invalid post_id=%s", post_id_raw)
        return 403, _unpublish_html("error", "token 検証失敗 (mail link が改ざん or 期限切れ)")

    post_id = int(post_id_raw)
    try:
        from src.wp_client import WPClient
    except Exception as exc:  # noqa: BLE001
        log.warning("unpublish_wp_client_import_failed err=%s", exc)
        return 500, _unpublish_html("error", "内部エラー (wp_client import 失敗)")

    try:
        wp = WPClient()
        wp.update_post_status(
            post_id,
            "draft",
            caller="server.unpublish_endpoint",
            source_lane="mail_unpublish",
        )
    except Exception as exc:  # noqa: BLE001
        # block_enabled (ENABLE_WP_PUBLISHED_REVERT_GUARD=1) が ON だと
        # RuntimeError で blocked される。user に分かるよう error message 返す。
        err_msg = str(exc)
        log.warning(
            "unpublish_wp_failed post_id=%s err=%s", post_id, err_msg
        )
        if "blocked" in err_msg.lower():
            return 503, _unpublish_html(
                "error",
                f"非公開化が ENABLE_WP_PUBLISHED_REVERT_GUARD で block されました (post_id={post_id})。env flag を OFF にすれば実行可。",
            )
        return 500, _unpublish_html("error", f"WP REST 失敗 (post_id={post_id}): {err_msg[:200]}")

    log.info("unpublish_success post_id=%s caller=mail_unpublish_endpoint", post_id)
    return 200, _unpublish_html(
        "success",
        f"post_id={post_id} を非公開 (draft) に変更しました",
        post_id=post_id,
    )


def _run_publish_and_tweet(
    method: str,
    post_id_raw: str,
    token: str,
) -> tuple[int, str, dict]:
    """379-OPS (GH #53): mail 内「公開してX投稿画面へ」ボタンの handler 本体。

    Returns ``(status_code, body, extra_headers)``。
    """
    log = logging.getLogger("server.publish_and_tweet")
    try:
        from src.publish_button_handler import handle_get, handle_post
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_button_handler_import_failed err=%s", exc)
        return 500, "<h2>内部エラー</h2><p>handler import 失敗</p>", {}
    try:
        from src.wp_client import WPClient
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_button_wp_client_import_failed err=%s", exc)
        return 500, "<h2>内部エラー</h2><p>wp_client import 失敗</p>", {}

    wp = WPClient()

    def _fetch(pid: int):
        try:
            return wp.get_post(pid)
        except Exception:
            return None

    def _update(pid: int, new_status: str) -> None:
        wp.update_post_status(
            pid,
            new_status,
            caller="server.publish_and_tweet_endpoint",
            source_lane="mail_publish_and_tweet",
        )

    if method == "GET":
        return handle_get(
            post_id_raw=post_id_raw,
            token=token,
            fetch_post=_fetch,
        )
    return handle_post(
        post_id_raw=post_id_raw,
        token=token,
        fetch_post=_fetch,
        update_post_status=_update,
    )


def _unpublish_html(status: str, message: str, post_id: int | None = None) -> str:
    """unpublish endpoint 用の簡易 HTML response。"""
    title = "非公開化 完了" if status == "success" else "非公開化 エラー"
    color = "#1b8a3e" if status == "success" else "#d73a3a"
    admin_link = ""
    if post_id and status == "success":
        admin_link = (
            f'<p><a href="https://yoshilover.com/wp-admin/post.php?post={post_id}&action=edit">'
            f"WP admin で確認 / 再公開</a></p>"
        )
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        f'<title>{title}</title></head><body style="font-family:sans-serif;padding:32px;">'
        f'<h2 style="color:{color};">{title}</h2>'
        f'<p>{message}</p>'
        f'{admin_link}'
        '</body></html>'
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # アクセスログ抑制

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._respond(200, "OK")
        elif parsed.path == "/test-gemini":
            if not ENABLE_TEST_GEMINI:
                self._respond(404, "Not Found")
                return
            if not _uses_cloud_run_auth() and not _secret_is_configured():
                self._respond(503, "RUN_SECRET is not configured")
                return
            if not _is_authorized(self):
                self._respond(403, "Forbidden")
                return
            try:
                result = subprocess.run(
                    ["gemini", "-p", "読売ジャイアンツについて一言"],
                    capture_output=True, text=True, timeout=90, cwd="/app"
                )
                out = result.stdout.strip() or result.stderr.strip() or "(no output)"
                self._respond(200, out[:500])
            except Exception as e:
                self._respond(200, f"ERROR: {e}")
        elif parsed.path == "/fact_check_notify":
            if not _uses_cloud_run_auth() and not _secret_is_configured():
                self._respond(503, "RUN_SECRET is not configured")
                return
            if not _is_authorized_with_secret_fallback(self):
                self._respond(403, "Forbidden")
                return
            since = _parse_query_value(self.path, "since", "yesterday")
            category = _parse_query_value(self.path, "category", "")
            limit = _parse_query_value(self.path, "limit", "20")
            send = not _parse_bool_query(self.path, "dry_run", False)
            code, body = _run_fact_check_notify(since, limit, category=category, send=send)
            self._respond(code, body, content_type="application/json; charset=utf-8")
        elif parsed.path == "/audit_notify":
            if not _secret_is_configured():
                self._respond(503, "RUN_SECRET is not configured")
                return
            if not _is_authorized_with_secret_fallback(self):
                self._respond(403, "Forbidden")
                return
            window_minutes = _parse_query_value(self.path, "window_minutes", "60")
            send = not _parse_bool_query(self.path, "dry_run", False)
            code, body = _run_audit_notify(window_minutes, send=send)
            self._respond(code, body, content_type="application/json; charset=utf-8")
        elif parsed.path == "/unpublish":
            # 2026-05-14 user request: mail 1-click 非公開 endpoint。
            # token (HMAC of post_id) で検証、認証 OK なら WP REST で status="draft" に flip。
            qs = parse_qs(parsed.query or "")
            post_id_raw = (qs.get("post_id", [""])[0] or "").strip()
            token = (qs.get("token", [""])[0] or "").strip()
            code, html = _run_unpublish(post_id_raw, token)
            self._respond(code, html, content_type="text/html; charset=utf-8")
        elif parsed.path == "/publish-and-tweet":
            # 379-OPS (GH #53): mail 内「公開してX投稿画面へ」ボタン confirmation page。
            qs = parse_qs(parsed.query or "")
            post_id_raw = (qs.get("post_id", [""])[0] or "").strip()
            token = (qs.get("token", [""])[0] or "").strip()
            code, body, extra_headers = _run_publish_and_tweet("GET", post_id_raw, token)
            self._respond(code, body, content_type="text/html; charset=utf-8", extra_headers=extra_headers)
        elif parsed.path == "/x-intent":
            # 2026-05-22: x_post_mail X button needs to reach x.com via server
            # redirect so the mobile X app's universal-link intercept routes
            # to @yoshilover6760 (matching publish_notice's working pattern).
            # No token required — this is a pure URL passthrough with no side
            # effects, just a 302 to x.com/intent/post.
            qs = parse_qs(parsed.query or "")
            text_param = (qs.get("text", [""])[0] or "")
            hashtags_param = (qs.get("hashtags", [""])[0] or "")
            from urllib.parse import quote as _q
            location = f"https://x.com/intent/post?text={_q(text_param, safe='')}"
            if hashtags_param:
                location += f"&hashtags={_q(hashtags_param, safe=',')}"
            self._respond(302, "", content_type="text/plain", extra_headers={"Location": location})
        else:
            self._respond(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/publish-and-tweet":
            # 379-OPS (GH #53): confirmation page から submit された publish + X intent。
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length).decode() if length else ""
            form = parse_qs(raw_body)
            post_id_raw = (form.get("post_id", [""])[0] or "").strip()
            token = (form.get("token", [""])[0] or "").strip()
            code, body, extra_headers = _run_publish_and_tweet("POST", post_id_raw, token)
            self._respond(code, body, content_type="text/html; charset=utf-8", extra_headers=extra_headers)
            return
        if self.path != "/run":
            self._respond(404, "Not Found")
            return
        if not _uses_cloud_run_auth() and not _secret_is_configured():
            self._respond(503, "RUN_SECRET is not configured")
            return
        if not _is_authorized(self):
            self._respond(403, "Forbidden")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else ""
        content_type = self.headers.get("Content-Type", "")
        mode = _parse_mode(body, content_type)
        # DIGEST-DAILY-MORNING Phase 2 (2026-05-21): mode dispatch
        if mode == "digest_daily":
            _log_run_started()
            code, message = _run_digest_daily()
            self._respond(code, message, content_type="application/json; charset=utf-8")
            return
        limit = _parse_limit(body, content_type)
        _log_run_started()
        code, message = _run_fetcher(limit)
        self._respond(code, message)

    def _respond(self, code, body, content_type="text/plain", extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body.encode())


if __name__ == "__main__":
    print(f"起動: port={PORT}")
    # DIGEST-DAILY-MORNING (2026-05-21) wire-fix: ThreadingHTTPServer に切替。
    # 旧 HTTPServer (single-threaded) では rss_fetcher subprocess block 中
    # に来た mode=digest_daily 等の他 mode request が queue 待機して
    # scheduler attemptDeadline 内に dispatch 不能だった。 各 do_POST が
    # 独立 thread で動くようにすることで、 短時間 handler (digest_daily) は
    # RSS subprocess と並列処理される。
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
