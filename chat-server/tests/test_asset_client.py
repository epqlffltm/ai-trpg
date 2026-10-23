# chat-server/tests/test_asset_client.py

"""
asset 서버를 부르는 것(app/assets/client.py)을 검증한다. 가짜 HTTP(httpx.MockTransport)로 돈다. DB 를 쓰지 않는다.

보는 것.
  - 주소와 서명: 이 서버의 이름(chat)의 주소로, 이 서버의 비밀로 서명하고(asset 서버의 is_valid 로 확인한다),
    사용자의 토큰을 함께 넘긴다
  - 답: 200 은 그 모양으로 읽는다. 형식 2 의 지도와 물건, 형식 3 의 호감도, 형식 4 의 시작 시각과 시간대 배경은 남긴다.
    앞 형식의 판에서는 비어 있다(시작 시각은 정오).
    404, 403 adult_content_required 는 각각의 예외다.
    그 밖의 답, 모양이 틀린 답, 닿지 못함, 주소가 없음은 모두 AssetUnavailableError 다
"""

import json
import time
import uuid

import httpx
import pytest
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

from app.assets.client import (
    AssetAdultRequiredError,
    AssetClient,
    AssetNotFoundError,
    AssetUnavailableError,
    character_path,
    persona_path,
)
from tests.assets import make_character, make_persona

SECRET = 'test-asset-secret-0123456789abcdef'
TOKEN = 'user-access-token'
BASE_URL = 'http://asset.test'


def client_answering(handler, base_url: str = BASE_URL + '/') -> AssetClient:
    return AssetClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), base_url, SECRET, 3.0)


def answer(status_code: int, body: object) -> httpx.Response:
    return httpx.Response(status_code, content=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})


async def test_a_character_is_fetched_with_a_signature_and_the_token():
    copy = make_character()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(200, copy.model_dump(mode='json'))

    fetched = await client_answering(handler).fetch_character(TOKEN, copy.id)

    (request,) = seen
    path = f'/api/v1/asset/service/chat/characters/{copy.id}/latest'
    assert (request.method, str(request.url)) == ('GET', BASE_URL + path)
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'GET', path, b'', time.time())
    assert request.headers['Authorization'] == f'Bearer {TOKEN}'
    assert request.extensions['timeout']['read'] == 3.0
    assert fetched == copy


async def test_a_persona_is_fetched_from_its_address():
    copy = make_persona()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f'/api/v1/asset/service/chat/personas/{copy.id}'
        return answer(200, copy.model_dump(mode='json'))

    assert await client_answering(handler).fetch_persona(TOKEN, copy.id) == copy


def test_the_paths_carry_this_servers_name():
    some_id = uuid.UUID(int=1)

    assert character_path(some_id) == f'/api/v1/asset/service/chat/characters/{some_id}/latest'
    assert persona_path(some_id) == f'/api/v1/asset/service/chat/personas/{some_id}'


async def test_unknown_fields_in_the_answer_are_ignored():
    copy = make_character()
    body = copy.model_dump(mode='json')
    body['later_field'] = 1
    body['document']['later_field'] = 2

    fetched = await client_answering(lambda request: answer(200, body)).fetch_character(TOKEN, copy.id)

    assert fetched == copy


# asset 서버의 형식 2 의 판에 든 지도와 물건
WORLD = {
    'places': [{'id': 'library', 'name': '도서관', 'description': '', 'image_id': None}],
    'paths': [],
    'start_place': 'library',
    'items': [
        {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'consumable': False, 'image_id': None}
    ],
    'start_items': [{'item': 'scarf', 'count': 1}],
}


async def test_the_map_and_items_of_a_format_two_version_are_kept():
    copy = make_character()
    body = copy.model_dump(mode='json')
    body['document'] |= {'format': 2, **WORLD}

    fetched = await client_answering(lambda request: answer(200, body)).fetch_character(TOKEN, copy.id)

    # 대화가 판을 복사할 때 이 모양으로 적는다(모르는 칸은 버리므로 여기에 있어야 남는다)
    kept = fetched.document.model_dump(mode='json')
    # 시간대 배경은 형식 4 에서 더했다. 앞 형식의 장소에는 없다(빈 것으로 읽는다)
    places = [{**place, 'backgrounds': {}} for place in WORLD['places']]
    assert {name: kept[name] for name in WORLD} == {**WORLD, 'places': places}


