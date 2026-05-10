# MCP 工具参考

本页列出主仓库内置 MCP 工具，以及当前组件目录中常见组件工具。内置工具由 `app_server.py` 注册；组件工具来自 `xiaozhiMCP-components` 仓库，安装并加载后才可用。

## 内置工具总览

server 角色始终注册以下工具：

| 工具 | 说明 |
| --- | --- |
| `catalog_list_components()` | 列出远程组件目录中的组件。 |
| `catalog_search_components(query, fuzzy, readme, platform)` | 搜索组件，支持名称、描述、README 和平台过滤。 |
| `catalog_describe_component(component_name)` | 获取组件摘要、版本、路径、入口和平台信息。 |
| `catalog_get_component_readme(component_name)` | 获取组件 README 原文。 |
| `catalog_get_component_platforms(component_name)` | 获取组件支持平台。 |
| `catalog_install_component_to_server(component_name)` | 把组件安装到 server 组件目录。 |
| `catalog_install_component_to_client(component_name, node_id, mode)` | 要求指定 client 拉取并安装组件。 |
| `logmcp_get_errors(limit)` | 查看 server 侧最近错误记录。 |

开启 `[cluster].enabled=true` 后额外注册：

| 工具 | 说明 |
| --- | --- |
| `cluster_list_clients()` | 列出已连接 client。 |
| `cluster_list_client_tools(node_id)` | 列出指定 client 的工具。 |
| `cluster_list_remote_tools()` | 列出所有远程 client 工具。 |
| `cluster_call_remote_tool(tool_name, arguments_json)` | 调用远程工具。 |

## `catalog_list_components()`

列出组件目录中的所有组件。

调用示例：

```python
catalog_list_components()
```

返回示例：

```json
{
  "success": true,
  "count": 5,
  "components": [
    {
      "name": "exa",
      "description": "Exa web search MCP component with search/content mode controls.",
      "version": "0.1.0",
      "path": "exa",
      "entry": "component.py",
      "readme": "README.md",
      "platforms": ["Windows", "Linux", "MacOs"]
    }
  ]
}
```

## `catalog_search_components(query, fuzzy, readme, platform)`

按名称、描述、README 或平台搜索组件。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `query` | string | `""` | 搜索关键词。为空时返回全部匹配平台的组件。 |
| `fuzzy` | boolean | `true` | `true` 表示包含匹配，`false` 表示组件名精确匹配。 |
| `readme` | boolean | `false` | 名称和描述未命中时，是否继续搜索 README。 |
| `platform` | string | `""` | 可选 `Windows`、`Linux`、`MacOs`，大小写不敏感。 |

调用示例：

```python
catalog_search_components(
    query="schedule",
    fuzzy=True,
    readme=False,
    platform="Windows"
)
```

## `catalog_describe_component(component_name)`

获取组件详细摘要。

调用示例：

```python
catalog_describe_component(component_name="local_schedule")
```

返回包含：

- `name`
- `description`
- `version`
- `path`
- `entry`
- `summary`
- `platforms`
- `platform_valid`
- `platform_warning`

## `catalog_get_component_readme(component_name)`

获取组件 README 内容。适合让小智先阅读组件使用说明再决定是否安装。

调用示例：

```python
catalog_get_component_readme(component_name="exa")
```

返回包含 README 原文、README 路径和平台解析结果。

## `catalog_get_component_platforms(component_name)`

获取组件平台兼容性。优先读取 `index.json` 的 `platforms`，没有时解析 README 最后一行 `Platforms: ...`。

调用示例：

```python
catalog_get_component_platforms(component_name="clipboard")
```

## `catalog_install_component_to_server(component_name)`

安装组件到 server 的组件目录。

调用示例：

```python
catalog_install_component_to_server(component_name="exa")
```

成功返回：

```json
{
  "success": true,
  "name": "exa",
  "installed_to": "components/exa"
}
```

安装后需要重启 server 才能加载新组件。

## `catalog_install_component_to_client(component_name, node_id, mode)`

要求指定 client 拉取并安装组件。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `component_name` | string | 无 | 组件名。 |
| `node_id` | string | 无 | 目标 client 节点 ID。 |
| `mode` | string | `client_pull` | 当前只支持 `client_pull`。 |

调用示例：

```python
catalog_install_component_to_client(
    component_name="clipboard",
    node_id="office-windows-pc",
    mode="client_pull"
)
```

前置条件：

