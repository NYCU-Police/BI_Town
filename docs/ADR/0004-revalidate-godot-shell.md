# Godot 殼檔用 no-cache 與 ETag，不讓邊緣留舊版

## 狀態

接受（2026-09-24）

## 背景

Web export 的檔名固定是 `index.html`、`index.js`、`index.wasm`、`index.pck`。Cloudflare 若把它們當成可長期快取的靜態檔，瀏覽器會一直拿到上一次部署的程式。

## 決定

這四個檔、網站根路徑 `/`，以及 `/build_info.json`，回應 `Cache-Control: no-cache`。Starlette 的 `FileResponse` 另帶 `ETag`；`If-None-Match` 對上時回 304。

`/api/health` 維持 `Cache-Control: no-store`，因為那是這次部署的身分，不應被再驗證後繼續使用舊 JSON。

## 後果

- 快取可以保存位元組，但使用前必須問來源。Cloudflare 在 Origin Cache Control 開啟時會標成 `REVALIDATED` 或 `EXPIRED`，不會在沒問來源時端出舊檔。該設定關閉時則是 `BYPASS`。
- 若有 Cache Rule 忽略 origin 的 `Cache-Control` 並自訂 Edge TTL，這條決定失效。這些路徑不能套那種規則。
- 本機測試只證明來源標頭與 304。邊緣的 `cf-cache-status` 要在部署後用 `curl -sI` 看。
