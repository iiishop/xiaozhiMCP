# Xiaozhi MCP Router + Exa Component

This project provides:

- A local MCP server (`app_server.py`) with extensible components.
- An Exa search component (`components/exa.py`).
- A router (`mcp_router.py`) that bridges Xiaozhi MCP endpoint (WebSocket) and local MCP stdio server.

## 1) Install dependencies

```bash
uv sync
```

## 2) Configure endpoint and keys (recommended: config file)

Create `config.toml` from the example:

```bash
cp config.example.toml config.toml
```

Edit `config.toml`:

```toml
[xiaozhi]
endpoint = "wss://api.xiaozhi.me/mcp/?token=..."
server_script = "app_server.py"

[exa]
api_key = "your_exa_api_key"
base_url = "https://api.exa.ai"

[schedule]
db_path = ""
```

If `schedule.db_path` is empty, local schedules are stored in `components/local_schedule.sqlite3`.

## 3) Start router

```bash
uv run start --config config.toml
```

The router will start local server with the same config file.

Alternative:

```bash
uv run python mcp_router.py --config config.toml
```

## Optional: environment variables fallback

Linux/macOS:

```bash
export MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=..."
export EXA_API_KEY="your_exa_api_key"
```

PowerShell:

```powershell
$env:MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=..."
$env:EXA_API_KEY="your_exa_api_key"
```

Use this only if you do not want config files.

## Tool exposed to model

- `exa_web_search(...)` with key parameters:
  - `keywords`
  - `num_results` (1-100)
  - `search_type` (`auto|fast|instant|deep-lite|deep|deep-reasoning`)
  - `content_mode` (`highlights|text|summary`)
  - `max_characters`
  - `max_age_hours` (optional)
  - `include_domains_csv` / `exclude_domains_csv`
  - `category`
  - `summary_query`
  - `output_schema_json` (optional JSON string)
  - `system_prompt`

It returns compact JSON to fit Xiaozhi payload constraints.

- `schedule_list_events(start_time: str = "", end_time: str = "")`
- `schedule_add_event(title: str, schedule_type: str = "range", start_time: str = "", end_time: str = "", due_time: str = "", status: str = "未开始", description: str = "")`
- `schedule_update_event(event_id: int, title: str = "", schedule_type: str = "", start_time: str = "", end_time: str = "", due_time: str = "")`
- `schedule_update_status(event_id: int, status: str)`
- `schedule_delete_event(event_id: int)`
- `schedule_find_free_slots(range_start: str, range_end: str, min_minutes: int = 30)`

Schedule types:

- `range`: for planned tasks with start/end (e.g. 2026-06-24 09:30 to 2026-06-25 08:00)
- `deadline`: for point-in-time items (e.g. DDL at 2026-06-24 05:20:49)

Status values:

- `未开始`
- `进行中`
- `已完成`

## Extend with more components

1. Add a new file under `components/`, implement `MCPComponent.register`.
2. Register it in `app_server.py`.

## Notes

- Use clear tool names and parameter names so the model can infer tool usage.
- Use logger instead of `print` for debug output.
- Keep tool return payload short.
