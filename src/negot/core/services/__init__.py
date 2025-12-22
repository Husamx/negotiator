"""
Service subpackage aggregating domain logic.

This package exposes functions for interacting with domain services such as
authentication, sessions, knowledge graph management, templates,
orchestration and web grounding. See individual modules for details.
"""
from . import auth, kg, orchestrator, sessions, templates, web_grounding  # noqa: F401