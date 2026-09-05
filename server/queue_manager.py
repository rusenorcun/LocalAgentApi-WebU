"""Tek GPU icin merkezi uretim sirasi (semaphore tabanli)."""
import asyncio
from contextlib import asynccontextmanager

from . import config


class QueueManager:
    def __init__(self, limit: int):
        self._sem = asyncio.Semaphore(limit)
        self._lock = asyncio.Lock()
        self.waiting = 0
        self.active = 0
        self.completed = 0
        self.errors = 0
        # Kullanicinin "Durdur" istegi icin: chat_id -> asyncio.Event
        # Uretim gorevi kaydeder, /stop endpoint'i set eder.
        self._cancels: dict[str, asyncio.Event] = {}

    # ── Iptal kaydi (durdur butonu) ──────────────────────────────────────────
    def register_cancel(self, chat_id: str) -> asyncio.Event:
        """Uretim baslarken cagrilir; bu sohbet icin iptal olayini kaydeder."""
        ev = asyncio.Event()
        self._cancels[chat_id] = ev
        return ev

    def request_cancel(self, chat_id: str) -> bool:
        """/stop: aktif uretim varsa iptal isareti koyar. True = isaretlendi."""
        ev = self._cancels.get(chat_id)
        if ev is not None and not ev.is_set():
            ev.set()
            return True
        return ev is not None

    def clear_cancel(self, chat_id: str, ev: asyncio.Event) -> None:
        """Uretim bitince kaydi temizle (yalniz kendi olayimizsa — yaris korumasi)."""
        if self._cancels.get(chat_id) is ev:
            self._cancels.pop(chat_id, None)

    @property
    def stats(self) -> dict:
        return {
            "queued": self.waiting,
            "active": self.active,
            "completed": self.completed,
            "errors": self.errors,
        }

    @asynccontextmanager
    async def slot(self):
        """Sira yuvasi al. Birakana kadar GPU erisimini serilestirir."""
        async with self._lock:
            self.waiting += 1
        try:
            await self._sem.acquire()
        except asyncio.CancelledError:
            async with self._lock:
                self.waiting -= 1
            raise
        async with self._lock:
            self.waiting -= 1
            self.active += 1
        _error = False
        try:
            yield
        except Exception:
            _error = True
            raise
        finally:
            async with self._lock:
                self.active -= 1
                if _error:
                    self.errors += 1
                else:
                    self.completed += 1
            self._sem.release()


queue = QueueManager(config.MAX_CONCURRENT_GENERATIONS)
