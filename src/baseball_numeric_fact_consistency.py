from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
DASH_VARIANTS = str.maketrans(
    {
        "－": "-",
        "‐": "-",
        "−": "-",
        "–": "-",
        "—": "-",
        "ー": "-",
    }
)
GIANTS_ALIASES = frozenset({"巨人", "ジャイアンツ", "読売", "読売ジャイアンツ"})
TEAM_ALIASES = (
    "読売ジャイアンツ",
    "ジャイアンツ",
    "巨人",
    "阪神",
    "中日",
    "広島",
    "ヤクルト",
    "楽天",
    "DeNA",
    "ＤｅＮＡ",
    "ベイスターズ",
    "ロッテ",
    "オリックス",
    "ソフトバンク",
    "日本ハム",
    "日ハム",
    "西武",
    "ドジャース",
)
TEAM_PATTERN = "|".join(sorted((re.escape(alias) for alias in TEAM_ALIASES), key=len, reverse=True))
TEAM_ALIAS_RE = re.compile(TEAM_PATTERN)
SCORE_RE = re.compile(r"(?<!\d)(?P<left>\d{1,2})\s*(?:-|対|vs)\s*(?P<right>\d{1,2})(?!\d)", re.IGNORECASE)
TEAM_COLON_SCORE_RE = re.compile(
    rf"(?P<left_team>{TEAM_PATTERN})\s*[:：]\s*(?P<left>\d{{1,2}})"
    rf"(?:\s+|[、,／/]\s*)"
    rf"(?P<right_team>{TEAM_PATTERN})\s*[:：]\s*(?P<right>\d{{1,2}})"
)
WIN_MARKER_RE = re.compile(r"(勝利|白星|連勝|逆転勝ち)")
LOSS_MARKER_RE = re.compile(r"(敗れ|敗戦|黒星|連敗|完敗)")
INNINGS_DECIMAL_PATTERN = re.compile(r"^\d+\.\d+$")
INNINGS_INTEGER_PATTERN = re.compile(r"^\d+$")
INNINGS_FRACTION_PATTERN = re.compile(r"^(\d+)\s+([12])/3$")
PITCHER_INNINGS_TOKEN = r"(?:\d{1,2}回\s*[12]/3|\d{1,2}\s+[12]/3回?|\d{1,2}(?:\.\d+)?回?)"
PITCHER_FULL_RE = re.compile(
    r"(?:先発)?(?P<name>[一-龯々]{2,5}(?:[ァ-ヴー]{0,4})?)(?:投手)?(?:が|は|も)\s*"
    rf"(?P<innings>{PITCHER_INNINGS_TOKEN})\s*(?P<hits>\d{{1,2}})(?:安打|被安打)\s*(?P<runs>\d{{1,2}})失点"
)
PITCHER_HITS_ONLY_RE = re.compile(
    r"(?:先発)?(?P<name>[一-龯々]{2,5}(?:[ァ-ヴー]{0,4})?)(?:投手)?(?:が|は|も)\s*"
    r"(?P<hits>\d{1,2})被?安打(?:\s*(?P<runs>\d{1,2})失点)?"
)
TEAM_STATS_RE = re.compile(
    rf"(?P<team>{TEAM_PATTERN}|チーム|打線)(?:は|が|も)?\s*(?P<hits>\d{{1,2}})安打(?:\s*(?P<runs>\d{{1,2}})得点)?"
)
PLAYER_NAME_RE = re.compile(
    r"(?P<name>[一-龯々]{2,5}(?:[ァ-ヴー]{0,4})?)(?:投手|捕手|内野手|外野手|選手|監督|コーチ)?(?=[がはも、。！\s]|$)"
)
PLAYER_FACT_TAIL_RE = re.compile(
    r"^(?:投手|捕手|内野手|外野手|選手|監督|コーチ)?(?:が|は).{0,20}"
    r"(?:回|安打|被安打|失点|勝利|敗れ|黒星|白星|連勝|連敗|完投|好投|登板|先発)"
)
JP_YMD_RE = re.compile(r"(?<!\d)(?P<year>20\d{2})年\s*(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日")
JP_MD_RE = re.compile(r"(?<!\d)(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日")
TODAY_RE = re.compile(r"(本日|きょう|今日)")
YESTERDAY_RE = re.compile(r"(昨日)")
SOURCE_KEY_CANDIDATES = (
    "source_summary",
    "source_description",
    "player_names",
)
NAME_STOPWORDS = frozenset(
    {
        "巨人",
        "ジャイアンツ",
        "読売",
        "阪神",
        "中日",
        "広島",
        "ヤクルト",
        "楽天",
        "ベイスターズ",
        "ロッテ",
        "オリックス",
        "ソフトバンク",
        "日本ハム",
        "日ハム",
        "西武",
        "ドジャース",
        "試合",
        "結果",
        "打線",
        "チーム",
        "先発",
        "投手",
        "選手",
        "監督",
        "コーチ",
        "参照元",
        "スポーツ報知",
        "日刊スポーツ",
        "スポニチ",
        "東京ドーム",
    }
)
STRICT_SUBTYPES = frozenset({"postgame", "farm_result", "lineup", "farm_lineup", "pregame", "probable_starter"})
LENIENT_SUBTYPES = frozenset({"manager_comment", "player_comment", "sns_topic", "rumor_market"})


