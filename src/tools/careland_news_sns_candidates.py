"""CARE LAND 発達障害・福祉ニュース版 候補ビルダー。

finance_news_sns と同方式:
  公開ソース取得 -> 重複チェック -> AI価値判定 -> 候補メール
SNS への自動投稿はしない。WordPress の自動公開もしない。最終判断は人間。

fetch / dedupe / score の足回りは finance_news_sns_candidates を流用し、
発達障害・福祉版の差分（lane ラベル・AI判定・ボタン付きメール）だけをここに置く。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from urllib.parse import quote
import logging
import os
import time

from src.tools import finance_news_sns_candidates as fnc
from src.careland_news_judgment import NewsVerdict, judge_news
from src.careland_news_article import build_article_draft, has_quotable_body
from src.careland_baseball_welfare import BaseballWelfarePost
from src.mail_delivery_bridge import InlineImage
from src import careland_share_x as cshare
from src.publish_button_token import build_publish_button_url

try:
    from src.source_article_body_extractor import extract_article_body_excerpt
except Exception:  # pragma: no cover - 抽出器が無くても動く
    extract_article_body_excerpt = None  # type: ignore

try:
    from src.google_news_url_resolver import (
        is_google_news_url,
        resolve_google_news_url,
        reset_circuit as reset_gnews_circuit,
        split_publisher_from_title,
    )
except Exception:  # pragma: no cover - リゾルバが無くても動く
    is_google_news_url = lambda u: False  # type: ignore  # noqa: E731
    resolve_google_news_url = lambda u, **k: None  # type: ignore  # noqa: E731
    reset_gnews_circuit = lambda: None  # type: ignore  # noqa: E731
    split_publisher_from_title = lambda t: (t, None)  # type: ignore  # noqa: E731

LOG = logging.getLogger(__name__)


import re as _re_og


def _extract_og_image(html_text: str, base_url: str) -> str:
    """元記事の og:image（無ければ twitter:image）を取り出す。アイキャッチ用。"""
    if not html_text:
        return ""
    for pat in (
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    ):
        m = _re_og.search(pat, html_text, _re_og.IGNORECASE)
        if m:
            url = (m.group(1) or "").strip()
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            if url.lower().startswith("https://"):
                return url
    return ""


def fetch_excerpt_and_image(url: str, title: str, *, timeout_seconds: int) -> tuple[str, str]:
    """元ページを1回取得し、(本文抜粋1200字, og:image URL) を返す。失敗時は ('','')。"""
    if not extract_article_body_excerpt or not url:
        return "", ""
    try:
        html_text = fnc._http_get(url, timeout_seconds=timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        LOG.info("careland_excerpt_fetch_failed url=%s error=%s", url, type(exc).__name__)
        return "", ""
    try:
        excerpt = extract_article_body_excerpt(html_text, url, max_chars=1200, title=title)
    except Exception:  # noqa: BLE001
        excerpt = ""
    return excerpt, _extract_og_image(html_text, url)


def _fetch_excerpt(url: str, title: str, *, timeout_seconds: int) -> str:
    """元ページを取得して本文抜粋を返す（best-effort）。失敗時は空文字。

    yoshilover 同様「元ページをしっかり読む」ための材料。転載はせず判定/文案の参考に使う。
    """
    return fetch_excerpt_and_image(url, title, timeout_seconds=timeout_seconds)[0]

# Xポスト末尾のブランド署名。user 指定で既定は「無し」。
# 付けたい場合のみ env CARELAND_X_BRAND_TAG で1行指定する。
DEFAULT_X_BRAND_TAG = ""


def _x_brand_tag() -> str:
    raw = os.environ.get("CARELAND_X_BRAND_TAG")
    tag = DEFAULT_X_BRAND_TAG if raw is None else raw
    tag = tag.strip()
    if not tag:
        return ""
    return tag if tag.startswith("\n") else "\n" + tag

DEFAULT_SOURCE_FILE = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "config" / "careland_news_sources.example.json"
)

DECISION_LABEL = {
    "x_article": "Xポスト＋記事候補",
    "x_only": "Xポスト候補",
    "weekly": "週次まとめ候補",
    "hold": "保留（要確認）",
    "discard": "破棄候補",
}

# 図カード（render_message_card）のカテゴリピル文言。Xに出す候補だけ図を作る。
_CARD_CATEGORY = {
    "x_article": "制度・公式発表",
    "x_only": "福祉ニュース",
}


# カード見出しの最大文字数。薄帯カードに **大きな1行** で収まる量に省略する
# （これ以上は「…」で省略。2行にはしない＝user指定「1行に短く」）。
_CARD_MESSAGE_MAX = 14
# 見出しを途中で切るときに優先して区切る位置（前半=主題が残るように）。
_CARD_HEAD_SPLITS = ("──", "—", "―", "〜", "～", "｜", "|", "【", "】", "。")
# 途中で締めるときの区切り（開き括弧の直前では切らない＝中身が消えるため）。
_CARD_SOFT_BOUNDARY = ("、", "，", "・", "：", ":", " ")


def _card_message(title: str, *, max_chars: int = _CARD_MESSAGE_MAX) -> str:
    """ニュース見出しをカード用に短く省略する。

    1) ──/—/｜/【】/。 など最初の大区切りで切って主題だけ残す
    2) まだ長ければ max_chars 以内の最後の自然な区切り（、・：等）で締める
    3) それも無ければ詰めて「…」を付ける
    """
    text = (title or "").strip()
    # 先頭の 【カテゴリ】 は主題ではないので落とす。
    if text.startswith("【") and "】" in text:
        text = text.split("】", 1)[1].strip()
    # 最初の大区切りで前半（主題）だけ取る。
    for sep in _CARD_HEAD_SPLITS:
        i = text.find(sep)
        if 0 < i:
            text = text[:i].strip()
            break
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    cut = max(head.rfind(b) for b in _CARD_SOFT_BOUNDARY)
    # 区切りが十分後ろ（7割以降）にある時だけそこで締める。早すぎる区切り
    # （例: 「Google、…」の直後のカンマ）で切ると意味が失われるので詰めて「…」。
    if cut >= int(max_chars * 0.7):
        return head[:cut].rstrip("、，・：: ")
    return head.rstrip() + "…"


def _card_image_bytes(cand: "CarelandCandidate") -> bytes | None:
    """候補から「文字で訴える」緑カード PNG を作る。PIL未導入や失敗時は None。"""
    try:
        from src.careland_brand_image import render_message_card
    except Exception:  # noqa: BLE001  (Pillow 未導入の dry-run 等)
        return None
    try:
        return render_message_card(
            _card_message(cand.title),
            category=_CARD_CATEGORY.get(cand.decision, "福祉ニュース"),
        )
    except Exception:  # noqa: BLE001  (フォント無し等でも本文は送る)
        logging.getLogger(__name__).info("careland brand card render failed", exc_info=True)
        return None


@dataclass(frozen=True)
class CarelandCandidate:
    source_id: str
    source_name: str
    post_lane: str
    lane_label: str
    default_decision: str
    title: str
    url: str
    summary: str
    score: int
    priority: str
    dedupe_key: str
    verdict: NewsVerdict
    # 元記事本文の抜粋（適法引用ブロック用。転載はせず短く引用）
    body_excerpt: str = ""
    # 元記事の og:image（ヒーロー画像＋アイキャッチ用）
    hero_image_url: str = ""
    # x_article のとき、メールに同梱する記事候補プレビュー
    article_title: str = ""
    article_html: str = ""
    # runner が WP draft を作ったら埋まる（記事候補のみ）
    post_id: int | None = None
    want_index: bool = False

    @property
    def decision(self) -> str:
        return self.verdict.decision

    def x_post_text(self, *, max_chars: int = 240) -> str:
        base = self.verdict.x_post_text or f"【{self.lane_label}】{self.title}（出所: {self.source_name}）"
        tag = _x_brand_tag()
        # ブランド署名込みで max_chars に収める（署名は必ず残す）。
        room = max(0, max_chars - len(tag))
        if len(base) > room:
            # 文の途中で切らず、room 内の最後の句点(。/！/？/改行)で締める。
            cut = base[:room]
            boundary = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("\n"))
            if boundary >= room // 2:
                base = cut[: boundary + 1].rstrip()
            else:
                base = cut[: max(0, room - 1)].rstrip() + "…"
        return f"{base}{tag}"

    def x_intent_url(self) -> str:
        # finance 同様、サーバを介さずクライアント側で X composer を開く（自動投稿しない）。
        return "https://twitter.com/intent/tweet?text=" + quote(self.x_post_text(), safe="")


@dataclass
class CarelandBuildResult:
    candidates: list[CarelandCandidate]
    stats: fnc.FinanceBuildStats


def _lane_meta(config: dict) -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for lane in config.get("lanes", []):
        if isinstance(lane, dict) and lane.get("lane"):
            meta[str(lane["lane"])] = lane
    return meta


def lane_label(config: dict, lane: str) -> str:
    return str(_lane_meta(config).get(lane, {}).get("label") or "発達障害・福祉ニュース")


def lane_default_decision(config: dict, lane: str) -> str:
    return str(_lane_meta(config).get(lane, {}).get("default_decision") or "weekly")


def build_candidates(
    *,
    source_path=DEFAULT_SOURCE_FILE,
    now: datetime | None = None,
    timeout_seconds: int = 6,
    max_items_per_source: int = 20,
    max_candidates: int = 8,
    minimum_score: int | None = None,
    ledger_path: str | None = None,
    gcs_ledger_uri: str | None = None,
    run_judgment: bool = True,
    api_key: str | None = None,
) -> CarelandBuildResult:
    """finance の足回りで候補を集め、各候補を AI 判定する。"""
    reset_gnews_circuit()  # 実行ごとに Google News 解決のキャッシュ/ブレーカーを初期化
    active_now = now or datetime.now().astimezone()
    sources, config = fnc.load_sources(source_path)
    stats = fnc.FinanceBuildStats(loaded_sources=len(sources))

    raw_items = fnc.collect_raw_items(
        sources,
        timeout_seconds=timeout_seconds,
        max_items_per_source=max_items_per_source,
        stats=stats,
    )
    min_score = int(
        minimum_score
        if minimum_score is not None
        else config.get("scoring", {}).get("minimum_score_to_mail", 70)
    )
    scored = fnc.score_items(raw_items, minimum_score=min_score, stats=stats)

    window = int(config.get("scoring", {}).get("dedupe_window_hours", 48))
    ledger_file = ledger_path or os.environ.get(
        "CARELAND_NEWS_LEDGER_PATH", "logs/careland_news_ledger.jsonl"
    )
    ledger_uri = gcs_ledger_uri or os.environ.get("CARELAND_NEWS_LEDGER_GCS_URI") or None
    seen = fnc.load_ledger_keys(
        now=active_now, window_hours=window, ledger_path=ledger_file, gcs_uri=ledger_uri
    )
    # タイトルに「New」バッジや日付が付いて揺れると key だけでは重複を取りこぼすため、
    # 送信済み URL でも重複を弾く（後方互換: ledger には以前から url がある）。
    seen_urls = fnc.load_ledger_urls(
        now=active_now, window_hours=window, ledger_path=ledger_file, gcs_uri=ledger_uri
    )
    unseen = [
        c for c in scored
        if c.dedupe_key not in seen
        and fnc.normalize_dedupe_url(c.url) not in seen_urls
    ]
    if stats is not None:
        stats.deduped_items = len(scored) - len(unseen)
    # 上位 max_candidates 件が Google News の解決失敗(429)等で全滅すると候補0になっていた。
    # そこで「成功が max_candidates 件たまるまで新着を順に処理」する。ただし resolve リクエストが
    # 際限なく増えないよう、試行件数に上限（max_candidates の数倍）を設ける。
    backfill_cap = int(config.get("scoring", {}).get(
        "max_candidate_attempts", max(max_candidates * 5, 40)))
    fresh = unseen[:backfill_cap]

    judgment_cfg = config.get("judgment", {})
    max_ai = int(judgment_cfg.get("max_ai_calls_per_run", max_candidates))
    do_ai = run_judgment and bool(judgment_cfg.get("enabled", True))

    wp_cfg = config.get("wordpress", {})
    breaking_id = int(wp_cfg.get("breaking_category_id", 55))
    category_map = {k: int(v) for k, v in (wp_cfg.get("category_map") or {}).items()}
    default_index = bool(wp_cfg.get("default_index", False))

    candidates: list[CarelandCandidate] = []
    ai_calls = 0
    # 同一記事が複数キーワードフィードに現れるため、解決後の実URLで run 内重複も弾く。
    # 転載（Yahoo↔元媒体）は実URLが違うので、正規化タイトルでも重複を弾く（重複コンテンツ防止）。
    run_seen_urls: set[str] = set()
    run_seen_titles: set[str] = set()

    def _norm_title(t: str) -> str:
        import re as _re
        base = _re.sub(r"[\s　…\"'《》「」『』【】\[\]()（）|｜:：\-–—]", "", (t or ""))
        return base[:40].lower()
    # Google News 解決(429リトライ)で実行が長引きすぎないよう実時間バジェットを設ける。
    resolve_deadline = time.monotonic() + float(
        config.get("scoring", {}).get("max_resolve_seconds", 300))
    for fin in fresh:
        # 成功候補が必要数に達したら打ち切り（残りの新着は次回以降にまわす）。
        if len(candidates) >= max_candidates:
            break
        # 時間切れ。これ以上の新着探索は次回以降にまわし、今ある候補で送る。
        if time.monotonic() > resolve_deadline:
            LOG.info("careland_resolve_time_budget_reached candidates=%s", len(candidates))
            break
        lane = fin.post_lane
        label = lane_label(config, lane)
        default_decision = lane_default_decision(config, lane)
        # Googleニュースのラッパーリンクは元記事の実URLに解決する（適法引用・canonical用）。
        # 解決できれば実URL＋実媒体名を使い、できなければ元のまま degrade（記事は出るが引用は付かない）。
        item_url = fin.url
        item_title = fin.title
        source_name = fin.source_name
        if is_google_news_url(fin.url):
            resolved = resolve_google_news_url(fin.url, timeout=timeout_seconds)
            clean_title, publisher = split_publisher_from_title(fin.title)
            if resolved:
                item_url = resolved
                item_title = clean_title or fin.title
                if publisher:
                    source_name = publisher
                LOG.info("gnews_resolved %s -> %s (媒体=%s)",
                         fin.url[:48], item_url[:64], source_name)
            else:
                # 解決できないと適法引用も出典(実媒体)も付かない＝引用記事として成立しない。
                # ラッパーURLの低品質記事は作らずスキップ（候補は他キーワードに大量にある）。
                LOG.info("gnews_resolve_skip url=%s", fin.url[:48])
                continue
        # 解決後の実URLで run 内重複を弾く（複数キーワードに同一記事が出るため）。
        norm_url = fnc.normalize_dedupe_url(item_url)
        norm_title = _norm_title(item_title)
        if norm_url in run_seen_urls or (norm_title and norm_title in run_seen_titles):
            LOG.info("careland_run_dup_skip url=%s", item_url[:64])
            continue
        run_seen_urls.add(norm_url)
        if norm_title:
            run_seen_titles.add(norm_title)
        # 元ページを読む（ポスト文案の材料）＋ og:image（ヒーロー画像/アイキャッチ）。
        body_excerpt, hero_image_url = fetch_excerpt_and_image(
            item_url, item_title, timeout_seconds=timeout_seconds)
        use_ai = do_ai and ai_calls < max_ai
        if use_ai:
            ai_calls += 1
            verdict = judge_news(
                title=item_title, summary=fin.summary, source_name=source_name,
                url=item_url, lane=lane, lane_label=label,
                default_decision=default_decision, body_excerpt=body_excerpt, api_key=api_key,
            )
        else:
            from src.careland_news_judgment import fallback_verdict
            verdict = fallback_verdict(
                title=item_title, summary=fin.summary, source_name=source_name,
                url=item_url, lane=lane, lane_label=label, default_decision=default_decision,
                body_excerpt=body_excerpt,
            )
        # AI・ITニュース(it_ai_trend)は記事化しない＝Xポスト候補のみ（ユーザー方針）。
        # judgment が x_article を返しても x_only に固定する。
        if lane == "it_ai_trend" and verdict.decision == "x_article":
            from dataclasses import replace as _dc_replace
            verdict = _dc_replace(verdict, decision="x_only")
        # 引用元が Googleニュース(ラッパー)/Yahoo!ニュース/有料記事で**実本文が取れない**ものは
        # 引用記事にしない（スカスカ記事になるため）。Xポスト候補(x_only)に留める。
        if verdict.decision == "x_article" and not has_quotable_body(body_excerpt):
            from dataclasses import replace as _dc_replace
            verdict = _dc_replace(verdict, decision="x_only")
            LOG.info("careland_article_skip_no_body url=%s src=%s", item_url[:64], source_name)
        article_title = ""
        article_html = ""
        want_index = False
        if verdict.decision == "x_article":
            draft = build_article_draft(
                verdict=verdict, title=item_title, summary=fin.summary,
                source_name=source_name, url=item_url, lane=lane, lane_label=label,
                breaking_id=breaking_id, category_map=category_map,
                default_index=default_index, slug_hint=fin.dedupe_key[:8],
                body_excerpt=body_excerpt, hero_image_url=hero_image_url,
            )
            article_title = draft.title
            article_html = draft.content
            want_index = draft.want_index

        candidates.append(
            CarelandCandidate(
                source_id=fin.source_id,
                source_name=source_name,
                post_lane=lane,
                lane_label=label,
                default_decision=default_decision,
                title=item_title,
                url=item_url,
                summary=fin.summary,
                score=fin.score,
                priority=fin.priority,
                dedupe_key=fin.dedupe_key,
                verdict=verdict,
                body_excerpt=body_excerpt,
                hero_image_url=hero_image_url,
                article_title=article_title,
                article_html=article_html,
                want_index=want_index,
            )
        )
    return CarelandBuildResult(candidates=candidates, stats=stats)


# --- mail composition (yoshilover 体裁: 560px 白カード + グラデ帯 + 全幅ボタン) ---

# yoshilover の publish-notice メールボタンと同値に統一
# (publish_notice_email_sender.py: max-width:300px / padding:13px 20px / radius:6px / font-size:15px / weight:700)。
_BTN = ("display:block;width:100%;max-width:300px;margin:0 auto 10px;padding:13px 20px;"
        "color:#ffffff;text-decoration:none;border-radius:6px;font-size:15px;"
        "font-weight:700;text-align:center;")

_DECISION_BADGE = {
    "x_article": ("#1b8a3e", "Xポスト＋記事候補"),
    "x_only": ("#1d9bf0", "Xポスト候補"),
    "weekly": ("#6b5bd2", "週次まとめ候補"),
    "hold": ("#b0852a", "保留（要確認）"),
    "discard": ("#9a9a9a", "破棄候補"),
}


def _card(inner_html: str) -> str:
    """560px 白角丸カード（yoshilover と同じ器）。"""
    return (
        '<tr><td align="center" style="padding:0 0 16px;">'
        '<table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);'
        'max-width:560px;width:100%;">'
        f'{inner_html}'
        '</table></td></tr>'
    )


def _wp_confirm_url(wp_admin_base: str, mode: str, *, post_id: int | None = None,
                    extra: dict[str, str] | None = None) -> str:
    """ログイン必須の WordPress 確認画面 URL。

    /wp-admin/admin-post.php?action=careland_news_confirm&mode=...&post=...
    nonce は確認画面(WP側)で発行するため、メールの URL には載せない（WPログインが関門）。
    """
    qs = f"action=careland_news_confirm&mode={quote(mode)}"
    if post_id:
        qs += f"&post={int(post_id)}"
    for key, value in (extra or {}).items():
        qs += f"&{key}={quote(value, safe='')}"
    return f"{wp_admin_base.rstrip('/')}/wp-admin/admin-post.php?{qs}"


def _wp_edit_url(wp_admin_base: str, post_id: int) -> str:
    return f"{wp_admin_base.rstrip('/')}/wp-admin/post.php?post={int(post_id)}&action=edit"


def _btn(href: str, label: str, bg: str) -> str:
    return f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener" style="{_BTN}background:{bg};">{escape(label)}</a>'


def _candidate_buttons(cand: CarelandCandidate, wp_admin_base: str | None,
                       fetcher_base: str | None = None) -> str:
    """判定に応じた承認ボタン群（全幅）。

    yoshilover と同じ「🚀 公開してX投稿画面へ」（公開エンドポイント /publish-and-tweet）を主導線にしつつ、
    careland 固有の index/noindex 出し分け・非公開化は WordPress(ログイン必須)の確認画面を併設する。
    """
    parts: list[str] = []
    # yoshilover と同じ公開導線: ワンクリックで draft→publish して X 投稿画面へ（自動投稿しない）。
    if fetcher_base and cand.post_id and cand.decision == "x_article":
        pub_url = build_publish_button_url(cand.post_id, fetcher_base)
        if pub_url:
            parts.append(_btn(pub_url, "🚀 公開してX投稿画面へ", "#1b8a3e"))
    # Xポスト(下書きのまま): サーバを介さずクライアント側で composer を開く（公開しない）
    parts.append(_btn(cand.x_intent_url(), "𝕏 下書きのままX投稿画面", "#000000"))
    if wp_admin_base:
        if cand.post_id and cand.decision == "x_article":
            parts.append(_btn(_wp_confirm_url(wp_admin_base, "publish_index", post_id=cand.post_id), "🚀 記事公開（index）", "#1b8a3e"))
            parts.append(_btn(_wp_confirm_url(wp_admin_base, "publish_noindex", post_id=cand.post_id), "🔒 noindex公開", "#2d7d9a"))
            parts.append(_btn(_wp_confirm_url(wp_admin_base, "unpublish", post_id=cand.post_id), "↩ 非公開化", "#b0852a"))
            parts.append(_btn(_wp_edit_url(wp_admin_base, cand.post_id), "✏️ WP編集画面で確認", "#555555"))
        weekly_extra = {} if cand.post_id else {"title": cand.title[:80], "url": cand.url, "src": cand.source_name[:40]}
        parts.append(_btn(_wp_confirm_url(wp_admin_base, "weekly", post_id=cand.post_id, extra=weekly_extra), "週次まとめに入れる", "#6b5bd2"))
    return "".join(parts)


def _x_post_intent_url(text: str, quote_url: str | None = None) -> str:
    """X intent。quote_url があれば url= を付けて“引用ポスト”にする（本文は自分のオリジナル）。"""
    params = "text=" + quote(text, safe="")
    if quote_url:
        params += "&url=" + quote(quote_url, safe="")
    return "https://twitter.com/intent/tweet?" + params


def _baseball_card(post: BaseballWelfarePost) -> str:
    """プロ野球×福祉の引用ポスト枠（巨人カラーのオレンジ帯）。

    SNSMONEY と同方式: @yoshilover6760 の元ツイを題材に福祉/IT就労観点のオリジナル本文を書き、
    intent の url= に元ツイを付けて“引用ポスト”にする（本文に @メンションは入れない）。
    """
    text = post.text
    if post.quote_tweet_url:
        btn = _btn(_x_post_intent_url(text, post.quote_tweet_url), "↻ 引用ポストで投稿", "#000000")
        # 引用される @yoshilover6760 の元ポストを、Xの引用カード風にメール内へ表示する。
        quote_body = (post.quote_tweet_text or "").strip()
        quote_preview = (
            '<div style="border:1px solid #cfd9e0;border-radius:12px;padding:10px 12px;margin:10px 0 2px;background:#f7f9fa;">'
            '<div style="color:#657786;font-size:12px;margin-bottom:4px;">引用元 ・ @yoshilover6760</div>'
            f'<div style="white-space:pre-wrap;font-size:13px;line-height:1.55;color:#39444d;">{escape(quote_body)}</div>'
            '</div>'
        ) if quote_body else ''
        source_link = (
            f'<tr><td style="padding:0 22px 16px;"><a href="{escape(post.quote_tweet_url, quote=True)}" '
            'target="_blank" rel="nofollow noopener" style="font-size:12px;color:#1d6fb8;">'
            '引用元（@yoshilover6760 の元ポスト）をXで開く</a></td></tr>'
        )
        note = '本文は自分のオリジナル投稿、下の「引用元」が @yoshilover6760 の元ポストです。ボタンで引用ポストになります（自動投稿しません）。'
    else:
        btn = _btn(_x_post_intent_url(text), "𝕏 投稿画面を開く", "#000000")
        quote_preview = ''
        source_link = ""
        note = '引用元が拾えなかったため通常ポストです（自動投稿しません）。'
    return (
        '<tr><td style="padding:16px 22px 4px;">'
        '<span style="display:inline-block;background:#e8740c;color:#fff;font-size:11px;'
        'font-weight:700;padding:3px 10px;border-radius:9999px;">プロ野球×福祉</span>'
        f'<span style="color:#999;font-size:11px;margin-left:8px;">{escape(post.source_note)}</span>'
        f'<p style="margin:10px 0 4px;font-size:13px;color:#666;">{escape(note)}</p>'
        '</td></tr>'
        '<tr><td style="padding:4px 22px 8px;">'
        '<div style="border:1px solid #f0e0d0;border-radius:14px;padding:14px;margin:6px 0;background:#fffaf5;">'
        '<div style="display:flex;align-items:center;margin-bottom:8px;">'
        '<div style="width:38px;height:38px;border-radius:50%;background:#e8740c;color:#fff;'
        'text-align:center;line-height:38px;font-weight:700;font-size:15px;">球</div>'
        '<div style="padding-left:10px;"><div style="font-weight:700;color:#0f1419;">発達障害・福祉ニュース</div>'
        '<div style="color:#657786;font-size:13px;">@nananana43219</div></div></div>'
        f'<div style="white-space:pre-wrap;font-size:15px;line-height:1.6;color:#0f1419;">{escape(text)}</div>'
        f'{quote_preview}'
        f'<div style="color:#657786;font-size:12px;margin-top:8px;">{len(text)}文字（本文）＋ 引用: @yoshilover6760 ・ 投稿はXの画面でご自身で実行します</div>'
        '</div></td></tr>'
        f'<tr><td align="center" style="padding:0 22px 14px;">{btn}</td></tr>'
        f'{source_link}'
    )


def _tweet_card(cand: CarelandCandidate) -> str:
    """実際に投稿される文面をツイート風に表示する。"""
    text = cand.x_post_text()
    return (
        '<div style="border:1px solid #e1e8ed;border-radius:14px;padding:14px;margin:10px 0;background:#ffffff;">'
        '<div style="display:flex;align-items:center;margin-bottom:8px;">'
        '<div style="width:38px;height:38px;border-radius:50%;background:#1b8a3e;color:#fff;'
        'text-align:center;line-height:38px;font-weight:700;font-size:15px;">福</div>'
        '<div style="padding-left:10px;"><div style="font-weight:700;color:#0f1419;">発達障害・福祉ニュース</div>'
        '<div style="color:#657786;font-size:13px;">@nananana43219</div></div></div>'
        f'<div style="white-space:pre-wrap;font-size:15px;line-height:1.6;color:#0f1419;">{escape(text)}</div>'
        f'<div style="color:#657786;font-size:12px;margin-top:8px;">{len(text)}文字 ・ 投稿はXの画面でご自身で実行します（自動投稿しません）</div>'
        '</div>'
    )


# 時間帯ラベル（SNSMONEY の TIME_BAND と同じ並び）。配信は朝8/12/15時 JST。
_TIME_BAND: tuple[tuple[range, str, str], ...] = (
    (range(5, 11), "朝", "🌅"),
    (range(11, 14), "昼", "🌞"),
    (range(14, 17), "午後", "📊"),
    (range(17, 21), "夕方", "🌆"),
)


def _careland_time_band(hour: int) -> tuple[str, str]:
    for rng, label, emoji in _TIME_BAND:
        if hour in rng:
            return label, emoji
    return "夜", "🌙"


def subject_purpose_label(candidates: list[CarelandCandidate]) -> str:
    """件名の用途ラベル（SNSMONEY の subject_purpose_label と同位置）。"""
    decisions = {c.verdict.decision for c in candidates}
    if "x_article" in decisions:
        return "制度+記事"
    if "x_only" in decisions:
        return "速報+X"
    if "weekly" in decisions:
        return "週まとめ"
    if "hold" in decisions:
        return "要確認"
    return "福祉+材料"


def build_mail_subject(candidates: list[CarelandCandidate], *, now: datetime) -> str:
    band, band_emoji = _careland_time_band(now.hour)
    purpose = subject_purpose_label(candidates)
    return (
        f"🟢🌱📮【福祉ニュース候補 {len(candidates)}件】"
        f"{band_emoji}{band}｜{purpose} {now.strftime('%H:%M')} JST | CARELAND"
    )


# yoshilover の _MAIL_CLASS_CONFIGS と同じ「種別ごとに別メール」方式。
#   x_article -> 【下書き】(公開確認: 🚀公開してX 主動線)  ／ x_only,hold -> 【投稿候補】(Xポスト用)
#   weekly -> 【まとめ】。件名は {prefix}{title} | CARELAND（yoshilover の build_subject と同形）。
_MAIL_CLASS = {
    "x_article": ("【下書き】", "新規 下書き"),
    "x_only": ("【投稿候補】", "X 投稿候補"),
    "hold": ("【要確認】", "要確認"),
    "weekly": ("【まとめ】", "週次まとめ候補"),
}


def _mail_class(decision: str) -> tuple[str, str]:
    return _MAIL_CLASS.get(decision, ("【投稿候補】", "X 投稿候補"))


def build_candidate_subject(cand: "CarelandCandidate", *, now: datetime) -> str:
    prefix, _ = _mail_class(cand.decision)
    title = (cand.article_title or cand.title or "").strip()
    if len(title) > 80:
        title = title[:79] + "…"
    return f"{prefix}{title} | CARELAND"


# yoshilover build_body_html_per_post と同じボタン体裁（max-width300/padding13 20/radius6/font15/weight700）。
def _post_btn(href: str, label: str, *, bg: str, fg: str = "#ffffff",
              border: str | None = None, font: int = 15, pad: str = "13px 20px") -> str:
    border_css = f"border:1px solid {border};" if border else "border:0;"
    return (
        '<tr><td align="center" style="padding:0 22px 14px;">'
        f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener" '
        'style="display:inline-block;width:100%;max-width:300px;'
        f'padding:{pad};background:{bg};color:{fg};text-decoration:none;'
        f'border-radius:6px;font-size:{font}px;font-weight:700;text-align:center;{border_css}">'
        f'{label}</a></td></tr>'
    )


def _excerpt_block(label: str, text: str, *, accent: str = "#1b8a3e") -> str:
    """yoshilover の「📄 本文(抜粋)」ブロックと同構造（緑左帯）。"""
    body = (text or "").strip()
    if not body:
        return ""
    paras = []
    for p in body.split("\n\n"):
        p = p.strip()
        if not p:
            continue
        paras.append('<p style="margin:0 0 14px;font-size:15px;line-height:1.85;'
                     f'color:#1a1a1a;word-break:break-word;">{escape(p).replace(chr(10), "<br>")}</p>')
    if not paras:
        return ""
    paras[-1] = paras[-1].replace("margin:0 0 14px", "margin:0", 1)
    return (
        '<tr><td style="padding:6px 22px 22px;">'
        f'<div style="background:#f7f9f7;border-left:4px solid {accent};padding:18px 20px;border-radius:4px;">'
        '<p style="margin:0 0 12px;font-size:11px;line-height:1.4;color:#566;font-weight:700;'
        f'letter-spacing:0.6px;">{label}</p>{"".join(paras)}</div></td></tr>'
    )


def compose_candidate_mail(
    cand: "CarelandCandidate",
    *,
    now: datetime,
    idx: int = 1,
    wp_admin_base: str | None = None,
    fetcher_base: str | None = None,
    share_enabled: bool = False,
    share_bucket: str = "",
    run_id: str = "",
) -> tuple[str, str, str, list[InlineImage]]:
    """候補1件＝1通。yoshilover build_body_html_per_post と同じカード仕様（careland 緑＋ペルソナ）。

    x_article=【下書き】(公開確認: 📰記事を見る→📱画像でX→🚀公開してX→✏️WP編集)、
    x_only/hold=【投稿候補】(Xポスト文案＋𝕏投稿＋📱画像でX、公開ボタン無し)。
    """
    v = cand.verdict
    # x_article でも下書きが未作成(post_id無し)なら公開できない＝実質「投稿候補」。
    # 件名クラスと本文レイアウトを is_draft で必ず一致させる（件名【下書き】×本文投稿候補の食い違いを防ぐ）。
    is_draft = cand.decision == "x_article" and bool(cand.post_id)
    if is_draft:
        effective_decision = "x_article"
    elif cand.decision in ("hold", "weekly"):
        effective_decision = cand.decision
    else:
        effective_decision = "x_only"
    prefix, class_label = _mail_class(effective_decision)
    title_for_subject = (cand.article_title or cand.title or "").strip()
    if len(title_for_subject) > 80:
        title_for_subject = title_for_subject[:79] + "…"
    subject = f"{prefix}{title_for_subject} | CARELAND"
    title = (cand.article_title or cand.title or "").strip()
    url = cand.url or v.official_url or ""

    inline_images: list[InlineImage] = []

    # 画像プレビュー＋「📱 画像つきでX」共有ボタン（share 有効時。yoshilover image_preview と同位置）。
    image_preview_html = ""
    share_btn_html = ""
    if cand.decision in _CARD_CATEGORY:
        png = _card_image_bytes(cand)
        if png:
            cid = f"carecard{idx}@careland"
            inline_images.append(InlineImage(content_id=cid, data=png, mime_subtype="png",
                                             filename=f"careland-card-{idx}.png"))
            image_preview_html = (
                '<tr><td align="center" style="padding:0 22px 14px;">'
                f'<img src="cid:{cid}" alt="{escape(title)}" '
                'style="display:block;width:100%;max-width:300px;border-radius:6px;border:1px solid #d7e4dc;" />'
                '</td></tr>'
            )
            if share_enabled and run_id:
                key = cshare.blob_key(run_id, idx)
                if cshare.upload_card_to_gcs(png, bucket_name=share_bucket, key=key):
                    surl = cshare.build_share_button_url(key, fetcher_base=fetcher_base,
                                                         post_text=cand.x_post_text(), post_url="")
                    if surl:
                        share_btn_html = _post_btn(surl, "📱 画像つきで X に投稿 (おすすめ)", bg="#ef6c00")

    # ボタン群（種別で出し分け＝yoshilover の class→action と同じ思想）
    buttons = ""
    if is_draft:
        # 【下書き】公開確認: 記事を見る→画像でX→公開してX→WP編集
        buttons += _post_btn(url, "📰 元記事を見る", bg="#003da5")
        buttons += share_btn_html
        if fetcher_base:
            pub = build_publish_button_url(cand.post_id, fetcher_base)
            if pub:
                buttons += _post_btn(pub, "🚀 公開してX投稿画面へ", bg="#1b8a3e")
        if wp_admin_base:
            buttons += _post_btn(_wp_edit_url(wp_admin_base, cand.post_id),
                                 "✏️ WP編集画面で確認", bg="#ffffff", fg="#003da5",
                                 border="#003da5", font=13, pad="11px 20px")
    else:
        # 【投稿候補】Xポスト用: 𝕏投稿→画像でX→元記事
        buttons += _post_btn(cand.x_intent_url(), "𝕏 投稿画面を開く", bg="#000000")
        buttons += share_btn_html
        buttons += _post_btn(url, "📰 元記事を見る", bg="#003da5")

    # 本文/抜粋ブロック: 下書き=本文抜粋、投稿候補=Xポスト文案。
    if is_draft:
        excerpt = _excerpt_block("📄 本文(抜粋)", cand.body_excerpt)
    else:
        excerpt = _excerpt_block("𝕏 投稿文案（このままコピペ可）", cand.x_post_text())

    text_body = "\n".join([
        f"{prefix}{title}",
        f"判定: {DECISION_LABEL.get(cand.decision, cand.decision)}（{v.source}） 出所={cand.source_name}",
        f"対象: {v.audience or '当事者・家族・支援者'}",
        "",
        ("--- 本文(抜粋) ---" if is_draft else "--- Xポスト文案 ---"),
        (cand.body_excerpt if is_draft else cand.x_post_text()),
        "",
        f"元記事: {url}",
        ("公開してX: " + (build_publish_button_url(cand.post_id, fetcher_base) or "")
         if is_draft and fetcher_base else f"X投稿画面: {cand.x_intent_url()}"),
        "",
        "AIは公開・投稿しません。最終判断はあなたが行います。",
    ])

    html_body = (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#eef1ee;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'Hiragino Sans\',sans-serif;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#eef1ee;padding:20px 0;"><tr><td align="center">'
        '<table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);max-width:560px;width:100%;">'
        # ヘッダ帯（careland 緑）
        '<tr><td style="padding:18px 22px 14px;background:linear-gradient(135deg,#34b36b 0%,#1b8a3e 100%);border-radius:8px 8px 0 0;">'
        '<p style="margin:0;font-size:18px;line-height:1.3;font-weight:700;color:#ffffff;letter-spacing:0.5px;">発達障害・福祉ニュース</p>'
        '<p style="margin:4px 0 0;font-size:11px;line-height:1.4;color:#e6f4ea;letter-spacing:0.4px;">CARE LAND ＠nananana43219</p>'
        '</td></tr>'
        # タイトル節
        '<tr><td style="padding:22px 22px 8px;">'
        f'<p style="margin:0 0 6px;font-size:11px;line-height:1.4;color:#888;font-weight:700;letter-spacing:0.5px;">📝 {escape(class_label)}</p>'
        f'<p style="margin:0 0 14px;font-size:17px;line-height:1.5;font-weight:700;color:#1a1a1a;">{escape(title)}</p>'
        f'<p style="margin:0 0 18px;font-size:12px;line-height:1.4;color:#666;word-break:break-all;">🔗 {escape(url)}</p>'
        '</td></tr>'
        f'{excerpt}'
        f'{image_preview_html}'
        f'{buttons}'
        # フッタ帯
        '<tr><td style="padding:14px 22px 20px;border-top:1px solid #eee;background:#fafafa;border-radius:0 0 8px 8px;">'
        '<p style="margin:0;font-size:13px;line-height:1.5;color:#1b8a3e;text-align:center;font-weight:700;">発達障害・福祉ニュース</p>'
        '<p style="margin:4px 0 0;font-size:11px;line-height:1.5;color:#888;text-align:center;">'
        'CARE LAND ｜ AIは自動公開・自動投稿しません。最終判断はあなたが行います。</p>'
        '</td></tr>'
        '</table></td></tr></table></body></html>'
    )
    return subject, text_body, html_body, inline_images


def compose_baseball_mail(
    post: BaseballWelfarePost, *, now: datetime,
) -> tuple[str, str, str, list[InlineImage]]:
    """プロ野球×福祉の引用ポストを 1 通（【投稿候補】）で送る。careland 固有枠。"""
    subject = f"【投稿候補】プロ野球×福祉（引用ポスト） {now.strftime('%H:%M')} JST | CARELAND"
    text_body = "\n".join([
        "【投稿候補】プロ野球×福祉（引用ポスト）",
        post.source_note,
        "--- Xポスト文案（本文・オリジナル） ---",
        post.text,
        (f"引用元(@yoshilover6760): {post.quote_tweet_url}" if post.quote_tweet_url else "引用元: （拾えず通常ポスト）"),
        "",
        "AIは公開・投稿しません。最終判断はあなたが行います。",
    ])
    html_body = (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#eef1ee;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'Hiragino Sans\',sans-serif;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#eef1ee;padding:20px 0;"><tr><td align="center">'
        '<table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);max-width:560px;width:100%;">'
        f'{_baseball_card(post)}'
        '</table></td></tr></table></body></html>'
    )
    return subject, text_body, html_body, []


def _evergreen_card(post: BaseballWelfarePost) -> str:
    """福祉エバーグリーン枠（新着0件の便の常設ポスト）。careland グリーンの通常ポストカード。"""
    text = post.text
    btn = _btn(_x_post_intent_url(text), "𝕏 投稿画面を開く", "#000000")
    note = '新着ニュースが無い便のための常設ポストです（引用元なしの通常ポスト・自動投稿しません）。'
    return (
        '<tr><td style="padding:16px 22px 4px;">'
        '<span style="display:inline-block;background:#1b8a3e;color:#fff;font-size:11px;'
        'font-weight:700;padding:3px 10px;border-radius:9999px;">福祉・常設ポスト</span>'
        f'<span style="color:#999;font-size:11px;margin-left:8px;">{escape(post.source_note)}</span>'
        f'<p style="margin:10px 0 4px;font-size:13px;color:#666;">{escape(note)}</p>'
        '</td></tr>'
        '<tr><td style="padding:4px 22px 8px;">'
        '<div style="border:1px solid #cfe8d6;border-radius:14px;padding:14px;margin:6px 0;background:#f6fbf7;">'
        '<div style="display:flex;align-items:center;margin-bottom:8px;">'
        '<div style="width:38px;height:38px;border-radius:50%;background:#1b8a3e;color:#fff;'
        'text-align:center;line-height:38px;font-weight:700;font-size:15px;">福</div>'
        '<div style="padding-left:10px;"><div style="font-weight:700;color:#0f1419;">発達障害・福祉ニュース</div>'
        '<div style="color:#657786;font-size:13px;">@nananana43219</div></div></div>'
        f'<div style="white-space:pre-wrap;font-size:15px;line-height:1.6;color:#0f1419;">{escape(text)}</div>'
        f'<div style="color:#657786;font-size:12px;margin-top:8px;">{len(text)}文字 ・ 投稿はXの画面でご自身で実行します（自動投稿しません）</div>'
        '</div></td></tr>'
        f'<tr><td align="center" style="padding:0 22px 14px;">{btn}</td></tr>'
    )


def compose_evergreen_mail(
    post: BaseballWelfarePost, *, now: datetime,
) -> tuple[str, str, str, list[InlineImage]]:
    """福祉エバーグリーンのポストを 1 通（【投稿候補】）で送る。新着0件の便の保険。"""
    subject = f"【投稿候補】福祉の常設ポスト {now.strftime('%H:%M')} JST | CARELAND"
    text_body = "\n".join([
        "【投稿候補】福祉の常設ポスト（新着ニュースが無い便）",
        post.source_note,
        "--- Xポスト文案（本文・オリジナル） ---",
        post.text,
        "",
        "AIは公開・投稿しません。最終判断はあなたが行います。",
    ])
    html_body = (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#eef1ee;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'Hiragino Sans\',sans-serif;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#eef1ee;padding:20px 0;"><tr><td align="center">'
        '<table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);max-width:560px;width:100%;">'
        f'{_evergreen_card(post)}'
        '</table></td></tr></table></body></html>'
    )
    return subject, text_body, html_body, []


def compose_mail(
    candidates: list[CarelandCandidate],
    *,
    now: datetime,
    stats: fnc.FinanceBuildStats,
    wp_admin_base: str | None = None,
    baseball_post: BaseballWelfarePost | None = None,
) -> tuple[str, str, str, list[InlineImage]]:
    """本文同梱の確認メール (subject, text_body, html_body, inline_images) を作る。

    inline_images は各 Xポスト候補の「文字で訴える」緑カード（cid 埋め込み）。
    """
    date_label = now.strftime("%Y-%m-%d %H:%M")
    subject = build_mail_subject(candidates, now=now)

    text_lines = [
        f"発達障害・福祉ニュース候補 ({date_label} JST)",
        "",
        "AIは公開・投稿しません。最終判断はあなたが行います。",
        "医療・診断・薬・障害年金の可否・法律判断は断定しないでください。",
        "",
        f"sources={stats.loaded_sources} raw={stats.raw_items} scored={stats.scored_items} deduped={stats.deduped_items}",
        "",
    ]

    # ヘッダ帯（careland グリーン）
    header_card = _card(
        '<tr><td style="padding:18px 22px 14px;background:linear-gradient(135deg,#34b36b 0%,#1b8a3e 100%);'
        'border-radius:10px 10px 0 0;">'
        '<p style="margin:0;font-size:18px;line-height:1.3;font-weight:700;color:#ffffff;letter-spacing:0.5px;">発達障害・福祉ニュース</p>'
        '<p style="margin:4px 0 0;font-size:11px;line-height:1.4;color:#e6f4ea;letter-spacing:0.4px;">ニュース候補通知</p>'
        '</td></tr>'
        '<tr><td style="padding:16px 22px 6px;">'
        f'<p style="margin:0 0 8px;font-size:12px;color:#888;">{escape(date_label)} JST ・ 候補 {len(candidates)}件</p>'
        '<p style="margin:0;font-size:12px;line-height:1.6;color:#666;background:#f7f9f7;border-left:4px solid #1b8a3e;padding:10px 12px;border-radius:4px;">'
        'AIは公開・投稿しません。最終判断はあなたが行います。<br>'
        '医療・診断・薬・障害年金の可否・法律判断は断定しないでください。</p>'
        '</td></tr>'
    )
    cards = [header_card]
    inline_images: list[InlineImage] = []
    # share-x-cand（図カードを画像つきでXにポスト）の設定。env が揃わなければ無効＝
    # 従来の X intent（本文のみ）ボタンにフォールバック。
    share_bucket, share_fetcher_base, share_enabled = cshare.resolve_share_x_config()
    run_id = now.strftime("%Y%m%d-%H%M%S")

    if not candidates:
        text_lines.append("候補はありません。")
        cards.append(_card('<tr><td style="padding:18px 22px;color:#666;">候補はありません。</td></tr>'))

    for idx, cand in enumerate(candidates, 1):
        v = cand.verdict
        decision_label = DECISION_LABEL.get(cand.decision, cand.decision)
        badge_color, _ = _DECISION_BADGE.get(cand.decision, ("#777", decision_label))
        flags = " / ".join(v.risk_flags) if v.risk_flags else "なし"
        text_lines.extend([
            f"■ 候補 {idx}: {cand.title}",
            f"判定: {decision_label}（{v.source}） score={cand.score} 出所={cand.source_name}",
            f"誰に関係: {v.audience}",
            f"確認すべき点: {v.where_to_check}",
            f"注意フラグ: {flags}",
            "--- Xポスト文案 ---",
            cand.x_post_text(),
            f"X投稿画面: {cand.x_intent_url()}",
            f"元URL: {cand.url}",
            "",
        ])
        if cand.article_html:
            text_lines.insert(len(text_lines) - 1, "[記事候補] " + cand.article_title)

        # 記事候補プレビュー（x_article のみ。ホームページは後回し前提で折りたたみ表示）
        article_preview_html = ""
        if cand.article_html:
            article_preview_html = (
                '<tr><td style="padding:0 22px 14px;">'
                '<details style="border:1px dashed #cfd8d0;border-radius:8px;padding:10px;background:#fbfdfb;">'
                f'<summary style="cursor:pointer;font-weight:700;color:#1b8a3e;font-size:13px;">記事候補プレビュー（後で公開可・index={"許可候補" if cand.want_index else "noindex"}）</summary>'
                f'<div style="margin-top:8px;font-size:14px;line-height:1.7;color:#333;">{cand.article_html}</div>'
                '</details></td></tr>'
            )

        # 「文字で訴える」図カード（Xに出す候補のみ）。メールにインライン表示し、
        # 投稿時に人間がこの画像を X の作成画面へドラッグ添付する（自動投稿はしない）。
        card_image_html = ""
        if cand.decision in _CARD_CATEGORY:
            png = _card_image_bytes(cand)
            if png:
                cid = f"carecard{idx}@careland"
                inline_images.append(InlineImage(
                    content_id=cid, data=png, mime_subtype="png",
                    filename=f"careland-card-{idx}.png",
                ))
                # 図カードを「画像つきでポスト」できるボタン（他レーンと同じ share-x-cand）。
                # GCS にアップ → 署名つき /share-x-cand URL → Web Share API で画像＋本文を X へ。
                share_btn_html = ""
                if share_enabled and png:
                    key = cshare.blob_key(run_id, idx)
                    if cshare.upload_card_to_gcs(png, bucket_name=share_bucket, key=key):
                        share_url = cshare.build_share_button_url(
                            key, fetcher_base=share_fetcher_base,
                            post_text=cand.x_post_text(), post_url="",
                        )
                        if share_url:
                            share_btn_html = (
                                f'<a href="{escape(share_url, quote=True)}" '
                                'rel="nofollow noopener" target="_blank" '
                                'style="display:block;width:100%;max-width:340px;margin:10px auto 2px;'
                                'padding:12px 16px;background:#0f1419;color:#fff;text-decoration:none;'
                                'border-radius:8px;font-size:14px;font-weight:700;text-align:center;">'
                                '𝕏 画像つきでポスト</a>'
                                '<div style="font-size:11px;color:#999;text-align:center;">'
                                'スマホ=画像ごとXアプリへ／PC=画像を保存して添付</div>'
                            )
                drag_note = (
                    '↑スマホは長押し保存、PCはドラッグで添付できます'
                    if not share_btn_html
                    else '図カード（下のボタンでそのままポストできます）'
                )
                card_image_html = (
                    '<tr><td style="padding:4px 22px 8px;">'
                    f'<img src="cid:{cid}" alt="{escape(cand.title)}" '
                    'width="320" style="width:320px;max-width:100%;height:auto;border-radius:12px;'
                    'border:1px solid #d7e4dc;display:block;" draggable="true">'
                    f'<div style="font-size:11px;color:#999;margin-top:4px;">{drag_note}</div>'
                    f'{share_btn_html}</td></tr>'
                )

        inner = (
            '<tr><td style="padding:16px 22px 4px;">'
            f'<span style="display:inline-block;background:{badge_color};color:#fff;font-size:11px;'
            f'font-weight:700;padding:3px 10px;border-radius:9999px;">{escape(decision_label)}</span>'
            f'<span style="color:#999;font-size:11px;margin-left:8px;">{escape(cand.source_name)} ・ {escape(v.source)}判定</span>'
            f'<p style="margin:10px 0 4px;font-size:16px;line-height:1.5;font-weight:700;color:#1a1a1a;">{escape(cand.title)}</p>'
            f'<p style="margin:0 0 4px;font-size:12px;color:#666;">対象: {escape(v.audience or "当事者・家族・支援者")}</p>'
            f'<p style="margin:0 0 4px;font-size:12px;color:#666;">確認点: {escape(v.where_to_check or "公式情報を確認")}</p>'
            f'<p style="margin:0;font-size:12px;color:#b0852a;">注意: {escape(flags)}</p>'
            '</td></tr>'
            f'<tr><td style="padding:4px 22px 8px;">{_tweet_card(cand)}</td></tr>'
            f'{card_image_html}'
            f'<tr><td align="center" style="padding:0 22px 14px;">{_candidate_buttons(cand, wp_admin_base, fetcher_base=share_fetcher_base)}</td></tr>'
            f'<tr><td style="padding:0 22px 16px;"><a href="{escape(cand.url, quote=True)}" '
            'rel="nofollow noopener" target="_blank" style="font-size:12px;color:#1d6fb8;">元記事・公式を開く</a></td></tr>'
            f'{article_preview_html}'
        )
        cards.append(_card(inner))

    # プロ野球×福祉 の引用ポスト枠（毎回1個。本文オリジナル＋@yoshilover6760 の元ツイを引用）
    if baseball_post is not None:
        text_lines.extend([
            "■ プロ野球×福祉（引用ポスト候補）",
            baseball_post.source_note,
            "--- Xポスト文案（本文・オリジナル） ---",
            baseball_post.text,
            (f"引用元(@yoshilover6760): {baseball_post.quote_tweet_text or ''}".rstrip()
             if baseball_post.quote_tweet_url else "引用元: （拾えず通常ポスト）"),
            (f"引用元URL: {baseball_post.quote_tweet_url}" if baseball_post.quote_tweet_url else ""),
            "",
        ])
        cards.append(_card(_baseball_card(baseball_post)))

    # フッタ帯
    cards.append(_card(
        '<tr><td style="padding:14px 22px 18px;background:#fafafa;border-radius:10px;">'
        '<p style="margin:0;font-size:13px;line-height:1.5;color:#1b8a3e;text-align:center;font-weight:700;">発達障害・福祉ニュース</p>'
        '<p style="margin:4px 0 0;font-size:11px;line-height:1.6;color:#999;text-align:center;">'
        '候補通知（自動公開・自動投稿はしません）<br>'
        '公開/noindex/非公開化/週次まとめは WordPress にログインした確認画面のボタンでのみ実行されます。'
        '破棄は WordPress で下書きを削除してください。</p>'
        '</td></tr>'
    ))

    html_body = (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#eef1ee;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'Hiragino Sans\',sans-serif;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="background:#eef1ee;padding:20px 0;"><tr><td align="center">'
        '<table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;width:100%;">'
        f'{"".join(cards)}'
        '</table></td></tr></table></body></html>'
    )
    return subject, "\n".join(text_lines), html_body, inline_images


__all__ = [
    "CarelandCandidate",
    "CarelandBuildResult",
    "build_candidates",
    "compose_mail",
    "compose_candidate_mail",
    "compose_baseball_mail",
    "compose_evergreen_mail",
    "build_candidate_subject",
    "lane_label",
    "lane_default_decision",
    "DECISION_LABEL",
]
