# UI 規格

盤點從 UI 工作開始前的畫面寫起。指認與揭曉是 PR #39 合進 main 之後才有，列在 1.1 與第 3 節。本文件只定畫面，不改協定、不加素材。

寫這份文件時，工作樹停在 `feat/game-feel-2`，那條分支還沒有對話與筆記。下面的面板、訊息與顏色都從 `origin/main` 的程式讀來。開 UI-1 時從 `main` 拉分支，把這份文件帶過去。

## 1. 現況盤點

視窗 1280×720，`stretch/mode = canvas_items`，aspect 沒寫，Godot 4 預設 `keep`。960×540 與 1280×720 同為 16:9，整張畫面等比縮小，不會重排。字型是 Fusion Pixel 12px zh_hant，專案預設字級 12。`game_theme.tres` 只掛了這顆字，沒有 StyleBox、沒有顏色。

`packs/default/ui/` 四張圖都是 Ninja Adventure Theme Wood（CC0），在 `hud.gd` 的 `_ready` 裡被做成 `StyleBoxTexture`。`hud.tscn` 裡的深色 `StyleBoxFlat` 只存在於編輯器，一進遊戲就被蓋掉。

| 圖 | 尺寸 | 9-slice 實測 | 執行時用在哪 |
| --- | --- | --- | --- |
| `panel.png` | 16×16 | 左 6、上 6、右 5、下 5。中心 `#f38c4c` | 右欄、檢視卡，以及選中的快捷格。邊距在程式裡寫成四邊都是 6 |
| `panel_bg.png` | 16×16 | 約 2px 暗邊，填色 `#46402e` | 底部操作提示 |
| `slot.png` | 16×16 | 四邊 3。中心 `#8d977f` | 沒選中的快捷格 |
| `button.png` | 16×8 | 四邊 2。中心 `#f06733`。只有 normal，沒有 hover / pressed | 靜音鍵。四個狀態共用同一張，邊距寫成 0，邊框被拉伸 |

### 1.1 面板

