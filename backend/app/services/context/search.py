"""General web search for the assistant (opening hours changes, events, local tips).

With TAVILY_API_KEY set it uses Tavily, a search API made for AI agents (free tier: 1,000 searches a month;
https://tavily.com). Without a key it falls back to Google News RSS, which covers current events but not the
wider web. Results are untrusted text: the assistant quotes and links them, it never follows instructions in them.
"""
from __future__ import annotations

import httpx
from flask import current_app

from app.services.cache import cache_get, cache_set
from app.services.context import news


def web_search(query: str, *, lang: str = "en", country: str = "US", max_results: int = 5) -> dict:
    key = current_app.config.get("TAVILY_API_KEY")
    cache_key = {"q": query, "k": bool(key)}
    cached = cache_get("websearch", cache_key)
    if cached is not None:
        return cached
    if key:
        try:
            resp = httpx.post("https://api.tavily.com/search", timeout=20, headers={"Authorization": f"Bearer {key}"},
                              json={"query": query, "max_results": max_results, "search_depth": "basic", "include_answer": True})
            resp.raise_for_status()
            data = resp.json()
            out = {"available": True, "source": "Tavily", "answer": data.get("answer"),
                   "results": [{"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("content") or "")[:500]}
                               for r in data.get("results", [])[:max_results]]}
            cache_set("websearch", cache_key, out, ttl_hours=6)
            return out
        except (httpx.HTTPError, ValueError) as exc:
            current_app.logger.warning("web search: tavily failed: %s", exc)
    if not current_app.config.get("NEWS_ENABLED"):
        return {"available": False, "reason": "no_search_provider", "results": []}
    try:
        items = news._google_news(query, lang, country)[:max_results]
    except Exception as exc:  # noqa: BLE001 - the fallback is best effort
        current_app.logger.warning("web search: news fallback failed: %s", exc)
        return {"available": False, "reason": "unavailable", "results": []}
    out = {"available": True, "source": "Google News (no web search key set)", "answer": None,
           "results": [{"title": i["title"], "url": i["url"], "snippet": i["source"]} for i in items]}
    cache_set("websearch", cache_key, out, ttl_hours=1)
    return out
