"""
Negotiation Companion core package.

This package contains all application modules for the Negotiation Companion
(working name "negotiator"). The code is organised into subpackages for
configuration, database models, services, API routing and user interfaces.

Following the repository specifications, the code is designed to be
modular, type annotated and self‑documenting. To learn more about
the architecture and domain concepts consult the documentation under
``docs/legacy/`` in the project root.
"""

from .core.config import Settings  # noqa: F401