| 面板 | 位置（1280×720） | 預設 | 顯示什麼 | 資料從哪來 | 問題 |
| --- | --- | --- | --- | --- | --- |
| 右欄 `Panel` | 錨右，寬 360，全高 | 顯示 | 標題與版本、frontend / backend commit、`Day` 與時間、`Server ● Online/Offline`、`Agents: N`、標題「Event Log」、最多 20 行事件 | 時鐘與人數：`world_snapshot`、`agent_update` 的 `day` / `time` / `agents`。事件：`world_snapshot.events` 與 `world_event`。版本與 commit：`/api/health`、`/build_info.json`，不是 WebSocket | 主欄在右側，不是左上。沒有居民名單，只有人數。亮灰字畫在 `#f38c4c` 上，對比約 1.0–2.1:1。commit 是除錯資訊，一直佔著玩家的欄。文案中英夾雜 |
| 事件日誌 | 右欄裡往下長 | 顯示，跟著捲 | 客戶端用 event type 組句。`produced` 與 `conversing_ended` 直接丟掉。其餘 `left` / `entered` / `activity` / `ate` / `gave` / `picked_up` / `said` / `thought` / `conversing` 都進同一條，12px，沒有分類。點名字會把鏡頭對到那個人 | `WorldEvent`：`timestamp`、`agent_id`、`event`、`location`、`target_agent_id`、`content`、`item`。句子是客戶端模板，伺服器不送現成句 | 移動與活動把 20 行額度洗掉。心聲與公開說話跟走路混在一起。名字色寫死在 `hud.gd`，沒有走 `visual_manifest` 的 `name_color` |
| 需求列 | 左下，快捷欄上方 | 顯示 | `Hunger N  Energy N  Social N` | 自己那名 agent 的 `needs`（`world_snapshot` / `agent_update`）。低於 30 的變色只做在檢視卡，這一行不變色 | 英文。玩家最常要看的數字，字小，又貼在操作提示上面 |
| 快捷欄 4 格 | 左下，每格 52×48 | 顯示。第 4 格預設選中 | 1–3 工具圖與數量，4 是目前物品。圖走 `VisualBinder` | 自己的 `tools`、`items` | 數字是亮色，坐在 `#8d977f` 或 `#f38c4c` 上，對比 2.6:1 與 2.1:1。選中格用整張橘色面板當外框 |
| 操作提示 | 快捷欄下方 | 顯示 | 固定句：點地點、滾輪、空白鍵、1–3、4、E、G、Q | 無。寫死在 `hud.tscn` | 沒寫 N，也沒寫「點居民再打字」。底是 `panel_bg`，這塊字本身讀得清楚 |
| 意圖一行 | 提示下方，高 22 | 空著，失敗才有字 | `intent_result.reason` 對應的中文，例如「他好像沒空理你。」`superseded` 不顯示 | `intent_result` | 琥珀字 `#f59e2e` 若疊在橘色面板上幾乎看不見。目前這一行的父節點沒套面板，字直接壓地圖 |
| 檢視卡 `Inspect` | 左上 16,16，寬 204，高 96 | 隱藏。點居民後出現 | 名字 24px，Hunger / Energy / Social。低於 30 變紅 | 被點那名 agent 的 `name` 與 `needs` | 跟靜音鍵（16,16，48×24）重疊。跟筆記（16,56）也重疊。同樣貼 `panel.png`，亮字對比不足 |
| 靜音鍵 | 程式建在 16,16 | 顯示，「聲音」/「靜音」 | 靜音 | 本地。第一次點擊後才有聲音 | hover 與 pressed 跟 normal 同一張圖。蓋住檢視卡 |
| 對話框 | 程式建。x 16–480，y 360–552 | 一直顯示 | 歷史、「你：…」、「{名字}對你說：…」、等待列「{名字}想了想」加 `·` / `··` / `···`（0.4 秒一拍）、輸入列 | `world_snapshot.dialogue_history`（`speaker_id`、`reply`、`role`）。送出後先本地加一行，再送 `intent` `talk`。回覆是只給這條連線的 `dialogue_result`（`reply`、`speaker_id`）。`mood` 有欄位，畫面沒畫 | 深色 `#1c1916` / 字 `#f4f0e6`，跟右欄的橘色木框是兩套。空著也佔 464×192。輸入框沿用 Godot 預設淺色，沒進 theme。鍵盤送出沒有點擊音 |
| 筆記 | 程式建。x 16–336，y 56–320 | 隱藏。N 切換 | 標題「筆記」。每列一句加「出示」。空的顯示「還沒有筆記。」 | `world_snapshot.notes` / `note_ids`；`dialogue_result` 同兩個欄位；另外一則線上訊息 `type: notebook`（見第 5 節） | 顏色寫死。按鈕是 Godot 預設灰鈕，沒有停用原因。`note_ids` 為空的那列（對質後的 `crack_text`）與「還沒點人」看起來一樣，都是灰色「出示」 |
| 廣場公告 | 世界座標，廣場下方 | 有公告才有字 | `public_brief` 的句子 | `world_snapshot.notice`、`agent_update.notice`、`notebook.notice` | 白字描邊直接壓在地面上，沒有面板。不是 HUD 節點 |
| 地名 | 每個 POI 上方 −68px 一枚常駐；滑過時在 −54px 再畫一枚 | 常駐一直在 | `world.gd` 的中文地名。F3 改顯示 `poi.{id}` | 地名表在客戶端。伺服器只送 location id | 九個地點都會重疊，Rin 的家只是目前被看到的那個。`hud.gd` 另有一份相同地名表，給日誌用 |
| 頭上名字與公開泡泡 | 角色節點 | 名字一直在。`said` 才出泡泡 | 名字色來自 manifest。公開句在白底圓角泡泡，沒有「對你說」。活動文字是灰字加描邊 | `said` 的 `content` 走 `world_event`，全員看得到。私下回覆不進這裡 | 白底圓角是第三套形狀，跟像素框、深色對話框都不一樣 |
| 狀態圖示與浮動字 | 角色頭上 / 身上 | 條件成立才出現 | 飢餓、倒下、說話中用 `fx.hungry` / `fx.collapsed` / `fx.chat`。吃、撿、給有跳躍與浮動字 | `needs.hunger < 30`、`collapsed`、`conversing` / `conversing_ended`、`ate` / `picked_up` / `gave` | 浮動字顏色寫在 `npc.gd`。說話圖示分不出「公開一句」和「正在跟你談」 |
| 目的地標記 | 點過的 POI | 走到之前顯示 | 黃色針 | 本地，直到 `agent_update` 顯示自己不再 walking | 顏色寫死。不擋閱讀 |
| 指認與揭曉 | 畫面正中。錨點 0.5，440×360，x 420–860、y 180–540 | 隱藏。`phase` 為 `assembly` 或 `reveal` 才出現 | 人選、動機、倒數、狀態、「確認」；揭曉時改成正文、分數與「下一局」 | `assembly_open`、`reveal`，以及 `world_snapshot` 的 `phase` / `accused` / `reveal_text` / `remaining_seconds` / `score` | #39 用深色 `StyleBoxFlat` 與亮字 override。下拉是預設淺底。UI-5 改吃 theme |

