"""437 Phase 2C: X-post image の手動 sample 生成 CLI。

x_post_image_gen_v2.generate_png() を mock data で叩いて 1080x1080 PNG を
file に保存する。 X live post には触れない (見せる用のローカル生成のみ)。

使用例:
    python3 src/tools/generate_x_post_image_sample.py
    python3 src/tools/generate_x_post_image_sample.py --output /tmp/sample.png
    python3 src/tools/generate_x_post_image_sample.py --emoji 🔥 --emoji-end 🏆

user 確認用 ("全部終わったら手動でだして見せて") の手動 generation 専用。
production 自動 lane からは絶対 import しない。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

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


def _build_default_hook(emoji_start: str, emoji_end: str, giants_count: int) -> str:
    pieces = []
    if emoji_start:
        pieces.append(emoji_start)
    pieces.append(f"巨人 {giants_count} 名 トップ 10 入り")
    if emoji_end:
        pieces.append(emoji_end)
    return " ".join(pieces)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="437 Phase 2C: X-post image sample generator (manual review)"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="/tmp/437_v2_sample.png",
        help="出力 PNG path (default: /tmp/437_v2_sample.png)",
    )
    parser.add_argument(
        "--title",
        default="セ・リーグ OPS ランキング",
        help="ヘッダ title",
    )
    parser.add_argument(
        "--subtitle",
        default="直近 10 試合 / 規定打席 20 以上",
        help="ヘッダ subtitle",
    )
    parser.add_argument(
        "--emoji-start",
        default="🔥",
        help="hook 先頭 emoji (空文字で無効化)",
    )
    parser.add_argument(
        "--emoji-end",
        default="🏆",
        help="hook 末尾 emoji (空文字で無効化)",
    )
    parser.add_argument(
        "--hook",
        default=None,
        help="hook line 全文を上書き (emoji 引数を無視)",
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

    giants_count = sum(1 for r in DEFAULT_ROWS if r.get("is_giants"))
    hook = args.hook or _build_default_hook(
        args.emoji_start, args.emoji_end, giants_count
    )

    data = build_ranking_data(
        title=args.title,
        subtitle=args.subtitle,
        hook_line=hook,
        rows=DEFAULT_ROWS,
    )
    png = generate_png("ranking_table", data)
    if png is None:
        logger.error("[437v2] generate_png returned None — see prior WARN logs")
        return 1
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    logger.info(
        "[437v2] sample saved: %s (%d bytes, %d giants in TOP 8)",
        out,
        len(png),
        giants_count,
    )
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
