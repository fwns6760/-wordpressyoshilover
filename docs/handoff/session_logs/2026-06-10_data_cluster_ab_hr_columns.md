# 2026-06-10 /data 捕手・野手一覧に打数・本塁打列追加

- 08:25 JST | commit | user 依頼「捕手とバッターに打数と本塁打がないから追加して」 | 1905e250 | build → job update → execute verify
- BattingStatsSeason.hr 新設 (atbats_json の「本」cell count、fetch_team_leaders 本塁打 board と同方式。HR は batting_logs に列が無い)
- 列構成: 試合/打数/安打/打率/本塁打/打点 (捕手・内野手・外野手の 3 表共通 _build_batter_group_table_html)
- 注意: commit 1905e250 には同 file に残っていた deploy 済み未 commit drift (notable page / jersey / rotation / hash ledger) を同梱 (message に明記済)
- tests: test_data_site_template_cluster 28 passed / query+publisher 60 passed
11:41 JST | fire | foreign-players hub | 5b3ddf02+8722d52e | build foreign-players-5b3ddf02 → job update → execute → verify → 063 zip user渡し
11:56 JST | done | foreign-players hub LIVE | data-site-publisher-kb87l success | /data/foreign-players/ 200 verify済、残=063 zip user手動upload
