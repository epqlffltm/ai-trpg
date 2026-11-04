# shared/ai-core/tests/test_try_image.py

"""
연구·개발용 명령(scripts/try_image.py)의 읽기와 찍기를 검증한다.
그림을 만드는 것은 tests/test_image_providers.py 가 본다.

보는 것.
  - 명령줄: comfyui 는 체크포인트와 크기, gemini 는 모델과 참고 그림을 읽는다
  - 참고 그림의 형식은 확장자로 정하고, 찍는 줄에 씨앗과 토큰 수가 있을 때만 싣는다
"""

import importlib.util
from pathlib import Path

from ai_core.image_provider import GeneratedImage

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'try_image.py'
spec = importlib.util.spec_from_file_location('try_image', SCRIPT)
assert spec is not None and spec.loader is not None
try_image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(try_image)


def test_comfyui_arguments():
    args = try_image.parse_args(['comfyui', '--checkpoint', 'a.safetensors', '--prompt', '비', '--out', 'x.png'])

    request = try_image.request_of(args)

    assert (args.provider, args.checkpoint, args.width, args.url) == (
        'comfyui',
        'a.safetensors',
        1024,
        try_image.COMFYUI_URL,
    )
    assert (request.prompt, request.references, request.seed) == ('비', (), None)


def test_gemini_arguments_read_references(tmp_path: Path):
    face = tmp_path / 'face.JPG'
    face.write_bytes(b'jpg')
    args = try_image.parse_args(['gemini', '--prompt', '비', '--out', 'x.png', '--ref', str(face), '--seed', '3'])

    request = try_image.request_of(args)

    assert (args.model, args.size) == (try_image.GEMINI_MODEL, '1K')
    assert [(image.data, image.mime_type) for image in request.references] == [(b'jpg', 'image/jpeg')]
    assert request.seed == 3


def test_the_report_line():
    local = GeneratedImage(data=b'1234', mime_type='image/png', model='m', seed=9)
    remote = GeneratedImage(data=b'12', mime_type='image/png', model='m', input_tokens=5, output_tokens=6)

    assert try_image.report(local, Path('a.png'), 1.25) == 'a.png (image/png, 4 바이트, 1.2초, 씨앗 9)'
    assert try_image.report(remote, Path('b.png'), 2.0) == 'b.png (image/png, 2 바이트, 2.0초, 토큰 입력 5 출력 6)'
