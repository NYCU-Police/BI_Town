# 手繪覆寫

外觀記在 `game/data/visual_manifest.json`，只存 kind、category、footprint、origin 與顏色，不存路徑。

`VisualBinder` 用 content id 推出檔名。`kind` 為 `sprite` 時依序找：

1. `res://assets/packs/user/<category>/<name>.png`
2. `res://assets/packs/default/<category>/<name>.png`
3. 依 footprint 畫色塊，並標上 content id

`kind` 為 `spritesheet` 時，同一路徑的 PNG 是動畫表。`frame_size` 是單幀大小，`anims` 的每個影格是 `[欄, 列]`。角色表是 16×16：欄 0–3 為下、上、左、右，走路用該欄的列 0–3，idle 只用列 0。圖缺失時仍畫色塊。

`kind` 為 `none` 時，外觀由 TileMap 提供：不畫色塊，也不發 warning。`packs/user/<category>/<name>.png` 存在時仍然繪製，並與角色、樹一起依 Y 排序。目前 9 個 POI 都是 `none`。

`category` 目錄是 `poi`、`actors`、`items`、`tools`、`fx`。`agent.*` 對應 `actors`，`item.*` 對應 `items`，`tool.*` 對應 `tools`。manifest 用 `FileAccess.file_exists()` 判斷；PNG 用 `ResourceLoader.exists()`。圖存在就用 nearest 畫。placeholder warning 以 manifest key 為準（`agent.player_…` 併成 `agent.player`），同一個 key 只警告一次。manifest 讀不到則 `push_error`。

角色與地圖上的樹、建物在同一個 `z_index`，依 Y 排序，所以站在樹後面會被樹擋住。地面、花與水面在更低的層，不參與這個排序。地名顯示後端的中文名稱；F3 切換後改顯示 content id。

日夜是 `CanvasModulate`，顏色跟伺服器傳來的時刻走：黎明偏暖、中午正常、黃昏偏橘、夜晚深藍。夜晚時建物窗戶有 `PointLight2D`。這只改畫面，不推進時鐘。

## Credits

Ninja Adventure Asset Pack，作者 Pixel-boy 與 AAA。
素材頁：https://pixel-boy.itch.io/ninja-adventure-asset-pack
授權：CC0 1.0 Universal（可商用、可再散布，不要求署名）。
https://creativecommons.org/publicdomain/zero/1.0/

這一輪用到的只有四張角色表（Princess、Knight、Monk、Boy）與 Floor、FloorDetail、House、Nature、Water tileset。麵包、木材、路燈、長椅、噴水池立繪在包裡沒有可對上的圖，保留 placeholder，沒有用其他來源替代。澆水壺、表情氣泡、UI 框、音樂、音效在包裡有，但還沒接上。

手繪蓋過預設圖的流程：

1. 把 PNG 放到 user pack，例如 `game/assets/packs/user/actors/mina.png`。
2. 匯入：在 `game/` 執行 `godot --headless --import`，或打開編輯器讓它匯入。
3. 執行遊戲，或重新 export。

也就是：放 PNG → `godot --headless --import`（或開編輯器）→ 執行／重新 export。

全遊戲字型是 Fusion Pixel 12px（OFL，簡繁體字形都在同一檔）。濾鏡用 nearest，字級只用 12 與 24。授權在 `game/assets/fonts/`。
