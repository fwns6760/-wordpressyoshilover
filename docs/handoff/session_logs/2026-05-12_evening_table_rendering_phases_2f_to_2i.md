# 2026-05-12 evening — Table rendering phases 2F → 2I handoff

これは午後の `2026-05-12_pm_table_rendering_phases_2a_to_2e.md` の続編で、
夕方〜夜の作業(Phase 2F-2I)を覚えておくための引継ぎ。
午後分(2A → 2E)はそちらを先に読むこと。

## 結論(本日の最終状態)

- 1日で **11 phase 連続着地・本番反映**: 2A → 2A-1 → 2B → 2C → 2D-A → 2D-B → 2E → 2F → 2G → 2H → 2I
- prod 最終 revision: **`yoshilover-fetcher-00413-yix`** = commit **`0dcb423`** = Phase 2I
- prod / canary `/health` = 200(11 回の deploy で 1 度も rollback なし)
- full suite: **3644 tests / failures=2**(2 件は pre-existing、Phase 2F-2I 起因 0)
- 追加 runtime cost: **¥0**(NPB 公式 / Yahoo Sportsnavi いずれも無料 + cache)
- 公式 X / WP 公開 mutation には一切触っていない(noindex 維持、SNS 解放は user 判断のまま)

## Phase 別の短い要約

| Phase | commit | revision | やったこと |
|---|---|---|---|
| 2F | `df7271b` | 00407-vod | NPB公式 `box.html` parser(per-batter atbat / per-pitcher detail / nested table stack scan) + 4 sub-table render |
| 2G | `3e1759b` | 00409-xav | NPB block と Yahoo W/L/S sub-block の合成(helper 抽出 + 並走描画)。一時的に Yahoo HTTP を常時 fetch に変更 |
| 2H | `c64aadb` | 00411-poq | NPB pitcher row[0] (○/●/S/H) から W/L/S を直接 derive、Phase 2G で追加した Yahoo HTTP を removable に戻す |
| 2I | `0dcb423` | 00413-yix | NPB公式 `playbyplay.html` parser + 得点プレー timeline 描画(本塁打 / 適時 / 犠飛 / 押し出し / スクイズ keyword filter) |

詳細は `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md` の Phase 2F-2I section(8 軸 template で 8 項目)。

## 1日合計の table marker(11 種類が本番で fires しうる)

- `nomotoke-card-compact-lineup` — 1軍/2軍 hochi compact lineup table(Phase 2A / 2A-1)
- `nomotoke-card-emoji-lineup` — 1軍 keycap-emoji lineup table(Phase 2B)
- `nomotoke-card-starter-rotation` — 先発ローテ arrow chain(Phase 2C)
- `nomotoke-card-postgame-result` — Yahoo box / 散文 postgame の試合結果 header(Phase 2D-A / 2D-B)
- `nomotoke-card-postgame-inning` — Yahoo or NPB inning table(Phase 2D-B / 2F)
- `nomotoke-card-postgame-pitchers` — W/L/S 投手 summary(Phase 2E / 2H、Yahoo or NPB 由来)
- `nomotoke-card-postgame-batter` — NPB per-batter atbat grid(Phase 2F)
- `nomotoke-card-postgame-pitcher-detail` — NPB per-pitcher line(Phase 2F)
- `nomotoke-card-postgame-scoring-plays` — playbyplay 得点プレー timeline(Phase 2I)

tail inject 優先順:
NPB box(fires時)→ NPB W/L/S → NPB scoring-plays → starter-rotation → postgame-result → postgame-inning(NPB ない時 Yahoo / NPB ない時 散文)→ ファンの声 …

## 不変・不可触(次セッションへ)

1. Phase 2A-2I 全 parser / renderer / fetcher logic 不変(各 phase の work_log §8 を尊重)
2. NPB box `_iter_outer_tables` / `_flatten_inner_tables` stack-scan は nested `table_inning` 対応の中核、触ると pitcher table 取りこぼし
3. NPB playbyplay `_HALF_INNING_RE`(`com\d+-\d+` id 形式)も NPB 側の規約に依存、変更不可
4. `_NPB_GIANTS_GAME_URL_RE = r"/scores/(\d{4})/(\d{4})/([a-z]+-g-\d+|g-[a-z]+-\d+)/"` は box / playbyplay 両 fetcher が再利用
5. fixture `tests/fixtures/npb_score_2026_0510_d-g-08_*.html`(box / playbyplay / roster)は real NPB HTML、再加工不可
6. tail inject の subtype 描画順(NPB → W/L/S → scoring-plays)は CSS / 観察 query を壊さないよう不変

