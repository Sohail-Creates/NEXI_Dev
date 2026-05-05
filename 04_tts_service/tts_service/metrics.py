"""
PHASE 4.1: Prometheus Metrics Integration
High-performance metrics collection for monitoring and observability.
"""

import time
import threading
from typing import Dict, Optional
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest


# ==========================
# Metrics Definitions
# ==========================
class MetricsRegistry:
    """Central metrics registry for TTS service."""
    
    def __init__(self):
        """Initialize Prometheus metrics."""
        self.registry = CollectorRegistry()
        
        # Counter: Total synthesis requests (by result)
        self.synthesis_requests_total = Counter(
            'tts_synthesis_requests_total',
            'Total synthesis requests',
            ['status'],  # status: success, validation_error, timeout, server_error
            registry=self.registry
        )
        
        # Histogram: Synthesis latency (in seconds)
        self.synthesis_latency_seconds = Histogram(
            'tts_synthesis_latency_seconds',
            'Synthesis request latency',
            ['voice_id'],  # Per-voice latency tracking
            buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0),  # 100ms to 5s
            registry=self.registry
        )
        
        # Counter: Synthesis errors by type
        self.synthesis_errors_total = Counter(
            'tts_synthesis_errors_total',
            'Total synthesis errors',
            ['error_type'],  # error_type: validation, timeout, synthesis, resource
            registry=self.registry
        )
        
        # Gauge: Queue depth per worker
        self.worker_queue_depth = Gauge(
            'tts_worker_queue_depth',
            'Current queue depth per worker',
            ['worker_id'],
            registry=self.registry
        )
        
        # Gauge: Cache hit rate
        self.cache_hit_rate = Gauge(
            'tts_cache_hit_rate',
            'Overall cache hit rate (0-1)',
            registry=self.registry
        )
        
        # Counter: Cache hits and misses
        self.cache_operations_total = Counter(
            'tts_cache_operations_total',
            'Total cache operations',
            ['type'],  # type: hit, miss
            registry=self.registry
        )
        
        # Gauge: Available voices
        self.available_voices = Gauge(
            'tts_available_voices',
            'Number of available voices',
            registry=self.registry
        )
        
        # Gauge: Service uptime (seconds)
        self.service_uptime_seconds = Gauge(
            'tts_service_uptime_seconds',
            'Service uptime in seconds',
            registry=self.registry
        )
        
        # Counter: Requests per voice
        self.requests_per_voice_total = Counter(
            'tts_requests_per_voice_total',
            'Total requests per voice',
            ['voice_id'],
            registry=self.registry
        )
        
        # Gauge: Worker pool health
        self.worker_pool_health = Gauge(
            'tts_worker_pool_health',
            'Worker pool health (0=degraded, 1=healthy)',
            registry=self.registry
        )
        
        # Counter: Active requests (gauge-like)
        self.active_requests = Gauge(
            'tts_active_requests',
            'Number of active synthesis requests',
            registry=self.registry
        )
        
        # Histogram: Text length distribution
        self.text_length_characters = Histogram(
            'tts_text_length_characters',
            'Distribution of input text lengths',
            buckets=(10, 50, 100, 200, 500, 1000, 5000),
            registry=self.registry
        )
        
        # Counter: Language hints used
        self.language_hints_total = Counter(
            'tts_language_hints_total',
            'Total requests with language hints',
            ['language'],  # language: en, urdu, none
            registry=self.registry
        )
        
        # Gauge: Error rate (per minute)
        self.error_rate_per_minute = Gauge(
            'tts_error_rate_per_minute',
            'Error rate per minute',
            registry=self.registry
        )
        
        self.lock = threading.RLock()
    
    def record_successful_synthesis(self, voice_id: str, latency_seconds: float,
                                   text_length: int, language_hint: Optional[str] = None) -> None:
        """Record successful synthesis."""
        with self.lock:
            self.synthesis_requests_total.labels(status='success').inc()
            self.synthesis_latency_seconds.labels(voice_id=voice_id).observe(latency_seconds)
            self.requests_per_voice_total.labels(voice_id=voice_id).inc()
            self.text_length_characters.observe(text_length)
            
            if language_hint:
                self.language_hints_total.labels(language=language_hint).inc()
            else:
                self.language_hints_total.labels(language='none').inc()
    
    def record_validation_error(self, voice_id: Optional[str] = None) -> None:
        """Record validation error."""
        with self.lock:
            self.synthesis_requests_total.labels(status='validation_error').inc()
            self.synthesis_errors_total.labels(error_type='validation').inc()
    
    def record_timeout_error(self, voice_id: Optional[str] = None) -> None:
        """Record timeout error."""
        with self.lock:
            self.synthesis_requests_total.labels(status='timeout').inc()
            self.synthesis_errors_total.labels(error_type='timeout').inc()
    
    def record_synthesis_error(self, voice_id: Optional[str] = None) -> None:
        """Record synthesis/server error."""
        with self.lock:
            self.synthesis_requests_total.labels(status='server_error').inc()
            self.synthesis_errors_total.labels(error_type='synthesis').inc()
    
    def record_resource_error(self) -> None:
        """Record resource exhaustion error."""
        with self.lock:
            self.synthesis_requests_total.labels(status='resource_error').inc()
            self.synthesis_errors_total.labels(error_type='resource').inc()
    
    def set_queue_depth(self, worker_id: str, depth: int) -> None:
        """Update queue depth for worker."""
        with self.lock:
            self.worker_queue_depth.labels(worker_id=worker_id).set(depth)
    
    def set_cache_hit_rate(self, hit_rate: float) -> None:
        """Update cache hit rate (0.0 to 1.0)."""
        with self.lock:
            self.cache_hit_rate.set(hit_rate)
    
    def record_cache_hit(self) -> None:
        """Record cache hit."""
        with self.lock:
            self.cache_operations_total.labels(type='hit').inc()
    
    def record_cache_miss(self) -> None:
        """Record cache miss."""
        with self.lock:
            self.cache_operations_total.labels(type='miss').inc()
    
    def set_available_voices(self, count: int) -> None:
        """Update available voices count."""
        with self.lock:
            self.available_voices.set(count)
    
    def set_uptime(self, seconds: float) -> None:
        """Update service uptime."""
        with self.lock:
            self.service_uptime_seconds.set(seconds)
    
    def set_worker_pool_health(self, is_healthy: bool) -> None:
        """Update worker pool health status."""
        with self.lock:
            self.worker_pool_health.set(1 if is_healthy else 0)
    
    def set_active_requests(self, count: int) -> None:
        """Update active request count."""
        with self.lock:
            self.active_requests.set(count)
    
    def set_error_rate(self, errors_per_minute: float) -> None:
        """Update error rate."""
        with self.lock:
            self.error_rate_per_minute.set(errors_per_minute)
    
    def get_metrics_text(self) -> str:
        """Get Prometheus metrics in text format."""
        return generate_latest(self.registry).decode('utf-8')
    
    def get_metrics_dict(self) -> Dict:
        """Get metrics as dictionary (for JSON endpoints)."""
        # Simple extraction of current metric values
        metrics = {
            "synthesis_requests_total": self._get_counter_value('tts_synthesis_requests_total'),
            "synthesis_errors_total": self._get_counter_value('tts_synthesis_errors_total'),
            "cache_hit_rate": self.cache_hit_rate._value.get(),
            "available_voices": int(self.available_voices._value.get()),
            "service_uptime_seconds": self.service_uptime_seconds._value.get(),
            "active_requests": int(self.active_requests._value.get()),
            "error_rate_per_minute": self.error_rate_per_minute._value.get(),
        }
        return metrics
    
    @staticmethod
    def _get_counter_value(metric_name: str) -> int:
        """Helper to extract counter values (simplified)."""
        # This is a simplified approach - in production, would extract from registry
        return 0


