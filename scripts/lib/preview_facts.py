from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any


JSONDict = dict[str, Any]

ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    flags=re.IGNORECASE | re.DOTALL,
)
URL_RE = re.compile(r"^https?://")
HEADING_RE = re.compile(r"^(?:【.+】|[📌📊👀💬].+)$")
PERSON_TOKEN_RE = re.compile(r"[一-龯々]{2,4}[ぁ-んァ-ヶー一-龯]{0,2}")
STOP_NAME_TOKENS = {
    "巨人",
    "読売",
    "一軍",
    "二軍",
    "試合",
    "本日",
    "今日",
    "先発",
    "選手",
    "投手",
    "監督",
    "主将",
    "報知新聞",
    "スポーツ報知",
    "巨人公式",
    "話題",
    "要旨",
    "文脈",
    "背景",
    "関心",
    "ポイント",
}
TEAM_PATTERN = r"(DeNA|中日|ヤクルト|阪神|広島|楽天|ロッテ|日本ハム|ソフトバンク|西武|オリックス)"
SUBTYPE_MAP = {
    "GIANTS GAME NOTE": "postgame",
    "GIANTS FARM WATCH": "farm_result",
    "GIANTS MANAGER NOTE": "manager",
}


def load_jsonl_index(path: str | Path, key: str = "post_id") -> dict[int, JSONDict]:
    index: dict[int, JSONDict] = {}
    for raw_line in Path(path).read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if key not in entry:
            continue
        index[int(entry[key])] = entry
    return index


def load_backup(path: str | Path) -> JSONDict:
    return json.loads(Path(path).read_text())


