# BI_Town

## Overview

BI_Town (Behavioral Intelligence Town) 是一個 AI-native social simulation。
後端（FastAPI）是 world state 的唯一來源；Godot 之後只負責畫面。

目前是 **v0.1**：只建立 pipeline 骨架，不含 LLM 或 AI agent。

部署與回滾見 [docs/DEPLOY.md](docs/DEPLOY.md)。`GET /api/health` 回傳版本、git commit 與部署時間。

## Local Development

需求：Python 3.12，以及 uv 0.12.21（`backend/pyproject.toml` 的 `required-version`）。

```bash
cd backend
uv sync --frozen
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

執行測試：

```bash
cd backend
uv run pytest
uv run ruff check .
```
