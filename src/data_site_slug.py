"""Player name → URL slug 変換 (data-site Phase 1.0 / ticket 443).

slug rule (Phase 1.0 lock):
- 日本人 player: 姓-名 を kebab-case romaji (例: 吉川尚輝 → yoshikawa-naoki)
- 外国人 player (katakana): そのまま kebab-case romaji (例: マルティネス → martinez)
- 役職 suffix (監督/監督代行/コーチ/外野手/捕手 等) は除去
- 全角空白 / 半角空白 / 中黒 / 「・」 を kebab に統一

Phase 1.0 では hardcoded mapping table を持つ (姓名 → romaji)。
Phase 1 full 拡大時に kakasi / pykakasi 等の自動変換に切替検討。
"""

from __future__ import annotations

# Phase 1.0 で必要な 3 player + 拡張に備えた一軍 active player 主要 30 名を hardcode。
# Phase 1.5 で残り 80 名を追記する。
_PLAYER_SLUG_MAP: dict[str, str] = {
    # Phase 1.0
    "吉川尚輝": "yoshikawa-naoki",
    "坂本勇人": "sakamoto-hayato",
    "丸佳浩": "maru-yoshihiro",
    # Phase 1.5 想定 (一軍 active 主要、 段階追加)
    "岡本和真": "okamoto-kazuma",
    "戸郷翔征": "togo-shosei",
    "山﨑伊織": "yamazaki-iori",
    "田中将大": "tanaka-masahiro",
    "大城卓三": "ohshiro-takuzo",
    "キャベッジ": "cabbage",
    "マルティネス": "martinez",
    "リチャード": "richard",
    "中山礼都": "nakayama-raito",
    "門脇誠": "kadowaki-makoto",
    "西舘勇陽": "nishidate-yuyo",
    "森下暢仁": "morishita-masato",
    "泉口友汰": "izuguchi-yuta",
    # 監督・コーチ
    "阿部慎之助": "abe-shinnosuke",
    "橋上秀樹": "hashigami-hideki",
    # Phase 1.5 追加 (一軍 active player、 insight.db 出場 record top 30)
    "中川皓太": "nakagawa-kota",
    "ダルベック": "dalbec",
    "浦田俊輔": "urata-shunsuke",
    "佐々木俊輔": "sasaki-shunsuke",
    "岸田行倫": "kishida-yukinori",
    "高梨雄平": "takanashi-yuhei",
    "田和廉": "tawa-ren",
    "平山功太": "hirayama-kota",
    "井上温大": "inoue-haruhiro",
    "大勢": "taisei",
    "松本剛": "matsumoto-tsuyoshi",
    "船迫大雅": "funasako-taiga",
    "赤星優志": "akahoshi-yushi",
    "湯浅大": "yuasa-dai",
    "ウィットリー": "whitley",
    "則本昂大": "norimoto-takahiro",
    "西川歩": "nishikawa-ayumu",
    "北浦竜次": "kitaura-ryuji",
    "ルシアーノ": "luciano",
    "石川達也": "ishikawa-tatsuya",
    "小濱佑斗": "ohama-yuto",
    # ---- Phase 1 full 拡大 (支配下選手 + コーチ・監督、 ticket 446/447) ----
    # 注: slug は URL/SEO 用 romaji。 表示は常に kanji 名。 若手・育成昇格選手の
    # 読みは推定を含む (forward-only、 必要なら個別訂正可)。
    # 投手・野手 (支配下)
    "Ｆ．ウィットリー": "whitley",
    "甲斐拓也": "kai-takuya",
    "小林誠司": "kobayashi-seiji",
    "石塚裕惺": "ishizuka-yusei",
    "萩尾匡也": "hagio-masaya",
    "岡田悠希": "okada-yuki",
    "浅野翔吾": "asano-shogo",
    "若林楽人": "wakabayashi-rakuto",
    "長野久義": "chono-hisayoshi",
    "泉圭輔": "izumi-keisuke",
    "宇都宮葵星": "utsunomiya-aoi",
    "竹丸和幸": "takemaru-kazuyuki",
    "田中瑛斗": "tanaka-akito",
    "ハワード": "howard",
    "堀田賢慎": "hotta-kenshin",
    "マタ": "mata",
    "増田陸": "masuda-riku",
    "又木鉄平": "matagi-teppei",
    "皆川岳飛": "minagawa-takato",
    "宮原駿介": "miyahara-shunsuke",
    "山城京平": "yamashiro-kyohei",
    "山瀬慎之助": "yamase-shinnosuke",
    "荒巻悠": "aramaki-yu",
    "亀田啓太": "kameda-keita",
    "川原田純平": "kawaharada-junpei",
    "河野優作": "kono-yusaku",
    "郡拓也": "kori-takuya",
    "坂本達也": "sakamoto-tatsuya",
    "代木大和": "shiroki-yamato",
    "鈴木大和": "suzuki-yamato",
    "園田純規": "sonoda-junki",
    "竹下徠空": "takeshita-sora",
    "田村朋輝": "tamura-tomoki",
    "知念大成": "chinen-taisei",
    "ティマ": "tima",
    "冨重英二郎": "tomishige-eijiro",
    "中田歩夢": "nakata-ayumu",
    "バルドナード": "baldonado",
    "板東湧梧": "bando-yugo",
    "藤井健翔": "fujii-kento",
    "平内龍太": "hirauchi-ryuta",
    "堀江正太郎": "horie-shotaro",
    "増田大輝": "masuda-daiki",
    "松浦慶斗": "matsuura-keito",
    "三塚琉生": "mitsuka-ryusei",
    "森田駿哉": "morita-shunya",
    "山田龍聖": "yamada-ryusei",
    "梶原昂希": "kajiwara-koki",
    "横川凱": "yokokawa-gai",
    # 監督・コーチ
    "川相昌弘": "kawai-masahiro",
    "村田善則": "murata-yoshinori",
    "杉内俊哉": "sugiuchi-toshiya",
    "内海哲也": "utsumi-tetsuya",
    "亀井善行": "kamei-yoshiyuki",
    "石井琢朗": "ishii-takuro",
    "ゼラス・ウィーラー": "zelous-wheeler",
    "李承燁": "lee-seungyeop",
    "吉川大幾": "yoshikawa-daiki",
    "實松一成": "sanematsu-kazunari",
    "金城龍彦": "kinjo-tatsuhiko",
    "脇谷亮太": "wakiya-ryota",
    "田口昌徳": "taguchi-masanori",
    "大田泰示": "ota-taishi",
    "鈴木尚広": "suzuki-naohiro",
    "山口鉄也": "yamaguchi-tetsuya",
    "大竹寛": "otake-hiroshi",
    "会田有志": "aida-yushi",
    "橋本到": "hashimoto-itaru",
    "若林晃弘": "wakabayashi-akihiro",
    "市川友也": "ichikawa-tomoya",
    "立岡宗一郎": "tatsuoka-soichiro",
    "野上亮磨": "nogami-ryoma",
    "西村健太朗": "nishimura-kentaro",
    "矢野謙次": "yano-kenji",
    "久保康生": "kubo-yasuo",
}


def player_slug(name: str) -> str:
    """canonical player name → URL slug.

    未知 player は roster name の lower + ascii fallback (kebab) を返す。
    呼び出し元が validate するため、 ここで例外は投げない。
    """
    if not name:
        return ""
    normalized = name.strip()
    # roster の姓名間 空白 (半角/全角) を吸収
    for sp in (" ", "　"):
        if sp in normalized:
            normalized = normalized.replace(sp, "")
    if normalized in _PLAYER_SLUG_MAP:
        return _PLAYER_SLUG_MAP[normalized]
    # fallback: ascii only / lower / kebab (未知 player 救済)
    ascii_part = "".join(c if (c.isascii() and (c.isalnum() or c == "-")) else "-" for c in normalized.lower())
    return "-".join(p for p in ascii_part.split("-") if p) or normalized


def known_player_names() -> list[str]:
    """slug map に載っている canonical name list (Phase 1.0+1.5 想定)。"""
    return sorted(_PLAYER_SLUG_MAP.keys())


__all__ = ["player_slug", "known_player_names"]
