"""3 アカウント (フーガ / 缶詰 / ヨシラバー) 定期分析 → 結果を markdown 添付でメール送信。

spec: mkdocs_docs/spec/x-post-mail.md「定期実施」/ doc/reference/x_post_mail_branding_spec.md §3.2。
voice をズラさないため、 voice モデル兼ライバルの フーガ / 缶詰 と自分 (ヨシラバー) を RSSHub で
read-only 再分析し、 比較レポートを月次でメール (本文 = 要約、 添付 = full markdown)。

- X API 不使用 (自前 RSSHub の twitter/user route)、 Gemini 不使用、 追加課金なし。
- いいね/RT 実数は RSSHub では取れない (他人 timeline read 不可) → 投稿パターンのみ。
"""
from __future__ import annotations

import argparse
import html as _html
import logging
import os
import re
import statistics
from datetime import timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

from src.mail_delivery_bridge import Attachment, MailRequest, send as bridge_send

LOG = logging.getLogger("rival_account_analysis")
_RSSHUB_BASE = "https://rsshub-487178857517.asia-northeast1.run.app"
JST = timezone(timedelta(hours=9))

# (handle, 表示名, 役割) — voice モデル 2 人 + 自分
_ACCOUNTS = [
    ("EH87EazmV9D2eSw", "フーガ", "戦術推論 (起用/打順/運用/人事)"),
    ("kandume92", "缶詰", "辛口の本音 + 理由 + ユーモア・ライブ"),
    ("yoshilover6760", "ヨシラバー", "自分 (データ掲示板)"),
]
_ENDERS = ("だわ", "だよな", "だな", "かな", "気がする", "と思う", "思います", "ですね", "ですよ", "してんな", "笑")
_TOPICS = ("打順", "スタメン", "起用", "継投", "抹消", "昇格", "先発", "ブルペン", "監督", "運用", "打線", "守備", "ドラフト", "グッズ", "アンケート")


