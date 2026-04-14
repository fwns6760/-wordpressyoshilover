"""
x_post_generator.py — WP記事からXポスト文案を自動生成するCLIスクリプト

使用例:
    python3 src/x_post_generator.py --title "巨人3-2阪神" --url https://yoshilover.com/... --category 試合速報
    python3 src/x_post_generator.py --post-id 61088
"""

import sys
import re
import random
import argparse
import os
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

_vendor = str(ROOT / 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from wp_client import WPClient

TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_LOW_COST_AI_CATEGORIES = {"試合速報", "選手情報", "首脳陣"}
GEMINI_FLASH_MODEL = "gemini-2.5-flash"
GEMINI_FLASH_THINKING_BUDGET = 0


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def low_cost_mode_enabled() -> bool:
    return _env_flag("LOW_COST_MODE", False)


def _env_csv_set(name: str, default: set[str]) -> set[str]:
    value = os.environ.get(name, "")
    if not value.strip():
        return set(default)
    return {item.strip() for item in value.split(",") if item.strip()}


def x_post_ai_categories() -> set[str]:
    default = DEFAULT_LOW_COST_AI_CATEGORIES if low_cost_mode_enabled() else set()
    return _env_csv_set("X_POST_AI_CATEGORIES", default)


def should_use_ai_for_x_post(category: str) -> bool:
    enabled = x_post_ai_categories()
    if not enabled:
        return not low_cost_mode_enabled()
    return category in enabled


def get_x_post_ai_mode() -> str:
    default_mode = "none" if low_cost_mode_enabled() else "auto"
    mode = os.environ.get("X_POST_AI_MODE", default_mode).strip().lower()
    if mode in {"auto", "grok", "gemini", "none"}:
        return mode
    return default_mode


def allow_gemini_cli_for_x_post() -> bool:
    return _env_flag("X_POST_GEMINI_ALLOW_CLI", False)


# ──────────────────────────────────────────────────────────
# Gemini APIでツイート文生成
# ──────────────────────────────────────────────────────────
def generate_with_grok(title: str, category: str, score: str, summary: str = "") -> str:
    """Grok Responses API（Web+X検索）でXポスト文を生成。失敗時は空文字を返す。"""
    api_key = os.environ.get("GROK_API_KEY", "")
    if not api_key:
        return ""

    from datetime import date, datetime, timedelta
    today = date.today().strftime("%Y年%m月%d日")
    from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    to_date   = datetime.now().strftime("%Y-%m-%d")

    quotes = re.findall(r'「([^」]{5,60})」', summary)
    decimal_stats = re.findall(r'\.\d{3}', summary)
    quote_info = f"\n監督・選手コメント: 「{quotes[0]}」" if quotes else ""
    stats_info = f"\n記事内データ: {', '.join(decimal_stats[:5])}" if decimal_stats else ""
    article_excerpt = summary[:600] if summary else ""

    prompt = f"""あなたは読売ジャイアンツ専門のファンアカウントの中の人です。
今日は{today}です。Web検索とX検索で最新情報を調べ、以下のニュースについてXポストを作ってください。

ニュース: {title}{quote_info}{stats_info}
カテゴリ: {category}
記事抜粋: {article_excerpt}

【パターン（状況に合うものを1つ選ぶ）】

パターンA：感情爆発型（劇的な結果・逆転・好記録）
⚾️〇〇きたーー！！🔥
（1行で核心。2行目に補足）
→詳細はブログで👇

パターンB：発言引用型（監督・選手コメントがある場合）
選手名「発言の前半部分…
（続きが気になるところで切る）
→全文はブログで👇

パターンC：データ比較型（成績・ランキング）
■〇〇 今季 vs 昨季
今季：打率.XXX / HR X本 / 打点XX
昨季：打率.XXX / HR X本 / 打点XX
→データで見ると驚愕👇

パターンD：ランキング型
■セリーグ〇〇ランキング（最新）
1位　選手名　成績
3位　巨人選手名　成績
→全部ブログで解説👇

【絶対ルール】
・80〜140文字以内（短く一目で読める）
・冒頭は「きた！」「ヤバい！」「〜きたーー！！」など感情爆発 or データの核心を一撃
・⚾️🔥🙌‼️を冒頭か末尾に1〜2個
・X検索でバズっている巨人投稿のトーンを参考にする
・Web検索で{today}現在のデータを確認してから数字を使う（推測不可）
・発言は検索結果から実際のものを引用（作らない）
・ハッシュタグ・URLは含めない（後で追加）
・最後は「→〇〇はブログで👇」で自然に誘導
・出力はポスト本文のみ（説明・前置き不要）"""

    payload = json.dumps({
        "model": "grok-4-1-fast-reasoning",
        "input": [{"role": "user", "content": prompt}],
        "tools": [
            {"type": "web_search"},
            {"type": "x_search", "from_date": from_date, "to_date": to_date}
        ]
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.x.ai/v1/responses",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            data = json.load(res)
        # output[] から type==message を探す
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") == "output_text":
                        text = content.get("text", "").strip()
                        if text and len(text) > 20:
                            return text
        return ""
    except Exception:
        return ""


def generate_with_gemini(title: str, category: str, score: str, summary: str = "") -> str:
    """GeminiでXポスト文を生成。CLIは明示 opt-in 時のみ使う。"""
    import subprocess, shutil
    api_key = os.environ.get("GEMINI_API_KEY", "")

    # 記事本文から発言・数字を抽出
    quotes = re.findall(r'「([^」]{5,60})」', summary)
    decimal_stats = re.findall(r'\.\d{3}', summary)
    article_excerpt = summary[:600] if summary else ""
    quote_info = f"\n監督・選手コメント: 「{quotes[0]}」" if quotes else ""
    stats_info = f"\n記事内データ: {', '.join(decimal_stats[:5])}" if decimal_stats else ""

    from datetime import date
    today = date.today().strftime("%Y年%m月%d日")
    prompt = f"""あなたは読売ジャイアンツ専門のデータ系ファンアカウントの中の人です。
今日は{today}です。Web検索して{today}現在の最新データを調べ、以下のニュースについてXポストを作ってください。

【参照すべきデータサイト】
・NPB公式: npb.jp
・Baseball Reference Japan
・1point02.jp（セイバーメトリクス）
・スポーツナビ baseball.yahoo.co.jp
・日刊スポーツ nikkansports.com

ニュース: {title}{quote_info}{stats_info}
カテゴリ: {category}
記事抜粋: {article_excerpt}

【参考にするフォーマット（carp_buunスタイル）】

パターンA：ランキング型
■セリーグ〇〇ランキング（最新）
1位　選手名　成績
3位　巨人選手名　成績
...
※〇〇の直近成績や注目ポイント
→ブログで全部解説👇

パターンB：発言引用型
選手名or監督名「発言の前半部分…
※記者：（質問内容）
※阿部監督「（回答の途中で切る、続きはブログへ）
→全文はブログで👇

パターンC：比較・分析型
■〇〇 今季 vs 昨季
今季：打率.XXX / HR X本 / 打点XX
昨季：打率.XXX / HR X本 / 打点XX
→データで見ると驚愕👇

【絶対ルール】
・Web検索で2026年の最新データを確認してから数字を使う
・ランキング型は検索で確認できた場合のみ使う（推測・記憶で書かない）
・確認できない場合はパターンBの発言引用型かパターンCを使う
・発言は記事や検索結果から実際のものを引用する（作らない）
・ハッシュタグは含めない（後で追加する）
・URLは含めない（後で追加する）
・改行を使って見やすく整形する
・最後は「→〇〇はブログで👇」など自然な誘導で締める
・出力はポスト本文のみ（説明不要）"""

    # Gemini CLI は課金経路が見えにくいため、明示 opt-in の時だけ使う
    if allow_gemini_cli_for_x_post() and shutil.which("gemini"):
        try:
            result = subprocess.run(
                ["gemini", "-p", prompt],
                capture_output=True, text=True, timeout=90,
                env={**os.environ, "GEMINI_API_KEY": api_key}
            )
            text = result.stdout.strip()
            if text and len(text) > 20:
                return text
        except Exception:
            pass

    # フォールバック：Gemini API Flash
    if not api_key:
        return ""
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 512,
            "temperature": 0.9,
            "thinkingConfig": {"thinkingBudget": GEMINI_FLASH_THINKING_BUDGET},
        },
    }).encode("utf-8")
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FLASH_MODEL}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.load(res)
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text
    except Exception:
        return ""

