# 2026-07-16 常連ページ /friends + manual-intake 認証有効化

- 09:05 JST | 調査 | ポストmail朝帯空白の報告 → 事故なし。昨日の便再編(朝=MLB専用化)× MLBオールスター休みで候補ゼロのsilent skip。金曜朝のMLB再開で自動復活
- 09:20 JST | impl | 常連専用ページ `/friends` 追加 (一覧200件/手動追加/✕削除/🚫ヤジ、/liveの👥はページ遷移化) | 3bef2df2
- 09:21 JST | deploy | manual-intake-service build 11d22034 → rev 00134-j2k
- 09:25 JST | security | MANUAL_INTAKE_TOKEN が prod 未設定で全endpoint認証素通し(/x-post-direct 含む)を発見 → Secret Manager `manual-intake-token` 新設、seo-web-runtime に secretAccessor 付与、rev 00136-hs4 で有効化。verify: no-token=403 / with-token=200
- 09:27 JST | handoff | ログインURL(token付き)は chat に出さず SMTP で fwns6760@gmail.com へ送付。各端末で一度タップ→90日cookie
- 常連の登録経路(仕様): ①アプリからリプ返し投稿成功で自動+1 ②手動追加のみ。受信リプでは入らない
- 09:38 JST | impl+deploy | トップnavに👥常連リンク+タブ折返し(スマホ) | build ca3c560b → rev 00137-b7n
- 09:50 JST | impl+deploy | 自分宛リプ→常連候補 自動取り込み (Yahooリアルタイム@メンション検索¥0、/live-friend-candidates、✔keep/✕dismiss/🚫yaji、bump時自動昇格) | build 25386e9a → rev 00138-9tv | prod smoke: 候補6人取り込み確認
- 10:00 JST | impl+deploy | 観戦モード: live-fuga(短文/長文)に一球速報の直近2プレー自動注入、recap force_long解除で短文長へ | rev 00139-tcw
- 10:25 JST | impl+deploy | 🔥トレンド反応 即応アプリ /trend (急上昇chips→trend_react共用生成→X直接投稿、トップnavに追加) | build 5c8ce416 → rev 00141-pcw | prod smoke: words 4語取得OK (1回目buildはGCP INTERNAL_ERROR、再buildで解消)
