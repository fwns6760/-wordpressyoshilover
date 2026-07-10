"""fan_pulse.py — ファンの反応まとめ (記事 + Xポスト候補、2026-07-10 user GO)。

Yahoo の AI コメントまとめ記事の yoshilover 版。ヤフコメは転載不可のため、
反応の源は X の公開ポスト (Yahoo リアルタイム検索経由・実在ポストのみ):
- 昼 (12時台): 午前の話題選手 1 人を topic に
- 試合後 (23時台): 今日の巨人戦の反応を topic に

構成 = 導入 (何が話題か) → 論点まとめ (LLM が実ポスト群をパラフレーズ、
原文転載しない) → 代表ポスト 3〜5 件の oEmbed 埋め込み (著作権セーフ) →
ヨシラバー締め。文体は です・ます調。

安全側:
- LLM 素材は取得した実ポスト text のみ。gate: 素材に無い数字・選手名は棄却
- 引用の原文は oEmbed 埋め込みだけ (地の文へのコピーはしない)
- 記事は noindex 環境 (yoshilover 現フェーズ) にそのまま乗る
- アイキャッチ: 選手 topic = eyecatch map の選手写真 / 無ければ巨人マーク
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Optional

LOG = logging.getLogger("fan_pulse")

_WEEKDAYS_JA = ("月", "火", "水", "木", "金", "土", "日")
_MIN_REACTIONS = 4
_EMBED_COUNT = 4


def gather_reactions(keyword: str) -> list[dict[str, Any]]:
    """X の公開ポスト (Yahoo リアルタイム検索、人気順 top10)。失敗は []。"""
    try:
        from src.rss_fetcher import fetch_yahoo_realtime_entries

        return fetch_yahoo_realtime_entries(keyword) or []
    except Exception as exc:  # noqa: BLE001
        LOG.info("fan_pulse reactions skip: %r", exc)
        return []


def _noon_topic() -> tuple[str, str]:
    """(keyword, topic_label)。午前の話題選手 1 人。取れなければ ("", "")。"""
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
        counts = vr.fetch_buzzing_players(
            detect_player_fn=lambda t: detect_giants_player_name(
                t, alias_map=alias_map
            ),
            min_mentions=2,
        )
        if not counts:
            return "", ""
        top = max(counts.items(), key=lambda kv: kv[1])[0]
        return top, f"{top}を巡るファンの反応"
    except Exception as exc:  # noqa: BLE001
        LOG.info("fan_pulse noon topic skip: %r", exc)
        return "", ""


def _postgame_topic() -> tuple[str, str]:
    """今日の巨人戦が終わっていれば ("巨人", "巨人{score}{opp}…")。無ければ ("", "")。"""
    try:
        from src.live_game_watch import fetch_today_live_game

        cur = fetch_today_live_game()
        if cur is None or cur.status != "試合終了":
            return "", ""
        outcome = (
            "勝利" if cur.giants_score > cur.opp_score
            else "敗戦" if cur.giants_score < cur.opp_score else "引き分け"
        )
        return (
            "巨人",
            f"巨人{cur.giants_score}-{cur.opp_score}{cur.opp_name}({outcome})への反応",
        )
    except Exception as exc:  # noqa: BLE001
        LOG.info("fan_pulse postgame topic skip: %r", exc)
        return "", ""


def _summarize(
    topic_label: str, reactions: list[dict], gemini_api_key: str
) -> dict[str, str]:
    """{intro, points, close, post}。gate 不合格・失敗は {}。"""
    if not gemini_api_key:
        return {}
    from google import genai

    from src.x_post_branding_gen import (
        _X_POST_DATA_LLM_MODEL,
        _extract_unverified_numbers,
        _llm_budget_guard,
        _x_post_generate_content,
    )

    source_texts = "\n".join(
        f"- {str(r.get('summary') or '')[:180]}" for r in reactions[:10]
    )
    prompt = "\n".join([
        "あなたは読売ジャイアンツ専門メディア「ヨシラバー」の編集者です。",
        f"X 上のファンの反応まとめ記事を作ります。話題: {topic_label}",
        "下の実在ポスト群だけを素材に、次の4部品を書いてください。",
        "",
        "【ルール (最重要)】",
        "- 素材に無い意見・数字・選手名・事実は一切作らない。",
        "- ポスト原文をコピーしない (すべて自分の言葉でパラフレーズする)。",
        "- 文体は です・ます調。煽り・断定・特定ユーザーへの言及は禁止。",
        "- 賛否が割れている時は両論を併記する。",
        "",
        "INTRO: 何が話題になっているかの導入 (2〜3文、100〜160字)",
        "POINTS: 論点まとめ (「・」始まりの箇条書き 2〜4 行、各40〜70字)",
        "CLOSE: ヨシラバーの締め (1〜2文。読者が意見を返したくなる余白を残す)",
        "POST: X 投稿用の文 (140〜250字。話題の紹介 + 論点2つ + 問いかけ余白。"
        "ハッシュタグ・URL なし)",
        "",
        "素材 (実在ポスト):",
        source_texts,
    ])
    try:
        _llm_budget_guard("fan_pulse")
        client = genai.Client(api_key=gemini_api_key)
        response = _x_post_generate_content(
            client,
            model=_X_POST_DATA_LLM_MODEL,
            contents=prompt,
            config={"temperature": 0.4},
        )
        raw = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001
        LOG.info("fan_pulse llm skip: %r", exc)
        return {}
    out: dict[str, str] = {}
    for label in ("INTRO", "POINTS", "CLOSE", "POST"):
        m = re.search(rf"{label}:\s*(.+?)(?=\n[A-Z]+:|\Z)", raw, re.DOTALL)
        if m:
            out[label.lower()] = m.group(1).strip()
    if len(out) != 4:
        LOG.info("fan_pulse gate_fail=missing_sections got=%s", sorted(out))
        return {}
    combined = " ".join(out.values())
    baseline = f"{topic_label} {source_texts}"
    if _extract_unverified_numbers(combined, baseline):
        LOG.info("fan_pulse gate_fail=unverified_numbers")
        return {}
    return out


def _article_html(
    topic_label: str, parts: dict[str, str], reactions: list[dict]
) -> str:
    points_html = "".join(
        f"<li>{_esc(line.lstrip('・-  '))}</li>"
        for line in parts["points"].splitlines() if line.strip()
    )
    embeds = "".join(
        '<blockquote class="twitter-tweet" data-dnt="true" data-lang="ja">'
        f'<a href="{_esc(str(r.get("link") or ""))}"></a></blockquote>\n'
        for r in reactions[:_EMBED_COUNT] if r.get("link")
    )
    return "\n".join([
        f"<p>{_esc(parts['intro'])}</p>",
        "<h3>論点まとめ</h3>",
        f"<ul>{points_html}</ul>",
        "<h3>実際の反応 (Xより)</h3>",
        embeds,
        f"<p>{_esc(parts['close'])}</p>",
        '<p class="fan-pulse-note">※この記事は X 上の公開ポストをもとに構成して'
        "います。引用は X の埋め込み機能によるものです。</p>",
        '<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>',
    ])


def _esc(text: str) -> str:
    import html as _html

    return _html.escape(text, quote=False)


def _eyecatch_media_id(player: str) -> Optional[int]:
    """選手写真 (eyecatch map) → 巨人マーク fallback (既存ルール)。"""
    try:
        from src.data_site_query import _GIANTS_MARK_MEDIA_ID, mapped_player_media_id

        if player:
            mid = mapped_player_media_id(player)
            if mid:
                return mid
        return _GIANTS_MARK_MEDIA_ID
    except Exception as exc:  # noqa: BLE001
        LOG.info("fan_pulse eyecatch skip: %r", exc)
        return None


def build_fan_pulse(
    *,
    now: datetime,
    window: str,
    gemini_api_key: str = "",
    dedup_set: Optional[set[str]] = None,
    wp_client_factory=None,
) -> Any:
    """記事を WP に作成し、X ポスト候補 (Candidate) を返す。素材不足は None。

    ``window``: "noon" | "postgame"。1 日各 1 本 (signature dedup)。
    """
    signature = "fanpulse|" + hashlib.sha1(
        f"{now.strftime('%Y%m%d')}|{window}".encode("utf-8")
    ).hexdigest()[:16]
    if dedup_set is not None and signature in dedup_set:
        return None
    keyword, topic_label = (
        _noon_topic() if window == "noon" else _postgame_topic()
    )
    if not keyword:
        return None
    reactions = gather_reactions(keyword)
    if len(reactions) < _MIN_REACTIONS:
        LOG.info("fan_pulse skip: reactions=%d (<%d)", len(reactions), _MIN_REACTIONS)
        return None
    parts = _summarize(topic_label, reactions, gemini_api_key)
    if not parts:
        return None

    date_label = f"{now.month}/{now.day}({_WEEKDAYS_JA[now.weekday()]})"
    title = f"【ファンの反応】{topic_label}まとめ｜{date_label}"
    article_url = ""
    try:
        if wp_client_factory is not None:
            wp = wp_client_factory()
        else:
            from src.wp_client import WPClient

            wp = WPClient()
        player = keyword if window == "noon" else ""
        post_id = wp.create_post(
            title,
            _article_html(topic_label, parts, reactions),
            status="publish",
            featured_media=_eyecatch_media_id(player),
            caller="fan_pulse",
            source_lane="fan_pulse",
        )
        post = wp.get_post(int(post_id))
        article_url = str(post.get("link") or "")
        LOG.info("fan_pulse article created id=%s url=%s", post_id, article_url)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fan_pulse wp create failed: %r", exc)
        return None

    from src.x_post_mail_lane import Candidate

    return Candidate(
        title=f"💬ファンの反応まとめ｜{topic_label}",
        metric="FAN_PULSE",
        period_label="反応まとめ",
        draft_text=(
            f"WP記事作成済 (noindex環境): {article_url}\n"
            f"素材 = Yahooリアルタイム検索の実在Xポスト {len(reactions)} 件 "
            f"(埋め込み {min(_EMBED_COUNT, len(reactions))} 件)。"
            "ポスト文は記事とは独立 (URL無し)。記事誘導するならリプにURL。"
        ),
        char_count=len(parts["post"]),
        signature=signature,
        post_text=parts["post"],
        focus_player=keyword if window == "noon" else "",
        source_material_type="fan_pulse",
    )
