# BI_Town 專案狀態

給新的 AI 助手對話或新加入的隊友接手。描述的是 repo 現況（v0.1.0），不是目標產品。

## 1. 專案是什麼

- 名稱：BI_Town（Behavioral Intelligence Town）。版本常數在 `backend/app/config.py` 的 `VERSION = "0.1.0"`。
- 類型：AI-native social simulation。目前沒有 LLM，也沒有真正的 AI agent。
- 架構：server-authoritative。World state 的唯一來源是 FastAPI backend。Godot client 只渲染 server 送來的狀態，不自行推進時鐘、不決定 NPC 去向。
- World 存在 process 記憶體（`backend/app/state.py` 的 `World` singleton）。重啟即重置。Postgres 與 Redis 只在 Docker Compose 裡待命，backend 程式尚未連線。
- 開局：Day 1、08:00。兩個 rule-based agent：Mina、Alex。地點：home、cafe、office、park。
- 正式站：https://bitown.aicanhelp.app （Cloudflare Tunnel）。健康檢查：`/api/health`（含 `version`、`git_commit`、`deployed_at`）。部署步驟與回滾見 `docs/DEPLOY.md`。

## 2. 目前架構

```
Godot 4.7 web client (renderer)
        |  WebSocket /ws
        v
FastAPI backend
  world clock + rule-based fake agents + events + WebSocket broadcast
        |
Docker Compose: backend + postgres + redis + cloudflared
        |
Cloudflare Tunnel → https://bitown.aicanhelp.app
```

- 模擬迴圈：`simulation_loop` 每 `SIMULATION_TICK_SECONDS`（1 秒）呼叫一次 `World.tick()`。每個 tick 推進 `GAME_MINUTES_PER_TICK`（1 遊戲分鐘）。
- `World.tick()` 順序：依當下遊戲時間套用行程 → 移動 walking agent → 推進時鐘。
- Agent 狀態只有 `idle` 與 `walking`。行程命中時從 idle 改為 walking，並記一筆 `left`。抵達 POI（距離 ≤ `ARRIVAL_DISTANCE_THRESHOLD` 或 ≤ 本 tick 步長）後改回 idle，記一筆 `entered`。
- WebSocket 訊息（`backend/app/models/schemas.py`）：
  - `world_snapshot`：連線當下整包狀態（day、time、agents、events）。
  - `agent_update`：本 tick 有變動的 agents，附上 day 與 time。
  - `world_event`：本 tick 新增的 `left` / `entered`。
- HTTP API（prefix `/api`）：`GET /health`、`GET /world`、`GET /agents`、`GET /events`。`/health` 帶 `Cache-Control: no-store`。`git_commit` 來自映像建置參數，`deployed_at` 來自容器建立時的環境變數；沒設定時是 `unknown`。Web export 的 HUD 用相對路徑 `/api/health` 取名稱、版本、commit、部署時間；請求失敗只顯示 `unknown`，遊戲繼續跑。
- Godot web export 由 backend 以靜態檔提供。`STATIC_WEB_DIR` 有值且目錄內有 `index.html` 才 mount 在 `/`。本機只跑 uvicorn、沒設這個變數時，只提供 API 與 WebSocket。
- HTTP 回應帶 `Cross-Origin-Opener-Policy: same-origin` 與 `Cross-Origin-Embedder-Policy: require-corp`（Godot 4 WASM）。
- Docker Compose 一份檔同時給本機與 staging。backend 把 host 的 `game/build/web` 唯讀掛進容器 `/app/web`。對外 port 綁 `127.0.0.1:${BI_TOWN_PORT:-8100}` → 容器 8000。
- `cloudflared` 在 profile `tunnel`。本機 `docker compose up` 不會啟動它。Staging 用 `--profile tunnel`，token 來自 `deploy/.env` 的 `TUNNEL_TOKEN`。