## 並走中に起きた事故(再発防止用 note)

Phase 2I 実装中、Codex 並走 lane(`9120618` 324-QA fan_voice_pool scaffolding、`+97` lines in `src/rss_fetcher.py`)が私の 4 edits の合間に commit を入れたところ、

- 私の 4 Edit のうち **import block 1 件だけ persist、残り 3 件(変数宣言・fetch・renderer・tail inject)が消失**
- Edit tool は全て "updated successfully" を返していた(silent loss)

**仮説**: 並走 commit 中の stale file snapshot に Edit が当たり、後続の git auto-merge / rebase 相当処理で先行 Edit が drop された可能性

**対応**:
- Phase 2I は full grep(`postgame_npb_pbp_facts` / `fetch_today_giants_npb_playbyplay_facts` 等)で 4 edits 全て persist 確認 → 通過
- **次回の運用ルール**: 大型 multi-edit 便の後は必ず grep で全 edit が working tree に残っているか verify する(particularly 並走 commit が同 file を触る場合)

## 残課題(明日以降)

### A. 自然発火 verify(passive、最優先)

- 本日試合(中日 vs 巨人)完了後の publish 記事(WP REST `/wp-json/wp/v2/posts?categories=試合速報&per_page=3` 程度)に
  - `nomotoke-card-postgame-batter`(NPB box が fires したか)
  - `nomotoke-card-postgame-pitcher-detail`
  - `nomotoke-card-postgame-pitchers`(NPB W/L/S が derive されたか)
  - `nomotoke-card-postgame-scoring-plays`(playbyplay scoring が render されたか)
- が emit されているか確認
- もし NPB fetch 失敗(`postgame_npb_fetch_skipped` warning)なら、URL regex / index page 構造を再点検

### B. pre-existing baseline 2 failures(独立 task)

- `test_game_live_primary_sources_are_hochi_only` — `巨人公式X` / `日刊スポーツ 巨人` を allowlist に追加した影響、別 module で source policy config が同期されていない
- `test_main_passes_36_hour_window_for_postgame_skip_check` — `skip_mock.call_count` が 0 != 1、36h window 関連、別 module で stub 設定が更新されていない

両方 Phase 2F-2I と無関係、test 側の expected 値更新で済むと推測

### C. Phase 2J 候補(MVP 必須ではない、優先度低)

- opponent_pitcher per-inning split tables(box.html に subtable が含まれる、Phase 2F でスキップ)
- 連勝 / 連敗 streak indicator(別 source / chrono データ要)
- 次戦予告 mini-table(NPB schedule API or 既存 source)
- playbyplay 飛距離 / 球種(NPB に含まれるか未確認、他 fixture で要 verify)

### D. 別 stream の working tree dirty(touch 厳禁)

- `doc/active/305-QA-featured-media-source-priority.md`(eyecatch ticket、別 work)
- `config/player_eyecatch_map.json`(eyecatch mapping update、別 work)
- `doc/active/assignments.md`(board update、ChatGPT / Codex 並走)
- `build/063-v13-wp-admin/*`(admin frontend ZIP、別 deploy)
- 数十件の `??` 新規 file(別 stream の untracked、整理は別便)

これらは触らない。

## 次セッション開始時の必読(順序)

1. **本ファイル**(`2026-05-12_evening_table_rendering_phases_2f_to_2i.md`)
2. `docs/handoff/session_logs/2026-05-12_pm_table_rendering_phases_2a_to_2e.md`(午前-午後分)
3. `docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md`(11 phase の 8 軸詳細)
4. `git log --oneline -20`(Phase 2F-2I + Codex 並走 lane の commit 確認)
5. `gcloud run services describe yoshilover-fetcher --region=asia-northeast1` で revision `00413-yix` (commit `0dcb423`) が 100% を持っていることを verify
6. `MEMORY.md`(永続 lock 系の更新確認、本日 wind-down で大きな変更なし)

## 連絡先(human judgment 必要時)

- **公開記事の削除 / 書き換え** → user 判断(本日まだ 0 件)
- **X 投稿解放 / 新カテゴリ解放** → user 判断
- **MVP scope 拡張 / 縮小** → user 判断
- **法務 / 著作権 / プライバシー / 金銭・外部 API 課金増** → user 判断

それ以外は §11 4 領域外、Claude 自律で進めて OK。

---

**本日のステータス: GREEN(11 phase 着地、prod 稼働、rollback ゼロ、cost ¥0)**
