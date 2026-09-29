# BI_Town 專案狀態

給新的 AI 助手對話或新加入的隊友接手。描述的是 `origin/main` 在 PR #38 合併之後的現況（v0.1.0），不是目標產品，也不包含尚未合併的 PR #39。

## 1. 專案是什麼

- 名稱：BI_Town（Behavioral Intelligence Town）。版本常數在 `backend/app/config.py` 的 `VERSION = "0.1.0"`。
- 類型：AI-native social simulation。程式預設大腦是行程表，不是 LLM。`BRAIN_MODE=llm` 才改走本機模型。正式站現在跑的是 `llm`（日誌有「（想）」、Rin 在場）。程式預設仍是 `rules`；改模式見 `docs/DEPLOY.md`。
- 架構：server-authoritative。World state 的唯一來源是 FastAPI backend。Godot client 只渲染 server 送來的狀態，不自行推進時鐘、不決定 NPC 去向。
- World 存在 process 記憶體（`backend/app/state.py` 的 `World` singleton）。重啟即重置。Postgres 與 Redis 只在 Docker Compose 裡待命，backend 程式尚未連線。
- 開局：Day 1、08:00。`rules` 只有 Mina、Alex，走行程表。`BRAIN_MODE=llm` 改為 Mina、Alex、Rin，三人都從自己的家出發，決策打本機 Ollama。地點是下面九個 POI，沒有共用的 `home`。
- 正式站：https://bitown.aicanhelp.app （Cloudflare Tunnel）。健康檢查：`/api/health`（含 `version`、`git_commit`、`deployed_at`、`brain_mode`）。部署步驟與回滾見 `docs/DEPLOY.md`。合併進 `main` 且 CI 成功就會部署，世界回到 Day 1 08:00。正式站的 `BRAIN_MODE` 現在是 `llm`。程式預設仍是 `rules`。

## 1.1 已合併的謎題（PR1–PR3）

玩法規格在 `docs/GDD.md`。案件 JSON 用 `schemas/case.schema.json` 驗證；Docker 只複製 `backend/app`，所以同一份 schema 也放在 `backend/app/simulation/cases/case.schema.json`，兩份必須逐字相同。案件在 import 時驗證，不由模型生成。

| PR | 合併 | 分支上的事 |
| --- | --- | --- |
| #35 PR1 | `47e2838` | 自由文字 `talk`、伺服器發的 `player_token`、深色對話框、`conversing` 圖示、單播 `dialogue_result`。`rules` 立刻回 `npc_unavailable`。玩家對話優先於居民工作。 |
| #36 PR1.1 | `66f60d7` | 玩家句子包在 `<player>`，歷史包在 `<history>`。`talk_log` 最多 200 則。dossier 超過 500 個 token 時丟掉最久沒出現的。斷線清掉 `conversing` 並廣播 `conversing_ended`。重連用 `dialogue_history` 把對話框補回來。 |
| #37 PR2 | `9e6adad` | 三個內建案件輪替、信任、允許清單、私人筆記、廣場公告。 |
| #38 PR3 | `654e2a1` | 出示筆記對質、八卦只傳標籤、犯人避開。 |

尚未合併：`feat/mystery-pr4` 是 PR #39，等玩法方向確認。它不在這份現況裡。不要把它當成已上線，也不要在沒有新指示時合併或接著開下一號功能 PR。

### 案件、信任、筆記（PR2）

- 三個案件：`builtin_cashbox`、`builtin_torn_notice`、`builtin_unsigned_letter`。第 `day` 天用 `(day - 1) % 3`。換日時鐘跨過午夜會換案件，廣場公告改成新的 `public_brief`，筆記改成新案件的公開事實。信任與對話記憶不會因為換日清空。
- 廣場公告就是當天 `public_brief`。筆記按 N 打開，不佔快捷欄。筆記存的是 fact id，畫面上是句子。對質失敗的 `crack_text` 不是 fact id，那一列的 id 是空字串。
- 信任起點 `TRUST_START` 20。送麵包 +15（一份麵包 20→35，不夠看信任 40 的事實），其他給予 +6，每輪對話最多再 +10（每次 +2）。對方飽足低於 `NEED_HUNGRY` 30 時信任 -20。案件要能在信任 40 以內解完（`TRUST_SOLVE_MAX`）。
- 允許清單：這位居民持有、有效信任夠、前置證據已在筆記、且不是公開事實。先依 `requires_trust` 由低到高排，再切到最多 8 條。公開事實不進個人允許清單，但 `public_brief` 會進 prompt。
- Prompt 的使用者訊息以「今天鎮上的事：{public_brief}」開頭。`kind: truth` 放在「你知道、可以說的事」，`kind: lie` 放在「你要堅持的說法」。每條用 `say_text`（沒有才用 `text`），並附標籤。系統要求第一人稱說謊、不編允許清單以外的細節、只答被問到的事。模型回傳的 `revealed_fact_ids` 先和允許清單交集，寫進筆記的是事實原文。允許清單是空的時，schema 的 `maxItems` 是 0。被丟掉的 id 只記一筆 warning。

