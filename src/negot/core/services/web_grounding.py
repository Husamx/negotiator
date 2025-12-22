"""
Web grounding service using Tavily search.

This service decides when to perform web search and assembles the
results into a structured grounding pack. It implements a simplified
version of the pipeline described in ``docs/WEB_GROUNDING.md``. In
production the functions here should integrate with the Tavily API and
use a language model to synthesise the evidence. For the MVP we rely
on simple heuristics and placeholders.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from httpx import AsyncClient
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings

try:
    from tavily import TavilyClient
except Exception:  # noqa: BLE001
    TavilyClient = None

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=6),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _tavily_search_sync(client: Any, query: str, settings: Any) -> dict:
    return client.search(
        query=query,
        search_depth=settings.tavily_search_depth,
        max_results=settings.tavily_max_results,
        include_answer=False,
        include_raw_content=False,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=6),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def _tavily_search_httpx(client: AsyncClient, query: str, settings: Any) -> dict:
    resp = await client.get(
        "https://api.tavily.com/search",
        params={
            "api_key": settings.tavily_api_key,
            "query": query,
            "depth": settings.tavily_search_depth,
            "max_results": settings.tavily_max_results,
            "include_answer": "false",
            "include_raw_content": "false",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def need_search(context: Dict[str, Any]) -> Dict[str, Any]:
    """Decide whether a web grounding search is required.

    This heuristic looks for keywords in the topic that suggest norms,
    policies or laws might be relevant. A more sophisticated
    implementation would include an LLM classification model.

    :param context: Context dictionary containing at least ``topic_text``.
    :return: A decision dictionary conforming to the schema defined in
        ``docs/WEB_GROUNDING.md``.
    """
    topic = context.get("topic_text", "").lower()
    decision = {
        "need_search": False,
        "reason_codes": [],
        "max_queries": 0,
        "max_sources_per_query": 0,
        "search_depth": "basic",
        "topic": "general",
    }
    triggers = {
        "CULTURE_NORMS": ["custom", "etiquette", "norm", "culture"],
        "POLICY_LAW": ["legal", "policy", "rights", "law", "bill", "tenant"],
        "TIME_SENSITIVE": ["current", "latest", "market", "2025", "2024"],
    }
    for code, keywords in triggers.items():
        if any(kw in topic for kw in keywords):
            decision["need_search"] = True
            decision.setdefault("reason_codes", []).append(code)
    if decision["need_search"]:
        decision["max_queries"] = 2
        decision["max_sources_per_query"] = 5
        decision["search_depth"] = get_settings().tavily_search_depth
    return decision


def plan_queries(context: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    """Plan a set of search queries based on the topic and decision.

    This function splits the topic into keywords and returns one or two
    simple queries. A real implementation would use a planning agent
    that decides on targeted queries and stop conditions.
    """
    if not decision.get("need_search"):
        return {"queries": [], "must_have_evidence": [], "stop_conditions": []}
    topic = context.get("topic_text", "")
    words = [w.strip() for w in topic.split() if len(w) > 3]
    queries = [" ".join(words[:5])]
    if len(words) > 5:
        queries.append(" ".join(words[5:10]))
    return {"queries": queries, "must_have_evidence": [], "stop_conditions": []}


async def run_search(queries: List[str]) -> List[Dict[str, Any]]:
    """Execute Tavily search for the given queries.

    If a Tavily API key is configured, this function will attempt to call
    Tavily's REST endpoint. If no key is present or if the call fails,
    it returns an empty list. Each result is a dictionary with ``url``,
    ``title`` and ``snippet``.
    """
    settings = get_settings()
    if not queries or not settings.tavily_api_key:
        return []
    results: List[Dict[str, Any]] = []
    ttl = timedelta(hours=settings.tavily_cache_ttl_hours)
    tavily_client = TavilyClient(api_key=settings.tavily_api_key) if TavilyClient else None
    async with AsyncClient() as http_client:
        for query in queries:
            cached = _CACHE.get(query)
            if cached:
                cached_at, cached_results = cached
                if datetime.utcnow() - cached_at <= ttl:
                    results.extend(cached_results)
                    continue
                _CACHE.pop(query, None)
            try:
                if tavily_client:
                    data = await asyncio.to_thread(
                        _tavily_search_sync, tavily_client, query, settings
                    )
                else:
                    data = await _tavily_search_httpx(http_client, query, settings)
                packed = [
                    {
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "snippet": item.get("content", ""),
                    }
                    for item in data.get("results", [])
                ]
                _CACHE[query] = (datetime.utcnow(), packed)
                results.extend(packed)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tavily search failed: %s", exc)
                continue
    return results


def synthesize(results: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    """Transform search results into a structured grounding pack.

    For the MVP we simply map the first few results into key points. Each
    key point references its source URL for citation. Unknown and
    disputed sections are left empty as we cannot infer them without an
    LLM. The ``what_to_ask_user`` section remains empty as well.
    """
    key_points = []
    for res in results[:3]:
        text = res.get("snippet", "").strip()
        if not text:
            continue
        key_points.append(
            {
                "text": text,
                "sources": [
                    {
                        "url": res.get("url"),
                        "title": res.get("title"),
                    }
                ],
                "confidence": 0.5,
            }
        )
    return {
        "key_points": key_points,
        "norms_and_expectations": [],
        "constraints_and_rules": [],
        "disputed_or_uncertain": [],
        "what_to_ask_user": [],
    }
