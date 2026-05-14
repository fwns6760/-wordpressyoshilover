"""のもとけ-style SEO title template assembler.

Reshapes the already-backfilled title into one of the 5 patterns observed
on dnomotoke.com:

  A. ``<name>「<quote>」``                 — quote-style
  B. ``<modifier>の巨人・<name>、<result>``  — situation+result
  C. ``<verb>+<name>、<info>``             — action-first
  D. ``<OB さん>「<comment>」``             — OB / commentator
  E. ``<date> <game>「巨人vs.<opp>」<...>``  — date-based notice/broadcast

Subtype → pattern mapping (covers ~80% of yoshilover publishes):

  player_comment / player_quote / player  → A
  manager / manager_comment               → A (suffix 監督)
  coach_comment                           → A (suffix コーチ / 投手コーチ 等)
  postgame                                → B
  broadcast / program                     → E (broadcast)
  lineup                                  → E (lineup)
  notice                                  → E (notice)

ENABLE_NOMOTOKE_TITLE_TEMPLATE env (default ON) controls activation.
Returns ``None`` when facts are insufficient — caller keeps original title.
"""

from __future__ import annotations

import os
import re
from typing import Mapping, Optional


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def nomotoke_title_template_enabled() -> bool:
    val = (os.getenv("ENABLE_NOMOTOKE_TITLE_TEMPLATE") or "1").strip().lower()
    return val in _TRUE_VALUES


_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_QUOTE_RE = re.compile(r"[「『]([^」』]{2,60})[」』]")


# 335-QA Phase 3 / Issue #8: 同一 axis 試合状態 fact 重複圧縮
# 67169 例「逆転サヨナラ３ラン + ２試合連続のサヨナラ勝」型を 1 件に圧縮。
# 数値 fact (通算\d+号) / HR 描写 (メモリアル弾) は別軸として共存可、touch しない。
_SAYONARA_AXIS_RE = re.compile(
    r"(?:\d+試合連続の?|[０-９]+試合連続の?)?(?:逆転)?サヨナラ"
    r"(?:[3３]ラン|[2２]ラン|ホームラン|安打|打|勝ち?)?"
)
_KANSHU_AXIS_RE = re.compile(r"完封(?:勝ち|勝利|負け)?")
_KANTO_AXIS_RE = re.compile(r"完投(?:勝利|勝ち|負け)?")

_EVENT_AXIS_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("sayonara", _SAYONARA_AXIS_RE),
    ("kanshu", _KANSHU_AXIS_RE),
    ("kanto", _KANTO_AXIS_RE),
)

_LEADING_PARTICLES_FOR_DROP = "がはをにでと"
_TRAILING_PUNCT_FOR_DROP = "、。！!？?…"


def compress_event_token_repetition(title: str) -> str:
    """Same-axis 試合状態 fact が 2+ 出現したら、最初の 1 件を残し以降を drop。

    対象 axis: サヨナラ / 完封 / 完投。数値 fact (通算\\d+号 等) や HR 描写
    (メモリアル弾) は別 axis として共存可、touch しない。
    forward-only、idempotent (1 回適用で完了)。
    """
    if not title:
        return title
    result = title
    for _axis_name, pattern in _EVENT_AXIS_PATTERNS:
        matches = list(pattern.finditer(result))
        if len(matches) < 2:
            continue
        keep_start = matches[0].start()
        for m in reversed(matches[1:]):
            drop_start, drop_end = m.start(), m.end()
            if drop_start <= keep_start < drop_end:
                continue
            if drop_start > 0 and result[drop_start - 1] in _LEADING_PARTICLES_FOR_DROP:
                drop_start -= 1
            while drop_end < len(result) and result[drop_end] in _TRAILING_PUNCT_FOR_DROP:
                drop_end += 1
            result = result[:drop_start] + result[drop_end:]
    return result


def _clean(text: str) -> str:
    if not text:
        return ""
    return _WS_RE.sub(" ", _HTML_RE.sub(" ", text)).strip()