快捷鍵現況：左鍵移動或點人，滾輪縮放，空白鍵鏡頭回到自己，1–3 工具，4 使用，E 撿，G 給予，Q 切換物品，N 筆記，F3 地名改 content id。

### 1.2 對比（右欄與檢視卡）

字色沿用以前深色底的亮灰，底已經換成 `panel.png` 的中心色 `#f38c4c`。WCAG 對比：

| 文字 | 對 `#f38c4c` |
| --- | --- |
| 標題約 `#edede6` | 2.06:1 |
| 時間約 `#dbdbd1` | 1.74:1 |
| 日誌 `#d1d1cc` | 1.58:1 |
| 移動 `#7a7a76` | 1.78:1 |
| 需求紅 `#ed5252` | 1.46:1 |
| 意圖琥珀 `#f59e2e` | 1.13:1 |

對話框 `#f4f0e6` 對 `#1c1916` 是 15.38:1。底部提示對 `panel_bg` 的 `#46402e` 是 9.44:1。讀得清楚的是這兩塊，不是橘色主欄。

同一套深色字 `#1c1916` 對按鈕中心 `#f06733` 是 5.58:1，對快捷格 `#8d977f` 是 5.72:1，對橘色中心 `#f38c4c` 是 7.22:1。所以橘色圖可以留在小控件上，字要改深，不能留在大段正文後面。

## 2. 設計提案

一套語言：大段文字坐 `panel_bg.png`，小控件用現有四張 9-slice。不新增圖、字、音效。顏色與 StyleBox 只寫在 `game_theme.tres`。`hud.gd` 與 `world.gd` 不寫 `Color(`。日誌裡的居民名字色是一組從 theme 讀出的字串。地圖上角色名字仍走 `visual_manifest` 的 `name_color`；那兩組不必相同，因為日誌坐在 `#46402e` 上，manifest 的 Mina / Alex 原色達不到 4.5:1。

### 2.1 色板與對比

自訂 theme type `UI`。正文只出現在 `bg`（`#1c1916`，輸入框）或 `panel`（`#46402e`，與 `panel_bg.png` 中心相同）。`ink` 只出現在按鈕與快捷格上。最低 4.5:1。

