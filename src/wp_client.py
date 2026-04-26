"""
wp_client.py — WP REST API 共通クライアント
全スクリプトから import して使用する。

使用例:
    from wp_client import WPClient
    wp = WPClient()
    post_id = wp.create_draft("タイトル", "<p>本文</p>", categories=[3])

疎通テスト:
    python3 src/wp_client.py --test
"""

import os
import sys
import json
import argparse
import html
import random
import re
import subprocess
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# vendorディレクトリをパスに追加（サーバー環境用）
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)
from pathlib import Path

import requests
from dotenv import load_dotenv

# プロジェクトルートの .env を読み込む
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
WP_REST_RETRY = 3
WP_REST_MAX_SLEEP = 30


def _parse_retry_after_seconds(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return max(float(int(text)), 0.0)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        return None
    return max(retry_at.timestamp() - time.time(), 0.0)


def _compute_retry_sleep(attempt: int, max_delay: int) -> float:
    return min((2 ** attempt) + random.uniform(0, 1), max_delay)


class WPClient:
    SOURCE_URL_META_KEY = "_yoshilover_source_url"
    SOURCE_URL_META_ALIASES = ("yl_source_url",)

    def __init__(self):
        self.base_url    = os.getenv("WP_URL", "").rstrip("/")
        self.user        = os.getenv("WP_USER", "")
        self.app_password = os.getenv("WP_APP_PASSWORD", "")

        if not all([self.base_url, self.user, self.app_password]):
            raise ValueError(".env に WP_URL / WP_USER / WP_APP_PASSWORD が設定されていません")

        self.auth    = (self.user, self.app_password)
        self.api     = f"{self.base_url}/wp-json/wp/v2"
        self.headers = {"Content-Type": "application/json"}

    def _request_with_retry(
        self,
        method,
        url: str,
        *,
        action: str,
        retry: int = WP_REST_RETRY,
        timeout: int = 30,
        **kwargs,
    ) -> requests.Response:
        attempts = retry + 1
        last_err: Exception | None = None
        request_kwargs = dict(kwargs)
        request_kwargs.setdefault("auth", self.auth)
        request_kwargs.setdefault("timeout", timeout)

        for attempt in range(attempts):
            try:
                resp = method(url, **request_kwargs)
            except (
                requests.ConnectionError,
                requests.Timeout,
                ConnectionError,
                TimeoutError,
                urllib.error.URLError,
            ) as e:
                last_err = e
                if attempt >= retry:
                    break
                time.sleep(_compute_retry_sleep(attempt, WP_REST_MAX_SLEEP))
                continue

            if resp.status_code == 429:
                if attempt >= retry:
                    self._raise_for_status(resp, action)
                retry_after = _parse_retry_after_seconds(
                    (resp.headers or {}).get("Retry-After")
                )
                time.sleep(
                    retry_after
                    if retry_after is not None
                    else _compute_retry_sleep(attempt, WP_REST_MAX_SLEEP)
                )
                continue

            if 500 <= resp.status_code < 600:
                if attempt >= retry:
                    self._raise_for_status(resp, action)
                time.sleep(_compute_retry_sleep(attempt, WP_REST_MAX_SLEEP))
                continue

            self._raise_for_status(resp, action)
            return resp

        raise RuntimeError(f"[WP] request failed after {attempts} attempts ({action}): {last_err!r}")

    @staticmethod
    def _normalize_title(title: str) -> str:
        return re.sub(r"[\s　【】「」『』〔〕（）()・\\/_-]", "", (title or "")).lower()

    @staticmethod
    def _normalize_source_url(source_url: str | None) -> str:
        return html.unescape((source_url or "").strip())

    @classmethod
    def _source_url_meta_keys(cls) -> tuple[str, ...]:
        return (cls.SOURCE_URL_META_KEY, *cls.SOURCE_URL_META_ALIASES)

    @classmethod
    def _get_source_url_meta(cls, post: dict) -> tuple[str, str]:
        present_key = ""
        meta = (post or {}).get("meta")
        if isinstance(meta, dict):
            for key in cls._source_url_meta_keys():
                if key in meta:
                    present_key = present_key or key
                    value = cls._normalize_source_url(meta.get(key))
                    if value:
                        return key, value
        for key in cls._source_url_meta_keys():
            if key in (post or {}):
                present_key = present_key or key
                value = cls._normalize_source_url((post or {}).get(key))
                if value:
                    return key, value
        return present_key or cls.SOURCE_URL_META_KEY, ""

    @classmethod
    def _build_source_url_meta_payload(
        cls,
        source_url: str | None,
        preferred_key: str | None = None,
    ) -> dict:
        normalized_source_url = cls._normalize_source_url(source_url)
        if not normalized_source_url:
            return {}
        target_key = preferred_key if preferred_key in cls._source_url_meta_keys() else cls.SOURCE_URL_META_KEY
        return {target_key: normalized_source_url}

    @staticmethod
    def _mark_reuse_reason(post: dict, reuse_reason: str) -> dict:
        marked = dict(post or {})
        marked["_yoshilover_reuse_reason"] = reuse_reason
        return marked

    def _load_post_detail_for_reuse(self, post_id: int) -> dict | None:
        detail_fields = ",".join(
            [
                "id",
                "date",
                "date_gmt",
                "title",
                "status",
                "featured_media",
                "categories",
                "meta",
                *self._source_url_meta_keys(),
            ]
        )
        query_variants = [
            {"context": "edit", "_fields": detail_fields},
            {"_fields": detail_fields},
        ]
        for params in query_variants:
            try:
                resp = self._request_with_retry(
                    requests.get,
                    f"{self.api}/posts/{post_id}",
                    action=f"既存記事詳細取得 post_id={post_id}",
                    params=params,
                )
                return resp.json()
            except Exception:
                continue
        return None

    @staticmethod
    def _get_image_candidate_exclusion_reason(image_url: str) -> str:
        low = html.unescape((image_url or "").strip()).lower()
        if re.search(r"\babs(?:-\d+)?\.twimg\.com/emoji/", low):
            return "emoji_svg_url"
        return ""

    @staticmethod
    def _get_image_mime_exclusion_reason(content_type: str) -> str:
        normalized = WPClient._normalize_content_type(content_type)
        if normalized == "image/svg+xml":
            return "svg_mime_type"
        return ""

    @staticmethod
    def _log_image_candidate_excluded(reason: str, excluded_url: str, source_url: str = ""):
        payload = {
            "event": "image_candidate_excluded",
            "reason": reason,
            "excluded_url": html.unescape((excluded_url or "").strip()),
            "source_url": html.unescape((source_url or "").strip()),
        }
        print(json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _is_recent_post(post: dict, within_hours: int) -> bool:
        threshold = timedelta(hours=within_hours)
        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now()

        for field in ("date_gmt", "date"):
            raw = (post or {}).get(field)
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo:
                return now_utc - parsed.astimezone(timezone.utc) <= threshold
            return now_local - parsed <= threshold
        return True

    def find_recent_post_by_title(
        self,
        title: str,
        within_hours: int = 24,
        reusable_statuses: set[str] | None = None,
        source_url: str | None = None,
        allow_title_only_reuse: bool = False,
    ) -> dict | None:
        """
        同タイトルの直近投稿を返す。
        単発スクリプトの再送や確認失敗時の二重作成を防ぐために使う。
        """
        normalized = self._normalize_title(title)
        normalized_source_url = self._normalize_source_url(source_url)
        if not normalized or len(normalized) < 6:
            return None

        after = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
        search_fields = ",".join(
            [
                "id",
                "date",
                "date_gmt",
                "title",
                "status",
                "featured_media",
                "categories",
                "meta",
                *self._source_url_meta_keys(),
            ]
        )
        query_variants = [
            {
                "search": title[:40],
                "per_page": 20,
                "status": "any",
                "context": "edit",
                "after": after,
                "_fields": search_fields,
            },
            {
                "search": title[:40],
                "per_page": 20,
                "after": after,
                "_fields": search_fields,
            },
        ]

        last_error = None
        for params in query_variants:
            try:
                resp = self._request_with_retry(
                    requests.get,
                    f"{self.api}/posts",
                    action="既存記事検索",
                    params=params,
                )
                for post in resp.json():
                    title_data = post.get("title") or {}
                    rendered = title_data.get("raw") or title_data.get("rendered") or ""
                    status = (post.get("status") or "").lower()
                    if reusable_statuses is not None and status not in reusable_statuses:
                        continue
                    if not self._is_recent_post(post, within_hours):
                        continue
                    if self._normalize_title(rendered) == normalized:
                        candidate = post
                        if normalized_source_url:
                            _, existing_source_url = self._get_source_url_meta(candidate)
                            if not existing_source_url and candidate.get("id"):
                                detailed = self._load_post_detail_for_reuse(int(candidate["id"]))
                                if detailed:
                                    candidate = detailed
                                    _, existing_source_url = self._get_source_url_meta(candidate)
                            if existing_source_url == normalized_source_url:
                                return self._mark_reuse_reason(candidate, "source_url_match")
                        if allow_title_only_reuse:
                            return self._mark_reuse_reason(candidate, "title_fallback")
                return None
            except Exception as e:
                last_error = e

        if last_error:
            print(f"[WP] 既存記事検索失敗（公開は継続）: {last_error}")
        return None

    def _reuse_existing_post(
        self,
        existing: dict,
        title: str,
        categories: list | None = None,
        status: str = "publish",
        featured_media: int | None = None,
        source_url: str | None = None,
    ) -> int:
        post_id = existing["id"]
        existing_status = (existing.get("status") or "").lower()
        update_fields = {}
        source_meta_key, existing_source_url = self._get_source_url_meta(existing)
        normalized_source_url = self._normalize_source_url(source_url)

        if featured_media and not existing.get("featured_media"):
            update_fields["featured_media"] = featured_media

        if categories:
            existing_categories = set(existing.get("categories") or [])
            requested_categories = set(categories)
            if (
                requested_categories
                and requested_categories != existing_categories
                and existing_status in {"draft", "pending", "future", "auto-draft"}
            ):
                update_fields["categories"] = categories

        requested_status = (status or "publish").lower()
        if requested_status == "publish" and existing_status != "publish":
            update_fields["status"] = "publish"

        if normalized_source_url and not existing_source_url:
            source_meta_payload = self._build_source_url_meta_payload(
                normalized_source_url,
                preferred_key=source_meta_key,
            )
            if source_meta_payload:
                update_fields["meta"] = source_meta_payload

        if update_fields:
            self.update_post_fields(post_id, **update_fields)
            print(f"[WP] 既存記事を更新 post_id={post_id} fields={','.join(update_fields.keys())}")

        reuse_reason = existing.get("_yoshilover_reuse_reason", "title_fallback")
        print(f"[WP] 既存記事を再利用 post_id={post_id} title={title!r} reuse_reason={reuse_reason}")
        return post_id

    # ------------------------------------------------------------------
    # 記事投稿（status指定可）
    # ------------------------------------------------------------------
    def create_post(self, title: str, content: str, categories: list = None,
                    status: str = "publish", featured_media: int = None,
                    source_url: str | None = None,
                    allow_title_only_reuse: bool | None = None) -> int:
        requested_status = (status or "publish").lower()
        normalized_source_url = self._normalize_source_url(source_url)
        if allow_title_only_reuse is None:
            allow_title_only_reuse = not bool(normalized_source_url)
        reusable_statuses = None
        if requested_status == "draft":
            reusable_statuses = {"draft", "pending", "future", "auto-draft"}
        elif requested_status == "publish":
            reusable_statuses = {"publish", "draft", "pending", "future", "auto-draft"}

        existing = self.find_recent_post_by_title(
            title,
            reusable_statuses=reusable_statuses,
            source_url=normalized_source_url,
            allow_title_only_reuse=allow_title_only_reuse,
        )
        if existing:
            return self._reuse_existing_post(
                existing,
                title,
                categories=categories,
                status=status,
                featured_media=featured_media,
                source_url=normalized_source_url,
            )

        payload = {
            "title":   title,
            "content": content,
            "status":  status,
        }
        if categories:
            payload["categories"] = categories
        if featured_media:
            payload["featured_media"] = featured_media
        source_meta_payload = self._build_source_url_meta_payload(normalized_source_url)
        if source_meta_payload:
            payload["meta"] = source_meta_payload

        resp = self._request_with_retry(
            requests.post,
            f"{self.api}/posts",
            action=f"記事{status}",
            json=payload,
            headers=self.headers,
        )
        post_id = resp.json()["id"]
        print(f"[WP] 記事{status} post_id={post_id} title={title!r}")
        return post_id

    # ------------------------------------------------------------------
    # 画像URLからWPメディアへアップロード
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_content_type(header_text: str) -> str:
        content_type = ""
        for line in (header_text or "").splitlines():
            if line.lower().startswith("content-type:"):
                content_type = line.split(":", 1)[1].strip()
        return WPClient._normalize_content_type(content_type) or "image/jpeg"

    @staticmethod
    def _normalize_content_type(content_type: str) -> str:
        return (content_type or "").split(";", 1)[0].strip().lower()

    @staticmethod
    def _download_image_via_curl(url: str, timeout: int = 15) -> tuple[bytes, str]:
        header_res = subprocess.run(
            ["curl", "-fsSL", "-A", HTTP_USER_AGENT, "-D", "-", "-o", "/dev/null", url],
            capture_output=True,
            check=True,
            timeout=timeout + 5,
        )
        body_res = subprocess.run(
            ["curl", "-fsSL", "-A", HTTP_USER_AGENT, url],
            capture_output=True,
            check=True,
            timeout=timeout + 5,
        )
        content_type = WPClient._parse_content_type(header_res.stdout.decode("iso-8859-1", errors="ignore"))
        return body_res.stdout, content_type

    def upload_image_from_url(self, image_url: str, filename: str = None, source_url: str = "") -> int:
        """
        外部画像URLをダウンロードしてWPメディアライブラリにアップロード。
        Returns: media_id (int)、失敗時は 0
        """
        try:
            normalized_url = html.unescape((image_url or "").strip())
            normalized_source_url = html.unescape((source_url or "").strip()) or normalized_url
            print(f"[WP] 画像アップロード開始 image_url={normalized_url}")
            url_exclusion_reason = self._get_image_candidate_exclusion_reason(normalized_url)
            if url_exclusion_reason:
                self._log_image_candidate_excluded(url_exclusion_reason, normalized_url, normalized_source_url)
                print(
                    "[WP] 画像アップロードskip: "
                    f"excluded_reason={url_exclusion_reason} image_url={normalized_url}"
                )
                return 0
            try:
                img_resp = requests.get(
                    normalized_url,
                    timeout=15,
                    headers={"User-Agent": HTTP_USER_AGENT},
                )
                img_resp.raise_for_status()
                image_data = img_resp.content
                content_type = self._normalize_content_type(img_resp.headers.get("Content-Type", "image/jpeg"))
            except Exception:
                image_data, content_type = self._download_image_via_curl(normalized_url, timeout=15)
                content_type = self._normalize_content_type(content_type)

            print(f"[WP] 画像ダウンロード Content-Type={content_type or 'unknown'} image_url={normalized_url}")
            mime_exclusion_reason = self._get_image_mime_exclusion_reason(content_type)
            if mime_exclusion_reason:
                self._log_image_candidate_excluded(mime_exclusion_reason, normalized_url, normalized_source_url)
            ext = ALLOWED_IMAGE_CONTENT_TYPES.get(content_type)
            if not ext:
                print(
                    "[WP] 画像アップロードskip: "
                    f"unsupported_content_type={content_type or 'unknown'} image_url={normalized_url}"
                )
                return 0
            if not filename:
                import hashlib
                filename = hashlib.md5(normalized_url.encode()).hexdigest()[:12] + f".{ext}"
            print(f"[WP] 画像アップロード filename={filename} Content-Type={content_type}")

            resp = self._request_with_retry(
                requests.post,
                f"{self.api}/media",
                action="画像アップロード",
                data=image_data,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": content_type,
                },
            )
            media_id = resp.json()["id"]
            print(f"[WP] 画像アップロード media_id={media_id}")
            return media_id
        except Exception as e:
            print(f"[WP] 画像アップロード失敗（スキップ）: {e}")
            return 0

    def upload_generated_image(self, image_data: bytes, filename: str, content_type: str) -> int:
        """生成済みの画像bytesをWPメディアにアップロードする。"""
        try:
            normalized_content_type = self._normalize_content_type(content_type)
            normalized_filename = (filename or "structured-eyecatch.svg").strip() or "structured-eyecatch.svg"
            if not image_data:
                print("[WP] 生成画像アップロードskip: empty_image_data")
                return 0
            if normalized_content_type not in {"image/svg+xml", "image/png", "image/jpeg", "image/webp"}:
                print(
                    "[WP] 生成画像アップロードskip: "
                    f"unsupported_content_type={normalized_content_type or 'unknown'} filename={normalized_filename}"
                )
                return 0
            resp = self._request_with_retry(
                requests.post,
                f"{self.api}/media",
                action="生成画像アップロード",
                data=image_data,
                headers={
                    "Content-Disposition": f'attachment; filename="{normalized_filename}"',
                    "Content-Type": normalized_content_type,
                },
            )
            media_id = resp.json()["id"]
            print(
                f"[WP] 生成画像アップロード media_id={media_id} "
                f"filename={normalized_filename} content_type={normalized_content_type}"
            )
            return int(media_id)
        except Exception as e:
            print(f"[WP] 生成画像アップロード失敗（スキップ）: {e}")
            return 0

    # ------------------------------------------------------------------
    # 下書き投稿
    # ------------------------------------------------------------------
    def create_draft(
        self,
        title: str,
        content: str,
        categories: list = None,
        featured_media: int = None,
        source_url: str | None = None,
        allow_title_only_reuse: bool | None = None,
    ) -> int:
        """
        WordPressに下書き記事を作成して post_id を返す。

        Args:
            title:      記事タイトル
            content:    記事本文（HTML / Gutenbergブロック）
            categories: WPカテゴリIDのリスト（例: [3, 5]）

        Returns:
            作成された投稿の post_id (int)
        """
        normalized_source_url = self._normalize_source_url(source_url)
        if allow_title_only_reuse is None:
            allow_title_only_reuse = not bool(normalized_source_url)
        existing = self.find_recent_post_by_title(
            title,
            reusable_statuses={"draft", "pending", "future", "auto-draft"},
            source_url=normalized_source_url,
            allow_title_only_reuse=allow_title_only_reuse,
        )
        if existing:
            return self._reuse_existing_post(
                existing,
                title,
                categories=categories,
                status="draft",
                featured_media=featured_media,
                source_url=normalized_source_url,
            )

        payload = {
            "title":   title,
            "content": content,
            "status":  "draft",
        }
        if categories:
            payload["categories"] = categories
        if featured_media:
            payload["featured_media"] = featured_media
        source_meta_payload = self._build_source_url_meta_payload(normalized_source_url)
        if source_meta_payload:
            payload["meta"] = source_meta_payload

        resp = self._request_with_retry(
            requests.post,
            f"{self.api}/posts",
            action="下書き作成",
            json=payload,
            headers=self.headers,
        )
        post_id = resp.json()["id"]
        print(f"[WP] 下書き作成 post_id={post_id} title={title!r}")
        return post_id

    def update_post_fields(self, post_id: int, **fields) -> None:
        """記事の任意フィールドを更新（featured_media など）"""
        payload = {k: v for k, v in fields.items() if v is not None}
        if not payload:
            return
        resp = self._request_with_retry(
            requests.post,
            f"{self.api}/posts/{post_id}",
            action=f"記事更新 post_id={post_id}",
            auth=self.auth,
            json=payload,
        )

    # ------------------------------------------------------------------
    # 記事取得
    # ------------------------------------------------------------------
    def get_post(self, post_id: int) -> dict:
        """
        投稿IDで記事を取得して dict を返す。
        """
        resp = self._request_with_retry(
            requests.get,
            f"{self.api}/posts/{post_id}",
            action=f"記事取得 post_id={post_id}",
        )
        return resp.json()

    def list_posts(
        self,
        status: str = "draft",
        per_page: int = 20,
        page: int = 1,
        orderby: str = "modified",
        order: str = "desc",
        search: str = "",
        context: str | None = "edit",
        fields: list[str] | None = None,
    ) -> list[dict]:
        """
        投稿一覧を取得する。

        Args:
            status:   draft / publish / any など
            per_page: 1〜100
            page:     ページ番号
            orderby:  modified / date など
            order:    desc / asc
            search:   検索キーワード
            context:  edit を使うと raw content も取得しやすい
            fields:   _fields に渡す一覧

        Returns:
            投稿 dict の配列
        """
        params = {
            "status": status,
            "per_page": max(1, min(per_page, 100)),
            "page": max(1, page),
            "orderby": orderby,
            "order": order,
        }
        if search.strip():
            params["search"] = search.strip()
        if context:
            params["context"] = context
        if fields:
            params["_fields"] = ",".join(fields)

        query_variants = [params]
        if context:
            relaxed = dict(params)
            relaxed.pop("context", None)
            query_variants.append(relaxed)

        last_error = None
        seen = set()
        for variant in query_variants:
            key = tuple(sorted(variant.items()))
            if key in seen:
                continue
            seen.add(key)
            try:
                resp = self._request_with_retry(
                    requests.get,
                    f"{self.api}/posts",
                    action=f"記事一覧取得 status={status}",
                    params=variant,
                )
                return resp.json()
            except Exception as e:
                last_error = e

        if last_error:
            raise last_error
        return []

    def update_post_status(self, post_id: int, status: str) -> None:
        """記事のステータスを更新（draft → publish など）"""
        resp = self._request_with_retry(
            requests.post,
            f"{self.api}/posts/{post_id}",
            action=f"ステータス更新 post_id={post_id}",
            json={"status": status},
        )

    # ------------------------------------------------------------------
    # カテゴリ一覧
    # ------------------------------------------------------------------
    def get_categories(self) -> list:
        """
        カテゴリ一覧を [{id, name, slug}, ...] で返す。
        """
        resp = self._request_with_retry(
            requests.get,
            f"{self.api}/categories",
            action="カテゴリ取得",
            params={"per_page": 100},
        )
        return [{"id": c["id"], "name": c["name"], "slug": c["slug"]}
                for c in resp.json()]

    # ------------------------------------------------------------------
    # カテゴリ名 → ID 変換
    # ------------------------------------------------------------------
    def resolve_category_id(self, name: str) -> int:
        """
        カテゴリ名からWP IDを返す。
        まず config/categories.json を参照し、0（未設定）なら
        WP REST APIから取得して照合する。

        Args:
            name: カテゴリ名（例: "試合速報"）

        Returns:
            カテゴリID (int)。見つからない場合は 0。
        """
        cats_file = ROOT / "config" / "categories.json"
        if cats_file.exists():
            with open(cats_file, encoding="utf-8") as f:
                mapping = json.load(f)
            if name in mapping and mapping[name] != 0:
                return mapping[name]

        # JSONが未設定の場合はAPIから取得
        for cat in self.get_categories():
            if cat["name"] == name:
                return cat["id"]

        print(f"[WP] 警告: カテゴリ '{name}' が見つかりません。0を返します。")
        return 0

    # ------------------------------------------------------------------
    # エラーハンドリング
    # ------------------------------------------------------------------
    def _raise_for_status(self, resp: requests.Response, action: str):
        if resp.status_code == 401:
            raise PermissionError(
                f"[WP] 認証失敗（{action}）: .env の WP_USER / WP_APP_PASSWORD を確認してください"
            )
        if resp.status_code == 403:
            raise PermissionError(
                f"[WP] アクセス拒否（{action}）: WP管理画面 → 設定 → パーマリンク → 「投稿名」→ 保存 を試してください"
            )
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"[WP] HTTPエラー（{action}）: {e}\nレスポンス: {resp.text[:300]}")


# ------------------------------------------------------------------
# CLI: 疎通テスト
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="WP REST API 疎通テスト")
    parser.add_argument("--test", action="store_true", help="カテゴリ一覧を取得して表示")
    parser.add_argument("--test-draft", action="store_true", help="テスト下書きを1件作成")
    args = parser.parse_args()

    wp = WPClient()

    if args.test:
        print(f"接続先: {wp.base_url}")
        print("カテゴリ一覧を取得中...")
        cats = wp.get_categories()
        if cats:
            print(f"取得成功！ {len(cats)}件のカテゴリ:")
            for c in cats:
                print(f"  ID={c['id']:3d}  {c['name']}  ({c['slug']})")
        else:
            print("カテゴリが0件です（カテゴリを作成してください）")
        return

    if args.test_draft:
        print("テスト下書きを作成中...")
        post_id = wp.create_draft(
            title="【テスト】wp_client.py 疎通確認",
            content="<p>このテスト下書きは削除してください。</p>",
        )
        print(f"成功！ post_id={post_id}")
        print(f"確認URL: {wp.base_url}/wp-admin/post.php?post={post_id}&action=edit")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
