# 本機開啟 LLM 居民

這是在部署主機上直接跑 uvicorn 的開發程序，不經過 Docker，也不佔正式站的 8100。正式站要開 LLM，改主機 `deploy/.env` 後重新部署，見 [docs/DEPLOY.md](../docs/DEPLOY.md)。

預設 `BRAIN_MODE` 是 `rules`。要在畫面上看到 Mina、Alex、Rin，在啟動 uvicorn 之前設成 `llm`。Ollama 要已在這台機器聽 `127.0.0.1:11434`。`STATIC_WEB_DIR` 指到已經 export 好的 Godot web 目錄；部署主機上是 `/srv/bi_town/game/build/web`。

在 repo 的 `backend/` 目錄啟動，綁 Tailscale 位址，不要綁正式站用的 port：

```bash
cd backend
source .venv/bin/activate
BRAIN_MODE=llm \
OLLAMA_URL=http://127.0.0.1:11434 \
LLM_MODEL=qwen3:14b \
LLM_TIMEOUT=60 \
STATIC_WEB_DIR=/srv/bi_town/game/build/web \
uvicorn app.main:app --host 100.76.54.51 --port 8200
```

Godot web 需要安全環境（HTTPS，或瀏覽器認定的 localhost）。這個程序只提供 HTTP，不要在瀏覽器直接開 Tailscale 位址。在自己的電腦上做 SSH 轉發，再從 localhost 開：

```bash
ssh -L 8200:100.76.54.51:8200 <user>@<host>
```

然後開 `http://localhost:8200/`。

`OLLAMA_URL`、`LLM_MODEL`、`LLM_TIMEOUT` 的預設就是上面這三個值。模型呼叫是 async，同時最多一個請求，其餘排隊。`tick()` 不會等模型回來。