# ──────────────────────────────────────────────────────────
# ハッシュタグ設定
# ──────────────────────────────────────────────────────────
REQUIRED_TAGS = ["#巨人", "#ジャイアンツ"]

CATEGORY_TAGS = {
    "試合速報":       ["#プロ野球", "#セリーグ"],
    "選手情報":       ["#プロ野球"],
    "首脳陣":         ["#プロ野球"],
    "ドラフト・育成": ["#ドラフト"],
    "OB・解説者":     ["#プロ野球OB"],
    "補強・移籍":     ["#FA"],
    "球団情報":       ["#東京ドーム"],
    "コラム":         ["#プロ野球"],
}

# 主要選手名 → ハッシュタグ
PLAYER_TAGS = {
    "岡本":      "#岡本和真",
    "坂本":      "#坂本勇人",
    "丸":        "#丸佳浩",
    "吉川":      "#吉川尚輝",
    "大城":      "#大城卓三",
    "山瀬":      "#山瀬慎之助",
    "戸郷":      "#戸郷翔征",
    "菅野":      "#菅野智之",
    "グリフィン": "#グリフィン",
    "ダルベック": "#ダルベック",
    "マタ":      "#マタ",
    "平山":      "#平山功太",
    "中山":      "#中山礼都",
    "阿部":      "#阿部慎之助",
    "則本":      "#則本昂大",
    "赤星":      "#赤星優志",
    "大勢":      "#大勢",
    "高橋礼":    "#高橋礼華",
    "井上":      "#井上温大",
    "門脇":      "#門脇誠",
    "泉口":      "#泉口友汰",
    "浅野":      "#浅野翔吾",
    "岡田":      "#岡田悠希",
}


