"""search_trend_note.py — Google 急上昇ワード (JP) を X ポスト候補メールに反映。

2026-07-10 user「インプあげるのに検索キーワード入れるといい。トレンドとか」:
検索インプは「いま検索されている語」を含むポストに集まる。X API Free (write-only)
ではトレンドが取れず、Yahoo リアルタイムの scrape はページ構造変更で壊れている
ため、Google Trends の公式 RSS (https://trends.google.co.jp/trending/rss?geo=JP、
無料・key 不要) を使う。

使い方 (run_x_post_mail):
- 野球/巨人に関係する急上昇ワードだけ抽出し、mail 冒頭の note 行にする
- 候補の本文/選手名にトレンド語が入っている候補は title に 🔥[急上昇] を付け、
  user が優先選択できるようにする
- 投稿文そのものは書き換えない (キーワード詰め込みで voice が崩れるのを防ぐ)
- 取得失敗・関連トレンド 0 件は note "" (mail は従来どおり)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

LOG = logging.getLogger("search_trend_note")

_TREND_RSS_URL = "https://trends.google.co.jp/trending/rss?geo=JP"
_TIMEOUT_SECONDS = 5

# 野球関連とみなす marker (トレンド語側に含まれていれば roster 一致不要)
_BASEBALL_MARKERS = (
    "巨人", "ジャイアンツ", "読売", "プロ野球", "野球", "NPB", "セリーグ", "セ・リーグ",
    "甲子園", "オールスター", "球宴", "サヨナラ", "ホームラン", "ノーヒットノーラン",
    "完全試合", "阪神", "タイガース", "広島", "カープ", "中日", "ドラゴンズ",
    "ヤクルト", "スワローズ", "DeNA", "ベイスターズ", "横浜",
    "MLB", "メジャー", "ドジャース", "パドレス", "大谷翔平",
)

_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_TITLE_RE = re.compile(r"<title>([^<]+)</title>")
_TRAFFIC_RE = re.compile(r"<ht:approx_traffic>([^<]+)</ht:approx_traffic>")


def fetch_jp_trends(timeout: float = _TIMEOUT_SECONDS) -> list[dict[str, str]]:
    """Google Trends JP RSS → [{keyword, traffic}]。失敗は []。"""
    try:
        resp = requests.get(
            _TREND_RSS_URL,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (yoshilover trend note)"},
        )
        resp.raise_for_status()
        return parse_trend_rss(resp.text)
    except Exception as exc:  # noqa: BLE001 - トレンドは飾り、失敗で止めない
        LOG.info("trend fetch skip: %r", exc)
        return []


def parse_trend_rss(xml_text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in _ITEM_RE.finditer(xml_text or ""):
        item = m.group(1)
        t = _TITLE_RE.search(item)
        if not t:
            continue
        keyword = t.group(1).strip()
        if not keyword:
            continue
        tr = _TRAFFIC_RE.search(item)
        out.append({
            "keyword": keyword,
            "traffic": (tr.group(1).strip() if tr else ""),
        })
    return out


def _giants_name_tokens() -> set[str]:
    """roster のフルネーム + 姓 (2 字以上)。取得失敗は空 set。"""
    try:
        from src.giants_roster_loader import load_active_roster

        entries = load_active_roster()
    except Exception as exc:  # noqa: BLE001
        LOG.info("trend roster skip: %r", exc)
        return set()
    tokens: set[str] = set()
    for e in entries or []:
        name = str(e.get("name") or "").strip()
        if not name:
            continue
        tokens.add(name.replace(" ", ""))
        surname = name.split(" ", 1)[0]
        if len(surname) >= 2:
            tokens.add(surname)
    return tokens


def build_trend_note_and_boost(candidates: list[Any]) -> str:
    """関連トレンドの note 行を返し、一致候補の title に 🔥 を付ける (in-place)。"""
    trends = fetch_jp_trends()
    if not trends:
        return ""
    roster = _giants_name_tokens()

    def _relevant(kw: str) -> bool:
        if any(mk in kw for mk in _BASEBALL_MARKERS):
            return True
        return any(tok in kw for tok in roster)

    relevant = [t for t in trends if _relevant(t["keyword"])][:6]
    if not relevant:
        LOG.info("search_trend: no baseball-related trend (total=%d)", len(trends))
        return ""
    boosted = 0
    for cand in candidates:
        hay = " ".join(
            str(getattr(cand, f, "") or "")
            for f in ("title", "post_text", "draft_text", "focus_player")
        )
        hit = next(
            (t["keyword"] for t in relevant if _keyword_hits(t["keyword"], hay)),
            "",
        )
        if hit and not str(getattr(cand, "title", "")).startswith("🔥"):
            try:
                cand.title = f"🔥[急上昇: {hit}] {cand.title}"
                boosted += 1
            except Exception:  # noqa: BLE001 - frozen 等は note のみで続行
                pass
    note = "🔥 Google急上昇 (野球/巨人関連): " + " / ".join(
        f"{t['keyword']}({t['traffic']})" if t["traffic"] else t["keyword"]
        for t in relevant
    )
    LOG.info(
        "search_trend: relevant=%d boosted=%d total=%d",
        len(relevant), boosted, len(trends),
    )
    return note


def _keyword_hits(keyword: str, haystack: str) -> bool:
    """トレンド語 (「パドレス 対 dバックス」等の複合語は token 分割) との一致。"""
    if keyword in haystack:
        return True
    tokens = [tok for tok in re.split(r"[\s　]+", keyword) if len(tok) >= 2]
    return bool(tokens) and all(tok in haystack for tok in tokens)
