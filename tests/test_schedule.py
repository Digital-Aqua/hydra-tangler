""" The rebuild loop keeps only the newest result. """

import asyncio

import pytest

from hydra_tangler.serve.schedule import RebuildRequest, RebuildScheduler
from hydra_tangler.serve.status import StatusReport


def test_overlapping_requests_publish_the_newest() -> None:
    asyncio.run(_newest())


def test_a_slow_rebuild_is_dropped_when_a_newer_one_arrives() -> None:
    asyncio.run(_drops_stale())


def test_a_save_during_debounce_writes_and_skips_the_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hydra_tangler.serve.schedule.QUIET_SECONDS",
        0.01,
    )
    asyncio.run(_save_wins())


async def _newest() -> None:
    seen: list[int] = []

    async def perform(job: RebuildRequest) -> StatusReport | None:
        seen.append(job.started)
        return StatusReport("idle", job.started, 0)

    scheduler = RebuildScheduler(perform, _ignore, _ignore_failure)
    scheduler.start()
    waiting = [
        scheduler.request(immediate=True, write=False, wait=True)
        for _ in range(4)
    ]
    reports = [await item for item in waiting if item is not None]
    await scheduler.stop()
    assert seen == [4]
    assert [item.errors for item in reports] == [4, 4, 4, 4]


async def _drops_stale() -> None:
    seen: list[int] = []
    gate = asyncio.Event()
    release = asyncio.Event()
    holder: list[RebuildScheduler] = []

    async def perform(job: RebuildRequest) -> StatusReport | None:
        scheduler = holder[0]
        if job.started == 1:
            _ = gate.set()
            _ = await release.wait()
        if job.started != scheduler.generation:
            return None
        seen.append(job.started)
        return StatusReport("idle", job.started, 0)

    scheduler = RebuildScheduler(perform, _ignore, _ignore_failure)
    holder.append(scheduler)
    scheduler.start()
    first = scheduler.request(immediate=True, write=False, wait=True)
    assert first is not None
    _ = await gate.wait()
    second = scheduler.request(immediate=True, write=False, wait=True)
    assert second is not None
    _ = release.set()
    assert (await second).errors == 2
    assert (await first).errors == 2
    await scheduler.stop()
    assert seen == [2]


async def _save_wins() -> None:
    seen: list[RebuildRequest] = []

    async def perform(job: RebuildRequest) -> StatusReport | None:
        seen.append(job)
        return StatusReport("idle", 0, 0)

    scheduler = RebuildScheduler(perform, _ignore, _ignore_failure)
    scheduler.start()
    _ = scheduler.request(immediate=False, write=False, wait=False)
    future = scheduler.request(immediate=True, write=True, wait=True)
    assert future is not None
    await future
    await scheduler.stop()
    assert len(seen) == 1
    assert seen[0].started == 2
    assert seen[0].write is True


def _ignore(report: StatusReport) -> None:
    _ = report


def _ignore_failure(message: str) -> None:
    _ = message


def test_a_rebuild_failure_does_not_stop_the_loop() -> None:
    asyncio.run(_survives_oserror())


async def _survives_oserror() -> None:
    seen: list[int] = []
    errors: list[str] = []

    async def perform(job: RebuildRequest) -> StatusReport | None:
        seen.append(job.started)
        if job.started == 1:
            raise OSError("disk full")
        return StatusReport("idle", 0, 1)

    scheduler = RebuildScheduler(perform, _ignore, errors.append)
    scheduler.start()
    first = scheduler.request(immediate=True, write=False, wait=True)
    assert first is not None
    _ = await first
    second = scheduler.request(immediate=True, write=False, wait=True)
    assert second is not None
    assert (await second).warnings == 1
    await scheduler.stop()
    assert seen == [1, 2]
    assert errors == ["disk full"]
