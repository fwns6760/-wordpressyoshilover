"""INSIGHT-009 — natural language query parser (rule-based, no LLM).

Maps free-form Japanese questions like
    「セリーグのセカンドUZRトップ10は？」
    「巨人の岡本のwOBA何位？」
    「先発FIPランキング上位5」
to structured query parameters that feed into
:func:`manual_intake_insight_query.generate_article`.

Pure dict + regex, no Gemini / external API. Coverage ~80% of common
operator phrasings; falls back to ``unresolved`` flags so the UI can
prompt for missing pieces.

Returns ``{metric, position, top_n, focus_player, league, raw_text,
unresolved: [...] }``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# ─── dictionaries ───────────────────────────────────────────────────────────

# Position aliases — Japanese natural language → single-kanji canonical
# used by insight_defense_proxy / insight_rank_query.
POSITION_ALIASES: dict[str, str] = {
    "ピッチャー": "投", "投手": "投", "先発": "投", "中継ぎ": "投", "抑え": "投",
    "キャッチャー": "捕", "捕手": "捕",
    "ファースト": "一", "一塁": "一", "一塁手": "一", "1B": "一",
    "セカンド": "二", "二塁": "二", "二塁手": "二", "2B": "二",
    "サード": "三", "三塁": "三", "三塁手": "三", "3B": "三",
    "ショート": "遊", "遊撃": "遊", "遊撃手": "遊", "SS": "遊",
    "レフト": "左", "左翼": "左", "左翼手": "左", "LF": "左",
    "センター": "中", "中堅": "中", "中堅手": "中", "CF": "中",
    "ライト": "右", "右翼": "右", "右翼手": "右", "RF": "右",
    "外野": None,  # unresolved, prompt user
    "内野": None,
}

# Metric aliases — natural Japanese / English → canonical name in
# insight_rank_query.KNOWN_METRICS
METRIC_ALIASES: dict[str, str] = {
    # batting
    "打率": "AVG", "AVG": "AVG",
    "出塁率": "OBP", "OBP": "OBP",
    "長打率": "SLG", "SLG": "SLG",
    "OPS": "OPS",
    "ISO": "ISO", "純長打": "ISO",
    "wOBA": "wOBA",
    "三振率": "K_pct", "K%": "K_pct", "K_pct": "K_pct",
    "四球率": "BB_pct", "BB%": "BB_pct", "BB_pct": "BB_pct",
    "BABIP": "BABIP",
    # pitching
    "防御率": "ERA", "ERA": "ERA",
    "WHIP": "WHIP",
    "K/9": "K_per_9", "K9": "K_per_9", "奪三振率": "K_per_9",
    "BB/9": "BB_per_9", "BB9": "BB_per_9",
    "HR/9": "HR_per_9", "HR9": "HR_per_9",
    "K/BB": "K_BB", "KBB": "K_BB",
    "FIP": "FIP",
    "xFIP": "xFIP",
    # defense
    "UZR": "UZR_proxy", "RF": "RF_proxy",
    "Range Factor": "RF_proxy",
    "守備機会変換率": "RF_proxy",
    "UZR_proxy": "UZR_proxy", "RF_proxy": "RF_proxy",
}

LEAGUE_ALIASES: dict[str, str] = {
    "セ・リーグ": "central", "セリーグ": "central", "セリーグの": "central",
    "セ": "central",
    "パ・リーグ": "pacific", "パリーグ": "pacific", "パリーグの": "pacific",
    "パ": "pacific",
    "全12球団": "all", "全球団": "all",
}

# top_n triggers — extract a number
_TOP_N_RE = re.compile(
    r"(?:トップ|上位|TOP|top)\s*(?P<n>\d+)|(?P<n2>\d+)\s*位",
    re.IGNORECASE,
)

# 自然語の数字 (一桁の漢数字、稀に必要)
_KANJI_NUMS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


# ─── helpers ────────────────────────────────────────────────────────────────


def _giants_roster_names() -> list[tuple[str, str]]:
    """Return active Giants ``(alias_or_canonical, canonical)`` pairs.

    Each canonical name is paired with itself and with every alias (so
    free-form input like 「岡本」「岡本 和真」「マー君」 all resolve back
    to the canonical). Surname-only entries are also generated when the
    surname uniquely maps to one canonical."""
    roster = Path(__file__).resolve().parents[2] / "config" / "giants_roster.json"
    if not roster.exists():
        return []
    try:
        rows = json.loads(roster.read_text(encoding="utf-8"))
    except Exception:
        return []
    pairs: list[tuple[str, str]] = []
    canonicals: list[str] = []
    for r in rows:
        if not r.get("active"):
            continue
        canon = (r.get("name") or "").strip()
        if not canon:
            continue
        canonicals.append(canon)
        # canonical itself + every alias
        pairs.append((canon, canon))
        for a in r.get("aliases") or []:
            alias = (a or "").strip()
            if alias and alias != canon:
                pairs.append((alias, canon))
        # spaces-removed variant for "岡本 和真" → "岡本和真"
        compact = canon.replace(" ", "").replace("　", "")
        if compact != canon and compact:
            pairs.append((compact, canon))
    # Surname (first 2 chars) fallback for unique surnames
    surname_groups: dict[str, list[str]] = {}
    for canon in canonicals:
        compact = canon.replace(" ", "").replace("　", "")
        if len(compact) >= 2:
            surname_groups.setdefault(compact[:2], []).append(canon)
    for surname, cands in surname_groups.items():
        if len(cands) == 1:
            pairs.append((surname, cands[0]))
    # Longest first so substring matches prefer specific names
    pairs.sort(key=lambda kv: -len(kv[0]))
    return pairs


def _detect_metric(text: str) -> Optional[str]:
    # Longer aliases first to avoid sub-matches (e.g. "BB/9" vs "9")
    for alias in sorted(METRIC_ALIASES, key=len, reverse=True):
        if alias in text:
            return METRIC_ALIASES[alias]
    return None


def _detect_position(text: str) -> tuple[Optional[str], bool]:
    """Return (canonical_position_kanji, was_ambiguous)."""
    for alias in sorted(POSITION_ALIASES, key=len, reverse=True):
        if alias in text:
            v = POSITION_ALIASES[alias]
            if v is None:
                return (None, True)  # 外野 / 内野 = ambiguous
            return (v, False)
    return (None, False)


def _detect_league(text: str) -> Optional[str]:
    for alias in sorted(LEAGUE_ALIASES, key=len, reverse=True):
        if alias in text:
            return LEAGUE_ALIASES[alias]
    return None


def _detect_top_n(text: str) -> Optional[int]:
    m = _TOP_N_RE.search(text)
    if m:
        n = m.group("n") or m.group("n2")
        try:
            return max(1, min(int(n), 50))
        except (TypeError, ValueError):
            pass
    return None


def _detect_focus_player(text: str, roster_pairs: list[tuple[str, str]]) -> Optional[str]:
    """Find the longest matching alias / canonical in ``text`` and return
    the canonical name. ``roster_pairs`` already sorted longest-first."""
    for alias, canon in roster_pairs:
        if alias in text:
            return canon
    return None


# ─── public API ─────────────────────────────────────────────────────────────


def parse_question(
    text: str,
    *,
    llm_fallback: bool = True,
    llm_client=None,
) -> dict:
    """Parse a natural Japanese question into structured query params.

    Returns ``{metric, position, top_n, focus_player, league, raw_text,
                unresolved, source}`` where ``source`` is "rule" or
    "llm_fallback" indicating which path resolved the metric.

    LLM fallback (Gemini 2.5 Flash) only fires when rule-based parsing
    fails to identify a metric AND the daily budget guard allows. Cost
    per query is ~0.005 yen; the budget cap defaults to 500/day for
    user-triggered queries.
    """
    raw = (text or "").strip()
    metric = _detect_metric(raw)
    position, position_ambiguous = _detect_position(raw)
    league = _detect_league(raw)
    top_n = _detect_top_n(raw)
    roster = _giants_roster_names()
    focus = _detect_focus_player(raw, roster)

    source = "rule"

    # LLM fallback when rule-based couldn't identify the metric.
    if not metric and llm_fallback and raw and _llm_budget_ok():
        llm_result = _parse_via_llm(raw, client=llm_client)
        if llm_result:
            _llm_record_use()
            source = "llm_fallback"
            metric = metric or llm_result.get("metric")
            position = position or llm_result.get("position")
            league = league or llm_result.get("league")
            if not top_n and llm_result.get("top_n"):
                top_n = llm_result["top_n"]
            if not focus and llm_result.get("focus_player"):
                # Validate LLM's player against the roster — never trust
                # the model to invent canonical names.
                candidate = str(llm_result["focus_player"]).strip()
                roster_canonicals = {canonical for _, canonical in roster}
                if candidate in roster_canonicals:
                    focus = candidate

    unresolved: list[str] = []
    if not metric:
        unresolved.append("metric")
    # Defense metric requires position
    if metric in {"RF_proxy", "UZR_proxy"} and not position:
        unresolved.append("position")
    if position_ambiguous and not position:
        unresolved.append("position_ambiguous")

    return {
        "metric": metric,
        "position": position,
        "top_n": top_n or 10,
        "focus_player": focus,
        "league": league,
        "raw_text": raw,
        "unresolved": unresolved,
        "source": source,
    }


# ─── LLM fallback (Gemini 2.5 Flash) ────────────────────────────────────────


import logging  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

_LOGGER = logging.getLogger(__name__)
_LLM_BUDGET_PATH_ENV = "INSIGHT_NL_LLM_BUDGET_PATH"
_LLM_BUDGET_DAILY_CAP_ENV = "INSIGHT_NL_LLM_DAILY_CAP"
_LLM_BUDGET_DEFAULT_PATH = "/tmp/insight_nl_llm_budget.json"
_LLM_BUDGET_DEFAULT_CAP = 500
_LLM_MODEL_NAME = "gemini-2.5-flash"


def _llm_budget_path() -> Path:
    return Path(os.environ.get(_LLM_BUDGET_PATH_ENV, _LLM_BUDGET_DEFAULT_PATH))


def _llm_budget_cap() -> int:
    raw = os.environ.get(_LLM_BUDGET_DAILY_CAP_ENV, "").strip()
    if not raw:
        return _LLM_BUDGET_DEFAULT_CAP
    try:
        return max(0, int(raw))
    except ValueError:
        return _LLM_BUDGET_DEFAULT_CAP


def _llm_budget_today_key() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _llm_budget_ok() -> bool:
    """Return True when today's LLM fallback budget has not been exceeded.

    File-based counter at ``_llm_budget_path()`` keyed by JST date. Cap
    defaults to 500/day (~$0.025), env-tunable via
    ``INSIGHT_NL_LLM_DAILY_CAP``.
    """
    if _llm_budget_cap() <= 0:
        return False
    path = _llm_budget_path()
    today = _llm_budget_today_key()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    used = int(data.get(today, 0) or 0)
    return used < _llm_budget_cap()


def _llm_record_use() -> None:
    path = _llm_budget_path()
    today = _llm_budget_today_key()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data[today] = int(data.get(today, 0) or 0) + 1
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        _LOGGER.warning("insight_nl_llm_budget_write_failed path=%s", path)


_LLM_SYSTEM_PROMPT = """あなたは野球統計クエリを解釈するパーサーです。

