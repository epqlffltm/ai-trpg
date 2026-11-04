# shared/ai-core/tests/test_image_providers.py

"""
그림 provider(ai_core/gemini_image.py, ai_core/comfyui.py, ai_core/fake.py 의 FakeImageProvider)를 검증한다.

실제 API 와 ComfyUI 를 부르지 않는다. httpx 의 가짜 전송이 Google 과 ComfyUI 인 척 답한다.
응답의 모양은 Google 의 문서(그림 만들기, 2026-11-04)와 ComfyUI 의 API(/prompt, /history, /view)를 따랐다.

보는 것.
  - Gemini: 주소와 머리(키는 주소에 싣지 않는다), 참고 그림이 앞이고 종류마다 상한, 그림만 달라고 함, 비율과 크기,
    저장하지 않음. 생각 그림은 읽지 않고 마지막 그림을 쓴다. 토큰 수. 막혔으면 refused, 그림이 없으면 no_image,
    읽을 수 없는 그림은 malformed. 상태 코드와 대기 시간, 연결 실패. 오류에 키와 본문을 싣지 않는다
  - ComfyUI: 기본 흐름에 지시와 씨앗을 채움, 연구용 흐름의 자리 바꾸기, 끝날 때까지 기록을 보고 그림을 받음,
    실패한 작업, 시간 상한, 참고 그림은 받지 않음, id 가 없는 답
  - 가짜: 정해 둔 그림, 실패, 참고 그림을 받지 않는 흉내
"""

import base64
import json

import httpx
import pytest
from pydantic import SecretStr

from ai_core.comfyui import (
    DEFAULT_NEGATIVE,
    ComfyUIProvider,
    ComfyUISettings,
    default_workflow,
    fill_template,
    filled_workflow,
)
from ai_core.fake import FAKE_PNG, FakeImageProvider
from ai_core.gemini_image import (
    MAX_CHARACTER_REFERENCES,
    MAX_OBJECT_REFERENCES,
    GeminiImageProvider,
    generate_url,
    request_body,
)
from ai_core.image_provider import ImageRequest, ReferenceImage, ReferenceKind
from ai_core.provider import ProviderError

BASE_URL = 'https://generativelanguage.googleapis.com/'
MODEL = 'gemini-nano-banana-2.1'
KEY = 'g-test-key'
PROMPT = '비 오는 도서관, 창가에 선 사서.'
SECRET = '이 지시는 오류에 실리면 안 된다.'
B64 = base64.b64encode(FAKE_PNG).decode('ascii')


def gemini(handler) -> GeminiImageProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiImageProvider(client, BASE_URL, SecretStr(KEY), MODEL, aspect_ratio='3:4', image_size='2K')


def answer(parts: list[dict], finish: str = 'STOP', **extra) -> httpx.Response:
    body = {
        'candidates': [{'content': {'role': 'model', 'parts': parts}, 'finishReason': finish}],
        'usageMetadata': {'promptTokenCount': 300, 'candidatesTokenCount': 1120},
        **extra,
    }
    return httpx.Response(200, json=body)


def reference(kind: ReferenceKind, n: int) -> ReferenceImage:
    return ReferenceImage(data=bytes([n]), mime_type='image/png', kind=kind)


async def test_gemini_sends_references_first_and_only_asks_for_an_image():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer([{'text': '그렸다'}, {'inlineData': {'mimeType': 'image/png', 'data': B64}}])

    face = reference(ReferenceKind.CHARACTER, 1)
    image = await gemini(handler).generate(ImageRequest(prompt=PROMPT, references=(face,)))

    (request,) = seen
    assert str(request.url) == f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent'
    assert request.headers['x-goog-api-key'] == KEY and KEY not in str(request.url)
    body = json.loads(request.content)
    parts = body['contents'][0]['parts']
    assert parts == [{'inlineData': {'mimeType': 'image/png', 'data': 'AQ=='}}, {'text': PROMPT}]
    assert body['generationConfig'] == {
        'responseModalities': ['IMAGE'],
        'imageConfig': {'aspectRatio': '3:4', 'imageSize': '2K'},
    }
    assert body['store'] is False
    assert (image.data, image.mime_type, image.model) == (FAKE_PNG, 'image/png', MODEL)
    assert (image.input_tokens, image.output_tokens) == (300, 1120)


