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
    "三軍",
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
TEAM_PATTERN = (
    r"(DeNA|中日|ヤクルト|阪神|広島|楽天|ロッテ|日本ハム|"
    r"ソフトバンク|西武|オリックス|福島レッドホープス)"
)
SUBTYPE_MAP = {
    "GIANTS GAME NOTE": "postgame",
    "GIANTS FARM WATCH": "farm_result",
    "GIANTS MANAGER NOTE": "manager",
    "GIANTS LINEUP NOTE": "lineup",
}
LINEUP_SECTION_HEADINGS = ("【スタメン一覧】", "【二軍スタメン一覧】")
OVERVIEW_SECTION_HEADINGS = ("【試合概要】", "【二軍試合概要】")
LINEUP_ENTRY_RE = re.compile(
    r"^([1-9])番\s+(.+?)\s+([左右中遊三二一捕投DH指ＤＨ]+)$"
)


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
    title_rendered = _safe_get_rendered(backup_doc, "title")
    lines = normalize_html_to_lines(rendered_html)
    sections = _split_sections(lines)

    banner_line = lines[0] if lines else ""
    source_label, subtype_label = _parse_banner(banner_line)
    source_lines = _extract_source_lines(lines)
    source_urls = _extract_source_urls(lines)
    subtype_hint = _infer_subtype(subtype_label, title_rendered, sections)
    source_cue = source_lines[-1] if source_lines else None
    source_cue_clean = _cleanup_source_sentence(source_cue) if source_cue else None
    score = _extract_score(source_lines)
    opponent = _extract_opponent(source_lines, sections, score)
    result = _extract_result(source_lines, score)
    pitching_line = _extract_pitching_line(source_lines)
    speaker_name = _extract_speaker_name(source_lines)
    player_name = _extract_player_name(source_lines, speaker_name)
    key_quote = _extract_key_quote(source_lines)
    lineup_order = _extract_lineup_order(sections)
    starter_pitcher = _extract_starter_pitcher(sections, lineup_order)
    venue = _extract_venue(sections, title_rendered, source_lines)
    game_date = _extract_game_date(title_rendered, sections)
    opponent_lineup_link = (
        _extract_opponent_lineup_link(source_urls) if subtype_hint == "lineup" else None
    )

    facts: JSONDict = {
        "post_id": backup_doc.get("id") or history_entry.get("post_id"),
        "backup_path": history_entry.get("backup_path"),
        "history_ts": history_entry.get("ts"),
        "history_status": history_entry.get("status"),
        "history_judgment": history_entry.get("judgment"),
        "title_rendered": title_rendered,
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
        "starter_pitcher": starter_pitcher,
        "subtype_hint": subtype_hint,
        "subtype_banner": subtype_label,
        "key_quote": key_quote,
        "venue": venue,
        "game_date": game_date,
        "opponent_lineup_link": opponent_lineup_link,
        "lineup_order": lineup_order,
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


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for line in lines[1:]:
        if HEADING_RE.match(line):
            current_heading = line
            sections.setdefault(current_heading, [])
            continue
        if current_heading is not None:
            sections[current_heading].append(line)
    return sections


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


def _infer_subtype(
    subtype_label: str | None,
    title_rendered: str,
    sections: dict[str, list[str]],
) -> str | None:
    if any(heading in sections for heading in LINEUP_SECTION_HEADINGS):
        return "lineup"
    if "スタメン" in title_rendered:
        return "lineup"
    return SUBTYPE_MAP.get(subtype_label or "", None)


def _extract_score(source_lines: list[str]) -> str | None:
    text = " ".join(source_lines)
    match = re.search(rf"巨人\s+([0-9]+-[0-9]+)x?\s*{TEAM_PATTERN}", text)
    if match:
        return match.group(1)
    match = re.search(r"\b([0-9]+-[0-9]+)\b", text)
    if match:
        return match.group(1)
    return None


def _extract_opponent(
    source_lines: list[str],
    sections: dict[str, list[str]],
    score: str | None,
) -> str | None:
    texts = [" ".join(source_lines)]
    texts.extend(_section_lines(sections, *OVERVIEW_SECTION_HEADINGS))
    text = " ".join(part for part in texts if part)
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
    if "引き分け" in text:
        return "引き分け"
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


def _extract_lineup_order(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    for heading in LINEUP_SECTION_HEADINGS:
        entries: list[dict[str, str]] = []
        for raw_line in sections.get(heading, []):
            line = raw_line.replace("　", " ").strip()
            match = LINEUP_ENTRY_RE.match(line)
            if not match:
                continue
            order = match.group(1)
            player = re.sub(r"\s+", " ", match.group(2)).strip()
            position = match.group(3).replace("ＤＨ", "DH")
            entries.append(
                {
                    "order": order,
                    "player": player,
                    "position": position,
                    "rendered": f"{order}番 {player} {position}",
                }
            )
        if entries:
            return entries
    return []


def _extract_starter_pitcher(
    sections: dict[str, list[str]],
    lineup_order: list[dict[str, str]],
) -> str | None:
    for entry in lineup_order:
        if entry.get("position") == "投":
            return entry.get("player")

    for line in sections.get("【先発投手】", []):
        cleaned = line.strip()
        if not cleaned:
            continue
        if "元記事で確認できる範囲" in cleaned or "source/meta" in cleaned:
            continue
        candidate = cleaned.removeprefix("-").strip()
        if candidate:
            return candidate
    return None


def _extract_venue(
    sections: dict[str, list[str]],
    title_rendered: str,
    source_lines: list[str],
) -> str | None:
    for line in _section_lines(sections, *OVERVIEW_SECTION_HEADINGS):
        match = re.search(r"球場は(.+?)です", line)
        if match:
            return match.group(1).strip()

    text = " ".join([title_rendered, *source_lines])
    match = re.search(r"([^\s【】]+(?:スタジアム|球場|ドーム))", text)
    if match:
        return match.group(1).strip()
    return None


def _extract_game_date(
    title_rendered: str,
    sections: dict[str, list[str]],
) -> str | None:
    text = " ".join([title_rendered, *sections.get("【試合概要】", [])])
    match = re.search(r"(\d{1,2}/\d{1,2})", text)
    if match:
        return match.group(1)
    match = re.search(r"(\d{1,2}月\d{1,2}日)", text)
    if match:
        return match.group(1)
    return None


def _extract_opponent_lineup_link(source_urls: list[str]) -> str | None:
    if len(source_urls) >= 2:
        return source_urls[1]
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
    cleaned = re.sub(r"(?<![一-龯ぁ-んァ-ヶー])選手(?=[^一-龯ぁ-んァ-ヶー]|$)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _build_coverable_facts(facts: JSONDict) -> list[dict[str, str]]:
    coverable: list[dict[str, str]] = []
    subtype_hint = facts.get("subtype_hint")
    if subtype_hint == "lineup":
        fields = ("opponent", "venue", "game_date", "starter_pitcher")
    elif subtype_hint == "manager":
        fields = ("speaker_name", "player_name", "key_quote")
    else:
        fields = (
            "score",
            "opponent",
            "result",
            "player_name",
            "speaker_name",
            "pitching_line",
            "key_quote",
        )

    for field in fields:
        value = facts.get(field)
        if value:
            coverable.append({"field": field, "value": str(value)})

    for entry in facts.get("lineup_order") or []:
        coverable.append({"field": "lineup_order", "value": str(entry["rendered"])})
    return coverable


def _section_lines(sections: dict[str, list[str]], *headings: str) -> list[str]:
    lines: list[str] = []
    for heading in headings:
        lines.extend(sections.get(heading, []))
    return lines


def _ensure_sentence_period(text: str) -> str:
    if text.endswith(("。", "！", "？")):
        return text
    return f"{text}。"