@dataclass(frozen=True)
class ScoreToken:
    raw: str
    left_score: int
    right_score: int
    start: int = -1
    left_team: str | None = None
    right_team: str | None = None
    giants_side: str | None = None

    @property
    def pair(self) -> tuple[int, int]:
        return (self.left_score, self.right_score)

    @property
    def reversed_pair(self) -> tuple[int, int]:
        return (self.right_score, self.left_score)

    @property
    def giants_score(self) -> int | None:
        if self.giants_side == "left":
            return self.left_score
        if self.giants_side == "right":
            return self.right_score
        return None

    @property
    def opponent_score(self) -> int | None:
        if self.giants_side == "left":
            return self.right_score
        if self.giants_side == "right":
            return self.left_score
        return None

    @property
    def giants_result(self) -> str | None:
        giants_score = self.giants_score
        opponent_score = self.opponent_score
        if giants_score is None or opponent_score is None:
            return None
        if giants_score > opponent_score:
            return "win"
        if giants_score < opponent_score:
            return "loss"
        return "tie"


@dataclass(frozen=True)
class DateToken:
    raw: str
    start: int = -1
    year: int | None = None
    month: int | None = None
    day: int | None = None
    relative_kind: str | None = None

    def resolve(self, publish_time_iso: str | None) -> str | None:
        reference = _publish_datetime(publish_time_iso)
        if reference is None:
            return None
        if self.relative_kind == "today":
            resolved = reference.date()
        elif self.relative_kind == "yesterday":
            resolved = reference.date() - timedelta(days=1)
        elif self.month is not None and self.day is not None:
            year = self.year if self.year is not None else reference.year
            resolved = date(year, self.month, self.day)
        else:
            return None
        return resolved.isoformat()


@dataclass(frozen=True)
class ConsistencyFinding:
    flag: str
    severity: str
    axis: str
    scope: str
    detail: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsistencyReport:
    severity: str
    findings: tuple[ConsistencyFinding, ...]
    hard_stop_flags: tuple[str, ...]
    review_flags: tuple[str, ...]
    x_candidate_suppress_flags: tuple[str, ...]


def _normalize_text(value: str) -> str:
    text = str(value or "").translate(FULLWIDTH_DIGITS).translate(DASH_VARIANTS)
    return text.replace("ＶＳ", "VS").replace("ｖｓ", "vs")


def _publish_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        current = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if current.tzinfo is None:
        return current.replace(tzinfo=JST)
    return current.astimezone(JST)


