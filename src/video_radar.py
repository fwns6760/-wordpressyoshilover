"""451: video-nostalgia-radar — 公式 / OB / メディアの YouTube RSS を read-only 巡回し、
「懐かしい・ファンが面白い」動画を X 投稿候補の素材として **拾う**。

重要な境界:
- 動画ファイルの転載・切り抜き再アップは **しない**。 出力は URL / 埋め込み紹介のみ。
- 「拾う(候補化)」と「転載」は別レイヤー。 チャンネルは全部スキャンしてよいが (user 2026-06-01)、
  status=excluded のものだけ除外する。
- Gemini / X API は使わない。 YouTube は公開 RSS (`feeds/videos.xml?channel_id=...`) を HTTP GET。

このモジュールは pure / network 注入可能で、 Candidate 生成は x_post_mail_lane 側が行う。
"""
from __future__ import annotations

import json as _json
import re as _re
from pathlib import Path as _Path
from typing import Callable, Optional
from urllib.request import Request as _Request, urlopen as _urlopen

from src.source_youtube_extractor import parse_youtube_atom

_CONFIG_DIR = _Path(__file__).resolve().parents[1] / "config"
_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

# 「懐かしい / 名場面」系シグナル
_NOSTALGIA_MARKERS = (
    "名場面", "名シーン", "名勝負", "名プレー", "名守備", "名言", "伝説", "レジェンド",
    "懐かし", "振り返り", "回顧", "あの日", "あの試合", "思い出", "秘話", "秘蔵", "お宝",
    "蔵出し", "アーカイブ", "球史", "当時", "現役時代", "全盛期",
)
# 「ファンが面白い / 反応する」系シグナル
_FUN_MARKERS = (
    "神", "規格外", "衝撃", "必見", "鳥肌", "劇的", "圧巻", "伝説の", "ヤバ", "エグ",
    "サヨナラ", "満塁", "逆転", "完全試合", "ノーヒットノーラン", "好プレー", "ファインプレー",
    "デビュー", "初", "号", "引退", "復活", "復帰",
)
# 二軍 marker
_FARM_MARKERS = ("二軍", "ファーム", "イースタン", "三軍")


def load_radar_channels(
    *,
    ob_path: Optional[_Path] = None,
    video_path: Optional[_Path] = None,
) -> list[dict]:
    """棚卸し済みチャンネルを全部返す (status=excluded / role=excluded のみ除外)。

    youtube_ob_sources.json (OB / メディア / 公式) + youtube_video_sources.json
    (公式 / 放送) をマージ。 channel_id 重複は ob 側を優先。
    """
    ob_path = ob_path or (_CONFIG_DIR / "youtube_ob_sources.json")
    video_path = video_path or (_CONFIG_DIR / "youtube_video_sources.json")
    out: dict[str, dict] = {}

    def _add(cid: str, name: str, role: str, status: str) -> None:
        cid = (cid or "").strip()
        if not cid:
            return
        if (status or "").strip().lower() == "excluded" or (role or "").strip().lower() == "excluded":
            return
        if cid not in out:
            out[cid] = {"channel_id": cid, "name": name or cid, "role": role or "", "status": status or ""}

    try:
        ob = _json.loads(ob_path.read_text(encoding="utf-8"))
        for s in ob.get("sources", []):
            _add(s.get("channel_id", ""), s.get("display_name", ""), s.get("role", ""), s.get("status", ""))
    except Exception:  # noqa: BLE001
        pass
    try:
        vid = _json.loads(video_path.read_text(encoding="utf-8"))
        rows = vid if isinstance(vid, list) else vid.get("sources", vid.get("channels", []))
        for s in (rows or []):
            url = str(s.get("url") or "")
            m = _re.search(r"channel_id=([A-Za-z0-9_-]+)", url)
            cid = m.group(1) if m else str(s.get("channel_id") or "")
            _add(cid, s.get("name", ""), s.get("role", "official_video_source"), s.get("status", "confirmed"))
    except Exception:  # noqa: BLE001
        pass
    return list(out.values())


