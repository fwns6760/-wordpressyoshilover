"""H3 normalization filter — 30+ 旧 H3 → 12 統一 set へ正規化。

H3-STRUCTURE-UNIFY-2026-05-08 Phase 2 (post-process filter)。

Background
==========

2026-05-08 PM の live audit で、live posts の H3 が 30+ 種類混在していた:
- 同じ「ファン関連 X 投稿」を指す H3 が 4 形式 (📣 関連投稿 3 形式 + 💬 ファンの声)
- Gemini 自由生成 H3 が 30+ 種類 (【ハイライト】/【ファームのハイライト】/
  【投稿で出ていた内容】/【ファンの関心ポイント】等)
- category と H3 内容が一致しない (コラムに 📋事実カード / 中継予定 等が混入)

memory rule (feedback_publish_forward_must_check_gate_reason.md) 由来の
「ファンが次に来る H3 を予測できない」状態を解消するため、H3 を 12 set に
正規化する filter を WP create_post chokepoint に組み込む。

Unified 12 H3 set
=================

📋 事実カード     - 数字・スコア・選手名・基本情報
📊 戦況          - 順位・連勝・直近 N 試合
🏆 注目選手      - 当日活躍・MVP級
📣 発言内容      - 監督・選手 quote
📅 次の注目      - 次戦・次回登板・復帰見込み
💬 ファンの声    - X embed 見出し統一
🎬 中継予定      - 放送情報 (broadcast 専用)
🔗 出典記事      - 出典明示 (必須)
💉 怪我状況      - injury / recovery
🎯 注目対戦      - matchup / pitcher 対決
🆕 プロフィール  - 新外国人 / 新人 / 入団
🎟 試合詳細      - 球場 / チケット / アクセス

Behavior
========

- ``<h3>...</h3>`` 内の text content を rule table に照合
- match → 新 label に置換 (絵文字 + 統一語)
- 完全一致 / 前方一致 / 部分一致を組み合わせて検出
- 一致しない H3 は **そのまま** (新規 / カスタム H3 を破壊しない)
- 大量量に変更を加えない: idempotent、再 apply で結果不変

Constraints
===========

- ¥0 (pure regex / string)
- 外部 call なし、stateless
- false positive 抑制: 完全一致 / strict prefix のみ判定、ambiguous は維持
"""

from __future__ import annotations

import os
import re

__all__ = ["normalize_h3_in_html"]


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _fan_voice_h3_dedup_enabled() -> bool:
    val = (os.getenv("ENABLE_FAN_VOICE_H3_DEDUP") or "1").strip().lower()
    return val in _TRUE_VALUES


def _h3_title_dup_removal_enabled() -> bool:
    """333-QA: body 冒頭の article-title 風 h3 (【...】... 。 形式) を削除。"""
    val = (os.getenv("ENABLE_H3_TITLE_DUP_REMOVAL") or "1").strip().lower()
    return val in _TRUE_VALUES


# (旧 H3 text、 新 H3 text) のマッピング表。
# 順序は重要: 長い / 具体的なものを先に置いて部分一致順序の不安定さを避ける。
# 全部 完全一致 (text 全体が一致) で判定する (部分置換しない)。
_H3_RULES_EXACT: tuple[tuple[str, str], ...] = (
    # X embed 関連投稿 (4 形式統一 → 💬 ファンの声)
    ("📣 関連投稿", "💬 ファンの声"),
    ("関連投稿", "💬 ファンの声"),
    # Gemini 自由生成 H3 (【...】 形式)
    ("【ハイライト】", "📋 事実カード"),
    ("【ファームのハイライト】", "📋 事実カード"),
    ("【一軍への示唆】", "📅 次の注目"),
    ("【投稿で出ていた内容】", "💬 ファンの声"),
    ("【ファンの関心ポイント】", "📅 次の注目"),
    ("【次の注目】", "📅 次の注目"),
    ("【今後の注目点】", "📅 次の注目"),
    ("【今後の注目】", "📅 次の注目"),
    ("【発言内容】", "📣 発言内容"),
    ("【具体的な変更内容】", "📣 発言内容"),
    ("【この変更が意味すること】", "📋 事実カード"),
    ("【試合展開】", "📋 事実カード"),
    ("【チームへの影響と今後の注目点】", "📋 事実カード"),
    ("【スタメン一覧】", "📋 事実カード"),
    ("【二軍スタメン一覧】", "📋 事実カード"),
    ("【故障の詳細】", "💉 怪我状況"),
    ("【対象選手の基本情報】", "📋 事実カード"),
    ("【ニュースの整理】", "📋 事実カード"),
    ("【注目ポイント】", "📋 事実カード"),
    ("【注目選手】", "🏆 注目選手"),
    # 絵文字付加(統一)
    ("中継予定", "🎬 中継予定"),
    ("試合スコア", "📋 事実カード"),
)