def _fetch(handle: str, *, limit: int = 40, timeout: int = 20) -> str:
    url = f"{_RSSHUB_BASE}/twitter/user/{handle}?limit={limit}"
    req = Request(url, headers={"User-Agent": "yoshilover-rival-analysis/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (自前 RSSHub のみ)
        return resp.read().decode("utf-8", errors="replace")


def _strip(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", _html.unescape(s or ""))
    s = re.sub(r"https?://\S+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def analyze_account(handle: str, *, fetch=_fetch) -> dict:
    """RSSHub feed から投稿パターンを集計。 取得失敗は {} (caller が skip)。"""
    try:
        xml = fetch(handle)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch failed handle=%s: %r", handle, exc)
        return {}
    items = re.findall(r"<item\b.*?</item>", xml or "", re.S | re.I)
    rt = img = vid = ank = 0
    dates = []
    texts: list[str] = []
    for it in items:
        tm = re.search(r"<title\b[^>]*>(.*?)</title>", it, re.S | re.I)
        title = _html.unescape(tm.group(1)) if tm else ""
        dm = re.search(r"<description\b[^>]*>(.*?)</description>", it, re.S | re.I)
        desc = dm.group(1) if dm else ""
        body = _strip(desc)
        if title.strip().startswith("RT "):
            rt += 1
        elif body:
            texts.append(body)
        if "amplify_video_thumb" in desc or "ext_tw_video_thumb" in desc:
            vid += 1
        elif "pbs.twimg.com/media" in desc:
            img += 1
        if "アンケート" in desc or "投票" in desc:
            ank += 1
        pm = re.search(r"<pubDate>(.*?)</pubDate>", it)
        if pm:
            try:
                dates.append(parsedate_to_datetime(pm.group(1)))
            except (TypeError, ValueError, IndexError):
                pass
    hours: dict[int, int] = {}
    for d in dates:
        jh = d.astimezone(JST).hour
        hours[jh] = hours.get(jh, 0) + 1
    ds = sorted(dates)
    span_days = (ds[-1] - ds[0]).total_seconds() / 86400 if len(ds) > 1 else 0.0
    rapid = sum(1 for i in range(1, len(ds)) if (ds[i] - ds[i - 1]).total_seconds() < 1800)
    joined = " ".join(texts)
    lens = sorted(len(t) for t in texts)
    return {
        "n": len(items),
        "own": len(texts),
        "rt": rt,
        "img": img,
        "vid": vid,
        "ank": ank,
        "rapid": rapid,
        "rapid_pct": round(100 * rapid / len(items)) if items else 0,
        "rt_pct": round(100 * rt / len(items)) if items else 0,
        "per_day": round(len(items) / (span_days / 1), 1) if span_days > 0 else None,
        "span_days": round(span_days, 1),
        "median_len": lens[len(lens) // 2] if lens else 0,
        "mean_len": round(statistics.mean(lens)) if lens else 0,
        "enders": {e: joined.count(e) for e in _ENDERS if joined.count(e) > 0},
        "topics": {t: joined.count(t) for t in _TOPICS if joined.count(t) > 0},
        "top_hours": sorted(hours.items(), key=lambda x: -x[1])[:5],
        "samples": texts[:5],
    }


def render_report(results: list[tuple[str, str, str, dict]], *, date_label: str) -> str:
    """markdown 比較レポートを返す。"""
    lines = [
        f"# ヨシラバー vs ライバル2人 定期分析 ({date_label})",
        "",
        "RSSHub 実投稿 (X API 不使用 / read-only)。 ※いいね・RT の実数は取得不可、 投稿パターンのみ。",
        "",
        "## 一覧",
        "",
        "| アカウント | 役割 | 投稿/日 | RT% | 連投% | 動画 | 画像 | アンケ | 中央字数 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for nm, _h, role, a in results:
        if not a:
            lines.append(f"| {nm} | {role} | (取得失敗) | | | | | | |")
            continue
        pd = a["per_day"] if a["per_day"] is not None else "?"
        lines.append(
            f"| {nm} | {role} | {pd} | {a['rt_pct']}% | {a['rapid_pct']}% | "
            f"{a['vid']} | {a['img']} | {a['ank']} | {a['median_len']} |"
        )
    for nm, _h, _role, a in results:
        if not a:
            continue
        lines += [
            "",
            f"## {nm} 詳細",
            f"- 投稿 {a['own']}本人/{a['n']}全 ・ RT {a['rt']} ・ 期間約{a['span_days']}日",
            f"- 形式: 動画{a['vid']} / 画像{a['img']} / アンケ{a['ank']} / 連投(30分内){a['rapid']}",
            f"- 字数: 中央{a['median_len']} 平均{a['mean_len']}",
            f"- 語尾/口調: {a['enders']}",
            f"- 話題: {a['topics']}",
            f"- 投稿時間帯(JST上位): {a['top_hours']}",
            "- サンプル:",
        ]
        lines += [f"  - {s[:120]}" for s in a["samples"]]
    lines += [
        "",
        "## 見るべき signal",
        "- フーガ/缶詰: 新しい語彙・話題・形式 → `_SYSTEM_PROMPT_YOSHILOVER` の few-shot へ反映",
        "- ヨシラバー: RT% / 媒体タイトル転載が下がり、 オリジナル voice 比率が上がってるか",
    ]
    return "\n".join(lines)


def _resolve_recipients(override: list[str] | None) -> list[str]:
    if override:
        return [r.strip() for r in override if r.strip()]
    raw = os.environ.get("MAIL_BRIDGE_TO") or os.environ.get("MAIL_TO") or ""
    return [r.strip() for r in raw.replace(";", ",").split(",") if r.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="3アカウント定期分析→添付メール")
    parser.add_argument("--dry-run", action="store_true", help="メール送信せずレポートを stdout に出す")
    parser.add_argument("--to", action="append", default=None, help="送信先 (省略時 MAIL_BRIDGE_TO env)")
    parser.add_argument("--date-label", default=None, help="レポート日付ラベル (省略時は省く)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    results = [(nm, h, role, analyze_account(h)) for (h, nm, role) in _ACCOUNTS]
    ok = sum(1 for *_x, a in results if a)
    LOG.info("rival_analysis fetched ok=%d/%d", ok, len(results))
    date_label = args.date_label or ""
    report = render_report(results, date_label=date_label)

    if args.dry_run:
        print(report)
        return 0

    recipients = _resolve_recipients(args.to)
    if not recipients:
        LOG.error("No recipients (MAIL_BRIDGE_TO env or --to). aborting.")
        return 2
    summary = "3アカウント(フーガ/缶詰/ヨシラバー)の定期分析です。詳細は添付 markdown を参照。\n\n"
    summary += "\n".join(
        f"- {nm}: " + ("取得失敗" if not a else f"投稿/日{a['per_day']} RT{a['rt_pct']}% 連投{a['rapid_pct']}% 動画{a['vid']}")
        for nm, _h, _role, a in results
    )
    fname = f"rival_account_analysis{('_' + date_label) if date_label else ''}.md"
    mail = MailRequest(
        to=recipients,
        subject=f"【定期分析】ヨシラバー vs フーガ/缶詰 {date_label}".strip(),
        text_body=summary,
        attachments=[Attachment(filename=fname, data=report.encode("utf-8"), maintype="text", subtype="markdown")],
        metadata={"lane": "rival_account_analysis"},
    )
    result = bridge_send(mail, dry_run=False)
    LOG.info("rival_analysis mail status=%s", result.status)
    return 0 if result.status in {"sent", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
