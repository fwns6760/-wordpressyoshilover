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
import re
import subprocess
from datetime import datetime, timedelta, timezone

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


class WPClient:
    def __init__(self):
        self.base_url    = os.getenv("WP_URL", "").rstrip("/")
        self.user        = os.getenv("WP_USER", "")
        self.app_password = os.getenv("WP_APP_PASSWORD", "")

        if not all([self.base_url, self.user, self.app_password]):
            raise ValueError(".env に WP_URL / WP_USER / WP_APP_PASSWORD が設定されていません")

        self.auth    = (self.user, self.app_password)
        self.api     = f"{self.base_url}/wp-json/wp/v2"
        self.headers = {"Content-Type": "application/json"}

    @staticmethod
    def _normalize_title(title: str) -> str:
        return re.sub(r"[\s　【】「」『』〔〕（）()・\\/_-]", "", (title or "")).lower()

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
        within_hours: int = 2,
        reusable_statuses: set[str] | None = None,
    ) -> dict | None:
        """
        同タイトルの直近投稿を返す。
        単発スクリプトの再送や確認失敗時の二重作成を防ぐために使う。
        """
        normalized = self._normalize_title(title)
        if not normalized or len(normalized) < 6:
            return None

        after = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
        query_variants = [
            {
                "search": title[:40],
                "per_page": 20,
                "status": "any",
                "context": "edit",
                "after": after,
                "_fields": "id,date,date_gmt,title,status,featured_media,categories",
            },
            {
                "search": title[:40],
                "per_page": 20,
                "after": after,
                "_fields": "id,date,date_gmt,title,status,featured_media,categories",
            },
        ]

        last_error = None
        for params in query_variants:
            try:
                resp = requests.get(
                    f"{self.api}/posts",
                    params=params,
                    auth=self.auth,
                    timeout=30,
                )
                self._raise_for_status(resp, "既存記事検索")
                for post in resp.json():
                    title_data = post.get("title") or {}
                    rendered = title_data.get("raw") or title_data.get("rendered") or ""
                    status = (post.get("status") or "").lower()
                    if reusable_statuses is not None and status not in reusable_statuses:
                        continue
                    if not self._is_recent_post(post, within_hours):
                        continue
                    if self._normalize_title(rendered) == normalized:
                        return post
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
    ) -> int:
        post_id = existing["id"]
        existing_status = (existing.get("status") or "").lower()
        update_fields = {}

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

        if update_fields:
            self.update_post_fields(post_id, **update_fields)
            print(f"[WP] 既存記事を更新 post_id={post_id} fields={','.join(update_fields.keys())}")

        print(f"[WP] 既存記事を再利用 post_id={post_id} title={title!r}")
        return post_id

    # ------------------------------------------------------------------
    # 記事投稿（status指定可）
    # ------------------------------------------------------------------
    def create_post(self, title: str, content: str, categories: list = None,
                    status: str = "publish", featured_media: int = None) -> int:
        requested_status = (status or "publish").lower()
        reusable_statuses = None
        if requested_status == "draft":
            reusable_statuses = {"draft", "pending", "future", "auto-draft"}
        elif requested_status == "publish":
            reusable_statuses = {"publish", "draft", "pending", "future", "auto-draft"}

        existing = self.find_recent_post_by_title(title, reusable_statuses=reusable_statuses)
        if existing:
            return self._reuse_existing_post(
                existing,
                title,
                categories=categories,
                status=status,
                featured_media=featured_media,
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

        resp = requests.post(
            f"{self.api}/posts",
            json=payload,
            auth=self.auth,
            headers=self.headers,
            timeout=30,
        )
        self._raise_for_status(resp, f"記事{status}")
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

    def upload_image_from_url(self, image_url: str, filename: str = None) -> int:
        """
        外部画像URLをダウンロードしてWPメディアライブラリにアップロード。
        Returns: media_id (int)、失敗時は 0
        """
        try:
            normalized_url = html.unescape((image_url or "").strip())
            print(f"[WP] 画像アップロード開始 image_url={normalized_url}")
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

            resp = requests.post(
                f"{self.api}/media",
                data=image_data,
                auth=self.auth,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": content_type,
                },
                timeout=30,
            )
            self._raise_for_status(resp, "画像アップロード")
            media_id = resp.json()["id"]
            print(f"[WP] 画像アップロード media_id={media_id}")
            return media_id
        except Exception as e:
            print(f"[WP] 画像アップロード失敗（スキップ）: {e}")
            return 0

    # ------------------------------------------------------------------
    # 下書き投稿
    # ------------------------------------------------------------------
    def create_draft(self, title: str, content: str, categories: list = None, featured_media: int = None) -> int:
        """
        WordPressに下書き記事を作成して post_id を返す。

        Args:
            title:      記事タイトル
            content:    記事本文（HTML / Gutenbergブロック）
            categories: WPカテゴリIDのリスト（例: [3, 5]）

        Returns:
            作成された投稿の post_id (int)
        """
        existing = self.find_recent_post_by_title(
            title,
            reusable_statuses={"draft", "pending", "future", "auto-draft"},
        )
        if existing:
            return self._reuse_existing_post(
                existing,
                title,
                categories=categories,
                status="draft",
                featured_media=featured_media,
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

        resp = requests.post(
            f"{self.api}/posts",
            json=payload,
            auth=self.auth,
            headers=self.headers,
            timeout=30,
        )
        self._raise_for_status(resp, "下書き作成")
        post_id = resp.json()["id"]
        print(f"[WP] 下書き作成 post_id={post_id} title={title!r}")
        return post_id

    def update_post_fields(self, post_id: int, **fields) -> None:
        """記事の任意フィールドを更新（featured_media など）"""
        payload = {k: v for k, v in fields.items() if v is not None}
        if not payload:
            return
        resp = requests.post(
            f"{self.api}/posts/{post_id}",
            auth=self.auth,
            json=payload,
            timeout=30,
        )
        self._raise_for_status(resp, f"記事更新 post_id={post_id}")

    # ------------------------------------------------------------------
    # 記事取得
    # ------------------------------------------------------------------
    def get_post(self, post_id: int) -> dict:
        """
        投稿IDで記事を取得して dict を返す。
        """
        resp = requests.get(
            f"{self.api}/posts/{post_id}",
            auth=self.auth,
            timeout=30,
        )
        self._raise_for_status(resp, f"記事取得 post_id={post_id}")
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
                resp = requests.get(
                    f"{self.api}/posts",
                    params=variant,
                    auth=self.auth,
                    timeout=30,
                )
                self._raise_for_status(resp, f"記事一覧取得 status={status}")
                return resp.json()
            except Exception as e:
                last_error = e

        if last_error:
            raise last_error
        return []

    def update_post_status(self, post_id: int, status: str) -> None:
        """記事のステータスを更新（draft → publish など）"""
        resp = requests.post(
            f"{self.api}/posts/{post_id}",
            auth=self.auth,
            json={"status": status},
            timeout=30,
        )
        self._raise_for_status(resp, f"ステータス更新 post_id={post_id}")

    # ------------------------------------------------------------------
    # カテゴリ一覧
    # ------------------------------------------------------------------
    def get_categories(self) -> list:
        """
        カテゴリ一覧を [{id, name, slug}, ...] で返す。
        """
        resp = requests.get(
            f"{self.api}/categories",
            params={"per_page": 100},
            auth=self.auth,
            timeout=30,
        )
        self._raise_for_status(resp, "カテゴリ取得")
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
