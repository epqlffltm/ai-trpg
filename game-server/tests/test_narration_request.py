# game-server/tests/test_narration_request.py

"""
서술자에게 줄 각자 한 일을 라운드에 굳히고 다시 읽는 것(app/rounds/narration_request.py)을 검증한다.

DB 를 쓰지 않는다. 굳힌 모양이 JSON 칸에 들어가고, 읽으면 처음 것과 같아지는지만 본다.
닫는 동안 누가 나가도 서술자가 닫힐 때의 모습을 받는지는 tests/test_round_closing.py 가 본다.

지난 라운드를 서술자에게 줄 모양으로 바꾸는 것(to_past)도 여기서 본다. 굳혀 둔 것에서 한 말을 읽는다.
"""

import json

import pytest
from pydantic import ValidationError

from app.rounds.models import Declaration, Round
from app.rounds.narration_request import dump_moves, read_moves, to_past
from app.rounds.narrator import DeathSaveNote, Impact, Move, PastRound, Verdict

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


# --- 지난 라운드의 한 말 ---


def make_verdict(success: bool) -> Verdict:
    return Verdict(ability='민첩', difficulty='보통', roll=10, modifier=0, total=10, target=10, success=success)


def declared(name: str, content: str, success: bool | None = None) -> Declaration:
    """선언 하나. success 를 주면 판정의 결과가 적힌 선언이다."""
    outcome = None if success is None else {'success': success}
    return Declaration(character_name=name, content=content, outcome=outcome)


def closed_round(moves: list[Move] | None, *declarations: Declaration) -> Round:
    """닫기 시작한 라운드. moves 가 None 이면 굳혀 두는 칸이 생기기 전의 옛 라운드다."""
    kept = None if moves is None else dump_moves(moves)
    return Round(number=2, scene='차단기가 내려와 있다.', moves=kept, declarations=list(declarations))


def test_what_was_said_is_read_from_the_kept_moves():
    moves = [
        Move(character_name='엘프', content='차단기를 뛰어넘는다.', verdict=make_verdict(False)),
        Move(character_name='드워프', content='망치를 휘두른다.', verdict=make_verdict(True)),
        Move(character_name='영애', content='구경한다.'),
    ]

    past = to_past(closed_round(moves))

    assert past == PastRound(
        number=2,
        scene='차단기가 내려와 있다.',
        lines=['엘프: 차단기를 뛰어넘는다.', '드워프: 망치를 휘두른다.', '영애: 구경한다.'],
        # 판정이 없던 선언은 지우지 않는다. 성공도 실패도 아닐 뿐이다
        successes=[False, True, None],
    )


def test_someone_who_did_not_declare_has_no_line():
    moves = [Move(character_name='엘프', content='달린다.'), Move(character_name='드워프', content=None, downed=True)]

    past = to_past(closed_round(moves))

    assert (past.lines, past.successes) == (['엘프: 달린다.'], [None])


def test_a_declaration_left_out_of_the_kept_moves_is_not_what_was_said():
    # 영애는 선언을 내고 마감 전에 나갔다. 선언은 기록에 남지만, 판정도 서술도 받지 않았다
    moves = [Move(character_name='엘프', content='달린다.')]
    round_ = closed_round(moves, declared('영애', '드워프를 공격한다.'), declared('엘프', '달린다.'))

    assert to_past(round_).lines == ['엘프: 달린다.']


def test_what_someone_said_stays_after_they_leave_once_it_is_kept():
    # 영애는 마감 뒤에 나갔다. 굳혀 둔 것에 있으므로, 지금 앉아 있지 않아도 지난 일에 남는다
    moves = [Move(character_name='엘프', content='달린다.'), Move(character_name='영애', content='손을 흔든다.')]

    assert to_past(closed_round(moves)).lines == ['엘프: 달린다.', '영애: 손을 흔든다.']


def test_an_old_round_without_kept_moves_is_read_from_its_declarations():
    round_ = closed_round(None, declared('엘프', '차단기를 넘는다.', success=False), declared('영애', '인사한다.'))

    past = to_past(round_)

    assert (past.lines, past.successes) == (['엘프: 차단기를 넘는다.', '영애: 인사한다.'], [False, None])


def test_kept_moves_from_before_a_newer_field_can_still_be_read():
    # 굳힌 뒤에 생긴 칸(부상 등)이 없는 옛 문서다. 지난 라운드를 읽다가 멈추면 안 된다
    old = [{'character_name': '엘프', 'content': '달린다.', 'verdict': {'success': True}}]
    round_ = Round(number=2, scene='장면', moves=old, declarations=[])

    past = to_past(round_)

    assert (past.lines, past.successes) == (['엘프: 달린다.'], [True])


def test_a_round_nobody_declared_in_has_no_lines():
    assert to_past(closed_round([Move(character_name='엘프', content=None)])).lines == []