Mina 行程：08:00 cafe、09:00 office、12:00 cafe、13:00 office、18:00 park、20:00 home。
Alex 行程：約晚 30 分鐘；12:00 去 park（Mina 是 cafe）。定義在 `backend/app/simulation/fake_agent.py`。

POI 座標（backend 與 Godot 必須一致）：

| id | 座標 |
| --- | --- |
| home | (100, 100) |
| cafe | (400, 250) |
| office | (700, 150) |
| park | (500, 500) |

## 3. 目錄結構

### `backend/app/`

| 路徑 | 職責 |
| --- | --- |
| `main.py` | FastAPI app。lifespan 啟動／取消模擬迴圈。COOP/COEP middleware。依 `STATIC_WEB_DIR` 掛 Godot 靜態檔。 |
| `config.py` | 全部設定與數字。route 與 simulation 不放 magic number。 |
| `state.py` | process 級 `world` singleton。`reset_world()` 給測試用。 |
| `api/routes.py` | `/api/health`、`/world`、`/agents`、`/events`。 |
| `models/schemas.py` | Pydantic models 與三種 WebSocket message。 |
| `simulation/clock.py` | 遊戲時鐘。`24:00` 進下一天 `00:00`。純函式。 |
| `simulation/world.py` | `World` 與 `tick()`。同步、可單測。回傳 `TickResult`（新事件、有變動的 agents）。 |
| `simulation/fake_agent.py` | 行程表、朝目標移動、`left` / `entered`。無 LLM。 |
| `simulation/poi.py` | POI id、名稱、座標。 |
| `simulation/loop.py` | async 迴圈。tick 後廣播。只在 `changed_agents` 非空時送 `agent_update`。 |
| `websocket/endpoint.py` | `WS /ws`。連上先送 `world_snapshot`，之後只收連線（client 不驅動模擬）。 |
| `websocket/manager.py` | 連線清單與 `broadcast`。 |

### `backend/` 其他

| 路徑 | 職責 |
| --- | --- |
| `requirements.txt` | fastapi、uvicorn、pydantic、pytest、httpx。 |
| `pytest.ini` | `pythonpath = .`，`testpaths = tests`。 |
| `Dockerfile` | `python:3.12-slim`，`uvicorn app.main:app --host 0.0.0.0 --port 8000`。 |
| `tests/conftest.py` | 關閉模擬迴圈；每個測試重置 world 與 WebSocket 連線。 |
| `tests/test_clock.py` | 時鐘進位與 `World.tick()` 跨日。 |
| `tests/test_agents.py` | 行程與移動。 |
| `tests/test_events.py` | `left` / `entered` 與事件上限。 |
| `tests/test_api.py` | HTTP API。 |
| `tests/test_websocket.py` | snapshot 與廣播。 |

### `game/`

Godot 4.7 專案。主場景 `scenes/main.tscn`。視窗 1280×720。

| 路徑 | 職責 |
| --- | --- |
| `project.godot` | 專案設定。features `4.7`。 |
| `export_presets.cfg` | Web preset，輸出 `build/web/index.html`。 |
| `serve_web.py` | 本機提供 web export，帶 COOP/COEP。預設 `127.0.0.1:8080`。 |
| `scenes/main.tscn` | `Main` + `NetworkClient` + `World` + `HUD`。 |
| `scenes/world.tscn` | 純色背景與四個 POI marker（ColorRect + Label）。 |
| `scenes/npc.tscn` | NPC：ColorRect 方塊 + 名字 Label。 |
| `scenes/ui/hud.tscn` | 時鐘、連線狀態、agent 數、事件日誌。 |
| `scripts/main.gd` | 把 WebSocket signal 接到 World 與 HUD。 |
| `scripts/network_client.gd` | WebSocket client。桌面預設 `ws://127.0.0.1:8000/ws`。Web build 用頁面同源 `/ws`；分進程本機開發用 query `?ws=`。斷線後 2s 起、上限 30s 重連。 |
| `scripts/world.gd` | 依 snapshot / agent_update 生成或更新 NPC。`_ready` 檢查場景 POI 座標是否與 backend 一致。 |
| `scripts/npc.gd` | 把座標 lerp 向 server 位置。顏色依 agent id（Mina 粉、Alex 青）。 |
| `scripts/hud.gd` | 時鐘、連線、人數、事件文字。時鐘只在 snapshot 與 agent_update 更新。 |
| `scripts/event_log.gd` | 事件日誌，最多 20 行。 |

