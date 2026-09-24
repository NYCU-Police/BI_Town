# 部署

staging 的對外網址是 https://bitown.aicanhelp.app。HTTPS 由 Cloudflare Tunnel 終止。應用只聽在主機的 `127.0.0.1:8100`，不對公網開 80 或 443。

合併到 `main` 且該次 push 的 CI 成功之後，`.github/workflows/deploy-staging.yml` 會經 Tailscale SSH 到主機。主機先 `git fetch origin main` 取得物件，再 `git reset --hard` 到觸發這次部署的 CI commit（`workflow_run.head_sha`），不是 `origin/main`。然後執行 `docker compose --profile tunnel up -d --build`。PR 的 CI 不會部署。

## 密鑰放哪裡

| 項目 | 位置 |
| --- | --- |
| `TS_OAUTH_CLIENT_ID`、`TS_OAUTH_SECRET`、`STAGING_HOST`、`STAGING_USER`、`STAGING_SSH_KEY` | GitHub environment `staging` |
| `TUNNEL_TOKEN`、`POSTGRES_PASSWORD` | 主機上的 `deploy/.env`（由 `deploy/.env.example` 複製） |
| `GIT_COMMIT` | 部署當下的映像建置參數，不是密鑰 |
| `DEPLOYED_AT` | 容器建立當下寫入的環境變數，不是密鑰 |

倉庫只提交 `*.env.example`。不要把 `deploy/.env` 或私鑰提交進來。

## 伺服器現況（已在跑的主機不必重做）

下列是這套部署假設主機已經具備的條件。新機器才需要從頭做。

1. 安裝 Docker Engine 與 Compose plugin。
2. 安裝 Tailscale，讓帶 `tag:ci` 的 GitHub Actions runner 能 SSH 進來。SSH 不依賴對公網開放 22。
3. 防火牆不要把 `8100`、`80`、`443` 暴露到公網。應用埠已綁在 `127.0.0.1`。
4. 把這個 repo clone 到 `/srv/bi_town`。
5. `cp deploy/.env.example deploy/.env`，填上 `POSTGRES_PASSWORD` 與 Cloudflare 的 `TUNNEL_TOKEN`。
6. 在 Cloudflare Zero Trust 把該 tunnel 的 public hostname 指到 compose 網路裡的 `http://backend:8000`。`cloudflared` 與 `backend` 在同一個 compose 網路，不要指到容器裡的 `127.0.0.1`。
7. DNS 用這條 tunnel 的 hostname（`bitown.aicanhelp.app`）。不需要再把 A 記錄指到這台機器的公網 IP。

首次手動啟動（之後改由 workflow 部署）：

```bash
cd /srv/bi_town
export GIT_COMMIT="$(git rev-parse HEAD)"
export DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cd deploy
docker compose --profile tunnel up -d --build
curl -fsS http://127.0.0.1:8100/api/health
```

`git_commit` 應等於剛才的 `GIT_COMMIT`，`deployed_at` 不應是 `unknown`。瀏覽器開啟 https://bitown.aicanhelp.app ，右側應看到前端 commit、後端 commit 與部署時間。兩邊 commit 不同時，這三行會變成琥珀色。

## 這次部署比對哪一個 commit

Deploy staging 的 concurrency group 是 `bi-town-staging`，`cancel-in-progress` 為 false：正在跑的那次不會被取消。取消 GitHub job 停不掉主機上已經開始的 `git reset` 與 `docker compose`。排隊中的部署只保留最新一個。連續 merge 時，中間還在排隊、尚未開始的 commit 會被取消，不會單獨部署。

比對用的 SHA 是觸發這次部署的 CI commit（`workflow_run.head_sha`，也就是那次 CI 的 `GITHUB_SHA`）。不是這支 deploy workflow 自己的 `github.sha`，也不是部署後主機上的 `HEAD`。`workflow_run` 裡的 `github.sha` 是 default branch 的尖端，可能已經往前走。

## 靜態檔快取

`/`、`/index.html`、`/index.js`、`/index.wasm`、`/index.pck`、`/build_info.json` 回 `Cache-Control: no-cache`，並帶 Starlette 產生的 `ETag`。條件請求對得上時回 304。

