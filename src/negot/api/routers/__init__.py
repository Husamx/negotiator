"""
Routing subpackage.

This module exposes the routers for sessions, knowledge graph and templates
so they can be imported succinctly in ``api/main.py``.
"""
from . import (
    admin,
    facts,
    knowledge_edges,
    knowledge_graph,
    relationships,
    sessions,
    strategies,
    templates,
    users,
)  # noqa: F401