| 前景 | 背景 | 對比 |
| --- | --- | --- |
| `text` `#f4f0e6` | `bg` `#1c1916` | 15.38:1 |
| `text` `#f4f0e6` | `panel` `#46402e` | 9.08:1 |
| `text_dim` `#c4bba8` | `bg` `#1c1916` | 9.18:1 |
| `text_dim` `#c4bba8` | `panel` `#46402e` | 5.42:1 |
| `accent` `#ffad55` | `bg` `#1c1916` | 9.47:1 |
| `accent` `#ffad55` | `panel` `#46402e` | 5.59:1 |
| `warn` `#ffb4a8` | `bg` `#1c1916` | 10.29:1 |
| `warn` `#ffb4a8` | `panel` `#46402e` | 6.07:1 |
| `need_low` `#ff958c` | `bg` `#1c1916` | 8.27:1 |
| `need_low` `#ff958c` | `panel` `#46402e` | 4.88:1 |
| `ink` `#1c1916` | `button.png` 中心 `#f06733` | 5.58:1 |
| `ink` `#1c1916` | `slot.png` 中心 `#8d977f` | 5.72:1 |
| `ink` `#1c1916` | `panel.png` 中心 `#f38c4c` | 7.22:1 |
| `name_mina` `#f09aa0` | `panel` `#46402e` | 4.84:1 |
| `name_alex` `#6ec4d2` | `panel` `#46402e` | 5.16:1 |
| `name_rin` `#f2c759` | `panel` `#46402e` | 6.44:1 |

`name_mina` / `name_alex` 比 manifest 的 `#e8737a`、`#59b8c7` 亮一階，只為了在日誌的深褐底上達標。Rin 的 `#f2c759` 原本就過。`need_low` 與 `warn` 分開：低需求用較深的 `#ff958c`，失敗理由用 `#ffb4a8`。

停用按鈕的底是 `slot.png`，字仍是 `ink`。跟可用的橘色 `button.png` 分開，對比是表上 `ink` 對 `slot.png` 的 5.72:1。

地圖地名用 `MapLabel`：字是 `text`，黑描邊。草地沒有單一底色，不列入上表。

### 2.2 StyleBox

文字面板用 `panel_bg.png`，不用 `panel.png`。`panel.png` 的中心是 `#f38c4c`，9-slice 拉大之後正文仍坐在橘色上，深色字雖然達標，整欄還是一塊亮橙，跟對話框合成不了一套。

| theme 類型 | StyleBox | 圖與邊距 | 字 |
| --- | --- | --- | --- |
| `Panel` / `panel` | `StyleBoxTexture` | `panel_bg.png`。texture margin 四邊 2，content margin 12。中心 `TILE` | 子節點繼承 `text` |
| `Button` 的 normal / hover / pressed / focus | `StyleBoxTexture` | `button.png`。texture margin 四邊 2，content margin 左右 4、上下 2。中心 `TILE` | `ink`，12px。沒有第二張圖，這三態先同一張；UI-4 才用 modulate 與下移 1px 分開 hover / pressed |
| `Button` 的 disabled | `StyleBoxTexture` | `slot.png`，與 `Slot` 同一張。margin 四邊 3 | `ink`，12px。灰底，跟橘色可用按鈕分開 |
| `Slot` / `panel` | `StyleBoxTexture` | `slot.png`。margin 四邊 3 | 格內數字 `ink` |
| `SlotSelected` / `panel` | `StyleBoxTexture` | `panel.png`。margin 左 6、上 6、右 5、下 5 | 格內數字 `ink` |
| `LineEdit` / normal、focus、read_only | `StyleBoxFlat` | 填 `bg`，邊 1px `#9b513c`，content margin 8,4 | 字 `text`，placeholder `text_dim`，12px |
| `OptionButton` | 同 `Button` 的五個 StyleBox | `button.png`；停用是 `slot.png`。字 `ink`，12px | 人選與動機。控件本身是橘色鈕，坐在 `panel_bg.png` 上仍可讀 |
| `PopupMenu` / panel、hover | panel 是 `panel_bg.png`；hover 是 `accent` 的 `StyleBoxFlat` | 字 `text`；滑過那一列字改 `ink` | 展開的名單。深底亮字，滑過是淺橘底深字 |

