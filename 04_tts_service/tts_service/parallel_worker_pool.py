"""
Parallel Worker Pool for TTS Service
Implements 3-parallel-worker synthesis with per-worker caches.
Each worker has its own UnifiedModelCache and EngineManager to eliminate lock contention.
"""

import asyncio
import logging
import threading
from typing import Optional, List
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class SynthesisTask:
    """Task submitted to worker pool."""
    text: str
    voice_id: str
    language_hint: Optional[str]
    request_id: str
    future: asyncio.Future
    submitted_time: float


class ParallelWorkerPool:
    """
    Manages 3 parallel worker threads for TTS synthesis.
    CRITICAL OPTIMIZATION: Each worker has its own UnifiedModelCache instance.
    This eliminates lock contention between workers and achieves true parallelism.
    """
    
    def __init__(self, num_workers: int = 3, queue_size: int = 50, models_dir: Optional[str] = None):
        """
        Initialize parallel worker pool with per-worker caches.
        
        Args:
            num_workers: Number of worker threads (default: 3)
            queue_size: Maximum tasks in queue before blocking
            models_dir: Path to models directory (for cache initialization)
        """
        self.num_workers = num_workers
        self.queue_size = queue_size
        self.models_dir = models_dir
        self.workers: List[asyncio.Task] = []
        self.task_queues: List[asyncio.Queue] = []
        self.worker_caches = []  # NEW: Per-worker caches
        self.running = False
        self.tasks_processed = 0
        self.tasks_failed = 0
        self.lock = threading.Lock()
        
        logger.info(f"ParallelWorkerPool initialized (workers: {num_workers}, queue_size: {queue_size})")
    
    async def start(self) -> None:
        """Start all worker threads with independent caches."""
        logger.info(f"Starting {self.num_workers} parallel workers with per-worker caches...")
        
        self.running: bool = True
        
        # Create task queue, cache, and worker thread for each worker
        for i in range(self.num_workers):
            # NEW: Create independent cache for this worker
            from .unified_model_cache import UnifiedModelCache
            from .config import Config
            
            models_dir = self.models_dir or str(Config.PIPER_MODELS_DIR)
            worker_cache = UnifiedModelCache(
                models_dir=models_dir,
                model_timeout=Config.MODEL_CACHE_TIMEOUT,
                max_cached_models=2
            )
            self.worker_caches.append(worker_cache)
            
            # Use asyncio queue per worker for async compatibility
            task_queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
            self.task_queues.append(task_queue)
            
            # Start worker coroutine with its own cache
            worker_task = asyncio.create_task(self._worker_loop(i, task_queue, worker_cache))
            self.workers.append(worker_task)
            
            logger.info(f"Worker {i} started with independent cache")
        
        logger.info(f"All {self.num_workers} workers ready (lock contention eliminated)")
    
    async def _worker_loop(
        self,
        worker_id: int,
        task_queue: asyncio.Queue,
        worker_cache
    ) -> None:
        """
        Worker loop - continuously process synthesis tasks.
        Each worker has its own cache, eliminating lock contention.
        
        Args:
            worker_id: Worker identifier
            task_queue: Queue for this worker's tasks
            worker_cache: Independent UnifiedModelCache for this worker
        """
        logger.info(f"Worker {worker_id} loop started (cache: {id(worker_cache)})")
        
        while self.running:
            try:
                # Get next task (timeout to check running flag)
                try:
                    task = await asyncio.wait_for(task_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # Process synthesis task
                try:
                    logger.debug(f"Worker {worker_id} processing: {task.request_id}")
                    
                    # NEW: Use worker-specific engine with worker-specific cache
                    from .engine_manager import EngineManager
                    
                    engine = EngineManager(model_cache=worker_cache)
                    
                    # PHASE 2.1: Wrap blocking synthesis in asyncio.to_thread()
                    # Moves ONNX synthesis to ThreadPoolExecutor, keeps event loop responsive
                    audio = await asyncio.to_thread(
                        engine.synthesize,
                        task.text,
                        task.voice_id,
                        task.language_hint,
                        task.request_id
                    )
                    
                    # Set result
                    if audio:
                        task.future.set_result(audio)
                        with self.lock:
                            self.tasks_processed += 1
                    else:
                        error = Exception("Synthesis returned None")
                        task.future.set_exception(error)
                        with self.lock:
                            self.tasks_failed += 1
                    
                    logger.debug(f"Worker {worker_id} completed: {task.request_id}")
                    
                except Exception as e:
                    logger.error(f"Worker {worker_id} synthesis error: {e}", exc_info=True)
                    if not task.future.done():
                        task.future.set_exception(e)
                    with self.lock:
                        self.tasks_failed += 1
                
                finally:
                    task_queue.task_done()
            
            except Exception as e:
                logger.error(f"Worker {worker_id} unexpected error: {e}", exc_info=True)
                await asyncio.sleep(0.1)
    
    async def submit_task(
        self,
        text: str,
        voice_id: str,
        request_id: str,
        language_hint: Optional[str] = None,
        timeout: int = 120
    ) -> bytes:
        """
        Submit synthesis task to worker pool.
        Distributes round-robin across workers.
        
        Args:
            text: Text to synthesize
            voice_id: Voice to use
            request_id: Request ID for tracking
            language_hint: Optional language hint (speeds up by skipping detection)
            timeout: Task timeout in seconds
            
        Returns:
            WAV audio bytes
            
        Raises:
            Exception: If synthesis fails or times out
        """
        if not self.running:
            raise RuntimeError("Worker pool not running")
        
        # Create future for result
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        # Create task
        task = SynthesisTask(
            text=text,
            voice_id=voice_id,
            language_hint=language_hint,
            request_id=request_id,
            future=future,
            submitted_time=time.time()
        )
        
        # Select worker round-robin (deterministic based on request_id)
        worker_idx = hash(request_id) % self.num_workers
        
        try:
            # Submit to worker queue
            self.task_queues[worker_idx].put_nowait(task)
            logger.debug(f"Task {request_id} submitted to worker {worker_idx}")
        except asyncio.QueueFull:
            raise RuntimeError("Worker queue full - too many concurrent requests")
        
        # Wait for result with timeout
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error(f"Task {request_id} timeout after {timeout}s")
            raise TimeoutError(f"Synthesis timeout after {timeout}s")
    
    async def stop(self) -> None:
        """Gracefully stop all workers and drain queues."""
        logger.info("Stopping worker pool...")
        
        self.running = False
        
        # Wait for all queues to drain
        for i, queue in enumerate(self.task_queues):
            try:
                timeout_count = 0
                while not queue.empty() and timeout_count < 10:
                    await asyncio.sleep(0.1)
                    timeout_count += 1
            except Exception as e:
                logger.warning(f"Error draining queue {i}: {e}")
        
        # Cancel all worker tasks
        for i, worker in enumerate(self.workers):
            try:
                worker.cancel()
            except Exception as e:
                logger.warning(f"Error canceling worker {i}: {e}")
        
        logger.info("Worker pool stopped")
    
    def get_stats(self) -> dict:
        """
        Get worker pool statistics.
        
        Returns:
            Dictionary with pool status and per-worker cache stats
        """
        with self.lock:
            # Gather cache stats from each worker
            cache_stats = []
            for i, cache in enumerate(self.worker_caches):
                try:
                    stats = cache.get_cache_stats()
                    cache_stats.append({
                        "worker_id": i,
                        "cached_models": stats["cached_models"],
                        "cached_voices": stats["cached_voices"],
                        "cache_hits": stats["cache_hits"],
                        "cache_misses": stats["cache_misses"],
                        "hit_rate_percent": stats["hit_rate_percent"],
                    })
                except Exception as e:
                    logger.warning(f"Error getting cache stats for worker {i}: {e}")
                    cache_stats.append({"worker_id": i, "error": str(e)})
            
            return {
                "num_workers": self.num_workers,
                "tasks_processed": self.tasks_processed,
                "tasks_failed": self.tasks_failed,
                "queue_depths": [q.qsize() for q in self.task_queues],
                "running": self.running,
                "worker_caches": cache_stats,
            }


# Global worker pool instance
_worker_pool: Optional[ParallelWorkerPool] = None


def get_worker_pool(num_workers: int = 3, models_dir: Optional[str] = None) -> ParallelWorkerPool:
    """
    Get or create global worker pool.
    
    Args:
        num_workers: Number of workers to create
        models_dir: Path to models directory (optional)
        
    Returns:
        Singleton ParallelWorkerPool instance
    """
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = ParallelWorkerPool(num_workers=num_workers, models_dir=models_dir)
    return _worker_pool
