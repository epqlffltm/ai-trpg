# chat-server/tests/test_snapshot_parts.py

"""
장면 그림(#983)의 조각을 DB 없이 검증한다. 지시 만들기(app/snapshots/prompt.py), 가격표 이름과 provider 고르기
(app/snapshots/providers.py), asset 서버에 맡기고 지우기(app/assets/client.py, 가짜 HTTP).

보는 것.
  - 지시: 지킬 것이 맨 앞, 비어 있는 칸은 뺌, 장소와 차림은 서버의 상태에서, 답과 사람의 말은 앞의 몇 글자만
  - 가격표 이름은 점을 붙임표로 바꾼다. off 거나 키·체크포인트가 없으면 provider 가 없다
  - 맡기기는 그림의 바이트까지 서명한 POST 이고 201 의 id 를 읽는다. 지우기는 204. 그 밖의 답은 쓸 수 없는 것이다
  - 참고 그림은 지금 차림의 기본 그림, 없으면 대표 그림이다. 지시 끝에 몇 번째 그림이 누구인지 적는다
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
from app.assets.schemas import ItemDocument, PlaceDocument, SpriteDocument
from app.core.config import Settings
from app.snapshots.prompt import ANSWER_CHARS, REFERENCE_RULE, RULES, snapshot_prompt, with_references
from app.snapshots.providers import build_image_provider, price_code_of
from app.snapshots.references import ReferenceTarget, character_targets
from app.world.state import WorldState
from tests.assets import make_character

SECRET = 'test-asset-secret-0123456789abcdef'
TOKEN = 'user-access-token'
BASE_URL = 'http://asset.test'


def test_the_prompt_comes_from_the_copy_and_the_server_state():
    document = make_character(
        world={
            'places': [PlaceDocument(id='lib', name='도서관', description='높은 책장', image_id=None)],
            'items': [ItemDocument(id='scarf', name='목도리', description='', kind='clothing', image_id=None)],
        }
    ).document
    state = WorldState(place='lib', minutes=0, inventory=(), visited=('lib',), outfit=('scarf',))

    prompt = snapshot_prompt(document, state, 21, '가' * (ANSWER_CHARS + 50), None)

    assert prompt.startswith('\n'.join(RULES))
    assert '[인물]\n이름: 세라\n나이: 스물넷\n성별: 여성\n소개: 도서관의 사서.' in prompt
    assert '장소: 도서관 — 높은 책장' in prompt and '상대의 차림: 목도리' in prompt and '21:00' in prompt
    assert '가' * ANSWER_CHARS in prompt and '가' * (ANSWER_CHARS + 1) not in prompt
    assert '사용자:' not in prompt


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
    assert images_path() == '/api/v1/asset/service/chat/images'
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


def test_the_reference_is_the_current_outfit_or_the_portrait():
    sprite = uuid.uuid4()
    plain = make_character().document
    dressed = make_character(world={'sprites': [SpriteDocument(id='base', image_id=sprite)]}).document
    faceless = plain.model_copy(update={'image_id': None})
    state = WorldState(place=None, minutes=0, inventory=(), visited=(), outfit=())

    assert character_targets(plain, state) == (ReferenceTarget(name='세라', image_id=plain.image_id),)
    assert character_targets(dressed, state) == (ReferenceTarget(name='세라', image_id=sprite),)
    assert character_targets(faceless, state) == ()


def test_the_reference_block_names_each_image_in_order():
    assert with_references('지시', []) == '지시'
    expected = f'지시\n\n[참고 그림]\n1번째 그림: 세라\n2번째 그림: 미나\n{REFERENCE_RULE}'
    assert with_references('지시', ['세라', '미나']) == expected


async def test_fetching_an_image_reads_its_bytes_and_type():
    image_id = uuid.uuid4()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b'png', headers={'Content-Type': 'image/png'})

    content = await client_answering(handler).fetch_image(TOKEN, image_id)

    (request,) = seen
    assert (request.method, request.url.path) == ('GET', image_content_path(image_id))
    assert image_content_path(image_id) == f'/api/v1/asset/service/chat/images/{image_id}/content'
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
