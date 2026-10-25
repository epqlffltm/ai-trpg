# board-server/contract/tests/test_errors.py

"""
오류 응답의 모양(board-server/test/errors.e2e-spec.ts). 예외를 응답으로 바꾸는 규칙과 입력 검사가
실제 주소에 걸려 있는지 본다. 오류는 {"detail"}, 입력 오류는 {"detail", "errors"} 와 400 이다.
"""

import httpx

from tests.urls import API, board_posts

INVALID_INPUT = '입력이 올바르지 않습니다.'


def test_unknown_path_is_404_without_echoing_path(client: httpx.Client):
    response = client.get(f'{API}/no-such-api')

    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '찾을 수 없습니다.'}


def test_broken_json_is_400_without_parser_message(client: httpx.Client, me: dict[str, str]):
    response = client.post(
        board_posts('free'),
        headers={**me, 'Content-Type': 'application/json'},
        content='{"title": "첫 글", '.encode(),
    )

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {'detail': '요청이 올바르지 않습니다.'}


def test_invalid_input_is_400_with_field_errors(client: httpx.Client, me: dict[str, str]):
    response = client.post(board_posts('free'), headers=me, json={'title': '   ', 'content': '본문'})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {'detail': INVALID_INPUT, 'errors': {'title': ['제목을 적어야 합니다.']}}


def test_unknown_field_is_400(client: httpx.Client, me: dict[str, str]):
    # 모르는 칸을 조용히 버리지 않는다. 칸 이름을 잘못 적은 클라이언트가 알 수 있게 한다
    response = client.post(board_posts('free'), headers=me, json={'title': '글', 'content': '본문', 'colour': 'red'})

    assert response.status_code == httpx.codes.BAD_REQUEST
    body = response.json()
    assert body['detail'] == INVALID_INPUT
    assert 'colour' in body['errors']