`game/build/` 與 `.godot/` 不進 git。

### `deploy/`

| 路徑 | 職責 |
| --- | --- |
| `docker-compose.yml` | backend、postgres:16、redis:7、cloudflared（profile `tunnel`）。 |
| `.env.example` | `BI_TOWN_PORT`、Postgres、`ENVIRONMENT`、`TUNNEL_TOKEN`。 |

### `.github/workflows/`

| 路徑 | 職責 |
| --- | --- |
| `ci.yml` | PR 進 `main`，以及 merge 後再跑一次。見第 4 節。 |
| `deploy-staging.yml` | CI 在 `main` 成功後才部署。見第 4 節。 |

### 根目錄其他

| 路徑 | 職責 |
| --- | --- |
| `README.md` | 短概述與本機 uvicorn / pytest。 |
| `ruff.toml` | Python 3.12，line length 88。規則 E、F、I、UP、B。 |
| `.gitignore` | `.env`、`.venv/`、`game/build/`、`.godot/`。保留 `.env.example` 與 `deploy/.env.example`。 |
| `.env.example` | 根目錄範本。v0.1 沒有必填 secret。 |
| `LICENSE` | MIT。 |

## 4. 開發流程

1. 從 `main` 開 feature branch，開 PR 進 `main`。
2. `main` 有 branch protection。
3. CI（`.github/workflows/ci.yml`）在 PR 與 push `main` 時跑。任一 job 失敗，workflow 失敗。三個 job：
   - `backend-test`：Python 3.12，`pytest -v`，`ruff check backend/`。
   - `docker-validate`：`docker build backend/`；複製 `.env.example` 成 `.env` 後 `docker compose config --quiet`（空的 `TUNNEL_TOKEN` 可過）。
   - `godot-export-check`：image `barichello/godot-ci:4.7.2`，headless export Web，確認 `index.html` 與 `index.wasm` 非空，artifact 名稱 `godot-web-build`（保留 7 天）。
4. Merge 進 `main` 後 CI 再跑一次。這次成功才會觸發 CD。CD 沒有自己的 `push` trigger。
5. CD（`.github/workflows/deploy-staging.yml`）：
   - 條件：上游 CI workflow 結論為 success，且 branch 是 `main`。
   - GitHub environment：`staging`。secret 只放在該 environment，workflow 不印出 secret。
   - Tailscale（`tag:ci`）連上 staging host，SSH。
   - rsync Godot web artifact 到 `/srv/bi_town/game/build/web/`（`--delete`）。不碰 host 上的 `deploy/.env`。
   - host 上：`cd /srv/bi_town && git fetch origin main && git reset --hard origin/main`。`GIT_COMMIT`（完整 SHA）是映像建置參數；`DEPLOYED_AT`（UTC）在 `docker compose up` 時寫進容器環境。
   - 健康檢查：本機 `http://127.0.0.1:8100/api/health` 與公開 `https://bitown.aicanhelp.app/api/health` 都要過。公開網址是經 Tailscale SSH 在部署主機上 curl，仍走 Cloudflare 與 Tunnel，不從 GitHub runner 打。每 3 秒一次，最多 60 秒。`status` 須為 `ok`，`git_commit` 須等於觸發這次部署的 CI commit（`workflow_run.head_sha`），`deployed_at` 不可為 `unknown`。本機回應還須帶 `Cache-Control: no-store`。公開網址的 SHA 對不上也會讓 job 失敗。
   - concurrency group `bi-town-staging`，新的部署會取消進行中的部署。

