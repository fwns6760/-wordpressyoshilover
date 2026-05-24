# 2026-05-24 quality gates deploy (3 gates + deploy hygiene)

## Scope

ニュース品質改善 3 ゲートの実装 + 恒久 deploy hygiene の lock。

## 実装 commit (feat/377-phase1c-mail-body-excerpt 上)

| commit | 内容 |
|---|---|
| `594e940` | title_body_nucleus_validator: 71314 型 lineup-announcement mismatch 検出 |
| `f987e47` | thin_body_validator: 1 ツイート水増し (thin_source_padding) 検出 |
| `f7686cf` | source_article_body_extractor: 媒体UI/nav + CSS/JS leak 除去 |
| `26b2f4a` | .gcloudignore: deploy hygiene 恒久 policy file |

テスト追加: 8 + 6 + 4 (24 ケース)。pytest 全 pass。

## prod 起点と release composition

- **fetcher prod 起点** = `c297e3d` (5/24 12:39 JST、image tag `mail-draft-label-20260524`)
- **guarded-publish prod 起点** = `8262003` (5/12、image tag `8262003`)
- fetcher は feat/377 HEAD まで進めて 3 commit ahead で済むが、guarded-publish は同じ HEAD まで進めると blast radius 大
- → guarded-publish は `release/quality-gates-guarded-publish-26b2f4a` worktree で `8262003` から cherry-pick (release HEAD = `2dfdb4e`)

## image build

| service | image tag | digest | build duration |
|---|---|---|---|
| yoshilover-fetcher | `quality-gates-26b2f4a` | `sha256:4c2bb2b5cb...` | 2m35s |
| guarded-publish | `quality-gates-2dfdb4e` | `sha256:31ae8db71f...` | 4m12s |

build context は .gcloudignore 効果で **540 files / 8.5 MiB** に圧縮。

## deploy

- **fetcher**: revision `yoshilover-fetcher-00640-tas` を `--no-traffic --tag=qgates` で deploy → canary URL `/health` smoke (HTTP 200 / 172ms / body=OK) → traffic 100% へ ramp → main URL `/health` 再 smoke (200/121ms)
- **guarded-publish**: Cloud Run Job `guarded-publish` の image を新 tag へ update。Scheduler `guarded-publish-trigger` は **pre-existing PAUSED 状態 (user 判断領域)** につき変更なし。次の user-initiated resume で新 image 自動 pickup

## 恒久 fix

`feedback_deploy_hygiene_policy_2026_05_24.md` を memory に lock:

1. `.gcloudignore` を repo 直下に常設 (secrets / logs / tests / dev artifact 除外)
2. release branch を **prod 起点** から `git worktree` で切る (origin/master 基準ではなく)
3. image tag に git short sha を埋め込む (例: `quality-gates-26b2f4a`)
4. dirty / untracked を build に bundled しない

これにより「working dir からそのまま deploy で 654 commit ahead が乗る」事故は再発しない。

## 残課題

- master が origin/master から 654 commit ahead で運用中。Layer C (master を prod-current に保つ workflow) は別 session で設計が必要。
- guarded-publish Scheduler の resume は user 判断。今 session は image update まで。
- 本番反映後の effective verification:
  - 71314 型 lineup-announcement mismatch のリアル発火件数 (log で確認)
  - thin_source_padding 発火件数 (false positive 監視)
  - extractor noise cleaner の効き目 (新規生成記事を grep で確認)

## refs

- 実装スレッド: 本セッション(2026-05-24)
- memory: [[feedback_deploy_hygiene_policy_2026_05_24]]
- release branch: `release/quality-gates-guarded-publish-26b2f4a` (HEAD: `2dfdb4e`)
