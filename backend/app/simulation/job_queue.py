"""One worker, two lanes. Player talks are taken before resident jobs."""

import asyncio
from collections import deque
from typing import Any


class JobQueue:
    def __init__(self, max_waiting: int) -> None:
        self.max_waiting = max_waiting
        self._players: deque[Any] = deque()
        self._residents: deque[Any] = deque()
        self._waiters: deque[asyncio.Future[None]] = deque()

    def qsize(self) -> int:
        return len(self._players) + len(self._residents)

    def player_count(self) -> int:
        return len(self._players)

    def has_pending_talk(self, token: str, agent_id: str) -> bool:
        return any(_same_talk(job, token, agent_id) for job in self._players)

    def put_nowait(self, job: Any) -> bool:
        """Queue a resident job. False means it was not queued."""
        if self.qsize() >= self.max_waiting:
            return False
        self._residents.append(job)
        self._wake()
        return True

    def put_player(self, job: Any) -> tuple[str, Any | None]:
        """Queue a player talk.

        Returns (status, other). status is ok, replaced, evicted, or busy.
        replaced yields the talk that was overwritten. evicted yields the
        resident job that was dropped to make room.
        """
        for index, existing in enumerate(self._players):
            if _same_talk(existing, job.token, job.agent_id):
                self._players[index] = job
                return "replaced", existing
        if self.qsize() >= self.max_waiting:
            if not self._residents:
                return "busy", None
            dropped = self._residents.popleft()
            self._players.append(job)
            self._wake()
            return "evicted", dropped
        self._players.append(job)
        self._wake()
        return "ok", None

    def get_nowait(self) -> Any:
        if self._players:
            return self._players.popleft()
        if self._residents:
            return self._residents.popleft()
        raise asyncio.QueueEmpty

    async def get(self) -> Any:
        while True:
            try:
                return self.get_nowait()
            except asyncio.QueueEmpty:
                loop = asyncio.get_running_loop()
                waiter: asyncio.Future[None] = loop.create_future()
                self._waiters.append(waiter)
                try:
                    await waiter
                except asyncio.CancelledError:
                    if waiter in self._waiters:
                        self._waiters.remove(waiter)
                    raise

    def _wake(self) -> None:
        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)
                return


def _same_talk(job: Any, token: str, agent_id: str) -> bool:
    return (
        getattr(job, "kind", "") == "talk"
        and getattr(job, "token", "") == token
        and getattr(job, "agent_id", "") == agent_id
    )
