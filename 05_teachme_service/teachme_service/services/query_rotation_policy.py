"""Non-destructive startup hook for the deferred history retention policy."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class QueryRotationPolicy:
    """Keep existing history until a retention policy is approved."""

    def __init__(self, storage_dir):
        self.storage_dir = Path(storage_dir)

    def run_cleanup(self):
        """Report that retention cleanup is disabled in Phase 1."""
        logger.info("Query history cleanup is disabled; retention policy is deferred")