### 對質、八卦、避開（PR3）

- `present_evidence` 的 `target` 是居民，`fact_id` 必須已在這位玩家的筆記。兩人要在同一地點，對方不能在走路或倒下。對話框沒開、或框裡那位不在面前，客戶端的「出示」是停用的。送給的是對話框綁定的那位，不是畫面上第一個掃到的人。
- `rules` 在檢查筆記之前就回 `npc_unavailable`，畫面上是「他好像沒空理你。」，所以不會洩漏筆記裡有沒有那條。
- 出示的事實若對上對方持有謊言的 `contradicts`，該謊的 `truth_id` 在這回合追加進允許清單，加在 8 條上限之後，不會被切掉。Prompt 在謊言旁邊加「玩家拿出的證據」。系統補一句：證據矛盾時可以改口承認那些 truth id，或閃躲，但不能否認證據本身。模型若回了 truth id，筆記寫事實原文並保留模型回覆。沒回就寫 `crack_text`，回覆改成 `CONFRONT_CRACK_REPLY`。對不上的事實就是普通對話，不額外解鎖。筆記因此變多時，客戶端播既有的給予音效；承認與 crack 走同一條，不分開。
- 玩家與居民 X 的這一輪若 X 實際交回了事實，那些事實的標籤記在 X 對這位玩家的紀錄上，來源是 X。什麼都沒交回就不記。自己交回的標籤不會讓自己開始避開。
- `asked_tags` 與 `heard_tags` 的葉子是 `dict[tag, set[origin_resident_id]]`。兩位居民在同一地點、都 idle，每 `GOSSIP_INTERVAL_MINUTES` 20 遊戲分鐘互相複製「哪位玩家問過哪些標籤」。不呼叫模型。複製前先留下來源快照。嚇到人只看來源裡除了接收者自己以外還有別人、而且標籤打中這位犯人持有謊言的敏感標籤。只有犯人自己的來源不會避開；同一條標籤只要還有別人的來源就會避開。Prompt 用的仍是標籤清單（「有人問過這類事」），不帶來源。
- 避開持續 `CULPRIT_AVOID_MINUTES` 60 遊戲分鐘，時間到就解除。期間下一個移動會改寫，避免停在那位玩家所在的地點；家與 `WORK_PLACES`（Mina、Alex 是咖啡廳與辦公室，Rin 是圖書館）仍可去。避開時 prompt 在歷史前插入「你最近在躲這位玩家」。出示不被避開擋住。避開與八卦用 token 當鍵，不用連線上的 player id。

## 1.2 rules 與 llm 差在哪

兩邊共用同一個時鐘、同一套案件、同一份信任與筆記。時鐘預設每真實秒 1 遊戲分鐘，整天都會走完，沒有鎮民大會。正式站主機現在是 `llm`。表裡的「預設」指程式與測試，不是正式站。

| | `rules`（程式預設，測試固定這個） | `llm`（正式站現在是這個） |
| --- | --- | --- |
| 居民 | Mina、Alex，行程表在 `fake_agent.py` | Mina、Alex、Rin。Rin 只在這個模式出現 |
| 決策 | `tick()` 內：倒下 → 手上有食物且飢餓低於門檻 → 否則行程。接著移動、需求、時鐘 | 另一個 async worker 呼叫 Ollama。`tick()` 只套用已經回來的決定，不把模型呼叫算進這一秒。倒下時不採用模型的移動 |
| `talk` / `present_evidence` | 立刻 `npc_unavailable`，不進佇列、不呼叫模型、不記標籤、不解鎖事實 | 進對話佇列，玩家工作優先。模型只負責說法，事實只能從允許清單來 |
| 八卦與避開 | 函式仍會跑，但沒有成功的對話就沒有標籤，避開不會開始 | 標籤會記、會傳、會改寫犯人的下一步 |
| 事件 | `left` / `entered` 與物品事件 | 另外有 `said`、`thought`，內容先轉繁體 |
| 測試 | `tests/conftest.py` 把 `BRAIN_MODE` 設成 `rules` | 個別測試再改成 `llm` |