# H3 抽出 regex: 開始 tag (任意 attr) + content + 閉 tag を 1 group で取る
_H3_RE = re.compile(
    r"(<h3\b[^>]*>)(.*?)(</h3>)",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_h3_inner_to_text(inner_html: str) -> str:
    """h3 タグ内 HTML から visible text のみを抽出 (suffix 検出 / mapping
    照合用)。例: ``📣 関連投稿(<span>巨人公式X</span>)`` → ``📣 関連投稿(巨人公式X)``。
    """
    text = _TAG_RE.sub("", inner_html or "")
    return _WS_RE.sub(" ", text).strip()


def _normalize_one_h3_text(inner_text: str) -> str | None:
    """1 つの h3 text に対する normalize 結果を返す。

    Returns:
      新 H3 text (置換すべき場合)、 None (置換しないべき場合 = 既に統一済 or
      mapping 該当なし)
    """
    if not inner_text:
        return None

    # 完全一致 / prefix 一致 (前方一致、suffix が ()/( 等の attribute 部分は許容)
    for old, new in _H3_RULES_EXACT:
        # 完全一致
        if inner_text == old:
            return new
        # prefix 一致 (suffix が「(」「(」で始まる attribution 部分)
        if inner_text.startswith(old):
            rest = inner_text[len(old):].lstrip()
            if rest.startswith("(") or rest.startswith("("):
                return new
            # space + 補足語 (例: 「📣 関連投稿 巨人公式X」)
            # rest が短く「(」 / 空白 / 漢字 ascii で始まる → suffix 部分扱いで置換
            if 0 < len(rest) <= 30:
                # 既に新 label が prefix の場合 (=既に normalize 済) は skip
                if not any(
                    n in inner_text for _, n in _H3_RULES_EXACT
                    if n != new and inner_text.startswith(n)
                ):
                    return new

    return None


def normalize_h3_in_html(html_body: str) -> str:
    """body HTML 内の全 ``<h3>...</h3>`` を 12 unified H3 set に正規化。

    入力 HTML を変更せず新文字列を返す。idempotent (再 apply で結果不変)。
    H3 が mapping に該当しない / 既に新形式の場合は そのまま 維持。
    """
    if not html_body:
        return html_body

    def _replace(m: re.Match) -> str:
        open_tag = m.group(1)
        inner_html = m.group(2)
        close_tag = m.group(3)

        inner_text = _strip_h3_inner_to_text(inner_html)
        new_text = _normalize_one_h3_text(inner_text)
        if new_text is None:
            return m.group(0)
        return f"{open_tag}{new_text}{close_tag}"

    normalized = _H3_RE.sub(_replace, html_body)
    if _fan_voice_h3_dedup_enabled():
        normalized = _dedupe_fan_voice_h3(normalized)
    if _h3_title_dup_removal_enabled():
        normalized = _remove_title_duplicate_first_h3(normalized)
    return normalized


def _remove_title_duplicate_first_h3(html_body: str) -> str:
    """body 冒頭の article-title 風 h3 を削除する。

    Heuristics (誤削除を防ぐため strict):
      - body 冒頭 200 chars 以内にある **first** h3 が対象
      - inner text length >= 26 chars (短い section h3 は対象外)
      - ``【`` で始まる (`【巨人】`, `【YouTube】`, `【大学野球】` 等)
      - ``。`` で終わる (完結した sentence)
      - 12 unified set のラベル ("📋 事実カード" 等) は ``【`` で始まらないので除外される

    idempotent: 既に削除済 (該当 h3 が無い) なら入力そのまま返す。
    """
    if not html_body:
        return html_body
    m = _H3_RE.search(html_body)
    if not m:
        return html_body
    # only first h3, and only if early in body
    if m.start() > 200:
        return html_body
    inner = _strip_h3_inner_to_text(m.group(2))
    if not inner or len(inner) < 26:
        return html_body
    if not inner.startswith("【"):
        return html_body
    if not inner.endswith("。"):
        return html_body
    return html_body[:m.start()] + html_body[m.end():]


_FAN_VOICE_LABEL = "💬 ファンの声"


def _dedupe_fan_voice_h3(html_body: str) -> str:
    """重複した ``💬 ファンの声`` h3 を 1 つに集約する。

    Background
    ----------
    Gemini 生成本文に ``【投稿で出ていた内容】`` heading が出ると、
    h3 normalize で ``💬 ファンの声`` に変換される。一方で
    ``src/rss_fetcher.py`` が X embed 用に ``<h3>💬 ファンの声（Xより）</h3>``
    を別に emit する場合があり、結果 2 重 h3 + 中身の薄い filler block が
    残る (66752 / 66788 等で観測)。

    本関数は **同一ラベル** の連続 / 近接 h3 を 1 つに集約する。残すのは:
      1. ``twitter-tweet`` blockquote を含む section
      2. それ以外は内容の長い方
      3. 同点なら最後の section
    削除側 section は h3 と本文ごと丸ごと除去する。section 境界は次の
    ``<h3``、``<hr``、または末尾。

    idempotent: 再 apply しても結果不変。
    """
    if not html_body or _FAN_VOICE_LABEL not in html_body:
        return html_body

    # section = (h3_start_idx, h3_end_idx, body_end_idx, label, has_twitter, body_len)
    h3_iter = list(_H3_RE.finditer(html_body))
    if len(h3_iter) < 2:
        return html_body

    sections = []
    for i, m in enumerate(h3_iter):
        inner_text = _strip_h3_inner_to_text(m.group(2))
        # section body = h3 終端 〜 次 h3 開始 (or next <hr ...> or 末尾)
        body_start = m.end()
        body_end = h3_iter[i + 1].start() if i + 1 < len(h3_iter) else len(html_body)
        # cut at <hr> if any (separator typically indicates section break)
        hr_match = re.search(r"<hr\b", html_body[body_start:body_end], re.IGNORECASE)
        if hr_match:
            body_end = body_start + hr_match.start()
        body = html_body[body_start:body_end]
        sections.append({
            "label": inner_text,
            "h3_start": m.start(),
            "body_end": body_end,
            "has_twitter": "twitter-tweet" in body,
            "body_len": len(re.sub(r"<[^>]+>", "", body).strip()),
        })

    # 同 label セクションをまとめる
    fan_sections = [s for s in sections if s["label"].startswith(_FAN_VOICE_LABEL)]
    if len(fan_sections) < 2:
        return html_body

    # keep: twitter-tweet を含むもの優先、なければ body_len 最大、同点なら最後
    def _keep_priority(s):
        return (1 if s["has_twitter"] else 0, s["body_len"], s["h3_start"])

    keeper = max(fan_sections, key=_keep_priority)
    drop_ranges = [
        (s["h3_start"], s["body_end"]) for s in fan_sections if s is not keeper
    ]
    if not drop_ranges:
        return html_body

    # 後ろから削除して index を保つ
    drop_ranges.sort(key=lambda r: r[0], reverse=True)
    result = html_body
    for start, end in drop_ranges:
        result = result[:start] + result[end:]
    return result
