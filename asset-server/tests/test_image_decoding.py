# asset-server/tests/test_image_decoding.py

"""
그림의 형식을 고르는 것(app/images/formats.py)과 따로 된 프로세스에서 여는 것(app/images/isolation.py,
app/images/decoder.py)을 검증한다. 실제로 프로세스를 띄운다. DB 를 쓰지 않는다.

보는 것.
  - 형식은 파일의 머리로 고른다. 받지 않는 형식과 빈 파일은 None 이다
  - 다시 인코딩한다: 형식과 크기가 그대로이고, EXIF(설명)가 없어지고, 방향은 픽셀에 적용된다.
    뒤에 붙인 바이트도 없어진다
  - 움직이는 그림은 첫 장만 남는다
  - 머리만 흉내 낸 파일, 다른 형식의 파일, 픽셀이 너무 많은 그림, 메모리를 넘는 그림, 시간이 다 된 것은
    열 수 없는 그림이다
  - 출력의 모양이 틀리면 열 수 없는 그림이다
  - 한꺼번에 여는 수를 묶는다
  - 여는 프로세스(decoder.py)는 서버의 코드를 가져오지 않는다(-I 로 돈다)
"""

import asyncio
import io
import warnings
from collections.abc import Iterator
from dataclasses import replace

import pytest
from PIL import Image, ImageCms, PngImagePlugin

from app.images import decoder as decoder_module
from app.images.formats import ImageFormat, check_image_header
from app.images.isolation import (
    DECODER,
    DecodeLimits,
    ImageUnreadableError,
    IsolatedDecoder,
    decoder_command,
    parse_output,
)
from tests.images import animated_webp, encoded, jpeg_bytes, opened, png_bytes, solid, webp_bytes
from tests.test_content_boundary import imported_modules

LIMITS = DecodeLimits(max_pixels=4_000_000, memory_bytes=512 * 1024 * 1024, cpu_seconds=10, wall_seconds=15)


def decoder(limits: DecodeLimits = LIMITS, concurrency: int = 2) -> IsolatedDecoder:
    return IsolatedDecoder(limits, concurrency)


# --- 형식 ---


@pytest.mark.parametrize(
    ('data', 'expected'),
    [
        (png_bytes(), ImageFormat.PNG),
        (jpeg_bytes(), ImageFormat.JPEG),
        (webp_bytes(), ImageFormat.WEBP),
        (b'GIF89a' + b'\x00' * 10, None),
        (b'RIFF\x00\x00\x00\x00WAVE', None),
        (b'RIFF', None),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', None),
        (b'', None),
    ],
    ids=['png', 'jpeg', 'webp', 'gif', 'riff-not-webp', 'short-riff', 'svg', 'empty'],
)
def test_the_format_comes_from_the_header(data: bytes, expected: ImageFormat | None):
    assert check_image_header(data) == expected


# --- 다시 인코딩 ---


@pytest.mark.parametrize(
    ('data', 'image_format', 'pillow_format', 'size'),
    [
        (png_bytes((7, 5)), ImageFormat.PNG, 'PNG', (7, 5)),
        (jpeg_bytes((6, 4)), ImageFormat.JPEG, 'JPEG', (6, 4)),
        (webp_bytes((5, 9)), ImageFormat.WEBP, 'WEBP', (5, 9)),
    ],
    ids=['png', 'jpeg', 'webp'],
)
async def test_an_image_is_encoded_again_in_its_format(
    data: bytes, image_format: ImageFormat, pillow_format: str, size: tuple[int, int]
):
    decoded = await decoder().decode(data, image_format)

    image = opened(decoded.data)
    assert (image.format, image.size, (decoded.width, decoded.height)) == (pillow_format, size, size)


async def test_exif_is_dropped_and_the_orientation_is_applied():
    # 방향 6 은 "오른쪽으로 90도 돌려 본다"다. 가로 4, 세로 2 인 사진이 세로 4, 가로 2 가 된다
    data = jpeg_bytes((4, 2), orientation=6, description='37.5665N 126.9780E')

    decoded = await decoder().decode(data, ImageFormat.JPEG)

    image = opened(decoded.data)
    assert (decoded.width, decoded.height) == (2, 4)
    assert dict(image.getexif()) == {}
    assert b'126.9780E' not in decoded.data


async def test_bytes_hidden_after_the_image_are_gone():
    data = png_bytes() + b'SECRET-PAYLOAD'

    decoded = await decoder().decode(data, ImageFormat.PNG)

    assert b'SECRET-PAYLOAD' not in decoded.data


