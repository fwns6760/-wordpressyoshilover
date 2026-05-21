# 382 古い記事 skip 仕様 (pro baseball 鮮度) — 2026-05-18 強化版

## meta

- status: CLOSED LIVE_DEPLOYED_VERIFIED (commit `270950a` 「382: stale content date skip — year context check 追加 + comprehensive tests (P1)」 landed、 yoshilover-fetcher 現 image `title-cap-warn-07d24d2` に含まれ LIVE、 2026-05-21 prod log で `stale_rss_entry` skip (source_age_hours: 336.0 等) 実発火確認、 5/14 memory `feedback_stale_content_date_skip_required` supersede)
- priority: P1 (mail noise 直結)
- owner: Claude (実装)、 user (受け入れ)
- created: 2026-05-18 EVENING
- supersedes: `[[feedback_stale_content_date_skip_required]]` (2026-05-14)

## user 仕様 (lock)

**pro baseball の news cycle は短い。 「5月17日朝」 のニュースは 5月18日午後には既に古い。**

source RSS が今日配信されていても、 内容が **昨日以前の event** を指す記事は **draft / publish / mail 全段階で skip** する。

## skip 対象

| field | 検出 |
|---|---|
| title / summary 内 keyword | 「昨日」「昨夜」「前日」「前夜」「先日」「凱旋」「翌朝」 (relative date) |
| title / summary 内 | 「N日」「N日の」「N日に」「N日から」「N日付」 + N < today (absolute date) |
| title / summary 内 | 「M月N日」「M/N」 + 該当日 < today (absolute date、 month 違いも include) |

# 対象 category

- 試合速報
- 選手情報
- 首脳陣
- postgame
- lineup

= 鮮度が命の category。 program / promotion / record / event 告知系は **除外** (これらは過去 reference でも valid)。

## 既存実装 (2026-05-14 既存)

`src/rss_fetcher.py:_should_skip_prior_event_postgame`:
- relative keyword (`昨夜/昨日/前夜/前日/先日/凱旋/翌朝`) で skip
- category 試合速報 / 選手情報 / 首脳陣 限定

## 不足 (2026-05-18 強化必要)

1. **absolute date check 未実装** = 「17日」「5月17日」「5/17」 等が today より前 でも skip しない
2. **判定 timing が draft 作成時のみ** = 既に draft 化された entry は通る (mail に流入)
3. **today の定義** = JST 00:00 区切り

## 実装案

### A. `_should_skip_stale_content_date` (新規)

```python
def _should_skip_stale_content_date(category: str, title: str, summary: str,
                                    now: datetime) -> tuple[bool, str]:
    """title/summary の date keyword が today より前なら skip。
    
    Returns (should_skip, reason)。
    """
    if category not in _STALE_CHECK_CATEGORIES:  # 試合速報/選手情報/首脳陣
        return False, ""
    text = _strip_html(f"{title} {summary}")
    today_jst = now.astimezone(JST).date()
    
    # relative keyword (既存 _PRIOR_EVENT_TITLE_MARKERS と重複でも OK)
    if any(m in text for m in ("昨日", "昨夜", "前日", "前夜", "先日", "凱旋", "翌朝")):
        return True, "stale_content_date:relative"
    
    # absolute date: 「N日」 form (1-31)
    for m in re.finditer(r"(\d{1,2})日(?:の|に|から|付|から)?", text):
        day = int(m.group(1))
        if 1 <= day <= 31 and _is_past_day_in_jst(day, today_jst):
            return True, f"stale_content_date:absolute_day_{day}"
    
    # absolute date: 「M月N日」 / 「M/N」 form
    for m in re.finditer(r"(\d{1,2})[月/](\d{1,2})日?", text):
        month, day = int(m.group(1)), int(m.group(2))
        # year は推定 (current year base、 month wrap で前年も考慮)
        if _is_past_month_day(month, day, today_jst):
            return True, f"stale_content_date:absolute_{month}_{day}"
    
    return False, ""
```

### B. 既存 `_should_skip_prior_event_postgame` を 拡張

current code (line 4693) を新 helper 呼出に統合、 または並行 OR で適用。

### C. 適用 point

- fetcher (draft 作成前): 既存 stale skip 経路と同じ場所で check
- publish-notice scanner (mail 通知前): scan_direct_publish_phase で post の title/summary check (defensive)

## 不可触

- program 系 (試合スケジュール表 / 月間予定 等) は **過去日付 reference でも valid** → category gate で除外
- 記録系 (「150勝」「300号」 等 milestone) は **過去 N 年の event** だが「現在話題」 → 別 logic で keep (今 spec では絞れない、 follow-up 必要)
- record 記事の「N年前 / N回目」 等の歴史 reference は **過去日付ではない** → 検出から除外

## 副作用想定

| 副作用 | 規模 |
|---|---|
| program 系で「7月17日 イベント」 等の future date を誤判定 | category 除外で OK |
| 「150勝」 milestone 記事に「5月18日 達成」 を含む場合、 same-day なので skip 対象外 | OK |
| 「N年前」 等の歴史 reference (「2019年5月17日」 等) | year context あり、 N < today だけで判定すると誤 skip → year 一致 check 必要 |
| 「5月18日 18時から」 (今夜の予定) を「過去 5月18日」 と誤判定 | same day = skip 対象外、 OK |

## 受け入れ条件 (user)

1. 5月18日 19:00 に mail で「5月17日朝」 系 post が **来ない**
2. 当日 (5月18日) の試合 / 練習 / コメント記事は **来る**
3. program / event 告知 (「7月17日 イベント」 等の future 日付) は **来る**
4. 「150勝」 milestone 系は **当日達成なら来る**、 過去 milestone reference は来ない

## 完了条件

1. `_should_skip_stale_content_date` 新規実装 + tests
2. fetcher draft 作成段階で適用、 既存 prior_event_postgame と統合
3. publish-notice scanner 段階で 2 段目 check (defensive)
4. dry-run で 5月17日 系 sample title を skip evidence 出す
5. fetcher build + deploy
6. publish-notice build + deploy (scanner side check 入る場合)
7. 自然 fire で 5/17 系が mail に来ない verify

## 不可触範囲

- WP plugin 設定 (SEO PACK 等)
- Cloud Scheduler
- env / Secret
- X / SNS 投稿経路
- 既存 publish 済記事
- ヨシラバー fallback eyecatch (commit `7761bff` 不変)
- mail format / brand / token / GCS one-shot (今 session で完成済の挙動 不変)
