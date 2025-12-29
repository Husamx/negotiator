from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import STRATEGY_DIR
from app.core.models import ActionType, Domain, Strategy


_ACTION_MAP = {
    "PROPOSE": ActionType.PROPOSE_OFFER,
    "COUNTER": ActionType.COUNTER_OFFER,
    "CONCEDE": ActionType.CONCEDE,
    "PACKAGE_OFFER": ActionType.PROPOSE_PACKAGE,
    "ADD_ISSUE": ActionType.PROPOSE_PACKAGE,
    "ASK_QUESTION": ActionType.ASK_INFO,
    "REQUEST_JUSTIFICATION": ActionType.REQUEST_CRITERIA,
    "REQUEST_CONCESSION": ActionType.TRADE,
    "PROVIDE_JUSTIFICATION": ActionType.REQUEST_CRITERIA,
    "REFRAME": ActionType.SUMMARIZE_VALIDATE,
    "SUMMARIZE": ActionType.SUMMARIZE_VALIDATE,
    "SET_PROCESS": ActionType.SUMMARIZE_VALIDATE,
    "SET_MEETING": ActionType.DEFER_AND_SCHEDULE,
    "DEFER": ActionType.DEFER_AND_SCHEDULE,
    "DOCUMENT": ActionType.SUMMARIZE_VALIDATE,
    "REFUSE": ActionType.REJECT,
    "DECLARE_LIMIT": ActionType.REJECT,
    "COMMIT": ActionType.ACCEPT,
}


class StrategyRegistry:
    def __init__(self, strategy_dir: Path | None = None) -> None:
        self.strategy_dir = strategy_dir or STRATEGY_DIR
        self._strategies: List[Strategy] = []

    def load(self) -> None:
        """Load and normalize strategy definitions from disk.
        """
        self._strategies = []
        for path in sorted(self.strategy_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            normalized = self._normalize(payload)
            self._strategies.append(Strategy(**normalized))

    def list(self) -> List[Strategy]:
        """Return cached strategies, loading from disk if needed.
        """
        if not self._strategies:
            self.load()
        return self._strategies

    def _normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize legacy strategy fields to the v0.1 schema.
        """
        preferred_raw = payload.get("preferred_actions", [])
        preferred_actions: List[str] = []
        for action in preferred_raw:
            if isinstance(action, str):
                mapped = _ACTION_MAP.get(action)
                if mapped:
                    preferred_actions.append(mapped.value)
        if not preferred_actions:
            preferred_actions = [ActionType.ASK_INFO.value, ActionType.PROPOSE_OFFER.value]

        online_reference = payload.get("online_reference")
        if isinstance(online_reference, dict):
            online_reference = online_reference.get("url")
        if not isinstance(online_reference, str):
            online_reference = ""

        ui = payload.get("ui", {})
        if not ui.get("icon"):
            ui["icon"] = "dot"

        applicability = payload.get("applicability", {}) or {}
        domains = applicability.get("domains", [])
        valid_domains = {d.value for d in Domain}
        filtered_domains = [d for d in domains if isinstance(d, str) and d in valid_domains]
        if not filtered_domains:
            filtered_domains = [Domain.GENERAL.value]
        applicability["domains"] = filtered_domains
        payload["applicability"] = applicability

        payload["preferred_actions"] = preferred_actions
        payload["online_reference"] = online_reference
        payload["ui"] = ui
        return payload
