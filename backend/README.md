# 本機開啟 LLM 居民

這是主機上的開發程序，不經過 Docker，也不要改 `deploy/` 或正式站的 8100。

預設 `BRAIN_MODE` 是 `rules`。要在畫面上看到 Mina、Alex、Rin，在啟動 uvicorn 之前設成 `llm`。Ollama 要已在這台機器聽 `127.0.0.1:11434`。`STATIC_WEB_DIR` 指到已經 export 好的 Godot web 目錄，這樣這個 process 才會同時提供遊戲與 `/ws`。

綁 Tailscale 位址，不要綁正式站用的 port：

```bash
cd /home/torscusero/Projects/BI_Town/backend
source .venv/bin/activate
BRAIN_MODE=llm \
OLLAMA_URL=http://127.0.0.1:11434 \
LLM_MODEL=qwen3:14b \
LLM_TIMEOUT=60 \
STATIC_WEB_DIR=/srv/bi_town/game/build/web \
uvicorn app.main:app --host 100.76.54.51 --port 8200
```

`OLLAMA_URL`、`LLM_MODEL`、`LLM_TIMEOUT` 的預設就是上面這三個值。模型呼叫是 async，同時最多一個請求，其餘排隊。`tick()` 不會等模型回來。

瀏覽器開 `http://100.76.54.51:8200/`。正式站 https://bitown.aicanhelp.app 仍是 `rules`，除非另一次部署明確改環境變數；這份說明不包含那個改動。