def _extract_short_quote(text: str, max_chars: int = 22) -> str:
    quotes = re.findall(r'「([^」]{4,60})」', text or "")
    if not quotes:
        return ""
    quote = quotes[0].strip()
    if len(quote) > max_chars:
        return quote[: max_chars - 1].rstrip() + "…"
    return quote


def _clean_title_for_x(title: str, max_chars: int = 34) -> str:
    clean = re.sub(r'^【[^】]+】\s*', '', title or "").strip()
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > max_chars:
        return clean[: max_chars - 1].rstrip() + "…"
    return clean


def _detect_primary_player_tag(text: str) -> str:
    tags = detect_player_tags(text)
    return tags[0] if tags else ""


def _detect_earliest_player_tag(text: str) -> str:
    source = text or ""
    best_index = None
    best_tag = ""
    for name, tag in PLAYER_TAGS.items():
        idx = source.find(name)
        if idx == -1:
            continue
        if best_index is None or idx < best_index:
            best_index = idx
            best_tag = tag
    return best_tag


def _looks_like_lineup_post(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    return any(keyword in text for keyword in ("スタメン", "オーダー", "打順"))


def _looks_like_postgame_post(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    if _looks_like_lineup_post(title, summary):
        return False
    return any(keyword in text for keyword in ("勝利", "敗れ", "敗戦", "黒星", "白星", "引き分け", "決勝打", "サヨナラ", "完封負け", "0封負け"))


def _looks_like_live_update_post(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    if _looks_like_lineup_post(title, summary) or _looks_like_postgame_post(title, summary):
        return False
    return any(keyword in text for keyword in ("途中経過", "回表", "回裏", "勝ち越し", "同点", "逆転"))


def _normalize_average(value: str) -> str:
    clean = (value or "").replace("．", ".").strip()
    if clean.startswith("."):
        return clean
    if re.fullmatch(r"\d{3}", clean):
        return f".{clean}"
    return clean


def _extract_lineup_stat_rows_from_html(content_html: str, max_rows: int = 2) -> list[dict]:
    rows = []
    seen = set()
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", content_html or "", re.IGNORECASE | re.DOTALL):
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell_html)).strip()
            for cell_html in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.IGNORECASE | re.DOTALL)
        ]
        if len(cells) < 7:
            continue
        order = cells[0]
        if not re.fullmatch(r"[1-9]", order):
            continue
        key = (order, cells[2])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "order": order,
            "name": cells[2],
            "avg": _normalize_average(cells[3]),
            "hr": cells[4],
            "rbi": cells[5],
            "sb": cells[6],
        })
        if len(rows) >= max_rows:
            break
    return rows


def _extract_lineup_stat_rows(text: str, max_rows: int = 2) -> list[dict]:
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = re.sub(r"\s+", " ", clean)
    pattern = re.compile(
        r"(?:(\d)番)\s*([一-龥ァ-ヴーA-Za-z]{2,12})\s*"
        r"(?:打率)?\s*([\.．]?\d{3})\s*"
        r"(\d+)本\s*(\d+)打点\s*(\d+)盗塁"
    )
    rows = []
    seen = set()
    for match in pattern.finditer(clean):
        order, name, avg, hr, rbi, sb = match.groups()
        key = (order, name)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "order": order,
            "name": name,
            "avg": _normalize_average(avg),
            "hr": hr,
            "rbi": rbi,
            "sb": sb,
        })
        if len(rows) >= max_rows:
            break
    return rows


