"""data/players page (選手索引・五十音順) — 2026-07-06 user GO。

959 選手ページへの「探す入口」。my-favorite-giants の五十音索引に相当する
回遊 hub で、全選手ページへの内部リンク集約 = クロール効率の土台にもなる。

読みの出典 (推測で埋めない):
- 現役: config/giants_name_readings.json (NPB 公式 pc_v_kana bake)
- OB: config/ob_legends_full.json の kana
- 補助: config/giants_salary.json の kana
- カタカナ登録名 (外国人) は読み変換不要でそのまま「外国人・登録名」節
- 読みが取れない選手は「その他」節に出す (silent drop しない)
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os
import re as _re

_CONFIG_DIR = _os.path.join(_os.path.dirname(__file__), "..", "config")

GOJUON_ROWS: tuple[tuple[str, str], ...] = (
    ("あ行", "あいうえおぁぃぅぇぉ"),
    ("か行", "かきくけこがぎぐげご"),
    ("さ行", "さしすせそざじずぜぞ"),
    ("た行", "たちつてとだぢづでどっ"),
    ("な行", "なにぬねの"),
    ("は行", "はひふへほばびぶべぼぱぴぷぺぽ"),
    ("ま行", "まみむめも"),
    ("や行", "やゆよゃゅょ"),
    ("ら行", "らりるれろ"),
    ("わ行", "わをん"),
)

_KATAKANA_ONLY_RE = _re.compile(r"^[ァ-ヶー・\.\s A-Za-z]+$")


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def _load_json(name: str):
    try:
        with open(_os.path.join(_CONFIG_DIR, name), encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _nospace(s: str) -> str:
    return str(s or "").replace(" ", "").replace("　", "")


def load_kana_map() -> dict[str, str]:
    """漢字フル名 (空白なし) → ひらがな読み。出典3系統を merge。"""
    out: dict[str, str] = {}
    salary = _load_json("giants_salary.json")
    for p in (salary.get("players") or []):
        kana = _nospace(p.get("kana") or "")
        if kana:
            out[_nospace(p.get("name"))] = kana
    legends = _load_json("ob_legends_full.json")
    for name, st in (legends.get("stats") or {}).items():
        kana = _nospace((st or {}).get("kana") or "")
        if kana:
            out[_nospace(name)] = kana
    # NPB 公式 bake (現役) を最優先で上書き
    for name, kana in (_load_json("giants_name_readings.json") or {}).items():
        out[_nospace(name)] = _nospace(kana)
    return out


def _gojuon_row(kana: str) -> str:
    head = (kana or "")[:1]
    for label, chars in GOJUON_ROWS:
        if head in chars:
            return label
    return ""


def build_index_entries(pillar_infos) -> list[dict]:
    """PillarPlayerInfo 群 → 索引 entry (name/slug/kana/group/row)。"""
    kana_map = load_kana_map()
    entries: list[dict] = []
    seen: set[str] = set()
    for info in pillar_infos or []:
        name = str(getattr(info, "name", "") or "").strip()
        slug = str(getattr(info, "slug", "") or "").strip()
        if not name or not slug or slug in seen:
            continue
        seen.add(slug)
        role = str(getattr(info, "role", "") or "player")
        if role in {"manager", "coach"}:
            group = "首脳陣"
        elif role == "ob":
            group = "OB・歴代選手"
        else:
            group = "現役選手"
        kana = kana_map.get(_nospace(name), "")
        if not kana and _KATAKANA_ONLY_RE.match(name):
            group = f"{group}（外国人・登録名）" if group == "現役選手" else group
            # カタカナ登録名はそのまま 50 音相当に落とす (ティマ→てぃま)
            kana = "".join(
                chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in _nospace(name)
            )
        row = _gojuon_row(kana)
        entries.append({
            "name": name, "slug": slug, "kana": kana, "group": group, "row": row,
        })
    return entries


def render_player_index_title() -> str:
    return "巨人 選手一覧・選手名鑑【現役・OB 五十音索引】 | 巨人データ"


def render_player_index_excerpt(entries: list[dict]) -> str:
    return (
        f"読売ジャイアンツの選手データページ全{len(entries)}人分を五十音順で探せる索引。"
        "現役選手・首脳陣・OB/歴代選手の成績・年俸・記録ページへの入口です。"
    )


def render_player_index_html(entries: list[dict]) -> str:
    groups = ["現役選手", "現役選手（外国人・登録名）", "首脳陣", "OB・歴代選手"]
    parts: list[str] = [
        f"<p>巨人の選手データページ 全{len(entries)}人分の索引です。"
        "選手名をタップすると、成績・記録・年俸推移のページに移動します。</p>"
    ]
    for group in groups:
        rows_in_group = [e for e in entries if e["group"] == group]
        if not rows_in_group:
            continue
        parts.append(f'<h2 style="font-size:18px;">{_esc(group)}（{len(rows_in_group)}人）</h2>')
        no_row = [e for e in rows_in_group if not e["row"]]
        for label, _chars in GOJUON_ROWS:
            in_row = sorted(
                (e for e in rows_in_group if e["row"] == label),
                key=lambda e: e["kana"],
            )
            if not in_row:
                continue
            links = "・".join(
                f'<a href="/data/{_esc(e["slug"])}">{_esc(e["name"])}</a>' for e in in_row
            )
            parts.append(
                f'<p style="line-height:2;"><strong>{label}</strong>｜{links}</p>'
            )
        if no_row:
            links = "・".join(
                f'<a href="/data/{_esc(e["slug"])}">{_esc(e["name"])}</a>'
                for e in sorted(no_row, key=lambda e: e["name"])
            )
            parts.append(f'<p style="line-height:2;"><strong>その他</strong>｜{links}</p>')
    return "\n".join(parts)
