"""セ・リーグ順位データ記事を描画して WordPress に投稿する runner。

データは JSON(standings/batting/pitching/date_label/source)を渡す。描画は
standings_article(LLM 不使用・数字はそのまま)。公開ページの事実事故を避けるため
既定は draft。--publish でライブ公開。--post-id で既存記事を更新。

usage:
    python3 -m src.tools.run_standings_article --data data.json --out out.html      # 描画のみ
    python3 -m src.tools.run_standings_article --data data.json --wp                 # draft 投稿
    python3 -m src.tools.run_standings_article --data data.json --wp --publish       # ライブ公開
    python3 -m src.tools.run_standings_article --data data.json --wp --post-id 92613 # 既存更新
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from src import standings_article as sa  # noqa: E402


def _wp_upsert(title: str, html: str, excerpt: str, *, publish: bool, post_id: int | None) -> dict:
    import requests
    from requests.auth import HTTPBasicAuth

    base = os.environ["WP_URL"].rstrip("/")
    auth = HTTPBasicAuth(os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
    payload = {
        "title": title,
        "content": html,
        "excerpt": excerpt,
        "status": "publish" if publish else "draft",
    }
    url = f"{base}/wp-json/wp/v2/posts" + (f"/{post_id}" if post_id else "")
    r = requests.post(url, json=payload, auth=auth, timeout=60)
    r.raise_for_status()
    return r.json()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="standings/batting/pitching を含む JSON")
    ap.add_argument("--out", default=None, help="HTML 書き出し先(任意)")
    ap.add_argument("--wp", action="store_true", help="WordPress に投稿する")
    ap.add_argument("--publish", action="store_true", help="ライブ公開(既定は draft)")
    ap.add_argument("--post-id", type=int, default=None, help="既存記事を更新する場合の ID")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    title, html, excerpt = sa.render_standings_article(
        data["standings"], data["batting"], data["pitching"],
        date_label=data["date_label"], source=data.get("source", "NPB公式成績 / スポーツナビ"),
    )
    print(f"=== title ===\n{title}\n=== html {len(html)} chars ===")

    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"[html] wrote {Path(args.out).resolve()}")

    if args.wp:
        res = _wp_upsert(title, html, excerpt, publish=args.publish, post_id=args.post_id)
        print(f"[wp] id={res.get('id')} status={res.get('status')} link={res.get('link')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
