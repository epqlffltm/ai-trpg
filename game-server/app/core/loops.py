# game-server/app/core/loops.py

"""
서버 안에서 몇 초마다 도는 작업을 띄우고 멈추는 법.
라운드의 시계(app/rounds/clock.py)와 청구 정리(app/billing/settler.py)가 쓴다.

작업은 run(stop) 하나만 있으면 된다. stop 이 켜질 때까지 돌다가 끝난다. 서버가 뜰 때 띄우고 꺼질 때 멈춘다(app/main.py).
"""

import asyncio
from dataclasses import dataclass
from typing import Protocol


class Loop(Protocol):
    """몇 초마다 도는 작업의 모양."""

    async def run(self, stop: asyncio.Event) -> None:
        """stop 이 켜질 때까지 돈다."""
        ...


@dataclass(frozen=True)
class Running:
    """돌고 있는 작업. 멈추라고 알리는 것과 도는 작업이다."""

    stop: asyncio.Event
    task: asyncio.Task

    async def halt(self) -> None:
        """멈추라고 알리고, 지금 도는 바퀴가 끝나기를 기다린다."""
        self.stop.set()
        await self.task


def start(loop: Loop, name: str) -> Running:
    """작업을 돌리기 시작한다. name 은 asyncio 작업의 이름이다."""
    stop = asyncio.Event()
    return Running(stop, asyncio.create_task(loop.run(stop), name=name))
