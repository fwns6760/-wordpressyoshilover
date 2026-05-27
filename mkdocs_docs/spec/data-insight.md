# :material-chart-bar: データ記事 (data-insight)

!!! info "これは何"

    巨人の選手 / チームの「数字が際立った瞬間」 を自動で記事化する系統。
    報知 / サンスポなどが書かない ==独自データ視点== でサイトの差別化を担う。

!!! quote "user 方向性"

    ヨシラバーは「データサイト」 方向に振る。 量と多様性が KPI。 守備も含めて metric を幅広く扱う。

## :material-format-list-checks: 出す対象 (allow list)

出典: `config/insight_whitelist.json` (2026-05-15 lock)

=== ":material-baseball-bat: 打撃"

    - 標準率: AVG / OBP / SLG / OPS
    - split: RISP (得点圏打率)

=== ":material-baseball: 投手"

    - 標準率: ERA / WIN_PCT
    - /9 系率: K_per_9 (奪三振率) / BB_per_9 (与四球率) / HR_per_9 (被本塁打率)

=== ":material-shield-account: 守備"

    - FIELDING_PCT (守備率)
    - UZR_proxy (簡易 UZR)

=== ":material-trophy: 総合"

    - WAR (総合貢献度)

## :material-cancel: 出さない指標 (disallow list)

??? abstract "クリックで展開"

    出典: `config/insight_whitelist.json` `metrics_disallowed`

    - ISO
    - wOBA
    - BABIP
    - K_pct
    - BB_pct
    - WHIP
    - K_BB
    - FIP
    - xFIP
    - RF_proxy

    !!! note "理由"

        サバメトリクス指数系はファン読者層に直感的でない。 ヨシラバーは「ファンが知ると楽しい切り分け」 を優先する。

## :material-chart-bell-curve: 閾値とランキング

| 軸 | 値 | 説明 |
| --- | --- | --- |
| z-score 閾値 | ==1.5 σ== | 標準偏差 1.5 を超えた値を「異常値」 として記事化候補 |
| Counting TOP N | ==10== | TOP10 にランクインしている巨人選手は記事化候補 |
| 最小サンプル (打者) | 打席 20 以上 | これを下回ると統計信頼度不足で skip |
| 最小サンプル (投手) | 投球回 10 以上 | 同上 |

出典: `config/insight_whitelist.json` `thresholds`

## :material-calendar-clock: 期間軸

==試合数 / 打席数 / 投球回 / 登板数ベース== に統一されている。

=== ":material-baseball-bat: 打者"

    - 直近 3 試合 (`last_3_games`)
    - 直近 5 試合 (`last_5_games`)
    - 直近 10 試合 (`last_10_games`)
    - 直近 30 打席 (`last_30_pa`)
    - 直近 50 打席 (`last_50_pa`)
    - 直近 100 打席 (`last_100_pa`)

=== ":material-baseball: 投手"

    - 直近 3 登板 (`last_3_appearances`)
    - 直近 5 登板 (`last_5_appearances`)
    - 直近 10 登板 (`last_10_appearances`)
    - 直近 5 投球回 (`last_5_ip`)
    - 直近 10 投球回 (`last_10_ip`)

=== ":material-calendar: 季節"

    - 今シーズン (`season`)
    - 月別 (`monthly`)
    - 週別 (`weekly`)

## :material-format-title: タイトルの組み立て

タイトルは **4 つの case** から該当形を選ぶ。

| case | format | 例 |
| --- | --- | --- |
| A 選手 stat | `【巨人データ】{player} {metric} {value}、 リーグ {rank} 位 ({scope})` | 【巨人データ】大城卓三 OPS .912、リーグ4位（直近5試合） |
| B 試合 event | `【巨人データ】{player} {event} ({date} vs {opponent})` | 【巨人データ】岡本和真 本塁打3本、チーム最多（直近10試合） |
| C 記録 / マイルストーン | `【巨人データ】{player} {achievement} ({date})` | 【巨人データ】山崎伊織 防御率1.80、リーグ3位（今シーズン） |
| D チーム ranking | `【巨人データ】チーム{metric} {value} ({scope})` | 【巨人データ】巨人 チーム打率.286（阪神3連戦） |

制約:

- 最大 60 字
- 最小 12 字
- 末尾 `…` 禁止 (trim 表示禁止)
- 同 event 重複禁止

## :material-content-duplicate: 重複抑制 (dedup)

| ルール | 値 |
| --- | --- |
| cooldown | 同 subject + metric は ==7 日== 空ける |
| 再掲条件 | 値が 5% 以上変化、 または順位 band ([1,5,10,30]) を超える変化 |
| 順位 band | TOP1 / TOP5 / TOP10 / TOP30 |

出典: `config/insight_whitelist.json` `dedup`

## :material-image: 記事のアイキャッチ

3 段 fallback (詳細は [アイキャッチ](eyecatch.md) を参照):

1. 元記事のアイキャッチ
2. 保存済みの選手写真 (`config/player_eyecatch_map.json`、 ==67 名分==)
3. 巨人チームマーク (固定 media_id `63578`)

## :material-target: 範囲

- title 主語: ==巨人選手のみ==
- baseline 計算: ==12 球団全選手==

出典: `config/insight_whitelist.json` `team_filter`

## :material-folder-file: 関連 file

- 異常値検出 + 記事化: `src/analysis/anomaly_article_publisher.py`
- 球団ランキング: `src/analysis/team_ranking_publisher.py`
- whitelist 設定: `config/insight_whitelist.json`
- 選手写真 map: `config/player_eyecatch_map.json`
- X 投稿 format: `src/format_as_x_post.py`
