# board-server/contract/tests/test_boards.py

"""게시판 목록(GET /boards). 게시판은 마이그레이션이 넣은 것이다."""

import httpx

from tests.urls import BOARDS


def test_boards_are_listed_in_order_without_login(client: httpx.Client):
    response = client.get(BOARDS)

    assert response.status_code == httpx.codes.OK
    assert response.json() == [
        {
            'slug': 'notice',
            'name': '공지사항',
            'description': '운영자가 알리는 소식입니다.',
            'write_policy': 'operator',
        },
        {
            'slug': 'event',
            'name': '이벤트',
            'description': '진행 중인 이벤트와 그 결과를 알립니다.',
            'write_policy': 'operator',
        },
        {
            'slug': 'free',
            'name': '자유 게시판',
            'description': '자유롭게 이야기를 나누는 곳입니다.',
            'write_policy': 'member',
        },
        {
            'slug': 'scenario',
            'name': '시나리오 이야기',
            'description': '시나리오에 대한 감상과 이야기를 나누는 곳입니다.',
            'write_policy': 'member',
        },
    ]
