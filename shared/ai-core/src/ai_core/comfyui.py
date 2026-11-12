# shared/ai-core/src/ai_core/comfyui.py

"""
로컬의 ComfyUI 로 Stable Diffusion 계열 모델을 돌리는 image provider(#983). 연구와 개발, 시험용이다.

운영의 장면 그림은 외부 API(ai_core/gemini_image.py)로 만든다. 이 provider 는 같은 모양이라 바꿔 끼울 수 있다.
API 값이 들지 않지만 GPU 하나는 한 번에 한 장을 그리고, 공급자의 안전 필터가 없다(거르는 것은 쓰는 쪽의 몫이다).

ComfyUI 의 API(서버 곁에서 도는 ComfyUI, 보통 http://127.0.0.1:8188).
  1. POST /prompt {"prompt": 작업 흐름, "client_id"} → {"prompt_id"}. 흐름이 틀리면 400
  2. GET /history/{prompt_id} 를 poll_interval 마다 본다. 끝나면 outputs 의 노드마다 images 가 실린다.
     status.status_str 이 error 면 실패다(generation_failed)
  3. GET /view?filename&subfolder&type 으로 그림의 바이트를 받는다
  한 장의 상한(timeout)이 지나면 timeout 이다. ComfyUI 의 줄에 남은 일은 지우지 않는다(연구용이라 그대로 둔다).

작업 흐름(workflow).
  - 기본은 SDXL 계열의 글→그림 흐름이다(default_workflow). 체크포인트 이름, 크기, 단계, CFG, 샘플러를 설정으로 받는다
  - 연구용으로 ComfyUI 에서 "API 형식으로 저장"한 흐름을 그대로 쓸 수 있다(workflow). 흐름 안의 글이 정확히
    "{{prompt}}", "{{negative}}", "{{seed}}" 인 칸을 그 값으로 바꾼다(fill_template).
    그림은 어느 노드의 images 든 첫 장을 쓴다
  - 참고 그림(IP-Adapter 같은 것)은 기본 흐름이 받지 않는다(supports_references 가 False). 연구용 흐름으로 따로 해 본다
"""

import asyncio
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from ai_core.image_http import get_bytes, get_json, post_json
from ai_core.image_provider import MALFORMED, REFERENCES_UNSUPPORTED, GeneratedImage, ImageRequest
from ai_core.provider import ProviderError

# 씨앗의 범위(ComfyUI 의 KSampler 가 받는 정수)
SEED_LIMIT = 2**32
# 바꿔 넣는 자리의 이름
PLACEHOLDERS = ('{{prompt}}', '{{negative}}', '{{seed}}')
# 기본 흐름이 그리지 말라고 하는 것
DEFAULT_NEGATIVE = 'lowres, blurry, bad anatomy, extra fingers, text, watermark, signature'
# 실패한 작업의 상태 이름
ERROR_STATUS = 'error'


@dataclass(frozen=True)
class ComfyUISettings:
    """기본 흐름의 설정. checkpoint 는 ComfyUI 의 models/checkpoints 안의 파일 이름이다."""

    checkpoint: str
    width: int = 1024
    height: int = 1024
    steps: int = 28
    cfg: float = 6.0
    sampler: str = 'euler_ancestral'
    scheduler: str = 'normal'


def default_workflow(settings: ComfyUISettings) -> dict[str, Any]:
    """SDXL 계열의 글→그림 흐름(API 형식). 지시와 씨앗의 자리는 비워 둔다(fill_template 이 채운다)."""
    return {
        '4': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': settings.checkpoint}},
        '5': {
            'class_type': 'EmptyLatentImage',
            'inputs': {'width': settings.width, 'height': settings.height, 'batch_size': 1},
        },
        '6': {'class_type': 'CLIPTextEncode', 'inputs': {'text': '{{prompt}}', 'clip': ['4', 1]}},
        '7': {'class_type': 'CLIPTextEncode', 'inputs': {'text': '{{negative}}', 'clip': ['4', 1]}},
        '3': {
            'class_type': 'KSampler',
            'inputs': {
                'seed': '{{seed}}',
                'steps': settings.steps,
                'cfg': settings.cfg,
                'sampler_name': settings.sampler,
                'scheduler': settings.scheduler,
                'denoise': 1.0,
                'model': ['4', 0],
                'positive': ['6', 0],
                'negative': ['7', 0],
                'latent_image': ['5', 0],
            },
        },
        '8': {'class_type': 'VAEDecode', 'inputs': {'samples': ['3', 0], 'vae': ['4', 2]}},
        '9': {'class_type': 'SaveImage', 'inputs': {'filename_prefix': 'ai-trpg', 'images': ['8', 0]}},
    }


def fill_template(node: Any, values: dict[str, Any]) -> Any:
    """흐름 안의 글이 정확히 자리의 이름인 칸을 그 값으로 바꾼 사본. 씨앗은 정수 그대로 들어간다."""
    if isinstance(node, dict):
        return {key: fill_template(value, values) for key, value in node.items()}
    if isinstance(node, list):
        return [fill_template(value, values) for value in node]
    if isinstance(node, str) and node in values:
        return values[node]
    return node


