# phase5_coverage_matrix

preview v0 phase 5 の目的は、BUG-004+291 subtask-9 の subtype-aware narrow unlock が返す 8 category を、live WP なしで本文修正 preview 側に受け渡せることを確認すること。

count basis:

- `preview v0 sample count` は phase 4 baseline brief の validated corpus を基準にし、phase 5 で追加した sample を加えた運用 count を使う。
- `lineup` 2 sample は preview corpus に残すが、この matrix の 8 category unlock scope には含めない。
- `若手選手 / player_notice` は current narrow unlock では `farm_player_result` へ寄せて扱う。

| category | subtask-9 unlock target | preview v0 sample count | auto-eval status | gap |
|---|---|---:|---|---|
| postgame | YES | 5 | PASS | - |
| manager-coach | YES | 1 | PASS | - |
| player_comment | YES | 1 (`sample_player_comment_63109.md`) | PASS | - |
| farm_result | YES | 2 | PASS | - |
| farm_lineup | YES | 1 (`sample_farm_lineup_63429.md`) | PASS | - |
| pregame / probable_starter | YES | 2 (`sample_pregame_63331.md`, `sample_pregame_63107.md`) | PASS | - |
| roster_notice | YES | 1 (`sample_roster_notice_63232.md`) | PASS | - |
| 若手選手 / player_notice | YES (`farm_player_result` unlock lane) | 1 (`sample_farm_player_result_63133.md`) | PASS | - |

phase 5 additions:

- `player_comment`: `63109`
- `farm_lineup`: `63429`
- `pregame`: `63331`, `63107`
- `roster_notice`: `63232`
- `若手選手 / player_notice -> farm_player_result`: `63133`

phase 5 auto-eval result:

- added samples: `6`
- pass: `6`
- fail: `0`
- excluded candidate: `63263`
- exclusion reason: `farm_player_result` の optional second sample は `interface_match=no` / `phase5=4/5` だったため validated corpus へは採用しない

## subtask-9 interface validation

preview v0 が受ける interface は以下で固定する:

- `unlock_title`
- `unlock_subtype`
- `source_url`
- `required_fact_axes`
- `present_fact_axes`

validation result:

- `player_comment` / `farm_lineup` / `pregame` / `roster_notice` / `farm_player_result` の phase 5 sample はすべて `interface_match=yes`
- preview v0 は `unlock_title` と `unlock_subtype` を正文として body template を選び、legacy backup の `article_subtype` は参考情報として扱う
- `pregame` sample `63107`, `63331` は backup 上の `article_subtype` が `postgame` でも、subtask-9 rescue の `unlock_subtype=pregame` を受けて body_contract / title-body integrity が通る
- `若手選手` 系は `player_notice` 抽象名のままではなく、current implementation の unlock lane `farm_player_result` に具体化されている

## completion check

- 8 category unlock scope coverage: `done`
- preview-only validation: `done`
- live WP write: `0`
- Gemini call: `0`
- deploy / env / scheduler change: `0`
