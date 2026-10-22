# asset-server/app/images/isolation.py

"""
그림을 따로 된 프로세스에서 연다(#566). 여는 일은 app/images/decoder.py 가 하고, 여기는 그 프로세스를 띄우고 기다린다.

  - 프로세스는 python -I 로 띄운다. 서버의 코드와 현재 폴더, 환경 변수(PYTHON*)를 읽지 않는다.
  - 메모리와 CPU 의 상한은 그 프로세스가 스스로 건다. 여기는 벽시계의 상한을 걸고, 넘으면 죽인다.
  - 한꺼번에 여는 수를 묶는다(Semaphore). 큰 그림 여럿이 동시에 와도 상한 × 그 수까지만 메모리를 쓴다.
    기다리는 동안 DB 연결을 잡고 있지 않는다(서비스가 연결을 잡기 전에 연다).
  - 열 수 없으면(형식이 다르다, 망가졌다, 상한을 넘었다, 시간이 다 됐다) ImageUnreadableError 다. 까닭은 나누지 않는다.
  - 프로세스를 띄우지 못하면(서버의 문제) OSError 가 그대로 올라간다. 500 이다.
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.images.formats import ImageFormat

DECODER = Path(__file__).with_name('decoder.py')


class ImageUnreadableError(Exception):
    """그림을 열 수 없다. 형식이 다르거나, 망가졌거나, 상한을 넘었다."""


@dataclass(frozen=True)
class DecodeLimits:
    """여는 프로세스 하나의 상한. 픽셀 수, 주소 공간(바이트), CPU 시간(초), 벽시계(초)."""

    max_pixels: int
    memory_bytes: int
    cpu_seconds: int
    wall_seconds: float


@dataclass(frozen=True)
class DecodedImage:
    """다시 인코딩한 그림과 그 크기."""

    data: bytes
    width: int
    height: int


def decoder_command(image_format: ImageFormat, limits: DecodeLimits) -> list[str]:
    """여는 프로세스의 명령줄."""
    return [
        sys.executable,
        '-I',
        str(DECODER),
        image_format.value,
        str(limits.max_pixels),
        str(limits.memory_bytes),
        str(limits.cpu_seconds),
    ]


def parse_output(output: bytes) -> DecodedImage:
    """여는 프로세스의 출력(첫 줄의 크기, 그 뒤의 바이트)을 읽는다. 모양이 틀리면 ImageUnreadableError."""
    header, separator, data = output.partition(b'\n')
    try:
        size = json.loads(header)
        width, height = int(size['width']), int(size['height'])
    except (ValueError, KeyError, TypeError) as error:
        raise ImageUnreadableError from error
    if not separator or not data or width < 1 or height < 1:
        raise ImageUnreadableError
    return DecodedImage(data, width, height)


async def run_decoder(data: bytes, image_format: ImageFormat, limits: DecodeLimits) -> bytes:
    """여는 프로세스를 돌리고 출력을 돌려준다. 실패했거나 시간이 다 됐으면 ImageUnreadableError."""
    process = await asyncio.create_subprocess_exec(
        *decoder_command(image_format, limits),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={},
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(data), timeout=limits.wall_seconds)
    except TimeoutError as error:
        process.kill()
        await process.wait()
        raise ImageUnreadableError from error
    if process.returncode != 0:
        raise ImageUnreadableError
    return output


class ImageDecoder(Protocol):
    """그림을 여는 것의 모양. 테스트는 가짜(tests/images.py)를 쓸 수 있다."""

    async def decode(self, data: bytes, image_format: ImageFormat) -> DecodedImage:
        """그림을 열어 다시 인코딩한다. 열 수 없으면 ImageUnreadableError."""
        ...


@dataclass
class IsolatedDecoder:
    """따로 된 프로세스에서 그림을 여는 것. 앱에 하나 둔다(app.state.image_decoder). 한꺼번에 concurrency 개까지다."""

    limits: DecodeLimits
    concurrency: int
    slots: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self.slots = asyncio.Semaphore(self.concurrency)

    async def decode(self, data: bytes, image_format: ImageFormat) -> DecodedImage:
        """그림을 열어 다시 인코딩한다. 열 수 없으면 ImageUnreadableError."""
        async with self.slots:
            return parse_output(await run_decoder(data, image_format, self.limits))