公開泡泡的 `Bubble` 留到 UI-3，這次的 theme 還沒有它。對話框與筆記就是 `Panel`，吃 `panel_bg.png`。

`hud.tscn` 不再內嵌 StyleBox。程式建的對話框、筆記、靜音鍵與「出示」不再自己上色。靜音與「出示」是 `Button`，字是 `ink`。停用時底改成 `slot.png`，字色不變。

日誌 BBCode 的說話用 `text`，移動與心聲用 `text_dim`。居民名字用上面的 `name_mina` / `name_alex` / `name_rin`。

### 2.3 字級與間距

像素字只用 12 與 24。

| 級 | 用在 |
| --- | --- |
| 24 | 對話對象的名字、筆記標題。UI-1 先讓現有的標題、時間、檢視名字維持 24，避免這一步又改層級 |
| 12 | 其餘全部。UI-2 把時間降回 12，24 只留在對話名字與筆記標題 |

間距以 4px 為一格：控件內 4 或 8，相關控制項之間 8，面板內距 12，區塊之間 16，離視窗邊 16。座標保持 4 的倍數。

## 3. 畫面配置

資訊層級：對話框、筆記、需求一直能讀到。時間與連線在一條細的頂欄。日誌預設收起。檢視卡不再獨立浮著，點過的居民需求放進對話框標題列（UI-2 才搬）。玩法與快捷鍵不變。

右側抽屜同時只開一個。N 開筆記時關掉日誌；開日誌時關掉筆記。避免兩塊面板同時壓住地圖。

```
1280×720

0                                                                        1279
+----------------------------------------------------------------------------+
| Day 1  08:00            ● 已連線                                  [聲音] |  y 0–40
|                                                                            |
|              +----------------------------------+                           |
|              | 鎮民大會（平常不畫）              |     地圖                  |
|              | 人選、動機、倒數、狀態            |     正中 440×360          |
|              | [確認] 或揭曉與 [下一局]          |     x 420–860 y 180–540   |
|              +----------------------------------+                           |
|                                                                            |
|                                              +--------------------------+  |
|                                              | 筆記                  N  |  |  預設不畫
|                                              | 句子              [出示] |  |  打開：x 904–1264
|                                              +--------------------------+  |           y 48–440
|                                                                            |
| +----------------------------------------------------------+    [日誌]   |
| | Mina                                          飢 70 體 80 |               |  y 496–640
| | Mina對你說：……                                              |               |  x 16–864
| | Mina想了想···                                               |               |
| | [跟 Mina 說…________________________________] [送出]       |               |
| +----------------------------------------------------------+               |
| 飢餓 70   體力 80   社交 65              [1] [2] [3] [4]                  |  y 648–712
+----------------------------------------------------------------------------+
```

日誌打開時佔 x 944–1264、y 48–328，筆記先收起。對話框右緣停在 864，跟抽屜左緣 904 隔 40px。底部需求列與對話框隔 8px。

指認面板只在大會與揭曉時畫在正中，蓋住地圖，不蓋住頂欄與底部需求列。打開的當下，對話框（含那一行輸入）、筆記、日誌先收起；面板關掉之後，這三塊回到打開前的樣子。

