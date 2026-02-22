"""System resource monitoring for adaptive concurrency."""

import os

import psutil


class ResourceMonitor:
    """Monitor system resources and calculate safe concurrency levels."""

    def __init__(
        self,
        max_memory_percent: float = 75.0,
        min_free_memory_mb: int = 512,
        max_workers: int = 10,
        min_workers: int = 1,
    ) -> None:
        self.max_memory_percent = max_memory_percent
        self.min_free_memory_mb = min_free_memory_mb
        self.max_workers = max_workers
        self.min_workers = min_workers

    def calculate_optimal_workers(self) -> int:
        """Calculate the optimal number of concurrent workers.

        Heuristic:
        - Each browser tab uses roughly 150-300 MB.
        - We estimate 200 MB per worker.
        - We cap at CPU_count * 2 (I/O bound work).
        - We cap at max_workers.
        - If memory is already above threshold, use minimum.
        """
        mem = psutil.virtual_memory()
        cpu_count = os.cpu_count() or 2

        # If memory already high, use minimum
        if mem.percent >= self.max_memory_percent:
            return self.min_workers

        # Available memory in MB
        available_mb = mem.available / (1024 * 1024)
        if available_mb < self.min_free_memory_mb:
            return self.min_workers

        # Reserve min_free_memory_mb, use the rest
        usable_mb = available_mb - self.min_free_memory_mb
        memory_based = int(usable_mb / 200)  # ~200MB per browser tab

        # CPU-based cap
        cpu_based = cpu_count * 2

        # Take the minimum of all caps
        workers = min(memory_based, cpu_based, self.max_workers)
        return max(workers, self.min_workers)

    def get_snapshot(self) -> dict:
        """Return current resource snapshot for logging."""
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": mem.percent,
            "memory_available_mb": round(mem.available / (1024 * 1024)),
            "optimal_workers": self.calculate_optimal_workers(),
        }
