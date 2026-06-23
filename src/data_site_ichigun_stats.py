"""巨人 一軍（セントラル）今季 個人打撃成績の取得（NPB公式）。

選手ページの「今季成績」を、insight.db (box score 積み上げ) ではなく NPB 公式の
シーズン合計から作るための authoritative source。 insight.db は試合取込漏れがあると
そのまま成績欠落になる (例: 宇都宮葵星 6試合2打数 が 0 になる) ため、 公式合計を正本に
する。 直近5試合・連続記録は引き続き insight.db を使う。

NPB 公式 一軍 打撃: https://npb.jp/bis/{year}/stats/idb1_g.html
  (二軍/ファームは idb2_g.html。 idb1=一軍, idb2=二軍 を取り違えない。)

giants_ichigun_batting_map(year) -> { 正規化名: {"games","ab","hits","rbi","runs","sb","hr"} }
ネットワーク失敗時は空 dict（呼び出し側は insight.db に fallback）。

依存は farm_stats の table parser を再利用（stdlib html.parser のみ）。
"""

from __future__ import annotations

import logging
from typing import Optional

from src.data_site_farm_stats import _fetch_table, _norm, _num

LOG = logging.getLogger(__name__)

_BAT_URL = "https://npb.jp/bis/{year}/stats/idb1_g.html"

# NPB 公式ヘッダ名 -> BattingStatsSeason フィールド名
_BAT_FIELDS = {
    "試合": "games",
    "打数": "ab",
    "安打": "hits",
    "打点": "rbi",
    "得点": "runs",
    "盗塁": "sb",
    "本塁打": "hr",
}

_CACHE: Optional[dict] = None
_CACHE_YEAR: Optional[int] = None


def _to_int(s: str) -> int:
    s = _num(s)
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def giants_ichigun_batting_map(year: int = 2026) -> dict:
    """{正規化名: {games, ab, hits, rbi, runs, sb, hr}}。失敗・空は {}。"""
    global _CACHE, _CACHE_YEAR
    if _CACHE is not None and _CACHE_YEAR == year:
        return _CACHE
    out: dict[str, dict] = {}
    try:
        header, rows = _fetch_table(_BAT_URL.format(year=year))
        if header:
            idx = {h.strip(): i for i, h in enumerate(header)}
            for r in rows:
                if not r or len(r) < 2:
                    continue
                name = _norm(r[0])
                if not name or "選手" in name:
                    continue
                rec: dict[str, int] = {}
                for src, field in _BAT_FIELDS.items():
                    i = idx.get(src)
                    if i is not None and i < len(r):
                        rec[field] = _to_int(r[i])
                # 試合数 0 / 全欠損は採用しない
                if rec.get("games"):
                    out[name] = rec
    except Exception as exc:  # noqa: BLE001
        LOG.warning("giants_ichigun_batting_map fetch failed: %r", exc)
        out = {}
    _CACHE, _CACHE_YEAR = out, year
    return out
