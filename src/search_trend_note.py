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
from typing import Any, Optional

import requests

LOG = logging.getLogger("search_trend_note")

_TREND_RSS_URL = "https://trends.google.co.jp/trending/rss?geo=JP"
# Yahoo 公式スポーツ・トピックス RSS (2026-07-10 user「メジャーとプロ野球の
# トレンドがとんでない」: Google 急上昇は野球ゼロの時間帯が多い。Yahoo の
# 編集トピックスは毎時更新で野球ネタが常時あるため合流させる)
_YAHOO_SPORTS_TOPICS_RSS = "https://news.yahoo.co.jp/rss/topics/sports.xml"
_TIMEOUT_SECONDS = 5

# カテゴリ別 marker (2026-07-10 user「巨人だけでなくプロ野球とメジャーも」)。
# トレンド語側に含まれていれば roster 一致不要。
_GIANTS_MARKERS = ("巨人", "ジャイアンツ", "読売")
_NPB_MARKERS = (
    "プロ野球", "野球", "NPB", "セリーグ", "セ・リーグ", "パリーグ", "パ・リーグ",
    "甲子園", "オールスター", "球宴", "サヨナラ", "ホームラン", "ノーヒットノーラン",
    "完全試合", "阪神", "タイガース", "広島", "カープ", "中日", "ドラゴンズ",
    "ヤクルト", "スワローズ", "DeNA", "ベイスターズ", "横浜", "ソフトバンク",
    "ホークス", "日本ハム", "ファイターズ", "ロッテ", "マリーンズ", "楽天",
    "イーグルス", "西武", "ライオンズ", "オリックス", "バファローズ",
)
_MLB_MARKERS = (
    "MLB", "メジャー", "大谷翔平", "山本由伸", "鈴木誠也", "村上宗隆",
    "ドジャース", "パドレス", "ヤンキース", "メッツ", "カブス", "レッドソックス",
    "ダルビッシュ", "今永昇太", "菅野智之", "佐々木朗希", "dバックス",
)
# 後方互換 (旧 relevance 判定): 全カテゴリの和
_BASEBALL_MARKERS = _GIANTS_MARKERS + _NPB_MARKERS + _MLB_MARKERS


def categorize_trend_keyword(kw: str, roster: set[str]) -> str:
    """トレンド語のカテゴリ ("giants" / "mlb" / "npb" / "")。

    判定順: 巨人 (marker or roster 名) → MLB → NPB。roster 名一致は巨人扱い。
    """
    if any(mk in kw for mk in _GIANTS_MARKERS) or any(tok in kw for tok in roster):
        return "giants"
    if any(mk in kw for mk in _MLB_MARKERS):
        return "mlb"
    if any(mk in kw for mk in _NPB_MARKERS):
        return "npb"
    return ""

_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_TITLE_RE = re.compile(r"<title>([^<]+)</title>")
_TRAFFIC_RE = re.compile(r"<ht:approx_traffic>([^<]+)</ht:approx_traffic>")
_NEWS_TITLE_RE = re.compile(r"<ht:news_item_title>([^<]+)</ht:news_item_title>")
_NEWS_URL_RE = re.compile(r"<ht:news_item_url>([^<]+)</ht:news_item_url>")
_NEWS_SOURCE_RE = re.compile(r"<ht:news_item_source>([^<]+)</ht:news_item_source>")


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
        nt = _NEWS_TITLE_RE.search(item)
        nu = _NEWS_URL_RE.search(item)
        ns = _NEWS_SOURCE_RE.search(item)
        out.append({
            "keyword": keyword,
            "traffic": (tr.group(1).strip() if tr else ""),
            "news_title": (nt.group(1).strip() if nt else ""),
            "news_url": (nu.group(1).strip() if nu else ""),
            "news_source": (ns.group(1).strip() if ns else ""),
        })
    return out


