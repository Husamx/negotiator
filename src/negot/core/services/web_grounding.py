"""
Web grounding service using Tavily search.

This service uses LLM-driven agents to decide when to search, plan
queries, and synthesize a grounding pack. It follows the pipeline
described in ``docs/WEB_GROUNDING.md``.
"""
from __future__ import annotations

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from httpx import AsyncClient
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import get_settings
from .llm_utils import acompletion_with_retry, extract_completion_text

try:
    from tavily import TavilyClient
except Exception:  # noqa: BLE001
    TavilyClient = None

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}


class GroundingDecision(BaseModel):
    need_search: bool = Field(..., description="Whether web grounding is required.")
    reason_codes: List[str] = Field(default_factory=list)
    max_queries: int = Field(2, ge=0)
    max_sources_per_query: int = Field(5, ge=0)
    search_depth: str = Field("basic")
    topic: str = Field("general")


class QueryPlan(BaseModel):
    queries: List[str] = Field(default_factory=list)
    must_have_evidence: List[str] = Field(default_factory=list)
    stop_conditions: List[str] = Field(default_factory=list)


class GroundingPack(BaseModel):
    key_points: List[dict] = Field(default_factory=list)
    norms_and_expectations: List[dict] = Field(default_factory=list)
    constraints_and_rules: List[dict] = Field(default_factory=list)
    disputed_or_uncertain: List[dict] = Field(default_factory=list)
    what_to_ask_user: List[dict] = Field(default_factory=list)


NEED_SEARCH_SYSTEM_PROMPT = """You are the Web Grounding NeedSearch agent.
Decide if web search is required to answer the user's topic or question.
Follow these rules:
- Prefer not to search unless common knowledge, policy/legal, or time-sensitive facts are required.
- Unknown must remain unknown; do not invent facts.
Output JSON only that matches the schema:
{"need_search": true|false, "reason_codes": [...], "max_queries": 0-3, "max_sources_per_query": 0-5, "search_depth": "basic"|"advanced", "topic": "general|news|finance"}.
"""


QUERY_PLAN_SYSTEM_PROMPT = """You are the Web Grounding QueryPlanner agent.
Given the context and decision, produce up to 3 high-signal queries.
Output JSON only that matches the schema:
{"queries": ["..."], "must_have_evidence": ["..."], "stop_conditions": ["..."]}.
"""


SYNTHESIZE_SYSTEM_PROMPT = """You are the Web Grounding EvidenceSynthesizer agent.
You must synthesize a Grounding Pack from the provided search results.
Rules:
- Every non-trivial claim must cite a source from the results.
- If uncertain, place it in disputed_or_uncertain.
- Do not infer personal facts.
Output JSON only that matches the schema:
{
  "key_points": [{"text": "...", "sources": [{"url": "...", "title": "..."}], "confidence": 0.0}],
  "norms_and_expectations": [...],
  "constraints_and_rules": [...],
  "disputed_or_uncertain": [...],
  "what_to_ask_user": [{"q": "...", "why": "..."}]
}
"""


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


async def need_search(context: Dict[str, Any]) -> Dict[str, Any]:
    """Decide whether a web grounding search is required (LLM-based)."""
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot decide web grounding.")
    payload = {"context": context}
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": NEED_SEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        "temperature": 0.0,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        response = await client(response_model=GroundingDecision, **completion_kwargs)
        decision = response.model_dump()
    except Exception:
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty grounding decision.")
        decision = GroundingDecision.model_validate_json(content).model_dump()
    decision["search_depth"] = settings.tavily_search_depth
    return decision


async def plan_queries(context: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    """Plan a set of search queries based on the topic and decision (LLM-based)."""
    if not decision.get("need_search"):
        return {"queries": [], "must_have_evidence": [], "stop_conditions": []}
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot plan web grounding queries.")
    payload = {"context": context, "decision": decision}
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": QUERY_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        "temperature": 0.0,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        response = await client(response_model=QueryPlan, **completion_kwargs)
        return response.model_dump()
    except Exception:
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty query plan.")
        return QueryPlan.model_validate_json(content).model_dump()


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


async def synthesize(results: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    """Transform search results into a structured grounding pack (LLM-based)."""
    settings = get_settings()
    if not settings.litellm_model:
        raise RuntimeError("LiteLLM model is not configured; cannot synthesize grounding.")
    payload = {"context": context, "results": results}
    completion_kwargs = {
        "model": settings.litellm_model,
        "messages": [
            {"role": "system", "content": SYNTHESIZE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        "temperature": 0.0,
    }
    if settings.litellm_api_key:
        completion_kwargs["api_key"] = settings.litellm_api_key
    if settings.litellm_base_url:
        completion_kwargs["base_url"] = settings.litellm_base_url
    try:
        from instructor import from_litellm

        client = from_litellm(acompletion_with_retry)
        response = await client(response_model=GroundingPack, **completion_kwargs)
        return response.model_dump()
    except Exception:
        response = await acompletion_with_retry(**completion_kwargs)
        content = extract_completion_text(response)
        if not content:
            raise RuntimeError("LiteLLM returned an empty grounding pack.")
        return GroundingPack.model_validate_json(content).model_dump()
