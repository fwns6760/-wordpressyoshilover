"""
weekly_summary.py — 過去7日間の記事をGeminiで週間まとめ記事として自動生成・公開

使用例:
    python3 src/weekly_summary.py
    python3 src/weekly_summary.py --dry-run
"""

import sys
import os
import json
import re
import urllib.request
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

_vendor = str(ROOT / 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from wp_client import WPClient

AUTO_POST_CATEGORY_ID = 673
WEEKLY_CATEGORY_NAME  = "コラム"


def fetch_recent_posts(wp: WPClient, days: int = 7) -> list:
    """過去N日間の自動投稿記事タイトルを取得"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        import base64
        auth = base64.b64encode(
            f"{os.environ['WP_USER']}:{os.environ['WP_APP_PASSWORD']}".encode()
        ).decode()
        url = (
            f"{os.environ['WP_URL'].rstrip('/')}/wp-json/wp/v2/posts"
            f"?categories={AUTO_POST_CATEGORY_ID}&after={since}&per_page=50&status=publish"
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=15) as res:
            posts = json.load(res)
        titles = []
        for p in posts:
            t = p.get("title", {}).get("rendered", "")
            t = re.sub(r"<[^>]+>", "", t)
            t = t.replace("&#8211;", "–").replace("&amp;", "&").replace("&quot;", '"')
            if t:
                titles.append(t)
        return titles
    except Exception as e:
        print(f"[WP] 記事取得失敗: {e}")
        return []


def generate_weekly_summary(titles: list) -> str:
    """Geminiで週間まとめ記事を生成"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    titles_text = "\n".join(f"・{t}" for t in titles[:30])
    now = datetime.now()
    week_label = f"{now.month}月第{(now.day - 1) // 7 + 1}週"

    prompt = f"""あなたは読売ジャイアンツのファンブロガーです。
今週（{week_label}）の巨人関連ニュースのまとめ記事を書いてください。

今週のニュース一覧:
{titles_text}

【出力フォーマット】
（今週の巨人を2〜3行で総括する導入文）

■ 今週の注目ニュース
（上のリストから特に重要な3〜5件をピックアップして、それぞれ2〜3行で解説）

■ ファンの注目ポイント
（ファン目線で今週最も話題になったことを150字程度で）

■ 来週の見どころ
（来週への期待・展望を100字程度で）

みなさんの意見はコメントで！

条件:
・全体600〜800文字
・HTMLタグは使わない、改行のみ
・本文のみ出力"""

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.8}
    }).encode("utf-8")

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.load(res)
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[Gemini] 生成失敗: {e}")
        return ""


def to_wp_blocks(text: str) -> str:
    blocks = ""
    for p in [line.strip() for line in text.split("\n") if line.strip()]:
        if p.startswith("■"):
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
    parser = argparse.ArgumentParser(description="週間まとめ記事を自動生成・公開")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿しない")
    args = parser.parse_args()

    now = datetime.now()
    week_label = f"{now.month}月第{(now.day - 1) // 7 + 1}週"
    title = f"【週間まとめ】{now.year}年{week_label} 巨人ニュース総まとめ"

    print(f"タイトル: {title}")

    wp = WPClient()
    titles = fetch_recent_posts(wp, days=7)
    print(f"対象記事: {len(titles)}件")

    if not titles:
        print("記事が見つかりません。終了します。")
        return

    print("Gemini生成中...")
    body_text = generate_weekly_summary(titles)
    if not body_text:
        print("生成失敗。終了します。")
        return

    print("─" * 40)
    print(body_text[:300] + "…")
    print("─" * 40)

    if args.dry_run:
        print("\n[DRY RUN] 投稿スキップ")
        return

    content = to_wp_blocks(body_text)
    category_id = wp.resolve_category_id(WEEKLY_CATEGORY_NAME)
    cats = [AUTO_POST_CATEGORY_ID]
    if category_id:
        cats.append(category_id)

    post_id = wp.create_post(title, content, categories=cats, status="publish")
    post = wp.get_post(post_id)
    url = post.get("link", "")
    print(f"\nWP公開完了: {url}")


if __name__ == "__main__":
    main()