def test_gemini_caps_references_per_kind():
    characters = tuple(reference(ReferenceKind.CHARACTER, n) for n in range(MAX_CHARACTER_REFERENCES + 2))
    objects = tuple(reference(ReferenceKind.OBJECT, 100 + n) for n in range(MAX_OBJECT_REFERENCES + 1))

    body = request_body(ImageRequest(prompt=PROMPT, references=characters + objects), '1:1', '1K')

    images = [part for part in body['contents'][0]['parts'] if 'inlineData' in part]
    assert len(images) == MAX_CHARACTER_REFERENCES + MAX_OBJECT_REFERENCES
    assert generate_url('http://g/', 'm') == 'http://g/v1beta/models/m:generateContent'


async def test_gemini_skips_thought_images_and_takes_the_last_image():
    other = base64.b64encode(b'\x89PNGfinal').decode('ascii')
    parts = [
        {'inlineData': {'mimeType': 'image/png', 'data': B64}, 'thought': True},
        {'inline_data': {'mime_type': 'image/webp', 'data': other}},
    ]

    image = await gemini(lambda request: answer(parts)).generate(ImageRequest(prompt=PROMPT))

    assert (image.data, image.mime_type) == (b'\x89PNGfinal', 'image/webp')


@pytest.mark.parametrize(
    ('response', 'reason'),
    [
        (httpx.Response(200, json={'promptFeedback': {'blockReason': 'PROHIBITED_CONTENT'}}), 'refused'),
        (answer([], finish='IMAGE_SAFETY'), 'refused'),
        (answer([{'text': SECRET}]), 'no_image'),
        (answer([{'inlineData': {'mimeType': 'image/png', 'data': '%%%'}}]), 'malformed'),
        (answer([{'inlineData': {'mimeType': 'image/png', 'data': ''}}]), 'malformed'),
        (httpx.Response(429, headers={'Retry-After': '7'}, text=SECRET), 'status_429'),
        (httpx.Response(200, text=SECRET), 'not_json'),
    ],
)
async def test_gemini_failures_are_named_without_secrets(response: httpx.Response, reason: str):
    with pytest.raises(ProviderError) as caught:
        await gemini(lambda request: response).generate(ImageRequest(prompt=SECRET))

    assert str(caught.value) == reason
    assert SECRET not in str(caught.value) and KEY not in str(caught.value)
    if reason == 'status_429':
        assert caught.value.retry_after == 7


async def test_gemini_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused')

    with pytest.raises(ProviderError, match='unreachable'):
        await gemini(handler).generate(ImageRequest(prompt=PROMPT))


SETTINGS = ComfyUISettings(checkpoint='sdxl.safetensors', width=832, height=1216, steps=20)


class FakeComfy:
    """ComfyUI 흉내. 작업을 받고, pending 번 기록을 비워 둔 뒤 끝난 기록을 돌려준다."""

    def __init__(self, pending: int = 1, status: str = 'success', prompt_answer: dict | None = None) -> None:
        self.pending = pending
        self.status = status
        self.prompt_answer = prompt_answer if prompt_answer is not None else {'prompt_id': 'p1', 'node_errors': {}}
        self.submitted: list[dict] = []
        self.views: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == 'POST' and request.url.path == '/prompt':
            self.submitted.append(json.loads(request.content))
            return httpx.Response(200, json=self.prompt_answer)
        if request.url.path == '/history/p1':
            if self.pending > 0:
                self.pending -= 1
                return httpx.Response(200, json={})
            outputs = {'9': {'images': [{'filename': 'ai-trpg_0001.png', 'subfolder': '', 'type': 'output'}]}}
            if self.status == 'error':
                outputs = {}
            return httpx.Response(200, json={'p1': {'outputs': outputs, 'status': {'status_str': self.status}}})
        if request.url.path == '/view':
            self.views.append(dict(request.url.params))
            return httpx.Response(200, content=FAKE_PNG, headers={'Content-Type': 'image/png'})
        return httpx.Response(404)


