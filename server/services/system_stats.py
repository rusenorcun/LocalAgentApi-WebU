"""Sistem izleci — kaynak kullanımı ve performans metrikleri.

psutil kuruluysa çapraz platform ölçüm yapılır (Windows dahil); kurulu
değilse Linux /proc tabanlı eski yönteme geri dönülür. Tüm ölçümler
senkrondur; async uçlarda asyncio.to_thread ile çağırılmalıdır.
"""
from __future__ import annotations

import os
import platform as _platform
import shutil
import time

from .. import config

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

if psutil is not None:
    # cpu_percent(interval=None) ilk çağrıda 0.0 döner; ilk ölçüm aralığı
    # modül yüklenirken başlasın diye burada bir kez çağrılır.
    psutil.cpu_percent(interval=None)


def _disk_path() -> str:
    p = str(config.DATA_DIR) if config.DATA_DIR else ""
    return p if p and os.path.exists(p) else os.sep


def _cpu_from_proc() -> float:
    """/proc/stat'tan kümülatif CPU yüzdesi (psutil yoksa, yalnız Linux)."""
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        if not line:
            return 0.0
        parts = line.split()
        vals = [float(x) for x in parts[1:9]]
        while len(vals) < 8:
            vals.append(0.0)
        user, nice, system, idle, iowait, irq, softirq, steal = vals
        total = user + nice + system + idle + iowait + irq + softirq + steal
        idle_total = idle + iowait
        if total <= 0:
            return 0.0
        return round(((total - idle_total) / total) * 100, 1)
    except Exception:
        return 0.0


def _memory_from_proc() -> float:
    """/proc/meminfo'dan bellek kullanım yüzdesi (psutil yoksa, yalnız Linux)."""
    try:
        mem_total = mem_available = 0.0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = float(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = float(line.split()[1])
        if mem_total <= 0:
            return 0.0
        return round(((mem_total - mem_available) / mem_total) * 100, 1)
    except Exception:
        return 0.0


def _processes_from_proc() -> int:
    try:
        if os.path.exists("/proc"):
            return len([p for p in os.listdir("/proc") if p.isdigit()])
        import subprocess
        result = subprocess.run(
            ["ps", "-eo", "pid", "--no-headers"], capture_output=True, text=True
        )
        if result.returncode == 0:
            return len([l for l in result.stdout.strip().split("\n") if l.strip()])
    except Exception:
        pass
    return 0


def collect() -> dict:
    """Anlık sistem metrikleri (izleç verisi). psutil yoksa CPU/RAM
    Windows/macOS'ta 0 dönebilir; disk her platformda çalışır."""
    out: dict = {
        "cpu_usage": 0.0,
        "cpu_count": os.cpu_count(),
        "memory_usage": 0.0,
        "memory_used_gb": None,
        "memory_total_gb": None,
        "disk_usage": 0.0,
        "disk_used_gb": None,
        "disk_total_gb": None,
        "active_processes": 0,
        "uptime_seconds": None,
        "load_avg": None,
        "platform": _platform.system() or None,
    }

    if psutil is not None:
        try:
            out["cpu_usage"] = round(psutil.cpu_percent(interval=None), 1)
            out["cpu_count"] = psutil.cpu_count(logical=True)
        except Exception:
            pass
        try:
            vm = psutil.virtual_memory()
            out["memory_usage"] = round(vm.percent, 1)
            out["memory_used_gb"] = round(vm.used / (1024 ** 3), 1)
            out["memory_total_gb"] = round(vm.total / (1024 ** 3), 1)
        except Exception:
            pass
        try:
            out["active_processes"] = len(psutil.pids())
            out["uptime_seconds"] = max(0, int(time.time() - psutil.boot_time()))
        except Exception:
            pass
        try:
            out["load_avg"] = [round(x, 2) for x in psutil.getloadavg()]
        except Exception:
            pass
    else:
        # psutil yok: /proc tabanlı eski yöntem (Linux) + unix geri dönüşleri
        out["cpu_usage"] = _cpu_from_proc()
        out["memory_usage"] = _memory_from_proc()
        out["active_processes"] = _processes_from_proc()
        try:
            with open("/proc/uptime", "r") as f:
                out["uptime_seconds"] = int(float(f.read().split()[0]))
        except Exception:
            pass
        try:
            out["load_avg"] = [round(x, 2) for x in os.getloadavg()]
        except Exception:
            pass

    # Disk her platformda çalışır (shutil, platform bağımsız)
    try:
        total_b, used_b, _ = shutil.disk_usage(_disk_path())
        if total_b > 0:
            out["disk_usage"] = round((used_b / total_b) * 100, 1)
            out["disk_used_gb"] = round(used_b / (1024 ** 3), 1)
            out["disk_total_gb"] = round(total_b / (1024 ** 3), 1)
    except Exception:
        pass

    return out
