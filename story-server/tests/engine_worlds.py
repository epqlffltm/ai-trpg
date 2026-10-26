# story-server/tests/engine_worlds.py

"""
엔진의 테스트가 쓰는 판. asset 서버가 굳힌 판의 문서(형식 3)와 같은 모양의 dict 를 만든다.
"""

from app.engine.clock import MINUTES_PER_DAY, MINUTES_PER_HOUR
from app.engine.world import World, read_world


def clock(day: int, hour: int, minute: int = 0) -> int:
    """day 일째 hour 시 minute 분의 시각(1일째 0시부터 흐른 분)."""
    return (day - 1) * MINUTES_PER_DAY + hour * MINUTES_PER_HOUR + minute


def member(
    cast_id: str,
    home: str | None = None,
    schedule: list | None = None,
    start: int = 0,
    confession: dict | None = None,
    gifts: list[dict] | None = None,
) -> dict:
    """인물 하나. 단계는 낯섦(0), 친함(30), 연인(70)이다. gifts 는 선물의 규칙들이다(gift)."""
    return {
        'id': cast_id,
        'character': {'name': cast_id},
        'home': home,
        'schedule': schedule or [],
        'affection': {
            'display': 'stage',
            'start': start,
            'stages': [{'name': '낯섦', 'at': 0}, {'name': '친함', 'at': 30}, {'name': '연인', 'at': 70}],
            'gifts': gifts or [],
        },
        'reveal': 'shown',
        'map': 'shown',
        'map_stage': None,
        'panel': ['intro'],
        'confession': confession,
    }


def line(slot: str, place: str, *items: dict, match: str = 'all') -> dict:
    """일정의 줄 하나. 조건은 items 다."""
    return {'slot': slot, 'place': place, 'when': {'match': match, 'items': list(items)}}


def condition(kind: str, target: str | None = None, value: str | None = None, count: int = 1) -> dict:
    """조건 하나."""
    return {'kind': kind, 'target': target, 'value': value, 'count': count}


def effect(kind: str, target: str, amount: int | None = None) -> dict:
    """효과 하나."""
    return {'kind': kind, 'target': target, 'amount': amount}


def event(
    event_id: str,
    *items: dict,
    match: str = 'all',
    repeat: bool = False,
    cast: list[str] | None = None,
    on_open: list[dict] | None = None,
    choices: list[dict] | None = None,
) -> dict:
    """이벤트 하나. 조건은 items 다. choices 는 {'id', 'text', 'effects'} 의 목록이다."""
    return {
        'id': event_id,
        'name': event_id,
        'when': {'match': match, 'items': list(items)},
        'repeat': repeat,
        'scene': {'text': f'{event_id} 의 장면.', 'cast': cast or [], 'image_id': None, 'collectible': False},
        'on_open': on_open or [],
        'choices': choices or [],
    }


def gift(gift_id: str, item: str, change: int, once: bool = False) -> dict:
    """선물의 규칙 하나."""
    return {'id': gift_id, 'item': item, 'change': change, 'once': once}


def confession(stage: str = '친함', *items: dict, on_fail: str = 'continue', drop: int = 10, days: int = 1) -> dict:
    """고백 하나. 조건은 items 다."""
    return {
        'stage': stage,
        'when': {'match': 'all', 'items': list(items)},
        'on_fail': on_fail,
        'fail_drop': drop,
        'cooldown_days': days,
    }


def ending(ending_id: str, kind: str, target: str | None = None, *items: dict, unlock: bool = True) -> dict:
    """엔딩 하나. 조건은 items 다."""
    return {
        'id': ending_id,
        'name': ending_id,
        'trigger': {'kind': kind, 'target': target},
        'when': {'match': 'all', 'items': list(items)},
        'scene': {'text': f'{ending_id} 의 장면.', 'cast': [], 'image_id': None, 'collectible': False},
        'unlock': unlock,
        'hint': '',
    }


def document(cast: list[dict] | None = None, events: list[dict] | None = None, **fields) -> dict:
    """판의 문서. 시간대는 아침(7시), 낮(12시), 밤(19시)이고 집에서 아침에 시작한다."""
    body = {
        'format': 3,
        'name': '여름 마을',
        'intro_html': '',
        'tags': [],
        'rating': 'all',
        'image_id': None,
        'slots': [
            {'id': 'morning', 'name': '아침', 'start_hour': 7},
            {'id': 'day', 'name': '낮', 'start_hour': 12},
            {'id': 'night', 'name': '밤', 'start_hour': 19},
        ],
        'start_slot': 'morning',
        'deadline_days': None,
        'after_ending': 'end',
        'places': [],
        'paths': [],
        'start_place': 'home',
        'items': [],
        'start_items': [],
        'cast': cast or [],
        'lorebooks': [],
        'events': events or [],
        'endings': [],
    }
    body.update(fields)
    return body


def world(cast: list[dict] | None = None, events: list[dict] | None = None, **fields) -> World:
    """엔진이 읽은 판."""
    return read_world(document(cast, events, **fields))
