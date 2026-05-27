# :material-rocket-launch: Deploy 手順

ヨシラバーは複数の Cloud Run service / Cloud Run job が ==それぞれ個別の image== で動いている。
Dockerfile + cloudbuild config を持ち、 別々に build + deploy する。

## :material-shield-check: hygiene 3 点

1. `.gcloudignore` をリポジトリ root に置く (working dir 全部 upload を防ぐ)
2. release branch は prod 起点で切る (`master` ではなく `feat/377-phase1c-mail-body-excerpt` が active branch)
3. image tag に git short sha を埋め込む (例: `draft-label-dca4db5`)

## :material-image-multiple: image / build config 対応表

`ls Dockerfile* cloudbuild_*.yaml` 2026-05-27 実行結果に基づく。

| 役割 | image / service or job 名 | Dockerfile | cloudbuild config | 実行種別 |
| --- | --- | --- | --- | --- |
| 記事収集 + 通知 (本体) | `yoshilover-fetcher` | `Dockerfile` (root) | (root tag build、 専用 yaml なし) | Cloud Run **service** |
| 手動 URL 投入 | `manual-intake-service` | `Dockerfile.manual_intake_service` | `cloudbuild_manual_intake_service.yaml` | Cloud Run **service** |
| publish 判定 + flip | `guarded-publish` | `Dockerfile.guarded_publish` | `cloudbuild_guarded_publish.yaml` | Cloud Run job |
| 通知メール (まとめ送信) | `publish-notice` | `Dockerfile.publish_notice` | `cloudbuild_publish_notice.yaml` | Cloud Run job |
| X 投稿候補メール | `x-post-mail-lane` | `Dockerfile.x_post_mail` | `cloudbuild_x_post_mail.yaml` | Cloud Run job |
| 小林誠司名言メール | `kobayashi-meigen-mail-lane` | `Dockerfile.kobayashi_meigen_mail` | `cloudbuild_kobayashi_meigen_mail.yaml` | Cloud Run job |
| 坂本勇人名言メール | `sakamoto-meigen-mail-lane` | `Dockerfile.sakamoto_meigen_mail` | `cloudbuild_sakamoto_meigen_mail.yaml` | Cloud Run job |
| insight 夜間バッチ | `insight-nightly` | `Dockerfile.insight_nightly` | `cloudbuild_insight_nightly.yaml` | Cloud Run job |
| 本文編集 (draft body editor) | `draft-body-editor` | `Dockerfile.draft_body_editor` | `cloudbuild_draft_body_editor.yaml` | Cloud Run job |
| 外部 ping | `external-ping` | `Dockerfile.external_ping` | `cloudbuild_external_ping.yaml` | Cloud Run job |
| Codex shadow lane | `codex-shadow` | `Dockerfile.codex_shadow` | `cloudbuild_codex_shadow.yaml` | Cloud Run job |

!!! warning "同じコードでも image は別々"

    `publish_notice_email_sender.py` のような共通モジュールは、 fetcher service と publish-notice job の両方の image に焼かれる。
    ==修正したら両方 build + deploy しないと挙動が揃わない==。

## :material-rocket: 標準フロー

=== ":material-clock-outline: Cloud Run **job** の更新"

    ```bash
    # 1. build (短 sha タグつき)
    gcloud builds submit \
      --config cloudbuild_publish_notice.yaml \
      --substitutions=_TAG=draft-label-32ed1a4 \
      --quiet

    # 2. job image 切替
    gcloud run jobs update publish-notice \
      --region=asia-northeast1 --project=baseballsite \
      --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:draft-label-32ed1a4 \
      --quiet

    # 3. 確認
    gcloud run jobs describe publish-notice \
      --region=asia-northeast1 --project=baseballsite \
      --format="value(spec.template.spec.template.spec.containers[0].image)"
    ```

=== ":material-server: Cloud Run **service** の更新"

    ```bash
    # 1. build (root Dockerfile の場合は --tag、 専用 cloudbuild がある場合は --config)
    gcloud builds submit \
      --tag asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:draft-label-dca4db5 \
      --quiet

    # 2. service image 切替 (env は維持)
    gcloud run services update yoshilover-fetcher \
      --region=asia-northeast1 --project=baseballsite \
      --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:draft-label-dca4db5 \
      --quiet

    # 3. 確認
    gcloud run services describe yoshilover-fetcher \
      --region=asia-northeast1 --project=baseballsite \
      --format="value(spec.template.spec.containers[0].image)"
    ```

## :material-check-circle: verify (deploy 直後に確認すること)

1. 新 image digest が job / service に乗っている
2. scheduler が ENABLED
3. 次の自然発火の時刻 (manual execute はしない、 二重送信になるため)
4. log で正常 exit、 期待した変化 (例: 件名 prefix 変化) を観察

!!! danger "manual run は打たない"

    `gcloud run jobs execute` / `gcloud scheduler jobs run` を deploy verify のために打たない。

    - publish-notice / x-post-mail-lane 系は実 mail を送るため、 user に二重通知が届く
    - fetcher service の `/run` は WP 下書きの二重生成になる

## :material-arrow-u-left-top: rollback

問題が出たら、 直前の安全な image tag に戻す。

=== "job rollback"

    ```bash
    gcloud run jobs update <JOB_NAME> \
      --region=asia-northeast1 --project=baseballsite \
      --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/<NAME>:SAFE_TAG
    ```

=== "service rollback"

    ```bash
    gcloud run services update-traffic yoshilover-fetcher \
      --region=asia-northeast1 --project=baseballsite \
      --to-revisions SAFE_REVISION=100
    ```

scheduler はそのまま動いているので、 image 戻し → ==次の自然発火で復旧==。

## :material-cog: env だけ切り替える

image rebuild なしで env だけ変えたい場合は `--update-env-vars` で job / service revision を作る。

```bash
# job の場合
gcloud run jobs update <JOB_NAME> \
  --region=asia-northeast1 --project=baseballsite \
  --update-env-vars=KEY=VALUE \
  --quiet

# service の場合
gcloud run services update <SERVICE_NAME> \
  --region=asia-northeast1 --project=baseballsite \
  --update-env-vars=KEY=VALUE \
  --quiet
```

新 env は ==次回 execution から== 適用される。 既に起動中の execution には影響なし。
