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

    # ------------------------------------------------------------------
    # 記事投稿（status指定可）
    # ------------------------------------------------------------------
    def create_post(self, title: str, content: str, categories: list = None,
                    status: str = "publish", featured_media: int = None) -> int:
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
    def upload_image_from_url(self, image_url: str, filename: str = None) -> int:
        """
        外部画像URLをダウンロードしてWPメディアライブラリにアップロード。
        Returns: media_id (int)、失敗時は 0
        """
        try:
            img_resp = requests.get(image_url, timeout=15)
            img_resp.raise_for_status()
            image_data = img_resp.content
            content_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
            ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
            if not filename:
                import hashlib
                filename = hashlib.md5(image_url.encode()).hexdigest()[:12] + f".{ext}"

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
    def create_draft(self, title: str, content: str, categories: list = None) -> int:
        """
        WordPressに下書き記事を作成して post_id を返す。

        Args:
            title:      記事タイトル
            content:    記事本文（HTML / Gutenbergブロック）
            categories: WPカテゴリIDのリスト（例: [3, 5]）

        Returns:
            作成された投稿の post_id (int)
        """
        payload = {
            "title":   title,
            "content": content,
            "status":  "draft",
        }
        if categories:
            payload["categories"] = categories

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