async def test_a_color_profile_and_text_chunks_are_dropped():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    text = PngImagePlugin.PngInfo()
    text.add_text('Comment', 'HIDDEN-NOTE')
    data = encoded(solid((3, 3), (1, 2, 3)), 'PNG', icc_profile=profile, pnginfo=text)

    decoded = await decoder().decode(data, ImageFormat.PNG)

    image = opened(decoded.data)
    assert ('icc_profile' in image.info, b'HIDDEN-NOTE' in decoded.data) == (False, False)


async def test_only_the_first_frame_of_an_animation_is_kept():
    decoded = await decoder().decode(animated_webp(), ImageFormat.WEBP)

    image = opened(decoded.data)
    assert getattr(image, 'n_frames', 1) == 1
    # 다시 인코딩한 손실 압축이라 값이 조금 흔들린다. 빨강(첫 장)인지만 본다
    red, _, blue = image.convert('RGB').getpixel((0, 0))
    assert (red > 200, blue < 50) == (True, True)


async def test_a_cmyk_jpeg_becomes_rgb():
    data = encoded(solid((3, 3), (0, 255, 255, 0), mode='CMYK'), 'JPEG')

    decoded = await decoder().decode(data, ImageFormat.JPEG)

    assert opened(decoded.data).mode == 'RGB'


# --- 열 수 없는 그림 ---


@pytest.mark.parametrize(
    ('data', 'image_format'),
    [
        (png_bytes()[:20], ImageFormat.PNG),
        (b'\x89PNG\r\n\x1a\n' + b'\x00' * 64, ImageFormat.PNG),
        (jpeg_bytes(), ImageFormat.PNG),
        (png_bytes(), ImageFormat.WEBP),
        (b'', ImageFormat.JPEG),
    ],
    ids=['cut-png', 'header-only', 'jpeg-as-png', 'png-as-webp', 'empty'],
)
async def test_broken_or_mismatched_files_are_unreadable(data: bytes, image_format: ImageFormat):
    with pytest.raises(ImageUnreadableError):
        await decoder().decode(data, image_format)


async def test_too_many_pixels_are_refused_before_decoding():
    limits = replace(LIMITS, max_pixels=1_000_000)
    # 압축하면 작지만 풀면 1,000 × 1,001 픽셀이다
    data = png_bytes((1000, 1001), color=(0, 0, 0))

    assert len(data) < 20_000
    with pytest.raises(ImageUnreadableError):
        await decoder(limits).decode(data, ImageFormat.PNG)
    assert (await decoder(limits).decode(png_bytes((1000, 1000)), ImageFormat.PNG)).width == 1000


async def test_an_image_bigger_than_the_memory_limit_is_unreadable():
    # 6,000 × 6,000 의 RGB 는 풀면 100MB 를 넘는다. 주소 공간을 160MB 로 묶으면 열지 못한다
    limits = replace(LIMITS, max_pixels=40_000_000, memory_bytes=160 * 1024 * 1024)
    data = png_bytes((6000, 6000), color=(0, 0, 0))

    with pytest.raises(ImageUnreadableError):
        await decoder(limits).decode(data, ImageFormat.PNG)
    # 상한을 넉넉히 주면 같은 그림이 열린다. 막은 것은 메모리의 상한이다
    roomy = replace(limits, memory_bytes=1024 * 1024 * 1024)
    assert (await decoder(roomy).decode(data, ImageFormat.PNG)).width == 6000


async def test_a_decode_past_the_wall_clock_is_killed():
    limits = replace(LIMITS, wall_seconds=0.001)

    with pytest.raises(ImageUnreadableError):
        await decoder(limits).decode(png_bytes(), ImageFormat.PNG)


