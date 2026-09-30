"""Shared bounded slot for CPU-heavy Vision model inference."""

import threading

from ..config import Config


INFERENCE_SLOTS = threading.BoundedSemaphore(Config.INFERENCE_MAX_CONCURRENCY)