def classify_video(
    title: str,
    *,
    role: str = "",
    player: str = "",
    today_players: Optional[set[str]] = None,
    today_opponent: str = "",
) -> tuple[int, str]:
    """動画 title からスコアと型タグを返す。 pure / 決定的 (LLM 不使用)。

    Returns ``(score, type_tag)``。 score>=2 を候補閾値の目安にする。
    """
    t = title or ""
    score = 0
    nostalgia = any(m in t for m in _NOSTALGIA_MARKERS)
    fun = any(m in t for m in _FUN_MARKERS)
    has_year = bool(_re.search(r"(19|20)\d{2}", t))
    is_farm = any(m in t for m in _FARM_MARKERS)
    is_ob_channel = (role or "") in ("giants_ob", "ob")

    if nostalgia:
        score += 2
    if fun:
        score += 1
    if has_year:
        score += 1
    if player:
        score += 2
    if is_ob_channel:
        score += 1  # OB 本人チャンネル = 懐かしネタ寄り
    # 今日の文脈ボーナス
    if player and today_players and player in today_players:
        score += 2
    if today_opponent and today_opponent in t:
        score += 1

    # 型タグ (優先順)
    if player and today_players and player in today_players:
        tag = "今日とつながる"
    elif is_ob_channel or (nostalgia and not is_farm):
        tag = "OB・懐かし" if is_ob_channel else "名場面回顧"
    elif is_farm:
        tag = "二軍ハイライト"
    elif has_year and player:
        tag = "過去ハイライト"
    elif fun:
        tag = "好プレー・一瞬"
    else:
        tag = "動画紹介"
    return score, tag


def _default_fetch(url: str, *, timeout: int = 12) -> str:
    req = _Request(url, headers={"User-Agent": "yoshilover-video-radar/1.0"})
    with _urlopen(req, timeout=timeout) as resp:  # noqa: S310 (公開 RSS のみ)
        return resp.read().decode("utf-8", errors="replace")


def gather_radar_videos(
    *,
    channels: list[dict],
    detect_player_fn: Callable[[str], str],
    fetch_fn: Optional[Callable[[str], str]] = None,
    today_players: Optional[set[str]] = None,
    today_opponent: str = "",
    min_score: int = 2,
    per_channel_limit: int = 8,
) -> list[dict]:
    """各チャンネルの RSS を巡回し、 候補動画 dict を score 降順で返す。

    各 dict: ``video_id / video_url / title / published_at / channel / role /
    player / score / type_tag``。 network 失敗チャンネルは silent skip。
    """
    fetch = fetch_fn or _default_fetch
    out: list[dict] = []
    for ch in channels:
        cid = ch.get("channel_id", "")
        if not cid:
            continue
        try:
            xml = fetch(_FEED_URL.format(cid=cid))
            parsed = parse_youtube_atom(xml)
        except Exception:  # noqa: BLE001
            continue
        entries = getattr(parsed, "entries", None) or []
        for e in entries[:per_channel_limit]:
            title = getattr(e, "title", "") or ""
            video_id = getattr(e, "video_id", "") or ""
            if not title or not video_id:
                continue
            player = ""
            try:
                player = detect_player_fn(title) or ""
            except Exception:  # noqa: BLE001
                player = ""
            score, tag = classify_video(
                title,
                role=ch.get("role", ""),
                player=player,
                today_players=today_players,
                today_opponent=today_opponent,
            )
            if score < min_score:
                continue
            out.append({
                "video_id": video_id,
                "video_url": getattr(e, "video_url", "") or f"https://www.youtube.com/watch?v={video_id}",
                "title": title,
                "published_at": getattr(e, "published_at", "") or "",
                "channel": ch.get("name", ""),
                "role": ch.get("role", ""),
                "player": player,
                "score": score,
                "type_tag": tag,
            })
    out.sort(key=lambda d: d["score"], reverse=True)
    return out