def normalize_html_to_lines(rendered_html: str) -> list[str]:
    text = ANCHOR_RE.sub(_anchor_to_text, rendered_html)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</span>", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</(?:p|div|h1|h2|h3|h4|h5|h6|li|figure|ul|ol|blockquote|hr)>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ").replace("\r", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    filtered: list[str] = []
    for line in lines:
        if not line or line == "#respond":
            continue
        if filtered and filtered[-1] == line:
            continue
        filtered.append(line)
    return filtered


def normalize_html(rendered_html: str) -> str:
    return "\n".join(normalize_html_to_lines(rendered_html))


def extract_preview_facts(history_entry: JSONDict, backup_doc: JSONDict) -> JSONDict:
    rendered_html = _safe_get_rendered(backup_doc, "content")
    lines = normalize_html_to_lines(rendered_html)

    banner_line = lines[0] if lines else ""
    source_label, subtype_label = _parse_banner(banner_line)
    subtype_hint = SUBTYPE_MAP.get(subtype_label or "", None)
    source_lines = _extract_source_lines(lines)
    source_urls = _extract_source_urls(lines)
    source_cue = source_lines[-1] if source_lines else None
    source_cue_clean = _cleanup_source_sentence(source_cue) if source_cue else None
    score = _extract_score(source_lines)
    opponent = _extract_opponent(source_lines, score)
    result = _extract_result(source_lines, score)
    pitching_line = _extract_pitching_line(source_lines)
    speaker_name = _extract_speaker_name(source_lines)
    player_name = _extract_player_name(source_lines, speaker_name)
    key_quote = _extract_key_quote(source_lines)

    facts: JSONDict = {
        "post_id": backup_doc.get("id") or history_entry.get("post_id"),
        "backup_path": history_entry.get("backup_path"),
        "history_ts": history_entry.get("ts"),
        "history_status": history_entry.get("status"),
        "history_judgment": history_entry.get("judgment"),
        "title_rendered": _safe_get_rendered(backup_doc, "title"),
        "modified": backup_doc.get("modified"),
        "fetched_at": backup_doc.get("fetched_at"),
        "source_label": source_label,
        "source_url": source_urls[0] if source_urls else None,
        "source_urls": source_urls,
        "source_headline": source_lines[0] if source_lines else None,
        "source_cue": source_cue_clean,
        "score": score,
        "opponent": opponent,
        "result": result,
        "player_name": player_name,
        "speaker_name": speaker_name,
        "pitching_line": pitching_line,
        "subtype_hint": subtype_hint,
        "subtype_banner": subtype_label,
        "key_quote": key_quote,
        "supporting_sentences": _extract_supporting_sentences(source_cue_clean),
    }
    facts["coverable_facts"] = _build_coverable_facts(facts)
    return facts


def _safe_get_rendered(doc: JSONDict, field: str) -> str:
    value = doc.get(field)
    if isinstance(value, dict):
        return str(value.get("rendered") or "")
    return str(value or "")


def _anchor_to_text(match: re.Match[str]) -> str:
    href = match.group(1).strip()
    inner = re.sub(r"<[^>]+>", "", match.group(2))
    inner = html.unescape(inner)
    inner = re.sub(r"\s+", " ", inner).strip()
    if inner and inner != href:
        return f"{inner}\n{href}"
    return href


def _parse_banner(line: str) -> tuple[str | None, str | None]:
    match = re.match(r"^📰\s*(.+?)\s*⚾\s*(.+)$", line)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, None


def _extract_source_lines(lines: list[str]) -> list[str]:
    collected: list[str] = []
    for line in lines[1:]:
        if line.startswith("📌 関連ポスト"):
            break
        if line.startswith("📰 参照元:"):
            break
        collected.append(line)
    return collected


def _extract_source_urls(lines: list[str]) -> list[str]:
    urls: list[str] = []
    in_related = False
    for line in lines:
        if line.startswith("📌 関連ポスト"):
            in_related = True
            continue
        if in_related and HEADING_RE.match(line):
            break
        if in_related and URL_RE.match(line):
            urls.append(line)
    return urls


def _extract_score(source_lines: list[str]) -> str | None:
    text = " ".join(source_lines)
    match = re.search(rf"巨人\s+([0-9]+-[0-9]+)x?\s*{TEAM_PATTERN}", text)
    if match:
        return match.group(1)
    match = re.search(r"\b([0-9]+-[0-9]+)\b", text)
    if match:
        return match.group(1)
    return None


def _extract_opponent(source_lines: list[str], score: str | None) -> str | None:
    text = " ".join(source_lines)
    if score:
        match = re.search(
            rf"巨人\s+{re.escape(score)}x?\s*{TEAM_PATTERN}",
            text,
        )
        if match:
            return match.group(1)
    match = re.search(rf"(?:巨人|ジャイアンツ)[^\n]*?{TEAM_PATTERN}", text)
    if match:
        return match.group(1)
    return None


def _extract_result(source_lines: list[str], score: str | None) -> str | None:
    text = " ".join(source_lines)
    if "勝利" in text:
        return "勝利"
    if "敗戦" in text or "サヨナラ負け" in text or "負け" in text:
        return "敗戦"
    if score and "x" in text:
        return None
    return None


def _extract_pitching_line(source_lines: list[str]) -> str | None:
    text = " ".join(source_lines)
    match = re.search(
        r"([0-9一二三四五六七八九十]+回(?:途中)?(?:[0-9一二三四五六七八九十]+安打)?(?:無失点|[0-9一二三四五六七八九十]+失点))",
        text,
    )
    if match:
        return match.group(1)
    return None


def _extract_key_quote(source_lines: list[str]) -> str | None:
    text = " ".join(source_lines)
    match = re.search(r"「([^」]+)」", text)
    if match:
        return match.group(1)
    return None


def _extract_speaker_name(source_lines: list[str]) -> str | None:
    text = " ".join(source_lines)
    match = re.search(r"([一-龯々]{2,4})監督", text)
    if match:
        return f"{match.group(1)}監督"
    return None


def _extract_player_name(source_lines: list[str], speaker_name: str | None) -> str | None:
    text = " ".join(source_lines)
    patterns = (
        r"主将[・･]([一-龯々]{2,4}[ぁ-んァ-ヶー一-龯]{0,2})",
        r"([一-龯々]{2,4}[ぁ-んァ-ヶー一-龯]{0,2})に「",
        r"([一-龯々]{2,4}[ぁ-んァ-ヶー一-龯]{0,2})が",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = match.group(1)
            candidate = re.sub(r"[にがをはへと]$", "", candidate)
            if candidate in STOP_NAME_TOKENS:
                continue
            if speaker_name and candidate in speaker_name:
                continue
            return candidate
    return None


def _extract_supporting_sentences(source_cue: str | None) -> list[str]:
    if not source_cue:
        return []
    cleaned = source_cue
    cleaned = re.sub(r"^【[^】]+】", "", cleaned).strip()
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=。)", cleaned)
        if sentence.strip()
    ]
    return [_ensure_sentence_period(sentence) for sentence in sentences]


def _cleanup_source_sentence(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"^【[^】]+】", "", cleaned).strip()
    cleaned = re.sub(rf"巨人\s+[0-9]+-[0-9]+x?\s*{TEAM_PATTERN}", "", cleaned).strip()
    cleaned = re.sub(r"先発の\s*投手は", "先発は", cleaned)
    cleaned = re.sub(r"先発\s*投手は", "先発は", cleaned)
    cleaned = re.sub(r"^の\s*投手は", "先発は", cleaned)
    cleaned = re.sub(r"^投手は", "先発は", cleaned)
    cleaned = re.sub(r"に\s*選手の", "に", cleaned)
    cleaned = re.sub(r"に\s*選手が", "に", cleaned)
    cleaned = re.sub(r"は\s*選手が", "は", cleaned)
    cleaned = re.sub(r"放った\s*選手(?:㊗️)?", "放った", cleaned)
    cleaned = re.sub(r"\s*選手㊗️", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _build_coverable_facts(facts: JSONDict) -> list[dict[str, str]]:
    coverable: list[dict[str, str]] = []
    for field in (
        "score",
        "opponent",
        "result",
        "player_name",
        "speaker_name",
        "pitching_line",
        "key_quote",
    ):
        value = facts.get(field)
        if value:
            coverable.append({"field": field, "value": str(value)})
    return coverable


def _ensure_sentence_period(text: str) -> str:
    if text.endswith(("。", "！", "？")):
        return text
    return f"{text}。"
