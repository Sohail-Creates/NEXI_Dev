"""Local history location required by the existing startup wiring."""

from pathlib import Path

from ..config import storage_config


class QueryHistoryStore:
    """Resolve the local history directory without creating a new write path.

    No route currently writes through this store. History persistence and the
    ordinary-Q/A boundary remain deferred to the approved later phases.
    """

    def __init__(self):
        self.storage_dir = Path(storage_config.STORAGE_FILE).parent / "history"
