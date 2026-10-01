# 救援進度

## 任務 A：依賴可重現

分支 `chore/reproducible-backend-deps`。

### 做了什麼

- 選 uv 0.12.21，不用 pip-tools。一份 `backend/uv.lock` 同時鎖執行期與 dev group，並用 `required-version = "==0.12.21"` 拒絕其他 uv。
- 直接依賴釘在已測過的版本：`fastapi==0.141.1`、`uvicorn[standard]==0.53.0`、`pydantic==2.13.5`、`httpx==0.28.1`、`jsonschema==4.26.0`、`opencc-python-reimplemented==0.1.7`。dev group：`pytest==9.1.1`、`ruff==0.16.8`、`httpx2==2.13.1`。Starlette 明確釘 `1.7.0`。
- 刪除 `backend/requirements.txt`。CI 與 Dockerfile 都改走 `uv sync --frozen`，`UV_PYTHON_DOWNLOADS=never`。正式映像用 `--no-dev`，CMD 是 `/app/.venv/bin/uvicorn`。CI 不使用 `astral-sh/setup-uv`，見下方 startup_failure。
- Dockerfile 設 `UV_PYTHON_DOWNLOADS=never`，依賴層只複製 `pyproject.toml` 與 `uv.lock`，安裝完才複製 `app/`。`GIT_COMMIT` 仍在依賴層之後。
- `httpx` 留在執行期。`httpx2` 只在 dev group。正式映像沒有 pytest、ruff、httpx2。
- 沒有改 `docker-compose.yml`、`deploy-staging.yml`、`llm_session.py`、Godot。

刪除 `requirements.txt` 之前，全庫引用如下。腳本與 `deploy/` 沒有引用。

| 位置 | 處理 |
| --- | --- |
| `backend/Dockerfile` | 改為 uv sync |
| `.github/workflows/ci.yml` | 改為 uv sync |
| `README.md` | 安裝說明改為 `uv sync --frozen` |
| `PROJECT_STATUS.md` | 檔案表與本機開發段落改為 lockfile |
| `docs/ADR/0002-deploy-identity-build-args.md` | 「pip install」改成「依賴安裝」，層次順序不變 |
| `docs/rescue/01-archaeology.md` | 保留。那是改動前的診斷，不是操作說明 |

### 怎麼驗證

- `uv lock` 用 uv 0.12.21、CPython 3.12.14 成功。lock 內是 `httpx2 2.13.1`、`starlette 1.7.0`、`httpx 0.28.1`。沒有改選其他版本。
- 本機 `uv sync --frozen` 後 `python` 為 3.12.14，`httpx` 為 0.28.1，`httpx2` 為 2.13.1。
- `uv run pytest -v`：135 passed，沒有 Starlette / anyio 棄用警告。`pytest.ini` 把這兩則設成 error。
- `uv run ruff check .`：All checks passed。
- `docker build` 成功。映像內 uv 0.12.21，Python 3.12.14，沒有 pytest / ruff / httpx2。
- `docker run -e BRAIN_MODE=rules` 後 `GET /api/health` 回 `{"status":"ok",...,"brain_mode":"rules"}`。日誌沒有 ERROR 或 Traceback。有一則既有 WARNING：`STATIC_WEB_DIR unset; Godot web client will not be served`。這次沒掛網頁目錄，所以會出現。CI 的 `docker-validate` 仍然只 build。

### 回滾

合併後若 staging 起不來，revert **PR #45**（https://github.com/NYCU-Police/BI_Town/pull/45）的 merge commit。在 GitHub 對該 PR 按 Revert，再開一個 revert PR。不要在 `main` 上直接改，也不要 SSH 進主機改映像或 `deploy/.env`。

revert PR 的 CI 全綠後，現有的 deploy workflow 會用舊的 `requirements.txt` 與 `pip install` 重建映像。後端測試與 Docker build 大約數分鐘，Godot web export 是這條 CI 裡較慢的一段；部署健康檢查三段各最多 60 秒。從 revert PR 合併算起，大約 15 分鐘可以回到舊安裝方式。runner 排隊會更久。

每次部署都會把世界重置到 Day 1 08:00。回滾恢復的是安裝方式，不會把世界狀態救回來。這次沒有改 compose 或 deploy workflow。

### CI startup_failure

PR #45 前兩次 workflow（run 36856940754、36856959792）結論都是 `startup_failure`，0 秒，`jobs` 為空，所以三個必要檢查停在 Expected。actionlint 沒有語法錯誤，job 名稱也沒改。

原因：repo 的 Actions 是 `allowed_actions: selected`，名單沒有 `astral-sh/setup-uv`。`uses:` 不在名單內時，整個 workflow 在啟動前被拒，連沒有用到該 Action 的 `docker-validate` 與 `godot-export-check` 也不會跑。

處理：移除 `astral-sh/setup-uv`。在已允許的 `actions/setup-python@v5` 之後執行 `pip install uv==0.12.21`，保留 `UV_PYTHON_DOWNLOADS=never`。uv 套件快取改用白名單內的 `actions/cache@v4`，目錄是 `UV_CACHE_DIR`，key 為 `uv-${{ runner.os }}-${{ hashFiles('backend/uv.lock') }}`。Dockerfile 仍從 `ghcr.io/astral-sh/uv:0.12.21` 複製 uv，那不是 `uses:`，不受這份白名單限制。

### 遺留與新風險

- 傳遞依賴相對舊的 Python 3.14 venv 有兩個小差異：`uvloop` 0.22.1 → 0.23.0，`python-dotenv` 1.2.3 → 1.2.4。直接依賴沒有升。135 個測試在 3.12 上通過。正式站舊映像的實際解析版本無法從 repo 還原，所以線上與這份 lock 是否逐套件相同仍【待確認】，要等這次部署的 `/api/health` 與容器啟動日誌。
- 本機若還留著 uv 0.12.9，`uv sync` 會被 `required-version` 拒絕。要用 0.12.21。舊的 3.14 `.venv` 已在這台機器刪掉並用 3.12 重建。
- `docs/rescue/01-archaeology.md` 仍描述舊的 `requirements.txt`。那是診斷當時的事實。