## 1.3 `config.py` 的名稱與預設

模擬數字都在 `backend/app/config.py`。下面是 main 上的值。環境變數有寫出來的才會蓋過預設；沒寫的就是常數。

時鐘與模式：

| 名稱 | 預設 |
| --- | --- |
| `SIMULATION_TICK_SECONDS` | `1.0` |
| `GAME_MINUTES_PER_TICK` | `1`（舊常數；實際速度看下面的函式） |
| `game_minutes_per_real_second()` | 環境變數 `GAME_MINUTES_PER_REAL_SECOND`。空白、非整數或 ≤ 0 都回 `1.0`。正數才採用。main 的程式預設是 1.0 |
| `SIMULATION_LOOP_ENABLED` | `True`（測試會關掉） |
| `INITIAL_DAY` / `INITIAL_TIME` | `1` / `"08:00"` |
| `current_brain_mode()` | 環境變數 `BRAIN_MODE`，只接受 `rules` 或 `llm`，其他回到 `rules` |
| `current_llm_think()` | 環境變數 `LLM_THINK` 為 `1` / `true` / `yes` / `on` 才開，否則關 |
| `STATIC_WEB_DIR` | 環境變數，空字串表示只提供 API |

謎題與對話（PR1–PR3 加的）：

| 名稱 | 預設 |
| --- | --- |
| `PLAYER_TOKEN_BYTES` | `32`（`token_urlsafe`，格式 `^[A-Za-z0-9_-]{43}$`） |
| `SHOW_PRODUCED_IN_EVENT_LOG` | `False` |
| `TALK_LOG_LIMIT` | `200` |
| `DOSSIER_LIMIT` | `500` |
| `TRUST_START` | `20` |
| `TRUST_GIFT_BREAD` | `15` |
| `TRUST_GIFT_OTHER` | `6` |
| `TRUST_TALK` | `2` |
| `TRUST_TALK_CAP_PER_ROUND` | `10` |
| `TRUST_HUNGER_PENALTY` | `20` |
| `TRUST_SOLVE_MAX` | `40` |
| `GOSSIP_INTERVAL_MINUTES` | `20` |
| `CULPRIT_AVOID_MINUTES` | `60` |
| `CONFRONT_CRACK_REPLY` | `……這句我沒辦法再照原樣說。` |
| `WORK_PLACES` | mina/alex：`cafe`、`office`；rin：`library` |
| `LLM_QUEUE_MAX` | `8`（不含正在跑的那筆） |
| `DIALOGUE_TIMEOUT_SECONDS` | `20.0` |
| `DIALOGUE_MAX_QUEUE_WAIT_SECONDS` | `25.0` |
| `DIALOGUE_PARSE_RETRIES` | `1`（只重試 JSON） |
| `DIALOGUE_FALLBACK_REPLY` | `……我現在不太想說。` |
| `DIALOGUE_MEMORY_TURNS` | `6` |
| `DIALOGUE_MAX_FACTS_IN_PROMPT` | `8` |
| `DIALOGUE_REPLY_MAX_CHARS` | `80` |
| `TALK_MAX_CHARS` | `200` |
| `TALK_MIN_INTERVAL_SECONDS` | `8.0` |
| `TALK_MAX_PER_MINUTE` | `6` |
| `TALK_MAX_PER_ROUND` | `40` |
| `TALK_BLOCK_SUBSTRINGS` | 兒童性剝削相關字串，命中就拒 |

移動、需求、物品：

