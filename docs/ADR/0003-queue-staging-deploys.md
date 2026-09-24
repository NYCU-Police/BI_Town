# Staging 部署排隊，不取消進行中的那次

## 狀態

接受（2026-09-24）

## 背景

Deploy staging 經 SSH 改同一台主機的 `/srv/bi_town`：rsync、`git reset`、`docker compose up --build`。workflow 已經有 concurrency group `bi-town-staging`，而且 `cancel-in-progress: true`。

取消 GitHub Actions job 不會關掉已經在主機上跑的 shell。後到的部署會和前一次的 rsync 或 compose 疊在一起。

## 決定

同一個 group 維持 `bi-town-staging`，改成 `cancel-in-progress: false`。新的部署排隊，等正在跑的那次結束。

## 後果

- 連續合併時，線上會依序變成每一次 CI 的 commit，不會兩邊同時寫目錄。
- 一次部署要等前一次做完，尖峰時公開站更新會比較慢。
- 最後排隊到的那次仍部署它自己的 CI commit，不會改去部署主機當時的 `HEAD`。
