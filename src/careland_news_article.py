"""CARE LAND 速報記事候補のビルダー。

判定 (NewsVerdict) と候補メタから、WordPress 下書き用の本文 (HTML) を組み立てる。
**レイアウトは yoshilover（のもとけ）のサテライト引用記事と同じ構造**にそろえる:

  1. NEWS DIGEST バナー（CARE LAND 緑）
  2. 出典行
  3. リード（クリーンな1〜2文。生RSS HTML/URLは除去する）
  4. 📖 本文抜粋（適法引用。元記事の要点を短く blockquote＋出典。**ペイウォールやナビの
     定型文（「有料プランをご購読」「記事を保存」等）しか取れていない時は出さない**）
  5. 出典バッジ（引用記事である旨＋出典リンク）
  6. 🏷 関連タグ
  7. 共有ボタン（𝕏 / LINE。JS不要の実リンク）
  8. 🔗 出典記事（元記事への named link）
  9. コメントCTA フッター
  10. ご注意（医療/法的断定をしない免責。careland 固有・必須）

  ※ yoshilover の「💬 ファンの声（Xより）」は careland では出さない（共有 h3_normalizer の
    自動付与は Job env `ENABLE_FAN_VOICE_ENSURE=0` で抑止する）。

careland.org の DB は utf8（4バイト絵文字が保存時に消える）なので、**絵文字は必ず HTML 実体
参照（&#NNNNN;）で出力**する。

index/noindex 判定もここで行う。WordPress 側は既定 noindex で、index_meta_key が
"1" のときだけ index 許可する設計（careland-news-noindex.php と対）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from urllib.parse import quote, urlparse

from src.careland_news_judgment import NewsVerdict

try:  # lead 整形は yoshilover と同じ sanitizer を流用（生RSS HTML/URLを除去）
    from src.nomotoke_card_renderer import _sanitize_lead_text as _sanitize_lead
except Exception:  # pragma: no cover - 取れなくても最低限の整形で動く
    def _sanitize_lead(raw):  # type: ignore
        import html as _html
        if not isinstance(raw, str) or not raw:
            return ""
        decoded = _html.unescape(raw)
        no_tags = re.sub(r"<[^>]+>", " ", decoded)
        no_urls = re.sub(r"https?://\S+", "", no_tags)
        return re.sub(r"\s+", " ", no_urls).strip()


# 引用本文（📖 本文抜粋）の文字数上限。yoshilover（manual_intake の
# SOURCE_BODY_EXCERPT_MAX_CHARS）と同じ 1200字にそろえる。
SOURCE_BODY_EXCERPT_MAX_CHARS = 1200


@dataclass(frozen=True)
class ArticleDraft:
    title: str
    content: str
    category_ids: tuple[int, ...]
    want_index: bool          # True=index許可候補 / False=noindex
    x_post_text: str
    slug_hint: str


# 元記事本文を転載しない注意書きと、医療/法的断定をしない免責。
_DISCLAIMER = (
    "本記事は公的発表・報道をもとに、当事者・家族・支援者向けに要点を整理した引用記事です。"
    "元記事本文の転載はしていません。診断・治療・服薬・障害年金の受給可否・法的判断を断定する"
    "ものではありません。正確な内容と最新情報は、必ず本文中の公式情報（一次情報）をご確認ください。"
)

# careland.org は utf8 のため 4バイト絵文字は実体参照で出力する（生だと保存時に消える）。
_EMO_NEWS = "&#128240;"   # 📰
_EMO_SEED = "&#127793;"   # 🌱
_EMO_BOOK = "&#128214;"   # 📖
_EMO_TAG = "&#127991;"    # 🏷
_EMO_CHAT = "&#128172;"   # 💬
_EMO_LINK = "&#128279;"   # 🔗
_EMO_X = "&#120143;"      # 𝕏

# 本文抜粋として出してはいけないペイウォール/ナビ/共有ボタンの定型文。
# これらしか取れていない引用は「引用元が悪い」ので 本文抜粋ごと省く。
_JUNK_MARKERS = (
    "有料プラン", "ご購読", "購読", "会員登録", "ログイン", "無料会員", "プレミアム",
    "記事を保存", "お気に入りに追加", "クリップ", "この記事の写真",
    "シェア", "ブックマーク", "facebook", "line", "コメント｜", "コメント |",
    "続きを読む", "残り", "文字", "の記事は有料", "閲覧できます", "ご利用いただけ",
    "アプリで読む", "ニュースレター", "メールマガジン",
)


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _is_paywall_junk(text: str) -> bool:
    """ナビ/ペイウォール/共有ボタンの定型文ばかりか判定する（長さは見ない）。"""
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()
    hits = sum(1 for m in _JUNK_MARKERS if m in low)
    # 定型文マーカーが多い、または本文の文（。）が無いのにマーカーがある＝ゴミ扱い。
    if hits >= 2:
        return True
    if t.count("。") == 0 and hits >= 1:
        return True
    return False


def has_quotable_body(excerpt: str, *, min_chars: int = 40) -> bool:
    """引用記事にできる「実本文」が取れているか。

    Googleニュースのラッパー／Yahoo!ニュース／有料記事は本文が抜けず、ナビ・ペイウォール
    定型文しか取れない。そういうものは引用記事にせず X ポスト候補に留めるための判定。
    """
    t = " ".join((excerpt or "").split()).strip()
    if len(t) < min_chars:
        return False
    if _is_paywall_junk(t):
        return False
    return True


def _clean_lead(*candidates: str) -> str:
    """先頭から有効なリード文を選ぶ。生RSS HTML/URLは除去、ペイウォール定型文は飛ばす。
    短い見出しフォールバックは許容する（lead に長さ要件は課さない）。"""
    for raw in candidates:
        cleaned = _sanitize_lead(raw or "")
        if cleaned and not _is_paywall_junk(cleaned):
            return cleaned
    return ""


def _trim_for_quote(text: str, max_chars: int) -> str:
    """引用は短く。max_chars 以内で、できれば文末(。！？)で切る。"""
    t = " ".join((text or "").split()).strip()
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    boundary = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
    if boundary >= max_chars // 2:
        return cut[: boundary + 1]
    return cut.rstrip() + "…"


# ---- ブロック生成（yoshilover/のもとけと同じクラス名・レイアウト） --------------------

def _news_digest_banner(media: str, title: str) -> str:
    """のもとけの NEWS DIGEST バナー（CARE LAND 緑）。"""
    return (
        '<div class="nomotoke-news-banner" style="background:linear-gradient(135deg,#34b36b 0%,#1b8a3e 100%);'
        'border-radius:10px;padding:18px 20px;margin:0 0 8px 0;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<span style="background:rgba(255,255,255,0.2);color:#fff;font-size:0.78em;font-weight:800;'
        f'padding:4px 10px;border-radius:20px;letter-spacing:0.05em;">{_EMO_NEWS} {escape(media)}</span>'
        f'<span style="color:rgba(255,255,255,0.85);font-size:0.72em;font-weight:700;'
        f'letter-spacing:0.08em;">{_EMO_SEED} CARE LAND NEWS</span>'
        '</div>'
        f'<div style="color:#fff;font-size:1.1em;font-weight:900;line-height:1.4;">{escape(title)}</div>'
        '</div>'
    )


def _source_line(url: str, label: str) -> str:
    return (
        f'<p class="nomotoke-source">出典: <a href="{escape(url, quote=True)}" '
        f'target="_blank" rel="noopener">{escape(label)}</a></p>'
    )


def _lead_block(text: str) -> str:
    return f'<p class="nomotoke-lead">{escape(text)}</p>'


def _excerpt_paragraphs_html(quoted: str) -> str:
    """yoshilover（のもとけ）と同じ見た目に寄せて、文単位で <br> 改行して段落化する。"""
    # 改行で段落、各段落は文末（。！？）で <br> 区切り。
    paras = [p.strip() for p in re.split(r"[\r\n]+", quoted) if p.strip()] or [quoted]
    out: list[str] = []
    for para in paras:
        sentences = [s for s in re.split(r"(?<=[。！？])", para) if s.strip()]
        inner = "<br>".join(escape(s.strip()) for s in sentences) if sentences else escape(para)
        out.append(f"<p>{inner}</p>")
    return "".join(out)


def _source_excerpt_block(excerpt: str, url: str, max_chars: int) -> str:
    """📖 本文抜粋（適法引用）。のもとけと同じ aside 構造・文字数（1200字）。ゴミなら空文字。"""
    quoted = _trim_for_quote(excerpt, max_chars)
    # 本文抜粋は「実本文が一定量ある」ことを要件にする（短い/ペイウォール定型文は出さない）。
    if not quoted or len(quoted) < 40 or _is_paywall_junk(quoted):
        return ""
    attr = _domain(url) or "元記事"
    return (
        '<aside class="nomotoke-source-excerpt" id="toc-excerpt">'
        f'<p class="nomotoke-source-excerpt__label">{_EMO_BOOK} 本文抜粋</p>'
        f'<blockquote class="nomotoke-source-excerpt__body">{_excerpt_paragraphs_html(quoted)}</blockquote>'
        f'<p class="nomotoke-source-excerpt__attr">— {escape(attr)}</p>'
        '</aside>'
    )


def _trust_badge(url: str, source_name: str) -> str:
    """出典バッジ（のもとけの trust-badge と同構造・CARE LAND 緑）。

    careland は AI 判定を使うので「AIを使わず」とは書かず、引用記事である旨を明示する。
    """
    safe = escape(url, quote=True)
    return (
        '<aside class="nomotoke-ai-badge nomotoke-trust-badge" '
        'style="margin:16px 0;padding:10px 14px;border-left:3px solid #1b8a3e;background:#e8f5e9;'
        'border-radius:4px;font-size:13px;line-height:1.5;color:#1b5e20;">'
        f'{_EMO_NEWS} この記事は出典記事の要点を整理した<strong>引用記事</strong>です'
        '（元記事本文の転載はしていません）。<br>'
        f'{_EMO_NEWS} 出典: <a href="{safe}" target="_blank" rel="noopener">{escape(source_name)}</a>'
        '</aside>'
    )


def _tag_chips(tags: list[str]) -> str:
    if not tags:
        return ""
    chips = "".join(
        f'<a class="nomotoke-chip" href="/?s={quote(t)}" '
        'style="display:inline-block;margin:4px 4px 0 0;padding:4px 10px;background:#e8f5e9;'
        'color:#1b5e20;border:1px solid #66bb6a;border-radius:14px;text-decoration:none;font-size:13px;">'
        f'#{escape(t)}</a>'
        for t in tags
    )
    return (
        '<aside class="nomotoke-tag-chips">'
        f'<p class="nomotoke-tag-chips__label">{_EMO_TAG} 関連タグ</p>'
        f'<p class="nomotoke-tag-chips__row">{chips}</p>'
        '</aside>'
    )


def _share_buttons(url: str, title: str) -> str:
    """共有ボタン（𝕏 / LINE）。JS不要の実リンク（careland.org に共有JSは無いため）。"""
    x_url = "https://twitter.com/intent/tweet?text=" + quote(f"{title}\n", safe="") + "&url=" + quote(url, safe="")
    line_url = "https://social-plugins.line.me/lineit/share?url=" + quote(url, safe="")
    btn = ('display:inline-block;margin:0 6px;padding:6px 14px;color:#fff;text-decoration:none;'
           'border-radius:6px;font-size:13px;font-weight:600;')
    return (
        '<aside class="nomotoke-share-buttons" style="margin:14px 0;padding:10px 0;'
        'border-top:1px solid #eee;border-bottom:1px solid #eee;text-align:center;">'
        '<p style="margin:0 0 8px;font-size:13px;font-weight:600;">&#9660; この記事を共有する</p>'
        '<p style="margin:0;">'
        f'<a class="nomotoke-share-x" href="{escape(x_url, quote=True)}" target="_blank" rel="noopener" '
        f'style="{btn}background:#000;">{_EMO_X} で共有</a>'
        f'<a class="nomotoke-share-line" href="{escape(line_url, quote=True)}" target="_blank" rel="noopener" '
        f'style="{btn}background:#06c755;">LINE で共有</a>'
        '</p>'
        '</aside>'
    )


def _source_article_block(url: str, title: str, source_name: str) -> str:
    safe = escape(url, quote=True)
    label = f"{title} | {source_name}" if source_name else title
    return (
        f'<h3>{_EMO_LINK} 出典記事</h3>'
        f'<p>記事全文は <a href="{safe}" target="_blank" rel="noopener">{escape(label)}</a> をご覧ください。</p>'
    )


def _footer_cta() -> str:
    return (
        '<hr class="nomotoke-card-divider">'
        '<div class="nomotoke-card-footer">'
        '<p class="nomotoke-cta-row">'
        '<a class="nomotoke-cta-button" href="#respond" '
        'style="display:inline-block;padding:12px 28px;background:#1b8a3e;color:#fff;text-decoration:none;'
        f'border-radius:8px;font-weight:700;font-size:16px;">{_EMO_CHAT} コメントする</a>'
        '</p>'
        '<p class="nomotoke-comment-hint">この記事へのコメント・反応はコメント欄からお願いします。</p>'
        '</div>'
    )


def _disclaimer_block() -> str:
    return (
        '<h3>ご注意</h3>'
        f'<p>{escape(_DISCLAIMER)}</p>'
    )


def decide_category_ids(*, lane: str, title: str, summary: str,
                        breaking_id: int, category_map: dict[str, int]) -> tuple[int, ...]:
    """速報カテゴリ + 本文一致したカテゴリ。常に速報を含める。"""
    text = f"{title} {summary}"
    ids: list[int] = [breaking_id]
    keyword_to_cat = {
        "障害者雇用": "障害者雇用",
        "法定雇用率": "障害者雇用",
        "就労移行": "就労支援",
        "就労継続": "就労支援",
        "就職": "就労支援",
        "報酬改定": "制度",
        "改正": "制度",
        "通知": "制度",
        "パブリックコメント": "制度",
        "意見募集": "制度",
    }
    for kw, cat_name in keyword_to_cat.items():
        if kw in text and cat_name in category_map:
            cid = category_map[cat_name]
            if cid not in ids:
                ids.append(cid)
    return tuple(ids)


def decide_index(verdict: NewsVerdict, *, default_index: bool) -> bool:
    """index/noindex 判定。

    - hold / discard は index しない（noindex 候補）。
    - 公式発表ベースの記事候補 (x_article) は index 候補にする。
    - それ以外は config の default_index に従う（既定: noindex）。
    リスクフラグがあれば常に noindex。
    """
    if verdict.needs_human_only:
        return False
    if verdict.risk_flags:
        return False
    if verdict.decision == "x_article":
        return True
    return bool(default_index)


def _derive_tags(*, lane_label: str, category_names: list[str]) -> list[str]:
    tags: list[str] = []
    for t in [lane_label, *category_names]:
        t = (t or "").strip()
        if t and t not in tags:
            tags.append(t)
    return tags[:4]


def build_article_draft(*, verdict: NewsVerdict, title: str, summary: str,
                        source_name: str, url: str, lane: str, lane_label: str,
                        breaking_id: int, category_map: dict[str, int],
                        default_index: bool, slug_hint: str,
                        body_excerpt: str = "") -> ArticleDraft:
    article_title = (verdict.article_title or title).strip()
    if not article_title.startswith("【"):
        article_title = f"【{lane_label}】{article_title}"
    headline = article_title.lstrip("【").split("】")[-1] or title

    official_url = verdict.official_url or url

    # リードは「クリーンな1〜2文」。生RSS HTML/URL を除去し、ゴミなら次の候補へ。
    lead = _clean_lead(verdict.what_changes or "", summary, headline)

    # 引用本文の文字数は yoshilover と同じ 1200字（manual_intake の SOURCE_BODY_EXCERPT_MAX_CHARS）。
    excerpt_html = _source_excerpt_block(body_excerpt, official_url, SOURCE_BODY_EXCERPT_MAX_CHARS)

    category_ids = decide_category_ids(
        lane=lane, title=title, summary=summary,
        breaking_id=breaking_id, category_map=category_map,
    )
    id_to_name = {v: k for k, v in category_map.items()}
    category_names = [id_to_name[c] for c in category_ids if c in id_to_name]
    tags = _derive_tags(lane_label=lane_label, category_names=category_names)

    # yoshilover（のもとけ）と同じブロック順で組む。
    parts = [
        _news_digest_banner(source_name, headline),
        _source_line(official_url, source_name),
    ]
    if lead:
        parts.append(_lead_block(lead))
    if excerpt_html:
        parts.append(excerpt_html)
    parts.append(_trust_badge(official_url, source_name))
    chips = _tag_chips(tags)
    if chips:
        parts.append(chips)
    parts.append(_share_buttons(official_url, headline))
    parts.append(_source_article_block(official_url, headline, source_name))
    parts.append(_footer_cta())
    parts.append(_disclaimer_block())

    x_text = verdict.x_post_text or f"【{lane_label}】{title}（出所: {source_name}）詳細はCARE LANDで整理しています。"

    content = "\n".join(parts).strip()
    want_index = decide_index(verdict, default_index=default_index)

    return ArticleDraft(
        title=article_title,
        content=content,
        category_ids=category_ids,
        want_index=want_index,
        x_post_text=x_text,
        slug_hint=slug_hint,
    )


__all__ = ["ArticleDraft", "build_article_draft", "decide_category_ids",
           "decide_index", "has_quotable_body"]
