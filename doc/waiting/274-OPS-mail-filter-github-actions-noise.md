# 274-OPS-mail-filter-github-actions-noise

| field | value |
|---|---|
| ticket_id | 274-OPS-mail-filter-github-actions-noise |
| priority | P2 (受信トレイ整理、本番影響なし) |
| status | READY_FOR_USER_APPLY |
| owner | user(Gmail 画面で手動適用) |
| lane | OPS |
| ready_for | user の Gmail 設定操作 |
| blocked_by | (なし) |
| doc_path | doc/active/274-OPS-mail-filter-github-actions-noise.md |
| created | 2026-04-30 |

## 結論

GitHub Actions の Tests failed 通知を Gmail フィルタで「GitHub Errors」ラベルへ振り分け、受信トレイから退避する。**コード・CI・GitHub Actions workflow・Cloud Run・publish-notice・Team Shiny From 設定は一切触らない**。

直近 04-30 朝に publish-notice 通知系で P0 デグレ復旧があったため、通知系本体への変更は **絶対禁止**。本ticket は Gmail 受信側のラベル振り分けのみ。

## 背景

### 維持対象(YOSHILOVER 本番通知、絶対変更しない)

| 種別 | From | To | Subject 例 |
|---|---|---|---|
| publish 通知 | Team Shiny / `y.sebata@shiny-lab.org` 系 | user Gmail | `【公開済】<title> \| YOSHILOVER` / `【要確認】RT 読売巨人軍...` |
| review 通知 | 同上 | 同上 | `【要review】<title> \| YOSHILOVER` |
| hold 通知 | 同上 | 同上 | `【hold:<reason>】<title> \| YOSHILOVER` |
| 古候補通知 | 同上 | 同上 | `【要確認(古い候補)】<title> \| YOSHILOVER` |

### 分離対象(GitHub Actions 失敗通知、ノイズ)

| field | value |
|---|---|
| From | `fwns6760/-wordpressyoshilover <-wordpressyoshilover@noreply.github.com>` |
| To | `fwns6760/-wordpressyoshilover <-wordpressyoshilover@noreply.github.com>` |
| Subject 例 | `Tests workflow run` / `All jobs have failed` / `Run failed: ... wordpressyoshilover` |

## 1. 推奨 Gmail フィルタ条件

### 推奨フィルタ A(安全側、GitHub の失敗通知のみ catch)

```
from:(noreply.github.com) subject:("All jobs have failed" OR "Tests workflow run" OR "Run failed")
```

- `from:` で `noreply.github.com` ドメインに限定
- `subject:` で **失敗系 subject に限定**
- PR レビュー依頼や Issue 通知など **役に立つ GitHub 通知は受信トレイに残る**

### 推奨フィルタ B(より広く、GitHub Actions 関連通知すべて catch)

```
from:(noreply.github.com) (subject:(workflow) OR subject:(failed) OR subject:(Run))
```

- フィルタ A より広く、Actions 関連通知全般を取る
- 通知量がさらに減る一方、成功通知も catch

### 非推奨候補(user 案 第一・第三 の安全性評価)

| user 候補 | 評価 |
|---|---|
| `from:(-wordpressyoshilover@noreply.github.com)` | Gmail の `from:` は `-` で始まる local-part を **検索演算子の除外と誤認**して動かない / 不安定の可能性。**非推奨**。 |
| `from:(noreply.github.com) subject:("Tests workflow run")` | 動くが「All jobs have failed」を catch しない。**部分的**。 |
| `from:(noreply.github.com) subject:("All jobs have failed")` | 動くが「Tests workflow run」を catch しない。**部分的**。 |

→ user 候補 第二・第三 を OR で合成した **推奨フィルタ A** が最良。

## 2. ラベル名

```
GitHub Errors
```

(user 指定通り)

## 3. Gmail での設定手順

### Step 1. ラベル作成

1. Gmail 左ペイン下部の「ラベルを作成」(または設定 → ラベル → 新しいラベルを作成)
2. ラベル名: `GitHub Errors`
3. 作成

### Step 2. フィルタ作成

1. Gmail 検索バー右端の **「検索オプションを表示」** ボタン(スライダー風アイコン)をクリック
2. 検索条件:
   - **From**: `noreply.github.com`
   - **件名**: `All jobs have failed OR Tests workflow run OR Run failed`
3. 右下「**フィルタを作成**」をクリック
4. 適用するアクションにチェック:
   - ☑ **受信トレイをスキップ(アーカイブする)**
   - ☑ **既読にする**
   - ☑ **ラベルを付ける** → `GitHub Errors` を選択
   - ☐ 削除する(チェックしない)
   - ☐ 迷惑メールにしない(チェックしない)
   - ☑ **○件の一致するスレッドにもフィルタを適用する**(既存 GitHub failure mail を一括退避)
