# INCIDENT 2026-05-12 evening — Publish 30 min 停止(UnboundLocalError)

**Severity**: P0(prod publish 機能停止)
**Duration**: ~30 min(20:45 JST 検知 〜 21:25 JST 復旧 deploy 完了)
**User impact**: 2 article publish 失敗 / 投稿 0 / live window publish 機能停止

## 結論(短く)

- prod の publish loop で `_article_images` / `title_template_key` の **UnboundLocalError** が発生し、tag_scrape / 非 X URL passthrough 記事の publish が 100% 失敗
- 原因は **Phase 2F-2I の deploy とは無関係**、別 stream の 2 つの commit(`2d5c334a` 19:00 JST eyecatch fix + `0cc0bdf` 19:29 JST source role 追加)の組み合わせ
- 一次対応 = traffic rollback(Phase 2G = `00409-xav` = `3e1759b`)で publish 復活
- 二次対応 = hotfix A(default 化、`802511f`) + hotfix B(else パス正規代入、`b8a7f01`)を直列で deploy
- 21:25 JST に hotfix B revision `00417-wuw` 100% flip 完了、21:30 JST の次回 `/run` で完全復旧 verify 中

## Timeline

| 時刻(JST) | 時刻(UTC) | event | commit / revision |
|---|---|---|---|
| 10:34 | 01:34 | `3854e542` "fix: prefer source article images for eyecatch"(_article_images 代入を helper 化)— 無罪 refactor | - |
| 19:00 | 10:00 | `2d5c334a` "fix(eyecatch): player photo priority"— **真犯人 #1**(else パス外で `if featured_media == 0 and _article_images:` 参照を追加) | - |
| 19:29 | 10:29 | `0cc0bdf` "config: 巨人公式X + 日刊スポーツ巨人 を game_live_primary 追加"— **真犯人 #2**(else パスを通る source が live window で active 化) | - |
| 20:00-20:30 | 11:00-11:30 | Phase 2F → 2H 連続 deploy | `df7271b` → `c64aadb` |
| 20:30 | 11:30 | `/run`: 投稿 4 / エラー 0(Phase 2G 配下、健全)| `00409-xav` |
| 20:37 | 11:37 | Phase 2H deploy 完了(`c64aadb` → revision `00411-poq`) | - |
| 20:45 | 11:45 | `/run`: 投稿 0 / **エラー 2**(初発症) | `00411-poq` |
| 21:00 | 12:00 | `/run`: 投稿 0 / **エラー 2**(継続) | `00411-poq` |
| 21:01 | 12:01 | Phase 2I deploy(`0dcb423` → `00413-yix`、100% flip)| `00413-yix` |
| 21:04 | 12:04 | Codex 並走 `88609cc` 326-QA ticket doc-only commit | - |
| 21:15 | 12:15 | user 質問「30 分来ない?」(検知) | - |
| 21:18 | 12:18 | error log で UnboundLocalError 特定、rollback 判断 | - |
| 21:18 | 12:18 | traffic rollback `00413-yix` → `00409-xav`(Phase 2G、healthy) | - |
| 21:19 | 12:19 | Root cause 特定(line 23827 else branch unbound)| - |
| 21:20 | 12:20 | hotfix A commit(`802511f`、for-loop 先頭 default 化)| - |
| 21:22 | 12:22 | hotfix A build SUCCESS、user が deploy 前に「正規修正?」確認 | - |
| 21:23 | 12:23 | hotfix B commit(`b8a7f01`、else パスで `_extract_source_article_image_urls` + `title_template_key=_passthrough_label`)| - |
| 21:25 | 12:25 | hotfix B build SUCCESS → revision `00417-wuw` 100% flip | `00417-wuw` |
| 21:30 | 12:30 | 次回 `/run` で publish 復活 verify(本記録 commit 時点では monitor 待機中)| - |

## VERIFY NOTE (2026-05-13 追記)