def comfy(handler, **kwargs) -> ComfyUIProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ComfyUIProvider(client, 'http://127.0.0.1:8188/', SETTINGS, poll_interval=0, **kwargs)


async def test_comfyui_fills_the_default_workflow_and_waits_for_the_image():
    server = FakeComfy(pending=2)

    image = await comfy(server).generate(ImageRequest(prompt=PROMPT, seed=42))

    (sent,) = server.submitted
    workflow = sent['prompt']
    assert workflow['6']['inputs']['text'] == PROMPT
    assert workflow['7']['inputs']['text'] == DEFAULT_NEGATIVE
    assert workflow['3']['inputs']['seed'] == 42
    assert workflow['5']['inputs'] == {'width': 832, 'height': 1216, 'batch_size': 1}
    assert workflow['4']['inputs']['ckpt_name'] == 'sdxl.safetensors'
    assert server.views == [{'filename': 'ai-trpg_0001.png', 'subfolder': '', 'type': 'output'}]
    assert (image.data, image.mime_type, image.model, image.seed) == (FAKE_PNG, 'image/png', 'sdxl.safetensors', 42)


async def test_comfyui_uses_a_research_workflow_with_placeholders():
    template = {
        '1': {'class_type': 'MyNode', 'inputs': {'text': '{{prompt}}', 'neg': '{{negative}}', 'seed': '{{seed}}'}}
    }
    server = FakeComfy(pending=0)

    image = await comfy(server, workflow=template).generate(ImageRequest(prompt=PROMPT, negative='nsfw', seed=7))

    assert server.submitted[0]['prompt'] == {
        '1': {'class_type': 'MyNode', 'inputs': {'text': PROMPT, 'neg': 'nsfw', 'seed': 7}}
    }
    assert image.seed == 7
    # 바꿔 넣는 것은 글 전체가 자리의 이름일 때만이다. 원본은 그대로다
    assert fill_template({'a': 'x {{prompt}}'}, {'{{prompt}}': 'y'}) == {'a': 'x {{prompt}}'}
    assert template['1']['inputs']['text'] == '{{prompt}}'


def test_a_seed_is_picked_when_none_is_given():
    workflow = filled_workflow(default_workflow(SETTINGS), ImageRequest(prompt=PROMPT), seed=123)

    assert workflow['3']['inputs']['seed'] == 123


@pytest.mark.parametrize(
    ('server', 'request_', 'reason'),
    [
        (FakeComfy(status='error'), ImageRequest(prompt=PROMPT), 'generation_failed'),
        (FakeComfy(prompt_answer={'error': 'x'}), ImageRequest(prompt=PROMPT), 'malformed'),
        (
            FakeComfy(),
            ImageRequest(prompt=PROMPT, references=(ReferenceImage(b'x', 'image/png'),)),
            'references_unsupported',
        ),
    ],
)
async def test_comfyui_failures(server: FakeComfy, request_: ImageRequest, reason: str):
    with pytest.raises(ProviderError, match=reason):
        await comfy(server).generate(request_)


async def test_comfyui_times_out_while_waiting():
    server = FakeComfy(pending=10**9)

    with pytest.raises(ProviderError, match='timeout'):
        await comfy(server, timeout=0.05).generate(ImageRequest(prompt=PROMPT))


async def test_the_fake_image_provider():
    fake = FakeImageProvider()
    no_references = FakeImageProvider(supports_references=False)
    refusing = FakeImageProvider(error='refused')
    request = ImageRequest(prompt=PROMPT, references=(ReferenceImage(b'x', 'image/png'),))

    image = await fake.generate(request)

    assert (image.data, image.mime_type) == (FAKE_PNG, 'image/png') and fake.calls == [request]
    with pytest.raises(ProviderError, match='references_unsupported'):
        await no_references.generate(request)
    with pytest.raises(ProviderError, match='refused'):
        await refusing.generate(ImageRequest(prompt=PROMPT))
