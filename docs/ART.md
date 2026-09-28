# 手繪覆寫

外觀記在 `game/data/visual_manifest.json`，只存 kind、category、footprint、origin 與顏色，不存路徑。

`VisualBinder` 用 content id 推出檔名。`kind` 為 `sprite` 時依序找：

1. `res://assets/packs/user/<category>/<name>.png`
2. `res://assets/packs/default/<category>/<name>.png`
3. 依 footprint 畫色塊，並標上 content id

`kind` 為 `none` 時，外觀由 TileMap 提供：不畫色塊，也不發 warning。`packs/user/<category>/<name>.png` 存在時仍然繪製，而且在角色下方。目前 9 個 POI 都是 `none`。

`category` 目錄是 `poi`、`actors`、`items`、`tools`、`fx`。`agent.*` 對應 `actors`，`item.*` 對應 `items`，`tool.*` 對應 `tools`。manifest 用 `FileAccess.file_exists()` 判斷；PNG 用 `ResourceLoader.exists()`。圖存在就用 nearest 畫。placeholder warning 以 manifest key 為準（`agent.player_…` 併成 `agent.player`），同一個 key 只警告一次。manifest 讀不到則 `push_error`。

角色的 `z_index` 高於 POI 與地圖裝飾。地名顯示後端的中文名稱；F3 切換後改顯示 content id。

手繪蓋過預設圖的流程：

1. 把 PNG 放到 user pack，例如 `game/assets/packs/user/actors/mina.png`。
2. 匯入：在 `game/` 執行 `godot --headless --import`，或打開編輯器讓它匯入。
3. 執行遊戲，或重新 export。

也就是：放 PNG → `godot --headless --import`（或開編輯器）→ 執行／重新 export。

全遊戲字型是 Fusion Pixel 12px（OFL，簡繁體字形都在同一檔）。濾鏡用 nearest，字級只用 12 與 24。授權在 `game/assets/fonts/`。
