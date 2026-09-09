"""Startup-compatible cloud sync boundary; export is deferred to Phase 7."""

import logging

logger = logging.getLogger(__name__)


class CloudSyncService:
    """Accept the existing configuration without reading or exporting data."""

    def __init__(self, history_dir: str, cloud_url: str):
        self.history_dir = history_dir
        self.cloud_url = cloud_url

    async def sync_history(self):
        """Leave data untouched and explicitly report the unimplemented sync."""
        logger.warning("Cloud sync is not implemented; deferred to Phase 7")