def seed_of(request: ImageRequest) -> int:
    """쓸 씨앗. 요청에 없으면 고른다."""
    return request.seed if request.seed is not None else secrets.randbelow(SEED_LIMIT)


def filled_workflow(template: dict[str, Any], request: ImageRequest, seed: int) -> dict[str, Any]:
    """요청의 지시와 씨앗을 채운 흐름. 그리지 말 것이 비어 있으면 기본의 것을 쓴다."""
    negative = request.negative or DEFAULT_NEGATIVE
    return fill_template(template, dict(zip(PLACEHOLDERS, (request.prompt, negative, seed), strict=True)))


def prompt_id_of(answer: Any) -> str:
    """POST /prompt 의 답에서 작업의 id. 없으면 ProviderError(malformed)."""
    prompt_id = answer.get('prompt_id') if isinstance(answer, dict) else None
    if not isinstance(prompt_id, str) or not prompt_id:
        raise ProviderError(MALFORMED)
    return prompt_id


def first_image(entry: dict[str, Any]) -> dict[str, str] | None:
    """끝난 작업의 기록에서 첫 그림의 위치(filename, subfolder, type). 아직 없으면 None."""
    outputs = entry.get('outputs')
    for output in outputs.values() if isinstance(outputs, dict) else []:
        images = output.get('images') if isinstance(output, dict) else None
        if isinstance(images, list) and images and isinstance(images[0], dict) and images[0].get('filename'):
            image = images[0]
            return {
                'filename': str(image['filename']),
                'subfolder': str(image.get('subfolder', '')),
                'type': str(image.get('type', 'output')),
            }
    return None


def failed(entry: dict[str, Any]) -> bool:
    """작업이 실패로 끝났는가."""
    status = entry.get('status')
    return isinstance(status, dict) and status.get('status_str') == ERROR_STATUS


def image_from_history(history: Any, prompt_id: str) -> dict[str, str] | None:
    """기록에서 그 작업의 첫 그림의 위치. 아직 끝나지 않았으면 None, 실패했으면 ProviderError(generation_failed)."""
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        return None
    if failed(entry):
        raise ProviderError('generation_failed')
    return first_image(entry)


@dataclass
class ComfyUIProvider:
    """
    ComfyUI 를 부르는 것. model 은 기록에 남길 이름이다(보통 체크포인트의 이름).
    workflow 를 주면 기본 흐름 대신 그것을 쓴다(연구용). timeout 은 한 장의 상한(초)이다.
    """

    @property
    def kind(self) -> str:
        """종류. 클래스마다 정해져 있다."""
        return 'comfyui'

    @property
    def supports_references(self) -> bool:
        """참고 그림을 받는가. 클래스마다 정해져 있다."""
        return False

    http: httpx.AsyncClient
    base_url: str
    settings: ComfyUISettings
    workflow: dict[str, Any] | None = None
    timeout: float = 300.0
    poll_interval: float = 1.0
    request_timeout: float = 30.0
    client_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def model(self) -> str:
        return self.settings.checkpoint

    def url(self, path: str) -> str:
        return f'{self.base_url.rstrip("/")}{path}'

    async def submit(self, workflow: dict[str, Any]) -> str:
        """흐름을 줄에 넣고 작업의 id 를 받는다."""
        body = {'prompt': workflow, 'client_id': self.client_id}
        return prompt_id_of(await post_json(self.http, self.url('/prompt'), body, {}, self.request_timeout))

    async def wait_for(self, prompt_id: str) -> dict[str, str]:
        """작업이 끝날 때까지 기록을 보고 첫 그림의 위치를 받는다."""
        while True:
            history = await get_json(self.http, self.url(f'/history/{prompt_id}'), self.request_timeout)
            image = image_from_history(history, prompt_id)
            if image is not None:
                return image
            await asyncio.sleep(self.poll_interval)

    async def draw(self, request: ImageRequest, seed: int) -> GeneratedImage:
        """흐름을 넣고 기다려 그림을 받는다."""
        template = self.workflow if self.workflow is not None else default_workflow(self.settings)
        prompt_id = await self.submit(filled_workflow(template, request, seed))
        location = await self.wait_for(prompt_id)
        data, mime_type = await get_bytes(self.http, self.url('/view'), location, self.request_timeout)
        return GeneratedImage(data=data, mime_type=mime_type, model=self.model, seed=seed)

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        """그림 한 장을 만든다. 참고 그림은 받지 않는다."""
        if request.references:
            raise ProviderError(REFERENCES_UNSUPPORTED)
        try:
            async with asyncio.timeout(self.timeout):
                return await self.draw(request, seed_of(request))
        except TimeoutError as exc:
            raise ProviderError('timeout') from exc