def fetch_yahoo_sports_topics(timeout: float = _TIMEOUT_SECONDS) -> list[str]:
    """Yahoo スポーツ・トピックスの見出し list (最大20)。失敗は []。"""
    try:
        resp = requests.get(
            _YAHOO_SPORTS_TOPICS_RSS,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (yoshilover trend note)"},
        )
        resp.raise_for_status()
        titles = _TITLE_RE.findall(resp.text)
        # 先頭はチャンネル名 (Yahoo!ニュース・トピックス - スポーツ)
        return [t.strip() for t in titles if "Yahoo!ニュース" not in t][:20]
    except Exception as exc:  # noqa: BLE001
        LOG.info("yahoo topics fetch skip: %r", exc)
        return []


def merge_yahoo_topics_into_relevant(
    relevant: list[dict[str, str]],
    roster: set[str],
    *,
    topics: Optional[list[str]] = None,
    max_per_category: int = 5,
) -> None:
    """Yahoo トピックス見出しをカテゴリ判定して relevant に追記 (in-place)。

    Google 急上昇に野球ゼロの便でも 巨人/プロ野球/メジャー 行が埋まる。
    見出しはそのまま トレンド反応候補の素材 (news_title) にもなる。
    """
    if topics is None:
        topics = fetch_yahoo_sports_topics()
    counts: dict[str, int] = {}
    for t in relevant:
        cat = t.get("category") or ""
        counts[cat] = counts.get(cat, 0) + 1
    seen = {t.get("keyword") for t in relevant}
    for title in topics:
        cat = categorize_trend_keyword(title, roster)
        if not cat or title in seen:
            continue
        if counts.get(cat, 0) >= max_per_category:
            continue
        relevant.append({
            "keyword": title,
            "traffic": "",
            "category": cat,
            "news_title": title,
            "news_url": "",
            "news_source": "Yahoo!トピックス",
        })
        counts[cat] = counts.get(cat, 0) + 1
        seen.add(title)


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


def build_trend_note_and_boost(
    candidates: list[Any],
    *,
    gemini_api_key: str = "",
    dedup_set: set[str] | None = None,
    now_date: str = "",
) -> str:
    """関連トレンドの note 行を返し、一致候補の title に 🔥 を付ける (in-place)。

    ``gemini_api_key`` があれば追加で:
    - 語を含まない候補への自然な織り込み (weave_trends_into_candidates)
    - トレンド語主役の反応ポスト候補を 1 本 append (build_trend_reaction_candidate)
    """
    trends = fetch_jp_trends()
    if not trends:
        return ""
    roster = _giants_name_tokens()

    # カテゴリ付与 (巨人/プロ野球/メジャー、2026-07-10 user)。10位まで拾う。
    relevant: list[dict[str, str]] = []
    for t in trends:
        cat = categorize_trend_keyword(t["keyword"], roster)
        if cat:
            relevant.append({**t, "category": cat})
        if len(relevant) >= 10:
            break
    # Yahoo トピックス見出しを合流 (Google に野球ゼロの便でも各行を埋める)
    try:
        merge_yahoo_topics_into_relevant(relevant, roster)
    except Exception as exc:  # noqa: BLE001
        LOG.info("yahoo topics merge skip: %r", exc)
    if not relevant:
        LOG.info("search_trend: no baseball-related trend (total=%d)", len(trends))
        # 野球関連が無くても総合トップ10は参考表示する
        top10 = " / ".join(t["keyword"] for t in trends[:10])
        return f"📈 参考・総合急上昇TOP10: {top10}" if top10 else ""
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
    woven = 0
    if gemini_api_key:
        # 反応ポストを織り込みより先に作る (2026-07-10 user「毎時出るんでしょ」:
        # trend_weave の LLM 小枠を織り込みが先に食うと反応ポストが毎便出ない)
        try:
            reaction = build_trend_reaction_candidate(
                relevant,
                gemini_api_key=gemini_api_key,
                dedup_set=dedup_set,
                now_date=now_date,
            )
            if reaction is not None:
                candidates.append(reaction)
        except Exception as exc:  # noqa: BLE001 - 反応候補失敗は note のみで続行
            LOG.info("trend_react skip: %r", exc)
        try:
            woven = weave_trends_into_candidates(
                candidates, relevant, gemini_api_key=gemini_api_key
            )
        except Exception as exc:  # noqa: BLE001 - 織り込み失敗は note のみで続行
            LOG.info("trend_weave skip: %r", exc)
    def _cat_line(label: str, cat: str) -> str:
        items = [
            f"{t['keyword']}({t['traffic']})" if t["traffic"] else t["keyword"]
            for t in relevant if t.get("category") == cat
        ]
        return f"{label}: " + " / ".join(items) if items else ""

    note_lines = [
        line for line in (
            _cat_line("🔥 急上昇/巨人", "giants"),
            _cat_line("⚾ 急上昇/プロ野球", "npb"),
            _cat_line("🌍 急上昇/メジャー", "mlb"),
        ) if line
    ]
    note = "\n".join(note_lines)
    top10 = " / ".join(t["keyword"] for t in trends[:10])
    if top10:
        note += f"\n📈 参考・総合急上昇TOP10: {top10}"
    LOG.info(
        "search_trend: relevant=%d boosted=%d woven=%d total=%d",
        len(relevant), boosted, woven, len(trends),
    )
    return note


