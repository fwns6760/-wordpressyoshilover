- pause 実行者: `fwns6760@gmail.com`
- pause 時刻: `2026-04-20T16:46:17.610593854+09:00`
- 呼び出し API: `google.cloud.scheduler.v1.CloudScheduler.PauseJob`
- 呼び出し元 IP: `153.242.185.12`
- 直前 14d の同 job 操作履歴:
  - `2026-04-19T03:16:03.783235275+09:00` `google.cloud.scheduler.v1.CloudScheduler.CreateJob` principal=`fwns6760@gmail.com` callerIp=`private`
  - `2026-04-19T09:09:14.192800595+09:00` `google.cloud.scheduler.v1.CloudScheduler.UpdateJob` principal=`fwns6760@gmail.com` callerIp=`153.242.185.12`
  - `2026-04-19T09:09:17.551997380+09:00` `google.cloud.scheduler.v1.CloudScheduler.UpdateJob` principal=`fwns6760@gmail.com` callerIp=`private`
  - `2026-04-19T13:38:18.481228648+09:00` `google.cloud.scheduler.v1.CloudScheduler.UpdateJob` principal=`fwns6760@gmail.com` callerIp=`153.242.185.12`
  - `2026-04-19T13:38:22.238364150+09:00` `google.cloud.scheduler.v1.CloudScheduler.UpdateJob` principal=`fwns6760@gmail.com` callerIp=`private`
  - `2026-04-20T16:40:44.942016962+09:00` `google.cloud.scheduler.v1.CloudScheduler.UpdateJob` principal=`fwns6760@gmail.com` callerIp=`153.242.185.12`
  - `2026-04-20T16:40:48.695699278+09:00` `google.cloud.scheduler.v1.CloudScheduler.UpdateJob` principal=`fwns6760@gmail.com` callerIp=`private`
  - `2026-04-20T16:46:17.610593854+09:00` `google.cloud.scheduler.v1.CloudScheduler.PauseJob` principal=`fwns6760@gmail.com` callerIp=`153.242.185.12`
  - `2026-04-20T16:46:18.151739839+09:00` `google.cloud.scheduler.v1.CloudScheduler.PauseJob` principal=`fwns6760@gmail.com` callerIp=`private`
- 判定: `意図的`。`PauseJob` は human principal `fwns6760@gmail.com` が `google-cloud-sdk gcloud/559.0.0 command/gcloud.scheduler.jobs.pause ... from-script/True` で直接発火しており、service account や自動 deploy 起因の痕跡は 14 日窓では検出されない。
- 次に Claude が判断すべきこと: `2026-04-20 16:46 JST の明示 pause を解除して再開するか、それとも停止維持を user 判断に上げるかを切り分ける。`

補足:
- 直近 14 日では `ResumeJob` は検出されなかった。監査ログ上は `CreateJob` 後に user principal の `UpdateJob` が数回あり、その後 `PauseJob` で停止している。
