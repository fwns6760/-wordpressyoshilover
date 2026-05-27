# :material-clock-time-eight: Cloud Scheduler 一覧

!!! info "出典"

    `gcloud scheduler jobs list --location=asia-northeast1 --project=baseballsite` の 2026-05-27 実行結果。
    state はすべて ==ENABLED== (時間順)。

## :material-table-of-contents: lane 別グループ

=== ":material-email-newsletter: publish-notice"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `publish-notice-trigger` | `5 6-15 * * *` | 朝〜午後の per_post 通知 |
    | `publish-notice-trigger-evening` | `5,35 16-22 * * *` | 夕方〜夜の per_post 通知 |
    | `publish-notice-trigger-burst-tail` | `10 7,10,12,15,17,20,21 * * *` | 多発時間帯の burst tail |

=== ":material-twitter: x-post-mail"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `x-post-mail-flush` | `0 6-22 * * *` | 朝 6 時〜夜 22 時の毎時 0 分 |
    | `x-post-mail-flush-game-1` | `15,30,45 19-20 * * *` | 試合中 (19,20 時) |
    | `x-post-mail-flush-game-2` | `15,30,45 21 * * *` | 試合終盤〜直後 (21 時) |

=== ":material-chart-bar: data-insight (1 日 7 回)"

    | スケジューラ | cron | 時刻 (JST) |
    | --- | --- | --- |
    | `data-insight-morning-trigger` | `0 7 * * *` | 07:00 |
    | `data-insight-1000-trigger` | `0 10 * * *` | 10:00 |
    | `data-insight-noon-trigger` | `0 12 * * *` | 12:00 |
    | `data-insight-1500-trigger` | `0 15 * * *` | 15:00 |
    | `data-insight-pregame-trigger` | `0 17 * * *` | 17:00 |
    | `data-insight-2000-trigger` | `0 20 * * *` | 20:00 |
    | `data-insight-during-game-trigger` | `0 21 * * *` | 21:00 |

=== ":material-shield-check: guarded-publish"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `guarded-publish-trigger` | `*/30 * * * *` | 30 分毎に draft→publish 判定 |

=== ":material-baseball: giants realtime / catchup"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `giants-realtime-trigger` | `0,30 17-21 * * *` | 試合時間帯 (17〜21 時の 0,30 分) |
    | `giants-realtime-peak-15min` | `15,45 18-21 * * *` | ピーク時間の 15,45 分 |
    | `giants-realtime-2230` | `30 22 * * *` | 22:30 試合直後 |
    | `giants-realtime-2300` | `0 23 * * *` | 23:00 試合直後 |
    | `giants-morning-catchup` | `30 4 * * *` | 早朝 catchup |
    | `giants-postgame-catchup-am` | `0 22 * * *` | 試合後 catchup |
    | `giants-weekday-daytime` | `0 6-16 * * *` | 平日昼間 |

=== ":material-baseball-bat: 試合連動 (lineup / pregame / postgame / broadcast)"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `lineup-auto-pregame` | `0,15,30,45 17-18 * * *` | 試合前スタメン (17,18 時の 15 分毎) |
    | `broadcast-auto-daily` | `30 11 * * *` | 11:30 放送情報 |
    | `postgame-auto-daily` | `30 22 * * *` | 22:30 試合後自動 |

=== ":material-format-quote-close: 名言 mail"

    | スケジューラ | cron | 時刻 (JST) |
    | --- | --- | --- |
    | `kobayashi-meigen-mail-trigger-noon` | `0 12 * * *` | 12:00 小林誠司 |
    | `kobayashi-meigen-mail-trigger-evening` | `0 17 * * *` | 17:00 小林誠司 |
    | `kobayashi-meigen-mail-trigger-night` | `0 20 * * *` | 20:00 小林誠司 |
    | `sakamoto-meigen-mail-trigger` | `0 18 * * *` | 18:00 坂本勇人 |

=== ":material-newspaper: 朝のレポート"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `digest-daily-morning` | `0 6 * * *` | 06:00 朝 digest |
    | `fact-check-morning-report` | `5 * * * *` | 毎時 5 分の fact-check report |

=== ":material-magnify: SEO / 解析"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `seo-fetch-daily` | `15 5 * * *` | 05:15 SEO 取得 |
    | `fetch-gsc-daily` | `0 6 * * *` | 06:00 GSC 取得 |
    | `prosports-fetch-gsc-daily` | `0 6 * * *` | 06:00 ProSports GSC |
    | `prosports-crawl-internal-links-daily` | `30 6 * * *` | 06:30 内部リンク crawl |
    | `ga4-traffic-analyzer-daily` | `0 6 * * *` | 06:00 GA4 解析 |

=== ":material-pen: その他"

    | スケジューラ | cron | 用途 |
    | --- | --- | --- |
    | `draft-body-editor-trigger` | `0 */3 * * *` | 3 時間毎の本文編集 |
    | `external-ping-trigger` | `0 6 * * *` | 06:00 外部 ping |

## :material-console: 操作コマンド

### 一覧

```bash
gcloud scheduler jobs list \
  --location=asia-northeast1 --project=baseballsite \
  --format="table(name.basename(),schedule,state)"
```

### 詳細

```bash
gcloud scheduler jobs describe <JOB_NAME> \
  --location=asia-northeast1 --project=baseballsite
```

### 一時停止 / 再開

```bash
gcloud scheduler jobs pause  <JOB_NAME> --location=asia-northeast1 --project=baseballsite
gcloud scheduler jobs resume <JOB_NAME> --location=asia-northeast1 --project=baseballsite
```

### 即時実行 (自然発火を待たずに今すぐ動かす)

```bash
gcloud scheduler jobs run <JOB_NAME> --location=asia-northeast1 --project=baseballsite
```

!!! warning "mail / draft 系の手動 run は二重発火に注意"

    publish-notice / x-post-mail-lane の手動 run は実 mail を二重送信、 fetcher 系の手動 run は WP 下書きの二重生成になる。
    通常は scheduler の自然発火を待つ。

## :material-state-machine: state

| state | 意味 |
| --- | --- |
| ENABLED | 通常運転 |
| PAUSED | 一時停止 (deploy 中 / debug 中) |
| DISABLED | 完全無効化 |

!!! danger "PAUSED を放置しない"

    新 image を入れたら自動的に resume が default。 STOP のまま放置するかは 1 度確認すること。

## :material-trash-can: 削除済の旧 scheduler

`backup/scheduler-deleted-2026-05-25/` 以下に保存されている YAML が「過去にあって、 もう存在しない」 scheduler。
中身は giants-weekday/weekend-pre/post/lineup 系。 必要なら復元可能だが、 現運用では使っていない。
