# 2026-06-10 /data 捕手・野手一覧に打数・本塁打列追加

- 08:25 JST | commit | user 依頼「捕手とバッターに打数と本塁打がないから追加して」 | 1905e250 | build → job update → execute verify
- BattingStatsSeason.hr 新設 (atbats_json の「本」cell count、fetch_team_leaders 本塁打 board と同方式。HR は batting_logs に列が無い)
- 列構成: 試合/打数/安打/打率/本塁打/打点 (捕手・内野手・外野手の 3 表共通 _build_batter_group_table_html)
- 注意: commit 1905e250 には同 file に残っていた deploy 済み未 commit drift (notable page / jersey / rotation / hash ledger) を同梱 (message に明記済)
- tests: test_data_site_template_cluster 28 passed / query+publisher 60 passed
11:41 JST | fire | foreign-players hub | 5b3ddf02+8722d52e | build foreign-players-5b3ddf02 → job update → execute → verify → 063 zip user渡し
11:56 JST | done | foreign-players hub LIVE | data-site-publisher-kb87l success | /data/foreign-players/ 200 verify済、残=063 zip user手動upload
12:55 JST | done | prosports相互リンク両方向LIVE | 1ad75f49+41dca070+script | 本体93→80page読み物box (OB含む) + prosports 93記事→本体逆リンク done=90 skip=3(canary) fail=0
12:55 JST | note | 岡本和真 /data page は更新経路外 (giants_roster stale在籍×NPB公式名簿外でtarget/OB両方から漏れ) — 読み物box未反映、MLB移籍選手の更新経路は別ticket候補
12:55 JST | note | prosports app password は ~/.prosports_wp_cred (600)。鍵がchatに貼られたため用済み後の破棄→再発行をuserに推奨済み
13:45 JST | done | 301一掃 (noslash links) 全ページ反映 | c845f3a4 / data-site-publisher-jsbnl | sakamoto/foreign/legends で slash link 0 件 verify
13:45 JST | done | 063 v0.21.18 user upload 済 | - | トップに歴代外国人カード + noslash 反映 verify 済
13:45 JST | fire | sitemap 整理 | - | user=投稿チェック外し待ち、Claude=301元抽出 scan 実行中 (b3ih11wuc) → 専用 sitemap 作成予定
