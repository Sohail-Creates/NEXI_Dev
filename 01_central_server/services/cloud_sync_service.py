"""Conversation-only cloud synchronization for the Central service.

This module owns a deliberately narrow SQLite projection. It can read only the
``conversations`` outbox and the worker's own ``sync_state`` metadata. The
receiver URL and credential are deployment configuration, never product code.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request

from shared.retry_handler import RetryHandler, RetryPolicy
from shared.security import require_internal_service


logger = logging.getLogger(__name__)
UTCClock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class CloudSyncError(RuntimeError):
    """Base error raised by the cloud-sync boundary."""


class RetryableCloudSyncError(CloudSyncError):
    """Transient transport/receiver error which may be retried."""


class CloudSyncRejectedError(CloudSyncError):
    """Permanent receiver rejection which must not be retried blindly."""


@dataclass(frozen=True)
class CloudSyncSettings:
    enabled: bool
    base_url: str
    auth_header: str
    auth_token: str
    timeout_seconds: float
    interval_seconds: float
    retry_attempts: int
    retry_initial_delay_seconds: float
    retry_max_delay_seconds: float
    retry_backoff_multiplier: float
    supervisor_retry_seconds: float
    batch_size: int

    @classmethod
    def from_env(cls) -> "CloudSyncSettings":
        enabled = os.getenv("CLOUD_SYNC_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        base_url = os.getenv("CLOUD_SYNC_BASE_URL", "").strip().rstrip("/")
        if enabled and not base_url:
            raise RuntimeError("CLOUD_SYNC_BASE_URL is required when cloud sync is enabled")
        auth_header = os.getenv("CLOUD_SYNC_AUTH_HEADER", "Authorization").strip()
        if not auth_header:
            raise RuntimeError("CLOUD_SYNC_AUTH_HEADER cannot be empty")
        return cls(
            enabled=enabled,
            base_url=base_url,
            auth_header=auth_header,
            auth_token=os.getenv("CLOUD_SYNC_AUTH_TOKEN", "").strip(),
            timeout_seconds=float(os.getenv("CLOUD_SYNC_TIMEOUT_SECONDS", "15")),
            interval_seconds=float(os.getenv("CLOUD_SYNC_INTERVAL_SECONDS", "86400")),
            retry_attempts=int(os.getenv("CLOUD_SYNC_RETRY_ATTEMPTS", "3")),
            retry_initial_delay_seconds=float(
                os.getenv("CLOUD_SYNC_RETRY_INITIAL_DELAY_SECONDS", "1")
            ),
            retry_max_delay_seconds=float(os.getenv("CLOUD_SYNC_RETRY_MAX_DELAY_SECONDS", "30")),
            retry_backoff_multiplier=float(os.getenv("CLOUD_SYNC_RETRY_BACKOFF", "2")),
            supervisor_retry_seconds=float(os.getenv("CLOUD_SYNC_SUPERVISOR_RETRY_SECONDS", "60")),
            batch_size=int(os.getenv("CLOUD_SYNC_BATCH_SIZE", "100")),
        )


@dataclass(frozen=True)
class ExportableConversation:
    """The complete and exclusive cloud export schema."""

    conversation_id: str
    user_id: str
    timestamp: str
    user_message: str
    assistant_response: str
    language: str | None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ExportableConversation":
        required = (
            "conversation_id",
            "user_id",
            "timestamp",
            "user_message",
            "assistant_response",
        )
        missing = [field for field in required if not isinstance(record.get(field), str)]
        if missing:
            raise ValueError(f"Conversation has invalid export fields: {', '.join(missing)}")
        language = record.get("language")
        if language is not None and not isinstance(language, str):
            raise ValueError("Conversation has invalid export field: language")
        return cls(
            conversation_id=record["conversation_id"],
            user_id=record["user_id"],
            timestamp=record["timestamp"],
            user_message=record["user_message"],
            assistant_response=record["assistant_response"],
            language=language,
        )


@dataclass(frozen=True)
class PendingBatch:
    batch_id: str
    records: tuple[ExportableConversation, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "records": [asdict(record) for record in self.records],
        }


class ConversationOutbox:
    """SQLite access constrained to the conversation outbox and sync metadata."""

    def __init__(self, database: Path | str, *, clock: UTCClock = _utc_now):
        self.database = Path(database)
        self.clock = clock

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def acquire_pending_batch(self, limit: int) -> PendingBatch | None:
        if limit < 1:
            raise ValueError("batch size must be positive")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT batch_id FROM conversations
                   WHERE synced = 0 AND batch_id IS NOT NULL
                   ORDER BY position LIMIT 1"""
            ).fetchone()
            if existing:
                batch_id = str(existing["batch_id"])
            else:
                positions = [
                    row["position"]
                    for row in connection.execute(
                        """SELECT position FROM conversations
                           WHERE synced = 0 AND batch_id IS NULL
                           ORDER BY position LIMIT ?""",
                        (limit,),
                    )
                ]
                if not positions:
                    return None
                batch_id = str(uuid.uuid4())
                placeholders = ",".join("?" for _ in positions)
                connection.execute(
                    f"UPDATE conversations SET batch_id=? WHERE position IN ({placeholders})",
                    (batch_id, *positions),
                )
            rows = connection.execute(
                """SELECT record FROM conversations
                   WHERE synced = 0 AND batch_id=? ORDER BY position""",
                (batch_id,),
            ).fetchall()
            records = tuple(
                ExportableConversation.from_record(json.loads(row["record"])) for row in rows
            )
            return PendingBatch(batch_id=batch_id, records=records)

    def mark_attempted(self, batch_id: str, attempted_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE conversations SET sync_attempted_at=?
                   WHERE synced = 0 AND batch_id=?""",
                (_iso(attempted_at), batch_id),
            )

    def acknowledge(self, batch_id: str, succeeded_at: datetime) -> int:
        value = _iso(succeeded_at)
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE conversations
                   SET synced=1, sync_succeeded_at=?, sync_attempted_at=?
                   WHERE synced=0 AND batch_id=?""",
                (value, value, batch_id),
            )
            self._set_state(connection, "last_success", value)
            self._set_state(connection, "last_error", "")
            return int(cursor.rowcount)

    def record_empty_success(self, succeeded_at: datetime) -> None:
        with self._connect() as connection:
            self._set_state(connection, "last_success", _iso(succeeded_at))
            self._set_state(connection, "last_error", "")

    def record_error(self, error: str) -> None:
        with self._connect() as connection:
            self._set_state(connection, "last_error", error)

    @staticmethod
    def _set_state(connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """INSERT INTO sync_state (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (key, value),
        )

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            pending = int(
                connection.execute(
                    "SELECT COUNT(*) FROM conversations WHERE synced=0"
                ).fetchone()[0]
            )
            state = {
                str(row["key"]): str(row["value"])
                for row in connection.execute("SELECT key, value FROM sync_state")
            }
        return {
            "last_successful_sync": state.get("last_success") or None,
            "pending_records": pending,
            "last_error": state.get("last_error") or None,
        }


class CloudSyncClient:
    """Config-driven HTTP sender using one shared bounded-retry interface."""

    def __init__(self, settings: CloudSyncSettings):
        self.settings = settings
        policy = RetryPolicy(
            max_attempts=settings.retry_attempts,
            initial_delay_ms=max(0, int(settings.retry_initial_delay_seconds * 1000)),
            max_delay_ms=max(0, int(settings.retry_max_delay_seconds * 1000)),
            backoff_multiplier=settings.retry_backoff_multiplier,
            jitter=False,
        ).add_retryable_exception(RetryableCloudSyncError)
        self.retry = RetryHandler(policy=policy, logger=logger)

    @property
    def endpoint(self) -> str:
        return f"{self.settings.base_url}/batches"

    def _headers(self) -> dict[str, str]:
        if not self.settings.auth_token:
            return {}
        return {self.settings.auth_header: self.settings.auth_token}

    async def send_batch(self, batch: PendingBatch) -> dict[str, Any]:
        return await self.retry.execute_async(
            self._send_once,
            batch,
            operation_name=f"cloud-sync batch {batch.batch_id}",
        )

    async def _send_once(self, batch: PendingBatch) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.post(
                    self.endpoint,
                    json=batch.payload(),
                    headers=self._headers(),
                )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise RetryableCloudSyncError(f"Cloud receiver unavailable: {exc}") from exc
        if response.status_code >= 500:
            raise RetryableCloudSyncError(
                f"Cloud receiver returned HTTP {response.status_code}"
            )
        if response.status_code >= 400:
            raise CloudSyncRejectedError(
                f"Cloud receiver rejected batch with HTTP {response.status_code}"
            )
        try:
            acknowledgement = response.json()
        except ValueError as exc:
            raise RetryableCloudSyncError("Cloud receiver returned invalid JSON") from exc
        if (
            acknowledgement.get("acknowledged") is not True
            or acknowledgement.get("batch_id") != batch.batch_id
        ):
            raise RetryableCloudSyncError("Cloud receiver returned an invalid acknowledgement")
        return acknowledgement


class CloudSyncService:
    """Executes outbox batches and supervises the persisted-time scheduler."""

    def __init__(
        self,
        outbox: ConversationOutbox,
        client: CloudSyncClient,
        settings: CloudSyncSettings,
        *,
        clock: UTCClock = _utc_now,
    ):
        self.outbox = outbox
        self.client = client
        self.settings = settings
        self.clock = clock
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @classmethod
    def from_env(cls, database: Path | str) -> "CloudSyncService":
        settings = CloudSyncSettings.from_env()
        outbox = ConversationOutbox(database)
        return cls(outbox, CloudSyncClient(settings), settings)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def run_once(self) -> dict[str, Any]:
        batch = await asyncio.to_thread(
            self.outbox.acquire_pending_batch, self.settings.batch_size
        )
        if batch is None:
            completed = self.clock()
            await asyncio.to_thread(self.outbox.record_empty_success, completed)
            return {"batch_id": None, "records_synced": 0, "completed_at": _iso(completed)}
        attempted = self.clock()
        await asyncio.to_thread(self.outbox.mark_attempted, batch.batch_id, attempted)
        try:
            acknowledgement = await self.client.send_batch(batch)
        except Exception as exc:
            await asyncio.to_thread(self.outbox.record_error, str(exc))
            raise
        succeeded = self.clock()
        updated = await asyncio.to_thread(self.outbox.acknowledge, batch.batch_id, succeeded)
        return {
            "batch_id": batch.batch_id,
            "records_synced": updated,
            "receiver_duplicate": bool(acknowledgement.get("duplicate", False)),
            "completed_at": _iso(succeeded),
        }

    async def sync_history(self) -> dict[str, Any]:
        """Compatibility name retained from the Phase 1 stub."""
        return await self.run_once()

    def seconds_until_next_run(self, now: datetime | None = None) -> float:
        status = self.outbox.status()
        raw = status["last_successful_sync"]
        if raw is None:
            return 0.0
        last_success = datetime.fromisoformat(raw)
        current = now or self.clock()
        elapsed = (current - last_success).total_seconds()
        return max(0.0, self.settings.interval_seconds - elapsed)

    async def _wait_or_stop(self, seconds: float) -> bool:
        if seconds <= 0:
            return self._stop_event.is_set()
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _supervised_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if await self._wait_or_stop(
                    await asyncio.to_thread(self.seconds_until_next_run)
                ):
                    break
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled cloud sync failed; supervisor will retry")
                if await self._wait_or_stop(self.settings.supervisor_retry_seconds):
                    break

    def start(self) -> asyncio.Task[None] | None:
        if not self.settings.enabled:
            logger.info("Cloud sync worker disabled by CLOUD_SYNC_ENABLED")
            return None
        if self.running:
            return self._task
        self._stop_event.clear()
        self._task = asyncio.create_task(self._supervised_loop(), name="cloud-sync-supervisor")
        return self._task

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict[str, Any]:
        state = self.outbox.status()
        state.update(
            {
                "enabled": self.settings.enabled,
                "worker_running": self.running,
                "next_run_in_seconds": self.seconds_until_next_run()
                if self.settings.enabled
                else None,
            }
        )
        return state


router = APIRouter(prefix="/sync", tags=["Cloud Sync"])


@router.get("/status")
async def sync_status(request: Request) -> dict[str, Any]:
    await require_internal_service(request)
    service = getattr(request.app.state, "cloud_sync_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Cloud sync service is unavailable")
    return await asyncio.to_thread(service.status)