@pytest.fixture
def fake_decoder(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """여는 프로세스를 그 내용의 스크립트로 바꾼다. 서버 쪽(띄우고 기다리고 읽기)만 본다."""

    def install(source: str) -> None:
        script = tmp_path / 'fake_decoder.py'
        script.write_text(source, encoding='utf-8')
        monkeypatch.setattr('app.images.isolation.DECODER', script)

    return install


async def test_a_hanging_decoder_is_killed_at_the_wall_clock(fake_decoder):
    fake_decoder('import time\ntime.sleep(30)\n')
    started = asyncio.get_running_loop().time()

    with pytest.raises(ImageUnreadableError):
        await decoder(replace(LIMITS, wall_seconds=0.3)).decode(png_bytes(), ImageFormat.PNG)

    # 죽이지 않고 기다리면 30초가 걸린다
    assert asyncio.get_running_loop().time() - started < 5


async def test_output_from_a_failed_decoder_is_not_trusted(fake_decoder):
    fake_decoder('import sys\nsys.stdout.buffer.write(b\'{"width": 1, "height": 1}\\nX\')\nsys.exit(1)\n')

    with pytest.raises(ImageUnreadableError):
        await decoder().decode(png_bytes(), ImageFormat.PNG)


@pytest.mark.parametrize(
    'output',
    [
        b'',
        b'not json\n\x89PNG',
        b'{"width": 3}\n\x89PNG',
        b'{"width": 0, "height": 2}\n\x89PNG',
        b'{"width": 3, "height": 2}\n',
    ],
    ids=['empty', 'not-json', 'no-height', 'zero-width', 'no-bytes'],
)
def test_an_odd_output_is_unreadable(output: bytes):
    with pytest.raises(ImageUnreadableError):
        parse_output(output)


def test_the_output_is_read_as_size_and_bytes():
    decoded = parse_output(b'{"width": 3, "height": 2}\n\x89PNG\nrest')

    assert (decoded.width, decoded.height, decoded.data) == (3, 2, b'\x89PNG\nrest')


# --- 격리 ---


def test_the_decoder_runs_isolated_with_its_limits():
    command = decoder_command(ImageFormat.WEBP, LIMITS)

    # -I: 서버의 코드, 현재 폴더, PYTHON* 환경 변수를 읽지 않는다
    assert command[1:] == ['-I', str(DECODER), 'webp', '4000000', str(512 * 1024 * 1024), '10']


def test_the_decoder_imports_nothing_from_the_app():
    assert [name for name in imported_modules(DECODER) if name.startswith(('app', '.'))] == []


async def test_decodes_wait_for_a_free_slot(monkeypatch: pytest.MonkeyPatch):
    running = 0
    most = 0

    async def slow_run(data: bytes, image_format: ImageFormat, limits: DecodeLimits) -> bytes:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.02)
        running -= 1
        return b'{"width": 1, "height": 1}\nx'

    monkeypatch.setattr('app.images.isolation.run_decoder', slow_run)
    shared = decoder(concurrency=2)

    await asyncio.gather(*(shared.decode(b'', ImageFormat.PNG) for _ in range(5)))

    assert most == 2


# --- 여는 프로세스의 함수(같은 프로세스에서 부른다. 상한은 걸지 않는다) ---


@pytest.fixture
def pillow_globals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """여는 함수가 바꾸는 Pillow 의 전역(픽셀 상한, 경고)을 테스트가 끝나면 되돌린다."""
    monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', Image.MAX_IMAGE_PIXELS)
    with warnings.catch_warnings():
        yield


@pytest.mark.usefixtures('pillow_globals')
def test_open_image_refuses_a_mismatched_format():
    with pytest.raises(ValueError, match='형식'):
        decoder_module.open_image(png_bytes(), 'jpeg', 1_000_000)


@pytest.mark.usefixtures('pillow_globals')
def test_open_image_refuses_too_many_pixels_before_loading():
    # 상한을 넘으면 Pillow 가 경고만 하는 구간(두 배 안쪽)도 오류로 친다
    with pytest.raises(Image.DecompressionBombWarning):
        decoder_module.open_image(png_bytes((10, 10)), 'png', 99)
    with pytest.raises(Image.DecompressionBombError):
        decoder_module.open_image(png_bytes((10, 10)), 'png', 40)


@pytest.mark.usefixtures('pillow_globals')
def test_main_writes_the_size_and_the_bytes(monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture):
    limited: list[tuple[int, int]] = []
    monkeypatch.setattr(decoder_module, 'limit_resources', lambda memory, cpu: limited.append((memory, cpu)))
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(webp_bytes((5, 9)))))

    code = decoder_module.main(['webp', '1000000', '268435456', '7'])

    decoded = parse_output(capsysbinary.readouterr().out)
    assert (code, limited, decoded.width, decoded.height) == (0, [(268435456, 7)], 5, 9)


@pytest.mark.usefixtures('pillow_globals')
def test_main_says_one_for_an_unreadable_image(monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture):
    monkeypatch.setattr(decoder_module, 'limit_resources', lambda memory, cpu: None)
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(b'\x89PNG\r\n\x1a\nbroken')))

    assert decoder_module.main(['png', '1000000', '268435456', '7']) == 1
    assert capsysbinary.readouterr().out == b''
