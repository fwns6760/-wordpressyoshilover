"""mlb_morning_digest_post.py — 毎朝の「今日の大谷・元巨人組」MLB定点ポスト (2026-07-13 user GO)。

morning_digest_post (巨人言及数定点) の MLB 版。フォロー転換の「毎日見る理由」
を作る連載枠で、2本柱 bio (巨人・MLB) の実体になる。

- 素材 = MLB 公式 Stats API (statsapi.mlb.com、無料・key 不要、mlb_alumni_fetch 流用)
- 対象 = 大谷翔平 (市場最大の入口) + 元巨人組 (岡本和真/菅野智之 = 「巨人アカが
  見る MLB」の差別化軸)。記事化 policy (元巨人のみ) は不変 — これは X ポスト側
  の別 spec list であり、MLB_ALUMNI 定数は触らない
- 数字は statsapi の literal のみ (捏造ゼロ)。直近試合が 2 日以内の選手が
  1 人もいない日は出さない (埋め草禁止)
- 1 日 1 本 (signature = 日付、GCS dedup 台帳で多重 fire 吸収)。LLM は締めの
  1 call のみ、不達は deterministic 締めで成立させる (連載を殺さない)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

LOG = logging.getLogger("mlb_morning_digest_post")

_WEEKDAYS_JA = ("月", "火", "水", "木", "金", "土", "日")

# X 定点ポスト用の対象 spec (mlb_alumni_fetch.MLB_ALUMNI + 大谷)。
# 大谷 mlb_id 660271 (statsapi people/search)。二刀流だが v0 は打撃のみ。
_DIGEST_SPECS = [
    {"mlb_id": 660271, "name": "大谷翔平", "group": "hitting", "slug": "ohtani-shohei"},
]

# 直近試合をポストに載せる鮮度 (日数)。米国日付 vs JST のずれ + デーゲームを
# 考慮して 2 日 (昨日/一昨日の米国日付) まで。
_FRESH_DAYS = 2


def _fresh(last_game: dict, now: datetime) -> bool:
    raw = str((last_game or {}).get("date") or "")
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return False
    return (now.date() - d) <= timedelta(days=_FRESH_DAYS)


def build_mlb_morning_digest_candidate(
    *,
    now: datetime,
    gemini_api_key: str = "",
    dedup_set: Optional[set[str]] = None,
    data: Optional[dict] = None,
) -> Any:
    """毎朝 1 本の MLB 定点ポスト候補。時間外 / 素材なし / dedup 済みは None。

    ``data`` は test 注入用 (fetch_mlb_alumni_data の返り値形)。None なら実 fetch。
    """
    # 8-10 時 JST のみ (米国の試合が出揃う朝帯。7時台は西海岸ナイターが試合中)。
    if not (8 <= now.hour <= 10):
        return None
    signature = "mlbdigest|" + hashlib.sha1(
        now.strftime("%Y%m%d").encode("utf-8")
    ).hexdigest()[:16]
    if dedup_set is not None and signature in dedup_set:
        return None

    from src import mlb_alumni_fetch as maf

    if data is None:
        try:
            data = maf.fetch_mlb_alumni_data(
                specs=_DIGEST_SPECS + list(maf.MLB_ALUMNI)
            )
        except Exception as exc:  # noqa: BLE001
            LOG.info("mlb_morning_digest fetch skip: %r", exc)
            return None
    players = list((data or {}).get("players") or [])
    if not players:
        return None
    # 直近 2 日以内に試合があった選手が 1 人もいなければ出さない (埋め草禁止)。
    fresh_players = [p for p in players if _fresh(p.get("last_game") or {}, now)]
    if not fresh_players:
        LOG.info("mlb_morning_digest skip: no fresh games (players=%d)", len(players))
        return None

    date_label = f"{now.month}/{now.day}({_WEEKDAYS_JA[now.weekday()]})"
    header = f"おはようございます。{date_label} 今朝のMLB定点観測🐰"
    blocks: list[str] = []
    for p in players:
        # 直近試合が古い選手は season 行のみ (fact line から直近行を落とす)。
        entry = dict(p)
        if not _fresh(p.get("last_game") or {}, now):
            entry.pop("last_game", None)
        line = maf.format_mlb_alumni_fact_line(entry)
        if line:
            blocks.append(line)
    if not blocks:
        return None

    fact = f"{date_label}時点のMLB成績:\n" + "\n".join(blocks)
    comment = _build_digest_comment(fact, gemini_api_key, hour=now.hour)
    if not comment:
        lead = fresh_players[0].get("name") or "大谷翔平"
        comment = (
            f"数字は毎朝ここで定点で見ていきます。今日も{lead}の試合から"
            "目が離せません。"
        )

    post_text = "\n".join([header, "", *blocks, "", comment])

    from src.x_post_mail_lane import Candidate

    draft = "\n".join([
        f"毎朝のMLB定点ポスト ({date_label})。",
        "数字 = MLB公式 Stats API (statsapi.mlb.com) の literal のみ。",
        "対象: 大谷翔平 + 元巨人組 (岡本和真/菅野智之)。1日1本。",
    ])
    LOG.info(
        "mlb_morning_digest built players=%d fresh=%d",
        len(blocks), len(fresh_players),
    )
    return Candidate(
        title=f"⚾️今朝のMLB定点｜大谷・元巨人組｜{fresh_players[0].get('name', '')}",
        metric="MLB_MORNING_DIGEST",
        period_label="毎朝MLB定点",
        draft_text=draft,
        char_count=len(post_text),
        signature=signature,
        post_text=post_text,
        focus_player=str(fresh_players[0].get("name") or ""),
        source_material_type="mlb_morning_digest",
    )


def _build_digest_comment(fact: str, gemini_api_key: str, hour: int = 0) -> str:
    """締めの 1〜2 文 (LLM)。失敗は "" (caller が deterministic 締めに落とす)。"""
    if not gemini_api_key:
        return ""
    try:
        from src.x_post_branding_gen import build_quote_rt_comment

        return (
            build_quote_rt_comment(
                fact, "", "",
                gemini_api_key=gemini_api_key,
                subject="今朝のMLB定点観測 (大谷・元巨人組)",
                db_fact="", require_db_fact=False,
                budget_site="morning_digest",
                extra_voice_note=(
                    "毎朝のMLB成績定点ポストの締め。大谷は巨人と無関係の別枠"
                    "なので巨人ファン視点や巨人との比較はせず、純粋に野球ファン"
                    "として読み解く。岡本和真・菅野智之は巨人から送り出した側の"
                    "親心・誇りの視点でよい。上の数字の読み解き 1 文 + 今日への"
                    "期待 1 文、合計 60〜120 字。数字・選手名は fact にあるもの"
                    "だけ使い、新しい数字は作らない。文体は です・ます調。"
                ),
            ) or ""
        ).strip()
    except Exception as exc:  # noqa: BLE001
        LOG.info("mlb_morning_digest comment skip: %r", exc)
        return ""