入力: 日本語の自然な質問文 (1 行)
出力: JSON オブジェクト。以下のフィールドのみ:
- metric (string | null): 指標。次のいずれか、または null。
    AVG, OBP, SLG, OPS, ISO, wOBA, K_pct, BB_pct, BABIP,
    ERA, WHIP, K_per_9, BB_per_9, HR_per_9, K_BB, FIP, xFIP,
    UZR_proxy, RF_proxy
- position (string | null): 守備位置 1 文字。次のいずれか、または null。
    投, 捕, 一, 二, 三, 遊, 左, 中, 右
- league (string | null): "central" / "pacific" / "all" / null
- top_n (integer | null): 上位 N 件。指定なければ null。
- focus_player (string | null): 質問文に出てくる選手名そのまま。

制約:
- 必ず JSON のみ返す。前後に説明文を書かない。
- データに無い指標 (得点圏打率/月別/対戦相手別/球場別 等) は metric=null にする。
- 確信が無いフィールドは null にする (推測で埋めない)。

例:
入力: 「セリーグのセカンドUZRトップ10は？」
出力: {"metric":"UZR_proxy","position":"二","league":"central","top_n":10,"focus_player":null}

入力: 「打撃絶好調なのはだれ？」
出力: {"metric":"OPS","position":null,"league":null,"top_n":null,"focus_player":null}

