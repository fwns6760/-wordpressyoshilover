"""INSIGHT-004 — NPB daily schedule fetch + parse + slug auto-resolve.

* NPB の daily schedule HTML から、指定日の **巨人** 試合の
  ``box.html`` slug を抽出する。
* HTML 構造は実 NPB ページに合わせる必要があるため、parser は ``box.html``
  パスを示す anchor を **汎用的に拾う** 形にしてある (``href="/scores/
  YYYY/MMDD/<away>-<home>-NN/box.html"`` パターンを正規表現で抽出)。
* 実 NPB URL に変化があった場合は parser を直すだけで済むよう、URL の
  パターンと parser を完全分離している。
* HTTP 部は :mod:`insight_fetcher` の polite ルールを再利用するため、
  この module 自体は **HTTP を呼ばない**。callers から fetched HTML を
  渡してもらう関数として実装。
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional

# ``/scores/YYYY/MMDD/<slug>/box.html`` の slug 部分を拾う。
_BOX_SLUG_RE = re.compile(
    r'href=["\']/scores/(?P<year>\d{4})/(?P<mmdd>\d{4})/(?P<slug_tail>[a-z0-9\-]+)/box\.html["\']',
    re.IGNORECASE,
)

# slug tail (e.g. "d-g-08") に 'g' を含む = Giants 関連。home/away どちら
# でも g が入る。
_GIANTS_SLUG_TAIL_RE = re.compile(r"(?:^|-)g(?:-|$)")


def parse_npb_schedule_html(html: str, *, target_date: Optional[str] = None) -> list[dict]:
    """指定日 (``YYYY-MM-DD``) の box slug 候補を返す。

    引数 ``target_date=None`` は filter なし (全 anchor を返す)。

    各要素: ``{"slug": "2026/0510/d-g-08", "date": "2026-05-10",
                "slug_tail": "d-g-08", "involves_giants": True|False}``
    """
    if not isinstance(html, str) or not html:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for m in _BOX_SLUG_RE.finditer(html):
        year = m.group("year")
        mmdd = m.group("mmdd")
        slug_tail = m.group("slug_tail")
        slug = f"{year}/{mmdd}/{slug_tail}"
        if slug in seen:
            continue
        seen.add(slug)
        date = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
        if target_date and date != target_date:
            continue
        out.append({
            "slug": slug,
            "date": date,
            "slug_tail": slug_tail,
            "involves_giants": bool(_GIANTS_SLUG_TAIL_RE.search(slug_tail)),
        })
    return out


def resolve_giants_slug_for_date(html: str, target_date: str) -> Optional[str]:
    """指定日の Giants の box slug を 1 件返す。

    複数あれば最初のものを採用 (DH 等、本フェーズでは複数対応しない)。
    無ければ ``None``。
    """
    candidates = parse_npb_schedule_html(html, target_date=target_date)
    giants = [c for c in candidates if c["involves_giants"]]
    if not giants:
        return None
    return giants[0]["slug"]


def npb_monthly_schedule_url(year: int, month: int) -> str:
    """NPB の **月別 schedule URL** 推定。

    NPB は ``https://npb.jp/games/YYYY/schedule_YYYYMM_<league>.html`` 形式の
    schedule ページを公開している (cross-league の交流戦含む場合は別 file
    の可能性)。実 URL は user --live 試走で 1 度確認した上で必要なら
    parser 側を調整する。
    """
    return f"https://npb.jp/games/{year}/schedule_{year}{month:02d}_01.html"


def npb_daily_schedule_url(date: dt.date) -> str:
    """NPB の **日次 schedule URL** 推定。

    `https://npb.jp/games/<year>/<MMDD>/index.html` を想定。実構造は user
    --live 試走で確認後に必要なら module 内 URL を訂正する。
    """
    return f"https://npb.jp/games/{date.year}/{date.month:02d}{date.day:02d}/index.html"


def previous_jst_date(now: Optional[dt.datetime] = None) -> dt.date:
    """``now`` の JST 換算日付の前日。``now=None`` で当該プロセスの now。"""
    JST = dt.timezone(dt.timedelta(hours=9))
    if now is None:
        now = dt.datetime.now(JST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    return (now.astimezone(JST).date() - dt.timedelta(days=1))