| 區塊 | 預設 | 快捷鍵 |
| --- | --- | --- |
| 頂欄：日、時間、連線、靜音 | 顯示 | 無。靜音仍是按鈕 |
| 對話框 | 顯示。沒有對象時，占位句維持「點一位居民，再打字」 | Enter 送出。不另外綁鍵 |
| 需求與快捷欄 | 顯示 | 1–3、4、E、G、Q，與現在相同 |
| 筆記 | 收起 | N。再按 N 收起 |
| 日誌 | 收起。按鈕寫「日誌」 | 按鈕。不新佔字母鍵，避免跟移動衝突 |
| 指認與揭曉 | 隱藏。只在大會與揭曉畫在正中 | 無。面板上的「確認」與「下一局」 |
| 檢視卡 | UI-2 起不再單獨存在 | 點居民仍會把對話框焦點給他，並在標題列顯示他的三項需求 |
| 操作提示 | 縮成頂欄放不下的那句，改到對話框占位與筆記標題 | 提示補上「N 筆記」 |
| commit | 前後端一致時不畫。不一致時頂欄用 `accent` 顯示短 hash | 無 |
| F3、滾輪、空白鍵、左鍵點地 | 維持 | 同現在。F3 不寫進玩家提示 |

960×540 不另做排版。`keep` 會把這張 1280 的圖等比縮到 0.75。面板在 1280 的座標上就互不重疊，縮小之後仍然不重疊。不改 stretch mode，web export 的畫布行為維持現狀。

## 4. 分階段

每個 PR 從 `main` 開分支，合進 `main` 之後再切下一個，不疊 PR。不開後端 PR，不碰 `feat/mystery-pr4`（#39）。不新增字型、圖、音效。

每個 PR 結束時跑與 CI 相同的 headless web export：

```bash
cd game
godot --headless --import --quit
godot --headless --export-release "Web" build/web/index.html
```

回報 `index.pck` 相對 `main` 的大小變化。Godot 的 CI 只檢查能匯出，下面每一段都附「請你在遊戲裡看」。

### UI-1 theme 系統

建立第 2.1 節的 `game_theme.tres`。右欄、檢視卡、對話框、筆記、底部列都坐 `panel_bg.png`。`panel.png` 只給選中的快捷格。按鈕字是 `ink`。

另外三件不算重排：事件日誌預設收起，標題列可點；底部列的右緣用 anchor 停在右欄左邊 16px，操作提示改成兩行；Inspect 開著時按 N，Inspect 先收起。滑過地點時隱藏那一枚常駐地名。地名表只留 `place_names.gd` 一份。

驗收：

- `hud.gd`、`world.gd` 沒有 `Color(`、`add_theme_color_override`、`add_theme_stylebox_override`。`hud.tscn` 沒有 `theme_override_colors`、`theme_override_styles`、StyleBox 子資源。
- 第 2.1 節每一組對比至少 4.5:1。
- 滑過任一地點，畫面上只有一枚地名。
- 日誌預設看不見。底部列不伸進右欄。Inspect 與筆記不同時疊在左上角。
- headless export 成功。

請你在遊戲裡看：

- 右側那欄的字可以讀完，不再浮在亮橙上。
- 滑過 Rin 的家，地名只有一枚；其他房子也一樣。
- 點居民、打一句、按 N，對話框與筆記還在原來的位置，只是顏色跟右欄同一套深色。
- 視窗拉到 960×540，這些面板仍分開，沒有叠在一起。

### UI-2 主畫面重排

依第 3 節把時間、連線收到頂欄。需求改成「飢餓／體力／社交」，低於 30 用 `need_low`。UI-1 已經把日誌收起、底部列讓開右欄；這一階段補分類，並把 commit 只留在前後端不一致時。`Agents: N` 從主畫面拿掉。

日誌分類，預設只留玩家用得上的：

| 分類 | 事件 | 預設 |
| --- | --- | --- |
| 談話 | `said`、`thought`、`conversing` | 打開就看得到。心聲用 `text_dim`，仍然沒有「對你說」 |
| 物品 | `ate`、`gave`、`picked_up` | 打開就看得到 |
| 移動 | `left`、`entered`、`activity` | 要再點「移動」才展開 |
| 不進日誌 | `produced`、`conversing_ended` | 維持現在的客戶端過濾 |

