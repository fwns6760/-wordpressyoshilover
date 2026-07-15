"""mlb_morning_digest_post.py — 毎朝の「今日の大谷・元巨人組」MLB定点ポスト (2026-07-13 user GO)。

morning_digest_post (巨人言及数定点) の MLB 版。フォロー転換の「毎日見る理由」
を作る連載枠で、2本柱 bio (巨人・MLB) の実体になる。

- 素材 = MLB 公式 Stats API (statsapi.mlb.com、無料・key 不要、mlb_alumni_fetch 流用)
- 対象 = 大谷翔平 (市場最大の入口) + 元巨人組 (岡本和真/菅野智之 = 「巨人アカが
  見る MLB」の差別化軸) + 日本人スター組 (2026-07-13 user「追加」: X/RSS 素材が
  503 で欠落しても全員の成績が公式 API から出る均等担保)。記事化 policy
  (元巨人のみ) は不変 — これは X ポスト側の別 spec list であり、MLB_ALUMNI
  定数は触らない
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

# 日本人スター組 (2026-07-13 user「追加」)。watch 便 _MLB_EXTRA_STARS と同じ顔ぶれ。
# 元巨人ではないので LLM framing は「巨人から送り出した」文脈にしない (ニュートラル)。
# mlb_id は statsapi people/search で 2026-07-13 に実確認済み (全員 active)。
_EXTRA_STAR_SPECS = [
    {"mlb_id": 808967, "name": "山本由伸", "group": "pitching", "slug": "yamamoto-yoshinobu"},
    {"mlb_id": 808963, "name": "佐々木朗希", "group": "pitching", "slug": "sasaki-roki"},
    {"mlb_id": 684007, "name": "今永昇太", "group": "pitching", "slug": "imanaga-shota"},
    {"mlb_id": 673548, "name": "鈴木誠也", "group": "hitting", "slug": "suzuki-seiya"},
    {"mlb_id": 807799, "name": "吉田正尚", "group": "hitting", "slug": "yoshida-masataka"},
    {"mlb_id": 808959, "name": "村上宗隆", "group": "hitting", "slug": "murakami-munetaka"},
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
    # 2026-07-15 user「メジャーリーガーは毎時でいいんじゃない？試合前まで」:
    # 8-17 時 JST の毎時便 (巨人戦の試合前まで)。米国の試合が動く午前は数字が
    # 毎時更新される。signature = 日付+内容ハッシュにし、**数字が前回投稿から
    # 変わった時だけ**出す (同一数字の連投=スパム化を構造的に防止。試合終了後は
    # 自然に沈黙し、最後に変わった時点が事実上の最終版になる)。
    if not (8 <= now.hour <= 17):
        return None
    edition = "pm" if now.hour >= 17 else "am"

    from src import mlb_alumni_fetch as maf

    if data is None:
        try:
            data = maf.fetch_mlb_alumni_data(
                specs=_DIGEST_SPECS + list(maf.MLB_ALUMNI) + _EXTRA_STAR_SPECS
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
    header = f"{date_label} {now.hour}時の日本人メジャーリーガー定点観測🐰"
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

    # 内容ハッシュ signature: 同じ数字のままなら同日中は再投稿しない
    sig_key = now.strftime("%Y%m%d") + "|" + "\n".join(blocks)
    signature = "mlbdigest|" + hashlib.sha1(sig_key.encode("utf-8")).hexdigest()[:16]
    if dedup_set is not None and signature in dedup_set:
        LOG.info("mlb_morning_digest skip: numbers unchanged (dedup)")
        return None

    fact = f"{date_label}時点のMLB成績:\n" + "\n".join(blocks)
    comment = _build_digest_comment(
        fact, gemini_api_key, hour=now.hour, edition=edition
    )
    if not comment:
        lead = fresh_players[0].get("name") or "大谷翔平"
        comment = (
            f"今日の日本人メジャーの結果は以上です。明日もここで。"
            f"{lead}、お見事でした。"
            if edition == "pm"
            else f"数字は毎時ここで定点で見ていきます。今日も{lead}の試合から"
            "目が離せません。"
        )

    post_text = "\n".join([header, "", *blocks, "", comment])

    from src.x_post_mail_lane import Candidate

    draft = "\n".join([
        f"毎時のMLB定点ポスト ({date_label} {now.hour}時)。",
        "数字 = MLB公式 Stats API (statsapi.mlb.com) の literal のみ。",
        "対象: 大谷翔平 + 元巨人組 (岡本和真/菅野智之) + 日本人スター組。"
        "数字が変わった時だけ投稿 (同一数字は自動skip)。",
    ])
    LOG.info(
        "mlb_morning_digest built hour=%d players=%d fresh=%d",
        now.hour, len(blocks), len(fresh_players),
    )
    return Candidate(
        title=f"⚾️{now.hour}時のMLB定点｜日本人メジャー組｜{fresh_players[0].get('name', '')}",
        metric="MLB_MORNING_DIGEST",
        period_label="毎時MLB定点",
        draft_text=draft,
        char_count=len(post_text),
        signature=signature,
        post_text=post_text,
        focus_player=str(fresh_players[0].get("name") or ""),
        source_material_type="mlb_morning_digest",
    )


def _build_digest_comment(
    fact: str, gemini_api_key: str, hour: int = 0, edition: str = "am"
) -> str:
    """締めの 1〜2 文 (LLM)。失敗は "" (caller が deterministic 締めに落とす)。"""
    if not gemini_api_key:
        return ""
    try:
        from src.x_post_branding_gen import build_quote_rt_comment

        out = (
            build_quote_rt_comment(
                fact, "", "",
                gemini_api_key=gemini_api_key,
                subject="毎時の日本人メジャーリーガー定点観測",
                db_fact="", require_db_fact=False,
                budget_site="morning_digest",
                extra_voice_note=(
                    (
                        "17時のMLB成績定点ポストの締め (当日の米国試合が全て"
                        "終わった最終版)。上の数字から今日の主役を 1 文で読み解き、"
                        "「明日もここで」系の連載締めを 1 文、合計 60〜120 字。"
                    )
                    if edition == "pm"
                    else (
                        "毎時のMLB成績定点ポストの締め。"
                        "上の数字の読み解き 1 文 + 期待 1 文、合計 60〜120 字。"
                    )
                ) + (
                    "岡本和真・菅野智之だけは"
                    "巨人から送り出した側の親心・誇りの視点でよい。それ以外"
                    "(大谷翔平・山本由伸・佐々木朗希・今永昇太・鈴木誠也・"
                    "吉田正尚・村上宗隆) は巨人と無関係の別枠なので巨人ファン"
                    "視点や巨人との比較はせず、純粋に野球ファンとして読み解く。"
                    "数字・選手名は fact にあるものだけ使い、新しい数字は作らない。"
                    "選手の役割 (先発/登板予定等) や試合結果・順位の未来予測を"
                    "断定形で書かない。文体は です・ます調。"
                ),
            ) or ""
        ).strip()
        # 2026-07-15 決定的 hallucination gate (巨人定点と共用、user「メジャーも」)。
        from src.morning_digest_post import find_digest_hallucination

        bad = find_digest_hallucination(out, fact)
        if not bad:
            for spec in _DIGEST_SPECS + _EXTRA_STAR_SPECS:
                nm = str(spec.get("name") or "")
                if nm and nm in out and nm not in fact:
                    bad = f"fabricated_name:{nm}"
                    break
        if bad:
            LOG.warning("mlb_morning_digest comment gate drop: %s", bad)
            return ""
        return out
    except Exception as exc:  # noqa: BLE001
        LOG.info("mlb_morning_digest comment skip: %r", exc)
        return ""
