"""Fixed-lane Gemini 2.5 Flash prompt contracts for ticket 036.

The builder is intentionally upstream-only: it hardens the prompt contract that
future fixed-lane generators and repair flows can reuse, while leaving the
actual validator logic to the existing downstream modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from src import body_validator, rss_fetcher, source_attribution_validator, title_style_validator, title_validator


PromptMode = Literal["initial", "repair"]

PROGRAM_REQUIRED_BLOCKS = (
    "【放送予定】",
    "【放送局・配信先】",
    "【出演者】",
    "【見どころ】",
    "【出典】",
)

MINIMUM_DIFF_REPAIR_RUBRIC = (
    "該当 block / 該当 sentence / 該当 attribution だけを直す。",
    "正しい block・正しい文・正しい出典表記は温存する。",
    "全文再生成は禁止。差分が最小になるように補修する。",
)


@dataclass(frozen=True)
class FixedLanePromptContract:
    subtype: str
    title_template: str
    sample_title: str
    required_blocks: tuple[str, ...]
    title_body_coherence: tuple[str, ...]
    abstract_lead_ban: tuple[str, ...]
    fallback_copy: tuple[str, ...]
    validator_subtype: str = ""


def _postgame_abstract_lead_line() -> str:
    banned = " / ".join(body_validator.POSTGAME_ABSTRACT_LEAD_PREFIXES[:4])
    return (
        f"【試合結果】の1文目はスコア・相手・勝敗・日付を先に置く。"
        f"{banned} のような抽象 lead で始めない。"
    )


def _postgame_fact_kernel_line() -> str:
    return (
        "【ハイライト】には決勝打・勝ち越し・本塁打・好投など、"
        "勝敗を動かした出来事を最低1つ入れる。コメント募集文を fact kernel より前に置かない。"
    )


CONTRACTS: dict[str, FixedLanePromptContract] = {
    "program": FixedLanePromptContract(
        subtype="program",
        title_template="[番組名]「[内容]」([日付] [時刻]放送)",
        sample_title='GIANTS TV「練習後インタビュー」(4月21日 20:00放送)',
        required_blocks=PROGRAM_REQUIRED_BLOCKS,
        title_body_coherence=(
            "title は放送日・番組名・放送予定の3点を先頭で確定させる。",
            "本文冒頭も放送予定の事実から入り、試合結果・速報・公示・スタメン記事の書き出しに寄せない。",
        ),
        abstract_lead_ban=(
            "1文目を『注目番組です』『楽しみな放送です』のような抽象 lead にしない。",
            "番組名・放送日時・放送局/配信先のうち source にある確定情報を先に置く。",
        ),
        fallback_copy=(
            "出演者や配信 platform が未確認なら『詳細は番組表更新待ちです』とだけ書く。",
            "未確認の出演者・解説者・放送局を推測で足さない。",
        ),
        validator_subtype="fact_notice",
    ),
    "notice": FixedLanePromptContract(
        subtype="notice",
        title_template="巨人、[選手名]を[対象]に[事象]",
        sample_title='巨人・戸郷翔征、右肘違和感で"離脱回避"！！！',
        required_blocks=tuple(rss_fetcher.NOTICE_REQUIRED_HEADINGS),
        title_body_coherence=(
            "title は選手名と公示種別を先頭で一致させ、本文1文目でも同じ対象を言い換えず確認する。",
            "公示記事なので、試合結果・速報・スタメン・抽象的な期待論に本文の重心をずらさない。",
        ),
        abstract_lead_ban=(
            "1文目を『大きな動きです』『気になる公示です』のような抽象 lead にしない。",
            "公示日・公示種別・対象選手を先に置き、理由や影響は source にある範囲だけで後段に回す。",
        ),
        fallback_copy=(
            "背景材料が薄い場合は、公示の事実と対象日だけを短く整理して止める。",
            "起用影響や登録理由は source に無ければ書かない。",
        ),
        validator_subtype="fact_notice",
    ),
    "probable_starter": FixedLanePromptContract(
        subtype="probable_starter",
        title_template="4月X日(曜)の予告先発が発表される！！！",
        sample_title="4月21日(月)の予告先発が発表される！！！",
        required_blocks=tuple(body_validator.expected_block_order("pregame")),
        title_body_coherence=(
            "030 pregame rail に合わせて、title と本文は『先発情報 / 予告先発 / 試合前』の語彙で揃える。",
            f"非 line-up 記事なので title/body で『{title_validator.TITLE_PREFIX_BY_SUBTYPE['postgame']}』や速報語に寄せない。",
        ),
        abstract_lead_ban=(
            "1文目を『注目の一戦です』『楽しみなマッチアップです』のような抽象 lead にしない。",
            "試合日・対戦カード・両軍予告先発の事実から入り、見どころは後段で1つに絞る。",
        ),
        fallback_copy=(
            "両軍の数字が片側しか無ければ、無い側は『公式発表待ち』または『source 記載なし』で止める。",
            "投手名が source に無い場合は『先発は公式発表待ち』とし、推測で名前を書かない。",
        ),
        validator_subtype="pregame",
    ),
    "farm_result": FixedLanePromptContract(
        subtype="farm_result",
        title_template="巨人二軍 [選手名]、[事象]！！！",
        sample_title="巨人二軍 浅野翔吾、2安打マルチヒット！！！",
        required_blocks=tuple(body_validator.expected_block_order("farm")),
        title_body_coherence=(
            "title と本文は『二軍 / ファーム』の語彙を維持し、一軍記事の文脈に混ぜない。",
            "結果記事なので、冒頭は二軍の結果と相手とスコアから入り、一軍昇格論だけで始めない。",
        ),
        abstract_lead_ban=(
            "1文目を『若手が躍動した』『将来が楽しみだ』のような感想 lead にしない。",
            "二軍の結果・主要選手の数字・次戦または一軍示唆の順で整理する。",
        ),
        fallback_copy=(
            "個別成績が不足する場合は score と主な出来事だけに絞る。",
            "一軍昇格の示唆は source に無ければ『今後の材料として見たい』程度に止める。",
        ),
        validator_subtype="farm",
    ),
    "postgame": FixedLanePromptContract(
        subtype="postgame",
        title_template="巨人・[選手名]、[事象]！！！",
        sample_title="巨人・岡本和真、決勝ホームラン！！！",
        required_blocks=tuple(body_validator.expected_block_order("postgame")),
        title_body_coherence=(
            f"030 postgame rail に合わせて、title と本文の重心は『{title_validator.TITLE_PREFIX_BY_SUBTYPE['postgame']}』側へ固定する。",
            "本文冒頭でスコア・相手・勝敗が見えない構成にしない。試合後なのに試合前/速報語へ戻さない。",
        ),
        abstract_lead_ban=(
            _postgame_abstract_lead_line(),
            _postgame_fact_kernel_line(),
        ),
        fallback_copy=(
            "事実が薄い場合でも、score / opponent / win-loss / decisive event / source link だけは残す。",
            "不足分を感想や一般論で埋めない。fan_view は最後の1文だけにする。",
        ),
        validator_subtype="postgame",
    ),
}


def supported_fixed_lane_subtypes() -> tuple[str, ...]:
    return tuple(CONTRACTS.keys())


def get_contract(subtype: str) -> FixedLanePromptContract:
    try:
        return CONTRACTS[subtype]
    except KeyError as exc:  # pragma: no cover - defensive path
        raise ValueError(f"unsupported fixed-lane subtype: {subtype!r}") from exc


def _render_source_facts(source_facts: Sequence[str] | str) -> str:
    if isinstance(source_facts, str):
        lines = [line.strip() for line in source_facts.splitlines() if line.strip()]
    else:
        lines = [str(item).strip() for item in source_facts if str(item).strip()]
    if not lines:
        return "- (source facts omitted)"
    return "\n".join(f"- {line.lstrip('- ').strip()}" for line in lines)


def _render_lines(lines: Sequence[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _title_style_lines(contract: FixedLanePromptContract) -> tuple[str, ...]:
    editorial_subtype = title_style_validator.fixed_lane_to_editorial_subtype(contract.subtype)
    return title_style_validator.build_title_style_prompt_lines(editorial_subtype)


def _attribution_lines(contract: FixedLanePromptContract) -> tuple[str, ...]:
    subtype = contract.validator_subtype
    if subtype in source_attribution_validator.SPECIAL_REQUIRED_SUBTYPES:
        return (
            "primary が 公式X / 公式媒体X の場合、本文か source block に明示 attribution を必ず残す。",
            "handle が曖昧な X は単独根拠にしない。T1 web の裏どり無しで断定しない。",
            "一次情報 URL が別にある場合も、出典リンクは省略しない。",
        )
    if subtype in source_attribution_validator.POSTGAME_OPTIONAL_WITH_WEB_SUBTYPES:
        return (
            "primary が T1 web なら web 出典を基準に書く。",
            "公式X / 公式媒体X を primary に使っても、T1 web が別にある場合は本文 attribution を省略可。ただし source block の URL は残す。",
            "handle が曖昧な X を単独根拠にしない。",
        )
    return (
        "primary tier source を本文断定の起点にする。",
        "補助 source は source block に退避し、本文では確定事実だけを書く。",
    )


def build_fixed_lane_prompt(
    *,
    subtype: str,
    mode: PromptMode,
    title_hint: str,
    source_facts: Sequence[str] | str,
    source_name: str = "",
    source_url: str = "",
    current_draft: str = "",
    fail_axes: Sequence[str] | None = None,
) -> str:
    if mode not in {"initial", "repair"}:
        raise ValueError(f"unsupported prompt mode: {mode!r}")

    contract = get_contract(subtype)
    source_facts_block = _render_source_facts(source_facts)
    current_draft_block = current_draft.strip() or "(current draft omitted)"
    fail_axis_labels = ", ".join(axis.strip() for axis in (fail_axes or ()) if axis.strip()) or "(unspecified)"

    prompt = [
        "あなたはヨシラバー fixed lane の本文生成担当です。",
        f"mode: {mode}",
        f"subtype: {subtype}",
        f"title_hint: {title_hint or contract.sample_title}",
        f"title_template: {contract.title_template}",
        f"source_name: {source_name or '(unknown)'}",
        f"source_url: {source_url or '(unknown)'}",
        "source_facts:",
        source_facts_block,
        "",
        "required_fact_block:",
        _render_lines(
            [
                "必須 block は次の順で固定する。",
                " -> ".join(contract.required_blocks),
            ]
        ),
        "title_body_coherence:",
        _render_lines(contract.title_body_coherence),
        "title_style_contract:",
        _render_lines(_title_style_lines(contract)),
        "abstract_lead_ban:",
        _render_lines(contract.abstract_lead_ban),
        "attribution_condition:",
        _render_lines(_attribution_lines(contract)),
        "fallback_copy:",
        _render_lines(contract.fallback_copy),
    ]

    if mode == "repair":
        prompt.extend(
            [
                "repair_context:",
                _render_lines(
                    [
                        f"修正対象 fail_axes: {fail_axis_labels}",
                        "現 draft の正しい箇所は保持し、validator fail の出た箇所だけを補修する。",
                    ]
                ),
                "current_draft:",
                current_draft_block,
                "minimum_diff_rubric:",
                _render_lines(MINIMUM_DIFF_REPAIR_RUBRIC),
            ]
        )
    else:
        prompt.extend(
            [
                "output_mode:",
                _render_lines(
                    [
                        "初稿は source facts にある事実だけで組み立てる。",
                        "後段 validator を前提に、ブロック欠落・title/body ずれ・出典漏れを初稿で持ち込まない。",
                    ]
                ),
            ]
        )

    prompt.extend(
        [
            "output_rules:",
            _render_lines(
                [
                    "本文のみを返す。前置き・注釈・JSON・コードブロックは禁止。",
                    "source に無い固有名詞・数値・日付・発言を追加しない。",
                ]
            ),
        ]
    )
    return "\n".join(prompt)


__all__ = [
    "CONTRACTS",
    "FixedLanePromptContract",
    "MINIMUM_DIFF_REPAIR_RUBRIC",
    "PromptMode",
    "build_fixed_lane_prompt",
    "get_contract",
    "supported_fixed_lane_subtypes",
]