這表示快取可以留著複本，但每次使用前都要向來源確認。Cloudflare 文件（[Cache-Control](https://developers.cloudflare.com/cache/concepts/cache-control/)）寫明：Origin Cache Control 開啟時（Free、Pro、Business 的預設），`no-cache` 會被存下來但每次都重新驗證，不會直接端出過期內容，`cf-cache-status` 是 `REVALIDATED` 或 `EXPIRED`。Origin Cache Control 關閉時（Enterprise 預設），`no-cache` 是不快取（`BYPASS`）。兩種都不會在沒問來源的情況下繼續給舊檔。若有 Cache Rule 把 Edge TTL 設成忽略 origin 的 `Cache-Control`，這個保證會被蓋掉，這些路徑不能套那條規則。

上線後用下面指令確認。第二次不應是帶著遞增 `Age` 的 `HIT`：

```bash
curl -sI https://bitown.aicanhelp.app/index.html
curl -sI https://bitown.aicanhelp.app/index.wasm
curl -sI https://bitown.aicanhelp.app/index.js
curl -sI https://bitown.aicanhelp.app/index.pck
curl -sI https://bitown.aicanhelp.app/build_info.json
```

回應要有 `cache-control: no-cache` 與 `etag`。把那個 `etag` 放進下一次請求應得到 304：

```bash
curl -sI -H 'If-None-Match: "<etag>"' https://bitown.aicanhelp.app/index.wasm
```

本機測試會打同一組標頭與 304，但沒有打到 Cloudflare 邊緣。邊緣行為要等這次部署後用上面的 `curl` 看 `cf-cache-status`。

## 正常發布

1. 功能分支開 PR 到 `main`。
2. CI 跑後端測試、ruff、backend image build、compose 設定檢查、Godot web export。匯出檔不進 git。CI 用 Godot headless 輸出 web，Deploy staging 把該 artifact rsync 到主機的 `game/build/web/`，compose 再掛進 backend。HUD 的改動跟著這次 export 上線。
3. 合併後 CI 在 `main` 再跑一次。成功才會觸發 Deploy staging。
4. workflow 失敗時，主機停留在上一次成功建出來的容器。若部署步驟已跑完、只有後面的檢查失敗，線上可能已經是新版本，但 workflow 仍算失敗。

公開網址檢查（`/api/health` 與 `/build_info.json`）是在部署主機上執行 `curl https://bitown.aicanhelp.app/...`。請求仍經過 Cloudflare 邊緣與 Tunnel，SHA 必須等於觸發這次部署的 CI commit（`workflow_run.head_sha`）。不從 GitHub runner 直接打公開網址：runner 的資料中心 IP 會被 Cloudflare 當成機器人回 403。這不是放寬檢查，也不要為了 runner 去改 Cloudflare 規則。本機 `127.0.0.1` 檢查另外保留。

## 回滾

標準做法：在 `main` 上對造成問題的合併執行 `git revert`，再開 PR 進 `main`。PR 合併後，CI 與 Deploy staging 會把線上環境建回 revert 之後的樹。主機上的 `main` 與 `origin/main` 保持一致。

```bash
git checkout main
git pull
git revert -m 1 <有問題的 merge commit>
# 把這個 revert commit 開 PR 並合併回 main
```

僅限緊急：CD 無法跑、必須先讓站恢復時，才在主機上執行下面的 `git reset --hard`。下一次成功的 Deploy staging 會把主機 reset 到觸發那次 CI 的 commit，所以主機上的 reset 留不住。要讓舊版留下來，仍要走上面的 revert PR。

```bash
cd /srv/bi_town
git fetch origin
git log --oneline -10
git reset --hard <已知良好的 commit>
export GIT_COMMIT="$(git rev-parse HEAD)"
export DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cd deploy
docker compose --profile tunnel up -d --build
curl -fsS http://127.0.0.1:8100/api/health
```

必須帶 `--build`。只 `restart` 不會更新映像裡的 commit。`deploy/.env` 不在 git 裡，`reset --hard` 不會刪掉它。

確認 `/api/health` 的 `git_commit` 是你指定的那個 commit 之後，再開 https://bitown.aicanhelp.app 看畫面上的 commit 是否相同。
