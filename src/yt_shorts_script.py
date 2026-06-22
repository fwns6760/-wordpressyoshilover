"""Script and number-guard helpers for YouTube Shorts generation."""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.yt_shorts_topic import ShortsTopic


NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:\d+\.\d+|\.\d+|\d+)")
DECIMAL_RE = re.compile(r"(?P<sign>[+-]?)(?P<value>(?:\d+)?\.\d+)(?!\d)")
JAPANESE_DIGITS = {
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}
KANA_DIGITS = {
    "0": "まる",
    "1": "いち",
    "2": "に",
    "3": "さん",
    "4": "よん",
    "5": "ご",
    "6": "ろく",
    "7": "なな",
    "8": "はち",
    "9": "きゅう",
}
METRIC_LABEL_REPLACEMENTS = (
    ("BB/9", "ビービーナイン"),
    ("K/9", "ケーナイン"),
    ("OPS", "オーピーエス"),
    ("WHIP", "ウィップ"),
    ("ERA", "防御率"),
    ("AVG", "打率"),
    ("OBP", "出塁率"),
    ("SLG", "長打率"),
)


@dataclass(frozen=True)
class ScriptCaption:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class ShortsScript:
    title: str
    description: str
    narration: str
    captions: tuple[ScriptCaption, ...]
    allowed_numbers: tuple[str, ...]
    x_post: str = ""


def _normalize_number(token: str) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    if raw.startswith("."):
        return raw
    if "." in raw:
        left, right = raw.split(".", 1)
        left = str(int(left or "0"))
        return f".{right}" if left == "0" else f"{left}.{right}"
    try:
        return str(int(raw))
    except ValueError:
        return raw


def extract_number_tokens(text: str) -> tuple[str, ...]:
    tokens = []
    for match in NUMBER_RE.finditer(str(text or "")):
        normalized = _normalize_number(match.group(0))
        if normalized:
            tokens.append(normalized)
    return tuple(tokens)


def allowed_numbers_for_topic(topic: ShortsTopic) -> tuple[str, ...]:
    source_text = " ".join(
        [
            topic.label,
            topic.value,
            topic.note,
            topic.as_of,
            str(topic.raw_item.get("label") or ""),
            str(topic.raw_item.get("value") or ""),
            str(topic.raw_item.get("note") or ""),
        ]
    )
    return tuple(dict.fromkeys(extract_number_tokens(source_text)))


def verify_number_guard(text: str, allowed_numbers: tuple[str, ...]) -> tuple[bool, tuple[str, ...]]:
    allowed = set(allowed_numbers)
    leaked = tuple(token for token in extract_number_tokens(text) if token not in allowed)
    return (not leaked, leaked)


def assert_number_guard(text: str, allowed_numbers: tuple[str, ...]) -> None:
    ok, leaked = verify_number_guard(text, allowed_numbers)
    if not ok:
        raise ValueError(f"yt_shorts number guard failed: leaked={list(leaked)}")


def display_as_of_date(as_of: str) -> str:
    raw = str(as_of or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not match:
        return raw
    year, month, day = match.groups()
    return f"{int(year)}年{int(month)}月{int(day)}日"


def _baseball_average_reading(match: re.Match[str]) -> str:
    sign = match.group("sign") or ""
    value = match.group("value")
    decimals = value.split(".", 1)[1][:3].ljust(3, "0")
    units = ("割", "分", "厘")
    parts = [
        f"{JAPANESE_DIGITS[digit]}{unit}"
        for digit, unit in zip(decimals, units, strict=True)
        if digit != "0"
    ]
    reading = "".join(parts) or "零"
    if sign == "+":
        return f"プラス{reading}"
    if sign == "-":
        return f"マイナス{reading}"
    return reading


def _decimal_point_reading(match: re.Match[str]) -> str:
    sign = match.group("sign") or ""
    value = match.group("value")
    if "." not in value:
        return match.group(0)
    left, right = value.split(".", 1)
    left = left or "0"
    left_reading = "".join(JAPANESE_DIGITS.get(digit, digit) for digit in left)
    right_reading = "".join(JAPANESE_DIGITS.get(digit, digit) for digit in right)
    reading = f"{left_reading}点{right_reading}"
    if sign == "+":
        return f"プラス{reading}"
    if sign == "-":
        return f"マイナス{reading}"
    return reading


def _ops_reading(match: re.Match[str]) -> str:
    sign = match.group("sign") or ""
    value = match.group("value")
    if "." not in value:
        return match.group(0)
    left, right = value.split(".", 1)
    if left in {"", "0"}:
        reading = "".join(KANA_DIGITS.get(digit, digit) for digit in right[:3])
    else:
        return _decimal_point_reading(match)
    if sign == "+":
        return f"プラス{reading}"
    if sign == "-":
        return f"マイナス{reading}"
    return reading


def _speech_metric_style(topic: ShortsTopic) -> str:
    source = " ".join([topic.label, topic.hook, topic.note, str(topic.raw_item.get("label") or "")])
    if re.search(r"\bOPS\b", source, flags=re.IGNORECASE):
        return "ops"
    if "打率" in source or "出塁率" in source or "長打率" in source or "勝率" in source:
        return "ratio"
    if re.search(r"\b(AVG|OBP|SLG)\b", source, flags=re.IGNORECASE):
        return "ratio"
    if "防御率" in source or re.search(r"\b(ERA|WHIP|K/9|BB/9)\b", source, flags=re.IGNORECASE):
        return "decimal"
    return ""


def _replace_metric_labels_for_speech(text: str) -> str:
    value = str(text or "")
    for raw, reading in METRIC_LABEL_REPLACEMENTS:
        value = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(raw)}(?![A-Za-z0-9])",
            reading,
            value,
            flags=re.IGNORECASE,
        )
    return value