def _player_name_to_hashtag(name: str) -> str:
    normalized = (name or "").replace(" ", "")
    for key, tag in PLAYER_TAGS.items():
        if key in normalized:
            return tag
    return f"#{normalized}" if normalized else ""


def _extract_data_obp_rows_from_html(content_html: str, max_rows: int | None = None) -> list[dict]:
    rows = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", content_html or "", re.IGNORECASE | re.DOTALL):
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell_html)).strip()
            for cell_html in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.IGNORECASE | re.DOTALL)
        ]
        if len(cells) < 6:
            continue
        order = cells[0]
        name = cells[1]
        if not re.fullmatch(r"\d+", order):
            continue
        obp = _normalize_average(cells[5])
        rows.append({"order": order, "name": name, "obp": obp})
        if max_rows is not None and len(rows) >= max_rows:
            break
    return rows


def _build_data_obp_post(title: str, url: str, content_html: str = "") -> str:
    rows = _extract_data_obp_rows_from_html(content_html)
    if not rows:
        base_tags = " ".join(REQUIRED_TAGS)
        return f"{_clean_title_for_x(title)}\n\n数字で見ると、打線の見え方が少し変わります。\nこの並び、どう見ますか？\n\n{url}\n{base_tags}"

    top_five = rows[:5]
    leader = top_five[0]
    sakamoto = next((row for row in rows if "坂本" in row["name"]), None)
    tags = list(REQUIRED_TAGS)
    for row in top_five:
        tag = _player_name_to_hashtag(row["name"])
        if tag:
            tags.append(tag)
    hashtag_str = " ".join(dict.fromkeys(tags))
    ranking_lines = [f"{row['name']} {row['obp']}" for row in top_five]
    ranking_block = "\n".join(ranking_lines)
    sakamoto_line = ""
    if sakamoto and sakamoto["order"] not in {row["order"] for row in top_five}:
        sakamoto_line = f"\n坂本勇人 {sakamoto['order']}位 {sakamoto['obp']}"

    return (
        "阿部監督は打線をどう組むのか。\n\n"
        "出塁率上位5人\n"
        f"{ranking_block}"
        f"{sakamoto_line}\n"
        "NPB調べ\n"
        "この並び、どう見ますか？\n\n"
        f"{url}\n{hashtag_str}"
    )


def _build_lineup_post(title: str, url: str, summary: str, hashtag_str: str, content_html: str = "") -> str:
    rows = _extract_lineup_stat_rows_from_html(content_html, max_rows=2) if content_html else []
    if not rows:
        rows = _extract_lineup_stat_rows(summary, max_rows=2)
    cleaned_title = _clean_title_for_x(title, max_chars=28)

    if rows:
        stat_lines = [
            f"{row['order']}番{row['name']} {row['avg']} {row['hr']}本 {row['rbi']}打点 {row['sb']}盗塁"
            for row in rows
        ]
        body = "\n".join(stat_lines)
        return f"{cleaned_title}\n\n{body}\nこの並び、どう見ますか？\n\n{url}\n{hashtag_str}"

    return f"{cleaned_title}\n\n今日の並び、どこが気になりますか？\n\n{url}\n{hashtag_str}"


