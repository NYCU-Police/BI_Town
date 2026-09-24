# 用映像建置參數記錄部署身分

## 狀態

接受（2026-09-24）

## 背景

瀏覽器和 `/api/health` 需要看出目前線上的是哪一次 commit、何時部署。程式在主機上用 `docker compose build` 建置，沒有獨立的映像倉庫。

## 決定

`GIT_COMMIT` 與 `DEPLOYED_AT` 只在建置映像時寫入。Deploy staging 在 `git reset --hard origin/main` 之後設定這兩個值，再 `docker compose up -d --build`。未設定或空白時，API 回 `unknown`。

它們不是密鑰，不寫進 GitHub secrets，也不提交到 `deploy/.env`。

## 後果

- 健康檢查要比對主機上的 `HEAD` 與回應裡的 `git_commit`。對不上，或 `deployed_at` 仍是 `unknown`，workflow 失敗。
- 只重啟容器、不重新 build，畫面上的 commit 不會更新。回滾也必須 `--build`。
- 本機 `uvicorn` 或沒帶這兩個變數的 build 會顯示 `unknown`。