def _speech_metric_text(topic: ShortsTopic, text: str) -> str:
    value = _replace_metric_labels_for_speech(text)
    style = _speech_metric_style(topic)
    if style == "ratio":
        return DECIMAL_RE.sub(_baseball_average_reading, value)
    if style == "ops":
        return DECIMAL_RE.sub(_ops_reading, value)
    if style == "decimal":
        return DECIMAL_RE.sub(_decimal_point_reading, value)
    if not style:
        return value
    return value


# 音声(VOICEVOX)が誤読する選手名の読み補正。narration(音声テキスト)にのみ適用し、
# title / caption / description の漢字表記はそのまま残す。
# key は長い順に置換する(姓名フルを先に当てて部分誤置換を防ぐ)。
NAME_READING_OVERRIDES: dict[str, str] = {
    # key は漢字フル名 / value は正しい かな 読み。VOICEVOX のデフォルト読みで
    # 外しやすい巨人 支配下選手を先回り登録。読みが確実なもののみ。新しい誤読が
    # 見つかったら姓名フルで追記する。
    "泉口友汰": "いずぐちゆうた",     # 泉=いずみ ではなく いず
    "大勢": "たいせい",               # 既定「おおぜい」
    "長野久義": "ちょうのひさよし",   # 長野=ながの ではなく ちょうの
    "井上温大": "いのうえはるひろ",   # 温大=おんだい ではなく はるひろ
    "郡拓也": "こおりたくや",         # 郡=ぐん ではなく こおり
    "皆川岳飛": "みながわたかと",     # 岳飛=がくひ ではなく たかと
    "中山礼都": "なかやまらいと",     # 礼都=れいと ではなく らいと
    "則本昂大": "のりもとたかひろ",   # 昂大=こうだい ではなく たかひろ
    "田中瑛斗": "たなかあきと",       # 瑛斗=えいと ではなく あきと
    "平内龍太": "ひらうちりゅうた",   # 平内=へいない ではなく ひらうち
    "船迫大雅": "ふなさこたいが",     # 迫=はく ではなく さこ
    "松本剛": "まつもとつよし",       # 剛=ごう ではなく つよし
    "萩尾匡也": "はぎおまさや",       # 匡也=きょうや ではなく まさや
    "若林楽人": "わかばやしらくと",   # 楽人=がくじん ではなく らくと
    "西舘勇陽": "にしだてゆうよう",   # 舘=かん ではなく だて
    "岸田行倫": "きしだゆきのり",     # 行倫=ぎょうりん ではなく ゆきのり
    "大城卓三": "おおしろたくぞう",   # 卓三=たくみ ではなく たくぞう
    "宇都宮葵星": "うつのみやあおい", # 葵星=きせい ではなく あおい
    "戸郷翔征": "とごうしょうせい",
    "田中将大": "たなかまさひろ",
    "山﨑伊織": "やまざきいおり",
    "坂本勇人": "さかもとはやと",     # 勇人=ゆうと ではなく はやと
    "又木鉄平": "またぎてっぺい",
    "横川凱": "よこかわがい",
    "三塚琉生": "みつかりゅうせい",
    "石塚裕惺": "いしづかゆうせい",
    # 泉口の姓のみ表記ゆれ対策(フル名置換の後に効く)
    "泉口": "いずぐち",
}


def _apply_name_readings(text: str) -> str:
    """誤読しやすい選手名を かな に置換して TTS の発音を正す。"""
    if not text:
        return text
    for kanji in sorted(NAME_READING_OVERRIDES, key=len, reverse=True):
        text = text.replace(kanji, NAME_READING_OVERRIDES[kanji])
    return text


# ブランディング定数(ヨシラバー｜巨人データ速報)
BRAND_CLOSING_LINE = "巨人データはヨシラバーで毎日更新中。"
SITE_URL = "https://yoshilover.com"
DATA_URL = "https://yoshilover.com/data"
X_HANDLE = "@yoshilover6760"
BASE_HASHTAGS = ("#巨人", "#読売ジャイアンツ", "#ジャイアンツ", "#プロ野球", "#npb", "#ヨシラバー")

