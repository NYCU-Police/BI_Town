# 手繪覆寫

外觀記在 `game/data/visual_manifest.json`，只存 kind、category、footprint、origin 與顏色，不存路徑。

`VisualBinder` 用 content id 推出檔名，依序找：

1. `res://assets/packs/user/<category>/<name>.png`
2. `res://assets/packs/default/<category>/<name>.png`
3. 依 footprint 畫色塊，並標上 content id

`category` 目錄是 `poi`、`actors`、`items`、`tools`、`fx`。`agent.*` 對應 `actors`，`item.*` 對應 `items`，`tool.*` 對應 `tools`。manifest 用 `FileAccess.file_exists()` 判斷；PNG 用 `ResourceLoader.exists()`。圖存在就用 nearest 畫。同一個 content id 的 fallback 只警告一次。manifest 讀不到則 `push_error`。

手繪蓋過預設圖的流程：

1. 把 PNG 放到 user pack，例如 `game/assets/packs/user/actors/mina.png`。
2. 匯入：在 `game/` 執行 `godot --headless --import`，或打開編輯器讓它匯入。
3. 執行遊戲，或重新 export。

也就是：放 PNG → `godot --headless --import`（或開編輯器）→ 執行／重新 export。