def _keyword_hits(keyword: str, haystack: str) -> bool:
    """トレンド語 (「パドレス 対 dバックス」等の複合語は token 分割) との一致。"""
    if keyword in haystack:
        return True
    tokens = [tok for tok in re.split(r"[\s　]+", keyword) if len(tok) >= 2]
    return bool(tokens) and all(tok in haystack for tok in tokens)


# ---------------------------------------------------------------------------
# トレンド語のポスト織り込み (2026-07-10 user「ポストに入れて自然にできないの？」)
# ---------------------------------------------------------------------------

# 2026-07-10 user「プレミアムプランだから長めで行ける」「毎時トレンド語を
# ポストに入れるでもいい」: 織り込みは2候補まで (LLM小枠3 = 反応1+織り込み2)、
# 追加は全角60字相当まで許容。
_WEAVE_MAX_PER_MAIL = 2
_WEAVE_MAX_EXTRA_WEIGHTED = 120


def weave_trends_into_candidates(
    candidates: list[Any],
    relevant: list[dict[str, str]],
    *,
    gemini_api_key: str,
) -> int:
    """トレンド語を候補の post_text へ自然に織り込む (in-place、最大2候補)。

    安全設計:
    - LLM の仕事は「この語が内容に本当に関係し、自然に入るなら1回だけ織り込む。
      無理なら NOCHANGE」。事実・数字・選手名の追加は prompt + gate の両方で禁止
    - gate: 語が入っていない / 新しい数字 / 新しい roster 名 / 長さ超過 → 元文のまま
    - 既に語を含む候補・post_text の無い候補は対象外
    """
    if not relevant or not gemini_api_key:
        return 0
    kws = [t["keyword"] for t in relevant]
    woven = 0
    for cand in candidates:
        if woven >= _WEAVE_MAX_PER_MAIL:
            break
        if str(getattr(cand, "metric", "")) == "TREND_REACTION":
            continue  # 反応ポストに別のトレンド語を重ね織りしない
        original = str(getattr(cand, "post_text", "") or "")
        if not original:
            continue
        hay = f"{getattr(cand, 'title', '')} {original}"
        missing = [k for k in kws if not _keyword_hits(k, hay)]
        if not missing:
            continue
        new_text, used_kw = _weave_llm(original, missing, gemini_api_key)
        if not new_text or not used_kw:
            continue
        if not _weave_gate_ok(original, new_text, used_kw):
            continue
        try:
            cand.post_text = new_text
            cand.title = f"🔥[急上昇入り: {used_kw}] {cand.title}"
        except Exception:  # noqa: BLE001 - frozen 等はスキップ
            continue
        woven += 1
        LOG.info("trend_weave applied kw=%s len=%d->%d", used_kw, len(original), len(new_text))
    return woven


