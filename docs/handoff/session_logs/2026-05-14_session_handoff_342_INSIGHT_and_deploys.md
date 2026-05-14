# 2026-05-14 セッション handoff — 342-INSIGHT 起票 + 5 deploy + 諸々

**作成**: 2026-05-14 PM
**前任**: Claude Code(本 session)
**次セッションへ**: 342-INSIGHT Phase 0 audit を本気でやる場合の前提と注意

---

## 1. 本 session で完了した production 反映(全て active)

deploy 順:

| commit | 内容 | image / 反映先 |
|---|---|---|
| `cf9b535` | 菅野智之 MLB 移籍除外 rule(rss_fetcher 3 prompt 箇所) + GIANTS NEWS DIGEST banner を nomotoke_card 11 種に展開 | yoshilover-fetcher rev `00482-pog` + broadcast-auto / lineup-auto / postgame-auto Jobs |
| `d749ed4` | publish-notice mail の `𝕏 で投稿する` intent URL に hashtag 自動付与(`#巨人` 固定 + title 内 player 名 抽出、最大 5) | publish-notice Job |
| `611b363` | fan voice h3 を canonical `💬 ファンの声（Xより）` で統一、`_dedupe_fan_voice_h3` を `_FAN_VOICE_BASE` 基準に変更、filler section drop(後の commit で fallback 置換に上書き) | fetcher + 3 Jobs |
| `fad09a2` | fan voice h3 を全 post に保証(`_ensure_fan_voice_section`)、X embed 無し section は body を `<p>関連ポストなし</p>` に置換、`thin_body_validator` で chrome として strip | fetcher rev `00494-yof` + 3 Jobs |
| `2a5fd7e` | media_xpost_selector の X embed 精度向上(time window 48h→24h、event keyword bonus +20、article publish JST hour で 2 tier step bonus: 17–23h=±3h / 0–16h=±10h、両側 +30) | fetcher rev `00498-san` + 3 Jobs |
| `bf306b9` | doc only: qa_backlog.md で 248-MKT-4 / -5 を DONE 化(実 production rendering 確認、commit `bb68e21`)、334-QA ticket doc を Phase 4 だけ残る形に更新、doc/README.md の 334 entry を PHASE_4_READY に変更 | doc only(production 影響なし) |

直近の deploy 検証は **post-deploy publish 出現待ち**(2026-05-14 PM 時点で全 deploy 完了、scheduler 自然発火で実 verify 可能)。

---

## 2. 342-INSIGHT 新規 ticket 起票完了

### file

- `doc/active/342-INSIGHT-data-driven-ranking-auto-publish.md`
- 内部 ticket_id / doc_path も全部 `342-INSIGHT-...`(341 残存 0、verify 済)

### GH Issue

- #21 `[342-INSIGHT] data-driven 定期 ranking 自動 publish 基盤 + 初版記事種`
- label: `enhancement` + `ticket:342-INSIGHT`
- URL: https://github.com/fwns6760/-wordpressyoshilover/issues/21

### scope(user 確定済)

- **B 案**(設計 + 初版 + 拡張可能 framework、私が初期提案した A/B/C 3 案のうちの B)
- INSIGHT-001〜009 で構築済 data 基盤(12 球団 batting/pitching、20+ advanced metrics、UZR proxy、`rank → article draft generator` 含む INSIGHT-008、`NL question → draft` 含む INSIGHT-009 rule-based)を活用
- pure rule-based、LLM 不使用(コスト 0)
- forward-only(過去 publish 不変)
- 初版候補 4(優先順):
  1. **月次 巨人選手 OPS / wOBA / ISO ranking**(月 1)
  2. **守備指標(UZR 代理)12 球団 rank**(月 1)
  3. **12 球団 OPS top 30 + 巨人選手の位置**(月 1)
  4. **直近 7 / 14 試合 hot/cold ranking**(週 1)

### status

- `DRAFT`、`user GO 待ち`(本格着手していない)
- 次は **Phase 0 read-only audit** が予定

### Phase 0 audit 着手時の必要 verify(本 ticket §10 から)

- INSIGHT DB の schema(advanced_metrics の field 一覧、defense proxy の field)
- 既存 `src/analysis/insight_*.py` の public API(再利用可能 helper)
- WP の category / tag 命名衝突 check(新 category 名選定)
- duplicate_guard が新 post type を skip しないか
- Cloud Scheduler の cron で「末日」発火を表現できるか
- 12 球団 batting/pitching の月次 sample 数(最小 PA / IP 閾値)
- WP REST 新 category 作成 + 新 post publish が既存 `WP_USER` 権限で可能か