| 名稱 | 預設 |
| --- | --- |
| `AGENT_SPEED_PER_TICK` | `50.0` |
| `ARRIVAL_DISTANCE_THRESHOLD` | `10.0` |
| `MAX_WORLD_EVENTS` | `50` |
| `NEED_MAX` | `100.0` |
| `NEED_START_ENERGY` / `FULLNESS` / `SOCIAL` | `80.0` / `70.0` / `65.0` |
| `ENERGY_DECAY_PER_MINUTE` | `0.05` |
| `FULLNESS_DECAY_PER_MINUTE` | `0.08` |
| `SOCIAL_DECAY_PER_MINUTE` | `0.04` |
| `SOCIAL_COMPANY_PER_MINUTE` | `0.04` |
| `EAT_FULLNESS_RESTORE` | `35.0` |
| `CAFE_HUNGER_RESTORE_PER_MINUTE` | `0.12` |
| `HOME_ENERGY_RESTORE_PER_MINUTE` | `0.10` |
| `COLLAPSE_NEED` | `0.0`（線上的 hunger 是飽足；飽足或體力 ≤ 0 就是倒下） |
| `BREAD_RESPAWN_MINUTES` | `20` |
| `BREAD_STOCK_MAX` | `4` |
| `FOOD_ITEMS` | `bread` |
| `TOOL_IDS` / `PARK_TOOL_ID` / `PARK_PRODUCT_ID` | `watering_can` / `watering_can` / `wood` |
| `PLAYER_ENABLED` | `True` |
| `INTENT_RATE_LIMIT_PER_SEC` | `5` |
| `INTENT_MAX_BYTES` | `4096` |
| `SLEEP_ENERGY_PER_MINUTE` / `REST_ENERGY_PER_MINUTE` | `0.25` / `0.08` |
| `TALK_SOCIAL_RESTORE` | `12.0` |
| `NEED_TIRED` / `NEED_EXHAUSTED` | `55.0` / `30.0` |
| `NEED_PECKISH` / `NEED_HUNGRY` | `55.0` / `30.0`（`HUNGER_ACTION_THRESHOLD` 等於 `NEED_HUNGRY`） |
| `NEED_LONELY_HINT` / `NEED_LONELY` | `55.0` / `30.0` |
| `SLEEP_HOUR` / `WAKE_HOUR` | `22` / `7` |

模型路徑（只有 `llm` 會用到）：

| 名稱 | 預設 |
| --- | --- |
| `DEFAULT_OLLAMA_URL` | `http://127.0.0.1:11434` |
| `DEFAULT_LLM_MODEL` | `qwen3:14b` |
| `DEFAULT_LLM_TIMEOUT_SECONDS` | `60.0` |
| `LLM_TEMPERATURE` | `0.8` |
| `LLM_IDLE_DECISION_MINUTES` | `15` |
| `LLM_IDLE_DECISION_MINUTES_BUSY` | `45` |
| `LLM_DECISION_MAX_PER_ROUND` | `8` |
| `LLM_MAX_CONSECUTIVE_DIALOGUE` | `4` |
| `LLM_DIALOGUE_COOLDOWN_MINUTES` | `30` |
| `LLM_RECENT_SAY_LIMIT` / `LLM_RECENT_SAY_PROMPT_LIMIT` | `5` / `3` |
| `LLM_RECENT_THOUGHT_LIMIT` | `3` |
| `LLM_SAY_SIMILARITY` / `LLM_THOUGHT_SIMILARITY` | `0.8` / `0.9` |
| `LLM_MIN_STAY_MINUTES` | `20` |
| `LLM_UNANSWERED_MINUTES` | `30` |
| `LLM_MEMORY_PROMPT_LIMIT` / `LLM_MEMORY_STORE_LIMIT` | `10` / `50` |
| `LLM_BACKGROUND_TIMEOUT_SECONDS` | `20.0` |
| `PLAN_MIN_ITEMS` / `PLAN_MAX_ITEMS` | `4` / `6` |
| `REVIEW_HISTORY_DAYS` | `3` |
| `EATING_ACTIVITIES` | `cook`、`order_coffee`、`shop` |
| `RESTING_ACTIVITIES` | `rest` |
| `SLEEPING_ACTIVITIES` | `sleep` |
| `ACTIVITY_MINUTES` | 見 `config.py` 的字典（例如 `order_coffee` 10、`sleep` 60） |
| `VERSION` / `SERVICE_NAME` | `0.1.0` / `BI_Town` |

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

