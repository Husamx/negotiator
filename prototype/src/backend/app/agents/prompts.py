from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import PROMPTS_DIR


@dataclass
class PromptTemplate:
    prompt_id: str
    prompt_version: str
    template: str


class PromptRegistry:
    def __init__(self, prompts_dir: Path | None = None) -> None:
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        self._templates: Dict[str, PromptTemplate] = {}

    def load(self) -> None:
        """Load prompt templates from the prompts directory.
        """
        self._templates = {}
        for path in sorted(self.prompts_dir.glob("*.md")):
            template = self._parse_prompt(path)
            self._templates[template.prompt_id] = template

    def list_versions(self) -> List[Dict[str, str]]:
        """Return prompt_id and prompt_version pairs for trace headers.
        """
        if not self._templates:
            self.load()
        return [
            {"prompt_id": tmpl.prompt_id, "prompt_version": tmpl.prompt_version}
            for tmpl in self._templates.values()
        ]

    def render(self, prompt_id: str, variables: Dict[str, Any]) -> PromptTemplate:
        """Render a prompt template with variables for agent calls.
        """
        if not self._templates:
            self.load()
        template = self._templates.get(prompt_id)
        if not template:
            raise KeyError(f"Prompt not found: {prompt_id}")
        # Use a safe replacement strategy to avoid .format() breaking on JSON braces.
        rendered = template.template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return PromptTemplate(prompt_id=template.prompt_id, prompt_version=template.prompt_version, template=rendered)

    def _parse_prompt(self, path: Path) -> PromptTemplate:
        """Parse prompt metadata and template body from a markdown file.
        """
        lines = path.read_text(encoding="utf-8").splitlines()
        prompt_id = path.stem
        prompt_version = "1"
        template_lines: List[str] = []
        idx = 0
        if lines and lines[0].startswith("prompt_id:"):
            prompt_id = lines[0].split(":", 1)[1].strip()
            idx = 1
        if len(lines) > idx and lines[idx].startswith("prompt_version:"):
            prompt_version = lines[idx].split(":", 1)[1].strip()
            idx += 1
        if len(lines) > idx and lines[idx].strip() == "---":
            idx += 1
        template_lines = lines[idx:]
        return PromptTemplate(prompt_id=prompt_id, prompt_version=prompt_version, template="\n".join(template_lines))
