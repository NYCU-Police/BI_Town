# WebSocket 改為雙向，只接受 intent

## 狀態

接受（2026-09-28）

## 背景

v0.1 的 `/ws` 只有伺服器往客戶端。連上之後客戶端送出的文字被讀掉，不影響世界。玩家要能走動、撿東西、吃、給人、使用工具，就必須有一條進世界的路。

世界仍在單一 process 的記憶體裡。若把客戶端訊息當成可任意改狀態的指令，伺服器權威就不成立。

## 決定

連線在 `PLAYER_ENABLED` 開啟時建立 `player_<conn_id>`，從廣場出現，斷線即移除。`PLAYER_ENABLED`、`INTENT_RATE_LIMIT_PER_SEC`、`INTENT_MAX_BYTES` 放在 `backend/app/config.py`。

客戶端只送這一種訊息：

```json
{"type":"intent","client_seq":1,"intent":{"action":"move_to","target":{"type":"poi","id":"cafe"}}}
```

`target.type` 只接受 `agent` 與 `poi`。伺服器對該連線回：

```json
{"type":"intent_result","client_seq":1,"ok":true,"reason":null}
```

`World.apply_intent()` 是同步函式。WebSocket handler 呼叫它，再立刻廣播 `agent_update` 與 `world_event`。模擬時鐘與 NPC 決策仍只在 `tick()`。

`give`、`use_tool`、`pick_up` 要求行動者與對象在同一個 POI，且都不是走路途中。咖啡廳的麵包按 `BREAD_RESPAWN_MINUTES` 補 1 個，上限 `BREAD_STOCK_MAX`。公園對 `watering_can` 產出 `wood`。

事件只帶結構化欄位（誰、哪種 event、地點、物品、對象）。畫面上的句子由 Godot 依 event type 產生。

## 後果

- 每個連線是一個玩家。重啟 process 後玩家與庫存消失，和既有世界一樣。
- 超過每秒次數或位元組上限的訊息得到 `intent_result`，不改世界。
- 非 `intent` 的文字仍被忽略，避免舊客戶端的雜訊驅動模擬。
- `PLAYER_ENABLED` 關掉時不建立玩家，`intent` 得到 `players_disabled`。
