# 部署

staging 的對外網址是 https://bitown.aicanhelp.app。HTTPS 由 Cloudflare Tunnel 終止。應用只聽在主機的 `127.0.0.1:8100`，不對公網開 80 或 443。

合併到 `main` 且 CI 成功之後，`.github/workflows/deploy-staging.yml` 會經 Tailscale SSH 到主機，在 `/srv/bi_town` 對齊 `origin/main`，再執行 `docker compose --profile tunnel up -d --build`。

## 密鑰放哪裡

| 項目 | 位置 |
| --- | --- |
| `TS_OAUTH_CLIENT_ID`、`TS_OAUTH_SECRET`、`STAGING_HOST`、`STAGING_USER`、`STAGING_SSH_KEY` | GitHub environment `staging` |
| `TUNNEL_TOKEN`、`POSTGRES_PASSWORD` | 主機上的 `deploy/.env`（由 `deploy/.env.example` 複製） |
| `GIT_COMMIT`、`DEPLOYED_AT` | 部署當下由 workflow 注入的建置參數，不是密鑰 |

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

`git_commit` 應等於剛才的 `GIT_COMMIT`，`deployed_at` 不應是 `unknown`。瀏覽器開啟 https://bitown.aicanhelp.app ，右側應看到專案名稱、縮短的 commit 與部署時間。

## 正常發布

1. 功能分支開 PR 到 `main`。
2. CI 跑後端測試、ruff、backend image build、compose 設定檢查、Godot web export。
3. 合併後 CI 在 `main` 再跑一次。成功才會觸發 Deploy staging。
4. workflow 失敗時，主機停留在上一次成功建出來的容器。

## 回滾

優先在 GitHub 上 revert 造成問題的合併，讓 CI 與 Deploy staging 再跑一輪。這樣主機上的 `main` 與線上映像一致。

緊急情況、CD 本身起不來時，可在主機上暫時建回舊 commit。下一次成功的 Deploy staging 會再次 `git reset --hard origin/main`，所以這只是暫時手段；要留住舊版，仍須讓 `main` 回到那個 commit。

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
