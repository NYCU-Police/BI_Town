# commit 寫進映像，部署時間在容器建立時注入

## 狀態

接受（2026-09-24）

## 背景

瀏覽器和 `/api/health` 需要看出目前線上的是哪一次 commit、何時部署。程式在主機上用 `docker compose build` 建置，沒有獨立的映像倉庫。

把時間放進映像建置參數時，它記錄的是 build 的時刻。部署若重用舊層，或只是建立容器，這個值就不再是這次部署的時間。

## 決定

- `GIT_COMMIT` 是映像建置參數，在 Dockerfile 裡放在 `pip install` 與 `COPY app` 之後。commit 變了只重跑最後的 `ENV`，不讓依賴層失效。
- `DEPLOYED_AT` 是容器環境變數。Deploy staging 在 `docker compose up` 當下用 UTC 時間寫入，容器建立時才進到行程。API 每次請求讀環境變數，所以這是這次容器被拉起來的時間。
- 未設定或空白時，API 回 `unknown`。兩者都不是密鑰，不寫進 GitHub secrets，也不提交到 `deploy/.env`。

## 後果

- 健康檢查要比對主機上的 `HEAD` 與回應裡的 `git_commit`。對不上，或 `deployed_at` 仍是 `unknown`，workflow 失敗。
- 只重啟、不重新 build，commit 不會變。只重建容器、不改 `GIT_COMMIT`，部署時間會更新、commit 仍是映像裡的那個。
- 回滾若要換上另一個 commit，必須 `--build`。
- 本機 `uvicorn` 沒帶這兩個變數時會顯示 `unknown`。