5. 「**フィルタを作成**」をクリック

### Step 3. 動作確認

- Gmail サイドバー「GitHub Errors」ラベルをクリック → 既存の Actions failure mail が一覧表示されること
- 受信トレイ → 「fwns6760/-wordpressyoshilover」系の mail が消えていること
- 受信トレイ → YOSHILOVER 本番通知(`【公開済】` / `【要確認】` / `【要review】` / `【hold:】` プレフィックス)は残っていること

## 4. YOSHILOVER 通知を巻き込まない理由

| 観点 | 根拠 |
|---|---|
| From ドメイン分離 | YOSHILOVER 本番通知 = `shiny-lab.org` ドメイン / GitHub Actions = `noreply.github.com` ドメイン。**完全に別ドメイン**で重複なし。 |
| Subject prefix 分離 | YOSHILOVER は `【公開済】` / `【要確認】` / `【要review】` / `【hold:】` で始まる(全角【】記号)。GitHub は `Run failed` / `All jobs have failed` / `Tests workflow run`(英語、ASCII)。**マッチしない**。 |
| 推奨フィルタの絞り込み | `from:(noreply.github.com)` で必ず GitHub ドメインに限定 + Subject で失敗系限定。**Team Shiny From 経由の mail は構造的に絶対 catch されない**。 |
| 削除しない設定 | 「削除する」は **チェックしない**。誤動作してもラベル付与のみ、メール本体は復旧可能。 |
| 迷惑メールに送らない | 「迷惑メールにしない」は **チェックしない**(Gmail デフォルトで迷惑メール扱いされない)。 |

## 5. デグレしない確認項目(受け入れ条件)

| # | 項目 | 確認方法 |
|---|---|---|
| 1 | GitHub Actions 失敗通知が受信トレイに出ない | 受信トレイを fresh で確認、`fwns6760/-wordpressyoshilover` 系が見えないこと |
| 2 | GitHub 通知は「GitHub Errors」ラベルで後から確認できる | 左ペイン「GitHub Errors」をクリック、過去通知が表示 |
| 3 | YOSHILOVER publish 通知は受信トレイに届く | publish-notice 次回 */5 発火後、`【公開済】` mail が受信トレイに届くか観察(または既存 04-30 10:50 の mail で確認) |
| 4 | YOSHILOVER review/hold 通知も受信トレイに届く | 同上、`【要review】` / `【hold:】` mail がフィルタ非適用 |
| 5 | YOSHILOVER 「【要確認(古い候補)】」mail も受信トレイに届く | 267-QA 経由通知、From=Team Shiny でフィルタ非適用 |
| 6 | Team Shiny From (`y.sebata@shiny-lab.org` 系) は影響なし | Gmail 設定 → フィルタ → 作成したフィルタが From=`noreply.github.com` 限定であること |
| 7 | publish-notice service に変更なし | Cloud Run Job `publish-notice` の image / env / scheduler 不変 |
| 8 | GitHub Actions workflow に変更なし | repo `.github/workflows/` 不変 |
| 9 | repo / Cloud Run / Scheduler / Secret 不変 | 本 ticket は doc-only、コード変更ゼロ |
| 10 | 削除/迷惑メール扱いなし | フィルタ設定で「削除する」「迷惑メール」のチェックなし |

## 不可触(Hard constraints)

- GitHub Actions workflow 変更
- Tests workflow disable
- repo 設定変更(branch protection / actions / webhook)
- CI 修正
- publish-notice service / scanner / sender / scheduler / image / env 変更
- Team Shiny From 変更
- YOSHILOVER 通知 From / To 変更
- Cloud Run Service / Job 変更
- Cloud Scheduler 変更
- Secret Manager 変更
- env 変更
- Gmail API 経由での自動変更(user が画面で手動適用するのみ)
- user 承認なしのメール設定変更

## 適用主体

**user 自身**(Gmail Web UI で手動適用)。Claude / Codex は適用しない。

## rollback

Gmail 設定 → フィルタ → 作成したフィルタを **削除**。
ラベルを付けた既存 mail は受信トレイに戻る(GitHub Errors ラベル外し: ラベル削除時に「ラベルとそれを付けたメールへの影響」を選択)。

## 関連 ticket

- 267-QA(publish-notice 通知拡張、本日 P0 復旧):本 ticket は 267-QA 通知系を **触らない**ことが前提
- 274-QA(cost audit):無関係(別 lane)

## 完了条件

- user が Gmail で フィルタ + ラベル を適用
- 上記 §5 の 10 項目 すべて pass
- 通知系本体に変更なし(repo 不変、cloud 不変)

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
