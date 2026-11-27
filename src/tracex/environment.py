from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass
import os
import platform
import socket
from typing import Any, Dict, Optional

_STATIC_CACHE: Optional[Dict[str, str]] = None
_WIN_RAM_READY = False

if os.name == "nt":
    try:
        from ctypes import wintypes

        class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _psapi = ctypes.WinDLL("psapi", use_last_error=True)

        _k32.GetCurrentProcess.argtypes = []
        _k32.GetCurrentProcess.restype = wintypes.HANDLE

        _psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        _psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        _WIN_RAM_READY = True
    except Exception:
        _WIN_RAM_READY = False


@dataclass
class EnvironmentDto:
    app_version: str
    environment_name: str
    os_name: str
    os_version: str
    device_model: str
    hostname: str
    runtime_version: str
    process_ram_mb: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _get_hostname() -> str:
    try:
        return socket.gethostname() or "unknown"
    except OSError:
        return "unknown"


def _get_static_env() -> Dict[str, str]:
    global _STATIC_CACHE
    if _STATIC_CACHE is None:
        hostname = _get_hostname()
        device_model = platform.machine() or hostname or "unknown"
        _STATIC_CACHE = {
            "os_name": platform.system() or "unknown",
            "os_version": platform.release() or "unknown",
            "device_model": device_model,
            "hostname": hostname,
            "runtime_version": platform.python_version(),
        }
    return _STATIC_CACHE


def _get_process_ram_mb() -> float:
    if os.name == "nt":
        if not _WIN_RAM_READY:
            return 0.0
        try:
            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            handle = _k32.GetCurrentProcess()
            if _psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return float(round(int(counters.WorkingSetSize) / (1024 * 1024), 2))
        except Exception:
            return 0.0
    else:
        try:
            import resource

            rss = int(getattr(resource, "getrusage")(getattr(resource, "RUSAGE_SELF")).ru_maxrss)
            divisor = 1024 * 1024 if platform.system() == "Darwin" else 1024
            return float(round(rss / divisor, 2))
        except Exception:
            return 0.0
    return 0.0


def collect_environment(app_version: str, environment_name: str = "production") -> EnvironmentDto:
    static = _get_static_env()
    return EnvironmentDto(
        app_version=app_version or "1.0.0",
        environment_name=environment_name or "production",
        os_name=static["os_name"],
        os_version=static["os_version"],
        device_model=static["device_model"],
        hostname=static["hostname"],
        runtime_version=static["runtime_version"],
        process_ram_mb=_get_process_ram_mb(),
    )