檢視卡的三項需求改畫在對話框標題列，獨立的 `Inspect` 隱藏。靜音鍵只留在頂欄。右側 360px 常駐欄拿掉，地圖用全寬。日誌與筆記是右側抽屜，同時只開一個，底都是 `panel_bg.png`。底部列高度跟內容，不預留空底。沒有對話對象時，只留一行輸入框，不畫整塊對話底。移動分類不記狀態，重開頁面回到收起。

驗收：

- 1280 與縮放後的 960×540，頂欄、對話框、快捷欄、打開的筆記、打開的日誌兩兩不相交。
- 公園連續使用澆水壺，日誌不會被「做出木材」填滿；走路訊息要點開「移動」才出現。
- 需求低於 30 時，底部那一行是 `warning`，不必再打開檢視卡。

請你在遊戲裡看：

- 進來先看到時間、自己的三項需求、對話框，地圖中間是空的。
- 按「日誌」才看到事件；不按時，右側沒有那條 360px 的欄。
- 點一位居民，他的飢餓、體力、社交出現在對話框標題，左上角不再多一塊卡片。

### UI-3 對話框與筆記

兩者改吃 UI-1 的主題，位置用第 3 節。等待列維持「{名字}想了想」與三拍省略號，這一行不加「對你說」。回覆列維持「{名字}對你說」。

公開泡泡改用 theme 的 `Bubble`：直角、淺底、`ink` 字，跟深色私下框並排時分得出來。頭上的 `fx.chat` 維持現況，不新增圖。

「出示」仍只用現有的 `note_ids` 與對方在不在面前。可按是橘色 `button.png`，不可按是灰底 `slot.png`。`fact_id` 是空的那列不畫按鈕。筆記標題列：人在面前寫「可向 X 出示」，否則寫「走到對方面前才能出示」。等待時輸入框停用，回覆到了再恢復並聚焦。日誌裡的公開 `said` 用 `text_dim` 加「（公開）」；對話框的「對你說」維持 `text`。新寫進筆記的那一列用 `accent` 閃 0.4 秒。

`mood` 有送到 `dialogue_result`，這一階段仍不畫。`lying` 寫上畫面會直接告訴玩家這句是謊。

驗收：

- 私下句只在對話框，帶「對你說」。公開句只在頭上泡泡與日誌，沒有「對你說」。
- 等待中的第二句仍取代還沒開始的那則，畫面不把 `superseded` 畫成紅色失敗。
- 空 id 的筆記列沒有「出示」。沒點人時，有 id 的列寫「先點居民」。

請你在遊戲裡看：

- 點 Mina 打一句。對話框先是「Mina想了想」與跳動的省略號，然後換成帶「對你說」的深色回覆。
- 居民頭上的公開泡泡是淺底直角，沒有「對你說」。
- 筆記裡，公告那條可以出示；對質之後多出來、沒有 id 的那條沒有按鈕。

### UI-4 回饋與打磨

不新增素材。抽屜與對話框的 tween 是 0.15 秒。筆記新列的閃光是 0.4 秒，低需求數字每秒脈衝一次。時長寫在 `hud.gd` 頂端。

| 動作 | 回饋 | 聲音（都是現成的） |
| --- | --- | --- |
| 按鈕 hover | theme 的 hover StyleBox，`button.png` modulate 1.15 | 無 |
| 按鈕 pressed | theme 的 pressed StyleBox，下移 1px | 現有的點擊聲 |
| 筆記開合、日誌開合、對話框出現 | 透明度 0.15 秒，不彈跳 | 點擊聲 |
| 撿起、吃、給予 | 維持現在的跳躍與浮動字 | `picked_up` / `ate` / `gave` 已有 |
| 鍵盤送出對話 | 送出時播放點擊聲 | 現有的 `click.wav` |
| 筆記筆數變多 | 筆記按鈕上的數字跳一下 | 沿用現在的給予聲 |
| 撿取、給予、送麵包成功 | 底部列短提示。送麵包看 `intent_result` 成功帶來的 `gave` 事件，不畫信任數字 | 現有的 `pickup.wav` / `give.wav` |

