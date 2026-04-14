"""
manual_post.py — 手動で即座にWP公開＋X投稿するCLIスクリプト

使用例:
    python3 src/manual_post.py "岡本3号逆転弾！巨人3-1快勝" 試合速報
    python3 src/manual_post.py "岡本3号逆転弾！" 試合速報 --body "9回裏に飛び出した！"
    python3 src/manual_post.py "岡本3号逆転弾！" --dry-run
"""

import sys
import os
import json
import argparse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from wp_client import WPClient
from x_post_generator import build_post as build_x_post_text

CATEGORIES = ["試合速報", "選手情報", "首脳陣", "ドラフト・育成", "OB・解説者", "補強・移籍", "球団情報", "コラム"]
AUTO_POST_CATEGORY_ID = 673
GEMINI_FLASH_MODEL = "gemini-2.5-flash"
GEMINI_FLASH_THINKING_BUDGET = 0


# ──────────────────────────────────────────────────────────
# Geminiで記事本文生成
# ──────────────────────────────────────────────────────────
def generate_body_with_gemini(title: str, category: str, hint: str = "") -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    hint_line = f"補足情報: {hint}" if hint else ""
    prompt = f"""あなたは読売ジャイアンツの熱狂的なファンブロガーです。
以下のニュースについて、巨人ファン向けのブログ記事本文を書いてください。

タイトル: {title}
カテゴリ: {category}
{hint_line}

条件:
・300〜500文字
・ファン目線の感情・コメントを入れる
・「注目ポイント」などの見出しを1〜2個入れる
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグは使わない、改行のみ
・本文のみ出力"""

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0.85,
            "thinkingConfig": {"thinkingBudget": GEMINI_FLASH_THINKING_BUDGET},
        },
    }).encode("utf-8")

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FLASH_MODEL}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.load(res)
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[Gemini] 生成失敗: {e}")
        return ""


# ──────────────────────────────────────────────────────────
# 本文をWPブロックHTMLに変換
# ──────────────────────────────────────────────────────────
def to_wp_blocks(text: str) -> str:
    blocks = ""
    for p in [line.strip() for line in text.split("\n") if line.strip()]:
        if p.startswith("【") or p.startswith("■"):
            blocks += f'<!-- wp:heading {{"level":3}} -->\n<h3>{p}</h3>\n<!-- /wp:heading -->\n\n'
        elif "みなさんの意見はコメントで" in p:
            blocks += (
                f'<!-- wp:separator -->\n'
                f'<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
                f'<!-- /wp:separator -->\n\n'
                f'<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->\n'
                f'<div class="wp-block-buttons">\n'
                f'<!-- wp:button -->\n'
                f'<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="#respond" style="background-color:#F5811F;color:#fff;font-size:1.05em;padding:12px 28px;">💬 {p}</a></div>\n'
                f'<!-- /wp:button -->\n'
                f'</div>\n'
                f'<!-- /wp:buttons -->\n\n'
            )
        else:
            blocks += f'<!-- wp:paragraph -->\n<p>{p}</p>\n<!-- /wp:paragraph -->\n\n'
    return blocks.strip()


def main():
    parser = argparse.ArgumentParser(description="即座にWP公開＋X投稿")
    parser.add_argument("title",    help="記事タイトル")
    parser.add_argument("category", nargs="?", default="試合速報",
                        choices=CATEGORIES, help="カテゴリ（デフォルト: 試合速報）")
    parser.add_argument("--body",   default="", help="本文（省略時はGeminiが自動生成）")
    parser.add_argument("--no-x",   action="store_true", help="X投稿しない")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿しない")
    args = parser.parse_args()

    print(f"タイトル : {args.title}")
    print(f"カテゴリ : {args.category}")

    # 本文生成
    if args.body:
        body_text = args.body
        print(f"本文     : 手動入力")
    else:
        print("本文     : Gemini生成中...")
        body_text = generate_body_with_gemini(args.title, args.category)
        if body_text:
            print("─" * 40)
            print(body_text[:200] + "…" if len(body_text) > 200 else body_text)
            print("─" * 40)
        else:
            body_text = "詳細はこちらをご覧ください。"
            print("本文     : Gemini失敗、デフォルト文を使用")

    content = to_wp_blocks(body_text) if "\n" in body_text else f"<p>{body_text}</p>"

    if args.dry_run:
        print("\n[DRY RUN] WP公開・X投稿はスキップ")
        return

    wp = WPClient()
    category_id = wp.resolve_category_id(args.category)
    cats = [AUTO_POST_CATEGORY_ID]
    if category_id:
        cats.append(category_id)

    post_id = wp.create_post(args.title, content, categories=cats, status="publish")
    post    = wp.get_post(post_id)
    url     = post.get("link", "")
    print(f"\nWP公開完了: {url}")

    if not args.no_x:
        try:
            import tweepy
            tweet_text = build_x_post_text(args.title, url, args.category)
            client = tweepy.Client(
                bearer_token=os.environ.get("X_BEARER_TOKEN"),
                consumer_key=os.environ.get("X_API_KEY"),
                consumer_secret=os.environ.get("X_API_SECRET"),
                access_token=os.environ.get("X_ACCESS_TOKEN"),
                access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET"),
            )
            response = client.create_tweet(text=tweet_text)
            tweet_id = response.data["id"]
            print(f"X投稿完了: https://x.com/i/web/status/{tweet_id}")
        except Exception as e:
            print(f"X投稿失敗: {e}")

if __name__ == "__main__":
    main()
