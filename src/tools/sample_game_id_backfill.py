"""Dry-run sampler for deriving game_id from recent draft posts."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from wp_client import WPClient

JST = timezone(timedelta(hours=9))
DEFAULT_OUTPUT = Path("/tmp/game_id_backfill_2026-04-21.md")
MATCH_BOUND_SUBTYPES = {"pregame", "lineup", "live_update", "live_anchor", "postgame", "farm", "farm_lineup"}
SOURCE_URL_KEYS = ("source_urls", "_yoshilover_source_url", "yl_source_url", "source_url")
TEAM_ALIASES = {
    "giants": ("巨人", "ジャイアンツ", "読売", "yomiuri", "giants"),
    "tigers": ("阪神", "タイガース", "hanshin", "tigers"),
    "dragons": ("中日", "ドラゴンズ", "chunichi", "dragons"),
    "swallows": ("ヤクルト", "スワローズ", "tokyo yakult", "swallows"),
    "baystars": ("dena", "de na", "de-na", "ベイスターズ", "横浜", "baystars"),
    "carp": ("広島", "カープ", "hiroshima", "carp"),
    "buffaloes": ("オリックス", "バファローズ", "orix", "buffaloes"),
    "marines": ("ロッテ", "マリーンズ", "chiba lotte", "marines"),
    "hawks": ("ソフトバンク", "ホークス", "fukuoka softbank", "hawks"),
    "eagles": ("楽天", "イーグルス", "tohoku rakuten", "eagles"),
    "fighters": ("日本ハム", "日ハム", "ファイターズ", "nippon-ham", "fighters"),
    "lions": ("西武", "ライオンズ", "seibu", "lions"),
}
VENUE_HOME_TEAM = {
    "東京ドーム": "giants",
    "甲子園": "tigers",
    "バンテリン": "dragons",
    "神宮": "swallows",
    "横浜スタジアム": "baystars",
    "マツダ": "carp",
    "京セラドーム": "buffaloes",
    "ほっともっと": "buffaloes",
    "zozoマリン": "marines",
    "paypayドーム": "hawks",
    "楽天モバイル": "eagles",
    "エスコン": "fighters",
    "ベルーナ": "lions",
    "ジャイアンツ球場": "giants",
}
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
URL_RE = re.compile(r"https?://[^\s<>'\"]+")
YAHOO_GAME_RE = re.compile(r"/npb/game/(\d+)/(?:top|score|index)")
OFFICIAL_GAME_RE = re.compile(r"/game/(\d{8})/([^/?#]+)/?")
DATE_JP_RE = re.compile(r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})日")
DOUBLEHEADER_1_RE = re.compile(r"(?:第\s*1\s*試合|第一試合|game\s*1|dh\s*1)", re.I)
DOUBLEHEADER_2_RE = re.compile(r"(?:第\s*2\s*試合|第二試合|game\s*2|dh\s*2)", re.I)


def _clean_text(value: str) -> str:
    text = TAG_RE.sub(" ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def normalize_team_code(value: str) -> str | None:
    normalized = re.sub(r"[\s　]+", "", html.unescape(value or "")).lower()
    normalized = normalized.replace("ｄｅｎａ", "dena")
    for team_code, aliases in TEAM_ALIASES.items():
        for alias in aliases:
            alias_key = re.sub(r"[\s　]+", "", alias).lower()
            if alias_key and alias_key in normalized:
                return team_code
    return None


def infer_subtype(post: dict) -> str:
    meta = post.get("meta") or {}
    subtype = str(meta.get("article_subtype") or "").strip().lower()
    if subtype:
        return subtype
    text = _clean_text(f"{_title_text(post)} {_body_text(post)}")
    has_farm = any(marker in text for marker in ("2軍", "二軍", "ファーム"))
    has_lineup = "スタメン" in text or "lineup" in text.lower()
    if has_farm and has_lineup:
        return "farm_lineup"
    if any(marker in text for marker in ("勝利", "敗戦", "引き分け", "試合終了")):
        return "postgame"
    if re.search(r"\d+回[表裏]?|\d+-\d+|同点|勝ち越し", text):
        return "live_update"
    if has_lineup:
        return "lineup"
    if has_farm:
        return "farm"
    if any(marker in text for marker in ("予告先発", "見どころ", "プレーボール")):
        return "pregame"
    return "general"


def detect_doubleheader_suffix(*parts: str) -> str:
    text = " ".join(_clean_text(part) for part in parts if part)
    if DOUBLEHEADER_1_RE.search(text):
        return "1"
    if DOUBLEHEADER_2_RE.search(text):
        return "2"
    return ""


def source_id_from_url(url: str) -> str:
    parsed = urlparse(_normalize_url(url))
    host = parsed.netloc.lower()
    if host.endswith(("x.com", "twitter.com")):
        match = re.search(r"/status/(\d+)", parsed.path)
        return f"x:{match.group(1)}" if match else f"x:{parsed.geturl()}"
    yahoo_match = YAHOO_GAME_RE.search(parsed.path)
    if yahoo_match:
        page = parsed.path.rstrip("/").split("/")[-1].lower()
        return f"npb:{yahoo_match.group(1)}:{page}"
    official_match = OFFICIAL_GAME_RE.search(parsed.path)
    if host.endswith("giants.jp") and official_match:
        return f"official:giants:{official_match.group(1)}:{official_match.group(2).lower()}"
    return f"rss:{parsed.geturl()}"


def derive_game_id_for_post(post: dict) -> dict[str, object]:
    subtype = infer_subtype(post)
    source_urls = _extract_source_urls(post)
    title = _title_text(post)
    body = _body_text(post)
    if subtype not in MATCH_BOUND_SUBTYPES:
        return _row(post, subtype, None, "subtype_not_match_bound", source_urls)
    game_date = _resolve_game_date(post, title, body, source_urls)
    if not game_date:
        return _row(post, subtype, None, "date_not_found", source_urls)
    teams = _resolve_teams(title, body, source_urls)
    if len(teams) != 2:
        return _row(post, subtype, None, "opponent_not_found", source_urls)
    home_team = _resolve_home_team(title, body, source_urls, teams)
    if not home_team:
        return _row(post, subtype, None, "home_away_ambiguous", source_urls)
    away_team = next(team for team in teams if team != home_team)
    suffix = detect_doubleheader_suffix(title, body, *source_urls)
    game_id = f"{game_date}-{home_team}-{away_team}" + (f"-{suffix}" if suffix else "")
    return _row(post, subtype, game_id, None, source_urls)


def load_recent_drafts(max_posts: int, wp: WPClient | None = None) -> list[dict]:
    client = wp or WPClient()
    return client.list_posts(
        status="draft",
        per_page=max_posts,
        page=1,
        orderby="modified",
        order="desc",
        context="edit",
        fields=["id", "modified", "modified_gmt", "date", "date_gmt", "status", "title", "content", "meta"],
    )


def render_report(rows: list[dict], max_posts: int) -> str:
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_posts": max_posts,
        "scanned_posts": len(rows),
        "derived_count": sum(1 for row in rows if row["derived_game_id"]),
        "null_count": sum(1 for row in rows if not row["derived_game_id"]),
        "reason_counts": _count_by_key(rows, "reason_if_null"),
        "subtype_counts": _count_by_key(rows, "subtype"),
        "source_id_examples": [source_id_from_url(url) for row in rows for url in row["source_urls_found"][:1]][:10],
    }
    lines = ["# game_id backfill dry-run", "", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", ""]
    lines.append("| post_id | subtype | title | derived_game_id | reason_if_null | source_urls_found |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        title = str(row["title"]).replace("|", "/")
        sources = "<br>".join(row["source_urls_found"]) if row["source_urls_found"] else "-"
        lines.append(
            f"| {row['post_id']} | {row['subtype']} | {title} | "
            f"{row['derived_game_id'] or '-'} | {row['reason_if_null'] or '-'} | {sources} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample game_id backfill without WP writes")
    parser.add_argument("--max-posts", type=int, default=30, help="Number of recent drafts to inspect")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown report output path")
    args = parser.parse_args(argv)
    try:
        rows = [derive_game_id_for_post(post) for post in load_recent_drafts(args.max_posts)]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report = render_report(rows, args.max_posts)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


def _title_text(post: dict) -> str:
    title = post.get("title") or {}
    return str(title.get("raw") or title.get("rendered") or "")


def _body_text(post: dict) -> str:
    content = post.get("content") or {}
    return str(content.get("raw") or content.get("rendered") or "")


def _extract_source_urls(post: dict) -> list[str]:
    meta = post.get("meta") or {}
    body = _body_text(post)
    urls: list[str] = []
    for key in SOURCE_URL_KEYS:
        value = meta.get(key)
        if isinstance(value, list):
            urls.extend(str(item) for item in value if item)
        elif value:
            urls.append(str(value))
    urls.extend(HREF_RE.findall(body))
    urls.extend(URL_RE.findall(body))
    return _dedupe(_normalize_url(url) for url in urls if str(url).strip())


def _normalize_url(url: str) -> str:
    parsed = urlparse(html.unescape(str(url)).strip())
    query = "&".join(f"{k}={v}" if v else k for k, v in sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def _resolve_game_date(post: dict, title: str, body: str, source_urls: list[str]) -> str:
    for url in source_urls:
        if match := YAHOO_GAME_RE.search(url):
            return match.group(1)[:8]
        if match := OFFICIAL_GAME_RE.search(urlparse(url).path):
            return match.group(1)
        if match := re.search(r"(20\d{2})(\d{2})(\d{2})", url):
            return "".join(match.groups())
    modified = _modified_jst(post)
    reference_year = modified.year if modified else datetime.now(JST).year
    for text in (title, body):
        if match := DATE_JP_RE.search(_clean_text(text)):
            year = int(match.group(1) or reference_year)
            return f"{year:04d}{int(match.group(2)):02d}{int(match.group(3)):02d}"
    return modified.strftime("%Y%m%d") if modified else ""


def _resolve_teams(title: str, body: str, source_urls: list[str]) -> list[str]:
    teams = {team for part in (title, body, " ".join(source_urls)) for team in [normalize_team_code(part)] if team}
    clean_text = _clean_text(f"{title} {body}").lower()
    for team_code, aliases in TEAM_ALIASES.items():
        if any(alias.lower() in clean_text for alias in aliases):
            teams.add(team_code)
    non_giants = {team for team in teams if team != "giants"}
    if len(teams) == 1 and non_giants:
        teams.add("giants")
    if "giants.jp" in " ".join(source_urls).lower() and len(non_giants) == 1:
        teams.add("giants")
    return sorted(teams)


def _resolve_home_team(title: str, body: str, source_urls: list[str], teams: list[str]) -> str | None:
    text = _clean_text(f"{title} {body} {' '.join(source_urls)}").lower()
    for venue, team_code in VENUE_HOME_TEAM.items():
        if venue.lower() in text and team_code in teams:
            return team_code
    if "ホーム" in text:
        for team in teams:
            if any(alias.lower() in text for alias in TEAM_ALIASES[team]):
                return team
    return None


def _modified_jst(post: dict) -> datetime | None:
    for field, assume_utc in (("modified_gmt", True), ("date_gmt", True), ("modified", False), ("date", False)):
        raw = str(post.get(field) or "").strip()
        if not raw:
            continue
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc if assume_utc else JST)
        return parsed.astimezone(JST)
    return None


def _row(post: dict, subtype: str, game_id: str | None, reason: str | None, source_urls: list[str]) -> dict[str, object]:
    return {
        "post_id": post.get("id"),
        "subtype": subtype,
        "title": _truncate(_title_text(post)),
        "derived_game_id": game_id,
        "reason_if_null": reason,
        "source_urls_found": source_urls,
    }


def _count_by_key(rows: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if not value:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _truncate(value: str, limit: int = 48) -> str:
    clean = _clean_text(value)
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _dedupe(items) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
