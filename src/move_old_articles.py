"""
move_old_articles.py — 旧記事を「旧記事」カテゴリに一括移動
=============================================================
新8カテゴリ（試合速報〜コラム）に属していない投稿を
「旧記事」カテゴリ（slug: old-articles）に移動する。

- 移動: 旧記事カテゴリを追加し、元のカテゴリは維持
- テスト記事（新8カテゴリ所属）は対象外
- 既に旧記事カテゴリに属している投稿はスキップ
"""

import os
import sys
import json
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

WP_URL       = os.getenv("WP_URL", "").rstrip("/")
AUTH         = (os.getenv("WP_USER", ""), os.getenv("WP_APP_PASSWORD", ""))
API          = f"{WP_URL}/wp-json/wp/v2"
HEADERS      = {"Content-Type": "application/json"}

# 新8カテゴリ（これに属していれば新記事 → 移動しない）
NEW_CAT_IDS  = {663, 664, 665, 666, 667, 668, 669, 670}
OLD_CAT_ID   = 672   # 旧記事カテゴリ


def get_all_posts(status: str = "publish") -> list[dict]:
    """全投稿を取得して返す（ページネーション対応）"""
    posts = []
    page  = 1
    while True:
        r = requests.get(
            f"{API}/posts",
            auth=AUTH,
            params={"per_page": 100, "page": page, "status": status},
            timeout=30,
        )
        if not r.ok:
            print(f"  警告: posts取得失敗 page={page} ({r.status_code})")
            break
        batch = r.json()
        if not batch:
            break
        posts.extend(batch)
        total_pages = int(r.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1
    return posts


def categorize(posts: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Returns (to_move, already_done)
    to_move: 旧記事カテゴリへ移動が必要な投稿
    already_done: 既に旧記事カテゴリに属している投稿
    """
    to_move      = []
    already_done = []
    skip_new     = []

    for p in posts:
        cats = set(p.get("categories", []))
        if cats & NEW_CAT_IDS:
            # 新カテゴリに属している → 対象外
            skip_new.append(p)
        elif OLD_CAT_ID in cats:
            # 既に旧記事カテゴリ
            already_done.append(p)
        else:
            # 旧記事カテゴリに移動が必要
            to_move.append(p)

    return to_move, already_done, skip_new


def move_posts(to_move: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """旧記事カテゴリに移動する。(moved, failed) を返す"""
    moved  = 0
    failed = 0

    for p in to_move:
        pid   = p["id"]
        title = p.get("title", {}).get("rendered", "")[:40]
        cats  = list(set(p.get("categories", [])) | {OLD_CAT_ID})

        if dry_run:
            print(f"  [DRY] ID={pid:6d} → cats={cats}  「{title}」")
            moved += 1
            continue

        r = requests.post(
            f"{API}/posts/{pid}",
            json={"categories": cats},
            auth=AUTH,
            headers=HEADERS,
            timeout=20,
        )
        if r.ok:
            print(f"  ✓ ID={pid:6d}  「{title}」")
            moved += 1
        else:
            print(f"  ✗ ID={pid:6d} ({r.status_code})  「{title}」")
            failed += 1

    return moved, failed


def main():
    parser = argparse.ArgumentParser(description="旧記事を「旧記事」カテゴリに一括移動")
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（変更なし）")
    args = parser.parse_args()

    print()
    print("=" * 55)
    print("旧記事を「旧記事」カテゴリに一括移動")
    print("=" * 55)
    print(f"  新カテゴリIDs (移動除外): {sorted(NEW_CAT_IDS)}")
    print(f"  旧記事カテゴリID: {OLD_CAT_ID}")
    if args.dry_run:
        print("  [DRY-RUN] 変更は行いません")
    print()

    # 全投稿取得
    print("投稿を取得中...")
    posts = get_all_posts("publish")
    print(f"  公開投稿: {len(posts)}件")

    # 分類
    to_move, already_done, skip_new = categorize(posts)
    print(f"  新カテゴリ所属（対象外）: {len(skip_new)}件")
    print(f"  既に旧記事カテゴリ    : {len(already_done)}件")
    print(f"  移動対象              : {len(to_move)}件")
    print()

    if not to_move:
        print("移動対象がありません。処理完了。")
        return

    # 移動実行
    print(f"{'[DRY] ' if args.dry_run else ''}移動開始...")
    moved, failed = move_posts(to_move, dry_run=args.dry_run)
    print()
    print(f"完了: {moved}件移動 / {failed}件失敗")
    if failed:
        print("  ⚠️  失敗した投稿は個別に確認してください")


if __name__ == "__main__":
    main()
