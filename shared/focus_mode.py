"""TeachMe focus broadcast and cooperative service-level yielding."""

import asyncio
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TEACHME_FOCUS = "focus: teachme"


class FocusModeBroadcast:
    """Thread-safe in-process publisher owned by Central."""

    def __init__(self):
        self._condition = threading.Condition()
        self._teachme_leases = set()
        self._subscribers = []
        self._generation = 0

    def publish_teachme(self, lease_id):
        with self._condition:
            changed = lease_id not in self._teachme_leases
            self._teachme_leases.add(lease_id)
            if changed:
                self._generation += 1
                snapshot = self._snapshot_unlocked()
                self._condition.notify_all()
            else:
                return self._snapshot_unlocked()
        self._notify(snapshot)
        return snapshot

    def clear_teachme(self, lease_id):
        with self._condition:
            changed = lease_id in self._teachme_leases
            self._teachme_leases.discard(lease_id)
            if changed:
                self._generation += 1
                snapshot = self._snapshot_unlocked()
                self._condition.notify_all()
            else:
                return self._snapshot_unlocked()
        self._notify(snapshot)
        return snapshot

    def snapshot(self):
        with self._condition:
            return self._snapshot_unlocked()

    def subscribe(self, callback):
        with self._condition:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback):
        with self._condition:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def wait_for_change(self, generation, timeout=None):
        with self._condition:
            self._condition.wait_for(
                lambda: self._generation != generation, timeout=timeout
            )
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self):
        active = bool(self._teachme_leases)
        return {
            "signal": TEACHME_FOCUS if active else None,
            "teachme_active": active,
            "generation": self._generation,
            "lease_ids": sorted(self._teachme_leases),
        }

    def _notify(self, snapshot):
        with self._condition:
            subscribers = tuple(self._subscribers)
        for callback in subscribers:
            callback(dict(snapshot))


class FocusModeClient:
    """Polling client used by services to delay non-TeachMe work."""

    def __init__(self, central_url=None, defer_seconds=None, status_provider=None):
        self.central_url = (central_url or os.getenv(
            "CENTRAL_SERVER_URL", "https://localhost:8000"
        )).rstrip("/")
        self.defer_seconds = float(
            defer_seconds if defer_seconds is not None
            else os.getenv("TEACHME_FOCUS_DEFER_SECONDS", "0.25")
        )
        self.status_provider = status_provider

    def snapshot(self):
        if self.status_provider is not None:
            return self.status_provider()
        try:
            from config.ssl_config import client_ssl_context
            from shared.security import internal_service_headers
            request = Request(self.central_url + "/resources/focus", headers=internal_service_headers())
            with urlopen(request, timeout=0.5, context=client_ssl_context(self.central_url)) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
            return {"signal": None, "teachme_active": False, "unavailable": True}

    def defer_if_needed(self, request_context="background"):
        if request_context.strip().lower() == "teachme":
            return 0.0
        if not self.snapshot().get("teachme_active", False):
            return 0.0
        started = time.monotonic()
        time.sleep(self.defer_seconds)
        return time.monotonic() - started

    async def async_defer_if_needed(self, request_context="background"):
        return await asyncio.to_thread(self.defer_if_needed, request_context)


_broadcast = FocusModeBroadcast()


def get_focus_mode_broadcast():
    return _broadcast
