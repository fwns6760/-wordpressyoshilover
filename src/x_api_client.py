"""
x_api_client.py — X API連携（投稿・収集）CLIスクリプト

使用例:
    # WP記事をXに投稿
    python3 src/x_api_client.py post --post-id 123

    # 巨人関連ポストを収集してWP下書きに変換
    python3 src/x_api_client.py collect
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

# vendorディレクトリをパスに追加（サーバー環境用）
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import tweepy
from wp_client import WPClient
from x_post_generator import build_post
from wp_draft_creator import build_oembed_block

# ──────────────────────────────────────────────────────────
# カテゴリ別X投稿テンプレート
# ──────────────────────────────────────────────────────────
X_TEMPLATES = {
    "試合速報":      ["【速報】{title}🔥 巨人ファンの声はこちら👇\n{url}\n{tags}",
                     "【試合速報】{title} 詳細・みんなの反応👇\n{url}\n{tags}"],
    "選手情報":      ["{title} 詳細はこちら👇\n{url}\n{tags}",
                     "【選手情報】{title} ファンの反応も👇\n{url}\n{tags}"],
    "補強・移籍":    ["【速報】{title} ファン騒然👇\n{url}\n{tags}",
                     "【移籍情報】{title} 詳細はこちら👇\n{url}\n{tags}"],
    "首脳陣":        ["【首脳陣】{title} 采配への声はこちら👇\n{url}\n{tags}"],
    "ドラフト・育成": ["【育成情報】{title} 詳細👇\n{url}\n{tags}"],
    "OB・解説者":    ["{title} 詳細はこちら👇\n{url}\n{tags}"],
    "球団情報":      ["【球団情報】{title} 詳細👇\n{url}\n{tags}"],
    "コラム":        ["{title} 👇\n{url}\n{tags}"],
}
X_DEFAULT_TEMPLATE = "{title} 詳細はこちら👇\n{url}\n{tags}"
X_HASHTAGS = "#巨人 #ジャイアンツ #読売ジャイアンツ"

import random

def build_x_post_text(title: str, url: str, category: str = "コラム") -> str:
    templates = X_TEMPLATES.get(category, [X_DEFAULT_TEMPLATE])
    template  = random.choice(templates)
    text = template.format(title=title, url=url, tags=X_HASHTAGS)
    # 280字に収める（URL=23字換算）
    max_len = 280 - 23 + len(url)
    if len(text) > max_len:
        cut = max_len - len(url) - len(X_HASHTAGS) - 20
        title = title[:cut] + "…"
        text = template.format(title=title, url=url, tags=X_HASHTAGS)
    return text

# ──────────────────────────────────────────────────────────
# ログ設定
# ──────────────────────────────────────────────────────────
LOG_FILE = ROOT / "logs" / "x_api.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────────────────
HISTORY_FILE = ROOT / "data" / "rss_history.json"
AUTO_POST_CATEGORY_ID = 673
COLLECT_INTERVAL_HOURS = 10  # 1日2〜3回に制限
COLLECT_QUERIES = [
    "from:TokyoGiants -is:retweet",
    "from:hochi_giants -is:retweet",
    "from:nikkansports 巨人 -is:retweet",
    "from:Sanspo_Giants -is:retweet",
    "from:tospo_giants -is:retweet",
    "from:koba_nikkan 巨人 -is:retweet",
]
COLLECT_MAX_RESULTS = 10  # 1クエリあたりの最大取得件数

# ──────────────────────────────────────────────────────────
# 認証
# ──────────────────────────────────────────────────────────
def x_collect_enabled() -> bool:
    return os.environ.get("ENABLE_X_COLLECT", "0").strip().lower() in {"1", "true", "yes", "on"}


def get_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=os.environ.get("X_BEARER_TOKEN"),
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def select_primary_category_name(cat_ids: list[int], categories: list[dict]) -> str:
    id_to_name = {c["id"]: c["name"] for c in categories}
    preferred_ids = [
        cat_id for cat_id in cat_ids
        if cat_id != AUTO_POST_CATEGORY_ID and id_to_name.get(cat_id) not in {"自動投稿"}
    ]
    selected_id = preferred_ids[0] if preferred_ids else (cat_ids[0] if cat_ids else None)
    return id_to_name.get(selected_id, "コラム")


def build_post_context(post: dict) -> tuple[str, str]:
    content_raw = post.get("content", {}).get("rendered", "")
    summary = content_raw
    if content_raw:
        import re as _re
        summary = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", content_raw)).strip()[:1500]
    return summary, content_raw

# ──────────────────────────────────────────────────────────
# postサブコマンド — WP記事をXに投稿
# ──────────────────────────────────────────────────────────
def cmd_post(args):
    wp = WPClient()
    post = wp.get_post(args.post_id)

    import re
    title = re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", ""))
    title = title.replace("&#8211;", "–").replace("&amp;", "&").replace("&quot;", '"')
    url = post.get("link", "")

    cat_ids = post.get("categories", [])
    category = select_primary_category_name(cat_ids, wp.get_categories())
    summary, content_html = build_post_context(post)
    tweet_text = build_post(title, url, category, summary=summary, content_html=content_html)

    if args.dry_run:
        print("[DRY RUN] 投稿内容:")
        print(tweet_text)
        return

    client = get_client()
    response = client.create_tweet(text=tweet_text)
    tweet_id = response.data["id"]
    logger.info(f"[post] 投稿成功 tweet_id={tweet_id} post_id={args.post_id}")
    print(f"投稿完了: https://x.com/i/web/status/{tweet_id}")

# ──────────────────────────────────────────────────────────
# collectサブコマンド — 巨人関連ポストを収集してWP下書きに変換
# ──────────────────────────────────────────────────────────
def load_history() -> dict:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history: dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def can_collect(history: dict) -> bool:
    last = history.get("x_collect_last_run")
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    return datetime.now() - last_dt >= timedelta(hours=COLLECT_INTERVAL_HOURS)

def cmd_collect(args):
    if not x_collect_enabled():
        logger.info("[collect] スキップ（ENABLE_X_COLLECT=0）")
        return

    history = load_history()

    if not args.force and not can_collect(history):
        last = history.get("x_collect_last_run")
        logger.info(f"[collect] スキップ（前回実行: {last}、{COLLECT_INTERVAL_HOURS}時間制限）")
        return

    posted_ids = set(history.get("x_collected_ids", []))
    client = get_client()
    wp = WPClient()

    total_fetched = 0
    total_drafted = 0

    for query in COLLECT_QUERIES:
        logger.info(f"[collect] 検索: {query}")
        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=COLLECT_MAX_RESULTS,
                tweet_fields=["created_at", "author_id", "text"],
            )
        except Exception as e:
            logger.error(f"[collect] 検索失敗: {e}")
            continue

        if not response.data:
            continue

        total_fetched += len(response.data)

        for tweet in response.data:
            tweet_id = str(tweet.id)
            if tweet_id in posted_ids:
                continue

            tweet_url = f"https://x.com/i/web/status/{tweet_id}"
            title = tweet.text[:50] + ("…" if len(tweet.text) > 50 else "")
            body = build_oembed_block(tweet_url)

            if args.dry_run:
                print(f"[DRY RUN] 下書き作成: {title}")
                print(f"  URL: {tweet_url}")
            else:
                draft_id = wp.create_draft(title, body, categories=[AUTO_POST_CATEGORY_ID])
                logger.info(f"[collect] 下書き作成 draft_id={draft_id} tweet_id={tweet_id}")
                total_drafted += 1

            posted_ids.add(tweet_id)

    # 履歴更新（直近2000件だけ保持）
    history["x_collected_ids"] = list(posted_ids)[-2000:]
    history["x_collect_last_run"] = datetime.now().isoformat()
    if not args.dry_run:
        save_history(history)

    logger.info(f"[collect] 完了 取得={total_fetched}件 下書き={total_drafted}件")

# ──────────────────────────────────────────────────────────
# CLIエントリーポイント
# ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="X API連携クライアント")
    sub = parser.add_subparsers(dest="command")

    p_post = sub.add_parser("post", help="WP記事をXに投稿")
    p_post.add_argument("--post-id", type=int, required=True, help="WP投稿ID")
    p_post.add_argument("--dry-run", action="store_true", help="実際には投稿しない")

    p_collect = sub.add_parser("collect", help="巨人関連ポストを収集してWP下書きに変換")
    p_collect.add_argument("--dry-run", action="store_true", help="実際には下書き作成しない")
    p_collect.add_argument("--force", action="store_true", help="インターバル制限を無視して実行")

    args = parser.parse_args()

    if args.command == "post":
        cmd_post(args)
    elif args.command == "collect":
        cmd_collect(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
