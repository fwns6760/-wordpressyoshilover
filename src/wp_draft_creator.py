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
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# vendorディレクトリをパスに追加（サーバー環境用）
ROOT = Path(__file__).parent.parent
_vendor = str(ROOT / 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)
sys.path.insert(0, str(Path(__file__).parent))

from wp_client import WPClient

POSTED_URLS_FILE = ROOT / "data" / "posted_urls.json"


# ------------------------------------------------------------------
# URL guard — build_oembed_block 入力検証用
#
# RELIABILITY-2026-05-08-G: 13:04 JST incident で hochi.news 等の非 X URL を
# build_oembed_block に渡したところ、Twitter widgets.js が render できず
# 本文ゼロ表示 (10 posts thin-body publish) になった。検出に使う helper を
# export し、callers (rss_fetcher / x_api_client / 本 module) が事前に check
# できるようにする。本 module 自身は build_oembed_block 内で warning log のみ
# 出し、enforce は upstream + WP create_post chokepoint の STOP gate
# (thin_body_validator) に任せる (二重防御)。
# ------------------------------------------------------------------

_X_URL_HOSTS = frozenset(
    [
        "x.com",
        "twitter.com",
        "mobile.twitter.com",
        "mobile.x.com",
        "www.twitter.com",
        "www.x.com",
    ]
)

_logger = logging.getLogger("wp_draft_creator")


def is_x_url(url: str) -> bool:
    """Return True if URL is an X / Twitter URL.

    Used by callers to decide whether ``build_oembed_block`` is safe to call
    (X URL → tweet が render される) or whether to fall back to a different
    body generator (非 X URL → tweet として render されない、本文崩壊リスク)。

    URL path / query は問わない、host のみで判定。
    """
    if not url:
        return False
    try:
        parsed = urlparse(str(url))
        host = (parsed.netloc or "").lower()
        # strip optional port
        if ":" in host:
            host = host.split(":", 1)[0]
        return host in _X_URL_HOSTS
    except Exception:
        return False


# ------------------------------------------------------------------
# X埋め込みHTML生成
# ------------------------------------------------------------------
def build_x_widget_script_block() -> str:
    return (
        '<!-- wp:html -->\n'
        '<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>\n'
        '<!-- /wp:html -->'
    )


def build_oembed_block(url: str, compact: bool = False, include_script: bool = True) -> str:
    # twitter.com 形式に統一し、公式 blockquote 埋め込みを使う。
    # wp:embed の 16:9 ラッパーを避け、余白と初期表示の遅さを抑える。
    #
    # RELIABILITY-2026-05-08-G: 非 X URL を受け取った時 warning log を出す。
    # tweet 化されず本文崩壊につながるため。enforce は upstream caller + WP
    # create_post の STOP gate (thin_body_validator) で行う (二重防御)。
    if url and not is_x_url(url):
        _logger.warning(
            "build_oembed_block_non_x_url url=%s — Twitter widgets.js は非 X URL を "
            "tweet 化できないため本文崩壊につながる可能性。caller 側で is_x_url() で "
            "事前 check するか、非 X URL は別 body 生成 path に流すこと。",
            url,
        )
    embed_url = url.replace("https://x.com/", "https://twitter.com/")
    wrapper_class = "yoshilover-x-embed yoshilover-x-embed-compact" if compact else "yoshilover-x-embed"
    wrapper_style = "margin:0 auto 0 !important;max-width:550px;" if compact else "margin:24px auto !important;max-width:550px;"
    extra_attrs = ' data-conversation="none" data-cards="hidden"' if compact else ""
    script_block = ("\n" + build_x_widget_script_block()) if include_script else ""
    return (
        '<!-- wp:html -->\n'
        f'<div class="{wrapper_class}" style="{wrapper_style}">\n'
        f'  <blockquote class="twitter-tweet" data-dnt="true" data-lang="ja"{extra_attrs}>\n'
        f'    <a href="{embed_url}">{embed_url}</a>\n'
        '  </blockquote>\n'
        '</div>\n'
        '<!-- /wp:html -->'
        f'{script_block}'
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