def _first_quote(*texts: str, max_len: int = 40) -> str:
    """335-QA Phase 1: literal quote を返す、`…` truncation は使わない。

    - 全長 ≤ max_len: そのまま literal を返す (trailing 。、 は strip)
    - 全長 > max_len: max_len 内で natural break (句読点 。！？、) を探し、
      その位置で literal 切り出して返す
    - natural break が無い極端な長文: backward compat 用に末尾 `…` で切る
      (新規記事では稀、レガシー fallback として残す)
    - 2 文字未満は空文字

    max_len 既定値を 28 → 40 に拡張([[feedback_title_clickable_descriptive]]
    で短すぎ引用 + `…` truncation を禁則化した結果)。
    """
    for t in texts:
        t = _clean(t)
        if not t:
            continue
        m = _QUOTE_RE.search(t)
        if not m:
            continue
        inner = m.group(1).strip().rstrip("。、")
        if len(inner) < 2:
            continue
        if len(inner) <= max_len:
            return inner
        # > max_len: natural break で literal 切り出し
        head = inner[:max_len]
        for sep in ("。", "！", "？", "、"):
            idx = head.rfind(sep)
            if idx >= max(2, max_len // 2):
                return head[: idx + 1].rstrip("。、")
        # natural break 無い極端な長文: legacy fallback で `…` 切り
        return head.rstrip() + "…"
    return ""


def _first_quote_for_digest(
    *texts: str,
    min_len: int = 20,
    max_len: int = 40,
) -> str:
    """player_voice_digest 専用: literal quote を [min_len, max_len] 文字で返す。

    既存 ``_first_quote`` と違い ``…`` の trim を行わない strict literal contract。
    複数 quote / 複数 text を順に走査し、範囲内のものを最初に拾う。trailing 。、
    は のもとけ headline style に合わせて strip。範囲内 quote が無ければ空文字。
    """
    for t in texts:
        t = _clean(t)
        if not t:
            continue
        for m in _QUOTE_RE.finditer(t):
            inner = m.group(1).strip().rstrip("。、")
            if min_len <= len(inner) <= max_len:
                return inner
    return ""


def _display_role_suffix(role: str) -> str:
    role = (role or "").strip()
    if role == "監督":
        return "監督"
    if role == "コーチ":
        return "コーチ"
    if role in {"投手"}:
        return "投手"
    if role in {"捕手", "内野手", "外野手", "選手"}:
        return ""
    return ""


_POSTGAME_RESULT_MARKERS = (
    ("サヨナラ", "サヨナラ勝ち"),
    ("逆転", "逆転勝ち"),
    ("完封", "完封勝ち"),
    ("延長", "延長戦"),
    ("連勝", "連勝"),
    ("敗戦", "敗戦"),
    ("惜敗", "惜敗"),
    ("勝利", "勝利"),
)


def _postgame_modifier(source_title: str, source_body: str, summary: str) -> str:
    """Extract a short B-pattern modifier like 「サヨナラ打の」「無失点投球の」.
    Returns empty when nothing matches."""
    text = " ".join(_clean(t) for t in (source_title, summary, source_body) if t)[:600]
    if not text:
        return ""
    if "サヨナラ" in text:
        return "サヨナラ"
    if "逆転" in text:
        return "逆転"
    if "無失点" in text:
        return "無失点投球"
    if "完封" in text:
        return "完封"
    if "ホームラン" in text or "本塁打" in text:
        return "本塁打"
    if "好救援" in text or "セーブ" in text:
        return "好救援"
    if "猛打賞" in text:
        return "猛打賞"
    return ""


def _postgame_result_phrase(source_title: str, source_body: str, summary: str) -> str:
    text = " ".join(_clean(t) for t in (source_title, summary, source_body) if t)[:600]
    if not text:
        return ""
    for needle, phrase in _POSTGAME_RESULT_MARKERS:
        if needle in text:
            return phrase
    return ""


def _opponent_from_facts(metadata: Mapping[str, object]) -> str:
    for key in ("opponent", "opponent_team", "opponent_team_name"):
        v = str(metadata.get(key) or "").strip()
        if v:
            return v
    return ""


def _date_label_from_facts(metadata: Mapping[str, object]) -> str:
    for key in ("event_date_label", "date_label", "game_date_label"):
        v = str(metadata.get(key) or "").strip()
        if v:
            return v
    return ""


def _is_quote_subtype(subtype: str) -> bool:
    return subtype in {
        "player_comment",
        "player_quote",
        "manager_comment",
        "coach_comment",
    }


# 335-QA Phase 2: 反応記事 (player A が player B を称賛 / 祝福 + 短引用 2 つ) を
# source 内 literal で検出する pattern。yoshilover の H2 generator が
# `AがBのfactをverb「q1」「q2」` 形式を出すケースを直接拾う。AI / LLM 一切なし。
_REACTION_PATTERN_RE = re.compile(
    r"([^\s「」]{2,8})が([^\s「」]{2,8})の([^を「」]{2,30})を"
    r"(祝福|称賛|絶賛|賛辞|評価|喜び|反応|感心|驚き|喝采|歓喜|たたえ)"
    r"「([^」]{2,15})」「([^」]{2,15})」"
)

# 335-QA Phase 2 followup (post 67262 fix):
# subject + 、 + 任意 descriptor (例 "幼なじみ") + target + の + fact + 任意を + verb + 「q1」「q2」
# 既存 R が `が` 区切り + を 必須を要求するのに対し、R2 は `、` 区切り + を 任意 + descriptor 任意。
_REACTION_PATTERN_RE2 = re.compile(
    r"([^\s「」、【】]{2,8})、"
    r"(?:[“”\"『][^“”\"』」、]{1,8}[“”\"』])?"
    r"([^\s「」、【】]{2,8})の"
    r"([^を「」]{2,30})を?"
    r"(祝福|称賛|絶賛|賛辞|評価|喜び|反応|感心|驚き|喝采|歓喜|たたえ)"
    r"\s*"
    r"「([^」]{2,15})」\s*「([^」]{2,15})」"
)


def _assemble_pattern_R_reaction(
    *,
    source_title: str,
    source_body: str,
    summary: str,
) -> str:
    """Pattern R: 反応記事の literal extraction。

    R: `[A]が[B]の[fact]を[verb]「[q1]」「[q2]」` (既存)
    R2: `[A]、(任意descriptor)[B]の[fact](任意を)[verb]「[q1]」「[q2]」` (67262 fix)

    R を優先試行、失敗時 R2。output 形式は常に `[A]が[B]の[fact]を[verb]「[q1]」「[q2]」`。
    見つからなければ空文字 (caller は Pattern A 等に fall-through)。
    """
    for text in (source_title, source_body, summary):
        text = _clean(text)
        if not text:
            continue
        for pat in (_REACTION_PATTERN_RE, _REACTION_PATTERN_RE2):
            m = pat.search(text)
            if not m:
                continue
            subject = m.group(1).strip()
            target = m.group(2).strip()
            fact = m.group(3).strip()
            verb = m.group(4).strip()
            q1 = m.group(5).strip().rstrip("。、")
            q2 = m.group(6).strip().rstrip("。、")
            if not (subject and target and fact and verb and q1 and q2):
                continue
            return f"{subject}が{target}の{fact}を{verb}「{q1}」「{q2}」"
    return ""


def _assemble_pattern_A(
    *,
    name: str,
    role: str,
    quote: str,
    is_manager: bool,
    is_coach: bool,
) -> Optional[str]:
    if not name or not quote:
        return None
    role_suffix = ""
    if is_manager:
        role_suffix = "監督"
    elif is_coach:
        role_suffix = _display_role_suffix(role) or "コーチ"
    if role_suffix and not name.endswith(role_suffix):
        head = f"{name}{role_suffix}"
    else:
        head = name
    return f"{head}「{quote}」"


def _assemble_pattern_B(
    *,
    name: str,
    role: str,
    source_title: str,
    source_body: str,
    summary: str,
) -> Optional[str]:
    if not name:
        return None
    modifier = _postgame_modifier(source_title, source_body, summary)
    result_phrase = _postgame_result_phrase(source_title, source_body, summary)
    if not modifier and not result_phrase:
        return None
    role_suffix = _display_role_suffix(role)
    name_with_role = f"{name}{role_suffix}" if role_suffix and not name.endswith(role_suffix) else name
    prefix = f"{modifier}の" if modifier else ""
    tail = f"、{result_phrase}" if result_phrase else ""
    return f"{prefix}巨人・{name_with_role}{tail}"


def _assemble_pattern_E_broadcast(
    *,
    metadata: Mapping[str, object],
    source_title: str,
) -> Optional[str]:
    """Returns broadcast-style title only when date+opponent are available."""
    date_label = _date_label_from_facts(metadata)
    opponent = _opponent_from_facts(metadata)
    if not date_label or not opponent:
        return None
    suffix = "【テレビ・ネット中継】"
    return f"{date_label}「巨人vs.{opponent}」{suffix}"


_SCORE_RE = re.compile(r"(\d{1,2})[\-－‐−](\d{1,2})")
_GAME_NUM_RE = re.compile(r"(\d{1,2})\s*回戦")


def _score_from_text(*texts: str) -> str:
    for t in texts:
        t = _clean(t)
        if not t:
            continue
        m = _SCORE_RE.search(t)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return ""


def _game_number_from_text(*texts: str) -> str:
    for t in texts:
        t = _clean(t)
        if not t:
            continue
        m = _GAME_NUM_RE.search(t)
        if m:
            return m.group(1)
    return ""


def _league_label_from_facts(metadata: Mapping[str, object]) -> str:
    v = str(metadata.get("league_label") or metadata.get("league") or "").strip()
    if v:
        return v
    return "セ・リーグ"


def _team_label_for_farm() -> str:
    return "巨人2軍"


def _team_label_for_first() -> str:
    return "巨人"


_NOTICE_ACTION_MARKERS = (
    ("登録抹消", "登録抹消"),
    ("抹消", "登録抹消"),
    ("一軍登録", "登録"),
    ("登録", "登録"),
    ("昇格", "昇格"),
    ("復帰", "復帰"),
    ("合流", "合流"),
    ("戦力外", "戦力外"),
)


def _notice_action_from_text(*texts: str) -> str:
    text = " ".join(_clean(t) for t in texts if t)
    if not text:
        return ""
    for needle, label in _NOTICE_ACTION_MARKERS:
        if needle in text:
            return label
    return ""


def _notice_player_count_from_text(*texts: str) -> int:
    text = " ".join(_clean(t) for t in texts if t)
    if not text:
        return 0
    m = re.search(r"(\d+)\s*(?:人|名)\s*の?\s*選手", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return 0
    return 0


def _assemble_pattern_F_postgame_detail(
    *,
    metadata: Mapping[str, object],
    source_title: str,
    source_body: str,
    summary: str,
    league_level: str = "first",
) -> Optional[str]:
    """Pattern F: postgame 試合結果速報 詳細版.

    `<date>(<曜>) <league>X回戦「巨人vs.<opp>」【試合結果】 巨人、<score>で<result>…`
    """
    date_label = _date_label_from_facts(metadata)
    opponent = _opponent_from_facts(metadata)
    if not date_label or not opponent:
        return None
    score = _score_from_text(source_title, source_body, summary)
    result_phrase = _postgame_result_phrase(source_title, source_body, summary)
    if not score and not result_phrase:
        return None
    league = _league_label_from_facts(metadata)
    game_num = _game_number_from_text(source_title, summary)
    game_label = f"{league}{game_num}回戦" if game_num else f"{league}公式戦"
    team_label = _team_label_for_first() if league_level != "farm" else _team_label_for_farm()
    tail = f" {team_label}、{score}で{result_phrase}…" if score and result_phrase else (
        f" {team_label}、{score}…" if score else f" {team_label}、{result_phrase}…"
    )
    return f"{date_label} {game_label}「巨人vs.{opponent}」【試合結果】{tail}"


def _assemble_pattern_G_farm_detail(
    *,
    metadata: Mapping[str, object],
    source_title: str,
    source_body: str,
    summary: str,
) -> Optional[str]:
    """Pattern G: ファーム公式戦 試合結果速報.

    `<date>(<曜>) ファーム公式戦「巨人vs.<opp>」【試合結果】 巨人2軍、<score>で<result>…`
    """
    date_label = _date_label_from_facts(metadata)
    opponent = _opponent_from_facts(metadata)
    if not date_label or not opponent:
        return None
    score = _score_from_text(source_title, source_body, summary)
    result_phrase = _postgame_result_phrase(source_title, source_body, summary)
    if not score and not result_phrase:
        return None
    tail = f" 巨人2軍、{score}で{result_phrase}…" if score and result_phrase else (
        f" 巨人2軍、{score}…" if score else f" 巨人2軍、{result_phrase}…"
    )
    return f"{date_label} ファーム公式戦「巨人vs.{opponent}」【試合結果】{tail}"


def _assemble_pattern_O_lineup(
    *,
    metadata: Mapping[str, object],
) -> Optional[str]:
    """Pattern O: スタメン発表.

    `<date>(<曜>) <league>X回戦「巨人vs.<opp>」 巨人、スタメン発表！！！`
    """
    date_label = _date_label_from_facts(metadata)
    opponent = _opponent_from_facts(metadata)
    if not date_label or not opponent:
        return None
    league = _league_label_from_facts(metadata)
    game_num = str(metadata.get("game_number") or "").strip()
    if not game_num:
        game_num = _game_number_from_text(date_label)
    game_label = f"{league}{game_num}回戦" if game_num else f"{league}公式戦"
    return f"{date_label} {game_label}「巨人vs.{opponent}」 巨人、スタメン発表！！！"


def _assemble_pattern_N_probable_starter(
    *,
    metadata: Mapping[str, object],
    source_title: str,
    summary: str,
) -> Optional[str]:
    """Pattern N: 予告先発発表.

    minimum: `<date>(<曜>)の予告先発が発表される！！！`
    enriched (opponent あり時): `<date>(<曜>) <league>X回戦「巨人vs.<opp>」 予告先発が発表される！！！`
    """
    date_label = _date_label_from_facts(metadata)
    if not date_label:
        return None
    text = " ".join(_clean(t) for t in (source_title, summary) if t)
    if "予告先発" not in text:
        return None
    opponent = _opponent_from_facts(metadata)
    if opponent:
        league = _league_label_from_facts(metadata)
        game_num = _game_number_from_text(date_label)
        game_label = f"{league}{game_num}回戦" if game_num else f"{league}公式戦"
        return f"{date_label} {game_label}「巨人vs.{opponent}」 予告先発が発表される！！！"
    return f"{date_label}の予告先発が発表される！！！"


def _assemble_pattern_M_notice(
    *,
    metadata: Mapping[str, object],
    source_title: str,
    source_body: str,
    summary: str,
) -> Optional[str]:
    """Pattern M: 公示.

    `【公示】<date>のプロ野球公示 巨人が<N>人の選手を<アクション>`
    """
    date_label = _date_label_from_facts(metadata)
    text = " ".join(_clean(t) for t in (source_title, source_body, summary) if t)
    if "公示" not in text:
        return None
    action = _notice_action_from_text(source_title, source_body, summary)
    if not action:
        return None
    if not date_label:
        return None
    count = _notice_player_count_from_text(source_title, source_body, summary)
    if count > 0:
        tail = f"巨人が{count}人の選手を{action}"
    else:
        tail = f"巨人が選手を{action}"
    return f"【公示】{date_label}のプロ野球公示 {tail}"


def _assemble_pattern_X_player_voice_digest(
    *,
    name: str,
    quote: str,
    event_token: str,
) -> Optional[str]:
    """Pattern X: player_voice_digest (multi-source digest).

    `<選手名>「<セリフ 20-40字>」<イベント>` の literal assembly。3-token 全て
    source からの literal でなければならず、LLM / AI rewrite を一切経由しない。

    Returns ``None`` when any token is missing or quote length is outside
    ``[20, 40]`` chars. 上位 caller はこの場合 draft + review に落とす想定で、
    LLM で「補完」「title 可能化」してはならない (本 ticket の不可触契約)。
    """
    name = (name or "").strip()
    quote = (quote or "").strip()
    event_token = (event_token or "").strip()
    if not name or not quote or not event_token:
        return None
    if not (20 <= len(quote) <= 40):
        return None
    return f"{name}「{quote}」{event_token}"


def assemble_nomotoke_title(
    *,
    article_subtype: str,
    existing_title: str,
    source_title: str = "",
    source_body: str = "",
    summary: str = "",
    player_name: str = "",
    role: str = "",
    metadata: Optional[Mapping[str, object]] = None,
) -> Optional[str]:
    """Reshape the title to a のもとけ-style pattern based on subtype.

    Returns the reshaped title, or ``None`` when:
      - the assembler is disabled via env
      - subtype has no mapped pattern
      - required facts (name / quote / modifier) are missing
      - the assembled title would equal the input (idempotent)

    Caller keeps ``existing_title`` when ``None`` is returned.
    """
    if not nomotoke_title_template_enabled():
        return None
    metadata = dict(metadata or {})
    subtype = (article_subtype or "").strip()
    name = (player_name or "").strip()

    assembled: Optional[str] = None
    if subtype == "player_voice_digest":
        # 3-token literal assembly: 選手名「セリフ20-40字」イベント。
        # metadata['event_token'] は upstream clusterer (Phase 2) が source 由来
        # の literal 数値 / 試合状態 fact を入れる。Phase 1 では title path のみ。
        # 3-token のいずれかが揃わなければ None (caller drops to draft + review)。
        quote = _first_quote_for_digest(
            source_body,
            source_title,
            summary,
            existing_title,
            min_len=20,
            max_len=40,
        )
        event_token = str(metadata.get("event_token") or "").strip()
        assembled = _assemble_pattern_X_player_voice_digest(
            name=name,
            quote=quote,
            event_token=event_token,
        )
    elif _is_quote_subtype(subtype):
        # 335-QA Phase 2: 反応 pattern を先に試す。source 内に「AがBのfactを
        # verb「q1」「q2」」 が literal で存在すれば、それをそのまま採用。
        # 失敗時は通常 Pattern A に fall-through (旧挙動)。
        reaction_assembled = _assemble_pattern_R_reaction(
            source_title=source_title,
            source_body=source_body,
            summary=summary,
        )
        if reaction_assembled:
            assembled = reaction_assembled
        else:
            quote = _first_quote(
                existing_title, source_title, source_body, summary
            )
            assembled = _assemble_pattern_A(
                name=name,
                role=role,
                quote=quote,
                is_manager=subtype == "manager_comment" or role == "監督",
                is_coach=subtype == "coach_comment" or role == "コーチ",
            )
    elif subtype == "manager":
        quote = _first_quote(existing_title, source_title, source_body, summary)
        assembled = _assemble_pattern_A(
            name=name,
            role=role or "監督",
            quote=quote,
            is_manager=True,
            is_coach=False,
        )
    elif subtype == "postgame":
        # B (修飾+選手+結果) を先に試す。name + modifier/result が揃わない時は
        # F (試合結果詳細、score+opp+result) に fall through。
        assembled = _assemble_pattern_B(
            name=name,
            role=role,
            source_title=source_title,
            source_body=source_body,
            summary=summary,
        )
        if not assembled:
            league_level = str(metadata.get("league_level") or "first")
            assembled = _assemble_pattern_F_postgame_detail(
                metadata=metadata,
                source_title=source_title,
                source_body=source_body,
                summary=summary,
                league_level=league_level,
            )
    elif subtype in {"farm", "farm_result"}:
        assembled = _assemble_pattern_G_farm_detail(
            metadata=metadata,
            source_title=source_title,
            source_body=source_body,
            summary=summary,
        )
    elif subtype in {"broadcast", "program"}:
        assembled = _assemble_pattern_E_broadcast(
            metadata=metadata,
            source_title=source_title,
        )
    elif subtype in {"lineup", "lineup_notice"}:
        assembled = _assemble_pattern_O_lineup(metadata=metadata)
    elif subtype in {"pregame", "probable_starter"}:
        assembled = _assemble_pattern_N_probable_starter(
            metadata=metadata,
            source_title=source_title,
            summary=summary,
        )
    elif subtype in {"notice", "official_notice"}:
        assembled = _assemble_pattern_M_notice(
            metadata=metadata,
            source_title=source_title,
            source_body=source_body,
            summary=summary,
        )

    if assembled and assembled.strip() and assembled.strip() != _clean(existing_title):
        return assembled.strip()
    return None


__all__ = [
    "assemble_nomotoke_title",
    "nomotoke_title_template_enabled",
]