- server 已开启集群。
- 目标 client 在线。
- 目标 client 已注册 `agent_install_component__{node_id}`。
- 目标 client 能访问组件仓库。

## `logmcp_get_errors(limit)`

查看最近错误。适合排查集群注册、工具冲突、未知异常。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `limit` | integer | `50` | 返回最近多少条错误。 |

调用示例：

```python
logmcp_get_errors(limit=20)
```

返回示例：

```json
{
  "success": true,
  "count": 1,
  "errors": [
    {
      "source": "cluster",
      "error_code": "UNAUTHORIZED_CLIENT",
      "message": "unauthorized",
      "conclusion": "Client token mismatch. Ensure client.client_token equals server cluster.client_token."
    }
  ]
}
```

## `cluster_list_clients()`

列出已连接 client。

调用示例：

```python
cluster_list_clients()
```

返回示例：

```json
{
  "success": true,
  "count": 1,
  "clients": [
    {
      "node_id": "office-windows-pc",
      "platform": "windows",
      "tool_count": 4,
      "last_seen": 1710000000
    }
  ]
}
```

## `cluster_list_client_tools(node_id)`

列出指定 client 的工具。

调用示例：

```python
cluster_list_client_tools(node_id="office-windows-pc")
```

如果 client 不存在，返回：

```json
{
  "success": false,
  "error": "client not found: office-windows-pc",
  "node_id": "office-windows-pc"
}
```

## `cluster_list_remote_tools()`

列出所有 client 注册的远程工具。

调用示例：

```python
cluster_list_remote_tools()
```

返回的每个工具包含 `name`、`description`、`node_id` 和 `platform`。

## `cluster_call_remote_tool(tool_name, arguments_json)`

调用远程工具。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `tool_name` | string | 无 | 精确工具名。 |
| `arguments_json` | string | `{}` | JSON object 字符串。 |

调用示例：

```python
cluster_call_remote_tool(
    tool_name="schedule_add_event",
    arguments_json='{"title":"产品评审","schedule_type":"range","start_time":"2026-05-10T14:00:00","end_time":"2026-05-10T15:00:00","status":"未开始","description":"评审新版本"}'
)
```

如果 `arguments_json` 不是 JSON object，会返回：

```json
{
  "success": false,
  "error": "arguments_json must decode to JSON object"
}
```

## 常见组件工具

### `exa`

工具：

```python
exa_web_search(
    keywords,
    num_results,
    search_type,
    content_mode,
    max_characters,
    max_age_hours,
    include_domains_csv,
    exclude_domains_csv,
    category,
    summary_query,
    output_schema_json,
    system_prompt
)
```

用途：调用 Exa 神经搜索。`search_type` 支持 `auto`、`fast`、`instant`、`deep-lite`、`deep`、`deep-reasoning`。`content_mode` 支持 `highlights`、`text`、`summary`。

### `local_schedule`

工具：

```python
schedule_list_events(start_time, end_time)
schedule_add_event(title, schedule_type, start_time, end_time, due_time, status, description)
schedule_update_event(event_id, title, schedule_type, start_time, end_time, due_time)
schedule_update_status(event_id, status)
schedule_delete_event(event_id)
schedule_find_free_slots(range_start, range_end, min_minutes)
```

时间使用 ISO 8601 字符串，例如 `2026-05-10T14:00:00`。状态支持 `未开始`、`进行中`、`已完成`。

### `clipboard`

Windows client 工具：

```python
clipboard_set(content, content_html)
clipboard_get()
```

`content_html` 可用于 CF_HTML 富文本剪贴板内容。

### `windows_manager`

Windows client 工具：

```python
windows_list_open_apps()
windows_find_apps(keyword)
windows_focus_app(keyword, match_index)
windows_close_app(keyword, match_index)
windows_list_app_performance(keyword)
```

用于枚举、查找、聚焦、关闭窗口，以及查看进程 CPU 和工作集内存。

### `apple_music_macos`

macOS client 工具。该组件会自动安装并桥接 `epheterson/mcp-applemusic`，所有上游工具以 `apple_music_` 前缀重新导出。实际工具列表取决于上游版本。

## 返回值约定

建议所有组件工具返回 dict，并包含：

```json
{
  "success": true,
  "data": {}
}
```

失败时包含明确 `error`：

```json
{
  "success": false,
  "error": "explain what happened"
}
```

这样小智可以更容易理解工具执行状态并给出后续建议。
