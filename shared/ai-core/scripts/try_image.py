# shared/ai-core/scripts/try_image.py

"""
그림 provider 를 손으로 불러 보는 연구·개발용 명령(#983). 서버를 띄우지 않고 지시 글 하나로 그림 한 장을 만든다.

    cd shared/ai-core
    uv run python scripts/try_image.py comfyui --checkpoint sdxl.safetensors --prompt "비 오는 도서관" --out rain.png
    uv run python scripts/try_image.py gemini --prompt "비 오는 도서관" --ref face.png --out rain.png

  - comfyui: 이 PC 에서 도는 ComfyUI(기본 http://127.0.0.1:8188)로 Stable Diffusion 계열 모델을 돌린다.
    API 값이 들지 않는다. --workflow 로 ComfyUI 에서 "API 형식으로 저장"한 흐름을 줄 수 있다
    ("{{prompt}}", "{{negative}}", "{{seed}}" 를 바꾼다)
  - gemini: Nano Banana 를 부른다. 키는 환경 변수 GEMINI_API_KEY 에서 읽는다(명령줄에 적지 않는다). 장마다 값이 든다
걸린 시간, 씨앗, 토큰 수를 찍는다. 운영 서버는 이 명령을 쓰지 않는다.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from pydantic import SecretStr

from ai_core.comfyui import ComfyUIProvider, ComfyUISettings
from ai_core.gemini_image import GeminiImageProvider
from ai_core.image_provider import GeneratedImage, ImageProvider, ImageRequest, ReferenceImage
from ai_core.provider import ProviderError

GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com'
GEMINI_MODEL = 'gemini-nano-banana-2.1'
COMFYUI_URL = 'http://127.0.0.1:8188'
# 참고 그림의 확장자 → 형식
MIME_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}


def parse_args(argv: list[str]) -> argparse.Namespace:
    """명령줄을 읽는다."""
    parser = argparse.ArgumentParser(description='그림 provider 를 불러 그림 한 장을 만든다(연구·개발용).')
    sub = parser.add_subparsers(dest='provider', required=True)
    for name in ('comfyui', 'gemini'):
        each = sub.add_parser(name)
        each.add_argument('--prompt', required=True)
        each.add_argument('--negative', default='')
        each.add_argument('--seed', type=int)
        each.add_argument('--out', type=Path, required=True)
    comfy = sub.choices['comfyui']
    comfy.add_argument('--url', default=COMFYUI_URL)
    comfy.add_argument('--checkpoint', required=True)
    comfy.add_argument('--width', type=int, default=1024)
    comfy.add_argument('--height', type=int, default=1024)
    comfy.add_argument('--steps', type=int, default=28)
    comfy.add_argument('--cfg', type=float, default=6.0)
    comfy.add_argument('--sampler', default='euler_ancestral')
    comfy.add_argument('--workflow', type=Path)
    gemini = sub.choices['gemini']
    gemini.add_argument('--model', default=GEMINI_MODEL)
    gemini.add_argument('--aspect', default='1:1')
    gemini.add_argument('--size', default='1K')
    gemini.add_argument('--ref', type=Path, action='append', default=[])
    return parser.parse_args(argv)


def reference_of(path: Path) -> ReferenceImage:
    """참고 그림 파일 하나. 형식은 확장자로 정한다."""
    return ReferenceImage(data=path.read_bytes(), mime_type=MIME_TYPES.get(path.suffix.lower(), 'image/png'))


def comfyui_provider(args: argparse.Namespace, http: httpx.AsyncClient) -> ComfyUIProvider:
    """ComfyUI provider. 흐름 파일을 주면 그것을 쓴다."""
    settings = ComfyUISettings(
        checkpoint=args.checkpoint,
        width=args.width,
        height=args.height,
        steps=args.steps,
        cfg=args.cfg,
        sampler=args.sampler,
    )
    workflow = json.loads(args.workflow.read_text(encoding='utf-8')) if args.workflow else None
    return ComfyUIProvider(http, args.url, settings, workflow=workflow)


def gemini_provider(args: argparse.Namespace, http: httpx.AsyncClient) -> GeminiImageProvider:
    """Nano Banana provider. 키가 없으면 끝낸다."""
    key = os.environ.get('GEMINI_API_KEY', '')
    if not key:
        sys.exit('GEMINI_API_KEY 환경 변수에 키를 넣어 주세요.')
    return GeminiImageProvider(
        http, GEMINI_BASE_URL, SecretStr(key), args.model, aspect_ratio=args.aspect, image_size=args.size
    )


def request_of(args: argparse.Namespace) -> ImageRequest:
    """명령줄의 요청."""
    references = tuple(reference_of(path) for path in getattr(args, 'ref', []))
    return ImageRequest(prompt=args.prompt, references=references, negative=args.negative, seed=args.seed)


def report(image: GeneratedImage, out: Path, seconds: float) -> str:
    """찍을 한 줄."""
    tokens = f', 토큰 입력 {image.input_tokens} 출력 {image.output_tokens}' if image.output_tokens is not None else ''
    seed = f', 씨앗 {image.seed}' if image.seed is not None else ''
    return f'{out} ({image.mime_type}, {len(image.data):,} 바이트, {seconds:.1f}초{seed}{tokens})'


async def run(args: argparse.Namespace) -> int:
    """그림 한 장을 만들어 파일로 적는다. 실패하면 까닭을 찍고 1."""
    async with httpx.AsyncClient() as http:
        provider: ImageProvider = (comfyui_provider if args.provider == 'comfyui' else gemini_provider)(args, http)
        started = time.monotonic()
        try:
            image = await provider.generate(request_of(args))
        except ProviderError as error:
            print(f'실패: {error}', file=sys.stderr)
            return 1
    args.out.write_bytes(image.data)
    print(report(image, args.out, time.monotonic() - started))
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(run(parse_args(sys.argv[1:]))))
