# 手繪覆寫

角色、物品與地點的圖都記在 `game/data/visual_manifest.json`。`art` 是 `res://` 路徑；空字串表示還沒有圖。

`VisualBinder` 先用 `ResourceLoader.exists()` 看這張圖在不在。在的話用 `texture_filter = Nearest` 畫 sprite。不在的話畫一個 ColorRect，上面標 content id。專案設定 `rendering/textures/canvas_textures/default_texture_filter` 已是 Nearest。不要用 Godot 3 的 `filter` 旗標。

手繪蓋過現有圖的流程：

1. 把 PNG 放到 manifest 寫的路徑（例如 `game/assets/characters/mina.png`）。
2. 匯入：在 `game/` 執行 `godot --headless --import`，或打開編輯器讓它匯入。
3. 執行遊戲，或重新 export。

也就是：放 PNG → `godot --headless --import`（或開編輯器）→ 執行／重新 export。
