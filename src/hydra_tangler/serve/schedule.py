""" Debounce rebuilds and publish only the newest one.

A change waits for a quiet period. Open, save, and an explicit
rebuild skip that wait. Work that is still running when a newer
request arrives may finish, but its result is dropped. This module
does not read Markdown or speak JSON-RPC.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import final

from hydra_tangler.serve.status import StatusReport

# Same quiet period as the file watcher, so a burst of keystrokes
# becomes one rebuild.
QUIET_SECONDS = 0.3

Perform = Callable[["RebuildRequest"], Awaitable[StatusReport | None]]
Notify = Callable[[StatusReport], None]


@dataclass(frozen=True)
class RebuildRequest:
    """ One generation of the scheduler and whether it should write. """

    started: int
    write: bool


@final
class RebuildScheduler:
    """ Coalesce rebuild requests onto a single loop. """

    def __init__(self, perform: Perform, on_status: Notify) -> None:
        self._perform = perform
        self._on_status = on_status
        self.generation = 0
        self._immediate = False
        self._write = False
        self._busy = False
        self._stopped = False
        self._last = StatusReport("idle", 0, 0)
        self._wake = asyncio.Event()
        self._waiters: list[asyncio.Future[StatusReport]] = []
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """ Begin the loop. A second call does nothing. """
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """ Finish the current pass and cancel anyone still waiting. """
        self._stopped = True
        self._wake.set()
        task = self._task
        if task is not None:
            await task
        self._cancel_waiters()

    def request(
        self,
        *,
        immediate: bool,
        write: bool,
        wait: bool,
    ) -> asyncio.Future[StatusReport] | None:
        """ Ask for a rebuild. The returned future finishes with the newest. """
        self.generation += 1
        if immediate:
            self._immediate = True
        if write:
            self._write = True
        self._signal_busy()
        self._wake.set()
        if not wait:
            return None
        future = asyncio.get_running_loop().create_future()
        self._waiters.append(future)
        return future

    async def _loop(self) -> None:
        while not self._stopped:
            _ = await self._wake.wait()
            if self._stopped:
                return
            self._wake.clear()
            await self._one()

    async def _one(self) -> None:
        started = self.generation
        if not await self._ready(started):
            return
        job = RebuildRequest(started, self._take_write())
        report = await self._perform(job)
        if self._stopped or started != self.generation or report is None:
            return
        self._finish(report)

    async def _ready(self, started: int) -> bool:
        immediate = self._immediate
        self._immediate = False
        if self._stopped:
            return False
        if immediate:
            return True
        await asyncio.sleep(QUIET_SECONDS)
        return not self._stopped and started == self.generation

    def _take_write(self) -> bool:
        write = self._write
        self._write = False
        return write

    def _signal_busy(self) -> None:
        if self._busy:
            return
        self._busy = True
        previous = self._last
        busy = StatusReport("busy", previous.errors, previous.warnings)
        self._on_status(busy)

    def _finish(self, report: StatusReport) -> None:
        self._busy = False
        idle = StatusReport("idle", report.errors, report.warnings)
        self._last = idle
        self._on_status(idle)
        waiters = self._waiters
        self._waiters = []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(idle)

    def _cancel_waiters(self) -> None:
        waiters = self._waiters
        self._waiters = []
        for waiter in waiters:
            if not waiter.done():
                _ = waiter.cancel()