---

## 3. 未着手 / 待機中の known item

| 項目 | 状態 | scope 主 |
|---|---|---|
| **342-INSIGHT Phase 0 audit** | user GO 待ち | 本 ticket |
| **334-QA Phase 4 canary**(player_voice_digest live ramp) | user GO 待ち(env `ENABLE_PLAYER_VOICE_DIGEST_DETECTION=1` apply)、§11 user 判断境界 | 別 ticket、Codex lane で Phase 1-3b 完了済 |
| **event_key_ledger fail**(`test_group_records_picks_player_anchor_over_empty_player`) | pre-existing 1 件、319-QA Regression Memo 欄に申し送り済(commit `47034cb`)、321-QA subtype routing に統合提案 | 別 ticket |
| **duplicate_prevention_golden 3 fail** | pre-existing(commit `24151ae` 由来、本 session の change と無関係) | 別 ticket / 別担当 |

---

## 4. 本 session で重要だった verification 学び(handoff の主目的)

### 4-A. ticket 番号の採番は **3 source 全部** verify する

本 session で **2 回番号衝突** した。両方とも commit log だけ見て採番 → GH Issue 側で既に landed していた既存 ticket と被った。

**衝突した試行**:

1. 338 → GH Issue #17 `[338-QA] タイトル「無失点」が「失点」に化ける bug` と衝突
2. 341 → GH Issue #20 `[341-FIX] tag_scrape の else 分岐 raw_html` と衝突
3. 342 で確定(これは衝突 verify 完了)

**今後の手順**: ticket 番号採番時は **必ず以下 3 source 全部** grep して未使用確認:

```bash
gh label list --search "ticket:"  # GH 側 label
gh issue list --search "<num>" --state all --json number,title  # GH 側 issue
ls doc/active doc/waiting | grep -oE "^[0-9]+"  # ローカル ticket file
git log --all --oneline --grep="<num>-"  # commit log(参考)
```

最後の commit log だけで判断するのは **silent skip**(本 session 2 回失敗の根因)。

### 4-B. verify と claim は分ける

本 session で複数の「silent skip」/「自己評価 OK」事故あり:

- 「11:00 batch で fan voice deploy verify できる」→ 11:00 batch は **公示テンプレ only** で fan voice section が元から無く、verify 対象外だった
- 「100 post sample で fan voice 重複 0」→ 重複 0 は正、ただし**最初の grep が narrow すぎて取りこぼし**、ユーザー指摘で wider sample 再 verify した
- 「low risk」「コスト 0」を verify せず claim → 各 case で grep / read で ground し直した

ユーザー何度も **「AI 最大事故源 = 記憶から再構成 / silent skip / 自己評価 OK」** リマインド。本 handoff の最重要 carry-over はこの方針。次 session も **必ず実 file / 実 data で ground する**。

### 4-C. ticket DOC と実 production が乖離するケース

本 session で発見:

- **248-MKT-4 / 248-MKT-5**(同選手回遊 / 同カテゴリ)は `qa_backlog.md` で `not-now` だったが、実 production で既に rendering 中(commit `bb68e21` で 2026-04-24 着地、別担当が実装後 doc 更新せず)
- **334-QA**: ticket doc で「Phase 1 着手判断待ち」だったが、Codex lane が Phase 1-3b まで commit 済(`78f1f79` / `5875247` / `c072884` / `cf80239` / `6d1d7a6` / `bf79c64` / `a008bdf`)、env flag OFF で dark ship 中

**教訓**: ticket status / qa_backlog の text を信用する前に **実 commit + 実 production HTML / src を verify**。doc は遅れる、実態が正。

### 4-D. release composition の事前 verify

本 session の deploy 5 件、いずれも `git log <prev_deployed>..HEAD` で **bundled commit を verify** してから build を fire した(`feedback_release_composition_verify_before_deploy.md` 準拠)。334-QA Phase 1-3b は **dark ship**(env flag OFF)で同梱、本番影響 0 を確認。

次 session でも deploy 前は同じ手順:

```bash
gcloud run services describe yoshilover-fetcher --region=asia-northeast1 --project=baseballsite \
  --format="value(spec.template.spec.containers[0].image)"  # 現行 image
git log --oneline <prev>..HEAD                              # 同梱 commit
git diff --stat <prev>..HEAD -- src/ config/                # src 変更範囲
```

---

## 5. 本 session 中 user から受けた永続 lock / 強い feedback

新規 lock は無し。既存 lock の再確認が多かった:

- **`feedback_publish_forward_must_check_gate_reason`** 路線(本文充実 / fan voice / banner / hashtag 全て forward-only、過去触らず)
- **`feedback_no_micro_user_check`** 路線(細かい確認を user に戻さない、deploy / commit / push は §11 4 領域以外は自律)
- **`feedback_3_choice_terse_report`** 路線(GO / HOLD / ROLLBACK の 3 択 + A.やったこと / B.結果 / C.異常 / D.次判断 4 行)

新規方針として固まったもの:

- **fan voice section policy**(2026-05-14 PM):
  - canonical label = `💬 ファンの声（Xより）`(1 種類のみ、plain は廃止)
  - X embed 無し section は body を `<p>関連ポストなし</p>` に置換(h3 残す、drop しない)
  - 全 post に fan voice h3 を保証(`_ensure_fan_voice_section`、env `ENABLE_FAN_VOICE_ENSURE` default ON)
- **X embed scoring policy**(2026-05-14 PM):
  - 24h window(48h からタイト化)
  - event keyword bonus +20(共有 token あり)
  - 試合中 article(JST 17–23h)= ±3h step bonus +30
  - 翌朝振り返り article(JST 0–16h)= ±10h step bonus +30
- **mail X intent hashtag policy**(2026-05-14):
  - 固定 `#巨人` + title から `find_all_allowlist_players` で抽出した player 名、最大 5

---

## 6. 次 session 開始時の必読(優先順)

1. **本 handoff doc**(本 file)
2. `AGENTS.md` § 7.5(GCP migration policy)
3. `CLAUDE.md`(全体ルール、特に §3 役割分担 / §10 自律範囲 / §11 user 判断境界 / §17 コスト hygiene / §31 監督ルール)
4. `docs/handoff/session_logs/2026-05-13_evening_session.md` 系(前日 session 経緯)
5. `doc/active/342-INSIGHT-data-driven-ranking-auto-publish.md`(本日起票 ticket)
6. `doc/active/qa_backlog.md`(248-MKT-4/5 を DONE 化、bf306b9 で更新)

---

## 7. 引き継ぎ後の最初の動き(推奨)

### Case A: 342-INSIGHT Phase 0 audit を進める場合

1. ticket §10 Regression Memo の "feasibility 確認事項(Phase 0 で audit)" を順に grep / read で ground
2. 結果を ticket doc に追記
3. Phase 0 完了 + Phase 1 spec 精度を上げてから user に GO 報告
4. **重要**: 採番 / claim 前に 4-A の 3 source verify を厳守

### Case B: 別 task が来た場合

- 本 handoff の §1 deploy 一覧で現状把握
- §3 未着手 known で別 ticket と被らないか check
- 着手前に必ず実 file / 実 production HTML で ground

### Case C: 次 deploy が必要になった場合

- §4-D の事前 verify 手順を踏む
- §11 4 領域(content / SNS / scope / 法務・コスト)以外は自律実行
- 完了後は §4-B の verification methodology 厳守

---

## 8. 触らないでほしいもの(明示)

- **Cloud Scheduler 既存 job の enable / pause / schedule**(本 session 中触ってない、次 session も基本触らない、新規追加のみ)
- **env / Secret Manager**(本 session 中触ってない、§11 user 判断境界)
- **master 以外への force push**(全 commit は `hotfix-eyecatch-hashtag` branch、push 後 PR にする場合は user 判断)
- **WP custom table schema**(本 session 中触ってない)
- **過去 publish 済 post の body / title / status / meta**(forward-only policy 厳守)

---

## 9. 本 session で残った dirty state(参考)

- `git status --short` でローカル untracked / modified が多数(本 session の change と関係ない ambient 状態、`feedback_ambient_dirty_provenance_boundary` 準拠で隔離)
- 本 session で commit 済 6 件(cf9b535 / d749ed4 / 611b363 / fad09a2 / 2a5fd7e / bf306b9)+ 342-INSIGHT ticket doc は **未 commit**(handoff 作成中、次 session で commit 判断)

---

## 10. user の現時点での mood / 期待値(私の観察)

- 本 session 中複数回「AI 最大事故源」リマインド → 私の verification 品質に懸念あり
- 即決断系の指示(`GO` / `A` / `B` 等)で進めるが、細部は私の verification を信頼する
- user は判断疲労を抱えている前提、open-ended 質問は禁止(`feedback_minimize_user_judgment`)
- 大きな mutation(env / SNS / scope / 法務・コスト)は §11 確認、それ以外 Claude 自律

次 session でも同じ温度感を維持してください。

---

(end of handoff)