- traffic: `00417-wuw` 100% を維持
- 5/12 21:30 JST 以降の Cloud Run log で `UnboundLocalError` 0 件
- 2026-05-13 朝の `/run`(JST):
  - 06:01: エラー=0
  - 07:01: 投稿=9 / エラー=0
  - 08:01: 投稿=2 / エラー=0
- incident は完全収束、`RESTORE-2026-05-08-MORNING-RELIABILITY` も同 verify で close (2026-05-13)

## Root cause(技術)

### コード構造の bug

`src/rss_fetcher.py` の publish for-loop(line 22917-)に、**if 分岐内のみ変数代入 + 後段の try block で無条件参照** という latent bug が存在:

```python
for item in prepared_entries:
    if source_type in {"news", "social_news"}:
        ...
        _article_images = _extract_source_article_image_urls(...)   # line 23173
        title_template_key = _rewrite_display_title_with_guard(...) # line 23192
        ...
    else:
        # tag_scrape / 非 X URL passthrough → 代入なし
        content = ...
        _passthrough_label = "non_x_url_passthrough"
        ...
    
    try:                                                            # line 23856
        ...
        extra_images=_article_images[1:],                           # line 23474 ← unbound!
        ...
        if featured_media == 0 and _article_images:                 # line 23895 ← unbound!
        ...
        enrichment_template_key=str(title_template_key or ""),      # line 23908 ← unbound!
```

### latency と trigger

- **2026-05-08 14:46**(`7b886946`): else パス用の eyecatch 補完 comment(「`_article_images` は上の source_type 分岐で populate 済」)が書かれた — この時点で誤った前提が文書化
- **2026-05-10**(`7d342bc4`): tag_scraper 経路の image 補完拡張 — `_article_raw_html` 系の if-branch 内側拡張
- **2026-05-12 19:00**(`2d5c334a`): eyecatch player photo priority fix で `if featured_media == 0 and _article_images:` を try block 内側に追加 — **コメントの誤った前提を信じて参照を追加**、これが直接原因
- **2026-05-12 19:29**(`0cc0bdf`): 巨人公式X + 日刊スポーツ巨人 を `game_live_primary` に追加 — **else パスを通る記事が live window(17-21時 JST)で active 化**、trigger

つまり「**3 件の commit が時間差で**」累積し、live window 中の特定 source_type 記事が publish loop に入った瞬間に発火。test では捕捉できなかった(integration test の fixture は news/social_news 型のみ)。

## 一次対応(rollback)

- `gcloud run services update-traffic --to-revisions=yoshilover-fetcher-00409-xav=100`
- Phase 2G(`3e1759b`)に traffic を戻し publish 機能復活
- canary `00407-vod` / `00411-poq` / `00413-yix` は 0% に退避

## 二次対応(hotfix)

### A: defensive default(`802511f`)

```python
for item in prepared_entries:
    _article_images: list = []
    title_template_key: str = ""
    ...
```

for-loop 先頭で default 化。crash は永続的に消える。else パスの記事は eyecatch fallback と template_key fallback で「動くが画像なし / template generic」状態。

### B: else 分岐の正規代入(`b8a7f01`)

else branch 内で if-branch と同じ画像抽出 logic を mirror、`title_template_key = _passthrough_label`:

```python
else:
    ...
    entry_obj_else = item.get("entry") if isinstance(item.get("entry"), dict) else {}
    _article_raw_html_else = ""
    if source_type == "tag_scrape":
        _article_raw_html_else = str(entry_obj_else.get("_html") or "")
        if not _article_raw_html_else:
            _article_raw_html_else = _fetch_url_html(post_url, max_bytes=240000, timeout=12)
    _article_images = _extract_source_article_image_urls(
        source_type, entry_obj_else, post_url, _article_raw_html_else, max_images=3,
    )
    _article_images = _filter_image_candidates(_article_images, post_url, logger)
    _article_images = _refetch_article_images_if_empty(_article_images, post_url, logger, max_images=3)
    title_template_key = _passthrough_label
```

