# 2026-06-28 YT Shorts: ranking + standings フォーマット追加

YouTube Shorts を当初計画3テーマ体制へ。data + legend に加え、残りの
「巨人目線のプロ野球ネタ」を自社データ決定論生成(number guard、外部ニュース
転載なし)で2フォーマット化して deploy + 既存 daily scheduler に載せた。

- 14:2x JST | impl+commit | yt-shorts ranking/standings | 7fd4c8a7 | 全63テスト緑・ローカルでフルMP4生成&目視OK
- 14:3x JST | build | yt-shorts-gen:yt-shorts-ranking-7fd4c8a7 | Cloud Build SUCCESS(4M17S) | -
- 14:3x JST | deploy | job yt-shorts-gen | image=ranking-7fd4c8a7 / args=`--live,--youtube-private-upload,--format,all` | scheduler 既存(0 10 * * * JST, ENABLED)が4フォーマット生成
- next | 明日10:00 が ranking/standings の初回ライブ実行。失敗時は main() の per-format try/except で失敗メールが飛び、他フォーマットは継続。live smoke は user が過去に止めた経緯から自動実行せず。

## フォーマット内容
- ranking(巨人データ・ランキング): `_serialize_notable_leaders(top_n=3)` の leaders を stat 別 TOP3。日替わり stat rotate(toordinal % N)。light テーマ。
- standings(巨人目線のセ・リーグ): `fetch_npb_cl_standings()` の巨人行から順位/勝敗/ゲーム差。他球団を煽らない巨人目線コピー。navy テーマ。
- 両方とも data/legend と同じ render→VOICEVOX→private upload→承認mail を流用。公開は手動承認ゲート維持。

## --format
data / legend / ranking / standings / both(=data+legend) / all(=data+legend+ranking+standings)。job は all。
