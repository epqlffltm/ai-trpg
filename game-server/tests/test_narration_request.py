# game-server/tests/test_narration_request.py

"""
서술자에게 줄 각자 한 일을 라운드에 굳히고 다시 읽는 것(app/rounds/narration_request.py)을 검증한다.

DB 를 쓰지 않는다. 굳힌 모양이 JSON 칸에 들어가고, 읽으면 처음 것과 같아지는지만 본다.
닫는 동안 누가 나가도 서술자가 닫힐 때의 모습을 받는지는 tests/test_round_closing.py 가 본다.
"""

import json

import pytest
from pydantic import ValidationError

from app.rounds.narration_request import dump_moves, read_moves
from app.rounds.narrator import DeathSaveNote, Impact, Move, Verdict

# 칸을 빠짐없이 채운 행동들. 판정과 HP 의 변화, 죽음의 굴림, 새로 들어온 캐릭터가 모두 있다
MOVES = [
    Move(
        character_name='엘프',
        content='바이크로 톨게이트를 뛰어넘는다.',
        verdict=Verdict(
            ability='민첩',
            difficulty='어려움',
            roll=6,
            modifier=-1,
            total=5,
            target=20,
            success=False,
            impact=Impact(kind='damage', character_name='엘프', amount=4, hp=0, max_hp=9, downed=True),
        ),
        downed=True,
    ),
    Move(
        character_name='드워프',
        content=None,
        downed=True,
        death_save=DeathSaveNote(roll=3, target=10, success=False, successes=0, failures=3, fate='dead'),
        dead=True,
    ),
    Move(character_name='영애', content=None, replaces='악역영애'),
]


def test_moves_come_back_as_they_were_kept():
    assert read_moves(dump_moves(MOVES)) == MOVES


def test_kept_moves_survive_a_trip_through_json():
    # DB 의 JSON 칸에 들어갔다 나온 것과 같다
    stored = json.loads(json.dumps(dump_moves(MOVES)))

    assert read_moves(stored) == MOVES


def test_no_moves_are_kept_as_an_empty_list():
    assert dump_moves([]) == []
    assert read_moves([]) == []


@pytest.mark.parametrize(
    'data',
    [
        [{'content': '이름이 없다.'}],
        [{'character_name': '엘프', 'content': None, 'verdict': {'ability': '민첩'}}],
        [{'character_name': '엘프', 'content': None, 'death_save': '죽음'}],
        {'character_name': '엘프', 'content': None},
    ],
)
def test_kept_moves_of_the_wrong_shape_are_refused(data):
    # 우리가 쓴 문서다. 모양이 틀렸으면 버그다. 틀린 채로 서술자에게 넘기지 않는다
    with pytest.raises(ValidationError):
        read_moves(data)
