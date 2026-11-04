# story-server/tests/test_snapshot_parts.py

"""
장면 그림(#983)의 조각을 DB 없이 검증한다. 지시 만들기(app/snapshots/prompt.py), 가격표 이름과 provider 고르기
(app/snapshots/providers.py), asset 서버에 맡기고 지우기(app/assets/client.py, 가짜 HTTP).

보는 것.
  - 지시: 지킬 것이 맨 앞, 비어 있는 칸은 뺌, 때와 장소는 엔진의 상태에서, 판에 없는 인물은 뺌, 서술은 글만
  - 가격표 이름은 점을 붙임표로 바꾼다. off 거나 키·체크포인트가 없으면 provider 가 없다
  - 맡기기는 그림의 바이트까지 서명한 POST 이고 201 의 id 를 읽는다. 지우기는 204. 그 밖의 답은 쓸 수 없는 것이다
  - 참고 그림은 장면의 인물의 차례로, 기본 표정 그림이나 대표 그림이다. 그림이 없거나 판에 없는 인물은 빼고 넷까지다.
    지시 끝에 몇 번째 그림이 누구인지 적는다
  - 그림 받기는 서명한 GET 이고 200 의 바이트와 형식을 읽는다. 404 는 없는 것, 그림이 아닌 답은 쓸 수 없는 것이다
"""

import json
import time
import uuid

import httpx
import pytest
from ai_core.comfyui import ComfyUIProvider
from ai_core.fake import FakeImageProvider
from ai_core.gemini_image import GeminiImageProvider
from pydantic import SecretStr
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

from app.assets.client import AssetClient, AssetNotFoundError, AssetUnavailableError, image_content_path, images_path
from app.core.config import Settings
from app.engine.state import StoryState
from app.engine.world import read_world
from app.snapshots.prompt import REFERENCE_RULE, RULES, snapshot_prompt, with_references
from app.snapshots.providers import build_image_provider, price_code_of
from app.snapshots.references import MAX_REFERENCES, ReferenceTarget, cast_targets
from app.turns.briefing import read_briefing
from tests.assets import world_document

SECRET = 'test-asset-secret-0123456789abcdef'
TOKEN = 'user-access-token'
BASE_URL = 'http://asset.test'


def test_the_prompt_comes_from_the_copy_and_the_engine_state():
    document = world_document(
        intro_html='<p>바닷가 마을의 여름.</p>',
        slots=[{'id': 'morning', 'name': '아침', 'start_hour': 7}, {'id': 'night', 'name': '밤', 'start_hour': 19}],
        start_slot='morning',
        places=[{'id': 'beach', 'name': '해변', 'description': '파도 소리'}],
        start_place='beach',
        cast=[
            {'id': 'mina', 'character': {'name': '미나', 'age': '17', 'gender': '여성', 'intro_html': '<p>수영부</p>'}}
        ],
    )
    briefing, world = read_briefing(document), read_world(document)
    state = StoryState(minutes=24 * 60 + 20 * 60, place='beach')
    segments = [
        {'speaker': None, 'text': '바람이 분다.'},
        {'speaker': 'mina', 'text': '왔구나.'},
        {'speaker': 'x', 'text': ' '},
    ]

    prompt = snapshot_prompt(briefing, world, state, ('mina', 'ghost'), segments, None)

    assert prompt.startswith('\n'.join(RULES))
    assert '[세계관]\n이름: 여름 마을\n소개: 바닷가 마을의 여름.' in prompt
    assert '때: 2일째 밤\n장소: 해변 — 파도 소리\n장면의 인물:\n- 미나(나이 17, 성별 여성, 소개 수영부)' in prompt
    assert 'ghost' not in prompt and '사용자:' not in prompt
    assert prompt.endswith('[일어나는 일]\n바람이 분다.\n미나: 왔구나.')
    assert len(snapshot_prompt(briefing, world, state, (), [{'text': '가' * 900}], None)) < 900


def settings(**fields) -> Settings:
    return Settings(database_url='postgresql+asyncpg://u:p@h/db', auth_jwks_url='http://a/api/v1/auth/jwks', **fields)


def test_the_price_code_and_the_provider_choice():
    http = httpx.AsyncClient()

    assert price_code_of('gemini-nano-banana-2.1') == 'image.gemini-nano-banana-2-1'
    assert build_image_provider(settings(), http) is None
    assert build_image_provider(settings(snapshot_provider='gemini'), http) is None
    assert isinstance(build_image_provider(settings(snapshot_provider='fake'), http), FakeImageProvider)
    gemini = build_image_provider(settings(snapshot_provider='gemini', gemini_api_key=SecretStr('k')), http)
    assert isinstance(gemini, GeminiImageProvider) and gemini.model == 'gemini-nano-banana-2.1'
    assert build_image_provider(settings(snapshot_provider='comfyui'), http) is None
    comfy = build_image_provider(settings(snapshot_provider='comfyui', comfyui_checkpoint='sdxl.safetensors'), http)
    assert isinstance(comfy, ComfyUIProvider)