## 5. 關鍵約定

- Server authoritative。模擬決策只寫在 backend。Godot 只顯示 server 座標與狀態；NPC 的 lerp 是畫面內插，不改變模擬結果。
- 新的數字與開關放 `backend/app/config.py`，不要散落在 route 或 simulation。
- Python 3.12，函式加 type hints。Lint 用 ruff（見 `ruff.toml`）。測試用 pytest，世界狀態用 `reset_world()`，不要靠測試間殘留狀態。
- 測試會把 `SIMULATION_LOOP_ENABLED` 設為 `False`，避免背景 tick 干擾。
- Godot 的 POI 座標要與 `backend/app/simulation/poi.py` 相同。`world.gd` 在 `_ready` 會對不上就 `push_error`。
- 不 commit secrets。`.env` 與 `deploy/.env` 不進 git。staging 的 `TUNNEL_TOKEN`、Tailscale、SSH 只在 GitHub environment `staging` 與 host 上。
- WebSocket 是 server → client。Client 連上後送出的文字不被當成指令。

## 6. 本機開發怎麼跑

需求：Python 3.12+。Godot 編輯器 4.7（CI export 用 4.7.2）。

Backend（API + WebSocket，不提供網頁）：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

測試與 lint：

```bash
cd backend
source .venv/bin/activate
pytest
ruff check backend/
```

Godot 編輯器：開啟 `game/`（`game/project.godot`）。桌面執行時 WebSocket 預設打 `ws://127.0.0.1:8000/ws`，backend 要先在 8000。

Web export（headless，與 CI 相同的兩步）：

```bash
cd game
godot --headless --import --quit
godot --headless --export-release "Web" build/web/index.html
```

本機看 web export（與 uvicorn 分開，要自己帶 COOP/COEP）：

```bash
python3 game/serve_web.py
# http://127.0.0.1:8080/?ws=ws://127.0.0.1:8000/ws
```

`?ws=` 只在 web build 有效。同源部署（compose 或正式站）不需要這個參數，client 會連頁面自己的 host 的 `/ws`。

Docker Compose（含 Postgres、Redis；不含 tunnel）：

```bash
cd deploy
cp .env.example .env
docker compose up --build
```

瀏覽器開 `http://127.0.0.1:8100/`。前提是已經 export 到 `game/build/web/`（compose 把該目錄掛進 backend）。

要連 Cloudflare Tunnel 時才加 profile（需要 `deploy/.env` 裡的真實 `TUNNEL_TOKEN`）：

```bash
cd deploy
docker compose --profile tunnel up -d --build
```

## 7. 已知待辦

這三項是現況缺陷，尚未修。

- 時鐘在全員 idle 時停走。`World.tick()` 仍會 `advance_clock`，但 `broadcast_tick` 只在 `changed_agents` 非空時送 `agent_update`。該遊戲分鐘沒有人出發、也沒有人在走時，client 收不到新的 day/time。HUD 只在 `world_snapshot` 與 `agent_update` 改時鐘。沒有 `time_update`（或同等、即使沒有 agent 變動也帶 day/time 的廣播）。
- Day 顯示 `1.0`。`hud.gd` 的 `_set_clock` 用 `%s` 印 `data["day"]`。Godot `JSON.parse_string` 把 JSON number 解成 float，整數 day 會印成 `1.0`。
- 同地點 NPC 名字重疊。兩個 agent 停在同一 POI 時座標相同，`npc.tscn` 的 Label 以節點為中心，沒有錯開。

## 8. v0.2 roadmap

順序固定，LLM 排在最後：

1. 視覺基礎：tilemap、NPC sprite（取代現在的 ColorRect 方塊與純色背景）。
2. Needs 系統。
3. NPC 狀態圖示。
4. 之後才接 LLM。v0.1 的 fake agent 與 WebSocket pipeline 是這一步之前的骨架。
