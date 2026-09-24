# 沿用 Godot、FastAPI 與 Cloudflare Tunnel

## 狀態

接受（2026-09-24）

## 背景

階段 0 的草稿曾建議改成 React + Vite + PixiJS、Fastify、pnpm monorepo，並用 Caddy 在自有網域上做 HTTPS。當時倉庫已有可部署的 v0.1：Godot 4.7 只負責畫面，FastAPI 是世界狀態的唯一來源，staging 經 Tailscale SSH 部署，對外由 Cloudflare Tunnel 提供 https://bitown.aicanhelp.app。

## 決定

階段 0 不更換執行環境。補上的是部署身分（git commit、部署時間）、部署文件與上線後的健康檢查，既有客戶端、後端與隧道維持不變。

Gobot 沒有具體要借鑒的行為，因此不納入這個階段。

## 後果

- 合併到 `main` 之後，仍走現有 CI，再由 Deploy staging 在主機上建置並重啟。
- 不引入容器 registry、Caddy，也不把 80/443 開到這台機器上。
- 之後若要換渲染器或網域，另開一則 ADR，不在這個決定裡隱含。