- 模擬迴圈：`simulation_loop` 每 `SIMULATION_TICK_SECONDS`（1 秒）呼叫一次 `World.tick()`。`GAME_MINUTES_PER_REAL_SECOND`（預設 0.4，環境變數可蓋）用浮點累加，滿 1 才推進 1 遊戲分鐘。還沒滿的 tick 只移動正在走路的人。
- `llm` 模式走到 18:00 開鎮民大會：時鐘停在 18:00，需求仍結算，居民改往廣場。玩家用 `accuse` 指認人與動機，不呼叫模型。揭曉後 45 真實秒，或所有在線玩家都按下一局，一起進入下一天 08:00，私人進度清空、token 保留。`rules` 不開大會，時鐘照常走過 18:00。正式站要等 PR4 部署成功後，由人把 `deploy/.env` 的 `BRAIN_MODE` 改成 `llm` 再重新部署。見 `docs/DEPLOY.md`。
- `World.tick()` 在預設 `rules` 的順序：NPC 先看是否倒下，再看手上有沒有食物、飢餓是否低於門檻，否則才套行程 → 移動 walking agent → 需求結算 → 推進時鐘。`llm` 不套這條優先序；決策在另一個 async worker 裡跑，`tick()` 只套用已經回來的結果。需求照樣結算，倒下時不採用 LLM 的移動。
- Agent 狀態只有 `idle` 與 `walking`。行程命中時從 idle 改為 walking，並記一筆 `left`。抵達 POI（距離 ≤ `ARRIVAL_DISTANCE_THRESHOLD` 或 ≤ 本 tick 步長）後改回 idle，記一筆 `entered`。
- WebSocket 是雙向的。連線會生成 `player_<conn_id>`，斷線就從世界上移除。私人進度掛在伺服器發的 `player_token` 上。客戶端可送 `intent`，伺服器回 `intent_result` 後立刻廣播變動。見 `docs/ADR/0005-bidirectional-websocket.md`。
- WebSocket 訊息（`backend/app/models/schemas.py`）：
  - `session`：連線後的第一則，帶伺服器發的 `player_token`。
  - `world_snapshot`：接著整包狀態（day、time、agents、events、`you`、`dialogue_history`、`notice`、`notes`、`note_ids`）。`dialogue_history` 是這個 token 跟每位居民最近幾輪的私訊。`notice` 是廣場公告。`notes` 是句子，`note_ids` 是對上的 fact id（crack 那列是空字串）。按 N 打開筆記面板，不佔快捷欄。
  - `agent_update`：每個 tick 都送，附上 day 與 time。`agents` 只列本 tick 有移動、改狀態，或需求整數有變的人，可以是空陣列。需求只在整數變化時放進該 agent，並且是整數。`removed` 只在有人斷線時出現。
  - `world_event`：`left` / `entered`，以及 `ate` / `gave` / `picked_up` / `produced`（`item`，`gave` 另有 `target_agent_id`）。`llm` 模式另有 `said` 與 `thought`。句子由客戶端依 event type 組，伺服器不送現成句子。`said` / `thought` 的 content 在寫入前用 OpenCC `s2twp` 轉成繁體中文。`conversing` / `conversing_ended` 不含對白。
  - `intent` / `intent_result`：見 ADR 0005。`talk` 與 `present_evidence` 另有單播的 `dialogue_result`（只有那個連線看得到回覆，並帶 `note_ids`）。`rules` 這兩種都是 `npc_unavailable`。
- HTTP API（prefix `/api`）：`GET /health`、`GET /world`、`GET /agents`、`GET /events`。`/health` 帶 `Cache-Control: no-store`。`git_commit` 來自映像建置參數，`deployed_at` 來自容器建立時的環境變數；沒設定時是 `unknown`。Godot 殼檔（`/`、`index.html`、`index.js`、`index.wasm`、`index.pck`、`build_info.json`）回 `Cache-Control: no-cache`，並用 ETag 回 304。
- Web export 的 HUD 向 `/build_info.json` 讀前端 commit、向 `/api/health` 讀後端 commit。兩邊不同時，右側身分列用琥珀色。請求失敗只把缺的那側顯示成 `unknown`，遊戲繼續跑。CI 在 export 前把 `GITHUB_SHA` 寫進 `game/build_info.json`，export 後再複製到產物目錄。
- Godot web export 由 backend 以靜態檔提供。`STATIC_WEB_DIR` 有值且目錄內有 `index.html` 才 mount 在 `/`。本機只跑 uvicorn、沒設這個變數時，只提供 API 與 WebSocket。
- HTTP 回應帶 `Cross-Origin-Opener-Policy: same-origin` 與 `Cross-Origin-Embedder-Policy: require-corp`（Godot 4 WASM）。
- Docker Compose 一份檔同時給本機與 staging。backend 把 host 的 `game/build/web` 唯讀掛進容器 `/app/web`。對外 port 綁 `127.0.0.1:${BI_TOWN_PORT:-8100}` → 容器 8000。
- `cloudflared` 在 profile `tunnel`。本機 `docker compose up` 不會啟動它。Staging 用 `--profile tunnel`，token 來自 `deploy/.env` 的 `TUNNEL_TOKEN`。