# ==========================
# Global Metrics Instance
# ==========================
metrics_registry = MetricsRegistry()


# ==========================
# Convenience Functions
# ==========================
def record_successful_synthesis(voice_id: str, latency_seconds: float,
                               text_length: int, language_hint: Optional[str] = None) -> None:
    """Record successful synthesis request."""
    metrics_registry.record_successful_synthesis(voice_id, latency_seconds, 
                                                 text_length, language_hint)


def record_validation_error(voice_id: Optional[str] = None) -> None:
    """Record validation error."""
    metrics_registry.record_validation_error(voice_id)


def record_timeout_error(voice_id: Optional[str] = None) -> None:
    """Record timeout error."""
    metrics_registry.record_timeout_error(voice_id)


def record_synthesis_error(voice_id: Optional[str] = None) -> None:
    """Record synthesis error."""
    metrics_registry.record_synthesis_error(voice_id)


def get_metrics_text() -> str:
    """Get Prometheus metrics in text format."""
    return metrics_registry.get_metrics_text()


def get_metrics_dict() -> Dict:
    """Get metrics as dictionary."""
    return metrics_registry.get_metrics_dict()


# Export
__all__ = [
    "MetricsRegistry",
    "metrics_registry",
    "record_successful_synthesis",
    "record_validation_error",
    "record_timeout_error",
    "record_synthesis_error",
    "get_metrics_text",
    "get_metrics_dict",
]
