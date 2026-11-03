# story-server/tests/test_shortcut_calls.py

"""
단축어를 부르는 말을 읽는 것(app/shortcuts/calls.py)과 asset 서버에서 내 단축어를 가져오는 것을 검증한다.
DB 를 쓰지 않는다. asset 서버는 가짜 HTTP(httpx.MockTransport)다.

보는 것.
  - 맨 앞의 "/이름"만 부른 것이다. 이름은 빈칸과 / 가 없는 10자까지이고 뒤는 빈칸이나 끝이다
  - 작품의 것이 먼저이고, 본문은 400자까지만 붙는다. 빈 본문은 붙이지 않는다
  - 모델에 보낼 글: 그 턴이면 본문이 붙고, 지난 말이면 이름을 뗀다
  - 내 단축어는 서명한 GET 으로 가져오고, 모양이 틀리면 쓸 수 없는 것이다
"""

import json
import time

import httpx
import pytest
from server_core.service_auth.signing import SIGNATURE_HEADER, is_valid

from app.assets.client import AssetClient, AssetUnavailableError, shortcuts_path
from app.assets.schemas import ShortcutDocument
from app.shortcuts.calls import (
    SHORTCUT_BODY_MAX_CHARS,
    Call,
    body_for,
    choosable,
    model_text,
    split_call,
)

SECRET = 'test-asset-secret-0123456789abcdef'
TOKEN = 'user-access-token'
BASE_URL = 'http://asset.test'


def shortcut(name: str, body: str = '본문.', description: str = '') -> ShortcutDocument:
    return ShortcutDocument(name=name, description=description, body=body)


@pytest.mark.parametrize(
    ('content', 'expected'),
    [
        ('/일기', Call('일기', '')),
        ('/일기 비가 왔어 ', Call('일기', '비가 왔어')),
        ('  /일기\n비가 왔어', Call('일기', '비가 왔어')),
        ('/abcdefghij 끝', Call('abcdefghij', '끝')),
        ('/abcdefghijk', None),
        ('/일기/회상', None),
        ('/ 일기', None),
        ('일기 /일기', None),
        ('//일기', None),
    ],
)
def test_only_a_leading_name_is_a_call(content: str, expected: Call | None):
    assert split_call(content) == expected


def test_the_work_wins_and_the_body_is_clipped():
    work = [shortcut('일기', '작품의 일기.')]
    mine = [shortcut('일기', '내 일기.'), shortcut('독백', 'x' * (SHORTCUT_BODY_MAX_CHARS + 5)), shortcut('빈', '  ')]

    assert body_for('/일기', work, mine) == '작품의 일기.'
    assert body_for('/독백', work, mine) == 'x' * SHORTCUT_BODY_MAX_CHARS
    assert body_for('/빈 안녕', work, mine) is None
    assert body_for('/없음', work, mine) is None
    assert body_for('안녕', work, mine) is None


def test_the_list_drops_my_shortcut_with_the_works_name():
    work = [shortcut('일기'), shortcut('회상')]
    mine = [shortcut('일기'), shortcut('독백')]

    assert [(item.name, from_work) for item, from_work in choosable(work, mine)] == [
        ('일기', True),
        ('회상', True),
        ('독백', False),
    ]


def test_the_model_text_has_the_body_only_on_its_turn():
    assert model_text('/일기 비', '본문.', current=True) == '비\n\n[단축어] 본문.'
    assert model_text('/일기', '본문.', current=True) == '[단축어] 본문.'
    assert model_text('/일기 비', '본문.', current=False) == '비'
    assert model_text('/일기', '본문.', current=False) == '/일기'
    # 단축어를 쓰지 않은 말은 그대로다
    assert model_text('/없음 비', None, current=True) == '/없음 비'


async def test_my_shortcuts_are_fetched_with_a_signature():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {'items': [{'name': '일기', 'description': '', 'body': '본문.'}]}
        return httpx.Response(200, content=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})

    client = AssetClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), BASE_URL, SECRET, 3.0)
    found = await client.fetch_shortcuts(TOKEN)

    (request,) = seen
    assert shortcuts_path() == '/api/v1/asset/service/story/shortcuts'
    assert str(request.url) == BASE_URL + shortcuts_path()
    assert is_valid(SECRET, request.headers[SIGNATURE_HEADER], 'GET', shortcuts_path(), b'', time.time())
    assert request.headers['Authorization'] == f'Bearer {TOKEN}'
    assert [item.name for item in found.items] == ['일기']


async def test_a_wrong_shape_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"items": [{"name": "x"}]}', headers={'Content-Type': 'application/json'})

    client = AssetClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)), BASE_URL, SECRET, 3.0)
    with pytest.raises(AssetUnavailableError):
        await client.fetch_shortcuts(TOKEN)