Mina 行程（只在 `rules`）：08:00 cafe、09:00 office、12:00 cafe、13:00 office、18:00 park、20:00 home。
Alex 行程：約晚 30 分鐘；12:00 去 park（Mina 是 cafe）。行程裡的 `home` 會解析成 `home_for` 的那一戶。定義在 `backend/app/simulation/fake_agent.py`。

POI 座標（`backend/app/simulation/poi.py`、`game/scripts/world.gd`、`game/scenes/world.tscn` 三處必須一致）：

| id | 座標 |
| --- | --- |
| mina_home | (56, 96) |
| alex_home | (168, 96) |
| rin_home | (280, 96) |
| cafe | (392, 96) |
| store | (504, 96) |
| office | (56, 144) |
| library | (168, 144) |
| plaza | (280, 192) |
| park | (392, 320) |

## 3. 目錄結構

### `backend/app/`

| 路徑 | 職責 |
| --- | --- |
| `main.py` | FastAPI app。lifespan 啟動／取消模擬迴圈。COOP/COEP middleware。依 `STATIC_WEB_DIR` 掛 Godot 靜態檔。 |
| `config.py` | 全部設定與數字。route 與 simulation 不放 magic number。 |
| `state.py` | process 級 `world` singleton。`reset_world()` 給測試用。 |
| `api/routes.py` | `/api/health`、`/world`、`/agents`、`/events`。 |
| `models/schemas.py` | Pydantic models、世界訊息，以及 `intent` / `intent_result`。 |
| `simulation/clock.py` | 遊戲時鐘。`24:00` 進下一天 `00:00`。純函式。 |
| `simulation/world.py` | `World`、`tick()`、`apply_intent()`。同步、可單測。 |
| `simulation/player_talk.py` | 玩家 `talk` 與 `present_evidence`：過濾、允許清單、單播回覆與筆記。 |
| `simulation/gossip.py` | 居民之間複製問過的標籤；犯人避開，不呼叫模型。 |
| `simulation/assembly.py` | 18:00 大會、指認、揭曉與下一局。不呼叫模型。`rules` 不開大會。 |
| `simulation/job_queue.py` | 玩家對話優先於居民工作的單工佇列。 |
| `simulation/fake_agent.py` | 行程表、朝目標移動、`left` / `entered`。無 LLM。 |
| `simulation/poi.py` | POI id、名稱、座標。 |
| `simulation/cases/` | 三個內建案件、載入與 BFS。`case.schema.json` 必須與 `schemas/case.schema.json` 逐字相同。 |
| `simulation/needs.py` | 飢餓、體力、社交的每分鐘結算。 |
| `simulation/loop.py` | async 迴圈。tick 後廣播。只在 `changed_agents` 非空時送 `agent_update`。 |
| `websocket/endpoint.py` | `WS /ws`。先送 `session`，再送 `world_snapshot`，之後接受 `intent`。 |
| `websocket/manager.py` | 連線清單與 `broadcast`。 |

### `backend/` 其他

| 路徑 | 職責 |
| --- | --- |
| `requirements.txt` | fastapi、uvicorn、pydantic、pytest、httpx、opencc-python-reimplemented、jsonschema。 |
| `pytest.ini` | `pythonpath = .`，`testpaths = tests`。 |
| `Dockerfile` | `python:3.12-slim`，`uvicorn app.main:app --host 0.0.0.0 --port 8000`。 |
| `tests/conftest.py` | 關閉模擬迴圈，`BRAIN_MODE=rules`；每個測試重置 world 與 WebSocket 連線。 |
| `tests/test_dialogue.py` | 對話、token、佇列、注入包裝。 |
| `tests/test_cases.py` | 案件輪替、信任、允許清單、schema 逐字相同。 |
| `tests/test_confront.py` | 出示、八卦來源、避開。 |
| `tests/ws_helpers.py` | 測試用 WebSocket。第一則是 `session`，不是 snapshot。 |
| `tests/test_clock.py` 等 | 時鐘、行程、事件、HTTP、WebSocket、intent、需求、POI 同步、視覺 manifest、LLM。 |

### `game/`

Godot 4.7 專案。主場景 `scenes/main.tscn`。視窗 1280×720。