def _postgame_result_line(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    if "引き分け" in text:
        return "巨人、引き分け。"
    if any(keyword in text for keyword in ("完封負け", "0封負け", "打線が沈黙")):
        if "連敗" in text:
            return "巨人、打線が沈黙して連敗。"
        return "巨人、打線が沈黙して敗戦。"
    if any(keyword in text for keyword in ("サヨナラ勝",)):
        return "巨人、サヨナラで勝利。"
    if any(keyword in text for keyword in ("勝利", "白星")):
        if "連勝" in text:
            return "巨人、競り勝って連勝。"
        return "巨人、競り勝って白星。"
    if any(keyword in text for keyword in ("敗れ", "敗戦", "黒星")):
        if "連敗" in text:
            return "巨人、競り負けて連敗。"
        return "巨人、敗戦。"
    return _clean_title_for_x(title, max_chars=24)


def _postgame_angle(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    player_tag = _detect_earliest_player_tag(text)
    player_name = player_tag.lstrip("#") if player_tag else ""
    if any(keyword in text for keyword in ("完封負け", "0封負け", "打線が沈黙", "援護なく", "攻略できず")):
        if player_name and any(keyword in text for keyword in ("失点", "粘投", "試合を作", "先発")):
            return f"{player_name}は試合を壊さず、勝敗を分けたのは攻撃でした。"
        return "勝敗を分けたのは攻撃でした。"
    if any(keyword in text for keyword in ("決勝打", "サヨナラ", "逆転")):
        if player_name:
            return f"{player_name}の一打で流れが動き、終盤の勝負どころがはっきり出た試合でした。"
        return "終盤の一打で流れが動き、勝負どころがはっきり出た試合でした。"
    if any(keyword in text for keyword in ("継投", "救援", "守り切", "逃げ切")):
        return "終盤のベンチワークが勝敗に直結した試合でした。"
    return "流れがどこで傾いたかを見たい試合でした。"


def _build_postgame_post(title: str, url: str, summary: str, hashtag_str: str) -> str:
    result_line = _postgame_result_line(title, summary)
    angle = _postgame_angle(title, summary)
    question = "この試合の分岐点、どこでしたか？"
    return f"{result_line}\n\n{angle}\n{question}\n\n{url}\n{hashtag_str}"


def _live_update_state(title: str, summary: str) -> str:
    match = re.search(r"(\d+回[表裏]?)", f"{title} {summary}")
    return match.group(1) if match else "途中経過"


def _build_live_update_post(title: str, url: str, summary: str, hashtag_str: str) -> str:
    score = detect_score(title + " " + summary)
    state = _live_update_state(title, summary)
    text = f"{title} {summary}"

    if "逆転" in text:
        lead = f"巨人、{state}に{score}で逆転を許しました。" if score else f"巨人、{state}に逆転を許しました。"
        angle = "ここからベンチがどう立て直すかです。"
    elif "勝ち越し" in text:
        lead = f"巨人、{state}に{score}で勝ち越し。" if score else f"巨人、{state}に勝ち越し。"
        angle = "このあとどう逃げ切るかが気になります。"
    elif "同点" in text:
        lead = f"巨人、{state}に{score}の同点。" if score else f"巨人、{state}に同点。"
        angle = "次の1点をどちらが取るかです。"
    else:
        lead = f"巨人、{state}で{score}。" if score else f"巨人、{state}の途中経過。"
        angle = "ここから流れがどちらへ傾くかです。"

    return f"{lead}\n\n{angle}\nこの流れ、どう見ますか？\n\n{url}\n{hashtag_str}"


def _player_post_angle(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    if any(keyword in text for keyword in ("フォーム", "改造", "投げ方", "助言")):
        return "今回は結果より、フォーム変更の中身が気になる記事です。"
    if any(keyword in text for keyword in ("昇格", "合流", "復帰", "再調整")):
        return "今回の動き、今後の起用にも関わってきそうです。"
    if any(keyword in text for keyword in ("先発", "登板", "ローテ")):
        return "次の登板をどう見るかが気になる記事です。"
    if any(keyword in text for keyword in ("抹消", "離脱", "故障")):
        return "ここからどう立て直すかが気になる記事です。"
    return "今回のポイントを整理した記事です。"


def _player_post_question(title: str, summary: str, player_name: str) -> str:
    text = f"{title} {summary}"
    if any(keyword in text for keyword in ("フォーム", "改造", "投げ方", "助言")):
        return "この変化、どう見ますか？"
    if any(keyword in text for keyword in ("昇格", "合流", "復帰", "再調整")):
        return "この流れ、どう見ますか？"
    if any(keyword in text for keyword in ("先発", "登板", "ローテ")):
        return "次はどこを見たいですか？"
    if any(keyword in text for keyword in ("抹消", "離脱", "故障")):
        return "ここからどう立て直してほしいですか？"
    return f"{player_name}のこの動き、どう見ますか？"


def _build_player_post(title: str, url: str, summary: str, hashtag_str: str) -> str:
    player_tag = _detect_primary_player_tag(title + " " + summary)
    player_name = player_tag.lstrip("#") if player_tag else ""
    quote = _extract_short_quote(f"{title}\n{summary}")
    if player_name and quote:
        lead = f"{player_name}「{quote}」"
    elif quote:
        lead = f"「{quote}」"
    elif player_name:
        lead = f"{player_name}の今回の動き、気になります。"
    else:
        lead = _clean_title_for_x(title)

    angle = _player_post_angle(title, summary)
    question = _player_post_question(title, summary, player_name or "この話題")
    return f"{lead}\n\n{angle}\n{question}\n\n{url}\n{hashtag_str}"


def _farm_post_angle(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    if any(keyword in text for keyword in ("昇格", "支配下", "合流")):
        return "この動き、一軍の入れ替えにも関わってきそうです。"
    if any(keyword in text for keyword in ("本塁打", "猛打賞", "マルチ", "適時打")):
        return "二軍での打席内容、昇格候補としても気になります。"
    if any(keyword in text for keyword in ("好投", "先発", "無失点", "三振")):
        return "二軍での投球内容、次の昇格候補として見たいです。"
    if any(keyword in text for keyword in ("スタメン", "打順", "オーダー")):
        return "二軍の並びも、一軍昇格のヒントになります。"
    return "二軍の動きも、次の一軍を考える材料になります。"


def _farm_post_question(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    if any(keyword in text for keyword in ("昇格", "支配下", "合流")):
        return "次に上がるなら誰を見たいですか？"
    if any(keyword in text for keyword in ("本塁打", "猛打賞", "マルチ", "適時打", "好投", "無失点")):
        return "この2軍情報、どう見ますか？"
    return "この2軍の動き、どう見ますか？"


def _build_farm_post(title: str, url: str, summary: str, hashtag_str: str) -> str:
    player_tag = _detect_primary_player_tag(title + " " + summary)
    player_name = player_tag.lstrip("#") if player_tag else ""
    quote = _extract_short_quote(f"{title}\n{summary}")
    if player_name and quote:
        lead = f"{player_name}「{quote}」"
    elif player_name:
        lead = f"{player_name}の2軍での動き、気になります。"
    else:
        lead = _clean_title_for_x(title, max_chars=30)

    angle = _farm_post_angle(title, summary)
    question = _farm_post_question(title, summary)
    return f"{lead}\n\n{angle}\n{question}\n\n{url}\n{hashtag_str}"


def _manager_post_subtype(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    if any(keyword in text for keyword in ("競争", "レギュラー", "固定", "序列")):
        return "competition"
    if "若手" in text and "起用" in text:
        return "competition"
    if any(keyword in text for keyword in ("継投", "采配", "ベンチ", "勝負手", "代打", "守備固め")):
        return "strategy"
    if any(keyword in text for keyword in ("スタメン", "打順", "オーダー", "起用")):
        return "lineup"
    if "若手" in text:
        return "competition"
    return "general"


def _manager_post_angle(title: str, summary: str) -> str:
    subtype = _manager_post_subtype(title, summary)
    if subtype == "competition":
        return "このコメント、次の序列にも関わってきそうです。"
    if subtype == "lineup":
        return "この発言、次のスタメンをどう動かすか気になります。"
    if subtype == "strategy":
        return "この発言、次のベンチワークをどう読むか気になります。"
    return "この発言、ベンチの狙いが見える記事です。"


def _manager_post_question(title: str, summary: str) -> str:
    subtype = _manager_post_subtype(title, summary)
    if subtype == "competition":
        return "この競争、どう見ますか？"
    if subtype == "lineup":
        return "次のスタメン、どう変わると思いますか？"
    if subtype == "strategy":
        return "この采配、どう見ますか？"
    return "この発言、どう見ますか？"


def _build_manager_post(title: str, url: str, summary: str, hashtag_str: str) -> str:
    manager_tag = _detect_primary_player_tag(title + " " + summary)
    manager_name = manager_tag.lstrip("#") if manager_tag else ""
    quote = _extract_short_quote(f"{title}\n{summary}", max_chars=28)
    if manager_name and quote:
        lead = f"{manager_name}「{quote}」"
    elif quote:
        lead = f"「{quote}」"
    elif manager_name:
        lead = f"{manager_name}の今回のコメント、気になります。"
    else:
        lead = _clean_title_for_x(title)

    angle = _manager_post_angle(title, summary)
    question = _manager_post_question(title, summary)
    return f"{lead}\n\n{angle}\n{question}\n\n{url}\n{hashtag_str}"

# ──────────────────────────────────────────────────────────
# カテゴリ別テンプレート（{title} {url} {tags} を使用）
# ──────────────────────────────────────────────────────────
TEMPLATES = {
    "試合速報": [
        "⚾ {title}\n\nスコア・データ全部ブログで👇\n{url}\n{tags}",
        "🔥 {title}\n\n数字で振り返るとヤバい👇\n{url}\n{tags}",
        "{title}\n\nデータで見ると面白い👇\n{url}\n{tags}",
    ],
    "選手情報": [
        "{title}\n\n成績データをブログで全部解説👇\n{url}\n{tags}",
        "⚡ {title}\n\n数字で見ると驚愕👇\n{url}\n{tags}",
        "{title}\n\n昨季との比較データはブログで👇\n{url}\n{tags}",
    ],
    "補強・移籍": [
        "🚨 {title}\n\n賛否データも含めブログで解説👇\n{url}\n{tags}",
        "‼️ {title}\n\n実績データで分析してみた👇\n{url}\n{tags}",
        "{title}\n\n数字で見ると評価が変わる👇\n{url}\n{tags}",
    ],
    "首脳陣": [
        "{title}\n\n采配データで読み解くブログ👇\n{url}\n{tags}",
        "{title}\n\n戦術をデータで分析してみた👇\n{url}\n{tags}",
    ],
    "ドラフト・育成": [
        "🌟 {title}\n\n成績データはブログで全部見られる👇\n{url}\n{tags}",
        "{title}\n\n数字で追うと面白い👇\n{url}\n{tags}",
    ],
    "OB・解説者": [
        "{title}\n\n現役時代のデータと比べてみた👇\n{url}\n{tags}",
        "{title}\n\nブログで詳しく掘り下げてます👇\n{url}\n{tags}",
    ],
    "球団情報": [
        "{title}\n\nデータで見るとこうなってる👇\n{url}\n{tags}",
        "{title}\n\nブログで全部まとめてます👇\n{url}\n{tags}",
    ],
    "コラム": [
        "📝 {title}\n\nデータ込みで分析してみた👇\n{url}\n{tags}",
        "{title}\n\n数字で見ると納得👇\n{url}\n{tags}",
    ],
}
DEFAULT_TEMPLATES = [
    "{title}\n\nデータで見ると面白い👇\n{url}\n{tags}",
    "⚾ {title}\n\n数字で全部解説してます👇\n{url}\n{tags}",
]

# ──────────────────────────────────────────────────────────
# 選手名検出
# ──────────────────────────────────────────────────────────
def detect_score(text: str) -> str:
    """タイトルからスコアを抽出。例: '巨人3-2阪神' → '3-2'"""
    m = re.search(r'(\d{1,2}[-–]\d{1,2})', text)
    return m.group(1) if m else ""

def detect_player_tags(text: str) -> list:
    tags = []
    for name, tag in PLAYER_TAGS.items():
        if name in text and tag not in tags:
            tags.append(tag)
    return tags[:2]  # 多すぎると邪魔なので最大2人

# ──────────────────────────────────────────────────────────
# ポスト文案組み立て
# ──────────────────────────────────────────────────────────
def build_post(title: str, url: str, category: str, summary: str = "", content_html: str = "") -> str:
    # 既存の接頭語を除去（テンプレートと重複しないよう）
    title = re.sub(r'^【(速報|選手情報|球団情報|首脳陣|育成情報|OB情報)】\s*', '', title)

    # ハッシュタグ収集
    tags = list(REQUIRED_TAGS)
    player_tags = detect_player_tags(title + " " + summary)
    if category == "選手情報":
        tags += player_tags[:1]
    elif category == "試合速報" and _looks_like_postgame_post(title, summary):
        postgame_tag = _detect_earliest_player_tag(title + " " + summary)
        if postgame_tag:
            tags.append(postgame_tag)
    elif category == "ドラフト・育成":
        tags += player_tags[:1]
    else:
        tags += CATEGORY_TAGS.get(category, ["#プロ野球"])
        tags += player_tags
    seen = set()
    unique_tags = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique_tags.append(t)
    hashtag_str = " ".join(unique_tags)

    if category == "選手情報":
        return _build_player_post(title, url, summary, hashtag_str)
    if category == "首脳陣":
        manager_tags = list(REQUIRED_TAGS)
        if player_tags:
            manager_tags.append(player_tags[0])
        manager_hashtag_str = " ".join(dict.fromkeys(manager_tags))
        return _build_manager_post(title, url, summary, manager_hashtag_str)
    if category == "試合速報" and _looks_like_lineup_post(title, summary):
        lineup_tags = list(REQUIRED_TAGS) + player_tags[:2]
        lineup_hashtag_str = " ".join(dict.fromkeys(lineup_tags))
        return _build_lineup_post(title, url, summary, lineup_hashtag_str, content_html=content_html)
    if category == "試合速報" and _looks_like_live_update_post(title, summary):
        live_tags = list(REQUIRED_TAGS)
        live_tag = _detect_earliest_player_tag(title + " " + summary)
        if live_tag:
            live_tags.append(live_tag)
        live_hashtag_str = " ".join(dict.fromkeys(live_tags))
        return _build_live_update_post(title, url, summary, live_hashtag_str)
    if category == "試合速報" and _looks_like_postgame_post(title, summary):
        postgame_tags = list(REQUIRED_TAGS)
        postgame_tag = _detect_earliest_player_tag(title + " " + summary)
        if postgame_tag:
            postgame_tags.append(postgame_tag)
        postgame_hashtag_str = " ".join(dict.fromkeys(postgame_tags))
        return _build_postgame_post(title, url, summary, postgame_hashtag_str)
    if category == "ドラフト・育成":
        farm_tags = list(REQUIRED_TAGS)
        if player_tags:
            farm_tags.append(player_tags[0])
        farm_hashtag_str = " ".join(dict.fromkeys(farm_tags))
        return _build_farm_post(title, url, summary, farm_hashtag_str)
    if category == "コラム" and ("出塁率" in title or "出塁率" in content_html):
        return _build_data_obp_post(title, url, content_html=content_html)

    # スコア検出
    score = detect_score(title)
    result_info = ""
    score_line = ""
    if score and category == "試合速報":
        g, o = (score.replace("–", "-").split("-") + ["0"])[:2]
        try:
            result_info = "⭕ 勝利" if int(g) > int(o) else "❌ 敗戦" if int(g) < int(o) else "🟡 引き分け"
        except Exception:
            pass
        score_line = f"\n巨人 {score} {result_info}" if result_info else ""

    # テンプレート選択
    templates = TEMPLATES.get(category, DEFAULT_TEMPLATES)
    template = random.choice(templates)

    # タイトル文字数制限（URL=23字換算、テンプレート固定部分を除く）
    fixed_part = template.replace("{title}", "").replace("{url}", "x" * 23).replace("{tags}", hashtag_str)
    title_limit = 140 - len(fixed_part) - 1
    if len(title) > title_limit:
        title = title[:title_limit - 1] + "…"

    ai_comment = ""
    ai_mode = get_x_post_ai_mode()
    if should_use_ai_for_x_post(category):
        if ai_mode == "grok":
            ai_comment = generate_with_grok(title, category, score, summary=summary)
            if not ai_comment:
                ai_comment = generate_with_gemini(title, category, score, summary=summary)
        elif ai_mode == "gemini":
            ai_comment = generate_with_gemini(title, category, score, summary=summary)
        elif ai_mode == "auto":
            ai_comment = generate_with_grok(title, category, score, summary=summary)
            if not ai_comment:
                ai_comment = generate_with_gemini(title, category, score, summary=summary)

    if ai_comment:
        # 140文字制限チェック（URL=23字換算）
        body = f"{ai_comment}\n{url}\n{hashtag_str}"
        char_count = len(ai_comment) + 23 + 1 + len(hashtag_str) + 1
        if char_count > 280:  # 余裕を持って280まで
            # ハッシュタグを減らす
            body = f"{ai_comment}\n{url}\n{' '.join(unique_tags[:2])}"
        return body
    else:
        text = template.format(title=title, url=url, tags=hashtag_str)
        return text

# ──────────────────────────────────────────────────────────
# CLIエントリーポイント
# ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="WP記事からXポスト文案を生成")
    parser.add_argument("--title",    help="記事タイトル")
    parser.add_argument("--url",      help="記事URL")
    parser.add_argument("--category", help="カテゴリ名", default="コラム")
    parser.add_argument("--post-id",  type=int, help="WP投稿ID（WPから自動取得）")
    args = parser.parse_args()

    if args.post_id:
        wp    = WPClient()
        post  = wp.get_post(args.post_id)
        title = re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", ""))
        title = title.replace("&#8211;", "–").replace("&amp;", "&").replace("&quot;", '"')
        url   = post.get("link", "")
        # 記事本文を取得してXポスト生成に使う
        content_raw = post.get("content", {}).get("rendered", "")
        summary = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", content_raw)).strip()[:1500]
        content_html = content_raw
        cat_ids = post.get("categories", [])
        category = args.category
        if cat_ids:
            cats = wp.get_categories()
            id_to_name = {c["id"]: c["name"] for c in cats}
            category = id_to_name.get(cat_ids[0], "コラム")
    elif args.title and args.url:
        title    = args.title
        url      = args.url
        category = args.category
        summary  = ""
        content_html = ""
    else:
        parser.print_help()
        sys.exit(1)

    post_text = build_post(title, url, category, summary=summary, content_html=content_html)
    char_count = len(post_text.replace(url, "x" * 23))

    print(post_text)
    print(f"\n--- {char_count}字 / 140字 ---", file=sys.stderr)


if __name__ == "__main__":
    main()