驗收：不新增檔案。hover 與 pressed 看得出來。拾取與給予仍有原本的聲音與浮動字。

請你在遊戲裡看：

- 滑過「送出」與「出示」，按鈕會亮一點；按下時下移一格。
- 按 N，筆記在 0.15 秒內淡入，再按一次淡出。日誌也一樣。
- 撿麵包、把麵包給人，仍有聲音與頭上的字。畫面沒有出現「信任 +15」這類伺服器沒送的數字。

### UI-5 指認與揭曉

#39 已經把大會、指認、揭曉與下一局合進 main。這一階段只改畫面，不改後端行為、不改 schema、不加圖。

面板維持正中 440×360（x 420–860、y 180–540），底是 `Panel` 的 `panel_bg.png`。正文、倒數、狀態列用 theme 的 `RichTextLabel` / `Label`，字是 `text`。人選與動機是 `OptionButton`：收合時是橘色 `button.png`、字 `ink`；展開的 `PopupMenu` 坐 `panel_bg.png`、字 `text`，滑過那一列是 `accent` 底、字 `ink`。停用時跟其他按鈕一樣，灰底 `slot.png`、字仍是 `ink`。「確認」與「下一局」是現有的 `Button`。

開關用 `_MOTION_SEC`（0.15 秒）淡入淡出，不彈跳。面板出現時，對話框、那一行輸入、筆記、日誌收起；這段時間 N 與「日誌」不再把它們打開。面板關掉之後，這三塊回到剛才的開合，輸入列回到原位。

驗收：

- `hud.gd` 全檔沒有 `Color(`，也沒有 `add_theme_color_override`、`add_theme_stylebox_override`。
- 指錯仍然會揭曉。分數與正文用伺服器送來的欄位，客戶端不算分。
- 「下一局」之後時鐘是下一天 08:00，筆記是空的。這是 #39 的行為，畫面只跟著隱藏面板。

請你在遊戲裡看：

- 把時鐘調快，走到 18:00。正中出現深色面板，人選與動機的字讀得清楚；展開下拉，名單也是深底亮字。
- 對話框、筆記、日誌在面板開著時都不見；關掉之後，剛才開著的那一塊回來。
- 選一個錯的人再按「確認」，仍會進入揭曉，看得到分數與「下一局」。
- 按「下一局」，時間變成 Day 2  08:00。按 N，筆記是空的。

## 5. 不屬於 UI、這次不動

- 信任是伺服器上的整數（`TRUST_START` 20，給麵包 +15）。`schemas.py` 的 `Agent`、`world_snapshot`、`agent_update`、`dialogue_result` 都沒有信任欄位。UI 不能畫信任條，也不在這四個 PR 裡加欄位。
- 線上有一則 `{"type":"notebook","notes","note_ids","notice"}`，由 `player_talk.push_notebooks` 送出，客戶端已經在收。`schemas.py` 沒有對應的 model。三個欄位跟 `world_snapshot` 裡同名的欄位一樣。UI PR 繼續顯示它們，不補 schema、不加新欄位。
- `dialogue_result.mood` 已存在（`calm` / `wary` / `upset` / `lying` / `hungry`）。畫面刻意不顯示，避免把說謊標出來。飢餓已經能從 `needs.hunger` 與 `fx.hungry` 看到。
- 鎮民大會的規則、分數與 schema 在 PR #39，已經合進 main。畫面在 UI-5，不在這四個 PR 裡重做玩法。
- 需求變紅的門檻 30 與後端 `NEED_HUNGRY` 是同一個數，客戶端目前寫死。這次只把顏色搬進 theme，不改門檻、不改協定。