# 独自コメント(ファン目線の所感)プール。数字・事実は入れない=量産AIに見えない
# 一言の "巨人目線の敬意ある考察"。player+日付で rotate して同じにならないようにする。
# NOTE: より高い独自性が必要なら Gemini Flash 生成に差し替え可(v2)。
FAN_COMMENT_POOL: tuple[str, ...] = (
    "派手さはないけど、こういう選手が今の巨人を支えてる。",
    "数字の裏側に、巨人の野球の積み上げが見えます。",
    "結果だけじゃなく、流れで見ると面白い一人。",
    "地味だけど、巨人ファンならニヤッとするポイント。",
    "この働き、ちゃんと見てる巨人ファンは見てる。",
    "勝負どころで効いてくるタイプ、巨人には大事。",
    "目立たないけど、今の巨人に欠かせない存在。",
    "こういう積み重ねが、巨人の地力になっていく。",
)


def _hashtag_player(player: str) -> str:
    """選手名をハッシュタグ用に整形(空白・中黒を除去)。"""
    return (player or "").replace(" ", "").replace("　", "").replace("・", "")


def _fan_comment(topic: ShortsTopic) -> str:
    """ファン目線の一言コメントを deterministic に rotate して返す(数字なし)。"""
    seed = f"{topic.player}|{topic.as_of}|{topic.label}"
    idx = sum(ord(ch) for ch in seed) % len(FAN_COMMENT_POOL)
    return FAN_COMMENT_POOL[idx]


def build_x_post(topic: ShortsTopic, *, date_label: str) -> str:
    """X(旧Twitter)再投稿用のポスト文。導線とハッシュタグ込み。"""
    hook = topic.hook.strip()
    tags = " ".join(BASE_HASHTAGS[:4])
    lines = [
        f"【巨人データ】{hook}",
        "",
        _fan_comment(topic),
        "",
        "30秒のShortsにまとめました👇",
        "[Shorts URL]",
        "",
        f"巨人の全選手データはこちら → {DATA_URL}",
        tags,
    ]
    return "\n".join(lines)


def build_script(topic: ShortsTopic) -> ShortsScript:
    """Build a deterministic Japanese narration script.

    Phase 1 intentionally avoids asking an LLM to invent facts.  The only
    numeric strings in the script must come from ``topic.value`` / ``topic.note``
    / ``topic.as_of``; ``assert_number_guard`` enforces that contract.
    """

    allowed = allowed_numbers_for_topic(topic)
    date_label = display_as_of_date(topic.as_of)
    date_line = f"記録日は、{date_label}時点。" if date_label else ""
    speech_hook = _speech_metric_text(topic, topic.hook)
    speech_note = _speech_metric_text(topic, topic.note)
    note_line = f"ポイントは、{speech_note}。" if topic.note else "今の巨人で見逃せない数字です。"
    narration_parts = [
        f"今日の注目は、{speech_hook}。",
        date_line,
        "この数字、見逃せません。",
        note_line,
        _fan_comment(topic),
        BRAND_CLOSING_LINE,
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)
    # 数値ガード通過後に選手名の読みを補正(数字は変えない)
    narration = _apply_name_readings(narration)

    title = f"{topic.title}｜{date_label}時点" if date_label else topic.title
    # 事実部分(hook + 記録日)のみ数値ガード対象。固定ブランディング文(導線・@handle・
    # "30秒" 等)は捏造数字ではないのでガード外で連結する。
    desc_factual = (
        f"{topic.hook}。\n"
        f"記録日: {date_label or topic.as_of or '未設定'}"
    )
    assert_number_guard(title + "\n" + desc_factual, allowed)
    desc_branding = (
        "\n\n"
        "巨人特化メディア「ヨシラバー」が、巨人の注目データを毎日30秒のShortsでお届け。\n"
        "「巨人といえばヨシラバー」を目指して、ファン目線で発信しています。\n\n"
        f"▼巨人の全選手データ(毎日更新)\n{DATA_URL}\n\n"
        f"▼巨人ニュース・速報\n{SITE_URL}\n\n"
        f"▼X(旧Twitter)でも毎日発信\n{X_HANDLE}\n\n"
        f"詳しいデータ: {topic.source_url}\n"
        "音声: VOICEVOX 青山龍星\n\n"
        + " ".join((*BASE_HASHTAGS, f"#{_hashtag_player(topic.player)}"))
    )
    description = desc_factual + desc_branding

    captions = (
        ScriptCaption(0.0, 2.2, f"{topic.hook} / {date_label}時点" if date_label else topic.hook),
        ScriptCaption(2.2, 8.4, f"{topic.label} {topic.value}"),
        ScriptCaption(8.4, 14.8, topic.note or "今の巨人で見逃せない数字"),
        ScriptCaption(14.8, 21.0, "結果だけでなく、流れまで見る"),
        ScriptCaption(21.0, 27.0, "巨人データはヨシラバーで毎日更新中"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    return ShortsScript(
        title=title,
        description=description,
        narration=narration,
        captions=captions,
        allowed_numbers=allowed,
        x_post=build_x_post(topic, date_label=date_label),
    )


__all__ = [
    "ScriptCaption",
    "ShortsScript",
    "allowed_numbers_for_topic",
    "assert_number_guard",
    "build_script",
    "display_as_of_date",
    "extract_number_tokens",
    "verify_number_guard",
]
