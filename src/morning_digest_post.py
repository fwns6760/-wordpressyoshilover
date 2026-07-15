"""morning_digest_post.py — 毎朝の巨人データ定点ポスト (2026-07-10 user)。

user が示した金融アカの型 (売買代金上位の定点ポスト → 解説 → 自分の立場で
締め) の野球翻訳。「トレンドの順位とその他。カードも使ってる」:

- 関心ランキング = スポーツ媒体 X での巨人選手言及数 TOP5 (野球版・売買代金上位)
- 検索急上昇の野球ワード (Google Trends)
- 解説 + ヨシラバーの立場 (データ辛口×巨人愛) で締め — LLM、数字ガードつき
- カード: draft_text に 437 のランキング行 format (`1位 名前（巨人）… 🟧巨人🟧`)
  を入れることで既存の候補カード PNG 生成に自動で乗せる

数字は RSSHub 言及数と Google Trends の literal のみ (捏造ゼロ)。
1 日 1 本 (signature = 日付)。
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Optional

LOG = logging.getLogger("morning_digest_post")

_WEEKDAYS_JA = ("月", "火", "水", "木", "金", "土", "日")
# 2026-07-10 user「トップ10位でいいのでは」(金融アカの売買代金上位10と同じ粒度)
_TOP_N = 10


def build_morning_digest_candidate(
    *,
    now: datetime,
    gemini_api_key: str = "",
    dedup_set: Optional[set[str]] = None,
    buzz_counts: Optional[dict[str, int]] = None,
    trend_keywords: Optional[list[str]] = None,
) -> Any:
    """毎朝 1 本の定点ポスト候補。素材不足 (話題選手 3 人未満) / dedup 済みは None。

    ``buzz_counts`` / ``trend_keywords`` は test 注入用。None なら実 fetch。
    2026-07-10 user「毎時で出したい」: signature を 日+時 にして毎時 1 本。
    """
    signature = "morndigest|" + hashlib.sha1(
        now.strftime("%Y%m%d-%H").encode("utf-8")
    ).hexdigest()[:16]
    if dedup_set is not None and signature in dedup_set:
        return None

    if buzz_counts is None:
        buzz_counts = _fetch_buzz_counts()
    ranked = sorted(
        (buzz_counts or {}).items(), key=lambda kv: kv[1], reverse=True
    )[:_TOP_N]
    if len(ranked) < 3:
        LOG.info("morning_digest skip: buzz names=%d (<3)", len(ranked))
        return None

    if trend_keywords is None:
        trend_keywords = _fetch_baseball_trends()
    by_cat: dict[str, list[str]] = {"giants": [], "npb": [], "mlb": []}
    if isinstance(trend_keywords, dict):
        for cat in by_cat:
            by_cat[cat] = list(trend_keywords.get(cat) or [])
    else:  # 後方互換 (list) は巨人枠に寄せる
        by_cat["giants"] = list(trend_keywords or [])
    flat_trends = by_cat["giants"] + by_cat["npb"] + by_cat["mlb"]

    date_label = f"{now.month}/{now.day}({_WEEKDAYS_JA[now.weekday()]})"
    greeting = (
        "おはようございます。" if 5 <= now.hour <= 10
        else "こんばんは。" if now.hour >= 18
        else ""
    )
    header = f"{greeting}{date_label} {now.hour}時の巨人データ定点観測🐰"
    # ランキングは文字で書く (2026-07-10 user「図が意味わからない。ランキング
    # 書けばいいじゃん」: 437 カードは使わない = draft にランキング行 format を
    # 入れない)。巨人は2パターン (①言及数ランキング ②巨人トレンド語)。
    section = f"【いま話題の巨人選手 TOP{len(ranked)}】(スポーツ媒体Xでの言及数)"
    plain_lines = [f"{i}位 {name}" for i, (name, _c) in enumerate(ranked, 1)]
    trend_lines = [
        line for line in (
            ("【検索トレンド/巨人】" + " / ".join(by_cat["giants"][:5])
             if by_cat["giants"] else ""),
            ("【検索トレンド/プロ野球】" + " / ".join(by_cat["npb"][:5])
             if by_cat["npb"] else ""),
            ("【検索トレンド/メジャー】" + " / ".join(by_cat["mlb"][:5])
             if by_cat["mlb"] else ""),
        ) if line
    ]

    fact = (
        f"{date_label}のスポーツ媒体Xでの巨人選手言及数ランキング: "
        + "、".join(f"{i}位 {n} ({c}件)" for i, (n, c) in enumerate(ranked, 1))
        + (("。検索急上昇の野球ワード: " + "、".join(flat_trends[:8]))
           if flat_trends else "")
    )
    comment = _build_digest_comment(fact, gemini_api_key, hour=now.hour)
    if not comment:
        # LLM 不達でも定点データ自体に価値があるので deterministic 締めで成立させる
        top_name = ranked[0][0]
        comment = (
            f"言及が集まる場所は、ファンの目線が集まる場所です。今日は{top_name}"
            "から目が離せません。"
        )

    body_parts = [header, "", section, *plain_lines]
    for line in trend_lines:
        body_parts += ["", line]
    body_parts += ["", comment]
    post_text = "\n".join(body_parts)

    from src.x_post_mail_lane import Candidate

    draft = "\n".join([
        f"毎時の定点ポスト ({date_label} {now.hour}時)。"
        "言及数 = RSSHub 経由のスポーツ媒体X実測。",
        "ランキングは本文の文字表記のみ (カードは使わない、2026-07-10 user)。",
    ])
    LOG.info(
        "morning_digest built names=%d trends=%d", len(ranked), len(flat_trends)
    )
    return Candidate(
        title=f"📊{now.hour}時の定点観測｜話題選手TOP{len(ranked)}｜{ranked[0][0]}",
        metric="MORNING_DIGEST",
        period_label="毎朝定点",
        draft_text=draft,
        char_count=len(post_text),
        signature=signature,
        post_text=post_text,
        focus_player=ranked[0][0],
        source_material_type="morning_digest",
    )


def _fetch_buzz_counts() -> dict[str, int]:
    """スポーツ媒体 X の巨人選手言及数 (RSSHub、失敗は {})。"""
    try:
        from src import video_radar as vr
        from src.x_post_mail_lane import (
            _load_giants_member_aliases,
            _load_giants_player_aliases,
            detect_giants_player_name,
        )

        alias_map = {
            **_load_giants_player_aliases(),
            **_load_giants_member_aliases(),
        }
        return vr.fetch_buzzing_players(
            detect_player_fn=lambda t: detect_giants_player_name(
                t, alias_map=alias_map
            ),
            min_mentions=1,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.info("morning_digest buzz skip: %r", exc)
        return {}


def _fetch_baseball_trends() -> dict[str, list[str]]:
    """カテゴリ別 (giants/npb/mlb) の急上昇ワード + Yahoo トピックス。失敗は空。"""
    out: dict[str, list[str]] = {"giants": [], "npb": [], "mlb": []}
    try:
        from src import search_trend_note as stn

        roster = stn._giants_name_tokens()
        relevant: list[dict] = []
        for t in stn.fetch_jp_trends():
            kw = t.get("keyword") or ""
            cat = stn.categorize_trend_keyword(kw, roster)
            if cat:
                relevant.append({"keyword": kw, "category": cat})
        # Yahoo トピックス合流 (Google に野球ゼロでも各カテゴリを埋める)
        stn.merge_yahoo_topics_into_relevant(relevant, roster)
        # MLB 空白は MLB 媒体 X の言及数上位で埋める
        stn.fill_mlb_from_mentions(relevant)
        for t in relevant:
            out[t["category"]].append(t["keyword"])
        return out
    except Exception as exc:  # noqa: BLE001
        LOG.info("morning_digest trends skip: %r", exc)
        return out


# 締めのエンゲ型ローテ (2026-07-10 user「エンゲージ>インプ」「1から3と
# ランキングポストの全部」): 返信を誘う締め3型を時刻で回す。
# ランキング本文 (TOP5 行・トレンド行) は不変、変わるのは締め 2〜3 文のみ。
_DIGEST_CLOSING_STYLES = (
    "ランキングの中の1点にあえて強めの自分の断定を出し、反対意見の余地を"
    "一言だけ残して締める (賛否が割れる形。直球の「どう思う?」は禁止)",
    "ランキングから論点を二択で示し (例: 1位の勢い継続か、2位の巻き返しか)、"
    "自分はどちら派か理由付きで断定して締める (読者が反対側に立ちたくなる形)",
    "次の1時間または今夜のランキングの動きを1つだけ断定予想して締める "
    "(次の定点ポストが答え合わせになる形。予想は fact にある選手の範囲のみ)",
)


# 2026-07-15 user「今夜は先発の戸郷翔征が快投し、次のランキングで1位になります。
# 先発が違う」: prompt 指示だけでは LLM が (a) fact に無い役割 (先発/スタメン) を
# 断定し (b) 未来の成績・順位変動を確定形で書く事故が起きた。出力を決定的に
# 検証する gate。巨人・MLB 両定点で共用 (mlb_morning_digest_post が import)。
_FUTURE_ASSERT_RE = re.compile(
    r"(?:\d+位|首位|トップ)にな(?:り|る)|(?:快投|好投|活躍|爆発)(?:し(?:ます|て)|する)"
)
_ROLE_CLAIM_WORDS = (
    "先発", "スタメン", "登板予定", "快投", "好投", "完封", "完投",
    "サヨナラ", "逆転", "優勝", "マジック",
)


def find_digest_hallucination(comment: str, fact: str) -> str:
    """定点締めコメントの捏造検知。問題なければ ""、あれば理由 slug。

    - 未来断定 (「1位になります」「快投します」等) は fact の有無に関わらず破棄
      (定点は現在の数字を語る場。未来の成績・順位変動を確定形で書かない)
    - 役割・場面 claim 語 (先発/スタメン/完封等) は fact に literal で無ければ破棄
    """
    text = (comment or "").strip()
    if not text:
        return ""
    if _FUTURE_ASSERT_RE.search(text):
        return "future_assertion"
    src = fact or ""
    for w in _ROLE_CLAIM_WORDS:
        if w in text and w not in src:
            return f"unsupported_claim:{w}"
    return ""


def _giants_name_hallucination(comment: str, fact: str) -> str:
    """roster 実名が fact に無いのに comment に出たら理由 slug (取得失敗は "")。"""
    try:
        from src.giants_roster_loader import load_active_roster

        for e in load_active_roster() or []:
            nm = str(e.get("name") or "").replace(" ", "")
            if len(nm) >= 3 and nm in comment and nm not in (fact or ""):
                return f"fabricated_name:{nm}"
    except Exception:  # noqa: BLE001 - roster 不達は gate skip (fail-open)
        return ""
    return ""


def _build_digest_comment(fact: str, gemini_api_key: str, hour: int = 0) -> str:
    """解説+締めの 2〜3 文 (LLM)。失敗は ""。締めはエンゲ3型を時刻ローテ。"""
    if not gemini_api_key:
        return ""
    closing = _DIGEST_CLOSING_STYLES[hour % len(_DIGEST_CLOSING_STYLES)]
    try:
        from src.x_post_branding_gen import build_quote_rt_comment

        out = (
            build_quote_rt_comment(
                fact, "", "",
                gemini_api_key=gemini_api_key,
                subject="今朝の巨人関心データ定点観測",
                db_fact="", require_db_fact=False,
                budget_site="morning_digest",
                extra_voice_note=(
                    "毎時の定点データポストの締め。上のランキングの読み解き"
                    " (どこに関心が集まっているか、なぜか) を1〜2文 + ヨシラバー"
                    "の立場 (データは辛口・巨人愛は本物) の一言で締める。"
                    f"締め方は今回この型で: {closing}。"
                    "2〜3文、80〜140字。ランキングの数字・選手名は fact に"
                    "あるものだけ使い、新しい数字・選手名は作らない。"
                    "文体は必ず です・ます調 (丁寧語) で統一する "
                    "(「〜だよな」等のカジュアル語尾は禁止)。"
                    "選手の役割 (先発/スタメン等) や試合結果・順位の未来予測を"
                    "断定形で書かない (fact に無いことは一切書かない)。"
                ),
            ) or ""
        ).strip()
        # 2026-07-15 決定的 hallucination gate (prompt 指示だけでは再発するため)
        bad = find_digest_hallucination(out, fact) or _giants_name_hallucination(
            out, fact
        )
        if bad:
            LOG.warning("morning_digest comment gate drop: %s", bad)
            return ""
        return out
    except Exception as exc:  # noqa: BLE001
        LOG.info("morning_digest comment skip: %r", exc)
        return ""