def _normalize_team_name(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in {"ＤｅＮＡ", "ベイスターズ"}:
        return "DeNA"
    if text == "読売ジャイアンツ":
        return "巨人"
    return text


def _team_before(text: str, start: int, *, radius: int = 18) -> str | None:
    window = text[max(0, start - radius) : start]
    matches = list(TEAM_ALIAS_RE.finditer(window))
    if not matches:
        return None
    return _normalize_team_name(matches[-1].group(0))


def _team_after(text: str, end: int, *, radius: int = 18) -> str | None:
    window = text[end : min(len(text), end + radius)]
    match = TEAM_ALIAS_RE.search(window)
    if not match:
        return None
    return _normalize_team_name(match.group(0))


def _giants_side(left_team: str | None, right_team: str | None) -> str | None:
    if left_team in GIANTS_ALIASES and right_team not in GIANTS_ALIASES:
        return "left"
    if right_team in GIANTS_ALIASES and left_team not in GIANTS_ALIASES:
        return "right"
    return None


def extract_scores(text: str) -> list[ScoreToken]:
    normalized = _normalize_text(text)
    tokens: list[ScoreToken] = []
    seen_spans: set[tuple[int, int]] = set()

    for match in TEAM_COLON_SCORE_RE.finditer(normalized):
        span = match.span()
        if span in seen_spans:
            continue
        seen_spans.add(span)
        left_team = _normalize_team_name(match.group("left_team"))
        right_team = _normalize_team_name(match.group("right_team"))
        tokens.append(
            ScoreToken(
                raw=str(text or "")[span[0] : span[1]],
                left_score=int(match.group("left")),
                right_score=int(match.group("right")),
                start=span[0],
                left_team=left_team,
                right_team=right_team,
                giants_side=_giants_side(left_team, right_team),
            )
        )

    for match in SCORE_RE.finditer(normalized):
        span = match.span()
        if span in seen_spans:
            continue
        seen_spans.add(span)
        left_team = _team_before(normalized, span[0])
        right_team = _team_after(normalized, span[1])
        tokens.append(
            ScoreToken(
                raw=str(text or "")[span[0] : span[1]],
                left_score=int(match.group("left")),
                right_score=int(match.group("right")),
                start=span[0],
                left_team=left_team,
                right_team=right_team,
                giants_side=_giants_side(left_team, right_team),
            )
        )

    return tokens


def extract_win_loss_markers(text: str) -> dict[str, Any]:
    normalized = _normalize_text(text)
    win_markers = [match.group(0) for match in WIN_MARKER_RE.finditer(normalized)]
    loss_markers = [match.group(0) for match in LOSS_MARKER_RE.finditer(normalized)]
    orientation: str | None = None
    if win_markers and not loss_markers:
        orientation = "win"
    elif loss_markers and not win_markers:
        orientation = "loss"
    return {
        "orientation": orientation,
        "win_markers": tuple(dict.fromkeys(win_markers)),
        "loss_markers": tuple(dict.fromkeys(loss_markers)),
    }


def _normalize_name(value: str) -> str:
    text = str(value or "").strip()
    for suffix in ("投手", "捕手", "内野手", "外野手", "選手", "監督", "コーチ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text.strip()


def _valid_player_name(value: str) -> bool:
    name = _normalize_name(value)
    if not name or name in NAME_STOPWORDS:
        return False
    if name in GIANTS_ALIASES:
        return False
    return 2 <= len(name) <= 8


def normalize_innings(value: Any) -> str | None:
    """Normalize pitcher innings notation into a conservative canonical string."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("回", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if INNINGS_INTEGER_PATTERN.match(text):
        return f"{int(text)}_0"
    if INNINGS_DECIMAL_PATTERN.match(text):
        whole, fraction = text.split(".", 1)
        if fraction == "0":
            return f"{int(whole)}_0"
        if fraction == "1":
            return f"{int(whole)}_1/3"
        if fraction == "2":
            return f"{int(whole)}_2/3"
        return None
    match = INNINGS_FRACTION_PATTERN.match(text)
    if match:
        return f"{int(match.group(1))}_{match.group(2)}/3"
    return None


def _legacy_innings_value(value: Any) -> int | None:
    normalized = normalize_innings(value)
    if normalized is None:
        return None
    whole, _, remainder = normalized.partition("_")
    if remainder == "0":
        return int(whole)
    return None


def extract_pitcher_team_stats(text: str) -> dict[str, list[dict[str, Any]]]:
    normalized = _normalize_text(text)
    pitchers: list[dict[str, Any]] = []
    teams: list[dict[str, Any]] = []
    seen_pitchers: set[tuple[str, str, int, int | None]] = set()
    seen_teams: set[tuple[str, int, int | None]] = set()

    for match in PITCHER_FULL_RE.finditer(normalized):
        name = _normalize_name(match.group("name"))
        if not _valid_player_name(name):
            continue
        innings_raw = match.group("innings")
        innings_normalized = normalize_innings(innings_raw)
        key = (name, innings_normalized or innings_raw, int(match.group("hits")), int(match.group("runs")))
        if key in seen_pitchers:
            continue
        seen_pitchers.add(key)
        pitchers.append(
            {
                "name": name,
                "innings": _legacy_innings_value(innings_raw),
                "innings_raw": innings_raw,
                "innings_normalized": innings_normalized,
                "hits": int(match.group("hits")),
                "runs": int(match.group("runs")),
                "raw": match.group(0),
            }
        )

    for match in PITCHER_HITS_ONLY_RE.finditer(normalized):
        name = _normalize_name(match.group("name"))
        if not _valid_player_name(name):
            continue
        innings = None
        runs = int(match.group("runs")) if match.group("runs") else None
        key = (name, "", int(match.group("hits")), runs)
        if key in seen_pitchers:
            continue
        seen_pitchers.add(key)
        pitchers.append(
            {
                "name": name,
                "innings": innings,
                "innings_raw": None,
                "innings_normalized": None,
                "hits": int(match.group("hits")),
                "runs": runs,
                "raw": match.group(0),
            }
        )

    for match in TEAM_STATS_RE.finditer(normalized):
        team = _normalize_team_name(match.group("team")) or "team"
        runs = int(match.group("runs")) if match.group("runs") else None
        key = (team, int(match.group("hits")), runs)
        if key in seen_teams:
            continue
        seen_teams.add(key)
        teams.append(
            {
                "team": team,
                "hits": int(match.group("hits")),
                "runs": runs,
                "raw": match.group(0),
            }
        )

    return {"pitchers": pitchers, "teams": teams}


def extract_player_names(text: str) -> set[str]:
    names: set[str] = set()
    normalized = _normalize_text(text)
    for match in PLAYER_NAME_RE.finditer(normalized):
        name = _normalize_name(match.group("name"))
        if _valid_player_name(name):
            names.add(name)
    return names


def extract_dates(text: str) -> list[DateToken]:
    normalized = _normalize_text(text)
    tokens: list[DateToken] = []
    seen_spans: set[tuple[int, int]] = set()

    for match in JP_YMD_RE.finditer(normalized):
        span = match.span()
        seen_spans.add(span)
        tokens.append(
            DateToken(
                raw=str(text or "")[span[0] : span[1]],
                start=span[0],
                year=int(match.group("year")),
                month=int(match.group("month")),
                day=int(match.group("day")),
            )
        )

    for match in JP_MD_RE.finditer(normalized):
        span = match.span()
        if span in seen_spans:
            continue
        seen_spans.add(span)
        tokens.append(
            DateToken(
                raw=str(text or "")[span[0] : span[1]],
                start=span[0],
                month=int(match.group("month")),
                day=int(match.group("day")),
            )
        )

    for pattern, kind in ((TODAY_RE, "today"), (YESTERDAY_RE, "yesterday")):
        for match in pattern.finditer(normalized):
            span = match.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            tokens.append(DateToken(raw=str(text or "")[span[0] : span[1]], start=span[0], relative_kind=kind))

    return tokens


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return tuple(ordered)


def _source_metadata_text(metadata: Mapping[str, Any] | None) -> str:
    if not metadata:
        return ""
    parts: list[str] = []
    for key in SOURCE_KEY_CANDIDATES:
        value = metadata.get(key)
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _normalized_subtype(subtype: str) -> str:
    return str(subtype or "").strip().lower()


def _effective_article_severity(*, subtype: str, scope: str, severity: str) -> str:
    normalized_subtype = _normalized_subtype(subtype)
    if scope != "article" or severity != "hard_stop":
        return severity
    if normalized_subtype in STRICT_SUBTYPES:
        return severity
    if normalized_subtype in LENIENT_SUBTYPES:
        return "review"
    return "review"


def _apply_subtype_severity(
    findings: Sequence[ConsistencyFinding],
    *,
    subtype: str,
) -> tuple[ConsistencyFinding, ...]:
    adjusted: list[ConsistencyFinding] = []
    for finding in findings:
        effective_severity = _effective_article_severity(
            subtype=subtype,
            scope=finding.scope,
            severity=finding.severity,
        )
        if effective_severity == finding.severity:
            adjusted.append(finding)
            continue
        adjusted.append(
            ConsistencyFinding(
                flag=finding.flag,
                severity=effective_severity,
                axis=finding.axis,
                scope=finding.scope,
                detail=finding.detail,
                context=dict(finding.context),
            )
        )
    return tuple(adjusted)


def _choose_unique_score(tokens: Sequence[ScoreToken]) -> tuple[ScoreToken | None, bool]:
    if not tokens:
        return None, False
    unique_pairs = {token.pair for token in tokens}
    if len(unique_pairs) != 1:
        return None, True
    explicit = [token for token in tokens if token.giants_side]
    return (explicit[0] if explicit else tokens[0]), False


def _choose_unique_date(tokens: Sequence[DateToken], publish_time_iso: str) -> tuple[str | None, bool]:
    if not tokens:
        return None, False
    resolved = [token.resolve(publish_time_iso) for token in tokens]
    values = {value for value in resolved if value}
    if len(values) == 1:
        return next(iter(values)), False
    if len(values) > 1:
        return None, True
    return None, False


def _append_finding(
    findings: list[ConsistencyFinding],
    *,
    flag: str,
    severity: str,
    axis: str,
    scope: str,
    detail: str,
    **context: Any,
) -> None:
    findings.append(
        ConsistencyFinding(
            flag=flag,
            severity=severity,
            axis=axis,
            scope=scope,
            detail=detail,
            context={key: value for key, value in context.items() if value is not None and value != ""},
        )
    )


def _check_article_score_consistency(
    findings: list[ConsistencyFinding],
    *,
    source_text: str,
    generated_body: str,
) -> tuple[ScoreToken | None, ScoreToken | None]:
    source_tokens = extract_scores(source_text)
    generated_tokens = extract_scores(generated_body)
    source_score, source_ambiguous = _choose_unique_score(source_tokens)
    generated_score, generated_ambiguous = _choose_unique_score(generated_tokens)

    if source_ambiguous:
        _append_finding(
            findings,
            flag="score_order_mismatch_review",
            severity="review",
            axis="score",
            scope="article",
            detail="source_score_ambiguous",
            source_scores=[token.pair for token in source_tokens],
        )
        return source_score, generated_score
    if generated_ambiguous:
        _append_finding(
            findings,
            flag="score_order_mismatch_review",
            severity="review",
            axis="score",
            scope="article",
            detail="generated_score_ambiguous",
            generated_scores=[token.pair for token in generated_tokens],
        )
        return source_score, generated_score
    if source_score and generated_score and source_score.pair != generated_score.pair:
        if generated_score.pair == source_score.reversed_pair and (source_score.giants_side or generated_score.giants_side):
            flag = "score_order_mismatch"
            detail = "score_order_reversed"
        else:
            flag = "numeric_fact_mismatch"
            detail = "score_value_mismatch"
        _append_finding(
            findings,
            flag=flag,
            severity="hard_stop",
            axis="score",
            scope="article",
            detail=detail,
            source_score=source_score.pair,
            generated_score=generated_score.pair,
        )
    return source_score, generated_score


def _check_article_win_loss_consistency(
    findings: list[ConsistencyFinding],
    *,
    source_text: str,
    generated_body: str,
    source_score: ScoreToken | None,
    generated_score: ScoreToken | None,
) -> None:
    source_markers = extract_win_loss_markers(source_text)
    generated_markers = extract_win_loss_markers(generated_body)
    source_result = source_score.giants_result if source_score else None
    generated_result = generated_score.giants_result if generated_score else None

    if source_result and source_markers["orientation"] and source_markers["orientation"] != source_result:
        _append_finding(
            findings,
            flag="win_loss_score_conflict_review",
            severity="review",
            axis="win_loss",
            scope="article",
            detail="source_win_loss_conflict",
            source_score=source_score.pair,
            source_markers=source_markers["orientation"],
        )

    body_orientation = generated_markers["orientation"]
    expected_orientation = generated_result or source_result
    if body_orientation and expected_orientation and body_orientation != expected_orientation:
        _append_finding(
            findings,
            flag="win_loss_score_conflict",
            severity="hard_stop",
            axis="win_loss",
            scope="article",
            detail="generated_win_loss_conflict",
            source_score=source_score.pair if source_score else None,
            generated_score=generated_score.pair if generated_score else None,
            generated_markers=body_orientation,
        )


def _check_article_pitcher_team_confusion(
    findings: list[ConsistencyFinding],
    *,
    source_text: str,
    generated_body: str,
) -> None:
    source_stats = extract_pitcher_team_stats(source_text)
    generated_stats = extract_pitcher_team_stats(generated_body)
    source_pitchers_by_fact: dict[tuple[str, int, int | None], list[dict[str, Any]]] = {}
    generated_pitchers_by_fact: dict[tuple[str, int, int | None], list[dict[str, Any]]] = {}
    for item in source_stats["pitchers"]:
        source_pitchers_by_fact.setdefault((item["name"], item["hits"], item.get("runs")), []).append(item)
    for item in generated_stats["pitchers"]:
        generated_pitchers_by_fact.setdefault((item["name"], item["hits"], item.get("runs")), []).append(item)
    source_pitcher_pairs = {
        (item["hits"], item["runs"])
        for item in source_stats["pitchers"]
        if item.get("runs") is not None
    }
    source_pitcher_hits = {item["hits"] for item in source_stats["pitchers"]}
    source_team_pairs = {
        (item["hits"], item["runs"])
        for item in source_stats["teams"]
        if item.get("runs") is not None
    }
    source_team_hits = {item["hits"] for item in source_stats["teams"]}

    for item in generated_stats["pitchers"]:
        if item["hits"] in source_team_hits and item["hits"] not in source_pitcher_hits:
            _append_finding(
                findings,
                flag="pitcher_team_stat_confusion",
                severity="hard_stop",
                axis="pitcher_team_stats",
                scope="article",
                detail="team_hits_written_as_pitcher_hits",
                source_team_hits=sorted(source_team_hits),
                generated_pitcher=item["raw"],
            )
            return

    for item in generated_stats["teams"]:
        pair = (item["hits"], item.get("runs"))
        if pair[1] is not None and pair in source_pitcher_pairs and pair not in source_team_pairs:
            _append_finding(
                findings,
                flag="pitcher_team_stat_confusion",
                severity="hard_stop",
                axis="pitcher_team_stats",
                scope="article",
                detail="pitcher_line_written_as_team_line",
                source_pitcher_pairs=sorted(source_pitcher_pairs),
                generated_team=item["raw"],
            )
            return
        if item["hits"] in source_pitcher_hits and item["hits"] not in source_team_hits:
            _append_finding(
                findings,
                flag="pitcher_team_stat_confusion",
                severity="hard_stop",
                axis="pitcher_team_stats",
                scope="article",
                detail="pitcher_hits_written_as_team_hits",
                source_pitcher_hits=sorted(source_pitcher_hits),
                generated_team=item["raw"],
            )
            return

    for fact_key, generated_pitchers in generated_pitchers_by_fact.items():
        source_pitchers = source_pitchers_by_fact.get(fact_key)
        if not source_pitchers or len(source_pitchers) != 1 or len(generated_pitchers) != 1:
            continue
        source_pitcher = source_pitchers[0]
        generated_pitcher = generated_pitchers[0]
        source_normalized = source_pitcher.get("innings_normalized")
        generated_normalized = generated_pitcher.get("innings_normalized")
        if source_normalized is not None and generated_normalized is not None:
            if source_normalized != generated_normalized:
                _append_finding(
                    findings,
                    flag="pitcher_team_stat_confusion",
                    severity="hard_stop",
                    axis="pitcher_team_stats",
                    scope="article",
                    detail="pitcher_innings_mismatch",
                    source_pitcher=source_pitcher["raw"],
                    generated_pitcher=generated_pitcher["raw"],
                    source_innings=source_normalized,
                    generated_innings=generated_normalized,
                )
                return
            continue
        source_fallback = source_pitcher.get("innings_raw")
        generated_fallback = generated_pitcher.get("innings_raw")
        if source_fallback is not None and generated_fallback is not None and source_fallback != generated_fallback:
            _append_finding(
                findings,
                flag="pitcher_team_stat_confusion",
                severity="hard_stop",
                axis="pitcher_team_stats",
                scope="article",
                detail="pitcher_innings_mismatch",
                source_pitcher=source_pitcher["raw"],
                generated_pitcher=generated_pitcher["raw"],
                source_innings=source_fallback,
                generated_innings=generated_fallback,
            )
            return


def _check_article_date_consistency(
    findings: list[ConsistencyFinding],
    *,
    source_text: str,
    generated_body: str,
    publish_time_iso: str,
) -> None:
    source_dates = extract_dates(source_text)
    generated_dates = extract_dates(generated_body)
    source_date, source_ambiguous = _choose_unique_date(source_dates, publish_time_iso)
    generated_date, generated_ambiguous = _choose_unique_date(generated_dates, publish_time_iso)

    if source_ambiguous:
        _append_finding(
            findings,
            flag="date_fact_mismatch_review",
            severity="review",
            axis="date",
            scope="article",
            detail="source_date_ambiguous",
            source_dates=[token.resolve(publish_time_iso) for token in source_dates],
        )
        return
    if generated_ambiguous:
        _append_finding(
            findings,
            flag="date_fact_mismatch_review",
            severity="review",
            axis="date",
            scope="article",
            detail="generated_date_ambiguous",
            generated_dates=[token.resolve(publish_time_iso) for token in generated_dates],
        )
        return
    if source_date and generated_date and source_date != generated_date:
        _append_finding(
            findings,
            flag="date_fact_mismatch",
            severity="hard_stop",
            axis="date",
            scope="article",
            detail="date_value_mismatch",
            source_date=source_date,
            generated_date=generated_date,
        )


def _trusted_player_names(source_text: str, generated_body: str, metadata: Mapping[str, Any] | None) -> set[str]:
    names = set(extract_player_names(source_text))
    names.update(extract_player_names(generated_body))
    if metadata:
        for key in ("player_names", "article_title", "source_summary", "summary"):
            value = metadata.get(key)
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    if _valid_player_name(str(item)):
                        names.add(_normalize_name(str(item)))
            else:
                names.update(extract_player_names(str(value or "")))
    return names


def _name_used_as_fact_subject(text: str, name: str) -> bool:
    normalized = _normalize_text(text)
    for match in re.finditer(re.escape(name), normalized):
        window = normalized[match.end() : min(len(normalized), match.end() + 24)]
        if PLAYER_FACT_TAIL_RE.search(window):
            return True
    return False


def _candidate_numeric_baseline(source_text: str, generated_body: str) -> tuple[ScoreToken | None, str | None]:
    source_score, source_ambiguous = _choose_unique_score(extract_scores(source_text))
    if source_score is not None or source_ambiguous:
        return source_score, "source"
    generated_score, _ = _choose_unique_score(extract_scores(generated_body))
    if generated_score is not None:
        return generated_score, "generated"
    return None, None


def _candidate_date_baseline(source_text: str, generated_body: str, publish_time_iso: str) -> tuple[str | None, str | None]:
    source_date, source_ambiguous = _choose_unique_date(extract_dates(source_text), publish_time_iso)
    if source_date is not None or source_ambiguous:
        return source_date, "source"
    generated_date, _ = _choose_unique_date(extract_dates(generated_body), publish_time_iso)
    if generated_date is not None:
        return generated_date, "generated"
    return None, None


def _check_x_candidate_consistency(
    findings: list[ConsistencyFinding],
    *,
    source_text: str,
    generated_body: str,
    x_candidates: Sequence[str],
    metadata: Mapping[str, Any] | None,
    publish_time_iso: str,
) -> None:
    baseline_score, score_origin = _candidate_numeric_baseline(source_text, generated_body)
    baseline_date, date_origin = _candidate_date_baseline(source_text, generated_body, publish_time_iso)
    trusted_names = _trusted_player_names(source_text, generated_body, metadata)

    for index, candidate in enumerate(x_candidates):
        candidate_score, candidate_score_ambiguous = _choose_unique_score(extract_scores(candidate))
        if baseline_score and candidate_score and baseline_score.pair != candidate_score.pair:
            _append_finding(
                findings,
                flag="x_post_numeric_mismatch",
                severity="x_candidate_suppress",
                axis="score",
                scope="x_candidate",
                detail="candidate_score_mismatch",
                candidate_index=index,
                source_score=baseline_score.pair,
                candidate_score=candidate_score.pair,
                baseline_origin=score_origin,
            )
            continue
        if candidate_score_ambiguous:
            _append_finding(
                findings,
                flag="x_post_numeric_mismatch",
                severity="x_candidate_suppress",
                axis="score",
                scope="x_candidate",
                detail="candidate_score_ambiguous",
                candidate_index=index,
            )
            continue

        candidate_markers = extract_win_loss_markers(candidate)
        expected_result = candidate_score.giants_result if candidate_score else baseline_score.giants_result if baseline_score else None
        if candidate_markers["orientation"] and expected_result and candidate_markers["orientation"] != expected_result:
            _append_finding(
                findings,
                flag="x_post_numeric_mismatch",
                severity="x_candidate_suppress",
                axis="win_loss",
                scope="x_candidate",
                detail="candidate_win_loss_conflict",
                candidate_index=index,
                expected_result=expected_result,
                candidate_markers=candidate_markers["orientation"],
            )
            continue

        candidate_dates = extract_dates(candidate)
        candidate_date, candidate_date_ambiguous = _choose_unique_date(candidate_dates, publish_time_iso)
        if baseline_date and candidate_date and baseline_date != candidate_date:
            _append_finding(
                findings,
                flag="x_post_numeric_mismatch",
                severity="x_candidate_suppress",
                axis="date",
                scope="x_candidate",
                detail="candidate_date_mismatch",
                candidate_index=index,
                source_date=baseline_date,
                candidate_date=candidate_date,
                baseline_origin=date_origin,
            )
            continue
        if candidate_date_ambiguous and baseline_date:
            _append_finding(
                findings,
                flag="x_post_numeric_mismatch",
                severity="x_candidate_suppress",
                axis="date",
                scope="x_candidate",
                detail="candidate_date_ambiguous",
                candidate_index=index,
            )
            continue

        unverified_names = sorted(
            name for name in extract_player_names(candidate) if name not in trusted_names and _name_used_as_fact_subject(candidate, name)
        )
        if unverified_names:
            _append_finding(
                findings,
                flag="x_post_unverified_player_name",
                severity="x_candidate_suppress",
                axis="player_name",
                scope="x_candidate",
                detail="candidate_player_name_unverified",
                candidate_index=index,
                unverified_names=unverified_names,
            )


def check_consistency(
    source_text: str,
    generated_body: str,
    x_candidates: Sequence[str],
    metadata: Mapping[str, Any] | None,
    publish_time_iso: str,
    subtype: str = "",
) -> ConsistencyReport:
    normalized_source = "\n".join(part for part in (str(source_text or ""), _source_metadata_text(metadata)) if part)
    normalized_body = str(generated_body or "")
    findings: list[ConsistencyFinding] = []

    source_score, generated_score = _check_article_score_consistency(
        findings,
        source_text=normalized_source,
        generated_body=normalized_body,
    )
    _check_article_win_loss_consistency(
        findings,
        source_text=normalized_source,
        generated_body=normalized_body,
        source_score=source_score,
        generated_score=generated_score,
    )
    _check_article_pitcher_team_confusion(
        findings,
        source_text=normalized_source,
        generated_body=normalized_body,
    )
    _check_article_date_consistency(
        findings,
        source_text=normalized_source,
        generated_body=normalized_body,
        publish_time_iso=publish_time_iso,
    )
    _check_x_candidate_consistency(
        findings,
        source_text=normalized_source,
        generated_body=normalized_body,
        x_candidates=tuple(str(item or "") for item in x_candidates if str(item or "").strip()),
        metadata=metadata,
        publish_time_iso=publish_time_iso,
    )
    effective_findings = _apply_subtype_severity(findings, subtype=subtype)

    hard_stop_flags = _dedupe(finding.flag for finding in effective_findings if finding.severity == "hard_stop")
    review_flags = _dedupe(finding.flag for finding in effective_findings if finding.severity == "review")
    x_candidate_suppress_flags = _dedupe(
        finding.flag for finding in effective_findings if finding.severity == "x_candidate_suppress"
    )
    severity = "pass"
    if hard_stop_flags:
        severity = "hard_stop"
    elif review_flags:
        severity = "review"
    elif x_candidate_suppress_flags:
        severity = "x_candidate_suppress"
    return ConsistencyReport(
        severity=severity,
        findings=effective_findings,
        hard_stop_flags=hard_stop_flags,
        review_flags=review_flags,
        x_candidate_suppress_flags=x_candidate_suppress_flags,
    )
