# asset-server/tests/worlds.py

"""
세계관을 보는 테스트가 함께 쓰는 것(#591).

  - bearer: 만드는 사람(운영자)과 남의 토큰
  - character: 게시한(또는 하지 않은) 캐릭터. 세계관의 인물이 가리킨다
  - full_world: 게시할 수 있는 세계관의 칸들. 장소 셋(하나는 닿지 않는다), 물건, 인물 둘, 일정과 조건이 있다
"""

import uuid

from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token

from app.main import API_PREFIX

WORLDS_URL = f'{API_PREFIX}/worlds'
CHARACTERS_URL = f'{API_PREFIX}/characters'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
OWNER = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
STAGES = [{'name': '낯섦', 'at': 0}, {'name': '친함', 'at': 40}, {'name': '연인', 'at': 80}]


def bearer(signing_key: SigningKey, user_id: uuid.UUID, operator: bool = True, adult: bool = False) -> dict:
    """그 사람의 토큰. 1~2단계에는 운영자만 세계관을 만든다."""
    claims = make_access_claims(sub=str(user_id))
    claims['roles'] = ['operator'] if operator else []
    if adult:
        claims['adult_content'] = True
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


async def character(client: AsyncClient, headers: dict, name: str = '아리', published: bool = True, **fields) -> dict:
    """캐릭터 하나. published 면 게시까지 한다."""
    body = {'name': name, 'starts': [START], 'speech_examples': f'{name}의 말투', **fields}
    response = await client.post(CHARACTERS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    made = response.json()
    if published:
        response = await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=headers)
        assert response.status_code == status.HTTP_201_CREATED, response.text
    return made


def member(member_id: str, character_id: str, **fields) -> dict:
    """인물 하나. 호감도의 단계는 셋이다."""
    return {'id': member_id, 'character_id': character_id, 'affection': {'stages': STAGES}, **fields}


# 도서관에 가면 버를 만난다. 선택지 둘이고, 고르는 것마다 효과가 다르다
MEET = {
    'id': 'meet',
    'name': '도서관의 만남',
    'when': {'match': 'all', 'items': [{'kind': 'reach_place', 'target': 'library'}]},
    'scene': {'text': '도서관 구석에서 버가 책을 떨어뜨린다.', 'cast': ['beo', 'ari']},
    'on_open': [{'kind': 'affection', 'target': 'beo', 'amount': 3}],
    'choices': [
        {'id': 'help', 'text': '책을 주워 준다', 'effects': [{'kind': 'affection', 'target': 'beo', 'amount': 5}]},
        {
            'id': 'walk',
            'text': '함께 나간다',
            'effects': [{'kind': 'accompany_start', 'target': 'beo'}, {'kind': 'move_to', 'target': 'school'}],
        },
    ],
}
# 만남을 본 뒤 3일째부터 열린다. 장미를 하나 받는다
CONFESSION_HINT = {
    'id': 'hint',
    'name': '쪽지',
    'when': {'match': 'all', 'items': [{'kind': 'event_seen', 'target': 'meet'}, {'kind': 'day_at_least', 'count': 3}]},
    'scene': {'text': '책 사이에 쪽지가 끼워져 있다.'},
    'on_open': [{'kind': 'give_item', 'target': 'rose', 'amount': 1}],
}


def full_world(ari: str, beo: str) -> dict:
    """
    게시할 수 있는 세계관. 학교(시작), 도서관(길로 이어짐), 옥상(길이 없다)이 있다.
    아리는 도서관에 있고 저녁에는 친하면 학교로 간다. 버는 기본 장소가 없고 이벤트(만남)로만 나온다.
    """
    return {
        'name': '여름 학원',
        'intro_html': '<p>여름 방학의 학원.</p><script>x()</script>',
        'tags': ['학원'],
        'deadline_days': 30,
        'places': [
            {'id': 'school', 'name': '학교', 'backgrounds': {}},
            {'id': 'library', 'name': '도서관'},
            {'id': 'roof', 'name': '옥상'},
        ],
        'paths': [{'a': 'school', 'b': 'library', 'minutes': 10}],
        'start_place': 'school',
        'items': [{'id': 'rose', 'name': '장미'}],
        'start_items': [{'item': 'rose', 'count': 2}],
        'show': {'reveal': 'silhouette', 'map': 'hidden', 'panel': ['intro', 'affection']},
        'cast': [
            member(
                'ari',
                ari,
                home='library',
                schedule=[
                    {
                        'slot': 'evening',
                        'place': 'school',
                        'when': {
                            'match': 'all',
                            'items': [{'kind': 'affection_at_least', 'target': 'ari', 'value': '친함'}],
                        },
                    }
                ],
                affection={'start': 10, 'stages': STAGES, 'gifts': [{'id': 'rose-1', 'item': 'rose', 'change': 5}]},
                reveal='shown',
            ),
            member('beo', beo, map='stage', map_stage='친함'),
        ],
        'events': [MEET, CONFESSION_HINT],
    }


async def create_world(client: AsyncClient, headers: dict, body: dict) -> dict:
    """세계관을 만든다. 만들어져야 한다."""
    response = await client.post(WORLDS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish(client: AsyncClient, headers: dict, world: dict):
    """게시한다. 응답을 그대로 돌려준다."""
    return await client.post(f'{WORLDS_URL}/{world["id"]}/versions', json={}, headers=headers)


async def check(client: AsyncClient, headers: dict, world: dict) -> dict:
    """게시해 보기의 응답."""
    response = await client.get(f'{WORLDS_URL}/{world["id"]}/publish-check', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()
