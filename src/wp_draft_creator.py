"""
wp_draft_creator.py — XポストURLからWP下書きを自動生成するCLIスクリプト

使用例:
    python3 src/wp_draft_creator.py --url https://x.com/user/status/12345
    python3 src/wp_draft_creator.py --file urls.txt --category 試合速報
    python3 src/wp_draft_creator.py --url https://x.com/... --title "巨人が開幕3連勝" --category 試合速報
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

# vendorディレクトリをパスに追加（サーバー環境用）
ROOT = Path(__file__).parent.parent
_vendor = str(ROOT / 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)
sys.path.insert(0, str(Path(__file__).parent))

from wp_client import WPClient

POSTED_URLS_FILE = ROOT / "data" / "posted_urls.json"


# ------------------------------------------------------------------
# oEmbedブロックHTML生成
# ------------------------------------------------------------------
def build_oembed_block(url: str) -> str:
    # twitter.com 形式に統一（WP oEmbedはtwitter.comを認識する）
    embed_url = url.replace("https://x.com/", "https://twitter.com/")
    return (
        f'<!-- wp:embed {{"url":"{embed_url}","type":"rich","providerNameSlug":"twitter","responsive":true,"className":"wp-embed-aspect-16-9 wp-has-aspect-ratio"}} -->\n'
        f'<figure class="wp-block-embed is-type-rich is-provider-twitter wp-block-embed-twitter wp-embed-aspect-16-9 wp-has-aspect-ratio">\n'
        f'  <div class="wp-block-embed__wrapper">\n'
        f'    {embed_url}\n'
        f'  </div>\n'
        f'</figure>\n'
        f'<!-- /wp:embed -->'
    )


# ------------------------------------------------------------------
# 仮タイトル生成
# ------------------------------------------------------------------
def auto_title(url: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"X投稿 {today}"


# ------------------------------------------------------------------
# posted_urls.json の読み込み / 書き込み
# ------------------------------------------------------------------
def load_posted_urls() -> dict:
    if POSTED_URLS_FILE.exists():
        with open(POSTED_URLS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_posted_url(url: str, posted_urls: dict):
    POSTED_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    posted_urls[url] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with open(POSTED_URLS_FILE, "w", encoding="utf-8") as f:
        json.dump(posted_urls, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------
# 1件処理
# ------------------------------------------------------------------
def process_url(wp: WPClient, url: str, title: str, category_id: int, posted_urls: dict) -> bool:
    """
    1件のXポストURLを下書き投稿する。
    スキップした場合は False、投稿した場合は True を返す。
    """
    if url in posted_urls:
        print(f"[SKIP] 投稿済み: {url}")
        return False

    content = build_oembed_block(url)
    categories = [category_id] if category_id else None
    wp.create_draft(title, content, categories=categories)
    save_posted_url(url, posted_urls)
    return True


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="XポストURLからWP下書きを自動生成")
    parser.add_argument("--url",      help="XポストURL（単体）")
    parser.add_argument("--file",     help="URLリストファイルパス（1行1URL）")
    parser.add_argument("--category", help="カテゴリ名（例: 試合速報）", default="")
    parser.add_argument("--title",    help="記事タイトル手動指定", default="")
    args = parser.parse_args()

    if not args.url and not args.file:
        parser.print_help()
        sys.exit(1)

    wp = WPClient()
    posted_urls = load_posted_urls()

    # カテゴリID解決
    category_id = 0
    if args.category:
        category_id = wp.resolve_category_id(args.category)
        if category_id == 0:
            print(f"[警告] カテゴリ '{args.category}' が見つかりません。カテゴリなしで投稿します。")

    # URLリスト構築
    urls = []
    if args.url:
        urls.append(args.url.strip())
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"[エラー] ファイルが見つかりません: {args.file}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

    if not urls:
        print("[エラー] 処理するURLがありません")
        sys.exit(1)

    # 処理
    success = skip = error = 0
    for i, url in enumerate(urls, 1):
        title = args.title if args.title else auto_title(url)
        # 複数URL一括時は連番をタイトルに付加
        if len(urls) > 1 and not args.title:
            title = f"{title} ({i})"
        try:
            posted = process_url(wp, url, title, category_id, posted_urls)
            if posted:
                success += 1
            else:
                skip += 1
        except Exception as e:
            print(f"[ERROR] {url}: {e}")
            error += 1

    print(f"\n完了: 投稿={success} / スキップ={skip} / エラー={error}  合計={len(urls)}件")


if __name__ == "__main__":
    main()
