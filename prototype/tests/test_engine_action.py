import unittest
from types import SimpleNamespace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND_SRC))

from app.agents.prompts import PromptRegistry
from app.core.models import ActionType
from app.services.strategy_registry import StrategyRegistry
from app.simulation.engine import SimulationEngine


class ExtractActionTests(unittest.TestCase):
    def setUp(self):
        self.engine = SimulationEngine(StrategyRegistry(), PromptRegistry())

    def _call(self, action_type_value):
        return SimpleNamespace(
            parsed_output={
                "action": {"type": action_type_value, "payload": {"question": "Q?"}},
            }
        )

    def test_extract_action_enum_type(self):
        call = self._call(ActionType.ASK_INFO)
        action_type, payload, action = self.engine._extract_action(call)
        self.assertEqual(action_type, "ASK_INFO")
        self.assertEqual(payload.get("question"), "Q?")
        self.assertEqual(action.get("type"), ActionType.ASK_INFO)

    def test_extract_action_string_type(self):
        call = self._call("ASK_INFO")
        action_type, payload, action = self.engine._extract_action(call)
        self.assertEqual(action_type, "ASK_INFO")
        self.assertEqual(payload.get("question"), "Q?")
        self.assertEqual(action.get("type"), "ASK_INFO")

    def test_extract_action_enum_string_repr(self):
        call = self._call("ActionType.ASK_INFO")
        action_type, _, _ = self.engine._extract_action(call)
        self.assertEqual(action_type, "ASK_INFO")


if __name__ == "__main__":
    unittest.main()