| 路徑 | 職責 |
| --- | --- |
| `project.godot` | 專案設定。features `4.7`。 |
| `export_presets.cfg` | Web preset，輸出 `build/web/index.html`。`exclude_filter` 排除 `build/*`，避免上一次的 web 產物再被打進 pck。 |
| `serve_web.py` | 本機提供 web export，帶 COOP/COEP。預設 `127.0.0.1:8080`。 |
| `scenes/main.tscn` | `Main` + `NetworkClient` + `World` + `HUD`。 |
| `scenes/world.tscn` | 地圖與 POI 位置節點。POI 外觀由 `VisualBinder` 畫，場景裡不放圖。 |
| `scenes/npc.tscn` | NPC：16×16 像素人物（3 倍、nearest）、腳下陰影、圓角名字底牌。 |
| `scenes/ui/hud.tscn` | 時鐘、連線狀態、agent 數、事件日誌、點角色後的需求卡。 |
| `scripts/main.gd` | 把 WebSocket signal 接到 World 與 HUD。 |
| `scripts/network_client.gd` | WebSocket client。桌面預設 `ws://127.0.0.1:8000/ws`。Web build 用頁面同源 `/ws`；分進程本機開發用 query `?ws=`。斷線後 2s 起、上限 30s 重連。可送 `intent`，並接收 `intent_result`。 |
| `scripts/world.gd` | 依 snapshot / agent_update 生成或更新 NPC。自己的角色用 snapshot 的 `you`。滑鼠靠近 POI 時高亮並顯示後端中文地名，F3 改顯示 content id。點擊後在目的地留標記直到抵達。點在角色身上則回傳該 agent。 |
| `scripts/camera.gd` | 預設以約 3 倍跟隨自己的玩家。滾輪縮放，拖曳後改為自由觀看，空白鍵回到玩家。 |
| `scripts/npc.gd` | 把座標 lerp 向 server 位置。停留時另加門口地面的顯示偏移，伺服器座標不變。四方向走路用 spritesheet，不再上下彈或左右翻轉。名字顏色讀 manifest 的 `name_color`。自己的角色頭上顯示「你」與向下箭頭，腳下有高亮圈。外觀走 `agent.<id>`。角色與樹、建物同一 `z_index`，依 Y 排序。 |
| `scripts/visual_binder.gd` | 依 content id 找 `packs/user` 再 `packs/default`，都沒有就畫 placeholder。`kind: none` 不畫色塊、不警告；user pack 圖仍畫，並與角色依 Y 排序。`kind: spritesheet` 依 `frame_size` 與 `anims` 切幀。placeholder warning 以 manifest key 為準。manifest 讀不到時 `push_error`。快捷欄圖示也走這裡。 |
| `data/visual_manifest.json` | 外觀設定（kind、category、footprint、origin、顏色；角色另有 frame_size 與 anims）。不存座標，也不存檔案路徑。9 個 POI 的 kind 是 `none`。四個 agent 是 `spritesheet`。 |
| `scripts/town_map.gd` | 用 Ninja Adventure 的草地、石板路、建物、樹與水面鋪圖。建物落在原本地塊。沒有路燈、長椅、噴水池立繪。廣場水池是水面格。 |
| `scripts/day_night.gd` | 依伺服器時刻用 CanvasModulate 上色，夜晚點亮窗戶與路燈。不推進時鐘。 |
| `scripts/game_audio.gd` | 第一次點擊後才播放。環境音樂、點擊、撿起、吃、給予。音量偏低，可靜音。 |
| `assets/fonts/` | Fusion Pixel 12px（OFL）。字級 12 與 24，nearest。 |
| `scripts/hud.gd` | 時鐘、連線、人數、事件文字、需求、快捷欄與筆記。快捷欄每格有編號、圖示與數量，數量在格子右下角，選中格有外框。底部操作說明有半透明深色底。點角色後左上角顯示名字與 hunger/energy/social，低於 30 標紅。事件句子依 event type 模板生成。時鐘只在 snapshot 與 agent_update 更新。筆記每條可出示。 |
| `scripts/player_input.gd` | 點角色查看需求，點 POI 移動。1–3 使用工具，4 使用目前選中物品，E 撿麵包，G 給予，Q 切換物品，N 開關筆記。出示只送給對話框綁定的那位居民，而且對方要在面前。失敗原因依 `intent_result.reason` 顯示具體中文。 |
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
| `.gitignore` | `.env`、`.venv/`、`game/build/`、`.godot/`、`game/assets/_incoming/`。保留 `.env.example` 與 `deploy/.env.example`。 |
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
   - 條件：上游 CI 是 `push`、結論為 success，且 head branch 是 `main`。`pull_request` 的 CI 不部署。
   - GitHub environment：`staging`。secret 只放在該 environment，workflow 不印出 secret。
   - Tailscale（`tag:ci`）連上 staging host，SSH。
   - rsync Godot web artifact 到 `/srv/bi_town/game/build/web/`（`--delete`）。不碰 host 上的 `deploy/.env`。
   - host 上：`git fetch origin main` 後 `git reset --hard` 到觸發這次部署的 CI commit（`workflow_run.head_sha`）。`GIT_COMMIT` 用同一個 SHA，不讀主機 `HEAD`。`DEPLOYED_AT`（UTC）在 `docker compose up` 時寫進容器環境。
   - 健康檢查：本機 `http://127.0.0.1:8100/api/health`、公開 `https://bitown.aicanhelp.app/api/health`，以及公開 `https://bitown.aicanhelp.app/build_info.json` 都要過。公開網址是經 Tailscale SSH 在部署主機上 curl，仍走 Cloudflare 與 Tunnel，不從 GitHub runner 打。每 3 秒一次，最多 60 秒。`/api/health` 的 `status` 須為 `ok`，`git_commit` 須等於該 CI commit，`deployed_at` 不可為 `unknown`。本機回應還須帶 `Cache-Control: no-store`。`build_info.json` 的 `commit` 也須等於該 CI commit。對不上會讓 job 失敗。
   - concurrency group `bi-town-staging`，`cancel-in-progress: false`。正在跑的不取消。排隊中只保留最新一個，中間的 pending 部署不會跑。