これで else パスでも実 candidate と正規 template_key を try block が見る。

### A + B 両方残してる理由

- B が正規修正なので A は技術的に redundant
- ただし A を削除すると、将来 Codex 並走 lane が新しい `elif` を if/else に挟んで forget assignment した時に同じ事故が再発
- belt-and-suspenders として A を残置(defense-in-depth、可読性 sacrifice は許容)

## 学んだこと(future incident 防止)

### 1. コメントの前提を信じて参照を追加するな

`2d5c334a` の commit メッセージ:
> _article_images は上の source_type 分岐で populate 済、image_urls 空なら関数が 0 を返すので safe。

このコメント自体が **else パスで unbound になる事実を見落としていた**。同様のコメントを信じて参照を追加すると同種事故が再発する。

**ルール**: コメントを信じて変数を参照する前に、grep で「全 code path で assign されているか」を verify せよ。

### 2. 巨大 if/else は latent bug の温床

main() 関数 2000+ 行、if/else は 800 行スパン。新 reference を追加する人は全 branch を確認できない。

**ルール**: if/else 内で同じ変数群が共通使用される pattern は、closure / function 抽出すべき。今回の publish loop body は将来 `process_publish_iteration(item) -> PublishResult` 等に切り出す候補。

### 3. integration test の coverage gap

`tests/test_rss_fetcher_postgame_table.py` は news/social_news 型のみ fixture 化、tag_scrape / 非 X URL passthrough の publish loop entry は未 cover。

**ルール**: 主要 source_type(news / social_news / tag_scrape / x_short_player / oembed)それぞれで「publish loop が UnboundLocalError なく完走する」最小 smoke test を追加すべき。今回の事故は test 1 件あれば deploy 前に検出できた。

### 4. 並走 commit の組み合わせ事故

3 つの commit(`7b886946` + `2d5c334a` + `0cc0bdf`)はそれぞれ単独では bug を顕在化しない。**累積で初めて発火**。

**ルール**: rollout cadence が早い repo では「全 commit 単独 OK」と「累積 OK」を区別すべき。staging 環境で 1 日分の累積を検証してから prod へ流す pipeline が理想。今は no staging、prod 直行運用なので、せめて smoke test を increase。

### 5. user 報告経由で検知した

production 障害を **user の「30 分来ない?」質問で検知**。自動 alert が未整備(`audit-notify-6x` は PAUSED、`postgame-auto-daily` は 22:30 JST、error rate alert なし)。

**ルール**: `/run` が 連続 2 回 投稿 0 + エラー ≥1 を返したら Cloud Monitoring alert を fire する設定を追加(別 ticket、user 判断境界 — Scheduler 操作 含むので).

## 次セッション必読

1. **本ファイル**
2. `/home/fwns6/code/wordpressyoshilover/docs/handoff/session_logs/2026-05-12_evening_table_rendering_phases_2f_to_2i.md`(本日 11 phase 着地)
3. `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md`(Phase 2A-2I 詳細)
4. `git log --oneline -30`(commit timeline、特に夕方の `2d5c334a` / `0cc0bdf` を確認)
5. `gcloud run services describe yoshilover-fetcher --region=asia-northeast1`(現 revision = `00417-wuw` = `b8a7f01` = hotfix B 含む)
6. 21:30 JST の `/run` 完了 log(`gcloud logging read`)で publish ≥1 / エラー 0 を verify

## Status(本記録 commit 時点)

- ✅ 一次対応(rollback)完了
- ✅ Root cause 特定
- ✅ Hotfix A commit + deploy
- ✅ Hotfix B commit + deploy + 100% flip
- ⏳ 21:30 JST `/run` で publish ≥1 / エラー 0 を verify
- ⏳ Phase 2I + hotfix の最終 prod 状態を session log update で fix

**現 prod revision**: `yoshilover-fetcher-00417-wuw` = commit `b8a7f01` = Phase 2I + hotfix A + B