async def test_the_affection_of_a_format_three_version_is_kept():
    copy = make_character()
    body = copy.model_dump(mode='json')
    affection = {
        'display': 'stage',
        'start': 10,
        'stages': [{'name': '낯섦', 'at': 0}],
        'rules': [{'id': 'gift', 'on': {'kind': 'give_item', 'target': 'scarf'}, 'change': 5, 'once': True}],
    }
    body['document'] |= {'format': 3, 'affection': affection}

    fetched = await client_answering(lambda request: answer(200, body)).fetch_character(TOKEN, copy.id)

    assert fetched.document.model_dump(mode='json')['affection'] == affection
    assert make_character().document.affection is None


async def test_the_start_hours_and_backgrounds_of_a_format_four_version_are_kept():
    copy = make_character()
    body = copy.model_dump(mode='json')
    night = str(uuid.UUID(int=7))
    starts = [{'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.', 'hour': 21}]
    places = [{**WORLD['places'][0], 'backgrounds': {'night': night, 'later_time': night}}]
    body['document'] |= {'format': 4, **WORLD, 'starts': starts, 'places': places}

    fetched = await client_answering(lambda request: answer(200, body)).fetch_character(TOKEN, copy.id)

    kept = fetched.document.model_dump(mode='json')
    # 모르는 시간대도 받아 둔다(쓰이지 않을 뿐이다)
    assert (kept['starts'], kept['places']) == (starts, places)


async def test_a_format_three_version_starts_at_noon():
    copy = make_character()
    body = copy.model_dump(mode='json')
    body['document'] |= {'format': 3, 'starts': [{'title': '오후', 'situation': '햇살이 든다.'}]}

    fetched = await client_answering(lambda request: answer(200, body)).fetch_character(TOKEN, copy.id)

    assert fetched.document.starts[0].hour == 12


async def test_a_format_one_version_has_no_map_or_items():
    copy = make_character()
    body = copy.model_dump(mode='json')
    for name in WORLD:
        del body['document'][name]

    fetched = await client_answering(lambda request: answer(200, body)).fetch_character(TOKEN, copy.id)

    assert (fetched.document.places, fetched.document.start_place, fetched.document.start_items) == ([], None, [])


@pytest.mark.parametrize(
    ('status_code', 'body', 'error'),
    [
        (404, {'detail': '찾을 수 없습니다.'}, AssetNotFoundError),
        (403, {'detail': '성인', 'code': 'adult_content_required'}, AssetAdultRequiredError),
        (403, {'detail': '다른 까닭'}, AssetUnavailableError),
        (403, ['not', 'an', 'object'], AssetUnavailableError),
        (401, {'detail': '요청의 서명이 맞지 않습니다.'}, AssetUnavailableError),
        (500, {'detail': '오류'}, AssetUnavailableError),
        (200, {'id': 'not the shape'}, AssetUnavailableError),
    ],
    ids=['not-found', 'adult', 'other-403', 'odd-403', 'bad-signature', 'server-error', 'bad-shape'],
)
async def test_answers_become_errors(status_code: int, body: object, error: type[Exception]):
    asset = client_answering(lambda request: answer(status_code, body))

    with pytest.raises(error):
        await asset.fetch_character(TOKEN, uuid.uuid4())


@pytest.mark.parametrize('status_code', [202, 500])
async def test_only_200_is_read_even_if_the_body_fits(status_code: int):
    copy = make_character()
    asset = client_answering(lambda request: answer(status_code, copy.model_dump(mode='json')))

    with pytest.raises(AssetUnavailableError):
        await asset.fetch_character(TOKEN, copy.id)


async def test_the_adult_code_counts_only_on_403():
    asset = client_answering(lambda request: answer(500, {'code': 'adult_content_required'}))

    with pytest.raises(AssetUnavailableError):
        await asset.fetch_character(TOKEN, uuid.uuid4())


async def test_a_403_that_is_not_json_is_unavailable():
    asset = client_answering(lambda request: httpx.Response(403, content=b'<html>'))

    with pytest.raises(AssetUnavailableError):
        await asset.fetch_character(TOKEN, uuid.uuid4())


async def test_not_reaching_it_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('닿지 않는다', request=request)

    with pytest.raises(AssetUnavailableError):
        await client_answering(handler).fetch_persona(TOKEN, uuid.uuid4())


async def test_without_an_address_nothing_is_called():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return answer(200, {})

    with pytest.raises(AssetUnavailableError):
        await client_answering(handler, base_url='').fetch_character(TOKEN, uuid.uuid4())
    assert calls == []
