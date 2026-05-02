from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from ..base import MCPComponent

logger = logging.getLogger("exa_component")

ALLOWED_SEARCH_TYPES = {
    "auto",
    "fast",
    "instant",
    "deep-lite",
    "deep",
    "deep-reasoning",
}
ALLOWED_CONTENT_MODES = {"highlights", "text", "summary"}


def _trim_text(text: str, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _split_csv(csv_text: str) -> list[str]:
    if not csv_text:
        return []
    return [item.strip() for item in csv_text.split(",") if item.strip()]


def _normalize_search_type(search_type: str) -> str:
    value = (search_type or "auto").strip().lower()
    if value in ALLOWED_SEARCH_TYPES:
        return value
    return "auto"


def _normalize_content_mode(content_mode: str) -> str:
    value = (content_mode or "highlights").strip().lower()
    if value in ALLOWED_CONTENT_MODES:
        return value
    return "highlights"


def build_search_payload(
    *,
    keywords: str,
    num_results: int,
    search_type: str,
    content_mode: str,
    max_characters: int,
    max_age_hours: int | None,
    include_domains_csv: str,
    exclude_domains_csv: str,
    category: str,
    system_prompt: str,
    output_schema_json: str,
    summary_query: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": keywords,
        "type": _normalize_search_type(search_type),
        "numResults": max(1, min(int(num_results), 100)),
        "contents": {},
    }

    contents: dict[str, Any] = payload["contents"]
    mode = _normalize_content_mode(content_mode)
    chars = max(300, min(int(max_characters), 12000))

    if mode == "highlights":
        highlights_data: dict[str, Any] = {"maxCharacters": chars}
        if summary_query.strip():
            highlights_data["query"] = summary_query.strip()
        contents["highlights"] = highlights_data
    elif mode == "text":
        contents["text"] = {
            "maxCharacters": chars,
            "verbosity": "compact",
        }
    else:
        if summary_query.strip():
            contents["summary"] = {"query": summary_query.strip()}
        else:
            contents["summary"] = True

    if max_age_hours is not None:
        contents["maxAgeHours"] = int(max_age_hours)

    include_domains = _split_csv(include_domains_csv)
    if include_domains:
        payload["includeDomains"] = include_domains

    exclude_domains = _split_csv(exclude_domains_csv)
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains

    if category.strip():
        payload["category"] = category.strip()

    if system_prompt.strip():
        payload["systemPrompt"] = system_prompt.strip()

    if output_schema_json.strip():
        payload["outputSchema"] = json.loads(output_schema_json)

    return payload


def _extract_snippet(row: dict[str, Any], mode: str) -> str:
    if mode == "highlights":
        highlights = row.get("highlights")
        if isinstance(highlights, list) and highlights:
            return str(highlights[0])
    if mode == "summary":
        summary = row.get("summary")
        if isinstance(summary, str) and summary:
            return summary
    return str(row.get("text", "") or row.get("snippet", ""))


class ExaSearchComponent(MCPComponent):
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or os.getenv("EXA_API_KEY", "")
        self.base_url = (base_url or os.getenv("EXA_BASE_URL", "https://api.exa.ai")).rstrip("/")

    def register(self, mcp: Any) -> None:
        @mcp.tool()
        def exa_web_search(
            keywords: str,
            num_results: int = 5,
            search_type: str = "auto",
            content_mode: str = "highlights",
            max_characters: int = 1400,
            max_age_hours: int | None = None,
            include_domains_csv: str = "",
            exclude_domains_csv: str = "",
            category: str = "",
            summary_query: str = "",
            output_schema_json: str = "",
            system_prompt: str = "",
        ) -> dict:
            """
            Use this tool when the assistant needs real-time web information.
            keywords should be concise search terms.
            search_type supports auto/fast/instant/deep-lite/deep/deep-reasoning.
            content_mode supports highlights/text/summary.
            """
            if not self.api_key:
                return {
                    "success": False,
                    "error": "EXA_API_KEY is missing. Set env var EXA_API_KEY first.",
                }

            try:
                payload = build_search_payload(
                    keywords=keywords,
                    num_results=num_results,
                    search_type=search_type,
                    content_mode=content_mode,
                    max_characters=max_characters,
                    max_age_hours=max_age_hours,
                    include_domains_csv=include_domains_csv,
                    exclude_domains_csv=exclude_domains_csv,
                    category=category,
                    system_prompt=system_prompt,
                    output_schema_json=output_schema_json,
                    summary_query=summary_query,
                )
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": f"Invalid search parameters: {exc}"}

            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
            }

            try:
                resp = requests.post(
                    f"{self.base_url}/search",
                    json=payload,
                    headers=headers,
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()

                mode = _normalize_content_mode(content_mode)
                rows = data.get("results", [])[:5]
                output_rows = []
                for row in rows:
                    snippet = _extract_snippet(row, mode)
                    output_rows.append(
                        {
                            "title": _trim_text(row.get("title", ""), 120),
                            "url": row.get("url", ""),
                            "publishedDate": row.get("publishedDate", ""),
                            "snippet": _trim_text(snippet, 220),
                        }
                    )

                output: dict[str, Any] = {
                    "success": True,
                    "query": keywords,
                    "searchType": data.get("searchType", payload.get("type", "auto")),
                    "count": len(output_rows),
                    "results": output_rows,
                }

                if "output" in data:
                    output["output"] = data["output"]

                raw = json.dumps(output, ensure_ascii=False)
                if len(raw.encode("utf-8")) > 1000:
                    output["results"] = output_rows[:3]
                    for item in output["results"]:
                        item["snippet"] = _trim_text(item.get("snippet", ""), 120)
                    if "output" in output:
                        output["output"] = {
                            "content": _trim_text(json.dumps(output["output"].get("content", ""), ensure_ascii=False), 220)
                        }

                logger.info("exa_web_search called, keywords=%s, type=%s", keywords, payload.get("type", "auto"))
                return output
            except Exception as exc:  # noqa: BLE001
                logger.exception("exa_web_search failed")
                return {"success": False, "error": str(exc)}

    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "exa_web_search",
                "description": "Search web with Exa. Supports search type and content mode.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "keywords": {"type": "string"},
                        "num_results": {"type": "integer"},
                        "search_type": {"type": "string"},
                        "content_mode": {"type": "string"},
                    },
                    "required": ["keywords"],
                },
            }
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if tool_name != "exa_web_search":
            raise RuntimeError(f"unknown tool: {tool_name}")

        # Reuse the same logic as MCP tool implementation by calling HTTP workflow directly.
        keywords = str(arguments.get("keywords", ""))
        num_results = int(arguments.get("num_results", 5))
        search_type = str(arguments.get("search_type", "auto"))
        content_mode = str(arguments.get("content_mode", "highlights"))
        max_characters = int(arguments.get("max_characters", 1400))
        max_age_hours = arguments.get("max_age_hours")
        include_domains_csv = str(arguments.get("include_domains_csv", ""))
        exclude_domains_csv = str(arguments.get("exclude_domains_csv", ""))
        category = str(arguments.get("category", ""))
        summary_query = str(arguments.get("summary_query", ""))
        output_schema_json = str(arguments.get("output_schema_json", ""))
        system_prompt = str(arguments.get("system_prompt", ""))

        if not self.api_key:
            return {"success": False, "error": "EXA_API_KEY is missing. Set env var EXA_API_KEY first."}

        try:
            payload = build_search_payload(
                keywords=keywords,
                num_results=num_results,
                search_type=search_type,
                content_mode=content_mode,
                max_characters=max_characters,
                max_age_hours=max_age_hours,
                include_domains_csv=include_domains_csv,
                exclude_domains_csv=exclude_domains_csv,
                category=category,
                system_prompt=system_prompt,
                output_schema_json=output_schema_json,
                summary_query=summary_query,
            )
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Invalid search parameters: {exc}"}

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/search",
                json=payload,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            mode = _normalize_content_mode(content_mode)
            rows = data.get("results", [])[:5]
            output_rows = []
            for row in rows:
                snippet = _extract_snippet(row, mode)
                output_rows.append(
                    {
                        "title": _trim_text(row.get("title", ""), 120),
                        "url": row.get("url", ""),
                        "publishedDate": row.get("publishedDate", ""),
                        "snippet": _trim_text(snippet, 220),
                    }
                )
            output: dict[str, Any] = {
                "success": True,
                "query": keywords,
                "searchType": data.get("searchType", payload.get("type", "auto")),
                "count": len(output_rows),
                "results": output_rows,
            }
            return output
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}


def build_component(config: dict[str, Any] | None = None) -> ExaSearchComponent:
    section = config or {}
    return ExaSearchComponent(
        api_key=str(section.get("api_key", "")) if isinstance(section, dict) else None,
        base_url=str(section.get("base_url", "")) if isinstance(section, dict) else None,
    )
