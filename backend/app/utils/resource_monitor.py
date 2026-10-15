"""
Resource Monitor
Measures peak RAM and VRAM (GPU memory) usage during pipeline stages.
"""

import os
import shutil
import subprocess
import threading
import time
from typing import Optional


class ResourceMonitor:
    def __init__(self, interval_seconds: float = 0.5):
        self.interval = interval_seconds
        self.peak_ram_mb: float = 0.0
        self.peak_vram_mb: float = 0.0
        self.elapsed_seconds: float = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0
        self._nvidia_smi = shutil.which("nvidia-smi")

    def _get_ram_mb(self) -> float:
        """Read VmRSS from /proc/self/status if available."""
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # Format: VmRSS:     12345 kB
                        parts = line.split()
                        return float(parts[1]) / 1024.0
        except Exception:
            pass
        return 0.0

    def _get_vram_mb(self) -> float:
        """Query nvidia-smi for current GPU memory used."""
        if not self._nvidia_smi:
            return 0.0
        try:
            res = subprocess.run(
                [self._nvidia_smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=1
            )
            if res.returncode == 0:
                lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip().isdigit()]
                if lines:
                    return float(lines[0])
        except Exception:
            pass
        return 0.0

    def _sample_loop(self):
        while self._running:
            ram = self._get_ram_mb()
            if ram > self.peak_ram_mb:
                self.peak_ram_mb = ram

            vram = self._get_vram_mb()
            if vram > self.peak_vram_mb:
                self.peak_vram_mb = vram

            time.sleep(self.interval)

    def start(self):
        self._start_time = time.time()
        self.peak_ram_mb = self._get_ram_mb()
        self.peak_vram_mb = self._get_vram_mb()
        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.elapsed_seconds = round(time.time() - self._start_time, 2)
        # Final sample
        ram = self._get_ram_mb()
        if ram > self.peak_ram_mb:
            self.peak_ram_mb = round(ram, 1)
        vram = self._get_vram_mb()
        if vram > self.peak_vram_mb:
            self.peak_vram_mb = round(vram, 1)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
