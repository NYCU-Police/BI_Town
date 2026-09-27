# LLM Town POC

獨立腳本，用來觀察三個居民在本地模型下會做出什麼事。它不啟動伺服器模擬迴圈，也不會因為合併而改變 https://bitown.aicanhelp.app 的行為。正式後端映像只複製 `backend/app/`，不會帶上這個目錄。

居民是 Mina、Alex、Rin。地點沿用 `app/simulation/poi.py` 的 home、cafe、office、park。開局第一分鐘、抵達目的地、閒置滿 30 遊戲分鐘，或剛被搭話的下一分鐘，才向模型要一個動作：`move_to`、`stay`、`talk_to`。`talk_to` 的對象必須在同一地點且為 idle，否則改成 `stay`。同一對居民連續對話最多 6 句，之後回到一般規則。每筆記憶以 `[HH:MM]` 開頭。想法與對話要求繁體中文。解析失敗、逾時、HTTP 錯誤或無效對話會改成 `stay` 並寫進劇本，腳本不會因此中止。

遊戲時間快轉，不會 `sleep`。預設從 08:00 跑到 20:00。

## 事前準備

主機上要有已啟動的 [Ollama](https://ollama.com/)，並已拉取模型：

```bash
ollama pull qwen3:14b
```

## 執行

在 `backend/` 目錄：

```bash
export OLLAMA_URL=http://127.0.0.1:11434
export LLM_MODEL=qwen3:14b
export LLM_TIMEOUT=60

python -m poc.llm_town
python -m poc.llm_town --start 08:00 --end 12:00
```

| 環境變數 | 預設 | 意義 |
| --- | --- | --- |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama 服務位址，腳本會 POST `{URL}/api/chat` |
| `LLM_MODEL` | `qwen3:14b` | 模型名稱 |
| `LLM_TIMEOUT` | `60` | 單次請求秒數 |

同一時間只送一個請求。`think` 設為 `false`，避免 qwen3 先做一段推理。

終端機與 `poc_output/<時間戳>.md`（專案根目錄）會同步寫下劇本。該目錄已在 `.gitignore`，不要提交。

## 測試

不需要 Ollama。假回應跑 1 個遊戲小時：

```bash
cd backend
pytest -v tests/test_llm_poc.py
```