def _weave_llm(
    original: str, keywords: list[str], gemini_api_key: str
) -> tuple[str, str]:
    """(織り込み後の本文, 使った語)。不適合・失敗は ("", "")。"""
    from google import genai

    from src.x_post_branding_gen import (
        _X_POST_DATA_LLM_MODEL,
        _llm_budget_guard,
        _x_post_generate_content,
    )

    try:
        _llm_budget_guard("trend_weave")
    except Exception as exc:  # noqa: BLE001 - 枠切れは静かにスキップ
        LOG.info("trend_weave budget skip: %r", exc)
        return "", ""
    prompt = "\n".join([
        "あなたは X 投稿の編集者です。下の投稿文に、候補ワードのうち投稿の内容に"
        "本当に関係する語が 1 つあれば、その語を自然な形で 1 回だけ織り込んで"
        "書き直してください。",
        "",
        "【ルール (最重要)】",
        "- 語を入れる以外の変更はしない。事実・数字・選手名・絵文字を追加しない。",
        "- 既存の数字・名前・意味を変えない。文体もそのまま。",
        "- どの語も内容に関係しない、または入れると不自然になる場合は"
        " NOCHANGE とだけ返す。",
        "",
        "候補ワード: " + " / ".join(keywords),
        "",
        "出力形式 (ラベル必須):",
        "KEYWORD: <使った語 (NOCHANGE 時は書かない)>",
        "POST: <書き直した本文 (NOCHANGE 時は NOCHANGE)>",
        "",
        "投稿文:",
        original,
    ])
    try:
        client = genai.Client(api_key=gemini_api_key)
        response = _x_post_generate_content(
            client,
            model=_X_POST_DATA_LLM_MODEL,
            contents=prompt,
            config={"temperature": 0.2},
        )
        raw = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001
        LOG.info("trend_weave llm skip: %r", exc)
        return "", ""
    if "NOCHANGE" in raw[:200] and "POST:" not in raw:
        return "", ""
    kw_m = re.search(r"KEYWORD:\s*(.+)", raw)
    post_m = re.search(r"POST:\s*(.+)", raw, re.DOTALL)
    if not kw_m or not post_m:
        return "", ""
    used_kw = kw_m.group(1).strip()
    new_text = post_m.group(1).strip()
    if new_text == "NOCHANGE" or used_kw not in keywords:
        return "", ""
    return new_text, used_kw


# トレンド反応の構成パターン (毎回ローテーション、2026-07-10 user)
_TREND_ARRANGEMENTS = (
    "冒頭は違和感・驚きのフック1行 → 見出しの事実 → フーガ風の読み → 論点で締め",
    "冒頭は読者への問いかけ1行 (「どう思う?」の直球は禁止) → 自分の立場 → 理由 → 展望",
    "冒頭は結論を半分だけ言う1行 (オチは後半まで引っ張る) → 経緯 → 事実 → 巨人ファンとしての本音",
    "冒頭は場面・空気の描写1行 → 何が起きたか → なぜ効くのか → 一言で締め",
    "冒頭はトレンド語を主語にした断定1行 → 根拠 → 逆側の見方に一言触れる → 自分はこう見る、で締め",
)


