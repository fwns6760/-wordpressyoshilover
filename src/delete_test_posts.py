"""
delete_test_posts.py — テスト記事10本を一括削除
================================================
create_test_posts.py が作成した記事（ID 61088〜61097）を削除する。
本番運用開始時に実行する。

使用方法:
    python3 src/delete_test_posts.py            # 確認プロンプトあり
    python3 src/delete_test_posts.py --force    # 確認なしで削除
    python3 src/delete_test_posts.py --dry-run  # 確認のみ（削除なし）
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

WP_URL  = os.getenv("WP_URL", "").rstrip("/")
AUTH    = (os.getenv("WP_USER", ""), os.getenv("WP_APP_PASSWORD", ""))
API     = f"{WP_URL}/wp-json/wp/v2"

# テスト記事のタイトルで特定（IDは変わらないが念のためタイトルも確認）
TEST_TITLES = [
    "【試合速報】巨人3-2阪神｜岡本和真の逆転3ランで劇的勝利！戸郷翔征が7回1失点好投",
    "【試合速報】巨人7-0ヤクルト｜山崎伊織が今季初完封！坂本勇人3打数2安打の活躍",
    "岡本和真インタビュー「今年は50本狙う」オープン戦絶好調で本番へ準備万端",
    "戸郷翔征2026年シーズン展望｜開幕エース確定、球速UP＆新変化球で三振量産狙う",
    "阿部慎之助監督会見「若手を積極的に使う。失敗を恐れない野球を目指す」春季キャンプ総括",
    "【ファーム速報】ドラフト1位・森田大翔が一軍昇格へ急接近！153km/hをマーク、首脳陣が高評価",
    "高橋由伸氏が徹底分析「岡本はMVP候補筆頭。長打＋打率の両立は松井以来」今季の巨人展望",
    "巨人が国内FA選手の獲得に動く？外野手補強の最有力候補として複数名との接触報道",
    "東京ドーム2026シーズン限定グルメ＆応援グッズ発表！岡本モデルの限定ユニフォームが人気",
    "【コラム】2026年セ・リーグ優勝予想｜データで見る巨人連覇の可能性と阻む壁",
]

# create_test_posts.py が作成した既知のID範囲
KNOWN_IDS = list(range(61088, 61098))


def find_test_posts() -> list[dict]:
    """テスト記事を検索して返す"""
    found = []

    # 既知IDで直接取得
    for pid in KNOWN_IDS:
        r = requests.get(
            f"{API}/posts/{pid}",
            auth=AUTH,
            params={"status": "any"},
            timeout=20,
        )
        if r.ok:
            post = r.json()
            title = post.get("title", {}).get("rendered", "")
            if any(t in title for t in TEST_TITLES):
                found.append({"id": pid, "title": title, "status": post.get("status")})
            else:
                # IDは一致するがタイトルが異なる（書き換えられた可能性）
                if "test-article-notice" in post.get("content", {}).get("rendered", ""):
                    found.append({"id": pid, "title": title, "status": post.get("status"), "note": "本文注記あり"})

    # タイトルで追加検索（IDが変わっている場合に備えて）
    if len(found) < len(TEST_TITLES):
        r = requests.get(
            f"{API}/posts",
            auth=AUTH,
            params={"per_page": 50, "status": "any"},
            timeout=30,
        )
        if r.ok:
            for post in r.json():
                pid = post["id"]
                if pid in [p["id"] for p in found]:
                    continue
                title = post.get("title", {}).get("rendered", "")
                if any(t == title for t in TEST_TITLES):
                    found.append({"id": pid, "title": title, "status": post.get("status")})

    return found


def delete_posts(posts: list[dict], dry_run: bool = False) -> tuple[int, int]:
    deleted, failed = 0, 0
    for p in posts:
        pid   = p["id"]
        title = p["title"][:50]
        if dry_run:
            print(f"  [DRY] ID={pid}  「{title}」")
            deleted += 1
            continue
        # force=true で完全削除（ゴミ箱を経由しない）
        r = requests.delete(
            f"{API}/posts/{pid}",
            auth=AUTH,
            params={"force": "true"},
            timeout=20,
        )
        if r.ok:
            print(f"  ✓ 削除  ID={pid}  「{title}」")
            deleted += 1
        else:
            print(f"  ✗ 失敗  ID={pid} ({r.status_code})  「{title}」")
            failed += 1
    return deleted, failed


def main():
    parser = argparse.ArgumentParser(description="テスト記事10本を削除")
    parser.add_argument("--force",   action="store_true", help="確認なしで削除")
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（削除なし）")
    args = parser.parse_args()

    print()
    print("=" * 55)
    print("テスト記事 一括削除")
    print("=" * 55)
    if args.dry_run:
        print("  [DRY-RUN] 削除は行いません")
    print()

    print("テスト記事を検索中...")
    posts = find_test_posts()
    print(f"  {len(posts)}件のテスト記事を検出:")
    for p in posts:
        note = f"  ({p.get('note','')})" if p.get("note") else ""
        print(f"    ID={p['id']}  [{p['status']}]  「{p['title'][:45]}」{note}")
    print()

    if not posts:
        print("削除対象のテスト記事が見つかりません。")
        return

    if not args.dry_run and not args.force:
        ans = input(f"  {len(posts)}件を完全削除します。よろしいですか？ [y/N]: ")
        if ans.lower() != "y":
            print("  キャンセルしました。")
            return

    deleted, failed = delete_posts(posts, dry_run=args.dry_run)
    print()
    print(f"完了: {deleted}件削除 / {failed}件失敗")
    if deleted > 0 and not args.dry_run:
        print()
        print("  ✓ テスト記事を削除しました。")
        print("  ✓ 本番コンテンツのみ残っています。")


if __name__ == "__main__":
    main()