## 5. 關鍵約定

- Server authoritative。模擬決策只寫在 backend。Godot 只顯示 server 座標與狀態；NPC 的 lerp 是畫面內插，不改變模擬結果。
- 新的數字與開關放 `backend/app/config.py`，不要散落在 route 或 simulation。
- Python 3.12，函式加 type hints。Lint 用 ruff（見 `ruff.toml`）。測試用 pytest，世界狀態用 `reset_world()`，不要靠測試間殘留狀態。
- 測試會把 `SIMULATION_LOOP_ENABLED` 設為 `False`，避免背景 tick 干擾。
- Godot 的 POI 座標要與 `backend/app/simulation/poi.py` 相同。`world.gd` 在 `_ready` 會對不上就 `push_error`。
- 不 commit secrets。`.env` 與 `deploy/.env` 不進 git。staging 的 `TUNNEL_TOKEN`、Tailscale、SSH 只在 GitHub environment `staging` 與 host 上。
- WebSocket 雙向只接受 `intent`。模擬結果仍只由伺服器決定；客戶端不能直接改座標或需求。見 `docs/ADR/0005-bidirectional-websocket.md`。

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

Godot 編輯器：開啟 `game/`（`game/project.godot`）。桌面執行時 WebSocket 預設打 `ws://127.0.0.1:8000/ws`，backend 要先在 8000。手繪圖怎麼蓋過現有素材見 `docs/ART.md`。

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

TileMap 走 content id 這一輪不做。地面與建物仍由 `town_map.gd` 直接鋪格，沒有接到 `visual_manifest.json`。

先前三項畫面缺陷已修：全員 idle 時每個 tick 仍廣播 `agent_update`（時鐘繼續走）、HUD 把 day 轉成整數（不再顯示 `1.0`）、同座標的 NPC 只在 client 上錯開名字與對話泡泡，伺服器座標不變。

預設大腦仍是 `rules`。差異見第 1.2 節。正式站要改模式，由人改主機 `deploy/.env` 的 `BRAIN_MODE` 再重新部署，見 `docs/DEPLOY.md`。未設定時 compose 仍是 `rules`。

謎題做到 PR3。PR #39（`feat/mystery-pr4`）還沒進 main，等玩法確認。下一輪不要從這份文件推斷該合併它，或該開下一號功能。

## 8. v0.2 roadmap

順序固定，LLM 排在最後：

1. 視覺基礎：tilemap 與 NPC sprite 已取代 ColorRect 方塊與純色背景。角色、地圖、物品、表情、木框 HUD 與環境音樂都來自 Ninja Adventure（CC0）。TileMap 本身還沒改走 content id。噴水池立繪沒有，廣場是水面格。麵包圖是幸運餅，因為食物圖裡沒有麵包。
2. Needs 系統。
3. NPC 狀態圖示。
4. 之後才做產品意義上的 LLM 居民。目前的 `BRAIN_MODE=llm` 只是可選的本機路徑，預設仍是 rules，不算這一步完成。