def build_trend_reaction_candidate(
    relevant: list[dict[str, str]],
    *,
    gemini_api_key: str,
    dedup_set: set[str] | None = None,
    now_date: str = "",
) -> Any:
    """急上昇トレンド + そのニュース見出しから独立の反応ポスト候補を 1 本作る。

    2026-07-10 user「毎時、野球トレンドキーワードをポストに入れるでもいい」:
    既存候補への織り込みと別に、トレンド語そのものを主役にした候補を出す。
    事実源 = Google Trends RSS が添える見出し (news_item_title) のみ。
    voice は既存 build_quote_rt_comment (フーガ+缶詰、捏造数字 gate 込み)。
    見出し無し / 生成失敗 / dedup 済みは None。
    """
    if not gemini_api_key:
        return None
    import hashlib as _hashlib

    from src.x_post_branding_gen import build_quote_rt_comment

    for t in relevant:
        kw = t.get("keyword") or ""
        news_title = t.get("news_title") or ""
        if not kw or not news_title:
            continue
        # dedup 粒度 = 時間 + 語 + 見出し (2026-07-10 user「同じ語は1日1回を
        # 省いて」): 同じ語でも毎時再度出す (voice は都度生成で文面は変わる)。
        # 15分毎の試合帯で全く同じ候補が4連続で並ぶのだけ防ぐ。
        # 見出しが更新されれば同じ時間内でも新候補。
        signature = "trendreact|" + _hashlib.sha1(
            f"{now_date}|{kw}|{news_title}".encode("utf-8")
        ).hexdigest()[:16]
        if dedup_set is not None and signature in dedup_set:
            continue
        source = t.get("news_source") or "Google Trends"
        fact = f"いま検索急上昇「{kw}」。{news_title}（{source}）"
        # 構成ローテーション (2026-07-10 user「プレミアムなんで長文で。
        # 毎回アレンジ変えて」): 時間+語で決定論的に構成を変え、テンプレ臭を防ぐ。
        arrangement = _TREND_ARRANGEMENTS[
            int(_hashlib.sha1(f"{now_date}|{kw}".encode("utf-8")).hexdigest(), 16)
            % len(_TREND_ARRANGEMENTS)
        ]
        try:
            post_text = (
                build_quote_rt_comment(
                    fact, "", "",
                    gemini_api_key=gemini_api_key,
                    subject="検索で急上昇中の野球トピック",
                    db_fact="", require_db_fact=False,
                    budget_site="trend_weave",
                    force_long=True,
                    extra_voice_note=(
                        f"いま検索で急上昇中の話題への反応ポスト (試合後の振り返り"
                        f"ではない)。トレンド語「{kw}」を本文に必ず1回そのまま入れる。"
                        "見出しにある事実だけで書き、見出しに無い数字・選手名・結果は"
                        f"作らない。今回の構成: {arrangement}。"
                        "文体は必ず です・ます調 (丁寧語) で統一する "
                        "(「〜だよな」「〜だわ」等のカジュアル語尾は今回は禁止。"
                        "丁寧だが堅すぎない、読みやすい情報ポストの文体)。"
                    ),
                ) or ""
            ).strip()
        except Exception as exc:  # noqa: BLE001
            LOG.info("trend_react llm skip: %r", exc)
            post_text = ""
        if not post_text or kw not in post_text:
            LOG.info("trend_react skip kw=%s reason=%s", kw, "no_voice" if not post_text else "kw_missing")
            continue
        from src.x_post_mail_lane import Candidate

        LOG.info("trend_react built kw=%s", kw)
        return Candidate(
            title=f"🔥トレンド反応｜{kw}（{t.get('traffic') or '急上昇'}）",
            metric="TREND_REACTION",
            period_label="検索急上昇",
            draft_text=f"{fact}\n(source: {t.get('news_url') or 'Google Trends'})",
            char_count=len(post_text),
            signature=signature,
            post_text=post_text,
            source_material_type="trend_reaction",
        )
    return None


def _weave_gate_ok(original: str, new_text: str, keyword: str) -> bool:
    """織り込み結果の決定論 gate。false = 元文のまま使う。"""
    if not _keyword_hits(keyword, new_text):
        LOG.info("trend_weave reject reason=keyword_missing")
        return False
    baseline = f"{original} {keyword}"
    new_numbers = set(re.findall(r"\d[\d,.]*", new_text)) - set(
        re.findall(r"\d[\d,.]*", baseline)
    )
    if new_numbers:
        LOG.info("trend_weave reject reason=new_numbers %s", sorted(new_numbers))
        return False
    for tok in _giants_name_tokens():
        if tok in new_text and tok not in baseline:
            LOG.info("trend_weave reject reason=new_name %s", tok)
            return False
    try:
        from src.x_post_mail_lane import x_weighted_len

        if x_weighted_len(new_text) > x_weighted_len(original) + _WEAVE_MAX_EXTRA_WEIGHTED:
            LOG.info("trend_weave reject reason=too_long")
            return False
    except Exception:  # noqa: BLE001 - 長さ検証不能時は plain len で代替
        if len(new_text) > len(original) + _WEAVE_MAX_EXTRA_WEIGHTED:
            return False
    return True