入力: 「得点圏で熱い奴」
出力: {"metric":null,"position":null,"league":null,"top_n":null,"focus_player":null}
"""


def _parse_via_llm(text: str, *, client=None) -> Optional[dict]:
    """Call Gemini Flash to extract structured query params from a free-
    form Japanese question. Returns ``None`` on any error (network /
    parse / API key missing) so the caller falls back gracefully.

    The function never raises — failures are logged and the rule-based
    result stands.
    """
    if not text:
        return None
    try:
        if client is None:
            client = _build_gemini_client()
        if client is None:
            return None
        response_text = client.parse(text)
        return _normalize_llm_response(response_text)
    except Exception as exc:  # noqa: BLE001 — never propagate to caller
        _LOGGER.warning("insight_nl_llm_fallback_error: %s", exc)
        return None


def _build_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY") or ""
    if not api_key:
        return None
    try:
        import importlib

        sdk = importlib.import_module("google.generativeai")
    except ImportError:
        return None
    sdk.configure(api_key=api_key)
    model = sdk.GenerativeModel(
        model_name=_LLM_MODEL_NAME,
        system_instruction=_LLM_SYSTEM_PROMPT,
    )

    class _GeminiClient:
        def parse(self, question: str) -> str:
            response = model.generate_content(
                question,
                generation_config={"response_mime_type": "application/json"},
            )
            return getattr(response, "text", "") or ""

    return _GeminiClient()


_VALID_METRICS = {
    "AVG", "OBP", "SLG", "OPS", "ISO", "wOBA",
    "K_pct", "BB_pct", "BABIP",
    "ERA", "WHIP", "K_per_9", "BB_per_9", "HR_per_9", "K_BB",
    "FIP", "xFIP", "UZR_proxy", "RF_proxy",
}
_VALID_POSITIONS = {"投", "捕", "一", "二", "三", "遊", "左", "中", "右"}
_VALID_LEAGUES = {"central", "pacific", "all"}


def _normalize_llm_response(response_text: str) -> Optional[dict]:
    """Parse LLM JSON output and clamp values to the known vocabulary.

    Returns ``None`` when the response is not valid JSON. Unknown
    metric / position / league values are dropped (set to None) so they
    never reach the SQL layer.
    """
    if not response_text:
        return None
    # Strip code fences just in case the model adds them despite
    # response_mime_type=application/json.
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    metric = data.get("metric")
    if metric not in _VALID_METRICS:
        metric = None
    position = data.get("position")
    if position not in _VALID_POSITIONS:
        position = None
    league = data.get("league")
    if league not in _VALID_LEAGUES:
        league = None
    top_n_raw = data.get("top_n")
    try:
        top_n = int(top_n_raw) if top_n_raw is not None else None
    except (TypeError, ValueError):
        top_n = None
    if top_n is not None and not (1 <= top_n <= 50):
        top_n = None
    focus_player = data.get("focus_player")
    if focus_player is not None and not isinstance(focus_player, str):
        focus_player = None
    return {
        "metric": metric,
        "position": position,
        "league": league,
        "top_n": top_n,
        "focus_player": focus_player,
    }
