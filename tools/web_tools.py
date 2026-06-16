"""Lightweight Web Tools for LeadFlow Agent Core.

Provides web_search and web_extract with two backends:
  - Tavily (default): search + extract, requires TAVILY_API_KEY
  - DuckDuckGo (fallback): search only, requires `pip install ddgs`

No plugin system dependency. Self-contained ~200 lines.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

# ── Backend Selection ──────────────────────────────────────────────────────

def _has_env(name: str) -> bool:
    val = os.getenv(name, "").strip()
    return bool(val)


def _get_backend() -> str:
    """Determine which backend to use. Tavily preferred, ddgs fallback."""
    # Explicit config
    try:
        from hermes_cli.config import load_config
        configured = (load_config().get("web", {}) or {}).get("backend", "").strip().lower()
        if configured in ("tavily", "ddgs"):
            return configured
    except Exception:
        pass

    # Auto-detect
    if _has_env("TAVILY_API_KEY"):
        return "tavily"
    try:
        import ddgs  # noqa: F401
        return "ddgs"
    except ImportError:
        pass

    return "tavily"  # default (will fail with clear error if no key)


def check_web_api_key() -> bool:
    """Return True when at least one backend is usable."""
    if _has_env("TAVILY_API_KEY"):
        return True
    try:
        import ddgs  # noqa: F401
        return True
    except ImportError:
        return False


# ── Tavily ─────────────────────────────────────────────────────────────────

def _tavily_search(query: str, limit: int = 5) -> Dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {"success": False, "error": "TAVILY_API_KEY is not set"}

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": min(limit, 20),
                "include_answer": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("Tavily search HTTP error: %s", exc)
        return {"success": False, "error": f"Tavily returned HTTP {exc.response.status_code}"}
    except httpx.RequestError as exc:
        logger.warning("Tavily search request error: %s", exc)
        return {"success": False, "error": f"Could not reach Tavily: {exc}"}

    try:
        data = resp.json()
    except Exception:
        return {"success": False, "error": "Could not parse Tavily response as JSON"}

    raw = data.get("results", []) or []
    web_results = [
        {
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "description": str(r.get("content", ""))[:500],
            "position": i + 1,
        }
        for i, r in enumerate(raw[:limit])
    ]

    logger.info("Tavily search '%s': %d results", query, len(web_results))
    return {"success": True, "data": {"web": web_results}}


def _tavily_extract(urls: List[str]) -> Dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {"success": False, "error": "TAVILY_API_KEY is not set"}

    results = []
    for url in urls[:5]:
        try:
            resp = httpx.post(
                "https://api.tavily.com/extract",
                json={
                    "api_key": api_key,
                    "urls": [url],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_results = data.get("results", []) or []
            for r in raw_results:
                content = str(r.get("raw_content", "") or r.get("content", ""))
                results.append({
                    "url": url,
                    "title": str(r.get("title", "")),
                    "content": content[:5000] if len(content) > 5000 else content,
                    "error": None,
                })
        except Exception as exc:
            logger.warning("Tavily extract error for %s: %s", url, exc)
            results.append({"url": url, "title": "", "content": "", "error": str(exc)[:200]})

    return {"success": True, "data": results}


# ── DuckDuckGo (fallback) ─────────────────────────────────────────────────

def _ddgs_search(query: str, limit: int = 5) -> Dict[str, Any]:
    try:
        from ddgs import DDGS  # type: ignore
    except ImportError:
        return {
            "success": False,
            "error": "ddgs package not installed — run `pip install ddgs`",
        }

    try:
        web_results = []
        with DDGS() as client:
            for i, hit in enumerate(client.text(query, max_results=max(1, int(limit)))):
                if i >= limit:
                    break
                url = str(hit.get("href") or hit.get("url") or "")
                web_results.append({
                    "title": str(hit.get("title", "")),
                    "url": url,
                    "description": str(hit.get("body", "")),
                    "position": i + 1,
                })
    except Exception as exc:
        logger.warning("DDGS search error: %s", exc)
        return {"success": False, "error": f"DuckDuckGo search failed: {exc}"}

    logger.info("DDGS search '%s': %d results", query, len(web_results))
    return {"success": True, "data": {"web": web_results}}


# ── Tool Implementations ──────────────────────────────────────────────────

def web_search_tool(query: str, limit: int = 5) -> str:
    """Search the web using Tavily or DuckDuckGo."""
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 5

    backend = _get_backend()

    if backend == "tavily":
        result = _tavily_search(query, limit)
    elif backend == "ddgs":
        result = _ddgs_search(query, limit)
    else:
        result = {"success": False, "error": f"Unknown backend: {backend}"}

    return json.dumps(result, indent=2, ensure_ascii=False)


async def web_extract_tool(urls: List[str], format: str = "markdown", **kwargs) -> str:
    """Extract content from web pages using Tavily."""
    if not urls or not isinstance(urls, list):
        return json.dumps({"success": False, "error": "urls must be a non-empty list"})

    urls = [u for u in urls[:5] if isinstance(u, str) and u.strip()]
    if not urls:
        return json.dumps({"success": False, "error": "No valid URLs provided"})

    backend = _get_backend()

    if backend == "tavily":
        result = _tavily_extract(urls)
    else:
        # ddgs doesn't support extract — fall back to httpx fetch
        result = _fallback_extract(urls)

    return json.dumps(result, indent=2, ensure_ascii=False)


def _fallback_extract(urls: List[str]) -> Dict[str, Any]:
    """Simple httpx-based content extraction (no JS rendering)."""
    results = []
    for url in urls[:5]:
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "LeadFlow-Agent/1.0"})
            resp.raise_for_status()
            content = resp.text[:5000]
            results.append({
                "url": url,
                "title": "",
                "content": content,
                "error": None,
            })
        except Exception as exc:
            logger.warning("Fallback extract error for %s: %s", url, exc)
            results.append({"url": url, "title": "", "content": "", "error": str(exc)[:200]})

    return {"success": True, "data": results}


# ── Registry ──────────────────────────────────────────────────────────────

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": "Search the web for information. Returns up to 5 results by default with titles, URLs, and descriptions.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web."
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return. Defaults to 5.",
                "minimum": 1,
                "maximum": 100,
                "default": 5
            }
        },
        "required": ["query"]
    }
}

WEB_EXTRACT_SCHEMA = {
    "name": "web_extract",
    "description": "Extract content from web page URLs. Returns page content in markdown format. Max 5 URLs per call. Pages over 5000 chars are truncated.",
    "parameters": {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of URLs to extract content from (max 5 URLs per call)",
                "maxItems": 5
            }
        },
        "required": ["urls"]
    }
}

registry.register(
    name="web_search",
    toolset="web",
    schema=WEB_SEARCH_SCHEMA,
    handler=lambda args, **kw: web_search_tool(args.get("query", ""), limit=args.get("limit", 5)),
    check_fn=check_web_api_key,
    requires_env=["TAVILY_API_KEY"],
    emoji="🔍",
    max_result_size_chars=100_000,
)

registry.register(
    name="web_extract",
    toolset="web",
    schema=WEB_EXTRACT_SCHEMA,
    handler=lambda args, **kw: web_extract_tool(
        args.get("urls", [])[:5] if isinstance(args.get("urls"), list) else [], "markdown"),
    check_fn=check_web_api_key,
    requires_env=["TAVILY_API_KEY"],
    is_async=True,
    emoji="📄",
    max_result_size_chars=100_000,
)
