"""437 Phase 3: text + 画像 を X に実 post する CLI tool。

user §11 GO (2026-05-26「出すように作って」) で起票。 image gen → tweepy v1
media_upload → tweepy v2 Client.create_tweet(media_ids=...) を 1 コマンドで実行。

使用例 (dry-run で確認):
    python3 src/tools/post_x_with_image.py \\
        --text "★ 巨人 2 名がセ・リーグ OPS TOP10 入り" --dry-run

使用例 (実 post):
    python3 src/tools/post_x_with_image.py \\
        --text "★ 巨人 2 名がセ・リーグ OPS TOP10 入り"

使用例 (任意 ranking JSON):
    python3 src/tools/post_x_with_image.py \\
        --text "..." \\
        --ranking-json /path/to/rankings.json

ranking JSON 形式:
    {
      "title": "セ・リーグ OPS ランキング",
      "subtitle": "直近 10 試合 / 規定打席 20 以上",
      "hook": "★ 巨人 2 名 ★",
      "rows": [
        {"rank": 1, "name": "佐藤輝明", "team": "阪神", "value": ".961", "is_giants": false},
        ...
      ]
    }

failure 方針:
  - image gen 失敗 → exit 1 (post しない)
  - image upload 失敗 → exit 1 (post しない、 silent text-only fallback はしない)
  - create_tweet 失敗 → exit 1 (rate limit / auth 等)
  - dry-run → image を file 保存して exit 0、 X に届かない
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# vendor path (.env / dotenv 等の path に合わせる)
_VENDOR = ROOT / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from src.x_post_image_attach_x import attach_x_post_image  # noqa: E402
from src.x_post_image_gen_v2 import build_ranking_data, generate_png  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_ROWS = [
    {"rank": 1, "name": "佐藤輝明", "team": "阪神", "value": ".961", "is_giants": False},
    {"rank": 2, "name": "坂倉将吾", "team": "広島", "value": ".882", "is_giants": False},
    {"rank": 3, "name": "坂本勇人", "team": "巨人", "value": ".867", "is_giants": True},
    {"rank": 4, "name": "村松開人", "team": "中日", "value": ".831", "is_giants": False},
    {"rank": 5, "name": "武岡龍世", "team": "ヤクルト", "value": ".812", "is_giants": False},
    {"rank": 6, "name": "大山悠輔", "team": "阪神", "value": ".798", "is_giants": False},
    {"rank": 7, "name": "森下翔太", "team": "阪神", "value": ".785", "is_giants": False},
    {"rank": 8, "name": "岡本和真", "team": "巨人", "value": ".772", "is_giants": True},
]


def _load_ranking(ranking_json: str | None) -> dict[str, Any]:
    if not ranking_json:
        return {
            "title": "セ・リーグ OPS ランキング",
            "subtitle": "直近 10 試合 / 規定打席 20 以上",
            "hook": "🔥 巨人 2 名 トップ 10 入り 🏆",
            "rows": DEFAULT_ROWS,
        }
    raw = Path(ranking_json).read_text(encoding="utf-8")
    return json.loads(raw)


def _build_image(spec: dict[str, Any]) -> bytes | None:
    data = build_ranking_data(
        title=spec.get("title", ""),
        subtitle=spec.get("subtitle", ""),
        hook_line=spec.get("hook", ""),
        rows=spec.get("rows", []),
    )
    return generate_png("ranking_table", data)


def _get_v1_api_for_upload():
    """tweepy.API (v1.1 OAuth1) — media_upload に必要。 attach_x_post_image
    が import するが、 本 CLI 側で env validate して fail-fast にする。"""
    required = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"X API env missing: {missing}. "
            ".env で X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / "
            "X_ACCESS_TOKEN_SECRET を設定してください。"
        )
    import tweepy

    auth = tweepy.OAuth1UserHandler(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return tweepy.API(auth)


def _get_v2_client():
    """tweepy.Client (v2) — create_tweet(media_ids=...) で post する。"""
    import tweepy

    return tweepy.Client(
        bearer_token=os.environ.get("X_BEARER_TOKEN"),
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def main(
    argv: list[str] | None = None,
    *,
    _api_v1_factory=_get_v1_api_for_upload,
    _client_factory=_get_v2_client,
) -> int:
    """CLI entry point. test では _api_v1_factory / _client_factory を差し替える。"""
    parser = argparse.ArgumentParser(
        description="437 Phase 3: text + 画像 を X に実 post する CLI"
    )
    parser.add_argument("--text", required=True, help="X post 本文 (必須)")
    parser.add_argument(
        "--ranking-json",
        default=None,
        help="ranking 構造 JSON file (省略時は sample)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="X には post せず image を file に保存して終了",
    )
    parser.add_argument(
        "--dry-run-output",
        default="/tmp/post_x_image_dryrun.png",
        help="--dry-run の保存先 (default: /tmp/post_x_image_dryrun.png)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="info ログを抑止",
    )
    args = parser.parse_args(argv)

    if not args.quiet:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )

    # 1. ranking data load
    try:
        spec = _load_ranking(args.ranking_json)
    except Exception as exc:
        logger.error("[437p3] ranking JSON load failed: %s", exc)
        return 2

    # 2. 画像生成
    png = _build_image(spec)
    if png is None:
        logger.error("[437p3] image generation returned None — abort")
        return 2
    logger.info("[437p3] image generated: %d bytes", len(png))

    # 3. dry-run 分岐 (X には触れない)
    if args.dry_run:
        out = Path(args.dry_run_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        print("[DRY-RUN] X には post しません")
        print(f"  text  : {args.text}")
        print(f"  image : {out}")
        print(f"  bytes : {len(png)}")
        print("実 post するには --dry-run を外してください")
        return 0

    # 4. media upload (tweepy v1.1)
    try:
        api_v1 = _api_v1_factory()
    except RuntimeError as exc:
        logger.error("[437p3] %s", exc)
        return 3
    media_id = attach_x_post_image(api_v1, png)
    if not media_id:
        logger.error(
            "[437p3] media_upload failed — abort (silent text-only fallback はしない)"
        )
        return 4
    logger.info("[437p3] media uploaded: media_id=%s", media_id)

    # 5. create_tweet (tweepy v2)
    try:
        client = _client_factory()
        response = client.create_tweet(text=args.text, media_ids=[media_id])
    except Exception as exc:
        logger.error("[437p3] create_tweet failed (%s): %s", type(exc).__name__, exc)
        return 5
    if not response or not getattr(response, "data", None):
        logger.error("[437p3] create_tweet response missing data")
        return 5
    tweet_id = response.data.get("id")
    url = f"https://x.com/i/web/status/{tweet_id}"
    logger.info("[437p3] posted: %s", url)
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
