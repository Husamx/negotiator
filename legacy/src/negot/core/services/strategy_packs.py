"""
Strategy pack loader and schema validation utilities.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator, RefResolver

PACK_SCHEMA_NAME = "strategy_pack.schema.json"
STRATEGY_SCHEMA_NAME = "strategy_template.schema.json"
RUBRIC_SCHEMA_NAME = "rubric.schema.json"
CASE_SNAPSHOT_SCHEMA_NAME = "case_snapshot.schema.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _pack_root() -> Path:
    return _repo_root() / "strategy_pack"


@lru_cache(maxsize=1)
def _schema_store() -> Dict[str, dict]:
    schema_dir = _pack_root() / "schemas"
    store: Dict[str, dict] = {}
    for path in schema_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        schema_id = data.get("$id", path.name)
        store[schema_id] = data
        store[path.name] = data
    return store


def _validate(instance: dict, schema_name: str) -> None:
    store = _schema_store()
    schema = store.get(schema_name)
    if not schema:
        raise ValueError(f"Schema not found: {schema_name}")
    resolver = RefResolver.from_schema(schema, store=store)
    Draft202012Validator(schema, resolver=resolver).validate(instance)


@lru_cache(maxsize=1)
def load_pack_manifest() -> dict:
    manifest_path = _pack_root() / "strategy_packs" / "core" / "pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate(manifest, PACK_SCHEMA_NAME)
    return manifest


@lru_cache(maxsize=None)
def load_strategy(strategy_id: str) -> dict:
    manifest = load_pack_manifest()
    entry = next(
        (item for item in manifest.get("strategies", []) if item["strategy_id"] == strategy_id),
        None,
    )
    if not entry:
        raise ValueError(f"Unknown strategy_id: {strategy_id}")
    strategy_path = _pack_root() / "strategy_packs" / "core" / entry["path"]
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    _validate(strategy, STRATEGY_SCHEMA_NAME)
    return strategy


@lru_cache(maxsize=None)
def load_rubric(rubric_id: str) -> dict:
    manifest = load_pack_manifest()
    entry = next(
        (item for item in manifest.get("rubrics", []) if item["rubric_id"] == rubric_id),
        None,
    )
    if not entry:
        raise ValueError(f"Unknown rubric_id: {rubric_id}")
    rubric_path = _pack_root() / "strategy_packs" / "core" / entry["path"]
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    _validate(rubric, RUBRIC_SCHEMA_NAME)
    return rubric


def list_strategies(enabled_only: bool = True) -> List[dict]:
    manifest = load_pack_manifest()
    strategies = []
    for entry in manifest.get("strategies", []):
        if enabled_only and entry.get("enabled") is False:
            continue
        strategy = load_strategy(entry["strategy_id"])
        strategies.append(strategy)
    return strategies


def list_strategy_summaries(enabled_only: bool = True) -> List[dict]:
    summaries = []
    for strategy in list_strategies(enabled_only=enabled_only):
        summaries.append(
            {
                "strategy_id": strategy["strategy_id"],
                "name": strategy["name"],
                "summary": strategy["summary"],
                "goal": strategy.get("goal"),
                "category": strategy.get("category"),
                "tags": strategy.get("tags", []),
                "revision": strategy.get("revision"),
                "applicability": strategy.get("applicability", {}),
            }
        )
    return summaries


def get_strategy_summary(strategy_id: str) -> dict:
    strategy = load_strategy(strategy_id)
    return {
        "strategy_id": strategy["strategy_id"],
        "name": strategy["name"],
        "summary": strategy["summary"],
        "goal": strategy.get("goal"),
        "category": strategy.get("category"),
        "tags": strategy.get("tags", []),
        "revision": strategy.get("revision"),
        "applicability": strategy.get("applicability", {}),
    }


def pack_info() -> Dict[str, Optional[str]]:
    manifest = load_pack_manifest()
    return {
        "pack_id": manifest.get("pack_id"),
        "pack_version": manifest.get("pack_version"),
    }


def validate_case_snapshot(payload: dict) -> None:
    _validate(payload, CASE_SNAPSHOT_SCHEMA_NAME)
