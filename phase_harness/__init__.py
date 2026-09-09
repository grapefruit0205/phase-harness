"""Small, dependency-free two-role phase runner."""

from .core import HarnessError, PhaseRunner, import_legacy_phase

__all__ = ["HarnessError", "PhaseRunner", "import_legacy_phase"]
__version__ = "2.0.0"