def client_answering(handler) -> AssetClient:
    return AssetClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), BASE_URL, SECRET, 3.0)


async def test_keeping_signs_the_image_bytes():
    seen: list[httpx.Request] = []
    image_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, content=json.dumps({'id': str(image_id), 'format': 'png'}).encode())

    kept = await client_answering(handler).keep_image(TOKEN, b'png-bytes')

    (request,) = seen
    assert (request.method, request.url.path, request.content) == ('POST', images_path(), b'png-bytes')
    assert images_path() == '/api/v1/asset/service/story/images'
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'POST', images_path(), b'png-bytes', time.time())
    assert request.headers['Authorization'] == f'Bearer {TOKEN}'
    assert kept == image_id


async def test_discarding_and_unexpected_answers():
    image_id = uuid.uuid4()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    await client_answering(handler).discard_image(TOKEN, image_id)

    assert (seen[0].method, seen[0].url.path) == ('DELETE', images_path(image_id))
    with pytest.raises(AssetUnavailableError):
        await client_answering(lambda request: httpx.Response(415)).keep_image(TOKEN, b'x')
    with pytest.raises(AssetUnavailableError):
        await client_answering(lambda request: httpx.Response(201, content=b'{}')).keep_image(TOKEN, b'x')
    with pytest.raises(AssetUnavailableError):
        await client_answering(lambda request: httpx.Response(503)).discard_image(TOKEN, image_id)


def test_the_references_follow_the_scene_cast():
    ids = [uuid.uuid4() for _ in range(7)]
    jun = {'name': '', 'image_id': str(ids[1]), 'sprites': [{'id': 'b', 'image_id': str(ids[2])}]}
    cast = [
        {'id': 'mina', 'character': {'name': '미나', 'image_id': str(ids[0])}},
        {'id': 'jun', 'character': jun},
        {'id': 'faceless', 'character': {'name': '얼굴 없음'}},
        *({'id': f'c{n}', 'character': {'name': f'인물{n}', 'image_id': str(ids[n])}} for n in (3, 4, 5)),
    ]
    document = world_document(cast=cast)

    targets = cast_targets(document, ['jun', 'ghost', 'faceless', 'mina', 'jun', 'c3', 'c4', 'c5'])

    assert targets[:2] == (ReferenceTarget(name='jun', image_id=ids[2]), ReferenceTarget(name='미나', image_id=ids[0]))
    assert len(targets) == MAX_REFERENCES == 4 and targets[-1].name == '인물4'
    assert cast_targets(document, []) == ()


def test_the_reference_block_names_each_image_in_order():
    expected = f'지시\n\n[참고 그림]\n1번째 그림: 미나\n2번째 그림: 준\n{REFERENCE_RULE}'
    assert with_references('지시', []) == '지시'
    assert with_references('지시', ['미나', '준']) == expected


async def test_fetching_an_image_reads_its_bytes_and_type():
    image_id = uuid.uuid4()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b'png', headers={'Content-Type': 'image/png'})

    content = await client_answering(handler).fetch_image(TOKEN, image_id)

    (request,) = seen
    assert (request.method, request.url.path) == ('GET', image_content_path(image_id))
    assert image_content_path(image_id) == f'/api/v1/asset/service/story/images/{image_id}/content'
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'GET', image_content_path(image_id), b'', time.time())
    assert request.headers['Authorization'] == f'Bearer {TOKEN}'
    assert (content.data, content.mime_type) == (b'png', 'image/png')


@pytest.mark.parametrize(
    ('answer', 'error'),
    [
        (httpx.Response(404), AssetNotFoundError),
        (httpx.Response(503), AssetUnavailableError),
        (httpx.Response(200, content=b'{}', headers={'Content-Type': 'application/json'}), AssetUnavailableError),
        (httpx.Response(200, content=b'', headers={'Content-Type': 'image/png'}), AssetUnavailableError),
    ],
)
async def test_fetching_an_image_that_is_missing_or_not_an_image(answer: httpx.Response, error: type[Exception]):
    with pytest.raises(error):
        await client_answering(lambda request: answer).fetch_image(TOKEN, uuid.uuid4())
